"""
SPEC 10 — Bağlama (fikstür) kütüphanesi ve montaj-CAM köprüsü.

Parametrik mengene, üç çeneli torna aynası ve pabuç; sıkma denetimi; temkinli bağlama üst yüzey haritası;
SPEC 05 simülasyon sonucuna ek fikstür çarpışması; montaj ağacından CAM kurulumuna ve geri dönüş.
Saf Python + numpy (OCCT yok); `assy` paketinden yalnız `assy.model.Node` kullanılır.
Birimler: mm, derece. Hatalar `cam.model.CamError`. Hiçbir fonksiyon girdisini değiştirmez.

Çerçeve: Frame p_wcs = origin + R·p_yerel, 4x4 karşılığı T = [[R, origin], [0, 1]].
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, fields

import numpy as np

from assy.model import Node
from cam.gcode import DrillOp
from cam.model import (
    CamError,
    CylinderStock,
    Fixture,
    Frame,
    Move,
    MoveType,
    Setup,
    Stock,
    Tool,
    ToolKind,
    Toolpath,
    Wcs,
)
from cam.sim import SimResult, body_steps, simulate, sweep_envelope
from cam.sim.sweep import flat_min_z
from cam.sim.timing import arc_geometry
from geometry.part import Part

TOL_EKSEN = 1e-9  # yerel Z'nin WCS Z'ye paralelliği, R = I denetimi
ARCS = (MoveType.ARC_CW, MoveType.ARC_CCW)


def _birim() -> Frame:
    return Frame((0.0, 0.0, 0.0), ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)))


def _rz(deg: float) -> tuple:
    """Z çevresinde dönme (satır satır); 90°'nin katlarında tam değerler (gürültüsüz)."""
    tam = {0: (1.0, 0.0), 90: (0.0, 1.0), 180: (-1.0, 0.0), 270: (0.0, -1.0)}
    k = deg % 360
    if k in tam:
        c, s = tam[k]
    else:
        c, s = math.cos(math.radians(deg)), math.sin(math.radians(deg))
    return ((c, -s, 0.0), (s, c, 0.0), (0.0, 0.0, 1.0))


def _T(fr: Frame) -> np.ndarray:
    T = np.eye(4)
    T[:3, :3] = np.array(fr.R)
    T[:3, 3] = fr.origin
    return T


def _frame(T: np.ndarray) -> Frame:
    return Frame(tuple(float(v) for v in T[:3, 3]), tuple(tuple(float(v) for v in r) for r in T[:3, :3]))


def _compose(dis: Frame, ic: Frame) -> Frame:
    """dis ∘ ic: önce ic, sonra dis."""
    Ro, Ri = np.array(dis.R), np.array(ic.R)
    o = Ro @ np.array(ic.origin) + np.array(dis.origin)
    return Frame(tuple(float(v) for v in o), tuple(tuple(float(v) for v in r) for r in Ro @ Ri))


def _ters(T: np.ndarray) -> np.ndarray:
    """Rijit dönüşümün tersi [[Rᵀ, −Rᵀ t], [0, 1]]."""
    R, t = T[:3, :3], T[:3, 3]
    Ti = np.eye(4)
    Ti[:3, :3] = R.T
    Ti[:3, 3] = -R.T @ t
    return Ti


def _z_paralel(fr: Frame) -> bool:
    return bool(np.allclose(np.array(fr.R)[:, 2], (0.0, 0.0, 1.0), atol=TOL_EKSEN))


def _pozitif(nerede: str, **degerler) -> None:
    for ad, v in degerler.items():
        if isinstance(v, bool) or not isinstance(v, int | float) or not math.isfinite(v) or v <= 0:
            raise CamError(f"{nerede}: {ad} pozitif ve sonlu olmalı ({ad}={v!r})")


# ---------------------------------------------------------------- ilkel cisimler


@dataclass(frozen=True)
class Primitive:
    """Bağlama elemanının yerel çerçevesinde bir kutu ya da Z eksenli silindir."""

    shape: Stock | CylinderStock
    frame: Frame = field(default_factory=_birim)

    def __post_init__(self) -> None:
        if not isinstance(self.shape, Stock | CylinderStock):
            raise CamError(f"İlkel: şekil Stock veya CylinderStock olmalı ({type(self.shape).__name__})")
        if not isinstance(self.frame, Frame):
            raise CamError("İlkel: frame bir Frame olmalı")

    def to_dict(self) -> dict:
        """{"shape": shape.to_dict(), "frame": frame.to_dict()}"""
        return {"shape": self.shape.to_dict(), "frame": self.frame.to_dict()}

    @property
    def volume(self) -> float:
        return self.shape.volume

    def corners(self) -> np.ndarray:
        """Kutunun 8 köşesi WCS'de (frame ile taşınmış), (8, 3)."""
        s = self.shape
        K = np.array(
            [[x, y, z] for x in (s.xmin, s.xmax) for y in (s.ymin, s.ymax) for z in (s.zmin, s.zmax)]
        )
        return self.frame.to_world(K)

    def aabb(self) -> tuple[np.ndarray, np.ndarray]:
        """Eksenlere hizalı sınır kutusu (lo, hi): kutuda köşeler, silindirde eksen ± yarıçap."""
        s = self.shape
        if isinstance(s, Stock):
            P = self.corners()
            return P.min(axis=0), P.max(axis=0)
        a = self.frame.to_world(np.array([0.0, 0.0, s.zmin]))
        b = self.frame.to_world(np.array([0.0, 0.0, s.zmax]))
        ax = (b - a) / np.linalg.norm(b - a)
        pay = s.D / 2 * np.sqrt(np.clip(1 - ax**2, 0.0, None))
        return np.minimum(a, b) - pay, np.maximum(a, b) + pay


