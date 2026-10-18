"""
Malzeme listesi (BOM), montaj kütlesi ve ağırlık merkezi (SPEC 07).

Parça kütlesi m = ρ V (ρ [t/mm³], V [mm³], m [t]).
Ağırlık merkezi: x̄ = Σ m_i (R_i c_i + t_i) / Σ m_i   (Beer & Johnston, Statics, Bölüm 5)

Saf Python + numpy: parça yalnızca `.volume` ve `.center_of_mass` özniteliklerinden okunur.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from assy.model import Node
    from geometry.part import Part


@dataclass(frozen=True)
class BomLine:
    item: str  # parça kimliği veya alt montaj tanımı
    kind: str  # "parca" | "montaj"
    qty: int
    unit_mass: float | None  # t; kütle verilmediyse None
    total_mass: float | None  # qty · unit_mass


def unit_masses(parts: Mapping[str, Part], rho: float | Mapping[str, float]) -> dict[str, float]:
    """m = ρ · part.volume, parça kimliği başına."""
    raise NotImplementedError("SPEC 07: unit_masses")


def bom(root: Node, unit_mass: Mapping[str, float] | None = None, flat: bool = True) -> list[BomLine]:
    """flat=True: tüm yapraklar parça kimliğine göre; flat=False: kökün doğrudan çocukları tanıma göre."""
    raise NotImplementedError("SPEC 07: bom")


def total_mass(root: Node, unit_mass: Mapping[str, float]) -> float:
    """M = Σ q_p m_p."""
    raise NotImplementedError("SPEC 07: total_mass")


def mass_center(root: Node, parts: Mapping[str, Part], unit_mass: Mapping[str, float]) -> np.ndarray:
    """Montaj ağırlık merkezi x̄ (3,), dünya koordinatında."""
    raise NotImplementedError("SPEC 07: mass_center")
