#!/usr/bin/env python3
"""Re-check projects that were missed due to errors, CAPTCHAs, or session expiry.

Phase 1: Scrape all project IDs from search pages 1-N
Phase 2: Find IDs not in the log (never checked) + failed downloads
Phase 3: Run the full pipeline on each (visit, find README, classify, download)
"""

import csv
import random
import signal
import sys
import time

from playwright.sync_api import sync_playwright

import config
import tracker
import auth
import crawler
from cleanup import cleanup_playwright_artifacts
import analyzer
import downloader


def get_all_missed_ids():
    """Get project IDs that need re-checking."""
    checked = tracker.load_checked_ids()

    # Also find confirmed-available but not downloaded
    retry_ids = []
    if config.TRACKER_CSV.exists():
        with open(config.TRACKER_CSV) as f:
            for row in csv.DictReader(f):
                if row["classification"] in ("included", "external_public") and row["downloaded"] != "True":
                    retry_ids.append(row["project_id"])

    return checked, set(retry_ids)


def polite_wait(label=""):
    delay = random.uniform(config.MIN_DELAY, config.MAX_DELAY)
    print(f"    {delay:.0f}s pause {label}", flush=True)
    time.sleep(delay)


def process_project(page, ctx, pid, checked_ids):
    """Run the full pipeline on a single project. Returns True if downloaded."""
    url = f"https://www.openicpsr.org/openicpsr/project/{pid}/version/V1/view"
    row = tracker.make_row(pid)

    try:
        page.goto(url, wait_until="networkidle", timeout=60000)
        time.sleep(2)
        if not auth.check_session_alive(page, ctx):
            # Try once more after re-login
            page.goto(url, wait_until="networkidle", timeout=60000)
            time.sleep(2)
        if f"/project/{pid}/" not in page.url:
            page.goto(url, wait_until="networkidle", timeout=60000)
            time.sleep(2)
    except Exception as e:
        row["error"] = str(e)[:200]
        tracker.append_row(row)
        checked_ids.add(pid)
        print(f"    Page load failed: {e}", flush=True)
        return False

    title = analyzer.get_title(page)
    row["title"] = title
    print(f"    {title[:100]}", flush=True)

    # Find README
    readme = analyzer.find_readme(page, pid)
    if not readme:
        row["has_readme"] = "False"
        row["notes"] = "no_readme_found"
        tracker.append_row(row)
        checked_ids.add(pid)
        print(f"    No README — skip", flush=True)
        return False

    ftype, fname, fpath = readme
    row["has_readme"] = "True"
    row["readme_type"] = ftype
    print(f"    README: {fname}", flush=True)

    content = analyzer.fetch_readme_text(page, pid, fpath, ftype)
    if not content:
        row["notes"] = "empty_readme"
        tracker.append_row(row)
        checked_ids.add(pid)
        print(f"    Empty README — skip", flush=True)
        return False

    # LLM classification
    result = analyzer.classify_data_availability(content)
    classification = result["classification"]
    row["classification"] = classification
    row["rationale"] = result["rationale"]

    if classification in ("restricted", "unknown"):
        row["notes"] = f"{classification}_data"
        tracker.append_row(row)
        checked_ids.add(pid)
        print(f"    {classification} — skip ({result['rationale']})", flush=True)
        return False

    # Download (included or external_public)
    print(f"    {classification.upper()} — downloading...", flush=True)
    polite_wait("before download")

    # Try download with one retry
    size = downloader.download_project(page, pid)
    if size <= 0:
        print(f"    Retrying download...", flush=True)
        time.sleep(5)
        try:
            page.goto(url, wait_until="networkidle", timeout=60000)
            time.sleep(3)
            size = downloader.download_project(page, pid)
        except Exception:
            size = 0

    if size > 0:
        row["downloaded"] = "True"
        row["download_size_mb"] = str(size)
        if classification == "external_public":
            row["notes"] = "external_data_needs_separate_download"
        tracker.append_row(row)
        checked_ids.add(pid)
        return True
    else:
        row["error"] = "download_failed"
        tracker.append_row(row)
        checked_ids.add(pid)
        return False


