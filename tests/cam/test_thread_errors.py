"""SPEC 52 K9 — hatalar: diş olmayan yol, P ≤ 0, starts < 1, haritayı aşan yol,
ThreadMillForm geçersiz değerleri,
max_cells aşımı → CamError. Ölçümde hatalı taraf / bölge → CamError (thread_measure arayüz notu).

Testler SPEC 52 "Arayüz" ve K9'dan yazıldı; cam.sim kodu okunmadı.
"""

from __future__ import annotations

import functools

import pytest

from cam.lathe_ops import iso_thread_depth
from cam.model import (
    CamError,
    CylinderStock,
    FeedMode,
    Frame,
    Move,
    MoveType,
    Plane,
    Tool,
    ToolKind,
    Toolpath,
)
from cam.sim import PolarMap, simulate_thread, thread_measure
from cam.thread_mill import ThreadMillForm, thread_mill
from tests.cam.lsimref import G0, G1, lpath, turn_tool
from tests.cam.threadref import H_iso, dis_kalemi, mil_rmap, torna_disi

BIRIM = Frame((0.0, 0.0, 0.0), ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)))
P = 2.5


@functools.cache
def _bas() -> PolarMap:
    return PolarMap.from_radial(mil_rmap(20.0, 7.0, 0.1), dtheta_deg=2.0)


def _dis(**kw):
    return torna_disi(20.0, P, dis_kalemi(H_iso(P) / 6), iso_thread_depth(P), **kw)


def test_K9_dis_olmayan_torna_yolu():
    """Boyuna tornalama (feed 0.2 mm/dev, TURN kalemi) diş pasosu değil."""
    yol = lpath(turn_tool(0.8), (12.0, 2.0), [G0(9.0, 2.0), G1(9.0, -10.0, F=0.2), G0(12.0, -10.0)])
    with pytest.raises(CamError):
        simulate_thread([yol], _bas())


def test_K9_freze_yolu():
    t = Tool(1, "duz", ToolKind.FLAT, 6.0, 20.0)
    yol = Toolpath(
        "freze",
        t,
        (0.0, 0.0, 2.0),
        [Move(MoveType.LINEAR, (5.0, 0.0, -5.0), 300.0)],
        3000.0,
        Plane.XY,
        FeedMode.PER_MIN,
    )
    with pytest.raises(CamError):
        simulate_thread([yol], _bas(), frame=BIRIM)


def test_K9_bos_ops():
    with pytest.raises(CamError):
        simulate_thread([], _bas())


@pytest.mark.parametrize("starts", [0, -1])
def test_K9_starts(starts):
    with pytest.raises(CamError):
        simulate_thread([_dis()], _bas(), starts=starts)


def test_K9_haritayi_asan_yol():
    """Harita z ∈ [−30, 5]; paso z = −35'e iner (kesen profil haritanın dışına çıkar)."""
    with pytest.raises(CamError):
        simulate_thread([_dis(z_en=-35.0)], _bas())


@pytest.mark.parametrize("Pv", [0.0, -1.5])
def test_K9_thread_mill_hatve(Pv):
    with pytest.raises(CamError):
        thread_mill(BIRIM, 16.0, Pv, 10.0, ThreadMillForm(8.0))


@pytest.mark.parametrize(
    "kw",
    [
        {"D": 0.0},
        {"D": -8.0},
        {"D": 8.0, "eps_deg": 0.0},
        {"D": 8.0, "eps_deg": 180.0},
        {"D": 8.0, "eps_deg": -60.0},
        {"D": 8.0, "nose_r": -0.1},
    ],
)
def test_K9_thread_mill_form(kw):
    with pytest.raises(CamError):
        ThreadMillForm(**kw)


def test_K9_thread_mill_form_gecerli():
    ThreadMillForm(8.0, 60.0, 0.0)
    ThreadMillForm(8.0, 179.0, 0.2)


def test_K9_max_cells():
    """360 × 500 = 180 000 hücre > 1000."""
    with pytest.raises(CamError):
        PolarMap.from_stock(
            CylinderStock(D=20.0, zmin=-25.0, zmax=0.0), dtheta_deg=1.0, dz=0.05, max_cells=1000
        )


@pytest.mark.parametrize("side, z_range", [("orta", (-19.0, -5.0)), ("dis", (-5.0, -19.0))])
def test_K9_olcum_girdisi(side, z_range):
    with pytest.raises(CamError):
        thread_measure(_bas(), side, z_range)
