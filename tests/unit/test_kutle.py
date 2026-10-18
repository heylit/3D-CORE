"""
SPEC 45 kütle matrisi ve modal analiz hata testleri (specs/45-modal.md, K1, K2, K12).

Testler yalnız SPEC metninden yazıldı; uygulama kodu okunmadı.

Birimler N – mm – t – s: ρ [t/mm³], kütle [t].
"""

from __future__ import annotations

import types

import numpy as np
import pytest
import scipy.sparse as sp

from core import elements
from core.assembly import assemble_M
from core.elements import bar1d, tet4
from core.modal import modal, model_mass
from core.model import BC, Element, Material, Model, ModelError, Node, Section
from tests.benchmarks.tet_ag import kutu_agi, yuz_dugumleri

E, NU = 210_000.0, 0.3


def cubuk(x1: float, x2: float, A: float, rho: float) -> Model:
    return Model(
        dim=1,
        nodes=[Node(1, x1), Node(2, x2)],
        elements=[Element(1, "bar1d", [1, 2], "m", "s")],
        materials=[Material("m", E, NU, rho)],
        sections=[Section("s", A)],
    )


def tet(X: np.ndarray, rho: float, sira: tuple[int, int, int, int] = (1, 2, 3, 4)) -> Model:
    return Model(
        dim=3,
        nodes=[Node(i + 1, *X[i]) for i in range(4)],
        elements=[Element(1, "tet4", list(sira), "m")],
        materials=[Material("m", E, NU, rho)],
    )


BIRIM_TET = np.array([[0.0, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 1]])
GENEL_TET = np.array([[0.3, -0.2, 0.1], [2.1, 0.4, -0.3], [0.5, 1.7, 0.2], [0.2, 0.6, 1.9]])


def tet_hacmi(X: np.ndarray) -> float:
    return abs(np.linalg.det(X[1:] - X[0])) / 6.0


def oteleme(n_dugum: int, dpn: int, d: int) -> np.ndarray:
    """d yönünde birim öteleme vektörü (düğüm başına dpn DOF)."""
    r = np.zeros(n_dugum * dpn)
    r[d::dpn] = 1.0
    return r


# --- K1: bar1d ----------------------------------------------------------------------


@pytest.mark.parametrize("x1, x2", [(2.0, 5.0), (5.0, 2.0)])
def test_bar1d_tutarli_el_hesabi(x1, x2):
    """ρAL/6 · [[2, 1], [1, 2]]; ρ = 2, A = 4, L = 3 → ρAL = 24 (düğüm sırası ters olsa da)."""
    m = cubuk(x1, x2, A=4.0, rho=2.0)
    me = bar1d.me(m.elements[0], m)
    assert me.shape == (2, 2)
    np.testing.assert_allclose(me, 4.0 * np.array([[2.0, 1.0], [1.0, 2.0]]), rtol=1e-12, atol=0)


def test_bar1d_toplanmis_el_hesabi():
    m = cubuk(2.0, 5.0, A=4.0, rho=2.0)
    me = bar1d.me(m.elements[0], m, lumped=True)
    np.testing.assert_allclose(me, 12.0 * np.eye(2), rtol=1e-12, atol=0)


@pytest.mark.parametrize("lumped", [False, True])
def test_bar1d_simetrik_ve_toplam_kutle(lumped):
    rho, A, L = 7.85e-9, 10.0, 37.0
    m = cubuk(0.0, L, A=A, rho=rho)
    me = bar1d.me(m.elements[0], m, lumped=lumped)
    np.testing.assert_array_equal(me, me.T)
    r = np.ones(2)
    assert r @ me @ r == pytest.approx(rho * A * L, rel=1e-12)
    assert np.all(np.linalg.eigvalsh(me) > 0)


def test_bar1d_varsayilan_tutarli():
    m = cubuk(0.0, 1.0, A=1.0, rho=6.0)
    np.testing.assert_allclose(bar1d.me(m.elements[0], m), [[2.0, 1.0], [1.0, 2.0]], rtol=1e-12)


@pytest.mark.parametrize("rho", [0.0, -1e-9])
@pytest.mark.parametrize("lumped", [False, True])
def test_bar1d_rho_pozitif_degil(rho, lumped):
    m = cubuk(0.0, 1.0, A=1.0, rho=rho)
    with pytest.raises(ModelError):
        bar1d.me(m.elements[0], m, lumped=lumped)


# --- K1: tet4 -----------------------------------------------------------------------


def tet_tutarli_beklenen(rhoV: float) -> np.ndarray:
    """ρV/20 · (1 + δ_ab) ⊗ I₃; DOF sırası [u1, v1, w1, ..., w4]."""
    B = np.ones((4, 4)) + np.eye(4)
    beklenen = np.zeros((12, 12))
    for a in range(4):
        for b in range(4):
            beklenen[3 * a : 3 * a + 3, 3 * b : 3 * b + 3] = B[a, b] * np.eye(3)
    return rhoV / 20.0 * beklenen


