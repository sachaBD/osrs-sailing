"""Browser-only fixtures. Everything here is marked `browser` automatically."""
from __future__ import annotations

import base64
import pathlib

import pytest

VIEWPORT = {'width': 1600, 'height': 1000}
PHONE = {'width': 390, 'height': 844}

# One transparent pixel, served for every map tile.
PIXEL = base64.b64decode(
    'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk'
    'YPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==')


def stub_tiles(page) -> None:
    """Answer every map tile with that pixel, without leaving the machine.

    A view of the map is 64 tiles, and without `web/tiles` each one 404s and
    then retries the wiki - which was the whole cost of this suite.
    `test_map_tiles_load` wants the real ones and runs without this.
    """
    def fulfil(route):
        route.fulfill(status=200, content_type='image/png', body=PIXEL)

    page.route('**/tiles/**', fulfil)
    page.route('**maps.runescape.wiki/**', fulfil)


def open_app(page, url: str):
    """Load the app and wait for its first render, not for the network.

    main.js renders the table on its last line, so a row means every module
    parsed, ran and wired itself up.
    """
    page.goto(url, wait_until='commit')
    page.wait_for_selector('#tbody tr', state='attached')
    return page


def pytest_collection_modifyitems(items):
    """Mark the tests in this directory, and only those: the hook is handed
    every collected item, not just the ones under this conftest."""
    here = pathlib.Path(__file__).parent
    for item in items:
        if here in pathlib.Path(str(item.fspath)).parents:
            item.add_marker(pytest.mark.browser)


def watched(page, url: str):
    """A page that records every console error and page error it raises."""
    errors: list[str] = []
    page.on('console', lambda m: errors.append(m.text) if m.type == 'error' else None)
    page.on('pageerror', lambda e: errors.append(str(e)))
    page.errors = errors
    page.base_url = url + '/'
    stub_tiles(page)
    # The view persists itself to localStorage as well as to the URL, so a
    # plain reload is not a clean slate. Clearing before the app's own scripts
    # run makes every navigation a first visit, which used to take two of them.
    page.add_init_script('try { localStorage.clear(); } catch (e) { /* private mode */ }')
    return page


@pytest.fixture(scope='module')
def app(browser, app_url):
    """The app open in a page, with console and page errors collected.

    Module-scoped because launching a page is the slow part; `fresh` below puts
    the app back to its initial state per test.
    """
    page = watched(browser.new_page(viewport=VIEWPORT), app_url)
    open_app(page, page.base_url)
    yield page
    page.close()


@pytest.fixture
def fresh(app):
    """The app in its first-visit state."""
    return open_app(app, app.base_url)


@pytest.fixture(scope='module')
def phone_page(browser, app_url):
    """The app on a touch screen the size of a phone."""
    context = browser.new_context(viewport=PHONE, has_touch=True, is_mobile=True)
    page = watched(context.new_page(), app_url)
    yield page
    context.close()


@pytest.fixture
def phone(phone_page):
    return open_app(phone_page, phone_page.base_url + '?map=1')


def rows(page) -> int:
    """Visible task rows, ignoring the single 'no tasks match' placeholder."""
    if page.locator('#tbody .empty').count():
        return 0
    return page.locator('#tbody tr').count()


# Every filter re-renders the whole table, so the row count is the signal that
# a control has been acted on - and the thing the fixed waits were waiting for.
COUNTED = 'document.querySelectorAll("#tbody tr").length'


def wait_for_rows(page, count: int) -> None:
    """Wait until the table holds exactly `count` rows."""
    page.wait_for_function(f'n => {COUNTED} === n', arg=count)


def wait_for_fewer_rows(page, than: int) -> int:
    """Wait until the table has narrowed below `than`, and say how far."""
    page.wait_for_function(
        f'n => {COUNTED} < n || document.querySelector("#tbody .empty")', arg=than)
    return rows(page)


def pick_multi(page, panel_id: str, value: str) -> None:
    """Open a checkbox dropdown and tick one option."""
    page.click(f'{panel_id} .ms-button')
    page.check(f'{panel_id} .ms-options input[value="{value}"]')
    page.click('h1')          # close the menu
