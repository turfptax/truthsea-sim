"""Validation logic for TruthSea chain JSON and JSONL data."""

import json
from dataclasses import dataclass, field


VALID_SOURCE_TYPES = {
    "VERIFIED_EXPERIMENT", "RAW_MEDIA", "CONTENT_SIGNED",
    "AI_GENERATED", "ANONYMOUS", "alternative", "unknown",
}

REQUIRED_NODE_FIELDS = {"id", "chainId", "claim", "discipline", "layer", "sourceType", "scores"}
REQUIRED_SCORE_FIELDS = {"correspondence", "coherence", "convergence", "pragmatism"}
REQUIRED_MORAL_FIELDS = {
    "care", "fairness", "loyalty", "authority",
    "sanctity", "liberty", "epistemicHumility", "temporalStewardship",
}
REQUIRED_EVIDENCE_FIELDS = {"url", "title", "finding"}
VALID_EDGE_TYPES = {"depends", "supports", "contradicts"}


@dataclass
class ValidationError:
    severity: str       # "error" or "warning"
    field: str
    message: str
    node_id: str = ""

    def __str__(self):
        prefix = "ERROR" if self.severity == "error" else "WARNING"
        loc = f"[{self.node_id}] " if self.node_id else ""
        return f"  {prefix}: {loc}{self.field}: {self.message}"


@dataclass
class ValidationResult:
    chain_id: str
    errors: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    node_count: int = 0
    edge_count: int = 0
    evidence_count: int = 0

    @property
    def is_valid(self) -> bool:
        return len(self.errors) == 0

    def summary(self) -> str:
        status = "PASS" if self.is_valid else "FAIL"
        parts = [
            f"Validation [{status}]: {self.chain_id}",
            f"  {self.node_count} nodes, {self.edge_count} edges, {self.evidence_count} evidence",
        ]
        if self.errors:
            parts.append(f"  {len(self.errors)} error(s)")
        if self.warnings:
            parts.append(f"  {len(self.warnings)} warning(s)")
        return "\n".join(parts)


def validate_node(node: dict, chain_id: str, known_node_ids: set) -> list:
    """Validate a single JSONL node record. Returns list of ValidationError."""
    errs = []
    nid = node.get("id", "?")

    # Required fields
    for f in REQUIRED_NODE_FIELDS:
        if f not in node:
            errs.append(ValidationError("error", f, "required field missing", nid))

    # ID format
    if "id" in node and "." not in str(node["id"]):
        errs.append(ValidationError("error", "id", f"must be {{chainId}}.{{name}}, got '{node['id']}'", nid))
    if "chainId" in node and "id" in node:
        if not str(node["id"]).startswith(str(node["chainId"]) + "."):
            errs.append(ValidationError("warning", "id", f"id '{node['id']}' doesn't start with chainId '{node['chainId']}'", nid))

    # Layer
    layer = node.get("layer")
    if layer is not None and not isinstance(layer, int):
        errs.append(ValidationError("error", "layer", f"must be int, got {type(layer).__name__}", nid))
    elif layer is not None and layer not in (-1, 0, 1, 2, 3):
        errs.append(ValidationError("error", "layer", f"must be -1..3, got {layer}", nid))

    # Source type
    st = node.get("sourceType")
    if st and st not in VALID_SOURCE_TYPES:
        errs.append(ValidationError("warning", "sourceType", f"unusual value '{st}'", nid))

    # Pillar scores
    scores = node.get("scores", {})
    if isinstance(scores, dict):
        for sf in REQUIRED_SCORE_FIELDS:
            if sf not in scores:
                errs.append(ValidationError("error", f"scores.{sf}", "missing", nid))
            else:
                v = scores[sf]
                if not isinstance(v, (int, float)):
                    errs.append(ValidationError("error", f"scores.{sf}", f"must be numeric, got {type(v).__name__}", nid))
                elif v < 0 or v > 100:
                    errs.append(ValidationError("error", f"scores.{sf}", f"must be 0-100, got {v}", nid))
    else:
        errs.append(ValidationError("error", "scores", "must be an object", nid))

    # Moral vector
    mv = node.get("moralVector", {})
    if isinstance(mv, dict):
        for mf in REQUIRED_MORAL_FIELDS:
            if mf not in mv:
                errs.append(ValidationError("warning", f"moralVector.{mf}", "missing", nid))
            else:
                v = mv[mf]
                if isinstance(v, (int, float)) and (v < -100 or v > 100):
                    errs.append(ValidationError("error", f"moralVector.{mf}", f"must be -100..100, got {v}", nid))
    else:
        errs.append(ValidationError("warning", "moralVector", "missing or not an object", nid))

    # Evidence
    evidence = node.get("evidence", [])
    if not isinstance(evidence, list) or len(evidence) == 0:
        errs.append(ValidationError("warning", "evidence", "should have at least 1 source", nid))
    else:
        for i, ev in enumerate(evidence):
            for ef in REQUIRED_EVIDENCE_FIELDS:
                if ef not in ev:
                    errs.append(ValidationError("warning", f"evidence[{i}].{ef}", "missing", nid))

    # Score reasoning
    sr = node.get("scoreReasoning")
    if not sr or not isinstance(sr, dict):
        errs.append(ValidationError("warning", "scoreReasoning", "missing or not an object", nid))

    # Depends / contradicts
    depends = node.get("depends", [])
    if isinstance(depends, list):
        for dep in depends:
            if dep and dep not in known_node_ids:
                errs.append(ValidationError("warning", "depends", f"references unknown node '{dep}'", nid))
    contradicts = node.get("contradicts", [])
    if isinstance(contradicts, list):
        for con in contradicts:
            if con and con not in known_node_ids:
                errs.append(ValidationError("warning", "contradicts", f"references unknown node '{con}'", nid))

    return errs


