"""
SPEC 49 — Torna-freze postu: C ekseni aç / kapat ve indeks, canlı takım devri, polar ve silindirik
dönüşüm blokları.

| İşlev | Sinumerik 840D sl | Fanuc / MAPPS |
|---|---|---|
| C ekseni | SPOS=0 / CAxis.m_on, m_off | CAxis.m_on (M45), m_off (M46) |
| C indeks | SPOS=DC(C) | G0 C |
| Canlı takım | SETMS(2) … M2=3 S2=n, M2=5, SETMS | M13 S n … M15 |
| Polar | TRANSMIT … TRAFOOF | G12.1 … G13.1 (X çap, C sanal eksen mm) |
| Silindirik | TRACYL(2·r_ref) … TRAFOOF (Y = s) | G7.1 C r_ref … G7.1 C0 (C = s mm) |

Eksen kuralları: Fanuc'ta X her zaman çap (2·x), Sinumerik programı DIAMOF ile yarıçap yazar. Yay merkezi
başlangıca göre bağıl (I yarıçap; XY'de J, ZX'te K). Her yol bir `OP` yorumuyla başlar; yorum takımı ve
istasyonu taşır, okuyucu yolları bundan kurar. Torna yolları G18 ve dakikada / devirde ilerlemeyle aynı
programda yazılır (G0 / G1 / G2 / G3; çevrim yok). Fanuc / MAPPS M kodları (M13 / M15) taslaktır (Karar 1).
"""

from __future__ import annotations

import math
import re

import numpy as np

from cam.gcode.modal import fmt
from cam.millturn.indeks import _mod360, index_angle
from cam.millturn.istasyon import RADYAL_EKSEN, check_ops, station
from cam.model import (
    ARCS,
    CamError,
    FeedMode,
    LatheTool,
    LatheToolKind,
    MachineProfile,
    Move,
    MoveType,
    Plane,
    Setup,
    Tool,
    ToolKind,
    Toolpath,
)
from cam.post.format_sinumerik import sayi

UYARI = "DOGRULANMAMIS PROFIL - ILK PARCADA KURU CALISTIRIN"
_TIP = {MoveType.RAPID: "G0", MoveType.LINEAR: "G1", MoveType.ARC_CW: "G2", MoveType.ARC_CCW: "G3"}
_GTIP = {0: MoveType.RAPID, 1: MoveType.LINEAR, 2: MoveType.ARC_CW, 3: MoveType.ARC_CCW}


# ---------------------------------------------------------------- takım yorumu


def _ad(s: str) -> str:
    return re.sub(r"[^A-Za-z0-9_]", "_", s) or "_"


def _tool_comment(i: int, tp: Toolpath) -> str:
    """OP <i> <ad> ST=<istasyon> T=<id> <takım alanları> (okuyucu yolu bundan kurar)."""
    t = tp.tool
    st = 0 if tp.station is None else tp.station
    bas = f"OP {i} {_ad(tp.name)} ST={st} T={t.id}"
    if isinstance(t, LatheTool):
        alan = (
            f"TORNA K={t.kind.name} R={t.nose_r!r} TIP={t.tip} KR={t.kappa_r!r} ER={t.eps_r!r} W={t.width!r}"
        )
        if t.edge_len is not None:
            alan += f" EL={t.edge_len!r}"
        return f"{bas} {alan}"
    alan = (
        f"FREZE K={t.kind.name} D={t.D!r} L={t.flute_length!r} CR={t.corner_r!r} CC={int(t.center_cutting)}"
    )
    for ad, v in (("TA", t.tip_angle), ("TD", t.tip_d or None), ("P", t.pitch), ("LD", t.lead)):
        if v is not None:
            alan += f" {ad}={v!r}"
    return f"{bas} {alan}"