def run():
    checked_ids, retry_ids = get_all_missed_ids()
    state = tracker.load_state()
    last_page = state.get("last_page", 0)

    print(f"Recheck starting", flush=True)
    print(f"  Already checked: {len(checked_ids)}", flush=True)
    print(f"  Known failed downloads to retry: {len(retry_ids)}", flush=True)
    print(f"  Will scan search pages 1-{last_page} for missed projects", flush=True)
    print(f"  Delay: {config.MIN_DELAY}-{config.MAX_DELAY}s\n", flush=True)

    config.DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)

    # Check for cached missed IDs from a previous Phase 1 scan
    cache_file = config.BASE_DIR / "recheck_queue.json"
    unique_missed = None

    if cache_file.exists():
        import json
        with open(cache_file) as f:
            cached = json.load(f)
        if cached:
            unique_missed = cached
            print(f"  Loaded {len(unique_missed)} projects from recheck_queue.json (skipping Phase 1)", flush=True)

    with sync_playwright() as p:
        print(f"  Connecting to Chrome at {config.CDP_URL}...")
        try:
            browser = p.chromium.connect_over_cdp(config.CDP_URL)
        except Exception as e:
            print(f"  Could not connect: {e}")
            return

        ctx = browser.contexts[0]
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.set_default_timeout(60000)
        print(f"  Connected!")

        # Graceful shutdown
        downloaded_count = 0
        total_processed = 0

        def shutdown(sig, frame):
            print(f"\n\nShutting down. Processed {total_processed}, downloaded {downloaded_count}")
            # Save remaining queue so we can skip Phase 1 next time
            remaining = unique_missed[total_processed:] if unique_missed else []
            if remaining:
                import json
                with open(cache_file, "w") as f:
                    json.dump(remaining, f)
                print(f"  Saved {len(remaining)} remaining projects to recheck_queue.json")
            sys.exit(0)
        signal.signal(signal.SIGINT, shutdown)

        # Phase 1: Collect missed IDs (skip if we have a cache)
        if unique_missed is None:
            print(f"\n--- Phase 1: Scanning pages for missed projects ---", flush=True)
            missed_ids = []

            for pg_num in range(1, last_page + 1):
                try:
                    projects = crawler.get_search_projects(page, ctx, pg_num)
                    new = [pid for pid, url in projects if pid not in checked_ids]
                    if new:
                        missed_ids.extend(new)
                        print(f"  Page {pg_num}: {len(new)} missed", flush=True)
                    time.sleep(3)
                except Exception as e:
                    print(f"  Page {pg_num}: error ({e})", flush=True)
                    time.sleep(5)

            # Add known failed downloads
            for pid in retry_ids:
                if pid not in checked_ids and pid not in missed_ids:
                    missed_ids.append(pid)

            # Deduplicate
            seen = set()
            unique_missed = []
            for pid in missed_ids:
                if pid not in seen:
                    seen.add(pid)
                    unique_missed.append(pid)

            # Cache for next restart
            import json
            with open(cache_file, "w") as f:
                json.dump(unique_missed, f)

            print(f"\n  Total missed projects to process: {len(unique_missed)}", flush=True)
        else:
            print(f"\n  Projects to process: {len(unique_missed)}", flush=True)

        if not unique_missed:
            print("  Nothing to recheck!")
            browser.close()
            return

        # Phase 2: Process each missed project
        print(f"\n--- Phase 2: Processing missed projects ---", flush=True)

        for i, pid in enumerate(unique_missed):
            print(f"\n  [{i+1}/{len(unique_missed)}] Project {pid}", flush=True)

            success = process_project(page, ctx, pid, checked_ids)
            if success:
                downloaded_count += 1
                print(f"    Progress: {downloaded_count} recovered", flush=True)
            total_processed += 1

            # Move to external drive every 10 downloads
            if downloaded_count > 0 and downloaded_count % 10 == 0:
                import subprocess
                script = config.BASE_DIR / "move_to_external.sh"
                if script.exists():
                    try:
                        subprocess.run([str(script)], capture_output=True, timeout=60)
                    except Exception:
                        pass

            polite_wait()

        print(f"\n{'='*60}", flush=True)
        print(f"Recheck complete!", flush=True)
        print(f"  Processed: {total_processed}", flush=True)
        print(f"  Downloaded: {downloaded_count}", flush=True)

        browser.close()
        cleanup_playwright_artifacts()


if __name__ == "__main__":
    run()
