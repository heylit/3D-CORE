"""
Part boolean işlemleri, rijit taşıma ve en küçük uzaklık (SPEC 09).

Arayüz geometry/part.py'dedir (Part.moved, common, cut, fuse, distance); diğer paketler bu dosyayı import
etmez. Birimler: mm, mm³. Boolean sonucu geçersiz şekilse veya OCCT işlemi başarısızsa GeometryError.

build123d 0.13'te iki kürenin `a & b` sonucu yanlış (küçük kürenin tamamı); bu yüzden OCCT
BRepAlgoAPI_Common / Cut / Fuse doğrudan kullanılır (SPEC 09, ön deneme).
"""

from __future__ import annotations

import dataclasses
import math

import build123d as bd
import numpy as np
from OCP.BRep import BRep_Tool
from OCP.BRepAlgoAPI import BRepAlgoAPI_Common, BRepAlgoAPI_Cut, BRepAlgoAPI_Fuse
from OCP.BRepBuilderAPI import BRepBuilderAPI_Transform
from OCP.BRepCheck import BRepCheck_Analyzer
from OCP.BRepExtrema import BRepExtrema_DistShapeShape, BRepExtrema_IsInFace
from OCP.BRepGProp import BRepGProp
from OCP.GeomAPI import GeomAPI_ProjectPointOnSurf
from OCP.gp import gp_Pnt, gp_Trsf
from OCP.GProp import GProp_GProps
from OCP.ShapeUpgrade import ShapeUpgrade_UnifySameDomain
from OCP.TopoDS import TopoDS

from geometry.part import GeometryError, Hole, Part

TOL_RIJIT = 1e-9  # Rᵀ R = I, det R = 1 ve son satır [0, 0, 0, 1] toleransı
V_BOS = 1e-9  # mm³: bundan küçük hacimli sonuç "boş" sayılır
CILA_TUR = 50  # en yakın nokta cilalama turu üst sınırı
CILA_ADIM = 1e-3  # mm: cilalamada bir noktanın kayabileceği en büyük yol (yüz sınırından taşmasın)


def _hacim(sekil) -> float:
    g = GProp_GProps()
    BRepGProp.VolumeProperties_s(sekil, g)
    return float(g.Mass())


def _yeni_part(sekil, name: str, holes: tuple[Hole, ...]) -> Part:
    """OCCT sonucunu (geçerliyse) build123d şekline sarıp Part yapar; tek katıysa Solid'e indirir."""
    if not BRepCheck_Analyzer(sekil).IsValid():
        raise GeometryError(f"Parça '{name}': boolean sonucu geçersiz şekil")
    shape = bd.Compound(sekil) if sekil.ShapeType().name == "TopAbs_COMPOUND" else bd.Solid(sekil)
    if isinstance(shape, bd.Compound):
        solids = list(shape.solids())
        if len(solids) == 1:
            shape = solids[0]
    return Part(shape, name=name, holes=holes)


def _boolean(islem, a: Part, b: Part, ad: str):
    """BRepAlgoAPI işlemini çalıştırır, OCCT sonucunu döndürür; başarısızsa GeometryError."""
    try:
        op = islem(a.shape.wrapped, b.shape.wrapped)
        op.Build()
    except Exception as e:  # OCCT istisnası
        raise GeometryError(f"{ad}: OCCT boolean başarısız ({e})") from e
    if not op.IsDone():
        raise GeometryError(f"{ad}: OCCT boolean başarısız ('{a.name}', '{b.name}')")
    return op.Shape()


def _rijit(T: np.ndarray) -> np.ndarray:
    T = np.asarray(T, dtype=float)
    if T.shape != (4, 4) or not np.all(np.isfinite(T)):
        raise GeometryError(f"Taşıma: T 4x4 sonlu bir matris olmalı (şekil {T.shape})")
    R = T[:3, :3]
    if not (
        np.allclose(R.T @ R, np.eye(3), atol=TOL_RIJIT)
        and abs(np.linalg.det(R) - 1.0) <= TOL_RIJIT
        and np.allclose(T[3], [0, 0, 0, 1], atol=TOL_RIJIT)
    ):
        raise GeometryError("Taşıma: T rijit bir dönüşüm değil (ölçek, ayna veya kayma)")
    return T


def moved(part: Part, T: np.ndarray) -> Part:
    """Rijit T (4x4) ile taşınmış yeni parça; ad aynı, delik kayıtları da taşınır."""
    T = _rijit(T)
    R, t = T[:3, :3], T[:3, 3]
    trsf = gp_Trsf()
    trsf.SetValues(*R[0], t[0], *R[1], t[1], *R[2], t[2])
    sekil = BRepBuilderAPI_Transform(part.shape.wrapped, trsf, True).Shape()
    holes = tuple(dataclasses.replace(h, origin=R @ h.origin + t, axis=R @ h.axis) for h in part.holes)
    return _yeni_part(sekil, part.name, holes)


