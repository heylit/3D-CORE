"""
Doğrusal statik çözücü:  K u = F

Teori: specs/01-bar.md
"""

from __future__ import annotations

import numpy as np
import scipy.sparse as sp
import scipy.sparse.linalg as spla
from scipy.sparse.csgraph import reverse_cuthill_mckee

from core import post
from core.assembly import assemble_F, assemble_K
from core.model import Model, ModelError, Result

# Simetrik eliminasyonda pivot / köşegen oranı bunun altındaysa K_ff tekildir.
# Mekanizmada bu oran yuvarlama düzeyindedir (~1e-16); geçerli modelde rijitlik
# oranları kadar küçülebilir (ör. 1e-6 MPa'lık eleman çelik içinde: ~5e-12).
PIVOT_SINIRI = 1e-13


def _cozumle(K_ff, b: np.ndarray) -> np.ndarray:
    """
    K_ff u_f = b, simetrik pozitif tanımlı K_ff için.

    Tekillik testi (model boyundan bağımsız): K_ff = L D Lᵀ ayrışımında her pivot
    d_i kendi köşegeni K_ii ile karşılaştırılır. Rijit cisim modu (mekanizma)
    varsa bir pivot sıfıra düşer: d_i <= PIVOT_SINIRI · K_ii -> ModelError.
    Satır değişimi yapılmaz (diag_pivot_thresh=0), böylece U'nun köşegeni D olur;
    dolgu az olsun diye önce ters Cuthill-McKee ile yeniden numaralanır.
    """
    n = K_ff.shape[0]
    if n == 0:
        return np.zeros(0)
    K_ff = sp.csr_matrix(K_ff)
    p = reverse_cuthill_mckee(K_ff, symmetric_mode=True)
    B = K_ff[p][:, p].tocsc()
    K_ii = B.diagonal()
    if np.any(K_ii <= 0.0):
        raise ModelError(
            "FEM modeli: K_ff tekil, rijitliği olmayan serbest DOF var (mekanizma) — "
            "eksik mesnet ekleyin ya da bağlanmamış düğümleri kaldırın"
        )
    try:
        lu = spla.splu(
            B,
            permc_spec="NATURAL",
            diag_pivot_thresh=0.0,
            options={"SymmetricMode": True},
        )
    except RuntimeError as hata:
        raise ModelError(
            "FEM modeli: K_ff tekil, mesnet eksik olabilir (mekanizma) — "
            "her yönde rijit cisim hareketini engelleyecek mesnet ekleyin"
        ) from hata
    d = lu.U.diagonal()
    if not np.array_equal(lu.perm_r, np.arange(n)) or np.any(d <= PIVOT_SINIRI * K_ii):
        raise ModelError(
            "FEM modeli: K_ff tekil, mesnet eksik olabilir (mekanizma) — "
            "her yönde rijit cisim hareketini engelleyecek mesnet ekleyin"
        )
    u_f = np.empty(n)
    u_f[p] = lu.solve(np.asarray(b, dtype=float)[p])
    if not np.all(np.isfinite(u_f)):
        raise ModelError(
            "FEM modeli: çözüm sonlu değil, K_ff tekil (mekanizma) — "
            "mesnetleri ve malzeme değerlerini (E, A) denetleyin"
        )
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
