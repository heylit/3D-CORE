"""
SPEC 05 — CAD parçasının z-haritası: her hücre merkezinden geçen düşey doğrunun parçayı kestiği en yüksek Z.

Üçgen ağı (Part.mesh) hücre merkezlerinde barisentrik koordinatla örneklenir: merkez q üçgenin XY
izdüşümündeyse z = λ1·z1 + λ2·z2 + λ3·z3, hücre başına en büyük alınır. Düşey üçgenler (izdüşüm alanı 0) katkı
vermez; doğru parçaya değmiyorsa −∞.
"""

from __future__ import annotations

import numpy as np

from cam.sim.zmap import ZMap


def mesh_zmap(V: np.ndarray, T: np.ndarray, grid: ZMap) -> np.ndarray:
    """Üçgen ağından (köşeler V (n, 3), üçgenler T (m, 3)) parça z-haritası (ny, nx); değmeyen hücre −inf."""
    raise NotImplementedError("SPEC 05: uygulanmadı")


def part_zmap(part, grid: ZMap, tol: float = 0.01) -> np.ndarray:
    """geometry.part.Part için: part.mesh(tol) ağından mesh_zmap."""
    raise NotImplementedError("SPEC 05: uygulanmadı")
