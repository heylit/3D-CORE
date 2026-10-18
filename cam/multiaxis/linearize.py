"""
SPEC 42 — TCP kapalı çıkış için eklem uzayında doğrusallaştırma ve G93 ters zaman ilerlemesi.

Kontrolör eklemleri doğrusal enterpole eder: q(t) = q₀ + t(q₁ − q₀). Uç yolu doğrudan sapar;
sapma tol_p / tol_a'yı aşan hareket ortadan ikiye bölünür.
"""

from __future__ import annotations

import numpy as np

from cam.model import Kinematics, Toolpath, Wcs


def joint_path(
    tp: Toolpath, kin: Kinematics, wcs: Wcs, L: float, prev: tuple[float, ...] | None = None
) -> np.ndarray:
    """Her nokta için eklem değerleri (n+1, 3 + k); Move.axis kullanılır."""
    raise NotImplementedError("SPEC 42: joint_path")


def deviation(kin: Kinematics, wcs: Wcs, L: float, q0, q1, p0, p1, a0, a1, t: float) -> tuple[float, float]:
    """Eklem doğrusal enterpolasyonunda t anındaki (konum sapması [mm], yönelim sapması [°])."""
    raise NotImplementedError("SPEC 42: deviation")


def linearize(
    tp: Toolpath,
    kin: Kinematics,
    wcs: Wcs,
    L: float,
    tol_p: float = 1e-3,
    tol_a: float = 0.05,
    max_depth: int = 12,
) -> Toolpath:
    """Sapması toleransı aşan hareketleri ortadan bölerek yeni yol."""
    raise NotImplementedError("SPEC 42: linearize")


def inverse_time(
    tp: Toolpath, q: np.ndarray, F_rot: float | None = None, inv_max: float = 99999.0
) -> np.ndarray:
    """Her hareket için G93 değeri F_inv = F / L [1/dk]; yalnız döner harekette F_rot ile."""
    raise NotImplementedError("SPEC 42: inverse_time")
