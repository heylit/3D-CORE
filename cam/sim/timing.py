"""
SPEC 05 — İşleme süresi tahmini.

Hız sınırı v [mm/s]: kesmede F/60; G0'da eksen başına hızlı ilerlemeyi aşmayan doğrusal hız
v = min_i (rapid_i / |u_i|) / 60 (u birim yön). Yayda merkezcil ivme sınırı v ≤ √(a·r).
accel yoksa t = L / v. accel = a ile her hareket durarak başlar ve biter (tam duruş):
    L ≥ v²/a → trapez  t = L/v + v/a        L < v²/a → üçgen  t = 2·√(L/a)
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from cam.model import ARCS, CamError, Move, MoveType, Plane


def _pos_finite(v) -> bool:
    return isinstance(v, int | float) and not isinstance(v, bool) and math.isfinite(v) and v > 0


@dataclass(frozen=True)
class Machine:
    """Makine: eksen başına hızlı ilerleme [mm/dk], yol ivmesi [mm/s²] (None → sonsuz), takım değişimi [s]."""

    rapid: tuple[float, float, float] = (5000.0, 5000.0, 3000.0)
    accel: float | None = None
    tool_change: float = 0.0

    def __post_init__(self) -> None:
        rapid = tuple(self.rapid)
        if len(rapid) != 3 or not all(_pos_finite(v) for v in rapid):
            raise CamError(f"Makine: rapid üç pozitif sonlu değer olmalı ({self.rapid})")
        object.__setattr__(self, "rapid", tuple(float(v) for v in rapid))
        if self.accel is not None and not _pos_finite(self.accel):
            raise CamError(f"Makine: ivme pozitif sonlu olmalı veya None ({self.accel})")
        tc = self.tool_change
        if not (isinstance(tc, int | float) and not isinstance(tc, bool) and math.isfinite(tc) and tc >= 0):
            raise CamError(f"Makine: takım değişim süresi ≥ 0 olmalı ({tc})")


def _axis_limit(u: np.ndarray, rapid: tuple[float, float, float]) -> float:
    """Doğrultu u boyunca eksen hızlarını aşmayan en büyük yol hızı [mm/dk]."""
    return min(rapid[i] / abs(u[i]) for i in range(3) if abs(u[i]) > 1e-15)


def arc_geometry(p0, p1, center, cw: bool) -> tuple[float, float, float]:
    """G17 yayı: (r, |Δθ|, θ0). Başlangıç = bitiş (XY) ise tam daire."""
    c = np.asarray(center, dtype=float)
    v0 = np.asarray(p0[:2], dtype=float) - c
    v1 = np.asarray(p1[:2], dtype=float) - c
    r = float(np.hypot(*v0))
    th0 = math.atan2(v0[1], v0[0])
    dth = math.atan2(v1[1], v1[0]) - th0
    if cw:
        dth = -dth
    dth %= 2 * math.pi
    if dth < 1e-12:
        dth = 2 * math.pi
    return r, dth, th0


def move_time(p0, p1, move: Move, plane: Plane, machine: Machine) -> float:
    """Tek hareketin süresi [s]."""
    if Plane(plane) is not Plane.XY:
        raise CamError("Süre tahmini yalnız G17 (XY) yolları için")
    p0 = np.asarray(p0, dtype=float)
    p1 = np.asarray(p1, dtype=float)
    r = None
    if move.type in ARCS:
        r, dth, _ = arc_geometry(p0, p1, move.center, move.type is MoveType.ARC_CW)
        L = math.hypot(r * dth, p1[2] - p0[2])
    else:
        L = float(np.linalg.norm(p1 - p0))
    if L == 0:
        return 0.0
    if move.type is MoveType.RAPID:
        v = _axis_limit((p1 - p0) / L, machine.rapid) / 60
    else:
        if move.feed is None or not move.feed > 0:
            raise CamError(f"Hareket ({move.type.value}): ilerleme pozitif olmalı (feed={move.feed})")
        v = move.feed / 60
        if r is None:
            v = min(v, _axis_limit((p1 - p0) / L, machine.rapid) / 60)
        else:
            v = min(v, min(machine.rapid[0], machine.rapid[1]) / 60)
            if machine.accel is not None:
                v = min(v, math.sqrt(machine.accel * r))
    a = machine.accel
    if a is None:
        return L / v
    if L >= v * v / a:
        return L / v + v / a
    return 2 * math.sqrt(L / a)
