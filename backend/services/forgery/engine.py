"""
Orchestrates rule-based forgery checks and aggregates risk score + narrative.
"""

from __future__ import annotations

from typing import List, Set

from services.forgery.rules import (
    check_date_anomalies,
    check_document_structure,
    check_duplicate_khasra_multi_owner,
    check_missing_required_fields,
    check_ownership_mismatch,
    check_stamp_fraud,
    check_khasra_mismatch,
    check_area_mismatch,
    check_not_official_owner,
)
from services.forgery.schemas import ForgeryCheckRequest, ForgeryCheckResult


def run_forgery_checks(req: ForgeryCheckRequest) -> ForgeryCheckResult:
    """
    Run all rules, dedupe flags, combine severities into risk_score in [0, 1],
    and build a human-readable explanation.
    """
    doc = req.document
    bhulekh = req.bhulekh

    segments: List[str] = []
    flags_set: Set[str] = set()
    total_weight = 0.0

    checks = [
        check_ownership_mismatch(doc, bhulekh),
        check_duplicate_khasra_multi_owner(doc, req),
        check_stamp_fraud(doc, req.known_stamp_ids),
        check_date_anomalies(doc, bhulekh),
        check_missing_required_fields(doc),
        check_document_structure(doc),
        # Bhulekh cross-validation checks (fire only when bhulekh data is provided)
        check_khasra_mismatch(doc, bhulekh),
        check_area_mismatch(doc, bhulekh),
        check_not_official_owner(doc, bhulekh),
    ]

    for triggered, flag, detail, weight in checks:
        if not triggered or not flag:
            continue
        flags_set.add(flag)
        total_weight += weight
        segments.append(f"• {flag}: {detail}")

    # Deduplicate stamp vs ownership if same root cause — keep both flags if both fired

    risk_score = min(1.0, total_weight)
    if not flags_set:
        explanation = (
            "No rule-based risk signals were triggered for the provided data. "
            "This does not guarantee authenticity; corroborate with official Bhulekh and physical verification."
        )
    else:
        header = (
            f"Automated assessment found {len(flags_set)} issue type(s) with a combined risk score of {risk_score:.2f} "
            "(0 = low, 1 = high). Details:\n\n"
        )
        explanation = header + "\n".join(segments)
        explanation += (
            "\n\nThese checks are heuristic. Use them alongside manual review and official records."
        )

    return ForgeryCheckResult(
        flags=sorted(flags_set),
        risk_score=round(risk_score, 4),
        explanation=explanation,
    )
