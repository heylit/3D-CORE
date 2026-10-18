"""
SPEC 40 — Torna ekleri: eksenel delme ve punta, ters bağlama, profilli kanal (Recess).

Koordinatlar SPEC 20 gibi: iş mili ekseni Z, X yarıçap, ön uç büyük z; yollar y = 0, G18, G95.
- Delme: matkap iş mili ekseninde (x = 0) duran freze takımıdır (Tool, DRILL / CONE); programlanan nokta uç.
  L_uç = (D/2)/tan(φ/2), punta derinliği t = (d_c/2)/tan(φ/2).
- Ters bağlama: z' = z_ref − z, x' = x; varsayılan z_ref = zmin + zmax (stok kendine gider).
- Profilli kanal: kanal ucunun alt sınırı [C_L, C_R] ⊕ D(ρ); C_L yolu h_ρ(z_L) = max_{s∈[0,a]} g(z_L + s),
  g = profilin ρ burun merkezi yolu (SPEC 20 nose_path), a = w − 2r.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING

from cam.lathe_ops import TurnCut
from cam.model import CylinderStock, LatheTool, Setup, Tool, Toolpath, Wcs
from cam.profile import Profile, Segment

if TYPE_CHECKING:
    from cam.sim import RadialMap

MODES = ("tam", "kirma")


# ---------------------------------------------------------------- A. delme ve punta


@dataclass
class DrillCut:
    """Tornada delme parametreleri [mm/dev, dev/dk, mm]."""

    feed: float  # mm/dev (G95)
    rpm: float  # dev/dk, sabit devir (G97)
    peck: float | None = None  # q, paso boyu; None → tek paso
    mode: str = "tam"  # "tam" (G83 mantığı) | "kirma" (G73/G74 mantığı)
    retract: float = 0.5  # e, talaş kırma geri çekilmesi / yeniden yaklaşma payı
    clearance: float = 1.0  # cl, yüzeyden yaklaşma payı

    def __post_init__(self) -> None:
        raise NotImplementedError("SPEC 40: DrillCut doğrulaması")


def tip_length(tool: Tool) -> float:
    """L_uç = (D/2) / tan(φ/2)."""
    raise NotImplementedError("SPEC 40: tip_length")


def center_depth(tool: Tool, d_c: float) -> float:
    """Punta derinliği t = (d_c/2) / tan(φ/2)."""
    raise NotImplementedError("SPEC 40: center_depth")


def lathe_drill(
    stock: CylinderStock,
    tool: Tool,
    cut: DrillCut,
    z_top: float,
    z_bottom: float,
    full_diameter: bool = False,
    name: str = "delme",
) -> Toolpath:
    """Eksenel delme (x = 0); full_diameter=True ise z_bottom tam çap derinliği, uç L_uç daha derinde."""
    raise NotImplementedError("SPEC 40: lathe_drill")


def lathe_center(
    stock: CylinderStock, tool: Tool, cut: DrillCut, z_top: float, d_c: float, name: str = "punta"
) -> Toolpath:
    """Punta delme: tek paso, uç z_top − center_depth(tool, d_c)."""
    raise NotImplementedError("SPEC 40: lathe_center")


# ---------------------------------------------------------------- B. ters bağlama


def flip_profile(profile: Profile, z_ref: float) -> Profile:
    """(z, x) → (z_ref − z, x); yaylar ccw değiştirir, açık profil ön→arka."""
    raise NotImplementedError("SPEC 40: flip_profile")


def flip_stock(stock: CylinderStock, z_ref: float | None = None) -> CylinderStock:
    """CylinderStock(D, z_ref − zmax, z_ref − zmin, d); z_ref None → zmin + zmax."""
    raise NotImplementedError("SPEC 40: flip_stock")


def flip_setup(
    setup: Setup,
    fixtures: Sequence[CylinderStock],
    z_ref: float | None = None,
    wcs: Wcs | None = None,
    name: str | None = None,
) -> Setup:
    """İkinci bağlama: stok ters çevrilir, bağlama elemanları yeniden verilir, wcs varsayılan G55."""
    raise NotImplementedError("SPEC 40: flip_setup")


def flip_rmap(rmap: RadialMap, setup: Setup, cell: float, z_ref: float | None = None) -> RadialMap:
    """SPEC 22 radyal haritasını ikinci bağlamanın ızgarasına ters çevirerek taşır."""
    raise NotImplementedError("SPEC 40: flip_rmap")


# ---------------------------------------------------------------- C. profilli kanal


def recess_envelope(
    profile: Profile, tool: LatheTool, allowance: float = 0.0, side: str = "dis"
) -> list[Segment]:
    """C_L yolu h_ρ (ρ = r + allowance), erişim aralığında, arkadan öne."""
    raise NotImplementedError("SPEC 40: recess_envelope")


def recess_rest(profile: Profile, tool: LatheTool, side: str = "dis") -> float:
    """İnce pasodan sonra ölçülen bölgede en büyük kalan kalınlık e_max."""
    raise NotImplementedError("SPEC 40: recess_rest")


def recess_rough(
    profile: Profile,
    x_top: float,
    stock: CylinderStock,
    tool: LatheTool,
    cut: TurnCut,
    allowance: float = 0.0,
    side: str = "dis",
    name: str = "girinti_kaba",
) -> Toolpath:
    """Dalarak kaba: m dalış, tabanlar h_ρ(z_L,j)."""
    raise NotImplementedError("SPEC 40: recess_rough")


def recess_finish(
    profile: Profile,
    x_top: float,
    stock: CylinderStock,
    tool: LatheTool,
    cut: TurnCut,
    rest_max: float = 0.0,
    side: str = "dis",
    name: str = "girinti_ince",
) -> Toolpath:
    """Yanal ince paso önden arkaya; e_max > rest_max → CamError."""
    raise NotImplementedError("SPEC 40: recess_finish")
