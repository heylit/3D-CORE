"""
SPEC 41 — tezgâh kinematiği: dönme, ileri ve ters kinematik.

Eksenler sıfır konumunda makine koordinatında tanımlıdır (çarpımlar-üstel). Masa W = Rot(t1)∘Rot(t2),
kafa H = Trans(X, Y, Z)∘Rot(h1)∘Rot(h2); tip₀ = g − L·s. Ters yönelim Paden–Kahan alt problem 1 ve 2
ile çözülür. Açılar arayüzde derece; q'daki döner açılar `kin.rotary` sırasındadır.
"""

from __future__ import annotations

import math

import numpy as np

from cam.model import CamError, Kinematics, RotaryAxis, Wcs

TOL = 1e-9  # birim vektör, tekillik ve ulaşılabilirlik toleransı
GAMMA_TOL = 1e-12  # alt problem 2'de γ² için negatif tolerans
ESIT_TOL = 1e-7  # [derece] çözüm seçiminde eşitlik


def _birim(nerede: str, v) -> np.ndarray:
    v = np.asarray(v, dtype=float)
    if v.shape != (3,) or not np.all(np.isfinite(v)):
        raise CamError(f"{nerede}: 3 bileşenli sonlu vektör olmalı ({v})")
    n = float(np.linalg.norm(v))
    if abs(n - 1.0) > TOL:
        raise CamError(f"{nerede}: birim vektör olmalı (|v| = {n})")
    return v


def rotation(u, theta_deg: float) -> np.ndarray:
    """Birim eksen u etrafında theta [derece] dönme matrisi (Rodrigues), (3, 3).

    R = I + sin θ·K + (1 − cos θ)·K², K = [u]×.
    """
    u = np.asarray(u, dtype=float)
    n = float(np.linalg.norm(u))
    if not np.isfinite(n) or n < TOL or not np.isfinite(theta_deg):
        raise CamError(f"Dönme: eksen sıfır olmayan, açı sonlu olmalı (u={u}, θ={theta_deg})")
    u = u / n
    K = np.array([[0.0, -u[2], u[1]], [u[2], 0.0, -u[0]], [-u[1], u[0], 0.0]])
    t = math.radians(theta_deg)
    return np.eye(3) + math.sin(t) * K + (1.0 - math.cos(t)) * (K @ K)


def rotate_about(x, u, pivot, theta_deg: float) -> np.ndarray:
    """Pivottan geçen u ekseni etrafında nokta dönmesi: c + R(x − c); x (3,) veya (n, 3)."""
    c = np.asarray(pivot, dtype=float)
    return c + (np.asarray(x, dtype=float) - c) @ rotation(u, theta_deg).T


# ---------------------------------------------------------------- zincirler


def _zincirler(kin: Kinematics) -> tuple[list[int], list[int]]:
    """(masa eksenlerinin indeksleri, kafa eksenlerinin indeksleri), her biri tabandan uca."""
    masa = [i for i, a in enumerate(kin.rotary) if a.carrier == "masa"]
    kafa = [i for i, a in enumerate(kin.rotary) if a.carrier == "kafa"]
    return masa, kafa


def _uygula(x, eksenler: list[RotaryAxis], acilar: list[float]) -> np.ndarray:
    """Rot(e1)∘Rot(e2)∘…(x): en uçtaki eksen önce uygulanır."""
    x = np.asarray(x, dtype=float)
    for a, t in zip(reversed(eksenler), reversed(acilar), strict=True):
        x = rotate_about(x, a.u, a.pivot, t)
    return x


def _ters_uygula(x, eksenler: list[RotaryAxis], acilar: list[float]) -> np.ndarray:
    """(Rot(e1)∘Rot(e2)∘…)⁻¹(x): tabandaki eksen önce, ters açıyla."""
    x = np.asarray(x, dtype=float)
    for a, t in zip(eksenler, acilar, strict=True):
        x = rotate_about(x, a.u, a.pivot, -t)
    return x


def _donme(eksenler: list[RotaryAxis], acilar: list[float]) -> np.ndarray:
    R = np.eye(3)
    for a, t in zip(eksenler, acilar, strict=True):
        R = R @ rotation(a.u, t)
    return R


def _q_ayir(kin: Kinematics, q) -> tuple[np.ndarray, list[float]]:
    q = np.asarray(q, dtype=float)
    k = len(kin.rotary)
    if q.shape != (3 + k,) or not np.all(np.isfinite(q)):
        raise CamError(f"Kinematik: q (X, Y, Z + {k} açı) sonlu olmalı ({q})")
    return q[:3], [float(v) for v in q[3:]]


def _tip0(kin: Kinematics, L: float) -> np.ndarray:
    if not np.isfinite(L):
        raise CamError(f"Kinematik: takım boyu L sonlu olmalı ({L})")
    return np.array(kin.gauge) - L * np.array(kin.spindle)


