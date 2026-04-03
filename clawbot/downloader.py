"""Package download with Terms of Use handling."""

import os
import time
import glob
from playwright.sync_api import TimeoutError as PWTimeout
from config import DOWNLOAD_DIR


def cleanup_chrome_downloads():
    """Delete Chrome's duplicate downloads from ~/Downloads."""
    dupes = glob.glob(os.path.expanduser("~/Downloads/*-V1*.zip"))
    if dupes:
        for f in dupes:
            try:
                os.remove(f)
            except Exception:
                pass
        print(f"    Cleaned {len(dupes)} Chrome duplicate downloads", flush=True)


def download_project(page, project_id):
    """Download project ZIP, handling Terms of Use interstitial.

    Strategy: click download, if Terms appear accept them, then try download
    again. Use expect_download to capture the file.
    Returns file size in MB, or 0 on failure.
    """
    DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
    project_url = f"https://www.openicpsr.org/openicpsr/project/{project_id}/version/V1/view"

    try:
        # Ensure we're on the project page
        if f"/project/{project_id}/" not in page.url or "terms" in page.url:
            page.goto(project_url, wait_until="networkidle", timeout=60000)
            time.sleep(2)

        # First attempt: click download, might trigger Terms
        btn = _find_download_button(page)
        if not btn:
            print(f"    No download button found")
            return 0

        # Try to capture download directly (works if terms already accepted)
        try:
            with page.expect_download(timeout=15000) as dl_info:
                btn.click()
            return _save_download(dl_info.value, project_id)
        except PWTimeout:
            pass  # Probably went to Terms page instead

        # Handle Terms of Use
        if "terms" in page.url.lower():
            print(f"    Accepting Terms of Use...")
            _click_agree(page)
            time.sleep(3)
            page.wait_for_load_state("networkidle", timeout=30000)
            time.sleep(2)

        # Navigate back to project page
        page.goto(project_url, wait_until="networkidle", timeout=60000)
        time.sleep(2)

        # Second attempt: terms should be accepted now
        btn = _find_download_button(page)
        if not btn:
            print(f"    No download button after terms")
            return 0

        try:
            with page.expect_download(timeout=300000) as dl_info:
                btn.click()
                time.sleep(3)
                # Handle terms appearing again
                if "terms" in page.url.lower():
                    _click_agree(page)
            return _save_download(dl_info.value, project_id)
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
    """Save download to disk, wait for completion. Returns size in MB, or 0 if empty."""
    dest = str(DOWNLOAD_DIR / f"{project_id}.zip")

    # dl.path() blocks until the download is fully complete
    print(f"    Waiting for download to complete...", flush=True)
    path = dl.path()
    if path is None:
        print(f"    Download failed — no file received")
        return 0

    dl.save_as(dest)
    size_mb = os.path.getsize(dest) / (1024 * 1024)
    if size_mb < 0.001:
        print(f"    Download was empty (0 bytes) — removing")
        os.remove(dest)
        return 0
    print(f"    Downloaded {size_mb:.1f} MB -> {dest}")

    # Clean up Chrome's duplicate downloads
    cleanup_chrome_downloads()

    # Extra pause after large downloads
    if size_mb > 500:
        print(f"    Large file ({size_mb:.0f} MB) — extra 10s cooldown", flush=True)
        time.sleep(10)
    elif size_mb > 100:
        time.sleep(5)

    return round(size_mb, 2)
