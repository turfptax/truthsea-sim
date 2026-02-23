"""Sabotage scenario: weaken foundational nodes and measure cascade effects.

Targets 5 high-out-degree foundation nodes, drops each to 20-40 range,
runs propagation after each, and reports:
  - avg score, min score, % drop
  - downstream nodes that lost the most score
  - cascade depth (hops until attenuation)

Usage:
  python scenarios/sabotage_test.py                     # run all 5 targets
  python scenarios/sabotage_test.py --target universe_age.speed_of_light
  python scenarios/sabotage_test.py --target evolution.dna_heredity --score 25
  python scenarios/sabotage_test.py --csv output/sabotage_results.csv
"""

import argparse
import csv
import os
import sys
import io

if sys.stdout.encoding != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

# Allow imports from project root
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from tsim.db import get_db, DEFAULT_DB
from simulate import load_graph, propagate_scores, deepcopy_graph, cascade_depth

# Default sabotage targets: high out-degree foundation nodes across chains
DEFAULT_TARGETS = [
    ("universe_age.speed_of_light", 30),
    ("evolution.dna_heredity", 25),
    ("thermodynamics.energy_conservation", 35),
    ("climate_change.co2_infrared", 20),
    ("general_relativity.equivalence_principle", 30),
]


def run_sabotage(graph, target_id, sabotage_score, baseline_result):
    """Run a single sabotage scenario. Returns results dict."""
    baseline_scores = {c["id"]: c["new_score"] for c in baseline_result["changes"]}

    sabotaged_graph = deepcopy_graph(graph)
    sabotaged = propagate_scores(
        sabotaged_graph, intrinsic_overrides={target_id: sabotage_score}
    )
    after_scores = {c["id"]: c["new_score"] for c in sabotaged["changes"]}

    depth = cascade_depth(graph, target_id, baseline_scores, after_scores)

    # Per-node deltas
    affected = []
    for nid in baseline_scores:
        b = baseline_scores[nid]
        a = after_scores[nid]
        delta = a - b
        if abs(delta) > 0.01:
            affected.append({
                "id": nid,
                "claim": graph["nodes"][nid]["claim"],
                "chain_id": graph["nodes"][nid]["chain_id"],
                "before": round(b, 2),
                "after": round(a, 2),
                "delta": round(delta, 2),
            })
    affected.sort(key=lambda d: d["delta"])

    b_avg = baseline_result["metrics"]["avg_chain_score"]
    a_avg = sabotaged["metrics"]["avg_chain_score"]
    pct_drop = ((b_avg - a_avg) / b_avg * 100) if b_avg > 0 else 0

    return {
        "target_id": target_id,
        "original_score": graph["nodes"][target_id]["intrinsic_score"],
        "sabotage_score": sabotage_score,
        "baseline_avg": b_avg,
        "sabotaged_avg": a_avg,
        "pct_drop": round(pct_drop, 2),
        "baseline_min": baseline_result["metrics"]["min_chain_score"],
        "sabotaged_min": sabotaged["metrics"]["min_chain_score"],
        "nodes_affected": len(affected),
        "cascade_depth": depth,
        "affected": affected,
        "before_scores": list(baseline_scores.values()),
        "after_scores": list(after_scores.values()),
    }


def print_scenario_results(results):
    """Print the full results table."""
    print("=" * 80)
    print("SABOTAGE SCENARIO RESULTS")
    print("=" * 80)

    # Summary table
    print(f"\n{'Target':<45} {'Orig':>5} {'Sab':>4} {'AvgDrop':>8} {'MinScr':>6} {'#Aff':>5} {'Depth':>5}")
    print(f"{'-'*45} {'-'*5} {'-'*4} {'-'*8} {'-'*6} {'-'*5} {'-'*5}")
    for r in results:
        print(
            f"{r['target_id']:<45} {r['original_score']:>5.1f} {r['sabotage_score']:>4.0f} "
            f"{r['pct_drop']:>+7.1f}% {r['sabotaged_min']:>6.1f} {r['nodes_affected']:>5} {r['cascade_depth']:>5}"
        )

    # Per-target detail
    for r in results:
        print(f"\n{'- '*40}")
        print(f"Target: {r['target_id']}")
        print(f"  Score: {r['original_score']:.1f} -> {r['sabotage_score']:.0f}")
        print(f"  Avg chain score: {r['baseline_avg']:.1f} -> {r['sabotaged_avg']:.1f} ({r['pct_drop']:+.1f}%)")
        print(f"  Min chain score: {r['baseline_min']:.1f} -> {r['sabotaged_min']:.1f}")
        print(f"  Cascade depth: {r['cascade_depth']} hops, {r['nodes_affected']} nodes affected")

        if r["affected"]:
            print(f"\n  Downstream damage (top 5):")
            print(f"  {'Delta':>6} {'Before':>6} {'After':>6}  {'Claim'}")
            print(f"  {'-'*6} {'-'*6} {'-'*6}  {'-'*55}")
            for d in r["affected"][:5]:
                print(f"  {d['delta']:>+6.1f} {d['before']:>6.1f} {d['after']:>6.1f}  {d['claim'][:55]}")

    print(f"\n{'='*80}")


