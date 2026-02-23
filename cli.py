"""TruthSea Local Simulation CLI.

Usage:
  python cli.py init                             Create DB + schema
  python cli.py seed                             Import data from chain JSON files
  python cli.py simulate [options]               Run agent verification simulation
  python cli.py report <run_id>                  Print simulation summary
  python cli.py export <run_id> <output.csv>     Export round data as CSV
  python cli.py lens [--preset NAME]             Apply lens, show re-scored quanta
  python cli.py agents                           List all agents + stats
  python cli.py anomalies <run_id>               Show anomaly flags
  python cli.py sabotage <node_id> <new_score>   Weaken a node and re-propagate
  python cli.py flag-weak <src> <tgt>            Flag/invalidate a dependency edge
  python cli.py reset                            Drop and recreate DB
"""

import argparse
import sys
import io

# Fix Windows console encoding for Unicode characters
if sys.stdout.encoding != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
if sys.stderr.encoding != "utf-8":
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

from tsim.db import init_db, reset_db, get_db, DEFAULT_DB
from tsim.scoring import recalculate_all, PRESETS
from tsim.simulation import run_simulation, SimConfig
from tsim.reports import summary_report, agent_leaderboard, export_csv, anomaly_report
from simulate import load_graph, propagate_scores, deepcopy_graph, cascade_depth


def cmd_init(args):
    conn = init_db(args.db)
    print(f"Database initialized: {args.db}")
    conn.close()


def cmd_seed(args):
    from seed import seed
    seed(args.db, verbose=True)


def cmd_simulate(args):
    db = get_db(args.db)
    config = SimConfig(
        name=args.name,
        n_rounds=args.rounds,
        batch_size=args.batch,
        n_honest=args.honest,
        n_random=args.random,
        n_malicious=args.malicious,
        n_strategic=args.strategic,
        reward_rate=args.reward_rate,
        slash_rate=args.slash_rate,
        anomaly_detection=not args.no_anomaly,
        seed=args.seed,
    )
    run_id = run_simulation(db, config, verbose=True)
    db.close()
    print(f"\nRun ID: {run_id}")


def cmd_report(args):
    db = get_db(args.db)
    print(summary_report(args.run_id, db))
    db.close()


def cmd_export(args):
    db = get_db(args.db)
    rows = export_csv(args.run_id, db, args.output)
    print(f"Exported {rows} rows to {args.output}")
    db.close()


def cmd_lens(args):
    db = get_db(args.db)
    preset_name = args.preset or "blank"
    if preset_name not in PRESETS:
        print(f"Unknown preset: {preset_name}")
        print(f"Available: {', '.join(PRESETS.keys())}")
        db.close()
        return

    lens = PRESETS[preset_name]
    results = recalculate_all(db, lens)
    db.close()

    print(f"Lens: {preset_name}")
    print(f"{'='*80}")
    print(f"{'Score':>6} {'Intrinsic':>9} {'Opacity':>7} {'Warn':>5}  {'Discipline':<20} {'Claim'}")
    print(f"{'-'*6} {'-'*9} {'-'*7} {'-'*5}  {'-'*20} {'-'*40}")

    for r in results[:30]:  # Top 30
        warn = "!!" if r["edge_warning"] else ""
        print(
            f"{r['final_score']:>6.1f} {r['intrinsic_score']:>9.1f} "
            f"{r['visual_opacity']:>7.3f} {warn:>5}  "
            f"{r['discipline']:<20} {r['claim'][:50]}"
        )

    if len(results) > 30:
        print(f"\n  ... and {len(results) - 30} more quanta")

    # Summary stats
    scores = [r["final_score"] for r in results]
    if scores:
        avg = sum(scores) / len(scores)
        warnings = sum(1 for r in results if r["edge_warning"])
        print(f"\nSummary: {len(results)} quanta, avg={avg:.1f}, warnings={warnings}")


