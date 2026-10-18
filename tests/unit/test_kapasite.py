"""SPEC 68b K1: tet4 ısıl kapasite matrisi (specs/68b-gecici-isil-termomekanik.md).

Testler yalnız SPEC metninden ve arayüzden yazıldı; uygulama kodu okunmadı.

Ce = ρcp V / 20 · (1 + δ_ab) (tutarlı), Ce_topak = ρcp V / 4 · I. Birim: ρcp mJ/(mm³·K).
"""

from __future__ import annotations

import numpy as np
import pytest

from core.elements import tet4
from core.model import Element, Material, Model, ModelError, Node

REF = np.array([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]])
RASTGELE = np.array([[0.3, -0.2, 0.1], [4.1, 0.5, -0.3], [0.7, 3.2, 0.4], [1.1, 0.9, 2.7]])


def tet(X: np.ndarray, sira: tuple[int, int, int, int] = (1, 2, 3, 4)) -> tuple[Element, Model]:
    m = Model(
        dim=3,
        nodes=[Node(i + 1, *X[i]) for i in range(4)],
        elements=[Element(1, "tet4", list(sira), "celik")],
        materials=[Material("celik", 210_000.0)],
    )
    return m.elements[0], m


def hacim(X: np.ndarray) -> float:
    return abs(np.linalg.det(X[1:] - X[0])) / 6.0


@pytest.mark.parametrize("lumped", [False, True])
@pytest.mark.parametrize("sira", [(1, 2, 3, 4), (1, 3, 2, 4)])  # sağ el ve sol el düğüm sırası
def test_toplam_rho_cp_V(lumped, sira):
    rho_cp = 3.611
    e, m = tet(RASTGELE, sira)
    Ce = tet4.ct(e, m, rho_cp, lumped=lumped)
    assert Ce.shape == (4, 4)
    assert Ce.sum() == pytest.approx(rho_cp * hacim(RASTGELE), rel=1e-12)


def test_referans_tetrahedron_tutarli():
    e, m = tet(REF)
    V = 1.0 / 6.0
    beklenen = V / 20.0 * (np.ones((4, 4)) + np.eye(4))
    np.testing.assert_allclose(tet4.ct(e, m, 1.0), beklenen, rtol=0, atol=1e-15)
    np.testing.assert_allclose(tet4.ct(e, m, 1.0, lumped=False), beklenen, rtol=0, atol=1e-15)


def test_referans_tetrahedron_topakli():
    e, m = tet(REF)
    np.testing.assert_allclose(tet4.ct(e, m, 1.0, lumped=True), np.eye(4) / 24.0, rtol=0, atol=1e-15)


def test_tutarli_simetrik_ve_topakli_ile_ayni_satir_toplami():
    e, m = tet(RASTGELE)
    C = tet4.ct(e, m, 2.43)
    Cl = tet4.ct(e, m, 2.43, lumped=True)
    np.testing.assert_allclose(C, C.T, rtol=0, atol=1e-15 * np.abs(C).max())
    np.testing.assert_allclose(C.sum(axis=1), np.diag(Cl), rtol=1e-12)
    np.testing.assert_allclose(Cl, np.diag(np.diag(Cl)), rtol=0, atol=0)
    assert np.all(np.linalg.eigvalsh(C) > 0)


def test_rho_cp_ile_dogrusal():
    e, m = tet(RASTGELE)
    np.testing.assert_allclose(tet4.ct(e, m, 5.0), 5.0 * tet4.ct(e, m, 1.0), rtol=1e-14)


@pytest.mark.parametrize("rho_cp", [0.0, -1.0, float("nan"), float("inf")])
@pytest.mark.parametrize("lumped", [False, True])
def test_rho_cp_gecersiz(rho_cp, lumped):
    e, m = tet(REF)
    with pytest.raises(ModelError):
        tet4.ct(e, m, rho_cp, lumped=lumped)
