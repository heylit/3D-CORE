"""
CAD yüzü ↔ ağ sınır üçgenleri eşlemesi (SPEC 67b). gmsh + OCCT gerektirir.

Teori: specs/67-fem-genisletme.md (CAD yüzü eşlemesi). `geometry/part.py` arayüzü değişmez; OCCT yüz
özellikleri `mesh/` içinde build123d üzerinden okunur.

Biçim kuralları:
- `face_tris[i]`: OCCT yüz indeksi `i` (`Part.names` / `Part.find` sırası, 0'dan) → `(k, 3)` (order=1)
  ya da `(k, 6)` (order=2) düğüm id dizisi; `mesh.boundary_triangles(model)` satırlarının bir
  bölüntüsüdür (her sınır üçgeni tam bir yüze düşer). Anahtarlar parçanın bütün yüzleridir.
- `triangles(part, ref)`: `part.find(ref)`'in yüz indeksleri sırasıyla yüzlerin üçgenleri alt alta.
- `nodes(part, ref)`: o üçgenlerin bütün düğüm id'leri (kenar düğümleri dahil), artan, tekrarsız.
- Eşleme bire bir değilse, ya da iki yüz alan ve merkezde ayrışmıyorsa → ModelError.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

import numpy as np

from core.model import Material, Model, ModelError
from mesh.gmsh_ag import Refine, _boy_alanlari, _gmsh, tet_mesh
from mesh.secim import boundary_triangles

# Eşleme ölçütleri (Teori): alan göreli, merkez parça köşegenine göre
ALAN_TOL = 1e-6
MERKEZ_TOL = 1e-6
GMSH_TRI3 = 2  # gmsh eleman tipi: 3 düğümlü üçgen


@dataclass(frozen=True)
class PartMesh:
    model: Model
    face_tris: Mapping[int, np.ndarray]

    def _indeksler(self, part, ref) -> tuple[int, ...]:
        from geometry.part import GeometryError

        try:
            return part.find(ref)
        except GeometryError as hata:
            raise ModelError(str(hata)) from None

    def triangles(self, part, ref) -> np.ndarray:
        """`ref` (FaceRef) yüzlerinin sınır üçgenleri; bulunamayan ref → ModelError."""
        return np.concatenate([np.asarray(self.face_tris[i]) for i in self._indeksler(part, ref)])

    def nodes(self, part, ref) -> list[int]:
        """`ref` yüzlerindeki bütün düğümler (kenar düğümü dahil), artan."""
        return sorted({int(n) for n in self.triangles(part, ref).ravel()})


def _occt_yuzleri(part) -> list[tuple[float, np.ndarray]]:
    """OCCT yüzleri `part.shape.faces()` sırasıyla (Part indeksi): (alan, kütle merkezi)."""
    from build123d import CenterOf

    sonuc = []
    for yuz in part.shape.faces():
        c = yuz.center(CenterOf.MASS)
        sonuc.append((float(yuz.area), np.array([c.X, c.Y, c.Z])))
    return sonuc


def _gmsh_yuzeyleri(part, h: float, refine: Sequence[Refine]) -> list[tuple[float, np.ndarray, np.ndarray]]:
    """tet_mesh'in seçenekleriyle yalnız yüzey ağı: her gmsh yüzeyi için (alan, merkez, köşeler (k, 3, 3)).

    gmsh hacim ağını yüzey ağını değiştirmeden üretir; aynı STEP ve seçeneklerle yüzey üçgenleri tet_mesh
    ağının sınır üçgenleriyle aynı köşe koordinatlarına sahiptir (eşleşmeyen üçgen → ModelError).
    """
    import tempfile
    from pathlib import Path

    gmsh = _gmsh()
    with tempfile.TemporaryDirectory() as klasor:
        step = Path(klasor) / "parca.step"
        part.to_step(step)
        gmsh.initialize(interruptible=False)
        try:
            gmsh.option.setNumber("General.Terminal", 0)
            gmsh.option.setNumber("General.NumThreads", 1)
            gmsh.option.setNumber("Mesh.Algorithm3D", 1)
            gmsh.model.occ.importShapes(str(step))
            gmsh.model.occ.synchronize()
            _boy_alanlari(gmsh, h, refine)
            gmsh.option.setNumber("Mesh.HighOrderOptimize", 0)
            gmsh.model.mesh.generate(2)
            etiket, xyz, _ = gmsh.model.mesh.getNodes()
            X = dict(zip((int(t) for t in etiket), np.asarray(xyz, dtype=float).reshape(-1, 3), strict=True))
            sonuc = []
            for _, tag in gmsh.model.getEntities(2):
                _, baglanti = gmsh.model.mesh.getElementsByType(GMSH_TRI3, tag)
                T = np.asarray(baglanti, dtype=np.int64).reshape(-1, 3)
                kose = np.array([[X[int(n)] for n in t] for t in T]).reshape(-1, 3, 3)
                alan = float(gmsh.model.occ.getMass(2, tag))
                merkez = np.asarray(gmsh.model.occ.getCenterOfMass(2, tag), dtype=float)
                sonuc.append((alan, merkez, kose))
        except ModelError:
            raise
        except Exception as hata:  # gmsh hataları Exception olarak gelir
            raise ModelError(f"gmsh yüzey ağı üretemedi ({part.name}): {hata}") from None
        finally:
            gmsh.finalize()
    return sonuc


def _eslestir(part, yuzeyler, occt) -> list[int]:
    """gmsh yüzeyi sırasıyla OCCT yüz indeksi; alan (göreli) ve merkez (köşegene göre) ile, bire bir."""
    lo, hi = part.bbox
    kosegen = float(np.linalg.norm(np.asarray(hi) - np.asarray(lo)))
    if len(yuzeyler) != len(occt):
        raise ModelError(f"Parça '{part.name}': gmsh {len(yuzeyler)} yüzey, OCCT {len(occt)} yüz verdi")
    sonuc = []
    for s, (A_s, c_s, _) in enumerate(yuzeyler):
        aday = [
            i
            for i, (A_f, c_f) in enumerate(occt)
            if abs(A_s - A_f) <= ALAN_TOL * A_f and np.linalg.norm(c_s - c_f) <= MERKEZ_TOL * kosegen
        ]
        if len(aday) != 1:
            raise ModelError(
                f"Parça '{part.name}': gmsh yüzeyi {s} için {len(aday)} OCCT yüzü eşleşti (bire bir değil)"
            )
        sonuc.append(aday[0])
    if len(set(sonuc)) != len(sonuc):
        raise ModelError(f"Parça '{part.name}': iki gmsh yüzeyi aynı OCCT yüzüne eşleşti (ayrışmayan yüzler)")
    return sonuc


def mesh_part(part, h: float, material: Material, *, order: int = 1, refine=()) -> PartMesh:
    """`mesh.tet_mesh(part, h, material, order=order, refine=refine)` + yüz eşlemesi."""
    model = tet_mesh(part, h, material, order=order, refine=refine)
    refine = tuple(refine)
    yuzeyler = _gmsh_yuzeyleri(part, float(h), refine)
    yuz_indeksi = _eslestir(part, yuzeyler, _occt_yuzleri(part))

    # Köşe koordinatları (sırasız) → OCCT yüz indeksi
    anahtar_yuz: dict[tuple, int] = {}
    for (_, _, kose), i in zip(yuzeyler, yuz_indeksi, strict=True):
        for k in kose:
            anahtar_yuz[tuple(sorted(map(tuple, k.tolist())))] = i

    sinir = boundary_triangles(model)
    xyz = {n.id: (n.x, n.y, n.z) for n in model.nodes}
    satirlar: dict[int, list[int]] = {i: [] for i in range(len(yuz_indeksi))}
    for r, t in enumerate(sinir.tolist()):
        anahtar = tuple(sorted(xyz[n] for n in t[:3]))
        if anahtar not in anahtar_yuz:
            raise ModelError(f"Parça '{part.name}': sınır üçgeni {t[:3]} hiçbir gmsh yüzeyinde bulunamadı")
        satirlar[anahtar_yuz[anahtar]].append(r)
    if sum(len(v) for v in satirlar.values()) != len(sinir) or len(anahtar_yuz) != len(sinir):
        raise ModelError(f"Parça '{part.name}': yüzey üçgenleri sınır üçgenleriyle örtüşmüyor")
    face_tris = {i: sinir[satirlar[i]].reshape(-1, sinir.shape[1]) for i in sorted(satirlar)}
    return PartMesh(model, face_tris)
