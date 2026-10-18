"""
SPEC 02 — Kütle özellikleri: hacim, kütle, ağırlık merkezi, atalet tensörü.

Birimler: ρ [t/mm³], m [t], I [t·mm²] (N – mm – MPa ile tutarlı).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from geometry.part import Part


@dataclass(frozen=True)
class MassProps:
    """V [mm³], m [t], com (3,) [mm], I (3,3) ağırlık merkezine göre, global eksenlerde [t·mm²]."""

    V: float
    m: float
    com: np.ndarray
    I: np.ndarray  # noqa: E741 - formüldeki sembol


def mass_props(part: Part, rho: float) -> MassProps:
    """m = ρ V, I = ∫ ρ (|r|² 𝟙 − r rᵀ) dV, r = x − x̄."""
    raise NotImplementedError


def principal_moments(mp: MassProps) -> tuple[np.ndarray, np.ndarray]:
    """Artan sıralı asal momentler (3,) ve sütunları asal eksen olan (3,3) matris."""
    raise NotImplementedError
