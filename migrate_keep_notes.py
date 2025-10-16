import os
import sys
import re
import json
import time
import random
import hashlib
import argparse
from datetime import datetime
from typing import Any, Dict, List

# Selenium imports
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException

# Browser driver (undetected-chromedriver preferred)
try:
    import undetected_chromedriver as uc
except Exception as _e:
    uc = None  # We'll fail later when creating the driver if not installed
# --- Configuration ---
BASE_DIR = os.getcwd()
DEBUG_DIR = os.path.join(BASE_DIR, '.debug')
MANIFEST_PATH = os.path.join(BASE_DIR, 'import_manifest.json')
CHROME_PROFILE_DIR = os.path.join(BASE_DIR, '.chrome-profile')

# Directory to scan for exported Keep JSON files.
# By default, scan the current workspace. You can change this to a specific directory.
# NOTES_DIR = BASE_DIR
NOTES_DIR = '/Users/shubham/Library/CloudStorage/GoogleDrive-hello@shjoshi.com.np/My Drive/Pet Projects/GKeepImport/Keep/'

# Optional label to tag imported notes (only applied to new notes)
IMPORT_LABEL = None  # e.g., 'Imported from JSON'

# Map exported color names to Keep's color labels (best-effort)
COLOR_MAP = {
    'DEFAULT': None,
    'WHITE': None,
    'RED': 'Red',
    'ORANGE': 'Orange',
    'YELLOW': 'Yellow',
    'GREEN': 'Green',
    'TEAL': 'Teal',
    'BLUE': 'Blue',
    'DARKBLUE': 'Dark Blue',
    'PURPLE': 'Purple',
    'PINK': 'Pink',
    'BROWN': 'Brown',
    'GRAY': 'Gray',
}

# --- Helper functions ---

DEBUG = False
LIMIT = None

def ensure_dir(path: str):
    try:
        os.makedirs(path, exist_ok=True)
    except Exception:
        pass

def debug_log(msg: str):
    if DEBUG:
        ts = datetime.now().strftime('%H:%M:%S')
        print(f"[DEBUG {ts}] {msg}")

def sanitize_filename(name: str) -> str:
    name = name.strip() or 'untitled'
    name = re.sub(r'[\\/:*?"<>|]+', '_', name)
    return name[:80]

def snap(driver, name: str, html: bool = False):
    if not DEBUG:
        return
    ensure_dir(DEBUG_DIR)
    ts = datetime.now().strftime('%Y%m%d_%H%M%S_%f')
    base = f"{ts}_{sanitize_filename(name)}"
    png_path = os.path.join(DEBUG_DIR, base + '.png')
    try:
        if driver is None:
            return
        # Skip if window already closed
        if not getattr(driver, 'window_handles', []):
            return
        driver.save_screenshot(png_path)
        debug_log(f"Saved screenshot: {png_path}")
    except Exception as e:
        debug_log(f"Failed to save screenshot: {e}")
    if html:
        html_path = os.path.join(DEBUG_DIR, base + '.html')
        try:
            if driver is None or not getattr(driver, 'window_handles', []):
                return
            with open(html_path, 'w', encoding='utf-8') as f:
                f.write(driver.page_source)
            debug_log(f"Saved page source: {html_path}")
        except Exception as e:
            debug_log(f"Failed to save page source: {e}")

def create_driver():
    os.makedirs(CHROME_PROFILE_DIR, exist_ok=True)
    chrome_options = uc.ChromeOptions()
    chrome_options.add_argument(f"--user-data-dir={CHROME_PROFILE_DIR}")
    chrome_options.add_argument("--no-first-run")
    chrome_options.add_argument("--disable-popup-blocking")
    chrome_options.add_argument("--disable-features=Translate")
    # Align driver with Chrome 141 to reduce startup issues
    try:
        drv = uc.Chrome(options=chrome_options, version_main=141)
    except TypeError:
        # Older uc versions don't support version_main
        drv = uc.Chrome(options=chrome_options)
    return drv

