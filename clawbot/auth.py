"""ICPSR authentication — wait for manual login, don't fight Cloudflare."""

import time


def is_captcha_page(page):
    """Check if the current page is a Cloudflare CAPTCHA challenge.

    Only checks visible text and page title — not full HTML source,
    which can contain 'captcha' or 'challenge' in scripts/ads on normal pages.
    """
    try:
        title = (page.title() or "").lower()
        if "just a moment" in title or "attention required" in title:
            return True
        # Check visible body text (first 2000 chars to avoid scanning huge pages)
        visible = (page.inner_text("body") or "")[:2000].lower()
        return any(phrase in visible for phrase in [
            "verify you are human",
            "checking your browser",
            "checking if the site connection is secure",
        ])
    except Exception:
        return False


def is_logged_out(page):
    """Check if we're logged out. Looks for login page OR 'Log In' in nav bar."""
    url = page.url.lower()
    if "login" in url or "signin" in url or "sign-in" in url:
        return True
    try:
        content = page.content()
        lower = content.lower()
        # Check for login page content
        if "log in with" in lower or "sign in with email" in lower:
            return True
        # Check for "Log In/Create Account" link in nav bar (logged out state)
        if "log in/create account" in lower or "log in / create account" in lower:
            return True
        # Check for My Account link (logged in state) — if missing, we're logged out
        if "my account" not in lower and "myaccount" not in lower:
            # Only flag as logged out if we're actually on an openicpsr page
            if "openicpsr.org" in url:
                return True
        return False
    except Exception:
        return False


def wait_for_human(page, reason="action needed", timeout_hours=12):
    """Wait for the user to do something in the browser (login, CAPTCHA, etc.).

    Checks every 30 seconds. Waits up to timeout_hours.
    Prints a reminder every 10 minutes.
    """
    checks = timeout_hours * 120  # 30-sec intervals
    print(f"\n    >>> {reason} — please act in the Chrome window <<<", flush=True)
    print(f"    Checking every 30s, will wait up to {timeout_hours}h...", flush=True)

    for i in range(checks):
        time.sleep(30)

        # Print reminder every 10 min
        if i > 0 and i % 20 == 0:
            minutes = (i * 30) // 60
            print(f"    Still waiting... ({minutes} min elapsed)", flush=True)

        try:
            # Refresh to check current state
            if i % 4 == 0:  # reload every 2 min to pick up login changes
                try:
                    page.reload(wait_until="networkidle", timeout=15000)
                except Exception:
                    pass

            if not is_captcha_page(page) and not is_logged_out(page):
                print(f"    Detected login/solve! Resuming...", flush=True)
                return True
        except Exception:
            continue

    print(f"    Gave up waiting after {timeout_hours}h", flush=True)
    return False


def login_with_google(page):
    """Click 'Sign in with Google' — works if already authenticated in Chrome."""
    try:
        print("    Attempting Google login...", flush=True)
        page.goto("https://www.openicpsr.org/openicpsr/login", wait_until="networkidle", timeout=30000)
        time.sleep(3)

        if is_captcha_page(page):
            if not wait_for_human(page, "CAPTCHA on login page"):
                return False

        # Click the Google sign-in button
        google_btn = page.query_selector("text=Sign in with Google")
        if not google_btn:
            google_btn = page.query_selector("text=Google")
        if not google_btn:
            print("    No Google login button found", flush=True)
            return False

        google_btn.click()
        # Google OAuth may open a popup or redirect — wait for it
        time.sleep(5)
        page.wait_for_load_state("networkidle", timeout=30000)
        time.sleep(3)

        if not is_logged_out(page):
            print("    Google login successful!", flush=True)
            return True

        # Google might show account picker — try clicking the first account
        try:
            # Look for an email/account in the Google picker
            account = page.query_selector('[data-email], .lCoei, div[data-identifier]')
            if account:
                account.click()
                time.sleep(3)
                page.wait_for_load_state("networkidle", timeout=30000)
                time.sleep(3)
                if not is_logged_out(page):
                    print("    Google login successful (picked account)!", flush=True)
                    return True
        except Exception:
            pass

        print("    Google login didn't complete automatically", flush=True)
        return False

    except Exception as e:
        print(f"    Google login error: {e}", flush=True)
        return False


def ensure_logged_in(page, context):
    """Check if logged in. Try Google auto-login first, then wait for manual."""
    if is_captcha_page(page):
        if not wait_for_human(page, "CAPTCHA detected"):
            return False

    if not is_logged_out(page):
        return True

    # Try Google login (one-click if already authenticated in Chrome)
    if login_with_google(page):
        return True

    # Fall back to waiting for manual login
    return wait_for_human(page, "Auto-login failed — please log in at the Chrome window")


def check_session_alive(page, context):
    """Lightweight session check mid-crawl."""
    if is_captcha_page(page):
        wait_for_human(page, "CAPTCHA mid-crawl")

    if is_logged_out(page):
        print("    Session expired mid-crawl — trying Google login...", flush=True)
        if login_with_google(page):
            return True
        return wait_for_human(page, "Auto-login failed mid-crawl — please log in")

    return True
