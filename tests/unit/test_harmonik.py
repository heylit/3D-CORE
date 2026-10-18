"""SPEC 68c — core/harmonik.py birim testleri (K1, K3, K7, K8 ve FRF erişimcileri).

Testler yalnız SPEC 68c metninden ve iskeletin arayüzünden yazıldı; uygulama kodu okunmadı.
Referanslar:
- Statik sınır: core.solver.solve (SPEC 01/11, ayrı doğrulanmış) — ω → 0'da U = K⁻¹F.
- Rayleigh: ζ(ω) = α/(2ω) + βω/2; iki frekansta ζ veren kapalı form α = 2ζω₁ω₂/(ω₁+ω₂),
  β = 2ζ/(ω₁+ω₂) (Chopra, Dynamics of Structures, 11.4).
- Modal ↔ doğrudan eşdeğerliği: Rayleigh sönümü M- ve K-dik olduğundan tüm modlarla modal toplam
  (K − ω²M + iω(αM + βK))⁻¹F'ye tam eşittir; mod başına ζ_r = α/(2ω_r) + βω_r/2.
- Öz frekanslar core.modal.modal'dan (SPEC 45, ayrı doğrulanmış).
Birimler N – mm – t – s, frekans Hz.
"""

from __future__ import annotations

import ast
import math
import sys
from pathlib import Path

import numpy as np
import pytest

from core.harmonik import FRF, harmonic_direct, harmonic_modal, rayleigh_from_zeta
from core.modal import modal
from core.model import BC, Element, Load, Material, Model, ModelError, Node, Section
from core.solver import solve
from tests.benchmarks.tet_ag import kutu_agi, yuz_dugumleri

E, NU, RHO = 210_000.0, 0.3, 7.85e-9


def celik(rho: float = RHO) -> Material:
    return Material("celik", E, NU, rho)


def cubuk(N: int = 20, L: float = 1000.0, A: float = 100.0, F: float = 1000.0, rho: float = RHO) -> Model:
    """Ankastre (x = 0) – serbest bar1d çubuk, uçta eksenel F."""
    return Model(
        dim=1,
        nodes=[Node(i + 1, L * i / N) for i in range(N + 1)],
        elements=[Element(i + 1, "bar1d", [i + 1, i + 2], "celik", "s") for i in range(N)],
        materials=[celik(rho)],
        sections=[Section("s", A)],
        bcs=[BC(1, "ux")],
        loads=[Load(N + 1, "ux", F)],
    )


def konsol(rho: float = RHO) -> Model:
    """Kuhn tet4 konsolu 100 × 10 × 10, 10 × 2 × 2 hücre; x = 0 ankastre, uç yüz merkezinde Fz ve Fy."""
    m = kutu_agi(100.0, 10.0, 10.0, 10, 2, 2, celik(rho), name="harmonik_konsol")
    for n in yuz_dugumleri(m, 0, 0.0):
        m.bcs.extend(BC(n, d) for d in ("ux", "uy", "uz"))
    uc = yuz_dugumleri(m, 0, 100.0)
    m.loads = [Load(uc[4], "uz", 10.0), Load(uc[4], "uy", 4.0)]
    return m


def serbest_sayisi(m: Model) -> int:
    return m.n_dof - len({m.dof_index(b.node, b.dof) for b in m.bcs})


def goreli(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.linalg.norm(a - b) / np.linalg.norm(b))


MODELLER = [pytest.param(cubuk, id="cubuk"), pytest.param(konsol, id="tet4-konsol")]

# --- FRF erişimcileri -----------------------------------------------------------------------------


def test_frf_nokta_genlik_faz():
    m = cubuk(N=2)  # 3 DOF
    U = np.array(
        [
            [0.0, 2.0 + 0.0j, 0.0],
            [0.0, -3.0 + 0.0j, 1.0j],
            [0.0, 1.0 - 1.0j, -1.0j],
            [0.0, -1.0 + 1.0j, -2.0 + 1e-14j],
        ]
    )
    r = FRF(f=np.array([1.0, 2.0, 3.0, 4.0]), U=U)
    i = m.dof_index(2, "ux")
    np.testing.assert_array_equal(r.nokta(m, 2, "ux"), U[:, i])
    np.testing.assert_allclose(r.genlik(m, 2, "ux"), [2.0, 3.0, math.sqrt(2), math.sqrt(2)], rtol=1e-15)
    np.testing.assert_allclose(r.faz(m, 2, "ux"), [0.0, 180.0, -45.0, 135.0], atol=1e-12)
    np.testing.assert_allclose(r.faz(m, 3, "ux"), [0.0, 90.0, -90.0, 180.0], atol=1e-9)
    faz = r.faz(m, 2, "ux")
    assert np.all((faz > -180.0) & (faz <= 180.0))


