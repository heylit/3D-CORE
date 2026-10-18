"""SPEC 46 H6 — flanş + mil montajı (SPEC 07 ağaç, SPEC 08 kısıtlar). K6.

Mil keyfi bir konumdan (öteleme + Z etrafında dönme) başlar; eş eksen + çakışık alt düzlemlerle
flanşın merkez deliğine oturur. Kalan serbestlik: eksen etrafında dönme (dof = 1).
"""

from __future__ import annotations

import numpy as np
import pytest

from assy.solver import solve
from assy.tree import apply, flatten, validate, world
from tests.uctan_uca.conftest import MERKEZ, montaj_agaci, montaj_kisitlari


@pytest.fixture(scope="module")
def cozum():
    kok = montaj_agaci()
    assy = flatten(kok, fixed=["flans"])
    assy.mates = montaj_kisitlari()
    res = solve(assy)
    res.apply(assy)
    return kok, assy, res


def test_k6_cozucu_yakinsar_dof_1(cozum):
    _, _, res = cozum
    assert res.residual <= 1e-10
    assert res.dof == 1


def test_k6_mil_merkez_deligine_oturur(cozum):
    kok, assy, _ = cozum
    yeni = apply(kok, assy)
    validate(yeni)
    T = world(yeni, "mil")
    assert np.allclose(T[:3, 3], [*MERKEZ, 0.0], atol=1e-9)
    assert np.allclose(T[:3, 2], [0.0, 0.0, 1.0], atol=1e-9)  # mil ekseni +Z
    assert np.allclose(world(yeni, "flans"), np.eye(4), atol=1e-12)  # sabit parça kıpırdamaz
