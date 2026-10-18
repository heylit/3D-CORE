"""SPEC 68d K4, K5, K6, K8 (model kısmı) — düğüm gerilmesinden genlik/ortalama, Goodman ve ömür (Kuhn ağıyla).

Testler yalnız specs/68d-yorulma.md metninden ve analiz/yorulma.py arayüzünden yazıldı;
fonksiyon gövdeleri okunmadı.
Ağ SPEC 11 Kuhn kutusu (tests/benchmarks/tet_ag.py); gmsh / OCCT gerekmez.

K4 ve K6'da yer değiştirme doğrusal bir alandan doğrudan yazılır (u = ε·x): tet4 doğrusal alanı tam
taşır, her düğüm gerilmesi aynı σ'dır (SPEC 13 K4). Gerinme Hooke'un tersinden: ε = [(1 + ν)σ − ν·iz(σ)·I]/E.
K5'te çubuk çözülür (statik belirli mesnet: x = 0 yüzünde ux, köşelerde rijit gövde) → her yerde σxx = F/A.
"""

from __future__ import annotations

import functools
import math

import numpy as np
import pytest

from analiz.yorulma import Marin, Yorulma, dayanim_siniri, goodman, omur, yorulma
from core.model import BC, Material, Model
from core.solver import solve
from tests.analiz.yorulma_ref import HATALAR, NU, RM, RP02, E, N_kapali, celik, nf_kapali
from tests.benchmarks.tet_ag import kutu_agi, yuzey_cekmesi

L, B, H = 100.0, 10.0, 10.0
A_KESIT = B * H
F_YUK = 15_000.0  # N → σ = 150 MPa
G = E / (2 * (1 + NU))


def fem_malzemesi() -> Material:
    return Material("TEST-CELIK", E, NU, 7.85e-9)


@functools.cache
def _kutu() -> Model:
    return kutu_agi(L, B, H, 10, 2, 2, fem_malzemesi(), name="yorulma_kutu")


def _u(model: Model, eps: np.ndarray) -> np.ndarray:
    """Doğrusal alan u = ε·x global DOF sırasında (ε simetrik 3×3)."""
    u = np.zeros(model.n_dof)
    for n in model.nodes:
        d = eps @ np.asarray(n.xyz, dtype=float)
        for i, ad in enumerate(("ux", "uy", "uz")):
            u[model.dof_index(n.id, ad)] = d[i]
    return u


def _gerinme(S: np.ndarray) -> np.ndarray:
    return ((1 + NU) * S - NU * np.trace(S) * np.eye(3)) / E


def _alan(S) -> np.ndarray:
    return _u(_kutu(), _gerinme(np.asarray(S, dtype=float)))


def _vm(S: np.ndarray) -> float:
    d = S - np.trace(S) / 3 * np.eye(3)
    return math.sqrt(1.5 * np.sum(d * d))


# ------------------------------------------------------------------ K4 çok eksenli dönüşüm


def test_k4_eksenel_R_eksi_1():
    y = yorulma(_kutu(), _alan(np.diag([300.0, 0, 0])), R=-1.0, malzeme=celik())
    n = len(_kutu().nodes)
    assert y.sigma_a.shape == (n,) and y.sigma_m.shape == (n,)
    np.testing.assert_allclose(y.sigma_a, 300.0, rtol=1e-9)
    np.testing.assert_allclose(y.sigma_m, 0.0, atol=1e-9 * 300.0)


def test_k4_eksenel_R_sifir():
    y = yorulma(_kutu(), _alan(np.diag([300.0, 0, 0])), R=0.0, malzeme=celik())
    np.testing.assert_allclose(y.sigma_a, 150.0, rtol=1e-9)
    np.testing.assert_allclose(y.sigma_m, 150.0, rtol=1e-9)


def test_k4_saf_kayma():
    tau = 80.0
    S = np.array([[0, tau, 0], [tau, 0, 0], [0, 0, 0]])
    y = yorulma(_kutu(), _alan(S), R=-1.0, malzeme=celik())
    np.testing.assert_allclose(y.sigma_a, math.sqrt(3) * tau, rtol=1e-9)
    np.testing.assert_allclose(y.sigma_m, 0.0, atol=1e-9 * tau)


