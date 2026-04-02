"""Package download with Terms of Use handling."""

import os
import time
from playwright.sync_api import TimeoutError as PWTimeout
from config import DOWNLOAD_DIR


def download_project(page, project_id):
    """Download project ZIP, handling Terms of Use interstitial.

    Waits for download to fully complete before returning.
    Returns file size in MB, or 0 on failure.
    """
    DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
    project_url = f"https://www.openicpsr.org/openicpsr/project/{project_id}/version/V1/view"

    try:
        # Ensure we're on the project page
        if f"/project/{project_id}/" not in page.url or "terms" in page.url:
            page.goto(project_url, wait_until="networkidle", timeout=60000)
            time.sleep(2)

        # Click Download
        btn = page.query_selector(
            "a:has-text('DOWNLOAD THIS PROJECT'), "
            "a:has-text('Download this project'), "
            "button:has-text('Download this project')"
        )
        if not btn:
            print(f"    No download button found")
            return 0

        btn.click()
        page.wait_for_load_state("networkidle", timeout=30000)
        time.sleep(2)

        # Accept Terms if present
        if "terms" in page.url.lower():
            print(f"    Accepting Terms of Use...")
            try:
                with page.expect_download(timeout=30000) as dl_info:
                    _click_agree(page)
                return _save_download(dl_info.value, project_id)
            except PWTimeout:
                # Terms accepted but no download triggered — retry
                print(f"    Terms accepted, retrying download...")
                time.sleep(3)

        # Try download again (terms should be accepted now)
        if f"/project/{project_id}/" not in page.url:
            page.goto(project_url, wait_until="networkidle", timeout=60000)
            time.sleep(2)

        btn = page.query_selector(
            "a:has-text('DOWNLOAD THIS PROJECT'), "
            "a:has-text('Download this project'), "
            "button:has-text('Download this project')"
        )
        if not btn:
            print(f"    No download button after terms")
            return 0

        try:
            with page.expect_download(timeout=300000) as dl_info:
                btn.click()
                time.sleep(3)
                if "terms" in page.url.lower():
                    _click_agree(page)
            return _save_download(dl_info.value, project_id)
        except PWTimeout:
            print(f"    Download timed out")
            return 0

    except Exception as e:
        print(f"    Download error: {e}")
        return 0


def _click_agree(page):
    page.evaluate("""() => {
        const btns = document.querySelectorAll('button, input[type=submit], a');
        for (const b of btns) {
            if (b.textContent.trim() === 'I Agree' || b.value === 'I Agree') {
                b.click(); return true;
            }
        }
        return false;
    }""")


def _save_download(dl, project_id):
    """Save download to disk. Returns size in MB."""
    dest = str(DOWNLOAD_DIR / f"{project_id}.zip")
    dl.save_as(dest)
    size_mb = os.path.getsize(dest) / (1024 * 1024)
    print(f"    Downloaded {size_mb:.1f} MB -> {dest}")
    return round(size_mb, 2)
