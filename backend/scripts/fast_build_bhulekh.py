import json
import os
import time
from pathlib import Path
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

def _atomic_write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)

def main():
    backend_dir = Path(__file__).resolve().parents[1]
    out_path = backend_dir / "data" / "bhulekh_locations.up.json"

    # Load existing cache
    if out_path.is_file():
        try:
            existing = json.loads(out_path.read_text(encoding="utf-8"))
            if not isinstance(existing, dict):
                existing = {}
        except Exception:
            existing = {}
    else:
        existing = {}

    store = dict(existing)
    options = Options()
    if os.getenv("BHU_LEKH_HEADLESS") == "1":
        options.add_argument("--headless=new")
    
    print("Starting browser session for fast build...")
    driver = webdriver.Chrome(options=options)
    
    try:
        driver.get("https://upbhulekh.gov.in/#/khatauni_rtk")
        print("Please solve captcha if prompted...")
        
        # Wait for the main UI to load (captcha solved)
        comboboxes = []
        while True:
            comboboxes = driver.find_elements(By.CSS_SELECTOR, "mat-select, .mat-mdc-select, select")
            if len(comboboxes) >= 1:
                break
            time.sleep(1)
            
        print("UI loaded. Starting fast fetch...")
        
        is_select = driver.find_elements(By.TAG_NAME, "select")
        
        if len(is_select) >= 3:
            print("Using classic <select> dropdowns")
            from selenium.webdriver.support.ui import Select
            d_sel = Select(is_select[0])
            t_sel = Select(is_select[1])
            v_sel = Select(is_select[2])
            
            districts = [o.text.strip() for o in d_sel.options if o.text.strip() and "Select" not in o.text and "चुनें" not in o.text]
            
            for d in districts:
                if "buland" not in d.lower() and "बुलन्द" not in d:
                    continue
                # Overwrite cached for bulandshahar
                store[d] = {}
                print(f"District: {d}")
                d_sel.select_by_visible_text(d)
                time.sleep(1) # wait for tehsils
                
                tehsils = [o.text.strip() for o in t_sel.options if o.text.strip() and "Select" not in o.text and "चुनें" not in o.text]
                for t in tehsils:
                    if t in store[d] and store[d][t]:
                        continue # Already cached
                    print(f"  Tehsil: {t}")
                    t_sel.select_by_visible_text(t)
                    time.sleep(1) # wait for villages
                    
                    villages = [o.text.strip() for o in v_sel.options if o.text.strip() and "Select" not in o.text and "चुनें" not in o.text]
                    store[d][t] = villages
                    _atomic_write_json(out_path, store)
                    
        else:
            print("Using Angular/Material dropdowns")
            
            def open_combo(idx):
                el = comboboxes[idx]
                try: el.click()
                except:
                    try: el.find_element(By.CSS_SELECTOR, ".mat-mdc-select-trigger, .mat-select-trigger").click()
                    except: el.click()
                time.sleep(0.5)
                
            def get_options():
                opts = driver.find_elements(By.CSS_SELECTOR, "mat-option .mat-option-text, mat-option span, [role='option']")
                res = []
                for o in opts:
                    t = (o.text or "").strip()
                    if t and t not in ("Select", "चयन करें", "--Select--", "-- चुनें --"):
                        if t not in res: res.append(t)
                return res
            
            def select_option(text):
                opts = driver.find_elements(By.CSS_SELECTOR, "mat-option, [role='option']")
                for o in opts:
                    if (o.text or "").strip() == text:
                        o.click()
                        time.sleep(0.5)
                        return
                driver.find_element(By.TAG_NAME, "body").click() # close if not found
            
            open_combo(0)
            districts = get_options()
            print(f"Total districts: {len(districts)}")
            print(districts)
            driver.find_element(By.TAG_NAME, "body").click() # close overlay
            time.sleep(0.3)
            
            for d in districts:
                if "buland" not in d.lower() and "बुलन्द" not in d:
                    continue
                # Overwrite cached for bulandshahar
                store[d] = {}
                print(f"District: {d}")
                open_combo(0)
                select_option(d)
                time.sleep(0.5)
                
                open_combo(1)
                tehsils = get_options()
                driver.find_element(By.TAG_NAME, "body").click()
                time.sleep(0.3)
                
                for t in tehsils:
                    if t in store[d] and store[d][t]:
                        continue # Already cached
                    print(f"  Tehsil: {t}")
                    open_combo(1)
                    select_option(t)
                    time.sleep(0.5)
                    
                    open_combo(2)
                    villages = get_options()
                    driver.find_element(By.TAG_NAME, "body").click()
                    time.sleep(0.3)
                    
                    store[d][t] = villages
                    _atomic_write_json(out_path, store)

    except Exception as e:
        print(f"Error: {e}")
    finally:
        driver.quit()
        _atomic_write_json(out_path, store)
        print("Done!")

if __name__ == "__main__":
    main()