# ---------------------------------------------------------------- ileri kinematik


def forward(kin: Kinematics, q, L: float, wcs: Wcs) -> tuple[np.ndarray, np.ndarray]:
    """Eklem değerleri q = (X, Y, Z, θ…) → (uç noktası WCS (3,), takım ekseni WCS (3,)).

    tip_w = W⁻¹(H(tip₀)) − o_wcs, a_w = R_Wᵀ·R_H·s.
    """
    xyz, acilar = _q_ayir(kin, q)
    masa, kafa = _zincirler(kin)
    me, ma = [kin.rotary[i] for i in masa], [acilar[i] for i in masa]
    ke, ka = [kin.rotary[i] for i in kafa], [acilar[i] for i in kafa]
    h = xyz + _uygula(_tip0(kin, L), ke, ka)
    tip = _ters_uygula(h, me, ma) - np.array(wcs.origin)
    a = _donme(me, ma).T @ _donme(ke, ka) @ np.array(kin.spindle)
    return tip, a


# ---------------------------------------------------------------- Paden–Kahan


def _alt1(w: np.ndarray, x: np.ndarray, y: np.ndarray) -> float:
    """exp(wφ)x = y için φ [rad]; w·x = w·y olmalı (çağıran denetler)."""
    xp = x - w * (w @ x)
    yp = y - w * (w @ y)
    return math.atan2(float(w @ np.cross(xp, yp)), float(xp @ yp))


def _alt2(w1: np.ndarray, w2: np.ndarray, p: np.ndarray, q: np.ndarray) -> list[tuple[float, float]]:
    """exp(w1φ1)·exp(w2φ2)·p = q için (φ1, φ2) [rad] çözümleri; ulaşılamaz → CamError."""
    c = float(w1 @ w2)
    a = (c * (w2 @ p) - w1 @ q) / (c * c - 1.0)
    b = (c * (w1 @ q) - w2 @ p) / (c * c - 1.0)
    x = np.cross(w1, w2)
    g2 = (p @ p - a * a - b * b - 2.0 * a * b * c) / (x @ x)
    if g2 < -GAMMA_TOL:
        raise CamError(f"Ters kinematik: yön ulaşılamaz (γ² = {g2:.3e})")
    g = math.sqrt(max(g2, 0.0))
    isaretler = (1.0, -1.0) if g > 0.0 else (1.0,)
    sol = []
    for s in isaretler:
        z = a * w1 + b * w2 + s * g * x
        sol.append((-_alt1(w1, q, z), _alt1(w2, p, z)))
    return sol


def _sar(t: float) -> float:
    """Açı [derece] → (−180°, 180°]."""
    t = math.fmod(t, 360.0)
    if t <= -180.0:
        t += 360.0
    elif t > 180.0:
        t -= 360.0
    return t


def _temel(kin: Kinematics, a_w, prev: tuple[float, ...]) -> list[tuple[float, ...]]:
    """Temel çözümler (derece, kin.rotary sırasında); tekilde serbest açı prev'den."""
    q = _birim("Ters kinematik: takım ekseni", a_w)
    p = np.array(kin.spindle)
    k = len(kin.rotary)
    if k == 0:
        if np.max(np.abs(q - p)) > TOL:
            raise CamError(f"Ters kinematik: döner eksen yok, takım ekseni {tuple(p)} olmalı ({tuple(q)})")
        return [()]
    masa, kafa = _zincirler(kin)
    if k == 1:
        i = 0
        w = np.array(kin.rotary[0].u)
        sgn = -1.0 if kin.rotary[0].carrier == "masa" else 1.0
        if abs(w @ p - w @ q) > TOL:
            raise CamError(f"Ters kinematik: yön tek döner eksenle ulaşılamaz ({tuple(q)})")
        if np.linalg.norm(np.cross(w, p)) < TOL:
            return [(prev[i],)]
        return [(math.degrees(sgn * _alt1(w, p, q)),)]
    # iki eksen: exp(ω1φ1)·exp(ω2φ2)·p = q, φ = işaret·θ
    if len(masa) == 2:
        (i1, s1), (i2, s2) = (masa[1], -1.0), (masa[0], -1.0)
    elif len(kafa) == 2:
        (i1, s1), (i2, s2) = (kafa[0], 1.0), (kafa[1], 1.0)
    else:
        (i1, s1), (i2, s2) = (masa[0], -1.0), (kafa[0], 1.0)
    w1, w2 = np.array(kin.rotary[i1].u), np.array(kin.rotary[i2].u)

    def cozum(f1: float, f2: float) -> tuple[float, ...]:
        t = [0.0] * 2
        t[i1], t[i2] = math.degrees(f1) / s1, math.degrees(f2) / s2
        return tuple(t)

    if np.linalg.norm(np.cross(w1, q)) < TOL:  # φ1 serbest
        f1 = math.radians(s1 * prev[i1])
        z = rotation(w1, -math.degrees(f1)) @ q
        if abs(w2 @ p - w2 @ z) > TOL:
            raise CamError(f"Ters kinematik: yön ulaşılamaz ({tuple(q)})")
        return [cozum(f1, _alt1(w2, p, z))]
    if np.linalg.norm(np.cross(w2, p)) < TOL:  # φ2 serbest
        f2 = math.radians(s2 * prev[i2])
        z = rotation(w2, math.degrees(f2)) @ p
        if abs(w1 @ z - w1 @ q) > TOL:
            raise CamError(f"Ters kinematik: yön ulaşılamaz ({tuple(q)})")
        return [cozum(_alt1(w1, z, q), f2)]
    return [cozum(f1, f2) for f1, f2 in _alt2(w1, w2, p, q)]