def _kutu(xmin, ymin, zmin, xmax, ymax, zmax, frame: Frame | None = None) -> Primitive:
    s = Stock(xmin, ymin, zmin, xmax, ymax, zmax)
    return Primitive(s) if frame is None else Primitive(s, frame)


# ---------------------------------------------------------------- kütüphane


class _Olculu:
    """params() / from_params ortak gövdesi (dataclass alanları = ölçüler)."""

    def params(self) -> dict[str, float]:
        return {f.name: float(getattr(self, f.name)) for f in fields(self)}

    @classmethod
    def from_params(cls, d: Mapping[str, float]):
        if not isinstance(d, Mapping):
            raise CamError(f"{cls.__name__}: params sözlük olmalı")
        adlar = {f.name for f in fields(cls)}
        eksik, fazla = adlar - d.keys(), d.keys() - adlar
        if eksik or fazla:
            raise CamError(f"{cls.__name__}: eksik ölçü {sorted(eksik)}, bilinmeyen ölçü {sorted(fazla)}")
        return cls(**{k: d[k] for k in adlar})


@dataclass(frozen=True)
class Vise(_Olculu):
    """Mengene; yerel orijin açıklığın ortası, yatak üstünde; sıkma yönü yerel Y."""

    jaw_width: float
    jaw_thickness: float
    jaw_height: float
    opening: float
    bed_height: float = 40.0
    bed_extra: float = 60.0
    parallel: float = 0.0
    parallel_width: float = 6.0

    def __post_init__(self) -> None:
        _pozitif(
            "Mengene",
            jaw_width=self.jaw_width,
            jaw_thickness=self.jaw_thickness,
            jaw_height=self.jaw_height,
            opening=self.opening,
            bed_height=self.bed_height,
            bed_extra=self.bed_extra,
            parallel_width=self.parallel_width,
        )
        p = self.parallel
        if isinstance(p, bool) or not isinstance(p, int | float) or not math.isfinite(p) or p < 0:
            raise CamError(f"Mengene: paralel yüksekliği ≥ 0 ve sonlu olmalı ({p!r})")
        if self.parallel_width >= self.opening / 2:
            raise CamError(
                f"Mengene: paralel genişliği açıklığın yarısından küçük olmalı ({self.parallel_width})"
            )

    def primitives(self) -> list[Primitive]:
        """Sabit çene, hareketli çene, yatak, (p > 0 ise) iki paralel."""
        b2, t, hj, w2 = self.jaw_width / 2, self.jaw_thickness, self.jaw_height, self.opening / 2
        pr = [
            _kutu(-b2, -w2 - t, 0, b2, -w2, hj),
            _kutu(-b2, w2, 0, b2, w2 + t, hj),
            _kutu(-b2, -w2 - t, -self.bed_height, b2, w2 + t + self.bed_extra, 0),
        ]
        if self.parallel > 0:
            wp, p = self.parallel_width, self.parallel
            pr += [_kutu(-b2, -w2, 0, b2, -w2 + wp, p), _kutu(-b2, w2 - wp, 0, b2, w2, p)]
        return pr


@dataclass(frozen=True)
class Chuck3(_Olculu):
    """Üç çeneli torna aynası; yerel orijin eksende ayna alnında, +Z stoğa doğru."""

    grip_d: float
    jaw_length: float
    body_d: float = 160.0
    body_length: float = 80.0
    jaw_height: float = 25.0
    jaw_width: float = 20.0

    def __post_init__(self) -> None:
        _pozitif(
            "Ayna",
            grip_d=self.grip_d,
            jaw_length=self.jaw_length,
            body_d=self.body_d,
            body_length=self.body_length,
            jaw_height=self.jaw_height,
            jaw_width=self.jaw_width,
        )
        if self.jaw_width >= math.sqrt(3) * self.grip_d:
            raise CamError(
                f"Ayna: çene genişliği √3·d'den küçük olmalı (w_j={self.jaw_width}, d={self.grip_d})"
            )

    def primitives(self) -> list[Primitive]:
        """Gövde, çeneler 90°, 210°, 330°."""
        r, h, w2 = self.grip_d / 2, self.jaw_height, self.jaw_width / 2
        pr = [Primitive(CylinderStock(self.body_d, -self.body_length, 0.0))]
        for th in (90.0, 210.0, 330.0):
            pr.append(_kutu(r, -w2, 0, r + h, w2, self.jaw_length, Frame((0.0, 0.0, 0.0), _rz(th))))
        return pr

    def outer_radius(self) -> float:
        """Çene köşesinin en büyük yarıçapı r_o = √((d/2 + h)² + (w_j/2)²)."""
        return math.hypot(self.grip_d / 2 + self.jaw_height, self.jaw_width / 2)

    def rings(self, frame: Frame) -> list[CylinderStock]:
        """[çene halkası (D = 2 r_o, d = grip_d), gövde]; frame.R = I ve eksen x = y = 0 olmalı."""
        if not np.allclose(np.array(frame.R), np.eye(3), atol=TOL_EKSEN):
            raise CamError("Ayna halkaları: çerçevenin R'si birim olmalı (iş mili ekseni WCS Z)")
        if abs(frame.origin[0]) > TOL_EKSEN or abs(frame.origin[1]) > TOL_EKSEN:
            raise CamError(f"Ayna halkaları: ayna ekseni x = y = 0'da olmalı ({frame.origin})")
        zf = frame.origin[2]
        return [
            CylinderStock(2 * self.outer_radius(), zf, zf + self.jaw_length, d=self.grip_d),
            CylinderStock(self.body_d, zf - self.body_length, zf),
        ]


