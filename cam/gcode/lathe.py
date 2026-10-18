"""
Torna G-code: Fanuc torna (G-code sistemi A) son işlemcisi ve okuyucusu. SPEC 21.

- Modelde x yarıçaptır; G-code'da X çaptır (X = 2·x). Yay merkezi I yarıçap, başlangıca göre bağıl.
- İş mili: G97 S<n> (sabit devir) veya G50 S<n_max> + G96 S<Vc> (sabit kesme hızı); yön (M3/M4) zorunlu girdi.
- İlerleme G99 (mm/dev). G90, G91, G92, G94, G95, G98 asla yazılmaz (sistem A'da çevrim veya mm/dk).
- Taret sadece zorunlu takım değiştirme noktasında döner; hızlı hareketler eksen eksen
  (Fanuc G0 doğrusal olmayabilir).
- Diş: THREAD takımlı yolda Z'ye paralel G1 → G32 Z F<hatve>.
- Eksenel delme (Ek E3, SPEC 40): DRILL/CONE Tool, bütün noktalar x = 0, yay yok, G97; G0/G1 Z satırları.
Kaynak: Fanuc Series 0i-TF Operatör El Kitabı (B-64604EN); Smid, CNC Programming Handbook, torna bölümleri.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass

import numpy as np

from cam.gcode.modal import fmt, snap
from cam.model import (
    ARCS,
    R_MIN,
    CamError,
    FeedMode,
    LatheTool,
    LatheToolKind,
    Move,
    MoveType,
    Plane,
    Tool,
    Toolpath,
)

SPINDLE_DIRS = ("M3", "M4")
EPS = 1e-9  # mm: "eksen değişmedi" toleransı (çapraz G0, konik diş, eksenel yolda x = 0)
AXIAL_KINDS = ("DRILL", "CONE")  # eksenel delmede kabul edilen freze takımı türleri (Ek E3); ada göre


def _axial(tool) -> bool:
    """Eksenel delme takımı mı (Ek E3): Tool, türü DRILL veya CONE."""
    return isinstance(tool, Tool) and tool.kind.name in AXIAL_KINDS


@dataclass(frozen=True)
class LatheDialect:
    name: str
    decimals: int  # X (çap) ve Z ondalık basamağı
    feed_decimals: int  # F (mm/dev) ondalık basamağı
    lead_decimals: int  # G32 F (hatve) ondalık basamağı
    line_numbers: bool  # N10, N20, ... yazılsın mı
    line_step: int  # satır numarası artışı
    header: tuple[str, ...]  # program başı ('{program_no}' yer tutucusu)
    footer: tuple[str, ...]  # program sonu


FANUC_TORNA = LatheDialect(
    name="Fanuc torna",
    decimals=3,
    feed_decimals=3,
    lead_decimals=4,
    line_numbers=True,
    line_step=10,
    header=("%", "O{program_no:04d}", "G21 G18 G40 G99 G54"),
    footer=("M5", "M30", "%"),
)


def spindle_rpm(css: float, x: float, rpm_max: float) -> float:
    """G96'da kontrolörün devri: n = min(1000·Vc / (π·D), n_max), D = 2·|x|; x = 0 → n_max."""
    for ad, v in (("css", css), ("x", x), ("rpm_max", rpm_max)):
        if not math.isfinite(v):
            raise CamError(f"spindle_rpm: {ad} sonlu olmalı ({v})")
    if css <= 0 or rpm_max <= 0:
        raise CamError(f"spindle_rpm: css ve rpm_max pozitif olmalı ({css=}, {rpm_max=})")
    D = 2 * abs(x)
    if D == 0:
        return float(rpm_max)
    return min(1000 * css / (math.pi * D), float(rpm_max))


def _check_spindle(spindle) -> None:
    if spindle not in SPINDLE_DIRS:
        raise CamError(f"İş mili yönü 'M3' veya 'M4' olmalı ({spindle!r})")


