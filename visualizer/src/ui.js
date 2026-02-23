/**
 * UI controls: sliders, filters, detail panel rendering.
 */

const LAYER_NAMES = { 0: 'Foundation', 1: 'Method', 2: 'Inference', 3: 'Crown' };
const LAYER_CLASSES = { 0: 'badge-foundation', 1: 'badge-method', 2: 'badge-inference', 3: 'badge-crown' };

const MORAL_KEYS = [
  ['care', 'Care'],
  ['fairness', 'Fairness'],
  ['loyalty', 'Loyalty'],
  ['authority', 'Authority'],
  ['sanctity', 'Sanctity'],
  ['liberty', 'Liberty'],
  ['epistemic_humility', 'Epistemic Humility'],
  ['temporal_stewardship', 'Temporal Stewardship'],
];

/**
 * Initialize all slider controls and wire up change callbacks.
 */
export function initControls(onChange) {
  const sliders = {
    damping: document.getElementById('sl-damping'),
    floor: document.getElementById('sl-floor'),
    penalty: document.getElementById('sl-penalty'),
    'w-corr': document.getElementById('sl-w-corr'),
    'w-coh': document.getElementById('sl-w-coh'),
    'w-conv': document.getElementById('sl-w-conv'),
    'w-prag': document.getElementById('sl-w-prag'),
  };

  const vals = {
    damping: document.getElementById('val-damping'),
    floor: document.getElementById('val-floor'),
    penalty: document.getElementById('val-penalty'),
    'w-corr': document.getElementById('val-w-corr'),
    'w-coh': document.getElementById('val-w-coh'),
    'w-conv': document.getElementById('val-w-conv'),
    'w-prag': document.getElementById('val-w-prag'),
  };

  const weightSum = document.getElementById('weight-sum');

  function updateVals() {
    for (const [key, el] of Object.entries(sliders)) {
      vals[key].textContent = parseFloat(el.value).toFixed(2);
    }
    const sum = ['w-corr', 'w-coh', 'w-conv', 'w-prag']
      .reduce((s, k) => s + parseFloat(sliders[k].value), 0);
    weightSum.textContent = sum.toFixed(2);
    weightSum.style.color = Math.abs(sum - 1.0) < 0.01 ? 'var(--accent)' : 'var(--warning)';
  }

  for (const el of Object.values(sliders)) {
    el.addEventListener('input', () => {
      updateVals();
      onChange(getParams());
    });
  }

  updateVals();
  return sliders;
}

/**
 * Read current slider values into a params object.
 */
export function getParams() {
  return {
    damping: parseFloat(document.getElementById('sl-damping').value),
    floor: parseFloat(document.getElementById('sl-floor').value),
    contradiction_penalty: parseFloat(document.getElementById('sl-penalty').value),
    pillar_weights: [
      parseFloat(document.getElementById('sl-w-corr').value),
      parseFloat(document.getElementById('sl-w-coh').value),
      parseFloat(document.getElementById('sl-w-conv').value),
      parseFloat(document.getElementById('sl-w-prag').value),
    ],
  };
}

/**
 * Set slider values from a params object (used by lens presets).
 */
export function setParams(params) {
  document.getElementById('sl-damping').value = params.damping;
  document.getElementById('sl-floor').value = params.floor;
  document.getElementById('sl-penalty').value = params.contradiction_penalty;
  const [c, h, v, p] = params.pillar_weights;
  document.getElementById('sl-w-corr').value = c;
  document.getElementById('sl-w-coh').value = h;
  document.getElementById('sl-w-conv').value = v;
  document.getElementById('sl-w-prag').value = p;

  // Update displayed values
  for (const [id, valId] of [
    ['sl-damping', 'val-damping'], ['sl-floor', 'val-floor'],
    ['sl-penalty', 'val-penalty'], ['sl-w-corr', 'val-w-corr'],
    ['sl-w-coh', 'val-w-coh'], ['sl-w-conv', 'val-w-conv'],
    ['sl-w-prag', 'val-w-prag'],
  ]) {
    document.getElementById(valId).textContent = parseFloat(document.getElementById(id).value).toFixed(2);
  }

  const sum = params.pillar_weights.reduce((a, b) => a + b, 0);
  const weightSum = document.getElementById('weight-sum');
  weightSum.textContent = sum.toFixed(2);
  weightSum.style.color = Math.abs(sum - 1.0) < 0.01 ? 'var(--accent)' : 'var(--warning)';
}

/**
 * Build chain filter checkboxes from graph data.
 */
export function initChainFilters(chains, onChange) {
  const container = document.getElementById('chain-filters');
  container.innerHTML = '';
  const sorted = Object.entries(chains).sort((a, b) => a[1].name.localeCompare(b[1].name));
  for (const [id, chain] of sorted) {
    const label = document.createElement('label');
    const cb = document.createElement('input');
    cb.type = 'checkbox';
    cb.checked = true;
    cb.dataset.chain = id;
    cb.addEventListener('change', onChange);
    label.appendChild(cb);
    label.appendChild(document.createTextNode(' ' + chain.name));
    container.appendChild(label);
  }
}

