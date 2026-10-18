"""
SPEC 06 — Drop-cutter: takımı Z boyunca üçgen ağına değene kadar indirme.

Küresel (BALL) ve düz (FLAT, corner_r = 0) uç. CL = takım ucu (en alt nokta).
Birimler: mm. İskelet: gövdeler henüz yazılmadı.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from cam.model import Tool

TOL = 1e-9  # mm
NZ_TOL = 1e-12  # bundan küçük |n_z| dik üçgen sayılır


@dataclass
class TriMesh:
    """Üçgen ağı: köşeler V (n, 3) [mm], üçgenler T (m, 3) indeks."""

    V: np.ndarray
    T: np.ndarray

    def __post_init__(self) -> None:
        raise NotImplementedError("SPEC 06: TriMesh doğrulaması")

    def bbox(self) -> tuple[np.ndarray, np.ndarray]:
        raise NotImplementedError("SPEC 06: TriMesh.bbox")

    @classmethod
    def from_part(cls, part, tol: float = 0.01) -> TriMesh:
        """geometry.part.Part.mesh(tol) ile ağ."""
        raise NotImplementedError("SPEC 06: TriMesh.from_part")


def drop(mesh: TriMesh, tool: Tool, xy: np.ndarray, floor: float | None = None) -> np.ndarray:
    """Her (x, y) için z_CL = max(köşe, yüz, kenar testleri); floor verilmişse max(z_CL, floor)."""
    raise NotImplementedError("SPEC 06: drop")


def drop_one(mesh: TriMesh, tool: Tool, x: float, y: float, floor: float | None = None) -> float:
    """Tek nokta için drop."""
    raise NotImplementedError("SPEC 06: drop_one")