def _tool_from(alan: dict[str, str]):
    try:
        tid = int(alan["T"])
        if "TORNA" in alan:
            return LatheTool(
                tid,
                f"T{tid}",
                LatheToolKind[alan["K"]],
                float(alan["R"]),
                int(alan["TIP"]),
                float(alan["KR"]),
                float(alan["ER"]),
                width=float(alan["W"]),
                edge_len=float(alan["EL"]) if "EL" in alan else None,
            )
        kw = {}
        for ad, isim, tur in (("TA", "tip_angle", float), ("TD", "tip_d", float), ("P", "pitch", float)):
            if ad in alan:
                kw[isim] = tur(alan[ad])
        if "LD" in alan:
            kw["lead"] = float(alan["LD"])
        return Tool(
            tid,
            f"T{tid}",
            ToolKind[alan["K"]],
            float(alan["D"]),
            float(alan["L"]),
            corner_r=float(alan["CR"]),
            center_cutting=alan.get("CC", "1") == "1",
            **kw,
        )
    except (KeyError, ValueError) as e:
        raise CamError(f"OP yorumunda takım bilgisi eksik / bozuk ({e})") from e


# ---------------------------------------------------------------- yazıcı


class _Yazici:
    def __init__(self, machine: MachineProfile, spindle: str, tool_change) -> None:
        self.m = machine
        self.sin = machine.controller == "sinumerik"
        self.d = machine.decimals
        self.spindle = spindle
        self.tc = tool_change
        self.lines: list[str] = []
        self.c_mode = False

    def n(self, v: float) -> str:
        return sayi(v, self.d) if self.sin else fmt(v, self.d)

    def emit(self, *words: str) -> None:
        self.lines.append(" ".join(w for w in words if w))

    def comment(self, s: str) -> None:
        self.emit(f"; {s}" if self.sin else f"({s.replace('(', '[').replace(')', ']')})")

    # -- C ekseni
    def c_on(self) -> None:
        if self.c_mode:
            return
        ca = self.m.c_axis
        if self.sin:
            self.emit("SPOS=0")
        if ca.m_on:
            self.emit(ca.m_on)
        self.c_mode = True

    def c_off(self) -> None:
        if not self.c_mode:
            return
        if self.m.c_axis.m_off:
            self.emit(self.m.c_axis.m_off)
        self.c_mode = False

    def c_index(self, c: float) -> None:
        if self.sin:
            self.emit(f"SPOS=DC({self.n(_mod360(c))})")
        else:
            self.emit("G0", f"C{self.n(c)}")

    # -- koordinatlar
    def axes(self, tp: Toolpath, p) -> list[str]:
        x, y, z = (float(v) for v in p)
        X = (lambda v: f"X{self.n(v)}") if self.sin else (lambda v: f"X{self.n(2 * v)}")
        if isinstance(tp.tool, LatheTool):
            return [X(x), f"Z{self.n(z)}"]
        if tp.coord == "polar":
            return [X(x), f"Y{self.n(y)}" if self.sin else f"C{self.n(y)}", f"Z{self.n(z)}"]
        if tp.coord == "silindirik":  # (s, z, r)
            return [X(z), f"Y{self.n(x)}" if self.sin else f"C{self.n(x)}", f"Z{self.n(y)}"]
        return [X(x), f"Y{self.n(y)}", f"Z{self.n(z)}"]

    def center(self, tp: Toolpath, p0, m: Move) -> list[str]:
        cx, cy = m.center
        if isinstance(tp.tool, LatheTool):  # ZX: merkez (x, z)
            return [f"I{self.n(cx - p0[0])}", f"K{self.n(cy - p0[2])}"]
        return [f"I{self.n(cx - p0[0])}", f"J{self.n(cy - p0[1])}"]

    # -- yol
    def toolpath(self, i: int, tp: Toolpath) -> None:
        live = isinstance(tp.tool, Tool)
        self.comment(_tool_comment(i, tp))
        if self.tc is not None:
            xt, zt = self.tc
            X = f"X{self.n(xt)}" if self.sin else f"X{self.n(2 * xt)}"
            self.emit("G0", X, f"Z{self.n(zt)}")
        if live:
            self.c_on()
        else:
            self.c_off()
        st = tp.station if tp.station is not None else tp.tool.id
        self.emit(f"T{st} D1" if self.sin else f"T{st:02d}{st:02d}")
        dakika = tp.feed_mode is FeedMode.PER_MIN
        if live:
            self.emit("G17", ("G94" if self.sin else "G98") if dakika else ("G95" if self.sin else "G99"))
            rpm = round(tp.rpm)
            if self.sin:
                self.emit("SETMS(2)")
                self.emit(f"M2=3 S2={rpm}")
            else:
                self.emit("M13", f"S{rpm}")
        else:
            self.emit("G18", ("G94" if self.sin else "G98") if dakika else ("G95" if self.sin else "G99"))
            if tp.css is None:
                self.emit("G97", f"S{round(tp.rpm)}", self.spindle)
            else:
                self.emit(f"LIMS={round(tp.rpm)}" if self.sin else f"G50 S{round(tp.rpm)}")
                self.emit("G96", f"S{round(tp.css)}", self.spindle)
        if tp.coord == "polar":
            self.emit("TRANSMIT" if self.sin else "G12.1")
        elif tp.coord == "silindirik":
            r = float(tp.cyl_r)
            self.emit(f"TRACYL({self.n(2 * r)})" if self.sin else f"G7.1 C{self.n(r)}")
        c = None
        cs = [m.c for m in tp.moves if m.c is not None]
        if live and tp.coord == "kartezyen" and cs:
            r_max = float(np.max(np.hypot(tp.points()[:, 0], tp.points()[:, 1])))
            c = self._c(cs[0], r_max)
            self.c_index(c)
        self.emit("G0", *self.axes(tp, tp.start))
        p0 = np.array(tp.start, dtype=float)
        for m in tp.moves:
            if c is not None and m.c is not None and m.c != c:
                c = self._c(m.c, r_max)
                self.c_index(c)
            words = [_TIP[m.type], *self.axes(tp, m.end)]
            if m.type in ARCS:
                words += self.center(tp, p0, m)
            if m.type is not MoveType.RAPID:
                words.append(f"F{self.n(m.feed)}")
            self.emit(*words)
            p0 = np.array(m.end, dtype=float)
        if tp.coord == "polar":
            self.emit("TRAFOOF" if self.sin else "G13.1")
        elif tp.coord == "silindirik":
            self.emit("TRAFOOF" if self.sin else "G7.1 C0")
        if live:
            if self.sin:
                self.emit("M2=5")
                self.emit("SETMS")
            else:
                self.emit("M15")

    def _c(self, c: float, r: float) -> float:
        return index_angle(c, self.m.c_axis, r)


