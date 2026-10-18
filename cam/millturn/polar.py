"""
SPEC 49 — Polar (Fanuc G12.1 / Sinumerik TRANSMIT) ve silindirik (G7.1 / TRACYL) enterpolasyon.

Polar: parça çerçevesinde (x, y) → r = √(x² + y²), C = atan2(y, x). Eksenden h uzaklıkta geçen doğruda teğet
ilerleme F iken ω_max = F / h [rad/dk]; ω_max > 2π·CAxis.rpm_max → CamError;
merkezden geçiş (h < 1e-9) → CamError.
Silindirik: açılmış (s, z, r) → C = s / r_ref [rad], nokta (r cos C, r sin C, z).
"""

from __future__ import annotations

import math
from dataclasses import replace

import numpy as np

from cam.model import ARCS, CamError, CAxis, Move, MoveType, Toolpath

H_MIN = 1e-9  # mm, merkezden geçiş eşiği


def to_polar(p) -> tuple[float, float]:
    """(x, y[, z]) → (r, C) [mm, derece], C ∈ (−180, 180]."""
    x, y = float(p[0]), float(p[1])
    c = math.degrees(math.atan2(y, x))
    if c == -180.0:
        c = 180.0
    return math.hypot(x, y), c


def from_polar(r: float, c: float) -> np.ndarray:
    """(r, C [derece]) → (x, y)."""
    a = math.radians(c)
    return np.array([r * math.cos(a), r * math.sin(a)])


def from_cyl(s: float, z: float, r: float, r_ref: float) -> np.ndarray:
    """Açılmış silindirik nokta → parça çerçevesi (3,): C = s / r_ref [rad], (r cos C, r sin C, z)."""
    if not r_ref > 0:
        raise CamError(f"Silindirik açılım: r_ref pozitif olmalı ({r_ref})")
    C = s / r_ref
    return np.array([r * math.cos(C), r * math.sin(C), z])


def arc_chords(p0: np.ndarray, m: Move, arc_tol: float) -> list[np.ndarray]:
    """XY yayının kiriş uç noktaları (p0 hariç, bitiş dahil); sapma ≤ arc_tol, z doğrusal."""
    p1 = np.array(m.end, dtype=float)
    cx, cy = m.center
    r = math.hypot(p0[0] - cx, p0[1] - cy)
    th0 = math.atan2(p0[1] - cy, p0[0] - cx)
    dth = math.atan2(p1[1] - cy, p1[0] - cx) - th0
    cw = m.type is MoveType.ARC_CW
    if cw:
        dth = -dth
    dth %= 2 * math.pi
    if dth < 1e-12:
        dth = 2 * math.pi
    adim = 2 * math.acos(1 - arc_tol / r) if arc_tol < r else math.pi / 2
    n = max(1, math.ceil(dth / adim - 1e-12))
    s = -1.0 if cw else 1.0
    pts = []
    for i in range(1, n):
        th = th0 + s * dth * i / n
        pts.append(np.array([cx + r * math.cos(th), cy + r * math.sin(th), p0[2] + (p1[2] - p0[2]) * i / n]))
    pts.append(p1)
    return pts


def _omega_segment(a: np.ndarray, b: np.ndarray, F: float) -> float:
    """Doğru parçası a → b boyunca XY teğet hızıyla en büyük açısal hız [rad/dk]; h < H_MIN → CamError."""
    d = b[:2] - a[:2]
    Lxy = float(np.hypot(*d))
    if Lxy < 1e-12:
        return 0.0  # yalnız Z hareketi: C dönmez
    L = float(np.linalg.norm(b - a))
    Fxy = F * Lxy / L
    u = d / Lxy
    h = abs(float(a[0] * u[1] - a[1] * u[0]))  # eksenden doğruya uzaklık
    if h < H_MIN:
        # doğru eksenden geçer; parça ekseni kapsıyorsa tekil
        t = -float(a[:2] @ u)
        if -1e-12 <= t <= Lxy + 1e-12:
            raise CamError(f"Polar enterpolasyon: hareket merkezden geçiyor (h = {h:.3g} mm < {H_MIN})")
    # ω = F·h / r²; r en küçük: dikme ayağı parçadaysa r = h, değilse en yakın uç
    t = -float(a[:2] @ u)
    if 0.0 <= t <= Lxy:
        r2 = h * h
    else:
        r2 = min(float(a[:2] @ a[:2]), float(b[:2] @ b[:2]))
    if r2 < H_MIN * H_MIN:
        raise CamError("Polar enterpolasyon: hareket merkezden başlıyor ya da bitiyor")
    return Fxy * h / r2