def load_manifest() -> Dict[str, Any]:
    if os.path.exists(MANIFEST_PATH):
        try:
            with open(MANIFEST_PATH, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_manifest(manifest: Dict[str, Any]) -> None:
    tmp_path = MANIFEST_PATH + '.tmp'
    with open(tmp_path, 'w', encoding='utf-8') as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    os.replace(tmp_path, MANIFEST_PATH)

def compute_note_id(data: Dict[str, Any]) -> str:
    """Stable hash of note content to prevent duplicates across runs."""
    title = data.get('title', '') or ''
    txt = data.get('textContent', '') or ''
    items = data.get('listContent', []) or []
    is_pinned = data.get('isPinned', False)
    is_archived = data.get('isArchived', False)
    color = data.get('color', 'DEFAULT') or 'DEFAULT'
    labels = data.get('labels', []) or []
    label_names: List[str] = []
    for lab in labels:
        if isinstance(lab, dict):
            n = lab.get('name') or lab.get('label')
            if n:
                label_names.append(n)
        elif isinstance(lab, str):
            label_names.append(lab)
    payload = {
        'title': title,
        'text': txt,
        'items': [(it.get('text', ''), bool(it.get('isChecked', False))) for it in items],
        'pinned': bool(is_pinned),
        'archived': bool(is_archived),
        'color': color,
        'labels': sorted(label_names),
    }
    blob = json.dumps(payload, sort_keys=True, ensure_ascii=False).encode('utf-8')
    return hashlib.sha1(blob).hexdigest()

def short_sleep(a=0.2, b=0.6):
    time.sleep(random.uniform(a, b))

def get_title_input(driver):
    # Prefer visible contenteditable Title
    try:
        el = WebDriverWait(driver, 6).until(
            EC.visibility_of_element_located((By.CSS_SELECTOR, 'div[contenteditable="true"][aria-label="Title"]'))
        )
        debug_log('Title input found (contenteditable div, aria-label="Title").')
        return el
    except TimeoutException:
        pass
    # Visible input variants
    try:
        el = WebDriverWait(driver, 8).until(
            EC.visibility_of_element_located((By.CSS_SELECTOR, 'input[aria-label*="Title" i], input[placeholder*="Title" i]'))
        )
        debug_log('Title input found (input).')
        return el
    except TimeoutException:
        pass
    # Visible contenteditable Title variants
    try:
        el = WebDriverWait(driver, 6).until(
            EC.visibility_of_element_located((By.CSS_SELECTOR, 'div[contenteditable="true"][aria-label*="Title" i], div[placeholder*="Title" i]'))
        )
        debug_log('Title input found (contenteditable div).')
        return el
    except TimeoutException:
        pass

    # Structural fallback: pick the nearest visible editable field above the content editor (exclude the body)
    try:
        body = get_content_editor(driver)
        body_y = body.location.get('y', 10**9)
        candidates = driver.find_elements(By.CSS_SELECTOR, 'input[type="text"], div[contenteditable="true"], div[role="textbox"]')
        visibles = []
        for c in candidates:
            try:
                if not c.is_displayed():
                    continue
                cy = c.location.get('y', 10**9)
                same_place = abs(cy - body_y) < 2 and abs(c.rect.get('height', 0) - body.rect.get('height', 0)) < 2
                if cy < body_y - 2 and not same_place and c.rect.get('height', 0) > 0 and c.rect.get('width', 0) > 0:
                    visibles.append((cy, c))
            except Exception:
                continue
        if visibles:
            visibles.sort(key=lambda t: t[0], reverse=True)
            el = visibles[0][1]
            debug_log('Title input found via structural fallback.')
            return el
    except Exception:
        pass

    debug_log('Title input not found; proceeding without setting a title.')
    raise TimeoutException('Title input not found')
def wait_for_keep_url(driver, timeout=300):
    wait = WebDriverWait(driver, timeout)
    debug_log('Waiting for keep.google.com URL...')
    return wait.until(lambda d: isinstance(getattr(d, 'current_url', ''), str) and 'keep.google.com' in d.current_url)

def wait_for_keep_ready(driver):
    # Robust readiness: presence of any editor/composer nodes
    wait = WebDriverWait(driver, 300)
    debug_log(f"Current URL before readiness: {getattr(driver, 'current_url', '')}")
    try:
        wait.until(lambda d: isinstance(getattr(d, 'current_url', ''), str) and 'keep.google.com' in d.current_url)
    except Exception:
        pass
    selectors = [
        'div[role="button"][aria-label^="Take a note"]',
        '[aria-label^="Take a note"]',
        'div[aria-label="Note"]',
        'div[role="textbox"]',
        'input[aria-label="Title"]',
        'div[aria-label="Title"]',
    ]
    def any_present(d):
        try:
            for sel in selectors:
                if d.find_elements(By.CSS_SELECTOR, sel):
                    return True
            return False
        except Exception:
            return False
    wait.until(lambda d: any_present(d))
    debug_log('Keep editor/composer presence detected.')
    snap(driver, 'keep_ready_presence')

def open_compact_composer(driver):
    # Ensure we are on an active window
    try:
        if getattr(driver, 'window_handles', []):
            driver.switch_to.window(driver.window_handles[-1])
    except Exception:
        pass

    selectors_css = [
        'div[role="button"][aria-label^="Take a note"]',
        '[aria-label^="Take a note"]',
        'div[aria-label="Take a note"]',
        'div[aria-label="Take a note…"]',
    ]
    selectors_xpath = [
        "//div[@role='button' and contains(translate(@aria-label,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'note')]",
        "//*[contains(translate(@aria-label,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'take a note')]",
    ]
    for sel in selectors_css:
        try:
            comp = WebDriverWait(driver, 8).until(EC.element_to_be_clickable((By.CSS_SELECTOR, sel)))
            try:
                comp.click()
            except Exception:
                driver.execute_script("arguments[0].click();", comp)
            short_sleep()
            snap(driver, f'composer_opened_{sanitize_filename(sel)}')
            return True
        except Exception:
            continue
    for xp in selectors_xpath:
        try:
            comp = WebDriverWait(driver, 8).until(EC.presence_of_element_located((By.XPATH, xp)))
            try:
                driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", comp)
            except Exception:
                pass
            short_sleep(0.05, 0.15)
            try:
                comp.click()
            except Exception:
                try:
                    driver.execute_script("arguments[0].click();", comp)
                except Exception:
                    pass
            short_sleep()
            snap(driver, 'composer_opened_xpath')
            return True
        except Exception:
            continue
    try:
        editor = WebDriverWait(driver, 5).until(EC.presence_of_element_located((By.CSS_SELECTOR, 'div[role="textbox"]')))
        try:
            editor.click()
        except Exception:
            driver.execute_script("arguments[0].click();", editor)
        short_sleep()
        snap(driver, 'composer_opened_textbox')
        return True
    except Exception:
        snap(driver, 'composer_open_failed', html=True)
        return False

def start_new_list_note(driver) -> bool:
    # Try "New list" button near composer; fallback: open text note then toggle checkboxes from More menu
    selectors = [
        'div[aria-label="New list"]',
        'button[aria-label="New list"]',
        'div[aria-label^="New list"]',
        'button[aria-label*="list"]',
    ]
    for sel in selectors:
        try:
            btn = WebDriverWait(driver, 5).until(EC.element_to_be_clickable((By.CSS_SELECTOR, sel)))
            btn.click()
            short_sleep()
            return True
        except Exception:
            continue
    # Fallback: open text note and try to toggle checkboxes via More > Show checkboxes
    if open_compact_composer(driver):
        try:
            more_btn = WebDriverWait(driver, 5).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, '[aria-label*="More"]'))
            )
            more_btn.click()
            short_sleep()
            # Look for menu item containing 'checkbox'
            menu_item = WebDriverWait(driver, 5).until(
                EC.element_to_be_clickable((By.XPATH, "//div[@role='menuitem' and (contains(., 'checkbox') or contains(., 'Checkbox'))]"))
            )
            menu_item.click()
            short_sleep()
            return True
        except Exception:
            return False
    return False

