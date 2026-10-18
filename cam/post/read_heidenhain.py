"""
Heidenhain Klartext okuyucusu (SPEC 31): program metni → Toolpath listesi.

Kabul: BEGIN PGM, END PGM, TOOL CALL n Z S, L, CC, C, CP IPA IZ, FMAX, F, R0, DR±, M3 M5 M30 M91,
CYCL DEF 247 … Q339, `; yorum`. Blok numaraları 0'dan ardışık (değilse CamError). FMAX bloğu modal
F'yi değiştirmez. RL/RR, IX gibi artımsal koordinat, LP, CT, RND, CHF, diğer çevrimler, FN / Q
parametreleri, END PGM'siz program → CamError. Mesajlarda 'satır <n>' (1 tabanlı satır sırası).

Yol bölme, yay denetimi ve modal F, ISO okuyucusunun (`cam.gcode.reader._Reader`) kurallarıyla:
`TOOL CALL`'dan sonraki ilk `L ... FMAX` yolun başlangıcıdır; `M91` bloğundan sonra yeni `TOOL CALL`
gelmeden hareket CamError. Helis `CP IPA IZ`: bitiş, başlangıcın CC çevresinde IPA kadar dönmesidir;
|IPA| > 360 eşit parçalara (her biri ≤ 1 tur) bölünür.
"""

from __future__ import annotations

import math
import re

from cam.gcode.reader import _Reader
from cam.model import R_MIN, CamError, MoveType, Tool, Toolpath
from cam.post.format_heidenhain import HEIDENHAIN, dondur

_NO = re.compile(r"(\d+) (.*)")
_SAYI = r"[+-]?(?:\d+\.?\d*|\.\d+)"
_EKSEN = re.compile(rf"([XYZ])({_SAYI})")
_BEGIN = re.compile(r"BEGIN PGM (\S+) MM")
_END = re.compile(r"END PGM (\S+) MM")
_PRESET = re.compile(r"CYCL DEF 247 DATUM SETTING ~ Q339=\+?(\d+)")
_TOOL = re.compile(rf"TOOL CALL(?: (\d+))? Z S({_SAYI})")


