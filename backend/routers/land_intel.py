"""
Land intelligence APIs: UP Bhulekh scraper, ownership chain, supporting docs, decision engine.
"""

from __future__ import annotations

import asyncio
import threading
from uuid import uuid4
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from services.bhulekh import (
    BhulekhCaptchaError,
    BhulekhNavigationError,
    BhulekhNotFoundError,
    BhulekhTimeoutError,
    UPBhulekhScraper,
)
import httpx
from services.document_ocr_pipeline import extract_registry_fields_from_document
from services.bhulekh.location_store import default_location_store
from services.bhulekh.record_store import default_record_store
from services.decision_engine import run_decision
from services.ownership_chain import analyze_ownership_chain
from services.supporting_documents import analyze_supporting_documents
router = APIRouter(prefix="/land-intel", tags=["Land intelligence"])

_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="bhulekh")
_location_cache_build_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="bhulekh-cache-build")

_build_jobs: Dict[str, Dict[str, Any]] = {}
_build_jobs_lock = threading.Lock()
_current_build_running = False


def _parsed_owner_fallback(parsed: Dict[str, Any]) -> str:
    owner = str(parsed.get("owner") or "").strip()
    if owner:
        return owner
    entries = parsed.get("ownership_entries")
    if isinstance(entries, list):
        names: List[str] = []
        for row in entries:
            if not isinstance(row, dict):
                continue
            n = str(row.get("owner") or "").strip()
            if n and n not in names:
                names.append(n)
        if names:
            return " | ".join(names)
    return ""


def _compose_verify_result(raw: Dict[str, Any], parsed: Optional[Dict[str, Any]]) -> Dict[str, str]:
    """
    Prefer official PDF parsed fields whenever available.
    Fallback to scraper HTML extraction (`raw`) when parsed values are missing.
    """
    parsed_owner = _parsed_owner_fallback(parsed or {}) if parsed else ""
    parsed_khasra = str((parsed or {}).get("khasra") or "").strip() if parsed else ""
    parsed_area = str((parsed or {}).get("area") or "").strip() if parsed else ""

    owner = parsed_owner or str(raw.get("owner", ""))
    khasra = parsed_khasra or str(raw.get("khasra", ""))
    area = parsed_area or str(raw.get("area", ""))
    if _looks_like_garbage_value(owner):
        owner = ""
    if _looks_like_garbage_value(area):
        area = ""
    if _looks_like_garbage_value(khasra):
        khasra = ""

    return {
        "owner": owner,
        "khasra": khasra,
        "area": area,
        "search_mode": str(raw.get("search_mode", "")),
    }


def _looks_like_garbage_value(v: str) -> bool:
    s = (v or "").strip().lower()
    if not s:
        return False
    # CSS grid/template fragments observed in wrong Bhulekh extraction.
    if "top-start" in s or "center-start" in s or "bottom-start" in s:
        return True
    if "center-end" in s or "bottom-center" in s:
        return True
    if "class=" in s or "style=" in s:
        return True
    if "--bs-" in s or "form-control" in s or "ng-untouched" in s:
        return True
    if "white-space:nowrap" in s:
        return True
    # Clearly not owner/area text
    if s.count('"') >= 2 and ("top" in s or "center" in s):
        return True
    return False


def _sanitize_lookup_payload(raw: Dict[str, Any]) -> Dict[str, str]:
    owner = str(raw.get("owner", ""))
    khasra = str(raw.get("khasra", ""))
    area = str(raw.get("area", ""))
    if _looks_like_garbage_value(owner):
        owner = ""
    if _looks_like_garbage_value(area):
        area = ""
    return {
        "owner": owner,
        "khasra": khasra,
        "area": area,
        "search_mode": str(raw.get("search_mode", "")),
        "pdf_url": str(raw.get("pdf_url", "") or "").strip(),
    }


class BhulekhFetchBody(BaseModel):
    district: str
    tehsil: Optional[str] = ""
    village: str
    khasra: Optional[str] = ""
    owner_name: Optional[str] = ""
    fasli_year: Optional[str] = ""
    force_refresh: Optional[bool] = False


class BhulekhBuildCacheBody(BaseModel):
    force: bool = False
    pace_sec: float = 0.25


class TransactionModel(BaseModel):
    seller: str
    buyer: str
    year: int


