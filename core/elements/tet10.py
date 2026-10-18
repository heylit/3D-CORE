"""
3B on düğümlü ikinci dereceden tetrahedron elemanı (tet10, düğüm başına 3 DOF: ux, uy, uz).

Düğüm sırası CalculiX/Abaqus C3D10: köşeler 1–4,
kenarlar 5 (1–2), 6 (2–3), 7 (3–1), 8 (1–4), 9 (2–4), 10 (3–4).
Teori: specs/67-fem-genisletme.md (67a).
İskelet: gövdeler SPEC 67a testleri yazıldıktan sonra doldurulacak.
"""

from __future__ import annotations

import numpy as np

from core.model import Element, Model


def volume(element: Element, model: Model) -> float:
    """V = Σ_g w_g det J [mm³]. det J ≤ 0 olan Gauss noktası → ModelError."""
    raise NotImplementedError("SPEC 67a: tet10.volume")


def ke(element: Element, model: Model) -> np.ndarray:
    """ke = Σ_g w_g Bᵀ D B det J  (30 x 30), 4 noktalı Gauss kuralı."""
    raise NotImplementedError("SPEC 67a: tet10.ke")


def dofs(element: Element, model: Model) -> list[int]:
    """[ux1, uy1, uz1, ..., uz10], element.nodes sırasında."""
    raise NotImplementedError("SPEC 67a: tet10.dofs")


def me(element: Element, model: Model, lumped: bool = False) -> np.ndarray:
    """Tutarlı kütle matrisi (30 x 30) [t], 15 noktalı Keast kuralı. lumped=True → ModelError."""
    raise NotImplementedError("SPEC 67a: tet10.me")


def stress_gauss(element: Element, model: Model, u: np.ndarray) -> np.ndarray:
    """4 Gauss noktasında σ (4, 6) [MPa], Voigt: xx, yy, zz, xy, xz, yz."""
    raise NotImplementedError("SPEC 67a: tet10.stress_gauss")


def stress(element: Element, model: Model, u: np.ndarray) -> np.ndarray:
    """Eleman gerilmesi σ (6,) [MPa]: Gauss noktalarının ortalaması."""
    raise NotImplementedError("SPEC 67a: tet10.stress")


def stress_nodes(element: Element, model: Model, u: np.ndarray) -> np.ndarray:
    """Düğüm gerilmeleri (10, 6) [MPa]: köşelere doğrusal dış değerleme, kenarlara iki köşenin ortalaması."""
    raise NotImplementedError("SPEC 67a: tet10.stress_nodes")
