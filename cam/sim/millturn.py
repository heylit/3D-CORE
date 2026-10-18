"""
SPEC 49 — Torna-freze simülasyonu: önce torna işlemleri SPEC 22 RadialMap'te, ilk freze işleminden önce
RadialMap → TriDexel (kutu [−R, R]² × [zmin, zmax]), freze işlemleri parça çerçevesinde SPEC 43 kurallarıyla
(C açısı R_z(−C) ile parçaya çevrilir; polar / silindirik yollar önce kartezyen kirişlere açılır).
Frezeden sonra torna işlemi → CamError.
"""

from __future__ import annotations

from collections.abc import Sequence

from cam.model import CylinderStock, MachineProfile, Toolpath
from cam.sim.radial import RadialMap
from cam.sim.simulate5 import SimResult5
from cam.sim.timing import Machine
from cam.sim.tridexel import TriDexel


def rmap_to_tridexel(rmap: RadialMap, cell: float, max_rays: int = 3_000_000) -> TriDexel:
    """Dönel haritayı kutu [−r_max, r_max]² × [z0, z0 + nz·dz] üzerinde tri-dexel'e çevirir."""
    raise NotImplementedError


def to_part_frame(tp: Toolpath, arc_tol: float = 1e-3) -> Toolpath:
    """Freze yolunu parça çerçevesinde kartezyen yola çevirir: Move.c ile R_z(−C), polar / silindirik
    açılım."""
    raise NotImplementedError


def simulate_mt(
    ops: list[Toolpath],
    stock: CylinderStock,
    machine: MachineProfile,
    cell: float = 0.5,
    part=None,
    fixtures: Sequence[CylinderStock] = (),
    timing: Machine | None = None,
    arc_tol: float = 1e-3,
    tol: float = 1e-6,
    gouge_tol: float = 1e-3,
) -> SimResult5:
    """Torna + freze programını simüle eder; machine.kind != "millturn" → CamError."""
    raise NotImplementedError
