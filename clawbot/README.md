# Clawbot — AER Replication Data Collector

Automated crawler that finds and downloads replication packages from the [American Economic Review](https://www.aeaweb.org/journals/aer) on [openICPSR](https://www.openicpsr.org/openicpsr/search/aea/studies?q=). Uses an LLM to read each package's README and decide whether all data is publicly included before downloading.

Built to feed [davehedengren/replication-studies](https://github.com/davehedengren/replication-studies), which uses Claude Code to replicate economics papers and run robustness checks.

## Current Status (2026-04-03)

- **709 projects checked** across 68 search pages (~5,900 total on openICPSR)
- **62 downloaded** successfully to `/Volumes/Elements/AER_replication_data/`
- **94 classified as available but failed to download** — need retry
- **~1,200 projects on pages 1-68 never checked** (skipped due to CAPTCHAs, session expiry, zombie processes)

### Next steps

1. **Grant VS Code full disk access** so Claude Code can read the external drive
2. **Cross-reference** external drive contents against retry list to avoid re-downloading
3. **Run `retry_failed.py`** for the 94 failed downloads
4. **Run `recheck.py`** for the ~1,200 unchecked projects
5. **Run `main.py`** to continue past page 68

### Known issues fixed this session

- Zombie processes: multiple background Python processes were piling up and controlling Chrome simultaneously. Always check `ps aux | grep python3` before starting a new run.
- Playwright temp artifacts filling disk: `cleanup.py` now cleans these up on exit.
- Chrome double-downloading: downloader now uses native Chrome downloads (watch ~/Downloads for files) instead of Playwright's `expect_download`.
- CAPTCHA false positives: now checks visible text only, not full HTML source.

## What it does

1. Paginates through the AEA studies listing on openICPSR (~5,900 packages)
2. For each package, finds and reads the README (text, markdown, or PDF) via JavaScript `fetch()` in the browser — no visible navigation needed
3. Sends the README to **Claude Sonnet** (`claude-sonnet-4-6`) to classify data availability:
   - `included` — all data in the package, ready to replicate
   - `external_public` — data freely downloadable from public sources
   - `restricted` — requires paid/institutional/confidential access
   - `unknown` — can't determine
4. Downloads packages classified as `included` (and optionally `external_public`)
5. Logs every decision with the LLM's rationale to `project_log.csv` for auditing

## Setup

### Prerequisites

- Python 3.9+
- Google Chrome
- An openICPSR account (free)
- Anthropic API key
- External drive mounted at `/Volumes/Elements/` (for storing large downloads)

### Install

```bash
cd clawbot
pip3 install -r requirements.txt
```

### Configure

Create `clawbot/.env`:

```
ANTHROPIC_API_KEY=sk-ant-...
EMAIL_LOGIN=your@email.com
PASSWORD=yourpassword
```

### Launch Chrome with remote debugging

Clawbot connects to a real Chrome browser via CDP to avoid Cloudflare bot detection. You must start Chrome with the debug flag:

```bash
/Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome \
    --remote-debugging-port=9222 \
    --no-first-run \
    --user-data-dir="$HOME/chrome-debug-profile"
```

Then log into openICPSR **and Google** in that browser window (Google login is used for auto-re-login when session expires).

## Usage

### Before any run

Always check for zombie processes first:
```bash
ps aux | grep -E "python3.*(main|retry|recheck)" | grep -v grep
```
Kill any you find before starting a new run.

### Main crawl

```bash
cd clawbot && python3 main.py
```

Paginates through all AEA studies, classifies each, downloads qualifying packages. Fully resumable — Ctrl+C saves state, restart picks up where it left off.

### Retry failed downloads

```bash
cd clawbot && python3 retry_failed.py
```

Re-attempts downloads for packages that were classified as `included` but failed to download. Updates the CSV in-place on success.

### Recheck missed projects

```bash
cd clawbot && python3 recheck.py
```

Phase 1: Scans all previously-visited search pages, finds project IDs not in the log.
Phase 2: Runs the full pipeline on each (visit, README, classify, download).
Saves queue to `recheck_queue.json` on Ctrl+C so Phase 1 can be skipped on restart.

### Move downloads to external drive

```bash
./move_to_external.sh
```

Moves completed zips from `download_staging/` to `/Volumes/Elements/AER_replication_data/`.

### Check status

```bash
cat download_tracker.json                    # quick overview
python3 -c "
import csv
d=sum(1 for r in csv.DictReader(open('project_log.csv')) if r['downloaded']=='True')
t=sum(1 for _ in csv.DictReader(open('project_log.csv')))
print(f'{d} downloaded, {t} checked')
"
```

## How it handles failures

- **Session expiry**: Tries "Sign in with Google" automatically. Falls back to waiting up to 12 hours for manual login with 30s polling.
- **CAPTCHA**: Detects Cloudflare challenges (visible text check), pauses, waits for manual solve, resumes.
- **Download failure**: Retries once. After 3 consecutive failures, recovers by navigating to search page and re-authenticating.
- **Network drops**: Recovers automatically on next attempt.
- **LLM errors**: Logs as `unknown` and skips — doesn't block the crawl.
- **Playwright temp files**: `cleanup.py` removes temp artifact dirs on exit.

## Download flow

1. Navigate directly to project's Terms of Use URL
2. Click "I Agree" (accepts terms without triggering download)
3. Navigate to project page
4. Click "DOWNLOAD THIS PROJECT" — Chrome downloads natively to `~/Downloads/`
5. Watch `~/Downloads/` for new files; when size stops growing, move to `download_staging/`
6. Periodically run `move_to_external.sh` to move from staging to external drive

## Files

| File | Purpose |
|------|---------|
| `main.py` | Main crawl orchestrator |
| `retry_failed.py` | Re-download confirmed-available packages that failed |
| `recheck.py` | Find and process projects skipped due to errors |
| `config.py` | All settings (delays, paths, target count, LLM model) |
| `auth.py` | Login detection, Google auto-login, CAPTCHA handling |
| `crawler.py` | Search page pagination and project ID extraction |
| `analyzer.py` | README discovery, text extraction, LLM classification |
| `downloader.py` | Native Chrome download with Terms of Use handling |
| `tracker.py` | CSV + JSON progress tracking for resumability |
| `cleanup.py` | Remove Playwright temp artifacts |
| `move_to_external.sh` | Move zips to external drive |
| `project_log.csv` | Per-project log (classification, rationale, download status) |
| `download_tracker.json` | Overall crawl state (page number, counts) |
| `recheck_queue.json` | Cached list of missed project IDs (skip Phase 1 on restart) |

## Stats

- ~34% of AER papers have all data included in the package
- ~55% use restricted/proprietary data (confidential admin records, paid databases, etc.)
- ~7% have data freely available from external public sources
- ~4% couldn't be classified (README parsing failures, LLM errors)