@pytest.mark.parametrize("sira", [(1, 2, 3, 4), (1, 3, 2, 4)])  # sağ el ve sol el
def test_tet4_tutarli_birim_kose(sira):
    """Birim köşe tetrahedronu, ρ = 3: V = 1/6, ρV = 0.5."""
    m = tet(BIRIM_TET, rho=3.0, sira=sira)
    me = tet4.me(m.elements[0], m)
    assert me.shape == (12, 12)
    np.testing.assert_allclose(me, tet_tutarli_beklenen(0.5), rtol=1e-12, atol=1e-15)


@pytest.mark.parametrize("sira", [(1, 2, 3, 4), (1, 3, 2, 4)])
def test_tet4_toplanmis_birim_kose(sira):
    m = tet(BIRIM_TET, rho=3.0, sira=sira)
    me = tet4.me(m.elements[0], m, lumped=True)
    np.testing.assert_allclose(me, 0.5 / 4.0 * np.eye(12), rtol=1e-12, atol=1e-15)


def test_tet4_genel_tetrahedron():
    """Eğik tetrahedron: aynı kalıp, V testin kendi determinant hesabından."""
    rho = 7.85e-9
    m = tet(GENEL_TET, rho=rho)
    rhoV = rho * tet_hacmi(GENEL_TET)
    np.testing.assert_allclose(tet4.me(m.elements[0], m), tet_tutarli_beklenen(rhoV), rtol=1e-12, atol=0)
    me_k = tet4.me(m.elements[0], m, lumped=True)
    np.testing.assert_allclose(me_k, rhoV / 4 * np.eye(12), rtol=1e-12, atol=0)


@pytest.mark.parametrize("lumped", [False, True])
def test_tet4_simetrik_pozitif_toplam_kutle(lumped):
    rho = 7.85e-9
    m = tet(GENEL_TET, rho=rho)
    me = tet4.me(m.elements[0], m, lumped=lumped)
    np.testing.assert_array_equal(me, me.T)
    assert np.all(np.linalg.eigvalsh(me / rho) > 0)
    rhoV = rho * tet_hacmi(GENEL_TET)
    for d in range(3):
        r = oteleme(4, 3, d)
        assert r @ me @ r == pytest.approx(rhoV, rel=1e-12)


def test_tet4_toplanmis_kosegen():
    m = tet(GENEL_TET, rho=1.0)
    me = tet4.me(m.elements[0], m, lumped=True)
    np.testing.assert_array_equal(me, np.diag(np.diag(me)))


@pytest.mark.parametrize("rho", [0.0, -1e-9])
@pytest.mark.parametrize("lumped", [False, True])
def test_tet4_rho_pozitif_degil(rho, lumped):
    m = tet(BIRIM_TET, rho=rho)
    with pytest.raises(ModelError):
        tet4.me(m.elements[0], m, lumped=lumped)


def test_tet4_yassi_eleman_hatasi():
    """Hatalar ke ile aynı: yassı tetrahedron → ModelError."""
    X = BIRIM_TET.copy()
    X[3] = [0.3, 0.3, 0.0]
    m = tet(X, rho=1.0)
    with pytest.raises(ModelError):
        tet4.me(m.elements[0], m)


# --- K2: assemble_M + model_mass ------------------------------------------------------

L, B, H = 6.0, 2.0, 1.5
RHO = 7.85e-9


def kutu(rho: float = RHO) -> Model:
    return kutu_agi(L, B, H, 4, 3, 2, Material("celik", E, NU, rho), kaydirma=0.2, tohum=3)


@pytest.mark.parametrize("lumped", [False, True])
def test_assemble_M_kutu_toplam_kutle(lumped):
    m = kutu()
    M = assemble_M(m, lumped=lumped)
    assert sp.issparse(M)
    assert M.shape == (m.n_dof, m.n_dof)
    for d in range(3):
        r = oteleme(len(m.nodes), 3, d)
        assert r @ (M @ r) == pytest.approx(RHO * L * B * H, rel=1e-12)
    assert abs(M - M.T).max() <= 1e-14 * abs(M).max()


def test_assemble_M_varsayilan_tutarli():
    m = kutu()
    fark = assemble_M(m) - assemble_M(m, lumped=False)
    assert abs(fark).max() == 0.0
    # tutarlı kütle köşegen değildir, toplanmış köşegendir
    Mt = assemble_M(m).toarray()
    Mk = assemble_M(m, lumped=True).toarray()
    assert np.abs(Mt - np.diag(np.diag(Mt))).max() > 0
    np.testing.assert_array_equal(Mk, np.diag(np.diag(Mk)))


def test_model_mass_kutu():
    assert model_mass(kutu()) == pytest.approx(RHO * L * B * H, rel=1e-12)


