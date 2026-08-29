"""Run tests/browser/unit.js in a real browser and report each check.

The browser parses the modules for real, so syntax errors and bad imports
surface as page errors rather than being guessed at with regexes.
"""
from __future__ import annotations

import pytest


@pytest.fixture(scope='module')
def results(browser, repo_url):
    """Every check unit.js recorded, plus any error the page raised."""
    page = browser.new_page()
    errors: list[str] = []
    page.on('pageerror', lambda e: errors.append(str(e)))
    page.on('console', lambda m: errors.append(m.text) if m.type == 'error' else None)
    page.goto(f'{repo_url}/tests/browser/unit.html', wait_until='networkidle')
    page.wait_for_timeout(300)
    out = page.evaluate('() => window.__results || null')
    page.close()
    assert not errors, 'the module graph did not load: ' + '; '.join(errors[:5])
    assert out, 'no results: the test module did not finish'
    return out


def test_the_suite_ran(results):
    assert len(results) > 10, f'only {len(results)} checks ran'


def test_every_check_passes(results):
    failed = [f"{r['name']}: {r['detail']}" for r in results if not r['ok']]
    assert not failed, '\n'.join(failed)
