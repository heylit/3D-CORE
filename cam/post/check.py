"""
Tezgâh sınır denetimi (SPEC 30): program tezgâha gitmeden kurs, devir, ilerleme, takım ve program
numarası. Hiçbir değer kırpılmaz; ilk ihlalde CamError (op adı, hareket sırası, değer, sınır).

Kurs: uç makinede p + origin; ölçü hattı Z'si z + origin_z + L (L = Tool.gauge_length).
Yaylarda süpürülen eksen yönü noktaları (0, π/2, π, 3π/2) da denetlenir. DrillOp kanonik açılımıyla.
"""

from __future__ import annotations

import numpy as np

from cam.gcode.cycles import DrillOp
from cam.gcode.writer import _yazilabilir, cevrim_op
from cam.model import CamError, MachineProfile, MoveType, Setup, Toolpath

EKSEN = ("X", "Y", "Z")


def _yol(op: Toolpath | DrillOp) -> Toolpath:
    """Op doğrulaması; DrillOp kanonik açılımına (G0/G1) çevrilir."""
    if isinstance(op, Toolpath):
        op.validate()
        _yazilabilir(op)  # torna (G18 / G95 / G96), frame, eğik eksen → CamError
        return op
    if isinstance(op, DrillOp) or cevrim_op(op):  # SPEC 04b G82 / G84 da açılımıyla (kılavuz F dahil)
        op.validate()
        return op.to_toolpath()
    raise CamError(f"Denetlenemeyen op tipi: {type(op).__name__}")


def _parcalar(tp: Toolpath):
    """(hareket sırası k ≥ 1, hareket, parçanın noktaları iş koordinatında); k = 0 başlangıç noktası."""
    yield 0, None, np.array([tp.start], dtype=float)
    p0 = tp.start
    for k, m in enumerate(tp.moves, start=1):
        if m.type in (MoveType.ARC_CW, MoveType.ARC_CCW):
            lo, hi = Toolpath(tp.name, tp.tool, p0, [m], rpm=tp.rpm).bbox()  # çeyrek noktaları dahil
            pts = np.array([lo, hi])
        else:
            pts = np.array([m.end], dtype=float)
        yield k, m, pts
        p0 = m.end


def _olcu_boyu(machine: MachineProfile, tp: Toolpath) -> float:
    L = tp.tool.gauge_length
    if L is None:
        if machine.z is not None:
            raise CamError(
                f"'{tp.name}': takım '{tp.tool.name}' ölçü boyu bilinmiyor (tutucu yok); "
                "Z kursu varken varsayılan boy kabul edilmez"
            )
        return 0.0
    return float(L)


def _makine(pts: np.ndarray, setup: Setup | None, L: float) -> np.ndarray:
    """İş koordinatı → makine: x + ox, y + oy, z + oz + L (ölçü hattı)."""
    o = np.zeros(3) if setup is None else np.array(setup.wcs.origin, dtype=float)
    return pts + o + np.array([0.0, 0.0, L])


def _kurs(machine: MachineProfile, tp: Toolpath, k: int, pts: np.ndarray) -> None:
    yer = "başlangıç" if k == 0 else f"hareket {k}"
    for i, lim in enumerate((machine.x, machine.y, machine.z)):
        if lim is None:
            continue
        for v in pts[:, i]:
            if not lim.min <= v <= lim.max:
                ad = "Z (ölçü hattı)" if i == 2 else EKSEN[i]
                raise CamError(
                    f"'{tp.name}' {yer}: {ad} makinede {v:.4f} kurs [{lim.min:g}, {lim.max:g}] dışında"
                )


def _devir(machine: MachineProfile, name: str, rpm: float) -> None:
    S = round(rpm)
    if not machine.rpm_min <= S <= machine.rpm_max:
        raise CamError(
            f"'{name}': devir S{S} tezgâh aralığı [{machine.rpm_min:g}, {machine.rpm_max:g}] dışında; "
            "kesme verisinde n_max ile sınırlayın (SPEC 14)"
        )


