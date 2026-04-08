# dna-kyc-screener

A demonstration tool implementing Know Your Customer (KYC) screening rules for DNA synthesis providers, based on publicly available biosecurity frameworks. Built for educational and research purposes — not a production compliance system.

Inspired by KYC policy for averting AI misuse mentioned in The Intelligence Curse essay series (https://intelligence-curse.ai/breaking/)

---

## Background

The rapid commoditisation of DNA synthesis has created a meaningful biosecurity surface: short oligonucleotides and gene fragments that would once have required specialist infrastructure can now be ordered online, often with minimal friction. In response, several frameworks have emerged to formalise screening obligations for synthesis providers:

- **IGSC Common Mechanism** (International Gene Synthesis Consortium) — voluntary but widely adopted industry standard requiring sequence and customer screening before fulfilment
- **NTI Biosecurity Innovation and Risk Reduction Initiative** — policy framework recommending mandatory KYC requirements for all synthesis providers above a certain throughput threshold
- **EO 14110 §4.4** (Biden, Oct 2023) — directed OSTP and relevant agencies to develop a framework for oversight of nucleic acid synthesis providers, including sequence screening requirements
- **NSABB 2023 recommendations** — advised a two-part screen: sequence similarity to pathogens of concern, plus customer/end-use plausibility assessment

This tool demonstrates what a rule-based implementation of those recommendations looks like in practice.

---

## What it does

Given an order — a DNA/RNA sequence plus customer metadata — the tool runs three parallel screens and aggregates their outputs into a risk decision:

```
Order (sequence + customer)
        │
        ├─── Sequence screen   → similarity to Select Agents / pathogens of concern
        ├─── Entity screen     → customer / institution against sanctions watchlists
        └─── Legitimacy check  → end-use plausibility given customer type
                │
        Risk aggregation (weighted scoring)
                │
        ┌───────┼───────┐
     Approve  Flag   Reject
                │
        Audit log (all decisions)
```

Every decision is written to a structured audit log with a timestamp, input hash, per-module scores, triggered rules, and the final determination. This is not cosmetic — regulators and auditors care about the decision trail, not just the outcome.

---

## Repository structure

```
dna-kyc-screener/
├── core/
│   ├── sequence_screener.py     # BLAST-based similarity vs. pathogen reference list
│   ├── entity_screener.py       # Fuzzy name matching vs. OFAC SDN, BIS Entity List
│   ├── legitimacy_rules.py      # Rule table: end-use × customer type plausibility
│   └── risk_aggregator.py       # Weighted score → decision (approve / flag / reject)
├── api/
│   ├── main.py                  # FastAPI app
│   ├── schemas.py               # Pydantic request/response models
│   └── routes.py                # /screen endpoint
├── data/
│   ├── select_agents.json       # CDC/USDA Select Agent list (public)
│   ├── watchlist_sample.csv     # Synthetic watchlist for demo purposes
│   └── legitimacy_matrix.json   # End-use × customer type scoring rules
├── audit/
│   └── logger.py                # Structured decision logging
├── frontend/
│   └── index.html               # Minimal demo form
├── tests/
│   ├── test_sequence_screener.py
│   ├── test_entity_screener.py
│   ├── test_risk_aggregator.py
│   └── fixtures/                # Synthetic test sequences (labelled)
├── pyproject.toml
└── README.md
```

---

## Screening modules

### 1. Sequence screening (`core/sequence_screener.py`)

Runs pairwise alignment between the submitted sequence and a curated reference database of pathogen sequences (Select Agents, USDA PPQ list, and a subset of CDC Category A/B/C agents). Uses Biopython's BLAST wrapper for local alignment, returning a match score, matched organism, and percent identity.

Thresholds are configurable. The IGSC Common Mechanism recommends flagging at ≥85% identity over a window of ≥200bp — this tool uses that as its default but exposes it as a parameter.

**Reference sources used:**
- CDC Select Agent Program list (public)
- USDA Agricultural Select Agents and Toxins (public)
- GenBank sequences for organisms on the above lists (public accession numbers)

### 2. Entity screening (`core/entity_screener.py`)

Checks the submitting customer (name, institution, country) against:
- OFAC Specially Designated Nationals (SDN) list
- BIS Entity List (US Department of Commerce)
- UN Security Council Consolidated Sanctions List

Uses `rapidfuzz` for fuzzy name matching (configurable threshold, default 88) to handle transliteration variants and name reordering. Country-level flags (embargoed jurisdictions) are applied as a hard rule before fuzzy matching.

### 3. Legitimacy rules (`core/legitimacy_rules.py`)

A weighted rule table assessing whether the stated end-use is plausible given the customer type, order quantity, sequence type, and institution verification status. Example rules:

| Signal | Weight | Direction |
|---|---|---|
| Customer is verified academic / government lab | 0.15 | ↓ risk |
| End-use is "personal" or unspecified | 0.20 | ↑ risk |
| Order quantity inconsistent with stated application | 0.15 | ↑ risk |
| Sequence matches known vaccine or therapeutic target | 0.10 | ↓ risk |
| Shipping address is residential | 0.12 | ↑ risk |

The rule table lives in `data/legitimacy_matrix.json` and is designed to be extended without touching Python.

### 4. Risk aggregation (`core/risk_aggregator.py`)

Combines the three module outputs into a single risk score (0–100) using configurable weights (default: sequence 50%, entity 30%, legitimacy 20%). Score bands:

| Score | Decision |
|---|---|
| 0–39 | Approve |
| 40–69 | Flag for human review |
| 70–100 | Reject |

---

## API

```bash
uvicorn api.main:app --reload
```

**POST `/screen`**

```json
{
  "customer": {
    "name": "Jane Smith",
    "institution": "University of Edinburgh",
    "country": "GB",
    "end_use": "vaccine research"
  },
  "sequence": "ATGGCTAGCTAGCTAGC...",
  "format": "raw"
}
```

**Response**

```json
{
  "decision": "approve",
  "risk_score": 18,
  "module_scores": {
    "sequence": 5,
    "entity": 2,
    "legitimacy": 11
  },
  "rules_triggered": [],
  "audit_id": "a3f9c2e1-...",
  "timestamp": "2025-09-14T11:42:00Z"
}
```

Accepts FASTA, GenBank accession strings (fetched via Entrez), or raw nucleotide strings.

---

## Installation

```bash
git clone https://github.com/yourhandle/dna-kyc-screener
cd dna-kyc-screener
pip install -e ".[dev]"

# Run tests
pytest tests/

# Start API
uvicorn api.main:app --reload
```

Dependencies: `biopython`, `rapidfuzz`, `fastapi`, `pydantic`, `httpx` (for Entrez), `pytest`.

---

## Limitations and responsible use

This is a **demonstration system**, not a validated compliance tool. Specific limitations:

**Scientific:** The sequence screening approach (BLAST similarity) is a necessary but not sufficient screen. A determined actor could engineer around similarity thresholds using codon reassignment or split-gene strategies. More sophisticated approaches (e.g. functional annotation, protein structure prediction) are active research areas not implemented here.

**Coverage:** The reference pathogen list is derived from public regulatory sources. It does not cover all sequences of concern — notably, novel pandemic-potential pathogens and engineered variants not yet characterised in public databases would not be flagged.

**Entity data:** The watchlist data used here is either synthetic (for demo) or derived from public sources. A production system would integrate with live, regularly updated government feeds.

**No legal weight:** Decisions from this tool carry no regulatory validity. Real synthesis providers should work with qualified biosecurity counsel and implement systems that meet the specific requirements of the jurisdictions they operate in.

The tool is intended to illustrate the structure of a KYC framework — what signals matter, how they combine, and what a decision audit trail looks like — rather than to serve as a drop-in compliance solution.

---

## Policy references

- [IGSC Harmonised Screening Protocol](https://www.genesynthesisconsortium.org/)
- [NTI Biosecurity Innovation and Risk Reduction Initiative](https://www.nti.org/analysis/articles/strengthening-biosecurity-in-dna-synthesis/)
- [CDC Select Agent Program](https://www.selectagents.gov/)
- [EO 14110 on Safe, Secure, and Trustworthy AI — §4.4 Biosecurity](https://www.whitehouse.gov/briefing-room/presidential-actions/2023/10/30/executive-order-on-the-safe-secure-and-trustworthy-development-and-use-of-artificial-intelligence/)
- [NSABB 2023 Recommendations on Oversight of Dual-Use Research](https://www.hhs.gov/nsabb)

---

## Author

Olivia — MSc AI for Biosciences / BA Neuroscience. Interests: AI safety evaluation, biosecurity, neuroAI.

---

## License

MIT. The screening logic and rule weights are illustrative defaults — treat them as a starting point, not a specification.