def test_k4_basma_ortalamasi_isaretli():
    # S_A = diag(−300), R = 0 → S_m = diag(−150): iz < 0 → σm = −150
    y = yorulma(_kutu(), _alan(np.diag([-300.0, 0, 0])), R=0.0, malzeme=celik())
    np.testing.assert_allclose(y.sigma_a, 150.0, rtol=1e-9)
    np.testing.assert_allclose(y.sigma_m, -150.0, rtol=1e-9)
    Se = y.Se
    np.testing.assert_allclose(y.n_f, Se / 150.0, rtol=1e-9)  # basma ortalaması yararına sayılmaz


def test_k4_iki_yuk_durumu_cok_eksenli():
    # Genel tensörler: S_a = (S_A − S_B)/2, S_m = (S_A + S_B)/2, σm = sign(iz S_m)·σvM(S_m)
    S_A = np.array([[120.0, 30.0, -10.0], [30.0, -40.0, 20.0], [-10.0, 20.0, 60.0]])
    S_B = np.array([[-50.0, 10.0, 5.0], [10.0, 25.0, -15.0], [5.0, -15.0, -20.0]])
    y = yorulma(_kutu(), _alan(S_A), _alan(S_B), malzeme=celik())
    Sa, Sm = (S_A - S_B) / 2, (S_A + S_B) / 2
    np.testing.assert_allclose(y.sigma_a, _vm(Sa), rtol=1e-9)
    np.testing.assert_allclose(y.sigma_m, np.sign(np.trace(Sm)) * _vm(Sm), rtol=1e-9)


def test_k4_sonuc_alanlari():
    model = _kutu()
    marin = Marin(yuzey="islenmis")
    mat = celik()
    y = yorulma(model, _alan(np.diag([250.0, 0, 0])), R=0.0, malzeme=mat, marin=marin)
    assert isinstance(y, Yorulma)
    Se = dayanim_siniri(mat, marin)
    assert y.Se == pytest.approx(Se, rel=1e-12)
    assert dict(y.katsayilar) == pytest.approx(marin.katsayilar(RM), rel=1e-12)
    sa, sm = 125.0, 125.0
    np.testing.assert_allclose(y.n_f, np.asarray(goodman(sa, sm, Se, RM), dtype=float), rtol=1e-9)
    np.testing.assert_allclose(y.n_y, RP02 / (sa + abs(sm)), rtol=1e-9)  # Langer
    N = np.asarray(omur(sa, sm, Se, RM), dtype=float)
    if np.isinf(N):
        assert np.all(np.isinf(y.N))
    else:
        np.testing.assert_allclose(y.N, N, rtol=1e-9)
    assert y.dusuk_cevrim.dtype == bool and not y.dusuk_cevrim.any()
    assert y.n_f_min == pytest.approx(float(np.min(y.n_f)), rel=1e-12)
    assert y.N_min == float(np.min(y.N))
    ids = [n.id for n in model.nodes]
    assert y.dugum in ids
    i = ids.index(y.dugum)
    assert y.n_f[i] == pytest.approx(y.n_f_min, rel=1e-12)
    np.testing.assert_allclose(y.konum, model.node(y.dugum).xyz, atol=1e-12)
    assert "ön değerlendirme" in y.not_
    assert "kb" in y.not_  # d verilmedi → kb = 1 uyarısı


def test_k4_yuksuz():
    y = yorulma(_kutu(), np.zeros(_kutu().n_dof), R=-1.0, malzeme=celik())
    assert np.all(np.isinf(y.n_f)) and np.all(np.isinf(y.N))
    assert math.isinf(y.n_f_min) and math.isinf(y.N_min)


# ------------------------------------------------------------------ K5 FEM ile


@functools.cache
def _cubuk() -> Model:
    m = kutu_agi(L, B, H, 20, 2, 2, fem_malzemesi(), name="yorulma_cubuk")
    for n in m.nodes:
        x, y, z = n.xyz
        if abs(x) < 1e-12:
            m.bcs.append(BC(n.id, "ux"))
            if abs(y) < 1e-12 and abs(z) < 1e-12:
                m.bcs.extend([BC(n.id, "uy"), BC(n.id, "uz")])
            elif abs(y - B) < 1e-12 and abs(z) < 1e-12:
                m.bcs.append(BC(n.id, "uz"))
    return m


@functools.cache
def _cubuk_u(F: float) -> np.ndarray:
    import copy

    m = copy.deepcopy(_cubuk())
    m.loads.extend(yuzey_cekmesi(m, 0, L, (F / A_KESIT, 0.0, 0.0)))
    return solve(m).u


def _orta_maske(m: Model) -> np.ndarray:
    return np.array([B <= n.xyz[0] <= L - B for n in m.nodes])