@dataclass(frozen=True)
class Clamp(_Olculu):
    """Pabuç (kol + topuk + cıvata); yerel orijin burnun alt kenarında, kol −X yönünde."""

    support_height: float
    arm_length: float = 80.0
    arm_width: float = 20.0
    arm_thickness: float = 12.0
    bolt_d: float = 12.0
    bolt_above: float = 15.0
    heel_width: float = 15.0

    def __post_init__(self) -> None:
        _pozitif(
            "Pabuç",
            support_height=self.support_height,
            arm_length=self.arm_length,
            arm_width=self.arm_width,
            arm_thickness=self.arm_thickness,
            bolt_d=self.bolt_d,
            bolt_above=self.bolt_above,
            heel_width=self.heel_width,
        )
        if self.arm_width < self.bolt_d:
            raise CamError(
                f"Pabuç: kol genişliği cıvata çapından küçük olamaz ({self.arm_width} < {self.bolt_d})"
            )
        if self.heel_width + self.bolt_d / 2 >= self.arm_length / 2:
            raise CamError("Pabuç: topuk ve cıvata kolun ortasını geçiyor (w_h + d_b/2 < L_a/2 olmalı)")

    def primitives(self) -> list[Primitive]:
        """Kol, topuk, cıvata."""
        La, w2, ta, Hs = self.arm_length, self.arm_width / 2, self.arm_thickness, self.support_height
        return [
            _kutu(-La, -w2, 0, 0, w2, ta),
            _kutu(-La, -w2, -Hs, -La + self.heel_width, w2, 0),
            Primitive(
                CylinderStock(self.bolt_d, -Hs, ta + self.bolt_above),
                Frame((-La / 2, 0.0, 0.0), _birim().R),
            ),
        ]


_TURLER: dict[str, type] = {"mengene": Vise, "ayna": Chuck3, "pabuc": Clamp}


def _olculer(nerede: str, olculer: dict, yasak: set[str]) -> None:
    if yasak & olculer.keys():
        raise CamError(f"{nerede}: {sorted(yasak & olculer.keys())} yerleşimden hesaplanır, verilemez")


def vise_for(stock: Stock, grip: float, axis: str = "x", **olculer) -> tuple[Vise, Frame]:
    """Mengeneyi stoğa yerleştirir: tutma yüksekliği grip, paralel p = h_j − g,
    origin (x_c, y_c, zmin − p)."""
    if not isinstance(stock, Stock):
        raise CamError(f"Mengene: kutu stok gerekir ({type(stock).__name__})")
    _pozitif("Mengene", grip=grip)
    _olculer("Mengene", olculer, {"opening", "parallel"})
    olcu = {"jaw_width": 100.0, "jaw_thickness": 20.0, "jaw_height": 40.0, **olculer}
    if axis == "x":
        w, R = stock.ymax - stock.ymin, _birim().R
    elif axis == "y":
        w, R = stock.xmax - stock.xmin, _rz(90)
    else:
        raise CamError(f"Mengene: axis 'x' veya 'y' olmalı ({axis!r})")
    H = stock.zmax - stock.zmin
    if grip >= H:
        raise CamError(
            f"Mengene: tutma yüksekliği stok yüksekliğine ulaşıyor (g={grip} ≥ {H}); üst yüz işlenemez"
        )
    p = olcu["jaw_height"] - grip
    if p < 0:
        raise CamError(f"Mengene: çene yüksekliği tutma için yetmiyor (h_j={olcu['jaw_height']} < g={grip})")
    v = Vise(opening=w, parallel=p, **olcu)
    xc, yc = (stock.xmin + stock.xmax) / 2, (stock.ymin + stock.ymax) / 2
    return v, Frame((xc, yc, stock.zmin - p), R)


def chuck_for(stock: CylinderStock, grip: float, **olculer) -> tuple[Chuck3, Frame]:
    """Aynayı torna çubuğuna yerleştirir: d = stock.D, L_j = grip, alın z = stock.zmin."""
    if not isinstance(stock, CylinderStock):
        raise CamError(f"Ayna: silindir stok gerekir ({type(stock).__name__})")
    _pozitif("Ayna", grip=grip)
    _olculer("Ayna", olculer, {"grip_d", "jaw_length"})
    if grip >= stock.length:
        raise CamError(f"Ayna: tutma boyu stok boyuna ulaşıyor ({grip} ≥ {stock.length})")
    return Chuck3(grip_d=stock.D, jaw_length=grip, **olculer), Frame((0.0, 0.0, stock.zmin), _birim().R)


