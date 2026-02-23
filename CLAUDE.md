# TruthSea Local Simulation Environment

## What This Is
A Python + SQLite simulation environment for the TruthSea epistemic truth-scoring protocol. It mirrors the blockchain-based TruthSea system but runs entirely locally without any crypto/blockchain dependencies. You can run agent-based verification simulations, apply worldview lenses, and analyze results.

## Quick Start
```bash
cd truthsea-sim
python cli.py reset          # Fresh database
python cli.py seed           # Import 20 chains / 151 quanta from JSONL
python cli.py import-chain --directory chains/   # Add coherence theory chains
python cli.py simulate --rounds 10 --honest 5 --malicious 2
python cli.py report 1       # View results
```

## Project Structure
```
cli.py              # CLI entry point (argparse) — start here for usage
simulate.py         # Standalone DAG propagation with tunable params
seed.py             # Imports data from ../TruthSea/agent-toolkit/chains/ + output/
schema.sql          # SQLite schema (10 tables)
truthsea.db         # Generated database (created by init/seed)
tsim/
  db.py             # get_db(), init_db(), reset_db()
  scoring.py        # intrinsic_score(), chain_score(), apply_lens(), PRESETS
  agents.py         # 4 agent types: honest, random, malicious, strategic
  economics.py      # stake_weighted_consensus(), distribute_rewards()
  simulation.py     # run_simulation(db, SimConfig) — main loop
  anomaly.py        # Bayesian classification: fabrication/genuine/misinterpretation
  reports.py        # summary_report(), export_csv(), anomaly_report()
  validate.py       # Chain/JSONL data validation (ValidationError, ValidationResult)
  importer.py       # Incremental import with ON CONFLICT upsert
scenarios/
  sabotage_test.py  # Multi-target sabotage scenario with cascade analysis + plots
chains/             # Local chain data (JSON + JSONL pairs, importable)
  epistemic_foundations.json + .jsonl
  philosophy_of_science.json + .jsonl
  mathematical_foundations.json + .jsonl
  consciousness_foundations.json + .jsonl
  physical_reality.json + .jsonl
  classical_mechanics.json + .jsonl
  calculus_foundations.json + .jsonl
  empirical_measurement.json + .jsonl
  logic_and_proof.json + .jsonl
missions/           # Mission templates for external AI agents
visualizer/         # 3D interactive graph visualizer (Vite + 3d-force-graph)
output/             # Generated PNGs and CSVs from scenarios
```

## Data Model
- **chain_definition** — 30 chains (20 science + 10 foundational) across 21 disciplines
- **chain_node** — 216 quanta + 59 alternatives (layer -1). Each has 4 pillar scores (0-100), 8 moral vector dimensions, intrinsic/chain scores
- **evidence_source** — 593 evidence items linked to quanta
- **chain_edge** — 275 DAG edges (depends, supports, contradicts)
- **agent** — simulation agents with stake, reputation, accuracy tracking
- **verification** — agent verdicts (accept/reject/flag) per quanta per round
- **simulation_run** — run config + summary JSON
- **round_snapshot** — per-round consensus scores
- **stake_event** — reward/slash accounting
- **anomaly_flag** — Bayesian anomaly classifications

## Scoring Formulas (in tsim/scoring.py)
- **Intrinsic**: 0.30*correspondence + 0.25*coherence + 0.25*convergence + 0.20*pragmatism
- **Chain**: intrinsic * (0.3 + 0.7 * weakest_dep/100) - contradiction_penalty
- **Lens v1.0**: base * humilityFactor * purityFactor * rigidityFactor * skepticismFactor
  - 5 presets available: scientist, religious, ea, libertarian, blank

