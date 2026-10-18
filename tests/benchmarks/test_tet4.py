"""
tet4 analitik benchmark'ları (specs/11-tet4.md, K7–K11 ve K13).

Ağlar tests/benchmarks/tet_ag.py'deki yapılandırılmış Kuhn kutu ağından gelir.
"""

from __future__ import annotations

import functools
from pathlib import Path

import numpy as np
import pytest

from core import post
from core.elements import tet4
from core.model import BC, Material, Model, ModelError
from core.solver import solve
from tests.benchmarks.tet_ag import kutu_agi, yuz_dugumleri, yuzey_cekmesi
from tests.conftest import STEEL_E

NU = 0.3
ORNEK = Path(__file__).resolve().parents[2] / "examples" / "11_tet4_cekme.json"


def celik() -> Material:
    return Material("celik", STEEL_E, NU)


def dugum_dizileri(model: Model, v: np.ndarray) -> np.ndarray:
    """Global DOF vektörü -> (düğüm sayısı, 3), model.nodes sırasında."""
    return np.array([[v[model.dof_index(n.id, d)] for d in ("ux", "uy", "uz")] for n in model.nodes])


def kuvvet_vektoru(model: Model) -> np.ndarray:
    F = np.zeros(model.n_dof)
    for ld in model.loads:
        F[model.dof_index(ld.node, ld.dof)] += ld.value
    return F


def denge_kontrol(model: Model, r) -> None:
    """K9: Σ (R + F) = 0 her eksende ve Σ x × (R + F) = 0 (abs 1e-8 · |F| · L).

    |F| ölçeği = Σ|F| + Σ|R| (sadece zorlanmış yer değiştirmeli modellerde F = 0 olur),
    L = modelin en büyük boyu.
    """
    X = np.array([n.xyz for n in model.nodes])
    F = kuvvet_vektoru(model)
    T = dugum_dizileri(model, r.reactions + F)
    olcek = np.abs(F).sum() + np.abs(r.reactions).sum()
    L = np.ptp(X, axis=0).max()
    assert olcek > 0
    np.testing.assert_allclose(T.sum(axis=0), 0.0, atol=1e-8 * olcek)
    np.testing.assert_allclose(np.cross(X, T).sum(axis=0), 0.0, atol=1e-8 * olcek * L)


def sabitle(model: Model, eksen: int, deger: float, dofs: tuple[str, ...]) -> None:
    for n in yuz_dugumleri(model, eksen, deger):
        model.bcs.extend(BC(n, d, 0.0) for d in dofs)


# --- K7: Patch test (Irons) ------------------------------------------------------

PATCH_H = np.array([[1.2, -0.7, 0.4], [0.9, -0.5, 1.6], [-1.1, 0.3, 0.8]]) * 1e-3  # simetrik değil
PATCH_U0 = np.array([0.01, -0.02, 0.015])


def _patch_model(tohum: int) -> tuple[Model, set[int]]:
    """3 x 3 x 3 kutu (2 x 1.5 x 1 mm), iç düğümler düzensiz kaydırılmış; sınıra u0 + H x yazılı."""
    L, b, h = 2.0, 1.5, 1.0
    m = kutu_agi(L, b, h, 3, 3, 3, celik(), kaydirma=0.2, tohum=tohum)
    sinir: set[int] = set()
    for eksen, deger in ((0, 0.0), (0, L), (1, 0.0), (1, b), (2, 0.0), (2, h)):
        sinir.update(yuz_dugumleri(m, eksen, deger))
    for nid in sorted(sinir):
        u = PATCH_U0 + PATCH_H @ m.node(nid).xyz
        m.bcs.extend(BC(nid, d, float(u[i])) for i, d in enumerate(("ux", "uy", "uz")))
    return m, sinir


@pytest.mark.parametrize("tohum", [0, 7])
def test_patch_interior_nodes_reproduce_linear_field(tohum):
    m, sinir = _patch_model(tohum)
    ic = [n for n in m.nodes if n.id not in sinir]
    assert len(ic) == 8
    assert any(abs(n.x - round(n.x / (2.0 / 3)) * (2.0 / 3)) > 1e-3 for n in ic)  # gerçekten kaydırılmış
    r = solve(m)
    for n in ic:
        beklenen = PATCH_U0 + PATCH_H @ n.xyz
        bulunan = [r.displacement(m, n.id, d) for d in ("ux", "uy", "uz")]
        np.testing.assert_allclose(bulunan, beklenen, rtol=0, atol=1e-10)


@pytest.mark.parametrize("tohum", [0, 7])
def test_patch_constant_stress_in_every_element(tohum):
    m, _ = _patch_model(tohum)
    r = solve(m)
    H = PATCH_H
    eps = np.array([H[0, 0], H[1, 1], H[2, 2], H[0, 1] + H[1, 0], H[0, 2] + H[2, 0], H[1, 2] + H[2, 1]])
    lam = STEEL_E * NU / ((1 + NU) * (1 - 2 * NU))
    G = STEEL_E / (2 * (1 + NU))
    s = np.concatenate([lam * eps[:3].sum() + 2 * G * eps[:3], G * eps[3:]])  # σ = D ε(H)
    sig = post.element_stress_tensors(m, r.u)
    assert set(sig) == {e.id for e in m.elements}
    for e in m.elements:
        np.testing.assert_allclose(sig[e.id], s, rtol=0, atol=1e-9 * np.abs(s).max())


