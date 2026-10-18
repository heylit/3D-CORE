"""
Sınır koşulları ve tutarlı düğüm yükleri: mesnet, yüzey çekmesi, basınç.

Teori: specs/12-gmsh.md
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Sequence

import numpy as np

from core.model import BC, Load, Model, ModelError
from mesh.secim import _capraz, _ucgenler, _xyz

DOFLAR = ("ux", "uy", "uz")

# 6 noktalı Dunavant kuralı (4. derece) alan koordinatlarında; Σw = 1 (referans alanı ½ ayrıca çarpılır)
_DA, _DB = 0.445948490915965, 0.091576213509771
DUNAVANT_L = np.array(
    [
        [1 - 2 * _DA, _DA, _DA],
        [_DA, 1 - 2 * _DA, _DA],
        [_DA, _DA, 1 - 2 * _DA],
        [1 - 2 * _DB, _DB, _DB],
        [_DB, 1 - 2 * _DB, _DB],
        [_DB, _DB, 1 - 2 * _DB],
    ]
)
DUNAVANT_W = np.array([0.223381589678011] * 3 + [0.109951743655322] * 3)

# tri6 kenarları (0 tabanlı): 3 (0–1), 4 (1–2), 5 (2–0)
_TRI6_KENAR = ((0, 1), (1, 2), (2, 0))
# L1 = 1 − ξ − η, L2 = ξ, L3 = η → ∂L / ∂(ξ, η)
_DL_DXI = np.array([[-1.0, -1.0], [1.0, 0.0], [0.0, 1.0]])


def _tri6_N(L: np.ndarray) -> np.ndarray:
    """tri6 şekil fonksiyonları (6,): köşe L_i(2L_i − 1), kenar 4 L_i L_j."""
    return np.concatenate([L * (2.0 * L - 1.0), [4.0 * L[i] * L[j] for i, j in _TRI6_KENAR]])


def _tri6_dN(L: np.ndarray) -> np.ndarray:
    """∂N_a / ∂(ξ, η) (6 x 2)."""
    G = np.zeros((6, 3))
    G[range(3), range(3)] = 4.0 * L - 1.0
    for a, (i, j) in enumerate(_TRI6_KENAR, start=3):
        G[a, i] = 4.0 * L[j]
        G[a, j] = 4.0 * L[i]
    return G @ _DL_DXI


def _tri6_kuvvetler(model: Model, tris, yogunluk) -> dict[int, np.ndarray]:
    """f_a = ∫ N_a q dA, 6 noktalı Dunavant; q = yogunluk(a), a = ∂x/∂ξ × ∂x/∂η (= n dA / dξdη).

    Düz üçgende düzgün yükte köşeler 0, kenar düğümleri q A / 3 alır.
    """
    T = _ucgenler(tris)
    P = _xyz(model, T)  # (k, 6, 3)
    toplam: dict[int, np.ndarray] = {}
    for dugumler, X in zip(T.tolist(), P, strict=True):
        f = np.zeros((6, 3))
        for L, w in zip(DUNAVANT_L, DUNAVANT_W, strict=True):
            dX = X.T @ _tri6_dN(L)  # (3, 2): ∂x/∂ξ, ∂x/∂η
            a = np.cross(dX[:, 0], dX[:, 1])
            f += 0.5 * w * np.outer(_tri6_N(L), yogunluk(a))
        for nid, fa in zip(dugumler, f, strict=True):
            toplam[nid] = toplam.get(nid, np.zeros(3)) + fa
    return toplam


def _yukleri_yaz(model: Model, toplam: dict[int, np.ndarray]) -> None:
    """(düğüm, dof) başına tek Load, düğüm id sırasında; sıfır bileşen yazılmaz."""
    for nid in sorted(toplam):
        for dof, v in zip(DOFLAR, toplam[nid], strict=True):
            if v != 0.0:
                model.dof_index(nid, dof)
                model.loads.append(Load(nid, dof, float(v)))


def fix(
    model: Model,
    node_ids: Iterable[int],
    dofs: Sequence[str] = ("ux", "uy", "uz"),
    value: float = 0.0,
) -> None:
    """Her (düğüm, dof) için BC ekler; aynı değerle tutuluysa atlar, farklı değer -> ModelError."""
    value = float(value)
    if not math.isfinite(value):
        raise ModelError(f"Mesnet değeri sonlu olmalı (value={value})")
    mevcut = {(bc.node, bc.dof): bc.value for bc in model.bcs}
    for nid in node_ids:
        nid = int(nid)
        for dof in dofs:
            model.dof_index(nid, dof)  # bilinmeyen düğüm / dof -> ModelError
            anahtar = (nid, dof)
            if anahtar in mevcut:
                if mevcut[anahtar] != value:
                    raise ModelError(
                        f"Düğüm {nid} {dof} zaten {mevcut[anahtar]} değeriyle tutulu, {value} verilemez"
                    )
                continue
            model.bcs.append(BC(nid, dof, value))
            mevcut[anahtar] = value


def _dugum_yukleri(model: Model, tris, F_ucgen: np.ndarray) -> None:
    """Üçgen başına kuvvet (k, 3) -> her köşeye F/3, (düğüm, dof) başına tek Load (düğüm id, ux, uy, uz)."""
    T = _ucgenler(tris)
    toplam: dict[int, np.ndarray] = {}
    for kose, F in zip(T.tolist(), F_ucgen / 3.0, strict=True):
        for nid in kose:
            toplam[nid] = toplam.get(nid, np.zeros(3)) + F
    _yukleri_yaz(model, toplam)


def _tri6_mi(tris) -> bool:
    return _ucgenler(tris).shape[1] == 6


def add_traction(model: Model, tris: np.ndarray, t: Sequence[float]) -> None:
    """Yüzey çekmesi t (3,) [MPa], (düğüm, dof) başına tek Load.

    tri3 (k, 3): her köşeye t A / 3. tri6 (k, 6): f_a = ∫ N_a t dA (düz üçgende köşeler 0, kenarlar t A / 3).
    """
    t = np.asarray(t, dtype=float).ravel()
    if t.shape != (3,) or not np.all(np.isfinite(t)):
        raise ModelError(f"Yüzey çekmesi üç sonlu bileşenli olmalı (t={t})")
    if _tri6_mi(tris):
        _yukleri_yaz(model, _tri6_kuvvetler(model, tris, lambda a: np.linalg.norm(a) * t))
        return
    A = 0.5 * np.linalg.norm(_capraz(model, tris), axis=1)
    _dugum_yukleri(model, tris, A[:, None] * t)


def add_pressure(model: Model, tris: np.ndarray, p: float) -> None:
    """Basınç p [MPa] (pozitif: cisme bastırır): t = −p n, (düğüm, dof) başına tek Load.

    tri3: her köşeye −p n A / 3. tri6: f_a = ∫ N_a (−p n) dA, eğri yüzde de doğru (n dA izoparametrik).
    """
    p = float(p)
    if not math.isfinite(p):
        raise ModelError(f"Basınç sonlu olmalı (p={p})")
    if _tri6_mi(tris):
        _yukleri_yaz(model, _tri6_kuvvetler(model, tris, lambda a: -p * a))
        return
    nA = 0.5 * _capraz(model, tris)  # n A
    _dugum_yukleri(model, tris, -p * nA)
