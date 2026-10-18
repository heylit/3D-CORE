"""
SPEC 12 — mesnet ve tutarlı düğüm yükleri (mesh.fix, mesh.add_traction, mesh.add_pressure): K8, K9, K10.

Testler sadece specs/12-gmsh.md'den yazıldı; mesh/ uygulama kodu okunmadı.
Ağlar çoğunlukla SPEC 11'in yapılandırılmış Kuhn kutusudur (gmsh'siz); gmsh silindiri `gmsh` fikstürü
ve `occt` işaretiyle atlanabilir.
"""

from __future__ import annotations

import copy
import functools
import math

import numpy as np
import pytest

import mesh
from core.model import BC, Load, Material, Model, ModelError
from tests.benchmarks.tet_ag import kutu_agi

E, NU = 210_000.0, 0.3
L, B, H = 10.0, 4.0, 2.0
DOF = ("ux", "uy", "uz")


def celik() -> Material:
    return Material("celik", E, NU)


@pytest.fixture
def gmsh():
    return pytest.importorskip("gmsh", reason='gmsh kurulu değil (pip install -e ".[mesh]")')


def yapili_ag() -> Model:
    return kutu_agi(L, B, H, 5, 2, 2, celik(), kaydirma=0.2, tohum=5)


@functools.cache
def gmsh_silindir() -> Model:
    import build123d as bd

    from geometry.part import Part

    return mesh.tet_mesh(Part(bd.Cylinder(10.0, 20.0), name="silindir"), 2.5, celik())


# --- testin kendi hesabı -------------------------------------------------------------


