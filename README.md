# truthsea-sim

Local Python + SQLite simulation of the [TruthSea](https://github.com/turfptax/TruthSea) epistemic truth-scoring protocol. No blockchain, no testnet, no gas — just the scoring math, agent dynamics, and DAG propagation, runnable on your laptop.

Use this to:
- Test scoring or lens changes against a corpus before pushing to TruthSea on-chain
- Explore how a single quantum's score propagates through dependent claims
- Run mixed populations of honest, random, malicious, and strategic agents and watch consensus form
- Apply worldview lenses (`scientist`, `religious`, `ea`, `libertarian`, `blank`) to the same DAG and compare results

## Stack
Stdlib-only Python (`sqlite3`, `json`, `csv`, `argparse`, `random`, `math`) — no external dependencies.

## Quick start

```bash
python cli.py reset        # fresh DB
python cli.py seed         # import 20 chains / 151 quanta
python cli.py simulate --rounds 10 --honest 5 --malicious 2
python cli.py report 1     # view results
```

## What's in the box

- **20 chains, 151 quanta, 179 DAG edges** across 14 disciplines, seeded from the TruthSea agent toolkit
- **4 agent types** — honest, random, malicious, strategic — with stake, reputation, and accuracy tracking
- **Stake-weighted consensus** with reward/slash economics
- **Bayesian anomaly classification** (fabrication / genuine / misinterpretation)
- **Worldview lenses** that re-weight the four pillars (correspondence, coherence, convergence, pragmatism)

See [`CLAUDE.md`](./CLAUDE.md) for the full data model, scoring formulas, and CLI reference.

## Related

- [TruthSea](https://github.com/turfptax/TruthSea) — on-chain protocol (Base Sepolia testnet)
- [CrowdedSea](https://github.com/turfptax/CrowdedSea) — bounty marketplace bridge
