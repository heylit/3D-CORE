"""
SPEC 15 — Görüntüleyici sahne verisi (saf numpy, pyvista gerektirmez).

Takım yolunu (G2/G3 yayları kiriş sapması ≤ tol ile çokgene çevrilerek) çizgilere, montajı dünya
koordinatındaki üçgen ağlarına, ham malzemeyi kutu kenarlarına çevirir. Yalnızca arayüzleri kullanır:
geometry.part.Part, cam.model, assy.model.

Birimler: mm.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from assy.model import Assembly
from cam.model import Stock, Toolpath


class VizError(ValueError):
    """Çizilemeyen girdi (boş takım yolu, eksik parça, geçersiz tolerans / görünüm...)."""


# Montaj bileşen renkleri: sırayla, döngüsel.
PALETTE: tuple[str, ...] = (
    "steelblue",
    "darkorange",
    "seagreen",
    "firebrick",
    "mediumpurple",
    "sienna",
    "orchid",
    "gray",
)


@dataclass(frozen=True)
class ComponentMesh:
    """Bir bileşenin dünya koordinatındaki ağı. V (n, 3) mm, T (m, 3) üçgen indeksleri, color: PALETTE'ten."""

    name: str
    V: np.ndarray
    T: np.ndarray
    color: str


def toolpath_polyline(tp: Toolpath, tol: float = 0.01) -> tuple[np.ndarray, np.ndarray]:
    """Noktalar P (k+1, 3) (ilk nokta tp.start) ve parça tipleri kinds (k,) (MoveType, dtype object)."""
    raise NotImplementedError("SPEC 15: toolpath_polyline")


def split_rapid_feed(P: np.ndarray, kinds: np.ndarray) -> tuple[list[np.ndarray], list[np.ndarray]]:
    """Art arda aynı türden parçaları birleştirir: (hızlı çizgiler, kesme çizgileri), her biri (m, 3)."""
    raise NotImplementedError("SPEC 15: split_rapid_feed")


def assembly_meshes(assy: Assembly, parts: dict, tol: float = 0.01) -> list[ComponentMesh]:
    """Her bileşenin ağı dünya koordinatında (V' = V Rᵀ + t). parts: Component.part → Part."""
    raise NotImplementedError("SPEC 15: assembly_meshes")


def stock_box(stock: Stock) -> tuple[np.ndarray, np.ndarray]:
    """Ham malzeme kutusunun 8 köşesi (8, 3) ve 12 kenarı (12, 2) indeks."""
    raise NotImplementedError("SPEC 15: stock_box")
