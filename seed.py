"""Seed the SQLite database from existing TruthSea chain JSON and JSONL files.

Two data source strategies:
1. Raw: chain JSON (nodes are string IDs) + JSONL files (full node data)
2. Assembled: assembled-chains.json (nodes are full objects inline)
"""

import json
import os
import sys
from tsim.db import init_db, DEFAULT_DB
from tsim.scoring import intrinsic_score, chain_score

# Data source paths (relative to repo root)
REPO_ROOT = os.path.dirname(os.path.abspath(__file__))
CHAINS_DIR = os.path.join(REPO_ROOT, "..", "TruthSea", "agent-toolkit", "chains")
JSONL_DIR = os.path.join(REPO_ROOT, "..", "TruthSea", "agent-toolkit", "output")
EMBEDDED_JSON = os.path.join(
    REPO_ROOT, "..", "truthsea-dashboard", "src", "data", "assembled-chains.json"
)


def seed(db_path: str = DEFAULT_DB, verbose: bool = True):
    """Import all chain data into the database."""
    conn = init_db(db_path)

    chains_loaded = 0
    nodes_loaded = 0
    edges_loaded = 0
    evidence_loaded = 0
    alts_loaded = 0

    # Strategy 1: Raw chain JSON + JSONL files
    if os.path.isdir(CHAINS_DIR) and os.path.isdir(JSONL_DIR):
        # Load all JSONL node data into a lookup dict
        node_lookup = _load_all_jsonl(JSONL_DIR, verbose)

        chain_files = [f for f in os.listdir(CHAINS_DIR) if f.endswith(".json")]
        if verbose:
            print(f"Found {len(chain_files)} chain files, {len(node_lookup)} JSONL nodes")

        for fname in sorted(chain_files):
            path = os.path.join(CHAINS_DIR, fname)
            with open(path, "r", encoding="utf-8") as f:
                chain = json.load(f)
            c, n, e, ev, a = _import_raw_chain(conn, chain, node_lookup, verbose)
            chains_loaded += c
            nodes_loaded += n
            edges_loaded += e
            evidence_loaded += ev
            alts_loaded += a

    # Strategy 2: Assembled JSON (full nodes inline)
    elif os.path.isfile(EMBEDDED_JSON):
        if verbose:
            print(f"Using assembled data from {EMBEDDED_JSON}")
        with open(EMBEDDED_JSON, "r", encoding="utf-8") as f:
            data = json.load(f)
        for chain_key, chain in data.items():
            if "id" not in chain:
                chain["id"] = chain_key
            c, n, e, ev, a = _import_assembled_chain(conn, chain, verbose)
            chains_loaded += c
            nodes_loaded += n
            edges_loaded += e
            evidence_loaded += ev
            alts_loaded += a
    else:
        print("ERROR: No data sources found.", file=sys.stderr)
        print(f"  Looked for chains dir: {CHAINS_DIR}", file=sys.stderr)
        print(f"  Looked for JSONL dir:  {JSONL_DIR}", file=sys.stderr)
        print(f"  Looked for embedded:   {EMBEDDED_JSON}", file=sys.stderr)
        sys.exit(1)

    # Recalculate chain scores now that all nodes are inserted
    _recalculate_scores(conn, verbose)

    conn.commit()
    conn.close()

    if verbose:
        print(f"\nSeed complete:")
        print(f"  Chains:       {chains_loaded}")
        print(f"  Nodes:        {nodes_loaded}")
        print(f"  Alternatives: {alts_loaded}")
        print(f"  Edges:        {edges_loaded}")
        print(f"  Evidence:     {evidence_loaded}")


def _load_all_jsonl(jsonl_dir: str, verbose: bool) -> dict[str, dict]:
    """Load all JSONL files into a dict keyed by node ID."""
    lookup = {}
    for fname in sorted(os.listdir(jsonl_dir)):
        if not fname.endswith(".jsonl"):
            continue
        path = os.path.join(jsonl_dir, fname)
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                node = json.loads(line)
                lookup[node["id"]] = node
    if verbose:
        print(f"Loaded {len(lookup)} nodes from JSONL files")
    return lookup