class _HeidenhainReader(_Reader):
    def __init__(self, tools: dict[int, Tool], arc_tol: float) -> None:
        super().__init__(tools, HEIDENHAIN, arc_tol)
        self.cc: tuple[float, float] | None = None
        self.bitti = False  # M30 geldi

    # --- bloklar ----------------------------------------------------------------------
    def blok(self, s: str) -> None:
        if self.bitti:
            raise CamError("M30'dan sonra hareket bloğu olamaz")
        if s.startswith("CYCL DEF"):
            if not _PRESET.fullmatch(s):
                raise CamError(f"desteklenmeyen çevrim '{s}' (yalnız CYCL DEF 247 DATUM SETTING Q339)")
            return
        if s.startswith("TOOL CALL"):
            self.tool_call(s)
            return
        cins, _, kalan = s.partition(" ")
        if cins == "L":
            self.dogru(kalan.split())
        elif cins == "CC":
            self.merkez(kalan.split())
        elif cins == "C":
            self.c(kalan.split())
        elif cins == "CP":
            self.cp(kalan.split())
        else:
            raise CamError(f"desteklenmeyen blok '{s}'")

    def tool_call(self, s: str) -> None:
        m = _TOOL.fullmatch(s)
        if m is None:
            raise CamError(f"TOOL CALL yalnız 'TOOL CALL <n> Z S<devir>' biçiminde ('{s}')")
        w = {"S": float(m.group(2))}
        if m.group(1) is not None:
            w["T"] = float(m.group(1))
        elif self.state.tool is None:
            raise CamError("takım numarasız TOOL CALL: etkin takım yok")
        self.words(w)

    def kelimeler(self, toks: list[str], izin: str) -> tuple[dict[str, float], set[str]]:
        """Eksen kelimeleri ve bayraklar (R0, FMAX, DR±, M, F). R0 zorunlu; izin dışı her şey CamError."""
        w: dict[str, float] = {}
        bayrak: set[str] = set()
        for t in toks:
            m = _EKSEN.fullmatch(t)
            if m is not None and m.group(1) in izin:
                if m.group(1) in w:
                    raise CamError(f"'{m.group(1)}' blokta iki kez var")
                w[m.group(1)] = float(m.group(2))
            elif t in ("R0", "FMAX", "DR+", "DR-", "M3", "M5", "M30", "M91"):
                bayrak.add(t)
            elif re.fullmatch(rf"F{_SAYI}", t):
                if "F" in w:
                    raise CamError("F blokta iki kez var")
                w["F"] = float(t[1:])
            elif t in ("RL", "RR"):
                raise CamError(f"{t} (yarıçap telafisi) desteklenmiyor; yalnız R0")
            else:
                raise CamError(f"bilinmeyen kelime '{t}'")
        if "R0" not in bayrak:
            raise CamError("R0 yok (yarıçap telafisi modal kalabilir; her blokta R0 yazılmalı)")
        return w, bayrak

    def m_kodlari(self, bayrak: set[str]) -> None:
        if "M3" in bayrak:
            self.spindle_on = True
        if "M5" in bayrak:
            self.spindle_on = False
        if "M30" in bayrak:
            self.spindle_on = False
            self.bitti = True

    def ilerleme(self, w: dict[str, float]) -> None:
        if "F" in w:
            if not w["F"] > 0:
                raise CamError(f"ilerleme pozitif olmalı (F{w['F']:g})")
            self.state.feed = w["F"]

    def dogru(self, toks: list[str]) -> None:
        w, bayrak = self.kelimeler(toks, "XYZ")
        if not any(k in w for k in "XYZ"):
            raise CamError("L bloğunda eksen yok")
        if "M91" in bayrak:
            if set(w) != {"Z"} or "FMAX" not in bayrak or bayrak - {"R0", "FMAX", "M91"}:
                raise CamError("M91 yalnız 'L Z<v> R0 FMAX M91' biçiminde destekleniyor")
            self.state.pos = None
            self.g53 = True
            return
        if "FMAX" in bayrak:
            if "F" in w:
                raise CamError("FMAX ve F aynı blokta")
            self.add(MoveType.RAPID, self.target(w))
        else:
            self.ilerleme(w)
            self.add(MoveType.LINEAR, self.target(w))
        self.m_kodlari(bayrak)

    def merkez(self, toks: list[str]) -> None:
        w = {}
        for t in toks:
            m = _EKSEN.fullmatch(t)
            if m is None or m.group(1) not in "XY" or m.group(1) in w:
                raise CamError(f"CC yalnız 'CC X<x> Y<y>' biçiminde ('{t}')")
            w[m.group(1)] = float(m.group(2))
        if set(w) != {"X", "Y"}:
            raise CamError("CC'de X ve Y yazılmalı")
        self.cc = (w["X"], w["Y"])

    def yon(self, bayrak: set[str]) -> MoveType:
        dr = bayrak & {"DR+", "DR-"}
        if len(dr) != 1:
            raise CamError("yayda yön (DR+ / DR-) yok")
        if bayrak & {"FMAX", "M91"}:
            raise CamError("yayda FMAX / M91 olamaz")
        if self.cc is None:
            raise CamError("yay merkezi (CC) tanımlanmamış")
        return MoveType.ARC_CCW if "DR+" in dr else MoveType.ARC_CW

    def c(self, toks: list[str]) -> None:
        w, bayrak = self.kelimeler(toks, "XY")
        t = self.yon(bayrak)
        if set(w) - {"F"} != {"X", "Y"}:
            raise CamError("C'de X ve Y yazılmalı")
        p0 = self.state.pos
        if p0 is None:
            raise CamError("yay başlangıcı bilinmiyor")
        self.ilerleme(w)
        p1 = (w["X"], w["Y"], p0[2])
        self.add(t, p1, self.check_arc(p0, p1, self.cc))
        self.m_kodlari(bayrak)

    def cp(self, toks: list[str]) -> None:
        if len(toks) < 2 or not toks[0].startswith("IPA") or not toks[1].startswith("IZ"):
            raise CamError("CP yalnız 'CP IPA<açı> IZ<dz> DR± R0 [F]' biçiminde")
        try:
            ipa, iz = float(toks[0][3:]), float(toks[1][2:])
        except ValueError:
            raise CamError(f"CP sayısı çözülemedi ('{toks[0]} {toks[1]}')") from None
        w, bayrak = self.kelimeler(toks[2:], "")
        t = self.yon(bayrak)
        if ipa == 0 or (ipa > 0) != (t is MoveType.ARC_CCW):
            raise CamError(f"IPA{ipa:+g} yönle (DR) uyuşmuyor")
        p0 = self.state.pos
        if p0 is None:
            raise CamError("helis başlangıcı bilinmiyor")
        if math.hypot(p0[0] - self.cc[0], p0[1] - self.cc[1]) < R_MIN:
            raise CamError("helis yarıçapı sıfır")
        self.ilerleme(w)
        k = math.ceil(abs(ipa) / 360.0 - 1e-12)  # parça başına en çok bir tur
        for n in range(1, k + 1):
            p = self.state.pos
            if abs(ipa / k) == 360.0:
                xy = (p[0], p[1])  # tam tur: bitiş başlangıca tam eşit
            else:
                xy = dondur(p, self.cc, ipa / k)
            self.add(t, (xy[0], xy[1], p0[2] + iz * n / k), self.cc)
        self.m_kodlari(bayrak)


def read_heidenhain(text: str, tools: dict[int, Tool], arc_tol: float = 0.005) -> list[Toolpath]:
    rd = _HeidenhainReader(tools, arc_tol)
    ad: str | None = None
    son = False
    satirlar = text.splitlines()
    for n, raw in enumerate(satirlar, start=1):
        try:
            if not raw.strip():
                continue
            m = _NO.fullmatch(raw.strip())
            if m is None:
                raise CamError(f"blok numarası yok ('{raw}')")
            if int(m.group(1)) != n - 1:
                raise CamError(f"blok numarası {n - 1} bekleniyordu, {m.group(1)} geldi (eksik blok)")
            s = m.group(2).split(";", 1)[0].strip().upper()
            if son:
                raise CamError("END PGM'den sonra blok olamaz")
            if n == 1:
                b = _BEGIN.fullmatch(s)
                if b is None:
                    raise CamError("program 'BEGIN PGM <ad> MM' ile başlamalı")
                ad = b.group(1)
                continue
            if not s:
                continue  # yorum bloğu
            e = _END.fullmatch(s)
            if e is not None:
                if e.group(1) != ad:
                    raise CamError(f"END PGM adı '{e.group(1)}', BEGIN PGM '{ad}'")
                son = True
                continue
            rd.blok(s)
        except CamError as err:
            raise CamError(f"satır {n}: {err}") from None
    if not son:
        raise CamError(f"satır {len(satirlar)}: END PGM yok (program eksik)")
    return rd.finish()
