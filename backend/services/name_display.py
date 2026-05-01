"""
Format Hindi / Devanagari names for UI: romanized English plus original script in parentheses.

Uses ITRANS romanization for the Latin part (readable for UP Bhulekh–style extracts).
"""

from __future__ import annotations

import re

from indic_transliteration.sanscript import DEVANAGARI, ITRANS, transliterate  # type: ignore

_DEV_RE = re.compile(r"[\u0900-\u097F][\u0900-\u097F\s]*")


def format_bilingual_name(text: str) -> str:
    """
    If `text` contains Devanagari, return ``Romanized (original)``.
    Otherwise return `text` unchanged (already Latin / numeric).
    """
    s = (text or "").strip()
    if not s:
        return ""
    if not re.search(r"[\u0900-\u097F]", s):
        return s
    try:
        roman = _romanize_mixed(s)
    except Exception:
        return s
    pretty = " ".join(p.title() for p in roman.split())
    return f"{pretty} ({s})"


def _romanize_mixed(s: str) -> str:
    """Replace each Devanagari span with ITRANS romanization; keep Latin segments."""
    parts: list[str] = []
    last = 0
    for m in _DEV_RE.finditer(s):
        parts.append(s[last : m.start()])
        seg = m.group().strip()
        if seg:
            t = transliterate(seg, DEVANAGARI, ITRANS).replace("_", " ")
            parts.append(t)
        last = m.end()
    parts.append(s[last:])
    return " ".join("".join(parts).split())
