"""SPEC 38 K6 — ISO 2768-1 genel doğrusal tolerans ve ilk parça ölçüm kalemleri (§6).

Kaynak: ISO 2768-1:1989, Tablo 1. Aralık sınırı alt aralığa aittir (3 → "0,5–3").
Testler yalnız SPEC 38 metninden yazıldı; `atolye` uygulama kodu okunmadı.
"""

from __future__ import annotations

import numpy as np
import pytest

from atolye import inspection_items, tolerance_2768
from cam.gcode import DrillOp
from cam.model import CamError, Move, MoveType, Toolpath
from geometry.drawing.types import Dimension
from tests.atolye import ek_a

TOL = 1e-9


@pytest.mark.parametrize(
    "nominal,cls,t",
    [
        (3, "m", 0.1),
        (6, "m", 0.1),
        (6.01, "m", 0.2),
        (30, "m", 0.2),
        (120, "m", 0.3),
        (4000, "m", 2),
        (6, "f", 0.05),
        (6.01, "f", 0.1),
        (0.5, "c", 0.2),
        # Tablonun diğer hücreleri
        (0.5, "m", 0.1),
        (3.0001, "m", 0.1),
        (30.01, "m", 0.3),
        (400, "m", 0.5),
        (1000, "m", 0.8),
        (2000, "m", 1.2),
        (2000, "f", 0.5),
        (3, "c", 0.2),
        (3.0001, "c", 0.3),
        (4000, "c", 4),
        (3.0001, "v", 0.5),
        (4000, "v", 8),
    ],
)
def test_tolerans(nominal, cls, t):
    assert tolerance_2768(nominal, cls) == pytest.approx(t, abs=1e-12)


def test_tolerans_varsayilan_m():
    assert tolerance_2768(50) == pytest.approx(0.3, abs=1e-12)


@pytest.mark.parametrize(
    "nominal,cls",
    [
        (0.4, "m"),
        (4001, "m"),
        (2, "v"),  # v sınıfında 0,5–3 tanımsız
        (2500, "f"),  # f sınıfında >2000–4000 tanımsız
        (10, "x"),
        (0, "m"),
        (-5, "m"),
    ],
)
def test_tolerans_tanimsiz(nominal, cls):
    with pytest.raises(CamError):
        tolerance_2768(nominal, cls)


def _dim(value: float, text: str) -> Dimension:
    return Dimension("yatay", np.array([0.0, 0.0]), np.array([value, 0.0]), 10.0, value, text)


def _delik_drillop() -> DrillOp:
    """Ek A'nın T2 deliği DrillOp olarak (derinliği ölçüm listesine girmez)."""
    return DrillOp("delik", ek_a.T2(), rpm=3000, start=(20, 20, 15), holes=[(20, 20)], z=-5, r=2, feed=150)


def test_olcum_kalemleri():
    dims = [_dim(50, "50"), _dim(40, "40")]
    items = inspection_items(dims, [ek_a.setup()], [[ek_a.tp1(), _delik_drillop()]])
    assert [i.no for i in items] == [1, 2, 3]
    assert [i.text for i in items] == ["50", "40", "on-yuz: derinlik 1"]
    assert [i.nominal for i in items] == pytest.approx([50, 40, 1], abs=TOL)
    assert [i.tol for i in items] == pytest.approx([0.3, 0.3, 0.1], abs=1e-12)
    for i in items:
        assert i.lower == pytest.approx(i.nominal - i.tol, abs=TOL)
        assert i.upper == pytest.approx(i.nominal + i.tol, abs=TOL)

    # f sınıfı
    items = inspection_items(dims, [ek_a.setup()], [[ek_a.tp1(), _delik_drillop()]], cls="f")
    assert [i.tol for i in items] == pytest.approx([0.15, 0.15, 0.05], abs=1e-12)


def test_derinlikler_toolpath_hepsi_artan_tekil():
    """Her Toolpath op'unun en alçak kesme Z'si: Ek A'da cep 1, delik (Toolpath) 5; eşit derinlik tek."""
    cep2 = Toolpath(
        "cep2",
        ek_a.T1(),
        start=(30, 30, 15),
        moves=[Move(MoveType.LINEAR, (30, 30, -1 + 1e-7), 100)],
        rpm=10000,
    )
    # Sıra bilerek: derin op önce; kalemler artan derinlikle
    items = inspection_items([], [ek_a.setup()], [[ek_a.tp2(), ek_a.tp1(), cep2]])
    assert [i.text for i in items] == ["on-yuz: derinlik 1", "on-yuz: derinlik 5"]
    assert [i.nominal for i in items] == pytest.approx([1, 5], abs=1e-6)
    assert [i.no for i in items] == [1, 2]


def test_derinlik_hizli_hareket_sayilmaz():
    """Yalnız kesme hareketleri (G1/G2/G3) derinlik verir; G0 alçalması sayılmaz; derinlik ≤ 0 alınmaz."""
    tp = Toolpath(
        "hava",
        ek_a.T1(),
        start=(25, 20, 15),
        moves=[
            Move(MoveType.RAPID, (25, 20, -3)),
            Move(MoveType.LINEAR, (25, 20, 1), 100),
            Move(MoveType.LINEAR, (30, 20, 1), 100),
        ],
        rpm=10000,
    )
    assert inspection_items([], [ek_a.setup()], [[tp]]) == []


def test_bos():
    assert inspection_items([], [ek_a.setup()], [[_delik_drillop()]]) == []


def test_tanimsiz_olcu_hata():
    with pytest.raises(CamError):
        inspection_items([_dim(0.3, "0,3")], [ek_a.setup()], [[ek_a.tp1()]])
    with pytest.raises(CamError):
        inspection_items([], [ek_a.setup()], [[ek_a.tp1()]], cls="x")
