"""
3D-CORE katı parça arayüzü (OCCT, build123d üzerinden).

build123d / OpenCascade SADECE bu katmanda import edilir. cam/ ve assy/ bir parçaya ihtiyaç duyduğunda
bu sınıfı kullanır, build123d'yi doğrudan değil.

Birimler: mm, mm², mm³.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np

try:
    import build123d as bd
except ImportError:  # pragma: no cover - kurulum yoksa anlamlı hata ver
    bd = None


class GeometryError(ValueError):
    """Geçersiz veya okunamayan geometri."""


def _require_occt() -> None:
    if bd is None:
        raise GeometryError('build123d kurulu değil: pip install -e ".[cad]"')


@dataclass(frozen=True)
class Region:
    """Düzlemsel bir kesitte tek bağlantılı malzeme bölgesi (XY koordinatı, mm).

    outer: dış sınır, (k, 2), saat yönünün tersine (CCW, işaretli alan > 0).
    holes: iç sınırlar (delik / cep), her biri (k, 2), saat yönünde (CW).
    Çokgenler kapalıdır ama son nokta ilk noktayı tekrar etmez.
    """

    outer: np.ndarray
    holes: tuple[np.ndarray, ...] = ()


@dataclass(frozen=True)
class PlanarFace:
    """Parçanın düzlemsel bir yüzü. normal: birim, malzemeden dışa bakar. origin: yüzün ağırlık merkezi."""

    index: int  # OCCT yüz sırası; düzlemsel ve silindirik yüzlerde ortak, aynı parçada kararlı
    origin: np.ndarray  # (3,) mm
    normal: np.ndarray  # (3,) birim
    area: float  # mm²


@dataclass(frozen=True)
class CylindricalFace:
    """Parçanın silindirik bir yüzü (tam veya kısmi).

    Eksen: origin + s · axis, s ∈ [0, length]; axis birimdir, işareti OCCT'nin yüzey tanımından gelir
    (delik "giriş yönü" anlamı taşımaz). angle: yüzeyin eksen etrafında taradığı açı [derece]; 360 → tam
    silindir. concave=True → malzeme yüzeyin dışında (delik, cep köşesi); False → dış yüzey (mil, boss).
    """

    index: int
    origin: np.ndarray  # (3,) mm, eksen üzerinde yüzeyin başladığı nokta
    axis: np.ndarray  # (3,) birim
    radius: float  # mm
    length: float  # mm, eksen boyunca
    angle: float  # derece, (0, 360]
    concave: bool
    area: float  # mm²


class Part:
    """Tek bir katı parça: build123d Shape (Solid / Compound) + ad."""

    def __init__(self, shape, name: str = "parca") -> None:
        _require_occt()
        if shape is None or not shape.is_valid:
            raise GeometryError(f"Parça '{name}': geçersiz şekil")
        if shape.volume <= 0:
            raise GeometryError(f"Parça '{name}': hacim pozitif olmalı (V={shape.volume})")
        self.shape = shape
        self.name = name

    @property
    def volume(self) -> float:
        return float(self.shape.volume)

    @property
    def area(self) -> float:
        return float(self.shape.area)

    @property
    def center_of_mass(self) -> np.ndarray:
        c = self.shape.center(bd.CenterOf.MASS)
        return np.array([c.X, c.Y, c.Z])

    @property
    def bbox(self) -> tuple[np.ndarray, np.ndarray]:
        b = self.shape.bounding_box()
        return np.array([b.min.X, b.min.Y, b.min.Z]), np.array([b.max.X, b.max.Y, b.max.Z])

    def to_step(self, path: str | Path) -> None:
        if not bd.export_step(self.shape, str(path)):
            raise GeometryError(f"STEP yazılamadı: {path}")

    @classmethod
    def from_step(cls, path: str | Path, name: str | None = None) -> Part:
        _require_occt()
        path = Path(path)
        if not path.is_file():
            raise GeometryError(f"STEP dosyası yok: {path}")
        return cls(bd.import_step(str(path)), name=name or path.stem)

    def to_stl(self, path: str | Path, tolerance: float = 0.01) -> None:
        if not bd.export_stl(self.shape, str(path), tolerance=tolerance):
            raise GeometryError(f"STL yazılamadı: {path}")

    # ---------- CAM / montaj sorguları (inceleme Y5) ----------

    def section_z(self, z: float, tol: float = 0.01) -> list[Region]:
        """z = sabit düzlemiyle kesit: malzemenin bulunduğu bölgeler (XY çokgenleri).

        Eğriler en çok tol [mm] kiriş sapmasıyla çokgene çevrilir. Düzlem parçayı kesmiyorsa boş liste.
        z bir düzlemsel yüzün tam üstündeyse OCCT o düzlemdeki malzemeyi döndürür; cep tabanı gibi
        seviyelerde kararsızlık istemiyorsanız z'yi küçük bir payla kaydırın.
        """
        from geometry.query import section_z

        return section_z(self, z, tol)

    def planar_faces(self) -> list[PlanarFace]:
        """Tüm düzlemsel yüzler (dışa bakan normal ile)."""
        from geometry.query import planar_faces

        return planar_faces(self)

    def cylindrical_faces(self) -> list[CylindricalFace]:
        """Tüm silindirik yüzler (delikler concave=True)."""
        from geometry.query import cylindrical_faces

        return cylindrical_faces(self)

    def mesh(self, tol: float = 0.01) -> tuple[np.ndarray, np.ndarray]:
        """Kapalı, dışa yönlü üçgen ağı: köşeler V (n, 3), üçgenler T (m, 3). tol: kiriş sapması [mm]."""
        from geometry.mesh import tessellate

        return tessellate(self, tol)
