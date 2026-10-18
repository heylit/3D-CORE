"""
Tek yönlü termo-mekanik zincir: sıcaklık geçmişi → ısıl yük (67b) → statik çözüm (SPEC 68b).

Mekanik sonuç ısıyı etkilemez. Isıl ve mekanik ağ aynı düğümlerde olmalı
(aynı tet4 ağı ya da tet10'un köşe düğümleri).

Teori: specs/68b-gecici-isil-termomekanik.md
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

import numpy as np

from core.isil import ThermalResult
from core.isil_gecici import TransientResult
from core.model import Model


@dataclass(frozen=True)
class TermoMekanik:
    t: np.ndarray  # (s,)
    sigma_vM_maks: np.ndarray  # (s,) her zamanda en büyük düğüm σ_vM [MPa]
    u_maks: np.ndarray  # (s,) mm
    en_kotu_an: float  # s
    alanlar: Mapping[float, tuple[np.ndarray, np.ndarray]]  # istenen zamanlar: (u, düğüm σ_vM)


def zincir(
    model_mek: Model,
    sicaklik: TransientResult | ThermalResult,
    T_ref: float,
    alpha,
    zamanlar: Sequence[float] | None = None,
) -> TermoMekanik:
    """Sıcaklık geçmişini statik çözüme zincirler. Ağ uyuşmazlığı, eksik alpha → ModelError."""
    raise NotImplementedError("SPEC 68b: zincir")
