"""Legitimacy screening via a configurable rule table.

Rules are loaded from data/legitimacy_matrix.json at module import.
Each rule defines a set of conditions (AND logic) and a score contribution.
Triggered rule scores are summed and capped at 1.0.

To add, remove, or retune rules, edit the JSON — do not modify this file.
"""

import json
import logging
import operator
from pathlib import Path
from typing import Any

import config
from api.schemas import LegitimacyResult

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Condition evaluation
# ---------------------------------------------------------------------------

_OPS: dict[str, Any] = {
    "eq": operator.eq,
    "neq": operator.ne,
    "gt": operator.gt,
    "gte": operator.ge,
    "lt": operator.lt,
    "lte": operator.le,
    "in": lambda a, b: a in b,
    "not_in": lambda a, b: a not in b,
}


def _evaluate_condition(condition: dict[str, Any], input_values: dict[str, Any]) -> bool:
    """Evaluate a single condition dict against the screener input.

    Args:
        condition: Dict with keys 'field', 'op', 'value'.
        input_values: Flat dict of screener input fields.

    Returns:
        True if the condition is satisfied.

    Raises:
        KeyError: If the condition references an unknown field.
        ValueError: If the condition uses an unsupported operator.
    """
    field = condition["field"]
    op_name = condition["op"]
    expected = condition["value"]

    if field not in input_values:
        raise KeyError(f"Condition references unknown field: {field!r}")
    if op_name not in _OPS:
        raise ValueError(f"Unsupported operator: {op_name!r}")

    actual = input_values[field]
    return _OPS[op_name](actual, expected)


def _evaluate_rule(rule: dict[str, Any], input_values: dict[str, Any]) -> bool:
    """Return True if all conditions in a rule are satisfied (AND logic).

    Args:
        rule: Rule dict with a 'conditions' list.
        input_values: Flat dict of screener input fields.

    Returns:
        True if every condition in the rule matches.
    """
    return all(_evaluate_condition(c, input_values) for c in rule["conditions"])


# ---------------------------------------------------------------------------
# Module-level reference data (loaded once at import)
# ---------------------------------------------------------------------------


def _load_matrix(path: str) -> list[dict[str, Any]]:
    """Load and validate the legitimacy rule matrix from JSON.

    Args:
        path: Path to legitimacy_matrix.json.

    Returns:
        List of rule dicts, each with 'name', 'score', and 'conditions'.

    Raises:
        ValueError: If any rule is missing required keys.
    """
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    rules = data["rules"]
    required = {"name", "score", "conditions"}
    for rule in rules:
        missing = required - rule.keys()
        if missing:
            raise ValueError(f"Rule {rule.get('name', '?')!r} missing keys: {missing}")
    logger.info("Loaded %d legitimacy rules from %s", len(rules), path)
    return rules


_RULES: list[dict[str, Any]] = _load_matrix(config.LEGITIMACY_MATRIX_PATH)


# ---------------------------------------------------------------------------
# Public interface
# ---------------------------------------------------------------------------


def screen_legitimacy(
    end_use: str,
    customer_type: str,
    quantity_bp: int,
    address_type: str,
    institution_verified: bool,
) -> LegitimacyResult:
    """Evaluate the legitimacy of an order against the rule matrix.

    Each rule whose conditions all match contributes its score. The final
    rule_score is the sum of triggered scores, capped at 1.0. The module
    is flagged if any rule is triggered.

    Args:
        end_use: Declared end use for the synthesised sequence.
        customer_type: Category of the ordering customer.
        quantity_bp: Number of base pairs in the order.
        address_type: Type of delivery/billing address on record.
        institution_verified: Whether the customer's institution was verified.

    Returns:
        LegitimacyResult with rule_score, rules_triggered, and flagged.
    """
    input_values: dict[str, Any] = {
        "end_use": end_use,
        "customer_type": customer_type,
        "quantity_bp": quantity_bp,
        "address_type": address_type,
        "institution_verified": institution_verified,
    }

    triggered_names: list[str] = []
    total_score: float = 0.0

    for rule in _RULES:
        try:
            matched = _evaluate_rule(rule, input_values)
        except (KeyError, ValueError) as exc:
            logger.warning("Skipping malformed rule %r: %s", rule.get("name"), exc)
            continue

        if matched:
            triggered_names.append(rule["name"])
            total_score += rule["score"]
            logger.debug("Legitimacy rule triggered: %s (score +%.2f)", rule["name"], rule["score"])

    rule_score = round(min(1.0, total_score), 4)
    flagged = len(triggered_names) > 0

    logger.debug(
        "Legitimacy screen: rule_score=%.4f flagged=%s triggered=%s",
        rule_score,
        flagged,
        triggered_names,
    )

    return LegitimacyResult(
        rule_score=rule_score,
        rules_triggered=triggered_names,
        flagged=flagged,
    )
