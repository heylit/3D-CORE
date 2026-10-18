"""
SPEC 23 — Havşalı, lambalı, dişli ve eğimli delik; diş ve lamba tabloları.

Her delik işlemi dönen parçaya bir geometry.part.Hole kaydı ekler (CAM delme çevrimleri bunu okur).
Hiçbir işlem girdi parçayı değiştirmez. Birimler: mm, açı: derece.
"""

from __future__ import annotations

import numpy as np

from geometry.part import Part

# ISO 261 / ISO 724 kaba hatve P [mm]; kılavuz matkabı d_m = d_n − P
THREADS_COARSE: dict[str, float] = {
    "M3": 0.5,
    "M4": 0.7,
    "M5": 0.8,
    "M6": 1.0,
    "M8": 1.25,
    "M10": 1.5,
    "M12": 1.75,
    "M14": 2.0,
    "M16": 2.0,
    "M20": 2.5,
    "M24": 3.0,
}

# ISO 4762 imbus civata lambası: (d geçiş ISO 273 orta, D lamba, t_c lamba derinliği) DIN 974-1 [mm]
CBORE_ISO4762: dict[str, tuple[float, float, float]] = {
    "M3": (3.4, 6.5, 3.4),
    "M4": (4.5, 8.0, 4.4),
    "M5": (5.5, 10.0, 5.4),
    "M6": (6.6, 11.0, 6.4),
    "M8": (9.0, 15.0, 8.6),
    "M10": (11.0, 18.0, 10.6),
    "M12": (13.5, 20.0, 12.6),
    "M14": (15.5, 24.0, 14.6),
    "M16": (17.5, 26.0, 16.6),
    "M20": (22.0, 33.0, 20.6),
    "M24": (26.0, 40.0, 24.8),
}


def parse_thread(spec: str) -> tuple[float, float]:
    """ "M8" → (8.0, 1.25), "M8x1" → (8.0, 1.0): (nominal çap d_n, hatve P)."""
    raise NotImplementedError("SPEC 23: parse_thread")


def countersink_hole(
    part: Part,
    x: float,
    y: float,
    d: float,
    csk_d: float,
    csk_angle: float = 90.0,
    depth: float | None = None,
) -> Part:
    """Üstten −Z havşalı delik, eksen (x, y). depth=None → boydan boya."""
    raise NotImplementedError("SPEC 23: countersink_hole")


def counterbore_hole(
    part: Part,
    x: float,
    y: float,
    screw: str | None = None,
    d: float | None = None,
    cbore_d: float | None = None,
    cbore_depth: float | None = None,
    depth: float | None = None,
) -> Part:
    """Üstten −Z lambalı delik, eksen (x, y). screw verilirse eksik ölçüler CBORE_ISO4762'den."""
    raise NotImplementedError("SPEC 23: counterbore_hole")


def tapped_hole(
    part: Part,
    x: float,
    y: float,
    thread: str,
    depth: float | None = None,
    thread_depth: float | None = None,
) -> Part:
    """Üstten −Z dişli delik (kozmetik diş): kılavuz matkabı d_m = d_n − P."""
    raise NotImplementedError("SPEC 23: tapped_hole")


def inclined_hole(
    part: Part,
    p: np.ndarray,
    n: np.ndarray,
    d: float,
    depth: float | None = None,
) -> Part:
    """Giriş noktası p (yüzeyde), delme yönü n ile eğimli delik. depth=None → boydan boya."""
    raise NotImplementedError("SPEC 23: inclined_hole")
