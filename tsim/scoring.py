"""Scoring formulas ported from the TypeScript dashboard.

Intrinsic score: 0.30*corr + 0.25*coh + 0.25*conv + 0.20*prag
Chain score:     intrinsic * (0.3 + 0.7 * weakest_dep/100) + support_boost - contradiction_penalty
Lens v1.0:       base * humility * purity * rigidity * skepticism
"""

import math
import sqlite3
from typing import Optional


DIRECT_EVIDENCE_TYPES = {"VERIFIED_EXPERIMENT", "RAW_MEDIA"}

# Default lens preset values (Blank Slate)
DEFAULT_LENS = {
    "correspondence": 25,
    "coherence": 25,
    "relativism": 25,
    "pragmatism": 25,
    "moral_care": 1.0,
    "moral_fairness": 1.0,
    "moral_loyalty": 1.0,
    "moral_authority": 1.0,
    "moral_sanctity": 1.0,
    "moral_liberty": 1.0,
    "moral_epistemic_humility": 1.0,
    "moral_temporal_stewardship": 1.0,
    "global_conviction": 1.0,
    "epistemic_humility": 50,
    "direct_evidence_purity": 50,
    "chain_rigidity": 50,
    "pragmatic_skepticism": 50,
}

PRESETS = {
    "scientist": {
        **DEFAULT_LENS,
        "correspondence": 35, "coherence": 30, "relativism": 25, "pragmatism": 10,
        "moral_fairness": 1.2, "moral_loyalty": 0.8, "moral_authority": 0.9,
        "moral_sanctity": 0.7, "moral_liberty": 1.3,
        "moral_epistemic_humility": 1.5, "moral_temporal_stewardship": 1.4,
        "epistemic_humility": 70, "direct_evidence_purity": 60,
        "chain_rigidity": 50, "pragmatic_skepticism": 40,
    },
    "religious": {
        **DEFAULT_LENS,
        "correspondence": 20, "coherence": 35, "relativism": 30, "pragmatism": 15,
        "moral_care": 1.3, "moral_loyalty": 1.5, "moral_authority": 1.8,
        "moral_sanctity": 2.0, "moral_liberty": 0.7,
        "moral_epistemic_humility": 0.6, "moral_temporal_stewardship": 1.2,
        "global_conviction": 1.2,
        "epistemic_humility": 30, "direct_evidence_purity": 20,
        "chain_rigidity": 80, "pragmatic_skepticism": 20,
    },
    "ea": {
        **DEFAULT_LENS,
        "correspondence": 30, "coherence": 25, "relativism": 20, "pragmatism": 25,
        "moral_care": 1.8, "moral_fairness": 1.5, "moral_loyalty": 0.6,
        "moral_authority": 0.5, "moral_sanctity": 0.4, "moral_liberty": 1.2,
        "moral_epistemic_humility": 2.0, "moral_temporal_stewardship": 2.5,
        "global_conviction": 0.9,
        "epistemic_humility": 90, "direct_evidence_purity": 50,
        "chain_rigidity": 40, "pragmatic_skepticism": 70,
    },
    "libertarian": {
        **DEFAULT_LENS,
        "correspondence": 25, "coherence": 20, "relativism": 15, "pragmatism": 40,
        "moral_care": 0.8, "moral_loyalty": 0.6, "moral_authority": 0.3,
        "moral_sanctity": 0.5, "moral_liberty": 2.5,
        "moral_temporal_stewardship": 0.8,
        "global_conviction": 0.8,
        "epistemic_humility": 50, "direct_evidence_purity": 80,
        "chain_rigidity": 30, "pragmatic_skepticism": 90,
    },
    "blank": DEFAULT_LENS,
}


def intrinsic_score(node: dict) -> float:
    """Compute intrinsic score from 4 pillars."""
    return (
        0.30 * node["correspondence"]
        + 0.25 * node["coherence"]
        + 0.25 * node["convergence"]
        + 0.20 * node["pragmatism"]
    )


def chain_score(
    node: dict, all_nodes: dict[str, dict], support_boost: float = 0.0
) -> float:
    """Compute chain score with dependency walk.

    Formula: intrinsic * (0.3 + 0.7 * weakest_dep/100) + support_boost - contradiction_penalty
    """
    iscore = node.get("intrinsic_score") or intrinsic_score(node)

    # Find weakest dependency
    depends = _parse_list(node.get("depends", ""))
    weakest_dep = 100.0
    if depends:
        for dep_id in depends:
            dep = all_nodes.get(dep_id)
            if dep:
                dep_score = dep.get("intrinsic_score") or intrinsic_score(dep)
                weakest_dep = min(weakest_dep, dep_score)

    # Contradiction penalty
    contradicts = _parse_list(node.get("contradicts", ""))
    contradiction_penalty = len(contradicts) * 2.0  # 2 points per contradiction

    score = iscore * (0.3 + 0.7 * weakest_dep / 100) + support_boost - contradiction_penalty
    return max(0.0, min(100.0, score))


