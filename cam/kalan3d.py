"""
SPEC 39 — 3B kalan malzeme: kalan kalınlık, bölgeler, girme derinliği ve kalan malzeme süzgeci.

Durum (state) SPEC 05'in ZMap'i ya da DexelMap'idir; bu modül yalnız okur. Süzgeç bir 3 eksen
yolunun (SPEC 03, 06, 06b) malzemeye t_min'den derin girmeyen kesme hareketlerini atar ve koşular
arasına güvenli bağlantı kurar. rest_finish / rest_rough SPEC 06 finish / rough yolunu süzer.

Birimler: mm, mm/dk.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from cam.dropcutter import TriMesh
from cam.model import Move, Stock, Tool, Toolpath
from cam.ops3d import Raster
from cam.sim import DexelMap, ZMap

State = ZMap | DexelMap


def rest_thickness(state: State, part_z: np.ndarray | None = None, allowance: float = 0.0) -> np.ndarray:
    """Hücre başına düşey kalan kalınlık t(q), şekil (ny, nx)."""
    raise NotImplementedError("SPEC 39: rest_thickness")


@dataclass
class RestRegion:
    """Kalan malzeme bölgesi: hücreler [i, j], hacim, en kalın nokta ve XY sınır kutusu."""

    cells: np.ndarray
    volume: float
    t_max: float
    at: tuple[float, float, float]
    bbox: tuple[float, float, float, float]


def rest_regions(state: State, t: np.ndarray, t_min: float) -> list[RestRegion]:
    """t > t_min maskesinin 8 komşulu bileşenleri; hacme göre azalan sırada."""
    raise NotImplementedError("SPEC 39: rest_regions")


def engagement(
    tool: Tool, p0: tuple[float, float, float], move: Move, state: State, arc_tol: float = 1e-3
) -> float:
    """Hareketin durumdan kaldıracağı en büyük hücre boyu g_k [mm]; durum değişmez."""
    raise NotImplementedError("SPEC 39: engagement")


@dataclass
class RestPath:
    """Süzgeç sonucu: süzülmüş yol (yoksa None), son durum, tutulan hareket indeksleri, kaldırılan hacim."""

    toolpath: Toolpath | None
    state: State
    kept: list[int]
    removed: float


def rest_filter(
    path: Toolpath,
    state: State,
    t_min: float = 0.02,
    z_safe: float | None = None,
    clearance: float = 1.0,
    plunge_feed: float | None = None,
    arc_tol: float = 1e-3,
) -> RestPath:
    """Sıralı kalan malzeme süzgeci (SPEC 39 Teori)."""
    raise NotImplementedError("SPEC 39: rest_filter")


def rest_finish(
    mesh: TriMesh,
    tool: Tool,
    r: Raster,
    state: State,
    t_min: float = 0.02,
    floor: float | None = None,
) -> RestPath:
    """SPEC 06 finish yolu + kalan malzeme süzgeci."""
    raise NotImplementedError("SPEC 39: rest_finish")


def rest_rough(
    mesh: TriMesh,
    stock: Stock,
    tool: Tool,
    r: Raster,
    a_p: float,
    z_bottom: float,
    state: State,
    allowance: float = 0.0,
    t_min: float = 0.02,
) -> RestPath:
    """SPEC 06 rough yolu + kalan malzeme süzgeci."""
    raise NotImplementedError("SPEC 39: rest_rough")
