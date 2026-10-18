"""
Bağımsız referans G-code yorumlayıcısı (çapraz kontrol, inceleme bulgusu Y1).

Neden ayrı: `cam.gcode` yazıcısı ve okuyucusu aynı `ModalState`'i ve aynı `hole_moves` açılımını
paylaşıyor; iki tarafta aynı yorum hatası varsa `read(write(x)) == x` yine geçer. Bu modül
`cam.gcode`'dan HİÇBİR ŞEY import etmez; G-code anlamını doğrudan RS274NGC / LinuxCNC
belgesinden kurar:
    - LinuxCNC G-code referansı (G0–G3, G17, G21, G43, G54, G80–G83, G90/G91, G90.1/G91.1, G98/G99)
    - LinuxCNC "Order of Execution" (aynı satırda: F, S, T, M6, M3/M4/M5, G43/G49, G54, G90/G91,
      G98/G99, hareket, M0/M2/M30 sırası)
    - Smid, CNC Programming Handbook, Bölüm 21–22 (G81/G82/G83/G84 çevrimleri)
    - LinuxCNC G82 (dipte P saniye bekleme), G84 (sağ el kılavuz: dipte iş mili ters, ilerlemeyle
      R'ye dönüş, iş mili ileri), G4 (bekleme). Fanuc `M29 S` (rijit kılavuz modu) bayrak olarak
      kaydedilir (SPEC 04b).

Çıktı: tezgâhın gerçekten yapacağı hareketlerin listesi (`Canon`) ve olaylar (`Event`: takım
değişimi, iş mili, duruş, program sonu). Her hareket o anki makine durumunu (iş mili, devir, takım,
boy telafisi, iş koordinatı) taşır; güvenlik kontrolleri bu durumdan yapılır.

Bilerek basit tutulan noktalar:
    - Sadece G17 (XY) düzlemi, mm (G21), mutlak/artımsal; çevrimler sadece G90 altında.
    - G43 bir bayraktır (H numarası kaydedilir); koordinatlar takım ucuna göre kabul edilir.
    - M6 iş milini durdurur (LinuxCNC ve tipik Fanuc takım değiştirme makrosu böyle).
      GRBL'de M6 yok: `tool_change="M0"` modunda bekleyen T, M0 duruşunda takılır; M0 iş milini
      DURDURMAZ (GRBL 1.1).
    - G83 geri çekilme payı tezgâh parametresidir (LinuxCNC 0.254 mm, bizim diller 0.5 mm);
      `peck_clearance` ile verilir.
    - Bekleme (G82 P, G4 P) hareket değildir: `dwell` olayı olarak, P dilin yazdığı birimde (Fanuc
      milisaniye, LinuxCNC / GRBL / Haas saniye) olduğu gibi kaydedilir.
Bilinmeyen kelime veya kod sessizce atlanmaz: `RefError`.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field

import numpy as np

ZERO_LEN = 1e-9  # mm: bundan kısa hareket yok sayılır (kanonik listede yer almaz)


class RefError(ValueError):
    """Referans yorumlayıcının kabul etmediği G-code (satır numarasıyla)."""


@dataclass
class Canon:
    """Tek bir kanonik hareket ve o anki makine durumu."""

    kind: str  # "rapid" | "feed" | "arc"
    p0: np.ndarray  # başlangıç (x, y, z)
    p1: np.ndarray  # bitiş (x, y, z)
    line: int  # programdaki 1 tabanlı satır
    feed: float | None = None  # mm/dk (rapid'de None)
    center: tuple[float, float] | None = None
    ccw: bool | None = None  # yay yönü: True = G3, False = G2
    turns: int = 0  # P ile istenen ek tam tur
    spindle_on: bool = False
    rpm: float | None = None
    tool: int | None = None  # takılı takım
    tlo: int | None = None  # etkin boy telafisi H numarası (G43), yoksa None
    wcs: str | None = None  # etkin iş koordinatı (G54..G59), seçilmediyse None

    @property
    def length(self) -> float:
        if self.kind != "arc":
            return float(np.linalg.norm(self.p1 - self.p0))
        r, sweep = arc_geometry(self.p0, self.p1, self.center, self.ccw, self.turns)
        return math.hypot(r * sweep, self.p1[2] - self.p0[2])


@dataclass
class Event:
    kind: str  # "tool_change" | "spindle" | "stop" | "end"
    line: int
    pos: np.ndarray | None
    data: dict = field(default_factory=dict)


@dataclass
class Trace:
    moves: list[Canon] = field(default_factory=list)
    events: list[Event] = field(default_factory=list)


def arc_geometry(p0, p1, c, ccw: bool, turns: int = 0) -> tuple[float, float]:
    """Yay yarıçapı r ve süpürme açısı [rad]. XY'de başlangıç = bitiş ise tam daire (2π)."""
    a0 = math.atan2(p0[1] - c[1], p0[0] - c[0])
    a1 = math.atan2(p1[1] - c[1], p1[0] - c[0])
    d = (a1 - a0) if ccw else (a0 - a1)
    d %= 2 * math.pi
    if math.hypot(p1[0] - p0[0], p1[1] - p0[1]) <= ZERO_LEN:
        d = 2 * math.pi
    return math.hypot(p0[0] - c[0], p0[1] - c[1]), d + 2 * math.pi * turns


