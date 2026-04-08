"""Central configuration loaded from environment variables with defaults.

All thresholds, weights, and file paths live here.
Module logic must never hardcode these values.

File path defaults are resolved relative to this file's directory at runtime,
so the process can be started from any working directory.
"""

import os
from pathlib import Path

_BASE = Path(__file__).parent


def _path(env_var: str, relative_default: str) -> str:
    """Return an absolute path from an env var or a default relative to _BASE."""
    value = os.environ.get(env_var)
    if value:
        return str(Path(value).resolve())
    return str(_BASE / relative_default)

# ---------------------------------------------------------------------------
# Sequence screener
# ---------------------------------------------------------------------------

SEQUENCE_IDENTITY_THRESHOLD: float = float(
    os.environ.get("SEQUENCE_IDENTITY_THRESHOLD", "85.0")
)
SEQUENCE_MIN_ALIGN_BP: int = int(os.environ.get("SEQUENCE_MIN_ALIGN_BP", "200"))
SELECT_AGENTS_PATH: str = _path("SELECT_AGENTS_PATH", "data/select_agents.json")

# ---------------------------------------------------------------------------
# Entity screener
# ---------------------------------------------------------------------------

ENTITY_THRESHOLD: float = float(os.environ.get("ENTITY_THRESHOLD", "88.0"))
WATCHLIST_PATH: str = _path("WATCHLIST_PATH", "data/watchlist_sample.csv")
EMBARGOED_COUNTRIES_PATH: str = _path("EMBARGOED_COUNTRIES_PATH", "data/embargoed_countries.json")

# ---------------------------------------------------------------------------
# Legitimacy rules
# ---------------------------------------------------------------------------

LEGITIMACY_MATRIX_PATH: str = _path("LEGITIMACY_MATRIX_PATH", "data/legitimacy_matrix.json")

# ---------------------------------------------------------------------------
# Risk aggregator weights (must sum to 1.0)
# ---------------------------------------------------------------------------

WEIGHT_SEQUENCE: float = float(os.environ.get("WEIGHT_SEQUENCE", "0.50"))
WEIGHT_ENTITY: float = float(os.environ.get("WEIGHT_ENTITY", "0.30"))
WEIGHT_LEGITIMACY: float = float(os.environ.get("WEIGHT_LEGITIMACY", "0.20"))

# Score band thresholds (risk_score is 0–100)
APPROVE_THRESHOLD: int = int(os.environ.get("APPROVE_THRESHOLD", "40"))
REJECT_THRESHOLD: int = int(os.environ.get("REJECT_THRESHOLD", "70"))

# ---------------------------------------------------------------------------
# Audit
# ---------------------------------------------------------------------------

AUDIT_LOG_PATH: str = _path("AUDIT_LOG_PATH", "audit/decisions.jsonl")
