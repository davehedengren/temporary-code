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

        # Find download button — try multiple selectors
        btn = _find_download_button(page)
        if not btn:
            print(f"    No download button found")
            return 0

        btn.click()
        page.wait_for_load_state("networkidle", timeout=30000)
        time.sleep(2)

        # Accept Terms if present
        if "terms" in page.url.lower():
            print(f"    Accepting Terms of Use...")
            agreed = _click_agree(page)
            if not agreed:
                print(f"    Could not find I Agree button")
                return 0

            # Wait for navigation after agreeing
            page.wait_for_load_state("networkidle", timeout=30000)
            time.sleep(3)

            # After terms, we usually get redirected back to the project page.
            # Now click download again — this time it should trigger the actual download.
            if f"/project/{project_id}/" not in page.url:
                page.goto(project_url, wait_until="networkidle", timeout=60000)
                time.sleep(2)

        # Now try the actual download (terms already accepted)
        btn = _find_download_button(page)
        if not btn:
            print(f"    No download button after terms")
            return 0

        try:
            with page.expect_download(timeout=300000) as dl_info:
                btn.click()
                # If we hit terms again, accept them
                time.sleep(3)
                if "terms" in page.url.lower():
                    _click_agree(page)
            dl = dl_info.value
            # Wait for download to fully complete
            path = dl.path()  # blocks until download finishes
            if path is None:
                print(f"    Download failed — no file received")
                return 0
            return _save_download(dl, project_id)
        except PWTimeout:
            print(f"    Download timed out (5 min)")
            return 0

    except Exception as e:
        print(f"    Download error: {e}")
        return 0


def _find_download_button(page):
    """Try multiple selectors to find the download button."""
    selectors = [
        "a:has-text('DOWNLOAD THIS PROJECT')",
        "a:has-text('Download this project')",
        "a:has-text('Download This Project')",
        "button:has-text('DOWNLOAD THIS PROJECT')",
        "button:has-text('Download this project')",
        "a:has-text('Download All')",
        "a:has-text('download')",
    ]
    for sel in selectors:
        btn = page.query_selector(sel)
        if btn:
            return btn
    return None


def _click_agree(page):
    """Click the I Agree button. Returns True if found and clicked."""
    return page.evaluate("""() => {
        const btns = document.querySelectorAll('button, input[type=submit], a');
        for (const b of btns) {
            const text = (b.textContent || b.value || '').trim();
            if (text === 'I Agree' || text === 'I agree' || text === 'I AGREE') {
                b.click(); return true;
            }
        }
        return false;
    }""")


def _save_download(dl, project_id):
    """Save download to disk. Returns size in MB, or 0 if empty."""
    dest = str(DOWNLOAD_DIR / f"{project_id}.zip")
    dl.save_as(dest)
    size_mb = os.path.getsize(dest) / (1024 * 1024)
    if size_mb < 0.001:
        print(f"    Download was empty (0 bytes) — removing")
        os.remove(dest)
        return 0
    print(f"    Downloaded {size_mb:.1f} MB -> {dest}")
    return round(size_mb, 2)
