"""SPEC 71 testleri için bağımsız chatter referans hesabı (cam.chatter / cam.frf kullanılmaz).

Bu modül test değildir (adı test_ ile başlamaz). Sadece numpy ve SPEC 71 "Teori" formülleri:
- SDOF FRF: g(f) = 1 / (k (1 − r² + 2iζr)),  r = f / f_n  [mm/N]
- Tornalama (Tlusty): a = −1 / (2 K_s u Re g),  Re g < 0;  ε = 3π + 2 atan(Re g / Im g),
  n = 60 f_c / (k + ε/2π)
- Frezeleme (Altintas–Budak, sıfırıncı mertebe), izotrop G = g·I: Φ = [α] g, özdeğer λ = μ g (μ, [α]'nın
  özdeğeri); Λ = −1/λ, κ = Λ_I/Λ_R, a = −2π Λ_R (1 + κ²) / (N K_t), ε = π − 2 atan κ,
  T = (ε + 2kπ)/ω_c, n = 60 / (N T); yalnız a > 0.
- Yönsel katsayılar: SPEC'teki dört ifade, φ_st'den φ_ex'e (üst sınır − alt sınır).

Bir lob noktası (n, a) verildiğinde `match_rel` aynı lob numarası k için n'yi veren bütün f_c köklerini
(yoğun örnekleme + ikiye bölme, analitik g ile) bulur, a'ya en yakın referans değerin göreli farkını verir:
böylece kodun hangi frekans ızgarasını taradığından bağımsız, noktasal bir denetim yapılır.
"""

from __future__ import annotations

import math
from collections.abc import Callable

import numpy as np

TWO_PI = 2.0 * math.pi


def sdof_g(f, fn: float, zeta: float, k: float):
    """SDOF FRF [mm/N] (skaler veya dizi)."""
    r = np.asarray(f, dtype=float) / fn
    return 1.0 / (k * (1.0 - r**2 + 2j * zeta * r))


def alpha(phi_st: float, phi_ex: float, K_r: float) -> np.ndarray:
    """SPEC 71 yönsel katsayıları [[α_xx, α_xy], [α_yx, α_yy]], φ_st'den φ_ex'e."""

    def F(p: float) -> np.ndarray:
        c2, s2 = math.cos(2 * p), math.sin(2 * p)
        return 0.5 * np.array(
            [
                [c2 - 2 * K_r * p + K_r * s2, -s2 - 2 * p + K_r * c2],
                [-s2 + 2 * p + K_r * c2, -c2 - 2 * K_r * p - K_r * s2],
            ]
        )

    return F(phi_ex) - F(phi_st)


# ---------------------------------------------------------------- tornalama


def torna_n_a(f, g_fun: Callable, K_s: float, k: int, u: float = 1.0):
    """(n, a) tornalama lobu k için; Re g ≥ 0 olan frekanslarda a = nan."""
    G = u * g_fun(f)
    with np.errstate(divide="ignore", invalid="ignore"):
        a = np.where(G.real < 0, -1.0 / (2.0 * K_s * G.real), np.nan)
        eps = 3 * math.pi + 2 * np.arctan(G.real / G.imag)
    n = 60.0 * np.asarray(f, dtype=float) / (k + eps / TWO_PI)
    return n, a


# ---------------------------------------------------------------- frezeleme


def freze_n_a(f, g_fun: Callable, mu: complex, N: int, K_t: float, k: int):
    """(n, a) frezeleme lobu k, özdeğer ailesi λ = μ g için; a ≤ 0 olan frekanslarda a = nan."""
    f = np.asarray(f, dtype=float)
    lam = mu * g_fun(f)
    Lam = -1.0 / lam
    kap = Lam.imag / Lam.real
    a = -TWO_PI * Lam.real * (1.0 + kap**2) / (N * K_t)
    a = np.where(a > 0, a, np.nan)
    eps = math.pi - 2 * np.arctan(kap)
    T = (eps + 2 * k * math.pi) / (TWO_PI * f)
    n = 60.0 / (N * T)
    return n, a


# ---------------------------------------------------------------- noktasal eşleme


def roots_a(n_target: float, curve: Callable, f_lo: float, f_hi: float, m: int = 20001) -> list[float]:
    """curve(f) -> (n, a). n(f) = n_target olan (a tanımlı) bütün köklerde a değerleri."""
    f = np.linspace(f_lo, f_hi, m)
    n, a = curve(f)
    d = n - n_target
    out = []
    for i in np.flatnonzero(np.sign(d[:-1]) * np.sign(d[1:]) <= 0):
        lo, hi = f[i], f[i + 1]
        dlo = d[i]
        for _ in range(80):
            mid = 0.5 * (lo + hi)
            dm = float(curve(np.array([mid]))[0][0]) - n_target
            if np.sign(dm) == np.sign(dlo) and dm != 0.0:
                lo, dlo = mid, dm
            else:
                hi = mid
        aa = float(curve(np.array([0.5 * (lo + hi)]))[1][0])
        if math.isfinite(aa):
            out.append(aa)
    return out


def match_rel(n_i: float, a_i: float, curves: list[Callable], f_lo: float, f_hi: float) -> float:
    """Noktanın (n_i, a_i) referans eğrilerine en küçük göreli a farkı (kök yoksa inf)."""
    best = math.inf
    for c in curves:
        for aa in roots_a(n_i, c, f_lo, f_hi):
            best = min(best, abs(aa - a_i) / abs(aa))
    return best


def sample_idx(n: int, m: int) -> np.ndarray:
    """0..n−1 arasından en fazla m eşit aralıklı indis."""
    return np.unique(np.linspace(0, n - 1, min(n, m)).round().astype(int))