def validate_chain_json(chain: dict) -> list:
    """Validate a chain definition JSON. Returns list of ValidationError."""
    errs = []
    cid = chain.get("id", "?")

    for f in ("id", "name", "discipline", "crownClaim"):
        if f not in chain:
            errs.append(ValidationError("error", f, "required field missing"))

    nodes = chain.get("nodes", [])
    if not isinstance(nodes, list) or len(nodes) == 0:
        errs.append(ValidationError("error", "nodes", "must be a non-empty list"))

    node_set = set()
    for n in nodes:
        if isinstance(n, str):
            node_set.add(n)
        elif isinstance(n, dict) and "id" in n:
            node_set.add(n["id"])

    # Include alternatives in the known set for edge validation
    for alt in chain.get("alternatives", []):
        if "id" in alt:
            node_set.add(alt["id"])

    edges = chain.get("edges", [])
    for i, edge in enumerate(edges):
        for f in ("source", "target", "type"):
            if f not in edge:
                errs.append(ValidationError("error", f"edges[{i}].{f}", "missing"))
        if "type" in edge and edge["type"] not in VALID_EDGE_TYPES:
            errs.append(ValidationError("error", f"edges[{i}].type", f"invalid: '{edge['type']}'"))
        if "source" in edge and edge["source"] not in node_set:
            errs.append(ValidationError("warning", f"edges[{i}].source", f"'{edge['source']}' not in node list"))
        if "target" in edge and edge["target"] not in node_set:
            errs.append(ValidationError("warning", f"edges[{i}].target", f"'{edge['target']}' not in node list"))

    for i, alt in enumerate(chain.get("alternatives", [])):
        for f in ("id", "claim"):
            if f not in alt:
                errs.append(ValidationError("error", f"alternatives[{i}].{f}", "missing"))

    return errs


def validate_chain_dataset(
    chain_json: dict,
    nodes: list,
    existing_node_ids: set | None = None,
) -> ValidationResult:
    """Full validation of a chain definition + its JSONL nodes."""
    cid = chain_json.get("id", "unknown")
    result = ValidationResult(chain_id=cid)

    # Validate chain JSON
    chain_errs = validate_chain_json(chain_json)
    for e in chain_errs:
        if e.severity == "error":
            result.errors.append(e)
        else:
            result.warnings.append(e)

    # Build known ID set: nodes from this chain + existing DB nodes
    node_ids = {n.get("id") for n in nodes if "id" in n}
    all_known = node_ids | (existing_node_ids or set())

    # Also add alt IDs from chain JSON
    for alt in chain_json.get("alternatives", []):
        if "id" in alt:
            all_known.add(alt["id"])

    # Validate each node
    ev_count = 0
    seen_ids = set()
    for node in nodes:
        nid = node.get("id", "?")
        if nid in seen_ids:
            result.errors.append(ValidationError("error", "id", f"duplicate node ID '{nid}'", nid))
        seen_ids.add(nid)

        node_errs = validate_node(node, cid, all_known)
        for e in node_errs:
            if e.severity == "error":
                result.errors.append(e)
            else:
                result.warnings.append(e)

        ev_count += len(node.get("evidence", []))

    # Cross-check: every node ID in chain JSON should have a JSONL record
    chain_node_list = chain_json.get("nodes", [])
    for cn in chain_node_list:
        cn_id = cn if isinstance(cn, str) else cn.get("id", "")
        if cn_id and cn_id not in node_ids:
            result.warnings.append(
                ValidationError("warning", "nodes", f"chain lists '{cn_id}' but no JSONL record found")
            )

    result.node_count = len(nodes)
    result.edge_count = len(chain_json.get("edges", []))
    result.evidence_count = ev_count

    return result


def validate_jsonl_file(path: str, chain_id: str | None = None) -> ValidationResult:
    """Validate a standalone JSONL file."""
    nodes = []
    line_errors = []

    with open(path, "r", encoding="utf-8") as f:
        for i, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                nodes.append(obj)
            except json.JSONDecodeError as e:
                line_errors.append(
                    ValidationError("error", f"line {i}", f"invalid JSON: {e}")
                )

    # Infer chain_id from first record
    if not chain_id and nodes:
        chain_id = nodes[0].get("chainId", "unknown")

    result = ValidationResult(chain_id=chain_id or "unknown")
    result.errors.extend(line_errors)

    node_ids = {n.get("id") for n in nodes if "id" in n}
    ev_count = 0

    for node in nodes:
        errs = validate_node(node, chain_id or "", node_ids)
        for e in errs:
            if e.severity == "error":
                result.errors.append(e)
            else:
                result.warnings.append(e)
        ev_count += len(node.get("evidence", []))

    result.node_count = len(nodes)
    result.evidence_count = ev_count
    return result
