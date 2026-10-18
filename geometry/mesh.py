"""
SPEC 02 — Üçgen ağı (görüntüleme / STL) ve STL okuma.

tessellate: OCCT BRepMesh ile yüz yüz üçgenleme; yüzler arası ortak köşeler birleştirilir, üçgenler
dışa bakan sıraya çevrilir. mesh_volume saf numpy'dir (OCCT'siz).
read_stl: STL üçgenlerini dikip (sewing) kabuk → katı yapar.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from geometry.part import GeometryError, Part

try:
    import build123d as bd
    from OCP.BRep import BRep_Tool
    from OCP.BRepBuilderAPI import (
        BRepBuilderAPI_Copy,
        BRepBuilderAPI_MakePolygon,
        BRepBuilderAPI_MakeSolid,
        BRepBuilderAPI_Sewing,
    )
    from OCP.BRepGProp import BRepGProp
    from OCP.BRepLib import BRepLib_MakeFace
    from OCP.BRepMesh import BRepMesh_IncrementalMesh
    from OCP.gp import gp_Pnt
    from OCP.GProp import GProp_GProps
    from OCP.RWStl import RWStl
    from OCP.TopAbs import TopAbs_FACE, TopAbs_REVERSED, TopAbs_SHELL
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopLoc import TopLoc_Location
    from OCP.TopoDS import TopoDS
except ImportError:  # pragma: no cover - build123d kurulu değilse Part zaten hata verir
    pass

ACI_TOL = 0.5  # rad: açısal sapma (BRepMesh varsayılanı); ağı tol'un kendisi belirlesin diye gevşek
KAYNAK_TOL = 1e-9  # mm: bu mesafeden yakın köşeler aynı düğüm sayılır (ölçeğe göre büyütülür)


# --- tessellate ---------------------------------------------------------------------------------


def _yuz_ucgenleri(yuz) -> tuple[np.ndarray, np.ndarray] | None:
    """Ağlanmış bir yüzün düğümleri (k,3) ve dışa bakan üçgenleri (t,3); ağ yoksa None."""
    loc = TopLoc_Location()
    tri = BRep_Tool.Triangulation_s(yuz, loc)
    if tri is None:
        return None
    trsf = loc.Transformation()
    P = np.array(
        [
            (lambda p: (p.X(), p.Y(), p.Z()))(tri.Node(i).Transformed(trsf))
            for i in range(1, tri.NbNodes() + 1)
        ]
    )
    T = np.array([tri.Triangle(i).Get() for i in range(1, tri.NbTriangles() + 1)], dtype=np.int64) - 1
    if yuz.Orientation() == TopAbs_REVERSED:
        T = T[:, ::-1]  # yüz ters yönlüyse üçgen sırası da ters: normal dışa baksın
    return P, T


def _kaynakla(P: np.ndarray, T: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Çakışık köşeleri tek düğümde birleştirir, dejenere (iki köşesi aynı) üçgenleri atar."""
    olcek = max(1.0, float(np.max(np.abs(P))))
    anahtar = np.round(P / (KAYNAK_TOL * olcek)).astype(np.int64)
    _, ilk, yeni = np.unique(anahtar, axis=0, return_index=True, return_inverse=True)
    V = P[ilk]
    T = yeni.reshape(-1)[T]
    saglam = (T[:, 0] != T[:, 1]) & (T[:, 1] != T[:, 2]) & (T[:, 2] != T[:, 0])
    return V, T[saglam]


def _kapali_ve_yonlu(T: np.ndarray) -> bool:
    """Her yönlü kenar (i, j) tam bir kez ve tersi (j, i) tam bir kez geçiyorsa True."""
    if len(T) == 0:
        return False
    E = np.concatenate([T[:, [0, 1]], T[:, [1, 2]], T[:, [2, 0]]])
    n = int(E.max()) + 1
    kod = E[:, 0] * n + E[:, 1]
    if len(np.unique(kod)) != len(kod):
        return False
    ters = E[:, 1] * n + E[:, 0]
    return bool(np.all(np.isin(ters, kod)))


def tessellate(part: Part, tol: float = 0.01) -> tuple[np.ndarray, np.ndarray]:
    """Köşeler V (n,3) ve dışa bakan üçgenler T (m,3); ağ kapalı.

    tol: doğrusal sapma (kiriş ile yüzey arası en büyük mesafe) [mm]. Açısal sapma ACI_TOL gevşek
    tutulur; böylece ağ yoğunluğunu tol belirler (silindirde r(1 − cos(θ/2)) ≤ tol).
    """
    if not (np.isfinite(tol) and tol > 0):
        raise GeometryError(f"tol > 0 olmalı (tol={tol})")
    try:
        # Derin kopya (ağ kopyalanmadan): girdi parçanın yüzlerine üçgenleme yazılmasın
        shape = BRepBuilderAPI_Copy(part.shape.wrapped, True, False).Shape()
        mesh = BRepMesh_IncrementalMesh(shape, tol, False, ACI_TOL, False)
        mesh.Perform()
    except Exception as e:  # OCCT istisnası
        raise GeometryError(f"üçgenleme başarısız: {e}") from e
    Ps, Ts, ofset = [], [], 0
    exp = TopExp_Explorer(shape, TopAbs_FACE)
    while exp.More():
        sonuc = _yuz_ucgenleri(TopoDS.Face(exp.Current()))
        if sonuc is None:
            raise GeometryError("bir yüz üçgenlenemedi")
        P, T = sonuc
        Ps.append(P)
        Ts.append(T + ofset)
        ofset += len(P)
        exp.Next()
    if not Ps:
        raise GeometryError("parçada yüz yok")
    V, T = _kaynakla(np.vstack(Ps), np.vstack(Ts))
    if not _kapali_ve_yonlu(T):
        raise GeometryError("üçgen ağı kapalı / tutarlı yönlü değil")
    if mesh_volume(V, T) <= 0:
        raise GeometryError("üçgen ağı içe bakıyor (hacim ≤ 0)")
    return V, T