class OwnershipChainBody(BaseModel):
    transactions: List[TransactionModel]


class SupportingDocItem(BaseModel):
    type: str = Field(..., description="electricity | house_tax | water")
    text: str = Field(..., description="OCR or pasted bill text")


class SupportingDocsBody(BaseModel):
    documents: List[SupportingDocItem]
    claimed_owner: str
    claimed_land_address: str = ""


class PartySignals(BaseModel):
    bhulekh_match: Optional[bool] = Field(
        None, description="True if official Bhulekh owner matches this party's claim"
    )
    registry_valid: bool = False
    chain_valid: bool = False
    supporting_score: float = Field(0.0, ge=0.0, le=10.0)
    forgery_flags: List[str] = Field(default_factory=list)


class DecisionBody(BaseModel):
    party_a: PartySignals
    party_b: PartySignals


@router.post(
    "/bhulekh/fetch",
    summary="Fetch khasra extract fields from UP Bhulekh (Selenium)",
    response_model=Dict[str, str],
)
async def bhulekh_fetch(body: BhulekhFetchBody) -> Dict[str, str]:
    scraper = UPBhulekhScraper()
    store = default_record_store()
    lookup_key = store.make_key(
        district=body.district,
        tehsil=body.tehsil,
        village=body.village,
        khasra=body.khasra or "",
        owner_name=body.owner_name or "",
        fasli_year=body.fasli_year or "",
    )
    loop = asyncio.get_event_loop()
    try:
        def _fetch_or_cached() -> Dict[str, Any]:
            cached = store.get_entry(lookup_key)
            if cached and isinstance(cached.get("lookup"), dict):
                return cached["lookup"]

            raw = scraper.fetch_record(
                district=body.district,
                tehsil=body.tehsil,
                village=body.village,
                khasra=body.khasra,
                owner_name=body.owner_name,
                fasli_year=body.fasli_year,
            )
            lookup_payload = {
                "owner": str(raw.get("owner", "")),
                "khasra": str(raw.get("khasra", "")),
                "area": str(raw.get("area", "")),
                "search_mode": str(raw.get("search_mode", "")),
                "pdf_url": str(raw.get("pdf_url", "") or "").strip(),
            }
            store.upsert_lookup(lookup_key, lookup=lookup_payload)
            return lookup_payload

        lookup = await loop.run_in_executor(_executor, _fetch_or_cached)
    except BhulekhNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except BhulekhTimeoutError as e:
        raise HTTPException(status_code=504, detail=str(e)) from e
    except BhulekhCaptchaError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    except BhulekhNavigationError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e

    return {
        "owner": str(lookup.get("owner", "")),
        "khasra": str(lookup.get("khasra", "")),
        "area": str(lookup.get("area", "")),
        "search_mode": str(lookup.get("search_mode", "")),
    }


@router.get("/bhulekh/options/districts", summary="List Bhulekh districts (जनपद)")
async def bhulekh_districts() -> Dict[str, Any]:
    store = default_location_store()
    # Build cache lazily on first use (so we don't scrape every time).
    loop = asyncio.get_event_loop()
    try:
        districts = await loop.run_in_executor(
            _executor, lambda: store.ensure_districts_cached()
        )
    except BhulekhNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except BhulekhTimeoutError as e:
        raise HTTPException(status_code=504, detail=str(e)) from e
    except BhulekhCaptchaError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    except BhulekhNavigationError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
    if not districts:
        raise HTTPException(
            status_code=503,
            detail=(
                "Bhulekh location cache is empty. Populate backend/data/bhulekh_locations.up.json "
                "(district → tehsil → villages)."
            ),
        )
    return {"districts": districts}


@router.get("/bhulekh/options/tehsils", summary="List tehsils for a district")
async def bhulekh_tehsils(district: str) -> Dict[str, Any]:
    store = default_location_store()
    loop = asyncio.get_event_loop()
    try:
        tehsils = await loop.run_in_executor(
            _executor, lambda: store.ensure_tehsils_cached(district=district)
        )
    except BhulekhNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except BhulekhTimeoutError as e:
        raise HTTPException(status_code=504, detail=str(e)) from e
    except BhulekhCaptchaError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    except BhulekhNavigationError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
    return {"tehsils": tehsils}


