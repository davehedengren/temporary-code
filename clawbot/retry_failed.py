#!/usr/bin/env python3
"""Retry downloading projects that were classified as 'included' but failed to download."""

import csv
import random
import time
import sys

from playwright.sync_api import sync_playwright

import config
import tracker
import downloader
import auth
from cleanup import cleanup_playwright_artifacts


def get_failed_ids():
    """Find project IDs classified as included/external_public but not downloaded."""
    failed = []
    with open(config.TRACKER_CSV) as f:
        for row in csv.DictReader(f):
            if row["classification"] in ("included", "external_public") and row["downloaded"] != "True":
                failed.append(row["project_id"])
    return failed


def update_csv_row(project_id, size_mb):
    """Update the existing CSV row to mark as downloaded."""
    rows = []
    with open(config.TRACKER_CSV) as f:
        reader = csv.DictReader(f)
        fields = reader.fieldnames
        for row in reader:
            if row["project_id"] == project_id and size_mb > 0:
                row["downloaded"] = "True"
                row["download_size_mb"] = str(size_mb)
                row["error"] = ""
            rows.append(row)

    with open(config.TRACKER_CSV, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def run():
    failed = get_failed_ids()
    if not failed:
        print("No failed downloads to retry!")
        return

    print(f"Retrying {len(failed)} failed downloads...\n")

    with sync_playwright() as p:
        print(f"  Connecting to Chrome at {config.CDP_URL}...")
        try:
            browser = p.chromium.connect_over_cdp(config.CDP_URL)
        except Exception as e:
            print(f"  Could not connect to Chrome: {e}")
            print(f"  Make sure Chrome is running with --remote-debugging-port=9222")
            return

        ctx = browser.contexts[0]
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.set_default_timeout(60000)

        success = 0
        for i, pid in enumerate(failed):
            print(f"\n  [{i+1}/{len(failed)}] Retrying project {pid}...")

            # Navigate to project page
            url = f"https://www.openicpsr.org/openicpsr/project/{pid}/version/V1/view"
            try:
                page.goto(url, wait_until="networkidle", timeout=60000)
                time.sleep(3)

                if auth.is_captcha_page(page):
                    print("    CAPTCHA — please solve it...")
                    auth.wait_for_captcha(page)

                if not auth.check_session_alive(page, ctx):
                    print("    Session lost, stopping retries.")
                    break

                size = downloader.download_project(page, pid)
                if size > 0:
                    update_csv_row(pid, size)
                    success += 1
                    print(f"    Success! ({success} recovered so far)")
                else:
                    print(f"    Still failed")

            except Exception as e:
                print(f"    Error: {e}")

            delay = random.uniform(config.MIN_DELAY, config.MAX_DELAY)
            print(f"    {delay:.0f}s pause")
            time.sleep(delay)

        print(f"\n{'='*60}")
        print(f"Retry complete: {success}/{len(failed)} recovered")
        browser.close()
        cleanup_playwright_artifacts()


if __name__ == "__main__":
    run()
