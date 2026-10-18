"""SPEC 46 H3 — flanşın elle kurulan freze yolları (SPEC 03, 04 `DrillOp`). K3.

SPEC 46 K3'te delme dibi `z = 0`: SPEC 14 ham malzeme altına inmeyi yasaklar (taşma 0).
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from cam.gcode import DrillOp
from cam.model import MoveType, Toolpath
from tests.uctan_uca.conftest import D_MERKEZ, KOSELER, MERKEZ, H

TOL = 1e-6
KESME = {MoveType.LINEAR, MoveType.ARC_CW, MoveType.ARC_CCW}


def kesme_noktalari(tp: Toolpath) -> np.ndarray:
    return np.array([m.end for m in tp.moves if m.type in KESME], dtype=float)


def test_k3_islem_sirasi_ve_turleri(freze_ops):
    alin, cep, delik = freze_ops
    assert isinstance(alin, Toolpath) and alin.tool.id == 1
    assert isinstance(cep, Toolpath) and cep.tool.id == 2
    assert isinstance(delik, DrillOp) and delik.tool.id == 3


def test_k3_alin_z12ye_iner_altina_inmez(freze_ops):
    P = kesme_noktalari(freze_ops[0])
    assert P[:, 2].min() == pytest.approx(H, abs=TOL)


def test_k3_cep_dairenin_icinde_dibi_z0(freze_ops):
    cep = freze_ops[1]
    P = kesme_noktalari(cep)
    r = np.hypot(P[:, 0] - MERKEZ[0], P[:, 1] - MERKEZ[1])
    assert r.max() <= D_MERKEZ / 2 - cep.tool.D / 2 + TOL
    assert P[:, 2].min() == pytest.approx(0.0, abs=TOL)
    # yaylar da daire içinde: merkez + yarıçap ≤ r − D/2
    p0 = np.array(cep.start, dtype=float)
    for m in cep.moves:
        if m.type in (MoveType.ARC_CW, MoveType.ARC_CCW):
            R = math.hypot(p0[0] - m.center[0], p0[1] - m.center[1])
            d = math.hypot(m.center[0] - MERKEZ[0], m.center[1] - MERKEZ[1])
            assert d + R <= D_MERKEZ / 2 - cep.tool.D / 2 + TOL
        p0 = np.array(m.end, dtype=float)


def test_k3_kose_delikleri(freze_ops):
    delik = freze_ops[2]
    delik.validate()
    assert sorted(delik.holes) == sorted(KOSELER)
    assert delik.z == pytest.approx(0.0)
