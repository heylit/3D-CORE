"""
SPEC 27 — Torna profilinden işleme özellikleri: alın, G71 tip I kaba zarf, kanal, genel girinti.

Girdi SPEC 20 kuralındaki yarı kesit profilidir ((u, v) = (z, x), açık); katı parçadan gelen profil SPEC 28
`TurnProfile.outer` (side="dis") veya `.inner` (side="ic"). Hesap dış çerçevede yapılır,
iç tarafta x → −x aynası.
Birimler: mm.
"""

from __future__ import annotations

from dataclasses import dataclass

from cam.model import CylinderStock
from cam.profile import Profile


@dataclass(frozen=True)
class Groove:
    """Dikdörtgen kanal; parametreler doğrudan SPEC 20 groove()'a gider."""

    z_left: float  # arka duvar
    z_right: float  # ön duvar
    x_top: float
    x_bottom: float


@dataclass(frozen=True)
class Recess:
    """Genel girinti: köprünün altında kalan alt profil (ön→arka, açık)."""

    profile: Profile
    z_left: float
    z_right: float
    x_top: float


@dataclass(frozen=True)
class TurnFeatures:
    side: str
    z_face: float | None
    face_depth: float | None
    rough: Profile  # monoton kaba zarf (açık)
    finish: Profile  # girdi profili, ön→arka
    grooves: tuple[Groove, ...]  # ön→arka
    recesses: tuple[Recess, ...]  # ön→arka


def turn_features(
    profile: Profile, stock: CylinderStock | None = None, side: str = "dis", tol: float = 1e-3
) -> TurnFeatures:
    """Profilden alın, kaba zarf, kanal ve girintileri çıkarır (SPEC 27 §9)."""
    raise NotImplementedError("SPEC 27: uygulanmadı")
