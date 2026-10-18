"""
Malzeme listesi (BOM), montaj kütlesi ve ağırlık merkezi (SPEC 07).

Parça kütlesi m = ρ V (ρ [t/mm³], V [mm³], m [t]).
Ağırlık merkezi: x̄ = Σ m_i (R_i c_i + t_i) / Σ m_i   (Beer & Johnston, Statics, Bölüm 5)

Saf Python + numpy: parça yalnızca `.volume` ve `.center_of_mass` özniteliklerinden okunur.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np

from assy.model import AssyError, Node
from assy.tree import validate, walk

if TYPE_CHECKING:
    from geometry.part import Part


@dataclass(frozen=True)
class BomLine:
    item: str  # parça kimliği veya alt montaj tanımı
    kind: str  # "parca" | "montaj"
    qty: int
    unit_mass: float | None  # t; kütle verilmediyse None
    total_mass: float | None  # qty · unit_mass


def _pozitif(x, ne: str) -> float:
    try:
        v = float(x)
    except (TypeError, ValueError):
        raise AssyError(f"{ne} sayı olmalı ({x!r})") from None
    if not math.isfinite(v) or v <= 0:
        raise AssyError(f"{ne} sonlu ve > 0 olmalı ({x!r})")
    return v


def _yapraklar(n: Node) -> list[tuple[Node, np.ndarray]]:
    return [(m, T) for _, m, T in walk(n) if m.part is not None]


def _kutleler(root: Node, unit_mass: Mapping[str, float]) -> dict[str, float]:
    """Ağaçtaki her parça kimliğinin doğrulanmış birim kütlesi."""
    out = {}
    for n, _ in _yapraklar(root):
        if n.part not in out:
            if n.part not in unit_mass:
                raise AssyError(f"Parça '{n.part}' için birim kütle yok")
            out[n.part] = _pozitif(unit_mass[n.part], f"'{n.part}' birim kütlesi")
    return out


def unit_masses(parts: Mapping[str, Part], rho: float | Mapping[str, float]) -> dict[str, float]:
    """m = ρ · part.volume, parça kimliği başına. rho sözlükse her kimlik için olmalı."""
    out = {}
    for kimlik, p in parts.items():
        if isinstance(rho, Mapping):
            if kimlik not in rho:
                raise AssyError(f"Parça '{kimlik}' için yoğunluk yok")
            r = rho[kimlik]
        else:
            r = rho
        out[kimlik] = _pozitif(r, f"'{kimlik}' yoğunluğu") * float(p.volume)
    return out


def bom(root: Node, unit_mass: Mapping[str, float] | None = None, flat: bool = True) -> list[BomLine]:
    """flat=True: tüm yapraklar parça kimliğine göre; flat=False: kökün doğrudan çocukları tanıma göre.

    Satırlar walk sırasında ilk görülme sırasıyla.
    """
    validate(root)
    m = _kutleler(root, unit_mass) if unit_mass is not None else None

    # kalem -> (tür, adet, birim kütle)
    kalemler: dict[str, list] = {}
    if flat:
        for n, _ in _yapraklar(root):
            kalem = kalemler.setdefault(n.part, ["parca", 0, m[n.part] if m else None])
            kalem[1] += 1
    else:
        for c in root.children:
            tur = "parca" if c.part is not None else "montaj"
            bm = sum(m[y.part] for y, _ in _yapraklar(c)) if m else None
            kalem = kalemler.setdefault(c.definition, [tur, 0, bm])
            kalem[1] += 1
    return [
        BomLine(item=k, kind=tur, qty=q, unit_mass=bm, total_mass=None if bm is None else q * bm)
        for k, (tur, q, bm) in kalemler.items()
    ]


def total_mass(root: Node, unit_mass: Mapping[str, float]) -> float:
    """M = Σ q_p m_p."""
    return float(sum(s.total_mass for s in bom(root, unit_mass)))


def mass_center(root: Node, parts: Mapping[str, Part], unit_mass: Mapping[str, float]) -> np.ndarray:
    """Montaj ağırlık merkezi x̄ (3,), dünya koordinatında: Σ m_i (R_i c_i + t_i) / Σ m_i."""
    validate(root)
    m = _kutleler(root, unit_mass)
    toplam_m, moment = 0.0, np.zeros(3)
    for n, T in _yapraklar(root):
        if n.part not in parts:
            raise AssyError(f"Parça '{n.part}' parts içinde yok")
        c = np.asarray(parts[n.part].center_of_mass, dtype=float)
        toplam_m += m[n.part]
        moment += m[n.part] * (T[:3, :3] @ c + T[:3, 3])
    return moment / toplam_m
