"""Search pagination and project discovery on openICPSR."""

import re
import time
from config import SEARCH_URL, SEARCH_SORT, ROWS_PER_PAGE
from auth import check_session_alive


def get_search_projects(page, context, page_num):
    """Fetch one page of AEA search results. Returns list of (project_id, url)."""
    start = (page_num - 1) * ROWS_PER_PAGE
    url = f"{SEARCH_URL}?q=&start={start}&ARCHIVE=aea&sort={SEARCH_SORT}&rows={ROWS_PER_PAGE}"

    page.goto(url, wait_until="domcontentloaded", timeout=90000)
    time.sleep(3)

    if not check_session_alive(page, context):
        return []

    # Re-navigate if bounced away
    if "search/aea/studies" not in page.url:
        page.goto(url, wait_until="domcontentloaded", timeout=90000)
        time.sleep(3)

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
