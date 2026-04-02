"""README finding, fetching, and LLM-powered data availability classification."""

import re
import time
import tempfile
import base64
import anthropic
from config import ANTHROPIC_API_KEY, LLM_MODEL


# --- README discovery ---

def find_readme(page, project_id):
    """BFS scan for README files in project. Returns (type, name, path) or None."""
    readmes = _scan_links_for_readme(page)
    if readmes:
        return readmes[0]

    original_url = page.url

    # BFS through subfolders (depth 2, max 40 folders)
    queue = []
    for name, href in _get_folder_links(page):
        queue.append((name, href, 1, name))

    visited = set()
    scanned = 0
    while queue and scanned < 40:
        folder_name, folder_href, depth, trail = queue.pop(0)
        folder_url = _to_full_url(folder_href, project_id)
        if folder_url in visited:
            continue
        visited.add(folder_url)
        scanned += 1

        try:
            page.goto(folder_url, wait_until="networkidle", timeout=45000)
            time.sleep(1)
            readmes = _scan_links_for_readme(page)
            if readmes:
                print(f"    Found README in {trail}/")
                return readmes[0]
            if depth < 2:
                for child_name, child_href in _get_folder_links(page):
                    queue.append((child_name, child_href, depth + 1, f"{trail}/{child_name}"))
        except Exception:
            continue

    # Navigate back
    try:
        page.goto(original_url, wait_until="networkidle", timeout=30000)
        time.sleep(1)
    except Exception:
        pass
    return None


def _scan_links_for_readme(page):
    try:
        links = page.query_selector_all("a")
    except Exception:
        return []
    readmes = []
    for link in links:
        try:
            text = (link.inner_text() or "").strip()
            href = link.get_attribute("href") or ""
            tl = text.lower()
            if "readme" in tl and "type=file" in href:
                path_m = re.search(r"path=([^&]+)", href)
                if path_m:
                    fpath = path_m.group(1)
                    if tl.endswith(".md"):
                        readmes.append(("md", text, fpath))
                    elif tl.endswith(".pdf") or tl.endswith(".docx"):
                        readmes.append(("pdf", text, fpath))
                    else:
                        readmes.append(("txt", text, fpath))
        except Exception:
            continue
    priority = {"md": 0, "txt": 1, "pdf": 3}
    readmes.sort(key=lambda x: priority.get(x[0], 2))
    return readmes


def _get_folder_links(page):
    try:
        links = page.query_selector_all("a")
    except Exception:
        return []
    folders = []
    for link in links:
        try:
            text = (link.inner_text() or "").strip()
            href = link.get_attribute("href") or ""
            if "type=folder" in href:
                folders.append((text, href))
        except Exception:
            continue
    return folders


def _to_full_url(href, project_id):
    if href.startswith("?"):
        return f"https://www.openicpsr.org/openicpsr/project/{project_id}/version/V1/view{href}"
    if href.startswith("http"):
        return href
    return f"https://www.openicpsr.org{href}"


# --- README fetching ---

def fetch_readme_text(page, project_id, file_path, ftype):
    """Fetch README content via getBinary endpoint."""
    if ftype == "pdf":
        return _fetch_pdf_readme(page, project_id, file_path)

    ctype = "text/x-web-markdown" if ftype == "md" else "text/plain"
    try:
        content = page.evaluate(
            """async ([pid, fpath, ct]) => {
                try {
                    const resp = await fetch(
                        `/openicpsr/project/${pid}/version/V1/getBinary?filePath=${fpath}&contentType=${ct}`,
                        {credentials: 'include'}
                    );
                    if (!resp.ok) return '';
                    return await resp.text();
                } catch(e) { return ''; }
            }""",
            [project_id, file_path, ctype],
        )
        return content or ""
    except Exception as e:
        print(f"    Fetch failed: {e}")
        return ""


def _fetch_pdf_readme(page, project_id, file_path):
    """Download PDF README and extract text with PyMuPDF."""
    try:
        import fitz
        pdf_b64 = page.evaluate(
            """async ([pid, fpath]) => {
                try {
                    const resp = await fetch(
                        `/openicpsr/project/${pid}/version/V1/getBinary?filePath=${fpath}&contentType=application/pdf`,
                        {credentials: 'include'}
                    );
                    if (!resp.ok) return '';
                    const buf = await resp.arrayBuffer();
                    const bytes = new Uint8Array(buf);
                    let binary = '';
                    for (let i = 0; i < bytes.length; i++) {
                        binary += String.fromCharCode(bytes[i]);
                    }
                    return btoa(binary);
                } catch(e) { return ''; }
            }""",
            [project_id, file_path],
        )
        if not pdf_b64:
            return ""
        pdf_bytes = base64.b64decode(pdf_b64)
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=True) as tmp:
            tmp.write(pdf_bytes)
            tmp.flush()
            doc = fitz.open(tmp.name)
            text = "".join(pg.get_text() for pg in doc)
            doc.close()
            return text
    except Exception as e:
        print(f"    PDF extract failed: {e}")
        return ""


# --- LLM classification ---

def classify_data_availability(readme_text):
    """Use Claude Sonnet to classify data availability from README text.

    Returns: {"classification": str, "rationale": str}
    Classification is one of: included, external_public, restricted, unknown
    """
    if not ANTHROPIC_API_KEY:
        print("    No ANTHROPIC_API_KEY — skipping LLM classification")
        return {"classification": "unknown", "rationale": "no API key"}

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    # Truncate very long READMEs to save tokens
    text = readme_text[:8000] if len(readme_text) > 8000 else readme_text

    try:
        response = client.messages.create(
            model=LLM_MODEL,
            max_tokens=200,
            messages=[{
                "role": "user",
                "content": f"""You are classifying the data availability of an economics paper's replication package based on its README file.

Classify into exactly one category:

- **included**: All data needed to replicate the paper is included in the package itself. The code can be run with only the files provided.
- **external_public**: Data is NOT in the package, but is freely downloadable from public sources (census, government sites, etc.). May require free registration but no paid access.
- **restricted**: Some or all data requires paid/institutional/confidential access (e.g., proprietary databases, hospital records, restricted-use government data, FSRDC).
- **unknown**: Can't determine from the README.

Respond with ONLY a JSON object, no other text:
{{"classification": "included|external_public|restricted|unknown", "rationale": "one sentence explaining why"}}

README:
{text}"""
            }]
        )

        import json
        result_text = response.content[0].text.strip()
        # Handle potential markdown wrapping
        if result_text.startswith("```"):
            result_text = re.sub(r"^```(?:json)?\n?", "", result_text)
            result_text = re.sub(r"\n?```$", "", result_text)
        result = json.loads(result_text)
        return {
            "classification": result.get("classification", "unknown"),
            "rationale": result.get("rationale", "")[:200],
        }

    except Exception as e:
        print(f"    LLM classification failed: {e}")
        return {"classification": "unknown", "rationale": f"LLM error: {str(e)[:100]}"}


def get_title(page):
    try:
        h1 = page.query_selector("h1")
        if h1:
            return h1.inner_text().strip()[:200]
    except Exception:
        pass
    return "Unknown"


def in_target_years(page, target_years):
    """Heuristic year filter. Returns True if target_years is None (no filter)."""
    if target_years is None:
        return True
    try:
        text = (page.inner_text("body") or "")[:20000]
    except Exception:
        return False
    return any(y in text for y in target_years)
