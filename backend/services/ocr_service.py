"""
OCR utilities: PDF and raster images → text.

UP Bhulekh PDFs are usually **digital** (embedded text). We read that first with PyMuPDF,
then fall back to **Tesseract** on rasterized pages for scans or when the text layer is thin.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
from io import BytesIO
from pathlib import Path
from typing import List, Tuple

import fitz  # type: ignore  # PyMuPDF
from pdf2image import convert_from_bytes  # type: ignore
from PIL import Image  # type: ignore
import pytesseract  # type: ignore

logger = logging.getLogger(__name__)


def _load_backend_env_once() -> None:
    """Load backend/.env so TESSERACT_CMD etc. apply even if this module is imported without main.py."""
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    env_file = Path(__file__).resolve().parent.parent / ".env"
    if env_file.is_file():
        load_dotenv(env_file)


_load_backend_env_once()


def _resolve_tesseract_executable() -> str | None:
    """
    Locate tesseract: TESSERACT_CMD if valid, then Windows default path, then PATH.
    If TESSERACT_CMD is set but invalid, we ignore it so a working default/PATH install still works.
    """
    env_cmd = (os.getenv("TESSERACT_CMD") or "").strip()
    if env_cmd and os.path.isfile(env_cmd):
        return env_cmd

    if os.name == "nt":
        default_path = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
        if os.path.isfile(default_path):
            return default_path
        for name in ("tesseract.exe", "tesseract"):
            w = shutil.which(name)
            if w:
                return w
        return None

    if env_cmd:
        return None
    return shutil.which("tesseract")


def _configure_tesseract() -> None:
    path = _resolve_tesseract_executable()
    if path:
        pytesseract.pytesseract.tesseract_cmd = path


def get_ocr_environment_diagnostics() -> str:
    """
    Short hints for API errors when PDF/image extraction returns empty (local dev / Windows setup).
    """
    parts: List[str] = []
    path = _resolve_tesseract_executable()
    if not path:
        parts.append(
            "Tesseract is not installed or not on PATH. Install from "
            "https://github.com/UB-Mannheim/tesseract/wiki (include Hindi data), "
            "or set TESSERACT_CMD to the full path of tesseract.exe."
        )
        return " ".join(parts)

    try:
        pytesseract.pytesseract.tesseract_cmd = path
        pytesseract.get_tesseract_version()
    except Exception as exc:
        parts.append(f"Tesseract at {path!r} failed to run: {exc}")
        return " ".join(parts)

    lang_primary = _get_tesseract_lang()
    if "hin" in lang_primary.lower():
        try:
            proc = subprocess.run(
                [path, "--list-langs"],
                capture_output=True,
                text=True,
                timeout=15,
                check=False,
            )
            listed = (proc.stdout or "") + (proc.stderr or "")
            langs = {ln.strip() for ln in listed.splitlines() if ln.strip() and not ln.startswith("List of ")}
            if proc.returncode == 0 and "hin" not in langs and "hin" in lang_primary.lower():
                parts.append(
                    "Hindi (hin) is not installed for Tesseract. Add it in the installer "
                    "(Additional language data) or set TESSERACT_LANG=eng for English-only scans."
                )
        except Exception as exc:
            parts.append(f"Could not verify Tesseract language packs: {exc}")

    if not _get_poppler_path() and os.name == "nt":
        parts.append(
            "Optional: install Poppler (see POPPLER_PATH) if PyMuPDF raster OCR mishandles your PDF."
        )

    return " ".join(p for p in parts if p)


def _get_tesseract_lang() -> str:
    """
    Default `hin+eng` (Tesseract **hin** traineddata + **eng**) for Devanagari land records.

    Override with ``TESSERACT_LANG`` (e.g. ``hin``, ``hin+eng``, ``hin+eng+script/Devanagari``).

    **Windows:** Tesseract installer → Additional language data → Hindi; or place ``hin.traineddata``
    in the ``tessdata`` folder next to ``tesseract.exe``. Verify: ``tesseract --list-langs`` includes ``hin``.

    **Linux/Docker:** package ``tesseract-ocr-hin`` (see ``backend/Dockerfile``).
    """
    return os.getenv("TESSERACT_LANG", "hin+eng").strip() or "hin+eng"


def _lang_fallback_chain(primary: str) -> List[str]:
    """
    Try compound langs first, then single components, then English — so missing ``hin`` still yields text.

    Order for ``hin+eng``: ``hin+eng`` → ``hin`` → ``eng``.
    """
    p = (primary or "").strip() or "hin+eng"
    out: List[str] = []
    for x in (p, *[s.strip() for s in p.split("+") if s.strip()], "eng"):
        if x and x not in out:
            out.append(x)
    return out


def _get_poppler_path() -> str | None:
    env_path = os.getenv("POPPLER_PATH")
    if env_path:
        return env_path

    default_windows_path = r"C:\poppler\Library\bin"
    if os.name == "nt" and os.path.isdir(default_windows_path):
        return default_windows_path

    return None


def _truthy_env(name: str) -> bool:
    v = os.getenv(name, "").strip().lower()
    return v in ("1", "true", "yes", "on")


def _normalize_pil_image(image: Image.Image) -> Image.Image:
    if image.mode in ("RGB", "L"):
        return image
    return image.convert("RGB")


def _preprocess_for_ocr(image: Image.Image) -> Image.Image:
    """
    Boost contrast / sharpness for faint scans, watermarked Bhulekh PDFs, and small text.
    Disable with OCR_DISABLE_PREPROCESS=1.
    """
    if _truthy_env("OCR_DISABLE_PREPROCESS"):
        return _normalize_pil_image(image)
    try:
        from PIL import ImageEnhance  # type: ignore
    except ImportError:
        return _normalize_pil_image(image)

    im = _normalize_pil_image(image)
    gray = im.convert("L")
    # Gentler than heavy sharpen — reduces misread Latin next to Devanagari
    gray = ImageEnhance.Contrast(gray).enhance(1.14)
    gray = ImageEnhance.Sharpness(gray).enhance(1.03)
    return gray.convert("RGB")


def _get_pdf_render_dpi() -> int:
    try:
        return max(200, min(600, int(os.getenv("OCR_PDF_DPI", "400"))))
    except ValueError:
        return 400


def _get_tesseract_ocr_config() -> str:
    """Default: full auto segmentation — better for multi-column Khatauni than single block."""
    return os.getenv("TESSERACT_OCR_CONFIG", "--oem 3 --psm 3").strip()


def _get_ocr_passes() -> List[str]:
    """Multiple OCR passes improve table-cell capture on scanned Khatauni PDFs."""
    raw = os.getenv("TESSERACT_OCR_PASSES", "3,6,11").strip()
    passes: List[str] = []
    for token in raw.split(","):
        t = token.strip()
        if not t:
            continue
        if t.startswith("--"):
            passes.append(t)
        elif t.isdigit():
            passes.append(f"--oem 3 --psm {t}")
    if not passes:
        passes = ["--oem 3 --psm 3"]
    out: List[str] = []
    for p in passes:
        if p not in out:
            out.append(p)
    return out


def _merge_ocr_texts(texts: List[str]) -> str:
    """
    Keep each Tesseract pass as a contiguous block.

    De-duplicating lines across passes destroyed row/column order on Khatauni tables.
    """
    blocks = [t.strip() for t in texts if t and str(t).strip()]
    if not blocks:
        return ""
    if len(blocks) == 1:
        return blocks[0]
    return "\n\n--- ocr-pass ---\n\n".join(blocks)


def _ocr_page(im: Image.Image, lang: str) -> str:
    """Run multi-pass Tesseract with Hindi+English (see ``_get_tesseract_lang``) and merge."""
    _configure_tesseract()
    texts: List[str] = []
    chain = _lang_fallback_chain(lang)

    for cfg in _get_ocr_passes():
        chunk = ""
        for try_lang in chain:
            try:
                t = pytesseract.image_to_string(im, lang=try_lang, config=cfg) or ""
                if t.strip():
                    chunk = t
                    break
            except Exception as exc:
                err = str(exc).lower()
                if "hin" in try_lang.lower() and (
                    "traineddata" in err or "could not load" in err or "lang" in err
                ):
                    logger.warning(
                        "Tesseract may be missing Hindi traineddata (lang=%r). "
                        "Install tesseract-ocr-hin or add hin.traineddata to tessdata. Error: %s",
                        try_lang,
                        exc,
                    )
                else:
                    logger.warning("Tesseract OCR failed for lang=%r cfg=%r: %s", try_lang, cfg, exc)
        if chunk:
            texts.append(chunk)
    if texts:
        return _merge_ocr_texts(texts)

    return ""


def _images_to_text(images: List[Image.Image], lang: str, page_labels: bool = True) -> str:
    parts: List[str] = []
    for page_idx, image in enumerate(images):
        im = _preprocess_for_ocr(_normalize_pil_image(image))
        text = _ocr_page(im, lang)
        if not text or not text.strip():
            continue
        if page_labels and len(images) > 1:
            parts.append(f"\n\n--- Page {page_idx + 1} ---\n{text}")
        else:
            parts.append(text)
    return "\n".join(parts).strip()


_KHATAUNI_TEXT_MARKERS = (
    "खतौनी",
    "खसरा",
    "गाटा",
    "खातेदार",
    "भूलेख",
    "अभिलेख",
    "उद्धरण",
    "क्षेत्रफल",
    "हेक्टेयर",
    "हैक्टेयर",
)


def _extract_pdf_text_layer_fitz(pdf_bytes: bytes) -> str:
    """Pull embedded PDF text (vector / born-digital Bhulekh saves)."""
    if not pdf_bytes:
        return ""
    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    except Exception as exc:
        logger.warning("PyMuPDF could not open PDF: %s", exc)
        return ""
    try:
        parts: List[str] = []
        for i in range(len(doc)):
            try:
                parts.append(doc.load_page(i).get_text())
            except Exception:
                continue
        return "\n".join(parts)
    finally:
        doc.close()


def _pdf_text_layer_looks_usable(text: str) -> bool:
    """True if the embedded layer has enough content to skip raster OCR."""
    t = (text or "").strip()
    if len(t) < 18:
        return False
    if any(m in t for m in _KHATAUNI_TEXT_MARKERS):
        return True
    dev = sum(1 for c in t if "\u0900" <= c <= "\u097f")
    if dev >= 12:
        return True
    letters = sum(1 for c in t if c.isalpha())
    if len(t) >= 45 and letters >= 20:
        return True
    return len(t) >= 350


def _raster_pdf_tesseract(pdf_bytes: bytes) -> str:
    """pdf2image + Tesseract; requires Poppler (``pdftoppm``) on PATH or ``POPPLER_PATH``."""
    if not pdf_bytes:
        return ""
    lang = _get_tesseract_lang()
    dpi = _get_pdf_render_dpi()
    poppler_path = _get_poppler_path()
    try:
        if poppler_path:
            images: List[Image.Image] = convert_from_bytes(
                pdf_bytes, dpi=dpi, poppler_path=poppler_path
            )
        else:
            images = convert_from_bytes(pdf_bytes, dpi=dpi)
    except Exception as exc:
        logger.warning(
            "pdf2image failed — install Poppler (Windows: %s or set POPPLER_PATH). %s",
            r"C:\poppler\Library\bin",
            exc,
        )
        return ""
    if not images:
        logger.warning("pdf2image returned zero pages (check Poppler and PDF).")
        return ""
    return _images_to_text(images, lang=lang, page_labels=True)


def _raster_pdf_fitz_pixmap_ocr(pdf_bytes: bytes) -> str:
    """
    Render pages with PyMuPDF and run Tesseract — **no Poppler** required.

    Use when ``pdf2image``/Poppler is unavailable (typical Windows setups) but the PDF
    is image-based or the text layer is empty.
    """
    if not pdf_bytes:
        return ""
    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    except Exception as exc:
        logger.warning("PyMuPDF could not open PDF for raster OCR: %s", exc)
        return ""
    lang = _get_tesseract_lang()
    dpi = _get_pdf_render_dpi()
    zoom = max(1.0, dpi / 72.0)
    mat = fitz.Matrix(zoom, zoom)
    pieces: List[str] = []
    try:
        n = len(doc)
        for i in range(n):
            try:
                page = doc.load_page(i)
                pix = page.get_pixmap(matrix=mat, alpha=False)
                img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
            except Exception as exc:
                logger.warning("PyMuPDF render page %s failed: %s", i + 1, exc)
                continue
            txt = _ocr_page(img, lang)
            if not (txt or "").strip():
                continue
            if n > 1:
                pieces.append(f"\n\n--- Page {i + 1} ---\n{txt.strip()}")
            else:
                pieces.append(txt.strip())
    finally:
        doc.close()
    out = "\n".join(pieces).strip()
    if out:
        logger.info("Extracted PDF text via PyMuPDF raster + Tesseract (%d page(s))", n)
    return out


def extract_text_from_pdf_bytes(pdf_bytes: bytes) -> str:
    """
    Prefer embedded text (PyMuPDF); fall back to Tesseract on rendered pages for scans.

    Many Bhulekh downloads are digital-backed — Tesseract alone can yield nothing if
    Poppler is missing or raster output is blank, while the text layer is complete.
    """
    if not pdf_bytes:
        return ""

    layer = _extract_pdf_text_layer_fitz(pdf_bytes).strip()
    if _pdf_text_layer_looks_usable(layer):
        return layer

    ocr = _raster_pdf_tesseract(pdf_bytes).strip()
    if ocr:
        return ocr

    ocr_fitz = _raster_pdf_fitz_pixmap_ocr(pdf_bytes).strip()
    if ocr_fitz:
        return ocr_fitz

    if layer:
        return layer

    logger.warning(
        "PDF produced no usable text: empty or missing text layer, pdf2image failed, "
        "and PyMuPDF+Tesseract raster OCR returned nothing. Check TESSERACT_CMD / PATH, "
        "Hindi traineddata (hin), and that the PDF is not corrupt or password-locked."
    )
    return ""


def extract_text_from_image_bytes(image_bytes: bytes) -> str:
    """Run OCR on a single PNG/JPEG/TIFF/WebP (or other PIL-supported) image."""
    if not image_bytes:
        return ""

    lang = _get_tesseract_lang()
    image = Image.open(BytesIO(image_bytes))
    return _images_to_text([image], lang=lang, page_labels=False)


# Extensions we accept for uploads
PDF_EXTENSIONS = frozenset({".pdf"})
IMAGE_EXTENSIONS = frozenset({".png", ".jpg", ".jpeg", ".tif", ".tiff", ".webp", ".bmp", ".gif"})


def _guess_kind(filename: str, content: bytes) -> Tuple[str, str]:
    """
    Returns (kind, normalized_extension) where kind is 'pdf' or 'image'.
    """
    name = (filename or "").lower().strip()
    ext = ""
    if "." in name:
        ext = name[name.rfind(".") :]

    if ext in PDF_EXTENSIONS:
        return "pdf", ext
    if ext in IMAGE_EXTENSIONS:
        return "image", ext

    # Magic bytes fallback
    if content.startswith(b"%PDF"):
        return "pdf", ".pdf"
    if len(content) >= 2 and content[:2] == b"\xff\xd8":
        return "image", ".jpg"
    if len(content) >= 8 and content[:8] == b"\x89PNG\r\n\x1a\n":
        return "image", ".png"
    if len(content) >= 6 and content[:6] in (b"GIF87a", b"GIF89a"):
        return "image", ".gif"

    raise ValueError(
        "Unsupported or unknown file type. Use PDF or a common image format (PNG, JPEG, TIFF, WebP)."
    )


def extract_text_from_document_bytes(content: bytes, filename: str = "") -> str:
    """
    Unified entry: PDF or image bytes → full OCR text.

    Parameters
    ----------
    content : bytes
        Raw file bytes.
    filename : str
        Original name; used for type detection (extension).
    """
    if not content:
        return ""

    kind, _ext = _guess_kind(filename, content)

    if kind == "pdf":
        return extract_text_from_pdf_bytes(content)
    return extract_text_from_image_bytes(content)
