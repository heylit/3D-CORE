"""SPEC 68c — ankastre–serbest eksenel çubuğun frekans tepkisi (K2, K4).

Testler yalnız SPEC 68c metninden yazıldı; uygulama kodu okunmadı. Kapalı form (sönümsüz):
    U(L) = F tan(βL) / (E A β),   β = ω √(ρ/E),   ω → 0: F L / (E A)
Rezonans βL = (2n − 1)π/2; βL = π/4'te U/U_statik = tan(π/4)/(π/4) = 1.27324.
Çelik, L = 1000, A = 100: f₁ = c/(4L) = 1293.05 Hz. Birinci modun uç statik esnekliğe katkısı 8/π²,
ζ = 0.02 ile rezonansta |U| ≈ (8/π²)/(2ζ) · U_statik = 20.26 U_statik (diğer modlar ±%1).
Tek serbestlikli sistemde genlik tepesi ω_r √(1 − 2ζ²)'dedir.
Kaynak: Rao, Mechanical Vibrations (eksenel çubuk); Ewins, Modal Testing, bölüm 2.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from core.harmonik import harmonic_direct, harmonic_modal
from core.model import BC, Element, Load, Material, Model, Node, Section

E, NU, RHO = 210_000.0, 0.3, 7.85e-9
L, A, F, N = 1000.0, 100.0, 1000.0, 200
C = math.sqrt(E / RHO)  # mm/s
U_ST = F * L / (E * A)


def cubuk() -> Model:
    return Model(
        dim=1,
        nodes=[Node(i + 1, L * i / N) for i in range(N + 1)],
        elements=[Element(i + 1, "bar1d", [i + 1, i + 2], "celik", "s") for i in range(N)],
        materials=[Material("celik", E, NU, RHO)],
        sections=[Section("s", A)],
        bcs=[BC(1, "ux")],
        loads=[Load(N + 1, "ux", F)],
    )


def f_of_betaL(bL: np.ndarray) -> np.ndarray:
    """βL → f [Hz]: ω = β c."""
    return np.asarray(bL) / L * C / (2 * math.pi)


def kapali(bL: np.ndarray) -> np.ndarray:
    bL = np.asarray(bL)
    return F * np.tan(bL) / (E * A * bL / L)


def test_sabitler():
    assert C / (4 * L) == pytest.approx(1293.05, abs=0.01)
    assert math.tan(math.pi / 4) / (math.pi / 4) == pytest.approx(1.27324, abs=1e-5)
    assert (8 / math.pi**2) / (2 * 0.02) == pytest.approx(20.26, abs=0.005)


def _yollar():
    """K2 iki yolla: modal (ζ = 1e-6, 50 mod, kalıntı açık) ve sönümsüz doğrudan."""
    m = cubuk()
    return m, [
        lambda f: harmonic_modal(m, f, zeta=1e-6, n_modes=50, residual=True),
        lambda f: harmonic_direct(m, f),
    ]


@pytest.mark.parametrize("yol", [0, 1], ids=["modal", "dogrudan"])
def test_k2_pi_bolu_4(yol):
    m, yollar = _yollar()
    r = yollar[yol](f_of_betaL([math.pi / 4]))
    oran = r.nokta(m, N + 1, "ux")[0].real / U_ST
    assert oran == pytest.approx(1.27324, rel=1e-3)


@pytest.mark.parametrize("yol", [0, 1], ids=["modal", "dogrudan"])
def test_k2_kapali_form_20_frekans(yol):
    m, yollar = _yollar()
    bL = np.linspace(0.1, 1.4, 20)
    r = yollar[yol](f_of_betaL(bL))
    U = r.nokta(m, N + 1, "ux")
    np.testing.assert_allclose(U.real, kapali(bL), rtol=5e-3, atol=0)
    assert np.all(np.abs(U.imag) <= 1e-3 * np.abs(U.real))


@pytest.mark.parametrize("yol", [0, 1], ids=["modal", "dogrudan"])
def test_k2_faz(yol):
    """Birinci rezonansın altında faz 0°, üstünde (βL ∈ (π/2, 3π/2)) ±180°."""
    m, yollar = _yollar()
    alt = np.array([0.3, 0.9, 1.4])
    ust = np.array([1.75, 2.5, 3.5, 4.5])
    r = yollar[yol](f_of_betaL(np.concatenate([alt, ust])))
    faz = r.faz(m, N + 1, "ux")
    np.testing.assert_allclose(faz[:3], 0.0, atol=0.01)
    np.testing.assert_allclose(np.abs(faz[3:]), 180.0, atol=0.01)
    np.testing.assert_allclose(
        r.genlik(m, N + 1, "ux"), np.abs(kapali(np.concatenate([alt, ust]))), rtol=2e-2
    )


def test_k4_rezonans_genligi_ve_tepe():
    m = cubuk()
    zeta = 0.02
    f1 = C / (4 * L)
    r = harmonic_modal(m, [f1], zeta=zeta, n_modes=10, residual=True)
    assert r.genlik(m, N + 1, "ux")[0] / U_ST == pytest.approx(20.26, rel=1e-2)
    # Tepe: f₁√(1 − 2ζ²) merkezli, aralığı 1e-3 f₁ olan ızgarada en büyük genlik o noktada
    fp = f1 * math.sqrt(1 - 2 * zeta**2)
    izgara = fp * (1 + 1e-3 * np.arange(-20, 21))
    g = harmonic_modal(m, izgara, zeta=zeta, n_modes=10, residual=True).genlik(m, N + 1, "ux")
    assert int(np.argmax(g)) == int(np.argmin(np.abs(izgara - fp)))
