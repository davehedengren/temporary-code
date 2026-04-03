"""Search pagination and project discovery on openICPSR."""

import re
import time
from config import SEARCH_URL, SEARCH_SORT, ROWS_PER_PAGE
from auth import check_session_alive


def get_search_projects(page, context, page_num):
    """Fetch one page of AEA search results. Returns list of (project_id, url)."""
    start = (page_num - 1) * ROWS_PER_PAGE
    url = f"{SEARCH_URL}?q=&start={start}&ARCHIVE=aea&sort={SEARCH_SORT}&rows={ROWS_PER_PAGE}"

    print(f"    Loading: {url}", flush=True)
    page.goto(url, wait_until="networkidle", timeout=90000)
    time.sleep(5)

    if not check_session_alive(page, context):
        return []

    # Re-navigate if bounced away
    if "search/aea/studies" not in page.url:
        print(f"    Bounced to: {page.url} — retrying", flush=True)
        page.goto(url, wait_until="networkidle", timeout=90000)
        time.sleep(5)

    # Wait for search results to actually render
    try:
        page.wait_for_selector("a[href*='/openicpsr/project/']", timeout=15000)
    except Exception:
        print(f"    No project links found on page. URL: {page.url}", flush=True)
        # Dump a snippet of page text for debugging
        try:
            text = page.inner_text("body")[:500]
            print(f"    Page text: {text[:200]}", flush=True)
        except Exception:
            pass
        return []

    links = page.query_selector_all("a[href*='/openicpsr/project/']")
    projects = []
    seen = set()
    for link in links:
        href = link.get_attribute("href") or ""
        pid = _extract_project_id(href)
        if pid and pid not in seen:
            seen.add(pid)
            full = href if href.startswith("http") else f"https://www.openicpsr.org{href}"
            projects.append((pid, full))
    return projects


def _extract_project_id(url):
    m = re.search(r"/project/(\d+)", url)
    return m.group(1) if m else None
