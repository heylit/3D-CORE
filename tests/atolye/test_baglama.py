"""SPEC 38 K7 — bağlama resmi (§5): ham malzeme EKSEN, bağlama elemanı GORUNUR + TARAMA,
iş sıfırı simgesi OLCU.

Görünüşler iş koordinatındadır (öteleme yok): "on" (u = x, v = z), "ust" (u = x, v = y). Denetimler görünüş
koordinatında, görünüşün `edges` + `hatch` varlıkları üzerinden yapılır.
Testler yalnız SPEC 38 metninden yazıldı; `atolye` uygulama kodu okunmadı.
"""

from __future__ import annotations

import math
import xml.etree.ElementTree as ET

import numpy as np
import pytest

from atolye import setup_drawing
from cam.model import CamError, CylinderStock, Setup, Stock, Wcs
from geometry.drawing.svg import write_svg
from geometry.drawing.types import Arc2D, Line2D, Polyline2D, Sheet, Text2D, View
from geometry.part import GeometryError
from tests.atolye import ek_a

TOL = 1e-9


def _view(sheet: Sheet, name: str) -> View:
    bulunan = [pv.view for pv in sheet.views if pv.view.name == name]
    assert len(bulunan) == 1, f"'{name}' görünüşü bir kez olmalı"
    return bulunan[0]


def _ents(view: View, layer: str) -> list:
    return [e for e in (*view.edges, *view.hatch) if e.layer == layer]


def _boy(ents) -> float:
    L = 0.0
    for e in ents:
        if isinstance(e, Line2D):
            L += float(np.linalg.norm(np.asarray(e.p1) - np.asarray(e.p0)))
        elif isinstance(e, Arc2D):
            L += e.r * math.radians(e.a1 - e.a0)
        elif isinstance(e, Polyline2D):
            L += float(np.linalg.norm(np.diff(np.asarray(e.P), axis=0), axis=1).sum())
    return L


def _parcalar(ents) -> list[tuple[np.ndarray, np.ndarray]]:
    """Çizgi ve çoklu çizgileri doğru parçalarına aç."""
    out = []
    for e in ents:
        if isinstance(e, Line2D):
            out.append((np.asarray(e.p0, float), np.asarray(e.p1, float)))
        elif isinstance(e, Polyline2D):
            P = np.asarray(e.P, float)
            out += [(P[i], P[i + 1]) for i in range(len(P) - 1)]
    return out


def _dikdortgen_kenarlari_var(ents, u0, v0, u1, v1):
    """Dikdörtgenin dört kenarı varlıkların üzerinde (her kenarın orta noktası bir parçanın üstünde)."""
    kenarlar = [((u0, v0), (u1, v0)), ((u1, v0), (u1, v1)), ((u1, v1), (u0, v1)), ((u0, v1), (u0, v0))]
    parcalar = _parcalar(ents)
    for a, b in kenarlar:
        m = (np.array(a, float) + np.array(b, float)) / 2
        ok = False
        for p, q in parcalar:
            d = q - p
            L = float(np.linalg.norm(d))
            if L == 0:
                continue
            t = float(np.dot(m - p, d) / L**2)
            if -1e-9 <= t <= 1 + 1e-9 and np.linalg.norm(p + t * d - m) <= 1e-6:
                ok = True
                break
        assert ok, f"dikdörtgen kenarı {a}–{b} çizilmemiş"


def _ok_var(view: View, yon: np.ndarray, A: float):
    """Orijinden `yon` doğrultusunda A boyunda OLCU gövdesi var."""
    for p, q in _parcalar(_ents(view, "OLCU")):
        for a, b in ((p, q), (q, p)):
            if np.linalg.norm(a) <= 1e-6 and np.linalg.norm(b - A * yon) <= 1e-6:
                return
    raise AssertionError(f"orijinden {yon} yönünde {A} mm ok gövdesi yok")


def _metinler(view: View, layer: str = "OLCU") -> list[str]:
    return [e.text for e in view.edges if isinstance(e, Text2D) and e.layer == layer]


def test_gorunusler_ve_ham_malzeme():
    sheet = setup_drawing(ek_a.setup())
    assert isinstance(sheet, Sheet)
    on, ust = _view(sheet, "on"), _view(sheet, "ust")
    assert on.direction == "on" and ust.direction == "ust"
    # Ham malzeme dış çizgisi EKSEN: üstte 50 × 40, önde 50 × 20
    assert _boy(_ents(ust, "EKSEN")) == pytest.approx(2 * (50 + 40), abs=1e-6)
    assert _boy(_ents(on, "EKSEN")) == pytest.approx(2 * (50 + 20), abs=1e-6)
    _dikdortgen_kenarlari_var(_ents(ust, "EKSEN"), 0, 0, 50, 40)
    _dikdortgen_kenarlari_var(_ents(on, "EKSEN"), 0, -20, 50, 0)
    # Birinci açı: üst görünüş önün altında
    konum = {pv.view.name: np.asarray(pv.offset, float) for pv in sheet.views}
    assert konum["ust"][1] < konum["on"][1]