def get_title_input(driver):
    # Prefer explicit contenteditable Title (visible)
    try:
        el = WebDriverWait(driver, 6).until(
            EC.visibility_of_element_located((By.CSS_SELECTOR, 'div[contenteditable="true"][aria-label="Title"]'))
        )
        debug_log('Title input found (contenteditable div, aria-label="Title").')
        return el
    except TimeoutException:
        pass
    # Input variants (visible)
    try:
        el = WebDriverWait(driver, 8).until(
            EC.visibility_of_element_located((By.CSS_SELECTOR, 'input[aria-label*="Title" i], input[placeholder*="Title" i]'))
        )
        debug_log('Title input found (input).')
        return el
    except TimeoutException:
        pass
    # Contenteditable variants (visible)
    try:
        el = WebDriverWait(driver, 6).until(
            EC.visibility_of_element_located((By.CSS_SELECTOR, 'div[contenteditable="true"][aria-label*="Title" i], div[placeholder*="Title" i]'))
        )
        debug_log('Title input found (contenteditable div).')
        return el
    except TimeoutException:
        pass

    # Structural fallback: pick the editable field above the content editor (exclude body)
    try:
        body = get_content_editor(driver)
        body_y = body.location.get('y', 10**9)
        candidates = driver.find_elements(By.CSS_SELECTOR, 'input[type="text"], div[contenteditable="true"], div[role="textbox"]')
        # Filter visible and above the body
        visibles = []
        for c in candidates:
            try:
                if not c.is_displayed():
                    continue
                cy = c.location.get('y', 10**9)
                same_place = abs(cy - body_y) < 2 and abs(c.rect.get('height', 0) - body.rect.get('height', 0)) < 2
                if cy < body_y - 2 and not same_place and c.rect.get('height', 0) > 0 and c.rect.get('width', 0) > 0:
                    visibles.append((cy, c))
            except Exception:
                continue
        if visibles:
            visibles.sort(key=lambda t: t[0], reverse=True)  # closest above the body
            el = visibles[0][1]
            debug_log('Title input found via structural fallback.')
            return el
    except Exception:
        pass

    debug_log('Title input not found; proceeding without setting a title.')
    raise TimeoutException('Title input not found')

