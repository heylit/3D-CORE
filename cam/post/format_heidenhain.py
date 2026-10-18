"""
Heidenhain TNC 640 / 620 / 530 Klartext biçimleyicisi (SPEC 31).

`plan()`'ın bloklarını biçimler; karar vermez.
- Blok numarası 0'dan ardışık; `0 BEGIN PGM <ad> MM` … `<n> END PGM <ad> MM`.
- `L X+10 Y-2.5 R0 F300`: işaretli sayı, sondaki sıfırlar atılır; her `L`'de `R0`; yalnız değişen eksenler.
- `FMAX` yalnız o blokta geçerli; kesme `F`'si modaldır (FMAX'tan sonra tekrar yazılmaz).
- Yay: `CC X Y` (her yayda) sonra `C X Y DR± R0 F`; helis `CP IPA±<derece, 4 ondalık> IZ±<dz> DR± R0 F`.
- Takım `TOOL CALL n Z S<rpm>`; `M3` ilk hareket bloğunda, `M5` geri çekme bloğunda.
- İş sıfırı: `presets` eşlemesiyle `CYCL DEF 247 DATUM SETTING ~ Q339=+<n>`; eşleme yoksa CamError.
- Makine Z'si (`tool_change_z`): `L Z+<v> R0 FMAX M91`. Program sonu `L Z+<safe_z> R0 FMAX M30`.
Delik op'ları kanonik açılımla. Kaynak: HEIDENHAIN TNC 640 Klartext User's Manual (ID 892903).
"""

from __future__ import annotations

import math

from cam.gcode.dialect import Dialect
from cam.gcode.modal import fmt, snap
from cam.model import CamError
from cam.post.blocks import (
    Arc,
    Block,
    Comment,
    End,
    Linear,
    MachineZ,
    Rapid,
    Spindle,
    Start,
    ToolChange,
)

__all__ = ["HEIDENHAIN", "format_heidenhain"]

HEIDENHAIN = Dialect(
    name="Heidenhain",
    decimals=3,
    feed_decimals=1,
    line_numbers=False,
    line_step=1,
    header=(),
    footer=(),
    tool_change="M6",
    canned_cycles=False,
    peck_clearance=0.5,
)

IPA_DECIMALS = 4  # helis açısı ondalığı (derece)
CC_DECIMALS = 4  # helis (CP) merkezi ondalığı: TNC giriş çözünürlüğü 0.1 µm (doğrulanmalı)
CC_ARAMA = 2  # orta dikmedeki merkezin çevresinde ±2 ızgara basamağı


def sayi(v: float, decimals: int) -> str:
    """İşaretli, noktasız sayı: 10 → '+10', -2.5 → '-2.5', 0 → '+0'."""
    s = fmt(v, decimals).rstrip(".")
    return s if s.startswith("-") else "+" + s


def dondur(p, c, derece: float) -> tuple[float, float]:
    """`p` noktasını `c` merkezi çevresinde `derece` kadar döndürür (okuyucunun CP hesabı)."""
    a = math.radians(derece)
    dx, dy = p[0] - c[0], p[1] - c[1]
    return (c[0] + dx * math.cos(a) - dy * math.sin(a), c[1] + dx * math.sin(a) + dy * math.cos(a))


def _ipa(S, E, c, ccw: bool) -> float:
    """S'den E'ye `c` çevresinde süpürme [derece], 4 ondalık: DR+ için (0, 360], DR- için [−360, 0)."""
    a = math.degrees(math.atan2(E[1] - c[1], E[0] - c[0]) - math.atan2(S[1] - c[1], S[0] - c[0]))
    a = a % 360.0 if ccw else -((-a) % 360.0)
    a = round(a, IPA_DECIMALS)
    if a == 0.0:
        a = 360.0 if ccw else -360.0
    return a


