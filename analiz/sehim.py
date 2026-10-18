"""
Kesme kuvveti altında sehim: takım temas noktasında statik uyum (SPEC 45).

Kuvvet, noktaya r yarıçapı içindeki sınır düğümlerine eşit bölünür; δ = F̂ · u_p, k = |F| / δ.
gmsh ve OCCT gerektirmez; her dim = 3 tet4 Model ile çalışır.

Teori: specs/45-modal.md
"""

from __future__ import annotations

import copy
from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np

import mesh
from core.model import Load, Model, ModelError
from core.solver import solve

DOF_SIRASI = ("ux", "uy", "uz")


@dataclass(frozen=True)
class Sehim:
    """Kesme sehimi sonucu."""

    dugumler: list[int]  # yük alan sınır düğümleri, artan
    u_nokta: np.ndarray  # (3,) [mm], yük alan düğümlerin ortalama yer değiştirmesi
    delta: float  # [mm], F̂ · u_nokta
    k: float  # [N/mm], |F| / delta
    u: np.ndarray  # (n_dof,) [mm]
    u_maks: float  # [mm], en büyük düğüm yer değiştirmesi büyüklüğü


def nokta_kuvveti(model: Model, nokta: Sequence[float], F: Sequence[float], yaricap: float) -> list[int]:
    """Noktaya yarıçap içindeki sınır düğümlerine F/|S| yükü ekler (model yerinde değişir); S'yi döndürür."""
    p, Fv, r = _girdiler(model, nokta, F, yaricap)
    tris = mesh.boundary_triangles(model)
    sinir = np.unique(tris)
    X = np.array([model.node(int(n)).xyz for n in sinir]).reshape(-1, 3)
    S = sorted(int(n) for n in sinir[np.linalg.norm(X - p, axis=1) <= r])
    if not S:
        raise ModelError(f"Noktanın {r} mm yarıçapında sınır düğümü yok: {p.tolist()}")
    pay = Fv / len(S)
    for n in S:
        for d, ad in enumerate(DOF_SIRASI):
            if pay[d] != 0.0:
                model.loads.append(Load(n, ad, float(pay[d])))
    return S


def kesme_sehimi(model: Model, nokta: Sequence[float], F: Sequence[float], yaricap: float) -> Sehim:
    """Modelin kopyasına nokta_kuvveti uygular ve çözer; verilen model değişmez (model.loads boş olmalı)."""
    _girdiler(model, nokta, F, yaricap)
    if model.loads:
        raise ModelError(
            "kesme_sehimi: model.loads boş olmalı (kesme kuvveti başka yüklerle sessizce toplanmaz)"
        )
    kopya = copy.deepcopy(model)
    S = nokta_kuvveti(kopya, nokta, F, yaricap)
    u = solve(kopya).u
    idx = np.array([[kopya.dof_index(n, ad) for ad in DOF_SIRASI] for n in S])
    u_nokta = u[idx].mean(axis=0)
    Fv = np.asarray(F, dtype=float)
    delta = float(Fv @ u_nokta / np.linalg.norm(Fv))
    if not delta > 0.0:
        raise ModelError(f"kesme_sehimi: sehim pozitif değil (δ={delta})")
    u_maks = float(np.linalg.norm(u.reshape(-1, 3), axis=1).max())
    return Sehim(
        dugumler=S,
        u_nokta=u_nokta,
        delta=delta,
        k=float(np.linalg.norm(Fv) / delta),
        u=u,
        u_maks=u_maks,
    )


def _girdiler(
    model: Model, nokta: Sequence[float], F: Sequence[float], yaricap: float
) -> tuple[np.ndarray, np.ndarray, float]:
    """Girdileri denetler: dim = 3, nokta ve F sonlu (3,), |F| > 0, yarıçap pozitif ve sonlu."""
    if model.dim != 3:
        raise ModelError(f"Kesme sehimi 3B model ister (dim={model.dim})")
    try:
        p = np.asarray(nokta, dtype=float)
        Fv = np.asarray(F, dtype=float)
        r = float(yaricap)
    except (TypeError, ValueError) as hata:
        raise ModelError(f"Geçersiz girdi: {hata}") from None
    if p.shape != (3,) or not np.all(np.isfinite(p)):
        raise ModelError(f"nokta sonlu (3,) dizi olmalı: {nokta}")
    if Fv.shape != (3,) or not np.all(np.isfinite(Fv)):
        raise ModelError(f"F sonlu (3,) dizi olmalı: {F}")
    if np.linalg.norm(Fv) == 0.0:
        raise ModelError("F sıfır vektör olamaz")
    if not (np.isfinite(r) and r > 0.0):
        raise ModelError(f"yaricap pozitif ve sonlu olmalı (yaricap={yaricap})")
    return p, Fv, r
