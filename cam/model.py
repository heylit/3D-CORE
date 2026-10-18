"""
3D-CORE CAM veri modeli.

CAM katmanının (takım yolu, G-code, simülasyon, kurulum) ortak dili. Saf Python + numpy; OCCT gerektirmez.

Birimler:
    uzunluk     : mm
    ilerleme    : mm/dk (G94) veya mm/dev (G95, torna)
    devir       : dev/dk
    kesme hızı  : m/dk (Vc)
    açı         : derece

Hareketler G-code anlamıyla aynıdır (ISO 6983): G0 hızlı, G1 doğrusal, G2 saat yönü yay,
G3 saat yönü tersi yay. Yaylar takım yolunun düzlemindedir:
    G17 (XY): +Z'den bakınca; merkez (x, y). Z değişirse helis.
    G18 (ZX): +Y'den bakınca, G3 = Z'den X'e dönüş; merkez (x, z) (I, K sırası). Y değişirse helis.
Yay merkezi mutlak koordinattır.

Torna: iş mili ekseni Z, X radyal ve modelde X yarıçaptır (çap programlama G-code işidir).
Torna yolları y = 0 düzleminde, XZ'dedir.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from enum import StrEnum

import numpy as np

ARC_TOL = 1e-6  # mm: yayın başlangıç ve bitiş yarıçapı arasındaki izin verilen fark
R_MIN = 1e-9  # mm: bundan küçük yarıçap yay sayılmaz


class CamError(ValueError):
    """CAM modelinde tutarsızlık (geçersiz takım, eksik ilerleme, hatalı yay...)."""


class ToolKind(StrEnum):
    FLAT = "duz"
    BALL = "kuresel"
    DRILL = "matkap"
    CONE = "konik"
    SPOT = "punta"
    CHAMFER = "havsa"
    TAP = "kilavuz"


class LatheToolKind(StrEnum):
    TURN = "tornalama"
    BORE = "ic_tornalama"
    GROOVE = "kanal"
    THREAD = "dis"


class MoveType(StrEnum):
    RAPID = "G0"
    LINEAR = "G1"
    ARC_CW = "G2"
    ARC_CCW = "G3"


class Plane(StrEnum):
    XY = "G17"
    ZX = "G18"


class FeedMode(StrEnum):
    PER_MIN = "G94"  # mm/dk
    PER_REV = "G95"  # mm/dev


ARCS = {MoveType.ARC_CW, MoveType.ARC_CCW}
WCS_CODES = ("G54", "G55", "G56", "G57", "G58", "G59")
UNIT_TOL = 1e-9  # birim vektör ve dik matris toleransı


def _sonlu(nerede: str, **degerler) -> None:
    """Her değer (sayı veya sayı dizisi) sonlu olmalı; nan / inf → CamError. Sessiz hata yok."""
    for ad, v in degerler.items():
        if not np.all(np.isfinite(np.asarray(v, dtype=float))):
            raise CamError(f"{nerede}: {ad} sonlu olmalı ({ad}={v})")


def _vektor3(nerede: str, ad: str, v) -> tuple[float, float, float]:
    """3 bileşenli, sonlu float tuple; aksi CamError."""
    try:
        t = tuple(float(x) for x in v)
    except (TypeError, ValueError) as e:
        raise CamError(f"{nerede}: {ad} 3 sayı olmalı ({v!r})") from e
    if len(t) != 3:
        raise CamError(f"{nerede}: {ad} 3 bileşenli olmalı ({v!r})")
    _sonlu(nerede, **{ad: t})
    return t


def _birim3(nerede: str, ad: str, v) -> tuple[float, float, float]:
    """Birim 3 vektör (| |v| − 1 | ≤ UNIT_TOL); sessiz normalleştirme yok."""
    t = _vektor3(nerede, ad, v)
    if abs(math.sqrt(sum(x * x for x in t)) - 1) > UNIT_TOL:
        raise CamError(f"{nerede}: {ad} birim vektör olmalı ({t})")
    return t


def _alanlar(nerede: str, d: dict, zorunlu: set[str], istege_bagli: set[str]) -> None:
    """JSON sözlüğünde eksik zorunlu alan veya bilinmeyen alan → CamError."""
    eksik = zorunlu - d.keys()
    fazla = d.keys() - zorunlu - istege_bagli
    if eksik or fazla:
        raise CamError(f"{nerede}: eksik alan {sorted(eksik)}, bilinmeyen alan {sorted(fazla)}")


# ---------------------------------------------------------------- kesme verisi, tutucu


@dataclass
class CuttingData:
    """Bir malzeme için kesme verisi. Freze: fz [mm/diş]; torna: fn [mm/dev]. Tam olarak biri verilir."""

    Vc: float  # m/dk, kesme hızı
    fz: float | None = None  # mm/diş (freze)
    fn: float | None = None  # mm/dev (torna)
    ap: float | None = None  # mm, kesme derinliği
    ae: float | None = None  # mm, yanal kesme genişliği

    def __post_init__(self) -> None:
        _sonlu("Kesme verisi", Vc=self.Vc)
        if self.Vc <= 0:
            raise CamError(f"Kesme verisi: Vc pozitif olmalı (Vc={self.Vc})")
        if (self.fz is None) == (self.fn is None):
            raise CamError(f"Kesme verisi: fz ve fn'den tam olarak biri verilmeli ({self.fz=}, {self.fn=})")
        for ad in ("fz", "fn", "ap", "ae"):
            v = getattr(self, ad)
            if v is None:
                continue
            _sonlu("Kesme verisi", **{ad: v})
            if v <= 0:
                raise CamError(f"Kesme verisi: {ad} pozitif olmalı ({ad}={v})")

    def to_dict(self) -> dict:
        return {"Vc": self.Vc, "fz": self.fz, "fn": self.fn, "ap": self.ap, "ae": self.ae}

    @classmethod
    def from_dict(cls, d: dict) -> CuttingData:
        _alanlar("Kesme verisi", d, {"Vc"}, {"fz", "fn", "ap", "ae"})
        return cls(**d)


def _cutting_from_dict(d: dict) -> dict[str, CuttingData]:
    return {k: CuttingData.from_dict(v) for k, v in d.items()}


@dataclass
class ToolHolder:
    """Takım tutucu: iş mili ölçü hattından ağza boy ve dönel kesit profili.

    profile: (z, r) noktaları; z tutucu ağzından (z = 0) yukarı, azalmayan;
    ardışık iki nokta arası kesik koni.
    """

    name: str
    gauge_length: float  # mm, ölçü hattı → tutucu ağzı
    profile: tuple[tuple[float, float], ...]

    def __post_init__(self) -> None:
        self.profile = tuple((float(z), float(r)) for z, r in self.profile)
        nerede = f"Tutucu '{self.name}'"
        _sonlu(nerede, gauge_length=self.gauge_length)
        if self.gauge_length <= 0:
            raise CamError(f"{nerede}: ölçü boyu pozitif olmalı ({self.gauge_length})")
        if len(self.profile) < 2:
            raise CamError(f"{nerede}: profil en az 2 nokta olmalı")
        P = np.array(self.profile)
        _sonlu(nerede, profile=P)
        z, r = P[:, 0], P[:, 1]
        if z[0] != 0:
            raise CamError(f"{nerede}: profil z = 0'dan (ağız) başlamalı (z0={z[0]})")
        if np.any(np.diff(z) < 0):
            raise CamError(f"{nerede}: profilde z azalmamalı")
        if z[-1] > self.gauge_length:
            raise CamError(f"{nerede}: profil ölçü boyunu aşıyor (z={z[-1]} > {self.gauge_length})")
        if np.any(r <= 0):
            raise CamError(f"{nerede}: profil yarıçapları pozitif olmalı")

    def to_dict(self) -> dict:
        profile = [list(p) for p in self.profile]
        return {"name": self.name, "gauge_length": self.gauge_length, "profile": profile}

    @classmethod
    def from_dict(cls, d: dict) -> ToolHolder:
        _alanlar("Tutucu", d, {"name", "gauge_length", "profile"}, set())
        profile = tuple(tuple(p) for p in d["profile"])
        return cls(name=d["name"], gauge_length=d["gauge_length"], profile=profile)


# ---------------------------------------------------------------- takımlar


@dataclass
class Tool:
    """Freze / matkap takımı."""

    id: int
    name: str
    kind: ToolKind
    D: float  # mm, takım çapı
    flute_length: float  # mm, kesici boy
    corner_r: float = 0.0  # mm, köşe radyüsü (küresel uçta D/2)
    flutes: int | None = None  # z, diş sayısı
    shank_d: float | None = None  # mm, sap çapı; None → D
    stickout: float | None = None  # mm, tutucu ağzından takım ucuna boy
    holder: ToolHolder | None = None
    cutting: dict[str, CuttingData] = field(default_factory=dict)  # malzeme → kesme verisi (fz)
    center_cutting: bool = True  # merkezden keser mi (False → düz dalma yok, SPEC 03 / 04)
    tip_angle: float | None = (
        None  # derece, tam uç açısı φ: CONE/SPOT/CHAMFER'da zorunlu, DRILL'de isteğe bağlı
    )
    tip_d: float = 0.0  # mm, havşa takımının düz uç çapı (yalnız CHAMFER)
    pitch: float | None = None  # mm, kılavuz diş adımı (yalnız TAP, zorunlu)
    lead: float | None = None  # diş sayısı, kılavuz giriş pahı (yalnız TAP, zorunlu)
    ramp_angle_max: float | None = None  # derece, izin verilen en büyük rampa açısı (SPEC 03c)

    def __post_init__(self) -> None:
        self.kind = ToolKind(self.kind)
        nerede = f"Takım '{self.name}'"
        _sonlu(nerede, D=self.D, flute_length=self.flute_length, corner_r=self.corner_r)
        if self.D <= 0:
            raise CamError(f"{nerede}: D pozitif olmalı (D={self.D})")
        if self.flute_length <= 0:
            raise CamError(f"{nerede}: kesici boy pozitif olmalı ({self.flute_length})")
        if self.kind is ToolKind.BALL:
            self.corner_r = self.D / 2
        if not 0 <= self.corner_r <= self.D / 2:
            raise CamError(f"{nerede}: köşe radyüsü 0..D/2 olmalı ({self.corner_r})")
        if self.flutes is not None and (isinstance(self.flutes, bool) or not isinstance(self.flutes, int)):
            raise CamError(f"{nerede}: diş sayısı tam sayı olmalı ({self.flutes!r})")
        if self.flutes is not None and self.flutes < 1:
            raise CamError(f"{nerede}: diş sayısı en az 1 olmalı ({self.flutes})")
        if self.shank_d is not None:
            _sonlu(nerede, shank_d=self.shank_d)
            if self.shank_d <= 0:
                raise CamError(f"{nerede}: sap çapı pozitif olmalı ({self.shank_d})")
        if self.stickout is not None:
            _sonlu(nerede, stickout=self.stickout)
            if self.stickout < self.flute_length:
                raise CamError(f"{nerede}: taşma boyu kesici boydan kısa olamaz ({self.stickout})")
        if not isinstance(self.center_cutting, bool):
            raise CamError(f"{nerede}: center_cutting bool olmalı ({self.center_cutting!r})")
        if self.kind is ToolKind.DRILL and not self.center_cutting:
            raise CamError(f"{nerede}: matkap merkezden keser; center_cutting=False olamaz")
        for malzeme, c in self.cutting.items():
            if c.fz is None:
                raise CamError(f"{nerede}: '{malzeme}' kesme verisinde fz (mm/diş) olmalı")
        self._uc_acisi(nerede)
        self._kilavuz(nerede)
        if self.ramp_angle_max is not None:
            _sonlu(nerede, ramp_angle_max=self.ramp_angle_max)
            if not 0 < self.ramp_angle_max <= 90:
                raise CamError(f"{nerede}: en büyük rampa açısı 0 < α ≤ 90 olmalı ({self.ramp_angle_max})")

    def _uc_acisi(self, nerede: str) -> None:
        """Konik uçlu takımlar (CONE, SPOT, CHAMFER): 0 < φ < 180, köşe radyüsü yok,
        koni yüksekliği ((D − tip_d)/2)·cot(φ/2) kesici boya sığar. DRILL'de φ isteğe bağlı."""
        _sonlu(nerede, tip_d=self.tip_d)
        if self.kind is ToolKind.CHAMFER:
            if not 0 <= self.tip_d < self.D:
                raise CamError(f"{nerede}: havşa uç çapı 0 ≤ tip_d < D olmalı ({self.tip_d})")
        elif self.tip_d != 0:
            raise CamError(f"{nerede}: uç çapı (tip_d) yalnız havşa takımında verilir ({self.tip_d})")
        konik = self.kind in (ToolKind.CONE, ToolKind.SPOT, ToolKind.CHAMFER)
        if self.tip_angle is None:
            if konik:
                raise CamError(f"{nerede}: {self.kind.value} takımda uç açısı (tip_angle) zorunlu")
            return
        if not konik and self.kind is not ToolKind.DRILL:
            raise CamError(f"{nerede}: uç açısı yalnız konik, punta, havşa takımında ve matkapta verilir")
        _sonlu(nerede, tip_angle=self.tip_angle)
        if not 0 < self.tip_angle < 180:
            raise CamError(f"{nerede}: uç açısı 0..180 derece arasında olmalı ({self.tip_angle})")
        if konik:
            if self.corner_r != 0:
                raise CamError(f"{nerede}: {self.kind.value} takımda köşe radyüsü 0 olmalı ({self.corner_r})")
            h_c = (self.D - self.tip_d) / 2 / math.tan(math.radians(self.tip_angle) / 2)
            if h_c > self.flute_length:
                raise CamError(f"{nerede}: koni yüksekliği kesici boydan büyük ({h_c} > {self.flute_length})")

    def _kilavuz(self, nerede: str) -> None:
        """Kılavuz: pitch > 0 ve lead > 0 zorunlu, köşe radyüsü yok, giriş pahı lead·pitch < kesici boy."""
        if self.kind is not ToolKind.TAP:
            if self.pitch is not None or self.lead is not None:
                raise CamError(f"{nerede}: diş adımı (pitch) ve giriş pahı (lead) yalnız kılavuzda verilir")
            return
        if self.pitch is None or self.lead is None:
            raise CamError(f"{nerede}: kılavuzda diş adımı (pitch) ve giriş pahı (lead) zorunlu")
        _sonlu(nerede, pitch=self.pitch, lead=self.lead)
        if self.pitch <= 0 or self.lead <= 0:
            raise CamError(f"{nerede}: diş adımı ve giriş pahı pozitif olmalı ({self.pitch}, {self.lead})")
        if self.corner_r != 0:
            raise CamError(f"{nerede}: kılavuzda köşe radyüsü 0 olmalı ({self.corner_r})")
        if not self.lead * self.pitch < self.flute_length:
            raise CamError(f"{nerede}: giriş pahı boyu (lead·pitch) kesici boydan kısa olmalı")

    @property
    def shank(self) -> float:
        """Sap çapı [mm]; verilmemişse D."""
        return self.D if self.shank_d is None else self.shank_d

    @property
    def gauge_length(self) -> float | None:
        """Ölçü hattından takım ucuna boy [mm] = tutucu ölçü boyu + taşma; biri yoksa None."""
        if self.holder is None or self.stickout is None:
            return None
        return self.holder.gauge_length + self.stickout

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "kind": self.kind.value,
            "D": self.D,
            "flute_length": self.flute_length,
            "corner_r": self.corner_r,
            "flutes": self.flutes,
            "shank_d": self.shank_d,
            "stickout": self.stickout,
            "holder": None if self.holder is None else self.holder.to_dict(),
            "cutting": {k: v.to_dict() for k, v in self.cutting.items()},
            "center_cutting": self.center_cutting,
            "tip_angle": self.tip_angle,
            "tip_d": self.tip_d,
            "pitch": self.pitch,
            "lead": self.lead,
            "ramp_angle_max": self.ramp_angle_max,
        }

    @classmethod
    def from_dict(cls, d: dict) -> Tool:
        _alanlar(
            "Takım",
            d,
            {"id", "name", "kind", "D", "flute_length"},
            {
                "corner_r",
                "flutes",
                "shank_d",
                "stickout",
                "holder",
                "cutting",
                "center_cutting",
                "tip_angle",
                "tip_d",
                "pitch",
                "lead",
                "ramp_angle_max",
            },
        )
        d = dict(d)
        if d.get("holder") is not None:
            d["holder"] = ToolHolder.from_dict(d["holder"])
        d["cutting"] = _cutting_from_dict(d.get("cutting") or {})
        return cls(**d)