def ensure_title_set(driver, editor_el, title: str) -> bool:
    """Ensure the title is set in the visible Title field; return True on success."""
    if not title:
        return True
    # Try direct element
    try:
        title_el = get_title_input(driver)
        _send_text_to_element(driver, title_el, title)
        # Verify; if mismatch, force-set and fire events
        try:
            val = (title_el.get_attribute('value') or title_el.text or '').strip()
            if val != (title or '').strip():
                driver.execute_script(
                    "if(arguments[0].isContentEditable){arguments[0].innerText=arguments[1]; arguments[0].dispatchEvent(new InputEvent('input',{bubbles:true}));} else {arguments[0].value=arguments[1]; arguments[0].dispatchEvent(new Event('input',{bubbles:true}));}",
                    title_el, title or ''
                )
                short_sleep(0.05, 0.12)
        except Exception:
            pass
        return True
    except Exception:
        pass

    # Fallback: Focus body editor and SHIFT+TAB until Title receives focus
    try:
        from selenium.webdriver.common.keys import Keys
        if editor_el is not None:
            editor_el.click()
            short_sleep(0.05, 0.12)
            for _ in range(3):
                try:
                    editor_el.send_keys(Keys.SHIFT, Keys.TAB)
                    short_sleep(0.1, 0.2)
                    active = driver.switch_to.active_element
                    aria = (active.get_attribute('aria-label') or '').lower()
                    if 'title' in aria:
                        _send_text_to_element(driver, active, title)
                        try:
                            val = (active.get_attribute('value') or active.text or '').strip()
                            if val != (title or '').strip():
                                driver.execute_script(
                                    "if(arguments[0].isContentEditable){arguments[0].innerText=arguments[1]; arguments[0].dispatchEvent(new InputEvent('input',{bubbles:true}));} else {arguments[0].value=arguments[1]; arguments[0].dispatchEvent(new Event('input',{bubbles:true}));}",
                                    active, title or ''
                                )
                                short_sleep(0.05, 0.12)
                        except Exception:
                            pass
                        return True
                except Exception:
                    continue
    except Exception:
        pass
    return False

def get_content_editor(driver):
    # Editor area for note body
    try:
        el = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, 'div[aria-label="Note"]'))
        )
        debug_log('Content editor found (aria-label="Note").')
        return el
    except TimeoutException:
        try:
            el = WebDriverWait(driver, 5).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, 'div[role="textbox"]'))
            )
            debug_log('Content editor found (role="textbox").')
            return el
        except TimeoutException:
            el = WebDriverWait(driver, 5).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, 'div[contenteditable="true"]'))
            )
            debug_log('Content editor found (contenteditable=true).')
            return el