def _sweep_lt_pi(p0, p1, m: Move) -> bool:
    """Yayın süpürmesi < π mi? ZX'te (u, v) = (z, x); G3'te v0 × v1 > 0, G2'de < 0 (SPEC 04 Ek B1)."""
    cx, cz = m.center
    v0 = (p0[2] - cz, p0[0] - cx)
    v1 = (p1[2] - cz, p1[0] - cx)
    cross = v0[0] * v1[1] - v0[1] * v1[0]
    return cross > 0 if m.type is MoveType.ARC_CCW else cross < 0


# ---------------------------------------------------------------- yazıcı


def _check_op(tp: Toolpath, tc: tuple[float, float]) -> None:
    """Bir yolun torna yazıcısına uygunluğu (SPEC 21 "Arayüz"); aksi CamError."""
    tp.validate()
    nerede = f"Takım yolu '{tp.name}'"
    if _axial(tp.tool):
        raise NotImplementedError("SPEC 21 Ek E3: eksenel delme yazımı")
    if not isinstance(tp.tool, LatheTool):
        raise CamError(f"{nerede}: torna takımı değil; freze yolları cam.gcode.write ile yazılır")
    if tp.plane is not Plane.ZX:
        raise CamError(f"{nerede}: torna yolu ZX (G18) düzleminde olmalı")
    if tp.feed_mode is not FeedMode.PER_REV:
        raise CamError(f"{nerede}: tornada sadece G99 (mm/dev) yazılır ({tp.feed_mode.value})")
    tid = tp.tool.id
    if isinstance(tid, bool) or not isinstance(tid, int) or not 1 <= tid <= 99:
        raise CamError(f"{nerede}: takım no. 1..99 olmalı (T<ss><oo>), {tid!r}")
    thread = tp.tool.kind is LatheToolKind.THREAD
    if thread and tp.css is not None:
        raise CamError(f"{nerede}: diş (G32) sabit devir ister; css verilmemeli")
    p = tp.start
    for i, m in enumerate(tp.moves):
        dx, dz = abs(m.end[0] - p[0]), abs(m.end[2] - p[2])
        if m.type is MoveType.RAPID and dx > EPS and dz > EPS:
            raise CamError(f"{nerede}, hareket {i}: çapraz G0 yazılmaz (Fanuc G0 doğrusal olmayabilir)")
        if thread and m.type in ARCS:
            raise CamError(f"{nerede}, hareket {i}: diş yolunda yay olamaz")
        if thread and m.type is MoveType.LINEAR and dx > EPS:
            raise CamError(f"{nerede}, hareket {i}: konik diş desteklenmiyor (G32'de X değişmez)")
        p = m.end
    lo, hi = tp.bbox()
    if hi[0] > tc[0] + EPS or hi[2] > tc[1] + EPS:
        raise CamError(
            f"{nerede}: takım değiştirme noktası ({tc[0]}, {tc[1]}) yolun en büyük x / z'sinin "
            f"({hi[0]}, {hi[2]}) altında"
        )