@dataclass
class LatheHolder:
    """Torna takım tutucusu: burun merkezine göre dış çerçevede (z, x) dışbükey çokgen,
    y yönünde yarı kalınlık.

    polygon: en az 3 nokta, saat yönü tersi, son nokta tekrarsız.
    """

    name: str
    polygon: tuple[tuple[float, float], ...]
    half_width: float  # mm, y yönünde yarı kalınlık

    def __post_init__(self) -> None:
        nerede = f"Torna tutucusu '{self.name}'"
        self.polygon = tuple((float(z), float(x)) for z, x in self.polygon)
        _sonlu(nerede, half_width=self.half_width)
        if self.half_width <= 0:
            raise CamError(f"{nerede}: yarı kalınlık pozitif olmalı ({self.half_width})")
        if len(self.polygon) < 3:
            raise CamError(f"{nerede}: çokgen en az 3 nokta olmalı")
        P = np.array(self.polygon)
        _sonlu(nerede, polygon=P)
        # Ardışık kenarların vektörel çarpımı: saat yönü tersi dışbükey çokgende hepsi ≥ 0, alan > 0.
        e = np.roll(P, -1, axis=0) - P
        cross = e[:, 0] * np.roll(e, -1, axis=0)[:, 1] - e[:, 1] * np.roll(e, -1, axis=0)[:, 0]
        alan = 0.5 * float(
            np.sum(P[:, 0] * np.roll(P, -1, axis=0)[:, 1] - P[:, 1] * np.roll(P, -1, axis=0)[:, 0])
        )
        if alan <= 0:
            raise CamError(f"{nerede}: çokgen saat yönü tersi ve alanı pozitif olmalı (alan={alan})")
        if np.any(cross < 0):
            raise CamError(f"{nerede}: çokgen dışbükey olmalı")

    def to_dict(self) -> dict:
        return {"name": self.name, "polygon": [list(p) for p in self.polygon], "half_width": self.half_width}

    @classmethod
    def from_dict(cls, d: dict) -> LatheHolder:
        _alanlar("Torna tutucusu", d, {"name", "polygon", "half_width"}, set())
        return cls(name=d["name"], polygon=tuple(tuple(p) for p in d["polygon"]), half_width=d["half_width"])