def clamp_for(stock: Stock, side: str, at: float, overlap: float, **olculer) -> tuple[Clamp, Frame]:
    """Pabucu stok kenarına yerleştirir: burun stok üstünde, kenardan overlap içeride, kenar boyunca at'ta."""
    if not isinstance(stock, Stock):
        raise CamError(f"Pabuç: kutu stok gerekir ({type(stock).__name__})")
    _olculer("Pabuç", olculer, {"support_height"})
    c = Clamp(support_height=stock.zmax - stock.zmin, **olculer)
    for ad, v in (("at", at), ("overlap", overlap)):
        if isinstance(v, bool) or not isinstance(v, int | float) or not math.isfinite(v):
            raise CamError(f"Pabuç: {ad} sonlu olmalı ({v!r})")
    o = overlap
    if o <= 0:
        raise CamError(f"Pabuç: overlap pozitif olmalı ({o})")
    if o >= c.arm_length / 2 - c.bolt_d / 2:
        raise CamError(f"Pabuç: overlap = {o} cıvatayı stoğa sokuyor (< L_a/2 − d_b/2 olmalı)")
    s = stock
    tablo = {
        "x-": (_birim().R, (s.xmin + o, at, s.zmax), s.xmax - s.xmin, (s.ymin, s.ymax)),
        "x+": (_rz(180), (s.xmax - o, at, s.zmax), s.xmax - s.xmin, (s.ymin, s.ymax)),
        "y-": (_rz(90), (at, s.ymin + o, s.zmax), s.ymax - s.ymin, (s.xmin, s.xmax)),
        "y+": (_rz(-90), (at, s.ymax - o, s.zmax), s.ymax - s.ymin, (s.xmin, s.xmax)),
    }
    if side not in tablo:
        raise CamError(f"Pabuç: side 'x-', 'x+', 'y-', 'y+' olmalı ({side!r})")
    R, origin, boy, (a, b) = tablo[side]
    if o > boy:
        raise CamError(f"Pabuç: overlap stok boyunu aşıyor ({o} > {boy})")
    w2 = c.arm_width / 2
    if not a + w2 <= at <= b - w2:
        raise CamError(f"Pabuç: at = {at} kenarın içinde değil ([{a + w2}, {b - w2}])")
    return c, Frame(tuple(float(v) for v in origin), R)


def make_fixture(name: str, item: Vise | Chuck3 | Clamp, frame: Frame) -> Fixture:
    for kind, cls in _TURLER.items():
        if isinstance(item, cls):
            params = tuple(sorted(item.params().items()))
            return Fixture(name=name, part_ref=name, frame=frame, kind=kind, params=params)
    raise CamError(f"Bağlama: kütüphane elemanı bekleniyor ({type(item).__name__})")


def from_fixture(fx: Fixture) -> Vise | Chuck3 | Clamp:
    if fx.kind not in _TURLER:
        raise CamError(f"Bağlama '{fx.name}': tür '{fx.kind}' kütüphane elemanı değil")
    return _TURLER[fx.kind].from_params(dict(fx.params))


def primitives_wcs(fx: Fixture) -> list[Primitive]:
    return [Primitive(p.shape, _compose(fx.frame, p.frame)) for p in from_fixture(fx).primitives()]


def _parca(fx: Fixture, parts: Mapping[str, Part] | None) -> Part:
    if parts is None or fx.part_ref not in parts:
        raise CamError(f"Bağlama '{fx.name}': '{fx.part_ref}' parçası verilmedi (parts)")
    return parts[fx.part_ref]


def _kose_kutusu(T: np.ndarray, lo, hi) -> tuple[np.ndarray, np.ndarray]:
    K = np.array([[x, y, z, 1.0] for x in (lo[0], hi[0]) for y in (lo[1], hi[1]) for z in (lo[2], hi[2])])
    P = (T @ K.T).T[:, :3]
    return P.min(axis=0), P.max(axis=0)


def _stok(lo, hi) -> Stock:
    return Stock(*(float(v) for v in lo), *(float(v) for v in hi))


def envelope(fx: Fixture, parts: Mapping[str, Part] | None = None) -> list[Stock]:
    if fx.kind == "ozel":
        lo, hi = _parca(fx, parts).bbox
        return [_stok(*_kose_kutusu(_T(fx.frame), lo, hi))]
    return [_stok(*p.aabb()) for p in primitives_wcs(fx)]


# ---------------------------------------------------------------- sıkma denetimi


def _kutu_xy(p: Primitive) -> np.ndarray:
    """Z'ye paralel kutunun XY ayak izi köşeleri (4, 2), sırayla."""
    s = p.shape
    yerel = np.array(
        [[s.xmin, s.ymin, 0], [s.xmax, s.ymin, 0], [s.xmax, s.ymax, 0], [s.xmin, s.ymax, 0]], float
    )
    return p.frame.to_world(yerel)[:, :2]


def _z_araligi(p: Primitive) -> tuple[float, float]:
    oz = p.frame.origin[2]
    return oz + p.shape.zmin, oz + p.shape.zmax


def _eksenler(kose: np.ndarray) -> list[np.ndarray]:
    """Ayırma ekseni testi için x, y ve dikdörtgenin iki kenar normali."""
    eks = [np.array([1.0, 0.0]), np.array([0.0, 1.0])]
    for e in (kose[1] - kose[0], kose[3] - kose[0]):
        n = np.array([-e[1], e[0]]) / np.hypot(*e)
        # 90°'nin katlarında cos/sin artığı (~1e-16) eksen dışı izdüşüm hatası yapmasın
        n[np.abs(n) < 1e-12] = 0.0
        eks.append(n / np.hypot(*n))
    return eks


