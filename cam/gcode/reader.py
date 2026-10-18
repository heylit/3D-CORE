"""
G-code okuyucu: program metni -> Toolpath listesi.

Yazıcıyla aynı `ModalState`'i kullanır: satırda olmayan kelime durumdan doldurulur.
- Her T kelimesinde veya S değişiminde yeni bir Toolpath başlar; ondan sonraki ilk hareket G0
  olmalıdır ve onun bitişi yolun başlangıcıdır.
- G91 artımsal X Y Z okunur; I, J her zaman başlangıca göre bağıldır (G91.1 varsayılanı).
- Yay R biçimi: h = sqrt(R² − (L/2)²), c = m ± h·n (G2/R>0 sağda, G3/R>0 solda, R<0 tersi).
- Yay doğrulama: |r0 − r1| > arc_tol -> CamError; aksi halde merkez kirişin orta dikmesine
  izdüşürülür: c' = m + ((c − m)·u) u.
- G81/G83 kanonik açılıma çevrilir (cycles.hole_moves).
- G43 H<n> (takım boyu telafisi) yola yansımaz ama denetlenir: H olmadan G43, G43 olmadan H
  veya etkin takımdan farklı H -> CamError (yanlış telafi takımı malzemeye sokar).
Hata mesajları 'satır <n>' içerir (metindeki 1 tabanlı satır sırası).
Kaynak: Smid, CNC Programming Handbook, Bölüm 4–6, 21–22, 29; LinuxCNC G-code referansı.
"""

from __future__ import annotations

import math
import re

from cam.gcode.cycles import hole_moves
from cam.gcode.dialect import GRBL, Dialect
from cam.gcode.modal import CYCLES as CYCLE_KINDS
from cam.gcode.modal import ModalState
from cam.model import R_MIN, CamError, Move, MoveType, Tool, Toolpath

_WORD = re.compile(r"([A-Z])([+-]?(?:\d+\.?\d*|\.\d+))")
_COMMENT = re.compile(r"\([^()]*\)")

LETTERS = set("GMXYZIJRQFSTNOH")
G_MOTION = {0: "G0", 1: "G1", 2: "G2", 3: "G3", 80: "G80", 81: "G81", 83: "G83"}
G_NOOP = {17, 21, 40, 49, 54, 94}           # baş satırda gelen, yola etkisi olmayan kodlar
G_REFUSED = {
    20: "G20 (inç) desteklenmiyor; birim dönüşümü yapılmaz",
    18: "G18 düzlemi desteklenmiyor (sadece G17)",
    19: "G19 düzlemi desteklenmiyor (sadece G17)",
    41: "G41 takım yarıçap telafisi desteklenmiyor",
    42: "G42 takım yarıçap telafisi desteklenmiyor",
}
M_OK = {0, 1, 2, 3, 5, 6, 7, 8, 9, 30}       # M7/M8/M9 kabul edilir, yola yansımaz
ARC_TYPES = {"G2": MoveType.ARC_CW, "G3": MoveType.ARC_CCW}
LINEAR_TYPES = {"G0": MoveType.RAPID, "G1": MoveType.LINEAR}


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
        if letter == "K":
            raise CamError("K kelimesi desteklenmiyor (sadece G17 / XY düzlemi)")
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


