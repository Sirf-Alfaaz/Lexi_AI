"""Rule-based forgery detection (ownership, khasra, stamp, dates, fields, structure)."""

from services.forgery.engine import run_forgery_checks
from services.forgery.schemas import (
    BhulekhData,
    ExtractedDocumentData,
    ForgeryCheckRequest,
    ForgeryCheckResult,
)

__all__ = [
    "run_forgery_checks",
    "BhulekhData",
    "ExtractedDocumentData",
    "ForgeryCheckRequest",
    "ForgeryCheckResult",
]
