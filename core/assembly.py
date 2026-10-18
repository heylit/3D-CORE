"""
Global rijitlik matrisi ve yük vektörü birleştirme (tüm eleman tipleri için ortak).

Uygulanacak: specs/01-bar.md
"""

from __future__ import annotations

import numpy as np
import scipy.sparse as sp

from core.model import Model


def assemble_K(model: Model) -> sp.csr_matrix:
    """Tüm elemanların ke matrislerini global K'ya ekler (n_dof x n_dof, seyrek)."""
    raise NotImplementedError("specs/01-bar.md uygulanacak")


def assemble_F(model: Model) -> np.ndarray:
    """Düğüm kuvvetlerinden global F vektörü (n_dof). Aynı DOF'a birden fazla yük toplanır."""
    raise NotImplementedError("specs/01-bar.md uygulanacak")