def post_mt(
    ops: list[Toolpath],
    machine: MachineProfile,
    setup: Setup | None = None,
    program_no: int = 1,
    spindle: str = "M3",
    tool_change: tuple[float, float] | None = None,
) -> str:
    """Torna + canlı takım programı; machine.kind != "millturn" → CamError."""
    check_ops(ops, machine)
    if spindle not in ("M3", "M4"):
        raise CamError(f"İş mili yönü 'M3' veya 'M4' olmalı ({spindle!r})")
    lo, hi = machine.program_no_range
    if isinstance(program_no, bool) or not isinstance(program_no, int) or not lo <= program_no <= hi:
        raise CamError(f"Program no {lo}..{hi} aralığında tam sayı olmalı ({program_no!r})")
    if tool_change is not None:
        tool_change = tuple(float(v) for v in tool_change)
        if len(tool_change) != 2 or not all(math.isfinite(v) for v in tool_change):
            raise CamError(f"Takım değiştirme noktası (x, z) sonlu olmalı ({tool_change})")
    w = _Yazici(machine, spindle, tool_change)
    wcs = "G54" if setup is None else setup.wcs.code
    if not w.sin:
        w.emit("%")
        w.emit(f"O{program_no:04d}")
    w.comment(f"POST {machine.name} {machine.controller.upper()}")
    if not machine.verified:
        w.comment(UYARI)
    w.emit("G71 G40 DIAMOF" if w.sin else "G21 G40 G80")
    w.emit(wcs)
    for i, tp in enumerate(ops):
        w.toolpath(i, tp)
    w.c_off()
    w.emit("M30")
    if not w.sin:
        w.emit("%")
    return "\n".join(w.lines) + "\n"


# ---------------------------------------------------------------- okuyucu

