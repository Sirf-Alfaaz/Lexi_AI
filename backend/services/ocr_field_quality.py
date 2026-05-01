"""
Reject obvious OCR mistakes: Fasli years as khasra, gibberish Latin “names”, etc.
"""

from __future__ import annotations

import re
from typing import Optional

_VOWELS = frozenset("aeiouAEIOU")


def _max_consonant_run(word: str) -> int:
    m = 0
    cur = 0
    for c in word.lower():
        if c.isalpha() and c not in _VOWELS:
            cur += 1
            m = max(m, cur)
        else:
            cur = 0
    return m


def is_plausible_khasra(s: Optional[str]) -> bool:
    """
    Reject Fasli year bands (e.g. 1430-1435) and other non–plot-number patterns.
    Real khasra is usually small integers or short fractions (113, 12/3, 45-2).
    """
    if not s:
        return False
    t = s.strip().replace("–", "-").replace("—", "-")
    t = " ".join(t.split())

    # 4-digit - 4-digit: almost always Fasli / accounting year on Bhulekh headers, not khasra
    m4 = re.fullmatch(r"(\d{4})\s*-\s*(\d{4})", t.replace(" ", ""))
    if m4:
        a, b = int(m4.group(1)), int(m4.group(2))
        if 1100 <= a <= 1700 and 1100 <= b <= 1700 and abs(b - a) <= 40:
            return False

    # Fiscal / assessment year on अभिलेख: 2024-25, 2024—25 (never a plot number)
    compact = t.replace(" ", "")
    m_cal = re.fullmatch(r"(\d{4})\s*-\s*(\d{1,4})", compact.replace("—", "-").replace("–", "-"))
    if m_cal and int(m_cal.group(1)) >= 1900:
        return False

    return True


def looks_like_bhulekh_header_noise(s: Optional[str]) -> bool:
    """
    Boilerplate from अधिकार अभिलेख / headers mistaken for person names (e.g. record id line,
    ``नाबालिग खातेदारों``, ``न्यायिक``, ``UP`` / ``REV`` fragments).
    """
    if not s or not str(s).strip():
        return False
    t = str(s).strip()
    if re.search(r"(?i)\bup/rev\b|\brev/kht\b|(?:^|\s)kht/\d{4}", t):
        return True
    compact_lat = re.sub(r"[\s:.,;|]+", "", t)
    if re.fullmatch(r"[A-Z]{2,6}", compact_lat):
        return True
    for frag in (
        "अभिलेख संख्या",
        "नाबालिग खातेदारों",
        "खातेदारों का विवरण",
        "खातेदारोंकाविवरण",
        "समस्त सह-खातेदार",
        "न्यायिक",
        "न्यायालय",
        # Khatauni category row / mortgage / footer — not co-owner names
        "श्रेणी",
        "संक्रमणीय भूमिधर",
        "एसबीआई",
        "बंधक",
        "प्रबंधक का नाम",
        "आदेश का दिनांक",
        "आदेश संख्या",
        "जाति कोड",
        "डिजिटल हस्ताक्षर",
        "यूनीक कोड",
        "भू-नक्शा",
        "जोत का आधार",
        # Portal / print footer (not owners)
        "कृपया उक्त",
        "कृपया",
        "अवलोकनार्थ",
        "लोकवाणी",
        "आँकड़े मात्र",
        "way की प्रस्थिति",
    ):
        if frag in t:
            return True
    if re.search(r"(?i)disclaimer", t):
        return True
    if "संख्या" in t and re.search(r"(?i)(\bup\b|/rev/|kht)", t):
        return True
    return False


