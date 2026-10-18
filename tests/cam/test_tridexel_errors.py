"""SPEC 43 K11 — simulate5 hata listesi → CamError (sessiz hata yok); `initial` ile bölünmüş program.

Testler SPEC 43 "Arayüz" bölümündeki hata listesinden yazıldı; cam.sim.simulate5 kodu okunmadı.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from cam.model import (
    CamError,
    CylinderStock,
    FeedMode,
    LatheTool,
    LatheToolKind,
    Move,
    MoveType,
    Plane,
    Stock,
    Toolpath,
)
from cam.sim import TriDexel, simulate5
from tests.cam import tridexref as tr
from tests.cam.simref import G1, flat, path

STOK = Stock(0.0, 0.0, -10.0, 20.0, 10.0, 0.0)


def _yol() -> Toolpath:
    return path(flat(), (-5.0, 5.0, 5.0), [G1(-5.0, 5.0, -2.0), G1(25.0, 5.0, -2.0)])


def test_bos_program():
    with pytest.raises(CamError):
        simulate5([], STOK)


def test_silindir_stok():
    with pytest.raises(CamError):
        simulate5([_yol()], CylinderStock(D=20.0, zmin=-10.0, zmax=0.0))


def test_torna_takimi():
    t = LatheTool(1, "torna", LatheToolKind.TURN, nose_r=0.4, tip=3, kappa_r=95.0, eps_r=80.0)
    yol = Toolpath(
        "torna",
        t,
        (20.0, 0.0, 5.0),
        [Move(MoveType.LINEAR, (20.0, 0.0, -10.0), 0.2)],
        1000.0,
        plane=Plane.ZX,
        feed_mode=FeedMode.PER_REV,
    )
    with pytest.raises(CamError):
        simulate5([yol], STOK)


def test_g95():
    yol = Toolpath(
        "g95", flat(), (-5.0, 5.0, 5.0), [G1(-5.0, 5.0, -2.0, F=0.1)], 1000.0, feed_mode=FeedMode.PER_REV
    )
    with pytest.raises(CamError):
        simulate5([yol], STOK)


def test_gecersiz_toolpath():
    yol = _yol()
    yol.rpm = 0.0
    with pytest.raises(CamError):
        simulate5([yol], STOK)
    yol2 = _yol()
    yol2.moves.append(Move(MoveType.LINEAR, (25.0, 9.0, -2.0)))  # ilerlemesiz G1
    with pytest.raises(CamError):
        simulate5([yol2], STOK)


def test_birim_olmayan_eksen():
    yol = _yol()
    yol.moves[1].axis = (0.0, 0.6, 0.6)  # oluşturulduktan sonra bozulmuş
    with pytest.raises(CamError):
        simulate5([yol], STOK)


def test_degisen_eksenli_yay():
    """Yayda eksen +z dışı (eş zamanlı 5 eksen yay yok)."""
    yol = _yol()
    yol.moves.append(Move(MoveType.ARC_CCW, (25.0, 5.0, -2.0), 300.0, center=(22.0, 5.0)))
    yol.moves[-1].axis = tr.axis_xz(10.0)
    with pytest.raises(CamError):
        simulate5([yol], STOK)


@pytest.mark.parametrize("sigma", [0.0, -0.1, math.nan])
def test_sigma(sigma):
    with pytest.raises(CamError):
        simulate5([_yol()], STOK, sigma=sigma)


@pytest.mark.parametrize("ad", ["tol", "arc_tol", "gouge_tol"])
@pytest.mark.parametrize("deger", [0.0, -1e-3])
def test_toleranslar(ad, deger):
    with pytest.raises(CamError):
        simulate5([_yol()], STOK, **{ad: deger})


@pytest.mark.parametrize("cell", [0.0, -1.0, math.nan, math.inf])
def test_hucre(cell):
    with pytest.raises(CamError):
        simulate5([_yol()], STOK, cell=cell)


def test_max_rays():
    # hücre 1: 20·10 + 10·10 + 20·10 = 500 ışın
    with pytest.raises(CamError):
        simulate5([_yol()], STOK, cell=1.0, max_rays=499)


def test_initial_izgara_uyusmazligi():
    with pytest.raises(CamError):
        simulate5([_yol()], STOK, cell=1.0, initial=TriDexel.from_stock(STOK, 0.5))
    with pytest.raises(CamError):
        simulate5(
            [_yol()],
            STOK,
            cell=1.0,
            initial=TriDexel.from_stock(Stock(1.0, 0.0, -10.0, 21.0, 10.0, 0.0), 1.0),
        )


def test_initial_ile_bolunmus_program():
    """Program iki parçada (ikincisi birincinin tri-dexel'inden) → tek seferdekiyle aynı aralıklar.

    initial değişmez."""
    tool = flat(D=6.0, Lf=30.0)
    a = path(tool, (-5.0, 3.0, 3.0), [G1(-5.0, 3.0, -2.0), G1(25.0, 4.0, -3.0), G1(12.0, 8.0, -1.0)], "a")
    b = path(tool, (12.0, 8.0, -1.0), [G1(3.0, 2.0, -4.0), G1(18.0, 6.0, -2.5), G1(18.0, 6.0, 3.0)], "b")
    tek = simulate5([a, b], STOK, cell=0.5)
    r1 = simulate5([a], STOK, cell=0.5)
    once = r1.tridexel.volumes()
    r2 = simulate5([b], STOK, cell=0.5, initial=r1.tridexel)
    assert r1.tridexel.volumes() == once
    t1, t2 = tek.tridexel, r2.tridexel
    for aile, n1, n2 in (("x", t1.ny, t1.nz), ("y", t1.nx, t1.nz), ("z", t1.nx, t1.ny)):
        for i in range(n1):
            for j in range(n2):
                np.testing.assert_allclose(
                    np.array(t2.intervals(aile, i, j), dtype=float).reshape(-1, 2),
                    np.array(t1.intervals(aile, i, j), dtype=float).reshape(-1, 2),
                    rtol=0,
                    atol=1e-12,
                )