@dataclass
class LatheTool:
    """Torna takımı (uç geometrisiyle).

    tip   : Fanuc hayali uç numarası 0..9 (burun yarıçapı telafisinin yönü; 0 ve 9 burun merkezi)
    kappa_r: yaklaşma açısı, ana kesici kenar ile ilerleme yönü arası [derece]
    eps_r : uç açısı [derece] (ISO: C 80, D 55, V 35, T 60; diş 60)
    """

    id: int
    name: str
    kind: LatheToolKind
    nose_r: float  # mm, burun yarıçapı
    tip: int
    kappa_r: float
    eps_r: float
    width: float = 0.0  # mm, kanal ucu genişliği
    cutting: dict[str, CuttingData] = field(default_factory=dict)  # malzeme → kesme verisi (fn)
    edge_len: float | None = None  # mm, kesici kenar boyu (burun teğet noktasından); kanalda dalma kapasitesi
    holder: LatheHolder | None = None

    def __post_init__(self) -> None:
        self.kind = LatheToolKind(self.kind)
        nerede = f"Torna takımı '{self.name}'"
        _sonlu(nerede, nose_r=self.nose_r, kappa_r=self.kappa_r, eps_r=self.eps_r, width=self.width)
        if self.nose_r < 0:
            raise CamError(f"{nerede}: burun yarıçapı negatif olamaz ({self.nose_r})")
        if self.kind in (LatheToolKind.TURN, LatheToolKind.BORE) and self.nose_r <= 0:
            raise CamError(f"{nerede}: tornalama ucunda burun yarıçapı pozitif olmalı ({self.nose_r})")
        if isinstance(self.tip, bool) or not isinstance(self.tip, int) or not 0 <= self.tip <= 9:
            raise CamError(f"{nerede}: uç numarası 0..9 tam sayı olmalı ({self.tip!r})")
        if not (0 < self.kappa_r < 180 and 0 < self.eps_r < 180):
            raise CamError(f"{nerede}: açılar 0..180 arasında olmalı (κr={self.kappa_r}, εr={self.eps_r})")
        if self.kappa_r + self.eps_r > 180:
            raise CamError(f"{nerede}: κr + εr ≤ 180 olmalı ({self.kappa_r} + {self.eps_r})")
        if self.kind is LatheToolKind.GROOVE:
            if self.width <= 0:
                raise CamError(f"{nerede}: kanal ucunda genişlik pozitif olmalı ({self.width})")
            if self.nose_r > self.width / 2:
                raise CamError(f"{nerede}: burun yarıçapı genişliğin yarısını aşamaz ({self.nose_r})")
        elif self.width != 0:
            raise CamError(f"{nerede}: genişlik sadece kanal ucunda verilir ({self.width})")
        for malzeme, c in self.cutting.items():
            if c.fn is None:
                raise CamError(f"{nerede}: '{malzeme}' kesme verisinde fn (mm/dev) olmalı")
        if self.edge_len is not None:
            _sonlu(nerede, edge_len=self.edge_len)
            if self.edge_len <= 0:
                raise CamError(f"{nerede}: kesici kenar boyu pozitif olmalı ({self.edge_len})")
        if self.holder is not None and not isinstance(self.holder, LatheHolder):
            raise CamError(f"{nerede}: tutucu LatheHolder olmalı ({type(self.holder).__name__})")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "kind": self.kind.value,
            "nose_r": self.nose_r,
            "tip": self.tip,
            "kappa_r": self.kappa_r,
            "eps_r": self.eps_r,
            "width": self.width,
            "cutting": {k: v.to_dict() for k, v in self.cutting.items()},
            "edge_len": self.edge_len,
            "holder": None if self.holder is None else self.holder.to_dict(),
        }

    @classmethod
    def from_dict(cls, d: dict) -> LatheTool:
        zorunlu = {"id", "name", "kind", "nose_r", "tip", "kappa_r", "eps_r"}
        _alanlar("Torna takımı", d, zorunlu, {"width", "cutting", "edge_len", "holder"})
        d = dict(d)
        d["cutting"] = _cutting_from_dict(d.get("cutting") or {})
        if d.get("holder") is not None:
            d["holder"] = LatheHolder.from_dict(d["holder"])
        return cls(**d)