@pytest.mark.parametrize("tohum", [0, 7])
def test_patch_equilibrium(tohum):
    m, _ = _patch_model(tohum)
    denge_kontrol(m, solve(m))


# --- K8: Tek eksenli çekme prizması ---------------------------------------------

CEKME_L, CEKME_b, CEKME_h, CEKME_SIGMA = 60.0, 20.0, 10.0, 120.0


def _cekme_model(nx: int, ny: int, nz: int, kaydirma: float) -> Model:
    """Simetri düzlemi mesnetleri (x=0: ux, y=0: uy, z=0: uz), x = L yüzünde düzgün çekme σ."""
    m = kutu_agi(CEKME_L, CEKME_b, CEKME_h, nx, ny, nz, celik(), kaydirma=kaydirma, tohum=3)
    sabitle(m, 0, 0.0, ("ux",))
    sabitle(m, 1, 0.0, ("uy",))
    sabitle(m, 2, 0.0, ("uz",))
    m.loads = yuzey_cekmesi(m, 0, CEKME_L, (CEKME_SIGMA, 0.0, 0.0))
    return m


CEKME_AGLARI = [(1, 1, 1, 0.0), (2, 1, 1, 0.0), (3, 2, 2, 0.0), (4, 3, 2, 0.2), (6, 2, 3, 0.15)]
CEKME_IDS = [f"{nx}x{ny}x{nz}{'_kaydirilmis' if a else ''}" for nx, ny, nz, a in CEKME_AGLARI]


@pytest.mark.parametrize(("nx", "ny", "nz", "kaydirma"), CEKME_AGLARI, ids=CEKME_IDS)
def test_tension_displacement_field_exact(nx, ny, nz, kaydirma):
    """u_x = σx/E, u_y = −νσy/E, u_z = −νσz/E her düğümde; u_x(L) = σL/E."""
    m = _cekme_model(nx, ny, nz, kaydirma)
    r = solve(m)
    s, E = CEKME_SIGMA, STEEL_E
    olcek = s * CEKME_L / E
    for n in m.nodes:
        beklenen = [s * n.x / E, -NU * s * n.y / E, -NU * s * n.z / E]
        bulunan = [r.displacement(m, n.id, d) for d in ("ux", "uy", "uz")]
        np.testing.assert_allclose(bulunan, beklenen, rtol=0, atol=1e-9 * olcek)
    for nid in yuz_dugumleri(m, 0, CEKME_L):
        assert r.displacement(m, nid, "ux") == pytest.approx(s * CEKME_L / E, rel=1e-9)


@pytest.mark.parametrize(("nx", "ny", "nz", "kaydirma"), CEKME_AGLARI, ids=CEKME_IDS)
def test_tension_uniform_stress(nx, ny, nz, kaydirma):
    """Her elemanda σ_xx = σ (rel 1e-9), diğer bileşenler ≤ 1e-9 σ."""
    m = _cekme_model(nx, ny, nz, kaydirma)
    r = solve(m)
    sig = post.element_stress_tensors(m, r.u)
    beklenen = np.array([CEKME_SIGMA, 0, 0, 0, 0, 0])
    for e in m.elements:
        np.testing.assert_allclose(sig[e.id], beklenen, rtol=0, atol=1e-9 * CEKME_SIGMA)
    assert r.element_forces == {} and r.element_stresses == {}


@pytest.mark.parametrize(("nx", "ny", "nz", "kaydirma"), CEKME_AGLARI[:3], ids=CEKME_IDS[:3])
def test_tension_equilibrium(nx, ny, nz, kaydirma):
    m = _cekme_model(nx, ny, nz, kaydirma)
    r = solve(m)
    denge_kontrol(m, r)
    # Uç yük toplamı = σ b h, x = 0 tepkisi bunun eksisi
    toplam = sum(ld.value for ld in m.loads if ld.dof == "ux")
    assert toplam == pytest.approx(CEKME_SIGMA * CEKME_b * CEKME_h, rel=1e-12)
    Rx = sum(r.reaction(m, n, "ux") for n in yuz_dugumleri(m, 0, 0.0))
    assert Rx == pytest.approx(-toplam, rel=1e-9)


# --- K10: Konsol kiriş yakınsaması -------------------------------------------------

KONSOL_L, KONSOL_b, KONSOL_h, KONSOL_P = 100.0, 10.0, 10.0, 1000.0


def delta_timoshenko() -> float:
    """δ_T = PL³/(3EI) + PL/(κGA), κ = 5/6."""
    E, G = STEEL_E, STEEL_E / (2 * (1 + NU))
    I = KONSOL_b * KONSOL_h**3 / 12.0  # noqa: E741
    A = KONSOL_b * KONSOL_h
    return KONSOL_P * KONSOL_L**3 / (3 * E * I) + KONSOL_P * KONSOL_L / (5.0 / 6.0 * G * A)


