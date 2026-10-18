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

from collections.abc import Mapping
from dataclasses import dataclass

import numpy as np

from core.model import Material, Model


@dataclass(frozen=True)
class PartMesh:
    model: Model
    face_tris: Mapping[int, np.ndarray]

    def triangles(self, part, ref) -> np.ndarray:
        """`ref` (FaceRef) yüzlerinin sınır üçgenleri; bulunamayan ref → ModelError."""
        raise NotImplementedError("SPEC 67b: PartMesh.triangles")

    def nodes(self, part, ref) -> list[int]:
        """`ref` yüzlerindeki bütün düğümler (kenar düğümü dahil), artan."""
        raise NotImplementedError("SPEC 67b: PartMesh.nodes")


def mesh_part(part, h: float, material: Material, *, order: int = 1, refine=()) -> PartMesh:
    """`mesh.tet_mesh(part, h, material, order=order, refine=refine)` + yüz eşlemesi."""
    raise NotImplementedError("SPEC 67b: mesh_part")
