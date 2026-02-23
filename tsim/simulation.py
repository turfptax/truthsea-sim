"""Monte Carlo simulation runner.

Orchestrates agents verifying quanta across multiple rounds,
computing consensus, distributing rewards/slashes, and flagging anomalies.
"""

import json
import random
import sqlite3
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Optional

from .agents import create_agent_pool, verify_quanta
from .economics import stake_weighted_consensus, distribute_rewards, update_reputation
from .anomaly import classify_anomaly


@dataclass
class SimConfig:
    """Simulation configuration."""
    n_rounds: int = 10
    batch_size: int = 20       # quanta per round (0 = all)
    n_honest: int = 5
    n_random: int = 2
    n_malicious: int = 1
    n_strategic: int = 2
    reward_rate: float = 0.05
    slash_rate: float = 0.10
    anomaly_detection: bool = True
    seed: Optional[int] = None
    name: str = "simulation"


def run_simulation(db: sqlite3.Connection, config: SimConfig, verbose: bool = True) -> int:
    """Run a full simulation. Returns the simulation run ID."""
    if config.seed is not None:
        random.seed(config.seed)

    # Create simulation run record
    db.execute(
        """INSERT INTO simulation_run (name, config, status, started_at)
           VALUES (?,?,?,?)""",
        (config.name, json.dumps(asdict(config)), "running", datetime.now().isoformat()),
    )
    run_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]
    db.commit()

    if verbose:
        print(f"Simulation #{run_id}: {config.name}")
        print(f"  Config: {config.n_rounds} rounds, batch={config.batch_size}")
        print(f"  Agents: {config.n_honest}H / {config.n_random}R / {config.n_malicious}M / {config.n_strategic}S")

    # Create agent pool
    agent_ids = create_agent_pool(
        db, config.n_honest, config.n_random, config.n_malicious, config.n_strategic,
    )
    if verbose:
        print(f"  Created {len(agent_ids)} agents")

    # Load all non-alternative quanta
    all_quanta = db.execute(
        "SELECT * FROM chain_node WHERE layer >= 0"
    ).fetchall()
    all_quanta = [dict(q) for q in all_quanta]

    if not all_quanta:
        print("  ERROR: No quanta in database. Run seed first.")
        return run_id

    total_anomalies = 0

    for round_num in range(1, config.n_rounds + 1):
        if verbose:
            print(f"\n  Round {round_num}/{config.n_rounds}:")

        # Select batch
        if config.batch_size > 0 and config.batch_size < len(all_quanta):
            batch = random.sample(all_quanta, config.batch_size)
        else:
            batch = all_quanta

        # Load current agent states
        agents = [
            dict(r)
            for r in db.execute("SELECT * FROM agent WHERE id IN ({})".format(
                ",".join("?" * len(agent_ids))
            ), agent_ids).fetchall()
        ]

        round_verifications = []

        for quanta in batch:
            quanta_verifications = []

            # First pass: all agents verify independently
            for agent in agents:
                v = verify_quanta(agent, quanta, db, run_id, round_num)
                v["stake"] = agent["stake"]
                quanta_verifications.append(v)

            # Second pass: strategic agents get majority info and re-verify
            # (simplified — in practice we use the first pass results)

            # Compute consensus
            consensus = stake_weighted_consensus(quanta_verifications)

            # Record round snapshot
            accept_count = sum(1 for v in quanta_verifications if v["verdict"] == "accept")
            flag_count = sum(1 for v in quanta_verifications if v["verdict"] == "flag")
            n_v = len(quanta_verifications)

            db.execute(
                """INSERT INTO round_snapshot
                   (run_id, round, quanta_id, consensus_score,
                    verification_count, accept_rate, flag_rate)
                   VALUES (?,?,?,?,?,?,?)""",
                (
                    run_id, round_num, quanta["id"],
                    consensus["score"], n_v,
                    accept_count / n_v if n_v else 0,
                    flag_count / n_v if n_v else 0,
                ),
            )

            # Distribute rewards/slashes
            distribute_rewards(
                quanta_verifications, consensus, db, run_id, round_num,
                config.reward_rate, config.slash_rate,
            )

            # Update reputations
            for v in quanta_verifications:
                correct = v["verdict"] == consensus["verdict"]
                update_reputation(v["agent_id"], correct, db)

            # Anomaly detection
            if config.anomaly_detection:
                result = classify_anomaly(quanta, quanta_verifications, db, run_id, round_num)
                if result["classification"] != "genuine":
                    total_anomalies += 1

            round_verifications.extend(quanta_verifications)

        db.commit()

        if verbose:
            verified = len(batch)
            print(f"    Verified {verified} quanta with {len(agents)} agents")

    # Write summary
    summary = _build_summary(db, run_id, config)
    summary["total_anomalies"] = total_anomalies

    db.execute(
        """UPDATE simulation_run SET status='complete', completed_at=?, summary=?
           WHERE id=?""",
        (datetime.now().isoformat(), json.dumps(summary), run_id),
    )
    db.commit()

    if verbose:
        print(f"\nSimulation #{run_id} complete.")
        print(f"  Total verifications: {summary.get('total_verifications', 0)}")
        print(f"  Anomalies flagged: {total_anomalies}")

    return run_id


def _build_summary(db: sqlite3.Connection, run_id: int, config: SimConfig) -> dict:
    """Build a summary dict for the completed simulation."""
    total_v = db.execute(
        "SELECT COUNT(*) as cnt FROM verification WHERE run_id=?", (run_id,)
    ).fetchone()["cnt"]

    total_rewards = db.execute(
        "SELECT COALESCE(SUM(amount),0) as total FROM stake_event WHERE run_id=? AND event_type='reward'",
        (run_id,),
    ).fetchone()["total"]

    total_slashes = db.execute(
        "SELECT COALESCE(SUM(ABS(amount)),0) as total FROM stake_event WHERE run_id=? AND event_type='slash'",
        (run_id,),
    ).fetchone()["total"]

    # Agent performance
    agents = db.execute("SELECT * FROM agent").fetchall()
    agent_summary = []
    for a in agents:
        a = dict(a)
        agent_summary.append({
            "id": a["id"],
            "name": a["name"],
            "type": a["agent_type"],
            "stake": a["stake"],
            "reputation": a["reputation"],
            "accuracy": a["accuracy_rate"],
            "total_verifications": a["total_verifications"],
        })

    return {
        "total_verifications": total_v,
        "total_rewards": round(total_rewards, 2),
        "total_slashes": round(total_slashes, 2),
        "rounds": config.n_rounds,
        "agents": agent_summary,
    }
