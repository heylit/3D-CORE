"""
Montajda girişim, temas ve boşluk kontrolü (SPEC 09).

Her yaprak çifti için önce kesişim hacmi V∩, sonra sınırlar arası uzaklık d:
    V∩ > tol_v                → GIRISIM
    d ≤ tol_d                 → TEMAS
    tol_d < d < clearance     → DAR
    aksi halde                → serbest (raporlanmaz)
Kaba eleme: taşınmış AABB'ler x eksenine göre sıralanıp süpürülür (Ericson, Real-Time Collision
Detection, Bölüm 7.5).

Saf Python + numpy: parça yalnızca Part arayüzünden (bbox, moved, common, distance, volume,
center_of_mass) kullanılır.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

import numpy as np

from assy.model import Node

if TYPE_CHECKING:
    from geometry.part import Part


class ClashKind(StrEnum):
    GIRISIM = "girisim"
    TEMAS = "temas"
    DAR = "dar"


@dataclass(frozen=True)
class Clash:
    a: str  # yaprak yolu (SPEC 07 walk biçimi), walk sırasında önce gelen
    b: str
    kind: ClashKind
    volume: float  # mm³; GIRISIM dışında 0
    distance: float  # mm; GIRISIM'de 0
    center: np.ndarray | None  # GIRISIM: kesişimin ağırlık merkezi (dünya); diğerleri None
    points: tuple[np.ndarray, np.ndarray] | None  # TEMAS / DAR: en yakın noktalar (dünya, a'da, b'de)


def world_aabb(part: Part, T: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Yerel bbox'ın 8 köşesi T ile taşınıp min / max alınmış dünya kutusu."""
    raise NotImplementedError("SPEC 09: assy.girisim.world_aabb")


def check(
    root: Node,
    parts: Mapping[str, Part],
    clearance: float = 0.0,
    tol_v: float = 1e-6,
    tol_d: float = 1e-6,
    scope: str = "",
    across: bool = False,
    ignore: Iterable[tuple[str, str]] = (),
) -> list[Clash]:
    """scope altındaki yaprak çiftlerinde girişim / temas / dar boşluk listesi (walk sırasıyla)."""
    raise NotImplementedError("SPEC 09: assy.girisim.check")


def gap(root: Node, parts: Mapping[str, Part], a: str, b: str) -> tuple[float, np.ndarray, np.ndarray]:
    """İki yaprak arasında dünya koordinatında en küçük uzaklık ve en yakın noktalar."""
    raise NotImplementedError("SPEC 09: assy.girisim.gap")
