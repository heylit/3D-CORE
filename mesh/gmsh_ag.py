"""
Parçadan (geometry.part.Part) gmsh ile dört düğümlü tetrahedron ağı -> core.model.Model.

Teori: specs/12-gmsh.md
"""

from __future__ import annotations

import math
import tempfile
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from core.model import Element, Material, Model, ModelError, Node

GMSH_TET4 = 4  # gmsh eleman tipi: 4 düğümlü tetrahedron


def _pozitif_sonlu(ad: str, deger) -> float:
    try:
        x = float(deger)
    except (TypeError, ValueError):
        raise ModelError(f"{ad} bir sayı olmalı ({deger!r})") from None
    if not math.isfinite(x) or x <= 0:
        raise ModelError(f"{ad} pozitif ve sonlu olmalı ({ad}={deger})")
    return x


@dataclass(frozen=True)
class Refine:
    """Yerel inceltme küresi [mm]: içinde eleman boyu h, dışında bir yarıçap boyunca genel boya geçiş."""

    center: tuple[float, float, float]
    radius: float
    h: float

    def __post_init__(self) -> None:
        try:
            c = tuple(float(v) for v in self.center)
        except (TypeError, ValueError):
            raise ModelError(f"Refine: merkez üç sayı olmalı ({self.center!r})") from None
        if len(c) != 3 or not all(math.isfinite(v) for v in c):
            raise ModelError(f"Refine: merkez üç sonlu sayı olmalı ({self.center!r})")
        # Dondurulmuş dataclass: normalleştirilmiş değerler object.__setattr__ ile yazılır
        object.__setattr__(self, "center", c)
        object.__setattr__(self, "radius", _pozitif_sonlu("Refine yarıçapı", self.radius))
        object.__setattr__(self, "h", _pozitif_sonlu("Refine boyu h", self.h))


def _gmsh():
    try:
        import gmsh
    except ImportError:
        raise ModelError("gmsh kurulu değil: pip install -e .[mesh]") from None
    return gmsh


def _boy_alanlari(gmsh, h: float, refine: Sequence[Refine]) -> None:
    """Genel boy h; her Refine bir Ball alanı, hepsi Min alanıyla birleşir (Teori: Ağ üretimi)."""
    gmsh.option.setNumber("Mesh.MeshSizeMax", h)
    gmsh.option.setNumber("Mesh.MeshSizeFromCurvature", 0)
    if not refine:
        return
    alan = gmsh.model.mesh.field
    toplar = []
    for r in refine:
        b = alan.add("Ball")
        for ad, v in zip(("XCenter", "YCenter", "ZCenter"), r.center, strict=True):
            alan.setNumber(b, ad, v)
        alan.setNumber(b, "Radius", r.radius)
        alan.setNumber(b, "VIn", r.h)
        alan.setNumber(b, "VOut", h)
        alan.setNumber(b, "Thickness", r.radius)  # bir yarıçap boyunca h_local -> h geçişi
        toplar.append(b)
    en_kucuk = alan.add("Min")
    alan.setNumbers(en_kucuk, "FieldsList", toplar)
    alan.setAsBackgroundMesh(en_kucuk)
    gmsh.option.setNumber("Mesh.MeshSizeExtendFromBoundary", 0)
    gmsh.option.setNumber("Mesh.MeshSizeFromPoints", 0)


def _gmsh_agi(part, h: float, refine: Sequence[Refine]) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """STEP -> gmsh OCC -> 3B ağ. Dönüş: düğüm etiketleri (n,), koordinatlar (n, 3), tet bağlantısı (m, 4)."""
    gmsh = _gmsh()
    with tempfile.TemporaryDirectory() as klasor:
        step = Path(klasor) / "parca.step"
        part.to_step(step)
        gmsh.initialize(interruptible=False)
        try:
            gmsh.option.setNumber("General.Terminal", 0)
            gmsh.option.setNumber("General.NumThreads", 1)
            gmsh.option.setNumber("Mesh.Algorithm3D", 1)  # Delaunay, tekrarlanabilir
            gmsh.model.occ.importShapes(str(step))
            gmsh.model.occ.synchronize()
            n_kati = len(gmsh.model.getEntities(3))
            if n_kati != 1:
                raise ModelError(f"Parça '{part.name}' tek katı olmalı (gmsh'te {n_kati} katı)")
            _boy_alanlari(gmsh, h, refine)
            gmsh.model.mesh.generate(3)
            etiket, xyz, _ = gmsh.model.mesh.getNodes()
            _, baglanti = gmsh.model.mesh.getElementsByType(GMSH_TET4)
        except ModelError:
            raise
        except Exception as hata:  # gmsh hataları Exception olarak gelir
            raise ModelError(f"gmsh ağ üretemedi ({part.name}): {hata}") from None
        finally:
            gmsh.finalize()
    X = np.asarray(xyz, dtype=float).reshape(-1, 3)
    return np.asarray(etiket), X, np.asarray(baglanti).reshape(-1, 4)


def tet_mesh(
    part,
    h: float,
    material: Material,
    *,
    refine: Sequence[Refine] = (),
    max_nodes: int = 200_000,
) -> Model:
    """Parçayı tet4 ağına çevirir: Model(dim=3), düğümler 1..n, elemanlar 1..m, hepsi det C > 0."""
    from geometry.part import Part

    if not isinstance(part, Part):
        raise ModelError(f"tet_mesh bir geometry.part.Part bekler ({type(part).__name__} verildi)")
    if not isinstance(material, Material):
        raise ModelError(f"tet_mesh bir core.model.Material bekler ({type(material).__name__} verildi)")
    h = _pozitif_sonlu("Eleman boyu h", h)
    refine = tuple(refine)
    if not all(isinstance(r, Refine) for r in refine):
        raise ModelError("refine sadece Refine kayıtları içermeli")

    etiket, xyz, baglanti = _gmsh_agi(part, h, refine)
    if len(baglanti) == 0:
        raise ModelError(f"Parça '{part.name}' için hiç tetrahedron üretilmedi")

    # Sadece tetrahedronlarda kullanılan düğümler, gmsh sırasıyla 1..n
    sira = {int(t): i for i, t in enumerate(etiket)}
    tet_dugumleri = set(np.unique(baglanti).tolist())
    kullanilan = [int(t) for t in etiket if int(t) in tet_dugumleri]
    if len(kullanilan) > max_nodes:
        raise ModelError(f"Ağda {len(kullanilan)} düğüm var, sınır max_nodes={max_nodes}")
    yeni = {t: i + 1 for i, t in enumerate(kullanilan)}
    X = xyz[[sira[t] for t in kullanilan]]

    # Yeni numaralı bağlantı; sol el sıralı elemanlarda 2. ve 3. düğüm yer değiştirir
    T = np.vectorize(yeni.__getitem__)(baglanti.astype(np.int64))
    P = X[T - 1]  # (m, 4, 3)
    det = np.einsum("ij,ij->i", P[:, 1] - P[:, 0], np.cross(P[:, 2] - P[:, 0], P[:, 3] - P[:, 0]))
    sol = det < 0
    T[sol, 1], T[sol, 2] = T[sol, 2].copy(), T[sol, 1].copy()

    model = Model(dim=3, name=part.name, materials=[material])
    model.nodes = [Node(i + 1, float(x), float(y), float(z)) for i, (x, y, z) in enumerate(X)]
    model.elements = [Element(j + 1, "tet4", [int(v) for v in t], material.name) for j, t in enumerate(T)]
    model.validate()
    return model
