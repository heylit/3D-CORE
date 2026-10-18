"""
SPEC 19 — Adaptif (sabit temas açılı) kaba işleme ve trokoidal kanal.

Temas açısı φ (derece) bir malzeme ızgarasında ölçülür; hiçbir kesme adımı hedef φ_t'yi aşmaz.
φ_t tutulamayan bölge kesilmez, AdaptiveResult.uncut_area ile raporlanır.
Tırmanma frezeleme (M3): malzeme ilerleme yönünün SAĞINDA.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from cam.model import Tool, Toolpath
from cam.ops2d import Cut
from cam.profile import Region

# ---------------------------------------------------------------- analitik yardımcılar


def ae_to_engagement(ae: float, D: float) -> float:
    """Düz duvar: φ = arccos(1 − 2·a_e/D) [derece]."""
    raise NotImplementedError("SPEC 19: ae_to_engagement")


def engagement_to_ae(phi: float, D: float) -> float:
    """Düz duvar: a_e = (D/2)(1 − cos φ) [mm]."""
    raise NotImplementedError("SPEC 19: engagement_to_ae")


def spiral_spacing(rho: float, r: float, phi: float) -> float:
    """İçbükey daire: Δ(ρ) = ρ + r − √(ρ² + r² + 2ρr·cos φ) [mm]."""
    raise NotImplementedError("SPEC 19: spiral_spacing")


def trochoid_pitch(rho: float, r: float, phi: float) -> float:
    """Trokoid: p(ρ, φ) = −r·cos φ + √((ρ + r)² − r²·sin² φ) − ρ [mm]."""
    raise NotImplementedError("SPEC 19: trochoid_pitch")


# ---------------------------------------------------------------- malzeme ızgarası


@dataclass
class MaterialGrid:
    """XY malzeme ızgarası; m[i, j] True = malzeme, hücre merkezi (x0 + (j + ½)h, y0 + (i + ½)h)."""

    x0: float
    y0: float
    h: float
    nx: int
    ny: int
    m: np.ndarray  # (ny, nx) bool

    @classmethod
    def from_region(cls, region: Region, h: float, pad: float = 0.0) -> MaterialGrid:
        """Merkezi bölgede olan hücreler malzeme."""
        raise NotImplementedError("SPEC 19: MaterialGrid.from_region")

    def cut_segment(self, a, b, r: float) -> float:
        """Merkezi [a, b]'ye uzaklığı ≤ r olan hücreleri boşaltır; boşaltılan alan [mm²]."""
        raise NotImplementedError("SPEC 19: MaterialGrid.cut_segment")

    def cut_arc(self, p0, p1, center, ccw: bool, r: float) -> float:
        """Yayı sapması ≤ h/4 kirişlerle cut_segment dizisine çevirir (p0 = p1 tam tur)."""
        raise NotImplementedError("SPEC 19: MaterialGrid.cut_arc")

    def engagement(self, a, b, r: float, n: int = 1440) -> float:
        """Adım [a, b]'nin temas açısı φ [derece]; ızgarayı değiştirmez."""
        raise NotImplementedError("SPEC 19: MaterialGrid.engagement")

    def area(self) -> float:
        """Kalan malzeme alanı h²·Σm [mm²]."""
        raise NotImplementedError("SPEC 19: MaterialGrid.area")


# ---------------------------------------------------------------- adaptif cep


@dataclass
class AdaptiveResult:
    toolpath: Toolpath
    material: MaterialGrid  # bir paso derinliğinin son ızgarası
    uncut_area: float  # T'nin iç hücrelerinde kalan malzeme [mm²]
    max_engagement: float  # helis dışındaki adımların en büyük φ'si [derece]


def adaptive_pocket(
    region: Region,
    tool: Tool,
    cut: Cut,
    engagement: float,
    *,
    leave: float = 0.0,
    step: float | None = None,
    cell: float | None = None,
    helix_radius: float | None = None,
    ramp_angle: float = 2.0,
    climb: bool = True,
    samples: int = 1440,
) -> AdaptiveResult:
    """Temas açısı ≤ φ_t olan adaptif cep yolu (SPEC 19)."""
    raise NotImplementedError("SPEC 19: adaptive_pocket")


# ---------------------------------------------------------------- trokoidal kanal


def trochoidal_slot(
    p0,
    p1,
    width: float,
    tool: Tool,
    cut: Cut,
    engagement: float,
    *,
    ramp_angle: float = 2.0,
    climb: bool = True,
) -> Toolpath:
    """P0 → P1 düz kanalı, döngü yarıçapı ρ = (w − D)/2 ve aralığı ≤ p(ρ, φ_t) olan trokoidle açar."""
    raise NotImplementedError("SPEC 19: trochoidal_slot")
