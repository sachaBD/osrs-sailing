"""Shared fixtures: the static server, and a browser page pointed at it.

The three browser entry points used to carry a copy each of "is a server up,
else spawn http.server, else sleep"; it lives here now, once.

Two document roots, deliberately:

    web/   what `make serve` serves, and all the app sees
    the repo root, only so the JS unit page under tests/browser/ can import
    the modules it is testing

Anything needing a browser is marked `browser`, so `pytest -m 'not browser'`
is the fast suite.
"""
from __future__ import annotations

import os
import pathlib
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
import warnings
from collections.abc import Iterator

import pytest

from porttasks import generate
from porttasks.paths import ROOT, WEB


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]


def _serve(directory) -> Iterator[str]:
    """Serve `directory` on a free port for the life of the fixture."""
    port = _free_port()
    base = f'http://127.0.0.1:{port}'
    proc = subprocess.Popen(
        [sys.executable, '-m', 'http.server', str(port),
         '--bind', '127.0.0.1', '--directory', str(directory)],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(100):
            try:
                urllib.request.urlopen(base, timeout=1)
                break
            except (urllib.error.URLError, OSError):
                time.sleep(0.1)
        else:
            raise RuntimeError(f'server for {directory} never came up')
        yield base
    finally:
        proc.terminate()
        proc.wait(timeout=5)


@pytest.fixture(scope='session')
def generated() -> None:
    """web/js/generated.js, rebuilt from the tables the tests are run against."""
    generate.main()


@pytest.fixture(scope='session')
def app_url(generated) -> Iterator[str]:
    """The app, served exactly as `make serve` serves it."""
    yield from _serve(WEB)


@pytest.fixture(scope='session')
def repo_url(generated) -> Iterator[str]:
    """The repo root, so tests/browser/unit.html can reach web/js/."""
    yield from _serve(ROOT)


# The binary inside a playwright browser build, per platform. The headless
# shell first because that is what `launch()` runs when headless, and the two
# are not quite the same browser: the full one asks for a favicon, which the
# unit page has not got, and a 404 is a console error the suite counts.
_SHELL = (
    'chromium_headless_shell-*/chrome-linux/headless_shell',
    'chromium_headless_shell-*/chrome-mac/headless_shell',
    'chromium_headless_shell-*/chrome-win/headless_shell.exe',
)
_FULL = (
    'chromium-*/chrome-linux/chrome',
    'chromium-*/chrome-mac/Chromium.app/Contents/MacOS/Chromium',
    'chromium-*/chrome-win/chrome.exe',
)


def _installed_chromium() -> pathlib.Path | None:
    """A chromium already on this machine: a headless shell for choice, and
    the newest build of whichever kind it ends up being."""
    root = pathlib.Path(os.environ.get('PLAYWRIGHT_BROWSERS_PATH')
                        or pathlib.Path.home() / '.cache' / 'ms-playwright')
    for patterns in (_SHELL, _FULL):
        found = [p for pattern in patterns for p in root.glob(pattern) if p.exists()]
        # build numbers sort as numbers, not as text: -1200 is newer than -999
        if found:
            return max(found, key=_build)
    return None


def _build(path: pathlib.Path) -> int:
    for part in path.parts:
        if part.startswith('chromium') and '-' in part:
            tail = part.rsplit('-', 1)[1]
            return int(tail) if tail.isdigit() else 0
    return 0


def _launch(pw):
    """Chromium, whichever build this machine actually has.

    The pip package and the browser it downloads are versioned together, so an
    environment that provisions browsers separately - a prebuilt container, a
    cached CI image - readily ends up holding a build the installed playwright
    does not ask for, and launching then fails on a path that does not exist.
    It is still a Chromium and it still drives the app, so run the one that is
    there rather than losing the whole browser suite over the version.
    """
    try:
        return pw.chromium.launch()
    except Exception:
        found = _installed_chromium()
        if found is None:
            raise
        warnings.warn(f'playwright wants a chromium this machine has not got; using {found}',
                      stacklevel=2)
        return pw.chromium.launch(executable_path=str(found))


@pytest.fixture(scope='session')
def browser():
    playwright = pytest.importorskip('playwright.sync_api')
    with playwright.sync_playwright() as pw:
        b = _launch(pw)
        yield b
        b.close()
