#!/usr/bin/env python3
"""Clawbot — automated AER replication package collector.

Crawls openICPSR AEA studies, uses Claude Sonnet to classify data availability
from README files, and downloads packages where all data is included.

Fully resumable: kill it anytime, restart and it picks up where it left off.
"""

import random
import signal
import sys
import time

from playwright.sync_api import sync_playwright

import config
import tracker
import auth
import crawler
import analyzer
import downloader


def polite_wait(label=""):
    delay = random.uniform(config.MIN_DELAY, config.MAX_DELAY)
    print(f"    {delay:.0f}s pause {label}", flush=True)
    time.sleep(delay)


def run():
    checked_ids = tracker.load_checked_ids()
    downloaded_count = tracker.count_downloads()
    state = tracker.load_state()
    start_page = state.get("last_page", 0) + 1

    print(f"Clawbot starting", flush=True)
    print(f"  Target: {config.TARGET_COUNT} | Downloaded: {downloaded_count}", flush=True)
    print(f"  Already checked: {len(checked_ids)}", flush=True)
    print(f"  Resuming from search page {start_page}", flush=True)
    print(f"  Delay: {config.MIN_DELAY}-{config.MAX_DELAY}s\n", flush=True)

    config.DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        # Launch browser with session state if available
        launch_args = {"headless": config.HEADLESS}
        if auth.session_file_valid():
            ctx = p.chromium.launch(**launch_args).new_context(
                storage_state=str(config.SESSION_FILE)
            )
            print("  Loaded saved session")
        else:
            ctx = p.chromium.launch(**launch_args).new_context()

        page = ctx.new_page()
        page.set_default_timeout(60000)

        # Graceful shutdown on Ctrl+C
        def shutdown(sig, frame):
            print("\n\nShutting down gracefully...")
            state["status"] = f"stopped_at_{downloaded_count}"
            state["downloaded_count"] = downloaded_count
            state["checked_count"] = len(checked_ids)
            tracker.save_state(state)
            auth.save_session(ctx)
            print(f"  State saved. Resume with: python main.py")
            sys.exit(0)
        signal.signal(signal.SIGINT, shutdown)

        # Initial login check
        page.goto("https://www.openicpsr.org/openicpsr/search/aea/studies?q=",
                   wait_until="domcontentloaded", timeout=60000)
        time.sleep(3)
        if not auth.ensure_logged_in(page, ctx):
            print("Failed to log in. Exiting.")
            return

        auth.save_session(ctx)

        for pg_num in range(start_page, config.MAX_PAGES + 1):
            if downloaded_count >= config.TARGET_COUNT:
                break

            print(f"\n{'='*60}", flush=True)
            print(f"Search page {pg_num}", flush=True)

            try:
                projects = crawler.get_search_projects(page, ctx, pg_num)
            except Exception as e:
                print(f"  Search page failed: {e}", flush=True)
                polite_wait("after error")
                continue

            new = [(pid, url) for pid, url in projects if pid not in checked_ids]
            print(f"  {len(projects)} total, {len(new)} unchecked", flush=True)

            if not new:
                polite_wait("no new projects")
                continue

            for pid, url in new:
                if downloaded_count >= config.TARGET_COUNT:
                    break

                print(f"\n  [{downloaded_count}/{config.TARGET_COUNT}] Project {pid}", flush=True)
                row = tracker.make_row(pid)

                # Load project page
                try:
                    page.goto(url, wait_until="networkidle", timeout=60000)
                    time.sleep(2)
                    if not auth.check_session_alive(page, ctx):
                        break
                    if f"/project/{pid}/" not in page.url:
                        page.goto(url, wait_until="networkidle", timeout=60000)
                        time.sleep(2)
                except Exception as e:
                    row["error"] = str(e)[:200]
                    tracker.append_row(row)
                    checked_ids.add(pid)
                    print(f"    Page load failed: {e}", flush=True)
                    polite_wait("after error")
                    continue

                title = analyzer.get_title(page)
                row["title"] = title
                print(f"    {title[:100]}", flush=True)

                # Year filter
                if not analyzer.in_target_years(page, config.TARGET_YEARS):
                    row["notes"] = "out_of_target_years"
                    tracker.append_row(row)
                    checked_ids.add(pid)
                    print(f"    Not in target years — skip", flush=True)
                    polite_wait()
                    continue

                # Find README
                readme = analyzer.find_readme(page, pid)
                if not readme:
                    row["has_readme"] = "False"
                    row["notes"] = "no_readme_found"
                    tracker.append_row(row)
                    checked_ids.add(pid)
                    print(f"    No README — skip", flush=True)
                    polite_wait()
                    continue

                ftype, fname, fpath = readme
                row["has_readme"] = "True"
                row["readme_type"] = ftype
                print(f"    README: {fname}", flush=True)

                # Fetch README text
                content = analyzer.fetch_readme_text(page, pid, fpath, ftype)
                if not content:
                    row["notes"] = "empty_readme"
                    tracker.append_row(row)
                    checked_ids.add(pid)
                    print(f"    Empty README — skip", flush=True)
                    polite_wait()
                    continue

                # LLM classification
                result = analyzer.classify_data_availability(content)
                classification = result["classification"]
                row["classification"] = classification
                row["rationale"] = result["rationale"]

                if classification == "restricted":
                    row["notes"] = "restricted_data"
                    tracker.append_row(row)
                    checked_ids.add(pid)
                    print(f"    Restricted data — skip ({result['rationale']})", flush=True)
                    polite_wait()
                    continue
                elif classification == "unknown":
                    row["notes"] = "unknown_data_availability"
                    tracker.append_row(row)
                    checked_ids.add(pid)
                    print(f"    Unknown availability — skip", flush=True)
                    polite_wait()
                    continue
                elif classification == "external_public":
                    print(f"    External public data — downloading code package...", flush=True)
                    polite_wait("before download")
                    size = downloader.download_project(page, pid)
                    if size > 0:
                        row["downloaded"] = "True"
                        row["download_size_mb"] = str(size)
                        row["notes"] = "external_data_needs_separate_download"
                    else:
                        row["error"] = "download_failed"
                    tracker.append_row(row)
                    checked_ids.add(pid)
                    polite_wait()
                    continue

                # classification == "included"
                print(f"    ALL DATA INCLUDED — downloading...", flush=True)
                polite_wait("before download")
                size = downloader.download_project(page, pid)
                if size > 0:
                    row["downloaded"] = "True"
                    row["download_size_mb"] = str(size)
                    downloaded_count += 1
                    print(f"    Progress: {downloaded_count}/{config.TARGET_COUNT}", flush=True)
                else:
                    row["error"] = "download_failed"

                tracker.append_row(row)
                checked_ids.add(pid)

                # Save state after each project
                state["last_page"] = pg_num
                state["downloaded_count"] = downloaded_count
                state["checked_count"] = len(checked_ids)
                state["status"] = "running"
                tracker.save_state(state)

                # Save session periodically
                auth.save_session(ctx)

                polite_wait()

            # Save page progress
            state["last_page"] = pg_num
            tracker.save_state(state)

        # Final state
        status = "completed" if downloaded_count >= config.TARGET_COUNT else f"stopped_at_{downloaded_count}"
        state["status"] = status
        state["downloaded_count"] = downloaded_count
        state["checked_count"] = len(checked_ids)
        tracker.save_state(state)

        print(f"\n{'='*60}", flush=True)
        print(f"Done! Status: {status}", flush=True)
        print(f"  Downloaded: {downloaded_count}/{config.TARGET_COUNT}", flush=True)
        print(f"  Total checked: {len(checked_ids)}", flush=True)

        ctx.browser.close()


if __name__ == "__main__":
    run()
