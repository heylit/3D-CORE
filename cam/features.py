"""
SPEC 27 — İşleme özelliği tanıma (freze, 3 eksen, üstten −Z takım yönü).

Parça yatay yüz seviyeleri arasında dilimlere bölünür; her dilim tek bir
`Part.section_z` kesitiyle tanımlanır.
Cep = kesitte iç halka, açık bölge = zarf dikdörtgeni ile dış halkalar arası boşluk, delik = eksenli silindir.
Yaylar dik silindirik yüzlerin tam merkez ve yarıçapıyla geri kurulur. 2.5D olmayan parça → CamError.
Yalnızca geometry/part.py arayüzü kullanılır. Birimler: mm, derece.
"""

from __future__ import annotations

from dataclasses import dataclass

from cam.model import Stock
from cam.profile import Profile, Region
from geometry.part import Hole, Part


@dataclass(frozen=True)
class FaceFeature:
    """Yüz alma: stok üstünden parça üstüne (z) kadar, zarf dikdörtgeni boyunca."""

    z: float  # yüz alma son seviyesi (parça üstü)
    depth: float  # stock.zmax − z
    boundary: Profile  # zarf dikdörtgeni E (CCW)


@dataclass(frozen=True)
class PocketFeature:
    """Kapalı cep: dış halka + adalar, [z_bottom, z_top] aralığında aynı boşluk imzası."""

    region: Region  # dış = cep halkası, holes = adalar
    z_top: float
    z_bottom: float
    r_corner: float  # bölgeden bakınca dışbükey en küçük köşe yarıçapı; keskin köşe → 0.0, köşe yok → inf

    @property
    def max_tool_d(self) -> float:
        """Köşelere tam giren en büyük takım çapı: 2 · r_corner."""
        raise NotImplementedError("SPEC 27: uygulanmadı")


@dataclass(frozen=True)
class OpenFeature:
    """Açık bölge (basamak, dış kontur): boşluk = boundary ∖ ∪ islands."""

    boundary: Profile  # E
    islands: tuple[Profile, ...]
    z_top: float
    z_bottom: float


@dataclass(frozen=True)
class HoleFeature:
    """Delik: kayıttan ("kayit") ya da silindirden tanınmış ("tanima")."""

    hole: Hole
    source: str  # "kayit" | "tanima"

    @property
    def top_access(self) -> bool:
        """Delme yönü −Z mi (üstten delinebilir)?"""
        raise NotImplementedError("SPEC 27: uygulanmadı")


@dataclass(frozen=True)
class Features:
    """Tanınan özellikler, SPEC 27'deki sıralarla."""

    faces: tuple[FaceFeature, ...]  # 0 veya 1 eleman
    pockets: tuple[PocketFeature, ...]  # z_top azalan, z_bottom azalan, dış halkanın ilk köşesi (x, y) artan
    opens: tuple[OpenFeature, ...]  # z_top azalan
    holes: tuple[HoleFeature, ...]  # önce kayıtlılar, sonra tanınanlar


def recognize(
    part: Part, stock: Stock | None = None, tol: float = 1e-3, hole_d_max: float = 20.0
) -> Features:
    """Parçadan yüz alma, cep, açık bölge ve delik özelliklerini çıkarır (SPEC 27 §1–8)."""
    raise NotImplementedError("SPEC 27: uygulanmadı")
