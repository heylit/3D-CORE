"""
Yazıcının iki aşaması (SPEC 30) ve ISO ailesi (GRBL, Fanuc, Haas) biçimleyicisi.

- `plan(...)`: modal durum makinesi ve bütün güvenlik mantığı (SPEC 04 Ek B/C) → blok listesi.
  Bloklar yuvarlanmış değerleri taşır; modal bastırma burada yapılır (değişmeyen eksen / F `None`).
- `format(blocks, dialect)`: blokları satırlara çevirir; karar vermez. Yalnız yazım kurallarını
  (satır numarası, baş / son satırlar, G kelimesinin modal yazımı) uygular.

Biçimleyicinin G kelimesi kuralı: hareket tipi bir önceki hareket bloğundakinden farklıysa yazılır.
Op başındaki üç eksenli `Rapid` (planın op başı, SPEC 04 Ek A) her zaman `G0` ile yazılır.
Takım değişimi, iş mili ve `G80` blokları hareket tipini değiştirmez, `G80` onu bilinmez yapar.

`HAAS`: Fanuc ailesi; `O00001` (5 hane), satır numarası yok, `T1 M06`, `H01` (iki hane).
"""

from __future__ import annotations

from cam.gcode.cycles import DrillOp
from cam.gcode.dialect import GRBL, HAAS, Dialect
from cam.gcode.modal import ModalState, fmt, snap
from cam.gcode.writer import _ofsetler, _stok_ustu, _yazilabilir, _z_kesme, cevrim_op
from cam.model import ARCS, CamError, Move, MoveType, Toolpath
from cam.post.blocks import (
    Arc,
    Block,
    Comment,
    Cycle,
    CycleEnd,
    Dwell,
    End,
    Linear,
    MachineZ,
    Rapid,
    RigidTap,
    Spindle,
    Start,
    ToolChange,
    ToolLength,
)

__all__ = ["HAAS", "format", "plan"]

XYZ = ("x", "y", "z")


