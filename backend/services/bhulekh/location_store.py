from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
import os
import threading
import time
from typing import Any, Callable, Dict, List, Optional

from services.bhulekh.scraper import UPBhulekhScraper

@dataclass(frozen=True)
class BhulekhLocationStore:
    """
    Cached dropdown options for Bhulekh (district → tehsil → village).

    This avoids Selenium on every dropdown interaction (fast + stable).
    """

    data_path: Path

    # Prevent concurrent Selenium cache builds corrupting the JSON file.
    _file_lock = threading.Lock()

    def _load(self) -> Dict[str, Dict[str, List[str]]]:
        if not self.data_path.is_file():
            return {}
        try:
            raw = json.loads(self.data_path.read_text(encoding="utf-8"))
        except Exception:
            return {}
        if not isinstance(raw, dict):
            return {}
        return raw  # district -> tehsil -> [villages]

    def _atomic_write(self, payload: Dict[str, Dict[str, List[str]]]) -> None:
        self.data_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.data_path.with_suffix(self.data_path.suffix + f".tmp.{os.getpid()}")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self.data_path)

    def _normalize_payload(self, payload: Any) -> Dict[str, Dict[str, List[str]]]:
        if not isinstance(payload, dict):
            return {}
        out: Dict[str, Dict[str, List[str]]] = {}
        for district, tehsil_map in payload.items():
            if not isinstance(district, str) or not district.strip():
                continue
            if not isinstance(tehsil_map, dict):
                continue
            out_d: Dict[str, List[str]] = {}
            for tehsil, villages in tehsil_map.items():
                if not isinstance(tehsil, str) or not tehsil.strip():
                    continue
                if not isinstance(villages, list):
                    continue
                out_d[tehsil] = [v for v in (str(x).strip() for x in villages) if v]
            out[district] = out_d
        return out

    def _canonical_key(self, s: str) -> str:
        """
        Canonicalize a portal label for cache matching.

        The cached JSON may store either:
          - "Bulandshahar"
        while the UI may send:
          - "Bulandshahar (बुलन्दशहर)"
        """
        if not isinstance(s, str):
            return ""
        left = s.split("(", 1)[0].strip()
        return " ".join(left.split()).lower()

    def _find_matching_key(self, mapping: Dict[str, Any], key: str) -> Optional[str]:
        """
        Find a key in `mapping` that matches `key` canonically.
        Returns the actual mapping key (for correct cache retrieval).
        """
        if not mapping:
            return None
        target = self._canonical_key(key)
        if not target:
            return None
        if key in mapping:
            return key
        for k in mapping.keys():
            if self._canonical_key(k) == target:
                return k
        return None

    def districts(self) -> List[str]:
        raw = self._load()
        return sorted([k for k in raw.keys() if isinstance(k, str) and k.strip()])

    def tehsils(self, district: str) -> List[str]:
        raw = self._load()
        d = raw.get(district) if isinstance(raw.get(district), dict) else {}
        return sorted([k for k in d.keys() if isinstance(k, str) and k.strip()])

    def villages(self, district: str, tehsil: str) -> List[str]:
        raw = self._load()
        d = raw.get(district) if isinstance(raw.get(district), dict) else {}
        v = d.get(tehsil) if isinstance(d.get(tehsil), list) else []
        out: List[str] = []
        for item in v:
            if isinstance(item, str) and item.strip():
                out.append(item.strip())
        # Preserve portal order if present; otherwise sort for stability
        return out or sorted(out)

    def ensure_districts_cached(self, *, pace_sec: float = 0.25, scraper: Optional[UPBhulekhScraper] = None) -> List[str]:
        """
        Ensure district keys exist in the JSON cache.

        - If cache file is missing/empty -> scrape only districts and write `{district: {}}`.
        - If districts already exist -> no-op.
        """
        with self._file_lock:
            raw = self._normalize_payload(self._load())
            if raw:
                return sorted([k for k in raw.keys() if isinstance(k, str) and k.strip()])

            sc = scraper or UPBhulekhScraper()
            out = sc.fetch_location_options().get("districts", [])
            districts = [d.strip() for d in (out or []) if isinstance(d, str) and d.strip()]
            raw = {d: {} for d in districts}
            self._atomic_write(raw)
            # Small pacing to reduce chance of throttling right after captcha changes.
            time.sleep(max(0.0, float(pace_sec)))
            return districts

    def ensure_tehsils_cached(
        self,
        district: str,
        *,
        pace_sec: float = 0.25,
        scraper: Optional[UPBhulekhScraper] = None,
    ) -> List[str]:
        """
        Ensure tehsil keys exist for a given district in the JSON cache.

        If district is missing (or empty), scrape tehsils for that district and update JSON.
        """
        d = (district or "").strip()
        if not d:
            return []

        with self._file_lock:
            raw = self._normalize_payload(self._load())
            d_key = self._find_matching_key(raw, d)
            existing = raw.get(d_key) if d_key and isinstance(raw.get(d_key), dict) else None
            if isinstance(existing, dict) and existing:
                return sorted([k for k in existing.keys() if isinstance(k, str) and k.strip()])

            sc = scraper or UPBhulekhScraper()
            district_for_scrape = d.split("(", 1)[0].strip() or d
            out = sc.fetch_location_options(district=district_for_scrape).get("tehsils", [])
            tehsils = [t.strip() for t in (out or []) if isinstance(t, str) and t.strip()]

            store_d_key = d_key or d
            raw.setdefault(store_d_key, {})
            # Preserve any already-cached villages for existing tehsils.
            for t in tehsils:
                raw[store_d_key].setdefault(t, raw[store_d_key].get(t, []))
            self._atomic_write(raw)
            time.sleep(max(0.0, float(pace_sec)))
            return sorted(tehsils)

    def ensure_villages_cached(
        self,
        district: str,
        tehsil: str,
        *,
        pace_sec: float = 0.15,
        scraper: Optional[UPBhulekhScraper] = None,
    ) -> List[str]:
        """
        Ensure villages list exists for (district, tehsil) in the JSON cache.

        If missing/empty, scrape villages and update JSON.
        """
        d = (district or "").strip()
        t = (tehsil or "").strip()
        if not d or not t:
            return []

        with self._file_lock:
            raw = self._normalize_payload(self._load())
            d_key = self._find_matching_key(raw, d)
            dmap = raw.get(d_key) if d_key and isinstance(raw.get(d_key), dict) else None

            # Try canonical cache lookup first (avoid Selenium if cache exists).
            if isinstance(dmap, dict):
                t_key = self._find_matching_key(dmap, t)
                if t_key and isinstance(dmap.get(t_key), list) and len(dmap.get(t_key) or []) > 0:
                    return [v for v in (dmap[t_key] or []) if isinstance(v, str) and v.strip()]

            sc = scraper or UPBhulekhScraper()
            district_for_scrape = d.split("(", 1)[0].strip() or d
            out = sc.fetch_location_options(district=district_for_scrape, tehsil=t).get("villages", [])
            villages = [v.strip() for v in (out or []) if isinstance(v, str) and v.strip()]

            store_d_key = d_key or d
            raw.setdefault(store_d_key, {})
            raw[store_d_key][t] = villages
            self._atomic_write(raw)
            time.sleep(max(0.0, float(pace_sec)))
            return villages

    def build_full_cache(
        self,
        *,
        force: bool = False,
        pace_sec: float = 0.25,
        on_progress: Optional[Callable[[str], None]] = None,
    ) -> Dict[str, Any]:
        """
        One-time "build everything" for UP Bhulekh dropdowns.

        - Resumes from existing JSON cache.
        - Scrapes ONLY missing tehsil/village entries when force=False.
        - Writes after each tehsil update so progress is not lost.
        """

        def _progress(msg: str) -> None:
            if on_progress is not None:
                try:
                    on_progress(msg)
                except Exception:
                    # Never fail the build because of progress callback.
                    pass

        with self._file_lock:
            raw_norm = self._normalize_payload(self._load())

        sc = UPBhulekhScraper()

        _progress("Ensuring districts list...")
        districts = self.ensure_districts_cached(pace_sec=pace_sec, scraper=sc)
        store: Dict[str, Dict[str, List[str]]] = dict(raw_norm)

        # If force=True, clear existing tehsil/village maps but keep district keys.
        if force:
            store = {d: {} for d in districts}

        fetched_districts = 0
        fetched_tehsils = 0
        written_tehsils = 0

        for di, district in enumerate(districts, start=1):
            fetched_districts += 1
            store.setdefault(district, {})
            _progress(f"[{di}/{len(districts)}] District: {district}")

            tehsils = sc.fetch_location_options(district=district).get("tehsils", [])
            tehsil_list = [t.strip() for t in (tehsils or []) if isinstance(t, str) and t.strip()]
            if not tehsil_list:
                _progress(f"  Warning: no tehsils found for {district!r}")
                continue

            for ti, tehsil in enumerate(tehsil_list, start=1):
                fetched_tehsils += 1
                already = store.get(district, {}).get(tehsil)
                # Consider "cached" even if the list is empty; we don't want repeated scraping.
                if not force and isinstance(already, list):
                    continue

                _progress(f"  [{ti}/{len(tehsil_list)}] Tehsil: {tehsil}")
                villages = sc.fetch_location_options(district=district, tehsil=tehsil).get("villages", [])
                villages_list = [v.strip() for v in (villages or []) if isinstance(v, str) and v.strip()]

                with self._file_lock:
                    store.setdefault(district, {})
                    store[district][tehsil] = villages_list
                    self._atomic_write(store)
                    written_tehsils += 1

                time.sleep(max(0.0, float(pace_sec)))

        _progress("Location cache build finished.")
        return {
            "districts": len(districts),
            "tehsils_checked": fetched_tehsils,
            "tehsils_written": written_tehsils,
            "cache_path": str(self.data_path),
        }


def default_location_store() -> BhulekhLocationStore:
    # location_store.py is at backend/services/bhulekh/location_store.py
    # parents[2] -> backend/
    backend_dir = Path(__file__).resolve().parents[2]
    return BhulekhLocationStore(data_path=backend_dir / "data" / "bhulekh_locations.up.json")

