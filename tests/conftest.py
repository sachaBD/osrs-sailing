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

import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
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


@pytest.fixture(scope='session')
def browser():
    playwright = pytest.importorskip('playwright.sync_api')
    with playwright.sync_playwright() as pw:
        b = pw.chromium.launch()
        yield b
        b.close()
