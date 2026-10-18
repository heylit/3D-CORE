"""SPEC 05 K17 — hatalı girdiler CamError (sessiz hata yok).

Testler SPEC 05 "Arayüz" bölümündeki hata listesinden yazıldı; cam.sim kodu okunmadı.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from cam.gcode import DrillOp
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
from cam.sim import Machine, ZMap, simulate
from tests.cam.simref import G1, drill, flat, path

STOK = Stock(0.0, 0.0, -10.0, 20.0, 10.0, 0.0)


def _yol() -> Toolpath:
    return path(flat(), (-5.0, 5.0, 5.0), [G1(-5.0, 5.0, -2.0), G1(25.0, 5.0, -2.0)])


def test_bos_program():
    with pytest.raises(CamError):
        simulate([], STOK)


def test_silindir_stok():
    with pytest.raises(CamError):
        simulate([_yol()], CylinderStock(D=20.0, zmin=-10.0, zmax=0.0))


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
    yol.validate()  # torna yolu kendi başına geçerli
    with pytest.raises(CamError):
        simulate([yol], STOK)


def test_g18():
    yol = Toolpath("g18", flat(), (-5.0, 5.0, 5.0), [G1(-5.0, 5.0, -2.0)], 1000.0, plane=Plane.ZX)
    with pytest.raises(CamError):
        simulate([yol], STOK)


def test_g95():
    yol = Toolpath(
        "g95", flat(), (-5.0, 5.0, 5.0), [G1(-5.0, 5.0, -2.0, F=0.1)], 1000.0, feed_mode=FeedMode.PER_REV
    )
    with pytest.raises(CamError):
        simulate([yol], STOK)


def test_gecersiz_toolpath():
    yol = _yol()
    yol.rpm = 0.0
    with pytest.raises(CamError):
        simulate([yol], STOK)
    yol2 = _yol()
    yol2.moves.append(Move(MoveType.LINEAR, (25.0, 9.0, -2.0)))  # ilerlemesiz G1
    with pytest.raises(CamError):
        simulate([yol2], STOK)
    yol3 = _yol()
    yol3.moves.append(Move(MoveType.ARC_CW, (25.0, 9.0, -2.0), 300.0, center=(0.0, 0.0)))  # yarıçap tutmuyor
    with pytest.raises(CamError):
        simulate([yol3], STOK)


def test_gecersiz_drillop():
    op = DrillOp("d", drill(), rpm=1000.0, start=(0.0, 0.0, 10.0), holes=[], z=-5.0, r=2.0, feed=100.0)
    with pytest.raises(CamError):
        simulate([op], STOK)


def test_part_z_sekli():
    g = ZMap.from_stock(STOK, 1.0)
    with pytest.raises(CamError):
        simulate([_yol()], STOK, cell=1.0, part_z=np.zeros((g.ny + 1, g.nx)))
    with pytest.raises(CamError):
        simulate([_yol()], STOK, cell=1.0, part_z=np.zeros((g.nx, g.ny)))  # devrik
    simulate([_yol()], STOK, cell=1.0, part_z=np.full((g.ny, g.nx), -5.0))  # doğru şekil kabul


@pytest.mark.parametrize("ad", ["tol", "arc_tol", "gouge_tol"])
@pytest.mark.parametrize("deger", [0.0, -1e-3])
def test_toleranslar_pozitif(ad, deger):
    with pytest.raises(CamError):
        simulate([_yol()], STOK, **{ad: deger})


@pytest.mark.parametrize("cell", [0.0, -1.0, math.nan, math.inf])
def test_hucre(cell):
    with pytest.raises(CamError):
        simulate([_yol()], STOK, cell=cell)


def test_max_cells():
    with pytest.raises(CamError):
        simulate([_yol()], STOK, cell=1.0, max_cells=199)  # 20 · 10 = 200 hücre


@pytest.mark.parametrize(
    "kw",
    [
        {"rapid": (0.0, 5000.0, 3000.0)},
        {"rapid": (5000.0, -1.0, 3000.0)},
        {"rapid": (5000.0, 5000.0, math.nan)},
        {"accel": 0.0},
        {"accel": -100.0},
        {"accel": math.nan},
        {"tool_change": -1.0},
        {"tool_change": math.nan},
    ],
)
def test_gecersiz_makine(kw):
    with pytest.raises(CamError):
        Machine(**kw)


def test_gecerli_makine_sinirlari():
    Machine(tool_change=0.0)
    Machine(accel=None)
    Machine(rapid=(1.0, 1.0, 1.0), accel=1e-3, tool_change=12.0)


def test_zmap_at_araligi():
    res = simulate([_yol()], STOK, cell=1.0)
    n = len(res.steps)
    res.zmap_at(0)
    res.zmap_at(n)
    for k in (-1, n + 1):
        with pytest.raises(CamError):
            res.zmap_at(k)