def is_plausible_person_name(s: Optional[str]) -> bool:
    """
    Drop garbage Latin OCR (e.g. misread Devanagari as random letters).
    Accepts Devanagari names or plausible English name tokens.
    """
    if not s:
        return False
    s = s.strip()
    if len(s) < 2:
        return False
    if looks_like_bhulekh_header_noise(s):
        return False

    # Devanagari: allow if reasonable length and not mostly digits/punct
    dev = re.findall(r"[\u0900-\u097F]+", s)
    if dev and sum(len(x) for x in dev) >= max(4, len(s) // 3):
        if re.search(r"[\u0900-\u097F]{2,}", s):
            return True

    # Latin-only heuristic
    latin = re.sub(r"[^A-Za-z\s.\-]", "", s)
    latin = " ".join(latin.split())
    if not latin:
        return False

    words = [w for w in latin.split() if w]
    if not words:
        return False

    # Tiny all-caps debris from bad OCR (e.g. ``RE BAe`` near stamps)
    for w in words:
        if w.isupper() and 2 <= len(w) <= 4:
            return False

    letters_only = "".join(words)
    if len(letters_only) < 4:
        return False
    if len(words) == 1 and len(words[0]) < 4:
        return False

    # Too many tiny tokens (OCR debris)
    if sum(1 for w in words if len(w) <= 1) > 2:
        return False
    if len(words) >= 4 and sum(1 for w in words if len(w) <= 2) >= 3:
        return False

    letters = "".join(words)
    vowel_ratio = sum(1 for c in letters if c.lower() in _VOWELS) / max(len(letters), 1)
    if len(letters) >= 10 and vowel_ratio < 0.12:
        return False

    for w in words:
        wl = re.sub(r"[^a-z]", "", w.lower())
        if len(wl) >= 4 and _max_consonant_run(wl) >= 5:
            return False
        # Repeated unlikely bigrams
        if re.search(r"(q|x)[^aeiou]{3,}", wl):
            return False

    # Suspicious: alternating case mid-word without spaces (scan artifact)
    if re.search(r"[a-z][A-Z]", s) and "|" not in s:
        pass  # not always wrong

    return True


def is_fasli_year_range(s: Optional[str]) -> bool:
    """Bhulekh headers often show फसली वर्ष 1430-1435 — not a calendar date."""
    if not s:
        return False
    t = s.strip().replace("–", "-").replace("—", "-")
    m = re.fullmatch(r"(\d{4})\s*-\s*(\d{4})", t.replace(" ", ""))
    if not m:
        return False
    a, b = int(m.group(1)), int(m.group(2))
    return 1100 <= a <= 1700 and 1100 <= b <= 1700 and abs(b - a) <= 40


def _plausible_multi_owner_field(v: str) -> bool:
    """Khatauni merges several names with ``|`` — validate each segment, not the whole string."""
    if not v or not str(v).strip():
        return False
    t = str(v).strip()
    if looks_like_bhulekh_header_noise(t):
        return False
    if "|" in t:
        parts = [p.strip() for p in t.split("|") if p.strip()]
        if not parts:
            return False
        return all(is_plausible_person_name(p) for p in parts)
    return is_plausible_person_name(t)


def sanitize_registry_fields(d: dict) -> dict:
    """Clear khasra / father / owner when heuristics say OCR noise."""
    out = dict(d)
    k = (out.get("khasra") or "").strip()
    if k and not is_plausible_khasra(k):
        out["khasra"] = ""

    for key in ("father", "owner"):
        v = (out.get(key) or "").strip()
        if v and (looks_like_bhulekh_header_noise(v) or not _plausible_multi_owner_field(v)):
            out[key] = ""

    oe = out.get("ownership_entries")
    if isinstance(oe, list) and oe:
        cleaned = []
        for row in oe:
            if not isinstance(row, dict):
                continue
            o = str(row.get("owner", "") or "").strip()
            f = str(row.get("father", "") or "").strip()
            if looks_like_bhulekh_header_noise(o) or looks_like_bhulekh_header_noise(f):
                continue
            if not is_plausible_person_name(o) or not is_plausible_person_name(f):
                continue
            dev_o = sum(1 for c in o if "\u0900" <= c <= "\u097f")
            dev_f = sum(1 for c in f if "\u0900" <= c <= "\u097f")
            # Short surnames (e.g. सिंह) are valid; noisy OCR can split Devanagari counts.
            if dev_o < 2 or dev_f < 2:
                continue
            if dev_o < 3 or dev_f < 3:
                if dev_o + dev_f < 8:
                    continue
            cleaned.append(row)
        out["ownership_entries"] = cleaned

    return out