def _import_raw_chain(
    conn, chain: dict, node_lookup: dict, verbose: bool
) -> tuple[int, int, int, int, int]:
    """Import a chain where nodes are string IDs referencing JSONL data."""
    chain_id = chain["id"]
    node_ids = chain.get("nodes", [])  # list of string IDs
    edges = chain.get("edges", [])
    alternatives = chain.get("alternatives", [])

    # Insert chain definition
    conn.execute(
        """INSERT OR IGNORE INTO chain_definition (id, name, discipline, crown_claim, node_count)
           VALUES (?, ?, ?, ?, ?)""",
        (chain_id, chain["name"], chain["discipline"], chain["crownClaim"], len(node_ids)),
    )

    nodes_loaded = 0
    evidence_loaded = 0

    # Insert nodes from JSONL lookup
    for nid in node_ids:
        node = node_lookup.get(nid)
        if not node:
            if verbose:
                print(f"    WARNING: Node {nid} not found in JSONL data")
            continue
        ev_count = _insert_node(conn, node, chain_id, chain["discipline"])
        nodes_loaded += 1
        evidence_loaded += ev_count

    # Insert alternatives (minimal data in raw chain files)
    alts_loaded = 0
    for alt in alternatives:
        alt_id = alt["id"]
        claim = alt.get("claim", "")
        # Check if alt node exists in JSONL data
        alt_node = node_lookup.get(alt_id)
        if alt_node:
            ev_count = _insert_node(conn, alt_node, chain_id, chain["discipline"], layer_override=-1)
            evidence_loaded += ev_count
        else:
            # Minimal alternative with just id + claim
            conn.execute(
                """INSERT OR IGNORE INTO chain_node
                   (id, chain_id, claim, discipline, layer, source_type,
                    correspondence, coherence, convergence, pragmatism,
                    intrinsic_score, depends, contradicts)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (alt_id, chain_id, claim, chain["discipline"], -1, "alternative",
                 0, 0, 0, 0, 0.0, "", ""),
            )
        alts_loaded += 1

    # Insert edges
    edges_loaded = 0
    for edge in edges:
        conn.execute(
            """INSERT OR IGNORE INTO chain_edge (chain_id, source_node, target_node, edge_type)
               VALUES (?,?,?,?)""",
            (chain_id, edge["source"], edge["target"], edge["type"]),
        )
        edges_loaded += 1

    if verbose:
        print(f"  {chain_id}: {nodes_loaded} nodes, {alts_loaded} alts, {edges_loaded} edges, {evidence_loaded} evidence")

    return (1, nodes_loaded, edges_loaded, evidence_loaded, alts_loaded)


def _import_assembled_chain(
    conn, chain: dict, verbose: bool
) -> tuple[int, int, int, int, int]:
    """Import a chain where nodes are full inline objects (assembled format)."""
    chain_id = chain["id"]
    nodes = chain.get("nodes", [])
    edges = chain.get("edges", [])
    alternatives = chain.get("alternatives", [])

    conn.execute(
        """INSERT OR IGNORE INTO chain_definition (id, name, discipline, crown_claim, node_count)
           VALUES (?, ?, ?, ?, ?)""",
        (chain_id, chain["name"], chain["discipline"], chain["crownClaim"], len(nodes)),
    )

    nodes_loaded = 0
    evidence_loaded = 0

    for node in nodes:
        ev_count = _insert_node(conn, node, chain_id, chain["discipline"])
        nodes_loaded += 1
        evidence_loaded += ev_count

    alts_loaded = 0
    for alt in alternatives:
        alt_id = alt["id"]
        scores = alt.get("scores", {})
        mv = alt.get("moralVector", {})

        iscore = (
            scores.get("correspondence", 0) * 0.30
            + scores.get("coherence", 0) * 0.25
            + scores.get("convergence", 0) * 0.25
            + scores.get("pragmatism", 0) * 0.20
        )

        conn.execute(
            """INSERT OR IGNORE INTO chain_node
               (id, chain_id, claim, discipline, layer, source_type,
                correspondence, coherence, convergence, pragmatism,
                intrinsic_score, moral_care, moral_fairness, moral_loyalty,
                moral_authority, moral_sanctity, moral_liberty,
                moral_epistemic_humility, moral_temporal_stewardship,
                score_reasoning, key_metrics, depends, contradicts)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                alt_id, chain_id, alt.get("claim", ""),
                chain["discipline"], -1, "alternative",
                scores.get("correspondence", 0), scores.get("coherence", 0),
                scores.get("convergence", 0), scores.get("pragmatism", 0),
                alt.get("intrinsicScore", iscore),
                mv.get("care", 0) if mv else 0,
                mv.get("fairness", 0) if mv else 0,
                mv.get("loyalty", 0) if mv else 0,
                mv.get("authority", 0) if mv else 0,
                mv.get("sanctity", 0) if mv else 0,
                mv.get("liberty", 0) if mv else 0,
                mv.get("epistemicHumility", 0) if mv else 0,
                mv.get("temporalStewardship", 0) if mv else 0,
                json.dumps(alt.get("scoreReasoning")) if alt.get("scoreReasoning") else None,
                json.dumps(alt.get("keyMetrics")) if alt.get("keyMetrics") else None,
                "", "",
            ),
        )
        alts_loaded += 1

        for ev in alt.get("evidence", []):
            conn.execute(
                """INSERT INTO evidence_source
                   (quanta_id, chain_id, url, title, finding, year, source_type)
                   VALUES (?,?,?,?,?,?,?)""",
                (alt_id, chain_id, ev.get("url", ""), ev.get("title", ""),
                 ev.get("finding", ""), ev.get("year"), ev.get("sourceType", "paper")),
            )
            evidence_loaded += 1

    edges_loaded = 0
    for edge in edges:
        conn.execute(
            """INSERT OR IGNORE INTO chain_edge (chain_id, source_node, target_node, edge_type)
               VALUES (?,?,?,?)""",
            (chain_id, edge["source"], edge["target"], edge["type"]),
        )
        edges_loaded += 1

    if verbose:
        print(f"  {chain_id}: {nodes_loaded} nodes, {alts_loaded} alts, {edges_loaded} edges, {evidence_loaded} evidence")

    return (1, nodes_loaded, edges_loaded, evidence_loaded, alts_loaded)