def tool_from_dict(d: dict) -> Tool | LatheTool:
    """`kind` değerine göre freze (Tool) veya torna (LatheTool) takımı."""
    kind = d.get("kind")
    if kind in {k.value for k in ToolKind}:
        return Tool.from_dict(d)
    if kind in {k.value for k in LatheToolKind}:
        return LatheTool.from_dict(d)
    raise CamError(f"Bilinmeyen takım türü: {kind!r}")


@dataclass
class ToolLibrary:
    tools: list[Tool | LatheTool] = field(default_factory=list)

    def validate(self) -> None:
        ids = [t.id for t in self.tools]
        dup = {i for i in ids if ids.count(i) > 1}
        if dup:
            raise CamError(f"Takım kütüphanesi: yinelenen id {sorted(dup)}")

    def get(self, id: int) -> Tool | LatheTool:
        for t in self.tools:
            if t.id == id:
                return t
        raise CamError(f"Takım kütüphanesi: T{id} yok")

    def add(self, tool: Tool | LatheTool) -> None:
        if any(t.id == tool.id for t in self.tools):
            raise CamError(f"Takım kütüphanesi: T{tool.id} zaten var")
        self.tools.append(tool)

    def to_dict(self) -> dict:
        return {"tools": [t.to_dict() for t in self.tools]}

    @classmethod
    def from_dict(cls, d: dict) -> ToolLibrary:
        _alanlar("Takım kütüphanesi", d, {"tools"}, set())
        lib = cls([tool_from_dict(t) for t in d["tools"]])
        lib.validate()
        return lib


# ---------------------------------------------------------------- ham malzeme, kurulum


@dataclass
class Stock:
    """Eksenlere hizalı ham malzeme kutusu [mm]."""

    xmin: float
    ymin: float
    zmin: float
    xmax: float
    ymax: float
    zmax: float

    def __post_init__(self) -> None:
        _sonlu("Ham malzeme", sinirlar=[self.xmin, self.ymin, self.zmin, self.xmax, self.ymax, self.zmax])
        if not (self.xmax > self.xmin and self.ymax > self.ymin and self.zmax > self.zmin):
            raise CamError(f"Ham malzeme: her eksende max > min olmalı ({self})")

    @property
    def size(self) -> np.ndarray:
        return np.array([self.xmax - self.xmin, self.ymax - self.ymin, self.zmax - self.zmin])

    @property
    def volume(self) -> float:
        return float(np.prod(self.size))

    def to_dict(self) -> dict:
        sinirlar = ("xmin", "ymin", "zmin", "xmax", "ymax", "zmax")
        return {"type": "kutu", **{k: getattr(self, k) for k in sinirlar}}

    @classmethod
    def from_dict(cls, d: dict) -> Stock:
        d = {k: v for k, v in d.items() if k != "type"}
        _alanlar("Ham malzeme", d, {"xmin", "ymin", "zmin", "xmax", "ymax", "zmax"}, set())
        return cls(**d)


@dataclass
class CylinderStock:
    """Z eksenli silindir ham malzeme (torna çubuğu, boru); ekseni x = y = 0 [mm]."""

    D: float  # dış çap
    zmin: float
    zmax: float
    d: float = 0.0  # iç çap (boru), 0 → dolu

    def __post_init__(self) -> None:
        _sonlu("Silindir ham malzeme", D=self.D, zmin=self.zmin, zmax=self.zmax, d=self.d)
        if self.D <= 0:
            raise CamError(f"Silindir ham malzeme: D pozitif olmalı (D={self.D})")
        if self.zmax <= self.zmin:
            raise CamError(f"Silindir ham malzeme: zmax > zmin olmalı ({self.zmin}, {self.zmax})")
        if not 0 <= self.d < self.D:
            raise CamError(f"Silindir ham malzeme: 0 ≤ d < D olmalı (d={self.d}, D={self.D})")

    @property
    def length(self) -> float:
        return self.zmax - self.zmin

    @property
    def volume(self) -> float:
        """V = π/4 · (D² − d²) · L"""
        return math.pi / 4 * (self.D**2 - self.d**2) * self.length

    def bbox(self) -> tuple[np.ndarray, np.ndarray]:
        R = self.D / 2
        return np.array([-R, -R, self.zmin]), np.array([R, R, self.zmax])

    def to_dict(self) -> dict:
        return {"type": "silindir", "D": self.D, "zmin": self.zmin, "zmax": self.zmax, "d": self.d}

    @classmethod
    def from_dict(cls, d: dict) -> CylinderStock:
        d = {k: v for k, v in d.items() if k != "type"}
        _alanlar("Silindir ham malzeme", d, {"D", "zmin", "zmax"}, {"d"})
        return cls(**d)


def _stock_from_dict(d: dict) -> Stock | CylinderStock:
    if d.get("type") == "silindir":
        return CylinderStock.from_dict(d)
    if d.get("type") == "kutu":
        return Stock.from_dict(d)
    raise CamError(f"Bilinmeyen ham malzeme türü: {d.get('type')!r}")


@dataclass
class Wcs:
    """İş koordinat sistemi: iş sıfırının makine koordinatı (G54..G59)."""

    code: str = "G54"
    origin: tuple[float, float, float] = (0.0, 0.0, 0.0)

    def __post_init__(self) -> None:
        if self.code not in WCS_CODES:
            raise CamError(f"İş sıfırı kodu G54..G59 olmalı ({self.code!r})")
        self.origin = tuple(float(v) for v in self.origin)
        if len(self.origin) != 3:
            raise CamError(f"İş sıfırı: origin 3 bileşenli olmalı ({self.origin})")
        _sonlu(f"İş sıfırı {self.code}", origin=self.origin)

    def to_machine(self, p) -> np.ndarray:
        """İş koordinatı → makine koordinatı: p + origin."""
        return np.asarray(p, dtype=float) + np.array(self.origin)

    def to_work(self, p) -> np.ndarray:
        """Makine koordinatı → iş koordinatı: p − origin."""
        return np.asarray(p, dtype=float) - np.array(self.origin)

    def to_dict(self) -> dict:
        return {"code": self.code, "origin": list(self.origin)}

    @classmethod
    def from_dict(cls, d: dict) -> Wcs:
        _alanlar("İş sıfırı", d, set(), {"code", "origin"})
        return cls(code=d.get("code", "G54"), origin=tuple(d.get("origin", (0.0, 0.0, 0.0))))


@dataclass
class Setup:
    """Bağlama: iş sıfırı, ham malzeme ve bağlama elemanları (iş koordinatında)."""

    name: str
    wcs: Wcs
    stock: Stock | CylinderStock
    fixtures: list[Stock | CylinderStock] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "wcs": self.wcs.to_dict(),
            "stock": self.stock.to_dict(),
            "fixtures": [f.to_dict() for f in self.fixtures],
        }

    @classmethod
    def from_dict(cls, d: dict) -> Setup:
        _alanlar("Kurulum", d, {"name", "wcs", "stock"}, {"fixtures"})
        return cls(
            name=d["name"],
            wcs=Wcs.from_dict(d["wcs"]),
            stock=_stock_from_dict(d["stock"]),
            fixtures=[_stock_from_dict(f) for f in d.get("fixtures", [])],
        )


# ---------------------------------------------------------------- iş düzlemi (çok eksen)


