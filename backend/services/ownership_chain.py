"""
Validate a sequential ownership / sale chain from registry-style transactions.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict, List, Tuple


def _norm_name(s: str) -> str:
    return " ".join(s.split()).casefold().strip()


def analyze_ownership_chain(transactions: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Input: list of ``{"seller": str, "buyer": str, "year": int}``.

    - Validates that each transaction's buyer matches the next seller (ordered by year).
    - Detects the same seller disposing to multiple distinct buyers in the same year.

    Returns ``{"valid_chain": bool, "issues": [...]}``.
    """
    issues: List[str] = []

    if not transactions:
        return {"valid_chain": False, "issues": ["empty_transaction_list"]}

    normalized: List[Tuple[str, str, int]] = []
    for i, tx in enumerate(transactions):
        try:
            seller = str(tx.get("seller", "")).strip()
            buyer = str(tx.get("buyer", "")).strip()
            year = int(tx.get("year", 0))
        except (TypeError, ValueError):
            issues.append(f"invalid_transaction_index_{i}")
            continue
        if not seller or not buyer:
            issues.append(f"missing_seller_or_buyer_index_{i}")
            continue
        if year <= 0:
            issues.append(f"invalid_year_index_{i}")
            continue
        normalized.append((seller, buyer, year))

    if not normalized:
        return {"valid_chain": False, "issues": issues or ["no_valid_transactions"]}

    normalized.sort(key=lambda x: (x[2], x[0]))

    for i in range(len(normalized) - 1):
        _, buyer, y1 = normalized[i]
        next_seller, _, y2 = normalized[i + 1]
        if _norm_name(buyer) != _norm_name(next_seller):
            issues.append(
                "broken_chain: "
                f"after {y1} buyer '{buyer}' does not match {y2} seller '{next_seller}'"
            )

    seller_year_buyers: Dict[Tuple[str, int], List[str]] = defaultdict(list)
    for seller, buyer, year in normalized:
        seller_year_buyers[(_norm_name(seller), year)].append(_norm_name(buyer))

    for (seller_key, year), buyers in seller_year_buyers.items():
        distinct = {b for b in buyers if b}
        if len(distinct) > 1:
            issues.append(
                "same_seller_multiple_buyers: "
                f"seller year {year} sold to {', '.join(sorted(distinct))}"
            )

    valid = not issues
    return {"valid_chain": valid, "issues": issues}