def _icten_kesisir(p: Primitive, s: Stock, tol: float) -> bool:
    """İlkel ile kutu stoğun iç kısımları kesişiyor mu (her eksende örtüşme > tol)."""
    if not _z_paralel(p.frame):
        raise CamError("Sıkma denetimi: yerel Z'si WCS Z'ye paralel olmayan ilkel desteklenmez")
    z0, z1 = _z_araligi(p)
    if min(z1, s.zmax) - max(z0, s.zmin) <= tol:
        return False
    if isinstance(p.shape, CylinderStock):
        cx, cy = p.frame.origin[0], p.frame.origin[1]
        ux = max(s.xmin - cx, 0.0, cx - s.xmax)
        uy = max(s.ymin - cy, 0.0, cy - s.ymax)
        return math.hypot(ux, uy) < p.shape.D / 2 - tol
    kose = _kutu_xy(p)
    stok = np.array([[s.xmin, s.ymin], [s.xmax, s.ymin], [s.xmax, s.ymax], [s.xmin, s.ymax]])
    for ax in _eksenler(kose):
        a, b = kose @ ax, stok @ ax
        if min(a.max(), b.max()) - max(a.min(), b.min()) <= tol:
            return False
    return True


def check_clamping(
    stock: Stock | CylinderStock,
    fixtures: Sequence[Fixture],
    parts: Mapping[str, Part] | None = None,
    tol_l: float = 1e-9,
    tol_v: float = 1e-6,
) -> None:
    """Bağlama elemanları stoğa değebilir ama içine giremez; ilk ihlalde CamError."""
    if isinstance(stock, CylinderStock):
        for fx in fixtures:
            if fx.kind != "ayna":
                raise CamError(f"Bağlama '{fx.name}': silindir stokta yalnız ayna denetlenir")
            c = from_fixture(fx)
            if abs(c.grip_d - stock.D) > 1e-9:
                raise CamError(f"Bağlama '{fx.name}': ayna tutma çapı {c.grip_d} ≠ stok çapı {stock.D}")
        return
    if not isinstance(stock, Stock):
        raise CamError(f"Sıkma denetimi: Stock veya CylinderStock bekleniyor ({type(stock).__name__})")
    for fx in fixtures:
        if fx.kind == "ozel":
            _ozel_sikma(fx, stock, parts, tol_v)
            continue
        for i, p in enumerate(primitives_wcs(fx)):
            if _icten_kesisir(p, stock, tol_l):
                raise CamError(f"Bağlama '{fx.name}': {i}. ilkel stoğun içine giriyor")


def _ozel_sikma(fx: Fixture, stock: Stock, parts, tol_v: float) -> None:
    # Kütüphane dışı gövde: kesin B-rep kesişimi (SPEC 09 Part.common). Stok kutusu katısı bu SPEC'in
    # geometry/baglama_parca.py dosyasıyla kurulur; OCCT yalnız bu yolda ve geç yüklenir.
    from geometry.baglama_parca import primitives_part

    govde = _parca(fx, parts).moved(_T(fx.frame))
    kutu = primitives_part([Primitive(stock).to_dict()], "stok")
    if govde.common(kutu, tol_v) is not None:
        raise CamError(f"Bağlama '{fx.name}': gövde stoğun içine giriyor (kesişim hacmi > {tol_v})")


def fixture_top(fixtures: Sequence[Fixture], parts: Mapping[str, Part] | None = None) -> float:
    if not fixtures:
        raise CamError("fixture_top: bağlama listesi boş")
    return max(b.zmax for fx in fixtures for b in envelope(fx, parts))


# ---------------------------------------------------------------- üst yüzey haritası


@dataclass
class FixtureMap:
    """Bir bağlamanın WCS XY sınır kutusundaki temkinli üst yüzey haritası; top (ny, nx), değmeyen -inf."""

    fixture: str
    x0: float
    y0: float
    dx: float
    dy: float
    nx: int
    ny: int
    top: np.ndarray

    def centers(self) -> tuple[np.ndarray, np.ndarray]:
        x = self.x0 + (np.arange(self.nx) + 0.5) * self.dx
        y = self.y0 + (np.arange(self.ny) + 0.5) * self.dy
        return np.meshgrid(x, y)


def _hucre_kenarlari(g: FixtureMap):
    xa = g.x0 + np.arange(g.nx) * g.dx
    ya = g.y0 + np.arange(g.ny) * g.dy
    XA, YA = np.meshgrid(xa, ya)
    return XA, XA + g.dx, YA, YA + g.dy


def primitive_topmap(prims: Sequence[Primitive], grid: FixtureMap) -> np.ndarray:
    """Hücrenin kapalı dikdörtgenine değen ilkellerin üst Z'lerinin en büyüğü; değmeyen −inf."""
    XA, XB, YA, YB = _hucre_kenarlari(grid)
    top = np.full((grid.ny, grid.nx), -np.inf)
    for p in prims:
        if not _z_paralel(p.frame):
            raise CamError(
                "Üst yüzey haritası: yerel Z'si WCS Z'ye paralel olmayan ilkel (ağ yolunu kullanın)"
            )
        z_ust = _z_araligi(p)[1]
        if isinstance(p.shape, CylinderStock):
            cx, cy = p.frame.origin[0], p.frame.origin[1]
            ux = np.maximum.reduce([XA - cx, np.zeros_like(XA), cx - XB])
            uy = np.maximum.reduce([YA - cy, np.zeros_like(YA), cy - YB])
            degiyor = np.hypot(ux, uy) <= p.shape.D / 2
        else:
            kose = _kutu_xy(p)
            hucre = [(XA, YA), (XB, YA), (XB, YB), (XA, YB)]
            degiyor = np.ones(XA.shape, dtype=bool)
            for ax in _eksenler(kose):
                pk = kose @ ax
                h = np.stack([X * ax[0] + Y * ax[1] for X, Y in hucre])
                degiyor &= (h.max(axis=0) >= pk.min()) & (pk.max() >= h.min(axis=0))
        top = np.where(degiyor, np.maximum(top, z_ust), top)
    return top


