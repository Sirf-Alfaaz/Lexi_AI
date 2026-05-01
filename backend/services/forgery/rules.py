"""
Individual rule checks. Each returns (triggered, flag_label, detail, severity_weight).
Severity weights are summed and capped in the engine.
"""

from __future__ import annotations

import re
from datetime import date
from typing import List, Optional, Tuple

from services.forgery.date_utils import compare_dates_doc_vs_bhulekh, parse_flexible_date
from services.forgery.schemas import BhulekhData, ExtractedDocumentData, ForgeryCheckRequest

RuleHit = Tuple[bool, str, str, float]

# Normalized flag labels (stable for API)
FLAG_OWNERSHIP_MISMATCH = "Ownership Mismatch"
FLAG_DUPLICATE_KHASRA = "Duplicate Khasra With Multiple Owners"
FLAG_STAMP_FRAUD = "Stamp Fraud"
FLAG_DATE_ANOMALY = "Date Anomaly"
FLAG_MISSING_FIELDS = "Missing Required Fields"
FLAG_DOCUMENT_STRUCTURE = "Invalid Document Structure"
FLAG_KHASRA_MISMATCH = "Khasra Mismatch With Official Record"
FLAG_AREA_MISMATCH = "Area Mismatch With Official Record"
FLAG_NOT_OFFICIAL_OWNER = "Document Owner Not In Official Record"


def _norm_name(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip().lower())


def _normalize_khasra(s: str) -> str:
    return re.sub(r"\s*[/\\\-]\s*", "/", (s or "").strip().lower())


def check_ownership_mismatch(doc: ExtractedDocumentData, bhulekh: Optional[BhulekhData]) -> RuleHit:
    if not bhulekh or not bhulekh.owner_name.strip():
        return False, "", "", 0.0
    if not doc.owner.strip():
        return False, "", "", 0.0

    a = _norm_name(doc.owner)
    b = _norm_name(bhulekh.owner_name)
    if not a or not b:
        return False, "", "", 0.0

    # Token overlap / substring heuristic for OCR noise
    if a == b:
        return False, "", "", 0.0
    if a in b or b in a:
        return False, "", "", 0.0
    # First + last token match
    ta, tb = a.split(), b.split()
    if len(ta) >= 2 and len(tb) >= 2 and ta[0] == tb[0] and ta[-1] == tb[-1]:
        return False, "", "", 0.0

    detail = (
        f"Document owner ({doc.owner.strip()}) does not align with Bhulekh owner "
        f"({bhulekh.owner_name.strip()})."
    )
    return True, FLAG_OWNERSHIP_MISMATCH, detail, 0.28


def check_duplicate_khasra_multi_owner(doc: ExtractedDocumentData, req: ForgeryCheckRequest) -> RuleHit:
    if not doc.khasra.strip():
        return False, "", "", 0.0

    doc_owner = _norm_name(doc.owner)
    k_norm = _normalize_khasra(doc.khasra)

    # Use explicit list of other claimants for this khasra (e.g. from another case or survey)
    others: List[str] = []
    for name in req.other_owners_same_khasra:
        n = _norm_name(name)
        if n and n != doc_owner:
            others.append(name.strip())

    if not others:
        return False, "", "", 0.0

    detail = (
        f"Khasra {_normalize_khasra(doc.khasra)} is associated with multiple distinct owners "
        f"({', '.join(others[:5])}), which raises duplicate-allocation concerns."
    )
    return True, FLAG_DUPLICATE_KHASRA, detail, 0.22


# Stamp: allow typical Indian revenue / judicial patterns
_STAMP_OK = re.compile(r"^[A-Za-z0-9][A-Za-z0-9/\-]{2,30}[A-Za-z0-9]$|^[A-Za-z0-9]{4,24}$")


