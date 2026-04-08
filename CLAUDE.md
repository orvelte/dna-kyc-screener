# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this project is

A rule-based KYC (Know Your Customer) screening tool for DNA synthesis providers. Given an order (customer metadata + nucleotide sequence), it runs three parallel screens and aggregates them into a risk decision: approve / flag / reject.

Implements the IGSC Common Mechanism and NSABB 2023 screening recommendations. Not a production compliance system.

## Commands

```bash
pip install -e ".[dev]"         # install with dev deps
pytest tests/                   # run all tests
pytest tests/test_<module>.py   # run a single test file
uvicorn api.main:app --reload   # start API on port 8000
```

## Architecture

Three screening modules run in parallel and feed a risk aggregator. Every decision is audit-logged regardless of outcome.

```
core/sequence_screener.py   # BLAST similarity vs. Select Agent reference list
core/entity_screener.py     # Fuzzy name match vs. OFAC SDN + BIS Entity List
core/legitimacy_rules.py    # Rule table: end-use × customer type plausibility
core/risk_aggregator.py     # Weighted score (0–100) → approve / flag / reject
api/main.py                 # FastAPI app
api/schemas.py              # Pydantic request/response models
api/routes.py               # POST /screen endpoint
audit/logger.py             # Structured decision log (every decision, always)
data/                       # Reference data (JSON/CSV, all public sources)
tests/                      # pytest, synthetic sequences only
frontend/index.html         # Minimal demo form
```

## Module contracts

### sequence_screener.py
- Input: nucleotide string (raw, FASTA, or GenBank accession) + format hint
- Output: `{"match_score": float, "matched_organism": str | None, "percent_identity": float, "flagged": bool}`
- Flag threshold: ≥85% identity over ≥200bp window (IGSC default, configurable)
- Reference DB loaded from `data/select_agents.json` at module init

### entity_screener.py
- Input: `{"name": str, "institution": str, "country": str}`
- Output: `{"match_score": float, "matched_entity": str | None, "list_source": str | None, "flagged": bool}`
- Fuzzy match threshold: 88 (configurable via `ENTITY_THRESHOLD` env var)
- Country-level embargo check runs first as a hard block before fuzzy matching

### legitimacy_rules.py
- Input: `{"end_use": str, "customer_type": str, "quantity_bp": int, "address_type": str, "institution_verified": bool}`
- Output: `{"rule_score": float, "rules_triggered": list[str]}`
- Rules loaded from `data/legitimacy_matrix.json` — edit that file, not the Python

### risk_aggregator.py
- Input: outputs from all three modules above
- Output: `{"risk_score": int, "decision": "approve"|"flag"|"reject", "module_scores": dict}`
- Default weights: sequence 50%, entity 30%, legitimacy 20%
- Score bands: 0–39 approve, 40–69 flag, 70–100 reject

## Data files

- `data/select_agents.json` — CDC/USDA Select Agent list with GenBank accessions (public)
- `data/watchlist_sample.csv` — **synthetic** watchlist for demo/testing only
- `data/legitimacy_matrix.json` — operator config for rule weights; never modify from Python

## Key dependencies

- `biopython` — BLAST wrapper and sequence parsing
- `rapidfuzz` — fuzzy name matching
- `fastapi` + `pydantic` — API layer
- `httpx` — Entrez API calls (GenBank accession fetching)

## Coding conventions

- Type hints on all function signatures
- Docstrings on all public functions (one-line summary + Args/Returns)
- Config values (thresholds, weights, file paths) via environment variables or `config.py` — never hardcoded in module logic
- No print statements — use Python `logging` module

## Testing rules

- Synthetic sequences only in test fixtures — never commit real Select Agent sequence data
- Synthetic test sequences must be clearly labelled as such in the fixture file
- Each module needs at least one true positive, one true negative, one edge case
- Test files: `tests/test_{module_name}.py`

## Hard constraints

- Do not commit real pathogen sequences or real PII
- Do not hardcode OFAC/BIS list data — load from file or public API
- Do not skip the audit log — every decision must be written, including approved ones
- Do not add dependencies without updating `pyproject.toml`
