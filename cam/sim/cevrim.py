"""
SPEC 72 — Çevrim süresi: plan / işlem listesi → CycleTime (kesme, hızlı, takım değişimi, iş mili,
bekleme, bağlama, palet, sabit) ve tezgâh ölçümüyle kalibrasyon (k = Σ t_ölç·t_tah / Σ t_tah²).

CycleTime, SPEC 58'in (süre, maliyet, teklif) okuduğu tek sözleşmedir.
"""

from __future__ import annotations

import math
import warnings
from dataclasses import asdict, dataclass

from cam.gcode.cycles import DrillOp
from cam.model import CamError, LatheTool, Toolpath
from cam.plan import MillPlan
from cam.plan_turn import TurnPlan
from cam.sim.sure import Dynamics, toolpath_time

KINDS = ("kesme", "hizli", "takim_degisimi", "is_mili", "bekleme", "baglama", "palet", "sabit")
OVERLAPS = ("max", "toplam")


def _nonneg(ad: str, x) -> float:
    if isinstance(x, bool) or not isinstance(x, int | float) or not math.isfinite(x) or x < 0:
        raise CamError(f"{ad} ≥ 0 sonlu olmalı ({x})")
    return float(x)


def _pos(ad: str, x) -> float:
    if isinstance(x, bool) or not isinstance(x, int | float) or not math.isfinite(x) or x <= 0:
        raise CamError(f"{ad} pozitif sonlu olmalı ({x})")
    return float(x)


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
        if not isinstance(self.machine, str) or not self.machine.strip():
            raise CamError(f"TimeProfile.machine boş olmayan ad olmalı ({self.machine!r})")
        if not isinstance(self.dynamics, Dynamics):
            raise CamError(f"TimeProfile.dynamics Dynamics olmalı ({type(self.dynamics).__name__})")
        for ad in ("tool_change", "turret_index", "pallet", "program_fixed"):
            object.__setattr__(self, ad, _nonneg(f"TimeProfile.{ad}", getattr(self, ad)))
        if self.spindle_accel is not None:
            object.__setattr__(self, "spindle_accel", _pos("TimeProfile.spindle_accel", self.spindle_accel))
        object.__setattr__(self, "k", _pos("TimeProfile.k", self.k))
        if not isinstance(self.verified, bool):
            raise CamError(f"TimeProfile.verified bool olmalı ({self.verified!r})")
        if self.spindle_overlap not in OVERLAPS:
            raise CamError(f"TimeProfile.spindle_overlap {OVERLAPS} olmalı ({self.spindle_overlap!r})")


@dataclass(frozen=True)
class Dwell:
    """İşlem listesinde bekleme (G4 P) [s]."""

    P: float

    def __post_init__(self) -> None:
        object.__setattr__(self, "P", _nonneg("Dwell.P", self.P))


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
        return sum(o.total for o in self.ops) + self.setup + self.pallet + self.fixed

    @property
    def total(self) -> float:
        return self.k * self.total_raw

    def by_kind(self) -> dict[str, float]:
        """Kalem kalem toplam: KINDS anahtarları."""
        return {
            "kesme": sum(o.cut for o in self.ops),
            "hizli": sum(o.rapid for o in self.ops),
            "takim_degisimi": sum(o.tool_change for o in self.ops),
            "is_mili": sum(o.spindle for o in self.ops),
            "bekleme": sum(o.dwell for o in self.ops),
            "baglama": self.setup,
            "palet": self.pallet,
            "sabit": self.fixed,
        }

    def to_dict(self) -> dict:
        return {
            "ops": [asdict(o) | {"total": o.total} for o in self.ops],
            "setup": self.setup,
            "pallet": self.pallet,
            "fixed": self.fixed,
            "k": self.k,
            "total_raw": self.total_raw,
            "total": self.total,
            "by_kind": self.by_kind(),
        }


@dataclass
class _Item:
    """Normalleştirilmiş işlem: bağlama, ad, takım, hareket (Toolpath) ya da bekleme."""

    setup: int
    name: str
    tool_id: int
    path: Toolpath | None
    dwell: float = 0.0


def _items(plan, prof: TimeProfile) -> tuple[list[_Item], int]:
    """Plan / liste → (işlemler, bağlama sayısı). Liste girdisi tek bağlamadır."""
    if isinstance(plan, MillPlan):
        return [_op_item(o.op, o.setup, o.name, o.tool_id) for o in plan.ops], len(plan.setups)
    if isinstance(plan, TurnPlan):
        return [_op_item(o.op, 0, o.name, o.tool_id) for o in plan.ops], 1
    if not isinstance(plan, list | tuple):
        raise CamError(
            f"cycle_time: MillPlan, TurnPlan veya işlem listesi bekleniyor ({type(plan).__name__})"
        )
    items = []
    for x in plan:
        if isinstance(x, Dwell):
            items.append(_Item(0, "bekleme", -1, None, x.P))
        elif isinstance(x, Toolpath | DrillOp):
            items.append(_op_item(x, 0, x.name, x.tool.id))
        else:
            raise CamError(f"cycle_time: bilinmeyen işlem tipi ({type(x).__name__})")
    return items, 1


