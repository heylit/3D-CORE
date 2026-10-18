"""SPEC 32 K15 — hatalı girdiler CamError verir (sessiz hata yok, nan / inf reddedilir)."""

from __future__ import annotations

import math

import pytest

from cam.ilerleme_opt import optimize_feed, split_moves
from cam.kuvvet import (
    KienzleMaterial,
    SpindleLimits,
    cutting_power,
    engagement_angle,
    kienzle_force,
    max_chip_thickness,
    mean_chip_thickness,
    milling_loads,
    specific_force,
    spindle_torque,
    turning_force,
)
from cam.model import CamError, Move, MoveType, Plane, Toolpath
from cam.sim import simulate
from tests.cam.kuvvet_ref import CELL, STOCK, kalem, kanal_programi, malzeme, parmak

NAN = math.nan
INF = math.inf


# ------------------------------------------------------------------ temel işlevler


@pytest.mark.parametrize("h", [0.0, -0.1, NAN, INF])
def test_h_gecersiz(h):
    mat = malzeme()
    with pytest.raises(CamError):
        specific_force(mat, h)
    with pytest.raises(CamError):
        kienzle_force(mat, 2.0, h)


@pytest.mark.parametrize("K", [0.0, -1.0, NAN])
def test_K_gecersiz(K):
    mat = malzeme()
    with pytest.raises(CamError):
        specific_force(mat, 0.2, K=K)
    with pytest.raises(CamError):
        kienzle_force(mat, 2.0, 0.2, K=K)


@pytest.mark.parametrize("b", [0.0, -2.0, NAN])
def test_b_gecersiz(b):
    mat = malzeme()
    with pytest.raises(CamError):
        kienzle_force(mat, b, 0.2)


@pytest.mark.parametrize("kr", [0.0, -10.0, 90.0001, 120.0, NAN])
def test_kappa_r_gecersiz(kr):
    mat = malzeme()
    with pytest.raises(CamError):
        turning_force(mat, 2.0, 0.2, kappa_r=kr)


@pytest.mark.parametrize("ap,f", [(0.0, 0.2), (2.0, 0.0), (-1.0, 0.2), (NAN, 0.2), (2.0, NAN)])
def test_torna_ap_f_gecersiz(ap, f):
    mat = malzeme()
    with pytest.raises(CamError):
        turning_force(mat, ap, f)


@pytest.mark.parametrize("ae", [0.0, -1.0, 10.0001, 20.0, NAN])
def test_ae_gecersiz(ae):
    for fn in (lambda: engagement_angle(ae, 10.0), lambda: mean_chip_thickness(0.1, ae, 10.0),
               lambda: max_chip_thickness(0.1, ae, 10.0)):  # fmt: skip
        with pytest.raises(CamError):
            fn()


@pytest.mark.parametrize("n", [0.0, -100.0, NAN])
def test_n_gecersiz(n):
    with pytest.raises(CamError):
        spindle_torque(1.0, n)


def test_guc_nan():
    with pytest.raises(CamError):
        cutting_power(NAN, 3000.0)
    with pytest.raises(CamError):
        cutting_power(450.0, NAN)
    with pytest.raises(CamError):
        spindle_torque(NAN, 3000.0)


@pytest.mark.parametrize(
    "kc11,mc",
    [(0.0, 0.2), (-1.0, 0.2), (1500.0, 1.0), (1500.0, 1.2), (1500.0, -0.01), (NAN, 0.2), (1500.0, NAN)],
)
def test_malzeme_gecersiz(kc11, mc):
    with pytest.raises(CamError):
        KienzleMaterial("x", kc11, mc)


@pytest.mark.parametrize(
    "kw",
    [
        {"P_max": 0.0},
        {"P_max": -1.0},
        {"M_max": 0.0},
        {"P_max": NAN},
        {"M_max": INF},
        {"eta": 0.0},
        {"eta": 1.01},
        {"eta": NAN},
    ],
)
def test_sinir_gecersiz(kw):
    with pytest.raises(CamError):
        SpindleLimits(**kw)


# ------------------------------------------------------------------ simülasyondan yük


def test_dis_sayisi_yok():
    mat = malzeme()
    tp, _ = kanal_programi(tool=parmak(flutes=None))
    res = simulate([tp], STOCK, cell=CELL)
    with pytest.raises(CamError):
        milling_loads([tp], res, mat)


def test_dexel_sonucu():
    mat = malzeme()
    tp, _ = kanal_programi()
    res = simulate([tp], STOCK, cell=1.0, model="dexel")
    with pytest.raises(CamError):
        milling_loads([tp], res, mat)


def test_ops_sonuc_uyusmuyor():
    mat = malzeme()
    tp, _ = kanal_programi()
    res = simulate([tp], STOCK, cell=CELL)
    fazla, _ = kanal_programi()
    fazla.moves.append(Move(MoveType.LINEAR, (90.0, 0.0, 5.0), feed=900.0))
    eksik, _ = kanal_programi()
    eksik.moves.pop()
    for ops in ([fazla], [eksik], [tp, tp]):
        with pytest.raises(CamError):
            milling_loads(ops, res, mat)


# ------------------------------------------------------------------ split_moves, optimize_feed


@pytest.mark.parametrize("seg", [0.0, -1.0, NAN])
def test_seg_gecersiz(seg):
    tp, _ = kanal_programi()
    with pytest.raises(CamError):
        split_moves([tp], seg)


def test_karisik_freze_torna():
    mat = malzeme()
    tp, _ = kanal_programi()
    torna = Toolpath(
        "torna", kalem(), (23.0, 0.0, 2.0), [Move(MoveType.LINEAR, (23.0, 0.0, -5.0), feed=0.2)], rpm=1000.0,
        plane=Plane.ZX, feed_mode="G95",
    )  # fmt: skip
    with pytest.raises(CamError):
        optimize_feed([tp, torna], STOCK, mat, SpindleLimits())


@pytest.mark.parametrize(
    "kw",
    [
        {"max_factor": 0.99},
        {"max_factor": NAN},
        {"min_factor": 0.0},
        {"min_factor": -0.1},
        {"min_factor": 1.01},
        {"min_factor": NAN},
        {"resolution": 0.0},
        {"resolution": -0.1},
        {"resolution": NAN},
        {"feed_max": 0.0},
        {"feed_max": -100.0},
        {"feed_max": NAN},
        {"air_feed": 0.0},
        {"air_feed": -1.0},
        {"air_feed": NAN},
        {"target_hex": 0.0},
        {"target_hex": -0.05},
        {"target_hex": NAN},
        {"seg": 0.0},
        {"K": 0.0},
    ],
)
def test_optimize_feed_gecersiz(kw):
    mat = malzeme()
    tp, _ = kanal_programi()
    with pytest.raises(CamError):
        optimize_feed([tp], STOCK, mat, SpindleLimits(), **kw)
