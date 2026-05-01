"""
UP Bhulekh (upbhulekh.gov.in) — Selenium-based khasra lookup.

The portal is an Angular SPA and may show captchas. Selectors can change; regex fallback
parses Hindi labels from page HTML when the DOM structure is unknown.

Environment:
  BHU_LEKH_URL          — entry URL (default: public bhulekh home)
  BHU_LEKH_USE_MOCK     — "1" / "true" returns canned JSON (no browser)
  BHU_LEKH_HEADLESS     — "0" / "false" opens visible Chrome (helps captcha)
  BHU_LEKH_CAPTCHA_WAIT — seconds to wait for manual captcha in non-headless (default 120)
"""

from __future__ import annotations

import logging
import os
import re
import time
from urllib.parse import urljoin
from typing import Any, Dict, List, Optional
from functools import lru_cache

from services.bhulekh.exceptions import (
    BhulekhCaptchaError,
    BhulekhNavigationError,
    BhulekhNotFoundError,
    BhulekhTimeoutError,
)

logger = logging.getLogger(__name__)

DEFAULT_URL = os.getenv("BHU_LEKH_URL", "https://upbhulekh.gov.in/bhulekh_login/#/home")
DEFAULT_OPTIONS_URL = os.getenv(
    "BHU_LEKH_OPTIONS_URL", "https://upbhulekh.gov.in/#/khatauni_rtk"
)


def _truthy(val: Optional[str]) -> bool:
    if val is None:
        return False
    return val.strip().lower() in ("1", "true", "yes", "on")


def _strip_html(text: str) -> str:
    t = re.sub(r"<[^>]+>", " ", text)
    return " ".join(t.split())


def _clean_html_for_regex(html: str) -> str:
    t = re.sub(r'<style[^>]*>.*?</style>', ' ', html, flags=re.DOTALL | re.IGNORECASE)
    t = re.sub(r'<script[^>]*>.*?</script>', ' ', t, flags=re.DOTALL | re.IGNORECASE)
    return t

def _regex_extract_from_html(html: str) -> Dict[str, str]:
    """Best-effort extraction of owner / khasra / area from portal HTML (Hindi + English)."""
    cleaned_html = _clean_html_for_regex(html)
    out = {"owner": "", "khasra": "", "area": ""}
    
    # Table-based extraction (often used in Khatauni RTK)
    try:
        # Replace <br> with ' | ' for better multi-owner formatting
        html_for_table = re.sub(r'<br\s*/?>', ' | ', html, flags=re.I)
        rows = re.findall(r'<tr[^>]*>(.*?)</tr>', html_for_table, re.I | re.DOTALL)
        headers = []
        for r in rows:
            if '<th>' in r.lower() or '<th ' in r.lower():
                headers = [re.sub(r'<[^>]+>', '', th).strip() for th in re.findall(r'<th[^>]*>(.*?)</th>', r, re.I | re.DOTALL)]
            elif headers and ('<td>' in r.lower() or '<td ' in r.lower()):
                tds = [re.sub(r'<[^>]+>', '', td).strip() for td in re.findall(r'<td[^>]*>(.*?)</td>', r, re.I | re.DOTALL)]
                # If lengths roughly match
                if len(tds) >= min(3, len(headers)):
                    for h, v in zip(headers, tds):
                        h_lower = h.lower()
                        if 'खातेदार' in h_lower or 'owner' in h_lower or 'नाम' in h_lower:
                            if not out['owner']: out['owner'] = v
                        elif 'खसरा' in h_lower or 'khasra' in h_lower or 'गाटा' in h_lower:
                            if not out['khasra']: out['khasra'] = v
                        elif 'क्षेत्रफल' in h_lower or 'area' in h_lower or 'हे' in h_lower:
                            if not out['area']: out['area'] = v
                    if out['owner'] or out['area']:
                        break
    except Exception:
        pass

    # Generic string-based extraction if table fails
    if not out["owner"]:
        for pat in (
            r"(?:काश्तकार|काश्तकार\s*का\s*नाम|भूमि\s*स्वामी|स्वामी|Owner|owner)[^:：\n]{0,40}[:：]?\s*([^<\n]{2,120})",
            r"(?:Name|नाम)[^:：\n]{0,20}[:：]\s*([^<\n]{2,120})",
        ):
            m = re.search(pat, cleaned_html, re.I | re.UNICODE)
            if m:
                out["owner"] = _strip_html(m.group(1)).strip(" :|")
                if out["owner"]:
                    break
    
    if not out["khasra"]:
        for pat in (
            r"(?:खसरा|Khasra|khasra)[^:：\n]{0,30}[:：]?\s*([^<\n]{2,80})",
            r"खसरा\s*संख्या[^:：\n]{0,20}[:：]?\s*([^<\n]{2,80})",
        ):
            m = re.search(pat, cleaned_html, re.I | re.UNICODE)
            if m:
                out["khasra"] = _strip_html(m.group(1)).strip(" :|")
                if out["khasra"]:
                    break
                    
    if not out["area"]:
        for pat in (
            r"(?:रकबा|क्षेत्रफल|Area|area|Land\s*area)[^:：\n]{0,30}[:：]?\s*([^<\n]{2,120})",
        ):
            m = re.search(pat, cleaned_html, re.I | re.UNICODE)
            if m:
                out["area"] = _strip_html(m.group(1)).strip(" :|")
                if out["area"]:
                    break

    return out


def _extract_pdf_url_from_html(html: str, base_url: str) -> str:
    """Best-effort PDF URL detection from page HTML."""
    if not html:
        return ""

    # Absolute URLs that directly end with .pdf (optionally with query params).
    m = re.search(r"""(https?://[^\s"'<>]+\.pdf(?:\?[^\s"'<>]*)?)""", html, re.I)
    if m:
        return m.group(1)

    # href/src attributes with .pdf.
    for m2 in re.finditer(r"""(?:href|src)\s*=\s*["']([^"']+\.pdf(?:\?[^"']*)?)["']""", html, re.I):
        candidate = (m2.group(1) or "").strip()
        if not candidate:
            continue
        if candidate.lower().startswith(("http://", "https://")):
            return candidate
        return urljoin(base_url, candidate)

    return ""


