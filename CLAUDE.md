# TruthSea Local Simulation Environment

## What This Is
A Python + SQLite simulation environment for the TruthSea epistemic truth-scoring protocol. It mirrors the blockchain-based TruthSea system but runs entirely locally without any crypto/blockchain dependencies. You can run agent-based verification simulations, apply worldview lenses, and analyze results.

## Quick Start
```bash
cd truthsea-sim
python cli.py reset          # Fresh database
python cli.py seed           # Import 20 chains / 151 quanta from JSONL
python cli.py simulate --rounds 10 --honest 5 --malicious 2
python cli.py report 1       # View results
```

## Project Structure
```
cli.py              # CLI entry point (argparse) — start here for usage
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
```

## Data Model
- **chain_definition** — 20 chains across 14 disciplines
- **chain_node** — 151 quanta + 39 alternatives (layer -1). Each has 4 pillar scores (0-100), 8 moral vector dimensions, intrinsic/chain scores
- **evidence_source** — 475 evidence items linked to quanta
- **chain_edge** — 179 DAG edges (depends, supports, contradicts)
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
python cli.py seed                              # Import chain data
python cli.py simulate [options]                # Run simulation
  --rounds N    --batch N     --seed N
  --honest N    --random N    --malicious N    --strategic N
  --reward-rate F   --slash-rate F   --no-anomaly
python cli.py report <run_id>                   # Text summary
python cli.py export <run_id> <file.csv>        # CSV export
python cli.py lens --preset <name>              # Apply worldview lens
python cli.py agents                            # List agents
python cli.py anomalies <run_id>                # Anomaly flags
python cli.py reset                             # Drop + recreate DB
```

## Key Design Decisions
- No external dependencies — stdlib only (sqlite3, json, csv, argparse, random, math)
- Data seeded from `../TruthSea/agent-toolkit/chains/*.json` (chain metadata + edges) and `../TruthSea/agent-toolkit/output/*.jsonl` (full node data). Falls back to `../truthsea-dashboard/src/data/assembled-chains.json` if those aren't available.
- Agents persist across simulations in the same DB. Use `reset` to start fresh.
- The `convergence` raw data column maps to the `relativism` lens weight (rename was UI-only).
- Windows environment — cli.py has UTF-8 stdout fix for Unicode characters in claims.

## Related Projects
- `../truthsea-dashboard/` — Next.js React dashboard with D3 visualizations (Supabase backend)
- `../TruthSea/` — Original TruthSea repo with Solidity contracts, agent toolkit, JSONL data
