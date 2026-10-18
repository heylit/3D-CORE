"""
Montaj sırası ve demontaj yolu (SPEC 36).

Sökerek montaj: tam montajdan her adımda bir birim, kalan birimlere girmeden tek bir doğrusal ötelemeyle
sökülür; geriye taban kalır. Montaj sırası demontaj sırasının tersidir.
    j, i'yi d yönünde engeller  ⇔  ∃ s > 0 :  V((i + s d) ∩ j) > tol_v
Kaynak: Wilson & Latombe, "Geometric reasoning about mechanical assembly", Artificial Intelligence 71, 1994.

Saf Python + numpy: parça yalnızca Part arayüzünden (bbox, moved, common, volume) kullanılır.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np

from assy.model import Assembly, Node

if TYPE_CHECKING:
    from geometry.part import Part

DIRECTIONS: tuple[np.ndarray, ...] = tuple(
    np.array(v, dtype=float) for v in [(0, 0, 1), (0, 0, -1), (1, 0, 0), (-1, 0, 0), (0, 1, 0), (0, -1, 0)]
)


@dataclass(frozen=True)
class Step:
    """Montaj sırasında bir adım. Taban: direction None, distance 0, T_out = T."""

    path: str  # birim yolu (SPEC 07 walk biçimi)
    leaves: tuple[str, ...]  # birimdeki yaprak yolları, walk sırasıyla
    direction: np.ndarray | None  # sökme yönü d (birim, dünya); montajda birim −d yönünde gelir
    distance: float  # s_çık, mm
    T: np.ndarray  # birimin yerindeki dünya dönüşümü
    T_out: np.ndarray  # Tr(distance · d) · T


def sequence(
    root: Node,
    parts: Mapping[str, Part],
    base: str | None = None,
    directions: Sequence = DIRECTIONS,
    *,
    scope: str = "",
    units: str = "yaprak",
    ignore: Iterable[tuple[str, str]] = (),
    step: float | None = None,
    eps: float = 0.01,
    tol_v: float = 1e-6,
    pay: float = 5.0,
) -> list[Step]:
    """Montaj sırası (taban başta). Demontaj sırası: reversed(...)'ın tabandan önceki kısmı."""
    raise NotImplementedError("SPEC 36: sequence")


def blocking(
    root: Node,
    parts: Mapping[str, Part],
    directions: Sequence = DIRECTIONS,
    *,
    scope: str = "",
    units: str = "yaprak",
    ignore: Iterable[tuple[str, str]] = (),
    step: float | None = None,
    eps: float = 0.01,
    tol_v: float = 1e-6,
) -> list[tuple[np.ndarray, set[tuple[str, str]]]]:
    """Tekilleştirilmiş her yön için (d, {(i, j) : j, i'yi d yönünde engeller})."""
    raise NotImplementedError("SPEC 36: blocking")


def mate_directions(assy: Assembly) -> list[np.ndarray]:
    """Kısıtlardan aday yönler (dünya): CONCENTRIC ekseni, düzlem–düzlem normali; her biri önce +, sonra −."""
    raise NotImplementedError("SPEC 36: mate_directions")