def apply_lens(node: dict, lens: dict, all_nodes: Optional[dict[str, dict]] = None) -> dict:
    """Apply worldview lens v1.0 to a single quanta. Returns scoring results dict."""
    # 1. Pillar score — relativism weight maps to convergence data
    pillar_score = (
        node["correspondence"] * lens["correspondence"]
        + node["coherence"] * lens["coherence"]
        + node["convergence"] * lens["relativism"]
        + node["pragmatism"] * lens["pragmatism"]
    ) / 100.0

    # 2. Moral multiplier (geometric mean of 8 values)
    moral_keys = [
        "moral_care", "moral_fairness", "moral_loyalty", "moral_authority",
        "moral_sanctity", "moral_liberty", "moral_epistemic_humility",
        "moral_temporal_stewardship",
    ]
    moral_product = 1.0
    for mk in moral_keys:
        moral_product *= lens[mk]
    moral_multiplier = moral_product ** (1 / 8)

    # 3. Base score
    base_score = pillar_score * moral_multiplier * lens["global_conviction"]

    # 4a. Epistemic Humility factor
    moral_eh = node.get("moral_epistemic_humility", 0)
    humility_factor = 1 - (lens["epistemic_humility"] / 100) * (1 - moral_eh / 100)

    # 4b. Direct Evidence Purity factor
    has_direct = node.get("source_type", "") in DIRECT_EVIDENCE_TYPES
    if has_direct:
        purity_factor = 1 + lens["direct_evidence_purity"] / 200
    else:
        purity_factor = 1 - lens["direct_evidence_purity"] / 200

    # 4c. Chain Rigidity factor
    rigidity_factor = 1.0
    depends = _parse_list(node.get("depends", ""))
    if depends and all_nodes:
        weakest_ratio = 1.0
        wl = node.get("weakest_link")
        if wl and wl in all_nodes:
            wn = all_nodes[wl]
            wn_score = wn.get("intrinsic_score") or intrinsic_score(wn)
            weakest_ratio = wn_score / 100
        else:
            min_score = 100.0
            for dep_id in depends:
                dep = all_nodes.get(dep_id)
                if dep:
                    ds = dep.get("intrinsic_score") or intrinsic_score(dep)
                    min_score = min(min_score, ds)
            weakest_ratio = min_score / 100
        rigidity_factor = 1 - (lens["chain_rigidity"] / 100) * (1 - weakest_ratio)

    # 4d. Pragmatic Skepticism factor
    skepticism_factor = 1 - (lens["pragmatic_skepticism"] / 100) * (1 - node["pragmatism"] / 100)

    # 5. Final score
    final_score = base_score * humility_factor * purity_factor * rigidity_factor * skepticism_factor
    final_score = max(0.0, min(100.0, final_score))
    final_score = round(final_score, 1)

    visual_opacity = max(0.15, min(1.0, final_score / 100))
    edge_warning = final_score < 30

    return {
        "final_score": final_score,
        "pillar_score": round(pillar_score, 2),
        "moral_multiplier": round(moral_multiplier, 4),
        "humility_factor": round(humility_factor, 4),
        "purity_factor": round(purity_factor, 4),
        "rigidity_factor": round(rigidity_factor, 4),
        "skepticism_factor": round(skepticism_factor, 4),
        "visual_opacity": round(visual_opacity, 3),
        "edge_warning": edge_warning,
        "has_direct_evidence": has_direct,
    }


def recalculate_all(db: sqlite3.Connection, lens: Optional[dict] = None) -> list[dict]:
    """Recalculate scores for all quanta using a lens. Returns list of results."""
    if lens is None:
        lens = DEFAULT_LENS

    rows = db.execute("SELECT * FROM chain_node WHERE layer >= 0").fetchall()
    all_nodes = {r["id"]: dict(r) for r in rows}

    results = []
    for node_id, node in all_nodes.items():
        result = apply_lens(node, lens, all_nodes)
        result["id"] = node_id
        result["claim"] = node["claim"]
        result["chain_id"] = node["chain_id"]
        result["discipline"] = node["discipline"]
        result["layer"] = node["layer"]
        result["intrinsic_score"] = node.get("intrinsic_score") or intrinsic_score(node)
        results.append(result)

    results.sort(key=lambda r: r["final_score"], reverse=True)
    return results


def _parse_list(val) -> list[str]:
    """Parse a comma-separated string or list into a list of non-empty strings."""
    if isinstance(val, list):
        return [v for v in val if v]
    if isinstance(val, str) and val.strip():
        return [v.strip() for v in val.split(",") if v.strip()]
    return []
