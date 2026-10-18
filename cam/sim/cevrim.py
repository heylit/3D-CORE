"""
SPEC 72 — Çevrim süresi: plan / işlem listesi → CycleTime (kesme, hızlı, takım değişimi, iş mili,
bekleme, bağlama, palet, sabit) ve tezgâh ölçümüyle kalibrasyon (k = Σ t_ölç·t_tah / Σ t_tah²).

CycleTime, SPEC 58'in (süre, maliyet, teklif) okuduğu tek sözleşmedir.
"""

from __future__ import annotations

from dataclasses import dataclass

from cam.gcode.cycles import DrillOp
from cam.model import CamError, Toolpath  # noqa: F401  (CamError gövdelerde kullanılacak)
from cam.plan import MillPlan
from cam.plan_turn import TurnPlan
from cam.sim.sure import Dynamics

KINDS = ("kesme", "hizli", "takim_degisimi", "is_mili", "bekleme", "baglama", "palet", "sabit")


@dataclass(frozen=True)
class TimeProfile:
    """Tezgâh zaman profili. machine = MachineProfile.name; verified yalnız kullanıcı tarafından True yapılır.

    tool_change, turret_index, pallet, program_fixed [s]; spindle_accel [dev/dk/s] (None → anlık);
    k kalibrasyon katsayısı; spindle_overlap: "max" (takım değişimi ile iş mili hızlanması örtüşür) veya
    "toplam" (Karar 4).
    """

    machine: str
    dynamics: Dynamics
    tool_change: float
    turret_index: float = 0.0
    spindle_accel: float | None = None
    pallet: float = 0.0
    program_fixed: float = 0.0
    k: float = 1.0
    verified: bool = False
    spindle_overlap: str = "max"

    def __post_init__(self) -> None:
        raise NotImplementedError


@dataclass(frozen=True)
class Dwell:
    """İşlem listesinde bekleme (G4 P) [s]."""

    P: float


@dataclass(frozen=True)
class OpTime:
    """Bir işlemin süre kalemleri [s]."""

    name: str
    setup: int
    tool_id: int
    cut: float
    rapid: float
    tool_change: float
    spindle: float
    dwell: float

    @property
    def total(self) -> float:
        return self.cut + self.rapid + self.tool_change + self.spindle + self.dwell


@dataclass(frozen=True)
class CycleTime:
    """Çevrim süresi; total = k · total_raw."""

    ops: tuple[OpTime, ...]
    setup: float
    pallet: float
    fixed: float
    k: float

    @property
    def total_raw(self) -> float:
        raise NotImplementedError

    @property
    def total(self) -> float:
        raise NotImplementedError

    def by_kind(self) -> dict[str, float]:
        """Kalem kalem toplam: KINDS anahtarları."""
        raise NotImplementedError

    def to_dict(self) -> dict:
        raise NotImplementedError


def cycle_time(
    plan: MillPlan | TurnPlan | list[Toolpath | DrillOp | Dwell],
    prof: TimeProfile,
    setup_time: float = 0.0,
) -> CycleTime:
    """Plan veya işlem listesinin çevrim süresi."""
    raise NotImplementedError


def calibrate(pairs: list[tuple[float, float]]) -> tuple[float, float]:
    """(t_tahmin, t_ölçülen) çiftlerinden (k, göreli RMS hata); boş liste → CamError."""
    raise NotImplementedError