def mesh_topmap(V: np.ndarray, F: np.ndarray, frame: Frame, grid: FixtureMap) -> np.ndarray:
    """Üçgen ağı (yerel) çerçeveyle WCS'ye taşır; üçgenler XY kenarı ≤ min(dx, dy) olana dek dörde bölünür,
    her alt üçgenin XY sınır kutusunun değdiği hücrelere alt üçgenin en büyük Z'si yazılır."""
    V = frame.to_world(np.asarray(V, dtype=float))
    F = np.asarray(F, dtype=np.int64)
    top = np.full((grid.ny, grid.nx), -np.inf)
    d_min = min(grid.dx, grid.dy)
    for tri in V[F]:
        A, B, C = tri
        kenar = max(np.hypot(*(B - A)[:2]), np.hypot(*(C - B)[:2]), np.hypot(*(A - C)[:2]))
        n = 1
        while kenar / n > d_min:
            n *= 2
        _boya(top, grid, _alt_ucgenler(A, B, C, n))
    return top


def _alt_ucgenler(A, B, C, n: int) -> np.ndarray:
    """Orta noktalardan n = 2^k kez bölünmüş üçgenin alt üçgenleri (m, 3, 3)."""
    i, j = np.meshgrid(np.arange(n), np.arange(n), indexing="ij")
    yukari = (i + j) <= n - 1
    asagi = (i + j) <= n - 2

    def P(a, b):
        return A + (a[..., None] / n) * (B - A) + (b[..., None] / n) * (C - A)

    iu, ju = i[yukari], j[yukari]
    up = np.stack([P(iu, ju), P(iu + 1, ju), P(iu, ju + 1)], axis=1)
    idn, jdn = i[asagi], j[asagi]
    dn = np.stack([P(idn + 1, jdn), P(idn, jdn + 1), P(idn + 1, jdn + 1)], axis=1)
    return np.concatenate([up, dn])


def _boya(top: np.ndarray, g: FixtureMap, T: np.ndarray) -> None:
    lo, hi = T.min(axis=1), T.max(axis=1)
    z = hi[:, 2]
    i0 = np.ceil((lo[:, 0] - g.x0) / g.dx - 1).astype(np.int64)
    i1 = np.floor((hi[:, 0] - g.x0) / g.dx).astype(np.int64)
    j0 = np.ceil((lo[:, 1] - g.y0) / g.dy - 1).astype(np.int64)
    j1 = np.floor((hi[:, 1] - g.y0) / g.dy).astype(np.int64)
    # alt üçgen kutusu ≤ hücre: eksen başına en çok 3 hücre
    for di in range(3):
        for dj in range(3):
            ii, jj = i0 + di, j0 + dj
            ok = (ii <= i1) & (jj <= j1) & (ii >= 0) & (jj >= 0) & (ii < g.nx) & (jj < g.ny)
            # kapalı kesişim: hücre kenarlarıyla kesin karşılaştırma
            xa = g.x0 + ii * g.dx
            ya = g.y0 + jj * g.dy
            ok &= (xa <= hi[:, 0]) & (xa + g.dx >= lo[:, 0]) & (ya <= hi[:, 1]) & (ya + g.dy >= lo[:, 1])
            np.maximum.at(top, (jj[ok], ii[ok]), z[ok])


def _xy_kutusu(fx: Fixture, parts) -> tuple[np.ndarray, np.ndarray]:
    if fx.kind == "ozel":
        lo, hi = _parca(fx, parts).bbox
        return _kose_kutusu(_T(fx.frame), lo, hi)
    kutular = [p.aabb() for p in primitives_wcs(fx)]
    return np.min([k[0] for k in kutular], axis=0), np.max([k[1] for k in kutular], axis=0)


def fixture_map(
    fx: Fixture,
    cell: float,
    parts: Mapping[str, Part] | None = None,
    mesh_tol: float = 0.01,
    max_cells: int = 4_000_000,
) -> FixtureMap:
    if isinstance(cell, bool) or not isinstance(cell, int | float) or not math.isfinite(cell) or cell <= 0:
        raise CamError(f"Bağlama haritası: hücre boyu pozitif ve sonlu olmalı (cell={cell})")
    lo, hi = _xy_kutusu(fx, parts)
    Lx, Ly = hi[0] - lo[0], hi[1] - lo[1]
    nx = max(1, math.ceil(Lx / cell - 1e-12))
    ny = max(1, math.ceil(Ly / cell - 1e-12))
    if nx * ny > max_cells:
        raise CamError(f"Bağlama haritası çok büyük: {nx}×{ny} hücre > {max_cells}")
    g = FixtureMap(fx.name, float(lo[0]), float(lo[1]), Lx / nx, Ly / ny, nx, ny, np.full((ny, nx), -np.inf))
    if fx.kind == "ozel":
        V, F = _parca(fx, parts).mesh(mesh_tol)
        g.top = mesh_topmap(V, F, fx.frame, g)
    else:
        g.top = primitive_topmap(primitives_wcs(fx), g)
    return g


# ---------------------------------------------------------------- fikstür çarpışması


@dataclass(frozen=True)
class FixtureCollision:
    fixture: str
    k: int
    op: int
    part: str  # "kesici" | "sap" | "tutucu"
    at: tuple[float, float, float]
    depth: float