@dataclass
class Frame:
    """İş düzlemi: yerel → WCS dönüşümü p_wcs = origin + R·p_yerel.

    R'nin sütunları yerel x, y, z eksenlerinin WCS birim vektörleri; R satır satır saklanır.
    """

    origin: tuple[float, float, float]
    R: tuple[tuple[float, float, float], tuple[float, float, float], tuple[float, float, float]]

    def __post_init__(self) -> None:
        self.origin = _vektor3("İş düzlemi", "origin", self.origin)
        try:
            rows = tuple(_vektor3("İş düzlemi", "R", r) for r in self.R)
        except TypeError as e:
            raise CamError(f"İş düzlemi: R 3x3 olmalı ({self.R!r})") from e
        if len(rows) != 3:
            raise CamError(f"İş düzlemi: R 3x3 olmalı ({self.R!r})")
        self.R = rows
        M = np.array(rows)
        if np.max(np.abs(M.T @ M - np.eye(3))) > UNIT_TOL:
            raise CamError("İş düzlemi: R dik (ortonormal) olmalı")
        if np.linalg.det(M) <= 0:
            raise CamError("İş düzlemi: det R > 0 olmalı (yansıma yok)")

    def to_world(self, p) -> np.ndarray:
        """Yerel nokta → WCS: origin + R·p (p (3,) veya (n, 3))."""
        return np.asarray(p, dtype=float) @ np.array(self.R).T + np.array(self.origin)

    def to_local(self, p) -> np.ndarray:
        """WCS nokta → yerel: Rᵀ·(p − origin)."""
        return (np.asarray(p, dtype=float) - np.array(self.origin)) @ np.array(self.R)

    def to_world_vec(self, v) -> np.ndarray:
        """Yerel yön → WCS: R·v."""
        return np.asarray(v, dtype=float) @ np.array(self.R).T

    def to_local_vec(self, v) -> np.ndarray:
        """WCS yön → yerel: Rᵀ·v."""
        return np.asarray(v, dtype=float) @ np.array(self.R)

    def to_dict(self) -> dict:
        return {"origin": list(self.origin), "R": [list(r) for r in self.R]}

    @classmethod
    def from_dict(cls, d: dict) -> Frame:
        _alanlar("İş düzlemi", d, {"origin", "R"}, set())
        return cls(origin=tuple(d["origin"]), R=tuple(tuple(r) for r in d["R"]))


# ---------------------------------------------------------------- hareketler, takım yolu

Z_AXIS = (0.0, 0.0, 1.0)


@dataclass
class Move:
    type: MoveType
    end: tuple[float, float, float]
    feed: float | None = None  # G1/G2/G3 için zorunlu; birimi Toolpath.feed_mode
    center: tuple[float, float] | None = None  # yay merkezi, mutlak; XY → (x, y), ZX → (x, z)
    axis: tuple[float, float, float] | None = None  # takım ekseni (uçtan iş miline), birim; None → +z

    def __post_init__(self) -> None:
        self.type = MoveType(self.type)
        self.end = tuple(float(v) for v in self.end)
        _sonlu(f"Hareket ({self.type.value})", end=self.end)
        if self.center is not None:
            self.center = tuple(float(v) for v in self.center)
            _sonlu(f"Hareket ({self.type.value})", center=self.center)
        if self.feed is not None:
            _sonlu(f"Hareket ({self.type.value})", feed=self.feed)
        if self.axis is not None:
            self.axis = _birim3(f"Hareket ({self.type.value})", "axis", self.axis)


# Düzlem → (u, v, w) eksen indisleri: G3 u'dan v'ye dönüştür, w düzleme dik (helis ekseni).
_UVW = {Plane.XY: (0, 1, 2), Plane.ZX: (2, 0, 1)}


def _center_uv(plane: Plane, center: tuple[float, float]) -> np.ndarray:
    """Merkez tuple'ı (XY: (x, y), ZX: (x, z)) → düzlemin (u, v) koordinatı."""
    if plane is Plane.XY:
        return np.array(center, dtype=float)
    return np.array([center[1], center[0]], dtype=float)  # ZX: u = z, v = x


def _arc_sweep(u0: np.ndarray, u1: np.ndarray, c: np.ndarray, cw: bool) -> tuple[float, float]:
    """Düzlemde (u, v) yay yarıçapı r ve süpürme açısı |Δθ| [rad]. Başlangıç = bitiş ise tam daire (2π)."""
    v0 = u0 - c
    v1 = u1 - c
    r = float(np.hypot(*v0))
    dtheta = math.atan2(v1[1], v1[0]) - math.atan2(v0[1], v0[0])
    if cw:
        dtheta = -dtheta
    dtheta %= 2 * math.pi  # saat yönü tersi için [0, 2π)
    if dtheta < 1e-12:
        dtheta = 2 * math.pi  # aynı nokta: tam daire
    return r, dtheta


