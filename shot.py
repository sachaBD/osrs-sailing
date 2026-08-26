"""Screenshot the app in a given state: python3 shot.py <out.png> [query]"""
import subprocess, sys, time, urllib.error, urllib.request
from playwright.sync_api import sync_playwright

URL = 'http://127.0.0.1:8000/'
out = sys.argv[1] if len(sys.argv) > 1 else 'shots/app.png'
query = sys.argv[2] if len(sys.argv) > 2 else ''

proc = None
try:
    urllib.request.urlopen(URL, timeout=2)
except Exception:
    proc = subprocess.Popen([sys.executable, '-m', 'http.server', '8000', '--bind', '127.0.0.1'],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(1.5)

import os
os.makedirs(os.path.dirname(out) or '.', exist_ok=True)
with sync_playwright() as pw:
    b = pw.chromium.launch()
    p = b.new_page(viewport={'width': 1500, 'height': 1000})
    errs = []
    p.on('pageerror', lambda e: errs.append(str(e)))
    p.on('console', lambda m: errs.append('console: ' + m.text) if m.type == 'error' else None)
    p.goto(URL + query, wait_until='networkidle')
    p.wait_for_timeout(1500)
    p.screenshot(path=out)
    print('wrote', out, '| errors:', errs[:3] if errs else 'none')
    b.close()
if proc:
    proc.terminate()