# --- K1 -------------------------------------------------------------------------------------------


@pytest.mark.parametrize("n_modes", [1, 3, 10])
@pytest.mark.parametrize("make", MODELLER)
def test_k1_statik_sinir_kalinti_acik(make, n_modes):
    m = make()
    u = solve(m).u
    r = harmonic_modal(m, [1e-6], zeta=0.02, n_modes=n_modes, residual=True)
    assert r.U.shape == (1, m.n_dof)
    np.testing.assert_allclose(r.f, [1e-6])
    assert goreli(r.U[0].real, u) <= 1e-9
    assert np.linalg.norm(r.U[0].imag) <= 1e-9 * np.linalg.norm(u)


@pytest.mark.parametrize("make", MODELLER)
def test_k1_kalinti_kapali_az_mod_farkli(make):
    """Kalıntı esneklik olmadan tek mod statik çözümü tutturamaz: göreli fark > 1e-3."""
    m = make()
    u = solve(m).u
    r = harmonic_modal(m, [1e-6], zeta=0.02, n_modes=1, residual=False)
    fark = goreli(r.U[0], u)
    assert fark > 1e-3, fark


# --- K3 -------------------------------------------------------------------------------------------


def test_k3_rayleigh_from_zeta():
    for f1, f2, z in [(100.0, 1000.0, 0.02), (1323.7, 8547.6, 0.05), (5.0, 7.0, 0.01)]:
        a, b = rayleigh_from_zeta(f1, f2, z)
        w1, w2 = 2 * math.pi * f1, 2 * math.pi * f2
        for w in (w1, w2):
            assert a / (2 * w) + b * w / 2 == pytest.approx(z, rel=1e-12)
        assert a == pytest.approx(2 * z * w1 * w2 / (w1 + w2), rel=1e-12)
        assert b == pytest.approx(2 * z / (w1 + w2), rel=1e-12)


@pytest.mark.slow
def test_k3_modal_dogrudan_esdeger():
    """Tüm modlar, Rayleigh sönümünün mod başına ζ_r'si, kalıntı kapalı ↔ doğrudan: 30 frekansta 1e-8."""
    m = konsol()
    n_f = serbest_sayisi(m)
    md = modal(m, n_f)
    f = md.f
    alpha, beta = rayleigh_from_zeta(float(f[0]), float(f[-1]), 0.02)
    zeta_r = alpha / (2 * md.omega) + beta * md.omega / 2
    assert np.all((zeta_r > 0) & (zeta_r <= 0.02 + 1e-12))  # ζ(ω) iki frekans arasında ≤ ζ
    fs = np.linspace(0.2 * f[0], 1.3 * f[9], 30)
    rm = harmonic_modal(m, fs, zeta=list(zeta_r), n_modes=n_f, residual=False)
    rd = harmonic_direct(m, fs, alpha=alpha, beta=beta)
    np.testing.assert_allclose(rm.f, fs)
    np.testing.assert_allclose(rd.f, fs)
    for k in range(len(fs)):
        assert goreli(rm.U[k], rd.U[k]) <= 1e-8, fs[k]