def check_stamp_fraud(doc: ExtractedDocumentData, known_stamp_ids: List[str]) -> RuleHit:
    sid = (doc.stamp_id or "").strip()
    if not sid:
        return False, "", "", 0.0

    reasons: List[str] = []
    if not _STAMP_OK.match(sid):
        reasons.append("Stamp identifier does not match the expected alphanumeric format.")

    norm_known = {_normalize_stamp(x) for x in known_stamp_ids if x.strip()}
    if _normalize_stamp(sid) in norm_known:
        reasons.append("This stamp ID matches another document already on file (possible duplicate stamp paper).")

    if not reasons:
        return False, "", "", 0.0

    return True, FLAG_STAMP_FRAUD, " ".join(reasons), 0.24


def _normalize_stamp(s: str) -> str:
    return re.sub(r"\s+", "", s.lower())


def check_date_anomalies(doc: ExtractedDocumentData, bhulekh: Optional[BhulekhData]) -> RuleHit:
    details: List[str] = []
    today = date.today()

    d = parse_flexible_date(doc.date) if doc.date else None
    if doc.date.strip() and d is None:
        details.append("Registry date could not be parsed; format may be invalid or OCR-noisy.")
    elif d is not None:
        if d > today:
            details.append(f"Registry date {d.isoformat()} is in the future relative to today.")
        if d.year < 1950:
            details.append(f"Registry year {d.year} is unusually early for typical digital records (verify authenticity).")

    if bhulekh:
        md = parse_flexible_date(bhulekh.mutation_date) if bhulekh.mutation_date else None
        lud = parse_flexible_date(bhulekh.last_updated) if bhulekh.last_updated else None
        ref = md or lud
        bad, msg = compare_dates_doc_vs_bhulekh(d, ref)
        if bad and msg:
            details.append(msg)

    if not details:
        return False, "", "", 0.0

    return True, FLAG_DATE_ANOMALY, " ".join(details), 0.18


_REQUIRED = ("owner", "khasra", "area", "date")


def _is_khatauni_text(raw: str) -> bool:
    t = (raw or "").strip().lower()
    hints = ("खतौनी", "उद्धरण", "खातेदार", "गाटा", "भूलेख")
    return any(h in t for h in hints)


def check_missing_required_fields(doc: ExtractedDocumentData) -> RuleHit:
    required = _REQUIRED
    # Khatauni extracts often don't carry registry stamp/date semantics.
    if doc.raw_text and _is_khatauni_text(doc.raw_text):
        required = ("owner", "khasra", "area")
    missing = [f for f in required if not str(getattr(doc, f, "") or "").strip()]
    if not missing:
        return False, "", "", 0.0

    detail = f"Missing or empty required fields: {', '.join(missing)}."
    return True, FLAG_MISSING_FIELDS, detail, 0.12 + 0.02 * len(missing)


def check_document_structure(doc: ExtractedDocumentData) -> RuleHit:
    raw = doc.raw_text
    if raw is None:
        # Without raw text, only light structural check on extracted fields
        filled = sum(1 for f in _REQUIRED if str(getattr(doc, f, "") or "").strip())
        if filled < 2:
            detail = "Very few fields could be extracted; document may be unreadable or non-standard."
            return True, FLAG_DOCUMENT_STRUCTURE, detail, 0.1
        return False, "", "", 0.0

    text = raw.strip()
    if len(text) < 80:
        if str(doc.khasra or "").strip() and (str(doc.owner or "").strip() or str(doc.area or "").strip()):
            return False, "", "", 0.0
        detail = "Extracted text is very short; the upload may be blank, cropped, or not a full deed page."
        return True, FLAG_DOCUMENT_STRUCTURE, detail, 0.12

    lowered = text.lower()
    hints = (
        "khasra",
        "खसरा",
        "registry",
        "पंजीकरण",
        "area",
        "बीघा",
        "biswa",
        "acre",
        "खातेदार",
        "हेक्टेयर",
        "क्षेत्रफल",
        "खतौनी",
        "भूलेख",
        "गाटा",
    )
    if not any(h in lowered for h in hints):
        detail = "Text lacks common land-registry keywords; verify that the correct document was uploaded."
        return True, FLAG_DOCUMENT_STRUCTURE, detail, 0.1

    return False, "", "", 0.0


