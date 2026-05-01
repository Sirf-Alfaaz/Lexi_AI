"""Input/output models for rule-based forgery detection."""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field


class ExtractedDocumentData(BaseModel):
    """Fields typically produced by OCR / extraction pipeline."""

    owner: str = ""
    father: str = ""
    khasra: str = ""
    area: str = ""
    date: str = ""
    stamp_id: str = ""
    raw_text: Optional[str] = Field(None, description="Optional full OCR text for structure checks")


class BhulekhData(BaseModel):
    """Optional official Bhulekh / revenue-record snapshot for cross-checks."""

    owner_name: str = ""
    khasra: str = ""
    area: str = ""
    district: str = ""
    village: str = ""
    # Optional reference dates from portal (ISO or DD/MM/YYYY)
    mutation_date: Optional[str] = None
    last_updated: Optional[str] = None


class ForgeryCheckRequest(BaseModel):
    """Inputs for the rule engine."""

    document: ExtractedDocumentData
    bhulekh: Optional[BhulekhData] = None
    # Stamp IDs already seen on other documents (same session / database slice)
    known_stamp_ids: List[str] = Field(default_factory=list)
    # Other claimant names associated with the same khasra (e.g. from another filing)
    other_owners_same_khasra: List[str] = Field(default_factory=list)


class ForgeryCheckResult(BaseModel):
    """Rule-based forgery assessment."""

    flags: List[str] = Field(default_factory=list, description="Human-readable issue labels")
    risk_score: float = Field(0.0, ge=0.0, le=1.0, description="Aggregated risk in [0, 1]")
    explanation: str = Field("", description="Human-readable summary of findings")
