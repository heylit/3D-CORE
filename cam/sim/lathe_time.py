"""
SPEC 22 — Torna hareket süresi: G95 (mm/dev), G96 sabit kesme hızı ve G50 devir sınırı.

G96: n(x) = min(1000·Vc / (2π·|x|), rpm), x = 0 → rpm; t = ∫ 60 ds / (F·n(x(s))).
G0 ve accel: SPEC 05 kuralları (cam.sim.timing).
"""

from __future__ import annotations

from cam.model import Move, Toolpath
from cam.sim.timing import Machine


def lathe_move_time(p0, p1, move: Move, path: Toolpath, machine: Machine) -> float:
    """Tek hareketin süresi [s]; feed_mode, css, rpm path'ten."""
    raise NotImplementedError