def cmd_agents(args):
    db = get_db(args.db)
    agents = db.execute("SELECT * FROM agent ORDER BY stake DESC").fetchall()
    db.close()

    if not agents:
        print("No agents found. Run a simulation first.")
        return

    print(f"{'Name':<25} {'Type':<12} {'Stake':>8} {'Rep':>6} {'Acc':>6} {'Verif':>6}")
    print(f"{'-'*25} {'-'*12} {'-'*8} {'-'*6} {'-'*6} {'-'*6}")
    for a in agents:
        a = dict(a)
        print(
            f"{a['name']:<25} {a['agent_type']:<12} {a['stake']:>8.1f} "
            f"{a['reputation']:>6.3f} {a['accuracy_rate']:>6.3f} {a['total_verifications']:>6}"
        )


def cmd_anomalies(args):
    db = get_db(args.db)
    print(anomaly_report(args.run_id, db))
    db.close()


def cmd_sabotage(args):
    db = get_db(args.db)
    graph = load_graph(db)

    node_id = args.node_id
    new_score = args.new_score

    if node_id not in graph["nodes"]:
        print(f"ERROR: Node '{node_id}' not found in graph.")
        print(f"Hint: use full ID like 'universe_age.speed_of_light'")
        db.close()
        return

    node = graph["nodes"][node_id]
    old_intrinsic = node["intrinsic_score"]
    reason = args.reason or "sabotage simulation"

    print(f"{'='*70}")
    print(f"Sabotage: {node_id}")
    print(f"  Claim:  {node['claim'][:65]}")
    print(f"  Chain:  {node['chain_id']}  Layer: {node['layer']}")
    print(f"  Reason: {reason}")
    print(f"  Intrinsic: {old_intrinsic:.1f} -> {new_score:.1f}")
    print(f"{'='*70}")

    # Baseline propagation
    baseline_graph = deepcopy_graph(graph)
    baseline = propagate_scores(baseline_graph)
    before_scores = {c["id"]: c["new_score"] for c in baseline["changes"]}

    # Sabotaged propagation
    sabotaged_graph = deepcopy_graph(graph)
    sabotaged = propagate_scores(sabotaged_graph, intrinsic_overrides={node_id: new_score})
    after_scores = {c["id"]: c["new_score"] for c in sabotaged["changes"]}

    # Cascade depth
    depth = cascade_depth(graph, node_id, before_scores, after_scores)

    # Compute per-node deltas
    deltas = []
    for nid in before_scores:
        b = before_scores[nid]
        a = after_scores[nid]
        if abs(b - a) > 0.01:
            deltas.append({
                "id": nid,
                "claim": graph["nodes"][nid]["claim"][:55],
                "before": round(b, 1),
                "after": round(a, 1),
                "delta": round(a - b, 1),
            })
    deltas.sort(key=lambda d: d["delta"])

    b_avg = baseline["metrics"]["avg_chain_score"]
    a_avg = sabotaged["metrics"]["avg_chain_score"]
    pct_drop = ((b_avg - a_avg) / b_avg * 100) if b_avg > 0 else 0

    print(f"\nImpact Summary:")
    print(f"  Avg chain score: {b_avg:.1f} -> {a_avg:.1f} ({pct_drop:+.1f}%)")
    print(f"  Min chain score: {baseline['metrics']['min_chain_score']:.1f} -> {sabotaged['metrics']['min_chain_score']:.1f}")
    print(f"  Nodes affected:  {len(deltas)}")
    print(f"  Cascade depth:   {depth} hops")

    if deltas:
        print(f"\nMost Affected Nodes:")
        print(f"  {'Delta':>6} {'Before':>6} {'After':>6}  {'Claim'}")
        print(f"  {'-'*6} {'-'*6} {'-'*6}  {'-'*50}")
        for d in deltas[:10]:
            print(f"  {d['delta']:>+6.1f} {d['before']:>6.1f} {d['after']:>6.1f}  {d['claim']}")

    # Update DB intrinsic score
    db.execute(
        "UPDATE chain_node SET intrinsic_score=? WHERE id=?",
        (new_score, node_id),
    )
    db.commit()
    print(f"\nDatabase updated: {node_id} intrinsic_score = {new_score}")

    db.close()
    print(f"{'='*70}")


