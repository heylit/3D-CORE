"""
3B dört düğümlü doğrusal tetrahedron elemanı (tet4, düğüm başına 3 DOF: ux, uy, uz).

Teori: specs/11-tet4.md (Logan, Bölüm 11; Zienkiewicz–Taylor–Zhu, Bölüm 6).
İskelet: gövdeler SPEC 11 testleri yazıldıktan sonra doldurulacak.
"""

from __future__ import annotations

import numpy as np

from core.model import Element, Material, Model


def volume(element: Element, model: Model) -> float:
    """V = |det C| / 6 [mm³]. Bozuk (yassı) eleman → ModelError."""
    raise NotImplementedError("SPEC 11: tet4.volume")


def B(element: Element, model: Model) -> np.ndarray:
    """Şekil değiştirme – yer değiştirme matrisi (6 x 12), Voigt: xx, yy, zz, xy, xz, yz."""
    raise NotImplementedError("SPEC 11: tet4.B")


def D(material: Material) -> np.ndarray:
    """İzotrop doğrusal elastik malzeme matrisi (6 x 6). ν ∉ (−1, 0.5) → ModelError."""
    raise NotImplementedError("SPEC 11: tet4.D")


def ke(element: Element, model: Model) -> np.ndarray:
    """ke = V · Bᵀ D B  (12 x 12)."""
    raise NotImplementedError("SPEC 11: tet4.ke")


def dofs(element: Element, model: Model) -> list[int]:
    """[ux1, uy1, uz1, ..., uz4], element.nodes sırasında."""
    raise NotImplementedError("SPEC 11: tet4.dofs")


def strain(element: Element, model: Model, u: np.ndarray) -> np.ndarray:
    """ε = B d  (6,)."""
    raise NotImplementedError("SPEC 11: tet4.strain")


def stress(element: Element, model: Model, u: np.ndarray) -> np.ndarray:
    """σ = D B d  (6,) [MPa]."""
    raise NotImplementedError("SPEC 11: tet4.stress")
