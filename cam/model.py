"""
3D-CORE CAM veri modeli.

CAM katmanının (takım yolu, G-code, simülasyon) ortak dili. Saf Python + numpy; OCCT gerektirmez.

Birimler:
    uzunluk  : mm
    ilerleme : mm/dk
    devir    : dev/dk

Hareketler G-code anlamıyla aynıdır (ISO 6983): G0 hızlı, G1 doğrusal, G2 saat yönü yay,
G3 saat yönü tersi yay (+Z'den bakınca). Yaylar XY düzleminde (G17); Z değişirse helis.
Yay merkezi mutlak XY koordinatıdır.
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


def _ek2(*_args, **_kwargs):
    """SPEC 00 Ek 2 iskeleti: henüz uygulanmadı."""
    raise NotImplementedError("SPEC 00 Ek 2")


def _sonlu(nerede: str, **degerler) -> None:
    """Her değer (sayı veya sayı dizisi) sonlu olmalı; nan / inf → CamError. Sessiz hata yok."""
    for ad, v in degerler.items():
        if not np.all(np.isfinite(np.asarray(v, dtype=float))):
            raise CamError(f"{nerede}: {ad} sonlu olmalı ({ad}={v})")


@dataclass
class Tool:
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

    def __post_init__(self) -> None:
        yeni = (self.flutes, self.shank_d, self.stickout, self.holder, self.cutting)
        if yeni != (None, None, None, None, {}):
            raise NotImplementedError("Tool yeni alanları (SPEC 00 Ek 2)")
        self.kind = ToolKind(self.kind)
        _sonlu(f"Takım '{self.name}'", D=self.D, flute_length=self.flute_length, corner_r=self.corner_r)
        if self.D <= 0:
            raise CamError(f"Takım '{self.name}': D pozitif olmalı (D={self.D})")
        if self.flute_length <= 0:
            raise CamError(f"Takım '{self.name}': kesici boy pozitif olmalı ({self.flute_length})")
        if self.kind is ToolKind.BALL:
            self.corner_r = self.D / 2
        if not 0 <= self.corner_r <= self.D / 2:
            raise CamError(f"Takım '{self.name}': köşe radyüsü 0..D/2 olmalı ({self.corner_r})")

    @property
    def shank(self) -> float:
        raise NotImplementedError("SPEC 00 Ek 2")

    @property
    def gauge_length(self) -> float | None:
        raise NotImplementedError("SPEC 00 Ek 2")

    def to_dict(self) -> dict:
        raise NotImplementedError("SPEC 00 Ek 2")

    @classmethod
    def from_dict(cls, d: dict) -> Tool:
        raise NotImplementedError("SPEC 00 Ek 2")


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

    to_dict = _ek2
    from_dict = classmethod(_ek2)


# ---------------------------------------------------------------- SPEC 00 Ek 2 iskeleti (uygulanacak)


@dataclass
class CuttingData:
    Vc: float  # m/dk
    fz: float | None = None  # mm/diş (freze)
    fn: float | None = None  # mm/dev (torna)
    ap: float | None = None  # mm
    ae: float | None = None  # mm

    __post_init__ = _ek2
    to_dict = _ek2
    from_dict = classmethod(_ek2)


@dataclass
class ToolHolder:
    name: str
    gauge_length: float  # mm, ölçü hattı → tutucu ağzı
    profile: tuple[tuple[float, float], ...]  # (z, r)

    __post_init__ = _ek2
    to_dict = _ek2
    from_dict = classmethod(_ek2)


@dataclass
class LatheTool:
    id: int
    name: str
    kind: LatheToolKind
    nose_r: float
    tip: int
    kappa_r: float
    eps_r: float
    width: float = 0.0
    cutting: dict[str, CuttingData] = field(default_factory=dict)

    __post_init__ = _ek2
    to_dict = _ek2
    from_dict = classmethod(_ek2)


def tool_from_dict(d: dict) -> Tool | LatheTool:
    raise NotImplementedError("SPEC 00 Ek 2")


@dataclass
class ToolLibrary:
    tools: list[Tool | LatheTool] = field(default_factory=list)

    __post_init__ = _ek2
    validate = _ek2
    get = _ek2
    add = _ek2
    to_dict = _ek2
    from_dict = classmethod(_ek2)


@dataclass
class CylinderStock:
    D: float
    zmin: float
    zmax: float
    d: float = 0.0

    __post_init__ = _ek2
    length = property(_ek2)
    volume = property(_ek2)
    bbox = _ek2
    to_dict = _ek2
    from_dict = classmethod(_ek2)


@dataclass
class Wcs:
    code: str = "G54"
    origin: tuple[float, float, float] = (0.0, 0.0, 0.0)

    __post_init__ = _ek2
    to_machine = _ek2
    to_work = _ek2
    to_dict = _ek2
    from_dict = classmethod(_ek2)


@dataclass
class Setup:
    name: str
    wcs: Wcs
    stock: Stock | CylinderStock
    fixtures: list[Stock | CylinderStock] = field(default_factory=list)

    __post_init__ = _ek2
    to_dict = _ek2
    from_dict = classmethod(_ek2)


@dataclass
class Move:
    type: MoveType
    end: tuple[float, float, float]
    feed: float | None = None  # mm/dk; G1/G2/G3 için zorunlu
    center: tuple[float, float] | None = None  # yay merkezi, mutlak XY

    def __post_init__(self) -> None:
        self.type = MoveType(self.type)
        self.end = tuple(float(v) for v in self.end)
        _sonlu(f"Hareket ({self.type.value})", end=self.end)
        if self.center is not None:
            self.center = tuple(float(v) for v in self.center)
            _sonlu(f"Hareket ({self.type.value})", center=self.center)
        if self.feed is not None:
            _sonlu(f"Hareket ({self.type.value})", feed=self.feed)


def _arc_sweep(p0: np.ndarray, p1: np.ndarray, c: np.ndarray, cw: bool) -> tuple[float, float]:
    """XY'de yay yarıçapı r ve süpürme açısı |Δθ| [rad]. Başlangıç = bitiş ise tam daire (2π)."""
    v0 = p0[:2] - c
    v1 = p1[:2] - c
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
    rpm: float = 0.0
    plane: Plane = Plane.XY
    feed_mode: FeedMode = FeedMode.PER_MIN
    css: float | None = None  # m/dk, G96 sabit kesme hızı

    def __post_init__(self) -> None:
        if (self.plane, self.feed_mode, self.css) != (Plane.XY, FeedMode.PER_MIN, None) or isinstance(
            self.tool, LatheTool
        ):
            raise NotImplementedError("Toolpath plane / feed_mode / css / torna (SPEC 00 Ek 2)")
        self.start = tuple(float(v) for v in self.start)
        _sonlu(f"Takım yolu '{self.name}'", start=self.start)

    def validate(self) -> None:
        """Tutarsızlıkta CamError. Hareketler oluşturulduktan sonra yerinde değiştirilmiş olabilir:
        sonlu sayı kontrolleri burada da tekrarlanır."""
        _sonlu(f"Takım yolu '{self.name}'", start=self.start, rpm=self.rpm)
        if self.rpm <= 0:
            raise CamError(f"Takım yolu '{self.name}': devir pozitif olmalı (rpm={self.rpm})")
        p0 = np.array(self.start)
        for i, m in enumerate(self.moves):
            p1 = np.array(m.end, dtype=float)
            _sonlu(f"Hareket {i} ({m.type.value})", end=p1)
            if m.center is not None:
                _sonlu(f"Hareket {i} ({m.type.value})", center=m.center)
            if m.feed is not None:
                _sonlu(f"Hareket {i} ({m.type.value})", feed=m.feed)
            if m.type is not MoveType.RAPID and (m.feed is None or m.feed <= 0):
                raise CamError(f"Hareket {i} ({m.type.value}): ilerleme pozitif olmalı (feed={m.feed})")
            if m.type in ARCS:
                if m.center is None:
                    raise CamError(f"Hareket {i} ({m.type.value}): yay merkezi yok")
                c = np.array(m.center)
                r0 = float(np.hypot(*(p0[:2] - c)))
                r1 = float(np.hypot(*(p1[:2] - c)))
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
        """Toplam yol boyu [mm]. Yay: s = sqrt((r·|Δθ|)² + Δz²)."""
        total = 0.0
        for m, p0, p1 in self._segments():
            if types is not None and m.type not in types:
                continue
            if m.type in ARCS:
                r, dtheta = _arc_sweep(p0, p1, np.array(m.center), m.type is MoveType.ARC_CW)
                total += math.hypot(r * dtheta, p1[2] - p0[2])
            else:
                total += float(np.linalg.norm(p1 - p0))
        return total

    def bbox(self) -> tuple[np.ndarray, np.ndarray]:
        """Sınır kutusu. Yayların geçtiği eksen uç noktaları (0°, 90°, 180°, 270°) da dahil."""
        pts = [self.points()]
        for m, p0, p1 in self._segments():
            if m.type not in ARCS:
                continue
            c = np.array(m.center)
            cw = m.type is MoveType.ARC_CW
            r, dtheta = _arc_sweep(p0, p1, c, cw)
            theta0 = math.atan2(p0[1] - c[1], p0[0] - c[0])
            for k in range(4):
                phi = k * math.pi / 2
                # başlangıçtan yay yönünde phi'ye kadarki açı
                d = (theta0 - phi) if cw else (phi - theta0)
                d %= 2 * math.pi
                if d <= dtheta:
                    z = p0[2] + (p1[2] - p0[2]) * d / dtheta
                    pts.append(np.array([[c[0] + r * math.cos(phi), c[1] + r * math.sin(phi), z]]))
        allp = np.vstack(pts)
        return allp.min(axis=0), allp.max(axis=0)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "tool": {**self.tool.__dict__, "kind": self.tool.kind.value},
            "start": list(self.start),
            "rpm": self.rpm,
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
            tool=Tool(**d["tool"]),
            start=tuple(d["start"]),
            rpm=d["rpm"],
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
