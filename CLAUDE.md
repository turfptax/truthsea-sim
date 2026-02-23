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
missions/           # Mission templates for external AI agents
visualizer/         # 3D interactive graph visualizer (Vite + 3d-force-graph)
output/             # Generated PNGs and CSVs from scenarios
```

## Data Model
- **chain_definition** — 24 chains (20 science + 4 coherence theory) across 18 disciplines
- **chain_node** — 176 quanta + 50 alternatives (layer -1). Each has 4 pillar scores (0-100), 8 moral vector dimensions, intrinsic/chain scores
- **evidence_source** — 525 evidence items linked to quanta
- **chain_edge** — 212 DAG edges (depends, supports, contradicts)
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

## Coherence Theory Chains
4 foundational chains forming the epistemological bedrock:
- **epistemic_foundations** — external world, logic, perception, induction, JTB
- **philosophy_of_science** — empiricism, falsifiability, experiments, peer review, scientific method
- **mathematical_foundations** — Peano axioms, ZFC, proof validity, Goedel incompleteness, mathematical modeling
- **consciousness_foundations** — qualia, neural correlates, psychophysics, hard problem

Axioms (e.g. "external world exists") score naturally: low correspondence (~15, can't empirically prove), high coherence/pragmatism (~85-95). The lens system reveals sensitivity — a scientist lens penalizes axioms more.
Cross-chain dependencies link these to each other (e.g. philosophy_of_science.empiricism depends on epistemic_foundations.perception_reliability).

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
