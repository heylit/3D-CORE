"""SPEC 16 — K10 DXF R12 gidiş-dönüş ve K11 ezdxf çapraz kontrolü (geometry/drawing/dxf.py).

OCCT gerektirmez: varlıklar elle kurulur. Teori: R12 ASCII ($ACADVER = AC1009), LTYPE (CONTINUOUS, HIDDEN,
CENTER) ve LAYER (beş katman) tabloları; LINE, CIRCLE, ARC, TEXT; çoklu çizgi LINE dizisi olarak yazılır;
sayılar en az 12 anlamlı basamak (geri okumada 1e-9 mm). ezdxf yalnızca çapraz kontrol için kullanılır.
Uygulama gövdeleri okunmadı.
"""

from __future__ import annotations

from collections import Counter

import numpy as np
import pytest

from geometry.drawing.dxf import read_dxf, write_dxf
from geometry.drawing.types import Arc2D, Line2D, Polyline2D, Text2D
from geometry.part import GeometryError

KATMANLAR = ("GORUNUR", "GIZLI", "EKSEN", "TARAMA", "OLCU")
CIZGI_TIPI = {
    "GORUNUR": "CONTINUOUS",
    "GIZLI": "HIDDEN",
    "EKSEN": "CENTER",
    "TARAMA": "CONTINUOUS",
    "OLCU": "CONTINUOUS",
}


def P(x, y) -> np.ndarray:
    return np.array([x, y], float)


# 12+ anlamlı basamak gerektiren koordinatlar (|x| < 1000 → 1e-9 mm çözünürlük)
VARLIKLAR = [
    Line2D(P(0.123456789012, 1.0), P(123.456789012345, 45.678901234567), "GORUNUR"),
    Line2D(P(10.0, 0.0), P(10.0, 30.0), "GIZLI"),
    Line2D(P(-2.0, 25.0), P(42.000000001, 25.0), "EKSEN"),
    Line2D(P(1.5, 1.5), P(7.5, 7.5), "TARAMA"),
    Line2D(P(0.0, -10.0), P(100.0, -10.0), "OLCU"),
    Arc2D(P(20.000000002, 25.0), 5.0, 0.0, 360.0, "GORUNUR"),
    Arc2D(P(-4.25, 3.125), 12.345678901234, 30.0, 120.5, "GIZLI"),
    Polyline2D(np.array([[0.0, 0.0], [10.0, 0.0], [10.0, 5.5], [3.333333333333, 7.0]]), "GORUNUR"),
    Text2D(P(30.0, -15.0), "12,5", 3.5, 0.0, "OLCU"),
    Text2D(P(-20.0, 40.0), "A-A", 5.0, 90.0, "EKSEN"),
]


def _beklenen_sayim() -> Counter:
    """Çoklu çizgi k nokta → k − 1 LINE; tam çember de Arc2D olarak döner."""
    n = Counter()
    for e in VARLIKLAR:
        if isinstance(e, Polyline2D):
            n[("Line2D", e.layer)] += len(e.P) - 1
        else:
            n[(type(e).__name__, e.layer)] += 1
    return n


def _sayim(ents) -> Counter:
    return Counter((type(e).__name__, e.layer) for e in ents)


def _parcalar(ents) -> list[Line2D]:
    """Line2D ve Polyline2D'leri doğru parçalarına aç."""
    out = []
    for e in ents:
        if isinstance(e, Line2D):
            out.append(e)
        elif isinstance(e, Polyline2D):
            Q = np.asarray(e.P, float)
            out += [Line2D(Q[i], Q[i + 1], e.layer) for i in range(len(Q) - 1)]
    return out


def _ayni_dogru(a: Line2D, b: Line2D, tol=1e-9) -> bool:
    if a.layer != b.layer:
        return False
    d1 = max(np.abs(a.p0 - b.p0).max(), np.abs(a.p1 - b.p1).max())
    d2 = max(np.abs(a.p0 - b.p1).max(), np.abs(a.p1 - b.p0).max())
    return min(d1, d2) < tol


def _aci_esit(a, b, tol=1e-9) -> bool:
    d = (a - b) % 360.0
    return min(d, 360.0 - d) < tol


@pytest.fixture
def dxf_dosyasi(tmp_path):
    return tmp_path / "varliklar.dxf"


def test_gidis_donus_sayim(dxf_dosyasi):
    write_dxf(VARLIKLAR, dxf_dosyasi)
    assert _sayim(read_dxf(dxf_dosyasi)) == _beklenen_sayim()


def test_gidis_donus_dogrular(dxf_dosyasi):
    write_dxf(VARLIKLAR, dxf_dosyasi)
    geri = [e for e in read_dxf(dxf_dosyasi) if isinstance(e, Line2D)]
    beklenen = _parcalar(VARLIKLAR)
    assert len(geri) == len(beklenen)
    kalan = list(geri)
    for b in beklenen:
        eslesen = [g for g in kalan if _ayni_dogru(g, b)]
        assert eslesen, f"DXF'den dönmeyen doğru: {b}"
        kalan.remove(eslesen[0])