_SAYI = r"[+-]?(?:\d+\.?\d*|\.\d+)"
_KELIME = re.compile(r"([A-Z])\s*(" + _SAYI + ")")
_ATAMA = re.compile(r"\b(SPOS|S2|M2|LIMS)\s*=\s*(DC\(\s*(" + _SAYI + r")\s*\)|" + _SAYI + ")")


class _Okuyucu:
    def __init__(self, machine: MachineProfile) -> None:
        self.m = machine
        self.sin = machine.controller == "sinumerik"
        self.paths: list[Toolpath] = []
        self.op: dict | None = None
        self.mode = "kartezyen"
        self.cyl_r: float | None = None
        self.motion = MoveType.RAPID
        self.feed: float | None = None
        self.c: float | None = None
        self.pos = {"X": None, "Y": 0.0, "Z": None, "C": 0.0}
        self.rpm: float | None = None
        self.css: float | None = None
        self.feed_mode = FeedMode.PER_MIN

    def _bitir(self) -> None:
        op = self.op
        self.op = None
        if op is None or op["start"] is None:
            return
        torna = isinstance(op["tool"], LatheTool)
        tp = Toolpath(
            op["name"],
            op["tool"],
            op["start"],
            op["moves"],
            rpm=op["rpm"] if op["rpm"] is not None else 0.0,
            plane=Plane.ZX if torna else Plane.XY,
            feed_mode=op["feed_mode"],
            css=op["css"],
            coord=op["coord"],
            cyl_r=op["cyl_r"],
            station=op["station"],
        )
        tp.validate()
        self.paths.append(tp)

    def _yeni(self, text: str) -> None:
        self._bitir()
        parca = text.split()
        alan = {}
        for p in parca[3:]:
            if "=" in p:
                k, v = p.split("=", 1)
                alan[k] = v
            else:
                alan[p] = ""
        tool = _tool_from(alan)
        st = int(alan.get("ST", "0")) or None
        radyal = False
        if st is not None and isinstance(tool, Tool):
            radyal = station(self.m, st)[0].direction == "radyal"
        self.op = {
            "name": parca[2] if len(parca) > 2 else f"op{len(self.paths)}",
            "tool": tool,
            "station": st,
            "radyal": radyal,
            "start": None,
            "moves": [],
            "rpm": None,
            "css": None,
            "coord": "kartezyen",
            "cyl_r": None,
            "feed_mode": FeedMode.PER_MIN,
            "c_set": False,
            "t_seen": False,
        }
        self.c = None

    def _nokta(self, X: float, Y: float, Z: float, C: float) -> tuple[float, float, float]:
        x = X if self.sin else X / 2
        if isinstance(self.op["tool"], LatheTool):
            return (x, 0.0, Z)
        if self.mode == "polar":
            return (x, Y if self.sin else C, Z)
        if self.mode == "silindirik":
            return (Y if self.sin else C, Z, x)
        return (x, Y, Z)

    def line(self, raw: str) -> None:
        if self.sin:
            i = raw.find(";")
            yorum, kod = (raw[i + 1 :].strip(), raw[:i]) if i >= 0 else ("", raw)
        else:
            yorumlar = re.findall(r"\(([^()]*)\)", raw)
            yorum = yorumlar[0].strip() if yorumlar else ""
            kod = re.sub(r"\([^()]*\)", " ", raw)
        if yorum.startswith("OP "):
            self._yeni(yorum)
        kod = kod.strip().upper()
        if not kod or kod == "%":
            return
        op = self.op
        # Sinumerik atamaları ve dönüşümleri
        for ad, deger, dc in _ATAMA.findall(kod):
            v = float(dc if dc else deger)
            if ad == "SPOS":
                self.c = v
                if dc and op is not None:
                    op["c_set"] = True
            elif ad == "S2" and op is not None:
                op["rpm"] = v
            elif ad == "LIMS" and op is not None:
                op["rpm"] = v
        kod = _ATAMA.sub(" ", kod)
        if "TRANSMIT" in kod:
            self.mode = "polar"
            return
        m = re.search(r"TRACYL\(\s*(" + _SAYI + r")\s*\)", kod)
        if m:
            self.mode, self.cyl_r = "silindirik", float(m.group(1)) / 2
            return
        if "TRAFOOF" in kod:
            self.mode, self.cyl_r = "kartezyen", None
            return
        if re.fullmatch(r"SETMS(\(\s*\d+\s*\))?|G71 G40 DIAMOF", kod.strip()):
            return
        words: dict[str, list[float]] = {}
        for k, v in _KELIME.findall(kod):
            words.setdefault(k, []).append(float(v))
        gs = words.get("G", [])
        if 12.1 in gs:
            self.mode = "polar"
            return
        if 13.1 in gs:
            self.mode = "kartezyen"
            return
        if 7.1 in gs:
            r = words.get("C", [0.0])[0]
            self.mode, self.cyl_r = ("silindirik", r) if r > 0 else ("kartezyen", None)
            return
        if op is None:
            return
        if "T" in words:
            op["t_seen"] = True
        for g in gs:
            if g in _GTIP:
                self.motion = _GTIP[g]
            elif g in (94, 98):
                op["feed_mode"] = FeedMode.PER_MIN
            elif g in (95, 99):
                op["feed_mode"] = FeedMode.PER_REV
            elif g == 97:
                op["css"] = None
                op["rpm"] = words.get("S", [op["rpm"]])[0]
            elif g == 96:
                op["css"] = words.get("S", [None])[0]
            elif g == 50:
                op["rpm"] = words.get("S", [op["rpm"]])[0]
        ms = words.get("M", [])
        if 13 in ms and "S" in words:
            op["rpm"] = words["S"][0]
        if "F" in words:
            self.feed = words["F"][0]
        eksen = {"X", "Y", "Z"} if (self.sin or self.mode == "kartezyen") else {"X", "C", "Z"}
        if not self.sin and self.mode == "kartezyen" and "C" in words and not (eksen & words.keys()):
            self.c = words["C"][0]  # G0 C: indeks
            op["c_set"] = True
            return
        if not (eksen & words.keys()) or not op["t_seen"]:
            return  # takım seçilmeden önceki hareket (takım değiştirme noktası) yola yazılmaz
        for k in ("X", "Y", "Z", "C"):
            if k in words and k in eksen:
                self.pos[k] = words[k][0]
        if self.pos["X"] is None or self.pos["Z"] is None:
            raise CamError("Torna-freze okuyucu: ilk konumda X ve Z yazılmalı")
        p = self._nokta(self.pos["X"], self.pos["Y"], self.pos["Z"], self.pos["C"])
        if op["start"] is None:
            op["start"] = p
            op["coord"], op["cyl_r"] = self.mode, self.cyl_r
            return
        moves = op["moves"]
        p0 = moves[-1].end if moves else op["start"]
        center = None
        if self.motion in ARCS:
            di = words.get("I", [0.0])[0]
            if isinstance(op["tool"], LatheTool):
                center = (p0[0] + di, p0[2] + words.get("K", [0.0])[0])
            else:
                center = (p0[0] + di, p0[1] + words.get("J", [0.0])[0])
        live_k = isinstance(op["tool"], Tool) and self.mode == "kartezyen"
        moves.append(
            Move(
                self.motion,
                p,
                feed=None if self.motion is MoveType.RAPID else self.feed,
                center=center,
                axis=RADYAL_EKSEN if live_k and op["radyal"] else None,
                c=self.c if live_k and op["c_set"] else None,
            )
        )

    def end(self) -> list[Toolpath]:
        self._bitir()
        return self.paths


def read_mt(text: str, machine: MachineProfile) -> list[Toolpath]:
    """post_mt çıktısını parça çerçevesinde yollara geri okur (gidiş-dönüş, yazılan ondalığa göre)."""
    if not isinstance(machine, MachineProfile) or machine.kind != "millturn":
        raise CamError("read_mt: torna-freze profili gerekli")
    r = _Okuyucu(machine)
    for n, raw in enumerate(text.splitlines(), start=1):
        try:
            r.line(raw)
        except CamError as e:
            raise CamError(f"satır {n}: {e}") from e
    return r.end()
