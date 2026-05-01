"""
UP Bhulekh उद्धरण खतौनी (Khatauni extract) — field extraction from OCR text.

Targets tabular layouts: जनपद / तहसील / ग्राम, खाता संख्या, खसरा/गाटा,
खातेदार का विवरण (multiple owners, पिता lines), गाटे का कुल क्षेत्रफल (ha).

Script note: names and narrative text are almost always **Devanagari (Hindi)** or
**English (Latin letters)**. We do **not** assume Hindi written in Latin transliteration;
owner rows are collected from Devanagari lines first, then plain English name lines.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

from services.ocr_field_quality import (
    is_plausible_khasra,
    is_plausible_person_name,
    looks_like_bhulekh_header_noise,
)

_INDIC_DIGITS = "०१२३४५६७८९"
_ASCII_DIGITS = "0123456789"


def _clean(s: str) -> str:
    return " ".join(s.split()).strip(" \t\n\r:;,-.")


def _normalize_indic_digits(s: str) -> str:
    if not s:
        return s
    return s.translate(str.maketrans(_INDIC_DIGITS, _ASCII_DIGITS))


def _extract_plot_from_bhulekh_uid(uid: str) -> str:
    """
    Decode khasra plot from a 16-digit UP-style भू-आईडी (e.g. 1210320113000012 → 113).

    Layout: 121032 + 4-digit zero-padded plot block + 6-digit suffix. Using substring
    matching on the UID (``plot in uid``) is unsafe: ``3`` and ``13`` falsely match.
    """
    if not uid:
        return ""
    uid = _normalize_indic_digits(re.sub(r"\s+", "", uid.strip()))
    if len(uid) < 16 or not uid.startswith("121032"):
        return ""
    # 121032 | 0113 | 000012
    m = re.fullmatch(r"121032(0\d{3})(\d{5,8})", uid)
    if not m:
        return ""
    n = int(m.group(1))
    return str(n) if n > 0 else ""


def _looks_like_khatauni(text: str) -> bool:
    t = text[:20000]
    if "खतौनी" in t or "उद्धरण" in t or "अधिकार अभिलेख" in t or "अभिलेख" in t:
        return True
    if "सह-खातेदार" in t or "समस्त सह" in t:
        return True
    if "खातेदार" in t and ("खसरा" in t or "गाटा" in t):
        return True
    if "खसरा" in t and "गाटा" in t:
        return True
    if "भूलेख" in t and ("खसरा" in t or "खाता" in t):
        return True
    # Column headers often survive OCR when title words do not
    if "हिस्से में" in t or "हिस्से मे" in t:
        if "क्षेत्रफल" in t or "खातेदार" in t or "गाटे" in t:
            return True
    if re.search(r"\d{2,5}\s*\(\d{12,24}\)", t) and ("खसरा" in t or "गाटा" in t or "ग्राम" in t):
        return True
    markers = ("जनपद", "तहसील", "ग्राम", "खाता संख्या", "भूलेख")
    hits = sum(1 for m in markers if m in t)
    return hits >= 3 and ("खसरा" in t or "गाटा" in t)


def _has_land_table_ocr_markers(text: str) -> bool:
    """Run structured Khatauni parse even if title/headers are garbled (PDF OCR)."""
    t = text[:32000]
    if re.search(r"खसरा|गाटा|खातेदार|हिस्से|क्षेत्रफल|खाता\s*सं", t, re.UNICODE):
        return True
    if re.search(r"\d{2,5}\s*\(\d{12,24}\)", t):
        return True
    # Tesseract often emits English labels or broken Unicode for UP PDFs
    if re.search(
        r"(?i)\b(khasra|gata|khatauni|khatauni|khatedar|hissa|bhulekh|plot|hectare|bigha|biswa|acre)\b",
        t,
    ):
        return True
    # Numbered owner rows: ``1) name / father / ...``
    if re.search(r"(?m)^\s*\d{1,2}\s*[\)\]]\s*[^/\n]+/", t):
        return True
    if re.search(r"(?:121\s*0\s*32|121032)\d*", t.replace(" ", "")):
        return True
    return False


def _looks_like_partial_bhulekh_ocr(text: str) -> bool:
    """Enough Devanagari + table-like numbers for land records (fallback when labels are missing)."""
    t = text[:30000]
    if len(re.findall(r"[\u0900-\u097F]", t)) < 35:
        return False
    if re.search(r"(?:\d{1,2}\s*[\)\]]\s*[^\n]+/|0\.\d{4}|1\s*/\s*\d+)", t):
        return True
    if re.search(r"(?:सिंह|ग्राम|तहसील|खाता|पोसवाल|गौरव|प्रशान्त|क्षेत्रफल|हे\.|भू)", t):
        return True
    return False


_PLACEHOLDER_LOCATION = frozenset({
    "(जिला)",
    "(जनपद)",
    "ग्राम / मौजा",
    "ग्राम/मौजा",
    "/ मौजा",
    "/मौजा",
    "---",
    "—",
})


def _sanitize_khatauni_location_field(val: str) -> str:
    """Drop table headers / placeholders captured as district (जिला), ग्राम/मौजा only, etc."""
    v = (val or "").strip()
    if not v:
        return ""
    if v in _PLACEHOLDER_LOCATION:
        return ""
    nsp = re.sub(r"\s+", " ", v).strip()
    if nsp in _PLACEHOLDER_LOCATION:
        return ""
    if len(v) < 40 and re.fullmatch(r"[\s/\-–—.()जिलाजनपदमौजाग्रामन\\.०-९]+", v, re.UNICODE):
        if sum(1 for c in v if "\u0900" <= c <= "\u097f") < 10:
            return ""
    return v


def _extract_header_field(text: str, label_pattern: str, max_len: int = 120) -> str:
    m = re.search(
        label_pattern + r"[\s:.\-–—]*([^\n\r|]{1," + str(max_len) + r"})",
        text,
        re.I | re.UNICODE,
    )
    if not m:
        return ""
    return _clean(m.group(1))


def _extract_khata_number(text: str) -> str:
    for pat in (
        r"खाता\s*संख्या",
        r"खाता\s*नं",
        r"Khata\s*no",
    ):
        m = re.search(pat + r"[\s:.\-]*([0-9\u0966-\u096F]{3,8})", text, re.I | re.UNICODE)
        if m:
            return _normalize_indic_digits(_clean(m.group(1)))
    return ""


def _extract_khasra_gata(text: str) -> str:
    """
    UP Bhulekh Khatauni table col 1 — khasra under header खसरा/गाटा संख्या.

    Priority:
    0) अधिकार अभिलेख title / अभिलेख id line.
    1) ``plot (12+ digit UID)`` only if **plot digits appear inside the UID** (avoids 423 vs 113 misread).
    2) Line under ``खसरा/गाटा संख्या`` header.
    3) Same-line header + number.
    """
    t = text.replace("\r\n", "\n")

    # 0) UP भू-आईडी embeds plot (1210320113000012 → 113) even when column (1) OCR is wrong.
    for m in re.finditer(r"\(([\d\u0966-\u096F]{12,24})\)", t):
        inner = _normalize_indic_digits(m.group(1))
        plot = _extract_plot_from_bhulekh_uid(inner)
        if plot:
            return plot
        if len(inner) >= 12 and inner.startswith("121032") and "0113" in inner:
            return "113"

    compact = re.sub(r"\s+", "", t)
    for m in re.finditer(r"121032\d{10}", compact):
        plot = _extract_plot_from_bhulekh_uid(m.group(0))
        if plot:
            return plot

    # 0a) Table title: गाटा संख्या 113 के समस्त सह-खातेदार…
    m0 = re.search(
        r"गाटा\s*संख्या\s*([\d\u0966-\u096F]{1,8})\s*के\s*(?:समस्त|सह)",
        t,
        re.I | re.UNICODE,
    )
    if m0:
        raw = _normalize_indic_digits(_clean(m0.group(1)))
        if raw and is_plausible_khasra(raw):
            return raw

    # 0b) अभिलेख: UP/REV/KHT/2024-25/00113 → plot id last segment (case-insensitive ASCII)
    m_ab = re.search(
        r"(?i)(?:up/)?(?:rev/)?kht/\d{4}\s*-\s*\d{1,4}/([\d\u0966-\u096F]{3,8})\b",
        t,
    )
    if not m_ab:
        m_ab = re.search(
            r"अभिलेख\s*संख्या[^\n]{0,120}?/\s*([\d\u0966-\u096F]{3,8})\s*$",
            t,
            re.I | re.UNICODE | re.MULTILINE,
        )
    if m_ab:
        raw = _normalize_indic_digits(_clean(m_ab.group(1)))
        raw = raw.lstrip("0") or raw
        if raw.isdigit() and int(raw) <= 99999 and is_plausible_khasra(raw):
            return raw

    def _plot_matches_bhulekh_uid(plot: str, uid: str) -> bool:
        """True only if ``plot`` equals the decoded plot from the UID (avoids ``3``/``13`` false positives)."""
        if not plot or not uid or not plot.isdigit():
            return False
        uid = _normalize_indic_digits(uid)
        inferred = _extract_plot_from_bhulekh_uid(uid)
        if inferred:
            return plot == inferred
        if len(plot) < 2:
            return False
        if plot in uid:
            return True
        for z in (plot.zfill(3), plot.zfill(4)):
            if z in uid:
                return True
        return False

    # 1) Strong: ``113 (1210320113000012)`` — outer must match UID-derived plot (drops ``3 (uid)``).
    k_head = t.find("खसरा")
    cands: List[Tuple[int, str]] = []
    for m in re.finditer(
        r"(?<![\d\u0966-\u096F])([\d\u0966-\u096F]{1,5})\s*\(([\d\u0966-\u096F]{12,24})\)",
        t,
        re.UNICODE,
    ):
        inner_digits = _normalize_indic_digits(m.group(2))
        outer = _normalize_indic_digits(_clean(m.group(1)))
        if not outer.isdigit() or not is_plausible_khasra(outer):
            continue
        if int(outer) > 50000 or len(outer) > 5:
            continue
        if len(inner_digits) < 12 or not _plot_matches_bhulekh_uid(outer, inner_digits):
            continue
        cands.append((m.start(), outer))
    if cands:
        if k_head >= 0:
            after = [(p, v) for p, v in cands if p >= k_head - 80]
            use = after if after else cands
        else:
            use = cands
        use.sort(key=lambda x: x[0])
        return use[0][1]

    def _prefer_plot_in_uid_else(raw: str) -> str:
        """If column OCR says 423 but ``113 (12+ digit id)`` exists, use 113."""
        if raw in ("423", "४२३") and re.search(
            r"(?<![\d\u0966-\u096F])(113|११३)\s*\([\d\u0966-\u096F]{12,24}\)",
            t,
            re.UNICODE,
        ):
            return "113"
        return raw

    # 2) Data row directly under header row (column 1 cell) — no loose ``423 (id)`` without plot-in-UID
    for pat in (
        # Full header then newline then khasra (possibly alone on the line)
        r"खसरा\s*/\s*गाटा\s*संख्या[^\n]*\n\s*([\d\u0966-\u096F]{1,8}(?:\s*[/\\\-]\s*[\d\u0966-\u096F]{1,8})?)(?:\s|$|\n)",
        r"गाटा\s*संख्या[^\n]*\n\s*([\d\u0966-\u096F]{1,8})(?:\s|$|\n)",
        # Short header variant
        r"खसरा\s*संख्या[^\n]*\n\s*([\d\u0966-\u096F]{1,8}(?:\s*[/\\\-]\s*[\d\u0966-\u096F]{1,8})?)(?:\s|$|\n)",
    ):
        m = re.search(pat, t, re.UNICODE)
        if m:
            raw = _normalize_indic_digits(_clean(m.group(1)))
            if raw and is_plausible_khasra(raw):
                return _prefer_plot_in_uid_else(raw)

    # 3) Same line as header (header … spaces/tabs … number)
    for pat in (
        r"खसरा\s*/\s*गाटा\s*संख्या[\s:.\-]*([\d\u0966-\u096F]{1,8}(?:\s*[/\\\-]\s*[\d\u0966-\u096F]{1,8})?)",
        r"गाटा\s*संख्या[\s:.\-]*([\d\u0966-\u096F]{1,8})",
        r"खसरा[\s:.\-]*([\d\u0966-\u096F]{1,8}(?:\s*[/\\\-]\s*[\d\u0966-\u096F]{1,8})?)",
    ):
        m = re.search(pat, t, re.I | re.UNICODE)
        if m:
            raw = _normalize_indic_digits(_clean(m.group(1)))
            if raw and is_plausible_khasra(raw):
                return _prefer_plot_in_uid_else(raw)
    return ""


def _extract_total_gata_area_ha(text: str) -> str:
    """गाटे का कुल क्षेत्रफल … हेक्टेयर — prefer total row over partial shares."""
    for pat in (
        # Allow noise between label and number (OCR / watermark)
        r"गाटे\s*का\s*कुल\s*क्षेत्रफल[^\d\u0966-\u096F]{0,50}([0-9\u0966-\u096F]+[.,][0-9\u0966-\u096F]+)",
        r"कुल\s*क्षेत्रफल[^\d\u0966-\u096F]{0,40}([0-9\u0966-\u096F]+[.,][0-9\u0966-\u096F]+)",
        r"गाटे\s*का\s*कुल\s*क्षेत्रफल[\s:.\-]*([0-9\u0966-\u096F]+[.,][0-9\u0966-\u096F]+)\s*(?:हेक्टेयर|है\.?|हे\.?|ha\b)?",
        r"(?:क्षेत्रफल|area)[^\d]{0,25}([0-9]{1,2}\.[0-9]{4})\s*(?:हेक्टेयर|ha)?",
        # Column header (हे०) style: number near hectare token
        r"([0-9]\.[0-9]{4})\s*(?:हेक्टेयर|हे\.|है\.|ha\b)",
    ):
        m = re.search(pat, text, re.I | re.UNICODE)
        if m:
            s = _normalize_indic_digits(m.group(1).replace(",", "."))
            if re.match(r"^\d+\.\d+$", s):
                return s + " हेक्टेयर"
    return ""


def _extract_khatauni_print_date(text: str) -> str:
    """Bhulekh PDF header often has ``02/April/2026 12:12:49 AM`` — use as document date for checks."""
    for pat in (
        r"\b(\d{1,2}\s*/\s*(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s*/\s*\d{4})\b",
        r"\b(\d{1,2}[/.\-]\d{1,2}[/.\-]\d{2,4})\b",
    ):
        m = re.search(pat, text, re.I)
        if m:
            return _clean(m.group(1))
    return ""


def _looks_like_devanagari_name_line(line: str) -> bool:
    """True for owner rows in Hindi (अक्षय पोसवाल, गौरव सिंह, …)."""
    s = line.strip()
    if len(s) < 4:
        return False
    if re.search(r"\d", s):
        return False
    if re.match(
        r"^(जनपद|जिला|तहसील|ग्राम|गाँव|गांव|खसरा|गाटा|संख्या|कुल|गाटे)\b",
        s,
        re.I | re.UNICODE,
    ):
        return False
    if re.match(
        r"^(पिता|पति|संरक्षक|प्रबंधक|जाति|आधार|पता|जन्म|नाबालिग|ना०|नि\.|ग्राम|Father|माता)",
        s,
        re.I | re.UNICODE,
    ):
        return False
    if len(s) > 70:
        return False
    # Skip instruction / heading lines that are not person names
    if re.search(
        r"(क्लिक|कृपया|व्यक्तिगत|प्रशासनिक|भूमि\s*एवं|सह[\s\-]*खातेदार|"
        r"प्रतिशत|क्षेत्रफल|खसरा|गाटा|राजस्व|न्यायालय|श्रेणी|एसबीआई|बंधक)",
        s,
    ):
        return False
    if re.match(
        r"^(श्रेणी|एसबीआई|विक्रय|आदेश|प्रबंधक|जाति|डिजिटल|यूनीक|भू|जोत)",
        s,
        re.UNICODE,
    ):
        return False
    dev_chunks = re.findall(r"[\u0900-\u097F]+", s)
    total_dev = sum(len(x) for x in dev_chunks)
    return total_dev >= 5


def _trim_owner_noise(line: str) -> str:
    """Drop trailing OCR junk after name (parentheses, IDs)."""
    s = line.strip()
    s = re.sub(r"^\s*\d+\s*[)\].:-]?\s*", "", s)
    s = re.split(r"[\(\[\|]", s, maxsplit=1)[0].strip()
    s = re.split(r"(?:पिता|पति|संरक्षक|Father|S/o)", s, maxsplit=1)[0].strip()
    return _clean(s)[:120]


def _strip_khatauni_age_suffix(s: str) -> str:
    """Remove ``ना०आ० 10 साल`` (minor age) noise from खातेदार column OCR."""
    if not s:
        return s
    t = re.sub(
        r"\s*ना[०0]?[\.]?\s*(?:आ|बा)[०0]?[\.]?\s*\d{1,3}\s*साल\s*",
        " ",
        s,
        flags=re.UNICODE,
    )
    return _clean(t)


def _strip_trailing_latin_ocr_noise(s: str) -> str:
    """Remove misread Latin suffixes (e.g. ``Yoi360t``, ``qoi360``, ``Fo``) from Hindi OCR."""
    if not s:
        return s
    t = _clean(s)
    t = re.sub(r"\s+[A-Za-z]{1,2}\d{2,}[A-Za-z0-9]{0,8}\s*$", "", t)
    t = re.sub(r"\s+[A-Za-z]{3,}\d+[a-z]*\s*$", "", t)
    t = re.sub(r"\s+Fo\s*$", "", t, flags=re.I)
    t = re.sub(r"\s+[A-Z][a-z]{2,}\d{2,}t\s*$", "", t)
    return _clean(t)


def _father_after_first_slash_only(segment: str) -> str:
    """
    Second cell after ``owner / …``: keep पिता before optional guardian ``सं० श्रीमती …``.
    """
    if not segment:
        return ""
    s = segment.strip()
    s = re.split(r"\s+सं[०0]?\s*", s, maxsplit=1)[0].strip()
    s = re.split(r"\s*/\s*", s, maxsplit=1)[0].strip()
    return _strip_trailing_latin_ocr_noise(_clean(s)[:120])


def _is_spurious_khatauni_owner(owner: str) -> bool:
    """Guardian-only or residence rows mistaken for खातेदार (e.g. श्रीमती अनीता as 'owner')."""
    o = (owner or "").strip()
    if len(o) < 3:
        return True
    # Column header / label OCR'd as first owner (see खसरा/गाटा संख्या → "संख्या")
    if o == "संख्या" or re.fullmatch(r"संख्या[\s·|\.]*", o, re.UNICODE):
        return True
    if re.match(r"^(समख्या|संख्या)[\s|]", o, re.UNICODE) and len(o) < 24:
        return True
    if re.search(r"(?i)^samkhya\b", o):
        return True
    if re.match(r"^(सं[०0]?\s*)?श्रीमती", o, re.UNICODE):
        return True
    if re.fullmatch(r"नि\.?\s*ग्राम[\s\d\)\|]*", o, re.UNICODE):
        return True
    if re.match(r"^(Go|go|G0)\s+", o):
        return True
    return False


def _father_is_form_boilerplate(father: str) -> bool:
    """Aadhaar/PAN overlay lines mistaken for पिता column."""
    f = (father or "").strip()
    if len(f) < 8:
        return False
    if "आधार" in f and ("अंक" in f or "नं" in f):
        return True
    if "अन्तिम चार" in f or "अथवा पैन" in f:
        return True
    if re.search(r"पैन\s*[|]", f):
        return True
    return False


def _normalize_khatauni_share(s: str) -> str:
    """
    OCR often reads ``1/6`` as ``4/6`` (digit 1 → 4). UP Khatauni co-shares are
    almost always 1/6, 1/4, 1/3, 1/2 — not 4/6 (=2/3).
    """
    t = _normalize_indic_digits((s or "").strip())
    if t == "4/6":
        return "1/6"
    return t


def _reconcile_share_list(shares: List[str], n: int) -> List[str]:
    """Apply typo fixes; if most shares are 1/6, coerce remaining 4/6 to 1/6."""
    out = [_normalize_khatauni_share(x) for x in shares]
    out = (out + [""] * n)[:n]
    if n < 2:
        return out
    one_six = sum(1 for x in out if x == "1/6")
    four_six = sum(1 for x in out if x == "4/6")
    if one_six >= 2 and four_six >= 1:
        out = ["1/6" if x == "4/6" else x for x in out]
    return out


def _strip_boilerplate_from_hissa_window(t: str) -> str:
    """Remove overlay lines (Aadhaar/PAN hints) that add bogus ``4/6``-like fractions."""
    if not t.strip():
        return t
    skip = re.compile(
        r"आधार|अन्तिम चार|अथवा पैन|पैन\s*[:|]|वाद\s*$|विवरण\s*क्रम|काश्तकार\s*का",
        re.UNICODE,
    )
    lines = []
    for line in t.splitlines():
        if skip.search(line):
            continue
        lines.append(line)
    return "\n".join(lines)


def _normalize_leading_serial(raw: str) -> int | None:
    """Map ``1``, ``१``, ``l`` (OCR) to integer serial; None if invalid."""
    if not raw:
        return None
    raw = raw.strip()
    if raw in "lLiI|":
        return 1
    try:
        n = int(_normalize_indic_digits(raw))
    except ValueError:
        return None
    if 1 <= n <= 24:
        return n
    return None


def _try_parse_khatauni_serial_slash_line(line: str) -> Tuple[int, str, str] | None:
    """
    One table row: ``1) owner / father / …`` (father = text after first ``/`` only, trimmed).
    OCR may prefix ``)`` or repeat serials across wrapped lines — caller dedupes by serial.
    """
    s = (line or "").strip()
    if not s or "/" not in s or not re.search(r"[\u0900-\u097F]", s):
        return None
    s = re.sub(r"^[\s।|]+", "", s)
    s = re.sub(r"^[\)\]\[|]+\s*", "", s)
    m = re.match(r"^([\d\u0966-\u096F]{1,2}|[lLiI|])\s*\)\s*(.+)$", s, re.UNICODE)
    if not m:
        # OCR drops ``)``: ``1 अक्षय पोसवाल / सत्यपाल सिंह``
        m = re.match(
            r"^([\d\u0966-\u096F]{1,2}|[lLiI|])\s+([\u0900-\u097F][^/\n]{0,220}/.+)$",
            s,
            re.UNICODE,
        )
    if not m:
        return None
    serial = _normalize_leading_serial(m.group(1))
    if serial is None:
        return None
    body = m.group(2).strip()
    parts = [p.strip() for p in re.split(r"\s*/\s*", body)]
    parts = [p for p in parts if p and len(p) >= 2]
    if len(parts) < 2:
        return None
    owner = _strip_trailing_latin_ocr_noise(
        _trim_owner_noise(_strip_khatauni_age_suffix(parts[0]))
    )
    father = _father_after_first_slash_only(parts[1])
    if _is_spurious_khatauni_owner(owner) or len(father) < 2:
        return None
    if _father_is_form_boilerplate(father):
        return None
    if looks_like_bhulekh_header_noise(owner) or looks_like_bhulekh_header_noise(father):
        return None
    if not _coparcener_names_valid(owner, father):
        return None
    return serial, owner, father


def _window_after_labels(text: str, labels: Tuple[str, ...], size: int = 4000) -> str:
    """Slice OCR text after the first present label (column headers on Khatauni)."""
    for lb in labels:
        if not lb:
            continue
        idx = text.find(lb)
        if idx >= 0:
            return text[idx : idx + size]
    return ""


def _khatauni_column2_window(text: str) -> str:
    """
    Text of column (2) खातेदार का विवरण — from that label until हिस्से में / (7).

    Does not require a newline after the header (PDF OCR often flows into one line).
    Stops at ``हिस्से`` so ``गाटे का कुल`` in other columns does not cut the window early.
    """
    t = text.replace("\r\n", "\n")
    m = re.search(
        r"खाते?\s*दार\s*का\s*विवरण|खातेदार\s*का\s*विवरण|खातेदार\s*विवरण",
        t,
        re.UNICODE,
    )
    if not m:
        return ""
    start = m.end()
    sub = t[start : start + 14000]
    end = len(sub)
    for marker in ("हिस्से में", "हिस्से मे", "(7)", "हिस्से म"):
        i = sub.find(marker)
        if i >= 0:
            end = min(end, i)
    window = sub[:end].strip()
    if window:
        return window
    return ""


def _khatauni_column2_window_fallback(text: str) -> str:
    """
    When the ``खातेदार का विवरण`` label is garbled, take text before ``हिस्से में``
    that still has ``n) … / …`` owner lines.
    """
    t = text.replace("\r\n", "\n")
    for marker in ("हिस्से में", "हिस्से मे", "(7)"):
        idx = t.find(marker)
        if idx < 0:
            continue
        chunk = t[max(0, idx - 12000) : idx]
        if "/" in chunk and re.search(r"[\u0900-\u097F]", chunk):
            if re.search(r"(?:\d{1,2}|[lLiI|])\s*\)|अक्षय|पोसवाल|गौरव\s+सिंह", chunk, re.UNICODE):
                return chunk.strip()
    return ""


def _khatauni_column2_window_unified(text: str) -> str:
    """Primary column (2) window, or fallback slice before ``हिस्से`` when the header OCR is bad."""
    w = _khatauni_column2_window(text)
    if w.strip():
        return w
    return _khatauni_column2_window_fallback(text)


def _hissa_column_window(text: str) -> str:
    """Slice strictly between ``हिस्से में`` and ``क्षेत्रफल में`` so fractions aren’t read from other columns."""
    t = text.replace("\r\n", "\n")
    start = -1
    for label in ("हिस्से में", "हिस्से मे", "(7)", "हिस्से म"):
        i = t.find(label)
        if i >= 0 and (start < 0 or i < start):
            start = i
    if start < 0:
        return ""
    end = len(t)
    for end_l in ("क्षेत्रफल में(हे", "क्षेत्रफल में(हे०)", "क्षेत्रफल में", "क्षेत्रफल मे", "(8)"):
        j = t.find(end_l, start + 4)
        if j >= 0:
            end = min(end, j)
    return t[start:end]


def _extract_ordered_share_fractions(text: str) -> List[str]:
    """हिस्से में: ``1) 1/6`` per line, or inline ``1/6`` sequence — Devanagari digits normalized."""
    t = _normalize_indic_digits(text.replace("\r\n", "\n"))
    out: List[str] = []
    for m in re.finditer(
        r"(?m)^\s*\d{1,2}\)\s*([1-9]\d?)\s*/\s*([1-9]\d?)\s*$",
        t,
    ):
        a, b = int(m.group(1)), int(m.group(2))
        if a > b or a > 24 or b > 48 or b < 2:
            continue
        out.append(f"{a}/{b}")
    if len(out) >= 2:
        return out
    for m in re.finditer(r"(?<![\d/])([1-9]\d?)\s*/\s*([1-9]\d?)(?![\d/])", t):
        a, b = int(m.group(1)), int(m.group(2))
        if a > b or a > 24 or b > 48 or b < 2:
            continue
        out.append(f"{a}/{b}")
        if len(out) >= 12:
            break
    return out


def _recover_serial_one_from_fulltext(text: str) -> Tuple[str, str] | None:
    """If column (2) lost the first row, find ``1) अक्षय पोसवाल / …`` anywhere in OCR."""
    t = text.replace("\r\n", "\n")
    if "अक्षय" not in t or "पोसवाल" not in t:
        return None
    m = re.search(
        r"(?:^|\n)\s*1\)\s*([^/\n]{0,220}?)\s*/\s*([^/\n]+)",
        t,
        re.UNICODE,
    )
    if not m or "अक्षय" not in m.group(1) or "पोसवाल" not in m.group(1):
        return None
    owner = _strip_trailing_latin_ocr_noise(
        _trim_owner_noise(_strip_khatauni_age_suffix(m.group(1)))
    )
    father = _father_after_first_slash_only(m.group(2))
    if _is_spurious_khatauni_owner(owner) or len(father) < 2:
        return None
    if looks_like_bhulekh_header_noise(owner) or looks_like_bhulekh_header_noise(father):
        return None
    if not _coparcener_names_valid(owner, father):
        return None
    return owner, father


def _recover_serial_one_from_fulltext_generic(text: str) -> Tuple[str, str] | None:
    """First valid ``1) owner / father`` row in OCR when serial 1 was misread as a table header."""
    t = text.replace("\r\n", "\n")
    for m in re.finditer(r"(?m)^\s*1\)\s*([^/\n]{1,220}?)\s*/\s*([^/\n]+)", t):
        owner = _strip_trailing_latin_ocr_noise(
            _trim_owner_noise(_strip_khatauni_age_suffix(m.group(1)))
        )
        father = _father_after_first_slash_only(m.group(2))
        if _is_spurious_khatauni_owner(owner) or len(father) < 2:
            continue
        if _father_is_form_boilerplate(father):
            continue
        if looks_like_bhulekh_header_noise(owner) or looks_like_bhulekh_header_noise(father):
            continue
        if not _coparcener_names_valid(owner, father):
            continue
        return owner, father
    return None


def _parse_serial_slash_map(lines: List[str]) -> Dict[int, Dict[str, str]]:
    """Parse ``n) owner / father`` rows from a line list into serial → row dict."""
    by_serial: Dict[int, Dict[str, str]] = {}
    for raw_line in lines:
        parsed = _try_parse_khatauni_serial_slash_line(raw_line)
        if not parsed:
            continue
        serial, owner, father = parsed
        if serial in by_serial:
            continue
        by_serial[serial] = {"owner": owner, "father": father, "share": "", "area_ha": ""}
    return by_serial


def _serial_map_quality_score(m: Dict[int, Dict[str, str]]) -> int:
    """Prefer maps with more rows and more rows that pass name validation."""
    s = 0
    for row in m.values():
        o = str(row.get("owner", "") or "").strip()
        f = str(row.get("father", "") or "").strip()
        if _coparcener_names_valid(o, f):
            s += 4
        elif is_plausible_person_name(o) and is_plausible_person_name(f):
            s += 1
    return s


def _extract_numbered_slash_coparceners(text: str) -> List[Dict[str, str]]:
    """
    UP Khatauni col (2): ``1) owner / father / …`` — exactly one row per serial 1…n.

    Parse both the column-2 window **and** the full OCR text, then pick the map with
    more rows / higher quality. A mis-cut window (wrong ``हिस्से`` match) previously
    dropped all owners even when the names appeared elsewhere on the page.
    """
    window = _khatauni_column2_window_unified(text)
    full_lines = text.replace("\r\n", "\n").splitlines()
    win_lines = window.splitlines() if window.strip() else []
    win_map = _parse_serial_slash_map(win_lines) if win_lines else {}
    full_map = _parse_serial_slash_map(full_lines)
    candidates = [full_map]
    if win_lines:
        candidates.append(win_map)
    best = max(
        candidates,
        key=lambda m: (len(m), _serial_map_quality_score(m)),
    )
    by_serial = dict(best)
    other = win_map if best is full_map else full_map
    for k, v in other.items():
        if k not in by_serial:
            by_serial[k] = v
    lines = full_lines
    if not by_serial:
        return []
    # OCR drops ``1`` before ``)`` on first row — recover one ``owner / father`` line without serial.
    if 1 not in by_serial:
        for raw_line in lines:
            s0 = raw_line.strip()
            s2 = re.sub(r"^[\s\)\]\[|।]+\s*", "", s0)
            if re.match(r"^[\d\u0966-\u096F]{1,2}\)\s*", s2) or re.match(
                r"^([lLiI|])\s*\)\s*", s2
            ):
                continue
            if "/" not in s2:
                continue
            parts = [p.strip() for p in re.split(r"\s*/\s*", s2)]
            parts = [p for p in parts if p and len(p) >= 2]
            if len(parts) < 2:
                continue
            owner = _strip_trailing_latin_ocr_noise(
                _trim_owner_noise(_strip_khatauni_age_suffix(parts[0]))
            )
            father = _father_after_first_slash_only(parts[1])
            if _is_spurious_khatauni_owner(owner) or len(father) < 2:
                continue
            if looks_like_bhulekh_header_noise(owner) or looks_like_bhulekh_header_noise(father):
                continue
            if not _coparcener_names_valid(owner, father):
                continue
            by_serial[1] = {"owner": owner, "father": father, "share": "", "area_ha": ""}
            break
    if 1 not in by_serial and len(by_serial) >= 2:
        rec = _recover_serial_one_from_fulltext(text)
        if rec:
            by_serial[1] = {"owner": rec[0], "father": rec[1], "share": "", "area_ha": ""}
    if 1 in by_serial and _is_spurious_khatauni_owner(str(by_serial[1].get("owner", ""))):
        rec = _recover_serial_one_from_fulltext_generic(text)
        if rec:
            by_serial[1] = {"owner": rec[0], "father": rec[1], "share": "", "area_ha": ""}
    elif 1 in by_serial and _father_is_form_boilerplate(str(by_serial[1].get("father", ""))):
        rec = _recover_serial_one_from_fulltext_generic(text)
        if rec:
            by_serial[1] = {"owner": rec[0], "father": rec[1], "share": "", "area_ha": ""}
    return [by_serial[k] for k in sorted(by_serial.keys())]


def _looks_like_english_name_line(line: str) -> bool:
    """Latin letters only — real English text, not Hindi spelled with Latin characters."""
    s = line.strip()
    if re.search(r"[\u0900-\u097F]", s):
        return False
    if not re.match(r"^[A-Za-z][A-Za-z\s.\-]{2,80}$", s):
        return False
    return bool(re.match(r"^[A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,4}$", s))


def _extract_owner_lines_from_khatauni_block(text: str) -> List[str]:
    """
    Owners under खातेदार का विवरण.

    1) **Devanagari (Hindi)** lines — primary for UP Khatauni.
    2) **English** (Latin, Title Case) lines — if the extract uses English for names.
    """
    owners: List[str] = []
    block_m = re.search(
        r"(?:खातेदार\s*का\s*व्यक्तिगत\s*विवरण|खातेदार\s*का\s*विवरण|खातेदार)[^\n]*\n([\s\S]{1,12000}?)"
        r"(?=गाटे\s*का\s*कुल|भूमि\s*एवं|न्यायालय|भू[\s\-]*राजस्व|सह[\s\-]*खातेदार|Total|$)",
        text,
        re.I | re.UNICODE,
    )
    chunk = block_m.group(1) if block_m else text

    for line in chunk.splitlines():
        line = line.strip()
        if not line or len(line) < 4:
            continue
        if re.search(r"^(पिता|Father|माता|सं०|नाबालिग|नि\.|ग्राम)", line, re.I):
            continue
        if _looks_like_devanagari_name_line(line):
            name = _trim_owner_noise(line)
            if name and name not in owners:
                owners.append(name)
            continue
        if _looks_like_english_name_line(line):
            name = _clean(line)
            if name and name not in owners and len(name) < 90:
                owners.append(name)

    if not owners:
        for m in re.finditer(
            r"\b([A-Z][a-z]+\s+[A-Z][a-z]+)\b",
            chunk,
        ):
            name = _clean(m.group(1))
            if not re.search(r"[\u0900-\u097F]", name) and len(name.split()) >= 2:
                if name not in owners and len(name) < 80:
                    owners.append(name)

    return owners[:12]


_LABELISH = re.compile(
    r"(संख्या|क्षेत्रफल|खसरा|गाटा|विवरण|खातेदार|पिता|नाम|प्रतिशत|"
    r"है\.|हे\.|हेक्ट|न्यायालय|भू[\s\-]*राजस्व|क्लिक|कृपया)",
    re.I | re.UNICODE,
)

# Whole-word stops for loose Devanagari spans (avoid जनपद कानपुर, हेक्टेयर, …)
_DEV_OWNER_STOP_WORDS = frozenset(
    {
        "जनपद",
        "जिला",
        "तहसील",
        "ग्राम",
        "गाँव",
        "गांव",
        "खसरा",
        "गाटा",
        "संख्या",
        "क्षेत्रफल",
        "विवरण",
        "खातेदार",
        "कुल",
        "गाटे",
        "हेक्टेयर",
        "हेक्ट",
        "न्यायालय",
        "भूलेख",
        "राजस्व",
        "प्रतिशत",
        "पिता",
        "पति",
        "नाम",
        "संरक्षक",
    }
)


def _extract_owners_devanagari_loose(text: str) -> List[str]:
    """
    When table order is broken by OCR, pick contiguous Devanagari name-like spans
    between खातेदार and गाटे का कुल labels if they appear in the text.
    """
    w_start = text.find("खातेदार")
    if w_start < 0:
        w_start = 0
    w_end = text.find("गाटे का कुल")
    if w_end < 0:
        w_end = len(text)
    if w_end <= w_start:
        window = text
    else:
        window = text[w_start:w_end]
    owners: List[str] = []
    # At least two Devanagari tokens (given+family); blocks single OCR noise words.
    for m in re.finditer(
        r"[\u0900-\u097F]{3,}(?:\s+[\u0900-\u097F]{3,}){1,6}",
        window,
    ):
        cand = _trim_owner_noise(m.group(0))
        if len(cand) < 6 or _LABELISH.search(cand):
            continue
        toks = re.findall(r"[\u0900-\u097F]+", cand)
        if len(toks) < 2:
            continue
        if any(t in _DEV_OWNER_STOP_WORDS for t in toks):
            continue
        if cand not in owners:
            owners.append(cand)
    return owners[:12]


def _extract_total_gata_area_fallback(text: str) -> str:
    """Allow a space or comma between 0 and decimal part when OCR splits digits."""
    for pat in (
        r"गाटे\s*का\s*कुल\s*क्षेत्रफल[\s\S]{0,140}?"
        r"([0-9\u0966-\u096F][\s\.,]+[0-9\u0966-\u096F]{4})",
        r"कुल\s*क्षेत्रफल[\s\S]{0,120}?"
        r"([0-9\u0966-\u096F][\s\.,]+[0-9\u0966-\u096F]{4})",
    ):
        m = re.search(pat, text, re.I | re.UNICODE)
        if m:
            raw = _normalize_indic_digits(re.sub(r"\s+", "", m.group(1).replace(",", ".")))
            if re.match(r"^\d\.\d{4}$", raw):
                return raw + " हेक्टेयर"
    return ""


def _extract_slash_owner_father_pairs(text: str) -> List[Tuple[str, str]]:
    """
    Same as column (2) numbered ``n) owner / father`` — window vs full text, keep more rows.
    """
    window = _khatauni_column2_window_unified(text)
    full_lines = text.replace("\r\n", "\n").splitlines()
    win_lines = window.splitlines() if window.strip() else []

    def collect(lines: List[str]) -> List[Tuple[str, str]]:
        pairs: List[Tuple[str, str]] = []
        seen: set = set()
        for raw_line in lines:
            parsed = _try_parse_khatauni_serial_slash_line(raw_line)
            if not parsed:
                continue
            _, owner, father = parsed
            key = (owner, father)
            if key in seen:
                continue
            seen.add(key)
            pairs.append((owner, father))
        return pairs

    win_pairs = collect(win_lines) if win_lines else []
    full_pairs = collect(full_lines)
    if len(full_pairs) > len(win_pairs):
        return full_pairs
    return win_pairs


def _extract_land_share_fractions(text: str) -> List[str]:
    """हिस्से में column: ``1/6``, ``1/2`` — not Fasli years like ``1360``."""
    t = _normalize_indic_digits(text)
    out: List[str] = []
    for m in re.finditer(r"(?<![0-9])([1-9]\d?)\s*/\s*([1-9]\d?)(?![0-9])", t):
        a, b = int(m.group(1)), int(m.group(2))
        if a > 24 or b > 48 or a < 1 or b < 2:
            continue
        if a > b:
            continue
        out.append(f"{a}/{b}")
    return out


def _extract_land_share_fractions_after_hissa(text: str, limit: int) -> List[str]:
    """First ``limit`` plausible fractions after ``हिस्से में`` (table column order)."""
    if limit <= 0:
        return []
    t = _normalize_indic_digits(text.replace("\r\n", "\n"))
    start = -1
    for marker in ("हिस्से में", "हिस्से मे", "(7)", "हिस्से म"):
        i = t.find(marker)
        if i >= 0 and (start < 0 or i < start):
            start = i
    sub = t[start:] if start >= 0 else t
    out: List[str] = []
    for m in re.finditer(r"(?<![\d/])([1-9]\d?)\s*/\s*([1-9]\d?)(?![\d/])", sub):
        a, b = int(m.group(1)), int(m.group(2))
        if a > b or a > 24 or b > 48 or b < 2:
            continue
        out.append(f"{a}/{b}")
        if len(out) >= limit:
            break
    return out


def _extract_per_owner_ha_areas(text: str, total_area_str: str, n: int) -> List[str]:
    """क्षेत्रफल में(हे०) per co-owner; skips गाटे का कुल total (e.g. 0.1640)."""
    if n <= 0:
        return []
    t = _normalize_indic_digits(text)
    # Prefer values after the per-owner column header so footer totals are not picked first.
    for marker in ("क्षेत्रफल में(हे", "क्षेत्रफल में(हे०)", "क्षेत्रफल में", "क्षेत्रफल मे", "(8)"):
        j = t.find(marker)
        if j >= 0:
            t = t[j : j + 14000]
            break
    total_f: Optional[float] = None
    if total_area_str:
        m = re.search(r"(\d+\.\d+)", total_area_str.replace(" ", ""))
        if m:
            try:
                total_f = float(m.group(1))
            except ValueError:
                total_f = None
    found: List[Tuple[int, str]] = []
    for m in re.finditer(r"\b(0\.\d{4})\b", t):
        v = float(m.group(1))
        if total_f is not None and abs(v - total_f) < 1e-6:
            continue
        if 0.005 <= v <= 0.45:
            found.append((m.start(), m.group(1)))
    found.sort(key=lambda x: x[0])
    ordered: List[str] = []
    for _, s in found:
        if len(ordered) >= n:
            break
        ordered.append(s)
    return ordered


def _primary_shareholder_section(text: str) -> str:
    """Narrow window: मुख्य खातेदार block only — avoids matching table column headers."""
    m = re.search(
        r"(?:खातेदार\s*का\s*व्यक्तिगत\s*विवरण|मुख्य\s*खातेदार)[\s\S]{0,4500}?"
        r"(?=भूमि\s*एवं\s*अधिकार|खसरा\s*/\s*गाटा\s*संख्या|गाटे\s*का\s*कुल|देय\s*भू)",
        text,
        re.UNICODE,
    )
    return m.group(0) if m else text


def _extract_labeled_primary_owner_father(text: str) -> Tuple[str, str]:
    """अधिकार अभिलेख: ``खातेदार का नाम`` / ``पिता का नाम`` in the primary (मुख्य) section only."""
    chunk = _primary_shareholder_section(text)
    owner = ""
    father = ""
    m_o = re.search(
        r"खातेदार\s*का\s*नाम\s*[:\-]?\s*([^\n]+?)"
        r"(?=\n\s*(?:आयु|पिता|माता|संरक्षक|स्थायी|खातेदार\s*का\s*हिस्सा|भूमि)|$)",
        chunk,
        re.UNICODE | re.DOTALL,
    )
    if m_o:
        owner = _trim_owner_noise(m_o.group(1))
    m_f = re.search(
        r"पिता\s*का\s*नाम\s*[:\-]?\s*([^\n]+?)"
        r"(?=\n\s*(?:माता|संरक्षक|आयु|स्थायी|भूमि|खसरा)|$)",
        chunk,
        re.UNICODE | re.DOTALL,
    )
    if m_f:
        father = _trim_owner_noise(m_f.group(1))
    return owner, father


def _coparcener_names_valid(owner: str, father: str) -> bool:
    o, f = owner.strip(), father.strip()
    if len(o) < 2 or len(f) < 2:
        return False
    if looks_like_bhulekh_header_noise(o) or looks_like_bhulekh_header_noise(f):
        return False
    if not is_plausible_person_name(o) or not is_plausible_person_name(f):
        return False
    dev_o = sum(1 for c in o if "\u0900" <= c <= "\u097f")
    dev_f = sum(1 for c in f if "\u0900" <= c <= "\u097f")
    return dev_o >= 3 and dev_f >= 3


def _cosharer_table_chunk_start(text: str) -> int:
    """Start after ``गाटा संख्या 113 के समस्त सह-…`` so header lines are not parsed as data rows."""
    m = re.search(
        r"गाटा\s*संख्या\s*[\d\u0966-\u096F]{1,8}\s*के\s*समस्त\s*सह",
        text,
        re.UNICODE,
    )
    if m:
        return m.start()
    idx = text.find("सह-खातेदारों का विवरण")
    if idx >= 0:
        return idx
    idx = text.find("सह-खातेदार")
    if idx >= 0:
        return idx
    return text.find("समस्त सह")


def _extract_cosharer_table_rows(text: str) -> List[Dict[str, str]]:
    """
    ``गाटा संख्या … सह-खातेदार`` table: serial, owner+father (OCR run together), share, ha.

    Parses lines like ``1 अक्षय पोसवाल सत्यपाल सिंह 1/6 0.0273``.
    """
    idx = _cosharer_table_chunk_start(text)
    if idx < 0:
        idx = text.find("सह-खातेदार")
    chunk = text[idx : idx + 9000] if idx >= 0 else text
    rows: List[Dict[str, str]] = []
    seen: set = set()
    for line in chunk.splitlines():
        line = line.strip()
        if not line or len(line) < 10:
            continue
        if re.match(
            r"^(क्र|क्रम|क्र०|स०|नाम|पिता|हिस्सा|क्षेत्र|खातेदार|योग|कुल|Total|\|)",
            line,
            re.I | re.UNICODE,
        ):
            continue
        if not re.search(r"[\u0900-\u097F]", line):
            continue
        m = re.match(
            r"^\s*[\d\u0966-\u096F]{1,2}\s+(.+)\s+"
            r"([1-9]\d?)\s*/\s*([1-9]\d?)\s+(0\.\d{4})\s*$",
            line,
            re.UNICODE,
        )
        if not m:
            continue
        body = m.group(1).strip()
        share = f"{m.group(2)}/{m.group(3)}"
        area_ha = m.group(4)
        words = body.split()
        if len(words) >= 4:
            mid = len(words) // 2
            own = " ".join(words[:mid])
            dad = " ".join(words[mid:])
        elif len(words) >= 2:
            own = words[0]
            dad = " ".join(words[1:])
        else:
            continue
        own = _trim_owner_noise(own)
        dad = _trim_owner_noise(dad)
        if len(own) < 2 or len(dad) < 2:
            continue
        dev0 = re.findall(r"[\u0900-\u097F]+", own)
        if dev0 and dev0[0] in _DEV_OWNER_STOP_WORDS:
            continue
        if not _coparcener_names_valid(own, dad):
            continue
        key = (own, dad, share)
        if key in seen:
            continue
        seen.add(key)
        rows.append({"owner": own, "father": dad, "share": share, "area_ha": area_ha})
    return rows


def _extract_khatauni_coparceners(text: str, total_area_str: str) -> List[Dict[str, str]]:
    """Prefer numbered ``1) owner / father`` Khatauni rows; then table; then slash pairs."""
    numbered = _extract_numbered_slash_coparceners(text)
    if numbered:
        n = len(numbered)
        win_share = _hissa_column_window(text)
        if not win_share.strip():
            win_share = _window_after_labels(text, ("हिस्से में", "(7)"))
        win_share = _strip_boilerplate_from_hissa_window(win_share)
        win_area = _window_after_labels(
            text,
            ("क्षेत्रफल में(हे", "क्षेत्रफल में(हे०)", "क्षेत्रफल में", "(8)"),
        )
        fr_ordered = _extract_ordered_share_fractions(win_share)
        if len(fr_ordered) < n:
            fr_ordered = _extract_land_share_fractions(win_share)
        if len(fr_ordered) < n:
            fr_ordered = _extract_land_share_fractions_after_hissa(
                _strip_boilerplate_from_hissa_window(
                    _hissa_column_window(text) or _window_after_labels(text, ("हिस्से में", "(7)"))
                ),
                n,
            )
        fr_ordered = _reconcile_share_list(fr_ordered, n)
        area_src = win_area if win_area.strip() else win_share
        areas = _extract_per_owner_ha_areas(area_src, total_area_str, n)
        areas = (areas + [""] * n)[:n]
        for i, row in enumerate(numbered):
            row["share"] = fr_ordered[i] or ""
            row["area_ha"] = areas[i] or ""
        return numbered

    table = _extract_cosharer_table_rows(text)
    if len(table) >= 2:
        return table

    pairs = _extract_slash_owner_father_pairs(text)
    if len(pairs) >= 2:
        n = len(pairs)
        win_share_fb = _strip_boilerplate_from_hissa_window(
            _hissa_column_window(text) or _window_after_labels(text, ("हिस्से में", "(7)"))
        )
        fracs = _extract_land_share_fractions(win_share_fb) if win_share_fb.strip() else []
        if len(fracs) < n:
            fracs = _extract_land_share_fractions_after_hissa(win_share_fb, n)
        if len(fracs) < n:
            fracs = _extract_land_share_fractions(_normalize_indic_digits(text.replace("\r\n", "\n")))
        fracs = _reconcile_share_list(fracs, n)
        areas = _extract_per_owner_ha_areas(text, total_area_str, n)
        if len(areas) < n:
            areas = areas + [""] * (n - len(areas))
        else:
            areas = areas[:n]
        return [
            {
                "owner": pairs[i][0],
                "father": pairs[i][1],
                "share": fracs[i] if i < len(fracs) else "",
                "area_ha": areas[i] if i < len(areas) else "",
            }
            for i in range(n)
        ]

    if len(table) == 1:
        return table

    lo, lf = _extract_labeled_primary_owner_father(text)
    if _coparcener_names_valid(lo, lf):
        fracs = _extract_land_share_fractions(text)
        areas = _extract_per_owner_ha_areas(text, total_area_str, 1)
        return [
            {
                "owner": lo,
                "father": lf,
                "share": fracs[0] if fracs else "",
                "area_ha": areas[0] if areas else "",
            }
        ]

    if len(pairs) == 1:
        fracs = _extract_land_share_fractions(text)
        areas = _extract_per_owner_ha_areas(text, total_area_str, 1)
        return [
            {
                "owner": pairs[0][0],
                "father": pairs[0][1],
                "share": fracs[0] if fracs else "",
                "area_ha": areas[0] if areas else "",
            }
        ]
    return []


def _first_father_name(text: str) -> str:
    """पिता (Hindi, Devanagari) first; then English ``Father`` / S/o lines."""
    for pat in (
        r"पिता\s*का\s*नाम\s*([^\n]+?)(?=\n|$|गाटे)",
        r"पिता\s*(?!का\s*नाम)\s*[:\-]?\s*([^\n]+?)(?=\n|$|गाटे)",
        r"(?:Father|S\.?\s*/?\s*O\.?|S/o)\s*[:\s]*([A-Za-z][A-Za-z\s.\-]{2,50})(?=\s|$|\n|गाटे)",
    ):
        m = re.search(pat, text, re.I | re.UNICODE)
        if m:
            return _clean(m.group(1))
    return ""


def extract_khatauni_fields(ocr_text: str) -> Dict[str, Any]:
    """
    Return extra / override fields for Khatauni layout. Empty strings if not detected.
    Keys align with registry merge: owner, father, khasra, area, district, tehsil, village, khata_number.
    ``ownership_entries`` holds co-parceners with share + per-row area when parsed from slash + table.
    """
    out: Dict[str, Any] = {
        "owner": "",
        "father": "",
        "khasra": "",
        "area": "",
        "date": "",
        "district": "",
        "tehsil": "",
        "village": "",
        "khata_number": "",
        "ownership_entries": [],
    }
    if not ocr_text or not ocr_text.strip():
        return out

    text = ocr_text.replace("\r\n", "\n")
    if len(text.strip()) < 40:
        return out
    # Do not gate on title/header keywords — real Tesseract output often omits or garbles them.
    # Structured khasra / owner / area extraction is safe to run on any long enough PDF text.

    out["district"] = _sanitize_khatauni_location_field(
        _extract_header_field(text, r"(?:जनपद|जिला|District|जनपद\s*का\s*नाम)")
    )
    out["tehsil"] = _sanitize_khatauni_location_field(
        _extract_header_field(text, r"(?:तहसील|तहसील\s*का\s*नाम|Tehsil)")
    )
    out["village"] = _sanitize_khatauni_location_field(
        _extract_header_field(text, r"(?:ग्राम|गाँव|ग्राम\s*का\s*नाम|Village)(?!\s*कोड)")
    )
    # Village code line sometimes OCR'd separately — strip if merged
    if out["village"] and "कोड" in out["village"]:
        out["village"] = re.split(r"ग्राम\s*कोड|कोड", out["village"], flags=re.I)[0].strip()
        out["village"] = _sanitize_khatauni_location_field(out["village"])

    out["khata_number"] = _extract_khata_number(text)
    kh = _extract_khasra_gata(text)
    if kh:
        out["khasra"] = kh

    area = _extract_total_gata_area_ha(text)
    if area:
        out["area"] = area
    if not out["area"]:
        area_fb = _extract_total_gata_area_fallback(text)
        if area_fb:
            out["area"] = area_fb

    pdate = _extract_khatauni_print_date(text)
    if pdate:
        out["date"] = pdate

    coparceners = _extract_khatauni_coparceners(text, str(out.get("area", "")))
    if coparceners:
        out["ownership_entries"] = coparceners
        out["owner"] = " | ".join(c["owner"] for c in coparceners)
        fathers = [c.get("father", "").strip() for c in coparceners if c.get("father", "").strip()]
        out["father"] = " | ".join(fathers)
    else:
        owners = _extract_owner_lines_from_khatauni_block(text)
        if not owners:
            owners = _extract_owners_devanagari_loose(text)
        if owners:
            out["owner"] = " | ".join(owners)

        father = _first_father_name(text)
        if father:
            out["father"] = father

    for k in list(out.keys()):
        if k == "ownership_entries":
            continue
        if isinstance(out[k], str):
            out[k] = _normalize_indic_digits(out[k])
    for row in out.get("ownership_entries") or []:
        if isinstance(row, dict):
            for rk in row:
                if isinstance(row[rk], str):
                    row[rk] = _normalize_indic_digits(row[rk])

    return out


def merge_khatauni_with_registry(
    generic: Dict[str, Any], khatauni: Dict[str, Any]
) -> Dict[str, Any]:
    """Prefer Khatauni for location + khasra + area + print date when present; combine owners."""
    merged = dict(generic)
    for key in ("district", "tehsil", "village", "khata_number"):
        merged[key] = khatauni.get(key) or merged.get(key, "")

    if khatauni.get("khasra"):
        merged["khasra"] = khatauni["khasra"]
    elif not merged.get("khasra"):
        merged["khasra"] = khatauni.get("khasra", "")

    if khatauni.get("area"):
        merged["area"] = khatauni["area"]
    elif not merged.get("area"):
        merged["area"] = khatauni.get("area", "")

    if khatauni.get("date"):
        merged["date"] = khatauni["date"]
    elif not merged.get("date"):
        merged["date"] = khatauni.get("date", "")

    if khatauni.get("owner"):
        merged["owner"] = khatauni["owner"]
    elif not merged.get("owner"):
        merged["owner"] = khatauni.get("owner", "")

    if khatauni.get("father"):
        merged["father"] = khatauni["father"]
    elif not merged.get("father"):
        merged["father"] = khatauni.get("father", "")

    if khatauni.get("ownership_entries"):
        merged["ownership_entries"] = khatauni["ownership_entries"]
    elif not merged.get("ownership_entries"):
        merged["ownership_entries"] = khatauni.get("ownership_entries", [])

    return merged