def test_baglama_elemani_ve_tarama():
    sheet = setup_drawing(ek_a.setup())
    # Eleman Stock(−15, 0, −20, −5, 40, 10): üstte [−15, −5] × [0, 40], önde [−15, −5] × [−20, 10]
    for name, (u0, v0, u1, v1) in {"ust": (-15, 0, -5, 40), "on": (-15, -20, -5, 10)}.items():
        v = _view(sheet, name)
        gor = _ents(v, "GORUNUR")
        _dikdortgen_kenarlari_var(gor, u0, v0, u1, v1)
        assert _boy(gor) == pytest.approx(2 * ((u1 - u0) + (v1 - v0)), abs=1e-6)
        tarama = _parcalar(_ents(v, "TARAMA"))
        assert tarama, f"'{name}' görünüşünde tarama yok"
        for p, q in tarama:
            m = (p + q) / 2
            assert u0 - TOL <= m[0] <= u1 + TOL and v0 - TOL <= m[1] <= v1 + TOL


def test_is_sifiri_simgesi():
    for scale in (1.0, 2.0):
        sheet = setup_drawing(ek_a.setup(), scale=scale)
        A = 15 / scale
        for name, harfler in {"on": {"X", "Z"}, "ust": {"X", "Y"}}.items():
            v = _view(sheet, name)
            _ok_var(v, np.array([1.0, 0.0]), A)
            _ok_var(v, np.array([0.0, 1.0]), A)
            metin = _metinler(v)
            assert "G55" in metin
            assert harfler <= set(metin)


def test_olcek():
    """scale = 2: paftadaki ham malzeme çizgileri iki kat."""

    def pafta_eksen(sheet: Sheet) -> float:
        return _boy([e for e in sheet.entities() if e.layer == "EKSEN"])

    s1 = setup_drawing(ek_a.setup(), scale=1.0)
    s2 = setup_drawing(ek_a.setup(), scale=2.0)
    assert pafta_eksen(s1) == pytest.approx(2 * (50 + 40) + 2 * (50 + 20), abs=1e-6)
    assert pafta_eksen(s2) == pytest.approx(2 * pafta_eksen(s1), abs=1e-6)
    assert all(pv.scale == 2.0 for pv in s2.views)


def test_silindir_baglama_elemani():
    D = 30.0
    s = Setup(
        "ayna",
        Wcs("G54", (0, 0, 0)),
        Stock(20, -10, -10, 60, 10, 0),
        fixtures=[CylinderStock(D=D, zmin=-30, zmax=-5)],
    )
    sheet = setup_drawing(s)
    ust, on = _view(sheet, "ust"), _view(sheet, "on")
    cember = [
        e
        for e in _ents(ust, "GORUNUR")
        if isinstance(e, Arc2D)
        and np.linalg.norm(np.asarray(e.c, float)) <= 1e-9
        and e.r == pytest.approx(D / 2, abs=1e-9)
        and e.a1 - e.a0 == pytest.approx(360.0, abs=1e-9)
    ]
    assert len(cember) == 1
    # Tarama çemberin içinde (1e-3 mm kiriş toleransı)
    tarama = _parcalar(_ents(ust, "TARAMA"))
    assert tarama
    for p, q in tarama:
        for x in (p, q):
            assert np.linalg.norm(x) <= D / 2 + 1e-3 + 1e-9
    # Önde dikdörtgen [−D/2, D/2] × [zmin, zmax]
    _dikdortgen_kenarlari_var(_ents(on, "GORUNUR"), -D / 2, -30, D / 2, -5)


def test_write_svg(tmp_path):
    yol = tmp_path / "baglama.svg"
    write_svg(setup_drawing(ek_a.setup()), yol)
    kok = ET.parse(yol).getroot()
    assert kok.tag.endswith("svg")


@pytest.mark.parametrize(
    "kw", [{"scale": 0}, {"scale": -1}, {"scale": math.inf}, {"gap": 0}, {"gap": math.nan}]
)
def test_gecersiz_olcek_bosluk(kw):
    """§Arayüz: scale, gap pozitif sonlu değil → CamError (SPEC 16'dan gelen GeometryError da kabul)."""
    with pytest.raises((CamError, GeometryError)):
        setup_drawing(ek_a.setup(), **kw)


@pytest.mark.occt
def test_parca_ile():
    """part verilince SPEC 16 project(part, "ust") kenarları resimde de var."""
    from build123d import Box, Pos

    from geometry.drawing.views import project
    from geometry.part import Part

    part = Part(Pos(25, 20, -10) * Box(50, 40, 20), name="blok")
    sheet = setup_drawing(ek_a.setup(), part=part)
    beklenen = _boy([e for e in project(part, "ust").edges if e.layer == "GORUNUR"])
    ust = _view(sheet, "ust")
    # GORUNUR = parça kenarları + bağlama elemanı dikdörtgeni (2·(10 + 40))
    assert _boy(_ents(ust, "GORUNUR")) == pytest.approx(beklenen + 100, abs=1e-6)
