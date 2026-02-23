"""Incremental chain import with upsert support.

Reads chain JSON + JSONL files and imports into the SQLite database,
updating existing records rather than ignoring duplicates.
"""

import json
import os
from dataclasses import dataclass, field

from tsim.scoring import intrinsic_score, chain_score
from tsim.validate import validate_chain_dataset, validate_jsonl_file, ValidationResult


@dataclass
class ImportResult:
    chain_id: str
    chains_upserted: int = 0
    nodes_inserted: int = 0
    nodes_updated: int = 0
    edges_upserted: int = 0
    evidence_inserted: int = 0
    alternatives_upserted: int = 0
    validation: ValidationResult = None
    scores_recalculated: int = 0

    def summary(self) -> str:
        parts = [f"Import: {self.chain_id}"]
        if self.validation and not self.validation.is_valid:
            parts.append(f"  FAILED validation ({len(self.validation.errors)} errors)")
            return "\n".join(parts)
        parts.append(
            f"  Nodes: {self.nodes_inserted} inserted, {self.nodes_updated} updated"
        )
        parts.append(f"  Edges: {self.edges_upserted}  Evidence: {self.evidence_inserted}")
        if self.alternatives_upserted:
            parts.append(f"  Alternatives: {self.alternatives_upserted}")
        parts.append(f"  Scores recalculated: {self.scores_recalculated}")
        return "\n".join(parts)


def import_chain(db, chain_json, nodes, validate_first=True, verbose=True):
    """Import a single chain with its nodes into the database.

    Uses ON CONFLICT DO UPDATE for upsert behavior.
    """
    cid = chain_json.get("id", "unknown")
    result = ImportResult(chain_id=cid)

    # Get existing node IDs for cross-chain reference validation
    existing_ids = set()
    try:
        rows = db.execute("SELECT id FROM chain_node").fetchall()
        existing_ids = {r["id"] for r in rows}
    except Exception:
        pass

    # Validate
    if validate_first:
        vr = validate_chain_dataset(chain_json, nodes, existing_ids)
        result.validation = vr
        if not vr.is_valid:
            if verbose:
                print(f"  Validation FAILED for {cid}:")
                for e in vr.errors:
                    print(f"    {e}")
            return result
        elif verbose and vr.warnings:
            for w in vr.warnings:
                print(f"    {w}")

    # Upsert chain_definition
    chain_node_list = chain_json.get("nodes", [])
    node_count = len(chain_node_list)
    db.execute(
        """INSERT INTO chain_definition (id, name, discipline, crown_claim, node_count)
           VALUES (?, ?, ?, ?, ?)
           ON CONFLICT(id) DO UPDATE SET
             name=excluded.name, discipline=excluded.discipline,
             crown_claim=excluded.crown_claim, node_count=excluded.node_count""",
        (cid, chain_json["name"], chain_json["discipline"],
         chain_json["crownClaim"], node_count),
    )
    result.chains_upserted = 1

    # Upsert nodes
    for node in nodes:
        inserted = _upsert_node(db, node, cid, chain_json.get("discipline", ""))
        if inserted:
            result.nodes_inserted += 1
        else:
            result.nodes_updated += 1

        # Replace evidence (delete + re-insert)
        nid = node["id"]
        db.execute("DELETE FROM evidence_source WHERE quanta_id = ?", (nid,))
        for ev in node.get("evidence", []):
            db.execute(
                """INSERT INTO evidence_source
                   (quanta_id, chain_id, url, title, finding, year, source_type)
                   VALUES (?,?,?,?,?,?,?)""",
                (nid, cid, ev.get("url", ""), ev.get("title", ""),
                 ev.get("finding", ""), ev.get("year"),
                 ev.get("sourceType", "paper")),
            )
            result.evidence_inserted += 1

    # Upsert edges
    for edge in chain_json.get("edges", []):
        src = edge["source"]
        tgt = edge["target"]
        etype = edge["type"]
        # For cross-chain edges, use the target node's chain_id
        edge_chain = cid
        if "." in tgt:
            tgt_chain = tgt.rsplit(".", 1)[0]
            if tgt_chain != cid:
                edge_chain = tgt_chain
        db.execute(
            """INSERT OR IGNORE INTO chain_edge (chain_id, source_node, target_node, edge_type)
               VALUES (?,?,?,?)""",
            (edge_chain, src, tgt, etype),
        )
        result.edges_upserted += 1

    # Process alternatives
    for alt in chain_json.get("alternatives", []):
        alt_id = alt["id"]
        claim = alt.get("claim", "")
        # Check if we have full JSONL data for this alt
        alt_node = None
        for n in nodes:
            if n.get("id") == alt_id:
                alt_node = n
                break

        if alt_node:
            _upsert_node(db, alt_node, cid, chain_json.get("discipline", ""), layer_override=-1)
        else:
            # Minimal alternative
            db.execute(
                """INSERT INTO chain_node
                   (id, chain_id, claim, discipline, layer, source_type,
                    correspondence, coherence, convergence, pragmatism,
                    intrinsic_score, depends, contradicts)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(id) DO UPDATE SET
                     claim=excluded.claim, discipline=excluded.discipline""",
                (alt_id, cid, claim, chain_json.get("discipline", ""),
                 -1, "alternative", 0, 0, 0, 0, 0.0, "", ""),
            )
        result.alternatives_upserted += 1

    # Recalculate scores for this chain
    result.scores_recalculated = _recalculate_chain_scores(db, cid, verbose)

    db.commit()

    if verbose:
        print(result.summary())

    return result


