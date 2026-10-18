"""2D çizim veri tipleri (SPEC 16). Saf numpy; koordinatlar mm."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal

import numpy as np

from geometry.part import GeometryError, Region

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
        return entities_bbox(self.edges)


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
        from geometry.drawing.dimensions import render_dimension

        out: list[Entity] = []
        for pv in self.views:
            k, t = pv.scale, np.asarray(pv.offset, dtype=float)
            out += [transform(e, k, t) for e in pv.view.edges]
            out += [transform(e, k, t) for e in pv.view.hatch]
            for dim in pv.view.dims:
                out += render_dimension(dim, k, t)
        return out + list(self.extras)

    def bbox(self) -> tuple[np.ndarray, np.ndarray]:
        return entities_bbox(self.entities())


# ---------- yardımcılar ----------


def transform(e: Entity, k: float, t: np.ndarray) -> Entity:
    """Benzerlik dönüşümü p' = k·p + t. Yazı boyu kağıt ölçüsüdür, ölçeklenmez."""
    t = np.asarray(t, dtype=float)
    if isinstance(e, Line2D):
        return Line2D(k * e.p0 + t, k * e.p1 + t, e.layer)
    if isinstance(e, Arc2D):
        return Arc2D(k * e.c + t, k * e.r, e.a0, e.a1, e.layer)
    if isinstance(e, Polyline2D):
        return Polyline2D(k * e.P + t, e.layer)
    if isinstance(e, Text2D):
        return Text2D(k * e.p + t, e.text, e.h, e.angle, e.layer)
    raise GeometryError(f"bilinmeyen çizim varlığı: {type(e).__name__}")


def arc_points(e: Arc2D) -> np.ndarray:
    """Yayın uç noktaları ve içerdiği eksen uç noktaları (0°, 90°, 180°, 270°): sınır kutusu için yeter."""
    acilar = [e.a0, e.a1]
    k0 = math.ceil(e.a0 / 90.0)
    acilar += [90.0 * k for k in range(k0, k0 + 5) if 90.0 * k <= e.a1]
    th = np.radians(acilar)
    return e.c + e.r * np.column_stack([np.cos(th), np.sin(th)])


def entity_points(e: Entity) -> np.ndarray:
    if isinstance(e, Line2D):
        return np.array([e.p0, e.p1], dtype=float)
    if isinstance(e, Arc2D):
        return arc_points(e)
    if isinstance(e, Polyline2D):
        return np.asarray(e.P, dtype=float)
    if isinstance(e, Text2D):
        return np.asarray(e.p, dtype=float)[None, :]
    raise GeometryError(f"bilinmeyen çizim varlığı: {type(e).__name__}")


def entities_bbox(entities) -> tuple[np.ndarray, np.ndarray]:
    """Varlıkların (min, max) sınır kutusu. Boş liste → GeometryError."""
    entities = list(entities)
    if not entities:
        raise GeometryError("boş çizimin sınır kutusu yok")
    P = np.vstack([entity_points(e) for e in entities])
    return P.min(axis=0), P.max(axis=0)