/**
 * Get current filter state: which chains and layers are visible.
 */
export function getFilters() {
  const chains = new Set();
  document.querySelectorAll('#chain-filters input:checked').forEach(cb => {
    chains.add(cb.dataset.chain);
  });
  const layers = new Set();
  document.querySelectorAll('#layer-filters input:checked').forEach(cb => {
    layers.add(parseInt(cb.dataset.layer));
  });
  return { chains, layers };
}

/**
 * Update the metrics display.
 */
export function updateMetrics(metrics) {
  document.getElementById('metric-avg').textContent = metrics.avg_chain_score;
  document.getElementById('metric-min').textContent = metrics.min_chain_score;
  document.getElementById('metric-max').textContent = metrics.max_chain_score;
}

/**
 * Score to color mapping.
 */
export function scoreColor(score) {
  if (score >= 80) return '#00e5b0';
  if (score >= 60) return '#ffd700';
  if (score >= 40) return '#ff6b35';
  return '#ff4757';
}

/**
 * Render the detail panel for a selected node.
 */
export function showDetail(node, onNodeClick) {
  const panel = document.getElementById('detail-panel');
  const content = document.getElementById('detail-content');
  panel.classList.remove('hidden');

  const layerName = LAYER_NAMES[node.layer] || 'Unknown';
  const layerClass = LAYER_CLASSES[node.layer] || 'badge-foundation';
  const chainScore = node.new_chain_score ?? node.chain_score ?? 0;
  const intrinsic = node.new_intrinsic ?? node.intrinsic_score ?? 0;
  const color = scoreColor(chainScore);

  let html = `
    <div class="detail-claim">${escHtml(node.claim)}</div>
    <div class="detail-meta">
      <span class="badge ${layerClass}">${layerName}</span>
      <span class="badge badge-discipline">${escHtml(node.discipline)}</span>
    </div>

    <div class="score-label">Chain Score</div>
    <div class="score-big" style="color:${color}">${chainScore.toFixed(1)}</div>

    <div class="score-row">
      <span class="score-label">Intrinsic</span>
      <span class="score-value">${intrinsic.toFixed(1)}</span>
    </div>
  `;

  // Pillar scores
  html += '<div class="detail-section"><h3>Pillars</h3>';
  const pillars = node.pillar_scores;
  for (const [key, label] of [['correspondence', 'Correspondence'], ['coherence', 'Coherence'],
    ['convergence', 'Convergence'], ['pragmatism', 'Pragmatism']]) {
    const val = pillars[key];
    html += barHtml(label, val, 100, scoreColor(val));
  }
  html += '</div>';

  // Moral vector
  html += '<div class="detail-section"><h3>Moral Vector</h3>';
  for (const [key, label] of MORAL_KEYS) {
    const val = node.moral_vector[key] ?? 0;
    html += barHtml(label, val, 100, '#7c8ba5');
  }
  html += '</div>';

  // Evidence
  html += `<div class="detail-section"><h3>Evidence</h3>
    <div class="evidence-count"><span>${node.evidence_count || 0}</span> sources</div></div>`;

  // Dependencies
  if (node.depends && node.depends.length) {
    html += '<div class="detail-section"><h3>Depends On</h3>';
    for (const depId of node.depends) {
      html += `<a class="dep-link" data-node-id="${escHtml(depId)}">${escHtml(depId)}</a>`;
    }
    html += '</div>';
  }

  // Contradictions
  if (node.contradicts && node.contradicts.length) {
    html += '<div class="detail-section"><h3>Contradicts</h3>';
    for (const cId of node.contradicts) {
      html += `<a class="dep-link contradicts" data-node-id="${escHtml(cId)}">${escHtml(cId)}</a>`;
    }
    html += '</div>';
  }

  content.innerHTML = html;

  // Wire up dependency clicks
  content.querySelectorAll('.dep-link').forEach(link => {
    link.addEventListener('click', () => {
      const targetId = link.dataset.nodeId;
      if (onNodeClick) onNodeClick(targetId);
    });
  });
}

export function hideDetail() {
  document.getElementById('detail-panel').classList.add('hidden');
}

function barHtml(label, value, max, color) {
  const pct = Math.max(0, Math.min(100, (value / max) * 100));
  return `<div class="bar-container">
    <div class="bar-label"><span>${label}</span><span>${value}</span></div>
    <div class="bar-track"><div class="bar-fill" style="width:${pct}%;background:${color}"></div></div>
  </div>`;
}

function escHtml(str) {
  if (!str) return '';
  return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}
