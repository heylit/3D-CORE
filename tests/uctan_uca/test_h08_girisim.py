"""SPEC 46 H8 — montajda girişim (SPEC 09). K8.

Mil Ø20, delik Ø20: yüzeyler çakışık → yalnız temas. Mil x yönünde e = 1 kaydırılınca girişim hacmi
A · 12, A = π r² − (2 r² acos(e / 2r) − (e/2) √(4r² − e²)) (eşit iki dairenin fark alanı).
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from tests.uctan_uca.conftest import R_MIL, H, halka, montaj_agaci

girisim = halka("09", "assy.girisim", "check", "ClashKind")
tree = halka("09", "assy.tree", "world")

pytestmark = pytest.mark.occt


def girisim_hacmi(e: float, r: float = R_MIL, h: float = H) -> float:
    mercek = 2 * r**2 * math.acos(e / (2 * r)) - (e / 2) * math.sqrt(4 * r**2 - e**2)
    return (math.pi * r**2 - mercek) * h


@pytest.fixture(scope="module")
def parcalar(flans, mil):
    return {"flans": flans, "mil": mil}


def test_k8_cozulmus_montajda_yalniz_temas(montaj, parcalar):
    sonuc = girisim.check(montaj, parcalar)
    assert [(c.a, c.b, c.kind) for c in sonuc] == [("flans", "mil", girisim.ClashKind.TEMAS)]


def test_k8_kaydirilmis_milde_girisim_hacmi(montaj, parcalar):
    T = tree.world(montaj, "mil").copy()
    T[0, 3] += 1.0
    kaymis = montaj_agaci(mil_T=T)
    sonuc = girisim.check(kaymis, parcalar)
    assert len(sonuc) == 1
    c = sonuc[0]
    assert (c.a, c.b, c.kind) == ("flans", "mil", girisim.ClashKind.GIRISIM)
    assert c.volume == pytest.approx(girisim_hacmi(1.0), rel=1e-3)
    assert c.center is not None and np.all(np.isfinite(c.center))