@dataclass
class Toolpath:
    name: str
    tool: Tool | LatheTool
    start: tuple[float, float, float]
    moves: list[Move] = field(default_factory=list)
    rpm: float = 0.0  # dev/dk; css verilirse devir üst sınırı (G50)
    plane: Plane = Plane.XY
    feed_mode: FeedMode = FeedMode.PER_MIN
    css: float | None = None  # m/dk, G96 sabit kesme hızı
    frame: Frame | None = None  # start, end, center bu çerçevede (yaylar yerel XY'de); None → WCS

    def __post_init__(self) -> None:
        if self.frame is not None and not isinstance(self.frame, Frame):
            raise CamError(f"Takım yolu '{self.name}': frame Frame olmalı ({type(self.frame).__name__})")
        self.start = tuple(float(v) for v in self.start)
        self.plane = Plane(self.plane)
        self.feed_mode = FeedMode(self.feed_mode)
        _sonlu(f"Takım yolu '{self.name}'", start=self.start)

    def _uv(self, p: np.ndarray) -> np.ndarray:
        iu, iv, _ = _UVW[self.plane]
        return np.array([p[iu], p[iv]])

    def validate(self) -> None:
        """Tutarsızlıkta CamError. Hareketler oluşturulduktan sonra yerinde değiştirilmiş olabilir:
        sonlu sayı kontrolleri burada da tekrarlanır."""
        nerede = f"Takım yolu '{self.name}'"
        _sonlu(nerede, start=self.start, rpm=self.rpm)
        if self.rpm <= 0:
            raise CamError(f"{nerede}: devir pozitif olmalı (rpm={self.rpm})")
        if self.css is not None:
            _sonlu(nerede, css=self.css)
            if self.css <= 0:
                raise CamError(f"{nerede}: sabit kesme hızı pozitif olmalı (css={self.css})")
        torna = isinstance(self.tool, LatheTool)
        if torna and self.plane is not Plane.ZX:
            raise CamError(f"{nerede}: torna yolu ZX (G18) düzleminde olmalı")
        if torna and self.start[1] != 0:
            raise CamError(f"{nerede}: torna yolunda başlangıç y = 0 olmalı (y={self.start[1]})")
        p0 = np.array(self.start)
        for i, m in enumerate(self.moves):
            p1 = np.array(m.end, dtype=float)
            _sonlu(f"Hareket {i} ({m.type.value})", end=p1)
            if m.center is not None:
                _sonlu(f"Hareket {i} ({m.type.value})", center=m.center)
            if m.feed is not None:
                _sonlu(f"Hareket {i} ({m.type.value})", feed=m.feed)
            if torna and p1[1] != 0:
                raise CamError(f"Hareket {i}: torna yolunda y = 0 olmalı (y={p1[1]})")
            if m.axis is not None:
                _birim3(f"Hareket {i} ({m.type.value})", "axis", m.axis)
                if torna:
                    raise CamError(f"Hareket {i}: torna yolunda takım ekseni (axis) verilemez")
                if m.type in ARCS and max(abs(a - b) for a, b in zip(m.axis, Z_AXIS, strict=True)) > UNIT_TOL:
                    raise CamError(f"Hareket {i}: yayda takım ekseni +z olmalı (eş zamanlı 5 eksen yay yok)")
            if m.type is not MoveType.RAPID and (m.feed is None or m.feed <= 0):
                raise CamError(f"Hareket {i} ({m.type.value}): ilerleme pozitif olmalı (feed={m.feed})")
            if m.type in ARCS:
                if m.center is None:
                    raise CamError(f"Hareket {i} ({m.type.value}): yay merkezi yok")
                c = _center_uv(self.plane, m.center)
                r0 = float(np.hypot(*(self._uv(p0) - c)))
                r1 = float(np.hypot(*(self._uv(p1) - c)))
                if r0 < R_MIN:
                    raise CamError(f"Hareket {i}: yay yarıçapı sıfır")
                if abs(r0 - r1) > ARC_TOL:
                    raise CamError(f"Hareket {i}: yay yarıçapları tutmuyor (r0={r0}, r1={r1})")
            p0 = p1

    def points(self) -> np.ndarray:
        """Başlangıç + her hareketin bitiş noktası, (n+1, 3)."""
        return np.array([self.start] + [m.end for m in self.moves], dtype=float)

    def _segments(self):
        p0 = np.array(self.start)
        for m in self.moves:
            p1 = np.array(m.end)
            yield m, p0, p1
            p0 = p1

    def length(self, types: set[MoveType] | None = None) -> float:
        """Toplam yol boyu [mm]. Yay: s = sqrt((r·|Δθ|)² + Δw²), w düzleme dik eksen."""
        w = _UVW[self.plane][2]
        total = 0.0
        for m, p0, p1 in self._segments():
            if types is not None and m.type not in types:
                continue
            if m.type in ARCS:
                c = _center_uv(self.plane, m.center)
                r, dtheta = _arc_sweep(self._uv(p0), self._uv(p1), c, m.type is MoveType.ARC_CW)
                total += math.hypot(r * dtheta, p1[w] - p0[w])
            else:
                total += float(np.linalg.norm(p1 - p0))
        return total

    def bbox(self) -> tuple[np.ndarray, np.ndarray]:
        """Sınır kutusu. Yayların geçtiği düzlem eksen uç noktaları (0°, 90°, 180°, 270°) da dahil."""
        iu, iv, iw = _UVW[self.plane]
        pts = [self.points()]
        for m, p0, p1 in self._segments():
            if m.type not in ARCS:
                continue
            c = _center_uv(self.plane, m.center)
            cw = m.type is MoveType.ARC_CW
            u0 = self._uv(p0)
            r, dtheta = _arc_sweep(u0, self._uv(p1), c, cw)
            theta0 = math.atan2(u0[1] - c[1], u0[0] - c[0])
            for k in range(4):
                phi = k * math.pi / 2
                # başlangıçtan yay yönünde phi'ye kadarki açı
                d = (theta0 - phi) if cw else (phi - theta0)
                d %= 2 * math.pi
                if d <= dtheta:
                    q = np.zeros(3)
                    q[iu] = c[0] + r * math.cos(phi)
                    q[iv] = c[1] + r * math.sin(phi)
                    q[iw] = p0[iw] + (p1[iw] - p0[iw]) * d / dtheta
                    pts.append(q[None, :])
        allp = np.vstack(pts)
        return allp.min(axis=0), allp.max(axis=0)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "tool": self.tool.to_dict(),
            "start": list(self.start),
            "rpm": self.rpm,
            "plane": self.plane.value,
            "feed_mode": self.feed_mode.value,
            "css": self.css,
            "frame": None if self.frame is None else self.frame.to_dict(),
            "moves": [
                {
                    "type": m.type.value,
                    "end": list(m.end),
                    "feed": m.feed,
                    "center": None if m.center is None else list(m.center),
                    "axis": None if m.axis is None else list(m.axis),
                }
                for m in self.moves
            ],
        }

    @classmethod
    def from_dict(cls, d: dict) -> Toolpath:
        return cls(
            name=d["name"],
            tool=tool_from_dict(d["tool"]),
            start=tuple(d["start"]),
            rpm=d["rpm"],
            plane=d.get("plane", Plane.XY),
            feed_mode=d.get("feed_mode", FeedMode.PER_MIN),
            css=d.get("css"),
            frame=None if d.get("frame") is None else Frame.from_dict(d["frame"]),
            moves=[
                Move(
                    type=m["type"],
                    end=tuple(m["end"]),
                    feed=m.get("feed"),
                    center=None if m.get("center") is None else tuple(m["center"]),
                    axis=None if m.get("axis") is None else tuple(m["axis"]),
                )
                for m in d["moves"]
            ],
        )


# ---------------------------------------------------------------- tezgâh profili (SPEC 30, 31, 41)

ROTARY_NAMES = ("A", "B", "C")
CARRIERS = ("masa", "kafa")
CONTROLLERS = ("grbl", "fanuc", "haas", "sinumerik", "heidenhain")
PROGRAM_NO_MAX = {"fanuc": 9999, "haas": 99999}  # dilin program numarası hane sınırı
_NAME_RE = re.compile(r"[A-Z0-9 _-]{1,32}")


@dataclass
class RotaryAxis:
    """Döner eksen: ad A/B/C, taşıyıcı masa veya kafa, eksen yönü u (birim), pivot noktası; açılar derece.

    min ve max ikisi birden None → sürekli eksen; aksi min < max.
    """

    name: str
    carrier: str
    u: tuple[float, float, float]
    pivot: tuple[float, float, float] = (0.0, 0.0, 0.0)
    min: float | None = None
    max: float | None = None

    def __post_init__(self) -> None:
        nerede = f"Döner eksen '{self.name}'"
        if self.name not in ROTARY_NAMES:
            raise CamError(f"{nerede}: ad A, B veya C olmalı")
        if self.carrier not in CARRIERS:
            raise CamError(f"{nerede}: taşıyıcı 'masa' veya 'kafa' olmalı ({self.carrier!r})")
        self.u = _birim3(nerede, "u", self.u)
        self.pivot = _vektor3(nerede, "pivot", self.pivot)
        if (self.min is None) != (self.max is None):
            raise CamError(f"{nerede}: min ve max ikisi birden verilmeli ya da ikisi de None olmalı")
        if self.min is not None:
            _sonlu(nerede, min=self.min, max=self.max)
            if not self.min < self.max:
                raise CamError(f"{nerede}: min < max olmalı ({self.min}, {self.max})")

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "carrier": self.carrier,
            "u": list(self.u),
            "pivot": list(self.pivot),
            "min": self.min,
            "max": self.max,
        }

    @classmethod
    def from_dict(cls, d: dict) -> RotaryAxis:
        _alanlar("Döner eksen", d, {"name", "carrier", "u"}, {"pivot", "min", "max"})
        d = dict(d)
        d["u"] = tuple(d["u"])
        if "pivot" in d:
            d["pivot"] = tuple(d["pivot"])
        return cls(**d)


@dataclass
class Kinematics:
    """Tezgâh kinematiği: en çok 2 döner eksen (her taşıyıcıda sıra tabandan uca),
    iş mili yönü, ölçü noktası."""

    rotary: tuple[RotaryAxis, ...] = ()
    spindle: tuple[float, float, float] = (0.0, 0.0, 1.0)
    gauge: tuple[float, float, float] = (0.0, 0.0, 0.0)

    def __post_init__(self) -> None:
        self.rotary = tuple(self.rotary)
        if not all(isinstance(a, RotaryAxis) for a in self.rotary):
            raise CamError("Kinematik: döner eksenler RotaryAxis olmalı")
        if len(self.rotary) > 2:
            raise CamError(f"Kinematik: en çok 2 döner eksen ({len(self.rotary)})")
        names = [a.name for a in self.rotary]
        if len(set(names)) != len(names):
            raise CamError(f"Kinematik: döner eksen adları tekil olmalı ({names})")
        if len(self.rotary) == 2:
            u1, u2 = (np.array(a.u) for a in self.rotary)
            if np.linalg.norm(np.cross(u1, u2)) <= UNIT_TOL:
                raise CamError("Kinematik: iki döner eksen paralel olamaz")
        self.spindle = _birim3("Kinematik", "spindle", self.spindle)
        self.gauge = _vektor3("Kinematik", "gauge", self.gauge)

    def to_dict(self) -> dict:
        return {
            "rotary": [a.to_dict() for a in self.rotary],
            "spindle": list(self.spindle),
            "gauge": list(self.gauge),
        }

    @classmethod
    def from_dict(cls, d: dict) -> Kinematics:
        _alanlar("Kinematik", d, set(), {"rotary", "spindle", "gauge"})
        return cls(
            rotary=tuple(RotaryAxis.from_dict(a) for a in d.get("rotary", [])),
            spindle=tuple(d.get("spindle", (0.0, 0.0, 1.0))),
            gauge=tuple(d.get("gauge", (0.0, 0.0, 0.0))),
        )


