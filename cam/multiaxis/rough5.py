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
    """06 kaba parametreleri (SPEC 50 Ek A); yerel raster ve z_bottom yönelimde yerel stoktan türetilir."""

    a_p: float  # eksenel kesme derinliği
    stepover: float  # radyal adım (raster sıra aralığı)
    feed: float
    plunge_feed: float
    rpm: float
    allowance: float = 0.0
    clearance: float = 1.0

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
    max_tilt: float = 30.0,
) -> tuple[list[Toolpath], TriDexel]:
    """Yönelim listesiyle kaba işleme; her yol frame = F_i, meta (kaba, 3+2). Son stok da döner.

    max_tilt [°]: yönelim ekseninin +Z ile en büyük açısı (Ek A kararı, varsayılan 30°); aşan F_i → CamError.
    machine verilirse setup zorunlu; her yol 44 check ile denetlenir.
    """
    raise NotImplementedError("SPEC 50: rough5")
