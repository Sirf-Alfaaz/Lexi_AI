"""HTTP API for rule-based forgery detection."""

from __future__ import annotations

from services.forgery import ForgeryCheckRequest, ForgeryCheckResult, run_forgery_checks

from fastapi import APIRouter

router = APIRouter(prefix="/forgery", tags=["Forgery detection"])


@router.post("/check", response_model=ForgeryCheckResult)
def check_forgery(payload: ForgeryCheckRequest) -> ForgeryCheckResult:
    """
    Run ownership, khasra, stamp, date, field, and structure rules.

    Supply optional Bhulekh data and auxiliary lists (`known_stamp_ids`, `other_owners_same_khasra`)
    when available.
    """
    return run_forgery_checks(payload)
