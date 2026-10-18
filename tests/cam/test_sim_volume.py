"""SPEC 05 K7–K8 — kaldırılan hacim: dikdörtgen cep ve delme.

Testler SPEC 05 "Z-haritası", "Doğrusal hareketin süpürme zarfı" ve "Program, adımlar" bölümlerinden yazıldı;
cam.sim kodu okunmadı.

Kaynaklar:
- Düz takımla köşe yarıçapı R olan a × b cep alanı ab − (4 − π)R² (dikdörtgenin dört köşesinden
  (2R)² − πR² ... her köşede R² − πR²/4 eksik); kaldırılan hacim alan · H.
- Izgara hatası: yalnız sınırı kesen hücreler hatalı; sınır şeridi alanı ≤ P·Δ → hata ≤ P·Δ·H,
  P = 2(a + b) − (8 − 2π)R (köşe yarıçaplı dikdörtgen çevresi).
- Delik (düz kabul edilen matkap, SPEC 05 "Takım alt yüzeyi"): her delik πR²·H; çevre 2πR.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from cam.gcode import DrillOp
from cam.model import Stock
from cam.sim import simulate
from tests.cam.simref import drill, flat, rect_pocket

# ------------------------------------------------------------------ K7

STOK = Stock(0.0, 0.0, -20.0, 60.3, 40.7, 0.0)
X0, Y0, A, B = 7.3, 5.6, 31.7, 22.9
H = 5.0


@pytest.mark.parametrize("cell", [1.0, 0.5, 0.25])
def test_K7_dikdortgen_cep_hacmi(cell):
    tool = flat(D=6.0)
    R = 3.0
    yol = rect_pocket(tool, X0, Y0, A, B, -H)
    res = simulate([yol], STOK, cell=cell)
    V = (A * B - (4 - math.pi) * R**2) * H
    P = 2 * (A + B) - (8 - 2 * math.pi) * R
    assert res.removed_volume == pytest.approx(V, abs=P * cell * H)
    assert STOK.volume - res.zmap.volume() == pytest.approx(res.removed_volume, rel=1e-9)
    # derinlik: hiçbir hücre cep tabanının altına inmez, cebin içi tam −H
    assert res.zmap.z.min() == pytest.approx(-H, abs=1e-12)
    assert not any(c.kind == "hizli_carpma" for c in res.collisions)


# ------------------------------------------------------------------ K8

D_STOK = Stock(0.0, 0.0, -30.0, 40.3, 35.1, 0.0)
DELIKLER = [(10.2, 10.1), (30.3, 9.7), (20.1, 25.3)]
Z_DIP = -12.0


def _delme(kind: str, q: float | None = None) -> DrillOp:
    return DrillOp(
        "delik",
        drill(D=8.0),
        rpm=1000.0,
        start=(0.0, 0.0, 10.0),
        holes=DELIKLER,
        z=Z_DIP,
        r=2.0,
        feed=100.0,
        kind=kind,
        q=q,
    )


@pytest.mark.parametrize("cell", [0.5, 0.25])
def test_K8_g81_hacim(cell):
    res = simulate([_delme("G81")], D_STOK, cell=cell)
    R = 4.0
    Hd = -Z_DIP
    V = 3 * math.pi * R**2 * Hd
    P = 3 * 2 * math.pi * R
    assert res.removed_volume == pytest.approx(V, abs=P * cell * Hd)
    assert res.zmap.z.min() == Z_DIP
    assert res.collisions == []


def test_K8_g83_ayni_yuzey():
    """G83 gagalama açılımı (SPEC 04) aynı delikleri aynı dibe deler: son yüzey birebir aynı."""
    r81 = simulate([_delme("G81")], D_STOK, cell=0.5)
    r83 = simulate([_delme("G83", q=4.0)], D_STOK, cell=0.5)
    np.testing.assert_array_equal(r81.zmap.z, r83.zmap.z)
    assert r83.collisions == []  # gagalar arası G0 dönüşleri açılmış delikte
    assert len(r83.steps) > len(r81.steps)


def test_K8_drillop_acilimi_adimlari():
    """DrillOp önce to_toolpath() kanonik açılımına çevrilir: adım sayısı açılımın hareket sayısı."""
    op = _delme("G81")
    res = simulate([op], D_STOK, cell=1.0)
    assert len(res.steps) == len(op.to_toolpath().moves)
    assert res.start == pytest.approx(op.start)
