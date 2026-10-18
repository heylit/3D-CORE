"""
3D-CORE katı parça arayüzü (OCCT, build123d üzerinden).

build123d / OpenCascade SADECE bu katmanda import edilir. cam/ ve assy/ bir parçaya ihtiyaç duyduğunda
bu sınıfı kullanır, build123d'yi doğrudan değil.

Birimler: mm, mm², mm³.
"""

from __future__ import annotations

import math
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


@dataclass(frozen=True)
class Hole:
    """Parçadaki bir deliğin tasarım kaydı (CAM delme / havşa / kılavuz çevrimleri bunu okur).

    origin: giriş noktası, delik ekseninin parça yüzeyini deldiği yer. axis: birim delme yönü (malzemeye
    doğru); takım ekseni = −axis. d: matkap çapı (dişli delikte kılavuz matkabı). depth: eksen boyunca
    girişten düz dibe; boydan boyada çıkış noktasına kadar. csk_d = 0 → havşa yok; thread = "" → dişsiz.
    Kayıt geometriye göre yeniden doğrulanmaz; STEP / STL gidiş-dönüşünde taşınmaz.
    """

    origin: np.ndarray  # (3,) mm
    axis: np.ndarray  # (3,) birim
    d: float  # mm
    depth: float  # mm
    through: bool
    csk_d: float = 0.0  # mm, havşa ağız çapı
    csk_angle: float = 0.0  # derece, havşa tepe açısı
    thread: str = ""  # "M8", "M8x1"
    thread_d: float = 0.0  # mm, nominal diş çapı
    pitch: float = 0.0  # mm, hatve
    thread_depth: float = 0.0  # mm, diş derinliği

    def __post_init__(self) -> None:
        origin = np.array(self.origin, dtype=float)
        axis = np.array(self.axis, dtype=float)
        if origin.shape != (3,) or axis.shape != (3,):
            raise GeometryError(f"Delik: origin ve axis (3,) olmalı ({origin.shape}, {axis.shape})")
        sayilar = [
            self.d,
            self.depth,
            self.csk_d,
            self.csk_angle,
            self.thread_d,
            self.pitch,
            self.thread_depth,
        ]
        if not (
            np.all(np.isfinite(origin)) and np.all(np.isfinite(axis)) and all(map(math.isfinite, sayilar))
        ):
            raise GeometryError(f"Delik: değerler sonlu olmalı ({self})")
        if abs(float(np.linalg.norm(axis)) - 1.0) > 1e-9:
            raise GeometryError(f"Delik: axis birim olmalı (|axis|={np.linalg.norm(axis)})")
        if self.d <= 0 or self.depth <= 0:
            raise GeometryError(f"Delik: d > 0 ve depth > 0 olmalı (d={self.d}, depth={self.depth})")
        if self.csk_d != 0 or self.csk_angle != 0:
            if self.csk_d <= self.d or not 0 < self.csk_angle < 180:
                raise GeometryError(
                    f"Delik: havşada csk_d > d ve 0 < csk_angle < 180 olmalı ({self.csk_d}, {self.csk_angle})"
                )
        if self.thread or self.thread_d or self.pitch or self.thread_depth:
            if not self.thread or self.thread_d <= self.d or self.pitch <= 0:
                raise GeometryError(
                    f"Delik: dişte thread, thread_d > d, pitch > 0 gerekli ({self.thread}, {self.thread_d})"
                )
            if not 0 < self.thread_depth <= self.depth:
                raise GeometryError(f"Delik: 0 < thread_depth <= depth olmalı ({self.thread_depth})")
        origin.flags.writeable = False
        axis.flags.writeable = False
        object.__setattr__(self, "origin", origin)
        object.__setattr__(self, "axis", axis)


class Part:
    """Tek bir katı parça: build123d Shape (Solid / Compound) + ad + delik kayıtları."""

    def __init__(self, shape, name: str = "parca", holes=()) -> None:
        _require_occt()
        if shape is None or not shape.is_valid:
            raise GeometryError(f"Parça '{name}': geçersiz şekil")
        if shape.volume <= 0:
            raise GeometryError(f"Parça '{name}': hacim pozitif olmalı (V={shape.volume})")
        holes = tuple(holes)
        if not all(isinstance(h, Hole) for h in holes):
            raise GeometryError(f"Parça '{name}': holes sadece Hole kayıtları içermeli")
        self.shape = shape
        self.name = name
        self._holes = holes

    @property
    def holes(self) -> tuple[Hole, ...]:
        """Delik kayıtları, eklenme sırasıyla (değiştirilemez)."""
        return self._holes

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