class _Planner:
    """Tek bir programın plan durumu: modal durum (yuvarlanmış değerler) + bloklar."""

    def __init__(
        self,
        dialect: Dialect,
        safe_z: float,
        tool_change_z: float | None,
        length_offsets: dict[int, float] | None = None,
    ) -> None:
        self.length_offsets = length_offsets
        self.d = dialect
        self.state = ModalState()
        self.blocks: list[Block] = []
        self.tools_used = 0
        self.safe_z = safe_z
        self.tool_change_z = tool_change_z
        self.p_true: tuple[float, float, float] | None = None  # yuvarlanmamış son nokta

    def s(self, v: float) -> float:
        """Yazılacak koordinat değeri (yuvarlanmış)."""
        return snap(v, self.d.decimals)

    def changed_axes(self, end) -> list[float | None]:
        """Durumdakinden farklı eksenlerin yuvarlanmış değeri, aynıysa None."""
        pos = self.state.pos
        return [
            self.s(v) if pos is None or fmt(v, self.d.decimals) != fmt(pos[i], self.d.decimals) else None
            for i, v in enumerate(end)
        ]

    def feed_value(self, feed: float) -> float | None:
        """Yuvarlanmış F, sadece durumdakinden farklıysa."""
        F = fmt(feed, self.d.feed_decimals)
        if self.state.feed is not None and F == fmt(self.state.feed, self.d.feed_decimals):
            return None
        self.state.feed = float(F)
        return float(F)

    def set_pos(self, end) -> None:
        self.state.pos = tuple(self.s(v) for v in end)

    # --- program parçaları ------------------------------------------------------------
    def retract(self) -> None:
        """Takım güvenli Z'nin altındaysa (yuvarlanmış değere göre) güvenli Z'ye G0."""
        pos = self.state.pos
        if pos is not None and pos[2] < self.s(self.safe_z):
            self.move(Move(MoveType.RAPID, (pos[0], pos[1], self.safe_z)))

    def tool_and_spindle(self, tool_id: int, rpm: float) -> bool:
        """Takım farklıysa M5 (iş mili dönüyorsa), G53 Z (profilde varsa) ve takım değişimi;
        takım veya devir farklıysa iş mili. Takım değiştiyse True."""
        S = round(rpm)
        changed = tool_id != self.state.tool
        if changed:
            if self.state.rpm is not None:
                self.blocks.append(Spindle(None))
                self.state.rpm = None
            if self.tool_change_z is not None:
                self.blocks.append(MachineZ(self.s(self.tool_change_z)))
                self.state.pos = None  # iş koordinatında Z artık bilinmiyor
                self.state.motion = "G0"
            self.blocks.append(ToolChange(tool_id, self.tools_used == 0))
            self.state.tool = tool_id
            self.tools_used += 1
            if self.length_offsets is not None:  # SPEC 14: GRBL G43.1
                self.blocks.append(ToolLength(tool_id, self.s(self.length_offsets[tool_id])))
        if changed or S != self.state.rpm:
            self.blocks.append(Spindle(S))
            self.state.rpm = S
        return changed

    def op_begin(self, tool_id: int, rpm: float, start) -> None:
        """Op başı: geri çekme, takım / devir, güvenli Z'de üç eksenli G0 (G43 H), gerekirse iniş."""
        self.retract()
        changed = self.tool_and_spindle(tool_id, rpm)
        g43 = tool_id if changed and self.d.tool_length_comp else None
        at_safe = (start[0], start[1], self.safe_z)
        self.blocks.append(Rapid(*(self.s(v) for v in at_safe), g43))
        self.state.motion = "G0"
        self.set_pos(at_safe)
        self.p_true = at_safe
        if fmt(start[2], self.d.decimals) != fmt(self.safe_z, self.d.decimals):
            self.move(Move(MoveType.RAPID, start))
        self.p_true = start

    def tiny_arc(self, m: Move) -> bool:
        """Yuvarlanmış uçları XY'de aynı ama modelde tam daire olmayan, süpürmesi < π yay (SPEC 04 B1)."""
        p0, p1, c = self.p_true, m.end, m.center
        d = self.d.decimals
        if p0[:2] == p1[:2] or any(fmt(p1[i], d) != fmt(self.state.pos[i], d) for i in (0, 1)):
            return False
        cross = (p0[0] - c[0]) * (p1[1] - c[1]) - (p0[1] - c[1]) * (p1[0] - c[0])
        return cross > 0 if m.type is MoveType.ARC_CCW else cross < 0

    def move(self, m: Move) -> None:
        """Tek hareket bloğu: değişen eksenler, yayda I J, değişen F."""
        if m.type in ARCS and self.tiny_arc(m):
            m = Move(MoveType.LINEAR, m.end, m.feed)  # kiriş ≤ 2ε: G1 yeterli
        x, y, z = self.changed_axes(m.end)
        if m.type in ARCS:
            x0, y0, _ = self.state.pos
            i = self.s(self.s(m.center[0]) - x0)  # I = round(cx) − round(x0)
            j = self.s(self.s(m.center[1]) - y0)
            F = self.feed_value(m.feed)
            self.blocks.append(Arc(x, y, z, i, j, m.type is MoveType.ARC_CCW, F))
        else:
            if x is None and y is None and z is None:
                x = self.s(m.end[0])  # eksensiz G0/G1 satırı hareket sayılmaz
            if m.type is MoveType.RAPID:
                self.blocks.append(Rapid(x, y, z))
            else:
                self.blocks.append(Linear(x, y, z, self.feed_value(m.feed)))
        self.state.motion = m.type.value
        self.set_pos(m.end)
        self.p_true = m.end

    def toolpath(self, tp: Toolpath, dwell: float | None = None) -> None:
        """Yol hareketleri; `dwell` verilirse (açılmış G82) her G1'den sonra `Dwell`."""
        self.op_begin(tp.tool.id, tp.rpm, tp.start)
        for m in tp.moves:
            self.move(m)
            if dwell is not None and m.type is MoveType.LINEAR:
                self.blocks.append(Dwell(dwell))

    def drill(self, op) -> None:
        """Delik op (DrillOp, SPEC 04b G82 / G84): çevrimli dilde Cycle ... CycleEnd; çevrimsiz dilde
        kanonik açılım (G82: dipte `Dwell`). Kılavuz çevrimsiz dilde `_guvenli_z`'de reddedilir."""
        tp = op.to_toolpath(self.d)  # c < q denetimi her iki dilde de
        dwell = op.dwell if op.kind == "G82" else None
        if not self.d.canned_cycles:
            self.toolpath(tp, dwell)
            return
        self.op_begin(op.tool.id, op.rpm, op.start)
        if op.kind == "G84" and self.d.rigid_tap == "m29":
            self.blocks.append(RigidTap(self.state.rpm))  # Fanuc: her G84'ten önce M29 S (SPEC 04b Karar 2)
        self.state.motion, self.state.retract = op.kind, op.retract
        z_ret = op.start[2] if op.retract == "G98" else op.r
        for k, (x, y) in enumerate(op.holes):
            if k == 0:
                F = float(fmt(op.feed, self.d.feed_decimals))
                q = self.s(op.q) if op.kind == "G83" else None
                blk = Cycle(
                    op.kind, op.retract, self.s(x), self.s(y), self.s(op.z), self.s(op.r), q, F, True, dwell
                )
                self.state.feed = F
            else:
                cx, cy, _ = self.changed_axes((x, y, self.state.pos[2]))
                if cx is None and cy is None:
                    cx = self.s(x)  # aynı noktada ikinci delik
                blk = Cycle(op.kind, op.retract, cx, cy, None, None, None, None, False)
            self.blocks.append(blk)
            self.set_pos((x, y, z_ret))
            self.p_true = (x, y, z_ret)
        self.blocks.append(CycleEnd())
        self.state.end_cycle()