def helis(S, T, c0, ccw: bool, decimals: int) -> tuple[tuple[float, float], float]:
    """Kısmi helis için (CC, IPA): S tezgâhın gerçek başlangıcı, T model bitişi, c0 yuvarlanmış merkez.

    `CP` bitişi yazılmaz, S'nin CC çevresinde IPA kadar dönmesidir; S ve c0'dan geçen çember T'den
    1.4·10⁻³ mm'ye kadar uzak geçebilir. CC, S ile T'nin orta dikmesine c0'ın izdüşümüdür (|CC − S| =
    |CC − T|); `CC_DECIMALS` ondalığa yuvarlanır ve çevresindeki ±2 ızgara noktasından okunan bitişi
    T'ye en yakın yapan seçilir. Yarıçap farkı ≤ 2·0.7·10⁻⁴ mm kalır (3 ondalıklı ızgarada eksene paralel
    kirişte 10⁻³'e çıkardı). c0 tutuyorsa (hata ≤ 10⁻⁹) c0 yazılır."""

    def hata(c):
        a = _ipa(S, T, c, ccw)
        p = dondur(S, c, a)
        return max(abs(p[0] - T[0]), abs(p[1] - T[1])), a

    e0, a0 = hata(c0)
    if e0 <= 1e-9:
        return c0, a0
    m = ((S[0] + T[0]) / 2, (S[1] + T[1]) / 2)
    d = (T[0] - S[0], T[1] - S[1])
    k = ((c0[0] - m[0]) * d[0] + (c0[1] - m[1]) * d[1]) / (d[0] ** 2 + d[1] ** 2)
    cs = (c0[0] - k * d[0], c0[1] - k * d[1])
    dec = max(decimals, CC_DECIMALS)
    h = 10.0**-dec
    best = (e0, c0, a0)
    for i in range(-CC_ARAMA, CC_ARAMA + 1):
        for j in range(-CC_ARAMA, CC_ARAMA + 1):
            c = (snap(cs[0] + i * h, dec), snap(cs[1] + j * h, dec))
            e, a = hata(c)
            if e < best[0]:
                best = (e, c, a)
    return best[1], best[2]


