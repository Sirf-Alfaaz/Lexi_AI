"""
High-level pipeline: document bytes → OCR text → structured registry fields.

Use from FastAPI routes, batch jobs, or tests without duplicating logic.
"""

from __future__ import annotations

from services.name_display import format_bilingual_name
from services.ocr_schemas import OwnershipEntry, RegistryOCRResponse
from services.ocr_service import extract_text_from_document_bytes, get_ocr_environment_diagnostics
from services.registry_field_parser import parse_registry_fields


class EmptyOCRTextError(Exception):
    """Tesseract produced no usable text (blank scan, wrong file, etc.)."""


def extract_registry_fields_from_document(
    content: bytes,
    filename: str = "",
    *,
    include_raw_text: bool = False,
) -> RegistryOCRResponse:
    """
    Run OCR on a PDF or image and map text to registry-style fields.

    Raises
    ------
    ValueError
        If file type is unsupported (from ``extract_text_from_document_bytes``).
    EmptyOCRTextError
        If OCR returns no non-whitespace text.
    """
    raw_text = extract_text_from_document_bytes(content, filename=filename)
    if not raw_text.strip():
        hint = get_ocr_environment_diagnostics()
        base = (
            "No text could be extracted from this PDF. The backend tries (1) embedded text, "
            "(2) Poppler+Tesseract, (3) PyMuPDF render+Tesseract without Poppler. "
            "Ensure Tesseract is on PATH or set TESSERACT_CMD, install the Hindi (hin) language pack, "
            "and try OCR_PDF_DPI=400. For password-protected or corrupt PDFs, unlock or re-export the file."
        )
        raise EmptyOCRTextError(f"{base} {hint}".strip())

    fields = parse_registry_fields(raw_text)
    owner = fields.get("owner", "")
    father = fields.get("father", "")
    raw_entries = fields.get("ownership_entries") or []
    ownership_entries: list[OwnershipEntry] = []
    for item in raw_entries:
        if isinstance(item, dict):
            ownership_entries.append(
                OwnershipEntry(
                    owner=str(item.get("owner", "") or ""),
                    father=str(item.get("father", "") or ""),
                    share=str(item.get("share", "") or ""),
                    area_ha=str(item.get("area_ha", "") or ""),
                )
            )
    return RegistryOCRResponse(
        owner=owner,
        owner_display=format_bilingual_name(owner) if owner else "",
        father=father,
        father_display=format_bilingual_name(father) if father else "",
        khasra=fields.get("khasra", ""),
        area=fields.get("area", ""),
        district=fields.get("district", ""),
        tehsil=fields.get("tehsil", ""),
        village=fields.get("village", ""),
        khata_number=fields.get("khata_number", ""),
        ownership_entries=ownership_entries,
        date=fields.get("date", ""),
        stamp_id=fields.get("stamp_id", ""),
        raw_text=raw_text if include_raw_text else None,
    )
