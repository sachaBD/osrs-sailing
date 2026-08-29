"""Browser-only fixtures. Everything here is marked `browser` automatically."""
from __future__ import annotations

import pathlib

import pytest

VIEWPORT = {'width': 1600, 'height': 1000}


def pytest_collection_modifyitems(items):
    """Mark the tests in this directory, and only those: the hook is handed
    every collected item, not just the ones under this conftest."""
    here = pathlib.Path(__file__).parent
    for item in items:
        if here in pathlib.Path(str(item.fspath)).parents:
            item.add_marker(pytest.mark.browser)


@pytest.fixture(scope='module')
def app(browser, app_url):
    """The app open in a page, with console and page errors collected.

    Module-scoped because launching a page and loading the map is the slow
    part; `fresh` below puts the app back to its initial state per test.
    """
    page = browser.new_page(viewport=VIEWPORT)
    errors: list[str] = []
    page.on('console', lambda m: errors.append(m.text) if m.type == 'error' else None)
    page.on('pageerror', lambda e: errors.append(str(e)))
    page.errors = errors
    page.base_url = app_url + '/'
    page.goto(page.base_url, wait_until='networkidle')
    yield page
    page.close()


@pytest.fixture
def fresh(app):
    """The app in its first-visit state.

    The view persists itself to localStorage as well as the URL, so a bare
    reload is not a clean slate: without the clear, one test's filters and map
    position leak into the next.
    """
    app.goto(app.base_url, wait_until='networkidle')
    app.evaluate('() => localStorage.clear()')
    app.goto(app.base_url, wait_until='networkidle')
    return app


def rows(page) -> int:
    """Visible task rows, ignoring the single 'no tasks match' placeholder."""
    if page.locator('#tbody .empty').count():
        return 0
    return page.locator('#tbody tr').count()


def pick_multi(page, panel_id: str, value: str) -> None:
    """Open a checkbox dropdown and tick one option."""
    page.click(f'{panel_id} .ms-button')
    page.check(f'{panel_id} .ms-options input[value="{value}"]')
    page.click('h1')          # close the menu
    page.wait_for_timeout(80)
