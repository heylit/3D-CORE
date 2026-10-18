"""
Kök pytest ayarları (tüm testler için).

1. `occt` işaretli testler build123d kurulu değilse atlanır.
2. Uygulanmamış kod kuralı: bir test SADECE NotImplementedError yüzünden düşerse "uygulanmamış" (xfail)
   sayılır. TDD'de önce yazılan kırmızı testler commit'i ve paralel dalları engellemez; gerçek hatalar
   (yanlış sayı, beklenmeyen hata) yine kırmızıdır. Bir SPEC'in bitmesi için kendi testlerinde
   0 "uygulanmamış" olmalı (BASLANGIC.md bölüm 5).
"""

from __future__ import annotations

import importlib.util

import pytest

HAS_OCCT = importlib.util.find_spec("build123d") is not None


def pytest_collection_modifyitems(config, items):
    if HAS_OCCT:
        return
    skip = pytest.mark.skip(reason='build123d kurulu değil (pip install -e ".[cad]")')
    for item in items:
        if "occt" in item.keywords:
            item.add_marker(skip)


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    rep = outcome.get_result()
    if call.when == "call" and rep.failed and call.excinfo is not None:
        if call.excinfo.errisinstance(NotImplementedError):
            rep.outcome = "skipped"
            rep.wasxfail = "uygulanmamış (NotImplementedError)"


def pytest_terminal_summary(terminalreporter):
    n = len([r for r in terminalreporter.stats.get("xfailed", [])
             if "uygulanmamış" in getattr(r, "wasxfail", "")])
    if n:
        terminalreporter.write_line(f"Uygulanmamış test: {n} (NotImplementedError; SPEC bitince 0 olmalı)")