def _op_item(op, setup: int, name: str, tool_id: int) -> _Item:
    if isinstance(op, DrillOp):
        op = op.to_toolpath()  # SPEC 04 hole_moves açılımı; gagalama geri çekilmeleri G0
    if not isinstance(op, Toolpath):
        raise CamError(f"cycle_time: işlem '{name}' Toolpath veya DrillOp olmalı ({type(op).__name__})")
    return _Item(setup, name, tool_id, op)


def cycle_time(
    plan: MillPlan | TurnPlan | list[Toolpath | DrillOp | Dwell],
    prof: TimeProfile,
    setup_time: float = 0.0,
) -> CycleTime:
    """Plan veya işlem listesinin çevrim süresi.

    Takım değişimi: bağlama içinde ardışık farklı takım + her bağlamanın ilk takımı (SPEC 29 tool_changes());
    torna takımında t_taret, frezede t_tc. İş mili: devir geçişi |Δn|/ṅ; bağlama değişiminde ve program
    sonunda duruş (M5). Takım değişimiyle örtüşen geçiş "max" kipinde max(t_tc, t_iş_mili) olarak sayılır.
    Bekleme önceki işleme (yoksa sonrakine) yazılır.
    """
    if not isinstance(prof, TimeProfile):
        raise CamError(f"cycle_time: TimeProfile bekleniyor ({type(prof).__name__})")
    setup_time = _nonneg("cycle_time: setup_time", setup_time)
    items, n_setups = _items(plan, prof)
    rows: list[dict] = []
    pending_dwell = 0.0
    tool: int | None = None
    setup: int | None = None
    n_cur = 0.0
    for it in items:
        if it.path is None:
            if rows:
                rows[-1]["dwell"] += it.dwell
            else:
                pending_dwell += it.dwell
            continue
        if it.setup != setup and rows:
            rows[-1]["spindle"] += _spindle(n_cur, 0.0, prof)  # bağlama değişimi: iş mili durur
            n_cur = 0.0
        t_tc = 0.0
        if it.setup != setup or it.tool_id != tool:
            t_tc = prof.turret_index if isinstance(it.path.tool, LatheTool) else prof.tool_change
        setup, tool = it.setup, it.tool_id
        t_sp = _spindle(n_cur, it.path.rpm, prof)
        n_cur = it.path.rpm
        if t_tc > 0 and prof.spindle_overlap == "max":
            t_sp = max(0.0, t_sp - t_tc)
        pt = toolpath_time(it.path, prof.dynamics)
        rows.append(
            dict(
                name=it.name,
                setup=it.setup,
                tool_id=it.tool_id,
                cut=pt.cut,
                rapid=pt.rapid,
                tool_change=t_tc,
                spindle=t_sp,
                dwell=pending_dwell,
            )
        )
        pending_dwell = 0.0
    if rows:
        rows[-1]["spindle"] += _spindle(n_cur, 0.0, prof)  # program sonu M5
    elif pending_dwell > 0:
        rows.append(
            dict(
                name="bekleme",
                setup=0,
                tool_id=-1,
                cut=0.0,
                rapid=0.0,
                tool_change=0.0,
                spindle=0.0,
                dwell=pending_dwell,
            )
        )
    return CycleTime(
        ops=tuple(OpTime(**r) for r in rows),
        setup=n_setups * setup_time,
        pallet=prof.pallet,
        fixed=prof.program_fixed,
        k=prof.k,
    )


def _spindle(n0: float, n1: float, prof: TimeProfile) -> float:
    """İş mili hız değişimi süresi |n₁ − n₀| / ṅ [s]; ṅ = None → anlık."""
    if prof.spindle_accel is None:
        return 0.0
    return abs(n1 - n0) / prof.spindle_accel


def calibrate(pairs: list[tuple[float, float]]) -> tuple[float, float]:
    """(t_tahmin, t_ölçülen) çiftlerinden (k, göreli RMS hata); boş liste → CamError.

    k = Σ t_ölç·t_tah / Σ t_tah² (orijinden geçen doğru); hata = √(ortalama ((k·t_tah − t_ölç) / t_ölç)²).
    Ölçüm < 3 ise uyarı (UserWarning).
    """
    pairs = list(pairs)
    if not pairs:
        raise CamError("calibrate: ölçüm listesi boş")
    for i, (t, m) in enumerate(pairs):
        _pos(f"calibrate: çift {i} t_tahmin", t)
        _pos(f"calibrate: çift {i} t_ölçülen", m)
    k = sum(t * m for t, m in pairs) / sum(t * t for t, _ in pairs)
    err = math.sqrt(sum(((k * t - m) / m) ** 2 for t, m in pairs) / len(pairs))
    if len(pairs) < 3:
        warnings.warn(
            f"calibrate: yalnız {len(pairs)} ölçüm; k güvenilir değil (en az 3 önerilir)", stacklevel=2
        )
    return k, err
