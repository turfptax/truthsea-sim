"""Agent-based verification simulation.

Agent types:
  - honest:    accepts if intrinsic_score > threshold, ~90-95% accuracy
  - random:    coin flip with slight bias toward accept
  - malicious: rejects high-quality quanta, accepts low-quality
  - strategic: follows majority with slight independent judgment
"""

import random
import sqlite3
import uuid
from dataclasses import dataclass
from typing import Optional

from .scoring import intrinsic_score


@dataclass
class AgentConfig:
    """Configuration for an agent."""
    agent_type: str
    name: str = ""
    stake: float = 100.0
    # Type-specific params
    threshold: float = 50.0  # honest: accept above this score
    noise: float = 0.05       # honest: probability of random error
    bias: float = 0.55        # random: accept probability
    malice_invert: float = 0.8  # malicious: probability of inverting correct answer
    herd_weight: float = 0.7    # strategic: weight given to majority opinion


def create_agent_pool(
    db: sqlite3.Connection,
    n_honest: int = 5,
    n_random: int = 2,
    n_malicious: int = 1,
    n_strategic: int = 2,
) -> list[str]:
    """Create agents in the database. Returns list of agent IDs."""
    agent_ids = []

    configs = (
        [("honest", n_honest), ("random", n_random),
         ("malicious", n_malicious), ("strategic", n_strategic)]
    )

    for agent_type, count in configs:
        for i in range(count):
            agent_id = f"{agent_type}_{uuid.uuid4().hex[:8]}"
            name = f"{agent_type.title()} Agent {i+1}"
            stake = 100.0
            if agent_type == "malicious":
                stake = 150.0  # malicious agents may invest more to gain influence

            db.execute(
                """INSERT INTO agent (id, name, agent_type, stake, reputation)
                   VALUES (?,?,?,?,?)""",
                (agent_id, name, agent_type, stake, 0.5),
            )
            agent_ids.append(agent_id)

    db.commit()
    return agent_ids


def verify_quanta(
    agent: dict,
    quanta: dict,
    db: sqlite3.Connection,
    run_id: int,
    round_num: int,
    majority_verdict: Optional[str] = None,
) -> dict:
    """Agent produces a verdict for a quanta. Returns verification dict."""
    agent_type = agent["agent_type"]
    iscore = quanta.get("intrinsic_score") or intrinsic_score(quanta)

    if agent_type == "honest":
        verdict, confidence = _honest_verify(iscore)
    elif agent_type == "random":
        verdict, confidence = _random_verify()
    elif agent_type == "malicious":
        verdict, confidence = _malicious_verify(iscore)
    elif agent_type == "strategic":
        verdict, confidence = _strategic_verify(iscore, majority_verdict)
    else:
        verdict, confidence = "accept", 0.5

    db.execute(
        """INSERT INTO verification (quanta_id, agent_id, run_id, verdict, confidence, round)
           VALUES (?,?,?,?,?,?)""",
        (quanta["id"], agent["id"], run_id, verdict, round(confidence, 3), round_num),
    )

    return {"agent_id": agent["id"], "verdict": verdict, "confidence": confidence}


def _honest_verify(score: float, threshold: float = 50.0, noise: float = 0.05) -> tuple[str, float]:
    """Honest agent: accepts high-quality, rejects low, with small error rate."""
    if random.random() < noise:
        # Random error
        verdict = random.choice(["accept", "reject", "flag"])
        confidence = random.uniform(0.3, 0.6)
    elif score >= threshold + 10:
        verdict = "accept"
        confidence = min(0.95, 0.5 + (score - threshold) / 100)
    elif score <= threshold - 10:
        verdict = "reject"
        confidence = min(0.95, 0.5 + (threshold - score) / 100)
    else:
        # Borderline — might flag for review
        if random.random() < 0.3:
            verdict = "flag"
            confidence = 0.4 + random.uniform(0, 0.2)
        elif score >= threshold:
            verdict = "accept"
            confidence = 0.5 + random.uniform(0, 0.15)
        else:
            verdict = "reject"
            confidence = 0.5 + random.uniform(0, 0.15)

    return verdict, confidence


def _random_verify(bias: float = 0.55) -> tuple[str, float]:
    """Random agent: mostly coin flip."""
    r = random.random()
    if r < bias:
        return "accept", random.uniform(0.3, 0.7)
    elif r < bias + (1 - bias) * 0.8:
        return "reject", random.uniform(0.3, 0.7)
    else:
        return "flag", random.uniform(0.2, 0.5)


def _malicious_verify(score: float, invert_prob: float = 0.8) -> tuple[str, float]:
    """Malicious agent: inverts the correct answer most of the time."""
    if random.random() < invert_prob:
        # Invert: accept bad, reject good
        if score >= 50:
            return "reject", random.uniform(0.6, 0.9)
        else:
            return "accept", random.uniform(0.6, 0.9)
    else:
        # Occasionally acts honestly to avoid detection
        if score >= 50:
            return "accept", random.uniform(0.4, 0.6)
        else:
            return "reject", random.uniform(0.4, 0.6)


def _strategic_verify(
    score: float,
    majority_verdict: Optional[str],
    herd_weight: float = 0.7,
) -> tuple[str, float]:
    """Strategic agent: follows majority with some independent judgment."""
    # Independent assessment
    if score >= 55:
        own_verdict = "accept"
    elif score <= 45:
        own_verdict = "reject"
    else:
        own_verdict = random.choice(["accept", "reject"])

    if majority_verdict and random.random() < herd_weight:
        verdict = majority_verdict
        confidence = 0.6 + random.uniform(0, 0.2)
    else:
        verdict = own_verdict
        confidence = 0.5 + random.uniform(0, 0.2)

    return verdict, confidence
