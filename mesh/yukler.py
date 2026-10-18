"""
Sınır koşulları ve tutarlı düğüm yükleri: mesnet, yüzey çekmesi, basınç.

Teori: specs/12-gmsh.md
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Sequence

import numpy as np

from core.model import BC, Load, Model, ModelError
from mesh.secim import _capraz, _ucgenler

DOFLAR = ("ux", "uy", "uz")


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
    for nid in sorted(toplam):
        for dof, v in zip(DOFLAR, toplam[nid], strict=True):
            if v != 0.0:
                model.dof_index(nid, dof)
                model.loads.append(Load(nid, dof, float(v)))


def add_traction(model: Model, tris: np.ndarray, t: Sequence[float]) -> None:
    """Yüzey çekmesi t (3,) [MPa]: her köşeye t A / 3, (düğüm, dof) başına tek Load."""
    t = np.asarray(t, dtype=float).ravel()
    if t.shape != (3,) or not np.all(np.isfinite(t)):
        raise ModelError(f"Yüzey çekmesi üç sonlu bileşenli olmalı (t={t})")
    A = 0.5 * np.linalg.norm(_capraz(model, tris), axis=1)
    _dugum_yukleri(model, tris, A[:, None] * t)


def add_pressure(model: Model, tris: np.ndarray, p: float) -> None:
    """Basınç p [MPa] (pozitif: cisme bastırır): her köşeye −p n A / 3, (düğüm, dof) başına tek Load."""
    p = float(p)
    if not math.isfinite(p):
        raise ModelError(f"Basınç sonlu olmalı (p={p})")
    nA = 0.5 * _capraz(model, tris)  # n A
    _dugum_yukleri(model, tris, -p * nA)
