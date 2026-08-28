"""Drive the real page in a headless browser and assert it actually works.

tests/unit.js covers the pure logic; this covers the wiring, which is where the
bugs have actually been: four filter dropdowns once shipped dead because nothing
clicked them. Every control must change the visible row count, state must
survive a reload through the URL, the map must render, pan and stay reachable,
and the console must stay clean.

    make test               run the checks
    make shots              also write screenshots into shots/
"""
import subprocess
import sys
import time
import urllib.error
import urllib.request

from playwright.sync_api import sync_playwright

URL = 'http://127.0.0.1:8000/'
SHOT_DIR = 'shots'
VIEWPORT = {'width': 1600, 'height': 1000}


def serve():
    """Start the app server if it isn't already up. Returns a process or None."""
    try:
        urllib.request.urlopen(URL, timeout=2)
        return None
    except (urllib.error.URLError, OSError):
        pass
    proc = subprocess.Popen(
        [sys.executable, '-m', 'http.server', '8000', '--bind', '127.0.0.1'],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(50):
        try:
            urllib.request.urlopen(URL, timeout=1)
            return proc
        except (urllib.error.URLError, OSError):
            time.sleep(0.2)
    raise SystemExit('could not start the server')


class Checks:
    def __init__(self):
        self.failures = []

    def check(self, name, condition, detail=''):
        mark = 'ok  ' if condition else 'FAIL'
        print(f'  [{mark}] {name}' + (f'  ({detail})' if detail else ''))
        if not condition:
            self.failures.append(f'{name}: {detail}')
        return condition


def rows(page):
    """Visible task rows, ignoring the single 'no tasks match' placeholder."""
    if page.locator('#tbody .empty').count():
        return 0
    return page.locator('#tbody tr').count()


def pick_multi(page, panel_id, value):
    """Open a checkbox dropdown and tick one option."""
    page.click(f'{panel_id} .ms-button')
    page.check(f'{panel_id} .ms-options input[value="{value}"]')
    page.click('h1')          # close the menu
    page.wait_for_timeout(80)


def main():
    shots = '--shots' in sys.argv
    proc = serve()
    c = Checks()

    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(viewport=VIEWPORT)

        errors = []
        page.on('console', lambda m: errors.append(m.text) if m.type == 'error' else None)
        page.on('pageerror', lambda e: errors.append(str(e)))

        page.goto(URL, wait_until='networkidle')
        base = rows(page)
        c.check('table renders all tasks', base == 439, f'{base} rows')

        # every multi-select must actually filter, which is what broke before
        for panel, value, label in [('#f-region', 'Zeah', 'region'),
                                    ('#f-ocean', 'Northern Ocean', 'ocean'),
                                    ('#f-from', 'Rellekka', 'origin'),
                                    ('#f-to', 'Prifddinas', 'destination')]:
            pick_multi(page, panel, value)
            n = rows(page)
            c.check(f'{label} filter narrows the table', 0 < n < base, f'{n} rows')
            c.check(f'{label} reaches the URL', value.split()[0] in page.url, page.url[-60:])
            page.click('#reset')
            page.wait_for_timeout(80)
            c.check(f'{label} filter resets', rows(page) == base)

        # scalar filters
        page.fill('#f-min', '70')
        page.wait_for_timeout(80)
        lvl = rows(page)
        c.check('level filter narrows the table', 0 < lvl < base, f'{lvl} rows')

        page.check('#f-recover')
        page.wait_for_timeout(80)
        rec = rows(page)
        c.check('recover filter narrows further', rec <= lvl, f'{rec} rows')

        # a reload must reproduce the same view from the URL alone
        url_before = page.url
        page.goto(url_before, wait_until='networkidle')
        c.check('URL restores the filtered view', rows(page) == rec,
                f'{rows(page)} vs {rec}')
        c.check('controls reflect the URL', page.input_value('#f-min') == '70')

        page.click('#reset')
        page.wait_for_timeout(80)

        # the map
        page.click('#map-toggle')
        page.wait_for_timeout(1200)
        c.check('map panel opens', page.is_visible('#map-viewport'))
        markers = page.locator('#map-overlay .marker').count()
        c.check('all ports have markers', markers == 30, f'{markers} markers')
        # background routes are suppressed at full dataset size (they were a
        # hairball), so absence here is the wanted behaviour
        routes = page.locator('#map-overlay .route').count()
        c.check('no route hairball on the full set', routes == 0, f'{routes} routes')
        page.check('#f-all-routes')
        page.wait_for_timeout(200)
        c.check('routes appear when asked for',
                page.locator('#map-overlay .route').count() > 0)
        page.uncheck('#f-all-routes')
        page.wait_for_timeout(150)

        tiles = page.locator('#map-tiles img').count()
        broken = page.evaluate(
            "Array.from(document.querySelectorAll('#map-tiles img'))"
            ".filter(i => i.complete && i.naturalWidth === 0).length")
        c.check('map tiles load', tiles > 0 and broken == 0,
                f'{tiles} tiles, {broken} broken')

        # dragging must pan by exactly the mouse delta, without selecting text
        box = page.locator('#map-viewport').bounding_box()
        cx, cy = box['x'] + box['width'] / 2, box['y'] + box['height'] / 2
        start = page.evaluate('() => ({x: __app.view.x, y: __app.view.y})')
        page.mouse.move(cx, cy)
        page.mouse.down()
        for i in range(1, 7):
            page.mouse.move(cx - i * 20, cy - i * 10)
            page.wait_for_timeout(16)
        page.mouse.up()
        page.wait_for_timeout(120)
        end = page.evaluate('() => ({x: __app.view.x, y: __app.view.y})')
        c.check('drag pans by the mouse delta',
                (round(end['x'] - start['x']), round(end['y'] - start['y'])) == (-120, -60),
                f"{round(end['x'] - start['x'])},{round(end['y'] - start['y'])}")
        c.check('drag selects no text', page.evaluate('() => String(getSelection())') == '')

        # and the map cannot be flung out of reach
        page.mouse.move(cx, cy)
        page.mouse.down()
        for i in range(1, 20):
            page.mouse.move(cx + i * 130, cy + i * 100)
            page.wait_for_timeout(8)
        page.mouse.up()
        page.wait_for_timeout(150)
        onscreen = page.evaluate('''() => {
          const b = document.querySelector('#map-viewport').getBoundingClientRect();
          const v = __app.view, M = __app.MAP_META;
          const w = M.size[0] * v.scale, h = M.size[1] * v.scale;
          const left = b.left + v.x, top = b.top + v.y;
          return Math.min(
            Math.min(b.right, left + w) - Math.max(b.left, left),
            Math.min(b.bottom, top + h) - Math.max(b.top, top));
        }''')
        c.check('map cannot be panned off screen', onscreen > 50, f'{round(onscreen)}px visible')
        page.click('#map-fit')
        page.wait_for_timeout(150)

        # clicking a marker filters the table
        # click the dot, not the <g>: its bbox includes the label above, so the
        # bbox centre can land in empty space between label and marker
        page.locator('#map-overlay .marker .dot').first.click()
        page.wait_for_timeout(150)
        picked = rows(page)
        c.check('clicking a port filters the table', 0 < picked < base, f'{picked} rows')
        c.check('port selection reaches the URL', 'port=' in page.url)

        # route builder
        page.click('#reset')
        page.wait_for_timeout(100)
        for i in range(4):
            page.locator('#tbody .trip-btn').nth(i).click()
            page.wait_for_timeout(60)
        c.check('trip panel appears', page.is_visible('#trip-panel'))
        stops = page.locator('#trip-stops li').count()
        legs = page.locator('.trip-leg').count()
        c.check('trip sequences into stops', stops >= 4, f'{stops} stops')
        c.check('trip draws one leg between stops', legs == stops - 1,
                f'{legs} legs for {stops} stops')
        c.check('trip reaches the URL', 'trip=' in page.url)

        # every task must be picked up before it is delivered
        order = page.evaluate('''() => {
          const t = __app.currentTrip();
          const seen = {};
          let ok = true;
          t.stops.forEach((s, i) => {
            s.picks.forEach(p => { seen[p.id] = i; });
            s.drops.forEach(d => { if (!(d.id in seen) || seen[d.id] > i) ok = false; });
          });
          return { ok, stops: t.stops.length, tasks: t.tasks.length };
        }''')
        c.check('pickups precede deliveries', order['ok'], str(order))

        page.goto(page.url, wait_until='networkidle')
        c.check('trip survives a reload', page.locator('#trip-stops li').count() == stops)

        # ports the route sails past, and the corridor control
        near = page.locator('.marker.near-route').count()
        c.check('route highlights ports it sails past', near > 0, f'{near} ports')
        c.check('passing list is shown', page.is_visible('#trip-passing'))
        page.fill('#trip-corridor', '20')
        page.wait_for_timeout(150)
        tight = page.locator('.marker.near-route').count()
        c.check('a tighter corridor highlights fewer', tight < near, f'{tight} at 20 tiles')
        page.fill('#trip-corridor', '400')
        page.wait_for_timeout(150)
        wide = page.locator('.marker.near-route').count()
        c.check('a wider corridor highlights more', wide > near, f'{wide} at 400 tiles')
        page.fill('#trip-corridor', '120')
        page.wait_for_timeout(120)

        page.click('#trip-clear')
        page.wait_for_timeout(100)
        c.check('clear trip empties the panel', not page.is_visible('#trip-panel'))

        if shots:
            import os
            os.makedirs(SHOT_DIR, exist_ok=True)
            page.screenshot(path=f'{SHOT_DIR}/map.png')
            page.click('#map-clear')
            page.click('#map-toggle')
            page.wait_for_timeout(200)
            page.screenshot(path=f'{SHOT_DIR}/table.png')
            print(f'  screenshots -> {SHOT_DIR}/map.png, {SHOT_DIR}/table.png')

        c.check('no console errors', not errors, '; '.join(errors[:3]))
        browser.close()

    if proc:
        proc.terminate()

    print()
    if c.failures:
        print(f'SMOKE TEST: {len(c.failures)} FAILED')
        return 1
    print('SMOKE TEST: pass')
    return 0


if __name__ == '__main__':
    sys.exit(main())
