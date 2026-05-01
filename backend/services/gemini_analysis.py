import json
import logging
from typing import Any, Dict, Optional

import google.generativeai as genai  # type: ignore

from services.name_display import format_bilingual_name

logger = logging.getLogger(__name__)


LAND_PROMPT = """
You are a legal assistant specialized in Indian land laws and the Land Acquisition Act 2013,
with a focus on Uttar Pradesh.

The document text may be entirely or partly in Hindi (Devanagari script), English, or mixed
(e.g. UP Bhulekh / revenue extracts). Preserve owner names, village names, and labels in their
original script in the JSON string values. Do not transliterate Hindi names to English unless
the source text is already English.

Analyze the following document text and extract:

1. Owner name
2. District and village
3. Khasra or survey number
4. Land area
5. Acquisition authority
6. Compensation details
7. Possible dispute or legal concern
8. Risk level (low, medium, high)
9. Geographic coordinates (latitude and longitude) if they are explicitly written anywhere in the document text.

Return the response in STRICT, VALID JSON format (UTF-8, no comments) with the keys:
{{
  "owner_name": string | null,
  "village": string | null,
  "district": string | null,
  "khasra_number": string | null,
  "land_area": string | null,
  "acquisition_authority": string | null,
  "compensation_amount": string | null,
  "possible_legal_issues": string | null,
  "dispute_risk_level": "low" | "medium" | "high",
  "latitude": number | null,
  "longitude": number | null
}}

IMPORTANT:
- If land area, khasra number, or coordinates are not clearly given in the text, set them to null. Do NOT guess or fabricate values.
- If coordinates are present multiple times, prefer the most precise pair that clearly refers to the land in question.
- Hindi field labels may include e.g. काश्तकार, खसरा, रकबा, भूमि स्वामी, ग्राम, ज़िला, तहसील — map them to the same JSON keys (owner_name, khasra_number, land_area, village, district, etc.) using the values that follow those labels.
- Numeric data may appear as Arabic digits (0-9) or Devanagari digits (०-९); copy them as plain digit strings in JSON when extracting areas, khasra, or dates.

Document text:
\"\"\"{document_text}\"\"\"
"""


def analyze_land_document(document_text: str, model_name: str = "gemini-2.5-flash") -> Dict[str, Any]:
    """
    Call Gemini to analyze land-related document text and return structured data.
    """
    if not document_text.strip():
        raise ValueError("Document text is empty")

    model = genai.GenerativeModel(model_name)  # type: ignore[attr-defined]

    prompt = LAND_PROMPT.format(document_text=document_text[:20000])
    logger.info("Sending land document for Gemini analysis (length=%d)", len(document_text))

    response = model.generate_content(prompt)
    raw_text: Optional[str] = getattr(response, "text", None)
    if not raw_text:
        raw_text = str(response)

    raw_text = raw_text.strip()

    # Try to parse JSON robustly
    try:
        # Sometimes model wraps JSON in code fences – strip them
        if raw_text.startswith("```"):
            raw_text = raw_text.strip("`")
            # Remove optional language hint like json\n
            if raw_text.lower().startswith("json"):
                raw_text = raw_text[4:]
        data = json.loads(raw_text)
    except Exception as parse_err:
        logger.warning("Failed to parse Gemini land JSON strictly: %s; returning fallback", parse_err)
        # Fallback: wrap whole text
        data = {
            "owner_name": None,
            "village": None,
            "district": None,
            "khasra_number": None,
            "land_area": None,
            "acquisition_authority": None,
            "compensation_amount": None,
            "possible_legal_issues": raw_text,
            "dispute_risk_level": "medium",
            "latitude": None,
            "longitude": None,
        }

    # Normalize keys and provide safe defaults
    normalized: Dict[str, Any] = {
        "owner_name": data.get("owner_name") or data.get("owner") or None,
        "village": data.get("village") or None,
        "district": data.get("district") or None,
        "khasra_number": data.get("khasra_number") or data.get("survey_number") or None,
        "land_area": data.get("land_area") or data.get("area") or None,
        "acquisition_authority": data.get("acquisition_authority") or data.get("authority") or None,
        "compensation_amount": data.get("compensation_amount") or data.get("compensation_details") or None,
        "possible_legal_issues": data.get("possible_legal_issues") or data.get("possible_dispute") or None,
        "dispute_risk_level": (data.get("dispute_risk_level") or "medium").lower(),
        "latitude": data.get("latitude"),
        "longitude": data.get("longitude"),
    }

    risk = normalized["dispute_risk_level"]
    if risk not in {"low", "medium", "high"}:
        normalized["dispute_risk_level"] = "medium"

    on = normalized.get("owner_name")
    normalized["owner_display"] = (
        format_bilingual_name(str(on).strip()) if on and str(on).strip() else None
    )
    vn = normalized.get("village")
    normalized["village_display"] = (
        format_bilingual_name(str(vn).strip()) if vn and str(vn).strip() else None
    )

    return normalized