def check_khasra_mismatch(doc: ExtractedDocumentData, bhulekh: Optional[BhulekhData]) -> RuleHit:
    """Flag when document khasra doesn't match the Bhulekh official khasra."""
    if not bhulekh or not bhulekh.khasra.strip() or not doc.khasra.strip():
        return False, "", "", 0.0

    dk = _normalize_khasra(doc.khasra)
    bk = _normalize_khasra(bhulekh.khasra)
    if not dk or not bk:
        return False, "", "", 0.0
    if dk == bk or dk in bk or bk in dk:
        return False, "", "", 0.0

    detail = (
        f"Document khasra/gata ({doc.khasra.strip()}) does not match "
        f"the official Bhulekh khasra ({bhulekh.khasra.strip()}). "
        "This could indicate a forged or altered document referencing a different plot."
    )
    return True, FLAG_KHASRA_MISMATCH, detail, 0.25


def _normalize_area(s: str) -> str:
    """Extract numeric portion from area strings for comparison."""
    s = (s or "").strip().lower()
    # Remove units and whitespace, keep digits and dots
    nums = re.findall(r"[\d.]+", s)
    return nums[0] if nums else ""


def check_area_mismatch(doc: ExtractedDocumentData, bhulekh: Optional[BhulekhData]) -> RuleHit:
    """Flag when document area significantly differs from the Bhulekh official area."""
    if not bhulekh or not bhulekh.area.strip() or not doc.area.strip():
        return False, "", "", 0.0

    da = _normalize_area(doc.area)
    ba = _normalize_area(bhulekh.area)
    if not da or not ba:
        return False, "", "", 0.0

    try:
        da_f = float(da)
        ba_f = float(ba)
        if da_f == 0 or ba_f == 0:
            return False, "", "", 0.0
        # Allow ±30% tolerance for unit conversion / rounding
        ratio = abs(da_f - ba_f) / max(da_f, ba_f)
        if ratio <= 0.30:
            return False, "", "", 0.0
    except (ValueError, ZeroDivisionError):
        # Non-numeric area strings — do string comparison
        if da == ba:
            return False, "", "", 0.0

    detail = (
        f"Document area ({doc.area.strip()}) differs significantly from "
        f"the official Bhulekh area ({bhulekh.area.strip()}). "
        "This could indicate tampering or an altered document."
    )
    return True, FLAG_AREA_MISMATCH, detail, 0.20


def check_not_official_owner(doc: ExtractedDocumentData, bhulekh: Optional[BhulekhData]) -> RuleHit:
    """
    The strongest forgery signal: the document claims an owner who
    is NOT listed in the official Bhulekh record at all.
    """
    if not bhulekh or not bhulekh.owner_name.strip() or not doc.owner.strip():
        return False, "", "", 0.0

    doc_owner = _norm_name(doc.owner)
    bhulekh_owner = _norm_name(bhulekh.owner_name)
    if not doc_owner or not bhulekh_owner:
        return False, "", "", 0.0

    # Check if document owner appears anywhere in the Bhulekh owner string
    # (Bhulekh may list multiple owners separated by | or commas)
    if doc_owner == bhulekh_owner:
        return False, "", "", 0.0
    if doc_owner in bhulekh_owner or bhulekh_owner in doc_owner:
        return False, "", "", 0.0

    # Token-level check: see if the document owner's name tokens appear in Bhulekh
    doc_tokens = set(doc_owner.split())
    bhu_tokens = set(bhulekh_owner.split())
    # If more than half of the document owner tokens are found in Bhulekh, it's likely a match
    overlap = doc_tokens & bhu_tokens
    if len(overlap) >= max(1, len(doc_tokens) * 0.5):
        return False, "", "", 0.0

    detail = (
        f"Document owner ({doc.owner.strip()}) is NOT found in the official "
        f"Bhulekh record which lists: {bhulekh.owner_name.strip()[:200]}. "
        "This is a strong indicator of a potentially forged or fraudulent document — "
        "the claimed owner does not appear in government land records."
    )
    return True, FLAG_NOT_OFFICIAL_OWNER, detail, 0.35
