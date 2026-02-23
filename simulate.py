"""TruthDAG V2 score propagation simulator.

Standalone script for parameterized DAG score propagation. Loads quanta
and edges from the SQLite database, builds an in-memory directed graph,
and propagates scores using tunable parameters (damping, floor,
contradiction penalty, pillar weights).

Usage:
  python simulate.py                         # baseline with defaults
  python simulate.py --damping 0.5           # lower damping
  python simulate.py --floor 0.2 --penalty 0.2
  python simulate.py --weights 0.4 0.2 0.2 0.2  # custom pillar weights
"""

import argparse
import sqlite3
import sys
import io

if sys.stdout.encoding != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from tsim.db import get_db, DEFAULT_DB


DEFAULT_PARAMS = {
    "damping": 0.7,
    "floor": 0.3,
    "contradiction_penalty": 0.15,
    "pillar_weights": [0.30, 0.25, 0.25, 0.20],
    "max_depth": 20,
}


def load_graph(db: sqlite3.Connection) -> dict:
    """Load quanta and edges from SQLite into a graph dict.

    Returns:
        {
            "nodes": {id: {id, claim, discipline, layer, chain_id,
                           pillar_scores, intrinsic_score, chain_score,
                           moral_vector, depends, contradicts}},
            "edges": [{source, target, type, chain_id}],
        }
    """
    rows = db.execute("SELECT * FROM chain_node WHERE layer >= 0").fetchall()
    nodes = {}
    for r in rows:
        r = dict(r)
        nodes[r["id"]] = {
            "id": r["id"],
            "claim": r["claim"],
            "discipline": r["discipline"],
            "layer": r["layer"],
            "chain_id": r["chain_id"],
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
            "depends": _parse_csv(r.get("depends", "")),
            "contradicts": _parse_csv(r.get("contradicts", "")),
        }

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

    return {"nodes": nodes, "edges": edges}


def compute_intrinsic(pillar_scores: dict, weights: list[float]) -> float:
    """Compute intrinsic score from 4 pillars using given weights."""
    pillars = ["correspondence", "coherence", "convergence", "pragmatism"]
    return sum(pillar_scores[p] * w for p, w in zip(pillars, weights))


def _topo_sort(nodes: dict) -> list[str]:
    """Topological sort of nodes by dependency edges (Kahn's algorithm).

    Processes foundation nodes first, then dependents. Nodes with no
    dependencies come first.
    """
    in_degree = {nid: 0 for nid in nodes}
    adjacency = {nid: [] for nid in nodes}

    for nid, node in nodes.items():
        for dep_id in node["depends"]:
            if dep_id in nodes:
                adjacency[dep_id].append(nid)
                in_degree[nid] += 1

    queue = [nid for nid, deg in in_degree.items() if deg == 0]
    queue.sort(key=lambda nid: nodes[nid]["layer"])
    order = []

    while queue:
        nid = queue.pop(0)
        order.append(nid)
        for child in adjacency[nid]:
            in_degree[child] -= 1
            if in_degree[child] == 0:
                queue.append(child)

    # Append any remaining nodes (cycles) at the end
    remaining = [nid for nid in nodes if nid not in set(order)]
    order.extend(remaining)

    return order


