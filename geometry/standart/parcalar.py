"""
SPEC 35 — Standart parçaların OCCT ile üretimi (basitleştirilmiş, el hesabıyla doğrulanan geometri).

Eksen yerel Z. Vida / civata: baş altı z = 0, baş z ∈ [0, k], gövde z ∈ [−L, 0].
Somun, pul, pim, rulman: alt yüz z = 0, gövde z ∈ [0, h]. Altıgenin düz kenarları X eksenine dik.
Part.name = kanonik tanım. Birimler: mm.
"""

from __future__ import annotations

from geometry.part import Part


def socket_screw(M: str, L: float) -> Part:
    """ISO 4762 imbus vida."""
    raise NotImplementedError("SPEC 35")


def hex_bolt(M: str, L: float) -> Part:
    """ISO 4017 altıgen civata."""
    raise NotImplementedError("SPEC 35")


def hex_nut(M: str) -> Part:
    """ISO 4032 altıgen somun."""
    raise NotImplementedError("SPEC 35")


def washer(M: str) -> Part:
    """ISO 7089 pul (normal seri)."""
    raise NotImplementedError("SPEC 35")


def dowel_pin(d: float, L: float) -> Part:
    """ISO 2338 silindirik pim."""
    raise NotImplementedError("SPEC 35")


def bearing(kod: str) -> Part:
    """ISO 15 sabit bilyalı rulman, zarf halka."""
    raise NotImplementedError("SPEC 35")


def parca(tanim: str) -> Part:
    """Kanonik tanımdan parça ("ISO 4762 M8x25", "ISO 15 6204" ...)."""
    raise NotImplementedError("SPEC 35")
