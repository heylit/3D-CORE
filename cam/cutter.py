"""
SPEC 06b — Dönel simetrik takımın dışbükey profili f(ρ).

f(ρ): eksenden ρ uzaklıkta takım alt yüzeyinin uca göre yüksekliği, ρ ∈ [0, R]; f(0) = 0,
azalmayan ve dışbükey; ρ > R için +∞ (üstünde dik silindir). Profil meridyen düzleminde doğru ve
çember yaylarından oluşur. Düz, küresel, torik ve konik takımlar ile bunların δ ofsetleri (işleme payı).

Destek (Legendre) fonksiyonu: f*(m) = max_{ρ ∈ [0, R]} (m·ρ − f(ρ)), en büyüğü veren ρ*(m).

Birimler: mm, açı derece.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from cam.model import Tool


@dataclass(frozen=True)
class Cutter:
    """Dışbükey takım profili; dış yarıçap R [mm], parçalar doğru ve yay."""

    R: float
    parcalar: tuple = ()

    def __post_init__(self) -> None:
        raise NotImplementedError("SPEC 06b: Cutter")

    @classmethod
    def flat(cls, R: float) -> Cutter:
        raise NotImplementedError("SPEC 06b: Cutter.flat")

    @classmethod
    def ball(cls, R: float) -> Cutter:
        raise NotImplementedError("SPEC 06b: Cutter.ball")

    @classmethod
    def torus(cls, R: float, r_c: float) -> Cutter:
        raise NotImplementedError("SPEC 06b: Cutter.torus")

    @classmethod
    def cone(cls, R: float, theta: float) -> Cutter:
        """theta: yarı açı [derece], 0 < theta < 90."""
        raise NotImplementedError("SPEC 06b: Cutter.cone")

    @classmethod
    def from_tool(cls, tool: Tool) -> Cutter:
        raise NotImplementedError("SPEC 06b: Cutter.from_tool")

    @property
    def height(self) -> float:
        """f(R) [mm]."""
        raise NotImplementedError("SPEC 06b: Cutter.height")

    def f(self, rho: np.ndarray) -> np.ndarray:
        """Profil yüksekliği; rho > R → inf, rho < 0 → CamError."""
        raise NotImplementedError("SPEC 06b: Cutter.f")

    def support(self, m: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """(f*(m), ρ*(m)); m < 0 → CamError."""
        raise NotImplementedError("SPEC 06b: Cutter.support")

    def offset(self, delta: float) -> Cutter:
        """δ küreyle Minkowski toplamının alt yüzeyi, ucu 0'a kaydırılmış; delta ≥ 0."""
        raise NotImplementedError("SPEC 06b: Cutter.offset")