@dataclass(frozen=True)
class AxisLimits:
    """Doğrusal eksen kursu, makine koordinatı [mm]; Z ölçü hattı için."""

    min: float
    max: float

    def validate(self, nerede: str = "Eksen kursu") -> None:
        _sonlu(nerede, min=self.min, max=self.max)
        if not self.min < self.max:
            raise CamError(f"{nerede}: min < max olmalı ({self.min}, {self.max})")

    def to_dict(self) -> dict:
        return {"min": self.min, "max": self.max}

    @classmethod
    def from_dict(cls, d: dict) -> AxisLimits:
        _alanlar("Eksen kursu", d, {"min", "max"}, set())
        return cls(min=d["min"], max=d["max"])


_PROFILE_KEYS = (
    "name", "controller", "kind", "x", "y", "z", "rpm_min", "rpm_max", "feed_max", "rapid",
    "tool_slots", "tool_change_z", "program_no_range", "decimals", "verified", "presets", "kinematics",
    "spindle_power_kw", "spindle_torque_nm",
)  # fmt: skip


@dataclass(frozen=True)
class MachineProfile:
    """Tezgâh profili (SPEC 30). Kurucu doğrulamaz; validate() ve from_dict() denetler."""

    name: str  # ASCII [A-Z0-9 _-], programa yorum olarak yazılır
    controller: str  # grbl | fanuc | haas | sinumerik | heidenhain
    kind: str = "mill"  # mill | lathe (torna: SPEC 40)
    x: AxisLimits | None = (
        None  # None → o eksen denetlenmez; tornada ÇAP cinsinden (yoldaki X yarıçaptır: 2·x ile karşılaştır)
    )
    y: AxisLimits | None = None
    z: AxisLimits | None = None
    rpm_min: float = 0.0
    rpm_max: float = field(kw_only=True)  # zorunlu, > 0
    feed_max: float = field(kw_only=True)  # zorunlu, mm/dk, kesme ilerlemesi üst sınırı
    rapid: tuple[float, float, float] | None = None  # mm/dk, eksen başına
    tool_slots: int | None = None  # None → elle takım değişimi
    tool_change_z: float | None = None
    program_no_range: tuple[int, int] = (1, 9999)
    decimals: int = 3
    verified: bool = False  # kullanıcı profili gerçek tezgâhta kuru çalıştırmayla doğruladı mı
    presets: dict[str, int] | None = None  # yalnız Heidenhain (SPEC 31), değerler ≥ 1
    kinematics: Kinematics | None = None  # None → 3 eksen, döner eksen yok
    spindle_power_kw: float | None = None  # kW, S1 sürekli iş mili gücü; None → denetlenmez
    spindle_torque_nm: float | None = None  # N·m, S1 sürekli iş mili torku; None → denetlenmez

    def validate(self) -> None:
        nerede = f"Tezgâh profili '{self.name}'"
        if not isinstance(self.name, str) or not _NAME_RE.fullmatch(self.name):
            raise CamError(f"{nerede}: ad ASCII [A-Z0-9 _-], 1–32 karakter olmalı")
        if self.controller not in CONTROLLERS:
            raise CamError(f"{nerede}: bilinmeyen dil {self.controller!r} ({', '.join(CONTROLLERS)})")
        if self.kind == "lathe":
            self._torna(nerede)
        elif self.kind != "mill":
            raise CamError(f"{nerede}: tür 'mill' veya 'lathe' olmalı ({self.kind!r})")
        for ad in ("x", "y", "z"):
            lim = getattr(self, ad)
            if lim is not None:
                if not isinstance(lim, AxisLimits):
                    raise CamError(f"{nerede}: {ad} AxisLimits olmalı")
                lim.validate(f"{nerede}: {ad} kursu")
        _sonlu(nerede, rpm_min=self.rpm_min, rpm_max=self.rpm_max, feed_max=self.feed_max)
        if not 0 <= self.rpm_min < self.rpm_max:
            raise CamError(f"{nerede}: 0 ≤ rpm_min < rpm_max olmalı ({self.rpm_min}, {self.rpm_max})")
        if self.feed_max <= 0:
            raise CamError(f"{nerede}: feed_max pozitif olmalı ({self.feed_max})")
        if self.rapid is not None:
            r = _vektor3(nerede, "rapid", self.rapid)
            if min(r) <= 0:
                raise CamError(f"{nerede}: hızlı ilerleme bileşenleri pozitif olmalı ({r})")
        if self.tool_slots is not None and (not _tam_sayi(self.tool_slots) or self.tool_slots < 1):
            raise CamError(f"{nerede}: tool_slots ≥ 1 tam sayı olmalı ({self.tool_slots!r})")
        if self.tool_change_z is not None:
            _sonlu(nerede, tool_change_z=self.tool_change_z)
            if self.z is None:
                raise CamError(f"{nerede}: Z kursu yokken tool_change_z denetlenemez")
            if not self.z.min <= self.tool_change_z <= self.z.max:
                raise CamError(f"{nerede}: tool_change_z Z kursu dışında ({self.tool_change_z})")
        self._program_no(nerede)
        if self.decimals not in (3, 4) or isinstance(self.decimals, bool):
            raise CamError(f"{nerede}: decimals 3 veya 4 olmalı ({self.decimals!r})")
        if not isinstance(self.verified, bool):
            raise CamError(f"{nerede}: verified bool olmalı ({self.verified!r})")
        if self.presets is not None:
            if self.controller != "heidenhain":
                raise CamError(f"{nerede}: presets yalnız Heidenhain'de verilir")
            if any(not _tam_sayi(n) or n < 1 for n in self.presets.values()):
                raise CamError(f"{nerede}: preset numaraları ≥ 1 tam sayı olmalı ({self.presets})")
        if self.kinematics is not None and not isinstance(self.kinematics, Kinematics):
            raise CamError(f"{nerede}: kinematics Kinematics olmalı")
        for ad in ("spindle_power_kw", "spindle_torque_nm"):
            v = getattr(self, ad)
            if v is not None:
                _sonlu(nerede, **{ad: v})
                if v <= 0:
                    raise CamError(f"{nerede}: {ad} pozitif olmalı ({v})")

    def _torna(self, nerede: str) -> None:
        """Torna profili (SPEC 40 E1): yalnız Fanuc; Y, takım değiştirme Z, kinematik, preset yok;
        X (çap) ve Z kursu birlikte ya da hiç."""
        if self.controller != "fanuc":
            raise CamError(f"{nerede}: torna profili yalnız fanuc dilinde ({self.controller!r})")
        for ad in ("y", "tool_change_z", "kinematics", "presets"):
            if getattr(self, ad) is not None:
                raise CamError(f"{nerede}: torna profilinde {ad} verilmez")
        if (self.x is None) != (self.z is None):
            raise CamError(f"{nerede}: tornada X ve Z kursu birlikte verilir ya da hiç verilmez")

    def _program_no(self, nerede: str) -> None:
        rng = tuple(self.program_no_range)
        if len(rng) != 2 or not all(_tam_sayi(n) for n in rng):
            raise CamError(f"{nerede}: program_no_range iki tam sayı olmalı ({self.program_no_range!r})")
        lo, hi = rng
        if not 1 <= lo <= hi:
            raise CamError(f"{nerede}: 1 ≤ program_no_range[0] ≤ program_no_range[1] olmalı ({rng})")
        sinir = PROGRAM_NO_MAX.get(self.controller)
        if sinir is not None and hi > sinir:
            raise CamError(f"{nerede}: {self.controller} program numarası en çok {sinir} ({hi})")

    def to_dict(self) -> dict:
        def lim(a: AxisLimits | None) -> dict | None:
            return None if a is None else a.to_dict()

        return {
            "name": self.name,
            "controller": self.controller,
            "kind": self.kind,
            "x": lim(self.x),
            "y": lim(self.y),
            "z": lim(self.z),
            "rpm_min": self.rpm_min,
            "rpm_max": self.rpm_max,
            "feed_max": self.feed_max,
            "rapid": None if self.rapid is None else list(self.rapid),
            "tool_slots": self.tool_slots,
            "tool_change_z": self.tool_change_z,
            "program_no_range": list(self.program_no_range),
            "decimals": self.decimals,
            "verified": self.verified,
            "presets": None if self.presets is None else dict(self.presets),
            "kinematics": None if self.kinematics is None else self.kinematics.to_dict(),
            "spindle_power_kw": self.spindle_power_kw,
            "spindle_torque_nm": self.spindle_torque_nm,
        }

    @classmethod
    def from_dict(cls, d: dict) -> MachineProfile:
        """Bilinmeyen / eksik anahtar veya geçersiz değer → CamError."""
        zorunlu = {"name", "controller", "rpm_max", "feed_max"}
        _alanlar("Tezgâh profili", d, zorunlu, set(_PROFILE_KEYS) - zorunlu)
        d = dict(d)
        for ad in ("x", "y", "z"):
            if d.get(ad) is not None:
                d[ad] = AxisLimits.from_dict(d[ad])
        if d.get("rapid") is not None:
            d["rapid"] = tuple(d["rapid"])
        if "program_no_range" in d:
            d["program_no_range"] = tuple(d["program_no_range"])
        if d.get("kinematics") is not None:
            d["kinematics"] = Kinematics.from_dict(d["kinematics"])
        m = cls(**d)
        m.validate()
        return m


