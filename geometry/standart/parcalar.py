"""
SPEC 35 — Standart parçaların OCCT ile üretimi (basitleştirilmiş, el hesabıyla doğrulanan geometri).

Eksen yerel Z. Vida / civata: baş altı z = 0, baş z ∈ [0, k], gövde z ∈ [−L, 0].
Somun, pul, pim, rulman: alt yüz z = 0, gövde z ∈ [0, h]. Altıgenin düz kenarları X eksenine dik.
Diş, pah, köşe yuvarlatması, lokma dibi konisi yok; rulman dolu halka (zarf). Part.name = kanonik tanım.
Birimler: mm.
"""

from __future__ import annotations

import math

import build123d as bd

from geometry.part import GeometryError, Part
from geometry.standart.tablo import ISO15, ISO4017, ISO4032, ISO4762, ISO7089, ayristir, boyut
from geometry.standart.tablo import tanim as _tanim


def _silindir(r: float, z0: float, z1: float):
    """Eksen Z, yarıçap r, z ∈ [z0, z1] silindir."""
    align = (bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN)
    return bd.Pos(0, 0, z0) * bd.Cylinder(r, z1 - z0, align=align)


def _altigen(s: float, z0: float, z1: float):
    """Anahtar ağzı s düzgün altıgen prizma, z ∈ [z0, z1]; köşeler ±Y'de (düz kenarlar X'e dik)."""
    R = s / math.sqrt(3)  # köşe yarıçapı
    noktalar = [
        (R * math.cos(math.radians(90 + 60 * i)), R * math.sin(math.radians(90 + 60 * i))) for i in range(6)
    ]
    taban = bd.Pos(0, 0, z0) * bd.Polygon(*noktalar, align=None)
    return bd.extrude(taban, amount=z1 - z0)


def _part(shape, ad: str) -> Part:
    """OCCT sonucunu tek katı Part'a çevirir; hatayı GeometryError'a sarar."""
    try:
        if isinstance(shape, bd.Compound | bd.ShapeList):
            solids = list(shape.solids())
            if len(solids) == 1:
                shape = solids[0]
        return Part(shape, name=ad)
    except GeometryError:
        raise
    except Exception as e:  # OCCT istisnası
        raise GeometryError(f"{ad}: OCCT parça kuramadı ({e})") from e


def socket_screw(M: str, L: float) -> Part:
    """ISO 4762 imbus vida: baş silindiri − altıgen lokma (derinlik t) + gövde."""
    ad = _tanim("4762", M=M, L=L)
    d_k, k, s, t, _, _ = ISO4762[M]
    d = boyut(M)
    govde = _silindir(d / 2, -L, 0.0) + _silindir(d_k / 2, 0.0, k)
    return _part(govde - _altigen(s, k - t, k), ad)


def hex_bolt(M: str, L: float) -> Part:
    """ISO 4017 altıgen civata: altıgen baş + gövde."""
    ad = _tanim("4017", M=M, L=L)
    s, k, _, _ = ISO4017[M]
    return _part(_silindir(boyut(M) / 2, -L, 0.0) + _altigen(s, 0.0, k), ad)


def hex_nut(M: str) -> Part:
    """ISO 4032 altıgen somun: altıgen prizma − nominal çaplı delik."""
    ad = _tanim("4032", M=M)
    s, m = ISO4032[M]
    return _part(_altigen(s, 0.0, m) - _silindir(boyut(M) / 2, -1.0, m + 1.0), ad)


def washer(M: str) -> Part:
    """ISO 7089 pul (normal seri): halka d₁ / d₂, kalınlık h."""
    ad = _tanim("7089", M=M)
    d1, d2, h = ISO7089[M]
    return _part(_silindir(d2 / 2, 0.0, h) - _silindir(d1 / 2, -1.0, h + 1.0), ad)


def dowel_pin(d: float, L: float) -> Part:
    """ISO 2338 silindirik pim, z ∈ [0, L]."""
    ad = _tanim("2338", d=d, L=L)
    return _part(_silindir(d / 2, 0.0, L), ad)


def bearing(kod: str) -> Part:
    """ISO 15 sabit bilyalı rulman, zarf halka d / D, genişlik B."""
    ad = _tanim("15", kod=kod)
    d, D, B = ISO15[kod]
    return _part(_silindir(D / 2, 0.0, B) - _silindir(d / 2, -1.0, B + 1.0), ad)


def parca(tanim: str) -> Part:
    """Kanonik tanımdan parça ("ISO 4762 M8x25", "ISO 15 6204" ...)."""
    std, olcu = ayristir(tanim)
    if std == "4762":
        return socket_screw(olcu["M"], olcu["L"])
    if std == "4017":
        return hex_bolt(olcu["M"], olcu["L"])
    if std == "4032":
        return hex_nut(olcu["M"])
    if std == "7089":
        return washer(olcu["M"])
    if std == "2338":
        return dowel_pin(olcu["d"], olcu["L"])
    return bearing(olcu["kod"])
