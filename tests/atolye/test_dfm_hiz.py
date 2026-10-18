"""SPEC 61 K10 — DFM denetiminin hızı ve süre bütçesi. OCCT gerektirir.

SPEC 53 referans parçası henüz yok; SPEC 61 "Bağımlılıklar" maddesine göre ≤ 2000 üçgenlik uydurma parça
burada kurulur: 100 × 60 × 20 blok, R5 köşeli cep, R4 köşeli ikinci cep, üç Ø8 boydan delik.
Testler yalnız SPEC metninden ve atolye/dfm.py arayüzünden yazıldı; gövdeler okunmadı.
"""

from __future__ import annotations

import time

import pytest

pytest.importorskip("build123d", reason='build123d kurulu değil (pip install -e ".[cad]")')

from atolye.dfm import DERECELER, Rapor, denetle  # noqa: E402
from cam.model import Tool, ToolKind, ToolLibrary  # noqa: E402
from geometry.features import block, hole, pocket  # noqa: E402

pytestmark = pytest.mark.occt

BUTCE_S = 1.0  # SPEC 61 §8


def referans_parca():
    p = pocket(block(100, 60, 20), 30, 30, 40, 30, 8, r=5)
    for x in (70, 80, 90):
        p = hole(p, x, 15, 8)
    return pocket(p, 80, 42, 24, 16, 6, r=4)


def kutuphane() -> ToolLibrary:
    return ToolLibrary(
        [
            Tool(id=1, name="freze6", kind=ToolKind.FLAT, D=6.0, flute_length=25.0),
            Tool(id=2, name="freze10", kind=ToolKind.FLAT, D=10.0, flute_length=30.0),
            Tool(id=3, name="matkap8", kind=ToolKind.DRILL, D=8.0, flute_length=60.0),
        ]
    )


def test_referans_parca_ucgen_siniri():
    _, T = referans_parca().mesh()
    assert len(T) <= 2000


def test_hiz():
    lib = kutuphane()
    denetle(block(50, 40, 10), lib)  # ısınma: içe aktarma ve ilk çağrı maliyeti ölçüme girmesin
    part = referans_parca()
    t0 = time.perf_counter()
    r = denetle(part, lib)
    sure = time.perf_counter() - t0
    assert isinstance(r, Rapor)
    assert r.tamam is True
    assert sure < BUTCE_S, f"denetim {sure:.3f} s sürdü"
    assert 0.0 <= r.sure_s <= sure + 1e-3


def test_butce_asimi_kismi():
    r = denetle(referans_parca(), kutuphane(), butce_s=1e-6)  # istisna yok
    assert isinstance(r, Rapor)
    assert r.tamam is False
    kismi = [b for b in r.bulgular if b.derece == "uyari" and "kısmi" in (b.mesaj + " " + b.oneri).lower()]
    assert kismi, r.bulgular
    assert all(b.derece in DERECELER for b in r.bulgular)


def test_butcesiz_tamam():
    r = denetle(referans_parca(), kutuphane(), butce_s=None)
    assert r.tamam is True