class _LatheWriter:
    """Tek programın yazım durumu. Konum, yazılan metnin okununca verdiği değerlerdir (x yarıçap)."""

    def __init__(self, d: LatheDialect, program_no: int, spindle: str, tc: tuple[float, float]) -> None:
        self.d = d
        self.program_no = program_no
        self.spindle = spindle
        self.tc = tc
        self.lines: list[str] = []
        self.n = 0
        self.motion: str | None = None
        self.F: str | None = None  # son yazılan F metni
        self.tool: int | None = None
        self.sp: tuple | None = None  # yazılı iş mili durumu; None → duruyor
        self.pos: tuple[float, float] | None = None  # (x̂, ẑ)
        self.p_true: tuple[float, float, float] | None = None  # yuvarlanmamış son nokta

    def emit(self, words: list[str]) -> None:
        line = " ".join(words)
        if self.d.line_numbers and line != "%" and not line.startswith("O"):
            self.n += self.d.line_step
            line = f"N{self.n} {line}"
        self.lines.append(line)

    def X(self, x: float) -> str:
        return fmt(2 * x, self.d.decimals)  # çap

    def Z(self, z: float) -> str:
        return fmt(z, self.d.decimals)

    def axis_words(self, x: float, z: float) -> list[str]:
        """Yuvarlanmış metne göre değişen X / Z kelimeleri."""
        words = []
        if self.pos is None or self.X(x) != self.X(self.pos[0]):
            words.append(f"X{self.X(x)}")
        if self.pos is None or self.Z(z) != self.Z(self.pos[1]):
            words.append(f"Z{self.Z(z)}")
        return words

    def set_pos(self, x: float, z: float) -> None:
        self.pos = (snap(2 * x, self.d.decimals) / 2, snap(z, self.d.decimals))
        self.p_true = (x, 0.0, z)

    def feed_word(self, feed: float, decimals: int) -> list[str]:
        F = fmt(feed, decimals)
        if F == self.F:
            return []
        self.F = F
        return [f"F{F}"]

    def rapid(self, x: float, z: float, force_x: bool = False) -> None:
        """Eksen eksen G0 (değişen eksen yoksa satır yazılmaz; force_x ise X her zaman yazılır)."""
        axes = self.axis_words(x, z)
        if force_x and not any(a.startswith("X") for a in axes):
            axes.insert(0, f"X{self.X(x)}")
        if not axes:
            return
        self.emit(([] if self.motion == "G0" else ["G0"]) + axes)
        self.motion = "G0"
        self.set_pos(x, z)

    def spindle_words(self, tp: Toolpath) -> None:
        """İş mili satırları: G97 S<n> M3|M4 veya G50 S<n_max> + G96 S<Vc> M3|M4 (değiştiyse)."""
        n = round(tp.rpm)
        sp = ("G97", n) if tp.css is None else ("G96", round(tp.css), n)
        if sp == self.sp:
            return
        if tp.css is None:
            self.emit(["G97", f"S{n}", self.spindle])
        else:
            self.emit(["G50", f"S{n}"])
            self.emit(["G96", f"S{round(tp.css)}", self.spindle])
        self.sp = sp
        self.motion = None  # iş mili satırından sonraki ilk hareket G kelimesini yazar

    def op_begin(self, tp: Toolpath) -> None:
        """Geri çekme, (takım değişimi), iş mili, G0 X<2x_A> z_tc'de, G0 Z<z_A>."""
        x_tc, z_tc = self.tc
        x_A, _, z_A = tp.start
        if self.pos is None:  # program başı: varsayım, taret tc'de veya ötesinde
            self.emit(["G0", f"X{self.X(x_tc)}", f"Z{self.Z(z_tc)}"])
            self.motion = "G0"
            self.set_pos(x_tc, z_tc)
        self.rapid(self.pos[0], z_tc)
        if tp.tool.id != self.tool:
            self.rapid(x_tc, z_tc)
            if self.sp is not None:
                self.emit(["M5"])
                self.sp = None
            self.emit([f"T{tp.tool.id:02d}{tp.tool.id:02d}"])
            self.tool = tp.tool.id
            self.motion = None
        self.spindle_words(tp)
        self.rapid(x_A, z_tc, force_x=True)
        self.rapid(x_A, z_A)
        self.p_true = tp.start

    def move(self, m: Move, thread: bool) -> None:
        x, _, z = m.end
        t = m.type
        if t in ARCS and not self.axis_words(x, z):  # çok kısa yay: uçlar aynı metne düşüyor
            if not _sweep_lt_pi(self.p_true, m.end, m):
                raise CamError("Yuvarlanınca tam daire okunacak yay (süpürme ≥ π) tornada yazılamaz")
            t = MoveType.LINEAR  # kiriş ≤ 2ε
        if t is MoveType.RAPID:
            self.rapid(x, z)
            self.p_true = m.end
            return
        g = "G32" if thread else t.value
        words = [] if self.motion == g else [g]
        axes = self.axis_words(x, z)
        if not axes and t not in ARCS:
            axes = [f"X{self.X(x)}"]  # eksensiz G1 satırı hareket sayılmaz
        words += axes
        if t in ARCS:
            cx, cz = m.center
            I = cx - self.pos[0]  # noqa: E741  I = c_x − x̂0 (yarıçap, bağıl)
            K = snap(cz, self.d.decimals) - self.pos[1]  # K = round(c_z) − ẑ0
            words += [f"I{fmt(I, self.d.decimals)}", f"K{fmt(K, self.d.decimals)}"]
        words += self.feed_word(m.feed, self.d.lead_decimals if thread else self.d.feed_decimals)
        self.emit(words)
        self.motion = g
        self.set_pos(x, z)

    def toolpath(self, tp: Toolpath) -> None:
        self.op_begin(tp)
        thread = tp.tool.kind is LatheToolKind.THREAD
        for m in tp.moves:
            self.move(m, thread)

    def end(self) -> None:
        x_tc, z_tc = self.tc
        self.rapid(self.pos[0], z_tc)
        self.rapid(x_tc, z_tc)