def import_from_directory(db, directory, validate_first=True, verbose=True):
    """Import chain data from a directory.

    Looks for matching pairs of {chain_id}.json + {chain_id}.jsonl.
    Also supports agent-toolkit layout with chains/ and output/ subdirs.
    """
    results = []

    # Determine layout
    chains_dir = directory
    output_dir = directory
    if os.path.isdir(os.path.join(directory, "chains")):
        chains_dir = os.path.join(directory, "chains")
    if os.path.isdir(os.path.join(directory, "output")):
        output_dir = os.path.join(directory, "output")

    # Find chain JSON files
    json_files = {}
    for f in os.listdir(chains_dir):
        if f.endswith(".json") and not f.startswith("_"):
            chain_id = f[:-5]  # strip .json
            json_files[chain_id] = os.path.join(chains_dir, f)

    # Find JSONL files
    jsonl_files = {}
    for f in os.listdir(output_dir):
        if f.endswith(".jsonl"):
            chain_id = f[:-6]  # strip .jsonl
            jsonl_files[chain_id] = os.path.join(output_dir, f)

    # Import each pair
    paired = set(json_files.keys()) & set(jsonl_files.keys())
    if not paired:
        if verbose:
            print(f"No matching chain JSON + JSONL pairs found in {directory}")
            print(f"  JSON files in {chains_dir}: {list(json_files.keys())}")
            print(f"  JSONL files in {output_dir}: {list(jsonl_files.keys())}")
        return results

    for chain_id in sorted(paired):
        if verbose:
            print(f"\nImporting {chain_id}...")

        with open(json_files[chain_id], "r", encoding="utf-8") as f:
            chain_json = json.load(f)

        nodes = _load_jsonl(jsonl_files[chain_id])

        r = import_chain(db, chain_json, nodes, validate_first, verbose)
        results.append(r)

    # Summary
    if verbose and results:
        total_nodes = sum(r.nodes_inserted + r.nodes_updated for r in results)
        total_edges = sum(r.edges_upserted for r in results)
        failed = sum(1 for r in results if r.validation and not r.validation.is_valid)
        print(f"\nImport complete: {len(results)} chains, {total_nodes} nodes, {total_edges} edges")
        if failed:
            print(f"  {failed} chain(s) failed validation")

    return results


