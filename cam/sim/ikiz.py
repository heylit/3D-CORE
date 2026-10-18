"""
SPEC 39 — İşlenmiş parça ikizi: simüle edilen durumdan kapalı ağ (kolon / yüzey), ikili STL ve
CAD parçasına göre işaretli sapma haritası (3B nokta–üçgen uzaklığı).

SPEC 05 dosyalarını değiştirmez; `cam.sim.ikiz` olarak içe aktarılır.

Birimler: mm.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np

from cam.sim.dexel import DexelMap
from cam.sim.zmap import ZMap

State = ZMap | DexelMap


@dataclass
class TwinMesh:
    """İkiz ağı: köşeler V (n, 3), üçgenler T (m, 3), üst yüz üçgeninin hücresi face_cell (m,), aksi −1."""

    V: np.ndarray
    T: np.ndarray
    face_cell: np.ndarray

    def volume(self) -> float:
        raise NotImplementedError("SPEC 39: TwinMesh.volume")

    def is_closed(self) -> bool:
        raise NotImplementedError("SPEC 39: TwinMesh.is_closed")

    def to_stl(self, path: str | Path, name: str = "ikiz") -> None:
        raise NotImplementedError("SPEC 39: TwinMesh.to_stl")


def twin_mesh(state: State, mode: str = "kolon") -> TwinMesh:
    """Durumdan kapalı ağ; mode "kolon" (kesin hacim) ya da "yuzey" (yalnız ZMap, görüntü)."""
    raise NotImplementedError("SPEC 39: twin_mesh")


def mesh_volume(V: np.ndarray, T: np.ndarray) -> float:
    """Diverjans teoremi: Σ v₀·(v₁ × v₂) / 6."""
    raise NotImplementedError("SPEC 39: mesh_volume")


def write_stl(path: str | Path, V: np.ndarray, T: np.ndarray, name: str = "ikiz") -> None:
    """İkili STL yazar (80 bayt başlık, uint32 sayı, üçgen başına 50 bayt, little-endian)."""
    raise NotImplementedError("SPEC 39: write_stl")


def point_triangle_distance(p: np.ndarray, a: np.ndarray, b: np.ndarray, c: np.ndarray) -> np.ndarray:
    """Noktalardan (k, 3) tek üçgene kesin uzaklık (Ericson 5.1.5)."""
    raise NotImplementedError("SPEC 39: point_triangle_distance")


def point_mesh_distance(p: np.ndarray, V: np.ndarray, T: np.ndarray) -> np.ndarray:
    """Noktalardan (k, 3) ağa en kısa uzaklık."""
    raise NotImplementedError("SPEC 39: point_mesh_distance")


@dataclass
class Deviation:
    """İşaretli sapma s (+ fazlalık, − çakma), düşey fark dz, ölçülen hücreler ve özet."""

    s: np.ndarray
    dz: np.ndarray
    measured: np.ndarray
    max_excess: float
    max_gouge: float
    rms: float

    def bands(self, edges: list[float]) -> np.ndarray:
        raise NotImplementedError("SPEC 39: Deviation.bands")

    def within(self, lo: float, hi: float) -> bool:
        raise NotImplementedError("SPEC 39: Deviation.within")


def deviation(state: State, V: np.ndarray, T: np.ndarray, part_z: np.ndarray | None = None) -> Deviation:
    """CAD ağına göre hücre başına işaretli sapma haritası."""
    raise NotImplementedError("SPEC 39: deviation")