def polar_check(tp: Toolpath, c_axis: CAxis, arc_tol: float = 1e-3) -> float:
    """coord = "polar" yolun kesme hareketlerinde en büyük açısal hız [dev/dk]; merkezden geçiş, sürekli
    olmayan C ekseni ya da rpm_max aşımı → CamError."""
    if not isinstance(c_axis, CAxis):
        raise CamError(f"Polar denetim: C ekseni CAxis olmalı ({type(c_axis).__name__})")
    if tp.coord != "polar":
        raise CamError(f"Yol '{tp.name}': polar denetim yalnız coord = 'polar' yolda ({tp.coord!r})")
    tp.validate()
    if not c_axis.continuous:
        raise CamError(f"Yol '{tp.name}': sürekli olmayan C ekseninde polar enterpolasyon yok")
    w_max = 0.0
    p0 = np.array(tp.start, dtype=float)
    for m in tp.moves:
        p1 = np.array(m.end, dtype=float)
        if m.type is not MoveType.RAPID:
            pts = arc_chords(p0, m, arc_tol) if m.type in ARCS else [p1]
            a = p0
            for b in pts:
                w_max = max(w_max, _omega_segment(a, b, float(m.feed)))
                a = b
        p0 = p1
    n = w_max / (2 * math.pi)
    if c_axis.rpm_max is not None and n > c_axis.rpm_max * (1 + 1e-12):
        raise CamError(
            f"Yol '{tp.name}': polar enterpolasyonda C devri {n:.4g} > {c_axis.rpm_max} dev/dk "
            "(yolu merkezden uzaklaştırın ya da ilerlemeyi düşürün)"
        )
    return n


def _cyl_axis(C: float) -> tuple[float, float, float]:
    """Radyal takım ekseni (uçtan iş miline) parça çerçevesinde: dışa doğru (cos C, sin C, 0)."""
    return (math.cos(C), math.sin(C), 0.0)


def _cyl_moves(tp: Toolpath, arc_tol: float) -> tuple[np.ndarray, list[Move]]:
    if tp.coord != "silindirik":
        raise CamError(f"Yol '{tp.name}': silindirik açılım yalnız coord = 'silindirik' yolda")
    tp.validate()
    if not arc_tol > 0:
        raise CamError(f"arc_tol pozitif olmalı ({arc_tol})")
    r_ref = float(tp.cyl_r)
    q0 = np.array(tp.start, dtype=float)
    moves: list[Move] = []
    for m in tp.moves:
        q1 = np.array(m.end, dtype=float)
        dphi = abs(q1[0] - q0[0]) / r_ref
        r_buyuk = max(q0[2], q1[2])
        if r_buyuk <= 0:
            raise CamError(f"Yol '{tp.name}': silindirik yolda r pozitif olmalı")
        adim = 2 * math.acos(1 - arc_tol / r_buyuk) if arc_tol < r_buyuk else math.pi / 2
        n = max(1, math.ceil(dphi / adim - 1e-12))
        for i in range(1, n + 1):
            q = q0 + (q1 - q0) * (i / n) if i < n else q1
            p = from_cyl(q[0], q[1], q[2], r_ref)
            moves.append(Move(m.type, tuple(p), feed=m.feed, axis=_cyl_axis(q[0] / r_ref)))
        q0 = q1
    s0, z0, r0 = tp.start
    return from_cyl(s0, z0, r0, r_ref), moves


def cyl_chords(tp: Toolpath, arc_tol: float = 1e-3) -> np.ndarray:
    """coord = "silindirik" yolun parça çerçevesinde kiriş noktaları (n, 3); her kirişin yaydan sapması
    ≤ arc_tol."""
    p0, moves = _cyl_moves(tp, arc_tol)
    return np.array([p0] + [m.end for m in moves], dtype=float)


def to_cartesian(tp: Toolpath, arc_tol: float = 1e-3) -> Toolpath:
    """Polar / silindirik yolu parça çerçevesinde kartezyen yola açar (simülasyon için); kartezyen yol
    aynen döner."""
    if tp.coord == "kartezyen":
        return tp
    if tp.coord == "polar":
        tp.validate()
        moves = [replace(m) for m in tp.moves]
        return replace(tp, moves=moves, coord="kartezyen", meta=None)
    p0, moves = _cyl_moves(tp, arc_tol)
    return replace(
        tp, start=tuple(float(v) for v in p0), moves=moves, coord="kartezyen", cyl_r=None, meta=None
    )
