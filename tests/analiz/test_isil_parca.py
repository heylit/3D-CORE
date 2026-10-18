"""
SPEC 56 — kalın cidarlı silindirde ısı iletimi (K7, K8) ve parça köprüsü `analiz.parca_isil` (K11).

gmsh + build123d gerekir (`occt` işareti; gmsh yoksa importorskip ile atlanır). K11 ayrıca B2 malzeme modelini
(`malzeme.model.Malzeme`) ister; o birleşmeden atlanır.

Referans (Incropera 3.3), iç yarıçap a = 10'da T1 = 200, dış yarıçap b = 30'da T2 = 50,
uçlar yalıtılmış, Lz = 20, k = 50 mW/(mm·K):
    T(r) = T1 + (T2 − T1) ln(r/a) / ln(b/a)
    Q = 2π k Lz (T1 − T2) / ln(b/a) = 2π·50·20·150 / ln 3 = 857 880.6 mW   (iç yüzden giren)
"""

from __future__ import annotations

import functools
import math

import numpy as np
import pytest

import mesh
from core.isil import Temperature, ThermalResult, solve_thermal
from core.model import Material, Model, ModelError

pytestmark = [pytest.mark.occt, pytest.mark.slow]  # gmsh ağı + çözüm 10 s üstü olabilir

A_IC, B_DIS, LZ = 10.0, 30.0, 20.0
T1, T2, K = 200.0, 50.0, 50.0
Q_TAM = 2 * math.pi * K * LZ * (T1 - T2) / math.log(B_DIS / A_IC)
TOL_SECIM = 1e-5  # mm, eğri yüzey düğümleri


@pytest.fixture
def gmsh():
    return pytest.importorskip("gmsh", reason='gmsh kurulu değil (pip install -e ".[mesh]")')


def silindir_parcasi():
    import build123d as bd

    from geometry.part import Part

    hiza = (bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN)
    sekil = bd.Cylinder(B_DIS, LZ, align=hiza) - bd.Cylinder(A_IC, LZ, align=hiza)
    return Part(sekil, name="kalin_cidar")


def ic_yuz():
    return mesh.on_cylinder((0, 0, 0), (0, 0, 1), A_IC, tol=TOL_SECIM)


def dis_yuz():
    return mesh.on_cylinder((0, 0, 0), (0, 0, 1), B_DIS, tol=TOL_SECIM)


def T_analitik(r: np.ndarray) -> np.ndarray:
    return T1 + (T2 - T1) * np.log(r / A_IC) / math.log(B_DIS / A_IC)


@functools.cache
def silindir_cozumu(h_ag: float) -> tuple[Model, ThermalResult, list[int]]:
    m = mesh.tet_mesh(silindir_parcasi(), h_ag, Material("celik", 210_000.0, 0.3))
    ic = mesh.select_nodes(m, ic_yuz())
    dis = mesh.select_nodes(m, dis_yuz())
    assert ic and dis
    temps = [Temperature(n, T1) for n in ic] + [Temperature(n, T2) for n in dis]
    return m, solve_thermal(m, K, temperatures=temps), ic


def dugum_hatasi(m: Model, r: ThermalResult) -> float:
    X = np.array([m.node(int(n)).xyz for n in r.node_ids])
    return float(np.max(np.abs(r.T - T_analitik(np.hypot(X[:, 0], X[:, 1])))))


def ic_tepki(r: ThermalResult, ic: list[int]) -> float:
    secili = set(ic)
    return float(sum(Rn for nid, Rn in zip(r.node_ids, r.R, strict=True) if int(nid) in secili))


def test_hand_value():
    assert Q_TAM == pytest.approx(857_880.6, abs=0.5)


# --- K7: silindir -----------------------------------------------------------------------------


def test_k7_coarse_mesh(gmsh):
    m, r, ic = silindir_cozumu(3.0)
    assert dugum_hatasi(m, r) <= 0.02 * (T1 - T2)
    assert ic_tepki(r, ic) == pytest.approx(Q_TAM, rel=0.03)


@pytest.mark.slow
def test_k7_fine_mesh_halves_error(gmsh):
    m3, r3, _ = silindir_cozumu(3.0)
    m15, r15, ic15 = silindir_cozumu(1.5)
    assert dugum_hatasi(m15, r15) <= 0.5 * dugum_hatasi(m3, r3)
    assert ic_tepki(r15, ic15) == pytest.approx(Q_TAM, rel=0.01)


