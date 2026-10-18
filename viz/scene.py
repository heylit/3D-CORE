"""
SPEC 15 — Görüntüleyici sahne verisi (saf numpy, pyvista gerektirmez).

Takım yolunu (G2/G3 yayları kiriş sapması ≤ tol ile çokgene çevrilerek) çizgilere, montajı dünya
koordinatındaki üçgen ağlarına, ham malzemeyi kutu kenarlarına çevirir. Yalnızca arayüzleri kullanır:
geometry.part.Part, cam.model, assy.model.

Birimler: mm.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from assy.model import Assembly
from cam.model import MoveType, Stock, Toolpath


class VizError(ValueError):
    """Çizilemeyen girdi (boş takım yolu, eksik parça, geçersiz tolerans / görünüm...)."""


# Montaj bileşen renkleri: sırayla, döngüsel.
PALETTE: tuple[str, ...] = (
    "steelblue",
    "darkorange",
    "seagreen",
    "firebrick",
    "mediumpurple",
    "sienna",
    "orchid",
    "gray",
)


@dataclass(frozen=True)
class ComponentMesh:
    """Bir bileşenin dünya koordinatındaki ağı. V (n, 3) mm, T (m, 3) üçgen indeksleri, color: PALETTE'ten."""

    name: str
    V: np.ndarray
    T: np.ndarray
    color: str


def _arc_points(p0: np.ndarray, p1: np.ndarray, c: np.ndarray, cw: bool, tol: float) -> np.ndarray:
    """Yayın ara noktaları ve bitişi, (n, 3): θ_k = θ₀ ± k φ, z doğrusal; son nokta tam p1."""
    v0 = p0[:2] - c
    r = float(np.hypot(*v0))
    theta0 = math.atan2(v0[1], v0[0])
    dtheta = math.atan2(p1[1] - c[1], p1[0] - c[0]) - theta0
    if cw:
        dtheta = -dtheta
    dtheta %= 2 * math.pi
    if dtheta < 1e-12:
        dtheta = 2 * math.pi  # başlangıç = bitiş: tam daire (cam.model ile aynı tanım)

    phi_max = math.pi if tol >= r else 2 * math.acos(1 - tol / r)
    n = max(1, math.ceil(dtheta / min(phi_max, math.pi / 2)))
    k = np.arange(1, n + 1)
    theta = theta0 + (-1 if cw else 1) * k * (dtheta / n)
    P = np.column_stack([c[0] + r * np.cos(theta), c[1] + r * np.sin(theta), p0[2] + (p1[2] - p0[2]) * k / n])
    P[-1] = p1
    return P


def toolpath_polyline(tp: Toolpath, tol: float = 0.01) -> tuple[np.ndarray, np.ndarray]:
    """Noktalar P (k+1, 3) (ilk nokta tp.start) ve parça tipleri kinds (k,) (MoveType, dtype object)."""
    if not tol > 0:
        raise VizError(f"Kiriş toleransı pozitif olmalı (tol={tol})")
    tp.validate()
    if not tp.moves:
        raise VizError(f"Takım yolu '{tp.name}': hareket yok, çizilecek bir şey yok")

    p0 = np.array(tp.start, dtype=float)
    parcalar = [p0[None, :]]
    kinds: list[MoveType] = []
    for m in tp.moves:
        p1 = np.array(m.end, dtype=float)
        if m.type in (MoveType.ARC_CW, MoveType.ARC_CCW):
            Q = _arc_points(p0, p1, np.array(m.center, dtype=float), m.type is MoveType.ARC_CW, tol)
        else:
            Q = p1[None, :]
        parcalar.append(Q)
        kinds.extend([m.type] * len(Q))
        p0 = p1
    return np.vstack(parcalar), np.array(kinds, dtype=object)


def split_rapid_feed(P: np.ndarray, kinds: np.ndarray) -> tuple[list[np.ndarray], list[np.ndarray]]:
    """Art arda aynı türden parçaları birleştirir: (hızlı çizgiler, kesme çizgileri), her biri (m, 3)."""
    P = np.asarray(P, dtype=float)
    if P.ndim != 2 or P.shape[1] != 3 or len(kinds) != len(P) - 1 or len(kinds) == 0:
        raise VizError(f"Çokgen ve parça tipleri uyuşmuyor (P {P.shape}, kinds {len(kinds)})")
    hizli: list[np.ndarray] = []
    kesme: list[np.ndarray] = []
    i = 0
    while i < len(kinds):
        rapid = kinds[i] is MoveType.RAPID
        j = i
        while j + 1 < len(kinds) and (kinds[j + 1] is MoveType.RAPID) == rapid:
            j += 1
        (hizli if rapid else kesme).append(P[i : j + 2].copy())
        i = j + 1
    return hizli, kesme


def assembly_meshes(assy: Assembly, parts: dict, tol: float = 0.01) -> list[ComponentMesh]:
    """Her bileşenin ağı dünya koordinatında (V' = V Rᵀ + t). parts: Component.part → Part."""
    assy.validate()
    if not assy.components:
        raise VizError(f"Montaj '{assy.name}': bileşen yok, çizilecek bir şey yok")
    eksik = [f"{c.name} ({c.part})" for c in assy.components if c.part not in parts]
    if eksik:
        raise VizError(f"Montaj '{assy.name}': parçası verilmeyen bileşenler: {', '.join(eksik)}")

    aglar: dict[str, tuple[np.ndarray, np.ndarray]] = {}  # aynı parça bir kez üçgenlenir
    sonuc = []
    for i, c in enumerate(assy.components):
        if c.part not in aglar:
            aglar[c.part] = parts[c.part].mesh(tol)
        V, T = aglar[c.part]
        R, t = c.T[:3, :3], c.T[:3, 3]
        sonuc.append(ComponentMesh(c.name, V @ R.T + t, T.copy(), PALETTE[i % len(PALETTE)]))
    return sonuc


def stock_box(stock: Stock) -> tuple[np.ndarray, np.ndarray]:
    """Ham malzeme kutusunun 8 köşesi (8, 3) ve 12 kenarı (12, 2) indeks."""
    # köşe indeksi = 4·ix + 2·iy + iz (her biri 0: min, 1: max)
    C = np.array(
        [
            (x, y, z)
            for x in (stock.xmin, stock.xmax)
            for y in (stock.ymin, stock.ymax)
            for z in (stock.zmin, stock.zmax)
        ],
        dtype=float,
    )
    # bir bitin değiştiği köşe çiftleri: bit 4 → x, 2 → y, 1 → z kenarları
    E = np.array([(i, i | b) for b in (4, 2, 1) for i in range(8) if not i & b], dtype=int)
    return C, E