def _guvenli_z(ops, dialect: Dialect, safe_z: float | None, stock_top: float | None) -> float:
    """Op doğrulaması ve güvenli Z kuralları (SPEC 04 Ek B2, Ek C1, C2); güvenli Z'yi döndürür."""
    import math

    for op in ops:
        if isinstance(op, Toolpath):
            op.validate()
            _yazilabilir(op)
        elif isinstance(op, DrillOp):
            op.validate()
        elif cevrim_op(op):
            op.validate()
            if op.kind == "G84" and not (dialect.canned_cycles and dialect.rigid_tap):
                raise CamError(f"'{op.name}': {dialect.name} kılavuz çekemez (eşzamanlı iş mili / G84 yok)")
        else:
            raise CamError(f"Yazılamayan op tipi: {type(op).__name__}")
    z_top = max((op.start[2] for op in ops), default=0.0)
    if safe_z is None:
        safe_z = z_top
    elif not math.isfinite(safe_z) or safe_z < z_top:
        raise CamError(f"Güvenli Z ({safe_z}) en yüksek op başından ({z_top}) alçak olamaz")
    z_kesme = _z_kesme(ops)
    if not safe_z > z_kesme:
        raise CamError(
            f"safe_z ({safe_z}) kesme seviyesinin ({z_kesme}) üstünde olmalı; yüksek safe_z verin (Ek C1)"
        )
    if stock_top is not None:
        _stok_ustu(ops, dialect, float(safe_z), stock_top)
    return float(safe_z)


def plan(
    ops: list[Toolpath | DrillOp],
    dialect: Dialect = GRBL,
    program_no: int = 1,
    safe_z: float | None = None,
    stock_top: float | None = None,
    tool_change_z: float | None = None,
    wcs: str | None = None,
    length_offsets: dict[int, float] | None = None,
) -> list[Block]:
    """Dilden bağımsız blok planı; koordinat basamağı `dialect.decimals`.

    Parametreler `cam.gcode.write` ile aynı anlamdadır. `tool_change_z` (makine koordinatı) verilirse
    her takım değişiminden önce (ilki dahil) `MachineZ`. `wcs` (SPEC 14) baş satırdaki G54'ün yerine;
    `length_offsets` (SPEC 14, GRBL) her takım değişiminden sonra `ToolLength`."""
    if tool_change_z is not None:
        import math

        if not math.isfinite(tool_change_z):
            raise CamError(f"tool_change_z sonlu olmalı ({tool_change_z})")
    z_s = _guvenli_z(ops, dialect, safe_z, stock_top)
    if length_offsets is not None:
        _ofsetler(length_offsets, ops, dialect)
    p = _Planner(dialect, z_s, tool_change_z, length_offsets)
    p.blocks.append(Start(program_no) if wcs is None else Start(program_no, wcs))
    for op in ops:
        if isinstance(op, Toolpath):
            p.toolpath(op)
        else:
            p.drill(op)
    p.retract()
    p.blocks.append(End())
    return p.blocks


# ---------------------------------------------------------------- biçimleyici


