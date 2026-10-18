"""
G-code çapraz kontrolünün karşılaştırma ve güvenlik denetimleri.

- `expected(ops)`: CAM modelinden (Toolpath / DrillOp) tezgâhın yapması gereken hareketler.
  Toolpath hareketleri doğrudan modelden alınır. DrillOp için `cam.gcode.cycles` KULLANILMAZ:
  op alanlarından tam hassasiyetli bir G81/G83 bloğu kurulup `gcode_ref.RefMachine`'de yürütülür
  (LinuxCNC çevrim tanımı). Böylece GRBL çıktısında yazıcının kendi açılımı (`hole_moves`)
  bağımsız bir tanımla karşılaştırılmış olur.
- `compare(beklenen, gerçek)`: kesme hareketleri (G1/G2/G3) birebir ve sırayla eşleşmeli; beklenen
  her hızlı hareketin bitişi gerçek hızlı hareketler içinde aynı sırayla bulunmalı. Gerçekte fazladan
  hızlı hareket olabilir: güvenli Z'ye geri çekme gibi güvenlik eklemeleri karşılaştırmayı bozmasın.
- `safety(trace, ...)`: tezgâh güvenliği (inceleme K2, K3): malzeme içinden XY hızlı hareket,
  kesme derinliğinde veya iş mili dönerken takım değişimi, iş mili duruyorken kesme,
  Fanuc'ta G43 H / G54 eksikliği, program sonunda iş mili açık.
"""

from __future__ import annotations

import math

import numpy as np

from cam.model import Move, MoveType, Toolpath
from tests.reference.gcode_ref import Canon, RefMachine, Trace

TOL_END = 0.5e-3 + 1e-9  # mm: 3 ondalık yuvarlama, koordinat başına
TOL_CENTER = 1.5e-3  # mm: yuvarlanmış merkez + yuvarlanmış I/J
TOL_LEN = 1e-2  # mm: yay boyu
TOL_FEED = 0.05 + 1e-9  # mm/dk: F 1 ondalık


def _canon_from_move(m: Move, p0: np.ndarray, tool: int, rpm: float) -> Canon:
    p1 = np.array(m.end, dtype=float)
    if m.type is MoveType.RAPID:
        return Canon("rapid", p0, p1, 0, tool=tool, rpm=rpm)
    if m.type is MoveType.LINEAR:
        return Canon("feed", p0, p1, 0, feed=m.feed, tool=tool, rpm=rpm)
    return Canon(
        "arc",
        p0,
        p1,
        0,
        feed=m.feed,
        center=tuple(m.center),
        ccw=m.type is MoveType.ARC_CCW,
        tool=tool,
        rpm=rpm,
    )


def _drill_canon(op, p0: np.ndarray, peck_clearance: float) -> list[Canon]:
    """DrillOp -> tam hassasiyetli LinuxCNC G81/G83 bloğu -> RefMachine hareketleri."""

    def n(v) -> str:
        return f"{float(v):.12f}"  # yuvarlamasız denecek kadar hassas, üssüz

    lines = [f"G90 G0 X{n(p0[0])} Y{n(p0[1])} Z{n(p0[2])}"]
    for k, (x, y) in enumerate(op.holes):
        if k == 0:
            q = f" Q{n(op.q)}" if op.kind == "G83" else ""
            lines.append(f"{op.retract} {op.kind} X{n(x)} Y{n(y)} Z{n(op.z)} R{n(op.r)}{q} F{n(op.feed)}")
        else:
            lines.append(f"X{n(x)} Y{n(y)}")
    lines.append("G80")
    m = RefMachine(peck_clearance=peck_clearance)
    moves = m.run("\n".join(lines)).moves
    for c in moves:
        c.tool, c.rpm = op.tool.id, op.rpm
    return moves


def expected(ops, peck_clearance: float) -> list[Canon]:
    """Op listesinin beklenen hareketleri: her op'un başlangıcına hızlı gidiş + op hareketleri."""
    out: list[Canon] = []
    pos: np.ndarray | None = None
    for op in ops:
        start = np.array(op.start, dtype=float)
        if pos is not None and np.linalg.norm(start - pos) > 1e-9:
            out.append(Canon("rapid", pos, start, 0, tool=op.tool.id, rpm=op.rpm))
        if isinstance(op, Toolpath):
            p0 = start
            for m in op.moves:
                c = _canon_from_move(m, p0, op.tool.id, op.rpm)
                if c.kind == "arc" or np.linalg.norm(c.p1 - c.p0) > 1e-9:
                    out.append(c)
                p0 = c.p1
            pos = p0
        else:
            dm = _drill_canon(op, start, peck_clearance)
            out += dm
            pos = dm[-1].p1 if dm else start
    return out


def _close(a: np.ndarray, b: np.ndarray, tol: float = TOL_END) -> bool:
    return bool(np.all(np.abs(np.asarray(a) - np.asarray(b)) <= tol))