## CLI Commands
```
python cli.py init                              # Create DB + schema
python cli.py seed                              # Import chain data from agent-toolkit
python cli.py simulate [options]                # Run simulation
  --rounds N    --batch N     --seed N
  --honest N    --random N    --malicious N    --strategic N
  --reward-rate F   --slash-rate F   --no-anomaly
python cli.py report <run_id>                   # Text summary
python cli.py export <run_id> <file.csv>        # CSV export
python cli.py lens --preset <name>              # Apply worldview lens
python cli.py agents                            # List agents
python cli.py anomalies <run_id>                # Anomaly flags
python cli.py sabotage <node_id> <score>        # Weaken node, show cascade
  --reason TEXT
python cli.py flag-weak <src> <tgt>             # Flag dependency edge
  --reason TEXT  --simulate-invalidate
python cli.py export-graph [--output PATH]      # Export JSON for 3D visualizer
python cli.py import-chain [options]            # Import chain data (incremental upsert)
  --directory DIR   --jsonl FILE   --chain-id ID   --skip-validation
python cli.py validate [options]                # Validate chain data (no import)
  --directory DIR   --jsonl FILE   --chain-id ID
python cli.py reset                             # Drop + recreate DB

python simulate.py [--damping F] [--floor F] [--penalty F]   # DAG propagation
python scenarios/sabotage_test.py [--target ID] [--csv FILE]  # Batch sabotage
```

## Import Workflow (for external AI agents)
1. Create a mission template in `missions/{chain_id}.json` (see existing examples)
2. Agent researches claims and produces:
   - `chains/{chain_id}.json` — dependency graph
   - `chains/{chain_id}.jsonl` — scored quanta (one JSON per line)
3. Validate: `python cli.py validate --directory chains/`
4. Import: `python cli.py import-chain --directory chains/`
5. Re-export for visualizer: `python cli.py export-graph`

Data format follows the agent-toolkit schema (see `../TruthSea/agent-toolkit/SCHEMA.md`).
Import uses upsert — re-importing updated data overwrites existing records.

## Foundational Chains
10 foundational chains forming the epistemological and scientific bedrock:

**Epistemological bedrock (4 chains):**
- **epistemic_foundations** — external world, logic, perception, induction, JTB
- **philosophy_of_science** — empiricism, falsifiability, experiments, peer review, scientific method
- **mathematical_foundations** — Peano axioms, ZFC, proof validity, Goedel incompleteness, mathematical modeling
- **consciousness_foundations** — qualia, neural correlates, psychophysics, hard problem

**First-principles science (5 chains):**
- **physical_reality** — object permanence, spacetime 3+1, causality, uniformity of nature, conservation laws
- **classical_mechanics** — Newton's 3 laws, universal gravitation, Noether conservation, orbital mechanics
- **calculus_foundations** — real numbers, limits, derivatives, integration, fundamental theorem
- **empirical_measurement** — SI units, measurement uncertainty, reproducibility, radiometric dating, historical record
- **logic_and_proof** — propositional logic, predicate logic, proof by contradiction, mathematical induction, completeness

**Chronological spine (1 chain):**
- **deep_time** — Big Bang (13.8 Gyr), solar system (4.567 Gyr), earliest life (3.5 Gyr), Cambrian explosion (541 Myr), K-Pg extinction (66 Myr), human emergence (300 kyr), Neolithic revolution (12 kyr). Cross-links universe_age, earth_age, evolution, mass_extinctions, and empirical_measurement chains.

Axioms (e.g. "external world exists") score naturally: low correspondence (~15, can't empirically prove), high coherence/pragmatism (~85-95). The lens system reveals sensitivity — a scientist lens penalizes axioms more.
Cross-chain dependencies link chains together (e.g. classical_mechanics.force_acceleration depends on calculus_foundations.derivatives and physical_reality.causality).

## Key Design Decisions
- Core: stdlib only (sqlite3, json, csv, argparse, random, math). matplotlib is optional (used for sabotage scenario plots)
- Data seeded from `../TruthSea/agent-toolkit/chains/*.json` (chain metadata + edges) and `../TruthSea/agent-toolkit/output/*.jsonl` (full node data). Falls back to `../truthsea-dashboard/src/data/assembled-chains.json` if those aren't available.
- Agents persist across simulations in the same DB. Use `reset` to start fresh.
- The `convergence` raw data column maps to the `relativism` lens weight (rename was UI-only).
- Windows environment — cli.py has UTF-8 stdout fix for Unicode characters in claims.
- Import uses `ON CONFLICT DO UPDATE` (SQLite upsert) for incremental data updates.
- Cross-chain edges use the target node's chain_id as the edge's chain_id.

## Related Projects
- `../truthsea-dashboard/` — Next.js React dashboard with D3 visualizations (Supabase backend)
- `../TruthSea/` — Original TruthSea repo with Solidity contracts, agent toolkit, JSONL data
