/**
 * TruthDAG 3D Visualizer — main entry point.
 *
 * Loads graph.json, initializes 3d-force-graph, wires up
 * UI controls for real-time score propagation.
 */

import ForceGraph3D from '3d-force-graph';
import * as THREE from 'three';
import { propagateScores, DEFAULT_PARAMS } from './propagate.js';
import { PRESETS, lensToPillarWeights } from './lenses.js';
import {
  initControls, getParams, setParams,
  initChainFilters, getFilters, updateMetrics,
  scoreColor, showDetail, hideDetail,
} from './ui.js';

const LAYER_COLORS = {
  0: '#00e5b0', // Foundation
  1: '#00a8ff', // Method
  2: '#ffd700', // Inference
  3: '#a855f7', // Crown
};

const EDGE_COLORS = {
  depends: '#00a8ff',
  supports: '#2ed573',
  contradicts: '#ff4757',
};

let rawData = null;     // Original graph.json data
let propagated = null;  // Latest propagation result
let graph = null;       // 3d-force-graph instance
let selectedNodeId = null;

async function init() {
  // Load data
  const resp = await fetch('/graph.json');
  rawData = await resp.json();

  document.getElementById('graph-stats').textContent =
    `${rawData.meta.node_count} nodes \u00b7 ${rawData.meta.edge_count} edges \u00b7 ${rawData.meta.chain_count} chains`;

  // Initial propagation
  propagated = propagateScores(rawData, DEFAULT_PARAMS);
  updateMetrics(propagated.metrics);

  // Init UI
  initControls(onParamsChange);
  initChainFilters(rawData.chains, onFilterChange);

  // Lens selector
  document.getElementById('lens-select').addEventListener('change', onLensChange);

  // Layer filter checkboxes
  document.querySelectorAll('#layer-filters input').forEach(cb => {
    cb.addEventListener('change', onFilterChange);
  });

  // Detail close button
  document.getElementById('detail-close').addEventListener('click', () => {
    selectedNodeId = null;
    hideDetail();
  });

  // Build graph
  buildGraph();
}

function buildGraph() {
  const container = document.getElementById('graph-container');
  const { filteredNodes, filteredEdges } = getFilteredData();

  graph = ForceGraph3D()(container)
    .graphData({ nodes: filteredNodes, links: filteredEdges })
    .nodeId('id')
    .linkSource('source')
    .linkTarget('target')
    .backgroundColor('#060c18')
    .nodeVal(n => {
      const score = propagated.nodes[n.id]?.new_chain_score ?? 50;
      return Math.max(1, score / 10);
    })
    .nodeColor(n => {
      const score = propagated.nodes[n.id]?.new_chain_score ?? 50;
      return scoreColor(score);
    })
    .nodeOpacity(0.9)
    .nodeLabel(n => {
      const score = propagated.nodes[n.id]?.new_chain_score ?? 0;
      return `${n.claim.slice(0, 80)}\nScore: ${score.toFixed(1)}`;
    })
    .linkColor(l => EDGE_COLORS[l.type] || '#334466')
    .linkOpacity(0.4)
    .linkWidth(0.5)
    .linkDirectionalArrowLength(3.5)
    .linkDirectionalArrowRelPos(1)
    .linkDirectionalArrowColor(l => EDGE_COLORS[l.type] || '#334466')
    .onNodeClick(onNodeClick)
    .onBackgroundClick(() => {
      selectedNodeId = null;
      hideDetail();
    });

  // Warm-up ticks for layout
  graph.d3Force('charge').strength(-30);
  graph.d3Force('link').distance(40);
}

function getFilteredData() {
  const filters = getFilters();

  const filteredNodes = rawData.nodes.filter(n =>
    filters.chains.has(n.chain_id) && filters.layers.has(n.layer)
  );

  const visibleIds = new Set(filteredNodes.map(n => n.id));

  const filteredEdges = rawData.edges
    .filter(e => visibleIds.has(e.source) && visibleIds.has(e.target))
    .map(e => ({ ...e })); // Clone to avoid mutation

  return { filteredNodes, filteredEdges };
}

function onParamsChange(params) {
  // Set lens dropdown to "Custom" when user manually adjusts sliders
  document.getElementById('lens-select').value = 'custom';
  recalculate(params);
}

function onLensChange(e) {
  const preset = e.target.value;
  if (preset === 'custom') return;

  const lens = PRESETS[preset];
  if (!lens) return;

  const weights = lensToPillarWeights(lens);
  const params = {
    ...getParams(),
    pillar_weights: weights,
  };
  setParams(params);
  recalculate(params);
}

function onFilterChange() {
  const { filteredNodes, filteredEdges } = getFilteredData();
  graph.graphData({ nodes: filteredNodes, links: filteredEdges });
}

function recalculate(params) {
  propagated = propagateScores(rawData, params);
  updateMetrics(propagated.metrics);

  // Re-render node colors and sizes
  graph.nodeVal(graph.nodeVal());
  graph.nodeColor(graph.nodeColor());

  // Update detail panel if a node is selected
  if (selectedNodeId && propagated.nodes[selectedNodeId]) {
    showDetail(propagated.nodes[selectedNodeId], navigateToNode);
  }
}

function onNodeClick(node) {
  if (!node) return;
  selectedNodeId = node.id;

  const pNode = propagated.nodes[node.id];
  if (pNode) {
    showDetail(pNode, navigateToNode);
  }

  // Aim camera at clicked node
  const distance = 120;
  const distRatio = 1 + distance / Math.hypot(node.x, node.y, node.z);
  graph.cameraPosition(
    { x: node.x * distRatio, y: node.y * distRatio, z: node.z * distRatio },
    node,
    1000
  );
}

function navigateToNode(nodeId) {
  // Find the node in the graph data
  const gData = graph.graphData();
  const target = gData.nodes.find(n => n.id === nodeId);
  if (target) {
    onNodeClick(target);
  }
}

init();
