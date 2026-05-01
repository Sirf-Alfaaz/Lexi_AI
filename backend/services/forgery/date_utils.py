"""Flexible date parsing for registry-style strings."""

from __future__ import annotations

import re
from datetime import date, datetime
from typing import Optional, Tuple


def parse_flexible_date(value: str) -> Optional[date]:
    """
    Parse common Indian registry date formats. Returns None if parsing fails.
    """
    if not value or not value.strip():
        return None

    s = value.strip()
    # DD/MM/YYYY, DD-MM-YYYY, DD.MM.YYYY
    m = re.match(r"^(\d{1,2})[/.\-](\d{1,2})[/.\-](\d{2,4})$", s)
    if m:
        d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if y < 100:
            y += 2000 if y < 50 else 1900
        try:
            return date(y, mo, d)
        except ValueError:
            return None

    # DD Mon YYYY
    m2 = re.match(
        r"^(\d{1,2})\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+(\d{4})$",
        s,
        re.I,
    )
    if m2:
        months = {
            "jan": 1,
            "feb": 2,
            "mar": 3,
            "apr": 4,
            "may": 5,
            "jun": 6,
            "jul": 7,
            "aug": 8,
            "sep": 9,
            "oct": 10,
            "nov": 11,
            "dec": 12,
        }
        mo = months[m2.group(2).lower()[:3]]
        try:
            return date(int(m2.group(3)), mo, int(m2.group(1)))
        except ValueError:
            return None

    # ISO YYYY-MM-DD
    m3 = re.match(r"^(\d{4})-(\d{2})-(\d{2})$", s)
    if m3:
        try:
            return date(int(m3.group(1)), int(m3.group(2)), int(m3.group(3)))
        except ValueError:
            return None

    return None


def compare_dates_doc_vs_bhulekh(
    doc_date: Optional[date],
    bhulekh_mutation: Optional[date],
) -> Tuple[bool, str]:
    """
    If both present, flag inconsistent timeline when document date is wildly before mutation
    or after last_updated in impossible ways (heuristic).
    """
    if not doc_date or not bhulekh_mutation:
        return False, ""
    # Document registration logically not years before cadastral mutation in typical flow — heuristic
    if doc_date < bhulekh_mutation:
        delta = (bhulekh_mutation - doc_date).days
        if delta > 365 * 2:
            return True, (
                f"Document date ({doc_date.isoformat()}) is more than two years before "
                f"Bhulekh mutation reference ({bhulekh_mutation.isoformat()}), which may indicate an inconsistent timeline."
            )
    return False, ""
