"""SPEC 46 H1 — model: flanş ve mil (SPEC 02, 23). K1."""

from __future__ import annotations

import numpy as np
import pytest

from tests.uctan_uca.conftest import D_KOSE, D_MERKEZ, KOSELER, L_MIL, MERKEZ, R_MIL, A, B, H, V_flans, V_mil

pytestmark = pytest.mark.occt


def test_k1_flans_hacim_ve_sinir_kutusu(flans):
    assert flans.volume == pytest.approx(V_flans(), rel=1e-6)
    lo, hi = flans.bbox
    assert np.allclose(lo, [0, 0, 0], atol=1e-6)
    assert np.allclose(hi, [A, B, H], atol=1e-6)


def test_k1_flans_delik_kayitlari(flans):
    delikler = flans.holes
    assert len(delikler) == 5
    assert all(h.through for h in delikler)
    merkezler = sorted((round(float(h.origin[0]), 6), round(float(h.origin[1]), 6), h.d) for h in delikler)
    beklenen = sorted([(*MERKEZ, D_MERKEZ)] + [(x, y, D_KOSE) for x, y in KOSELER])
    assert merkezler == pytest.approx(beklenen)


def test_k1_mil_hacim_ve_sinir_kutusu(mil):
    assert mil.volume == pytest.approx(V_mil(), rel=1e-6)
    lo, hi = mil.bbox
    assert np.allclose(lo, [-R_MIL, -R_MIL, 0], atol=1e-6)
    assert np.allclose(hi, [R_MIL, R_MIL, L_MIL], atol=1e-6)
