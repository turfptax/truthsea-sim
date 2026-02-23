/**
 * TruthDAG V2 score propagation — JS port of simulate.py.
 *
 * Runs entirely in-browser for instant slider feedback.
 */

export const DEFAULT_PARAMS = {
  damping: 0.7,
  floor: 0.3,
  contradiction_penalty: 0.15,
  pillar_weights: [0.30, 0.25, 0.25, 0.20],
  max_depth: 20,
};

const PILLAR_KEYS = ['correspondence', 'coherence', 'convergence', 'pragmatism'];

function computeIntrinsic(pillarScores, weights) {
  return PILLAR_KEYS.reduce((sum, key, i) => sum + pillarScores[key] * weights[i], 0);
}

/**
 * Topological sort by dependency edges (Kahn's algorithm).
 */
function topoSort(nodes) {
  const ids = Object.keys(nodes);
  const inDegree = {};
  const adjacency = {};
  for (const nid of ids) {
    inDegree[nid] = 0;
    adjacency[nid] = [];
  }
  for (const nid of ids) {
    for (const depId of nodes[nid].depends) {
      if (depId in nodes) {
        adjacency[depId].push(nid);
        inDegree[nid]++;
      }
    }
  }

  const queue = ids.filter(nid => inDegree[nid] === 0);
  queue.sort((a, b) => nodes[a].layer - nodes[b].layer);
  const order = [];

  while (queue.length) {
    const nid = queue.shift();
    order.push(nid);
    for (const child of adjacency[nid]) {
      inDegree[child]--;
      if (inDegree[child] === 0) queue.push(child);
    }
  }

  // Append remaining (cycles)
  const seen = new Set(order);
  for (const nid of ids) {
    if (!seen.has(nid)) order.push(nid);
  }
  return order;
}

/**
 * Propagate scores through the DAG using tunable parameters.
 *
 * @param {Object} graphData - Raw graph data { nodes: [...], edges: [...] }
 * @param {Object} params - Override any DEFAULT_PARAMS keys
 * @returns {Object} - { nodes: {id: nodeWithScores}, metrics }
 */
export function propagateScores(graphData, params = {}) {
  const p = { ...DEFAULT_PARAMS, ...params };
  const { damping, floor, contradiction_penalty, pillar_weights, max_depth } = p;

  // Build node lookup (deep-copy pillar_scores to avoid mutation)
  const nodes = {};
  for (const n of graphData.nodes) {
    nodes[n.id] = {
      ...n,
      pillar_scores: { ...n.pillar_scores },
      depends: [...(n.depends || [])],
      contradicts: [...(n.contradicts || [])],
    };
  }

  // Phase 1: Compute intrinsic scores
  for (const nid of Object.keys(nodes)) {
    nodes[nid].new_intrinsic = computeIntrinsic(nodes[nid].pillar_scores, pillar_weights);
  }

  // Phase 2: Topological propagation
  const order = topoSort(nodes);
  const cache = {};

  function chainScore(nid, depth = 0) {
    if (nid in cache) return cache[nid];
    if (depth > max_depth) return nodes[nid].new_intrinsic;

    const node = nodes[nid];
    const intrinsic = node.new_intrinsic;

    const deps = node.depends.filter(d => d in nodes);
    let minDep = 100;
    if (deps.length) {
      const depScores = deps.map(d => chainScore(d, depth + 1));
      minDep = Math.min(...depScores);
    }

    const contras = node.contradicts.filter(c => c in nodes);
    const nContradictions = contras.length;

    let score = intrinsic * (floor + damping * minDep / 100) * (1 - contradiction_penalty * nContradictions);
    score = Math.max(0, Math.min(100, score));
    cache[nid] = Math.round(score * 100) / 100;
    return cache[nid];
  }

  for (const nid of order) {
    chainScore(nid);
  }

  // Attach computed scores to nodes
  for (const nid of Object.keys(nodes)) {
    nodes[nid].new_chain_score = cache[nid] ?? nodes[nid].new_intrinsic;
  }

  // Metrics
  const scores = Object.values(nodes).map(n => n.new_chain_score);
  const avg = scores.reduce((a, b) => a + b, 0) / scores.length;

  return {
    nodes,
    metrics: {
      nodes_processed: scores.length,
      avg_chain_score: Math.round(avg * 10) / 10,
      min_chain_score: Math.round(Math.min(...scores) * 10) / 10,
      max_chain_score: Math.round(Math.max(...scores) * 10) / 10,
    },
  };
}