def compare(exp: list[Canon], act: list[Canon]) -> list[str]:
    """Farkların listesi (boş liste = eşleşti)."""
    errs: list[str] = []
    ec = [c for c in exp if c.kind != "rapid"]
    ac = [c for c in act if c.kind != "rapid"]
    if len(ec) != len(ac):
        errs.append(f"kesme hareketi sayısı: beklenen {len(ec)}, gerçek {len(ac)}")
    for i, (e, a) in enumerate(zip(ec, ac, strict=False)):
        where = f"kesme {i} (satır {a.line})"
        if e.kind != a.kind:
            errs.append(f"{where}: tip {e.kind} ≠ {a.kind}")
            continue
        if not _close(e.p0, a.p0):
            errs.append(f"{where}: başlangıç {e.p0} ≠ {a.p0}")
        if not _close(e.p1, a.p1):
            errs.append(f"{where}: bitiş {e.p1} ≠ {a.p1}")
        if abs(e.feed - a.feed) > TOL_FEED:
            errs.append(f"{where}: F {e.feed} ≠ {a.feed}")
        if a.tool != e.tool:
            errs.append(f"{where}: takım T{e.tool} beklenirken T{a.tool}")
        if a.rpm is None or abs(a.rpm - round(e.rpm)) > 0.5:
            errs.append(f"{where}: devir {e.rpm} beklenirken {a.rpm}")
        if e.kind == "arc":
            if e.ccw != a.ccw:
                errs.append(f"{where}: yay yönü farklı")
            if not _close(e.center, a.center, TOL_CENTER):
                errs.append(f"{where}: merkez {e.center} ≠ {a.center}")
            if abs(e.length - a.length) > TOL_LEN:
                errs.append(f"{where}: yay boyu {e.length:.4f} ≠ {a.length:.4f} mm")
    # hızlı hareket bitişleri: sıralı alt dizi
    ar = [c for c in act if c.kind == "rapid"]
    j = 0
    for e in (c for c in exp if c.kind == "rapid"):
        while j < len(ar) and not _close(ar[j].p1, e.p1):
            j += 1
        if j == len(ar):
            errs.append(f"hızlı hareket bitişi {e.p1} gerçek programda (sırasıyla) yok")
            break
        j += 1
    return errs


def total_length(moves: list[Canon], kinds=("feed", "arc")) -> float:
    return sum(c.length for c in moves if c.kind in kinds)


def safety(
    trace: Trace, z_safe: float, require_tlo: bool = False, require_wcs: bool = False
) -> list[tuple[str, str]]:
    """Güvenlik ihlalleri, (kod, mesaj) çiftleri; boş liste = güvenli. z_safe: ham malzeme üstü [mm].

    Kodlar: 'rapid' malzeme içinden XY hızlı hareket, 'tc_z' kesme derinliğinde takım değişimi,
    'tc_spindle' iş mili dönerken takım değişimi, 'cut_spindle' iş mili dururken kesme,
    'tlo' etkin boy telafisi takımla uyuşmuyor (G43 H), 'wcs' iş koordinatı seçilmemiş (G54),
    'end' program sonu yok.
    """
    errs: list[tuple[str, str]] = []
    wcs_reported = False
    for c in trace.moves:
        if c.kind == "rapid":
            xy = math.hypot(*(c.p1[:2] - c.p0[:2]))
            zmin = min(c.p0[2], c.p1[2])
            if xy > TOL_END and zmin < z_safe - 1e-9:
                errs.append(("rapid", f"satır {c.line}: Z={zmin:g} < {z_safe:g} iken XY hızlı hareket"))
        else:
            if not c.spindle_on:
                errs.append(("cut_spindle", f"satır {c.line}: iş mili dururken kesme"))
            if require_tlo and c.tlo != c.tool:
                errs.append(("tlo", f"satır {c.line}: T{c.tool} ile kesiyor, etkin boy telafisi H{c.tlo}"))
        if require_wcs and c.wcs is None and not wcs_reported:
            errs.append(("wcs", f"satır {c.line}: iş koordinatı (G54..G59) seçilmeden hareket"))
            wcs_reported = True
    for ev in trace.events:
        if ev.kind != "tool_change":
            continue
        if ev.pos is not None and ev.pos[2] < z_safe - 1e-9:
            errs.append(("tc_z", f"satır {ev.line}: takım değişimi Z={ev.pos[2]:g}'de (< {z_safe:g})"))
        if ev.data["spindle_on"] and not ev.data["implied_stop"]:
            errs.append(("tc_spindle", f"satır {ev.line}: iş mili dönerken takım değişimi (önce M5)"))
    if not any(e.kind == "end" for e in trace.events):
        errs.append(("end", "program sonu (M2/M30) yok"))
    return errs
