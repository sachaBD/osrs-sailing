"""Screenshot the app in a given state.

    python3 tools/screenshot.py [out.png] [query string]

Serves web/ on a free port, loads the page, and writes a PNG into out/shots/
by default. The end-to-end checks live in tests/browser; this is for looking.
"""
from __future__ import annotations

import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request

from playwright.sync_api import sync_playwright

from porttasks import generate
from porttasks.paths import SHOTS, WEB

VIEWPORT = {'width': 1500, 'height': 1000}


def serve(directory) -> tuple[subprocess.Popen, str]:
    with socket.socket() as s:
        s.bind(('127.0.0.1', 0))
        port = s.getsockname()[1]
    base = f'http://127.0.0.1:{port}'
    proc = subprocess.Popen(
        [sys.executable, '-m', 'http.server', str(port),
         '--bind', '127.0.0.1', '--directory', str(directory)],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(100):
        try:
            urllib.request.urlopen(base, timeout=1)
            return proc, base
        except (urllib.error.URLError, OSError):
            time.sleep(0.1)
    proc.terminate()
    raise SystemExit('could not start the server')


def main() -> None:
    out = sys.argv[1] if len(sys.argv) > 1 else str(SHOTS / 'app.png')
    query = sys.argv[2] if len(sys.argv) > 2 else ''

    generate.main()
    SHOTS.mkdir(parents=True, exist_ok=True)
    proc, base = serve(WEB)
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            page = browser.new_page(viewport=VIEWPORT)
            errors: list[str] = []
            page.on('pageerror', lambda e: errors.append(str(e)))
            page.on('console', lambda m: errors.append(m.text) if m.type == 'error' else None)
            page.goto(f'{base}/{query}', wait_until='networkidle')
            page.wait_for_timeout(1500)
            page.screenshot(path=out)
            browser.close()
    finally:
        proc.terminate()
    print(f'wrote {out} | errors: {errors[:3] if errors else "none"}')


if __name__ == '__main__':
    main()
