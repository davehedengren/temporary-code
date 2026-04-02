"""ICPSR authentication — session persistence + email login."""

import time
from datetime import datetime, timedelta
from config import EMAIL_LOGIN, PASSWORD, SESSION_FILE, SESSION_MAX_AGE_HOURS


def session_file_valid():
    """Check if session.json exists and is recent enough."""
    if not SESSION_FILE.exists():
        return False
    age = datetime.now().timestamp() - SESSION_FILE.stat().st_mtime
    return age < SESSION_MAX_AGE_HOURS * 3600


def save_session(context):
    """Save browser session state to disk."""
    context.storage_state(path=str(SESSION_FILE))
    print(f"  💾 Session saved to {SESSION_FILE.name}")


def is_login_page(page):
    """Check if the current page is an ICPSR login page."""
    url = page.url.lower()
    if "login" in url or "signin" in url or "sign-in" in url:
        return True
    try:
        content = page.content().lower()
        return "log in with" in content or "sign in with email" in content
    except Exception:
        return False


def login_with_email(page):
    """Automate the ICPSR email login flow."""
    if not EMAIL_LOGIN or not PASSWORD:
        print("  ❌ No EMAIL_LOGIN/PASSWORD in .env — cannot auto-login")
        return False

    print(f"  🔑 Logging in as {EMAIL_LOGIN}...")

    try:
        # Navigate to ICPSR login
        page.goto("https://www.openicpsr.org/openicpsr/login", wait_until="networkidle", timeout=30000)
        time.sleep(2)

        # Click "Sign in with email"
        email_btn = page.query_selector("text=Sign in with email")
        if email_btn:
            email_btn.click()
            page.wait_for_load_state("networkidle", timeout=15000)
            time.sleep(2)

        # Fill email
        email_input = page.query_selector('input[type="email"], input[name="email"], input[id*="email"]')
        if email_input:
            email_input.fill(EMAIL_LOGIN)
        else:
            # Try any visible text input
            inputs = page.query_selector_all('input[type="text"]')
            if inputs:
                inputs[0].fill(EMAIL_LOGIN)

        # Click next/continue if there's a multi-step flow
        next_btn = page.query_selector('button:has-text("Next"), button:has-text("Continue"), input[type="submit"]')
        if next_btn:
            next_btn.click()
            page.wait_for_load_state("networkidle", timeout=15000)
            time.sleep(2)

        # Fill password
        pw_input = page.query_selector('input[type="password"]')
        if pw_input:
            pw_input.fill(PASSWORD)

        # Submit
        submit_btn = page.query_selector(
            'button:has-text("Sign in"), button:has-text("Log in"), '
            'button:has-text("Submit"), input[type="submit"]'
        )
        if submit_btn:
            submit_btn.click()
        else:
            pw_input.press("Enter")

        page.wait_for_load_state("networkidle", timeout=30000)
        time.sleep(3)

        if is_login_page(page):
            print("  ❌ Still on login page — credentials may be wrong or flow changed")
            return False

        print("  ✅ Login successful!")
        return True

    except Exception as e:
        print(f"  ❌ Login failed: {e}")
        return False


def ensure_logged_in(page, context):
    """Check if logged in; if not, try session restore then email login."""
    if not is_login_page(page):
        return True

    print("  🔒 Login required...")

    # Try session restore
    if session_file_valid():
        print("  📂 Restoring saved session...")
        # Can't reload storage_state on existing context, so just try navigating
        page.goto("https://www.openicpsr.org/openicpsr/", wait_until="networkidle", timeout=30000)
        time.sleep(2)
        if not is_login_page(page):
            print("  ✅ Session restored!")
            return True

    # Email login
    if login_with_email(page):
        save_session(context)
        return True

    # Manual fallback
    print("\n  ⚠️  AUTO-LOGIN FAILED — please log in manually in the browser window.")
    print("     Waiting up to 5 minutes...")
    for _ in range(60):
        time.sleep(5)
        try:
            page.reload(wait_until="networkidle", timeout=15000)
        except Exception:
            pass
        if not is_login_page(page):
            print("  ✅ Manual login detected!")
            save_session(context)
            return True

    print("  ❌ Gave up waiting for login")
    return False


def check_session_alive(page, context):
    """Lightweight session check — auto-re-login if expired."""
    if not is_login_page(page):
        return True
    print("\n  🔒 Session expired mid-crawl...")
    return ensure_logged_in(page, context)