def export_csv_results(results, path):
    """Export results to CSV."""
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "target_id", "original_score", "sabotage_score",
            "baseline_avg", "sabotaged_avg", "pct_drop",
            "baseline_min", "sabotaged_min",
            "nodes_affected", "cascade_depth",
            "affected_node", "affected_claim", "affected_chain",
            "before", "after", "delta",
        ])
        for r in results:
            if r["affected"]:
                for a in r["affected"]:
                    writer.writerow([
                        r["target_id"], r["original_score"], r["sabotage_score"],
                        r["baseline_avg"], r["sabotaged_avg"], r["pct_drop"],
                        r["baseline_min"], r["sabotaged_min"],
                        r["nodes_affected"], r["cascade_depth"],
                        a["id"], a["claim"][:80], a["chain_id"],
                        a["before"], a["after"], a["delta"],
                    ])
            else:
                writer.writerow([
                    r["target_id"], r["original_score"], r["sabotage_score"],
                    r["baseline_avg"], r["sabotaged_avg"], r["pct_drop"],
                    r["baseline_min"], r["sabotaged_min"],
                    r["nodes_affected"], r["cascade_depth"],
                    "", "", "", "", "", "",
                ])
    print(f"CSV exported to {path}")


def plot_histograms(results, output_dir):
    """Plot before/after score distribution histograms."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        print("matplotlib not available, skipping plots")
        return

    os.makedirs(output_dir, exist_ok=True)

    for r in results:
        fig, ax = plt.subplots(figsize=(10, 5))
        bins = list(range(0, 105, 5))

        ax.hist(r["before_scores"], bins=bins, alpha=0.6, label="Baseline",
                color="#2196F3", edgecolor="white")
        ax.hist(r["after_scores"], bins=bins, alpha=0.6, label="Sabotaged",
                color="#F44336", edgecolor="white")

        short_id = r["target_id"].split(".")[-1]
        ax.set_title(
            f"Score Distribution: Sabotage {short_id} "
            f"({r['original_score']:.0f} -> {r['sabotage_score']:.0f})",
            fontsize=13,
        )
        ax.set_xlabel("Chain Score", fontsize=11)
        ax.set_ylabel("Number of Nodes", fontsize=11)
        ax.legend(fontsize=11)
        ax.set_xlim(0, 100)

        # Add stats annotation
        stats_text = (
            f"Avg: {r['baseline_avg']:.1f} -> {r['sabotaged_avg']:.1f}\n"
            f"Drop: {r['pct_drop']:+.1f}%\n"
            f"Affected: {r['nodes_affected']} nodes\n"
            f"Cascade: {r['cascade_depth']} hops"
        )
        ax.text(0.02, 0.95, stats_text, transform=ax.transAxes, fontsize=9,
                verticalalignment="top", fontfamily="monospace",
                bbox=dict(boxstyle="round,pad=0.4", facecolor="wheat", alpha=0.8))

        plt.tight_layout()
        fname = f"sabotage_{short_id}.png"
        fpath = os.path.join(output_dir, fname)
        fig.savefig(fpath, dpi=120)
        plt.close(fig)
        print(f"  Saved: {fpath}")


def main():
    parser = argparse.ArgumentParser(
        description="Sabotage scenario testing for TruthDAG",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--db", default=DEFAULT_DB, help="Database path")
    parser.add_argument("--target", default=None,
                        help="Single node ID to sabotage (default: run all 5)")
    parser.add_argument("--score", type=float, default=None,
                        help="Sabotage score override (default: per-target preset)")
    parser.add_argument("--csv", default=None,
                        help="Export results to CSV file")
    parser.add_argument("--no-plot", action="store_true",
                        help="Skip matplotlib histogram generation")
    parser.add_argument("--output-dir", default=os.path.join(
                            os.path.dirname(__file__), "..", "output"),
                        help="Directory for PNG output (default: output/)")

    args = parser.parse_args()

    db = get_db(args.db)
    graph = load_graph(db)
    db.close()

    if not graph["nodes"]:
        print("ERROR: No quanta in database. Run 'python cli.py seed' first.")
        sys.exit(1)

    # Build target list
    if args.target:
        if args.target not in graph["nodes"]:
            print(f"ERROR: Node '{args.target}' not found in graph.")
            print(f"Available foundation nodes (layer 0):")
            for nid, n in sorted(graph["nodes"].items()):
                if n["layer"] == 0:
                    print(f"  {nid}")
            sys.exit(1)
        score = args.score if args.score is not None else 30
        targets = [(args.target, score)]
    else:
        targets = DEFAULT_TARGETS
        if args.score is not None:
            targets = [(t[0], args.score) for t in targets]

    # Baseline propagation (once)
    baseline_graph = deepcopy_graph(graph)
    baseline = propagate_scores(baseline_graph)

    # Run each sabotage scenario
    results = []
    for target_id, sabotage_score in targets:
        if target_id not in graph["nodes"]:
            print(f"WARNING: Skipping '{target_id}' — not found in graph")
            continue
        r = run_sabotage(graph, target_id, sabotage_score, baseline)
        results.append(r)

    if not results:
        print("No valid targets found.")
        sys.exit(1)

    print_scenario_results(results)

    if args.csv:
        export_csv_results(results, args.csv)

    if not args.no_plot:
        plot_histograms(results, args.output_dir)


if __name__ == "__main__":
    main()