def _tam_sayi(n) -> bool:
    return isinstance(n, int) and not isinstance(n, bool)


# ---------------------------------------------------------------- giriş biçimi (SPEC 03c)


class EntryKind(StrEnum):
    PLUNGE = "dalma"
    RAMP = "rampa"
    HELIX = "helis"


@dataclass
class EntryMode:
    """Cebe / kontura giriş biçimi. Takıma bağlı sınırlar (merkezden kesmeyen takımla dalma,
    angle ≤ Tool.ramp_angle_max) işlem fonksiyonunda (SPEC 03c) denetlenir."""

    kind: EntryKind = EntryKind.PLUNGE
    angle: float = 2.0  # derece, yataydan iniş açısı α, 0 < α < 90
    radius: float | None = None  # mm, helis yarıçapı; yalnız HELIX
    length: float | None = None  # mm, rampa boyu; yalnız RAMP

    def __post_init__(self) -> None:
        nerede = "Giriş biçimi"
        try:
            self.kind = EntryKind(self.kind)
        except ValueError as e:
            raise CamError(f"{nerede}: bilinmeyen tür {self.kind!r}") from e
        _sonlu(nerede, angle=self.angle)
        if not 0 < self.angle < 90:
            raise CamError(f"{nerede}: açı 0 < α < 90 olmalı ({self.angle})")
        for ad, tur in (("radius", EntryKind.HELIX), ("length", EntryKind.RAMP)):
            v = getattr(self, ad)
            if v is None:
                continue
            if self.kind is not tur:
                raise CamError(f"{nerede}: {ad} yalnız {tur.value} girişinde verilir")
            _sonlu(nerede, **{ad: v})
            if v <= 0:
                raise CamError(f"{nerede}: {ad} pozitif olmalı ({v})")

    def to_dict(self) -> dict:
        return {"kind": self.kind.value, "angle": self.angle, "radius": self.radius, "length": self.length}

    @classmethod
    def from_dict(cls, d: dict) -> EntryMode:
        _alanlar("Giriş biçimi", d, set(), {"kind", "angle", "radius", "length"})
        return cls(**d)


# ---------------------------------------------------------------- bağlama (SPEC 10)

FIXTURE_KINDS = ("mengene", "ayna", "pabuc", "ozel")
_FIXTURE_NAME_RE = re.compile(r"[A-Za-z0-9 _/-]{1,64}")


def _birim_frame() -> Frame:
    return Frame((0.0, 0.0, 0.0), ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)))


@dataclass(frozen=True)
class Fixture:
    """Şekilli bağlama gövdesi. OCCT'siz: gövdenin kendisi değil anahtarı (part_ref) tutulur;
    anahtarı geometry.part.Part'a çevirmek SPEC 10'un işidir."""

    name: str  # [A-Za-z0-9 _/-]{1,64}; '/' montaj yaprak yolu ad olabilsin diye
    part_ref: str  # gövde anahtarı (montaj bileşeni / proje içi dosya), boş olamaz
    frame: Frame = field(default_factory=_birim_frame)  # yerel → WCS
    kind: str = "ozel"  # mengene | ayna | pabuc | ozel
    params: tuple[tuple[str, float], ...] = ()  # kütüphane iç ölçüleri: ada göre sıralı, tekil, sonlu

    def __post_init__(self) -> None:
        nerede = f"Bağlama '{self.name}'"
        if not isinstance(self.name, str) or not _FIXTURE_NAME_RE.fullmatch(self.name):
            raise CamError(f"{nerede}: ad [A-Za-z0-9 _/-], 1–64 karakter olmalı")
        if not isinstance(self.part_ref, str) or not self.part_ref:
            raise CamError(f"{nerede}: part_ref boş olmayan metin olmalı ({self.part_ref!r})")
        if not isinstance(self.frame, Frame):
            raise CamError(f"{nerede}: frame bir Frame olmalı")
        if self.kind not in FIXTURE_KINDS:
            raise CamError(f"{nerede}: tür {', '.join(FIXTURE_KINDS)} olmalı ({self.kind!r})")
        try:
            params = tuple((ad, float(v)) for ad, v in self.params)
        except (TypeError, ValueError) as e:
            raise CamError(f"{nerede}: params (ad, değer) çiftleri olmalı") from e
        adlar = [ad for ad, _ in params]
        if any(not isinstance(ad, str) or not ad for ad in adlar):
            raise CamError(f"{nerede}: params adları boş olmayan metin olmalı")
        if adlar != sorted(adlar) or len(set(adlar)) != len(adlar):
            raise CamError(f"{nerede}: params ada göre sıralı ve tekil olmalı ({adlar})")
        _sonlu(nerede, params=[v for _, v in params])
        object.__setattr__(self, "params", params)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "part_ref": self.part_ref,
            "frame": self.frame.to_dict(),
            "kind": self.kind,
            "params": dict(self.params),
        }

    @classmethod
    def from_dict(cls, d: dict) -> Fixture:
        _alanlar("Bağlama", d, {"name", "part_ref"}, {"frame", "kind", "params"})
        d = dict(d)
        if "frame" in d:
            d["frame"] = Frame.from_dict(d["frame"])
        if "params" in d:
            p = d["params"]
            if not isinstance(p, dict):
                raise CamError("Bağlama: params sözlük olmalı")
            d["params"] = tuple(sorted(p.items()))
        return cls(**d)
