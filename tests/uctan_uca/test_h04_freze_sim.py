"""SPEC 46 H4 — flanşın talaş simülasyonu (SPEC 05). K4.

Kaldırılan hacim sınırı (SPEC 46 §4): z-haritasında yalnız dikey duvarları kesen hücreler hatalıdır,
|ΔV − ΔV₀| ≤ 2·h·Σ(çevre · yükseklik); duvarlar Ø20 ve dört Ø6.6 delik, yükseklik 12.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from cam.sim import ZMap, part_zmap, simulate
from tests.uctan_uca.conftest import D_KOSE, D_MERKEZ, H, V_flans

pytestmark = pytest.mark.occt

CELL = 0.5


@pytest.fixture(scope="module")
def sonuc(freze_ops, flans_stok, flans):
    g = ZMap.from_stock(flans_stok, CELL)
    zP = np.asarray(part_zmap(flans, g, tol=0.01), dtype=float)
    return simulate(freze_ops, flans_stok, cell=CELL, part_z=zP)


def test_k4_carpisma_ve_cakma_yok(sonuc):
    assert sonuc.collisions == []


def test_k4_kaldirilan_hacim(sonuc, flans_stok):
    dV0 = flans_stok.volume - V_flans()
    duvar = (math.pi * D_MERKEZ + 4 * math.pi * D_KOSE) * H
    assert abs(sonuc.removed_volume - dV0) <= 2 * CELL * duvar
