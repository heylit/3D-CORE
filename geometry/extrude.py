"""
SPEC 26 — eskiz bölgesi + düzlem → OCCT katı: ekstrüzyon, ekleme, kesim; yüz düzlemi ve kenarları.

Bölgeler `sketch.model.SketchRegion` (uv, yaylar tam yay). Düzlem `sketch.model.Plane`:
P = origin + u·xdir + v·ydir. Yay ve daireler gerçek daire kenarıdır (çokgen yaklaşımı yok).
Bu modül `sketch`'ten yalnızca `sketch.model`'i import eder (K13).
"""

from __future__ import annotations

from geometry.part import Part
from sketch.model import Plane, SegArc, SegLine, SketchRegion

Seg = SegLine | SegArc


def extrude(
    regions: list[SketchRegion], plane: Plane, distance: float, symmetric: bool = False, name: str = "govde"
) -> Part:
    """Bölgeleri düzlem normali yönünde `distance` kadar (işaretli) çeker; simetrikte iki yana distance/2.

    Boş bölge listesi, distance = 0, sonsuz değer → GeometryError.
    """
    raise NotImplementedError("SPEC 26: extrude")


def extrude_add(
    part: Part, regions: list[SketchRegion], plane: Plane, distance: float, symmetric: bool = False
) -> Part:
    """Ekstrüzyonu parçaya ekler; sonuç tek katı olmalı, değmiyorsa GeometryError ("ayrık katı").
    Girdi parça değişmez; Part.holes kayıtları korunur."""
    raise NotImplementedError("SPEC 26: extrude_add")


def extrude_cut(part: Part, regions: list[SketchRegion], plane: Plane, depth: float | None) -> Part:
    """Bölgeleri −normal yönünde `depth` kadar keser; None = boydan boya (+PAY üstten, köşegen + PAY).
    Malzeme kaldırmıyorsa (ΔV ≤ 1e-9 mm³) GeometryError. Girdi değişmez; kesim delik kaydı üretmez."""
    raise NotImplementedError("SPEC 26: extrude_cut")


def face_plane(part: Part, index: int) -> Plane:
    """Düzlemsel yüzün düzlemi: origin ağırlık merkezi, normal dışa, xdir dünya X'in izdüşümü
    (|izdüşüm| < 1e-6 ise dünya Y). Düzlemsel olmayan / bilinmeyen index → GeometryError."""
    raise NotImplementedError("SPEC 26: face_plane")


def face_outline(part: Part, index: int) -> list[tuple[Seg, ...]]:
    """Yüzün kenar döngüleri face_plane uv'sinde (SegLine / SegArc; tam daire tek SegArc).
    Doğru ve daire dışı kenar → GeometryError."""
    raise NotImplementedError("SPEC 26: face_outline")
