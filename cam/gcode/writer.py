"""
G-code yazıcı (son işlemci): Toolpath / DrillOp listesi -> program metni.

Kurallar (SPEC 04 + Ek A):
- Satırdaki kelime sırası: N G X Y Z I J R Q F S T M; kelimeler tek boşlukla ayrılır.
- Koordinatlar her zaman mutlak (G90); bastırma yuvarlanmış metin üzerinden: fmt(yeni) == fmt(durum)
  ise eksen / F yazılmaz. G0'da F yazılmaz. Yayda I, J her zaman yazılır.
- I = round(cx) − round(x0): okuyucunun bulduğu merkez yuvarlanmış merkezin tam kendisidir.
- Her op başında: takım farklıysa takım değişimi, takım veya devir farklıysa S<rpm> M3,
  sonra üç eksenli G0 X Y Z.

Tezgâh güvenliği (SPEC 04 Ek B):
- Güvenli Z (`safe_z`, verilmezse op başlarının en yüksek Z'si): her op başında ve program sonunda
  takım bunun altındaysa önce `G0 Z<safe_z>`. Takım değişimi ve devir değişimi güvenli Z'de.
- Op başı `G0 X Y Z<safe_z>`; op başı daha alçaksa iniş ayrı satırda (`Z<z0>`).
- İş mili dönerken takım değiştirilmez: `T` satırından önce `M5`.
- `Dialect.tool_length_comp` ise (Fanuc) takım değişiminden sonraki ilk satır `G0 G43 X Y Z H<n>`.
- Yuvarlanınca uçları aynı noktaya düşen kısa yay (süpürme < π) tam daire olmasın diye G1 yazılır.
"""

from __future__ import annotations

import math