def cmd_flag_weak(args):
    db = get_db(args.db)
    graph = load_graph(db)

    src = args.source_node
    tgt = args.target_node

    if src not in graph["nodes"]:
        print(f"ERROR: Source node '{src}' not found.")
        db.close()
        return
    if tgt not in graph["nodes"]:
        print(f"ERROR: Target node '{tgt}' not found.")
        db.close()
        return

    # Verify edge exists
    edge_exists = False
    edge_type = None
    for e in graph["edges"]:
        if e["source"] == src and e["target"] == tgt:
            edge_exists = True
            edge_type = e["type"]
            break
    # Also check the depends/contradicts lists on the target node
    tgt_node = graph["nodes"][tgt]
    if src in tgt_node["depends"] or src in tgt_node["contradicts"]:
        edge_exists = True
        if src in tgt_node["contradicts"]:
            edge_type = edge_type or "contradicts"
        else:
            edge_type = edge_type or "depends"

    if not edge_exists:
        print(f"ERROR: No edge found from '{src}' to '{tgt}'.")
        print(f"  {tgt} depends on: {tgt_node['depends']}")
        print(f"  {tgt} contradicts: {tgt_node['contradicts']}")
        db.close()
        return

    print(f"{'='*70}")
    print(f"Flag Weak Link: {src} -> {tgt}")
    print(f"  Edge type:  {edge_type}")
    print(f"  Source:     {graph['nodes'][src]['claim'][:60]}")
    print(f"  Target:     {graph['nodes'][tgt]['claim'][:60]}")
    print(f"{'='*70}")

    # Record the flag
    flag_record = {
        "source": src, "target": tgt, "edge_type": edge_type,
        "reason": args.reason or "weak link flagged",
    }
    print(f"\nFlag recorded: {flag_record}")

    if args.simulate_invalidate:
        # Baseline
        baseline_graph = deepcopy_graph(graph)
        baseline = propagate_scores(baseline_graph)
        before_scores = {c["id"]: c["new_score"] for c in baseline["changes"]}

        # Invalidated: reduce edge weight by 50% (or 0 for contradicts)
        if edge_type == "contradicts":
            weight = 0.0
            action = "removed (contradiction nullified)"
        else:
            weight = 0.5
            action = "reduced to 50%"

        invalidated_graph = deepcopy_graph(graph)
        invalidated = propagate_scores(
            invalidated_graph, edge_weights={(src, tgt): weight}
        )
        after_scores = {c["id"]: c["new_score"] for c in invalidated["changes"]}

        print(f"\nSimulated invalidation: edge weight {action}")

        # Deltas
        deltas = []
        for nid in before_scores:
            b = before_scores[nid]
            a = after_scores[nid]
            if abs(b - a) > 0.01:
                deltas.append({
                    "id": nid,
                    "claim": graph["nodes"][nid]["claim"][:55],
                    "before": round(b, 1),
                    "after": round(a, 1),
                    "delta": round(a - b, 1),
                })
        deltas.sort(key=lambda d: d["delta"])

        b_avg = baseline["metrics"]["avg_chain_score"]
        a_avg = invalidated["metrics"]["avg_chain_score"]
        pct = ((a_avg - b_avg) / b_avg * 100) if b_avg > 0 else 0

        print(f"\nImpact:")
        print(f"  Avg chain score: {b_avg:.1f} -> {a_avg:.1f} ({pct:+.1f}%)")
        print(f"  Nodes affected:  {len(deltas)}")

        if deltas:
            print(f"\nAffected Nodes:")
            print(f"  {'Delta':>6} {'Before':>6} {'After':>6}  {'Claim'}")
            print(f"  {'-'*6} {'-'*6} {'-'*6}  {'-'*50}")
            for d in deltas[:10]:
                print(f"  {d['delta']:>+6.1f} {d['before']:>6.1f} {d['after']:>6.1f}  {d['claim']}")
    else:
        print("  (use --simulate-invalidate to see ripple effects)")

    db.close()
    print(f"\n{'='*70}")


