"""
SPEC 41 — iş düzlemi (Frame) kurucuları, Euler açıları ve 3+2 indeksli işleme akışı.

ZXZ: R = Rz(α)·Rx(β)·Rz(γ) (Fanuc G68.2). XYZ sabit eksen: R = Rz(c)·Ry(b)·Rx(a) (Heidenhain PLANE SPATIAL).
"""

from __future__ import annotations

import numpy as np

from cam.dropcutter import TriMesh
from cam.model import Frame, Kinematics, Stock, Toolpath, Wcs


def from_normal(o, n, x_hint) -> Frame:
    """z = n/|n|, x = x_hint'in z'ye dik bileşeni (birim), y = z × x."""
    raise NotImplementedError("SPEC 41: from_normal")


def from_zxz(o, alpha: float, beta: float, gamma: float) -> Frame:
    """R = Rz(α)·Rx(β)·Rz(γ), açılar derece."""
    raise NotImplementedError("SPEC 41: from_zxz")


def from_xyz(o, a: float, b: float, c: float) -> Frame:
    """R = Rz(c)·Ry(b)·Rx(a), açılar derece."""
    raise NotImplementedError("SPEC 41: from_xyz")


def zxz_angles(frame: Frame) -> tuple[float, float, float]:
    """(α, β, γ) [derece]; tekilde γ = 0."""
    raise NotImplementedError("SPEC 41: zxz_angles")


def xyz_angles(frame: Frame) -> tuple[float, float, float]:
    """(a, b, c) [derece]; tekilde c = 0."""
    raise NotImplementedError("SPEC 41: xyz_angles")


def local_stock(stock: Stock, frame: Frame) -> Stock:
    """Stok köşelerinin yerel çerçevedeki sınır kutusu."""
    raise NotImplementedError("SPEC 41: local_stock")


def local_mesh(mesh: TriMesh, frame: Frame) -> TriMesh:
    """Üçgen ağı WCS → yerel."""
    raise NotImplementedError("SPEC 41: local_mesh")


def to_world(tp: Toolpath, arc_tol: float = 1e-3) -> Toolpath:
    """Yerel çerçeveli yol → WCS (frame = None, her Move.axis dolu, yaylar kirişlere bölünür)."""
    raise NotImplementedError("SPEC 41: to_world")


def to_machine(
    tp: Toolpath, kin: Kinematics, wcs: Wcs, L: float, prev: tuple[float, ...] | None = None
) -> np.ndarray:
    """Her nokta için eklem değerleri, (n+1, 3 + k)."""
    raise NotImplementedError("SPEC 41: to_machine")


def machine_toolpath(
    tp: Toolpath, kin: Kinematics, wcs: Wcs, L: float, prev: tuple[float, ...] | None = None
) -> tuple[Toolpath, tuple[float, ...]]:
    """Masa döner eksenli 3+2'de makine koordinatlı G17 yol ve sabit açılar."""
    raise NotImplementedError("SPEC 41: machine_toolpath")
