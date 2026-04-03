"""Package download — let Chrome handle downloads natively."""

import os
import time
import glob
from config import DOWNLOAD_DIR

CHROME_DOWNLOADS = os.path.expanduser("~/Downloads")


def download_project(page, project_id):
    """Download project ZIP via Chrome's native download handler.

    Click download → accept Terms → wait for Chrome to finish → move file.
    Returns file size in MB, or 0 on failure.
    """
    DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
    project_url = f"https://www.openicpsr.org/openicpsr/project/{project_id}/version/V1/view"

    try:
        # Ensure we're on the project page
        if f"/project/{project_id}/" not in page.url or "terms" in page.url:
            page.goto(project_url, wait_until="networkidle", timeout=60000)
            time.sleep(2)

        # Snapshot existing files before download
        before = set(glob.glob(os.path.join(CHROME_DOWNLOADS, "*.zip")))
        before.update(glob.glob(os.path.join(CHROME_DOWNLOADS, "*.crdownload")))

        # Step 1: Navigate to Terms page directly and accept
        terms_url = f"https://www.openicpsr.org/openicpsr/project/{project_id}/version/V1/download/terms?path=/openicpsr/{project_id}/fcr:versions/V1&type=project"
        page.goto(terms_url, wait_until="networkidle", timeout=30000)
        time.sleep(2)

        if "terms" in page.url.lower():
            print(f"    Accepting Terms of Use...")
            _click_agree(page)
            page.wait_for_load_state("networkidle", timeout=30000)
            time.sleep(3)

        # Step 2: Go to project page and click download (terms now accepted)
        page.goto(project_url, wait_until="networkidle", timeout=60000)
        time.sleep(2)

        btn = _find_download_button(page)
        if not btn:
            print(f"    No download button found")
            return 0

        btn.click()
        time.sleep(3)

        # Wait for Chrome to start and finish the download
        dest = _wait_for_chrome_download(project_id, before, timeout=600)
        if dest:
            size_mb = os.path.getsize(dest) / (1024 * 1024)
            print(f"    Downloaded {size_mb:.1f} MB -> {dest}")
            if size_mb > 500:
                time.sleep(10)
            elif size_mb > 100:
                time.sleep(5)
            return round(size_mb, 2)
        else:
            print(f"    Download failed — no file appeared")
            return 0

    except Exception as e:
        print(f"    Download error: {e}")
        return 0


def _wait_for_chrome_download(project_id, before_files, timeout=600):
    """Wait for a new file to appear in Chrome's Downloads and finish.

    Chrome saves downloads as UUID-named files (no extension) while in progress,
    then renames to {id}-V1.zip when complete. We watch for both patterns.

    Returns the final path in DOWNLOAD_DIR, or None on failure.
    """
    dest = str(DOWNLOAD_DIR / f"{project_id}.zip")
    start = time.time()
    last_size = 0
    stall_count = 0

    while time.time() - start < timeout:
        time.sleep(5)

        # Snapshot all files in Downloads
        all_files = set(glob.glob(os.path.join(CHROME_DOWNLOADS, "*")))
        new_files = all_files - before_files

        # Filter out tiny files (<1KB, likely metadata) and directories
        new_files = {f for f in new_files if os.path.isfile(f) and os.path.getsize(f) > 1000}

        if not new_files:
            elapsed = int(time.time() - start)
            if elapsed > 30:
                # Nothing appeared after 30s — download probably didn't start
                return None
            continue

        # Check if any file is still growing (download in progress)
        total_size = sum(os.path.getsize(f) for f in new_files)
        if total_size > last_size:
            last_size = total_size
            stall_count = 0
            elapsed = int(time.time() - start)
            if elapsed % 30 < 6:
                sz = total_size / (1024 * 1024)
                print(f"    Downloading... {sz:.0f} MB ({elapsed}s)", flush=True)
            continue

        # Size hasn't changed — might be done
        stall_count += 1
        if stall_count < 3:
            continue  # Wait a bit more to confirm it's truly done

        # Download complete — find the largest new file (the actual download)
        src = max(new_files, key=os.path.getsize)
        size = os.path.getsize(src)
        if size < 1000:
            return None

        # Move to staging with proper name
        os.rename(src, dest)

        # Clean up any other new files (duplicates, metadata)
        for f in new_files:
            if f != src and os.path.exists(f):
                try:
                    os.remove(f)
                except Exception:
                    pass

        return dest

    return None


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