def _kirisler(p0: np.ndarray, m: Move, arc_tol: float) -> list[tuple[np.ndarray, np.ndarray]]:
    """Doğru → tek parça; yay → SPEC 05 kiriş kuralıyla kirişler (Z doğrusal paylaşılır)."""
    p1 = np.array(m.end, dtype=float)
    if m.type not in ARCS:
        return [(p0, p1)]
    cw = m.type is MoveType.ARC_CW
    r, dth, th0 = arc_geometry(p0, p1, m.center, cw)
    adim = 2 * math.acos(1 - arc_tol / r) if arc_tol < r else math.pi / 2
    n = max(1, math.ceil(dth / adim - 1e-12))
    s = -1.0 if cw else 1.0
    cx, cy = m.center
    pts = [p0]
    for i in range(1, n):
        th = th0 + s * dth * i / n
        pts.append(np.array([cx + r * math.cos(th), cy + r * math.sin(th), p0[2] + (p1[2] - p0[2]) * i / n]))
    pts.append(p1)
    return list(zip(pts[:-1], pts[1:], strict=True))


def _sisik_kesici(tool: Tool, delta: float) -> Tool:
    """Kesici profili δ kadar şişirilmiş takım: h_δ(d) = h(max(0, d − δ)), d ≤ R + δ."""
    R = tool.D / 2
    rc = 0.0 if tool.kind is ToolKind.DRILL else float(tool.corner_r)
    return Tool(tool.id, tool.name, ToolKind.FLAT, 2 * (R + delta), tool.flute_length, corner_r=rc)


def _takim(op) -> Tool:
    tool = op.tool
    if not isinstance(tool, Tool):
        raise CamError(f"Fikstür çarpışması: freze takımı bekleniyor ({type(tool).__name__})")
    return tool


def fixture_collisions(
    ops: list[Toolpath | DrillOp],
    result: SimResult,
    maps: Sequence[FixtureMap],
    arc_tol: float = 1e-3,
    tol: float = 1e-6,
) -> list[FixtureCollision]:
    for ad, v in (("arc_tol", arc_tol), ("tol", tol)):
        if isinstance(v, bool) or not isinstance(v, int | float) or not math.isfinite(v) or v <= 0:
            raise CamError(f"Fikstür çarpışması: {ad} pozitif ve sonlu olmalı ({v!r})")
    for s in result.steps:
        if not 0 <= s.op < len(ops):
            raise CamError(f"Fikstür çarpışması: adım {s.k} op {s.op} verilen {len(ops)} işlemle uyuşmuyor")
    hazir = []  # (harita, merkezler, δ)
    for g in maps:
        X, Y = g.centers()
        hazir.append((g, X, Y, math.hypot(g.dx, g.dy) / 2))
    araclar: dict[int, tuple[Tool, list]] = {}
    kayit: dict[tuple[int, str], FixtureCollision] = {}
    for s in result.steps:
        if s.op not in araclar:
            t = _takim(ops[s.op])
            araclar[s.op] = (t, body_steps(t))
        tool, govde = araclar[s.op]
        m = Move(s.type, s.end, s.feed, s.center)
        for a, b in _kirisler(np.array(s.start, dtype=float), m, arc_tol):
            for g, X, Y, delta in hazir:
                c = _parca_carpisma(g, X, Y, delta, tool, govde, a, b, s.k, s.op, tol)
                if c is None:
                    continue
                anahtar = (s.k, g.fixture)
                if anahtar not in kayit or c.depth > kayit[anahtar].depth:
                    kayit[anahtar] = c
    return [kayit[k] for k in sorted(kayit)]


def _parca_carpisma(g, X, Y, delta, tool, govde, a, b, k, op, tol) -> FixtureCollision | None:
    # pencere: kirişin XY kutusu ± en geniş (şişirilmiş) gövde yarıçapı
    rho = max([tool.D / 2] + [r for r, _, _ in govde]) + delta
    xlo, xhi = min(a[0], b[0]) - rho, max(a[0], b[0]) + rho
    ylo, yhi = min(a[1], b[1]) - rho, max(a[1], b[1]) + rho
    i0 = max(0, math.floor((xlo - g.x0) / g.dx))
    i1 = min(g.nx, math.ceil((xhi - g.x0) / g.dx) + 1)
    j0 = max(0, math.floor((ylo - g.y0) / g.dy))
    j1 = min(g.ny, math.ceil((yhi - g.y0) / g.dy) + 1)
    if i0 >= i1 or j0 >= j1:
        return None
    w = (slice(j0, j1), slice(i0, i1))
    Xw, Yw, top = X[w], Y[w], g.top[w]
    if not np.isfinite(top).any():
        return None
    e = sweep_envelope(_sisik_kesici(tool, delta), a, b, Xw, Yw)
    parca = np.zeros(e.shape, dtype=np.int64)  # 0 kesici, j + 1 gövde basamağı j
    for j, (r, H, _) in enumerate(govde):
        eb = H + flat_min_z(a, b, Xw, Yw, r + delta)
        daha = eb < e
        e = np.where(daha, eb, e)
        parca = np.where(daha, j + 1, parca)
    fark = np.where(np.isfinite(top) & np.isfinite(e), top - e, -np.inf)
    idx = np.unravel_index(np.argmax(fark), fark.shape)
    depth = float(fark[idx])
    if not depth > tol:
        return None
    pj = int(parca[idx])
    tur = "kesici" if pj == 0 else govde[pj - 1][2]
    at = (float(Xw[idx]), float(Yw[idx]), float(e[idx]))
    return FixtureCollision(g.fixture, k, op, tur, at, depth)