def _insert_node(
    conn, node: dict, chain_id: str, chain_discipline: str, layer_override: int = None
) -> int:
    """Insert a single node dict into the database. Returns evidence count."""
    node_id = node["id"]
    scores = node.get("scores", {})
    mv = node.get("moralVector", {})
    depends = node.get("depends", [])
    contradicts = node.get("contradicts", [])

    iscore = (
        scores.get("correspondence", 0) * 0.30
        + scores.get("coherence", 0) * 0.25
        + scores.get("convergence", 0) * 0.25
        + scores.get("pragmatism", 0) * 0.20
    )

    layer = layer_override if layer_override is not None else node.get("layer", 0)

    conn.execute(
        """INSERT OR IGNORE INTO chain_node
           (id, chain_id, claim, discipline, layer, source_type,
            correspondence, coherence, convergence, pragmatism,
            intrinsic_score, chain_score, weakest_link,
            moral_care, moral_fairness, moral_loyalty, moral_authority,
            moral_sanctity, moral_liberty, moral_epistemic_humility,
            moral_temporal_stewardship, score_reasoning, key_metrics,
            depends, contradicts, agent_id)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            node_id, chain_id, node["claim"],
            node.get("discipline", chain_discipline),
            layer, node.get("sourceType", "unknown"),
            scores.get("correspondence", 0), scores.get("coherence", 0),
            scores.get("convergence", 0), scores.get("pragmatism", 0),
            node.get("intrinsicScore", iscore),
            node.get("chainScore"),
            node.get("weakestLink"),
            mv.get("care", 0), mv.get("fairness", 0),
            mv.get("loyalty", 0), mv.get("authority", 0),
            mv.get("sanctity", 0), mv.get("liberty", 0),
            mv.get("epistemicHumility", 0), mv.get("temporalStewardship", 0),
            json.dumps(node.get("scoreReasoning")) if node.get("scoreReasoning") else None,
            json.dumps(node.get("keyMetrics")) if node.get("keyMetrics") else None,
            ",".join(depends) if isinstance(depends, list) else (depends or ""),
            ",".join(contradicts) if isinstance(contradicts, list) else (contradicts or ""),
            node.get("agentId"),
        ),
    )

    ev_count = 0
    for ev in node.get("evidence", []):
        conn.execute(
            """INSERT INTO evidence_source
               (quanta_id, chain_id, url, title, finding, year, source_type)
               VALUES (?,?,?,?,?,?,?)""",
            (node_id, chain_id, ev.get("url", ""), ev.get("title", ""),
             ev.get("finding", ""), ev.get("year"), ev.get("sourceType", "paper")),
        )
        ev_count += 1

    return ev_count


def _recalculate_scores(conn, verbose: bool):
    """Recalculate intrinsic and chain scores for all nodes."""
    rows = conn.execute("SELECT * FROM chain_node").fetchall()
    all_nodes = {r["id"]: dict(r) for r in rows}

    updated = 0
    for node_id, node in all_nodes.items():
        iscore = intrinsic_score(node)
        cscore = chain_score(node, all_nodes)
        conn.execute(
            "UPDATE chain_node SET intrinsic_score=?, chain_score=? WHERE id=?",
            (round(iscore, 2), round(cscore, 2), node_id),
        )
        updated += 1

    if verbose:
        print(f"\n  Recalculated scores for {updated} nodes")


if __name__ == "__main__":
    seed()