def test_k3_dogrudan_kendi_cozumu():
    """Küçük çubukta doğrudan yol testin kendi yoğun (K − ω²M + iωC)⁻¹F çözümüyle (Rayleigh)."""
    from core.assembly import assemble_F, assemble_K, assemble_M

    m = cubuk(N=8)
    serbest = np.flatnonzero(~np.isin(np.arange(m.n_dof), [m.dof_index(b.node, b.dof) for b in m.bcs]))
    K = assemble_K(m).toarray()[np.ix_(serbest, serbest)]
    M = assemble_M(m).toarray()[np.ix_(serbest, serbest)]
    F = assemble_F(m)[serbest]
    alpha, beta = 30.0, 2e-6
    fs = [100.0, 900.0, 1300.0, 2500.0]
    r = harmonic_direct(m, fs, alpha=alpha, beta=beta)
    for k, fk in enumerate(fs):
        w = 2 * math.pi * fk
        U = np.linalg.solve(K - w * w * M + 1j * w * (alpha * M + beta * K), F)
        assert goreli(r.U[k][serbest], U) <= 1e-10
        assert np.all(r.U[k][[m.dof_index(b.node, b.dof) for b in m.bcs]] == 0)


# --- K7 -------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "kw",
    [
        pytest.param({"zeta": None}, id="zeta-yok"),
        pytest.param({"zeta": 1.0}, id="zeta=1"),
        pytest.param({"zeta": 0.0}, id="zeta=0"),
        pytest.param({"zeta": -0.01}, id="zeta<0"),
        pytest.param({"zeta": [0.02, 0.02]}, id="zeta-uzunluk"),  # n_modes = 3
        pytest.param({"zeta": [0.02, 1.0, 0.02]}, id="zeta-mod-1"),
        pytest.param({"f": [-10.0]}, id="f<0"),
        pytest.param({"f": []}, id="f-bos"),
        pytest.param({"n_modes": 0}, id="n_modes=0"),
        pytest.param({"n_modes": -2}, id="n_modes<0"),
        pytest.param({"n_modes": 21}, id="n_modes>n_f"),  # 20 elemanlı çubuk: 20 serbest DOF
    ],
)
def test_k7_modal_hatali(kw):
    p = {"f": [100.0, 500.0], "zeta": 0.02, "n_modes": 3}
    p.update(kw)
    with pytest.raises(ModelError):
        harmonic_modal(cubuk(), p.pop("f"), **p)


def test_k7_yuk_yok():
    m = cubuk()
    m.loads = []
    with pytest.raises(ModelError):
        harmonic_modal(m, [100.0], zeta=0.02, n_modes=3)
    with pytest.raises(ModelError):
        harmonic_direct(m, [100.0], alpha=1.0)


@pytest.mark.parametrize("rho", [0.0, -1e-9])
def test_k7_yogunluk(rho):
    m = cubuk(rho=rho)
    with pytest.raises(ModelError):
        harmonic_modal(m, [100.0], zeta=0.02, n_modes=3)
    with pytest.raises(ModelError):
        harmonic_direct(m, [100.0], alpha=1.0)


@pytest.mark.parametrize("f", [[-10.0], [], [100.0, -1.0]])
def test_k7_dogrudan_frekans(f):
    with pytest.raises(ModelError):
        harmonic_direct(cubuk(), f, alpha=1.0)


def test_k7_dogrudan_sonumsuz_tam_rezonans():
    """Tek elemanlı çubuk (1 serbest DOF): K = EA/L, M = ρAL/3 (tutarlı) → ω² = 3E/(ρL²)."""
    L = 500.0
    m = cubuk(N=1, L=L)
    f_r = math.sqrt(3 * E / (RHO * L * L)) / (2 * math.pi)
    with pytest.raises(ModelError):
        harmonic_direct(m, [f_r])
    harmonic_direct(m, [0.5 * f_r])  # rezonans dışında sönümsüz çözüm geçerli
    harmonic_direct(m, [f_r], alpha=10.0)  # sönümlü rezonans tekil değil


# --- K8 -------------------------------------------------------------------------------------------


def test_k8_bagimliliklar():
    """core/harmonik.py yalnız numpy, scipy, core ve standart kütüphaneyi import eder."""
    yol = Path(__file__).resolve().parents[2] / "core" / "harmonik.py"
    agac = ast.parse(yol.read_text(encoding="utf-8"))
    kokler = set()
    for d in ast.walk(agac):
        if isinstance(d, ast.Import):
            kokler |= {a.name.split(".")[0] for a in d.names}
        elif isinstance(d, ast.ImportFrom) and d.level == 0:
            kokler.add(d.module.split(".")[0])
    izinli = {"numpy", "scipy", "core", "__future__"} | set(sys.stdlib_module_names)
    assert kokler <= izinli, kokler - izinli
