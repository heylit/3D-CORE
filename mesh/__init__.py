"""
Ağ (mesh) paketi: katı parçadan tetrahedron ağı ve sınır yükleri (SPEC 12).

Dışarıya sadece buradaki adlar açılır; çıktı her zaman core.model.Model'dir.
"""

from mesh.gmsh_ag import Refine, tet_mesh
from mesh.secim import (
    boundary_triangles,
    on_cylinder,
    on_plane,
    select_nodes,
    select_triangles,
    triangle_areas,
    triangle_normals,
)
from mesh.yukler import add_pressure, add_traction, fix
from mesh.yuz_esleme import PartMesh, mesh_part

__all__ = [
    "Refine",
    "tet_mesh",
    "boundary_triangles",
    "on_plane",
    "on_cylinder",
    "select_nodes",
    "select_triangles",
    "triangle_areas",
    "triangle_normals",
    "fix",
    "add_traction",
    "add_pressure",
    "PartMesh",
    "mesh_part",
]