def _send_text_to_element(driver, el, text: str):
    """Robustly send text to an input or contenteditable element and trigger input events."""
    from selenium.webdriver.common.keys import Keys
    try:
        el.click()
    except Exception:
        try:
            driver.execute_script("arguments[0].click();", el)
        except Exception:
            pass
    short_sleep(0.05, 0.15)

    # Select all and clear (platform-aware)
    try:
        if sys.platform == 'darwin':
            el.send_keys(Keys.COMMAND, 'a')
        else:
            el.send_keys(Keys.CONTROL, 'a')
        short_sleep(0.02, 0.08)
        el.send_keys(Keys.BACK_SPACE)
    except Exception:
        pass

    # Type text in chunks to avoid flakiness on long strings
    try:
        if text:
            for chunk_start in range(0, len(text), 200):
                chunk = text[chunk_start:chunk_start+200]
                el.send_keys(chunk)
                short_sleep(0.01, 0.03)
            # Nudge an extra input event
            el.send_keys(' ')
            el.send_keys(Keys.BACK_SPACE)
    except Exception:
        # JS fallback for contenteditable elements
        try:
            driver.execute_script(
                "if (arguments[0].isContentEditable) {arguments[0].innerText = arguments[1]; arguments[0].dispatchEvent(new InputEvent('input', {bubbles:true}));}",
                el, text or ''
            )
        except Exception:
            pass
    short_sleep(0.05, 0.15)

def set_pinned_state(driver, should_pin: bool):
    try:
        pin_btn = WebDriverWait(driver, 5).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, '[aria-label*="Pin note"], [aria-label*="Unpin note"]'))
        )
        label = pin_btn.get_attribute('aria-label') or ''
        if should_pin and 'Pin note' in label:
            pin_btn.click()
        elif not should_pin and 'Unpin note' in label:
            pin_btn.click()
        short_sleep()
    except Exception:
        pass

def set_archive_state(driver, should_archive: bool):
    if not should_archive:
        return False
    try:
        arch_btn = WebDriverWait(driver, 5).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, '[aria-label="Archive"]'))
        )
        arch_btn.click()
        short_sleep()
        return True  # Archiving usually closes the editor
    except Exception:
        return False

def set_color(driver, color_key: str):
    if not color_key:
        return
    keep_color = COLOR_MAP.get(color_key.upper())
    if not keep_color:
        return
    try:
        palette_btn = WebDriverWait(driver, 5).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, '[aria-label="Background options"]'))
        )
        palette_btn.click()
        short_sleep()
        # Pick color by aria-label
        opt = WebDriverWait(driver, 5).until(
            EC.element_to_be_clickable((By.XPATH, f"//div[@role='menuitem' or @role='button'][@aria-label='{keep_color}']"))
        )
        opt.click()
        short_sleep()
    except Exception:
        pass

def add_labels(driver, labels: List[str]):
    if not labels:
        return
    try:
        more_btn = WebDriverWait(driver, 5).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, '[aria-label*="More"]'))
        )
        more_btn.click()
        short_sleep()
        # Try find Add/Change labels menu
        try:
            label_menu = WebDriverWait(driver, 5).until(
                EC.element_to_be_clickable((By.XPATH, "//div[@role='menuitem' and (contains(., 'label') or contains(., 'Label'))]"))
            )
            label_menu.click()
            short_sleep()
        except Exception:
            pass

        # Look for labels input
        input_box = WebDriverWait(driver, 5).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, 'input[aria-label*="Label"], input[type="text"]'))
        )
        for lab in labels:
            input_box.clear()
            input_box.send_keys(lab)
            short_sleep(0.1, 0.2)
            # Select match (Enter)
            from selenium.webdriver.common.keys import Keys
            input_box.send_keys(Keys.ENTER)
            short_sleep(0.1, 0.2)

        # Close labels dialog with Escape
        from selenium.webdriver.common.keys import Keys
        input_box.send_keys(Keys.ESCAPE)
        short_sleep()
    except Exception:
        pass