def _onceki(kin: Kinematics, prev) -> tuple[float, ...]:
    k = len(kin.rotary)
    if prev is None:
        return (0.0,) * k
    prev = tuple(float(v) for v in prev)
    if len(prev) != k or not all(math.isfinite(v) for v in prev):
        raise CamError(f"Ters kinematik: önceki açılar {k} sonlu değer olmalı ({prev})")
    return prev


def all_solutions(kin: Kinematics, a_w) -> list[tuple[float, ...]]:
    """Takım ekseni a_w için sınırdan bağımsız temel açı çözümleri, (−180°, 180°]."""
    sol = []
    for s in _temel(kin, a_w, _onceki(kin, None)):
        s = tuple(_sar(t) for t in s)
        if not any(
            max((abs(_sar(a - b)) for a, b in zip(s, o, strict=True)), default=0.0) < ESIT_TOL for o in sol
        ):
            sol.append(s)
    return sol


def _aday(eksen: RotaryAxis, t: float, onceki: float) -> float | None:
    """t + 360k adaylarından sınır içinde önceki değere en yakın olan; yoksa None."""
    k0 = round((onceki - t) / 360.0)
    if eksen.min is None:
        return t + 360.0 * k0
    lo, hi = eksen.min - TOL, eksen.max + TOL
    adaylar = [t + 360.0 * k for k in range(math.floor((lo - t) / 360.0), math.ceil((hi - t) / 360.0) + 1)]
    adaylar = [v for v in adaylar if lo <= v <= hi]
    if not adaylar:
        return None
    return min(adaylar, key=lambda v: abs(v - onceki))


def inverse_axes(kin: Kinematics, a_w, prev: tuple[float, ...] | None = None) -> tuple[float, ...]:
    """Takım ekseni a_w için seçilmiş döner eksen açıları [derece] (sınır, süreklilik, tekillik kuralı)."""
    onceki = _onceki(kin, prev)
    secim: tuple[float, ...] | None = None
    secim_d = math.inf
    for s in _temel(kin, a_w, onceki):
        cand = [_aday(e, t, o) for e, t, o in zip(kin.rotary, s, onceki, strict=True)]
        if any(v is None for v in cand):
            continue
        cand = tuple(cand)
        d = sum(abs(v - o) for v, o in zip(cand, onceki, strict=True))
        if secim is None or d < secim_d - ESIT_TOL or (abs(d - secim_d) <= ESIT_TOL and cand[0] < secim[0]):
            secim, secim_d = cand, d
    if secim is None:
        sinirlar = ", ".join(f"{e.name} [{e.min}, {e.max}]" for e in kin.rotary if e.min is not None)
        raise CamError(f"Ters kinematik: eksen sınırları içinde çözüm yok ({sinirlar}; a_w = {tuple(a_w)})")
    return secim


def inverse(
    kin: Kinematics, p_w, a_w, L: float, wcs: Wcs, prev: tuple[float, ...] | None = None
) -> np.ndarray:
    """Uç noktası p_w ve eksen a_w (WCS) → eklem değerleri (X, Y, Z, θ…), (3 + k,).

    (X, Y, Z) = W(p_w + o_wcs) − (Rot(h1)∘Rot(h2))(tip₀).
    """
    p_w = np.asarray(p_w, dtype=float)
    if p_w.shape != (3,) or not np.all(np.isfinite(p_w)):
        raise CamError(f"Ters kinematik: uç noktası 3 bileşenli sonlu olmalı ({p_w})")
    acilar = list(inverse_axes(kin, a_w, prev))
    masa, kafa = _zincirler(kin)
    w = _uygula(p_w + np.array(wcs.origin), [kin.rotary[i] for i in masa], [acilar[i] for i in masa])
    h = _uygula(_tip0(kin, L), [kin.rotary[i] for i in kafa], [acilar[i] for i in kafa])
    return np.array([*(w - h), *acilar])
