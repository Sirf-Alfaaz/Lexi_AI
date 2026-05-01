from __future__ import annotations

import json
import os
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional


def _norm(v: Optional[str]) -> str:
    # Keep Hindi as-is, but normalize whitespace to avoid cache misses.
    s = (v or "").strip()
    return " ".join(s.split())


@dataclass(frozen=True)
class BhulekhRecordStore:
    """
    Persistent cache for Bhulekh lookups so we don't re-scrape the portal
    for the same (district, tehsil, village, khasra/owner_name) inputs.
    """

    data_path: Path
    max_entries: int = 2000

    _file_lock = threading.Lock()

    def _load(self) -> Dict[str, Any]:
        if not self.data_path.is_file():
            return {}
        try:
            raw = json.loads(self.data_path.read_text(encoding="utf-8"))
        except Exception:
            return {}
        if isinstance(raw, dict):
            return raw
        return {}

    def _atomic_write(self, payload: Dict[str, Any]) -> None:
        self.data_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.data_path.with_suffix(self.data_path.suffix + f".tmp.{os.getpid()}")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self.data_path)

    def make_key(
        self,
        *,
        district: str,
        tehsil: str,
        village: str,
        khasra: str,
        owner_name: str,
        fasli_year: str = "",
    ) -> str:
        khasra_n = _norm(khasra)
        owner_n = _norm(owner_name)
        search_by = "khasra" if khasra_n else "owner_name"

        return "|".join(
            [
                "v1",
                _norm(district),
                _norm(tehsil),
                _norm(village),
                search_by,
                khasra_n,
                owner_n,
                _norm(fasli_year),
            ]
        )

    def get_entry(self, key: str) -> Optional[Dict[str, Any]]:
        raw = self._load()
        entry = raw.get(key)
        return entry if isinstance(entry, dict) else None

    def upsert_lookup(
        self,
        key: str,
        *,
        lookup: Dict[str, Any],
    ) -> None:
        """
        Store/merge the base lookup payload.
        lookup can contain: owner, khasra, area, search_mode, pdf_url
        """
        with self._file_lock:
            raw = self._load()
            entry = raw.get(key) if isinstance(raw.get(key), dict) else {}
            entry["lookup"] = lookup
            entry.setdefault("key_version", 1)
            entry["cached_at"] = time.time()
            raw[key] = entry
            self._evict_if_needed(raw)
            self._atomic_write(raw)

    def upsert_verify(
        self,
        key: str,
        *,
        lookup: Dict[str, Any],
        official_pdf_parsed: Optional[Dict[str, Any]],
        pdf_url: str = "",
    ) -> None:
        with self._file_lock:
            raw = self._load()
            entry = raw.get(key) if isinstance(raw.get(key), dict) else {}
            entry["lookup"] = lookup
            # Store even when parsed is None to avoid repeated download/parse loops.
            entry["official_pdf_parsed"] = official_pdf_parsed
            entry["cached_at"] = time.time()
            entry.setdefault("key_version", 1)
            # keep pdf_url inside lookup as well for convenience
            if pdf_url and isinstance(entry.get("lookup"), dict):
                entry["lookup"].setdefault("pdf_url", pdf_url)
                entry["lookup"]["pdf_url"] = pdf_url
            raw[key] = entry
            self._evict_if_needed(raw)
            self._atomic_write(raw)

    def _evict_if_needed(self, raw: Dict[str, Any]) -> None:
        if len(raw) <= self.max_entries:
            return
        # Evict oldest by cached_at.
        items = []
        for k, v in raw.items():
            if not isinstance(v, dict):
                items.append((k, 0.0))
                continue
            items.append((k, float(v.get("cached_at") or 0.0)))
        # Sort ascending by time (oldest first), keep newest.
        items_sorted = sorted(items, key=lambda x: x[1])
        to_drop = items_sorted[: max(0, len(raw) - self.max_entries)]
        for k, _ in to_drop:
            raw.pop(k, None)

    def delete_key(self, key: str) -> None:
        with self._file_lock:
            raw = self._load()
            if key in raw:
                raw.pop(key, None)
                self._atomic_write(raw)


def default_record_store() -> BhulekhRecordStore:
    # record_store.py is at backend/services/bhulekh/record_store.py
    # parents[2] -> backend/
    backend_dir = Path(__file__).resolve().parents[2]
    return BhulekhRecordStore(data_path=backend_dir / "data" / "bhulekh_record_cache.up.json")