def close_note(driver):
    # Prefer Close button; fallback to Done; final fallback: click outside
    selectors = [
        '[aria-label="Close"]',
        '[data-tooltip="Close"]',
        'div[data-tooltip-text="Done"]',
        '[aria-label*="Done" i]',
        'button[aria-label*="Close" i]',
        'div[role="button"][aria-label*="Close" i]',
    ]
    for sel in selectors:
        try:
            btn = WebDriverWait(driver, 5).until(EC.element_to_be_clickable((By.CSS_SELECTOR, sel)))
            btn.click()
            short_sleep()
            snap(driver, 'note_closed')
            # Wait for editor to disappear
            try:
                WebDriverWait(driver, 5).until_not(
                    EC.presence_of_element_located((By.CSS_SELECTOR, 'input[aria-label="Title"], div[aria-label="Title"], div[aria-label="Note"], div[role="textbox"]'))
                )
            except Exception:
                # try ESC to close
                try:
                    from selenium.webdriver.common.keys import Keys
                    driver.switch_to.active_element.send_keys(Keys.ESCAPE)
                    short_sleep(0.2, 0.4)
                    WebDriverWait(driver, 4).until_not(
                        EC.presence_of_element_located((By.CSS_SELECTOR, 'input[aria-label="Title"], div[aria-label="Title"], div[aria-label="Note"], div[role="textbox"]'))
                    )
                except Exception:
                    pass
            return True
        except Exception:
            continue
    try:
        # keyboard fallback first
        try:
            from selenium.webdriver.common.keys import Keys
            driver.switch_to.active_element.send_keys(Keys.ESCAPE)
            short_sleep(0.2, 0.4)
            WebDriverWait(driver, 3).until_not(
                EC.presence_of_element_located((By.CSS_SELECTOR, 'input[aria-label="Title"], div[aria-label="Title"], div[aria-label="Note"], div[role="textbox"]'))
            )
            snap(driver, 'note_closed_escape')
            return True
        except Exception:
            pass
        driver.find_element(By.TAG_NAME, 'body').click()
        short_sleep()
        snap(driver, 'note_closed_body')
        return True
    except Exception:
        snap(driver, 'note_close_failed', html=True)
        return False

def _xpath_literal(s: str) -> str:
    if "'" not in s:
        return f"'{s}'"
    if '"' not in s:
        return '"' + s + '"'
    # contains both quotes, use concat
    parts = s.split("'")
    tokens = []
    # first part
    tokens.append("'" + parts[0] + "'")
    for p in parts[1:]:
        tokens.append("\"'\"")  # a double-quoted single-quote character
        tokens.append("'" + p + "'")
    return "concat(" + ", ".join(tokens) + ")"

def verify_note_present(driver, title: str, content: str, timeout: int = 12, refresh_once: bool = True) -> bool:
    """Verify a note card with the given title/content snippet is visible on the main page."""
    candidates = []
    if title and title.strip():
        candidates.append(title.strip()[:60])
    if content and content.strip():
        candidates.append(content.strip()[:60])
    # dedupe while preserving order
    seen = set()
    queries = [q for q in candidates if not (q in seen or seen.add(q))]
    if not queries:
        return False

    def search_once(q: str) -> bool:
        try:
            xp = f"//div[@role='main']//*[contains(normalize-space(), {_xpath_literal(q)})]"
            els = driver.find_elements(By.XPATH, xp)
            return len(els) > 0
        except Exception:
            return False

    # Try each query with live DOM wait
    end = time.time() + timeout
    while time.time() < end:
        for q in queries:
            if search_once(q):
                debug_log(f"Verified note appears with text snippet: {q!r}")
                return True
        short_sleep(0.2, 0.5)

    # Refresh once and retry
    if refresh_once:
        try:
            driver.refresh()
            short_sleep(1.0, 1.6)
        except Exception:
            pass
        end = time.time() + max(4, timeout // 2)
        while time.time() < end:
            for q in queries:
                if search_once(q):
                    debug_log(f"Verified after refresh: {q!r}")
                    return True
            short_sleep(0.2, 0.5)

    # Fallback: use Keep's search to look for the note
    try:
        from selenium.webdriver.common.keys import Keys
        search_box = WebDriverWait(driver, 5).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, 'input[aria-label*="Search" i], input[placeholder*="Search" i]'))
        )
        for q in queries:
            try:
                search_box.click()
            except Exception:
                driver.execute_script("arguments[0].click();", search_box)
            search_box.clear()
            search_box.send_keys(q)
            short_sleep(0.3, 0.6)
            xp = f"//div[@role='main']//*[contains(normalize-space(), {_xpath_literal(q)})]"
            end = time.time() + 6
            while time.time() < end:
                els = driver.find_elements(By.XPATH, xp)
                if els:
                    debug_log(f"Verified via search: {q!r}")
                    search_box.send_keys(Keys.ESCAPE)
                    short_sleep(0.2, 0.4)
                    return True
                short_sleep(0.2, 0.4)
            # clear for next query
            search_box.send_keys(Keys.ESCAPE)
            short_sleep(0.2, 0.4)
    except Exception:
        pass
    debug_log(f"Could not verify note presence for any of: {queries!r}")
    return False

