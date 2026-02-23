"""Reporting and export utilities."""

import csv
import json
import sqlite3
from typing import Optional


def summary_report(run_id: int, db: sqlite3.Connection) -> str:
    """Generate a text summary report for a simulation run."""
    run = db.execute("SELECT * FROM simulation_run WHERE id=?", (run_id,)).fetchone()
    if not run:
        return f"No simulation run found with ID {run_id}"

    run = dict(run)
    summary = json.loads(run["summary"]) if run["summary"] else {}
    config = json.loads(run["config"]) if run["config"] else {}

    lines = []
    lines.append(f"{'='*60}")
    lines.append(f"Simulation Report: #{run_id} — {run.get('name', 'unnamed')}")
    lines.append(f"{'='*60}")
    lines.append(f"Status:    {run['status']}")
    lines.append(f"Started:   {run.get('started_at', 'N/A')}")
    lines.append(f"Completed: {run.get('completed_at', 'N/A')}")
    lines.append("")

    # Config
    lines.append("Configuration:")
    lines.append(f"  Rounds:        {config.get('n_rounds', '?')}")
    lines.append(f"  Batch size:    {config.get('batch_size', '?')}")
    lines.append(f"  Reward rate:   {config.get('reward_rate', '?')}")
    lines.append(f"  Slash rate:    {config.get('slash_rate', '?')}")
    lines.append(f"  Anomaly det.:  {config.get('anomaly_detection', '?')}")
    lines.append("")

    # Totals
    lines.append("Results:")
    lines.append(f"  Total verifications: {summary.get('total_verifications', 0)}")
    lines.append(f"  Total rewards:       {summary.get('total_rewards', 0):.2f}")
    lines.append(f"  Total slashes:       {summary.get('total_slashes', 0):.2f}")
    lines.append(f"  Anomalies flagged:   {summary.get('total_anomalies', 0)}")
    lines.append("")

    # Agent leaderboard
    lines.append("Agent Performance:")
    lines.append(f"  {'Name':<25} {'Type':<12} {'Stake':>8} {'Rep':>6} {'Acc':>6} {'Verif':>6}")
    lines.append(f"  {'-'*25} {'-'*12} {'-'*8} {'-'*6} {'-'*6} {'-'*6}")

    agents = summary.get("agents", [])
    agents.sort(key=lambda a: a.get("stake", 0), reverse=True)
    for a in agents:
        lines.append(
            f"  {a['name']:<25} {a['type']:<12} {a['stake']:>8.1f} "
            f"{a['reputation']:>6.3f} {a['accuracy']:>6.3f} {a['total_verifications']:>6}"
        )
    lines.append("")

    # Consensus drift (average consensus score per round)
    lines.append("Consensus per Round:")
    rounds = db.execute(
        """SELECT round, AVG(consensus_score) as avg_score,
                  AVG(accept_rate) as avg_accept, AVG(flag_rate) as avg_flag
           FROM round_snapshot WHERE run_id=?
           GROUP BY round ORDER BY round""",
        (run_id,),
    ).fetchall()

    for r in rounds:
        r = dict(r)
        lines.append(
            f"  Round {r['round']:>3}: consensus={r['avg_score']:.3f}  "
            f"accept={r['avg_accept']:.2%}  flag={r['avg_flag']:.2%}"
        )
    lines.append("")

    # Anomalies
    anomalies = db.execute(
        "SELECT * FROM anomaly_flag WHERE run_id=? ORDER BY probability DESC LIMIT 10",
        (run_id,),
    ).fetchall()
    if anomalies:
        lines.append("Top Anomalies:")
        for af in anomalies:
            af = dict(af)
            node = db.execute(
                "SELECT claim FROM chain_node WHERE id=?", (af["quanta_id"],)
            ).fetchone()
            claim = dict(node)["claim"][:60] if node else "?"
            lines.append(
                f"  [{af['flag_type']:<18}] p={af['probability']:.3f}  {af['quanta_id'][:20]}: {claim}"
            )
        lines.append("")

    lines.append(f"{'='*60}")
    return "\n".join(lines)


def agent_leaderboard(run_id: int, db: sqlite3.Connection) -> str:
    """Ranked agents by accuracy, stake, reputation."""
    run = db.execute("SELECT summary FROM simulation_run WHERE id=?", (run_id,)).fetchone()
    if not run:
        return f"No simulation run found with ID {run_id}"

    summary = json.loads(dict(run)["summary"]) if dict(run)["summary"] else {}
    agents = summary.get("agents", [])

    lines = []
    lines.append(f"Agent Leaderboard — Simulation #{run_id}")
    lines.append(f"{'='*70}")
    lines.append(f"{'Rank':>4}  {'Name':<25} {'Type':<12} {'Stake':>8} {'Rep':>6} {'Acc':>6}")
    lines.append(f"{'':>4}  {'-'*25} {'-'*12} {'-'*8} {'-'*6} {'-'*6}")

    agents.sort(key=lambda a: (a.get("accuracy", 0), a.get("reputation", 0)), reverse=True)
    for i, a in enumerate(agents, 1):
        lines.append(
            f"{i:>4}. {a['name']:<25} {a['type']:<12} {a['stake']:>8.1f} "
            f"{a['reputation']:>6.3f} {a['accuracy']:>6.3f}"
        )

    return "\n".join(lines)


def export_csv(run_id: int, db: sqlite3.Connection, path: str):
    """Export round-by-round data as CSV."""
    rows = db.execute(
        """SELECT rs.round, rs.quanta_id, cn.claim, cn.discipline, cn.layer,
                  cn.intrinsic_score, rs.consensus_score, rs.verification_count,
                  rs.accept_rate, rs.flag_rate
           FROM round_snapshot rs
           JOIN chain_node cn ON rs.quanta_id = cn.id
           WHERE rs.run_id=?
           ORDER BY rs.round, rs.quanta_id""",
        (run_id,),
    ).fetchall()

    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "round", "quanta_id", "claim", "discipline", "layer",
            "intrinsic_score", "consensus_score", "verification_count",
            "accept_rate", "flag_rate",
        ])
        for row in rows:
            writer.writerow(list(row))

    return len(rows)


def anomaly_report(run_id: int, db: sqlite3.Connection) -> str:
    """Show all anomaly flags for a simulation run."""
    flags = db.execute(
        """SELECT af.*, cn.claim, cn.discipline, cn.intrinsic_score
           FROM anomaly_flag af
           JOIN chain_node cn ON af.quanta_id = cn.id
           WHERE af.run_id=?
           ORDER BY af.probability DESC""",
        (run_id,),
    ).fetchall()

    if not flags:
        return f"No anomalies flagged in simulation #{run_id}"

    lines = []
    lines.append(f"Anomaly Report — Simulation #{run_id}")
    lines.append(f"{'='*80}")
    lines.append(f"Total flags: {len(flags)}")
    lines.append("")

    for af in flags:
        af = dict(af)
        lines.append(f"  [{af['flag_type']:<18}] probability: {af['probability']:.4f}")
        lines.append(f"    Quanta:     {af['quanta_id']}")
        lines.append(f"    Claim:      {af['claim'][:70]}")
        lines.append(f"    Discipline: {af['discipline']}")
        lines.append(f"    Intrinsic:  {af['intrinsic_score']}")
        lines.append(f"    Round:      {af['round']}")
        lines.append(f"    Resolved:   {'Yes' if af['resolved'] else 'No'}")
        lines.append("")

    return "\n".join(lines)