def import_jsonl_only(db, jsonl_path, chain_id=None, validate_first=True, verbose=True):
    """Import just a JSONL file when the chain definition already exists."""
    nodes = _load_jsonl(jsonl_path)

    if not chain_id and nodes:
        chain_id = nodes[0].get("chainId", "unknown")

    # Verify chain exists
    row = db.execute(
        "SELECT * FROM chain_definition WHERE id = ?", (chain_id,)
    ).fetchone()
    if not row:
        print(f"ERROR: chain_definition '{chain_id}' not found in database.")
        print("  Import the chain JSON first, or use import-chain --directory.")
        return ImportResult(chain_id=chain_id or "unknown")

    # Build a minimal chain_json from existing data
    chain_json = {
        "id": row["id"],
        "name": row["name"],
        "discipline": row["discipline"],
        "crownClaim": row["crown_claim"],
        "nodes": [n["id"] for n in nodes],
        "edges": [],
        "alternatives": [],
    }

    return import_chain(db, chain_json, nodes, validate_first, verbose)


def _upsert_node(db, node, chain_id, discipline, layer_override=None):
    """Upsert a single node. Returns True if this was a new insert."""
    nid = node["id"]
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

    # Check if node exists
    existing = db.execute("SELECT id FROM chain_node WHERE id = ?", (nid,)).fetchone()

    db.execute(
        """INSERT INTO chain_node
           (id, chain_id, claim, discipline, layer, source_type,
            correspondence, coherence, convergence, pragmatism,
            intrinsic_score, chain_score, weakest_link,
            moral_care, moral_fairness, moral_loyalty, moral_authority,
            moral_sanctity, moral_liberty, moral_epistemic_humility,
            moral_temporal_stewardship, score_reasoning, key_metrics,
            depends, contradicts, agent_id)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
           ON CONFLICT(id) DO UPDATE SET
             chain_id=excluded.chain_id, claim=excluded.claim,
             discipline=excluded.discipline, layer=excluded.layer,
             source_type=excluded.source_type,
             correspondence=excluded.correspondence, coherence=excluded.coherence,
             convergence=excluded.convergence, pragmatism=excluded.pragmatism,
             intrinsic_score=excluded.intrinsic_score,
             moral_care=excluded.moral_care, moral_fairness=excluded.moral_fairness,
             moral_loyalty=excluded.moral_loyalty, moral_authority=excluded.moral_authority,
             moral_sanctity=excluded.moral_sanctity, moral_liberty=excluded.moral_liberty,
             moral_epistemic_humility=excluded.moral_epistemic_humility,
             moral_temporal_stewardship=excluded.moral_temporal_stewardship,
             score_reasoning=excluded.score_reasoning, key_metrics=excluded.key_metrics,
             depends=excluded.depends, contradicts=excluded.contradicts,
             agent_id=excluded.agent_id""",
        (
            nid, chain_id, node.get("claim", ""),
            node.get("discipline", discipline),
            layer, node.get("sourceType", "unknown"),
            scores.get("correspondence", 0), scores.get("coherence", 0),
            scores.get("convergence", 0), scores.get("pragmatism", 0),
            round(iscore, 2),
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

    return existing is None  # True = new insert


def _recalculate_chain_scores(db, chain_id, verbose=True):
    """Recalculate intrinsic and chain scores for nodes in a chain."""
    rows = db.execute("SELECT * FROM chain_node").fetchall()
    all_nodes = {r["id"]: dict(r) for r in rows}

    # Only update nodes belonging to this chain
    chain_nodes = [nid for nid, n in all_nodes.items() if n["chain_id"] == chain_id]
    updated = 0
    for nid in chain_nodes:
        node = all_nodes[nid]
        iscore = intrinsic_score(node)
        cscore = chain_score(node, all_nodes)
        db.execute(
            "UPDATE chain_node SET intrinsic_score=?, chain_score=? WHERE id=?",
            (round(iscore, 2), round(cscore, 2), nid),
        )
        updated += 1

    if verbose:
        print(f"  Recalculated scores for {updated} nodes in {chain_id}")
    return updated


def _load_jsonl(path):
    """Load a JSONL file into a list of dicts."""
    nodes = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                nodes.append(json.loads(line))
    return nodes
