"""
Part sorgularının OCCT uygulaması: Z kesiti, düzlemsel ve silindirik yüzler.

Arayüz geometry/part.py'dedir (Part.section_z, Part.planar_faces, Part.cylindrical_faces); diğer paketler
bu dosyayı import etmez. Birimler: mm, derece.
"""

from __future__ import annotations

import math

import numpy as np

from geometry.part import CylindricalFace, GeometryError, Part, PlanarFace, Region

try:
    import build123d as bd
    from OCP.BRepAdaptor import BRepAdaptor_CompCurve, BRepAdaptor_Surface
    from OCP.BRepTools import BRepTools
    from OCP.GCPnts import GCPnts_QuasiUniformDeflection
    from OCP.GeomAbs import GeomAbs_Cylinder, GeomAbs_Plane
except ImportError:  # pragma: no cover - build123d kurulu değilse Part zaten hata verir
    pass


def _isaretli_alan(P: np.ndarray) -> float:
    """Shoelace: A = ½ Σ (x_i y_{i+1} − x_{i+1} y_i). CCW → A > 0."""
    x, y = P[:, 0], P[:, 1]
    return 0.5 * float(np.sum(x * np.roll(y, -1) - np.roll(x, -1) * y))


def _cokgen(wire, tol: float, ccw: bool) -> np.ndarray:
    """Kapalı teli (k, 2) çokgene çevirir; kiriş sapması ≤ tol, istenen yönde, son nokta tekrarsız."""
    egri = BRepAdaptor_CompCurve(wire.wrapped)
    orn = GCPnts_QuasiUniformDeflection(egri, tol)
    if not orn.IsDone() or orn.NbPoints() < 3:
        raise GeometryError("kesit teli çokgene çevrilemedi")
    P = np.array([orn.Value(i).Coord()[:2] for i in range(1, orn.NbPoints() + 1)])
    if np.allclose(P[0], P[-1], atol=1e-9 * max(1.0, float(np.abs(P).max()))):
        P = P[:-1]
    A = _isaretli_alan(P)
    if A == 0.0:
        raise GeometryError("kesit teli dejenere (alan 0)")
    if (A > 0) != ccw:
        P = P[::-1].copy()
    return P


def section_z(part: Part, z: float, tol: float = 0.01) -> list[Region]:
    if not math.isfinite(z):
        raise GeometryError(f"kesit yüksekliği sonlu olmalı (z={z})")
    if not (math.isfinite(tol) and tol > 0):
        raise GeometryError(f"tol > 0 olmalı (tol={tol})")
    lo, hi = part.bbox
    if z < lo[2] or z > hi[2]:
        return []
    try:
        kesit = bd.section(part.shape, section_by=bd.Plane.XY.offset(z))
        yuzler = list(kesit.faces()) if kesit is not None else []
    except Exception as e:  # OCCT istisnası
        raise GeometryError(f"z = {z} kesiti başarısız: {e}") from e
    bolgeler = [
        Region(
            outer=_cokgen(y.outer_wire(), tol, ccw=True),
            holes=tuple(_cokgen(w, tol, ccw=False) for w in y.inner_wires()),
        )
        for y in yuzler
    ]
    # Kararlı sıra: büyük bölge önce
    return sorted(bolgeler, key=lambda r: -_isaretli_alan(r.outer))


def _vektor(v) -> np.ndarray:
    return np.array([v.X, v.Y, v.Z], dtype=float)


def planar_faces(part: Part) -> list[PlanarFace]:
    sonuc = []
    for i, yuz in enumerate(part.shape.faces()):
        if BRepAdaptor_Surface(yuz.wrapped).GetType() != GeomAbs_Plane:
            continue
        c = yuz.center(bd.CenterOf.MASS)
        n = _vektor(yuz.normal_at(c))  # normal_at yüz yönelimini (REVERSED) hesaba katar
        sonuc.append(
            PlanarFace(index=i, origin=_vektor(c), normal=n / np.linalg.norm(n), area=float(yuz.area))
        )
    return sonuc


def cylindrical_faces(part: Part) -> list[CylindricalFace]:
    sonuc = []
    for i, yuz in enumerate(part.shape.faces()):
        yuzey = BRepAdaptor_Surface(yuz.wrapped)
        if yuzey.GetType() != GeomAbs_Cylinder:
            continue
        sil = yuzey.Cylinder()
        eksen = sil.Axis()
        q = np.array(eksen.Location().Coord())
        d = np.array(eksen.Direction().Coord())
        r = float(sil.Radius())
        u0, u1, v0, v1 = BRepTools.UVBounds_s(yuz.wrapped)
        # OCCT silindiri: S(u, v) = q + r (cos u · x + sin u · y) + v · d  →  v eksen boyunca mesafe
        p = np.array(yuzey.Value(0.5 * (u0 + u1), 0.5 * (v0 + v1)).Coord())
        n = _vektor(yuz.normal_at(bd.Vector(*p)))
        radyal = (p - q) - ((p - q) @ d) * d  # eksenden yüzeye
        sonuc.append(
            CylindricalFace(
                index=i,
                origin=q + v0 * d,
                axis=d,
                radius=r,
                length=float(v1 - v0),
                angle=math.degrees(u1 - u0),
                concave=bool(n @ radyal < 0),  # dış normal eksene bakıyorsa malzeme dışarıda: delik
                area=float(yuz.area),
            )
        )
    return sonuc
