# Clawbot — AER Replication Data Collector

Automated crawler that finds and downloads replication packages from the [American Economic Review](https://www.aeaweb.org/journals/aer) on [openICPSR](https://www.openicpsr.org/openicpsr/search/aea/studies?q=). Uses an LLM to read each package's README and decide whether all data is publicly included before downloading.

Built to feed [davehedengren/replication-studies](https://github.com/davehedengren/replication-studies), which uses Claude Code to replicate economics papers and run robustness checks.

## What it does

1. Paginates through the AEA studies listing on openICPSR (~5,900 packages)
2. For each package, finds and reads the README (text, markdown, or PDF)
3. Sends the README to **Claude Sonnet** to classify data availability:
   - `included` — all data in the package, ready to replicate
   - `external_public` — data freely downloadable from public sources
   - `restricted` — requires paid/institutional/confidential access
   - `unknown` — can't determine
4. Downloads packages classified as `included` (and optionally `external_public`)
5. Logs every decision with the LLM's rationale to a CSV for auditing

## Setup

### Prerequisites

- Python 3.9+
- Google Chrome
- An openICPSR account (free)
- Anthropic API key

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

Then log into openICPSR in that browser window.

## Usage

### Main crawl

```bash
python3 main.py
```

Paginates through all AEA studies, classifies each, downloads qualifying packages. Fully resumable — Ctrl+C saves state, restart picks up where it left off.

### Retry failed downloads

```bash
python3 retry_failed.py
```

Re-attempts downloads for packages that were classified as `included` but failed to download (network errors, Terms of Use issues, etc.).

### Recheck missed projects

```bash
python3 recheck.py
```

Scans all previously-visited search pages, finds project IDs not in the log (skipped due to CAPTCHAs, session expiry, network drops), and runs the full pipeline on each.

### Move downloads to external drive

```bash
./move_to_external.sh
```

Moves completed zips from `download_staging/` to `/Volumes/Elements/AER_replication_data/`. Playwright can't write to external drives directly due to macOS sandbox permissions.

## How it handles failures

- **Session expiry**: Automatically clicks "Sign in with Google" (Chrome is already authenticated). Falls back to waiting up to 12 hours for manual login.
- **CAPTCHA**: Detects Cloudflare challenges, pauses the crawl, waits for manual solve, resumes.
- **Download failure**: Retries once immediately. After 3 consecutive failures, navigates back to search page and re-authenticates.
- **Network drops**: Recovers automatically on next attempt.
- **LLM errors**: Logs as `unknown` and skips — doesn't block the crawl.

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
| `downloader.py` | Package download with Terms of Use handling |
| `tracker.py` | CSV + JSON progress tracking for resumability |
| `move_to_external.sh` | Move zips to external drive |
| `project_log.csv` | Per-project log (classification, rationale, download status) |
| `download_tracker.json` | Overall crawl state (page number, counts) |

## Stats (as of initial run)

- ~34% of AER papers have all data included in the package
- ~55% use restricted/proprietary data (confidential admin records, paid databases, etc.)
- ~7% have data freely available from external public sources
- ~4% couldn't be classified (README parsing failures, LLM errors)
