"""
Doğrusal statik çözücü:  K u = F

Teori: specs/01-bar.md
"""

from __future__ import annotations

import warnings

import numpy as np
import scipy.sparse.linalg as spla

from core import post
from core.assembly import assemble_F, assemble_K
from core.model import Model, ModelError, Result

# Bu boyuta kadar K_ff yoğun matrise çevrilip koşul sayısı kontrol edilir.
YOGUN_SINIR = 2000
KOSUL_SINIRI = 1e12


def _cozumle(K_ff, b: np.ndarray) -> np.ndarray:
    """K_ff u_f = b. Tekil / kötü koşullu sistemde ModelError."""
    n = K_ff.shape[0]
    if n == 0:
        return np.zeros(0)
    if n <= YOGUN_SINIR and np.linalg.cond(K_ff.toarray()) > KOSUL_SINIRI:
        raise ModelError("K_ff tekil veya kötü koşullu: mesnet eksik olabilir (mekanizma)")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", spla.MatrixRankWarning)
            u_f = np.atleast_1d(spla.spsolve(K_ff.tocsc(), b))
    except (spla.MatrixRankWarning, RuntimeError) as hata:
        raise ModelError(f"K_ff tekil: mesnet eksik olabilir (mekanizma): {hata}") from None
    if not np.all(np.isfinite(u_f)):
        raise ModelError("Çözüm sonlu değil: K_ff tekil (mekanizma)")
    return u_f


def solve(model: Model) -> Result:
    """
    1. model.validate()
    2. K, F birleştir
    3. DOF'ları serbest (f) / tutulu (c) diye ayır, tutulu DOF'lara BC değerini yaz
    4. K_ff u_f = F_f - K_fc u_c   çöz
    5. Tepkiler: R = K u - F  (sadece tutulu DOF'larda, diğerleri 0)
    6. Eleman kuvvet ve gerilmelerini post.py ile hesapla
    Mekanizma (tekil K_ff) -> ModelError
    """
    model.validate()
    K = assemble_K(model)
    F = assemble_F(model)
    n = model.n_dof

    u = np.zeros(n)
    tutulu = np.zeros(n, dtype=bool)
    for bc in model.bcs:
        i = model.dof_index(bc.node, bc.dof)
        if tutulu[i] and u[i] != bc.value:
            raise ModelError(f"Düğüm {bc.node} '{bc.dof}' için çelişen sınır koşulları")
        tutulu[i] = True
        u[i] = bc.value
    c = np.flatnonzero(tutulu)
    f = np.flatnonzero(~tutulu)

    K_ff = K[f][:, f]
    K_fc = K[f][:, c]
    u[f] = _cozumle(K_ff, F[f] - K_fc @ u[c])

    R = np.zeros(n)
    R[c] = (K @ u - F)[c]

    return Result(
        u=u,
        reactions=R,
        element_forces=post.element_forces(model, u),
        element_stresses=post.element_stresses(model, u),
    )
