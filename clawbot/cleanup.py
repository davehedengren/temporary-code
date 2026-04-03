"""Cleanup utilities for Playwright temp artifacts."""

import glob
import os
import shutil
import tempfile


def cleanup_playwright_artifacts():
    """Remove Playwright temp artifact dirs that accumulate in system temp.

    Playwright creates playwright-artifacts-* directories in the system temp
    folder on every CDP connection. These never get cleaned up automatically
    and can consume tens of GB over time.
    """
    tmp = tempfile.gettempdir()
    for d in glob.glob(os.path.join(tmp, "playwright-artifacts-*")):
        try:
            shutil.rmtree(d)
        except Exception:
            pass