def mesh_volume(V: np.ndarray, T: np.ndarray) -> float:
    """Diverjans teoremi: V = (1/6) Σ p₁ · (p₂ × p₃)."""
    V = np.asarray(V, dtype=float)
    T = np.asarray(T, dtype=np.int64)
    p1, p2, p3 = V[T[:, 0]], V[T[:, 1]], V[T[:, 2]]
    return float(np.einsum("ij,ij->i", p1, np.cross(p2, p3)).sum() / 6.0)


# --- read_stl -----------------------------------------------------------------------------------


def _stl_oku(path: Path) -> tuple[np.ndarray, np.ndarray]:
    """STL (ikili / ASCII) → kaynaklanmış köşeler V ve üçgenler T (dosyadaki yön sırasıyla)."""
    tri = RWStl.ReadFile_s(str(path))
    if tri is None or tri.NbTriangles() == 0:
        raise GeometryError(f"STL okunamadı veya boş: {path}")
    P = np.array([(lambda p: (p.X(), p.Y(), p.Z()))(tri.Node(i)) for i in range(1, tri.NbNodes() + 1)])
    T = np.array([tri.Triangle(i).Get() for i in range(1, tri.NbTriangles() + 1)], dtype=np.int64) - 1
    return _kaynakla(P, T)


def _dik(V: np.ndarray, T: np.ndarray, tol: float):
    """Her üçgenden düzlemsel yüz yapar, BRepBuilderAPI_Sewing ile tek kabuğa diker."""
    sew = BRepBuilderAPI_Sewing(tol)
    noktalar = [gp_Pnt(*map(float, p)) for p in V]
    for i, j, k in T:
        poligon = BRepBuilderAPI_MakePolygon(noktalar[i], noktalar[j], noktalar[k], True)
        sew.Add(BRepLib_MakeFace(poligon.Wire(), True).Face())
    sew.Perform()
    if sew.NbFreeEdges() > 0:
        raise GeometryError(f"STL ağı kapalı değil ({sew.NbFreeEdges()} serbest kenar)")
    dikili = sew.SewedShape()
    exp = TopExp_Explorer(dikili, TopAbs_SHELL)
    kabuklar = []
    while exp.More():
        kabuklar.append(TopoDS.Shell(exp.Current()))
        exp.Next()
    if len(kabuklar) != 1:
        raise GeometryError(f"STL ağı tek kapalı kabuk değil ({len(kabuklar)} kabuk)")
    return kabuklar[0]


def _hacim(shape) -> float:
    g = GProp_GProps()
    BRepGProp.VolumeProperties_s(shape, g)
    return float(g.Mass())


def read_stl(path: str | Path, name: str | None = None) -> Part:
    """STL üçgenlerini dikip kapalı katıya çevirir.

    Adımlar: oku → çakışık köşeleri birleştir → kapalılık ve yön kontrolü (her yönlü kenar bir kez,
    tersi bir kez) → yüzleri dik → kabuk → katı. Katının hacmi negatifse (içe bakan kabuk) ters çevrilir.
    """

    path = Path(path)
    if not path.is_file():
        raise GeometryError(f"STL dosyası yok: {path}")
    try:
        V, T = _stl_oku(path)
    except GeometryError:
        raise
    except Exception as e:  # OCCT istisnası
        raise GeometryError(f"STL okunamadı: {path} ({e})") from e
    if not _kapali_ve_yonlu(T):
        raise GeometryError(f"STL ağı kapalı / tutarlı yönlü değil: {path}")
    if mesh_volume(V, T) <= 0:
        raise GeometryError(f"STL ağının hacmi ≤ 0 (içe bakan veya düz): {path}")
    olcek = max(1.0, float(np.ptp(V, axis=0).max()))
    try:
        kabuk = _dik(V, T, 1e-6 * olcek)
        kati = BRepBuilderAPI_MakeSolid(kabuk).Solid()
        if _hacim(kati) < 0:
            kati.Reverse()
        shape = bd.Solid(kati)
    except GeometryError:
        raise
    except Exception as e:  # OCCT istisnası
        raise GeometryError(f"STL katıya çevrilemedi: {path} ({e})") from e
    return Part(shape, name=name or path.stem)
