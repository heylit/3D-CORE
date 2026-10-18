"""
SPEC 42 — TCP kapalı çıkış için eklem uzayında doğrusallaştırma ve G93 ters zaman ilerlemesi.

Kontrolör eklemleri doğrusal enterpole eder: q(t) = q₀ + t(q₁ − q₀). Uç yolu doğrudan sapar;
sapma tol_p / tol_a'yı aşan hareket ortadan (p doğrusal, a slerp) ikiye bölünür.
"""

from __future__ import annotations

import math

import numpy as np

from cam.model import CamError, Kinematics, Move, Toolpath, Wcs
from cam.multiaxis.indexed import to_machine, to_world
from cam.multiaxis.kinematics import forward, inverse

_T = (0.25, 0.5, 0.75)
L_MIN = 1e-9  # mm, bundan kısa uç yolu "yalnız döner hareket" sayılır


def _slerp(a0: np.ndarray, a1: np.ndarray, t: float) -> np.ndarray:
    w = math.acos(float(np.clip(a0 @ a1, -1.0, 1.0)))
    if w < 1e-12:
        return a0.copy()
    if math.pi - w < 1e-9:
        raise CamError("slerp: zıt eksenler arası ara yön tanımsız")
    return (math.sin((1.0 - t) * w) * a0 + math.sin(t * w) * a1) / math.sin(w)


def _aci(u: np.ndarray, v: np.ndarray) -> float:
    return math.degrees(math.atan2(float(np.linalg.norm(np.cross(u, v))), float(u @ v)))


def _parca_uzaklik(x: np.ndarray, p0: np.ndarray, p1: np.ndarray) -> float:
    d = p1 - p0
    dd = float(d @ d)
    s = 0.0 if dd == 0 else float(np.clip((x - p0) @ d / dd, 0.0, 1.0))
    return float(np.linalg.norm(x - (p0 + s * d)))


def joint_path(
    tp: Toolpath, kin: Kinematics, wcs: Wcs, L: float, prev: tuple[float, ...] | None = None
) -> np.ndarray:
    """Her nokta için eklem değerleri (n+1, 3 + k); Move.axis kullanılır (41 to_machine)."""
    return to_machine(tp, kin, wcs, L, prev)


def deviation(kin: Kinematics, wcs: Wcs, L: float, q0, q1, p0, p1, a0, a1, t: float) -> tuple[float, float]:
    """Eklem doğrusal enterpolasyonunda t anındaki (konum sapması [mm], yönelim sapması [°])."""
    q0, q1 = np.asarray(q0, dtype=float), np.asarray(q1, dtype=float)
    p0, p1 = np.asarray(p0, dtype=float), np.asarray(p1, dtype=float)
    a0, a1 = np.asarray(a0, dtype=float), np.asarray(a1, dtype=float)
    tip, a = forward(kin, q0 + t * (q1 - q0), L, wcs)
    return _parca_uzaklik(tip, p0, p1), _aci(a, _slerp(a0, a1, t))


def linearize(
    tp: Toolpath,
    kin: Kinematics,
    wcs: Wcs,
    L: float,
    tol_p: float = 1e-3,
    tol_a: float = 0.05,
    max_depth: int = 12,
) -> Toolpath:
    """Sapması toleransı aşan hareketleri ortadan bölerek yeni yol (WCS, her Move.axis dolu).

    Eklem değerleri çıkış yolunun sırasıyla (her nokta öncekinin açılarından devam) hesaplanır;
    böylece sonuç joint_path(çıkış) ile aynı eklem yolunu verir.
    """
    for ad, v in (("tol_p", tol_p), ("tol_a", tol_a)):
        if not (math.isfinite(v) and v > 0):
            raise CamError(f"linearize: {ad} pozitif olmalı ({v})")
    if isinstance(max_depth, bool) or not isinstance(max_depth, int) or max_depth < 0:
        raise CamError(f"linearize: max_depth negatif olmayan tam sayı olmalı ({max_depth!r})")
    w = to_world(tp)
    A = [np.array(m.axis) for m in w.moves]
    p0 = np.array(w.start, dtype=float)
    a0 = A[0] if A else np.array([0.0, 0.0, 1.0])
    q0 = inverse(kin, p0, a0, L, wcs, None)
    moves: list[Move] = []
    for m, a_son in zip(w.moves, A, strict=True):
        yigin = [(np.array(m.end, dtype=float), a_son, 0)]
        while yigin:
            p1, a1, d = yigin[-1]
            q1 = inverse(kin, p1, a1, L, wcs, tuple(float(v) for v in q0[3:]))
            sap = [deviation(kin, wcs, L, q0, q1, p0, p1, a0, a1, t) for t in _T]
            if max(e for e, _ in sap) <= tol_p and max(e for _, e in sap) <= tol_a:
                moves.append(
                    Move(m.type, tuple(float(v) for v in p1), feed=m.feed, axis=tuple(float(v) for v in a1))
                )
                p0, a0, q0 = p1, a1, q1
                yigin.pop()
                continue
            if d >= max_depth:
                raise CamError(
                    f"linearize: '{tp.name}' {tuple(p0)} → {tuple(p1)} hareketi {max_depth} bölmede "
                    f"toleransa inmedi (e_p = {max(e for e, _ in sap):.3g} mm)"
                )
            yigin[-1] = (p1, a1, d + 1)
            yigin.append(((p0 + p1) / 2, _slerp(a0, a1, 0.5), d + 1))
    return Toolpath(
        name=w.name,
        tool=w.tool,
        start=w.start,
        moves=moves,
        rpm=w.rpm,
        plane=w.plane,
        feed_mode=w.feed_mode,
        css=w.css,
        frame=None,
    )


def inverse_time(
    tp: Toolpath, q: np.ndarray, F_rot: float | None = None, inv_max: float = 99999.0
) -> np.ndarray:
    """Her hareket için G93 değeri F_inv = F / L [1/dk]; yalnız döner harekette t = max|Δθ| / F_rot."""
    q = np.asarray(q, dtype=float)
    n = len(tp.moves)
    if q.ndim != 2 or q.shape[0] != n + 1 or q.shape[1] < 3:
        raise CamError(f"inverse_time: q (n+1, 3 + k) olmalı (n = {n}, şekil {q.shape})")
    if F_rot is not None and not (math.isfinite(F_rot) and F_rot > 0):
        raise CamError(f"inverse_time: F_rot pozitif olmalı ({F_rot})")
    if not (math.isfinite(inv_max) and inv_max > 0):
        raise CamError(f"inverse_time: inv_max pozitif olmalı ({inv_max})")
    P = tp.points()
    F = np.empty(n)
    for i, m in enumerate(tp.moves):
        Lk = float(np.linalg.norm(P[i + 1] - P[i]))
        if Lk >= L_MIN:
            if m.feed is None or m.feed <= 0:
                raise CamError(
                    f"inverse_time: hareket {i} ({m.type.value}) pozitif ilerleme ister ({m.feed})"
                )
            F[i] = m.feed / Lk
        else:
            if F_rot is None:
                raise CamError(f"inverse_time: hareket {i} yalnız döner (L = {Lk:.3g}), F_rot verilmeli")
            dth = float(np.max(np.abs(q[i + 1, 3:] - q[i, 3:]))) if q.shape[1] > 3 else 0.0
            if dth < L_MIN:
                raise CamError(f"inverse_time: hareket {i} sıfır boylu ve dönmesiz")
            F[i] = F_rot / dth
        if F[i] > inv_max:
            raise CamError(f"inverse_time: hareket {i} için F_inv = {F[i]:.6g} > {inv_max}")
    return F
