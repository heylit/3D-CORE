"""SPEC 16 — K12: SVG yazıcı (geometry/drawing/svg.py). OCCT gerektirmez; Sheet elle kurulur.

Teori: viewBox = pafta sınır kutusu + kenar payı; y aşağı baktığı için y_svg = y_maks − y (pafta y_maks →
SVG 0); her katman bir <g id="KATMAN">; gizli çizgi stroke-dasharray, eksen noktalı-kesikli; kalınlıklar
ISO 128-20 tablosundan. Uygulama gövdeleri okunmadı.

Elle kurulan pafta: görünüş [0,100]×[0,50], ölçek 0.5, öteleme (10, 20) → pafta [10,60]×[20,45].
Tüm diğer varlıklar bu kutunun içinde, böylece Sheet.bbox() = [10,60]×[20,45].
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from collections import Counter

import numpy as np
import pytest

from geometry.drawing.svg import write_svg
from geometry.drawing.types import Arc2D, Line2D, PlacedView, Sheet, Text2D, View

KATMANLAR = ("GORUNUR", "GIZLI", "EKSEN", "TARAMA", "OLCU")
KALINLIK = {"GORUNUR": 0.5, "GIZLI": 0.25, "EKSEN": 0.25, "TARAMA": 0.18, "OLCU": 0.18}
CIZIM_ETIKETLERI = {"line", "polyline", "polygon", "path", "circle", "ellipse", "text", "rect"}

K, OFF = 0.5, np.array([10.0, 20.0])
XMIN, YMIN, XMAX, YMAX = 10.0, 20.0, 60.0, 45.0


def P(x, y) -> np.ndarray:
    return np.array([x, y], float)


def _pafta() -> Sheet:
    edges = (
        Line2D(P(0, 0), P(100, 0), "GORUNUR"),
        Line2D(P(100, 0), P(100, 50), "GORUNUR"),
        Line2D(P(100, 50), P(0, 50), "GORUNUR"),
        Line2D(P(0, 50), P(0, 0), "GORUNUR"),
        Line2D(P(30, 0), P(30, 50), "GIZLI"),
        Arc2D(P(60, 25), 10.0, 0.0, 360.0, "GORUNUR"),
        Arc2D(P(60, 25), 15.0, 0.0, 90.0, "GORUNUR"),
        Line2D(P(60, 12), P(60, 38), "EKSEN"),
    )
    hatch = (Line2D(P(5, 5), P(20, 20), "TARAMA"), Line2D(P(5, 15), P(20, 30), "TARAMA"))
    view = View(name="on", direction="on", edges=edges, hatch=hatch)
    extras = (Text2D(P(15.0, 30.0), "A", 2.0, 0.0, "OLCU"), Line2D(P(12, 22), P(20, 22), "OLCU"))
    return Sheet(views=(PlacedView(view, OFF.copy(), K),), extras=extras)


def _etiket(el) -> str:
    return el.tag.rsplit("}", 1)[-1]


def _yaz_oku(tmp_path, margin=None):
    path = tmp_path / "pafta.svg"
    sheet = _pafta()
    if margin is None:
        write_svg(sheet, path)
    else:
        write_svg(sheet, path, margin=margin)
    return sheet, ET.parse(path).getroot()


def _katman_gruplari(root) -> dict[str, list]:
    g = {}
    for el in root.iter():
        if _etiket(el) == "g" and el.get("id") in KATMANLAR:
            g.setdefault(el.get("id"), []).append(el)
    return g


def _cizim_elemanlari(g) -> list:
    return [el for el in g.iter() if el is not g and _etiket(el) in CIZIM_ETIKETLERI]


def _ozellik(el, g, ad: str) -> str | None:
    """Özelliği elemanda, yoksa katman grubunda ara (doğrudan öznitelik veya style içinde)."""
    for x in (el, g):
        if x.get(ad) is not None:
            return x.get(ad)
        m = re.search(rf"{ad}\s*:\s*([^;]+)", x.get("style", ""))
        if m:
            return m.group(1).strip()
    return None


def _sayilar(s: str) -> list[float]:
    return [float(t) for t in re.findall(r"[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?", s)]


def _koordinatlar(el) -> np.ndarray:
    """line / polyline / path elemanının nokta listesi (SVG koordinatı)."""
    t = _etiket(el)
    if t == "line":
        v = [float(el.get(k)) for k in ("x1", "y1", "x2", "y2")]
    elif t in ("polyline", "polygon"):
        v = _sayilar(el.get("points"))
    else:
        v = _sayilar(el.get("d"))
    return np.array(v, float).reshape(-1, 2)


def test_xml_ayrisiyor_ve_svg_kok(tmp_path):
    _, root = _yaz_oku(tmp_path)
    assert _etiket(root) == "svg"


@pytest.mark.parametrize("margin", [None, 5.0])
def test_viewbox(tmp_path, margin):
    m = 10.0 if margin is None else margin
    _, root = _yaz_oku(tmp_path, margin)
    vb = _sayilar(root.get("viewBox"))
    beklenen = [XMIN - m, -m, (XMAX - XMIN) + 2 * m, (YMAX - YMIN) + 2 * m]
    assert vb == pytest.approx(beklenen, abs=1e-9)


def test_pafta_bbox():
    lo, hi = _pafta().bbox()
    assert np.asarray(lo, float) == pytest.approx([XMIN, YMIN], abs=1e-9)
    assert np.asarray(hi, float) == pytest.approx([XMAX, YMAX], abs=1e-9)


def test_her_katman_bir_grup(tmp_path):
    sheet, root = _yaz_oku(tmp_path)
    gruplar = _katman_gruplari(root)
    kullanilan = {e.layer for e in sheet.entities()}
    for layer in kullanilan:
        assert len(gruplar.get(layer, [])) == 1, f"<g id='{layer}'> tam bir kez olmalı"


def test_eleman_sayisi_entities_ile_ayni(tmp_path):
    sheet, root = _yaz_oku(tmp_path)
    ents = sheet.entities()
    gruplar = _katman_gruplari(root)
    sayim = Counter({ad: len(_cizim_elemanlari(gs[0])) for ad, gs in gruplar.items()})
    beklenen = Counter(e.layer for e in ents)
    assert +sayim == +beklenen
    assert sum(sayim.values()) == len(ents)


def test_gizli_ve_eksen_kesikli_gorunur_surekli(tmp_path):
    _, root = _yaz_oku(tmp_path)
    gruplar = _katman_gruplari(root)
    for layer in ("GIZLI", "EKSEN"):
        g = gruplar[layer][0]
        for el in _cizim_elemanlari(g):
            dash = _ozellik(el, g, "stroke-dasharray")
            assert dash not in (None, "", "none"), f"{layer}: stroke-dasharray yok"
    # noktalı-kesikli: en az iki farklı çizgi / boşluk boyu (çizgi-boşluk-nokta-boşluk)
    g = gruplar["EKSEN"][0]
    dash = _sayilar(_ozellik(_cizim_elemanlari(g)[0], g, "stroke-dasharray"))
    assert len(dash) >= 4 and len(set(dash)) >= 2
    g = gruplar["GORUNUR"][0]
    for el in _cizim_elemanlari(g):
        assert _ozellik(el, g, "stroke-dasharray") in (None, "", "none")


def test_cizgi_kalinliklari(tmp_path):
    _, root = _yaz_oku(tmp_path)
    for layer, gs in _katman_gruplari(root).items():
        g = gs[0]
        for el in _cizim_elemanlari(g):
            if _etiket(el) == "text":
                continue
            w = _ozellik(el, g, "stroke-width")
            assert w is not None, f"{layer}: stroke-width yok"
            assert _sayilar(w)[0] == pytest.approx(KALINLIK[layer], abs=1e-12)


def test_y_ekseni_cevrilmis(tmp_path):
    """Gizli çizgi görünüşte (30, 0)–(30, 50) → pafta (25, 20)–(25, 45) → SVG (25, 25)–(25, 0)."""
    _, root = _yaz_oku(tmp_path)
    g = _katman_gruplari(root)["GIZLI"][0]
    els = _cizim_elemanlari(g)
    assert len(els) == 1
    Q = _koordinatlar(els[0])
    uclar = sorted(map(tuple, np.round(Q[[0, -1]], 9)))
    assert uclar == [(25.0, 0.0), (25.0, 25.0)]


def test_entities_pafta_koordinati():
    """Sheet.entities(): görünüş varlıkları pafta = k · p + öteleme ile taşınır, yarıçap k ile çarpılır."""
    ents = _pafta().entities()
    gizli = [e for e in ents if e.layer == "GIZLI"]
    assert len(gizli) == 1
    uclar = sorted([tuple(np.round(gizli[0].p0, 9)), tuple(np.round(gizli[0].p1, 9))])
    assert uclar == [(25.0, 20.0), (25.0, 45.0)]
    cember = [e for e in ents if isinstance(e, Arc2D) and abs(e.a1 - e.a0 - 360.0) < 1e-9]
    assert len(cember) == 1
    assert np.asarray(cember[0].c, float) == pytest.approx([40.0, 32.5], abs=1e-9)
    assert cember[0].r == pytest.approx(5.0, abs=1e-9)
    assert sum(isinstance(e, Text2D) for e in ents) == 1
    assert sum(e.layer == "TARAMA" for e in ents) == 2