class _Formatter:
    def __init__(self, d: Dialect) -> None:
        self.d = d
        self.lines: list[str] = []
        self.n = 0
        self.motion: str | None = None

    def emit(self, words: list[str]) -> None:
        """Bir satır ekler; satır numaralı dilde '%' ve 'O...' dışındaki her satıra N verir."""
        line = " ".join(words)
        if self.d.line_numbers and line != "%" and not line.startswith("O"):
            self.n += self.d.line_step
            line = f"N{self.n} {line}"
        self.lines.append(line)

    def c(self, v: float) -> str:
        return fmt(v, self.d.decimals)

    def axes(self, b, names=XYZ) -> list[str]:
        return [f"{a.upper()}{self.c(getattr(b, a))}" for a in names if getattr(b, a) is not None]

    def g(self, code: str, force: bool = False) -> list[str]:
        out = [code] if force or self.motion != code else []
        self.motion = code
        return out

    def feed(self, F: float | None) -> list[str]:
        return [] if F is None else [f"F{fmt(F, self.d.feed_decimals)}"]

    def start(self, b: Start) -> None:
        lines = [h.format(program_no=b.program_no) for h in self.d.header]
        if b.wcs != "G54":
            i = next((k for k, ln in enumerate(lines) if "G54" in ln.split()), None)
            if i is None:  # G54'süz başlık (GRBL): G21'li satırın sonuna (SPEC 14)
                k = next((k for k, ln in enumerate(lines) if "G21" in ln.split()), len(lines) - 1)
                lines[k] = f"{lines[k]} {b.wcs}"
            else:
                lines[i] = " ".join(b.wcs if w == "G54" else w for w in lines[i].split())
        for ln in lines:
            self.emit([ln])

    def block(self, b: Block) -> None:
        d = self.d
        if isinstance(b, Start):
            self.start(b)
        elif isinstance(b, Comment):
            self.emit([f"({b.text})"])
        elif isinstance(b, ToolChange):
            words = [f"T{b.tool}"]
            if d.tool_change != "M0" or not b.first:
                words.append(d.tool_change_text or d.tool_change)
            self.emit(words)
        elif isinstance(b, ToolLength):
            self.emit(["G43.1", f"Z{self.c(b.delta)}"])
        elif isinstance(b, Spindle):
            self.emit(["M5"] if b.rpm is None else [f"S{b.rpm}", "M3"])
        elif isinstance(b, MachineZ):
            self.emit(["G53", "G0", f"Z{self.c(b.z)}"])
            self.motion = "G0"
        elif isinstance(b, Rapid):
            op_basi = b.x is not None and b.y is not None and b.z is not None
            words = self.g("G0", force=op_basi or b.g43_h is not None)
            if b.g43_h is not None:
                words.append("G43")
            words += self.axes(b)
            if b.g43_h is not None:
                words.append(f"H{b.g43_h:0{d.h_digits}d}")
            self.emit(words)
        elif isinstance(b, Linear):
            self.emit(self.g("G1") + self.axes(b) + self.feed(b.F))
        elif isinstance(b, Arc):
            words = self.g("G3" if b.ccw else "G2") + self.axes(b)
            words += [f"I{self.c(b.i)}", f"J{self.c(b.j)}"] + self.feed(b.F)
            self.emit(words)
        elif isinstance(b, Cycle):
            if b.first:
                words = [b.retract, b.kind] + self.axes(b, ("x", "y", "z", "r"))
                if b.q is not None:
                    words.append(f"Q{self.c(b.q)}")
                if b.p is not None:
                    words.append(f"P{round(b.p * 1000)}" if d.dwell_ms else f"P{fmt(b.p, 3)}")
                words += self.feed(b.F)
            else:
                words = self.axes(b, ("x", "y"))
            self.motion = b.kind
            self.emit(words)
        elif isinstance(b, RigidTap):
            if d.rigid_tap == "m29":
                self.emit(["M29", f"S{b.rpm}"])
            elif d.rigid_tap != "g84":
                raise CamError(f"{d.name}: rijit kılavuz yok")
        elif isinstance(b, Dwell):
            self.emit(["G4", f"P{fmt(b.seconds, 3)}"])
        elif isinstance(b, CycleEnd):
            self.emit(["G80"])
            self.motion = None
        elif isinstance(b, End):
            for f in d.footer:
                self.emit([f])
        else:
            raise CamError(f"Bilinmeyen blok: {type(b).__name__}")


def format(blocks: list[Block], dialect: Dialect) -> str:  # noqa: A001  SPEC 30 adı
    """Blok listesi → program metni ('\\n' ile biten)."""
    f = _Formatter(dialect)
    for b in blocks:
        f.block(b)
    return "\n".join(f.lines) + "\n"
