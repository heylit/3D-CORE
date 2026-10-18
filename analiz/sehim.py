"""
Kesme kuvveti altında sehim: takım temas noktasında statik uyum (SPEC 45).

Kuvvet, noktaya r yarıçapı içindeki sınır düğümlerine eşit bölünür; δ = F̂ · u_p, k = |F| / δ.
gmsh ve OCCT gerektirmez; her dim = 3 tet4 Model ile çalışır.

Teori: specs/45-modal.md
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np

from core.model import Model


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
    raise NotImplementedError("SPEC 45: nokta_kuvveti")


def kesme_sehimi(model: Model, nokta: Sequence[float], F: Sequence[float], yaricap: float) -> Sehim:
    """Modelin kopyasına nokta_kuvveti uygular ve çözer; verilen model değişmez (model.loads boş olmalı)."""
    raise NotImplementedError("SPEC 45: kesme_sehimi")