class _HeidenhainFormatter:
    def __init__(self, presets: dict[str, int], d: Dialect, program_name: str) -> None:
        self.presets = presets
        self.d = d
        self.ad = program_name
        self.lines: list[list[str]] = []
        self.pos: list[float] | None = None  # planın (yazılan) konumu
        self.gercek: list[float] | None = None  # tezgâhın konumu: CP'den sonra pos'tan biraz farklı
        self.preset: int | None = None  # yorumlardan sonra yazılacak ön ayar
        self.tool: int | None = None  # TOOL CALL bekleyen takım (devir Spindle'dan)
        self.m3 = False  # ilk hareket bloğuna M3
        self.son_hareket: int | None = None  # M5 / M30 eklenecek son hareket satırı

    def c(self, v: float) -> str:
        return sayi(v, self.d.decimals)

    def emit(self, words: list[str]) -> None:
        self.lines.append(words)

    def hareket(self, words: list[str]) -> None:
        if self.m3:
            words.append("M3")
            self.m3 = False
        self.emit(words)
        self.son_hareket = len(self.lines) - 1

    def m_ekle(self, m: str) -> None:
        if self.son_hareket is None:
            raise CamError(f"Heidenhain: {m} eklenecek hareket bloğu yok")
        self.lines[self.son_hareket].append(m)

    def axes(self, b) -> list[str]:
        out = []
        for a in "xyz":
            v = getattr(b, a)
            if v is not None:
                out.append(f"{a.upper()}{self.c(v)}")
        return out

    def kesin(self) -> bool:
        """Tezgâhın konumu yazılan konumla aynı mı (CP sonrası değildir)."""
        return self.gercek is not None and all(
            abs(g - p) <= 1e-9 for g, p in zip(self.gercek, self.pos, strict=True)
        )

    def dogru(self, b, words: list[str]) -> None:
        """L bloğu; CP sonrası (konum kesin değil) üç eksen de yazılır, konum yeniden kesinleşir."""
        p = self.yeni_konum(b)
        if self.pos is not None and not self.kesin():
            ax = [f"{a}{self.c(v)}" for a, v in zip("XYZ", p, strict=True)]
        else:
            ax = self.axes(b)
        self.hareket(["L", *ax, "R0", *words])
        self.pos = p
        self.gercek = list(p)

    def yeni_konum(self, b) -> list[float]:
        if self.pos is None and any(getattr(b, a) is None for a in "xyz"):
            raise CamError("Heidenhain: konum bilinmiyken eksik eksenli hareket (M91 sonrası)")
        return [self.pos[i] if getattr(b, a) is None else getattr(b, a) for i, a in enumerate("xyz")]

    def feed(self, F: float | None) -> list[str]:
        return [] if F is None else [f"F{fmt(F, self.d.feed_decimals).rstrip('.')}"]

    def block(self, b: Block) -> None:
        if isinstance(b, Start):
            if b.wcs not in self.presets:
                raise CamError(
                    f"Heidenhain: iş sıfırı {b.wcs} için ön ayar (presets) yok; varsayılan eşleme yapılmaz"
                )
            self.preset = self.presets[b.wcs]
            self.emit([f"BEGIN PGM {self.ad} MM"])
            return
        if isinstance(b, Comment):
            self.emit([f"; {b.text}"])
            return
        if self.preset is not None:
            self.emit([f"CYCL DEF 247 DATUM SETTING ~ Q339=+{self.preset}"])
            self.preset = None
        if isinstance(b, ToolChange):
            self.tool = b.tool
        elif isinstance(b, Spindle):
            if b.rpm is None:
                self.m_ekle("M5")  # geri çekme bloğu
            elif self.tool is not None:
                self.emit([f"TOOL CALL {self.tool} Z S{b.rpm}"])
                self.tool = None
                self.m3 = True
            else:
                self.emit([f"TOOL CALL Z S{b.rpm}"])  # aynı takım, yeni devir (iş mili dönüyor)
        elif self.tool is not None:
            raise CamError("Heidenhain: takım değişiminden sonra devir yok")
        elif isinstance(b, MachineZ):
            self.emit(["L", f"Z{self.c(b.z)}", "R0", "FMAX", "M91"])
            self.pos = self.gercek = None
        elif isinstance(b, Rapid):
            self.dogru(b, ["FMAX"])
        elif isinstance(b, Linear):
            self.dogru(b, self.feed(b.F))
        elif isinstance(b, Arc):
            self.yay(b)
        elif isinstance(b, End):
            self.m_ekle("M30")
            self.emit([f"END PGM {self.ad} MM"])
        else:
            raise CamError(f"Heidenhain: {type(b).__name__} bloğu yazılamaz (SPEC 31: kanonik açılım)")

    def yay(self, b: Arc) -> None:
        """Düz yay `CC` + `C`; helis ve CP sonrası tam daire `CC` + `CP` (okuyucuyla aynı hesap)."""
        P, G = self.pos, self.gercek
        if P is None:
            raise CamError("Heidenhain: yay başlangıcı bilinmiyor")
        dec = self.d.decimals
        E = self.yeni_konum(b)
        c = (snap(P[0] + b.i, dec), snap(P[1] + b.j, dec))
        dr = "DR+" if b.ccw else "DR-"
        tam = E[0] == P[0] and E[1] == P[1]
        if E[2] == P[2] and not (tam and G[:2] != P[:2]):
            self.emit(["CC", f"X{self.c(c[0])}", f"Y{self.c(c[1])}"])
            self.hareket(["C", f"X{self.c(E[0])}", f"Y{self.c(E[1])}", dr, "R0", *self.feed(b.F)])
            self.gercek = [E[0], E[1], G[2]]
        else:
            if tam:
                ipa = 360.0 if b.ccw else -360.0  # tam tur: bitiş tezgâhın başlangıcına tam eşit
            else:
                c, ipa = helis(G, b.end or E, c, b.ccw, dec)
            iz = snap(E[2] - P[2], dec)
            ipa_s = sayi(ipa, IPA_DECIMALS)
            ipa = float(ipa_s)  # okuyucunun gördüğü açı
            cd = max(dec, CC_DECIMALS)
            self.emit(["CC", f"X{sayi(c[0], cd)}", f"Y{sayi(c[1], cd)}"])
            self.hareket(["CP", f"IPA{ipa_s}", f"IZ{self.c(iz)}", dr, "R0", *self.feed(b.F)])
            xy = (G[0], G[1]) if tam else dondur(G, c, ipa)
            self.gercek = [xy[0], xy[1], G[2] + iz]
        self.pos = E


def format_heidenhain(
    blocks: list[Block], presets: dict[str, int], dialect: Dialect = HEIDENHAIN, program_name: str = "1"
) -> str:
    """Blok listesi → Klartext program metni ('\\n' ile biten). `presets`: G54..G59 → ön ayar numarası."""
    f = _HeidenhainFormatter(presets, dialect, program_name)
    for b in blocks:
        f.block(b)
    return "".join(f"{n} {' '.join(w)}\n" for n, w in enumerate(f.lines))
