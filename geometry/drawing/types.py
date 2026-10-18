"""2D çizim veri tipleri (SPEC 16). Saf numpy; koordinatlar mm."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import numpy as np

from geometry.part import Region

Layer = Literal["GORUNUR", "GIZLI", "EKSEN", "TARAMA", "OLCU"]


@dataclass(frozen=True)
class Line2D:
    p0: np.ndarray  # (2,) mm
    p1: np.ndarray  # (2,) mm
    layer: Layer


@dataclass(frozen=True)
class Arc2D:
    c: np.ndarray  # (2,) merkez, mm
    r: float  # mm
    a0: float  # derece, CCW; a0 < a1 <= a0 + 360
    a1: float  # a1 - a0 = 360 -> tam çember
    layer: Layer


@dataclass(frozen=True)
class Polyline2D:
    P: np.ndarray  # (k, 2), açık
    layer: Layer


@dataclass(frozen=True)
class Text2D:
    p: np.ndarray  # (2,) sol-alt köşe
    text: str
    h: float  # yazı boyu, mm
    angle: float  # derece
    layer: Layer


Entity = Line2D | Arc2D | Polyline2D | Text2D


@dataclass(frozen=True)
class Dimension:
    kind: Literal["yatay", "dikey", "cap"]
    p1: np.ndarray  # ölçülen 1. nokta (cap: çember merkezi)
    p2: np.ndarray  # ölçülen 2. nokta (cap: çember üstünde bir nokta)
    offset: float  # ölçü çizgisinin p1-p2'ye uzaklığı (mm, görünüş koordinatı)
    value: float  # mm, geometriden
    text: str  # format_value ile


@dataclass(frozen=True)
class View:
    name: str  # "on", "ust", "sol", "sag" veya "A-A"
    direction: str  # bakış yönü: "on", "ust", "sol", "sag"
    edges: tuple[Entity, ...]  # temizlenmiş görünen + gizli + eksen çizgileri (görünüş koordinatı)
    regions: tuple[Region, ...] = ()  # sadece kesitte: kesit yüzeyi
    hatch: tuple[Line2D, ...] = ()  # sadece kesitte
    dims: tuple[Dimension, ...] = ()

    def bbox(self) -> tuple[np.ndarray, np.ndarray]:
        """edges'in (u, v) sınır kutusu."""
        raise NotImplementedError


@dataclass(frozen=True)
class PlacedView:
    view: View
    offset: np.ndarray  # pafta = scale * görünüş + offset
    scale: float


@dataclass(frozen=True)
class Sheet:
    views: tuple[PlacedView, ...]
    extras: tuple[Entity, ...] = ()  # kesit çizgisi, etiketler (pafta koordinatı)

    def entities(self) -> list[Entity]:
        """Pafta koordinatında tüm çizim; ölçüler çizgi + metne açılmış."""
        raise NotImplementedError

    def bbox(self) -> tuple[np.ndarray, np.ndarray]:
        raise NotImplementedError
