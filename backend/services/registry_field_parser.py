"""
Heuristic extraction of Indian land-registry fields from OCR text.

Supports English, Hindi (Devanagari), and mixed UP Bhulekh-style layouts.
Numeric fields accept both ASCII and Devanagari digits (०-९).
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Tuple

from services.khatauni_field_parser import (
    _extract_khasra_gata,
    _extract_plot_from_bhulekh_uid,
    _normalize_khatauni_share,
    _reconcile_share_list,
    extract_khatauni_fields,
    merge_khatauni_with_registry,
)
from services.ocr_field_quality import is_fasli_year_range, is_plausible_khasra, sanitize_registry_fields

# Devanagari block (Hindi etc.)
_DEV = r"\u0900-\u097F"
# Devanagari digits ०-९
_INDIC_DIGITS = "०१२३४५६७८९"
_ASCII_DIGITS = "0123456789"


def _normalize_indic_digits(s: str) -> str:
    """Map ०-९ to 0-9 for consistent downstream use."""
    if not s:
        return s
    return s.translate(str.maketrans(_INDIC_DIGITS, _ASCII_DIGITS))


def _clean(s: str) -> str:
    return " ".join(s.split()).strip(" \t\n\r:;,-.")


def _first_match(patterns: List[Tuple[re.Pattern[str], int]], text: str) -> str:
    for rx, group_idx in patterns:
        m = rx.search(text)
        if m:
            val = m.group(group_idx)
            return _clean(val)
    return ""


def _first_plausible_khasra(patterns: List[Tuple[re.Pattern[str], int]], text: str, flat: str) -> str:
    for src in (text, flat):
        for rx, group_idx in patterns:
            m = rx.search(src)
            if m:
                val = _clean(m.group(group_idx))
                if val and is_plausible_khasra(val):
                    return val
    return ""


def _owner_patterns() -> List[Tuple[re.Pattern[str], int]]:
    """Hindi / UP revenue labels first, then English."""
    return [
        # Hindi — Bhulekh / revenue style
        (
            re.compile(
                r"(?:काश्तकार\s*का\s*नाम|किसान\s*का\s*नाम|भूमि\s*स्वामी\s*का\s*नाम|"
                r"खातेदार\s*का\s*नाम|स्वामी\s*का\s*नाम|भू\s*स्वामी|विक्रेता\s*का\s*नाम|"
                r"खरीददार\s*का\s*नाम|मालिक\s*का\s*नाम)[\s:.\-]*"
                r"([^\n:]{2,120}?)(?=\n|$|(?:पिता|खसरा|काश्तकार|क्षेत्र|रकबा|दिनांक|तारीख|Stamp|stamp|Khasra|khasra|Area))",
                re.UNICODE,
            ),
            1,
        ),
        (
            re.compile(
                rf"(?:नाम|नाम\s*[:.]|नाम\s*के\s*आगे)[\s:.\-]*([{_DEV}A-Za-z][{_DEV}A-Za-z\s.,\-]{{1,100}})",
                re.UNICODE,
            ),
            1,
        ),
        # English
        (
            re.compile(
                r"(?:name\s*of\s*(?:the\s*)?(?:owner|purchaser|vendee|buyer)|owner['’]s\s*name|"
                r"विक्रेता|खरीददार|स्वामी)[\s:.\-]*"
                r"([A-Za-z\u0900-\u097F][A-Za-z\u0900-\u097F\s.\-]{2,80}?)(?:\n|,|;|S\.|पिता|khasra|खसरा)",
                re.I | re.UNICODE,
            ),
            1,
        ),
        (
            re.compile(
                r"(?:Mr\.?|Mrs\.?|Ms\.?|Shri|श्री|Smt\.?|श्रीमती)\s+([A-Za-z\u0900-\u097F][A-Za-z\u0900-\u097F\s.\-]{2,60})",
                re.UNICODE,
            ),
            1,
        ),
    ]


def _father_patterns() -> List[Tuple[re.Pattern[str], int]]:
    return [
        (
            re.compile(
                r"(?:पिता\s*का\s*नाम|पिता\s*के\s*नाम)[\s:.\-]*"
                r"([^\n:]{2,80}?)(?=\n|$|(?:माता|खसरा|गाटे|काश्तकार|नाम|दिनांक|Stamp|khasra))",
                re.UNICODE,
            ),
            1,
        ),
        (
            re.compile(
                r"(?:पिता|Father)\s*[/:]\s*([A-Za-z\u0900-\u097F][A-Za-z\u0900-\u097F\s.\-]{2,55})"
                r"(?=\s|$|\n|गाटे|खसरा|क्षेत्र)",
                re.I | re.UNICODE,
            ),
            1,
        ),
        (
            re.compile(
                r"(?:S\.?\s*/?\s*O\.?|son\s*of)\s*[:\s]*"
                r"([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,4})",
                re.I | re.UNICODE,
            ),
            1,
        ),
    ]


def _khasra_patterns() -> List[Tuple[re.Pattern[str], int]]:
    return [
        # UP Bhulekh table: red cell "113 (1210320113000012)"
        (
            re.compile(
                r"(?<![\d\u0966-\u096F])([\d\u0966-\u096F]{2,5})\s*\([\d\u0966-\u096F]{12,24}\)",
                re.UNICODE,
            ),
            1,
        ),
        # First column cell on line after खसरा/गाटा संख्या header
        (
            re.compile(
                r"खसरा\s*/\s*गाटा\s*संख्या[^\n]*\n\s*([\d\u0966-\u096F]{1,8}(?:\s*[/\\\-]\s*[\d\u0966-\u096F]{1,8})?)(?:\s|$|\n)",
                re.UNICODE,
            ),
            1,
        ),
        (
            re.compile(
                r"(?:khasra|khasra\s*no|खसरा|खसरा\s*संख्या|खसरा\s*नं|खसरा\s*नंबर|खसरा\s*न\.?)[\s:.\-]*"
                r"([0-9\u0966-\u096F]{1,6}(?:\s*[/\\\-]\s*[0-9\u0966-\u096F]{1,6})+"
                r"(?:\s*[,;]\s*[0-9\u0966-\u096F]{1,6}(?:\s*[/\\\-]\s*[0-9\u0966-\u096F]{1,6})+)*)",
                re.I | re.UNICODE,
            ),
            1,
        ),
        # Short plot nos only (avoid matching Fasli 1430-1435 — filtered later)
        (
            re.compile(
                r"\b([0-9\u0966-\u096F]{1,4}\s*[/\\\-]\s*[0-9\u0966-\u096F]{1,4})\b",
                re.UNICODE,
            ),
            1,
        ),
    ]


def _area_patterns() -> List[Tuple[re.Pattern[str], int]]:
    return [
        (
            re.compile(
                r"गाटे\s*का\s*कुल\s*क्षेत्रफल[^\d\u0966-\u096F]{0,55}([0-9\u0966-\u096F]+[.,][0-9\u0966-\u096F]+)\s*(?:हेक्टेयर|हे\.|ha\b)?",
                re.I | re.UNICODE,
            ),
            1,
        ),
        (
            re.compile(
                r"(?:area|land\s*area|extent|रकबा|क्षेत्रफल|क्षेत्र|फल|रकबा\s*क्षेत्र)[\s:.\-]*"
                r"([0-9\u0966-\u096F][0-9\u0966-\u096F.,\s]*(?:bigha|biswa|acre|hectare|ha|sq\.?\s*m\.?|meter|metre|"
                r"गज|बीघा|बिस्वा|हेक्टेयर|हे\.|मी\.?|मीटर)?[^\n,]{0,100}?)",
                re.I | re.UNICODE,
            ),
            1,
        ),
        (
            re.compile(
                r"([0-9\u0966-\u096F][0-9\u0966-\u096F.,\s]*(?:bigha|biswa|acre|hectare|ha|बीघा|बिस्वा|हेक्टेयर)\b[^\n,]{0,50})",
                re.I | re.UNICODE,
            ),
            1,
        ),
    ]


def _stamp_patterns() -> List[Tuple[re.Pattern[str], int]]:
    return [
        (
            re.compile(
                r"(?:stamp\s*(?:no\.?|number|#)|स्टाम्प|अभिशुल्क|शुल्क\s*पत्र)[\s:.\-]*"
                r"([A-Za-z0-9\u0966-\u096F/\-]{4,40})",
                re.I | re.UNICODE,
            ),
            1,
        ),
        (
            re.compile(
                r"(?:judicial\s*stamp|non[\s\-]?judicial)[\s:.\-]*([A-Za-z0-9/\-]{3,32})",
                re.I,
            ),
            1,
        ),
    ]


def parse_registry_fields(ocr_text: str) -> Dict[str, Any]:
    """
    Parse owner, father, khasra, area, registry date, stamp number from OCR text.

    Handles Hindi (Devanagari) and English; normalizes Indic digits to ASCII in outputs.
    """
    if not ocr_text or not ocr_text.strip():
        return {
            "owner": "",
            "father": "",
            "khasra": "",
            "area": "",
            "date": "",
            "stamp_id": "",
            "district": "",
            "tehsil": "",
            "village": "",
            "khata_number": "",
            "ownership_entries": [],
        }

    text = ocr_text.replace("\r\n", "\n")
    flat = " ".join(text.split())

    khasra = _first_plausible_khasra(_khasra_patterns(), text, flat)
    area = _first_match(_area_patterns(), text) or _first_match(_area_patterns(), flat)

    date_patterns: List[Tuple[re.Pattern[str], int]] = [
        (re.compile(r"\b(\d{1,2}[/.\-\u0966-\u096F]{0,3}\d{1,2}[/.\-\u0966-\u096F]{0,3}\d{2,4})\b"), 1),
        (re.compile(r"\b(\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{2,4})\b", re.I), 1),
    ]
    date_str = ""
    reg_near = re.search(
        r"(?:registry|registration|पंजीकरण|दाखिल|दिनांक|तारीख|तिथि)[^\d\u0966-\u096F]{0,40}"
        r"(\d{1,2}[/.\-]\d{1,2}[/.\-]\d{2,4})",
        flat,
        re.I,
    )
    if reg_near:
        date_str = _clean(reg_near.group(1))
    else:
        for rx, gi in date_patterns:
            m = rx.search(flat)
            if m:
                date_str = _clean(_normalize_indic_digits(m.group(gi)))
                break

    if date_str and is_fasli_year_range(date_str):
        date_str = ""
    # Reject area-like decimals mistaken for dates (e.g. 0.1640 हेक्टेयर)
    if date_str and re.match(r"^\d\.\d{3,5}$", date_str.strip().replace(" ", "")):
        date_str = ""

    stamp_id = _first_match(_stamp_patterns(), text) or _first_match(_stamp_patterns(), flat)

    father = _first_match(_father_patterns(), text) or _first_match(_father_patterns(), flat)

    owner = _first_match(_owner_patterns(), text)
    if not owner:
        owner = _first_match(_owner_patterns(), flat)

    base = {
        "owner": _normalize_indic_digits(owner),
        "father": _normalize_indic_digits(father),
        "khasra": _normalize_indic_digits(khasra),
        "area": _normalize_indic_digits(area),
        "date": _normalize_indic_digits(date_str),
        "stamp_id": _normalize_indic_digits(stamp_id),
        "district": "",
        "tehsil": "",
        "village": "",
        "khata_number": "",
        "ownership_entries": [],
    }

    kh = extract_khatauni_fields(ocr_text)
    merged = merge_khatauni_with_registry(base, kh)
    # Table-aware khasra (plot embedded in भू-आईडी) overrides generic regex hits like 423.
    gk = _extract_khasra_gata(text)
    if gk:
        merged["khasra"] = _normalize_indic_digits(gk)
    # खाता संख्या sometimes OCR'd as a bare number and mistaken for a "date"
    ds = (merged.get("date") or "").strip()
    kn = (merged.get("khata_number") or "").strip()
    if ds and kn and ds == kn:
        merged["date"] = ""
    elif ds and re.fullmatch(r"\d{3,6}", ds.replace(" ", "")) and "/" not in ds and "-" not in ds:
        merged["date"] = ""
    merged = sanitize_registry_fields(merged)
    oe_shares = merged.get("ownership_entries")
    if isinstance(oe_shares, list) and oe_shares:
        rows = [r for r in oe_shares if isinstance(r, dict)]
        n_oe = len(rows)
        if n_oe:
            sh = [_normalize_khatauni_share(str(r.get("share") or "")) for r in rows]
            sh = _reconcile_share_list(sh, n_oe)
            for i, r in enumerate(rows):
                if i < len(sh):
                    r["share"] = sh[i]
    # Prefer plot decoded from भू-आईडी over mis-OCR column (423, bare 3, etc.)
    mk = (merged.get("khasra") or "").strip()
    mkn = _normalize_indic_digits(mk)
    compact = re.sub(r"\s+", "", text)
    inferred = ""
    for m in re.finditer(r"\(([\d\u0966-\u096F]{12,24})\)", text):
        inner = _normalize_indic_digits(m.group(1))
        inferred = _extract_plot_from_bhulekh_uid(inner)
        if inferred:
            break
    if not inferred:
        for m in re.finditer(r"121032\d{10}", compact):
            inferred = _extract_plot_from_bhulekh_uid(m.group(0))
            if inferred:
                break
    if inferred and inferred != mkn:
        if mkn in ("423", "425", "४२३", "४२५", "3", "13", "23", "33") or (
            mkn.isdigit() and len(mkn) <= 2
        ):
            merged["khasra"] = inferred
    oe = merged.get("ownership_entries")
    if isinstance(oe, list) and oe and not (merged.get("owner") or "").strip():
        merged["owner"] = _normalize_indic_digits(
            " | ".join(
                str(r.get("owner", "") or "").strip()
                for r in oe
                if isinstance(r, dict) and (str(r.get("owner", "") or "").strip())
            )
        )
    return merged
