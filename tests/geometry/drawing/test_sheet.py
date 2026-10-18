"""SPEC 16 — K9 pafta yerleşimi ve K13 uçtan uca çizim (geometry/drawing/sheet.py). OCCT gerektirir.

Teori (ISO 5456-2, birinci açı): üst görünüş önün altında, soldan görünüş önün sağında, sağdan görünüş
önün solunda; aralarında kağıt üzerinde g boşluk; ön ile üst aynı pafta X'ini, ön ile yanlar aynı pafta
Y'sini paylaşır. Pafta = k · görünüş + öteleme. Uygulama gövdeleri okunmadı.
Uydurma geometri: blok 100×60×30, delik d = 10 eksen (20, 25), cep 40×20 r = 5 t = 8 merkez (65, 30).
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from functools import cache

import numpy as np
import pytest

pytest.importorskip("build123d", reason='build123d kurulu değil (pip install -e ".[cad]")')

from geometry.drawing.dxf import read_dxf, write_dxf  # noqa: E402
from geometry.drawing.sheet import layout, make_drawing  # noqa: E402
from geometry.drawing.svg import write_svg  # noqa: E402
from geometry.drawing.types import Line2D, Text2D  # noqa: E402
from geometry.drawing.views import project  # noqa: E402
from geometry.features import block, hole, pocket  # noqa: E402
from geometry.part import GeometryError  # noqa: E402

from ._yardim import toplam_boy  # noqa: E402

pytestmark = pytest.mark.occt

A, B, C = 100.0, 60.0, 30.0
D, HX, HY = 10.0, 20.0, 25.0
G = 20.0


@cache
def _parca():
    return pocket(hole(block(A, B, C), HX, HY, D), 65.0, 30.0, 40.0, 20.0, 8.0, r=5.0)


@cache
def _gorunusler():
    return tuple(project(_parca(), yon) for yon in ("on", "ust", "sol", "sag"))


def _pafta_kutusu(pv):
    """Yerleşmiş görünüşün pafta sınır kutusu: k · bbox + öteleme."""
    lo, hi = pv.view.bbox()
    off = np.asarray(pv.offset, float)
    return pv.scale * np.asarray(lo, float) + off, pv.scale * np.asarray(hi, float) + off


def _adla(sheet):
    return {pv.view.name: pv for pv in sheet.views}


# --- K9: layout ------------------------------------------------------------------------------------


def test_birinci_aci_yerlesimi():
    sheet = layout(list(_gorunusler()), scale=1.0, gap=G)
    pv = _adla(sheet)
    assert set(pv) == {"on", "ust", "sol", "sag"}
    on_lo, on_hi = _pafta_kutusu(pv["on"])
    ust_lo, ust_hi = _pafta_kutusu(pv["ust"])
    sol_lo, sol_hi = _pafta_kutusu(pv["sol"])
    sag_lo, sag_hi = _pafta_kutusu(pv["sag"])
    # üst görünüş önün altında, arada g
    assert on_lo[1] - ust_hi[1] == pytest.approx(G, abs=1e-9)
    # soldan görünüş önün sağında, sağdan görünüş önün solunda
    assert sol_lo[0] - on_hi[0] == pytest.approx(G, abs=1e-9)
    assert on_lo[0] - sag_hi[0] == pytest.approx(G, abs=1e-9)
    # yan görünüşler önle aynı yükseklikte (v = z ortak)
    for lo, hi in ((sol_lo, sol_hi), (sag_lo, sag_hi)):
        assert lo[1] == pytest.approx(on_lo[1], abs=1e-9)
        assert hi[1] == pytest.approx(on_hi[1], abs=1e-9)


@pytest.mark.parametrize("k", [0.5, 2.0])
def test_bosluk_olcekten_bagimsiz(k):
    """Boşluk kağıt üzerinde g'dir (ölçek k'dan bağımsız; model biriminde g/k)."""
    pv = _adla(layout(list(_gorunusler()), scale=k, gap=G))
    on_lo, on_hi = _pafta_kutusu(pv["on"])
    ust_lo, ust_hi = _pafta_kutusu(pv["ust"])
    sol_lo, _ = _pafta_kutusu(pv["sol"])
    _, sag_hi = _pafta_kutusu(pv["sag"])
    assert on_lo[1] - ust_hi[1] == pytest.approx(G, abs=1e-9)
    assert sol_lo[0] - on_hi[0] == pytest.approx(G, abs=1e-9)
    assert on_lo[0] - sag_hi[0] == pytest.approx(G, abs=1e-9)


@pytest.mark.parametrize("k", [1.0, 0.5, 2.0])
def test_on_ve_ust_ayni_x(k):
    """Ön ve üst aynı u = x'i aynı pafta X'inde gösterir: k·x + öteleme_on = k·x + öteleme_ust."""
    sheet = layout(list(_gorunusler()[:2]), scale=k, gap=G)
    pv = _adla(sheet)
    for x in (0.0, HX, A):
        x_on = pv["on"].scale * x + pv["on"].offset[0]
        x_ust = pv["ust"].scale * x + pv["ust"].offset[0]
        assert x_on == pytest.approx(x_ust, abs=1e-9)


@pytest.mark.parametrize("k", [0.5, 2.0])
def test_olcek_boylari_k_kati(k):
    views = list(_gorunusler())
    sheet = layout(views, scale=k, gap=G)
    for pv in sheet.views:
        assert pv.scale == pytest.approx(k, rel=1e-12)
        lo, hi = pv.view.bbox()
        plo, phi = _pafta_kutusu(pv)
        assert phi - plo == pytest.approx(k * (np.asarray(hi, float) - np.asarray(lo, float)), abs=1e-9)


def test_on_yoksa_hata():
    with pytest.raises(GeometryError):
        layout(list(_gorunusler()[1:]))


@pytest.mark.parametrize("scale", [0.0, -1.0])
def test_gecersiz_olcek_hata(scale):
    with pytest.raises(GeometryError):
        layout(list(_gorunusler()), scale=scale)


def test_negatif_aralik_hata():
    with pytest.raises(GeometryError):
        layout(list(_gorunusler()), gap=-1.0)


# --- K13: uçtan uca ---------------------------------------------------------------------------------


@cache
def _cizim():
    return make_drawing(_parca(), section=("on", HY))


def test_kesit_on_gorunusun_yerine_gecer():
    pv = _adla(_cizim())
    assert "A-A" in pv
    assert pv["A-A"].view.direction == "on"
    assert "on" not in pv
    assert {"ust", "sol"} <= set(pv)


def test_kesit_cizgisi_ust_gorunuste():
    """`on` kesiti için kesit çizgisi üst görünüşte v = y₀ doğrusu (pafta koordinatı, EKSEN katmanı)."""
    sheet = _cizim()
    ust = _adla(sheet)["ust"]
    y = ust.scale * HY + ust.offset[1]
    cizgi = [
        e
        for e in sheet.extras
        if isinstance(e, Line2D)
        and e.layer == "EKSEN"
        and abs(e.p0[1] - y) < 1e-9
        and abs(e.p1[1] - y) < 1e-9
        and abs(e.p1[0] - e.p0[0]) > 1e-6
    ]
    assert cizgi


def test_temel_olcu_metinleri_paftada():
    metinler = {e.text for e in _cizim().entities() if isinstance(e, Text2D)}
    assert {"100", "30", "60", "Ø10", "20", "25"} <= metinler


def test_dxf_ve_svg_uctan_uca(tmp_path):
    sheet = _cizim()
    ents = sheet.entities()
    dxf = tmp_path / "cizim.dxf"
    svg = tmp_path / "cizim.svg"
    write_dxf(sheet, dxf)
    write_svg(sheet, svg)
    assert dxf.stat().st_size > 0
    ET.parse(svg)
    geri = read_dxf(dxf)
    for layer in ("GORUNUR", "GIZLI"):
        assert toplam_boy(ents, layer) > 0
        assert toplam_boy(geri, layer) == pytest.approx(toplam_boy(ents, layer), rel=1e-9)
    assert any(e.layer == "TARAMA" for e in geri)