def test_k8_energy_balance_cylinder(gmsh):
    """K8: Σ R + Q_gen + Q_flux + Q_conv = 0; iç yüzden giren = dış yüzden çıkan."""
    _, r, _ = silindir_cozumu(3.0)
    terimler = [float(np.sum(r.R)), r.Q_gen, r.Q_flux, r.Q_conv]
    giren = sum(Rn for Rn in r.R if Rn > 0)
    assert giren == pytest.approx(Q_TAM, rel=0.03)
    assert abs(sum(terimler)) <= 1e-9 * giren
    assert r.Q_gen == 0.0 and r.Q_flux == 0.0 and r.Q_conv == 0.0


# --- K11: parça köprüsü -----------------------------------------------------------------------


def malzeme_kaydi(k: float | None):
    neden = "B2 malzeme modeli (malzeme/model.py) henüz main'de değil"
    mm = pytest.importorskip("malzeme.model", reason=neden)
    return mm.Malzeme(
        id="TEST-CELIK",
        name="Uydurma çelik",
        standart="",
        grup="celik",
        kaynak="test: uydurma değerler",
        E=210_000.0,
        nu=0.3,
        rho=7.85e-9,
        k=k,
    )


def test_k11_parca_isil_matches_core(gmsh):
    """`analiz.parca_isil` K7 silindirini Malzeme kaydıyla (k = 50) kurar ve aynı sonucu verir."""
    from analiz import parca_isil

    mlz = malzeme_kaydi(K)
    m, r = parca_isil(silindir_parcasi(), 3.0, mlz, sabit=[(ic_yuz(), T1), (dis_yuz(), T2)])
    assert isinstance(m, Model) and isinstance(r, ThermalResult)
    assert {e.material for e in m.elements} == {"TEST-CELIK"}
    assert dugum_hatasi(m, r) <= 0.02 * (T1 - T2)
    ic = mesh.select_nodes(m, ic_yuz())
    assert ic_tepki(r, ic) == pytest.approx(Q_TAM, rel=0.03)
    m0, r0, _ = silindir_cozumu(3.0)
    if len(m0.nodes) == len(m.nodes):  # gmsh tekrarlanabilir (SPEC 12 K4): aynı ağ, aynı sonuç
        np.testing.assert_allclose(r.T, r0.T, rtol=1e-9, atol=1e-9 * T1)


def test_k11_flux_and_convection_selectors(gmsh):
    """Akı ve taşınım seçicileri: iç yüzden q̄ girer, dış yüz taşınımla soğur; enerji dengesi tutar."""
    from analiz import parca_isil

    mlz = malzeme_kaydi(K)
    q_bar, h, T_inf = 0.5, 0.01, 20.0
    m, r = parca_isil(silindir_parcasi(), 3.0, mlz, aki=[(ic_yuz(), q_bar)], tasinim=[(dis_yuz(), h, T_inf)])
    A_ic = mesh.triangle_areas(m, mesh.select_triangles(m, ic_yuz())).sum()
    assert r.Q_flux == pytest.approx(q_bar * A_ic, rel=1e-9)
    assert r.Q_conv == pytest.approx(-r.Q_flux, rel=1e-9)
    assert np.all(r.T > T_inf)


def test_k11_generation(gmsh):
    """Q verilince Q_gen = Q · V_ağ ve tutulu yüzlerden çıkar."""
    from analiz import parca_isil

    mlz = malzeme_kaydi(K)
    m, r = parca_isil(silindir_parcasi(), 3.0, mlz, sabit=[(ic_yuz(), 0.0), (dis_yuz(), 0.0)], Q=0.01)
    V = 0.0
    for e in m.elements:
        X = np.array([m.node(i).xyz for i in e.nodes])
        V += abs(np.linalg.det(X[1:] - X[0])) / 6.0
    assert r.Q_gen == pytest.approx(0.01 * V, rel=1e-9)
    assert float(np.sum(r.R)) == pytest.approx(-r.Q_gen, rel=1e-9)


def test_k11_material_without_k_raises(gmsh):
    from analiz import parca_isil

    mlz = malzeme_kaydi(None)
    with pytest.raises(ModelError):
        parca_isil(silindir_parcasi(), 3.0, mlz, sabit=[(ic_yuz(), T1), (dis_yuz(), T2)])


def test_k11_empty_selector_raises(gmsh):
    """Seçici hiçbir şey bulamazsa ModelError."""
    from analiz import parca_isil

    mlz = malzeme_kaydi(K)
    bos = mesh.on_plane((0, 0, 1000.0), (0, 0, 1))
    with pytest.raises(ModelError):
        parca_isil(silindir_parcasi(), 3.0, mlz, sabit=[(ic_yuz(), T1), (bos, T2)])
    with pytest.raises(ModelError):
        parca_isil(silindir_parcasi(), 3.0, mlz, sabit=[(ic_yuz(), T1)], aki=[(bos, 1.0)])