@router.get("/bhulekh/options/villages", summary="List villages for district+tehsil")
async def bhulekh_villages(district: str, tehsil: str) -> Dict[str, Any]:
    store = default_location_store()
    loop = asyncio.get_event_loop()
    try:
        villages = await loop.run_in_executor(
            _executor,
            lambda: store.ensure_villages_cached(district=district, tehsil=tehsil),
        )
    except BhulekhNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except BhulekhTimeoutError as e:
        raise HTTPException(status_code=504, detail=str(e)) from e
    except BhulekhCaptchaError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    except BhulekhNavigationError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
    return {"villages": villages}


@router.post(
    "/bhulekh/options/build-cache",
    summary="Build full Bhulekh dropdown cache (district → tehsil → villages)",
    status_code=202,
)
async def bhulekh_build_cache(body: BhulekhBuildCacheBody) -> Dict[str, Any]:
    """
    Starts a long-running cache build in background.

    It resumes from existing `backend/data/bhulekh_locations.up.json` and only fills missing
    tehsil/village entries (unless `force=true`).
    """
    global _current_build_running

    with _build_jobs_lock:
        if _current_build_running:
            # Return currently running job (single builder at a time).
            for job_id, job in _build_jobs.items():
                if job.get("status") == "running":
                    return {"status": "already_running", "job_id": job_id}

        job_id = str(uuid4())
        _current_build_running = True
        _build_jobs[job_id] = {
            "status": "running",
            "progress": "Queued…",
            "result": None,
            "error": None,
        }

    store = default_location_store()

    def _on_progress(msg: str) -> None:
        with _build_jobs_lock:
            job = _build_jobs.get(job_id)
            if job and job.get("status") == "running":
                job["progress"] = msg

    def _run_build() -> None:
        try:
            res = store.build_full_cache(force=body.force, pace_sec=body.pace_sec, on_progress=_on_progress)
            with _build_jobs_lock:
                _build_jobs[job_id]["status"] = "done"
                _build_jobs[job_id]["result"] = res
        except Exception as e:
            with _build_jobs_lock:
                _build_jobs[job_id]["status"] = "error"
                _build_jobs[job_id]["error"] = str(e)
        finally:
            with _build_jobs_lock:
                global _current_build_running
                _current_build_running = False

    _location_cache_build_executor.submit(_run_build)
    return {"status": "started", "job_id": job_id}