def write_lathe(
    ops: list[Toolpath],
    spindle: str,
    tool_change: tuple[float, float],
    dialect: LatheDialect = FANUC_TORNA,
    program_no: int = 1,
) -> str:
    """Torna yollarını Fanuc torna programına çevirir.

    `spindle`: 'M3' veya 'M4' (zorunlu). `tool_change`: (x_tc, z_tc), yarıçap, iş koordinatında.
    """
    _check_spindle(spindle)
    if not ops:
        raise CamError("Yazılacak torna yolu yok")
    tc = tuple(float(v) for v in tool_change)
    if len(tc) != 2 or not all(math.isfinite(v) for v in tc):
        raise CamError(f"Takım değiştirme noktası (x, z) sonlu olmalı ({tool_change})")
    for tp in ops:
        if not isinstance(tp, Toolpath):
            raise CamError(f"Yazılamayan op tipi: {type(tp).__name__}")
        _check_op(tp, tc)
    w = _LatheWriter(dialect, program_no, spindle, tc)
    for h in dialect.header:
        w.emit([h.format(program_no=program_no)])
    for tp in ops:
        w.toolpath(tp)
    w.end()
    for f in dialect.footer:
        w.emit([f])
    return "\n".join(w.lines) + "\n"


# ---------------------------------------------------------------- okuyucu

_WORD = re.compile(r"([A-Z])([+-]?(?:\d+\.?\d*|\.\d+))")
_COMMENT = re.compile(r"\([^()]*\)")

LETTERS = set("GMXZUWIKRFSTNO")
G_MOTION = {0: "G0", 1: "G1", 2: "G2", 3: "G3", 32: "G32"}
G_NOOP = {18, 21, 40, 54, 99}
G_SPINDLE = {50, 96, 97}
G_REFUSED = {
    90: "G90 sistem A'da dış çap çevrimidir (mutlak/artımsal X Z / U W ile)",
    91: "G91 desteklenmiyor (sistem B/C); artımsal için U / W",
    92: "G92 sistem A'da diş çevrimidir; desteklenmiyor",
    94: "G94 sistem A'da alın çevrimidir; desteklenmiyor",
    95: "G95 desteklenmiyor (sistem B/C); ilerleme G99",
    98: "G98 (mm/dk) desteklenmiyor; tornada G99 (mm/dev)",
    20: "G20 (inç) desteklenmiyor; birim dönüşümü yapılmaz",
    17: "G17 düzlemi desteklenmiyor (tornada G18)",
    19: "G19 düzlemi desteklenmiyor (tornada G18)",
    41: "G41 burun telafisi desteklenmiyor (yol CAM'de telafili; çift telafi)",
    42: "G42 burun telafisi desteklenmiyor (yol CAM'de telafili; çift telafi)",
    28: "G28 referansa dönüş desteklenmiyor (konum bilinmez)",
    **{g: f"G{g} kontrolör çevrimi desteklenmiyor" for g in (70, 71, 72, 73, 74, 75, 76)},
}
M_OK = {0, 1, 2, 3, 4, 5, 8, 9, 30}
ARC_TYPES = {"G2": MoveType.ARC_CW, "G3": MoveType.ARC_CCW}


