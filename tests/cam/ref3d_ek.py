"""SPEC 06b testleri için bağımsız referans hesapları (torik / konik profil, ofset, waterline ağları).

Bu modül `cam` paketinden hiçbir şey import etmez. Profil fonksiyonları SPEC 06b "Takım profili"
tablosundaki kapalı formlardır; destek fonksiyonu ve ofset profili kaba kuvvetle (sık örnekleme +
yerel sıklaştırma) hesaplanır, kapalı form kullanılmaz.

Kaynaklar:
- Dışbükey bir cismin küreyle Minkowski toplamı: dönel simetrik dışbükey cisimde meridyen kesiti,
  kesitin δ diskiyle 2D Minkowski toplamıdır; alt zarf = min_p (z_p − √(δ² − (ρ − ρ_p)²)).
- Noktanın dışbükey kümeye uzaklığı: torik takım katısının meridyen kesiti
  {(ρ, z) : ρ ≤ R, z ≥ f(ρ)}; düz taban, tüp yayı (merkez (R_t, r_c)) ve dik kenar bölgeleri.
"""

from __future__ import annotations

import math

import numpy as np
from scipy.optimize import minimize_scalar

# --- Profil ---------------------------------------------------------------------------------------


def profil(kind: str, R: float, rc: float = 0.0, theta: float | None = None):
    """SPEC 06b tablosu: f(ρ). kind ∈ {duz, kure, torik, konik}; theta yarı açı [derece].
    ρ > R → inf."""

    def f(rho):
        rho = np.asarray(rho, dtype=float)
        if kind == "duz":
            z = np.zeros_like(rho)
        elif kind == "kure":
            z = R - np.sqrt(np.maximum(R * R - rho * rho, 0.0))
        elif kind == "torik":
            Rt = R - rc
            q = np.clip(rho - Rt, 0.0, None)
            z = np.where(rho <= Rt, 0.0, rc - np.sqrt(np.maximum(rc * rc - q * q, 0.0)))
        elif kind == "konik":
            z = rho / math.tan(math.radians(theta))
        else:
            raise ValueError(kind)
        return np.where(rho > R, np.inf, z)

    return f


def brute_support(f, R: float, m: float) -> tuple[float, float]:
    """f*(m) = max_{ρ∈[0,R]} (mρ − f(ρ)) ve en küçük en büyük-veren ρ*: sık örnekleme + sınırlı
    tek boyutlu sıklaştırma (amaç içbükey)."""
    rho = np.linspace(0.0, R, 200_001)
    g = m * rho - f(rho)
    k = int(np.argmax(g))
    lo, hi = rho[max(k - 1, 0)], rho[min(k + 1, len(rho) - 1)]
    res = minimize_scalar(
        lambda r: -(m * r - float(f(r))), bounds=(lo, hi), method="bounded", options={"xatol": 1e-14}
    )
    best = max(float(g.max()), -float(res.fun))
    adaylar = np.append(rho, res.x)
    degerler = np.append(g, -res.fun)
    rho_star = float(adaylar[degerler >= best - 1e-12].min())
    return best, rho_star


def minkowski_profile(f, R: float, delta: float, rho_eval: np.ndarray, n: int = 80_001) -> np.ndarray:
    """Takım katısı ⊕ δ küre alt zarfı, ucu 0'a kaydırılmış (meridyen kesitinde kaba kuvvet)."""
    p = np.linspace(-R, R, n)
    zp = f(np.abs(p))
    out = np.empty(len(rho_eval))
    for i, rho in enumerate(rho_eval):
        dx = rho - p
        ok = np.abs(dx) <= delta
        out[i] = np.min(zp[ok] - np.sqrt(delta * delta - dx[ok] ** 2)) + delta if np.any(ok) else np.inf
    return out


def torus_tool_distance(pts: np.ndarray, cl, R: float, rc: float) -> float:
    """Noktaların torik takım katısına (dış yarıçap R, köşe r_c, ucu CL'de, yukarı sonsuz silindir) en
    kısa uzaklığı; r_c = 0 düz uçtur. İçerideki nokta için 0."""
    d = np.hypot(pts[:, 0] - cl[0], pts[:, 1] - cl[1])
    z = pts[:, 2] - cl[2]
    Rt = R - rc
    u = d - Rt
    w = z - rc
    taban = np.maximum(-z, 0.0)
    kenar = np.maximum(d - R, 0.0)
    tup = np.maximum(np.hypot(u, w) - rc, 0.0)
    dist = np.where(d <= Rt, taban, np.where(w >= 0, kenar, tup))
    return float(dist.min())


# --- Waterline ağları ve 2D geometri ---------------------------------------------------------------


def prism_mesh(
    rings: list[np.ndarray], top: list[tuple[int, int, int]], z_a: float, z_b: float, anchor=None
) -> tuple[np.ndarray, np.ndarray]:
    """Dik duvarlı prizma: her halka (k, 2) bir duvar zinciri (z_a..z_b), `top` üst kapak üçgenleri
    (halkaların birleştirilmiş köşe numarasıyla, yukarıdan CCW). anchor = (x, y, z): ağın sınır kutusunu
    genel konuma kaydıran küçük yatay üçgen (girişimi yok)."""
    V: list[list[float]] = []
    T: list[list[int]] = []
    ust: list[int] = []
    for ring in rings:
        k = len(ring)
        b0 = len(V)
        for x, y in ring:
            V.append([x, y, z_a])
        t0 = len(V)
        for x, y in ring:
            V.append([x, y, z_b])
        ust.extend(range(t0, t0 + k))
        for i in range(k):
            j = (i + 1) % k
            T.append([b0 + i, b0 + j, t0 + j])
            T.append([b0 + i, t0 + j, t0 + i])
    for a, b, c in top:
        T.append([ust[a], ust[b], ust[c]])
    if anchor is not None:
        x, y, z = anchor
        n = len(V)
        V += [[x, y, z], [x + 0.1, y, z], [x, y + 0.1, z]]
        T.append([n, n + 1, n + 2])
    return np.array(V, dtype=float), np.array(T, dtype=int)


def segments_of(rings: list[np.ndarray]) -> tuple[np.ndarray, np.ndarray]:
    A = np.vstack([np.asarray(r, dtype=float) for r in rings])
    B = np.vstack([np.roll(np.asarray(r, dtype=float), -1, axis=0) for r in rings])
    return A, B


def dist_to_segments(P: np.ndarray, A: np.ndarray, B: np.ndarray) -> np.ndarray:
    """(n, 2) noktaların (m) doğru parçasına en kısa uzaklığı, (n,)."""
    P = np.asarray(P, dtype=float)
    ab = B - A
    L2 = np.einsum("ij,ij->i", ab, ab)
    t = np.clip(np.einsum("nmj,mj->nm", P[:, None, :] - A[None], ab) / L2[None], 0.0, 1.0)
    Q = A[None] + t[..., None] * ab[None]
    return np.min(np.linalg.norm(P[:, None, :] - Q, axis=2), axis=1)


def signed_area(loop: np.ndarray) -> float:
    """Shoelace: CCW > 0, CW < 0."""
    x, y = loop[:, 0], loop[:, 1]
    return 0.5 * float(np.sum(x * np.roll(y, -1) - np.roll(x, -1) * y))
