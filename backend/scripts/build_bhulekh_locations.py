from __future__ import annotations

"""
One-time builder: scrape UP Bhulekh dropdowns and cache locally for fast UI.

Output:
  backend/data/bhulekh_locations.up.json

Notes:
- This can take a while (UP has lots of villages).
- If captcha blocks headless mode, set:
    BHU_LEKH_HEADLESS=0
    BHU_LEKH_CAPTCHA_WAIT=240
- The scraper reads dropdowns from:
    https://upbhulekh.gov.in/#/khatauni_rtk
"""

import json
import os
import time
from pathlib import Path
from typing import Dict, List

from services.bhulekh.scraper import UPBhulekhScraper


def _atomic_write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def main() -> None:
    backend_dir = Path(__file__).resolve().parents[1]
    out_path = backend_dir / "data" / "bhulekh_locations.up.json"

    # Resume if file exists
    if out_path.is_file():
        try:
            existing = json.loads(out_path.read_text(encoding="utf-8"))
            if not isinstance(existing, dict):
                existing = {}
        except Exception:
            existing = {}
    else:
        existing = {}

    scraper = UPBhulekhScraper()

    # Windows terminal sometimes uses cp1252; avoid crashing on Hindi names.
    try:
        import sys

        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
        if hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
    except Exception:
        pass

    print("Fetching district list…", flush=True)
    districts = scraper.fetch_location_options().get("districts", [])
    if not districts:
        raise SystemExit("No districts found. If blocked by captcha, set BHU_LEKH_HEADLESS=0 and retry.")

    store: Dict[str, Dict[str, List[str]]] = dict(existing)

    for di, district in enumerate(districts, start=1):
        if district not in store:
            store[district] = {}
        print(f"[{di}/{len(districts)}] District: {district}", flush=True)

        tehsils = scraper.fetch_location_options(district=district).get("tehsils", [])
        if not tehsils:
            print(f"  Warning: no tehsils read for {district!r}")
            continue

        for ti, tehsil in enumerate(tehsils, start=1):
            if tehsil in store[district] and isinstance(store[district][tehsil], list) and store[district][tehsil]:
                # already filled
                continue
            print(f"  [{ti}/{len(tehsils)}] Tehsil: {tehsil}", flush=True)
            villages = scraper.fetch_location_options(district=district, tehsil=tehsil).get("villages", [])
            store[district][tehsil] = villages
            _atomic_write_json(out_path, store)
            # Gentle pacing (avoid hammering)
            time.sleep(float(os.getenv("BHU_LEKH_OPTIONS_PACE_SEC", "0.25")))

    _atomic_write_json(out_path, store)
    print(f"Done. Wrote {out_path}")


if __name__ == "__main__":
    main()

