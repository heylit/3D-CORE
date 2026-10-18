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


def _sonlu(nerede: str, **degerler) -> None:
    """Her değer (sayı veya sayı dizisi) sonlu olmalı; nan / inf → CamError. Sessiz hata yok."""
    for ad, v in degerler.items():
        if not np.all(np.isfinite(np.asarray(v, dtype=float))):
            raise CamError(f"{nerede}: {ad} sonlu olmalı ({ad}={v})")


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
        }

    @classmethod
    def from_dict(cls, d: dict) -> Tool:
        _alanlar(
            "Takım",
            d,
            {"id", "name", "kind", "D", "flute_length"},
            {"corner_r", "flutes", "shank_d", "stickout", "holder", "cutting", "center_cutting"},
        )
        d = dict(d)
        if d.get("holder") is not None:
            d["holder"] = ToolHolder.from_dict(d["holder"])
        d["cutting"] = _cutting_from_dict(d.get("cutting") or {})
        return cls(**d)


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
        }

    @classmethod
    def from_dict(cls, d: dict) -> LatheTool:
        zorunlu = {"id", "name", "kind", "nose_r", "tip", "kappa_r", "eps_r"}
        _alanlar("Torna takımı", d, zorunlu, {"width", "cutting"})
        d = dict(d)
        d["cutting"] = _cutting_from_dict(d.get("cutting") or {})
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


# ---------------------------------------------------------------- hareketler, takım yolu


@dataclass
class Move:
    type: MoveType
    end: tuple[float, float, float]
    feed: float | None = None  # G1/G2/G3 için zorunlu; birimi Toolpath.feed_mode
    center: tuple[float, float] | None = None  # yay merkezi, mutlak; XY → (x, y), ZX → (x, z)

    def __post_init__(self) -> None:
        self.type = MoveType(self.type)
        self.end = tuple(float(v) for v in self.end)
        _sonlu(f"Hareket ({self.type.value})", end=self.end)
        if self.center is not None:
            self.center = tuple(float(v) for v in self.center)
            _sonlu(f"Hareket ({self.type.value})", center=self.center)
        if self.feed is not None:
            _sonlu(f"Hareket ({self.type.value})", feed=self.feed)


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

    def __post_init__(self) -> None:
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
            "moves": [
                {
                    "type": m.type.value,
                    "end": list(m.end),
                    "feed": m.feed,
                    "center": None if m.center is None else list(m.center),
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
            moves=[
                Move(
                    type=m["type"],
                    end=tuple(m["end"]),
                    feed=m.get("feed"),
                    center=None if m.get("center") is None else tuple(m["center"]),
                )
                for m in d["moves"]
            ],
        )
