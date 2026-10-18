"""
SPEC 65a — Serbest yüzey: loft, sweep, B-spline yüzey (OCCT hazır algoritmalarıyla).

Özellik ağacı (`geometry/agac.py`) serbest yüzey unsurları için yalnız bu modülü çağırır. Yüzey
matematiğini biz yazmıyoruz; OCCT'nin şu algoritmaları kullanılır:
- Loft: `BRepOffsetAPI_ThruSections` (ruled = regle yüzeyler, aksi tek B-spline yan yüz, G1)
- Sweep: `BRepOffsetAPI_MakePipeShell` (frenet / sabit / yardımcı yön)
- B-spline yüzey: `GeomAPI_PointsToBSplineSurface` (derece 3, `tol` içinde noktalardan geçer);
  katıya `BRepOffsetAPI_MakeThickSolid` (kalınlaştır) ya da `BRepAlgoAPI_Splitter` (yüzeyle kes) ile girer.

Hatalar `geometry.part.GeometryError` (ValueError; SPEC metnindeki ModelError'ın geometri paketindeki
karşılığı, SPEC 18 ile aynı). Ağaç içinde hata → özellik "hata", bağımlıları "atlandi" (S1).
Birimler: mm, radyan (iç hesap).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import build123d as bd

from sketch.model import Plane, SketchRegion

TOL_TEGET = 1e-6  # rad: sweep yolunda ardışık parçaların teğet açısı farkı sınırı


# --- Sweep yolu --------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Cizgi:
    """p0 → p1 doğru parçası (dünya koordinatı, mm)."""

    p0: tuple[float, float, float]
    p1: tuple[float, float, float]


@dataclass(frozen=True)
class Yay:
    """Üç noktadan geçen yay: p0 başlangıç, p1 ara nokta, p2 bitiş (dünya koordinatı, mm)."""

    p0: tuple[float, float, float]
    p1: tuple[float, float, float]
    p2: tuple[float, float, float]


@dataclass(frozen=True)
class Spline:
    """Noktalardan geçen 3B spline; teget0 / teget1 verilirse uçlardaki teğet yönü (normalize edilmez)."""

    noktalar: tuple[tuple[float, float, float], ...]
    teget0: tuple[float, float, float] | None = None
    teget1: tuple[float, float, float] | None = None


YolParcasi = Cizgi | Yay | Spline


@dataclass(frozen=True)
class Yol:
    """Uç uca eklenmiş parçalar zinciri; teğet sürekli (köşe ≤ TOL_TEGET rad), kendini kesmez."""

    parcalar: tuple[YolParcasi, ...]


# --- OCCT çağrıları ----------------------------------------------------------------------------------------


def yol_teli(yol: Yol) -> bd.Wire:
    """Yolu tek tel yapar. Boş yol, kopuk uçlar, teğet süreksizliği (> TOL_TEGET rad) ya da kendini kesen
    yol → GeometryError."""
    raise NotImplementedError


def yol_boyu(yol: Yol) -> float:
    """Yol boyu s [mm] (Pappus: V = A · s)."""
    raise NotImplementedError


def loft_govde(
    kesitler: Sequence[tuple[Plane, Sequence[SketchRegion]]], ruled: bool = False
) -> tuple[object, dict[str, list]]:
    """Kesitlerden katı (TopoDS_Solid) ve yerel yüz adları.

    Her kesit tek, deliksiz, kapalı bölgedir. Adlar: `bas`, `son`; ruled=False'ta `yan` (tek yüz),
    ruled=True'da `yan_1..yan_k` (k = kesit sayısı − 1, kesit aralığı başına).
    Kesit < 2, açık / delikli / çok bölgeli profil ya da OCCT eşleme hatası → GeometryError.
    """
    raise NotImplementedError


def sweep_govde(
    plane: Plane,
    bolgeler: Sequence[SketchRegion],
    yol: Yol,
    yonlendirme: str = "frenet",
    yardimci: tuple[float, float, float] | None = None,
) -> tuple[object, dict[str, list]]:
    """Profili yol boyunca süpürür; katı ve yerel adlar `bas`, `son`, `yan_i` (i = profil kenarı, 1'den).

    Profil eskiz düzleminde olduğu yerde kullanılır (taşınmaz). yonlendirme: "frenet" | "sabit" |
    "yardimci" (yardimci yön vektörü zorunlu). Hatalı yol / yön / OCCT hatası → GeometryError.
    """
    raise NotImplementedError


def bspline_yuzey(noktalar: Sequence[Sequence[Sequence[float]]], tol: float = 0.01) -> bd.Face:
    """m × n nokta ağından (m, n ≥ 4, düzenli) derece 3 B-spline yüzey (sınırlı build123d Face).

    Yüzey her noktadan tol içinde geçer. tol ≤ 0, düzensiz ağ, m veya n < 4 → GeometryError.
    """
    raise NotImplementedError


def kalinlastir(yuzey: bd.Face, kalinlik: float) -> tuple[object, dict[str, list]]:
    """Yüzeyi kalınlaştırıp katı yapar; kalinlik > 0 yüzey normali yönünde, < 0 tersinde.

    Adlar: `ust` (normal tarafındaki yüz), `alt`, `kenar_i` (1'den). kalinlik = 0 ya da OCCT hatası
    (ör. kalınlık eğrilik yarıçapından büyük) → GeometryError.
    """
    raise NotImplementedError


def yuzle_kes(govde, yuzey: bd.Face, sakla: str = "alt") -> tuple[object, list]:
    """Gövdeyi yüzeyle böler; yüzey normaline göre "ust" ya da "alt" taraf kalır.

    Dönüş: kalan katı ve kesik yüzler (`kesit` adı için). Yüzey gövdeyi bölmüyorsa → GeometryError.
    """
    raise NotImplementedError