from cam.gcode.cycles import DrillOp
from cam.gcode.dialect import GRBL, Dialect
from cam.gcode.modal import ModalState, fmt, snap
from cam.model import ARCS, CamError, FeedMode, LatheTool, Move, MoveType, Plane, Setup, Toolpath
from cam.setups import check_setup, clearance_height

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
        self.safe_z = 0.0
        self.p_true: tuple[float, float, float] | None = None  # yuvarlanmamış son nokta
        self.wcs: str | None = None  # SPEC 14: programa yazılacak iş sıfırı kodu
        self.length_offsets: dict[int, float] | None = None  # SPEC 14: GRBL G43.1 ofsetleri

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
            f"{a}{self.c(v)}"
            for i, (a, v) in enumerate(zip(AXES, end, strict=True))
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
        """Program başı. İş sıfırı verilmişse (SPEC 14) baştaki G54 onunla değişir; G54 yoksa
        G21'li satırın sonuna eklenir."""
        lines = [h.format(program_no=self.program_no) for h in self.d.header]
        if self.wcs is not None:
            words = [line.split() for line in lines]
            if any("G54" in w for w in words):
                words = [[self.wcs if x == "G54" else x for x in w] for w in words]
            else:
                i = next(i for i, w in enumerate(words) if "G21" in w)
                words[i].append(self.wcs)
            lines = [" ".join(w) for w in words]
        for line in lines:
            self.emit([line])

    def footer(self) -> None:
        for f in self.d.footer:
            self.emit([f])

    def retract(self) -> None:
        """Takım güvenli Z'nin altındaysa (yuvarlanmış metne göre) `G0 Z<safe_z>`."""
        pos = self.state.pos
        if pos is not None and pos[2] < snap(self.safe_z, self.d.decimals):
            self.move(Move(MoveType.RAPID, (pos[0], pos[1], self.safe_z)))

    def tool_and_spindle(self, tool_id: int, rpm: float) -> bool:
        """Takım farklıysa M5 (iş mili dönüyorsa) ve takım değişimi; takım veya devir farklıysa
        S<rpm> M3. Takım değiştiyse True."""
        S = round(rpm)
        changed = tool_id != self.state.tool
        if changed:
            if self.state.rpm is not None:
                self.emit(["M5"])
                self.state.rpm = None
            words = [f"T{tool_id}"]
            if self.d.tool_change == "M6" or self.tools_used > 0:
                words.append(self.d.tool_change)
            self.emit(words)
            self.state.tool = tool_id
            self.tools_used += 1
            if self.length_offsets is not None:
                self.emit(["G43.1", f"Z{self.c(self.length_offsets[tool_id])}"])
        if changed or S != self.state.rpm:
            self.emit([f"S{S}", "M3"])
            self.state.rpm = S
        return changed

    def op_begin(self, tool_id: int, rpm: float, start: tuple[float, float, float]) -> None:
        """Op başı: geri çekme, takım/devir, güvenli Z'de `G0 X Y Z` (G43 H), gerekirse iniş."""
        self.retract()
        changed = self.tool_and_spindle(tool_id, rpm)
        g43 = changed and self.d.tool_length_comp
        at_safe = (start[0], start[1], self.safe_z)
        words = ["G0"] + (["G43"] if g43 else [])
        words += [f"{a}{self.c(v)}" for a, v in zip(AXES, at_safe, strict=True)]
        self.emit(words + ([f"H{tool_id}"] if g43 else []))
        self.state.motion = "G0"
        self.set_pos(at_safe)
        self.p_true = at_safe
        if self.c(start[2]) != self.c(self.safe_z):
            self.move(Move(MoveType.RAPID, start))
        self.p_true = start

    def tiny_arc(self, m: Move) -> bool:
        """Yuvarlanmış uçları XY'de aynı ama modelde tam daire olmayan, süpürmesi < π yay mı?

        Metin tam daire okunurdu (2πr). Süpürme < π ⇔ G3'te v0 × v1 > 0, G2'de < 0
        (v0, v1: merkezden başlangıca ve bitişe vektörler).
        """
        p0, p1, c = self.p_true, m.end, m.center
        if p0[:2] == p1[:2] or any(self.c(p1[i]) != self.c(self.state.pos[i]) for i in (0, 1)):
            return False
        cross = (p0[0] - c[0]) * (p1[1] - c[1]) - (p0[1] - c[1]) * (p1[0] - c[0])
        return cross > 0 if m.type is MoveType.ARC_CCW else cross < 0

    def move(self, m: Move) -> None:
        """Tek hareket: değişen G, değişen eksenler, yayda I J, değişen F."""
        if m.type in ARCS and self.tiny_arc(m):
            m = Move(MoveType.LINEAR, m.end, m.feed)  # kiriş ≤ 2ε: G1 yeterli
        g = m.type.value
        words = [] if self.state.motion == g else [g]
        axes = self.axis_words(m.end)
        if not axes and m.type not in ARCS:
            axes = [f"X{self.c(m.end[0])}"]  # eksensiz G0/G1 satırı hareket sayılmaz
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
        self.p_true = m.end

    def toolpath(self, tp: Toolpath) -> None:
        self.op_begin(tp.tool.id, tp.rpm, tp.start)
        for m in tp.moves:
            self.move(m)

    def drill(self, op: DrillOp) -> None:
        """Delik op: Fanuc'ta G98/G99 G81/G83 ... G80; çevrimsiz dilde kanonik açılım."""
        tp = op.to_toolpath(self.d)  # c < q denetimi her iki dilde de
        if not self.d.canned_cycles:
            self.toolpath(tp)
            return
        self.op_begin(op.tool.id, op.rpm, op.start)
        self.state.motion, self.state.retract = op.kind, op.retract
        for k, (x, y) in enumerate(op.holes):
            if k == 0:
                words = [
                    op.retract,
                    op.kind,
                    f"X{self.c(x)}",
                    f"Y{self.c(y)}",
                    f"Z{self.c(op.z)}",
                    f"R{self.c(op.r)}",
                ]
                if op.kind == "G83":
                    words.append(f"Q{self.c(op.q)}")
                F = fmt(op.feed, self.d.feed_decimals)
                words.append(f"F{F}")
                self.state.feed = float(F)
            else:
                words = self.axis_words((x, y, self.state.pos[2]))
                if not words:
                    words = [f"X{self.c(x)}"]  # aynı noktada ikinci delik
            self.emit(words)
            self.set_pos((x, y, op.z_ret))
            self.p_true = (x, y, op.z_ret)
        self.emit(["G80"])
        self.state.end_cycle()


def _yazilabilir(tp: Toolpath) -> None:
    """Geçici koruma (SPEC 00 Ek 2): bu yazıcı yalnız G17 / G94 / sabit devirli freze yolu yazar.
    Torna yolları (G18, G95, G96) SPEC 21'in yazıcısına kadar sessizce yanlış yazılmasın diye reddedilir."""
    if isinstance(tp.tool, LatheTool):
        raise CamError(f"Takım yolu '{tp.name}': torna takımı bu yazıcıda desteklenmiyor (SPEC 21)")
    if tp.plane is not Plane.XY:
        raise CamError(f"Takım yolu '{tp.name}': {tp.plane.value} düzlemi desteklenmiyor, yalnız G17")
    if tp.feed_mode is not FeedMode.PER_MIN:
        raise CamError(f"Takım yolu '{tp.name}': {tp.feed_mode.value} desteklenmiyor, yalnız G94 (mm/dk)")
    if tp.css is not None:
        raise CamError(f"Takım yolu '{tp.name}': G96 sabit kesme hızı desteklenmiyor (SPEC 21)")


