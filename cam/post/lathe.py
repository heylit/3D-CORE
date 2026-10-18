"""
Torna tezgâh profili denetimi ve postprosesörü (SPEC 40 Ek E2, SPEC 30 Ek A).

- Kurs: makine koordinatı `X_m = 2·(x + o_x)` (profilde X **çap**, yolda `x` **yarıçap**), `Z_m = z + o_z`;
  her uç (`G0` dahil) ve yayların `(x, z)` düzleminde süpürdüğü eksen yönü noktaları; takım değiştirme
  noktası `tool_change = (x_tc, z_tc)` aynı dönüşümle. Kurs varken `setup` zorunlu.
- Devir: sabit devirde ve `G96`'nın `G50` sınırında `S = round(rpm)`, `rpm_min ≤ S ≤ rpm_max`.
- İlerleme (mm/dev): her kesme hareketinde `feed · S ≤ feed_max` (mm/dk; `G96`'da güvenli taraf).
- Taret: `tool_slots` varsa `1 ≤ T ≤ tool_slots`.
- Yol türü: `kind = "lathe"` profile freze yolu (`plane = XY` veya `feed_mode = PER_MIN`) → CamError.
- `post_lathe` = `check_lathe` + `write_lathe` + iki yorum satırı (`FANUC_TORNA` başlığından sonra).
"""

from __future__ import annotations

from dataclasses import replace

import numpy as np

from cam.gcode.lathe import FANUC_TORNA, write_lathe
from cam.model import ARCS, CamError, FeedMode, MachineProfile, MoveType, Plane, Setup, Toolpath

__all__ = ["check_lathe", "post_lathe"]

UYARI = "DOGRULANMAMIS PROFIL - ILK PARCADA KURU CALISTIRIN"


def _makine(setup: Setup | None, x: float, z: float) -> tuple[float, float]:
    """İş koordinatı (x yarıçap) → makine: X_m = 2·(x + o_x) (çap), Z_m = z + o_z."""
    ox, _, oz = (0.0, 0.0, 0.0) if setup is None else setup.wcs.origin
    return 2.0 * (x + ox), z + oz


def _kurs(machine: MachineProfile, yer: str, X: float, Z: float) -> None:
    for ad, v, lim in (("X (çap)", X, machine.x), ("Z", Z, machine.z)):
        if lim is not None and not lim.min <= v <= lim.max:
            raise CamError(f"{yer}: {ad} makinede {v:.4f} kurs [{lim.min:g}, {lim.max:g}] dışında")


def _torna_yolu(tp) -> Toolpath:
    if not isinstance(tp, Toolpath):
        raise CamError(f"Denetlenemeyen op tipi: {type(tp).__name__}")
    tp.validate()
    if tp.plane is not Plane.ZX or tp.feed_mode is not FeedMode.PER_REV:
        raise CamError(
            f"'{tp.name}': freze yolu (düzlem {tp.plane.value}, ilerleme {tp.feed_mode.value}) "
            "torna profiline yazılmaz"
        )
    return tp


def _parcalar(tp: Toolpath):
    """(hareket sırası k ≥ 1, hareket, noktalar); yaylarda (x, z) düzleminde çeyrek noktaları da."""
    p0 = tp.start
    for k, m in enumerate(tp.moves, start=1):
        if m.type in ARCS:
            lo, hi = replace(tp, start=p0, moves=[m]).bbox()
            pts = np.array([lo, hi])
        else:
            pts = np.array([m.end], dtype=float)
        yield k, m, pts
        p0 = m.end


def check_lathe(
    machine: MachineProfile,
    ops: list[Toolpath],
    setup: Setup | None,
    tool_change: tuple[float, float],
    program_no: int = 1,
) -> None:
    """Torna profili, program numarası ve her op için taret, devir, `feed·S` ve çap kursu denetimi."""
    machine.validate()
    if machine.kind != "lathe":
        raise CamError(f"Tezgâh profili '{machine.name}': torna profili değil (kind = {machine.kind!r})")
    lo, hi = machine.program_no_range
    if not lo <= program_no <= hi:
        raise CamError(f"Program numarası {program_no} tezgâh aralığı [{lo}, {hi}] dışında")
    if setup is None and (machine.x is not None or machine.z is not None):
        raise CamError(
            f"Tezgâh profili '{machine.name}': eksen kursu var, kurulum (setup) verilmeli "
            "(iş sıfırı makine sıfırında varsayılmaz)"
        )
    if setup is not None and setup.wcs.code != "G54":
        raise CamError(f"Torna yazıcısı yalnız G54 yazar; kurulum iş sıfırı {setup.wcs.code}")
    x_tc, z_tc = (float(v) for v in tool_change)
    _kurs(machine, f"Takım değiştirme noktası ({x_tc:g}, {z_tc:g})", *_makine(setup, x_tc, z_tc))
    for op in ops:
        tp = _torna_yolu(op)
        T = tp.tool.id
        if T < 1 or (machine.tool_slots is not None and T > machine.tool_slots):
            raise CamError(f"'{tp.name}': takım T{T} tarette yok (tool_slots = {machine.tool_slots})")
        S = round(tp.rpm)
        if not machine.rpm_min <= S <= machine.rpm_max:
            ne = "G50 devir sınırı" if tp.css is not None else "devir"
            raise CamError(
                f"'{tp.name}': {ne} S{S} tezgâh aralığı [{machine.rpm_min:g}, {machine.rpm_max:g}] dışında"
            )
        X, Z = _makine(setup, tp.start[0], tp.start[2])
        _kurs(machine, f"'{tp.name}' başlangıç", X, Z)
        for k, m, pts in _parcalar(tp):
            if m.type is not MoveType.RAPID and m.feed * S > machine.feed_max:
                raise CamError(
                    f"'{tp.name}' hareket {k}: ilerleme F{m.feed:g} mm/dev · S{S} = {m.feed * S:g} mm/dk "
                    f"> feed_max {machine.feed_max:g}"
                )
            for p in pts:
                _kurs(machine, f"'{tp.name}' hareket {k}", *_makine(setup, p[0], p[2]))


def post_lathe(
    ops: list[Toolpath],
    machine: MachineProfile,
    setup: Setup | None,
    spindle: str,
    tool_change: tuple[float, float],
    program_no: int = 1,
) -> str:
    """Denetim + `write_lathe(…, dialect_for(machine))` + `(POST <AD> <DIL>)` ve doğrulanmamış uyarı."""
    check_lathe(machine, ops, setup, tool_change, program_no)
    text = write_lathe(ops, spindle, tool_change, FANUC_TORNA, program_no)
    lines = text[:-1].split("\n")
    n = len(FANUC_TORNA.header)
    yorum = [f"(POST {machine.name} {machine.controller.upper()})"]
    if not machine.verified:
        yorum.append(f"({UYARI})")
    return "\n".join(lines[:n] + yorum + lines[n:]) + "\n"
