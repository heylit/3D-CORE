"""
SPEC 28 — Katı parçadan torna profili: eksenden geçen yarı düzlem kesitinden SPEC 20 profilleri.

Kesit geometry tarafında alınır (Part.axial_section); burada kenarlar Line/Arc'a çevrilir, bağlanır,
birleştirilir, serbest eğriler doğru + yaya uydurulur ve kapalı kesit dış / iç profile bölünür.
Koordinatlar (u, v) = (z, x).

Birimler: mm.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from cam.profile import Profile
from geometry.part import AxialSection, Part


@dataclass(frozen=True)
class TurnProfile:
    """Dönel parçanın yarı kesiti ve SPEC 20 profilleri."""

    section: Profile  # kapalı, CCW, (z, x), her noktada x ≥ 0
    outer: Profile  # açık, ön→arka, SPEC 20 side="dis"
    inner: Profile | None  # açık, ön→arka, SPEC 20 side="ic"; delik yoksa None
    origin: np.ndarray  # (3,)
    axis: np.ndarray  # (3,) birim
    xdir: np.ndarray  # (3,) birim
    fitted_length: float  # L_u: serbest eğriden uydurulan kenarların toplam boyu [mm]; tam kesitte 0


def profile_from_section(sec: AxialSection, tol: float = 1e-3) -> TurnProfile:
    """OCCT'siz: kenarları Line/Arc'a çevirir, bağlar, birleştirir, uydurur, dış/iç profili böler.

    off_axis_faces doluysa, yüz sayısı 1 değilse ya da yüzde iç halka varsa → CamError.
    """
    raise NotImplementedError("SPEC 28: cam.turn_profile.profile_from_section")


def turn_profile(part: Part, axis=(0.0, 0.0, 1.0), origin=(0.0, 0.0, 0.0), tol: float = 1e-3) -> TurnProfile:
    """part.axial_section + profile_from_section + Pappus hacim ve alan denetimi.

    axis="auto" desteklenir. Tüm hatalar CamError (GeometryError da CamError'a çevrilir, mesaj korunur).
    """
    raise NotImplementedError("SPEC 28: cam.turn_profile.turn_profile")
