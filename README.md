# Google Keep Import (UI Automation)

A Python script that migrates Google Keep notes from Google Takeout JSON files into a destination Google account by automating the Keep web UI with Selenium and undetected-chromedriver.

Key goals:
- Creates new notes only. It never edits or deletes existing notes.
- Idempotent via a local manifest (avoids duplicates across re-runs).
- Supports titles, plain text content, basic checklists, pin/archive, colors, and labels (best-effort).
- Persistent Chrome profile so you log in once.

Note: This script does not use any private Google APIs. It automates the browser UI you control.

## Requirements

- macOS with Google Chrome installed (stable).
- Python 3.9+ (tested with 3.11).
- Python packages:
  - selenium
  - undetected-chromedriver

Install:
```bash
python3 -m pip install --upgrade pip
python3 -m pip install selenium undetected-chromedriver
```

## Project layout

- migrate_keep_notes.py — the importer script
- .gitignore — repository ignores everything except the script and README
- import_manifest.json — created automatically to track imported notes
- .chrome-profile/ — persistent Chrome user data dir (created on first run)
- .debug/ — optional debug screenshots and HTML (created when --debug is used)

## Prepare your notes

- Place your exported Keep JSON files under the folder configured by `NOTES_DIR` in the script.
  - Default in this repo: `GKeepImport/Keep/`
  - You can change `NOTES_DIR` near the top of the script if your files are elsewhere.
- The script scans the directory recursively and imports all `.json` files it finds (excluding the manifest).

## Usage

From the repo root:
```bash
python3 migrate_keep_notes.py
```

Recommended on first runs:
```bash
# Save debug artifacts and limit to first N files to validate the flow
python3 migrate_keep_notes.py --debug --limit 1
```

What happens:
1) A Chrome window opens on keep.google.com.
2) Action required (first run): log in to your destination Google account in the opened window.
   - A persistent profile is stored in `.chrome-profile/`, so subsequent runs won’t ask again.
3) The script detects the Keep home page and begins importing notes.

Flags:
- `--debug`  Save screenshots/HTML in `.debug/` to aid troubleshooting.
- `--limit N` Import only the first N JSON files for a test run.

## Features

- Titles and content:
  - Opens the “Take a note…” composer, expands the editor, sets the Title, then the body content.
  - Robust title detection for the contenteditable Title field (aria-label="Title").
- Checklists:
  - If `listContent` exists, creates a list note and adds items line-by-line.
  - Checked/unchecked state is not guaranteed due to UI variability (best-effort omitted).
- Pin/archive:
  - Applies pinned state.
  - Archives when `isArchived` is true (note: archived notes won’t appear on the main grid).
- Colors:
  - Applies a best-effort color mapping (`COLOR_MAP` in the script).
- Labels:
  - Tries to add labels via the label dialog. If `IMPORT_LABEL` is set in the script, it adds that too.
- Idempotency:
  - Each note gets a stable content hash (title + content + items + metadata).
  - The script writes to `import_manifest.json` only after verifying the note appears.
  - If a manifest entry exists but the note isn’t visible, it “self-heals” by removing the entry and re-importing.

## Verification and safety

- After closing a note, the script verifies it appears on the grid (or via Keep’s search).
- It updates the manifest only on successful verification.
- Existing notes in your account are never modified or deleted.

## Configuration

Edit near the top of `migrate_keep_notes.py`:
- `NOTES_DIR` Path to your exported JSONs.
- `IMPORT_LABEL` Optional label to tag imported notes (e.g., `"Imported from JSON"`).
- `COLOR_MAP` Mapping from Takeout color keys to Keep’s color names.

## Troubleshooting

- It “does nothing” after login:
  - Ensure JSON files are under `NOTES_DIR`. The script prints “Found X JSON file(s)…”.
  - Use `--debug` to save `.debug/*keep_ready_presence.png` and `.html` artifacts.
- “Cannot open composer”:
  - UI variants/locales can differ. The script tries multiple selectors; enable `--debug` and share the latest `.debug/composer_open_failed.*` for adjustment.
- Title not set / content becomes the title:
  - Keep promotes the first line of the body to the title when no Title is set. The script now:
    - Expands the editor first.
    - Targets `div[contenteditable="true"][aria-label="Title"]` to set the title before content.
- Note not visible after save:
  - The script refreshes and uses Keep’s search to verify. If still not found, it logs a detailed error and does not mark the manifest.
- Archived notes:
  - They may not appear on the main grid. The script skips the grid verification when archiving is requested.

## Known limitations

- Creation/edited timestamps from Takeout cannot be set via the UI.
- Checklist checked-state is not reliably set via automation.
- Attachments/images/audio aren’t imported.
- Labels are best-effort and may require matching existing label names.

## Tips

- First run will require manual login. Subsequent runs reuse `.chrome-profile/`.
- Re-runs are safe and won’t duplicate previously imported notes (thanks to the manifest).
- If Chrome doesn’t launch or closes early:
  - Ensure Chrome is installed and up to date.
  - Reinstall undetected-chromedriver: `python3 -m pip install -U undetected-chromedriver`
  - Delete `.chrome-profile/` for a clean session if needed (you’ll need to log in again).

## License

Personal use only. Use responsibly and at your own discretion.

