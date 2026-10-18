"""
SPEC 49 — Polar (Fanuc G12.1 / Sinumerik TRANSMIT) ve silindirik (G7.1 / TRACYL) enterpolasyon.

Polar: parça çerçevesinde (x, y) → r = √(x² + y²), C = atan2(y, x). Eksenden h uzaklıkta geçen doğruda teğet
ilerleme F iken ω_max = F / h [rad/dk]; ω_max > 2π·CAxis.rpm_max → CamError;
merkezden geçiş (h < 1e-9) → CamError.
Silindirik: açılmış (s, z, r) → C = s / r_ref [rad], nokta (r cos C, r sin C, z).
"""

from __future__ import annotations

import numpy as np

from cam.model import CAxis, Toolpath

H_MIN = 1e-9  # mm, merkezden geçiş eşiği


def to_polar(p) -> tuple[float, float]:
    """(x, y[, z]) → (r, C) [mm, derece], C ∈ (−180, 180]."""
    raise NotImplementedError


def from_polar(r: float, c: float) -> np.ndarray:
    """(r, C [derece]) → (x, y)."""
    raise NotImplementedError


def from_cyl(s: float, z: float, r: float, r_ref: float) -> np.ndarray:
    """Açılmış silindirik nokta → parça çerçevesi (3,): C = s / r_ref [rad], (r cos C, r sin C, z)."""
    raise NotImplementedError


def polar_check(tp: Toolpath, c_axis: CAxis) -> float:
    """coord = "polar" yolun kesme hareketlerinde en büyük açısal hız [dev/dk]; merkezden geçiş, sürekli
    olmayan C ekseni ya da rpm_max aşımı → CamError."""
    raise NotImplementedError


def cyl_chords(tp: Toolpath, arc_tol: float = 1e-3) -> np.ndarray:
    """coord = "silindirik" yolun parça çerçevesinde kiriş noktaları (n, 3); her kirişin yaydan sapması
    ≤ arc_tol."""
    raise NotImplementedError


def to_cartesian(tp: Toolpath, arc_tol: float = 1e-3) -> Toolpath:
    """Polar / silindirik yolu parça çerçevesinde kartezyen yola açar (simülasyon için); kartezyen yol
    aynen döner."""
    raise NotImplementedError
