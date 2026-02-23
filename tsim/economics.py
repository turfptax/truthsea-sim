"""Reward/slash stake economics without blockchain.

Replaces TruthStaking.sol and TruthToken.sol logic with simple
in-database accounting.
"""

import sqlite3


# Default parameters
REWARD_RATE = 0.05      # 5% of stake rewarded for correct verification
SLASH_RATE = 0.10       # 10% of stake slashed for incorrect verification
MIN_STAKE = 10.0        # Minimum stake to remain active
REPUTATION_DECAY = 0.95 # EMA decay factor


def stake_weighted_consensus(verifications: list[dict]) -> dict:
    """Compute stake-weighted consensus from a list of verifications.

    Each verification dict needs: agent_id, verdict, confidence, stake.
    Returns dict with consensus verdict and score.
    """
    weighted = {"accept": 0.0, "reject": 0.0, "flag": 0.0}

    total_weight = 0.0
    for v in verifications:
        weight = v["stake"] * v["confidence"]
        weighted[v["verdict"]] += weight
        total_weight += weight

    if total_weight == 0:
        return {"verdict": "accept", "score": 0.5, "weights": weighted}

    # Normalize
    for k in weighted:
        weighted[k] /= total_weight

    # Consensus is the highest-weighted verdict
    consensus_verdict = max(weighted, key=weighted.get)
    consensus_score = weighted[consensus_verdict]

    return {
        "verdict": consensus_verdict,
        "score": round(consensus_score, 4),
        "weights": {k: round(v, 4) for k, v in weighted.items()},
    }


def distribute_rewards(
    verifications: list[dict],
    consensus: dict,
    db: sqlite3.Connection,
    run_id: int,
    round_num: int,
    reward_rate: float = REWARD_RATE,
    slash_rate: float = SLASH_RATE,
) -> dict:
    """Reward agents who matched consensus, slash those who didn't.

    Returns summary dict with total rewarded/slashed.
    """
    total_rewarded = 0.0
    total_slashed = 0.0
    consensus_verdict = consensus["verdict"]

    for v in verifications:
        agent_id = v["agent_id"]
        stake = v["stake"]

        if v["verdict"] == consensus_verdict:
            # Reward — proportional to confidence
            reward = stake * reward_rate * v["confidence"]
            new_stake = stake + reward
            total_rewarded += reward

            db.execute(
                "UPDATE agent SET stake=? WHERE id=?",
                (round(new_stake, 2), agent_id),
            )
            db.execute(
                """INSERT INTO stake_event (agent_id, run_id, round, event_type, amount, reason)
                   VALUES (?,?,?,?,?,?)""",
                (agent_id, run_id, round_num, "reward", round(reward, 2),
                 f"Matched consensus: {consensus_verdict}"),
            )
        else:
            # Slash — harder penalty
            slash = stake * slash_rate
            new_stake = max(MIN_STAKE, stake - slash)
            actual_slash = stake - new_stake
            total_slashed += actual_slash

            db.execute(
                "UPDATE agent SET stake=? WHERE id=?",
                (round(new_stake, 2), agent_id),
            )
            db.execute(
                """INSERT INTO stake_event (agent_id, run_id, round, event_type, amount, reason)
                   VALUES (?,?,?,?,?,?)""",
                (agent_id, run_id, round_num, "slash", round(-actual_slash, 2),
                 f"Disagreed with consensus: voted {v['verdict']}, consensus was {consensus_verdict}"),
            )

    return {
        "total_rewarded": round(total_rewarded, 2),
        "total_slashed": round(total_slashed, 2),
    }


def update_reputation(
    agent_id: str,
    correct: bool,
    db: sqlite3.Connection,
    decay: float = REPUTATION_DECAY,
):
    """Update agent reputation using exponential moving average."""
    row = db.execute(
        "SELECT reputation, total_verifications, correct_verifications FROM agent WHERE id=?",
        (agent_id,),
    ).fetchone()

    if not row:
        return

    old_rep = row["reputation"]
    total = row["total_verifications"] + 1
    correct_count = row["correct_verifications"] + (1 if correct else 0)

    # EMA: new_rep = decay * old_rep + (1 - decay) * observation
    observation = 1.0 if correct else 0.0
    new_rep = decay * old_rep + (1 - decay) * observation
    accuracy = correct_count / total if total > 0 else 0.0

    db.execute(
        """UPDATE agent SET reputation=?, accuracy_rate=?,
           total_verifications=?, correct_verifications=? WHERE id=?""",
        (round(new_rep, 4), round(accuracy, 4), total, correct_count, agent_id),
    )
