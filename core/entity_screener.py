"""Entity screening against sanctions watchlists and country embargo list.

Screening order:
  1. Country embargo check (hard block — no fuzzy matching attempted).
  2. Fuzzy name match of customer name and institution against the watchlist.

The watchlist and embargo list are loaded once at module import.
"""

import csv
import json
import logging
from pathlib import Path

from rapidfuzz import fuzz, process

import config
from api.schemas import EntityResult

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Module-level reference data (loaded once at import)
# ---------------------------------------------------------------------------


def _load_embargoed_countries(path: str) -> frozenset[str]:
    """Load the set of embargoed ISO alpha-2 country codes from JSON.

    Args:
        path: Path to embargoed_countries.json.

    Returns:
        Frozenset of uppercase country codes.
    """
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return frozenset(c.upper() for c in data["embargoed"])


def _load_watchlist(path: str) -> list[dict[str, str]]:
    """Load the sanctions watchlist from CSV.

    Skips comment lines (starting with #) and blank rows.

    Args:
        path: Path to watchlist CSV with columns: name, list_source, country.

    Returns:
        List of dicts with keys 'name', 'list_source', 'country'.
    """
    records: list[dict[str, str]] = []
    with Path(path).open(encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(row for row in fh if not row.startswith("#"))
        for row in reader:
            name = row.get("name", "").strip()
            if name:
                records.append(
                    {
                        "name": name,
                        "list_source": row.get("list_source", "").strip(),
                        "country": row.get("country", "").strip().upper(),
                    }
                )
    logger.info("Loaded %d watchlist entries from %s", len(records), path)
    return records


_EMBARGOED_COUNTRIES: frozenset[str] = _load_embargoed_countries(
    config.EMBARGOED_COUNTRIES_PATH
)
_WATCHLIST: list[dict[str, str]] = _load_watchlist(config.WATCHLIST_PATH)
# Lowercased names used for matching; originals preserved in _WATCHLIST for output.
_WATCHLIST_NAMES: list[str] = [e["name"].lower() for e in _WATCHLIST]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _fuzzy_match(
    query: str, threshold: float
) -> tuple[float, str | None, str | None]:
    """Run fuzzy match of query against the watchlist name list.

    Args:
        query: Name string to match.
        threshold: Minimum rapidfuzz score (0–100) to consider a hit.

    Returns:
        Tuple of (match_score_0_to_1, matched_name, list_source) where
        matched_name and list_source are None if no match exceeds threshold.
    """
    if not query.strip():
        return 0.0, None, None

    result = process.extractOne(
        query.lower(),
        _WATCHLIST_NAMES,
        scorer=fuzz.WRatio,
        score_cutoff=threshold,
    )

    if result is None:
        return 0.0, None, None

    matched_name, score, index = result
    entry = _WATCHLIST[index]
    return round(score / 100.0, 4), matched_name, entry["list_source"]


# ---------------------------------------------------------------------------
# Public interface
# ---------------------------------------------------------------------------


def screen_entity(
    name: str,
    institution: str | None,
    country: str,
    *,
    threshold: float = config.ENTITY_THRESHOLD,
) -> EntityResult:
    """Screen a customer against the sanctions watchlist and embargo list.

    Country embargo check runs first and is a hard block — if the country is
    embargoed the call returns immediately with flagged=True and no fuzzy
    matching is attempted.

    If not embargoed, fuzzy matching is run on both `name` and `institution`
    (when provided) and the higher-scoring match is returned.

    Args:
        name: Customer full name.
        institution: Customer institution name, or None for individuals.
        country: ISO 3166-1 alpha-2 country code (case-insensitive).
        threshold: Minimum rapidfuzz score (0–100) to flag a match.
                   Defaults to ENTITY_THRESHOLD from config.

    Returns:
        EntityResult with match_score, matched_entity, list_source, flagged.
    """
    country_upper = country.upper()

    # Step 1 — hard embargo block
    if country_upper in _EMBARGOED_COUNTRIES:
        logger.info("Entity screen: country embargo hit for country=%s", country_upper)
        return EntityResult(
            match_score=1.0,
            matched_entity=None,
            list_source="EMBARGO",
            flagged=True,
        )

    # Step 2 — fuzzy match on name
    name_score, name_match, name_source = _fuzzy_match(name, threshold)

    # Step 3 — fuzzy match on institution (if provided), take best
    inst_score, inst_match, inst_source = 0.0, None, None
    if institution:
        inst_score, inst_match, inst_source = _fuzzy_match(institution, threshold)

    if name_score >= inst_score:
        best_score, best_match, best_source = name_score, name_match, name_source
    else:
        best_score, best_match, best_source = inst_score, inst_match, inst_source

    flagged = best_match is not None

    logger.debug(
        "Entity screen: name=%r country=%s score=%.4f matched=%r flagged=%s",
        name,
        country_upper,
        best_score,
        best_match,
        flagged,
    )

    return EntityResult(
        match_score=best_score,
        matched_entity=best_match,
        list_source=best_source,
        flagged=flagged,
    )
