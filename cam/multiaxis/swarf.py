"""
SPEC 50 — yanak (swarf) frezeleme: regle yüzeyi düz ucun yan yüzüyle tek pasoda işleme.

S(u, v) = (1 − v)·C₀(u) + v·C₁(u); takım ekseni cetvel yönü g = norm(C₁ − C₀), eksen doğrusu cetvelin
n_m yönünde R ötesinde. Gelişebilir yüzeyde hata 0; bükülmüşte e ≈ R·(1 − cos Δφ) ve gerçek girme ölçülür.

Birimler: mm, mm/dk, dev/dk.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from cam.model import Tool, Toolpath


@dataclass
class RuledSurface:
    """Eş parametreli iki ray: C0 alt, C1 üst (n, 3)."""

    C0: np.ndarray
    C1: np.ndarray

    def __post_init__(self) -> None:
        raise NotImplementedError("SPEC 50: RuledSurface doğrulaması")


def swarf(
    surface: RuledSurface,
    tool: Tool,
    side: int = +1,
    allowance: float = 0.0,
    allowance_z: float = 0.0,
    tol_swarf: float = 0.01,
    n_check: int = 21,
    *,
    feed: float,
    rpm: float,
    clearance: float = 5.0,
) -> Toolpath:
    """Yanak yolu; her Move.axis = g(u), meta (yanak, 5). Hata tol_swarf'ı aşarsa CamError."""
    raise NotImplementedError("SPEC 50: swarf")


def swarf_error(surface: RuledSurface, tool: Tool, u: float, side: int = +1, n_check: int = 101) -> float:
    """u'daki takım konumunun gerçek yüzeye en büyük girmesi [mm]."""
    raise NotImplementedError("SPEC 50: swarf_error")
