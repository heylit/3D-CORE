"""
3D-CORE katı parça arayüzü (OCCT, build123d üzerinden).

build123d / OpenCascade SADECE bu katmanda import edilir. cam/ ve assy/ bir parçaya ihtiyaç duyduğunda
bu sınıfı kullanır, build123d'yi doğrudan değil.

Birimler: mm, mm², mm³.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, fields
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
    girişten düz dibe; boydan boyada çıkış noktasına kadar. csk_d = 0 → havşa yok; cbore_d = 0 → lamba
    yok; thread = "" → dişsiz. Havşa ve lamba aynı delikte olamaz.
    Kayıt geometriye göre yeniden doğrulanmaz; STEP / STL gidiş-dönüşünde taşınmaz.
    """

    origin: np.ndarray  # (3,) mm
    axis: np.ndarray  # (3,) birim
    d: float  # mm
    depth: float  # mm
    through: bool
    csk_d: float = 0.0  # mm, havşa ağız çapı
    csk_angle: float = 0.0  # derece, havşa tepe açısı
    cbore_d: float = 0.0  # mm, lamba çapı
    cbore_depth: float = 0.0  # mm, lamba derinliği (girişten eksen boyunca)
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
            self.cbore_d,
            self.cbore_depth,
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
        if self.cbore_d != 0 or self.cbore_depth != 0:
            if self.cbore_d <= self.d or not 0 < self.cbore_depth < self.depth:
                raise GeometryError(
                    "Delik: lambada cbore_d > d ve 0 < cbore_depth < depth olmalı "
                    f"({self.cbore_d}, {self.cbore_depth})"
                )
            if self.csk_d != 0 or self.csk_angle != 0:
                raise GeometryError("Delik: havşa ve lamba aynı delikte olamaz")
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

    def _anahtar(self) -> tuple:
        """Eşitlik ve hash için değer demeti (diziler tuple'a çevrilir)."""
        return (tuple(self.origin), tuple(self.axis)) + tuple(
            getattr(self, f.name) for f in fields(self) if f.name not in ("origin", "axis")
        )

    def __eq__(self, other: object) -> bool:
        # dataclass'ın ürettiği __eq__ numpy dizilerinde ValueError verir; değer karşılaştırması yap
        if not isinstance(other, Hole):
            return NotImplemented
        return self._anahtar() == other._anahtar()

    def __hash__(self) -> int:
        return hash(self._anahtar())


@dataclass(frozen=True)
class SectionEdge:
    """Eksenden geçen yarı düzlem kesitinde bir kenar; koordinatlar (z, x) [mm]."""

    kind: str  # "line" | "arc" | "curve"
    points: np.ndarray  # line, arc: (2, 2) [p0, p1]; curve: (k, 2), k ≥ 2, kiriş sapması ≤ tol/4
    center: np.ndarray | None = None  # arc: (2,)
    ccw: bool = True  # arc: (z, x) düzleminde saat yönü tersi


@dataclass(frozen=True)
class SectionFace:
    """Kesitte bir malzeme yüzü: dış halka CCW, iç halkalar CW; her halka uç uca sıralı kenarlar."""

    outer: tuple[SectionEdge, ...]
    holes: tuple[tuple[SectionEdge, ...], ...] = ()


@dataclass(frozen=True)
class AxialSection:
    """Part.axial_section sonucu: eksen çerçevesi, kesit yüzleri ve sınıflanamayan yüzlerin listesi."""

    origin: np.ndarray  # (3,) eksen noktası, parça koordinatı
    axis: np.ndarray  # (3,) birim, +z (ön) yönü
    xdir: np.ndarray  # (3,) birim, axis'e dik, kesit yarı düzleminin +x yönü
    faces: tuple[SectionFace, ...]
    off_axis_faces: tuple[int, ...]  # bu eksene göre dönel OLMAYAN yüzler (OCCT yüz sırası)
    unknown_faces: tuple[int, ...]  # türü sınıflanamayan yüzler (B-spline vb.)


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

    # ---------- Boolean, taşıma, uzaklık (SPEC 09 arayüz eki) ----------

    def moved(self, T: np.ndarray) -> Part:
        """Rijit T (4x4) ile taşınmış yeni parça; ad aynı, delik kayıtları da taşınır.

        T rijit değilse GeometryError.
        """
        from geometry.boolean import moved

        return moved(self, T)

    def common(self, other: Part, tol_v: float = 1e-6) -> Part | None:
        """Kesişim (A ∩ B). Hacmi ≤ tol_v ise None (temas veya ayrık). tol_v < 0 → GeometryError."""
        from geometry.boolean import common

        return common(self, other, tol_v)

    def cut(self, other: Part) -> Part:
        """Fark (A − B). Delik kayıtları korunur. Sonuç boşsa GeometryError."""
        from geometry.boolean import cut

        return cut(self, other)

    def fuse(self, other: Part) -> Part:
        """Birleşim (A ∪ B), tek parça; delik kayıtları A, B sırasıyla."""
        from geometry.boolean import fuse

        return fuse(self, other)

    def distance(self, other: Part) -> tuple[float, np.ndarray, np.ndarray]:
        """Sınırlar arası en küçük uzaklık d ve en yakın noktalar (p ∈ ∂A, q ∈ ∂B), mm."""
        from geometry.boolean import distance

        return distance(self, other)

    # ---------- Torna kesiti (SPEC 28 arayüz eki) ----------

    def axial_section(self, origin=(0.0, 0.0, 0.0), axis=(0.0, 0.0, 1.0), tol: float = 1e-3) -> AxialSection:
        """Eksenden geçen x ≥ 0 yarı düzlem kesiti. axis="auto" → dönel yüzlerden eksen bulunur.

        Sınıflama ve kesit; doğrulama ve uydurma yapmaz. Geçersiz eksen / bulunamayan eksen → GeometryError.
        """
        from geometry.revolve import axial_section

        return axial_section(self, origin, axis, tol)

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
