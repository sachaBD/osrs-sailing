"""Run the JS unit tests (tests/unit.js) in a real browser.

Replaces the hand-rolled static checker: the browser parses the modules for
real, so syntax errors and bad imports surface as page errors rather than being
guessed at with regexes.
"""
from __future__ import annotations

import subprocess
import sys
import time
import urllib.error
import urllib.request

from playwright.sync_api import sync_playwright

BASE = 'http://127.0.0.1:8000'
PAGE = f'{BASE}/tests/unit.html'


def serve() -> subprocess.Popen | None:
    """Start the static server unless one is already listening."""
    try:
        urllib.request.urlopen(BASE, timeout=2)
        return None
    except (urllib.error.URLError, OSError):
        pass
    proc = subprocess.Popen(
        [sys.executable, '-m', 'http.server', '8000', '--bind', '127.0.0.1'],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(50):
        try:
            urllib.request.urlopen(BASE, timeout=1)
            return proc
        except (urllib.error.URLError, OSError):
            time.sleep(0.2)
    proc.terminate()
    raise SystemExit('could not start the server')


def main() -> int:
    proc = serve()
    errors: list[str] = []
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            page = browser.new_page()
            page.on('pageerror', lambda e: errors.append(str(e)))
            page.on('console', lambda m: errors.append(m.text) if m.type == 'error' else None)
            page.goto(PAGE, wait_until='networkidle')
            page.wait_for_timeout(300)
            results = page.evaluate('() => window.__results || null')
            browser.close()
    finally:
        if proc:
            proc.terminate()

    if errors:
        print('MODULE ERRORS:')
        for e in errors[:10]:
            print(f'  {e}')
        return 1
    if not results:
        print('no results: the test module did not finish')
        return 1

    for r in results:
        mark = 'ok  ' if r['ok'] else 'FAIL'
        detail = f"  ({r['detail']})" if r['detail'] else ''
        print(f"  [{mark}] {r['name']}{detail}")

    failed = [r for r in results if not r['ok']]
    print()
    print(f'UNIT TESTS: {len(results) - len(failed)}/{len(results)} passed'
          + (' - FAILED' if failed else ''))
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
