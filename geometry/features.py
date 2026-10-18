"""
SPEC 02 — Kodla basit parça: blok, silindir, delik, cep, pah.

Koordinat kuralı: blok min köşesi orijinde; "üst yüz" = zmax düzlemi; delik ve cep üstten −Z yönünde.
Hiçbir işlem girdi parçayı değiştirmez, her zaman yeni Part döner. Birimler: mm.
"""

from __future__ import annotations

from geometry.part import Part


def block(a: float, b: float, c: float, name: str = "blok") -> Part:
    """a × b × c blok, x ∈ [0,a], y ∈ [0,b], z ∈ [0,c]."""
    raise NotImplementedError


def cylinder(r: float, h: float, name: str = "silindir") -> Part:
    """Yarıçap r, boy h silindir; taban merkezi orijinde, eksen +Z."""
    raise NotImplementedError


def hole(part: Part, x: float, y: float, d: float, depth: float | None = None) -> Part:
    """Üst yüzden −Z yönünde çap d delik, eksen (x, y). depth=None → boydan boya."""
    raise NotImplementedError


def pocket(part: Part, x: float, y: float, w: float, l: float, depth: float, r: float = 0.0) -> Part:  # noqa: E741
    """Üstten w × l dikdörtgen cep, merkez (x, y), köşe yarıçapı r, derinlik depth."""
    raise NotImplementedError


def chamfer_top(part: Part, d: float) -> Part:
    """Üst yüzün (zmax) tüm kenarlarına eşit mesafeli d pahı."""
    raise NotImplementedError