def _konsol_model(k: int) -> Model:
    """10k x k x k kutu ağı; x = 0 tamamen tutulu, x = L yüzünde −z yönünde düzgün kayma P."""
    m = kutu_agi(KONSOL_L, KONSOL_b, KONSOL_h, 10 * k, k, k, celik(), name=f"konsol_{k}")
    sabitle(m, 0, 0.0, ("ux", "uy", "uz"))
    m.loads = yuzey_cekmesi(m, 0, KONSOL_L, (0.0, 0.0, -KONSOL_P / (KONSOL_b * KONSOL_h)))
    return m


@functools.cache
def konsol(k: int) -> tuple[float, float]:
    """(δ_uç, W): δ_uç = serbest uç yüzündeki düğümlerin −u_z ortalaması, W = Fᵀ u."""
    m = _konsol_model(k)
    r = solve(m)
    denge_kontrol(m, r)
    uc = yuz_dugumleri(m, 0, KONSOL_L)
    delta = -float(np.mean([r.displacement(m, n, "uz") for n in uc]))
    W = float(kuvvet_vektoru(m) @ r.u)
    return delta, W


def test_cantilever_load_is_consistent():
    m = _konsol_model(2)
    assert sum(ld.value for ld in m.loads if ld.dof == "uz") == pytest.approx(-KONSOL_P, rel=1e-12)
    assert all(ld.dof == "uz" for ld in m.loads)


def test_cantilever_converges_from_below():
    """k = 1, 2, 4: W artar (iç içe ağ, alt sınır), δ_uç < δ_T, e_2 / e_4 ≥ 2."""
    dT = delta_timoshenko()
    sonuc = {k: konsol(k) for k in (1, 2, 4)}
    for k, (delta, _) in sonuc.items():
        assert 0.0 < delta < dT, f"k={k}: δ_uç/δ_T = {delta / dT:.3f}"
    assert sonuc[1][1] < sonuc[2][1] < sonuc[4][1]
    e = {k: 1.0 - sonuc[k][0] / dT for k in sonuc}
    assert e[2] / e[4] >= 2.0, f"e_2/e_4 = {e[2] / e[4]:.3f}"


@pytest.mark.slow
def test_cantilever_k8_accuracy():
    """k = 8: W(8) > W(4), δ_uç/δ_T ≥ 0.90, e_4/e_8 ≥ 2."""
    dT = delta_timoshenko()
    d4, W4 = konsol(4)
    d8, W8 = konsol(8)
    assert W8 > W4
    assert d8 < dT
    assert d8 / dT >= 0.90, f"δ_uç/δ_T = {d8 / dT:.3f}"
    e4, e8 = 1.0 - d4 / dT, 1.0 - d8 / dT
    assert e4 / e8 >= 2.0, f"e_4/e_8 = {e4 / e8:.3f}"


# --- K11: Mekanizma ------------------------------------------------------------------


def test_mechanism_single_fixed_node_raises():
    """Tek düğüm tamamen tutulu, dönmeler serbest: K_ff tekil -> ModelError."""
    m = kutu_agi(20.0, 10.0, 10.0, 2, 1, 1, celik())
    m.bcs = [BC(1, d, 0.0) for d in ("ux", "uy", "uz")]
    m.loads = yuzey_cekmesi(m, 0, 20.0, (0.0, 0.0, -1.0))
    with pytest.raises(ModelError):
        solve(m)


# --- K13: Örnek JSON -----------------------------------------------------------------


def test_example_json_tension_cube():
    """examples/11_tet4_cekme.json: K8 değerini verir (σ = ΣF_x / (b h), u_x(L) = σL/E)."""
    m = Model.from_json(ORNEK)
    assert m.dim == 3 and m.elements and all(e.type == "tet4" for e in m.elements)
    X = np.array([n.xyz for n in m.nodes])
    L, b, h = np.ptp(X, axis=0)
    E, nu = m.materials[0].E, m.materials[0].nu
    sigma = sum(ld.value for ld in m.loads if ld.dof == "ux") / (b * h)
    assert sigma > 0

    r = solve(m)
    for n in m.nodes:
        beklenen = [sigma * n.x / E, -nu * sigma * n.y / E, -nu * sigma * n.z / E]
        bulunan = [r.displacement(m, n.id, d) for d in ("ux", "uy", "uz")]
        np.testing.assert_allclose(bulunan, beklenen, rtol=0, atol=1e-9 * sigma * L / E)
    sig = post.element_stress_tensors(m, r.u)
    for e in m.elements:
        np.testing.assert_allclose(sig[e.id], [sigma, 0, 0, 0, 0, 0], rtol=0, atol=1e-9 * sigma)
    denge_kontrol(m, r)


def test_example_json_uses_tet4_volume():
    """Örnek küpün eleman hacimleri toplamı = L b h."""
    m = Model.from_json(ORNEK)
    X = np.array([n.xyz for n in m.nodes])
    L, b, h = np.ptp(X, axis=0)
    assert sum(tet4.volume(e, m) for e in m.elements) == pytest.approx(L * b * h, rel=1e-12)