# --- Main Script ---
driver = None  # Initialize driver to None
manifest = load_manifest()
created_ids_in_run = set()
try:
    # Parse CLI args
    parser = argparse.ArgumentParser(description='Google Keep UI Migration')
    parser.add_argument('--debug', action='store_true', help='Enable debug screenshots and verbose logs')
    parser.add_argument('--limit', type=int, default=None, help='Limit number of notes to import this run')
    args = parser.parse_args()
    DEBUG = args.debug
    LIMIT = args.limit
    if DEBUG:
        ensure_dir(DEBUG_DIR)
        print(f"Debug mode ON. Artifacts in: {DEBUG_DIR}")

    # 1. Create the driver instance
    print("Initializing browser...")
    driver = create_driver()
    
    # 2. Add a pause to let the browser initialize fully
    time.sleep(3) 

    # 3. Open Google Keep and wait for manual login (first run) or until main page loads (subsequent runs)
    print("Opening Google Keep...")
    driver.get("https://keep.google.com/#home")

    print("="*40)
    print("ACTION REQUIRED:")
    print("Please log in to your destination Google Account in the browser window.")
    print("The script will resume once you are on the main Keep page.")
    print("="*40)

    # Wait for composer (more resilient than relying on a specific sidebar link)
    # If the window is closed or crashes, recreate the driver and try once more.
    try:
        # Ensure we actually landed on the Keep app, then check editor presence
        try:
            wait_for_keep_url(driver, timeout=300)
        except Exception:
            pass
        wait_for_keep_ready(driver)
    except (WebDriverException, TimeoutException, Exception) as e:
        print(f"Could not detect Keep composer: {e}")
        snap(driver, 'keep_ready_exception', html=True)
        # Attempt one restart if window was closed
        try:
            if not getattr(driver, 'window_handles', []):
                debug_log('Window closed. Recreating driver and retrying...')
                try:
                    driver.quit()
                except Exception:
                    pass
                driver = create_driver()
                time.sleep(2)
                driver.get("https://keep.google.com")
                wait_for_keep_ready(driver)
            else:
                raise
        except Exception as e2:
            print(f"Retry failed: {e2}")
            sys.exit(1)
    print("Login detected. Starting note creation in 5 seconds...")
    time.sleep(5)

    # Find and process all .json files (recursive)
    json_files: List[str] = []
    for root, _, files in os.walk(NOTES_DIR):
        for f in files:
            if f.endswith('.json'):
                full_path = os.path.join(root, f)
                # Skip our manifest file if it's inside the scan directory
                if os.path.abspath(full_path) == os.path.abspath(MANIFEST_PATH):
                    continue
                json_files.append(full_path)

    print(f"Found {len(json_files)} JSON file(s) in: {NOTES_DIR}")
    if not json_files:
        print("No .json files found. Please verify NOTES_DIR and that your Takeout JSON files are present.")
        raise SystemExit(1)

    if LIMIT is not None and LIMIT > 0:
        json_files = json_files[:LIMIT]
        print(f"Limiting to first {LIMIT} file(s) for this run.")

    for file_path in json_files:
        filename = os.path.basename(file_path)
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        title = data.get('title', '') or ''
        content = data.get('textContent', '') or ''
        items = data.get('listContent', []) or []
        color_key = data.get('color', 'DEFAULT') or 'DEFAULT'
        is_pinned = bool(data.get('isPinned', False))
        is_archived = bool(data.get('isArchived', False))
        labels = []
        raw_labels = data.get('labels', []) or []
        for lab in raw_labels:
            if isinstance(lab, dict):
                name = lab.get('name') or lab.get('label')
                if name:
                    labels.append(name)
            elif isinstance(lab, str):
                labels.append(lab)
        if IMPORT_LABEL:
            labels.append(IMPORT_LABEL)

        note_id = compute_note_id(data)
        if note_id in manifest or note_id in created_ids_in_run:
            # Validate manifest entry by checking the note exists; if missing, self-heal and re-import
            if verify_note_present(driver, title, content):
                print(f"Skipping already imported note: '{title}'")
                continue
            else:
                print(f"Manifest had '{title}' but it is not visible. Will re-import it.")
                manifest.pop(note_id, None)
                save_manifest(manifest)
        
        if not title and not content and not items:
            continue

        print(f"Creating note: '{title}'")
        debug_log(f"Labels: {labels}; Pinned: {is_pinned}; Archived: {is_archived}; Color: {color_key}")
        if DEBUG:
            # Selector diagnostics
            try:
                elems = driver.find_elements(By.CSS_SELECTOR, 'div[role="button"][aria-label^="Take a note"]')
                debug_log(f"Compact composer candidates: {len(elems)}")
            except Exception:
                pass

        try:
            # Decide note type: checklist if listContent present, else text note
            if items:
                if not start_new_list_note(driver):
                    # fallback to text note
                    if not open_compact_composer(driver):
                        raise RuntimeError('Cannot open composer')
            else:
                if not open_compact_composer(driver):
                    raise RuntimeError('Cannot open composer')

            # Expand editor first to ensure title is present
            editor = None
            try:
                editor = get_content_editor(driver)
            except Exception:
                pass
            # Click editor to fully expand title region
            try:
                if editor is not None:
                    editor.click()
                    short_sleep(0.05, 0.12)
            except Exception:
                pass
            # Click the editor to fully expand header/title region
            try:
                if editor is not None:
                    editor.click()
                    short_sleep(0.05, 0.12)
            except Exception:
                pass

            # Fill title (after editor presence to ensure expanded UI)
            try:
                if title:
                    title_input = get_title_input(driver)
                    _send_text_to_element(driver, title_input, title)
            except Exception:
                # As a fallback, focus body and SHIFT+TAB (try up to 3 times) to move to title, then type
                if title and editor is not None:
                    try:
                        from selenium.webdriver.common.keys import Keys
                        editor.click()
                        short_sleep(0.05, 0.12)
                        success = False
                        for _ in range(3):
                            try:
                                editor.send_keys(Keys.SHIFT, Keys.TAB)
                                short_sleep(0.1, 0.2)
                                active = driver.switch_to.active_element
                                aria = (active.get_attribute('aria-label') or '').lower()
                                if 'title' in aria:
                                    _send_text_to_element(driver, active, title)
                                    success = True
                                    debug_log('Title entered via SHIFT+TAB fallback.')
                                    break
                            except Exception:
                                continue
                        if not success:
                            debug_log('Title entry SHIFT+TAB fallback did not succeed.')
                    except Exception:
                        debug_log('Title entry fallback failed.')

            # Fill body content or checklist items
            try:
                if editor is None:
                    editor = get_content_editor(driver)
                if items:
                    # Add checklist items
                    from selenium.webdriver.common.keys import Keys
                    for it in items:
                        text = it.get('text', '') or ''
                        if not text:
                            continue
                        editor.click()
                        editor.send_keys(text)
                        editor.send_keys(Keys.ENTER)
                        short_sleep(0.05, 0.15)
                    # Checked state is difficult to set reliably via UI; best-effort omitted
                else:
                    if content:
                        _send_text_to_element(driver, editor, content)
            except Exception as body_err:
                debug_log(f"Error entering body content: {body_err}")
            # Apply pin, color, labels
            set_pinned_state(driver, is_pinned)
            set_color(driver, color_key)
            add_labels(driver, labels)

            # Archive if requested (this usually closes the note)
            archived_closed = set_archive_state(driver, is_archived)
            if not archived_closed:
                close_note(driver)

            short_sleep(0.5, 1.0)

            # Verify the note card appears before recording manifest (skip for archived)
            verified = True
            if not is_archived:
                verified = verify_note_present(driver, title, content)
            if not verified:
                raise RuntimeError('Note not visible after save; verification failed')

            # Mark as imported
            manifest[note_id] = {
                'file': filename,
                'title': title,
                'ts': int(time.time()),
            }
            created_ids_in_run.add(note_id)
            save_manifest(manifest)

        except Exception as e:
            print(f"  -> Failed to create note '{title}'. Error: {e}")
            try:
                snap(driver, f"error_{sanitize_filename(title)}", html=True)
                driver.refresh()
            except Exception:
                pass
            time.sleep(5)

    print("\n✅ Migration process complete!")

finally:
    if driver:
        driver.quit()