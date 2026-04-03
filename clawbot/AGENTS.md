# Clawbot — Agent Reorientation Guide

This file helps a new Claude Code session pick up where the last one left off.

## What is this project?

An automated crawler that downloads economics replication packages from openICPSR (the AEA data repository). It reads each package's README with Claude Sonnet to decide if all data is publicly available, then downloads qualifying packages.

The downloaded packages feed into [davehedengren/replication-studies](https://github.com/davehedengren/replication-studies), where Claude Code replicates the papers and runs robustness checks.

## Architecture at a glance

```
Chrome (real browser, port 9222)
  ↑ CDP connection
  |
Playwright (Python) ← controls browser navigation + page interactions
  |
main.py / retry_failed.py / recheck.py  ← orchestrators
  |
analyzer.py → reads README via JS fetch() → sends to Claude Sonnet API
  |
downloader.py → accepts Terms, clicks download, watches ~/Downloads/
  |
download_staging/ → move_to_external.sh → /Volumes/Elements/AER_replication_data/
```

## Critical things to know

### 1. Must use real Chrome via CDP
Playwright's own Chromium gets blocked by Cloudflare. Always connect to a user-launched Chrome:
```bash
/Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome \
    --remote-debugging-port=9222 --no-first-run \
    --user-data-dir="$HOME/chrome-debug-profile"
```

### 2. Check for zombie processes FIRST
Previous sessions left orphaned Python processes that controlled Chrome simultaneously. Before ANY run:
```bash
ps aux | grep -E "python3.*(main|retry|recheck)" | grep -v grep
```
Kill all of them before starting. `pkill -f` only kills foreground; use `kill -9 <pid>` for backgrounded ones.

### 3. Downloads go through staging
Playwright can't write to external drives (macOS sandbox). Flow:
- Chrome downloads to `~/Downloads/` (native)
- `downloader.py` watches for completion, moves to `download_staging/`
- `move_to_external.sh` moves from staging to `/Volumes/Elements/AER_replication_data/`

### 4. The CSV is the source of truth
`project_log.csv` tracks every project checked. `download_tracker.json` is a convenience summary that can drift — reconcile from the CSV if numbers look wrong:
```python
import csv
d = sum(1 for r in csv.DictReader(open('project_log.csv')) if r['downloaded']=='True')
t = sum(1 for _ in csv.DictReader(open('project_log.csv')))
print(f'{d} downloaded, {t} checked')
```

### 5. Session expiry handling
ICPSR sessions expire. The auth module:
- Tries clicking "Sign in with Google" (works if Chrome is signed into Google)
- Falls back to waiting up to 12 hours for manual login
- Checks every 30 seconds, prints reminders every 10 minutes

### 6. Polite delays
30-60 second random delays between requests. Don't reduce below 30s — openICPSR will rate-limit or block.

### 7. Keep Mac awake
```bash
caffeinate -dims -w $(pgrep -f "python3 main.py" | head -1) &
```

## State files

| File | What it tracks |
|------|---------------|
| `project_log.csv` | Every project: ID, title, classification, rationale, download status |
| `download_tracker.json` | Last search page, download count (may be stale) |
| `recheck_queue.json` | Cached missed IDs from Phase 1 scan (avoids re-scanning) |
| `session.json` | Legacy — not used with CDP approach |

## Common tasks

### Resume the main crawl
```bash
cd ~/code/clawbot
ps aux | grep python3 | grep -v grep  # check for zombies
python3 main.py
```

### Retry failed downloads
```bash
python3 retry_failed.py
```

### Find and process missed projects
```bash
python3 recheck.py
```
Phase 1 scans search pages 1-N for IDs not in CSV (~5 min).
Phase 2 processes each missed project (~1 min each with delays).
Saves queue on Ctrl+C so Phase 1 can be skipped on restart.

### Check what's on the external drive vs what's in the CSV
```bash
ls /Volumes/Elements/AER_replication_data/ | sed 's/-V1.zip//' | sed 's/.zip//' | sort -n > /tmp/on_disk.txt
python3 -c "
import csv
with open('project_log.csv') as f:
    for r in csv.DictReader(f):
        if r['downloaded']=='True':
            print(r['project_id'])
" | sort -n > /tmp/in_csv.txt
diff /tmp/on_disk.txt /tmp/in_csv.txt
```

### Move staging to external drive
```bash
./move_to_external.sh
```

## What went wrong last session (lessons learned)

1. **Zombie processes**: `pkill` only kills foreground process. Background processes from `run_in_background=true` survive and keep controlling Chrome. Always use `ps aux` to find them all.
2. **Playwright temp artifacts**: Each Playwright session creates temp dirs in `/var/folders/.../playwright-artifacts-*`. These accumulated to 6+ GB. Now cleaned up by `cleanup.py`.
3. **Double downloads**: Playwright's `expect_download` AND Chrome's native handler both trigger. Solved by using only Chrome native downloads.
4. **External drive permissions**: Playwright/Python can't write to `/Volumes/Elements/` due to macOS sandbox. Must use staging dir on local disk.
5. **CAPTCHA false positives**: Checking full HTML for "captcha" matched scripts on normal pages. Now only checks visible body text.
6. **CDP `setDownloadBehavior`**: Setting this via CDP persists across script restarts and causes UUID-named files. Don't use it — let Chrome download normally.