def ucgen_verisi(model: Model, tris: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """(A, n, c): alanlar, birim normaller (köşe sırasına göre sağ el), ağırlık merkezleri."""
    X = {n.id: n.xyz for n in model.nodes}
    P = np.array([[X[int(i)] for i in t] for t in tris])
    v = np.cross(P[:, 1] - P[:, 0], P[:, 2] - P[:, 0])
    A2 = np.linalg.norm(v, axis=1)
    return 0.5 * A2, v / A2[:, None], P.mean(axis=1)


def toplam_kuvvet_ve_moment(model: Model, loads: list[Load]) -> tuple[np.ndarray, np.ndarray]:
    F, M = np.zeros(3), np.zeros(3)
    for ld in loads:
        f = np.zeros(3)
        f[DOF.index(ld.dof)] = ld.value
        F += f
        M += np.cross(model.node(ld.node).xyz, f)
    return F, M


def sira_kurali(loads: list[Load]) -> None:
    """(düğüm, dof) başına tek Load, tam sıfır bileşen yok, düğüm id'si sonra ux, uy, uz sırası."""
    anahtar = [(ld.node, DOF.index(ld.dof)) for ld in loads]
    assert len(set(anahtar)) == len(anahtar), "aynı (düğüm, dof) için birden fazla Load"
    assert anahtar == sorted(anahtar)
    assert all(ld.value != 0.0 for ld in loads)


def x_L_yuzu(m: Model) -> np.ndarray:
    return mesh.select_triangles(m, mesh.on_plane((L, 0.0, 0.0), (1.0, 0.0, 0.0)))


# --- K8: yüzey çekmesi -------------------------------------------------------------------


@pytest.mark.parametrize("t", [(50.0, -20.0, 0.0), (0.0, 0.0, 7.5), (3.0, 4.0, -12.0)])
def test_k8_cekme_kuvvet_ve_moment(t):
    """Σ F = t Σ A, Σ x × F = Σ A c × t (rel 1e-12); x = L yüzünde."""
    m = yapili_ag()
    tris = x_L_yuzu(m)
    mesh.add_traction(m, tris, t)
    A, _, c = ucgen_verisi(m, tris)
    t = np.asarray(t)
    F, M = toplam_kuvvet_ve_moment(m, m.loads)
    np.testing.assert_allclose(F, t * A.sum(), rtol=1e-12, atol=1e-12 * np.abs(t).max() * A.sum())
    M0 = (A[:, None] * np.cross(c, t)).sum(axis=0)
    olcek = np.abs(t).max() * A.sum() * L
    np.testing.assert_allclose(M, M0, rtol=1e-12, atol=1e-12 * olcek)


def test_k8_cekme_kose_payi_tek_ucgen():
    """Tek üçgende her köşeye t A / 3 (A = ½ · 1 · 1 = ½ için t / 6)."""
    from tests.mesh.test_secim import tek_tet

    m = tek_tet()
    mesh.add_traction(m, np.array([[1, 3, 2]]), (6.0, 0.0, -12.0))
    assert [(ld.node, ld.dof) for ld in m.loads] == [
        (1, "ux"),
        (1, "uz"),
        (2, "ux"),
        (2, "uz"),
        (3, "ux"),
        (3, "uz"),
    ]
    np.testing.assert_allclose([ld.value for ld in m.loads], [1.0, -2.0] * 3, rtol=1e-14)


def test_k8_cekme_tek_load_sifir_yok_sirali():
    """t_z = 0 → hiç uz yükü yok; paylaşılan köşeler toplanır; sıra kurala uygun."""
    m = yapili_ag()
    tris = x_L_yuzu(m)
    mesh.add_traction(m, tris, (50.0, -20.0, 0.0))
    sira_kurali(m.loads)
    assert {ld.dof for ld in m.loads} == {"ux", "uy"}
    assert {ld.node for ld in m.loads} == {int(i) for i in np.unique(tris)}


def test_k8_cekme_mevcut_yukleri_korur():
    """add_traction yeni Load'lar ekler; önceden var olanlara dokunmaz."""
    m = yapili_ag()
    onceki = Load(1, "uz", 5.0)
    m.loads.append(onceki)
    mesh.add_traction(m, x_L_yuzu(m), (1.0, 0.0, 0.0))
    assert m.loads[0] == onceki
    assert len(m.loads) == 1 + len(np.unique(x_L_yuzu(m)))


def test_k8_bos_ucgen_listesi():
    m = yapili_ag()
    mesh.add_traction(m, np.empty((0, 3), dtype=int), (1.0, 2.0, 3.0))
    mesh.add_pressure(m, np.empty((0, 3), dtype=int), 10.0)
    assert m.loads == []


@pytest.mark.parametrize("t", [(math.nan, 0.0, 0.0), (0.0, math.inf, 0.0)])
def test_k8_sonlu_olmayan_cekme(t):
    m = yapili_ag()
    with pytest.raises(ModelError):
        mesh.add_traction(m, x_L_yuzu(m), t)


def test_k8_bilinmeyen_dugum():
    m = yapili_ag()
    with pytest.raises(ModelError):
        mesh.add_traction(m, np.array([[1, 2, 99999]]), (1.0, 0.0, 0.0))
    with pytest.raises(ModelError):
        mesh.add_pressure(m, np.array([[1, 2, 99999]]), 1.0)


# --- K9: basınç ------------------------------------------------------------------------------


def test_k9_basinc_kapali_sinirda_dengede():
    """Tüm kapalı sınıra p: |Σ F| ≤ 1e-9 p Σ A, |Σ x × F| ≤ 1e-9 p Σ A ℓ."""
    m = yapili_ag()
    tris = mesh.boundary_triangles(m)
    p = 25.0
    mesh.add_pressure(m, tris, p)
    A, _, _ = ucgen_verisi(m, tris)
    X = np.array([n.xyz for n in m.nodes])
    ell = np.linalg.norm(X.max(axis=0) - X.min(axis=0))
    F, M = toplam_kuvvet_ve_moment(m, m.loads)
    assert len(m.loads) > 0
    assert np.linalg.norm(F) <= 1e-9 * p * A.sum()
    assert np.linalg.norm(M) <= 1e-9 * p * A.sum() * ell
    sira_kurali(m.loads)


@pytest.mark.occt
def test_k9_basinc_silindir_kapali_sinirda_dengede(gmsh):
    """Eğri yüzlü gmsh ağında da kapalı sınıra basınç toplamda sıfır kuvvet ve moment verir."""
    m = copy.deepcopy(gmsh_silindir())
    tris = mesh.boundary_triangles(m)
    p = 3.0
    mesh.add_pressure(m, tris, p)
    A, _, _ = ucgen_verisi(m, tris)
    X = np.array([n.xyz for n in m.nodes])
    ell = np.linalg.norm(X.max(axis=0) - X.min(axis=0))
    F, M = toplam_kuvvet_ve_moment(m, m.loads)
    assert np.linalg.norm(F) <= 1e-9 * p * A.sum()
    assert np.linalg.norm(M) <= 1e-9 * p * A.sum() * ell


@pytest.mark.parametrize("eksen, deger, n_hat", [(0, L, (1, 0, 0)), (1, 0.0, (0, -1, 0)), (2, H, (0, 0, 1))])
def test_k9_basinc_tek_yuz(eksen, deger, n_hat):
    """Tek düzlem yüzüne p: Σ F = −p n̂ A_yüz (rel 1e-12); pozitif p cisme bastırır."""
    m = yapili_ag()
    nokta = [0.0, 0.0, 0.0]
    nokta[eksen] = deger
    tris = mesh.select_triangles(m, mesh.on_plane(nokta, n_hat))
    A_yuz = (L * B * H) / (L, B, H)[eksen]
    p = 40.0
    mesh.add_pressure(m, tris, p)
    F, _ = toplam_kuvvet_ve_moment(m, m.loads)
    np.testing.assert_allclose(F, -p * np.array(n_hat, float) * A_yuz, rtol=1e-12, atol=1e-12 * p * A_yuz)
    sira_kurali(m.loads)


def test_k9_basinc_kose_payi_tek_ucgen():
    """Tek üçgen (1, 3, 2), n = −z, A = ½: her köşeye −p n A / 3 = (0, 0, p/6)."""
    from tests.mesh.test_secim import tek_tet

    m = tek_tet()
    mesh.add_pressure(m, np.array([[1, 3, 2]]), 6.0)
    assert [(ld.node, ld.dof) for ld in m.loads] == [(1, "uz"), (2, "uz"), (3, "uz")]
    np.testing.assert_allclose([ld.value for ld in m.loads], [1.0, 1.0, 1.0], rtol=1e-14)


@pytest.mark.parametrize("p", [math.nan, math.inf, -math.inf])
def test_k9_sonlu_olmayan_basinc(p):
    m = yapili_ag()
    with pytest.raises(ModelError):
        mesh.add_pressure(m, x_L_yuzu(m), p)


# --- K10: mesnet ------------------------------------------------------------------------------


def test_k10_ankastre_varsayilan():
    """Varsayılan: üç öteleme 0; düğüm × dof kadar BC."""
    m = yapili_ag()
    ids = mesh.select_nodes(m, mesh.on_plane((0.0, 0.0, 0.0), (1.0, 0.0, 0.0)))
    mesh.fix(m, ids)
    assert len(m.bcs) == 3 * len(ids)
    assert {(bc.node, bc.dof) for bc in m.bcs} == {(n, d) for n in ids for d in DOF}
    assert all(bc.value == 0.0 for bc in m.bcs)


def test_k10_secili_dof_ve_deger():
    """Simetri mesnedi gibi tek dof, veya zorlanmış yer değiştirme değeri."""
    m = yapili_ag()
    mesh.fix(m, [1, 2, 3], dofs=("uy",), value=0.25)
    assert sorted((bc.node, bc.dof, bc.value) for bc in m.bcs) == [
        (1, "uy", 0.25),
        (2, "uy", 0.25),
        (3, "uy", 0.25),
    ]


def test_k10_ayni_degerle_tekrar_degismez():
    m = yapili_ag()
    mesh.fix(m, [1, 2], dofs=("ux", "uz"))
    once = list(m.bcs)
    mesh.fix(m, [1, 2], dofs=("ux", "uz"))
    mesh.fix(m, [2], dofs=("uz",), value=0.0)
    assert m.bcs == once
    mesh.fix(m, [2, 3], dofs=("ux",))  # 2 zaten tutulu, sadece 3 eklenir
    assert len(m.bcs) == len(once) + 1
    assert m.bcs[-1] == BC(3, "ux", 0.0)


def test_k10_farkli_degerle_hata():
    m = yapili_ag()
    mesh.fix(m, [4], dofs=("ux",), value=0.0)
    with pytest.raises(ModelError):
        mesh.fix(m, [4], dofs=("ux",), value=0.1)


def test_k10_onceden_var_olan_bc_ile_celiski():
    """Model'e elle eklenmiş BC de dikkate alınır."""
    m = yapili_ag()
    m.bcs.append(BC(5, "uy", 0.3))
    mesh.fix(m, [5], dofs=("uy",), value=0.3)
    assert len(m.bcs) == 1
    with pytest.raises(ModelError):
        mesh.fix(m, [5], dofs=("uy",))