def cmd_reset(args):
    reset_db(args.db)
    print(f"Database reset: {args.db}")


def main():
    parser = argparse.ArgumentParser(
        description="TruthSea Local Simulation Environment",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--db", default=DEFAULT_DB, help="Database path (default: truthsea.db)")
    sub = parser.add_subparsers(dest="command", required=True)

    # init
    sub.add_parser("init", help="Initialize database")

    # seed
    sub.add_parser("seed", help="Import chain data")

    # simulate
    sim = sub.add_parser("simulate", help="Run simulation")
    sim.add_argument("--name", default="simulation", help="Simulation name")
    sim.add_argument("--rounds", type=int, default=10, help="Number of rounds")
    sim.add_argument("--batch", type=int, default=20, help="Quanta per round (0=all)")
    sim.add_argument("--honest", type=int, default=5, help="Number of honest agents")
    sim.add_argument("--random", type=int, default=2, help="Number of random agents")
    sim.add_argument("--malicious", type=int, default=1, help="Number of malicious agents")
    sim.add_argument("--strategic", type=int, default=2, help="Number of strategic agents")
    sim.add_argument("--reward-rate", type=float, default=0.05, help="Reward rate")
    sim.add_argument("--slash-rate", type=float, default=0.10, help="Slash rate")
    sim.add_argument("--no-anomaly", action="store_true", help="Disable anomaly detection")
    sim.add_argument("--seed", type=int, default=None, help="Random seed for reproducibility")

    # report
    rpt = sub.add_parser("report", help="Print simulation report")
    rpt.add_argument("run_id", type=int, help="Simulation run ID")

    # export
    exp = sub.add_parser("export", help="Export round data as CSV")
    exp.add_argument("run_id", type=int, help="Simulation run ID")
    exp.add_argument("output", help="Output CSV file path")

    # lens
    lns = sub.add_parser("lens", help="Apply worldview lens")
    lns.add_argument("--preset", default="blank", help="Lens preset: scientist, religious, ea, libertarian, blank")

    # agents
    sub.add_parser("agents", help="List agents")

    # anomalies
    anom = sub.add_parser("anomalies", help="Show anomaly flags")
    anom.add_argument("run_id", type=int, help="Simulation run ID")

    # sabotage
    sab = sub.add_parser("sabotage", help="Weaken a node and show ripple effects")
    sab.add_argument("node_id", help="Node ID to sabotage (e.g. universe_age.speed_of_light)")
    sab.add_argument("new_score", type=float, help="New intrinsic score (0-100)")
    sab.add_argument("--reason", default=None, help="Reason for sabotage")

    # flag-weak
    fw = sub.add_parser("flag-weak", help="Flag a dependency edge as weak")
    fw.add_argument("source_node", help="Source node ID of the edge")
    fw.add_argument("target_node", help="Target node ID of the edge")
    fw.add_argument("--reason", default=None, help="Reason for flagging")
    fw.add_argument("--simulate-invalidate", action="store_true",
                    help="Simulate edge invalidation and show score ripple")

    # reset
    sub.add_parser("reset", help="Reset database")

    args = parser.parse_args()

    commands = {
        "init": cmd_init,
        "seed": cmd_seed,
        "simulate": cmd_simulate,
        "report": cmd_report,
        "export": cmd_export,
        "lens": cmd_lens,
        "agents": cmd_agents,
        "anomalies": cmd_anomalies,
        "sabotage": cmd_sabotage,
        "flag-weak": cmd_flag_weak,
        "reset": cmd_reset,
    }

    commands[args.command](args)


if __name__ == "__main__":
    main()
