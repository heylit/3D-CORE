"""
Kesme kuvveti (Kienzle), kesme gücü, iş mili torku ve iş mili sınırı denetimi. SPEC 32.

Birimler: kuvvet N, uzunluk mm, özgül kesme kuvveti N/mm² (= MPa), güç kW, tork N·m,
talaş debisi Q mm³/s, devir dev/dk. Simülasyon sonuçları (SPEC 05 / 22) yalnız okunur.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from cam.gcode import DrillOp
from cam.model import Toolpath
from cam.sim import SimResult

if TYPE_CHECKING:
    from cam.model import MachineProfile  # A0 arayüz eki (SPEC 30)
    from cam.sim import LatheSimResult  # SPEC 22

ETA = 0.8  # iş mili verimi varsayılanı (kullanıcı kararı, 2026-10-18)


@dataclass(frozen=True)
class KienzleMaterial:
    """Kienzle malzeme verisi: kc11 [N/mm²] (b = h = 1 mm), mc [−] (0 ≤ mc < 1)."""

    name: str
    kc11: float
    mc: float

    def __post_init__(self) -> None:
        raise NotImplementedError("SPEC 32")

    def to_dict(self) -> dict:
        raise NotImplementedError("SPEC 32")

    @classmethod
    def from_dict(cls, d: dict) -> KienzleMaterial:
        raise NotImplementedError("SPEC 32")


def load_materials(path) -> dict[str, KienzleMaterial]:
    """UTF-8 JSON {"malzemeler": [{name, kc11, mc, kaynak}]} → ada göre sözlük."""
    raise NotImplementedError("SPEC 32")


def specific_force(mat: KienzleMaterial, h, K: float = 1.0):
    """kc(h) = K·kc11·h^(−mc) [N/mm²]; h ≤ 0, K ≤ 0 → CamError."""
    raise NotImplementedError("SPEC 32")


def kienzle_force(mat: KienzleMaterial, b: float, h: float, K: float = 1.0) -> float:
    """Fc = K·kc11·b·h^(1−mc) [N]."""
    raise NotImplementedError("SPEC 32")


def turning_force(mat: KienzleMaterial, ap: float, f: float, kappa_r: float = 90.0, K: float = 1.0) -> float:
    """Torna: h = f·sin κr, b = ap/sin κr → Fc [N]; 0 < κr ≤ 90."""
    raise NotImplementedError("SPEC 32")


def engagement_angle(ae: float, D: float) -> float:
    """φe = arccos(1 − 2·ae/D) [rad]; 0 < ae ≤ D."""
    raise NotImplementedError("SPEC 32")


def mean_chip_thickness(fz: float, ae: float, D: float) -> float:
    """hm = fz·(2·ae/D)/φe [mm]."""
    raise NotImplementedError("SPEC 32")


def max_chip_thickness(fz: float, ae: float, D: float) -> float:
    """hex = fz·sin(min(φe, π/2)) [mm]."""
    raise NotImplementedError("SPEC 32")


def cutting_power(Q: float, kc: float) -> float:
    """P = Q·kc/10⁶ [kW]; Q mm³/s, kc N/mm²."""
    raise NotImplementedError("SPEC 32")


def spindle_torque(P: float, n: float) -> float:
    """M = 60000·P/(2π·n) [N·m]; n ≤ 0 → CamError."""
    raise NotImplementedError("SPEC 32")


@dataclass(frozen=True)
class SpindleLimits:
    """İş mili sınırları: P_max [kW], M_max [N·m] (None → denetlenmez), verim eta (0 < eta ≤ 1)."""

    P_max: float | None = None
    M_max: float | None = None
    eta: float = ETA

    def __post_init__(self) -> None:
        raise NotImplementedError("SPEC 32")

    @classmethod
    def from_profile(cls, profile: MachineProfile, eta: float = ETA) -> SpindleLimits:
        """MachineProfile.spindle_power_kw / spindle_torque_nm (A0) alanlarından."""
        raise NotImplementedError("SPEC 32")


@dataclass
class Load:
    """Bir simülasyon adımının yükü. kind ∈ {"kesme", "hava", "atlandi"}."""

    k: int
    op: int
    move: int | None
    kind: str
    ap: float
    ae: float | None
    h: float | None
    kc: float | None
    Q: float
    P: float
    M: float
    F_t: float | None


@dataclass
class Overload:
    """İş mili sınırı aşımı. kind ∈ {"guc", "tork"}; value P/η veya M/η, limit P_max veya M_max."""

    k: int
    op: int
    move: int | None
    kind: str
    value: float
    limit: float


def milling_loads(
    ops: list[Toolpath | DrillOp],
    result: SimResult,
    material: KienzleMaterial,
    K: float = 1.0,
    v_tol: float = 1e-6,
) -> list[Load]:
    """SPEC 05 z-haritası sonucundan adım başına freze yükü (len == len(result.steps))."""
    raise NotImplementedError("SPEC 32")


def lathe_loads(
    ops: list[Toolpath],
    result: LatheSimResult,
    material: KienzleMaterial,
    K: float = 1.0,
    v_tol: float = 1e-6,
) -> list[Load]:
    """SPEC 22 radyal dexel sonucundan adım başına torna yükü."""
    raise NotImplementedError("SPEC 32")


def check_spindle(loads: list[Load], limits: SpindleLimits, tol: float = 1e-9) -> list[Overload]:
    """value > limit·(1 + tol) olan her (k, kind) için bir kayıt, k sırasıyla."""
    raise NotImplementedError("SPEC 32")
