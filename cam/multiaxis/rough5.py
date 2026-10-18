"""
SPEC 50 — 5 eksen kaba: yönelim kümesinde (3+2) stok bilinçli katmanlı kaba işleme.

Her yönelim F_i için ağ ve stok yerel çerçeveye çevrilir, SPEC 06 katmanlı kaba yerelde çalışır;
o ana kadarki tri-dexel stokta v_min'den az malzeme kaldıran ardışık G1'ler G0 bağlantıya çevrilir.

Birimler: mm, mm/dk, dev/dk, derece.
"""

from __future__ import annotations

from dataclasses import dataclass

from cam.dropcutter import TriMesh
from cam.model import Frame, Setup, Stock, Tool, Toolpath
from cam.multiaxis.machine import MachineModel
from cam.sim.tridexel import TriDexel


@dataclass
class RoughCut:
    """06 kaba parametreleri (SPEC 50 Ek A)."""

    ap: float  # eksenel kesme derinliği
    ae: float  # radyal adım (raster sıra aralığı)
    feed: float
    plunge_feed: float
    rpm: float
    allowance: float = 0.0
    ds: float = 1.0
    tol: float = 0.01
    ds_min: float = 0.1
    safe: float = 5.0  # yerel stok üstünden z_safe mesafesi
    clearance: float = 1.0
    direction: str = "x"
    max_tilt: float = 90.0  # yönelim ekseninin +Z ile en büyük açısı

    def __post_init__(self) -> None:
        raise NotImplementedError("SPEC 50: RoughCut doğrulaması")


def rough5(
    mesh: TriMesh,
    stock: Stock,
    tool: Tool,
    frames: list[Frame],
    cut: RoughCut,
    cell: float = 1.0,
    v_min: float | None = None,
    machine: MachineModel | None = None,
    setup: Setup | None = None,
) -> tuple[list[Toolpath], TriDexel]:
    """Yönelim listesiyle kaba işleme; her yol frame = F_i, meta (kaba, 3+2). Son stok da döner."""
    raise NotImplementedError("SPEC 50: rough5")
