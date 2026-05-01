"""API routers."""

from .forgery_detection import router as forgery_detection_router
from .ocr_document import router as ocr_document_router

__all__ = ["ocr_document_router", "forgery_detection_router"]
