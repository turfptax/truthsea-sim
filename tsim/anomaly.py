"""Bayesian anomaly classification.

Classifies quanta as:
  - fabrication:       likely fake/invented data
  - genuine:           legitimate finding
  - misinterpretation: real data, wrong conclusion

Uses evidence count, source diversity, moral vector magnitude,
and agent agreement rate as features.
"""

import math
import sqlite3
from typing import Optional


# Prior probabilities (can be tuned)
PRIORS = {
    "fabrication": 0.10,
    "genuine": 0.75,
    "misinterpretation": 0.15,
}


def classify_anomaly(
    quanta: dict,
    verifications: list[dict],
    db: sqlite3.Connection,
    run_id: int,
    round_num: int = 0,
) -> dict:
    """Bayesian classification of a quanta as fabrication/genuine/misinterpretation.

    Returns dict with probabilities for each class and the winning classification.
    """
    # Gather features
    evidence_count = _count_evidence(quanta["id"], db)
    source_diversity = _source_diversity(quanta["id"], db)
    moral_magnitude = _moral_vector_magnitude(quanta)
    agreement_rate = _agreement_rate(verifications)
    flag_rate = _flag_rate(verifications)
    score = quanta.get("intrinsic_score", 50)

    # Compute likelihoods for each class
    likelihoods = {
        "fabrication": _fabrication_likelihood(
            evidence_count, source_diversity, moral_magnitude,
            agreement_rate, flag_rate, score,
        ),
        "genuine": _genuine_likelihood(
            evidence_count, source_diversity, moral_magnitude,
            agreement_rate, flag_rate, score,
        ),
        "misinterpretation": _misinterpretation_likelihood(
            evidence_count, source_diversity, moral_magnitude,
            agreement_rate, flag_rate, score,
        ),
    }

    # Bayes' theorem: P(class|data) = P(data|class) * P(class) / P(data)
    posteriors = {}
    total = 0.0
    for cls in PRIORS:
        p = likelihoods[cls] * PRIORS[cls]
        posteriors[cls] = p
        total += p

    # Normalize
    if total > 0:
        for cls in posteriors:
            posteriors[cls] /= total
    else:
        posteriors = dict(PRIORS)

    # Round
    posteriors = {k: round(v, 4) for k, v in posteriors.items()}
    classification = max(posteriors, key=posteriors.get)

    # Store if not genuine with high probability
    if classification != "genuine" or posteriors.get("fabrication", 0) > 0.3:
        flagging_agent = None
        if verifications:
            # Find the agent who flagged (if any)
            flaggers = [v for v in verifications if v["verdict"] == "flag"]
            if flaggers:
                flagging_agent = flaggers[0].get("agent_id")

        db.execute(
            """INSERT INTO anomaly_flag
               (quanta_id, run_id, flag_type, probability, flagged_by_agent, round)
               VALUES (?,?,?,?,?,?)""",
            (
                quanta["id"], run_id, classification,
                posteriors[classification], flagging_agent, round_num,
            ),
        )

    return {
        "quanta_id": quanta["id"],
        "classification": classification,
        "posteriors": posteriors,
        "features": {
            "evidence_count": evidence_count,
            "source_diversity": source_diversity,
            "moral_magnitude": round(moral_magnitude, 2),
            "agreement_rate": round(agreement_rate, 3),
            "flag_rate": round(flag_rate, 3),
            "intrinsic_score": score,
        },
    }


def _count_evidence(quanta_id: str, db: sqlite3.Connection) -> int:
    row = db.execute(
        "SELECT COUNT(*) as cnt FROM evidence_source WHERE quanta_id=?",
        (quanta_id,),
    ).fetchone()
    return row["cnt"] if row else 0


def _source_diversity(quanta_id: str, db: sqlite3.Connection) -> int:
    """Count distinct source types for this quanta."""
    row = db.execute(
        "SELECT COUNT(DISTINCT source_type) as cnt FROM evidence_source WHERE quanta_id=?",
        (quanta_id,),
    ).fetchone()
    return row["cnt"] if row else 0


def _moral_vector_magnitude(quanta: dict) -> float:
    """L2 norm of the 8 moral vector dimensions."""
    keys = [
        "moral_care", "moral_fairness", "moral_loyalty", "moral_authority",
        "moral_sanctity", "moral_liberty", "moral_epistemic_humility",
        "moral_temporal_stewardship",
    ]
    return math.sqrt(sum(quanta.get(k, 0) ** 2 for k in keys))


def _agreement_rate(verifications: list[dict]) -> float:
    """Fraction of verifications that are 'accept'."""
    if not verifications:
        return 0.5
    accepts = sum(1 for v in verifications if v["verdict"] == "accept")
    return accepts / len(verifications)


def _flag_rate(verifications: list[dict]) -> float:
    """Fraction of verifications that are 'flag'."""
    if not verifications:
        return 0.0
    flags = sum(1 for v in verifications if v["verdict"] == "flag")
    return flags / len(verifications)


def _fabrication_likelihood(
    evidence_count, source_diversity, moral_magnitude,
    agreement_rate, flag_rate, score,
) -> float:
    """Higher when: few evidence, low diversity, low agreement, high flags, low score."""
    l = 1.0
    # Less evidence → more suspicious
    l *= math.exp(-evidence_count * 0.3)
    # Low diversity → suspicious
    l *= math.exp(-source_diversity * 0.5)
    # Low agreement → suspicious
    l *= (1 - agreement_rate) ** 0.5
    # High flag rate → suspicious
    l *= (1 + flag_rate * 3)
    # Low score → more suspicious
    l *= math.exp(-(score / 100) * 1.5)
    return l


def _genuine_likelihood(
    evidence_count, source_diversity, moral_magnitude,
    agreement_rate, flag_rate, score,
) -> float:
    """Higher when: lots of evidence, diverse sources, high agreement, low flags, high score."""
    l = 1.0
    l *= (1 + evidence_count * 0.4)
    l *= (1 + source_diversity * 0.5)
    l *= agreement_rate ** 0.5
    l *= (1 - flag_rate) ** 2
    l *= (score / 100) ** 0.5
    return l


def _misinterpretation_likelihood(
    evidence_count, source_diversity, moral_magnitude,
    agreement_rate, flag_rate, score,
) -> float:
    """Higher when: some evidence exists but moderate agreement,
    high moral vector (controversial topic), moderate score."""
    l = 1.0
    # Some evidence (not zero, not tons)
    l *= math.exp(-abs(evidence_count - 3) * 0.2)
    # Moderate agreement (neither very high nor very low)
    l *= math.exp(-abs(agreement_rate - 0.5) * 2)
    # High moral magnitude → more likely to be misinterpreted
    l *= (1 + moral_magnitude / 200)
    # Moderate flags
    l *= (1 + flag_rate)
    # Moderate score
    l *= math.exp(-abs(score - 50) * 0.02)
    return l