def propagate_scores(
    graph: dict,
    params: dict | None = None,
    intrinsic_overrides: dict[str, float] | None = None,
    edge_weights: dict[tuple[str, str], float] | None = None,
) -> dict:
    """Propagate scores through the TruthDAG using tunable parameters.

    Args:
        graph: Dict with "nodes" and "edges" from load_graph().
        params: Dict with keys: damping, floor, contradiction_penalty,
                pillar_weights, max_depth. Missing keys use defaults.
        intrinsic_overrides: {node_id: new_intrinsic_score} to override
            specific nodes (used by sabotage simulation).
        edge_weights: {(source, target): weight} to scale dependency
            contributions (0.0 = removed, 0.5 = half strength, etc.).
            Used by flag-weak simulation.

    Returns:
        Dict with:
            "nodes": updated node dict with new_intrinsic and new_chain_score
            "metrics": {avg_score_change, max_score_change, weakest_links,
                        nodes_processed, score_distribution}
    """
    p = {**DEFAULT_PARAMS, **(params or {})}
    damping = p["damping"]
    floor = p["floor"]
    penalty = p["contradiction_penalty"]
    weights = p["pillar_weights"]
    max_depth = p["max_depth"]
    overrides = intrinsic_overrides or {}
    ew = edge_weights or {}

    nodes = graph["nodes"]

    # Phase 1: Recompute intrinsic scores with custom pillar weights
    for nid, node in nodes.items():
        if nid in overrides:
            node["new_intrinsic"] = overrides[nid]
        else:
            node["new_intrinsic"] = compute_intrinsic(node["pillar_scores"], weights)

    # Phase 2: Topological propagation of chain scores
    order = _topo_sort(nodes)

    def _chain_score(nid: str, depth: int = 0) -> float:
        """Recursively compute chain score following dependencies."""
        node = nodes[nid]
        if "new_chain_score" in node:
            return node["new_chain_score"]

        if depth > max_depth:
            return node["new_intrinsic"]

        intrinsic = node["new_intrinsic"]

        # Find weakest dependency chain score (respecting edge weights)
        deps = [d for d in node["depends"] if d in nodes]
        if deps:
            dep_scores = []
            for d in deps:
                raw = _chain_score(d, depth + 1)
                w = ew.get((d, nid), 1.0)
                dep_scores.append(raw * w)
            min_dep = min(dep_scores)
        else:
            min_dep = 100.0  # no dependencies = full strength

        # Count contradictions (only those present in graph, weighted)
        contrad_ids = [c for c in node["contradicts"] if c in nodes]
        n_contradictions = sum(ew.get((c, nid), 1.0) for c in contrad_ids)

        # TruthDAG V2 formula:
        # chain_score = intrinsic * (floor + damping * min_dep/100) * (1 - penalty * contradictions)
        score = intrinsic * (floor + damping * min_dep / 100) * (1 - penalty * n_contradictions)
        score = max(0.0, min(100.0, score))

        node["new_chain_score"] = round(score, 2)
        return score

    # Process in topological order to maximize cache hits
    for nid in order:
        _chain_score(nid)

    # Phase 3: Compute metrics
    changes = []
    for nid, node in nodes.items():
        old = node.get("chain_score") or node["intrinsic_score"] or 0
        new = node.get("new_chain_score", node["new_intrinsic"])
        changes.append({
            "id": nid,
            "old_score": old,
            "new_score": new,
            "delta": new - old,
        })

    deltas = [abs(c["delta"]) for c in changes]
    new_scores = [c["new_score"] for c in changes]

    # Weakest links: nodes whose chain score dropped the most relative to intrinsic
    weakest = []
    for nid, node in nodes.items():
        intrinsic = node["new_intrinsic"]
        chain = node.get("new_chain_score", intrinsic)
        if intrinsic > 0:
            ratio = chain / intrinsic
            weakest.append({"id": nid, "claim": node["claim"][:60],
                            "intrinsic": round(intrinsic, 1),
                            "chain": round(chain, 1),
                            "ratio": round(ratio, 3)})

    weakest.sort(key=lambda x: x["ratio"])

    metrics = {
        "nodes_processed": len(nodes),
        "avg_score_change": round(sum(deltas) / len(deltas), 2) if deltas else 0,
        "max_score_change": round(max(deltas), 2) if deltas else 0,
        "avg_chain_score": round(sum(new_scores) / len(new_scores), 1) if new_scores else 0,
        "min_chain_score": round(min(new_scores), 1) if new_scores else 0,
        "max_chain_score": round(max(new_scores), 1) if new_scores else 0,
        "weakest_links": weakest[:10],
        "score_distribution": _histogram(new_scores),
    }

    return {"nodes": nodes, "metrics": metrics, "changes": changes}


def _histogram(scores: list[float], bins: int = 5) -> list[dict]:
    """Simple histogram of scores into bins."""
    if not scores:
        return []
    lo, hi = 0, 100
    step = (hi - lo) / bins
    result = []
    for i in range(bins):
        lower = lo + i * step
        upper = lower + step
        count = sum(1 for s in scores if lower <= s < upper or (i == bins - 1 and s == upper))
        result.append({"range": f"{lower:.0f}-{upper:.0f}", "count": count})
    return result