def _takim(machine: MachineProfile, name: str, T: int) -> None:
    if T < 1:
        raise CamError(f"'{name}': takım numarası T{T} ≥ 1 olmalı")
    if machine.tool_slots is not None and T > machine.tool_slots:
        raise CamError(f"'{name}': takım T{T} magazinde yok (tool_slots = {machine.tool_slots})")


def _ilerleme(machine: MachineProfile, tp: Toolpath, k: int, F: float) -> None:
    if F > machine.feed_max:
        raise CamError(f"'{tp.name}' hareket {k}: ilerleme F{F:g} > feed_max {machine.feed_max:g} mm/dk")


def _kurulum(machine: MachineProfile, setup: Setup | None) -> None:
    if setup is None and any(lim is not None for lim in (machine.x, machine.y, machine.z)):
        raise CamError(
            f"Tezgâh profili '{machine.name}': eksen kursu var, kurulum (setup) verilmeli "
            "(iş sıfırı makine sıfırında varsayılmaz)"
        )


def check_machine(
    machine: MachineProfile,
    ops: list[Toolpath | DrillOp],
    setup: Setup | None = None,
    program_no: int = 1,
) -> None:
    """Profil, program numarası, op'lar ve her op için takım, devir, ilerleme ve kurs denetimi."""
    machine.validate()
    lo, hi = machine.program_no_range
    if not lo <= program_no <= hi:
        raise CamError(f"Program numarası {program_no} tezgâh aralığı [{lo}, {hi}] dışında")
    _kurulum(machine, setup)
    for op in ops:
        tp = _yol(op)
        _takim(machine, tp.name, tp.tool.id)
        _devir(machine, tp.name, tp.rpm)
        if not isinstance(op, Toolpath):
            _ilerleme(machine, tp, 1, op.feed)
        L = _olcu_boyu(machine, tp)
        for k, m, pts in _parcalar(tp):
            if m is not None and m.type is not MoveType.RAPID:
                _ilerleme(machine, tp, k, m.feed)
            _kurs(machine, tp, k, _makine(pts, setup, L))


def check_safe_z(
    machine: MachineProfile, ops: list[Toolpath | DrillOp], setup: Setup | None, z: float
) -> None:
    """Yazıcının op başlarında ve geri çekmede gittiği güvenli Z (her op'un takım boyuyla) Z kursunda mı."""
    if machine.z is None:
        return
    for op in ops:
        tp = _yol(op)
        z_m = _makine(np.array([[0.0, 0.0, z]]), setup, _olcu_boyu(machine, tp))[0, 2]
        if not machine.z.min <= z_m <= machine.z.max:
            raise CamError(
                f"'{tp.name}': güvenli Z {z:g} makinede {z_m:.4f} (ölçü hattı), "
                f"Z kursu [{machine.z.min:g}, {machine.z.max:g}] dışında"
            )


def machine_extents(
    machine: MachineProfile, ops: list[Toolpath | DrillOp], setup: Setup
) -> dict[str, tuple[float, float]]:
    """Op'ların makine koordinatında kapladığı aralık: anahtarlar 'x', 'y', 'z_ölçü'."""
    lo = np.full(3, np.inf)
    hi = np.full(3, -np.inf)
    for op in ops:
        tp = _yol(op)
        L = tp.tool.gauge_length
        if L is None:
            raise CamError(f"'{tp.name}': takım '{tp.tool.name}' ölçü boyu bilinmiyor; z_ölçü hesaplanamaz")
        a, b = tp.bbox()
        pts = _makine(np.array([a, b]), setup, float(L))
        lo = np.minimum(lo, pts.min(axis=0))
        hi = np.maximum(hi, pts.max(axis=0))
    if not ops:
        raise CamError("machine_extents: op yok")
    return {
        "x": (float(lo[0]), float(hi[0])),
        "y": (float(lo[1]), float(hi[1])),
        "z_ölçü": (float(lo[2]), float(hi[2])),
    }
