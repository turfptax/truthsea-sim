/**
 * Worldview lens presets — ported from tsim/scoring.py.
 *
 * Each preset adjusts pillar weights (summing to 100) and
 * moral dimension multipliers used by the lens scoring system.
 */

const DEFAULT_LENS = {
  correspondence: 25,
  coherence: 25,
  relativism: 25,
  pragmatism: 25,
  moral_care: 1.0,
  moral_fairness: 1.0,
  moral_loyalty: 1.0,
  moral_authority: 1.0,
  moral_sanctity: 1.0,
  moral_liberty: 1.0,
  moral_epistemic_humility: 1.0,
  moral_temporal_stewardship: 1.0,
  global_conviction: 1.0,
  epistemic_humility: 50,
  direct_evidence_purity: 50,
  chain_rigidity: 50,
  pragmatic_skepticism: 50,
};

export const PRESETS = {
  blank: { ...DEFAULT_LENS },
  scientist: {
    ...DEFAULT_LENS,
    correspondence: 35, coherence: 30, relativism: 25, pragmatism: 10,
    moral_fairness: 1.2, moral_loyalty: 0.8, moral_authority: 0.9,
    moral_sanctity: 0.7, moral_liberty: 1.3,
    moral_epistemic_humility: 1.5, moral_temporal_stewardship: 1.4,
    epistemic_humility: 70, direct_evidence_purity: 60,
    chain_rigidity: 50, pragmatic_skepticism: 40,
  },
  religious: {
    ...DEFAULT_LENS,
    correspondence: 20, coherence: 35, relativism: 30, pragmatism: 15,
    moral_care: 1.3, moral_loyalty: 1.5, moral_authority: 1.8,
    moral_sanctity: 2.0, moral_liberty: 0.7,
    moral_epistemic_humility: 0.6, moral_temporal_stewardship: 1.2,
    global_conviction: 1.2,
    epistemic_humility: 30, direct_evidence_purity: 20,
    chain_rigidity: 80, pragmatic_skepticism: 20,
  },
  ea: {
    ...DEFAULT_LENS,
    correspondence: 30, coherence: 25, relativism: 20, pragmatism: 25,
    moral_care: 1.8, moral_fairness: 1.5, moral_loyalty: 0.6,
    moral_authority: 0.5, moral_sanctity: 0.4, moral_liberty: 1.2,
    moral_epistemic_humility: 2.0, moral_temporal_stewardship: 2.5,
    global_conviction: 0.9,
    epistemic_humility: 90, direct_evidence_purity: 50,
    chain_rigidity: 40, pragmatic_skepticism: 70,
  },
  libertarian: {
    ...DEFAULT_LENS,
    correspondence: 25, coherence: 20, relativism: 15, pragmatism: 40,
    moral_care: 0.8, moral_loyalty: 0.6, moral_authority: 0.3,
    moral_sanctity: 0.5, moral_liberty: 2.5,
    moral_temporal_stewardship: 0.8,
    global_conviction: 0.8,
    epistemic_humility: 50, direct_evidence_purity: 80,
    chain_rigidity: 30, pragmatic_skepticism: 90,
  },
};

/**
 * Convert a lens preset into propagation pillar_weights array.
 * Lens uses integer weights summing to 100; propagation needs
 * fractional weights summing to ~1.0.
 *
 * Mapping: correspondence -> correspondence, coherence -> coherence,
 *          relativism -> convergence, pragmatism -> pragmatism
 */
export function lensToPillarWeights(lens) {
  const total = lens.correspondence + lens.coherence + lens.relativism + lens.pragmatism;
  return [
    lens.correspondence / total,
    lens.coherence / total,
    lens.relativism / total,
    lens.pragmatism / total,
  ];
}
