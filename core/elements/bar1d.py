"""
1D çubuk elemanı (2 düğüm, düğüm başına 1 DOF: ux).

Teori: specs/01-bar.md (Logan, Bölüm 2–3).
"""

from __future__ import annotations

import numpy as np

from core.model import Element, Model, ModelError


def length(element: Element, model: Model) -> float:
    """Eleman boyu L = |x2 - x1| [mm]. L <= 1e-12 ise ModelError."""
    n1, n2 = (model.node(nid) for nid in element.nodes)
    L = abs(n2.x - n1.x)
    if L <= 1e-12:
        raise ModelError(f"Eleman {element.id}: sıfır boy (L={L})")
    return L


def _EA_L(element: Element, model: Model) -> float:
    """Eksenel rijitlik E*A/L [N/mm]."""
    E = model.material(element.material).E
    A = model.section(element.section).A
    return E * A / length(element, model)


def ke(element: Element, model: Model) -> np.ndarray:
    """k = (E*A/L) * [[1, -1], [-1, 1]]"""
    return _EA_L(element, model) * np.array([[1.0, -1.0], [-1.0, 1.0]])


def dofs(element: Element, model: Model) -> list[int]:
    """ke satır/sütunlarının global DOF numaraları (element.nodes sırasında)."""
    return [model.dof_index(nid, "ux") for nid in element.nodes]


def axial_force(element: Element, model: Model, u: np.ndarray) -> float:
    """N = (E*A/L) * (u_sağ - u_sol)  [N], pozitif = çekme.

    Düğüm sırası ters verilse de (x2 < x1) uzama sağ uç eksi sol uç olarak alınır.
    """
    n1, n2 = (model.node(nid) for nid in element.nodes)
    u1, u2 = (u[i] for i in dofs(element, model))
    uzama = (u2 - u1) if n2.x > n1.x else (u1 - u2)
    return float(_EA_L(element, model) * uzama)


def me(element: Element, model: Model, lumped: bool = False) -> np.ndarray:
    """Kütle matrisi [t] (specs/45-modal.md).

    tutarlı:   ρAL/6 · [[2, 1], [1, 2]]      toplanmış: ρAL/2 · I₂
    ρ ≤ 0 → ModelError.
    """
    rho = model.material(element.material).rho
    if rho <= 0.0:
        raise ModelError(f"Eleman {element.id}: kütle matrisi için ρ > 0 olmalı (ρ={rho})")
    m = rho * model.section(element.section).A * length(element, model)
    if lumped:
        return m / 2.0 * np.eye(2)
    return m / 6.0 * np.array([[2.0, 1.0], [1.0, 2.0]])