@router.get(
    "/bhulekh/options/build-cache/status",
    summary="Get background cache-build status",
)
async def bhulekh_build_cache_status(job_id: str) -> Dict[str, Any]:
    with _build_jobs_lock:
        job = _build_jobs.get(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Unknown job_id")
        return {"job_id": job_id, **job}


@router.get("/bhulekh/options/fasli-years", summary="List Fasli year options")
async def bhulekh_fasli_years() -> Dict[str, Any]:
    # Portal wording changes; keep human-friendly options.
    return {
        "fasli_years": [
            "वर्तमान फसली वर्ष",
            "पिछला फसली वर्ष",
        ]
    }


@router.post(
    "/bhulekh/verify",
    summary="Fetch official Bhulekh result and parse the official PDF (if available)",
)
async def bhulekh_verify(body: BhulekhFetchBody) -> Dict[str, Any]:
    """
    Strong verification endpoint:
    1) Run Bhulekh fetch (Selenium) using the exact district/tehsil/village + khasra/owner.
    2) If the portal exposes a PDF URL, download it server-side and parse the table into structured fields.
    """
    scraper = UPBhulekhScraper()
    store = default_record_store()
    verify_key = store.make_key(
        district=body.district,
        tehsil=body.tehsil,
        village=body.village,
        khasra=body.khasra or "",
        owner_name=body.owner_name or "",
        fasli_year=body.fasli_year or "",
    )
    loop = asyncio.get_event_loop()
    force = bool(body.force_refresh)
    try:
        raw: Optional[Dict[str, Any]] = None

        # If force_refresh, clear any existing cache and always run Selenium
        if force:
            await loop.run_in_executor(_executor, lambda: store.delete_key(verify_key))
        else:
            def _get_cached_verify() -> Optional[Dict[str, Any]]:
                cached = store.get_entry(verify_key)
                if not cached or not isinstance(cached, dict):
                    return None
                # If we have any marker that verification was attempted, reuse it.
                if "official_pdf_parsed" in cached:
                    return cached
                return None

            cached = await loop.run_in_executor(_executor, _get_cached_verify)

            if cached and isinstance(cached.get("lookup"), dict):
                lookup = cached["lookup"]
                cached_owner = str(lookup.get("owner") or "")
                cached_area = str(lookup.get("area") or "")
                cached_pdf = str(lookup.get("pdf_url") or "").strip()
                cached_parsed = cached.get("official_pdf_parsed")
                # If cached payload is clearly invalid and has no parsed/pdf backing, force refresh.
                if (_looks_like_garbage_value(cached_owner) or _looks_like_garbage_value(cached_area)) and not cached_pdf and not isinstance(cached_parsed, dict):
                    await loop.run_in_executor(_executor, lambda: store.delete_key(verify_key))
                else:
                    # Cached verify always includes official_pdf_parsed, so we can return directly.
                    pdf_url = str(lookup.get("pdf_url") or "").strip()
                    parsed = cached.get("official_pdf_parsed")
                    raw_result = {
                        "owner": str(lookup.get("owner", "")),
                        "khasra": str(lookup.get("khasra", "")),
                        "area": str(lookup.get("area", "")),
                        "search_mode": str(lookup.get("search_mode", "")),
                    }
                    return {
                        "result": _compose_verify_result(raw_result, parsed if isinstance(parsed, dict) else None),
                        "pdf_url": pdf_url,
                        "official_pdf_parsed": parsed,
                        "screenshot_b64": str(lookup.get("screenshot_b64", "")),
                    }

        # Always run Selenium to open Chrome and scrape the portal
        def _fetch_lookup() -> Dict[str, Any]:
            return scraper.fetch_record(
                district=body.district,
                tehsil=body.tehsil,
                village=body.village,
                khasra=body.khasra,
                owner_name=body.owner_name,
                fasli_year=body.fasli_year,
            )

        raw = await loop.run_in_executor(_executor, _fetch_lookup)
    except BhulekhNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except BhulekhTimeoutError as e:
        raise HTTPException(status_code=504, detail=str(e)) from e
    except BhulekhCaptchaError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    except BhulekhNavigationError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e

    pdf_url = str(raw.get("pdf_url") or "").strip()
    parsed = None
    if pdf_url:
        try:
            async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client:
                resp = await client.get(pdf_url)
            payload = resp.content or b""
            ctype = str(resp.headers.get("content-type") or "").lower()
            looks_like_pdf = payload.lstrip().startswith(b"%PDF") or (b"%PDF" in payload[:1024])
            if resp.status_code == 200 and payload and (looks_like_pdf or "application/pdf" in ctype):
                parsed = extract_registry_fields_from_document(
                    payload, filename="bhulekh_official.pdf", include_raw_text=False
                ).dict()
        except Exception:
            parsed = None

    lookup_payload = {
        **_sanitize_lookup_payload(raw),
        "pdf_url": pdf_url,
    }
    # Persist lookup + parsed PDF result so the same verify call is fast next time.
    await loop.run_in_executor(
        _executor,
        lambda: store.upsert_verify(
            verify_key,
            lookup=lookup_payload,
            official_pdf_parsed=parsed,
            pdf_url=pdf_url,
        ),
    )

    return {
        "result": _compose_verify_result(raw, parsed),
        "pdf_url": pdf_url,
        "official_pdf_parsed": parsed,
        "screenshot_b64": raw.get("screenshot_b64", ""),
    }


@router.post("/ownership-chain", summary="Validate sale / mutation chain")
async def ownership_chain(body: OwnershipChainBody) -> Dict[str, Any]:
    txs = [t.dict() for t in body.transactions]
    return analyze_ownership_chain(txs)


@router.post("/supporting-documents", summary="Score electricity / tax / water bills vs claim")
async def supporting_documents(body: SupportingDocsBody) -> Dict[str, Any]:
    docs = [{"type": d.type, "text": d.text} for d in body.documents]
    return analyze_supporting_documents(
        docs,
        claimed_owner=body.claimed_owner,
        claimed_land_address=body.claimed_land_address,
    )


@router.post("/decision", summary="Combine signals into party scores and winner")
async def decision(body: DecisionBody) -> Dict[str, Any]:
    return run_decision(
        party_a=body.party_a.dict(),
        party_b=body.party_b.dict(),
    )