class _Reader:
    """Okuma durumu: modal durum, çıkan yollar, açık yol ve 'yeni yol bekleniyor' bayrağı."""

    def __init__(self, tools: dict[int, Tool], dialect: Dialect, arc_tol: float) -> None:
        self.tools = tools
        self.d = dialect
        self.arc_tol = arc_tol
        self.state = ModalState()
        self.paths: list[Toolpath] = []
        self.path: Toolpath | None = None
        self.pending = False

    # --- satır ------------------------------------------------------------------------
    def line(self, gs: list[int], ms: list[int], w: dict[str, float]) -> None:
        motion = self.g_codes(gs)
        self.m_codes(ms)
        self.words(w)
        self.length_offset(43 in gs, w)
        if motion == "G80":
            if any(k in w for k in "XYZIJRQ"):
                raise CamError("G80 satırında eksen / çevrim kelimesi olamaz")
            self.state.end_cycle()
            return
        if motion in CYCLE_KINDS:
            if self.state.distance == "G91":
                raise CamError(f"G91 (artımsal) altında {motion} çevrimi desteklenmiyor")
            if not self.state.in_cycle:
                self.state.cycle_z0 = None       # yeni çevrim: z0 ilk delikte alınır
        elif motion is not None:
            self.state.end_cycle()
        if motion is not None:
            self.state.motion = motion
        self.execute(w)

    def g_codes(self, gs: list[int]) -> str | None:
        """Modal G kodlarını duruma işler; satırdaki hareket kodunu (varsa) döndürür."""
        motion = None
        for g in gs:
            if g in G_MOTION:
                if motion is not None:
                    raise CamError(f"satırda iki hareket kodu: {motion} ve G{g}")
                motion = G_MOTION[g]
            elif g in (90, 91):
                self.state.distance = f"G{g}"
            elif g == 43:
                pass                                 # length_offset() denetler
            elif g in (98, 99):
                self.state.retract = f"G{g}"
            elif g in G_REFUSED:
                raise CamError(G_REFUSED[g])
            elif g not in G_NOOP:
                raise CamError(f"bilinmeyen G kodu G{g}")
        return motion

    def m_codes(self, ms: list[int]) -> None:
        for m in ms:
            if m == 4:
                raise CamError("M4 (ters devir) desteklenmiyor")
            if m not in M_OK:
                raise CamError(f"bilinmeyen M kodu M{m}")

    def words(self, w: dict[str, float]) -> None:
        """F, T, S kelimeleri. T her zaman, S değişince yeni yol bekletir."""
        if "F" in w:
            self.state.feed = w["F"]
        if "T" in w:
            t = w["T"]
            if not t.is_integer() or int(t) not in self.tools:
                raise CamError(f"takım T{t:g} 'tools' sözlüğünde yok")
            self.state.tool = int(t)
            self.pending = True
        if "S" in w and w["S"] != self.state.rpm:
            self.state.rpm = w["S"]
            self.pending = True

    def length_offset(self, g43: bool, w: dict[str, float]) -> None:
        """G43 H<n>: H, etkin takımın numarası olmalı."""
        if g43 != ("H" in w):
            raise CamError("G43 ve H kelimesi birlikte verilmeli")
        if g43 and w["H"] != self.state.tool:
            raise CamError(f"G43 H{w['H']:g}: etkin takım T{self.state.tool} ile uyuşmuyor")

    # --- hareketler -------------------------------------------------------------------
    def execute(self, w: dict[str, float]) -> None:
        """Satırda hareket varsa yürütür (eksen kelimesi, yayda I/J/R, çevrimde X Y Z R Q)."""
        mo = self.state.motion
        if mo in CYCLE_KINDS:
            if any(k in w for k in "IJ"):
                raise CamError("çevrimde I/J kelimesi olamaz")
            if any(k in w for k in "XYZRQ"):
                self.hole(w)
            return
        if "Q" in w:
            raise CamError("Q kelimesi sadece G83 çevriminde geçerli")
        if mo in ARC_TYPES:
            if any(k in w for k in "XYZIJR"):
                self.arc(ARC_TYPES[mo], w)
            return
        if any(k in w for k in "IJR"):
            raise CamError("I/J/R kelimesi sadece yayda (G2/G3) geçerli")
        if any(k in w for k in "XYZ"):
            if mo is None:
                raise CamError("hareket tipi bilinmiyor (G0/G1/G2/G3 yazılmamış)")
            self.add(LINEAR_TYPES[mo], self.target(w))

    def target(self, w: dict[str, float]) -> tuple[float, float, float]:
        """Hedef nokta: G90'da kelime değeri, G91'de konum + kelime; eksik eksen konumdan."""
        pos = self.state.pos
        out = []
        for i, a in enumerate("XYZ"):
            if pos is None and (a not in w or self.state.distance == "G91"):
                raise CamError(f"{a} ekseninin konumu bilinmiyor (ilk hareket üç ekseni vermeli)")
            if a not in w:
                out.append(pos[i])
            elif self.state.distance == "G91":
                out.append(pos[i] + w[a])
            else:
                out.append(w[a])
        return tuple(out)

    def add(self, t: MoveType, end: tuple[float, float, float], center=None) -> None:
        """Hareketi açık yola ekler. T/S sonrası ilk hareket G0 ise yeni yolun başlangıcıdır."""
        if self.pending:
            if t is not MoveType.RAPID:
                raise CamError(f"T/S sonrası ilk hareket G0 olmalı ({t.value} geldi)")
            self.start_path(end)
            return
        if self.path is None:
            if t is not MoveType.RAPID:
                raise CamError(f"{t.value}: takım (T) ve devir (S) tanımlanmadan kesme hareketi")
            self.state.pos = end            # yol öncesi konumlama
            return
        feed = None
        if t is not MoveType.RAPID:
            if self.state.feed is None or self.state.feed <= 0:
                raise CamError(f"{t.value}: ilerleme (F) yok")
            feed = self.state.feed
        self.path.moves.append(Move(t, end, feed, center))
        self.state.pos = end

    def start_path(self, start: tuple[float, float, float]) -> None:
        if self.state.tool is None:
            raise CamError("takım (T) tanımlanmadan yol başlıyor")
        if self.state.rpm is None or self.state.rpm <= 0:
            raise CamError(f"devir (S) pozitif olmalı (S={self.state.rpm})")
        self.path = Toolpath("", self.tools[self.state.tool], start, [], self.state.rpm)
        self.paths.append(self.path)
        self.state.pos = start
        self.pending = False

    # --- yay --------------------------------------------------------------------------
    def arc(self, t: MoveType, w: dict[str, float]) -> None:
        p0 = self.state.pos
        p1 = self.target(w)
        if p0 is None:
            raise CamError("yay başlangıcı bilinmiyor")
        has_ij = "I" in w or "J" in w
        if has_ij and "R" in w:
            raise CamError("yayda hem I/J hem R verilmiş")
        if has_ij:
            c = (p0[0] + w.get("I", 0.0), p0[1] + w.get("J", 0.0))
        elif "R" in w:
            c = self.r_center(t, p0, p1, w["R"])
        else:
            raise CamError(f"{t.value}: yay merkezi yok (I/J veya R gerekli)")
        self.add(t, p1, self.check_arc(p0, p1, c))

    def r_center(self, t: MoveType, p0, p1, R: float) -> tuple[float, float]:
        """R biçimi: kiriş L, orta nokta m, sol normal n; c = m ± h·n, h = sqrt(R² − (L/2)²)."""
        dx, dy = p1[0] - p0[0], p1[1] - p0[1]
        L = math.hypot(dx, dy)
        if L == 0:
            raise CamError("R biçimiyle tam daire tanımsız (I/J kullanın)")
        if abs(R) < L / 2 - self.arc_tol:
            raise CamError(f"|R| = {abs(R)} kiriş yarısından küçük (L/2 = {L / 2})")
        h = math.sqrt(max(R * R - (L / 2) ** 2, 0.0))
        n = (-dy / L, dx / L)                       # kirişin solu (+Z'den bakınca)
        side = 1.0 if t is MoveType.ARC_CCW else -1.0   # G3 solda, G2 sağda (R > 0)
        if R < 0:
            side = -side                             # > 180° yay: taraf tersine
        m = ((p0[0] + p1[0]) / 2, (p0[1] + p1[1]) / 2)
        return (m[0] + side * h * n[0], m[1] + side * h * n[1])

    def check_arc(self, p0, p1, c) -> tuple[float, float]:
        """|r0 − r1| ≤ arc_tol denetimi; merkezi orta dikmeye izdüşürür (tam dairede değil)."""
        r0 = math.hypot(p0[0] - c[0], p0[1] - c[1])
        r1 = math.hypot(p1[0] - c[0], p1[1] - c[1])
        if r0 < R_MIN:
            raise CamError("yay yarıçapı sıfır")
        if abs(r0 - r1) > self.arc_tol:
            raise CamError(f"yay tutmuyor: |r0 − r1| = {abs(r0 - r1):.6g} > arc_tol = {self.arc_tol}")
        dx, dy = p1[0] - p0[0], p1[1] - p0[1]
        L = math.hypot(dx, dy)
        if L == 0:
            return c                                 # tam daire: düzeltme yok
        u = (-dy / L, dx / L)                        # orta dikme yönü
        m = ((p0[0] + p1[0]) / 2, (p0[1] + p1[1]) / 2)
        s = (c[0] - m[0]) * u[0] + (c[1] - m[1]) * u[1]
        return (m[0] + s * u[0], m[1] + s * u[1])

    # --- çevrim -----------------------------------------------------------------------
    def hole(self, w: dict[str, float]) -> None:
        """Çevrimdeki bir delik: kanonik açılım hareketleri açık yola eklenir."""
        st = self.state
        if st.distance == "G91":
            raise CamError(f"G91 (artımsal) altında {st.motion} çevrimi desteklenmiyor")
        if st.pos is None:
            raise CamError("çevrim başında konum bilinmiyor")
        if self.pending or self.path is None:
            raise CamError(f"T/S sonrası ilk hareket G0 olmalı ({st.motion} geldi)")
        st.cycle_z = w.get("Z", st.cycle_z)
        st.cycle_r = w.get("R", st.cycle_r)
        st.cycle_q = w.get("Q", st.cycle_q)
        if st.cycle_z is None or st.cycle_r is None:
            raise CamError(f"{st.motion}: Z veya R verilmemiş")
        if st.motion == "G83" and st.cycle_q is None:
            raise CamError("G83: Q verilmemiş")
        if st.feed is None or st.feed <= 0:
            raise CamError(f"{st.motion}: ilerleme (F) yok")
        if st.cycle_z0 is None:
            st.cycle_z0 = st.pos[2]                  # G98 dönüş düzlemi: çevrimin ilk satırındaki Z
        z, r, z0 = st.cycle_z, st.cycle_r, st.cycle_z0
        if not (z < r <= z0 and r <= st.pos[2]):
            raise CamError(f"{st.motion}: z < r ≤ z0 olmalı (z={z}, r={r}, z0={z0}, Z={st.pos[2]})")
        z_ret = z0 if st.retract == "G98" else r
        x, y = w.get("X", st.pos[0]), w.get("Y", st.pos[1])
        moves = hole_moves(st.motion, st.pos, x, y, z, r, z_ret, st.feed, st.cycle_q,
                           self.d.peck_clearance)
        self.path.moves += moves
        st.pos = (x, y, z_ret)

    def finish(self) -> list[Toolpath]:
        """Yol adları T<n>-<k>; her yol Toolpath.validate()'ten geçer."""
        for k, tp in enumerate(self.paths, start=1):
            tp.name = f"T{tp.tool.id}-{k}"
            tp.validate()
        return self.paths


def read(
    text: str, tools: dict[int, Tool], dialect: Dialect = GRBL, arc_tol: float = 0.005
) -> list[Toolpath]:
    """G-code metnini Toolpath listesine çevirir. Hatalar CamError, mesajda 'satır <n>'."""
    rd = _Reader(tools, dialect, arc_tol)
    for n, raw in enumerate(text.splitlines(), start=1):
        try:
            parsed = _parse(raw)
            if parsed is not None:
                rd.line(*parsed)
        except CamError as e:
            raise CamError(f"satır {n}: {e}") from None
    return rd.finish()