MARIN_K5 = Marin(yuzey="dovme")  # Se ≈ 140 < 150 → sonlu ömür


def test_k5_cubuk_genlik_ortalama():
    m = _cubuk()
    y = yorulma(m, _cubuk_u(F_YUK), _cubuk_u(-F_YUK), malzeme=celik(), marin=MARIN_K5)
    o = _orta_maske(m)
    assert o.sum() > 0
    np.testing.assert_allclose(y.sigma_a[o], 150.0, rtol=1e-9)
    np.testing.assert_allclose(y.sigma_m[o], 0.0, atol=1e-9 * 150.0)
    Se = dayanim_siniri(celik(), MARIN_K5)
    np.testing.assert_allclose(y.n_f[o], Se / 150.0, rtol=1e-9)
    np.testing.assert_allclose(y.N[o], N_kapali(150.0, 0.0, Se, RM), rtol=1e-9)
    np.testing.assert_allclose(y.N[o], float(np.asarray(omur(150.0, 0.0, Se, RM), dtype=float)), rtol=1e-9)
    np.testing.assert_allclose(y.n_f[o], nf_kapali(150.0, 0.0, Se, RM), rtol=1e-9)


def test_k5_R_ile_tek_yuk_ayni():
    m = _cubuk()
    a = yorulma(m, _cubuk_u(F_YUK), _cubuk_u(-F_YUK), malzeme=celik(), marin=MARIN_K5)
    b = yorulma(m, _cubuk_u(F_YUK), R=-1.0, malzeme=celik(), marin=MARIN_K5)
    for alan in ("sigma_a", "sigma_m", "n_f", "n_y", "N"):
        np.testing.assert_allclose(getattr(b, alan), getattr(a, alan), rtol=1e-9, atol=1e-9, err_msg=alan)
    assert b.n_f_min == pytest.approx(a.n_f_min, rel=1e-9)


# ------------------------------------------------------------------ K6 düşük çevrim


def test_k6_dusuk_cevrim():
    # σa = 560 > 0.9·Rm = 540, R = −1 → σar = 560
    y = yorulma(_kutu(), _alan(np.diag([560.0, 0, 0])), R=-1.0, malzeme=celik())
    assert y.dusuk_cevrim.dtype == bool
    assert np.all(y.dusuk_cevrim)
    assert np.all(y.n_f < 1)
    assert not np.any(np.isnan(y.N))
    assert np.all(y.N > 0) and np.all(y.N <= 1e3 * (1 + 1e-12))
    assert "düşük çevrim, kapsam dışı" in y.not_


def test_k6_yuksek_cevrim_isaretlenmez():
    y = yorulma(_kutu(), _alan(np.diag([300.0, 0, 0])), R=-1.0, malzeme=celik())
    assert not y.dusuk_cevrim.any()


# ------------------------------------------------------------------ K8 hatalar (model)


def test_k8_hem_u_B_hem_R():
    u = _alan(np.diag([100.0, 0, 0]))
    with pytest.raises(HATALAR):
        yorulma(_kutu(), u, u, R=-1.0, malzeme=celik())


def test_k8_ne_u_B_ne_R():
    with pytest.raises(HATALAR):
        yorulma(_kutu(), _alan(np.diag([100.0, 0, 0])), malzeme=celik())


@pytest.mark.parametrize("R", [1.0, 1.5, -1.01, -2.0, math.nan])
def test_k8_R_aralik_disi(R):
    with pytest.raises(HATALAR):
        yorulma(_kutu(), _alan(np.diag([100.0, 0, 0])), R=R, malzeme=celik())


def test_k8_u_boyu_uyusmuyor():
    u = _alan(np.diag([100.0, 0, 0]))
    with pytest.raises(HATALAR):
        yorulma(_kutu(), u[:-3], R=-1.0, malzeme=celik())
    with pytest.raises(HATALAR):
        yorulma(_kutu(), u, u[:-1], malzeme=celik())


def test_k8_rm_eksik():
    with pytest.raises(HATALAR):
        yorulma(_kutu(), _alan(np.diag([100.0, 0, 0])), R=-1.0, malzeme=celik(Rm=None))


def test_k8_guvenilirlik_95():
    with pytest.raises(HATALAR):
        yorulma(_kutu(), _alan(np.diag([100.0, 0, 0])), R=-1.0, malzeme=celik(), marin=Marin(guvenilirlik=95))
