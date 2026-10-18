"""
Parçadan (geometry.part.Part) gmsh ile dört düğümlü tetrahedron ağı -> core.model.Model.

Teori: specs/12-gmsh.md
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from core.model import Material, Model


@dataclass(frozen=True)
class Refine:
    """Yerel inceltme küresi [mm]: içinde eleman boyu h, dışında bir yarıçap boyunca genel boya geçiş."""

    center: tuple[float, float, float]
    radius: float
    h: float

    def __post_init__(self) -> None:
        raise NotImplementedError("SPEC 12: Refine doğrulaması")


def tet_mesh(
    part,
    h: float,
    material: Material,
    *,
    refine: Sequence[Refine] = (),
    max_nodes: int = 200_000,
) -> Model:
    """Parçayı tet4 ağına çevirir: Model(dim=3), düğümler 1..n, elemanlar 1..m, hepsi det C > 0."""
    raise NotImplementedError("SPEC 12: tet_mesh")
