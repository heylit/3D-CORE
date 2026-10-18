"""
SPEC 05 — İşleme süresi tahmini.

Hız sınırı v [mm/s]: kesmede F/60; G0'da eksen başına hızlı ilerlemeyi aşmayan doğrusal hız
v = min_i (rapid_i / |u_i|) / 60 (u birim yön). Yayda merkezcil ivme sınırı v ≤ √(a·r).
accel yoksa t = L / v. accel = a ile her hareket durarak başlar ve biter (tam duruş):
    L ≥ v²/a → trapez  t = L/v + v/a        L < v²/a → üçgen  t = 2·√(L/a)
"""

from __future__ import annotations

from dataclasses import dataclass

from cam.model import Move, Plane


@dataclass(frozen=True)
class Machine:
    """Makine: eksen başına hızlı ilerleme [mm/dk], yol ivmesi [mm/s²] (None → sonsuz), takım değişimi [s]."""

    rapid: tuple[float, float, float] = (5000.0, 5000.0, 3000.0)
    accel: float | None = None
    tool_change: float = 0.0

    def __post_init__(self) -> None:
        raise NotImplementedError("SPEC 05: uygulanmadı")


def arc_geometry(p0, p1, center, cw: bool) -> tuple[float, float, float]:
    """G17 yayı: (r, |Δθ|, θ0). Başlangıç = bitiş (XY) ise tam daire."""
    raise NotImplementedError("SPEC 05: uygulanmadı")


def move_time(p0, p1, move: Move, plane: Plane, machine: Machine) -> float:
    """Tek hareketin süresi [s]."""
    raise NotImplementedError("SPEC 05: uygulanmadı")
