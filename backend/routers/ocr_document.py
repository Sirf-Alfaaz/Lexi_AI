"""
FastAPI routes for document upload + Tesseract OCR + structured registry field extraction.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, File, HTTPException, Query, UploadFile

from services.document_ocr_pipeline import EmptyOCRTextError, extract_registry_fields_from_document
from services.ocr_schemas import RegistryOCRResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ocr", tags=["OCR"])

MAX_UPLOAD_BYTES = 25 * 1024 * 1024


@router.post(
    "/document",
    response_model=RegistryOCRResponse,
    summary="Upload PDF or image and get structured registry fields",
)
async def ocr_document_upload(
    file: UploadFile = File(..., description="PDF or image (PNG, JPEG, TIFF, WebP, …)"),
    include_raw_text: bool = Query(
        False,
        description="If true, include full OCR text in the response (debugging).",
    ),
) -> RegistryOCRResponse:
    """
    Accept a PDF or image, run Tesseract OCR, then parse owner, father, khasra, area, date, stamp_id.

    JSON body fields: owner, father, khasra, area, date, stamp_id (optional raw_text).
    """
    filename = file.filename or "upload"
    data = await file.read()

    if not data:
        raise HTTPException(status_code=400, detail="Empty upload.")

    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"File too large. Maximum size is {MAX_UPLOAD_BYTES // (1024 * 1024)} MB.",
        )

    try:
        return extract_registry_fields_from_document(
            data, filename=filename, include_raw_text=include_raw_text
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except EmptyOCRTextError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    except Exception as e:
        logger.exception("OCR pipeline failed")
        raise HTTPException(status_code=500, detail="OCR processing failed.") from e