def _parse(raw: str) -> tuple[list[int], list[int], dict[str, float]] | None:
    """Bir satırı (G kodları, M kodları, diğer kelimeler) olarak çözer; boş satırda None."""
    s = _COMMENT.sub("", raw).split(";", 1)[0]
    if "(" in s or ")" in s:
        raise CamError("kapanmamış yorum parantezi")
    s = "".join(s.split()).upper()
    if s in ("", "%"):
        return None
    gs: list[int] = []
    ms: list[int] = []
    w: dict[str, float] = {}
    i = 0
    while i < len(s):
        m = _WORD.match(s, i)
        if m is None:
            raise CamError(f"çözülemeyen ifade '{s[i:]}'")
        letter, num = m.group(1), m.group(2)
        i = m.end()
        if letter in "YJ":
            raise CamError(f"{letter} kelimesi desteklenmiyor (torna, G18 / XZ düzlemi)")
        if letter not in LETTERS:
            raise CamError(f"bilinmeyen kelime '{letter}{num}'")
        if letter in "GM":
            v = float(num)
            if not v.is_integer():
                raise CamError(f"bilinmeyen {letter} kodu '{letter}{num}'")
            (gs if letter == "G" else ms).append(int(v))
        elif letter in w:
            raise CamError(f"'{letter}' kelimesi satırda iki kez var")
        else:
            w[letter] = float(num)
    return gs, ms, w


def _arc_center_r(p0: np.ndarray, p1: np.ndarray, R: float, ccw: bool) -> np.ndarray:
    """R biçimi (SPEC 04), (u, v) = (z, x): h = √(R² − (L/2)²), c = m ± h·n.
    G3 ve R > 0 → merkez kirişin solunda, G2 → sağında; R < 0 tarafı çevirir."""
    d = p1 - p0
    L = float(np.hypot(*d))
    if L < R_MIN:
        raise CamError("R biçimiyle tam daire tanımsız")
    if abs(R) < L / 2:
        raise CamError(f"yay yarıçapı |R| = {abs(R)} kirişin yarısından ({L / 2}) küçük")
    h = math.sqrt(R * R - (L / 2) ** 2)
    n_left = np.array([-d[1], d[0]]) / L
    side = 1.0 if ccw else -1.0
    if R < 0:
        side = -side
    return (p0 + p1) / 2 + side * h * n_left