def print_results(result: dict, params: dict):
    """Print a formatted summary of propagation results."""
    nodes = result["nodes"]
    metrics = result["metrics"]
    changes = result["changes"]

    print("=" * 70)
    print("TruthDAG V2 — Score Propagation Results")
    print("=" * 70)

    print("\nParameters:")
    print(f"  damping:               {params['damping']}")
    print(f"  floor:                 {params['floor']}")
    print(f"  contradiction_penalty: {params['contradiction_penalty']}")
    print(f"  pillar_weights:        {params['pillar_weights']}")
    print(f"  max_depth:             {params['max_depth']}")

    print(f"\nGraph Summary:")
    print(f"  Nodes processed:       {metrics['nodes_processed']}")
    print(f"  Avg chain score:       {metrics['avg_chain_score']}")
    print(f"  Score range:           {metrics['min_chain_score']} - {metrics['max_chain_score']}")
    print(f"  Avg score change:      {metrics['avg_score_change']}")
    print(f"  Max score change:      {metrics['max_score_change']}")

    print(f"\nScore Distribution:")
    for bucket in metrics["score_distribution"]:
        bar = "#" * bucket["count"]
        print(f"  {bucket['range']:>7}: {bucket['count']:>3} {bar}")

    # Top 5 highest
    ranked = sorted(changes, key=lambda c: c["new_score"], reverse=True)
    print(f"\nTop 5 Highest Scores:")
    print(f"  {'Score':>6} {'Delta':>7}  {'ID'}")
    print(f"  {'-'*6} {'-'*7}  {'-'*50}")
    for c in ranked[:5]:
        node = nodes[c["id"]]
        delta_str = f"{c['delta']:+.1f}"
        print(f"  {c['new_score']:>6.1f} {delta_str:>7}  {node['claim'][:55]}")

    # Bottom 5 lowest
    print(f"\nTop 5 Lowest Scores:")
    print(f"  {'Score':>6} {'Delta':>7}  {'ID'}")
    print(f"  {'-'*6} {'-'*7}  {'-'*50}")
    for c in ranked[-5:]:
        node = nodes[c["id"]]
        delta_str = f"{c['delta']:+.1f}"
        print(f"  {c['new_score']:>6.1f} {delta_str:>7}  {node['claim'][:55]}")

    # Weakest links (most degraded by dependency chain)
    print(f"\nWeakest Links (chain/intrinsic ratio):")
    print(f"  {'Ratio':>6} {'Intr':>5} {'Chain':>6}  {'Claim'}")
    print(f"  {'-'*6} {'-'*5} {'-'*6}  {'-'*50}")
    for w in metrics["weakest_links"][:5]:
        print(f"  {w['ratio']:>6.3f} {w['intrinsic']:>5.1f} {w['chain']:>6.1f}  {w['claim']}")

    print(f"\n{'=' * 70}")


def cascade_depth(graph: dict, source_id: str, before: dict, after: dict, threshold: float = 0.5) -> int:
    """Measure how many hops damage propagates from a sabotaged node.

    Walks the dependency graph outward from source_id via BFS,
    counting hops while downstream nodes show score changes above threshold.
    """
    nodes = graph["nodes"]
    # Build reverse adjacency: node -> list of nodes that depend on it
    children = {nid: [] for nid in nodes}
    for nid, node in nodes.items():
        for dep_id in node["depends"]:
            if dep_id in children:
                children[dep_id].append(nid)

    visited = set()
    queue = [(source_id, 0)]
    max_depth = 0

    while queue:
        nid, depth = queue.pop(0)
        if nid in visited:
            continue
        visited.add(nid)

        for child in children.get(nid, []):
            if child in visited:
                continue
            b = before.get(child, 0)
            a = after.get(child, 0)
            if abs(b - a) >= threshold:
                max_depth = max(max_depth, depth + 1)
                queue.append((child, depth + 1))

    return max_depth


def deepcopy_graph(graph: dict) -> dict:
    """Deep-copy a graph dict so propagation doesn't mutate the original."""
    import copy
    return {
        "nodes": {nid: {**node} for nid, node in graph["nodes"].items()},
        "edges": [dict(e) for e in graph["edges"]],
    }


def _parse_csv(val) -> list[str]:
    if isinstance(val, list):
        return [v for v in val if v]
    if isinstance(val, str) and val.strip():
        return [v.strip() for v in val.split(",") if v.strip()]
    return []


def main():
    parser = argparse.ArgumentParser(
        description="TruthDAG V2 score propagation simulator",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--db", default=DEFAULT_DB, help="Database path")
    parser.add_argument("--damping", type=float, default=0.7,
                        help="Damping factor for dependency propagation (default: 0.7)")
    parser.add_argument("--floor", type=float, default=0.3,
                        help="Minimum dependency contribution floor (default: 0.3)")
    parser.add_argument("--penalty", type=float, default=0.15,
                        help="Per-contradiction penalty multiplier (default: 0.15)")
    parser.add_argument("--weights", type=float, nargs=4, default=[0.30, 0.25, 0.25, 0.20],
                        metavar=("CORR", "COH", "CONV", "PRAG"),
                        help="Pillar weights: correspondence coherence convergence pragmatism")
    parser.add_argument("--max-depth", type=int, default=20,
                        help="Max recursion depth for chain propagation (default: 20)")

    args = parser.parse_args()

    params = {
        "damping": args.damping,
        "floor": args.floor,
        "contradiction_penalty": args.penalty,
        "pillar_weights": args.weights,
        "max_depth": args.max_depth,
    }

    db = get_db(args.db)
    graph = load_graph(db)
    db.close()

    if not graph["nodes"]:
        print("ERROR: No quanta in database. Run 'python cli.py seed' first.")
        sys.exit(1)

    result = propagate_scores(graph, params)
    print_results(result, params)


if __name__ == "__main__":
    main()