_TOKEN = re.compile(r"([A-Z])([+-]?(?:\d+(?:\.\d*)?|\.\d+))")
_ALLOWED = set("GMXYZIJRQPFSTNOH")


def _tokens(raw: str) -> list[tuple[str, float]]:
    """Yorumları ( ... ) ve ; sonrası atar; harf + sayı çiftlerini döndürür."""
    s = re.sub(r"\([^)]*\)", "", raw).split(";")[0]
    if "(" in s or ")" in s:
        raise RefError("kapanmamış parantez")
    s = re.sub(r"\s+", "", s).upper()
    if s in ("", "%"):
        return []
    out, i = [], 0
    while i < len(s):
        m = _TOKEN.match(s, i)
        if not m:
            raise RefError(f"çözülemeyen ifade: {s[i:]!r}")
        if m.group(1) not in _ALLOWED:
            raise RefError(f"desteklenmeyen kelime {m.group(0)}")
        out.append((m.group(1), float(m.group(2))))
        i = m.end()
    return out


class RefMachine:
    """Basit 3 eksen dik işleme tezgâhı. `run(text)` -> `Trace`."""

    MOTION = {
        0.0: "G0",
        1.0: "G1",
        2.0: "G2",
        3.0: "G3",
        80.0: "G80",
        81.0: "G81",
        82.0: "G82",
        83.0: "G83",
        84.0: "G84",
    }
    CYCLES = ("G81", "G82", "G83", "G84")

    def __init__(
        self, tool_change: str = "M6", peck_clearance: float = 0.254, arc_tol: float = 0.005
    ) -> None:
        if tool_change not in ("M6", "M0"):
            raise ValueError(tool_change)
        self.tool_change_mode = tool_change
        self.peck_clearance = peck_clearance
        self.arc_tol = arc_tol
        self.pos: list[float | None] = [None, None, None]
        self.motion: str | None = None
        self.absolute = True  # G90
        self.ij_absolute = False  # G90.1 (varsayılan G91.1)
        self.feed: float | None = None
        self.rpm: float | None = None
        self.spindle_on = False
        self.selected: int | None = None  # T ile seçilen
        self.tool: int | None = None  # takılı
        self.tlo: int | None = None
        self.wcs: str | None = None
        self.retract_r = False  # G99
        self.cyc_z = self.cyc_r = self.cyc_q = self.cyc_p = None
        self.rigid_rpm: float | None = None  # son M29 S değeri (Fanuc rijit kılavuz)
        self.cyc_old_z: float | None = None
        self.ended = False
        self.trace = Trace()
        self.n = 0

    # ------------------------------------------------------------------ yardımcılar
    def _p(self) -> np.ndarray | None:
        return None if None in self.pos else np.array(self.pos, dtype=float)

    def _event(self, kind: str, **data) -> None:
        self.trace.events.append(Event(kind, self.n, self._p(), data))

    def _move(self, kind: str, p1, **kw) -> None:
        p0 = self._p()
        p1 = np.asarray(p1, dtype=float)
        if p0 is None:
            # İlk konumlama: başlangıç noktası bilinmediği için hareket kaydı yok, konum öğrenilir
            # (_target eksik eksende zaten RefError verir)
            self.pos = [float(v) for v in p1]
            return
        if kind == "arc" or np.linalg.norm(p1 - p0) > ZERO_LEN:
            self.trace.moves.append(
                Canon(
                    kind,
                    p0,
                    p1,
                    self.n,
                    spindle_on=self.spindle_on,
                    rpm=self.rpm,
                    tool=self.tool,
                    tlo=self.tlo,
                    wcs=self.wcs,
                    **kw,
                )
            )
        self.pos = [float(v) for v in p1]

    def _target(self, w: dict[str, float]) -> list[float]:
        out = []
        for i, a in enumerate("XYZ"):
            cur = self.pos[i]
            if a in w:
                if self.absolute:
                    out.append(w[a])
                elif cur is None:
                    raise RefError(f"G91 altında {a} konumu bilinmiyor")
                else:
                    out.append(cur + w[a])
            elif cur is None:
                raise RefError(f"{a} ekseninin konumu bilinmiyor")
            else:
                out.append(cur)
        return out

    def _need_feed(self) -> float:
        if self.feed is None or self.feed <= 0:
            raise RefError("kesme hareketinde ilerleme (F) yok")
        return self.feed

    # ------------------------------------------------------------------ çalıştırma
    def run(self, text: str) -> Trace:
        for self.n, raw in enumerate(text.splitlines(), start=1):
            try:
                toks = _tokens(raw)
                if toks:
                    self._block(toks)
            except RefError as e:
                raise RefError(f"satır {self.n}: {e}") from None
        return self.trace

    def _block(self, toks: list[tuple[str, float]]) -> None:
        if self.ended:
            raise RefError("program sonundan (M2/M30) sonra satır")
        gs = [v for k, v in toks if k == "G"]
        ms = [v for k, v in toks if k == "M"]
        w: dict[str, float] = {}
        for k, v in toks:
            if k in "GMNO":
                continue
            if k in w:
                raise RefError(f"{k} satırda iki kez")
            w[k] = v
        motion = None
        g43 = g49 = g4 = False
        for g in gs:
            if g == 4:
                g4 = True
            elif g in self.MOTION:
                if motion is not None:
                    raise RefError("satırda iki hareket kodu")
                motion = self.MOTION[g]
            elif g == 90:
                self.absolute = True
            elif g == 91:
                self.absolute = False
            elif g == 90.1:
                self.ij_absolute = True
            elif g == 91.1:
                self.ij_absolute = False
            elif g == 98:
                self.retract_r = False
            elif g == 99:
                self.retract_r = True
            elif g == 43:
                g43 = True
            elif g == 49:
                g49 = True
            elif g in (54, 55, 56, 57, 58, 59):
                self.wcs = f"G{int(g)}"
            elif g in (17, 21, 40, 94):
                pass  # tek desteklenen durumlar
            else:
                raise RefError(f"desteklenmeyen G{g:g}")
        for m in ms:
            if m not in (0, 1, 2, 3, 5, 6, 7, 8, 9, 29, 30):
                raise RefError(f"desteklenmeyen M{m:g}")
        if 4 in ms:
            raise RefError("M4 desteklenmiyor")

        # LinuxCNC yürütme sırası: F, S, T, M6, M3/M5, G43/G49, ..., hareket, M0/M2/M30
        if "F" in w:
            self.feed = w["F"]
        if "S" in w:
            self.rpm = w["S"]
        if "T" in w:
            if not float(w["T"]).is_integer():
                raise RefError("T tam sayı olmalı")
            self.selected = int(w["T"])
            if self.tool_change_mode == "M0" and self.tool is None:
                self.tool = self.selected  # GRBL: ilk takım zaten takılı kabul edilir
        if 6 in ms:
            if self.tool_change_mode != "M6":
                raise RefError("bu kontrolörde M6 yok")
            self._change_tool(implied_stop=True)
        if 3 in ms:
            if not self.rpm:
                raise RefError("M3: devir (S) yok")
            self.spindle_on = True
            self._event("spindle", on=True, rpm=self.rpm)
        if 5 in ms:
            self.spindle_on = False
            self._event("spindle", on=False)
        if 29 in ms:
            if "S" not in w:
                raise RefError("M29 için S gerekli")
            self.rigid_rpm = w["S"]
            self._event("rigid_tap", rpm=w["S"])
        if g49:
            self.tlo = None
        if g43:
            if "H" not in w:
                raise RefError("G43 için H gerekli")
            self.tlo = int(w["H"])
        elif "H" in w:
            raise RefError("G43 olmadan H")

        if g4:
            if motion is not None or any(k in w for k in "XYZIJRQ"):
                raise RefError("G4 satırında hareket kelimesi")
            if "P" not in w or w["P"] < 0:
                raise RefError("G4: P (bekleme) gerekli")
            self._event("dwell", p=w["P"])
        elif motion == "G80":
            if any(k in w for k in "XYZRQ"):
                raise RefError("G80 satırında eksen kelimesi")
            self.motion = None
            self.cyc_old_z = None
        elif motion is not None:
            if motion not in self.CYCLES or self.motion not in self.CYCLES:
                self.cyc_old_z = None  # yeni çevrim (veya çevrim iptali)
            self.motion = motion
        if not g4:
            self._motion(w)

        if 0 in ms or 1 in ms:
            self._event("stop")
            if self.tool_change_mode == "M0" and self.selected is not None and self.selected != self.tool:
                self._change_tool(implied_stop=False)
        if 2 in ms or 30 in ms:
            self.spindle_on = False
            self._event("end")
            self.ended = True

    def _change_tool(self, implied_stop: bool) -> None:
        if self.selected is None:
            raise RefError("takım değişimi: T seçilmemiş")
        self._event(
            "tool_change",
            old=self.tool,
            new=self.selected,
            spindle_on=self.spindle_on,
            implied_stop=implied_stop,
        )
        self.tool = self.selected
        if implied_stop:
            self.spindle_on = False

    # ------------------------------------------------------------------ hareketler
    def _motion(self, w: dict[str, float]) -> None:
        mo = self.motion
        if mo in self.CYCLES:
            if any(k in w for k in "IJ") or ("P" in w and mo != "G82"):
                raise RefError("çevrimde I/J/P")
            if "Q" in w and mo in ("G82", "G84"):
                raise RefError(f"{mo}: Q yok (gagalı kılavuz / gagalı bekleme kapsam dışı)")
            if any(k in w for k in "XYZR"):
                self._cycle(w)
            return
        if "Q" in w:
            raise RefError("Q sadece G83'te")
        if mo in ("G2", "G3"):
            if any(k in w for k in "XYZIJR"):
                self._arc(w, ccw=(mo == "G3"))
            return
        if any(k in w for k in "IJRP"):
            raise RefError("I/J/R/P sadece yayda")
        if any(k in w for k in "XYZ"):
            if mo is None:
                raise RefError("hareket kodu yok")
            if mo == "G0":
                self._move("rapid", self._target(w))
            else:
                self._move("feed", self._target(w), feed=self._need_feed())

    def _arc(self, w: dict[str, float], ccw: bool) -> None:
        p0 = self._p()
        if p0 is None:
            raise RefError("yay başlangıcı bilinmiyor")
        p1 = self._target(w)
        if "R" in w and ("I" in w or "J" in w):
            raise RefError("yayda hem R hem I/J")
        if "R" in w:
            c = self._r_center(p0, p1, w["R"], ccw)
        elif "I" in w or "J" in w:
            if self.ij_absolute:
                c = (w.get("I", p0[0]), w.get("J", p0[1]))
            else:
                c = (p0[0] + w.get("I", 0.0), p0[1] + w.get("J", 0.0))
        else:
            raise RefError("yay merkezi yok")
        r0 = math.hypot(p0[0] - c[0], p0[1] - c[1])
        r1 = math.hypot(p1[0] - c[0], p1[1] - c[1])
        if r0 <= ZERO_LEN:
            raise RefError("yay yarıçapı sıfır")
        if abs(r0 - r1) > self.arc_tol:
            raise RefError(f"yay yarıçapları tutmuyor: r0={r0:.6f}, r1={r1:.6f}")
        turns = 0
        if "P" in w:
            if not w["P"].is_integer() or w["P"] < 1:
                raise RefError("P pozitif tam sayı olmalı")
            turns = int(w["P"]) - 1
        self._move("arc", p1, feed=self._need_feed(), center=(float(c[0]), float(c[1])), ccw=ccw, turns=turns)

    @staticmethod
    def _r_center(p0, p1, R: float, ccw: bool) -> tuple[float, float]:
        """R biçimi (LinuxCNC): R > 0 → ≤ 180° yay, R < 0 → > 180° yay."""
        dx, dy = p1[0] - p0[0], p1[1] - p0[1]
        L = math.hypot(dx, dy)
        if L <= ZERO_LEN:
            raise RefError("R biçimiyle tam daire olmaz")
        if abs(R) < L / 2 - 1e-9:
            raise RefError("R kirişin yarısından küçük")
        h = math.sqrt(max(R * R - L * L / 4, 0.0))
        # Kirişin solundaki birim normal; G3'te merkez solda (R > 0), G2'de sağda
        nx, ny = -dy / L, dx / L
        s = h if ccw else -h
        if R < 0:
            s = -s
        return ((p0[0] + p1[0]) / 2 + s * nx, (p0[1] + p1[1]) / 2 + s * ny)

    def _cycle(self, w: dict[str, float]) -> None:
        """G81/G82/G83/G84, LinuxCNC tanımı (sadece G90)."""
        if not self.absolute:
            raise RefError("çevrim G91 altında desteklenmiyor")
        p = self._p()
        if p is None:
            raise RefError("çevrim başında konum bilinmiyor")
        self.cyc_z = w.get("Z", self.cyc_z)
        self.cyc_r = w.get("R", self.cyc_r)
        if self.motion == "G83":
            self.cyc_q = w.get("Q", self.cyc_q)
            if self.cyc_q is None or self.cyc_q <= 0:
                raise RefError("G83: Q pozitif olmalı")
        if self.motion == "G82":
            self.cyc_p = w.get("P", self.cyc_p)
            if self.cyc_p is None or self.cyc_p < 0:
                raise RefError("G82: P (bekleme) gerekli")
        if self.motion == "G84" and not self.spindle_on:
            raise RefError("G84: iş mili dönmüyor")
        if self.cyc_z is None or self.cyc_r is None:
            raise RefError("çevrimde Z veya R yok")
        z, r = self.cyc_z, self.cyc_r
        if z >= r:
            raise RefError("çevrim: dip Z, R düzleminin altında olmalı")
        feed = self._need_feed()
        if self.cyc_old_z is None:
            self.cyc_old_z = p[2]  # G98 dönüş yüksekliği: çevrimden önceki Z
        x, y = w.get("X", p[0]), w.get("Y", p[1])
        # Ön hareket: Z, R'nin altındaysa önce R'ye; sonra XY; sonra R'ye
        if p[2] < r:
            self._move("rapid", (p[0], p[1], r))
        self._move("rapid", (x, y, self.pos[2]))
        self._move("rapid", (x, y, r))
        if self.motion == "G81":
            self._move("feed", (x, y, z), feed=feed)
        elif self.motion == "G82":
            self._move("feed", (x, y, z), feed=feed)
            self._event("dwell", p=self.cyc_p)
        elif self.motion == "G84":
            # LinuxCNC G84: dipte iş mili ters döner, aynı ilerlemeyle R'ye çıkılır, iş mili ileri döner
            self._move("feed", (x, y, z), feed=feed)
            self._event("spindle_reverse")
            self._move("feed", (x, y, r), feed=feed)
            self._event("spindle_forward")
        else:
            depth = r
            while depth > z:
                nxt = max(depth - self.cyc_q, z)
                if depth < r:
                    self._move("rapid", (x, y, depth + self.peck_clearance))
                self._move("feed", (x, y, nxt), feed=feed)
                self._move("rapid", (x, y, r))
                depth = nxt
        clear = r if self.retract_r else max(self.cyc_old_z, r)
        self._move("rapid", (x, y, clear))


def run(text: str, **kw) -> Trace:
    """Kısayol: `RefMachine(**kw).run(text)`."""
    return RefMachine(**kw).run(text)
