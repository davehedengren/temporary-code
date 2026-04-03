# Temporary Code — Mobile Workspace

General-purpose scratch workspace for quick coding from Claude Code on mobile. Projects here are experiments, prototypes, and one-offs that may graduate to their own repos.

## Active Project: clawbot/

Automated crawler that downloads AER replication packages from openICPSR. See `clawbot/README.md` for full details.

### Quick reference

- **Start Chrome:** `/Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome --remote-debugging-port=9222 --no-first-run --user-data-dir="$HOME/chrome-debug-profile"`
- **Run main crawl:** `cd clawbot && python3 main.py`
- **Retry failed downloads:** `cd clawbot && python3 retry_failed.py`
- **Recheck missed projects:** `cd clawbot && python3 recheck.py`
- **Move files to external drive:** `cd clawbot && ./move_to_external.sh`
- **Check status:** `cat clawbot/download_tracker.json`

### Architecture

- Connects to a real Chrome browser via CDP (port 9222) to avoid Cloudflare bot detection
- Uses Claude Sonnet to classify data availability from README files (not regex)
- Downloads go to `clawbot/download_staging/`, then `move_to_external.sh` moves them to `/Volumes/Elements/AER_replication_data/`
- All progress tracked in `project_log.csv` (per-project) and `download_tracker.json` (overall state)
- Fully resumable — kill anytime, restart and it picks up where it left off

### Auth flow

Session expiry is handled by clicking "Sign in with Google" automatically (Chrome is already signed into Google). Falls back to waiting for manual login with 12h timeout. CAPTCHA detection pauses the crawl and waits.

### Known issues / patterns

- Playwright can't write to external drives (permission error) — use staging dir + move script
- Cloudflare blocks Playwright-launched browsers — must use CDP to a real Chrome
- Some openICPSR projects have no download button or broken Terms of Use flow
- ~34% of AER papers have all data included; ~55% use restricted/proprietary data

## How This Repo Works

- Each project gets its own subdirectory (e.g., `my-project/`)
- When something is worth keeping, move it to a standalone repo

## Preferred Stack

- **Quick web apps:** Python + Flask, Jinja2 templates, vanilla JS, SQLite
- **Data work:** Python (pandas, matplotlib)
- **LLM integrations:** Anthropic Claude API (claude-sonnet-4-6), OpenAI — keys in `.env`
- **Browser automation:** Playwright + CDP to real Chrome

## Code Style

- Keep it simple. No frameworks unless the project demands it.
- Each project should be self-contained and runnable independently.
- Include a `requirements.txt` in any Python project.
- Use `.env` for API keys — never commit secrets.

## .env Keys

- `ANTHROPIC_API_KEY` — Claude Sonnet for README classification
- `EMAIL_LOGIN` / `PASSWORD` — ICPSR credentials (not used for auto-login currently)

## Context

Dave is often working from his phone via Claude Code, so prefer concise responses and avoid unnecessary back-and-forth. Bias toward action — build the thing, then iterate.