def test_assemble_M_ve_model_mass_cubuk():
    """3 elemanlı çubuk: Σ M = ρAL, M üç köşegenli."""
    rho, A = 7.85e-9, 12.0
    m = Model(
        dim=1,
        nodes=[Node(1, 0.0), Node(2, 10.0), Node(3, 25.0), Node(4, 45.0)],
        elements=[Element(i, "bar1d", [i, i + 1], "m", "s") for i in (1, 2, 3)],
        materials=[Material("m", E, NU, rho)],
        sections=[Section("s", A)],
    )
    for lumped in (False, True):
        M = assemble_M(m, lumped=lumped)
        assert M.sum() == pytest.approx(rho * A * 45.0, rel=1e-12)
    M = assemble_M(m).toarray()
    np.testing.assert_allclose(M[1, 1], rho * A * (10.0 + 15.0) / 3.0, rtol=1e-12)
    np.testing.assert_allclose(M[1, 2], rho * A * 15.0 / 6.0, rtol=1e-12)
    assert M[0, 2] == 0.0
    assert model_mass(m) == pytest.approx(rho * A * 45.0, rel=1e-12)


def test_model_mass_rho_pozitif_degil():
    with pytest.raises(ModelError):
        model_mass(kutu(rho=0.0))
    with pytest.raises(ModelError):
        model_mass(cubuk(0.0, 1.0, A=1.0, rho=-1.0))


def test_assemble_M_rho_sifir():
    with pytest.raises(ModelError):
        assemble_M(kutu(rho=0.0))


# --- K12: modal hataları ----------------------------------------------------------------


def konsol_cubuk(n: int = 4, rho: float = RHO) -> Model:
    m = Model(
        dim=1,
        nodes=[Node(i + 1, 10.0 * i) for i in range(n + 1)],
        elements=[Element(i + 1, "bar1d", [i + 1, i + 2], "m", "s") for i in range(n)],
        materials=[Material("m", E, NU, rho)],
        sections=[Section("s", 10.0)],
        bcs=[BC(1, "ux")],
    )
    return m


@pytest.mark.parametrize("n_modes", [0, -1, 5])  # n_f = 4
def test_modal_gecersiz_mod_sayisi(n_modes):
    with pytest.raises(ModelError):
        modal(konsol_cubuk(4), n_modes)


@pytest.mark.parametrize("n_modes", [2.5, "2", None])
def test_modal_tamsayi_olmayan_mod_sayisi(n_modes):
    with pytest.raises(ModelError):
        modal(konsol_cubuk(4), n_modes)


def test_modal_n_f_kadar_mod_gecerli():
    assert len(modal(konsol_cubuk(4), 4).f) == 4


def test_modal_serbest_dof_yok():
    m = konsol_cubuk(2)
    m.bcs = [BC(i, "ux") for i in (1, 2, 3)]
    with pytest.raises(ModelError):
        modal(m, 1)


def test_modal_tet_serbest_dof_yok():
    m = kutu()
    for n in m.nodes:
        m.bcs.extend(BC(n.id, d) for d in ("ux", "uy", "uz"))
    with pytest.raises(ModelError):
        modal(m, 1)


@pytest.mark.parametrize("lumped", [False, True])
def test_modal_rho_sifir(lumped):
    with pytest.raises(ModelError):
        modal(konsol_cubuk(4, rho=0.0), 2, lumped=lumped)


def test_modal_tet_rho_sifir():
    m = kutu(rho=0.0)
    for n in yuz_dugumleri(m, 0, 0.0):
        m.bcs.extend(BC(n, d) for d in ("ux", "uy", "uz"))
    with pytest.raises(ModelError):
        modal(m, 3)


def test_modal_me_saglamayan_eleman(monkeypatch):
    """Test içinde kaydı yapılan sahte eleman tipi: ke ve dofs var, me yok → ModelError."""
    sahte = types.SimpleNamespace(ke=bar1d.ke, dofs=bar1d.dofs)
    monkeypatch.setitem(elements.ELEMENTS, "sahte", sahte)
    m = konsol_cubuk(3)
    m.elements[1].type = "sahte"
    with pytest.raises(ModelError):
        modal(m, 2)
    with pytest.raises(ModelError):
        assemble_M(m)


def test_modal_celisen_bc():
    m = konsol_cubuk(3)
    m.bcs = [BC(1, "ux", 0.0), BC(1, "ux", 0.5)]
    with pytest.raises(ModelError):
        modal(m, 2)


def test_modal_ayni_degerli_tekrar_bc_celismez():
    """Aynı değerle iki kez tutulan DOF çelişki değildir (solver ile aynı); BC value modları etkilemez."""
    tek = modal(konsol_cubuk(3), 3)
    m = konsol_cubuk(3)
    m.bcs = [BC(1, "ux", 0.25), BC(1, "ux", 0.25)]
    iki = modal(m, 3)
    np.testing.assert_allclose(iki.omega2, tek.omega2, rtol=1e-12)


def test_modal_bilinmeyen_dugum_bc():
    """model.validate() çağrılır: bilinmeyen düğümde BC → ModelError."""
    m = konsol_cubuk(3)
    m.bcs.append(BC(99, "ux"))
    with pytest.raises(ModelError):
        modal(m, 2)