def test_gidis_donus_yaylar(dxf_dosyasi):
    write_dxf(VARLIKLAR, dxf_dosyasi)
    geri = [e for e in read_dxf(dxf_dosyasi) if isinstance(e, Arc2D)]
    beklenen = [e for e in VARLIKLAR if isinstance(e, Arc2D)]
    assert len(geri) == len(beklenen)
    for b in beklenen:
        eslesen = [
            g
            for g in geri
            if g.layer == b.layer
            and np.abs(np.asarray(g.c) - b.c).max() < 1e-9
            and abs(g.r - b.r) < 1e-9
            and abs((g.a1 - g.a0) - (b.a1 - b.a0)) < 1e-9
            and (abs((b.a1 - b.a0) - 360.0) < 1e-9 or (_aci_esit(g.a0, b.a0) and _aci_esit(g.a1, b.a1)))
        ]
        assert eslesen, f"DXF'den dönmeyen yay: {b}"


def test_gidis_donus_metinler(dxf_dosyasi):
    write_dxf(VARLIKLAR, dxf_dosyasi)
    geri = [e for e in read_dxf(dxf_dosyasi) if isinstance(e, Text2D)]
    beklenen = [e for e in VARLIKLAR if isinstance(e, Text2D)]
    assert len(geri) == len(beklenen)
    for b in beklenen:
        eslesen = [
            g
            for g in geri
            if g.text == b.text
            and g.layer == b.layer
            and np.abs(np.asarray(g.p) - b.p).max() < 1e-9
            and abs(g.h - b.h) < 1e-9
            and _aci_esit(g.angle, b.angle)
        ]
        assert eslesen, f"DXF'den dönmeyen metin: {b}"


def test_baslik_ve_tablolar(dxf_dosyasi):
    write_dxf(VARLIKLAR, dxf_dosyasi)
    satirlar = [s.strip() for s in dxf_dosyasi.read_text(encoding="ascii", errors="replace").splitlines()]
    for ad in ("SECTION", "HEADER", "$ACADVER", "AC1009", "TABLES", "LTYPE", "LAYER", "ENTITIES", "EOF"):
        assert ad in satirlar, f"DXF'de '{ad}' yok"
    for ad in ("CONTINUOUS", "HIDDEN", "CENTER", *KATMANLAR):
        assert ad in satirlar, f"DXF tablolarında '{ad}' yok"
    assert satirlar.index("HEADER") < satirlar.index("TABLES") < satirlar.index("ENTITIES")


def test_eksik_dosya_hata(tmp_path):
    with pytest.raises(GeometryError):
        read_dxf(tmp_path / "yok.dxf")


def test_bozuk_grup_kodu_hata(dxf_dosyasi):
    write_dxf(VARLIKLAR, dxf_dosyasi)
    satirlar = dxf_dosyasi.read_text(encoding="ascii", errors="replace").splitlines()
    i = [s.strip() for s in satirlar].index("ENTITIES")
    satirlar[i + 1] = "abc"  # ilk varlığın grup kodu (" 0") sayı değil
    dxf_dosyasi.write_text("\n".join(satirlar) + "\n", encoding="ascii")
    with pytest.raises(GeometryError):
        read_dxf(dxf_dosyasi)


def test_anlamsiz_dosya_hata(dxf_dosyasi):
    dxf_dosyasi.write_text("bu bir dxf degil\n", encoding="ascii")
    with pytest.raises(GeometryError):
        read_dxf(dxf_dosyasi)


def test_desteklenmeyen_surum_hata(dxf_dosyasi):
    write_dxf(VARLIKLAR, dxf_dosyasi)
    metin = dxf_dosyasi.read_text(encoding="ascii", errors="replace")
    assert "AC1009" in metin
    dxf_dosyasi.write_text(metin.replace("AC1009", "AC1015"), encoding="ascii")
    with pytest.raises(GeometryError):
        read_dxf(dxf_dosyasi)


# --- K11: ezdxf çapraz kontrolü --------------------------------------------------------------------


def test_ezdxf_capraz_kontrol(dxf_dosyasi):
    ezdxf = pytest.importorskip("ezdxf")
    write_dxf(VARLIKLAR, dxf_dosyasi)
    doc = ezdxf.readfile(str(dxf_dosyasi))
    assert doc.dxfversion == "AC1009"
    auditor = doc.audit()
    assert not auditor.has_errors, [str(e) for e in auditor.errors]

    bizim = read_dxf(dxf_dosyasi)
    msp = doc.modelspace()
    yaylar = [e for e in bizim if isinstance(e, Arc2D)]
    tam = [e for e in yaylar if abs((e.a1 - e.a0) - 360.0) < 1e-9]
    kismi = [e for e in yaylar if abs((e.a1 - e.a0) - 360.0) >= 1e-9]
    assert len(msp.query("LINE")) == len([e for e in bizim if isinstance(e, Line2D)])
    assert len(msp.query("CIRCLE")) == len(tam)
    assert len(msp.query("ARC")) == len(kismi)
    assert len(msp.query("TEXT")) == len([e for e in bizim if isinstance(e, Text2D)])
    assert len(msp) == len(bizim)
    assert Counter(e.dxf.layer for e in msp) == Counter(e.layer for e in bizim)

    for ad in KATMANLAR:
        assert doc.layers.has_entry(ad)
        assert doc.layers.get(ad).dxf.linetype.upper() == CIZGI_TIPI[ad]
    for lt in ("CONTINUOUS", "HIDDEN", "CENTER"):
        assert lt in doc.linetypes
