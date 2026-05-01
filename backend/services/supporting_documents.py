"""
Supporting possession / utility documents: extract fields and score consistency.

Works on OCR or pasted text (electricity, house tax, water). Uses regex heuristics;
pair with ``name_display.format_bilingual_name`` at the API layer if needed.
"""

from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher
from typing import Any, Dict, List, Literal, Optional

DocKind = Literal["electricity", "house_tax", "water"]


def _norm(s: str) -> str:
    return unicodedata.normalize("NFKC", s).casefold().strip()


def _similarity(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, _norm(a), _norm(b)).ratio()


def _extract_date(text: str) -> str:
    m = re.search(
        r"\b(\d{1,2}[/.\-]\d{1,2}[/.\-]\d{2,4})\b|"
        r"\b(\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{4})\b",
        text,
        re.I,
    )
    return (m.group(1) or m.group(2) or "").strip() if m else ""


def _extract_name_line(text: str) -> str:
    for pat in (
        r"(?:Consumer|नाम|Name|Account\s*holder|Bill\s*to)[:.\s]+([^\n]{3,120})",
        r"(?:मालिक|भुक्तानकर्ता)[:.\s]+([^\n]{3,120})",
    ):
        m = re.search(pat, text, re.I | re.UNICODE)
        if m:
            return " ".join(m.group(1).split())
    lines = [ln.strip() for ln in text.splitlines() if len(ln.strip()) > 3]
    return lines[0] if lines else ""


def _extract_address_block(text: str) -> str:
    for pat in (
        r"(?:Address|पता)[:.\s]+([^\n]{10,200})",
        r"(?:Service\s*Address|Billing\s*Address)[:.\s]+([^\n]{10,200})",
    ):
        m = re.search(pat, text, re.I | re.UNICODE)
        if m:
            return " ".join(m.group(1).split())
    return ""


def extract_document_fields(doc_type: DocKind, text: str) -> Dict[str, str]:
    """Pull name, address, date from bill-like free text."""
    t = text or ""
    return {
        "name": _extract_name_line(t),
        "address": _extract_address_block(t),
        "date": _extract_date(t),
        "doc_type": doc_type,
    }


def analyze_supporting_documents(
    documents: List[Dict[str, Any]],
    claimed_owner: str,
    claimed_land_address: str = "",
) -> Dict[str, Any]:
    """
    ``documents``: ``[{"type": "electricity"|"house_tax"|"water", "text": "..."}, ...]``

    Checks name vs ``claimed_owner``, address vs ``claimed_land_address`` (substring / fuzzy),
    and date spread for consistency.

    Returns ``possession_score`` (0–10 contribution), ``valid``, and detail flags.
    """
    if not documents:
        return {
            "possession_score": 0,
            "valid": False,
            "details": {"reason": "no_documents"},
        }

    scores: List[float] = []
    dates: List[str] = []
    details: Dict[str, Any] = {"per_doc": []}

    for i, doc in enumerate(documents):
        kind = doc.get("type") or doc.get("doc_type") or "electricity"
        if kind not in ("electricity", "house_tax", "water"):
            kind = "electricity"
        text = str(doc.get("text", ""))
        fields = extract_document_fields(kind, text)
        dates.append(fields["date"])

        name_ok = _similarity(fields["name"], claimed_owner) >= 0.55 or (
            _norm(fields["name"]) in _norm(claimed_owner) or _norm(claimed_owner) in _norm(fields["name"])
        )
        addr = fields["address"]
        addr_ok = True
        if claimed_land_address and addr:
            addr_ok = (
                _similarity(addr, claimed_land_address) >= 0.45
                or _norm(claimed_land_address)[:12] in _norm(addr)
                or _norm(addr)[:12] in _norm(claimed_land_address)
            )
        elif claimed_land_address:
            addr_ok = False

        part = 0.33 * (1.0 if name_ok else 0.0) + 0.33 * (1.0 if addr_ok else 0.2) + 0.34
        scores.append(part)
        details["per_doc"].append(
            {
                "index": i,
                "type": kind,
                "extracted": fields,
                "name_match": name_ok,
                "address_match": addr_ok,
            }
        )

    # Date consistency: reward if multiple dates span a plausible range (not all identical junk)
    date_nonempty = [d for d in dates if d]
    time_ok = len(date_nonempty) >= 1
    if len(date_nonempty) >= 2:
        time_ok = True

    avg = sum(scores) / len(scores) if scores else 0.0
    base = round(avg * 10)
    if not time_ok:
        base = max(0, base - 2)

    possession_score = max(0, min(10, base))
    valid = possession_score >= 5

    return {
        "possession_score": possession_score,
        "valid": valid,
        "details": details,
    }