def _looks_like_markup_noise(v: str) -> bool:
    s = (v or "").strip().lower()
    if not s:
        return False
    if "<" in s or ">" in s:
        return True
    if "class=" in s or "style=" in s:
        return True
    if "--bs-" in s or "ng-untouched" in s or "form-control" in s:
        return True
    if "top-start" in s or "center-start" in s or "bottom-start" in s:
        return True
    if "white-space:nowrap" in s:
        return True
    if s.count(";") >= 2 and s.count(":") >= 2:
        return True
    return False


def _sanitize_extracted_fields(extracted: Dict[str, str]) -> Dict[str, str]:
    owner = str(extracted.get("owner", "") or "").strip()
    khasra = str(extracted.get("khasra", "") or "").strip()
    area = str(extracted.get("area", "") or "").strip()

    if _looks_like_markup_noise(owner):
        owner = ""
    if _looks_like_markup_noise(area):
        area = ""
    if _looks_like_markup_noise(khasra):
        khasra = ""
    if khasra and not re.search(r"[\d\u0966-\u096F]{1,6}", khasra):
        khasra = ""

    return {"owner": owner, "khasra": khasra, "area": area}


class UPBhulekhScraper:
    """Selenium driver wrapper for UP Bhulekh khasra search."""

    def __init__(
        self,
        *,
        base_url: str = DEFAULT_URL,
        headless: Optional[bool] = None,
        page_load_timeout: int = 45,
        implicit_wait: int = 5,
    ) -> None:
        self.base_url = base_url
        # Default: headless on servers; set BHU_LEKH_HEADLESS=0 for visible Chrome (captcha).
        if headless is None:
            self.headless = _truthy(os.getenv("BHU_LEKH_HEADLESS", "true"))
        else:
            self.headless = headless
        self.page_load_timeout = page_load_timeout
        self.implicit_wait = implicit_wait

    def fetch_khasra(
        self,
        district: str,
        tehsil: str,
        village: str,
        khasra: str,
    ) -> Dict[str, Any]:
        return self.fetch_record(
            district=district,
            tehsil=tehsil,
            village=village,
            khasra=khasra,
            owner_name=None,
        )

    def fetch_record(
        self,
        district: str,
        tehsil: str,
        village: str,
        khasra: Optional[str] = None,
        owner_name: Optional[str] = None,
        fasli_year: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Navigate Bhulekh, select location, search by khasra or owner_name, return
        ``{"owner","khasra","area","raw_error":null}`` or raise domain errors.
        """
        d, t, v = (x.strip() for x in (district, tehsil or "", village))
        k = (khasra or "").strip()
        owner_q = (owner_name or "").strip()
        fy = (fasli_year or "").strip()
        if not all([d, v]):
            raise ValueError("district and village are required.")
        if not k and not owner_q:
            raise ValueError("Either khasra or owner_name is required for Bhulekh lookup.")

        if _truthy(os.getenv("BHU_LEKH_USE_MOCK")):
            logger.info("BHU_LEKH_USE_MOCK active — returning sample payload")
            return {
                "owner": owner_q or "राम सिंह",
                "khasra": k or "113",
                "area": "1.50 हेक्टेयर",
                "mock": True,
                "search_mode": "khasra" if k else "owner_name",
            }

        try:
            from selenium import webdriver  # type: ignore
            from selenium.common.exceptions import (  # type: ignore
                NoSuchElementException,
                TimeoutException,
            )
            from selenium.webdriver.chrome.options import Options  # type: ignore
            from selenium.webdriver.chrome.service import Service  # type: ignore
            from selenium.webdriver.common.by import By  # type: ignore
            from selenium.webdriver.support.ui import Select, WebDriverWait  # type: ignore
            from webdriver_manager.chrome import ChromeDriverManager  # type: ignore
        except ImportError as e:
            raise RuntimeError(
                "Install selenium and webdriver-manager: pip install selenium webdriver-manager"
            ) from e

        opts = Options()
        # Always run visible so user can watch the automation
        if self.headless:
            opts.add_argument("--headless=new")
        opts.add_argument("--no-sandbox")
        opts.add_argument("--disable-dev-shm-usage")
        opts.add_argument("--window-size=1400,900")
        opts.add_argument(
            "--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )

        service = Service(ChromeDriverManager().install())
        driver = None
        try:
            driver = webdriver.Chrome(service=service, options=opts)
            driver.set_page_load_timeout(self.page_load_timeout)
            driver.implicitly_wait(self.implicit_wait)

            wait = WebDriverWait(driver, self.page_load_timeout)

            # Preferred strict flow for UP Bhulekh RTK (district/tehsil/village -> खोजें -> उद्धरण देखें).
            strict = self._fetch_record_strict_rtk(
                driver=driver,
                wait=wait,
                By=By,
                Select=Select,
                district=d,
                tehsil=t,
                village=v,
                khasra=k,
                owner_name=owner_q,
                fasli_year=fy,
            )
            if strict:
                return strict
            # Keep strict-by-default behavior configurable, but do not hard-fail normal runs.
            if _truthy(os.getenv("BHU_LEKH_STRICT_ONLY", "0")):
                raise BhulekhNavigationError(
                    "Strict Bhulekh flow failed (select location -> search -> choose row -> उद्धरण देखें)."
                )

            driver.get(self.base_url)
            time.sleep(2.5)

            # Try to open khasra / public search if a direct link exists
            for link_text in ("खसरा", "Khasra", "Public", "जनपद"):
                try:
                    el = driver.find_element(By.PARTIAL_LINK_TEXT, link_text)
                    el.click()
                    time.sleep(1.5)
                    break
                except NoSuchElementException:
                    continue

            # Native <select> chain (common on some routes)
            selects: List[Any] = []
            try:
                selects = driver.find_elements(By.TAG_NAME, "select")
            except Exception:
                selects = []

            if len(selects) >= 3:
                try:
                    Select(selects[0]).select_by_visible_text(d)
                    time.sleep(1.2)
                    if t:
                        Select(selects[1]).select_by_visible_text(t)
                        time.sleep(1.2)
                    Select(selects[2]).select_by_visible_text(v)
                except Exception as ex:
                    logger.warning("Native select chain failed: %s", ex)

            # Text inputs for khasra / owner / captcha
            # Target central search input (avoid ng-select search boxes).
            inputs = driver.find_elements(
                By.XPATH,
                "//input[(contains(@placeholder,'खसरा') or contains(@placeholder,'गाटा') or contains(@placeholder,'खातेदार') or contains(@class,'form-control')) and not(ancestor::ng-dropdown-panel)]",
            )
            if not inputs:
                inputs = driver.find_elements(By.CSS_SELECTOR, "input[type='text'], input:not([type])")
            filled = False
            search_mode = "khasra" if k else "owner_name"
            if search_mode == "khasra":
                filled = self._fill_search_input(
                    inputs=inputs,
                    value=k,
                    key_terms=("khasra", "गाटा", "खसरा", "plot"),
                )
            else:
                filled = self._fill_search_input(
                    inputs=inputs,
                    value=owner_q,
                    key_terms=("owner", "name", "खातेदार", "काश्तकार", "स्वामी", "नाम"),
                )

            if not filled and inputs:
                try:
                    inputs[-1].send_keys(k if k else owner_q)
                    filled = True
                except Exception:
                    pass

            # Captcha: optional wait for manual solve
            captcha_wait = int(os.getenv("BHU_LEKH_CAPTCHA_WAIT", "120"))
            if not self.headless:
                for _ in range(captcha_wait):
                    if "captcha" in driver.page_source.lower():
                        time.sleep(1)
                    else:
                        break
            elif re.search(r"captcha|कैप्चा", driver.page_source, re.I):
                raise BhulekhCaptchaError(
                    "Captcha detected. Set BHU_LEKH_HEADLESS=0 and BHU_LEKH_CAPTCHA_WAIT, "
                    "or complete lookup manually and use mock mode for automation tests."
                )

            # Submit
            for btn_text in ("खोजें", "Search", "देखें", "Submit"):
                try:
                    btn = driver.find_element(By.PARTIAL_LINK_TEXT, btn_text)
                    btn.click()
                    break
                except NoSuchElementException:
                    continue
            else:
                try:
                    driver.find_element(By.CSS_SELECTOR, "button[type='submit']").click()
                except NoSuchElementException:
                    pass

            try:
                wait.until(lambda dr: len(dr.find_elements(By.CSS_SELECTOR, "table tr, .table, mat-row")) > 0 or len(dr.page_source) > 5000)
            except TimeoutException:
                pass

            time.sleep(2)
            html = driver.page_source

            if re.search(r"no\s*record|नहीं\s*मिल|data\s*not\s*found|कोई\s*डाटा", html, re.I):
                raise BhulekhNotFoundError("No Bhulekh row found for the given district/tehsil/village/khasra.")

            extracted = _sanitize_extracted_fields(_regex_extract_from_html(html))
            if not any(extracted.values()):
                with open("bhulekh_debug.html", "w", encoding="utf-8") as f:
                    f.write(html)
                raise BhulekhNotFoundError(
                    "Could not parse owner/khasra/area from the portal response. "
                    "Portal layout may have changed — update selectors in services/bhulekh/scraper.py"
                )
            pdf_url = _extract_pdf_url_from_html(html, self.base_url)

            return {
                "owner": extracted.get("owner", ""),
                "khasra": extracted.get("khasra", "") or k,
                "area": extracted.get("area", ""),
                "search_mode": search_mode,
                "pdf_url": pdf_url,
            }

        except TimeoutException as e:
            raise BhulekhTimeoutError("Timed out waiting for Bhulekh page or results.") from e
        except BhulekhNotFoundError:
            raise
        except BhulekhCaptchaError:
            raise
        except Exception as e:
            logger.exception("Bhulekh navigation failed")
            raise BhulekhNavigationError(str(e)) from e
        finally:
            if driver is not None:
                try:
                    driver.quit()
                except Exception:
                    pass

    def _fetch_record_strict_rtk(
        self,
        *,
        driver: Any,
        wait: Any,
        By: Any,
        Select: Any,
        district: str,
        tehsil: str,
        village: str,
        khasra: str,
        owner_name: str,
        fasli_year: str,
    ) -> Optional[Dict[str, Any]]:
        """
        Simple, proven portal workflow using direct ng-select interaction:
        1) Open khatauni_rtk page.
        2) Select district/tehsil/village via ng-select dropdowns (English prefix typing).
        3) Type khasra number using on-screen virtual keyboard.
        4) Click खोजें, select the radio row, click red उद्धरण देखें.
        5) Take screenshot and extract details from the detail page.
        """
        import base64
        search_mode = "khasra" if khasra else "owner_name"
        query_val = khasra if khasra else owner_name
        if not query_val:
            return None

        try:
            logger.info("Opening UP Bhulekh RTK page...")
            driver.get(DEFAULT_OPTIONS_URL)
            time.sleep(3.0)

            # --- Step 1: Select District via ng-select ---
            logger.info("Selecting district: %s", district)
            ng_selects = driver.find_elements(By.CSS_SELECTOR, "ng-select")
            if len(ng_selects) < 3:
                logger.warning("Could not find 3 ng-select dropdowns, found %d", len(ng_selects))
                return None

            # District: click, type English prefix (first 5 chars), pick first option
            ng_selects[0].click()
            time.sleep(0.5)
            dist_input = ng_selects[0].find_element(By.CSS_SELECTOR, "input")
            dist_prefix = district[:5] if len(district) > 5 else district
            dist_input.send_keys(dist_prefix)
            time.sleep(1.0)
            opts = driver.find_elements(By.CSS_SELECTOR, "ng-dropdown-panel .ng-option")
            if not opts:
                logger.warning("No district options found for prefix '%s'", dist_prefix)
                return None
            opts[0].click()
            time.sleep(1.5)

            # --- Step 2: Select Tehsil via ng-select ---
            if tehsil:
                logger.info("Selecting tehsil: %s", tehsil)
                ng_selects = driver.find_elements(By.CSS_SELECTOR, "ng-select")
                ng_selects[1].click()
                time.sleep(0.5)
                teh_input = ng_selects[1].find_element(By.CSS_SELECTOR, "input")
                teh_prefix = tehsil[:4] if len(tehsil) > 4 else tehsil
                teh_input.send_keys(teh_prefix)
                time.sleep(2.0)
                opts = driver.find_elements(By.CSS_SELECTOR, "ng-dropdown-panel .ng-option")
                if not opts:
                    logger.warning("No tehsil options found for prefix '%s'", teh_prefix)
                    return None
                opts[0].click()
                time.sleep(1.5)

            # --- Step 3: Select Village via ng-select ---
            logger.info("Selecting village: %s", village)
            ng_selects = driver.find_elements(By.CSS_SELECTOR, "ng-select")
            ng_selects[2].click()
            time.sleep(0.5)
            vil_input = ng_selects[2].find_element(By.CSS_SELECTOR, "input")
            vil_prefix = village[:4] if len(village) > 4 else village
            vil_input.send_keys(vil_prefix)
            time.sleep(2.0)
            opts = driver.find_elements(By.CSS_SELECTOR, "ng-dropdown-panel .ng-option")
            if not opts:
                logger.warning("No village options found for prefix '%s'", vil_prefix)
                return None
            opts[0].click()
            time.sleep(2.0)

            # --- Step 4: Click the correct search tab ---
            if search_mode == "khasra":
                tabs = driver.find_elements(By.XPATH, "//*[contains(text(), 'खसरा/गाटा')]")
                for t in tabs:
                    if t.is_displayed():
                        try:
                            t.click()
                            break
                        except Exception:
                            pass
            else:
                tabs = driver.find_elements(By.XPATH, "//*[contains(text(), 'खातेदार')]")
                for t in tabs:
                    if t.is_displayed():
                        try:
                            t.click()
                            break
                        except Exception:
                            pass
            time.sleep(1.0)

            # --- Step 5: Type the khasra/owner using virtual keyboard or send_keys ---
            if search_mode == "khasra":
                # UP Bhulekh virtual keyboard uses <a class='thCellChild'> for digit keys
                all_keys = driver.find_elements(By.CSS_SELECTOR, "a.thCellChild, td, button")
                for digit in query_val:
                    clicked = False
                    for key in all_keys:
                        try:
                            if key.is_displayed() and key.text.strip() == digit:
                                key.click()
                                clicked = True
                                time.sleep(0.4)
                                break
                        except Exception:
                            pass
                    if not clicked:
                        # Fallback: use JavaScript to click
                        js_result = driver.execute_script(f"""
                            var els = document.querySelectorAll('a.thCellChild, td');
                            for (var i = 0; i < els.length; i++) {{
                                if (els[i].textContent.trim() === '{digit}' && els[i].offsetParent !== null) {{
                                    els[i].click();
                                    return true;
                                }}
                            }}
                            return false;
                        """)
                        if js_result:
                            clicked = True
                            time.sleep(0.4)
                    if not clicked:
                        logger.warning("Could not click virtual key for '%s'", digit)
            else:
                # For owner name, try typing into visible text input
                inputs = driver.find_elements(By.CSS_SELECTOR, "input[type='text'], input:not([type])")
                for inp in inputs:
                    try:
                        if inp.is_displayed() and "ng-select" not in (inp.find_element(By.XPATH, "..").tag_name or ""):
                            inp.clear()
                            inp.send_keys(query_val)
                            break
                    except Exception:
                        continue
            time.sleep(1.0)

            # --- Step 6: Click खोजें (Search button) ---
            logger.info("Clicking search button...")
            search_btns = driver.find_elements(By.XPATH, "//*[contains(text(), 'खोजें')]")
            search_clicked = False
            for btn in search_btns:
                if btn.is_displayed() and btn.tag_name in ("button", "a", "div", "span"):
                    try:
                        btn.click()
                        search_clicked = True
                        break
                    except Exception:
                        pass
            if not search_clicked:
                logger.warning("Could not click search button")
                return None
            time.sleep(3.0)

            # --- Step 7: Check for SweetAlert error ---
            swals = driver.find_elements(By.CSS_SELECTOR, ".swal-text")
            if swals and swals[0].is_displayed():
                swal_msg = swals[0].text
                logger.warning("Portal SweetAlert: %s", swal_msg)
                # Dismiss the alert
                try:
                    driver.find_element(By.CSS_SELECTOR, ".swal-button").click()
                except Exception:
                    pass
                raise BhulekhNotFoundError(f"Portal says: {swal_msg}")

            # --- Step 8: Select the radio button for the matching result ---
            logger.info("Selecting result row for query: %s", query_val)
            radios = driver.find_elements(By.CSS_SELECTOR, "input[type='radio']")
            radio_clicked = False
            for r in radios:
                if r.is_displayed():
                    try:
                        r.click()
                        radio_clicked = True
                        break
                    except Exception:
                        try:
                            driver.execute_script("arguments[0].click();", r)
                            radio_clicked = True
                            break
                        except Exception:
                            pass
            if not radio_clicked:
                logger.warning("No radio button found to select result row")
                # Still try to proceed - some pages don't use radio buttons

            time.sleep(1.0)

            # --- Step 9: Click red उद्धरण देखें button ---
            logger.info("Clicking उद्धरण देखें button...")
            red_btns = driver.find_elements(By.XPATH, "//*[contains(text(), 'उद्धरण देखें')]")
            red_clicked = False
            for btn in red_btns:
                if btn.is_displayed():
                    try:
                        btn.click()
                        red_clicked = True
                        break
                    except Exception:
                        pass
            if not red_clicked:
                # Try partial match
                red_btns = driver.find_elements(By.XPATH, "//*[contains(text(), 'उद्धरण')]")
                for btn in red_btns:
                    if btn.is_displayed():
                        try:
                            btn.click()
                            red_clicked = True
                            break
                        except Exception:
                            pass
            if not red_clicked:
                logger.warning("Could not click उद्धरण देखें button")
                return None

            # Handle possible browser alert
            try:
                alert = driver.switch_to.alert
                alert_text = alert.text
                alert.accept()
                logger.warning("Alert after clicking उद्धरण: %s", alert_text)
                raise BhulekhNotFoundError(f"Portal alert: {alert_text}")
            except BhulekhNotFoundError:
                raise
            except Exception:
                pass

            # Check again for SweetAlert
            time.sleep(1.0)
            swals = driver.find_elements(By.CSS_SELECTOR, ".swal-text")
            if swals and swals[0].is_displayed():
                swal_msg = swals[0].text
                try:
                    driver.find_element(By.CSS_SELECTOR, ".swal-button").click()
                except Exception:
                    pass
                raise BhulekhNotFoundError(f"Portal says: {swal_msg}")

            # --- Step 10: Wait for detail page to load ---
            logger.info("Waiting for detail page...")
            try:
                wait.until(
                    lambda dr: ("उद्धरण खतौनी" in dr.page_source)
                    or (len(dr.find_elements(By.CSS_SELECTOR, "table tr")) > 5)
                )
            except Exception:
                pass
            time.sleep(2.0)

            # --- Step 11: Take screenshot ---
            screenshot_path = os.path.join(os.path.dirname(__file__), "..", "..", "bhulekh_result.png")
            screenshot_path = os.path.abspath(screenshot_path)
            screenshot_b64 = ""
            try:
                driver.save_screenshot(screenshot_path)
                with open(screenshot_path, "rb") as f:
                    screenshot_b64 = base64.b64encode(f.read()).decode("utf-8")
                logger.info("Screenshot saved to %s", screenshot_path)
            except Exception as e:
                logger.warning("Failed to save screenshot: %s", e)

            # --- Step 12: Extract data from the detail page ---
            html = driver.page_source

            # Save debug HTML
            try:
                with open("bhulekh_debug_strict.html", "w", encoding="utf-8") as f:
                    f.write(html)
            except Exception:
                pass

            if re.search(r"no\s*record|नहीं\s*मिल|data\s*not\s*found|कोई\s*डाटा", html, re.I):
                raise BhulekhNotFoundError("No Bhulekh row found for the given district/tehsil/village/khasra.")

            extracted = _regex_extract_from_html(html)
            cleaned_html = _clean_html_for_regex(html)

            owner_table = self._extract_owner_from_detail_html(cleaned_html)
            if owner_table:
                extracted["owner"] = owner_table
            area_detail = self._extract_area_from_detail_html(cleaned_html)
            if area_detail:
                extracted["area"] = area_detail
            if not extracted.get("khasra"):
                extracted["khasra"] = self._extract_khasra_from_detail_html(cleaned_html) or khasra
            extracted = _sanitize_extracted_fields(extracted)

            if not any(extracted.values()):
                # Fallback: even if regex extraction failed, return khasra we searched for
                extracted["khasra"] = khasra

            pdf_url = _extract_pdf_url_from_html(html, self.base_url)
            result = {
                "owner": extracted.get("owner", ""),
                "khasra": extracted.get("khasra", "") or khasra,
                "area": extracted.get("area", ""),
                "search_mode": search_mode,
                "pdf_url": pdf_url,
            }
            if screenshot_b64:
                result["screenshot_b64"] = screenshot_b64
            return result

        except BhulekhNotFoundError:
            raise
        except Exception as ex:
            logger.warning("Strict RTK flow failed; falling back to generic flow: %s", ex)
            return None

    def _select_location(
        self,
        *,
        driver: Any,
        By: Any,
        Select: Any,
        district: str,
        tehsil: str,
        village: str,
        fasli_year: str = "",
    ) -> bool:
        # Native <select> path
        try:
            selects = driver.find_elements(By.TAG_NAME, "select")
            if len(selects) >= 3:
                self._select_native_option(Select(selects[0]), district)
                time.sleep(0.8)
                if tehsil:
                    self._select_native_option(Select(selects[1]), tehsil)
                    time.sleep(0.8)
                self._select_native_option(Select(selects[2]), village)
                time.sleep(0.8)
                if len(selects) >= 4:
                    try:
                        fy_sel = Select(selects[3])
                        if fasli_year:
                            self._select_native_option(fy_sel, fasli_year)
                        else:
                            # choose first non-empty option as safe default
                            for o in fy_sel.options:
                                tx = (o.text or "").strip()
                                if tx and tx not in ("Select", "चयन करें", "--Select--", "-- चुनें --"):
                                    fy_sel.select_by_visible_text(tx)
                                    break
                        time.sleep(0.6)
                    except Exception:
                        pass
                return True
        except Exception:
            pass

        # Material combobox path
        try:
            combos = driver.find_elements(By.CSS_SELECTOR, "[role='combobox'], mat-select, .mat-mdc-select, .mat-select")
            if len(combos) < 3:
                return False
            self._select_mat_option(driver=driver, By=By, combo=combos[0], value=district)
            time.sleep(0.8)
            if tehsil:
                combos = driver.find_elements(By.CSS_SELECTOR, "[role='combobox'], mat-select, .mat-mdc-select, .mat-select")
                self._select_mat_option(driver=driver, By=By, combo=combos[1], value=tehsil)
                time.sleep(0.8)
            combos = driver.find_elements(By.CSS_SELECTOR, "[role='combobox'], mat-select, .mat-mdc-select, .mat-select")
            self._select_mat_option(driver=driver, By=By, combo=combos[2], value=village)
            time.sleep(0.8)
            if len(combos) >= 4:
                try:
                    self._select_mat_option(
                        driver=driver,
                        By=By,
                        combo=combos[3],
                        value=fasli_year or "वर्तमान फसली वर्ष",
                    )
                    time.sleep(0.6)
                except Exception:
                    pass
            return True
        except Exception:
            pass

        # ng-select (searchable dropdowns as seen on current Bhulekh page)
        try:
            ok_d = self._select_ng_by_placeholder(
                driver=driver,
                By=By,
                placeholder_hint=("search or select district", "district", "जनपद"),
                value=district,
                fallback_index=0,
            )
            time.sleep(1.2)  # Wait for API to populate Tehsils
            
            ok_t = True
            if tehsil:
                ok_t = self._select_ng_by_placeholder(
                    driver=driver,
                    By=By,
                    placeholder_hint=("search or select tehsil", "tehsil", "तहसील"),
                    value=tehsil,
                    fallback_index=1,
                )
                time.sleep(1.2)  # Wait for API to populate Villages
                
            ok_v = self._select_ng_by_placeholder(
                driver=driver,
                By=By,
                placeholder_hint=("search or select village", "village", "ग्राम"),
                value=village,
                fallback_index=2,
            )
            time.sleep(1.0)
            
            ok_f = True
            if fasli_year:
                ok_f = self._select_ng_by_placeholder(
                    driver=driver,
                    By=By,
                    placeholder_hint=("फसली", "वर्तमान खतौनी", "fasli"),
                    value=fasli_year,
                    fallback_index=3,
                )
                time.sleep(0.5)
                
            return bool(ok_d and ok_t and ok_v and ok_f)
        except Exception:
            return False

    def _select_ng_by_placeholder(
        self,
        *,
        driver: Any,
        By: Any,
        placeholder_hint: tuple[str, ...],
        value: str,
        fallback_index: int = 0,
    ) -> bool:
        val = (value or "").strip()
        if not val:
            return False
            
        hints = [h.lower() for h in placeholder_hint if h]
        ng_candidates = driver.find_elements(By.CSS_SELECTOR, "ng-select, .ng-select")
        ng = None
        for cand in ng_candidates:
            t = ((cand.text or "") + " " + (cand.get_attribute("innerText") or "")).lower()
            if any(h in t for h in hints):
                ng = cand
                break
        if ng is None and len(ng_candidates) > fallback_index:
            ng = ng_candidates[fallback_index]
        if ng is None:
            return False

        try:
            ng.click()
        except Exception:
            try:
                driver.execute_script("arguments[0].click();", ng)
            except Exception:
                return False
        time.sleep(0.4)

        # The input is inside the ng-select element itself
        typed = False
        print(f"[DEBUG] Clicking ng-select for hints {hints}")
        for _ in range(6):  # Poll for up to 3 seconds for the panel to open and load
            time.sleep(0.5)
            # Find the input element inside the specific ng-select we clicked
            for si in ng.find_elements(By.CSS_SELECTOR, "input[type='text'], input[role='combobox']"):
                if not si.is_displayed():
                    continue
                try:
                    si.clear()
                    # Type only first 4 chars to avoid spelling differences at the end of the word
                    short_val = val[:4] if len(val) > 4 else val
                    si.send_keys(short_val)
                    print(f"[DEBUG] Typed '{short_val}' into search box")
                    typed = True
                    break
                except Exception as e:
                    print(f"[DEBUG] Error typing: {e}")
                    continue
            if typed:
                break
                
        if typed:
            print(f"[DEBUG] Waiting for options after typing...")
            for _ in range(15):  # Wait up to 7.5 seconds for API to populate options
                time.sleep(0.5)
                if self._click_option_text(driver=driver, By=By, value=val):
                    print(f"[DEBUG] Successfully clicked option using text matching for '{val}'")
                    return True
                # Fallback: if we typed and filtered the list, but text matching fails (e.g. English vs Hindi),
                # just click the first visible option in the filtered list.
                opts = driver.find_elements(By.CSS_SELECTOR, "ng-dropdown-panel .ng-option, [role='option']")
                for o in opts:
                    if o.is_displayed():
                        text = (o.text or "").lower()
                        if "not found" in text or "नहीं" in text:
                            continue
                        try:
                            o.click()
                        except Exception:
                            driver.execute_script("arguments[0].click();", o)
                        print(f"[DEBUG] Successfully clicked fallback option with text '{text}'")
                        return True
            print(f"[DEBUG] Failed to find option after 15 retries for '{val}'")
        else:
            print(f"[DEBUG] Failed to type into search box for '{val}'")
            if self._click_option_text(driver=driver, By=By, value=val):
                return True
                
        print(f"[DEBUG] Returning False for '{val}'")
        return False

    def _select_ng_by_label(
        self,
        *,
        driver: Any,
        By: Any,
        label_hint: tuple[str, ...],
        value: str,
    ) -> bool:
        val = (value or "").strip()
        if not val:
            return False
        # Locate block by label text and then the first ng-select under it.
        for hint in label_hint:
            try:
                block_xpath = (
                    f"//*[contains(normalize-space(.), \"{hint}\")]/following::*"
                    f"[self::ng-select or contains(@class,'ng-select')][1]"
                )
                blocks = driver.find_elements(By.XPATH, block_xpath)
                if not blocks:
                    continue
                ng = blocks[0]
                try:
                    ng.click()
                except Exception:
                    driver.execute_script("arguments[0].click();", ng)
                time.sleep(0.4)

                # Type in search box if present.
                search_inputs = driver.find_elements(By.CSS_SELECTOR, "input[type='text'], input[role='combobox']")
                typed = False
                for si in search_inputs:
                    if not si.is_displayed():
                        continue
                    try:
                        si.clear()
                        si.send_keys(val)
                        typed = True
                        break
                    except Exception:
                        continue
                if typed:
                    time.sleep(0.5)

                # Click option exact/contains.
                if self._click_option_text(driver=driver, By=By, value=val):
                    return True
                # fallback enter key selects highlighted option
                if typed:
                    try:
                        from selenium.webdriver.common.keys import Keys  # type: ignore
                        si.send_keys(Keys.ENTER)
                        time.sleep(0.3)
                        return True
                    except Exception:
                        pass
            except Exception:
                continue
        return False

    def _click_option_text(self, *, driver: Any, By: Any, value: str) -> bool:
        target = (value or "").strip()
        if not target:
            return False
        target_norm = target.split("(", 1)[0].strip().lower()
        opts = driver.find_elements(
            By.CSS_SELECTOR,
            "ng-dropdown-panel .ng-option, .ng-dropdown-panel .ng-option-label, [role='option'], .dropdown-item",
        )
        # exact
        for o in opts:
            tx = (o.text or "").strip()
            if tx == target:
                try:
                    o.click()
                except Exception:
                    driver.execute_script("arguments[0].click();", o)
                return True
        # normalized / contains
        for o in opts:
            tx = (o.text or "").strip()
            if not tx:
                continue
            tx_norm = tx.split("(", 1)[0].strip().lower()
            if tx_norm == target_norm or target.lower() in tx.lower() or (target_norm and target_norm in tx.lower()):
                try:
                    o.click()
                except Exception:
                    driver.execute_script("arguments[0].click();", o)
                return True
        # fuzzy matching fallback using difflib
        import difflib
        best_match = None
        best_ratio = 0.0
        for o in opts:
            tx = (o.text or "").strip()
            if not tx:
                continue
            tx_norm = tx.split("(", 1)[0].strip().lower()
            ratio = difflib.SequenceMatcher(None, target_norm, tx_norm).ratio()
            if ratio > best_ratio:
                best_ratio = ratio
                best_match = o
                
        if best_match and best_ratio > 0.75:  # 75% similarity threshold
            try:
                best_match.click()
            except Exception:
                driver.execute_script("arguments[0].click();", best_match)
            return True
            
        return False

    def _select_native_option(self, sel: Any, value: str) -> None:
        """
        Select option by tolerant matching:
        exact -> normalized (before '(') -> contains.
        """
        target = (value or "").strip()
        if not target:
            return
        target_norm = target.split("(", 1)[0].strip().lower()

        # 1) exact
        try:
            sel.select_by_visible_text(target)
            return
        except Exception:
            pass

        # 2) normalized match
        for o in sel.options:
            tx = (o.text or "").strip()
            if not tx:
                continue
            tx_norm = tx.split("(", 1)[0].strip().lower()
            if tx_norm and tx_norm == target_norm:
                o.click()
                return

        # 3) contains fallback
        for o in sel.options:
            tx = (o.text or "").strip()
            tx_l = tx.lower()
            if target.lower() in tx_l or (target_norm and target_norm in tx_l):
                o.click()
                return
        raise ValueError(f"Could not select option: {value}")

    def _select_mat_option(self, *, driver: Any, By: Any, combo: Any, value: str) -> None:
        try:
            combo.click()
        except Exception:
            try:
                combo.find_element(By.CSS_SELECTOR, ".mat-mdc-select-trigger, .mat-select-trigger").click()
            except Exception:
                combo.click()
        time.sleep(0.5)
        options = driver.find_elements(By.CSS_SELECTOR, "mat-option, [role='option']")
        for o in options:
            tx = (o.text or "").strip()
            if tx == value:
                o.click()
                return
        for o in options:
            tx = (o.text or "").strip()
            if value and (value in tx or tx in value):
                o.click()
                return
        # close overlay
        try:
            driver.find_element(By.TAG_NAME, "body").click()
        except Exception:
            pass

    def _click_by_text(self, driver: Any, By: Any, texts: tuple[str, ...]) -> bool:
        for txt in texts:
            if not txt:
                continue

            # 1. Try exact match first on all clickable elements
            xp_exact = (
                f"//*[self::button or self::a or self::span or self::div]"
                f"[normalize-space(.)=\"{txt}\"]"
            )
            try:
                els = driver.find_elements(By.XPATH, xp_exact)
                for el in els:
                    if not el.is_displayed():
                        continue
                    try:
                        el.click()
                    except Exception:
                        driver.execute_script("arguments[0].click();", el)
                    return True
            except Exception:
                pass

            # 2. Try partial link text
            try:
                driver.find_element(By.PARTIAL_LINK_TEXT, txt).click()
                return True
            except Exception:
                pass

            # 3. Generic clickable elements containing text
            xp_contains = (
                f"//*[self::button or self::a or self::span or self::div]"
                f"[contains(normalize-space(.), \"{txt}\")]"
            )
            try:
                els = driver.find_elements(By.XPATH, xp_contains)
                for el in els:
                    if not el.is_displayed():
                        continue
                    try:
                        el.click()
                    except Exception:
                        driver.execute_script("arguments[0].click();", el)
                    return True
            except Exception:
                pass
        return False

    def _select_result_row(self, *, driver: Any, By: Any, query: str) -> bool:
        q = (query or "").strip()
        if not q:
            return False
        # Prefer rows that mention the query.
        try:
            rows = driver.find_elements(By.CSS_SELECTOR, "table tr, .mat-row, mat-row, li")
            for row in rows:
                txt = (row.text or "").strip()
                if q not in txt:
                    continue
                radios = row.find_elements(By.CSS_SELECTOR, "input[type='radio']")
                if radios:
                    try:
                        radios[0].click()
                        return True
                    except Exception:
                        pass
        except Exception:
            pass
        # fallback: first visible radio
        try:
            radios = driver.find_elements(By.CSS_SELECTOR, "input[type='radio']")
            for r in radios:
                if r.is_displayed():
                    try:
                        r.click()
                        return True
                    except Exception:
                        continue
        except Exception:
            pass
        return False
        # 2. Try options or list items that contain the query
        try:
            for el in driver.find_elements(By.CSS_SELECTOR, "option, li, .list-group-item, .mat-row, .mat-option, .ng-option, tr"):
                tx = (el.text or "").strip()
                if not tx:
                    continue
                if q in tx:
                    try:
                        driver.execute_script("arguments[0].click();", el)
                        return
                    except Exception:
                        pass
        except Exception:
            pass

    def _extract_owner_from_detail_html(self, html: str) -> str:
        # Multi-owner rows typically start with "1)" / "2)" etc in the PDF/details view.
        owners: List[str] = []
        for m in re.finditer(r"(?:^|[\s>])\d+\)\s*([^\n<]{2,120})", html, re.UNICODE):
            line = _strip_html(m.group(1))
            line = re.split(r"/", line, maxsplit=1)[0].strip()
            if line and line not in owners and not re.search(r"(खातेदार|विवरण|संख्या|क्षेत्रफल)", line):
                owners.append(line)
            if len(owners) >= 8:
                break
        return " | ".join(owners)

    def _extract_area_from_detail_html(self, html: str) -> str:
        m = re.search(r"(?:गाटे\s*का\s*कुल\s*क्षेत्रफल|क्षेत्रफल)[^\d]{0,80}([0-9\u0966-\u096F]+\.[0-9\u0966-\u096F]{3,5})", html, re.UNICODE)
        if m:
            return _strip_html(m.group(1))
        return ""

    def _extract_khasra_from_detail_html(self, html: str) -> str:
        m = re.search(r"खसरा\s*/\s*गाटा\s*संख्या[^\d]{0,30}([0-9\u0966-\u096F]{1,6})", html, re.UNICODE)
        if m:
            return _strip_html(m.group(1))
        m2 = re.search(r"(?<!\d)([0-9\u0966-\u096F]{2,5})\s*\([0-9\u0966-\u096F]{12,24}\)", html, re.UNICODE)
        return _strip_html(m2.group(1)) if m2 else ""

    def fetch_location_options(
        self,
        *,
        district: str = "",
        tehsil: str = "",
    ) -> Dict[str, List[str]]:
        """
        Best-effort extraction of dropdown options from Bhulekh UI:
        - districts (जनपद)
        - tehsils (तहसील) for a given district
        - villages (ग्राम) for a given district+tehsil

        Returns keys present based on inputs.
        """
        if _truthy(os.getenv("BHU_LEKH_USE_MOCK")):
            return {
                "districts": ["Bulandshahar", "Lucknow"],
                "tehsils": ["Anupshahar"],
                "villages": ["Madhugadh"],
            }

        try:
            from selenium import webdriver  # type: ignore
            from selenium.common.exceptions import NoSuchElementException  # type: ignore
            from selenium.webdriver.chrome.options import Options  # type: ignore
            from selenium.webdriver.chrome.service import Service  # type: ignore
            from selenium.webdriver.common.by import By  # type: ignore
            from selenium.webdriver.support.ui import Select  # type: ignore
            from webdriver_manager.chrome import ChromeDriverManager  # type: ignore
        except ImportError as e:
            raise RuntimeError(
                "Install selenium and webdriver-manager: pip install selenium webdriver-manager"
            ) from e

        opts = Options()
        if self.headless:
            opts.add_argument("--headless=new")
        opts.add_argument("--no-sandbox")
        opts.add_argument("--disable-dev-shm-usage")
        opts.add_argument("--window-size=1400,900")

        service = Service(ChromeDriverManager().install())
        driver = None
        try:
            driver = webdriver.Chrome(service=service, options=opts)
            driver.set_page_load_timeout(self.page_load_timeout)
            driver.implicitly_wait(self.implicit_wait)
            # Use khatauni_rtk page for dropdowns (district/tehsil/village/fasli year)
            driver.get(DEFAULT_OPTIONS_URL)
            time.sleep(2.2)

            # Try native <select> first (some mirrors/variants still use it)
            selects = driver.find_elements(By.TAG_NAME, "select")
            if len(selects) >= 3:
                district_sel = Select(selects[0])
                tehsil_sel = Select(selects[1])
                village_sel = Select(selects[2])

                def _clean_options(sel: Select) -> List[str]:
                    out: List[str] = []
                    for o in sel.options:
                        t0 = (o.text or "").strip()
                        if not t0 or t0 in ("Select", "चयन करें", "--Select--", "-- चुनें --"):
                            continue
                        if t0 not in out:
                            out.append(t0)
                    return out

                out: Dict[str, List[str]] = {"districts": _clean_options(district_sel)}
                d = (district or "").strip()
                t = (tehsil or "").strip()
                if d:
                    try:
                        district_sel.select_by_visible_text(d)
                        time.sleep(1.2)
                    except Exception:
                        pass
                    out["tehsils"] = _clean_options(tehsil_sel)
                if d and t:
                    try:
                        tehsil_sel.select_by_visible_text(t)
                        time.sleep(1.2)
                    except Exception:
                        pass
                    out["villages"] = _clean_options(village_sel)
                return out

            # Angular/Material dropdowns (mat-select): use comboboxes in order (district, tehsil, village, fasli)
            comboboxes = driver.find_elements(By.CSS_SELECTOR, "[role='combobox'], mat-select")
            if len(comboboxes) < 3:
                # Some builds wrap the trigger
                comboboxes = driver.find_elements(By.CSS_SELECTOR, ".mat-mdc-select, .mat-select")
            if len(comboboxes) < 3:
                raise BhulekhNavigationError("Could not locate district/tehsil/village dropdowns on khatauni_rtk.")

            def _open_combo(idx: int) -> None:
                el = comboboxes[idx]
                try:
                    el.click()
                except Exception:
                    # click the inner trigger if needed
                    try:
                        el.find_element(By.CSS_SELECTOR, ".mat-mdc-select-trigger, .mat-select-trigger").click()
                    except Exception:
                        el.click()
                time.sleep(0.6)

            def _read_open_options() -> List[str]:
                # Material overlay options
                opts_els = driver.find_elements(
                    By.CSS_SELECTOR,
                    "mat-option .mat-option-text, mat-option span, [role='option']",
                )
                out2: List[str] = []
                for o in opts_els:
                    t0 = (o.text or "").strip()
                    if not t0 or t0 in ("Select", "चयन करें", "--Select--", "-- चुनें --"):
                        continue
                    if t0 not in out2:
                        out2.append(t0)
                return out2

            def _select_option(text: str) -> None:
                if not text:
                    return
                # Try exact match first
                for o in driver.find_elements(By.CSS_SELECTOR, "mat-option, [role='option']"):
                    if (o.text or "").strip() == text:
                        o.click()
                        time.sleep(0.8)
                        return
                # Fallback: contains
                for o in driver.find_elements(By.CSS_SELECTOR, "mat-option, [role='option']"):
                    if text in ((o.text or "").strip()):
                        o.click()
                        time.sleep(0.8)
                        return

            out: Dict[str, List[str]] = {}
            # Districts
            _open_combo(0)
            out["districts"] = _read_open_options()
            # Close overlay by selecting nothing? click body
            driver.find_element(By.TAG_NAME, "body").click()
            time.sleep(0.3)

            d = (district or "").strip()
            t = (tehsil or "").strip()
            if d:
                _open_combo(0)
                _select_option(d)
            # Tehsils
            _open_combo(1)
            out["tehsils"] = _read_open_options()
            driver.find_element(By.TAG_NAME, "body").click()
            time.sleep(0.3)

            if d and t:
                _open_combo(1)
                _select_option(t)
            # Villages
            _open_combo(2)
            out["villages"] = _read_open_options()
            driver.find_element(By.TAG_NAME, "body").click()
            time.sleep(0.3)

            return out
        except NoSuchElementException as e:
            raise BhulekhNavigationError("Bhulekh dropdown elements not found.") from e
        except Exception as e:
            logger.exception("Bhulekh options fetch failed")
            raise BhulekhNavigationError(str(e)) from e
        finally:
            if driver is not None:
                try:
                    driver.quit()
                except Exception:
                    pass

    @staticmethod
    def _fill_search_input(inputs: List[Any], value: str, key_terms: tuple[str, ...]) -> bool:
        """Find a likely input box by name/placeholder and fill it."""
        for inp in inputs:
            try:
                name = (inp.get_attribute("name") or "").lower()
                plc_raw = inp.get_attribute("placeholder") or ""
                plc = plc_raw.lower()
                if any(term.lower() in name or term.lower() in plc or term in plc_raw for term in key_terms):
                    try:
                        inp.clear()
                        inp.send_keys(value)
                    except Exception:
                        pass
                        
                    # Force Angular change detection using JS
                    try:
                        driver = inp.parent
                        driver.execute_script(
                            "arguments[0].value = arguments[1];"
                            "arguments[0].dispatchEvent(new Event('input', { bubbles: true }));"
                            "arguments[0].dispatchEvent(new Event('change', { bubbles: true }));",
                            inp, value
                        )
                    except Exception:
                        pass
                    return True
            except Exception:
                continue
        return False

    def _type_virtual_keyboard(self, driver: Any, By: Any, value: str) -> None:
        """Type using the on-screen virtual keyboard which UP Bhulekh strictly enforces."""
        if not value:
            return
            
        keys = driver.find_elements(By.CSS_SELECTOR, ".keyboard-container button, .keyboard button, .vk-btn, td, button")
        for char in value:
            for k in keys:
                if k.is_displayed() and k.text == char:
                    try:
                        k.click()
                        time.sleep(0.3)
                        break
                    except:
                        pass


@lru_cache(maxsize=1)
def cached_districts() -> List[str]:
    scraper = UPBhulekhScraper()
    return scraper.fetch_location_options().get("districts", [])
