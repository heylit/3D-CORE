"""
SPEC 23 — Yuvarlatma (fillet): dikey kenarlar, üst kenarlar, tüm kenarlar.

Hiçbir işlem girdi parçayı değiştirmez, her zaman yeni Part döner; delik kayıtları (Part.holes) korunur.
Birimler: mm.
"""

from __future__ import annotations

from geometry.part import Part


def fillet_vertical(part: Part, r: float) -> Part:
    """Z eksenine paralel tüm dışbükey doğrusal kenarları r yarıçapıyla yuvarlatır."""
    raise NotImplementedError("SPEC 23: fillet_vertical")


def fillet_top(part: Part, r: float) -> Part:
    """Üst yüzün (zmax) tüm kenarlarını r yarıçapıyla yuvarlatır (delik ağızları dahil)."""
    raise NotImplementedError("SPEC 23: fillet_top")


def fillet_all(part: Part, r: float) -> Part:
    """Parçanın tüm kenarlarını r yarıçapıyla yuvarlatır."""
    raise NotImplementedError("SPEC 23: fillet_all")
