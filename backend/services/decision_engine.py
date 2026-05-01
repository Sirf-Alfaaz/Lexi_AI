"""
Weighted scoring for land dispute parties using Bhulekh, registry, chain, supporting docs, forgery.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional


def _clamp(n: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, n))


def score_party(
    *,
    bhulekh_match: Optional[bool],
    registry_valid: bool,
    chain_valid: bool,
    supporting_score: float,
    forgery_flag_count: int,
) -> float:
    """
    Additive model (max ~110 before penalties; clamped to 0–100).

    - Bhulekh match: +50 (strongest when present)
    - Registry valid: +20
    - Chain valid: +15
    - Supporting docs: up to +10 (input is 0–10)
    - No forgery: +15; each flag reduces score
    """
    s = 0.0

    if bhulekh_match is True:
        s += 50.0
    elif bhulekh_match is False:
        # explicit mismatch with official extract — penalize slightly
        s -= 10.0

    if registry_valid:
        s += 20.0
    if chain_valid:
        s += 15.0

    s += _clamp(float(supporting_score), 0.0, 10.0)

    if forgery_flag_count <= 0:
        s += 15.0
    else:
        s -= min(45.0, 12.0 * forgery_flag_count)

    if bhulekh_match is None:
        # No Bhulekh data: rely more on documents — small nudge so registry/chain still matter
        s += 5.0

    return _clamp(s)


def run_decision(
    party_a: Dict[str, Any],
    party_b: Dict[str, Any],
) -> Dict[str, Any]:
    """
    ``party_*`` keys:
      - ``bhulekh_match``: bool | null
      - ``registry_valid``: bool
      - ``chain_valid``: bool
      - ``supporting_score``: number 0–10
      - ``forgery_flags``: list of strings (len used as count)
    """
    fa = len(party_a.get("forgery_flags") or [])
    fb = len(party_b.get("forgery_flags") or [])

    sa = score_party(
        bhulekh_match=party_a.get("bhulekh_match"),
        registry_valid=bool(party_a.get("registry_valid")),
        chain_valid=bool(party_a.get("chain_valid")),
        supporting_score=float(party_a.get("supporting_score") or 0),
        forgery_flag_count=fa,
    )
    sb = score_party(
        bhulekh_match=party_b.get("bhulekh_match"),
        registry_valid=bool(party_b.get("registry_valid")),
        chain_valid=bool(party_b.get("chain_valid")),
        supporting_score=float(party_b.get("supporting_score") or 0),
        forgery_flag_count=fb,
    )

    if sa > sb:
        winner = "Party A"
    elif sb > sa:
        winner = "Party B"
    else:
        winner = "Tie"

    margin = abs(sa - sb)
    confidence = _clamp(50.0 + margin * 0.45 + (10.0 if (party_a.get("bhulekh_match") or party_b.get("bhulekh_match")) else 0.0))

    reason_parts: List[str] = []
    if party_a.get("bhulekh_match") or party_b.get("bhulekh_match"):
        reason_parts.append("Bhulekh alignment considered")
    else:
        reason_parts.append("Bhulekh unavailable; document-based signals")
    if party_a.get("registry_valid") and party_b.get("registry_valid"):
        reason_parts.append("both registries plausible")
    if fa or fb:
        reason_parts.append("forgery penalties applied")
    if party_a.get("chain_valid") or party_b.get("chain_valid"):
        reason_parts.append("ownership chain")

    return {
        "partyA_score": round(sa, 1),
        "partyB_score": round(sb, 1),
        "winner": winner,
        "confidence": round(confidence, 0),
        "reason": "; ".join(reason_parts) + ".",
    }