class _LatheReader:
    def __init__(self, tools: dict[int, LatheTool | Tool], spindle: str | None, arc_tol: float) -> None:
        self.tools = tools
        self.spindle = spindle
        self.arc_tol = arc_tol
        self.x: float | None = None  # yarıçap
        self.z: float | None = None
        self.motion: str | None = None
        self.feed: float | None = None
        self.tool: LatheTool | Tool | None = None
        self.mode: str | None = None  # 'G96' | 'G97'
        self.css: float | None = None
        self.rpm: float | None = None  # G97 devri
        self.limit: float | None = None  # G50 devir sınırı
        self.pending = False  # yeni yol başlayacak: sonraki hareket G0 olmalı
        self.cur: Toolpath | None = None
        self.paths: list[Toolpath] = []

    # --- satır ------------------------------------------------------------------------
    def line(self, gs: list[int], ms: list[int], w: dict[str, float]) -> None:
        sp_g = None
        for g in gs:
            if g in G_REFUSED:
                raise CamError(G_REFUSED[g])
            if g in G_MOTION:
                self.motion = G_MOTION[g]
            elif g in G_SPINDLE:
                sp_g = g
            elif g not in G_NOOP:
                raise CamError(f"bilinmeyen G kodu 'G{g}'")
        for m in ms:
            if m not in M_OK:
                raise CamError(f"bilinmeyen M kodu 'M{m}'")
            if m in (3, 4) and self.spindle is not None and f"M{m}" != self.spindle:
                raise CamError(f"iş mili yönü M{m}, beklenen {self.spindle}")
        if "T" in w:
            self.tool_change(w["T"])
        if sp_g is not None or "S" in w:
            self.spindle_change(sp_g, w)
        if "F" in w:
            self.feed = w["F"]
        if any(a in w for a in "XZUW") or (self.motion in ARC_TYPES and any(a in w for a in "IKR")):
            self.do_move(w)

    def tool_change(self, T: float) -> None:
        if not T.is_integer():
            raise CamError(f"T kelimesi tam sayı olmalı (T{T})")
        ss, oo = divmod(int(T), 100)
        if ss not in self.tools:
            raise CamError(f"bilinmeyen takım T{ss:02d}")
        if oo != ss:
            raise CamError(f"T{ss:02d}{oo:02d}: ofset no. istasyonla aynı olmalı (T{ss:02d}{ss:02d})")
        if isinstance(self.tools[ss], Tool):
            raise NotImplementedError("SPEC 21 Ek E3: eksenel delme okuması")
        self.tool = self.tools[ss]
        self.pending = True

    def spindle_change(self, g: int | None, w: dict[str, float]) -> None:
        if "S" not in w:
            raise CamError(f"G{g} için S kelimesi gerekli")
        S = w["S"]
        before = (self.mode, self.css, self.rpm, self.limit)
        if g == 50:
            if "X" in w or "Z" in w or "U" in w or "W" in w:
                raise CamError("G50 X/Z koordinat sistemi kurar; desteklenmiyor (sadece G50 S)")
            self.limit = S
        elif g == 96 or (g is None and self.mode == "G96"):
            if self.limit is None:
                raise CamError("G96 için önce G50 S<devir sınırı> verilmeli")
            self.mode, self.css = "G96", S
        else:
            self.mode, self.rpm = "G97", S
        if (self.mode, self.css, self.rpm, self.limit) != before:
            self.pending = True

    # --- hareket ----------------------------------------------------------------------
    def target(self, w: dict[str, float]) -> tuple[float | None, float | None]:
        if "X" in w and "U" in w:
            raise CamError("aynı satırda X ve U")
        if "Z" in w and "W" in w:
            raise CamError("aynı satırda Z ve W")
        x, z = self.x, self.z
        if "X" in w:
            x = w["X"] / 2
        elif "U" in w:
            if self.x is None:
                raise CamError("X konumu bilinmiyor (U artımsal)")
            x = self.x + w["U"] / 2
        if "Z" in w:
            z = w["Z"]
        elif "W" in w:
            if self.z is None:
                raise CamError("Z konumu bilinmiyor (W artımsal)")
            z = self.z + w["W"]
        return x, z

    def do_move(self, w: dict[str, float]) -> None:
        if self.motion is None:
            raise CamError("hareket tipi (G0/G1/G2/G3/G32) bilinmiyor")
        x, z = self.target(w)
        if self.tool is None:
            if self.motion != "G0":
                raise CamError(f"ilk T'den önce sadece G0 olabilir ({self.motion})")
            self.x, self.z = x, z
            return
        if x is None or z is None:
            raise CamError("konumu bilinmeyen eksen")
        if self.pending:
            if self.motion != "G0":
                raise CamError(f"takım / iş mili değişiminden sonraki ilk hareket G0 olmalı ({self.motion})")
            self.start_path(x, z)
            self.x, self.z = x, z
            return
        if self.cur is None:
            raise CamError("yol başlamadı")
        self.cur.moves.append(self.make_move(x, z, w))
        self.x, self.z = x, z

    def start_path(self, x: float, z: float) -> None:
        if self.mode is None:
            raise CamError("iş mili devri tanımsız (G97 S veya G50 S + G96 S)")
        rpm = self.limit if self.mode == "G96" else self.rpm
        css = self.css if self.mode == "G96" else None
        k = len(self.paths) + 1
        self.cur = Toolpath(
            name=f"T{self.tool.id}-{k}",
            tool=self.tool,
            start=(x, 0.0, z),
            rpm=rpm,
            plane=Plane.ZX,
            feed_mode=FeedMode.PER_REV,
            css=css,
        )
        self.paths.append(self.cur)
        self.pending = False

    def make_move(self, x: float, z: float, w: dict[str, float]) -> Move:
        g = self.motion
        if g == "G0":
            return Move(MoveType.RAPID, (x, 0.0, z))
        if self.feed is None or self.feed <= 0:
            raise CamError(f"{g}: ilerleme (F) yok")
        if g == "G32":
            if self.tool.kind is not LatheToolKind.THREAD:
                raise CamError("G32 sadece diş takımıyla")
            return Move(MoveType.LINEAR, (x, 0.0, z), feed=self.feed)
        if g == "G1":
            return Move(MoveType.LINEAR, (x, 0.0, z), feed=self.feed)
        return Move(ARC_TYPES[g], (x, 0.0, z), feed=self.feed, center=self.arc_center(x, z, w))

    def arc_center(self, x: float, z: float, w: dict[str, float]) -> tuple[float, float]:
        """Yay merkezi (x, z): I/K (yarıçap, bağıl) veya R; uç yarıçapları denetlenip merkez orta dikmeye
        izdüşürülür. Tornada tam daire → CamError."""
        p0 = np.array([self.z, self.x])  # (u, v) = (z, x)
        p1 = np.array([z, x])
        if float(np.hypot(*(p1 - p0))) < R_MIN:
            raise CamError("tornada tam daire yay olamaz")
        ccw = self.motion == "G3"
        if "R" in w:
            if "I" in w or "K" in w:
                raise CamError("yayda hem R hem I/K")
            c = _arc_center_r(p0, p1, w["R"], ccw)
        else:
            c = p0 + np.array([w.get("K", 0.0), w.get("I", 0.0)])
        r0 = float(np.hypot(*(p0 - c)))
        r1 = float(np.hypot(*(p1 - c)))
        if r0 < R_MIN or abs(r0 - r1) > self.arc_tol:
            raise CamError(f"yay yarıçapları tutmuyor (r0={r0}, r1={r1})")
        m = (p0 + p1) / 2
        d = p1 - p0
        u = np.array([-d[1], d[0]]) / float(np.hypot(*d))
        c = m + float(np.dot(c - m, u)) * u
        return (float(c[1]), float(c[0]))


def read_lathe(
    text: str,
    tools: dict[int, LatheTool | Tool],
    spindle: str | None = None,
    arc_tol: float = 0.005,
) -> list[Toolpath]:
    """Fanuc torna programını Toolpath listesine okur (plane ZX, feed_mode PER_REV, x yarıçap)."""
    if spindle is not None:
        _check_spindle(spindle)
    r = _LatheReader(tools, spindle, arc_tol)
    for n, raw in enumerate(text.splitlines(), start=1):
        try:
            parsed = _parse(raw)
            if parsed is None:
                continue
            r.line(*parsed)
        except CamError as e:
            raise CamError(f"satır {n}: {e}") from e
    for tp in r.paths:
        tp.validate()
    return r.paths