def common(a: Part, b: Part, tol_v: float = 1e-6) -> Part | None:
    """A ∩ B; hacmi ≤ tol_v ise None. Ad: a.name."""
    if not (math.isfinite(tol_v) and tol_v >= 0):
        raise GeometryError(f"common: tol_v ≥ 0 ve sonlu olmalı ({tol_v})")
    sekil = _boolean(BRepAlgoAPI_Common, a, b, "common")
    if _hacim(sekil) <= tol_v:
        return None
    return _yeni_part(sekil, a.name, ())


def cut(a: Part, b: Part) -> Part:
    """A − B; delik kayıtları korunur, boş sonuç GeometryError. Ad: a.name."""
    sekil = _boolean(BRepAlgoAPI_Cut, a, b, "cut")
    if _hacim(sekil) <= V_BOS:
        raise GeometryError(
            f"{a.name} − {b.name}: kesim sonucu boş (hacim 0 mm³) — "
            "kesen parçayı küçültün ya da konumunu değiştirin"
        )
    return _yeni_part(sekil, a.name, a.holes)


def fuse(a: Part, b: Part) -> Part:
    """A ∪ B, tek parça; delik kayıtları A, B sırasıyla. Ad: a.name."""
    sekil = _boolean(BRepAlgoAPI_Fuse, a, b, "fuse")
    birlestir = ShapeUpgrade_UnifySameDomain(sekil, True, True, False)
    birlestir.Build()
    return _yeni_part(birlestir.Shape(), a.name, a.holes + b.holes)


def _vektor(p: gp_Pnt) -> np.ndarray:
    return np.array([p.X(), p.Y(), p.Z()])


def _yuzey(dist: BRepExtrema_DistShapeShape, hangi: int):
    """Çözüm noktası bir yüzün içindeyse o yüzün taşıyıcı yüzeyi, değilse None (kenar / köşe)."""
    tur = dist.SupportTypeShape1(1) if hangi == 1 else dist.SupportTypeShape2(1)
    if tur != BRepExtrema_IsInFace:
        return None
    destek = dist.SupportOnShape1(1) if hangi == 1 else dist.SupportOnShape2(1)
    return BRep_Tool.Surface_s(TopoDS.Face(destek))


def _izdusum(yuzey, x: np.ndarray) -> np.ndarray | None:
    proj = GeomAPI_ProjectPointOnSurf(gp_Pnt(*x), yuzey)
    return _vektor(proj.NearestPoint()) if proj.NbPoints() > 0 else None


def _cila(yA, yB, p: np.ndarray, q: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Dönüşümlü izdüşüm: p ← ∂A'ya izdüşüm(q), q ← ∂B'ye izdüşüm(p). Uzaklık azalmazsa durur.

    BRepExtrema yakınsama toleransı eğri yüzlerde noktaları ~1e-4 mm kaydırabiliyor; birkaç tur bu hatayı
    sıfıra indirir. Noktaların CILA_ADIM'dan fazla kaymasına izin verilmez (yüz sınırı dışına taşmasın).
    """
    p0, q0 = p, q
    d = float(np.linalg.norm(q - p))
    for _ in range(CILA_TUR):
        p1 = _izdusum(yA, q)
        q1 = _izdusum(yB, p1) if p1 is not None else None
        if q1 is None or np.linalg.norm(p1 - p0) > CILA_ADIM or np.linalg.norm(q1 - q0) > CILA_ADIM:
            break
        d1 = float(np.linalg.norm(q1 - p1))
        if d1 >= d:
            break
        p, q, d = p1, q1, d1
    return p, q


def distance(a: Part, b: Part) -> tuple[float, np.ndarray, np.ndarray]:
    """Sınırlar arası en küçük uzaklık d ve en yakın noktalar (p ∈ ∂A, q ∈ ∂B)."""
    dist = BRepExtrema_DistShapeShape(a.shape.wrapped, b.shape.wrapped)
    if not dist.IsDone() or dist.NbSolution() < 1:
        raise GeometryError(f"distance: OCCT uzaklık hesabı başarısız ('{a.name}', '{b.name}')")
    p, q = _vektor(dist.PointOnShape1(1)), _vektor(dist.PointOnShape2(1))
    yA, yB = _yuzey(dist, 1), _yuzey(dist, 2)
    if yA is not None and yB is not None and dist.Value() > 0:
        p, q = _cila(yA, yB, p, q)
    return float(np.linalg.norm(q - p)), p, q
