"""
Global rijitlik matrisi ve yük vektörü birleştirme (tüm eleman tipleri için ortak).

Teori: specs/01-bar.md
"""

from __future__ import annotations

import numpy as np
import scipy.sparse as sp

from core import elements
from core.model import Model, ModelError


def assemble_K(model: Model) -> sp.csr_matrix:
    """Tüm elemanların ke matrislerini global K'ya ekler (n_dof x n_dof, seyrek).

    COO biçiminde (satır, sütun, değer) üçlüleri toplanır; tocsr() aynı konumdaki
    değerleri otomatik olarak TOPLAR, bu da birleştirmenin kendisidir.
    """
    rows: list[int] = []
    cols: list[int] = []
    vals: list[float] = []
    for e in model.elements:
        eleman = elements.get(e.type)
        k = eleman.ke(e, model)
        d = np.asarray(eleman.dofs(e, model))
        rows.extend(np.repeat(d, len(d)))
        cols.extend(np.tile(d, len(d)))
        vals.extend(k.ravel())
    n = model.n_dof
    return sp.coo_matrix((vals, (rows, cols)), shape=(n, n)).tocsr()


def assemble_F(model: Model) -> np.ndarray:
    """Düğüm kuvvetlerinden global F vektörü (n_dof). Aynı DOF'a birden fazla yük toplanır."""
    F = np.zeros(model.n_dof)
    for ld in model.loads:
        F[model.dof_index(ld.node, ld.dof)] += ld.value
    return F


def assemble_M(model: Model, lumped: bool = False) -> sp.csr_matrix:
    """Tüm elemanların me matrislerini global M'ye ekler (n_dof x n_dof, seyrek) [t].

    assemble_K ile aynı COO birleştirmesi. Eleman me sağlamıyorsa ModelError.
    Teori: specs/45-modal.md
    """
    rows: list[int] = []
    cols: list[int] = []
    vals: list[float] = []
    for e in model.elements:
        eleman = elements.get(e.type)
        if not hasattr(eleman, "me"):
            raise ModelError(f"Eleman tipi '{e.type}' kütle matrisi (me) sağlamıyor")
        m = eleman.me(e, model, lumped=lumped)
        d = np.asarray(eleman.dofs(e, model))
        rows.extend(np.repeat(d, len(d)))
        cols.extend(np.tile(d, len(d)))
        vals.extend(m.ravel())
    n = model.n_dof
    return sp.coo_matrix((vals, (rows, cols)), shape=(n, n)).tocsr()


def assemble_Kg(model: Model, sigma0: dict[int, np.ndarray]) -> sp.csr_matrix:
    """Tüm elemanların kg matrislerini global Kg'ye ekler (n_dof x n_dof, seyrek).

    sigma0: eleman id -> eleman gerilmesi (tet4: (6,) Voigt). kg sağlamayan eleman tipi
    veya sigma0'da olmayan eleman → ModelError. Teori: specs/68a-burkulma.md
    """
    rows: list[int] = []
    cols: list[int] = []
    vals: list[float] = []
    for e in model.elements:
        eleman = elements.get(e.type)
        if not hasattr(eleman, "kg"):
            raise ModelError(f"Eleman tipi '{e.type}' geometrik rijitlik (kg) sağlamıyor")
        if e.id not in sigma0:
            raise ModelError(f"Eleman {e.id} için başlangıç gerilmesi (sigma0) verilmedi")
        k = eleman.kg(e, model, sigma0[e.id])
        d = np.asarray(eleman.dofs(e, model))
        rows.extend(np.repeat(d, len(d)))
        cols.extend(np.tile(d, len(d)))
        vals.extend(k.ravel())
    n = model.n_dof
    return sp.coo_matrix((vals, (rows, cols)), shape=(n, n)).tocsr()