def _z_kesme(ops: list[Toolpath | DrillOp]) -> float:
    """Ek C1: XY'de yer değiştiren (uçlara göre > 1e-9 mm) kesme hareketlerinin en yüksek Z'si; yoksa −∞."""
    z = -math.inf
    for op in ops:
        if not isinstance(op, Toolpath):
            continue
        p0 = op.start
        for m in op.moves:
            if m.type is not MoveType.RAPID and math.dist(p0[:2], m.end[:2]) > 1e-9:
                z = max(z, p0[2], m.end[2])
            p0 = m.end
    return z


def _stok_ustu(ops: list[Toolpath | DrillOp], dialect: Dialect, safe_z: float, stock_top: float) -> None:
    """Ek C2: safe_z > stock_top; hiçbir XY hızlı hareket stock_top altında değil (DrillOp: açılımı)."""
    if not math.isfinite(stock_top):
        raise CamError(f"stock_top sonlu olmalı ({stock_top})")
    if not safe_z > stock_top:
        raise CamError(f"safe_z ({safe_z}) ham malzeme üstünden ({stock_top}) yüksek olmalı (Ek C2)")
    for op in ops:
        tp = op if isinstance(op, Toolpath) else op.to_toolpath(dialect)
        p0 = tp.start
        for i, m in enumerate(tp.moves):
            xy = math.dist(p0[:2], m.end[:2]) > 1e-9
            if m.type is MoveType.RAPID and xy and min(p0[2], m.end[2]) < stock_top:
                z = min(p0[2], m.end[2])
                raise CamError(
                    f"'{op.name}' hareket {i}: Z={z} < stock_top={stock_top} iken XY hızlı hareket (Ek C2)"
                )
            p0 = m.end


def _ofsetler(length_offsets: dict[int, float], ops: list, dialect: Dialect) -> None:
    """G43.1 ofsetleri yalnız takım boyu tablosu olmayan dilde (GRBL); programdaki her takım için."""
    if dialect.tool_length_comp:
        raise CamError(f"{dialect.name}: takım boyu G43 H ile verilir, length_offsets kullanılmaz")
    for op in ops:
        n = op.tool.id
        if n not in length_offsets:
            raise CamError(f"length_offsets: T{n} için takım boyu ofseti yok")
        if not math.isfinite(length_offsets[n]):
            raise CamError(f"length_offsets: T{n} ofseti sonlu olmalı ({length_offsets[n]})")


def write(
    ops: list[Toolpath | DrillOp],
    dialect: Dialect = GRBL,
    program_no: int = 1,
    safe_z: float | None = None,
    stock_top: float | None = None,
    setup: Setup | None = None,
    length_offsets: dict[int, float] | None = None,
) -> str:
    """Op listesini `dialect` diline çevirir. Önce her op doğrulanır (CamError).

    `safe_z`: op geçişlerinde, takım değişiminde ve program sonunda çekilen güvenli Z [mm].
    Verilmezse op başlarının en yüksek Z'si. Bir op başından alçaksa CamError.
    `stock_top`: ham malzeme üstü [mm] (Ek C2); verilirse altında XY hızlı hareket yasak.
    Dönen metin satırları '\\n' ile ayrılır ve '\\n' ile biter.

    SPEC 14: `setup` verilirse bağlama denetimi, programda iş sıfırı kodu ve ham malzemeden güvenli Z;
    `length_offsets` (yalnız GRBL) her takım değişiminden sonra `G43.1 Z<ΔL>`.
    """
    for op in ops:
        if isinstance(op, Toolpath):
            op.validate()
            _yazilabilir(op)
        elif isinstance(op, DrillOp):
            op.validate()
        else:
            raise CamError(f"Yazılamayan op tipi: {type(op).__name__}")
    z_top = max((op.start[2] for op in ops), default=0.0)
    if setup is not None:
        check_setup(setup, ops)
        ust = clearance_height(setup, 0.0)  # malzeme / bağlama elemanlarının en üstü
        if safe_z is None:
            safe_z = max(clearance_height(setup), z_top)
        elif not math.isfinite(safe_z) or safe_z < ust:
            raise CamError(f"Güvenli Z ({safe_z}) ham malzeme / bağlama üstünden ({ust}) alçak olamaz")
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
    if length_offsets is not None:
        _ofsetler(length_offsets, ops, dialect)
    w = _Writer(dialect, program_no)
    w.safe_z = float(safe_z)
    w.wcs = None if setup is None else setup.wcs.code
    w.length_offsets = length_offsets
    w.header()
    for op in ops:
        if isinstance(op, Toolpath):
            w.toolpath(op)
        else:
            w.drill(op)
    w.retract()
    w.footer()
    return "\n".join(w.lines) + "\n"
