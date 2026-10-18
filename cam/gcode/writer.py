"""
G-code yazıcı (son işlemci): Toolpath / DrillOp listesi -> program metni.

Kurallar (SPEC 04 + Ek A):
- Satırdaki kelime sırası: N G X Y Z I J R Q F S T M; kelimeler tek boşlukla ayrılır.
- Koordinatlar her zaman mutlak (G90); bastırma yuvarlanmış metin üzerinden: fmt(yeni) == fmt(durum)
  ise eksen / F yazılmaz. G0'da F yazılmaz. Yayda I, J her zaman yazılır.
- I = round(cx) − round(x0): okuyucunun bulduğu merkez yuvarlanmış merkezin tam kendisidir.
- Her op başında: takım farklıysa takım değişimi, takım veya devir farklıysa S<rpm> M3,
  sonra üç eksenli G0 X Y Z.
"""

from __future__ import annotations

from cam.gcode.cycles import DrillOp
from cam.gcode.dialect import GRBL, Dialect
from cam.gcode.modal import ModalState, fmt, snap
from cam.model import ARCS, CamError, Move, MoveType, Toolpath

AXES = ("X", "Y", "Z")


class _Writer:
    """Tek bir programın yazım durumu: modal durum + satırlar + satır numarası."""

    def __init__(self, dialect: Dialect, program_no: int) -> None:
        self.d = dialect
        self.program_no = program_no
        self.state = ModalState()
        self.lines: list[str] = []
        self.n = 0
        self.tools_used = 0

    # --- satır ve sayı yardımcıları -------------------------------------------------
    def emit(self, words: list[str]) -> None:
        """Bir satır ekler; Fanuc'ta '%' ve 'O...' dışındaki her satıra N numarası verir."""
        line = " ".join(words)
        if self.d.line_numbers and line != "%" and not line.startswith("O"):
            self.n += self.d.line_step
            line = f"N{self.n} {line}"
        self.lines.append(line)

    def c(self, v: float) -> str:
        return fmt(v, self.d.decimals)

    def axis_words(self, end: tuple[float, float, float]) -> list[str]:
        """Durumdakinden farklı (yuvarlanmış metne göre) eksen kelimeleri."""
        pos = self.state.pos
        return [
            f"{a}{self.c(v)}" for i, (a, v) in enumerate(zip(AXES, end, strict=True))
            if pos is None or self.c(v) != self.c(pos[i])
        ]

    def feed_word(self, feed: float) -> list[str]:
        """F kelimesi, sadece yuvarlanmış değer durumdakinden farklıysa."""
        F = fmt(feed, self.d.feed_decimals)
        if self.state.feed is not None and F == fmt(self.state.feed, self.d.feed_decimals):
            return []
        self.state.feed = float(F)
        return [f"F{F}"]

    def set_pos(self, end: tuple[float, float, float]) -> None:
        self.state.pos = tuple(snap(v, self.d.decimals) for v in end)

    # --- program parçaları ------------------------------------------------------------
    def header(self) -> None:
        for h in self.d.header:
            self.emit([h.format(program_no=self.program_no)])

    def footer(self) -> None:
        for f in self.d.footer:
            self.emit([f])

    def tool_and_spindle(self, tool_id: int, rpm: float) -> None:
        """Takım farklıysa takım değişimi; takım veya devir farklıysa S<rpm> M3."""
        S = round(rpm)
        changed = tool_id != self.state.tool
        if changed:
            words = [f"T{tool_id}"]
            if self.d.tool_change == "M6" or self.tools_used > 0:
                words.append(self.d.tool_change)
            self.emit(words)
            self.state.tool = tool_id
            self.tools_used += 1
        if changed or S != self.state.rpm:
            self.emit([f"S{S}", "M3"])
            self.state.rpm = S

    def op_start(self, start: tuple[float, float, float]) -> None:
        """Op başlangıcı: G0 ve üç eksen her zaman yazılır."""
        self.emit(["G0"] + [f"{a}{self.c(v)}" for a, v in zip(AXES, start, strict=True)])
        self.state.motion = "G0"
        self.set_pos(start)

    def move(self, m: Move) -> None:
        """Tek hareket: değişen G, değişen eksenler, yayda I J, değişen F."""
        g = m.type.value
        words = [] if self.state.motion == g else [g]
        axes = self.axis_words(m.end)
        if not axes and m.type not in ARCS:
            axes = [f"X{self.c(m.end[0])}"]   # eksensiz G0/G1 satırı hareket sayılmaz
        words += axes
        if m.type in ARCS:
            x0, y0, _ = self.state.pos
            I = snap(m.center[0], self.d.decimals) - x0  # noqa: E741  I = round(cx) − round(x0)
            J = snap(m.center[1], self.d.decimals) - y0  #               J = round(cy) − round(y0)
            words += [f"I{self.c(I)}", f"J{self.c(J)}"]
        if m.type is not MoveType.RAPID:
            words += self.feed_word(m.feed)
        self.emit(words)
        self.state.motion = g
        self.set_pos(m.end)

    def toolpath(self, tp: Toolpath) -> None:
        self.tool_and_spindle(tp.tool.id, tp.rpm)
        self.op_start(tp.start)
        for m in tp.moves:
            self.move(m)

    def drill(self, op: DrillOp) -> None:
        """Delik op: Fanuc'ta G98/G99 G81/G83 ... G80; çevrimsiz dilde kanonik açılım."""
        tp = op.to_toolpath(self.d)       # c < q denetimi her iki dilde de
        if not self.d.canned_cycles:
            self.toolpath(tp)
            return
        self.tool_and_spindle(op.tool.id, op.rpm)
        self.op_start(op.start)
        self.state.motion, self.state.retract = op.kind, op.retract
        for k, (x, y) in enumerate(op.holes):
            if k == 0:
                words = [op.retract, op.kind, f"X{self.c(x)}", f"Y{self.c(y)}",
                         f"Z{self.c(op.z)}", f"R{self.c(op.r)}"]
                if op.kind == "G83":
                    words.append(f"Q{self.c(op.q)}")
                F = fmt(op.feed, self.d.feed_decimals)
                words.append(f"F{F}")
                self.state.feed = float(F)
            else:
                words = self.axis_words((x, y, self.state.pos[2]))
                if not words:
                    words = [f"X{self.c(x)}"]   # aynı noktada ikinci delik
            self.emit(words)
            self.set_pos((x, y, op.z_ret))
        self.emit(["G80"])
        self.state.end_cycle()


def write(ops: list[Toolpath | DrillOp], dialect: Dialect = GRBL, program_no: int = 1) -> str:
    """Op listesini `dialect` diline çevirir. Önce her op doğrulanır (CamError).

    Dönen metin satırları '\\n' ile ayrılır ve '\\n' ile biter.
    """
    for op in ops:
        if isinstance(op, Toolpath):
            op.validate()
        elif isinstance(op, DrillOp):
            op.validate()
        else:
            raise CamError(f"Yazılamayan op tipi: {type(op).__name__}")
    w = _Writer(dialect, program_no)
    w.header()
    for op in ops:
        if isinstance(op, Toolpath):
            w.toolpath(op)
        else:
            w.drill(op)
    w.footer()
    return "\n".join(w.lines) + "\n"
