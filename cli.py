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
  python cli.py export-graph [--output PATH]     Export graph JSON for visualizer
  python cli.py import-chain [options]           Import chain data (incremental)
  python cli.py validate [options]               Validate chain data (no import)
  python cli.py reset                            Drop and recreate DB
"""

import argparse
import json
import os
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


def cmd_export_graph(args):
    """Export graph data as JSON for the 3D visualizer."""
    from datetime import datetime
    from simulate import DEFAULT_PARAMS

    db = get_db(args.db)

    # Load nodes
    rows = db.execute("SELECT * FROM chain_node WHERE layer >= 0").fetchall()
    nodes = []
    for r in rows:
        r = dict(r)
        nodes.append({
            "id": r["id"],
            "chain_id": r["chain_id"],
            "claim": r["claim"],
            "discipline": r["discipline"],
            "layer": r["layer"],
            "source_type": r["source_type"],
            "pillar_scores": {
                "correspondence": r["correspondence"],
                "coherence": r["coherence"],
                "convergence": r["convergence"],
                "pragmatism": r["pragmatism"],
            },
            "intrinsic_score": r["intrinsic_score"],
            "chain_score": r["chain_score"],
            "moral_vector": {
                "care": r["moral_care"],
                "fairness": r["moral_fairness"],
                "loyalty": r["moral_loyalty"],
                "authority": r["moral_authority"],
                "sanctity": r["moral_sanctity"],
                "liberty": r["moral_liberty"],
                "epistemic_humility": r["moral_epistemic_humility"],
                "temporal_stewardship": r["moral_temporal_stewardship"],
            },
            "depends": [v.strip() for v in (r.get("depends") or "").split(",") if v.strip()],
            "contradicts": [v.strip() for v in (r.get("contradicts") or "").split(",") if v.strip()],
        })

    # Load chains
    chain_rows = db.execute("SELECT * FROM chain_definition").fetchall()
    chains = {}
    for c in chain_rows:
        c = dict(c)
        chains[c["id"]] = {"name": c["name"], "discipline": c["discipline"], "crown_claim": c["crown_claim"]}

    # Load edges
    edge_rows = db.execute("SELECT * FROM chain_edge").fetchall()
    edges = []
    for e in edge_rows:
        e = dict(e)
        edges.append({
            "source": e["source_node"],
            "target": e["target_node"],
            "type": e["edge_type"],
            "chain_id": e["chain_id"],
        })

    # Evidence counts per node
    ev_rows = db.execute(
        "SELECT quanta_id, COUNT(*) as cnt FROM evidence_source GROUP BY quanta_id"
    ).fetchall()
    ev_counts = {r["quanta_id"]: r["cnt"] for r in ev_rows}
    for node in nodes:
        node["evidence_count"] = ev_counts.get(node["id"], 0)

    db.close()

    data = {
        "meta": {
            "exported_at": datetime.now().isoformat(),
            "node_count": len(nodes),
            "edge_count": len(edges),
            "chain_count": len(chains),
        },
        "chains": chains,
        "nodes": nodes,
        "edges": edges,
        "params_default": DEFAULT_PARAMS,
    }

    output = args.output
    os.makedirs(os.path.dirname(output) or ".", exist_ok=True)
    with open(output, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    print(f"Exported graph: {len(nodes)} nodes, {len(edges)} edges, {len(chains)} chains")
    print(f"Output: {output}")


def cmd_import_chain(args):
    """Import chain data from files or directory."""
    from tsim.importer import import_chain as do_import, import_from_directory, import_jsonl_only

    db = get_db(args.db)

    if args.directory:
        results = import_from_directory(
            db, args.directory,
            validate_first=not args.skip_validation,
            verbose=True,
        )
    elif args.jsonl:
        result = import_jsonl_only(
            db, args.jsonl,
            chain_id=args.chain_id,
            validate_first=not args.skip_validation,
            verbose=True,
        )
    else:
        print("ERROR: Provide --directory or --jsonl")
        db.close()
        return

    db.close()


def cmd_validate(args):
    """Validate chain data without importing."""
    from tsim.validate import validate_chain_dataset, validate_jsonl_file

    if args.jsonl:
        result = validate_jsonl_file(args.jsonl, chain_id=args.chain_id)
        print(result.summary())
        for e in result.errors:
            print(str(e))
        for w in result.warnings:
            print(str(w))
        sys.exit(0 if result.is_valid else 1)

    elif args.directory:
        import json as _json

        # Determine layout
        chains_dir = args.directory
        output_dir = args.directory
        if os.path.isdir(os.path.join(args.directory, "chains")):
            chains_dir = os.path.join(args.directory, "chains")
        if os.path.isdir(os.path.join(args.directory, "output")):
            output_dir = os.path.join(args.directory, "output")

        json_files = {f[:-5]: os.path.join(chains_dir, f)
                      for f in os.listdir(chains_dir) if f.endswith(".json") and not f.startswith("_")}
        jsonl_files = {f[:-6]: os.path.join(output_dir, f)
                       for f in os.listdir(output_dir) if f.endswith(".jsonl")}

        paired = set(json_files.keys()) & set(jsonl_files.keys())
        if not paired:
            print(f"No matching chain JSON + JSONL pairs found in {args.directory}")
            sys.exit(1)

        all_valid = True
        for chain_id in sorted(paired):
            with open(json_files[chain_id], "r", encoding="utf-8") as f:
                chain_json = _json.load(f)
            nodes = []
            with open(jsonl_files[chain_id], "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        nodes.append(_json.loads(line))

            # Get existing IDs from DB for cross-chain validation
            existing_ids = set()
            try:
                db = get_db(args.db)
                rows = db.execute("SELECT id FROM chain_node").fetchall()
                existing_ids = {r["id"] for r in rows}
                db.close()
            except Exception:
                pass

            result = validate_chain_dataset(chain_json, nodes, existing_ids)
            print(result.summary())
            for e in result.errors:
                print(str(e))
            for w in result.warnings:
                print(str(w))
            if not result.is_valid:
                all_valid = False

        sys.exit(0 if all_valid else 1)
    else:
        print("ERROR: Provide --directory or --jsonl")
        sys.exit(1)


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

    # export-graph
    eg = sub.add_parser("export-graph", help="Export graph JSON for 3D visualizer")
    eg.add_argument("--output", default="visualizer/public/graph.json",
                     help="Output JSON path (default: visualizer/public/graph.json)")

    # import-chain
    imp = sub.add_parser("import-chain", help="Import chain data (incremental upsert)")
    imp.add_argument("--directory", "-d", help="Directory with chain JSON + JSONL files")
    imp.add_argument("--jsonl", help="Path to a single JSONL file")
    imp.add_argument("--chain-id", help="Chain ID (inferred from file if not given)")
    imp.add_argument("--skip-validation", action="store_true", help="Skip validation before import")

    # validate
    val = sub.add_parser("validate", help="Validate chain data (no import)")
    val.add_argument("--directory", "-d", help="Directory with chain files")
    val.add_argument("--jsonl", help="Path to JSONL file")
    val.add_argument("--chain-id", help="Chain ID for standalone JSONL validation")

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
        "export-graph": cmd_export_graph,
        "import-chain": cmd_import_chain,
        "validate": cmd_validate,
        "reset": cmd_reset,
    }

    commands[args.command](args)


if __name__ == "__main__":
    main()