@dataclass
class SetupSim:
    sim: SimResult
    fixture_collisions: list[FixtureCollision]
    maps: list[FixtureMap]


def simulate_setup(
    ops: list[Toolpath | DrillOp],
    stock: Stock,
    fixtures: Sequence[Fixture],
    parts: Mapping[str, Part] | None = None,
    cell: float = 1.0,
    fixture_cell: float | None = None,
    **sim_kwargs,
) -> SetupSim:
    adlar = [fx.name for fx in fixtures]
    if len(set(adlar)) != len(adlar):
        raise CamError(f"simulate_setup: bağlama adları tekil olmalı ({adlar})")
    sim = simulate(ops, stock, cell, **sim_kwargs)
    fc = cell if fixture_cell is None else fixture_cell
    maps = [fixture_map(fx, fc, parts) for fx in fixtures]
    kw = {k: sim_kwargs[k] for k in ("arc_tol", "tol") if k in sim_kwargs}
    return SetupSim(sim, fixture_collisions(ops, sim, maps, **kw), maps)


# ---------------------------------------------------------------- montaj köprüsü


@dataclass
class AssemblySetup:
    setup: Setup
    workpiece: str  # yaprak yolu
    part: str  # parça kimliği
    T_part: np.ndarray  # parçanın yerelinden WCS'ye, 4x4
    fixtures: list[Fixture] = field(default_factory=list)


def _dugumler(root: Node) -> dict[str, tuple[Node, np.ndarray]]:
    """Yol → (düğüm, dünya dönüşümü); yol biçimi SPEC 07 walk ile aynı (kök "")."""
    sonuc: dict[str, tuple[Node, np.ndarray]] = {}

    def gez(n: Node, yol: str, T: np.ndarray) -> None:
        Tw = T @ np.asarray(n.T, dtype=float)
        sonuc[yol] = (n, Tw)
        for c in n.children:
            gez(c, c.name if not yol else f"{yol}/{c.name}", Tw)

    gez(root, "", np.eye(4))
    return sonuc


def from_assembly(
    root: Node,
    parts: Mapping[str, Part],
    workpiece: str,
    wcs: str | Frame,
    fixtures: Sequence[str],
    name: str = "baglama",
    code: str = "G54",
    origin=(0.0, 0.0, 0.0),
    margin: float | tuple[float, float, float] = 0.0,
    kinds: Mapping[str, Fixture] | None = None,
) -> AssemblySetup:
    d = _dugumler(root)

    def yaprak(yol: str, ne: str) -> Node:
        if yol not in d:
            raise CamError(f"Montaj: bilinmeyen yol '{yol}' ({ne})")
        n = d[yol][0]
        if n.part is None:
            raise CamError(f"Montaj: '{yol}' yaprak değil ({ne})")
        if n.part not in parts:
            raise CamError(f"Montaj: '{n.part}' parçası verilmedi ({ne} '{yol}')")
        return n

    is_n = yaprak(workpiece, "iş parçası")
    if len(set(fixtures)) != len(fixtures):
        raise CamError(f"Montaj: bağlama yolları yineleniyor ({list(fixtures)})")
    if workpiece in fixtures:
        raise CamError(f"Montaj: iş parçası '{workpiece}' bağlama listesinde")
    bag_n = [yaprak(y, "bağlama") for y in fixtures]
    kinds = dict(kinds or {})
    if set(kinds) - set(fixtures):
        fazla = sorted(set(kinds) - set(fixtures))
        raise CamError(f"Montaj: kinds anahtarı bağlama listesinde değil ({fazla})")
    m = np.broadcast_to(np.asarray(margin, dtype=float), (3,))
    if not np.all(np.isfinite(m)) or np.any(m < 0):
        raise CamError(f"Montaj: margin ≥ 0 ve sonlu olmalı ({margin})")
    if isinstance(wcs, Frame):
        W = _T(wcs)
    else:
        if wcs not in d:
            raise CamError(f"Montaj: bilinmeyen WCS yolu '{wcs}'")
        W = d[wcs][1]
    Wi = _ters(W)
    T_part = Wi @ d[workpiece][1]
    lo, hi = _kose_kutusu(T_part, *parts[is_n.part].bbox)
    stock = _stok(lo - m, hi + m)
    fxs = []
    for yol, n in zip(fixtures, bag_n, strict=True):
        fr = _frame(Wi @ d[yol][1])
        lib = kinds.get(yol)
        if lib is None:
            fxs.append(Fixture(name=yol, part_ref=n.part, frame=fr, kind="ozel"))
        else:
            fxs.append(Fixture(name=yol, part_ref=n.part, frame=fr, kind=lib.kind, params=lib.params))
    zarf = [b for fx in fxs for b in envelope(fx, parts)]
    setup = Setup(name, Wcs(code, tuple(origin)), stock, fixtures=zarf)
    return AssemblySetup(setup, workpiece, is_n.part, T_part, fxs)


def to_assembly(job: AssemblySetup, name: str = "baglama") -> Node:
    cocuklar = [Node("is_parcasi", T=np.array(job.T_part, dtype=float), part=job.part)]
    for fx in job.fixtures:
        cocuklar.append(Node(fx.name.replace("/", "__"), T=_T(fx.frame), part=fx.part_ref))
    return Node(name, T=np.eye(4), children=cocuklar)
