"""
SPEC 29 — Otomatik işlem planı (freze): SPEC 27 özelliklerinden SPEC 03 / 04 işlemlerine, takım ve kesme
verisi SPEC 14 kütüphanesinden, işlem sırası, bağlama (gerekirse alt yüz için ikinci bağlama), G-code.

Planlanamayan her özellik gerekçe koduyla `Unplanned` olur; hiçbir özellik sessizce atlanmaz.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass, field

from cam import ops2d
from cam.cutting import SpindleFeed, milling
from cam.features import Features, recognize
from cam.gcode import GRBL, Dialect, DrillOp, write
from cam.model import (
    CamError,
    CylinderStock,
    Setup,
    Stock,
    Tool,
    ToolKind,
    ToolLibrary,
    Toolpath,
    Wcs,
)
from cam.offset import offset
from cam.ops2d import Cut
from cam.profile import Arc, Profile, Region
from cam.setups import check_setup, clearance_height
from cam.tool_length import length_offsets
from geometry.part import Part

KINDS = ("yuz_alma", "acik_bolge", "cep", "cep_kalan", "delik", "lamba")
UNPLANNED_CODES = (
    "kesme_verisi_yok",
    "takim_yok",
    "takim_sigmiyor",
    "kesici_boy_yetmez",
    "ustten_erisilemez",
    "havsa_takimi_yok",
    "kilavuz_cevrimi_yok",
    "baglama_carpismasi",
    "on_delik_yok",
    "genel_girinti",
)
NOTE_CODES = ("kose_artigi", "yan_paso_kisildi", "delik_tasma_kisildi", "ikinci_baglama")
ANG = 1e-6  # yön toleransı (SPEC 27 ile aynı)
S_RATIO = 0.5  # yan paso üst sınırı s_max = D/2 (SPEC 03 Ek A)


@dataclass(frozen=True)
class PlannedOp:
    name: str  # f"{sıra:02d}-{kind}-T{tool_id}", sıra 1'den, bağlamalar boyunca sürer
    kind: str
    setup: int  # 0 → setups[0], 1 → setups[1]
    feature: str  # özellik adresi; delik grubunda "holes[i,j,...]"
    tool_id: int
    op: Toolpath | DrillOp
    spindle: SpindleFeed
    a_p: float | None
    stepover: float | None


@dataclass(frozen=True)
class Unplanned:
    feature: str
    code: str
    detail: str


@dataclass(frozen=True)
class PlanNote:
    feature: str
    code: str
    value: float
    detail: str


@dataclass(frozen=True)
class MillOptions:
    n_max: float | None = None
    rest: bool = True
    plunge_ratio: float = 0.3
    clearance: float = 1.0
    open_margin: float = 1.0
    drill_tol: float = 0.01
    breakthrough: float = 1.0
    peck_limit: float = 3.0
    peck_q: float = 1.0
    hole_d_max: float = 20.0
    tol: float = 1e-3
    strict: bool = False


DEFAULT_OPTIONS = MillOptions()  # dondurulmuş: paylaşılan varsayılan güvenli


@dataclass(frozen=True)
class MillPlan:
    material: str
    features: Features
    setups: tuple[Setup, ...]
    ops: tuple[PlannedOp, ...]
    unplanned: tuple[Unplanned, ...]
    notes: tuple[PlanNote, ...]

    def ops_for(self, setup: int) -> list[Toolpath | DrillOp]:
        """Bir bağlamanın işlemleri, plan sırasıyla."""
        return [o.op for o in self.ops if o.setup == setup]

    def tool_changes(self) -> int:
        """Bağlama içinde ardışık farklı takım geçişleri + her bağlamanın ilk takımı."""
        n = 0
        for i in range(len(self.setups)):
            onceki = None
            for o in self.ops:
                if o.setup == i and o.tool_id != onceki:
                    n += 1
                    onceki = o.tool_id
        return n

    def summary(self) -> list[dict]:
        """Op başına {name, kind, setup, feature, tool_id, n, F, a_p, stepover}."""
        return [_ozet(o) for o in self.ops]

    def gcode(self, lib: ToolLibrary, dialect: Dialect = GRBL, program_no: int = 1) -> list[str]:
        """Bağlama başına bir program (SPEC 04 / 14 `write`)."""
        out = []
        for i, setup in enumerate(self.setups):
            ops = self.ops_for(i)
            if not ops:
                continue
            ids = list(dict.fromkeys(o.tool_id for o in self.ops if o.setup == i))
            lo = length_offsets(lib, ids, ref_id=ids[0]) if dialect.name == GRBL.name else None
            out.append(write(ops, dialect, program_no=program_no + i, setup=setup, length_offsets=lo))
        return out


def _ozet(o: PlannedOp) -> dict:
    return {
        "name": o.name,
        "kind": o.kind,
        "setup": o.setup,
        "feature": o.feature,
        "tool_id": o.tool_id,
        "n": o.spindle.n,
        "F": o.spindle.F,
        "a_p": o.a_p,
        "stepover": o.stepover,
    }


# ---------------------------------------------------------------- girdi denetimi


def _sayi(v) -> bool:
    return not isinstance(v, bool) and isinstance(v, (int, float)) and math.isfinite(v)


def _secenek(ad: str, v, alt: float, kapali: bool) -> None:
    """v sonlu ve v ≥ alt (kapali) ya da v > alt olmalı."""
    if not _sayi(v) or (v < alt if kapali else v <= alt):
        isaret = "≥" if kapali else ">"
        raise CamError(f"İşlem planı: {ad} sonlu ve {isaret} {alt:g} olmalı ({v!r})")


def check_common(material, lib) -> None:
    """Malzeme adı ve kütüphane (freze ve torna planı ortak)."""
    if not isinstance(material, str) or not material:
        raise CamError(f"İşlem planı: malzeme boş olmayan bir ad olmalı ({material!r})")
    if not isinstance(lib, ToolLibrary):
        raise CamError(f"İşlem planı: lib ToolLibrary olmalı ({type(lib).__name__})")
    lib.validate()


def _check_options(o: MillOptions) -> None:
    if not isinstance(o, MillOptions):
        raise CamError(f"İşlem planı: options MillOptions olmalı ({type(o).__name__})")
    if o.n_max is not None:
        _secenek("n_max", o.n_max, 0.0, False)
    _secenek("plunge_ratio", o.plunge_ratio, 0.0, False)
    if o.plunge_ratio > 1:
        raise CamError(f"İşlem planı: plunge_ratio (0, 1] aralığında olmalı ({o.plunge_ratio})")
    for ad in ("clearance", "open_margin", "drill_tol", "breakthrough"):
        _secenek(ad, getattr(o, ad), 0.0, True)
    for ad in ("peck_limit", "peck_q", "hole_d_max", "tol"):
        _secenek(ad, getattr(o, ad), 0.0, False)


# ---------------------------------------------------------------- geometri yardımcıları


def _r_corner(region: Region) -> float:
    """SPEC 27 §8: ccw yayların yarıçapı ve keskin sola dönüşler (0) arasında en küçüğü; yoksa inf."""
    r = math.inf
    for loop in region.loops:
        segs = loop.segments
        for k, s in enumerate(segs):
            if isinstance(s, Arc) and s.ccw:
                r = min(r, s.R)
            t1, t2 = segs[k - 1].tangent(1.0), s.tangent(0.0)
            if float(t1[0] * t2[1] - t1[1] * t2[0]) > ANG:
                r = 0.0
    return r


def _corner_area(region: Region, r: float) -> float:
    """§3: dışbükey köşelerde A = (r² − R_c²)·(tan(φ/2) − φ/2), yalnız r > R_c olanlar."""
    A = 0.0
    for loop in region.loops:
        segs = loop.segments
        for k, s in enumerate(segs):
            if isinstance(s, Arc) and s.ccw and s.R < r:
                A += (r * r - s.R * s.R) * (math.tan(s.sweep / 2) - s.sweep / 2)
            t1, t2 = segs[k - 1].tangent(1.0), s.tangent(0.0)
            cross = float(t1[0] * t2[1] - t1[1] * t2[0])
            if cross > ANG:
                phi = math.atan2(cross, float(t1 @ t2))
                A += r * r * (math.tan(phi / 2) - phi / 2)
    return A


def _sigar(omega: Region | None, tool: Tool) -> bool:
    """Takım bölgeye sığar ⇔ offset(Ω, D/2) ≠ [] (yüz almada bölge yok: her zaman)."""
    if omega is None:
        return True
    try:
        return offset(omega, tool.D / 2) != []
    except CamError:
        return False


# ---------------------------------------------------------------- planlayıcı


@dataclass
class _Plan:
    """Plan kurulurken biriken durum (dışarı verilmez)."""

    stock: Stock
    lib: ToolLibrary
    material: str
    o: MillOptions
    setups: list[Setup]
    ops: list[tuple[str, int, str, Toolpath | DrillOp, SpindleFeed, float | None, float | None, int]] = field(
        default_factory=list
    )  # (kind, setup, feature, op, spindle, a_p, stepover, tool_id)
    unplanned: list[Unplanned] = field(default_factory=list)
    notes: list[PlanNote] = field(default_factory=list)

    # ------------------------------------------------ ortak

    def fail(self, feature: str, code: str, detail: str) -> None:
        self.unplanned.append(Unplanned(feature, code, detail))

    def note(self, feature: str, code: str, value: float, detail: str) -> None:
        n = PlanNote(feature, code, float(value), detail)
        if n not in self.notes:
            self.notes.append(n)

    def add(self, kind, setup, feature, op, sf, a_p, s, tool) -> bool:
        """Bağlama denetiminden geçerse işlemi ekler; geçmezse baglama_carpismasi."""
        try:
            check_setup(self.setups[setup], [op])
        except CamError as e:
            self.fail(feature, "baglama_carpismasi", str(e))
            return False
        self.ops.append((kind, setup, feature, op, sf, a_p, s, tool.id))
        return True

    def mills(self) -> list[Tool]:
        """Freze adayları (§2): FLAT, kesme verisinde ap ve ae dolu; D azalan, id artan."""
        out = []
        for t in self.lib.tools:
            if isinstance(t, Tool) and t.kind is ToolKind.FLAT and self.material in t.cutting:
                cd = t.cutting[self.material]
                if cd.ap is not None and cd.ae is not None:
                    out.append(t)
        return sorted(out, key=lambda t: (-t.D, t.id))

    def cut(self, tool: Tool, z_top: float, z_bottom: float, setup: int, contour: bool):
        """§2 kesme verisi → (Cut, SpindleFeed, a_p, s, kısıldı mı)."""
        sf = milling(tool, self.material, self.o.n_max)
        cd = tool.cutting[self.material]
        a_p = min(cd.ap, tool.flute_length)
        s_max = S_RATIO * tool.D
        s = min(cd.ae, s_max)
        c = Cut(
            z_top=z_top,
            z_bottom=z_bottom,
            a_p=a_p,
            feed=sf.F,
            plunge_feed=self.o.plunge_ratio * sf.F,
            rpm=sf.n,
            z_safe=clearance_height(self.setups[setup]),
            clearance=self.o.clearance,
            stepover=None if contour else s,
        )
        return c, sf, a_p, None if contour else s, (not contour) and cd.ae > s_max

    # ------------------------------------------------ alan işlemleri (§3)

    def area(
        self, kind: str, feature: str, omega_of, z_t: float, z_b: float, d_max_of, setup: int, rest: bool
    ):
        """Takım seçimi ve işlem(ler). omega_of(T) → Region | None (yüz alma), d_max_of(Ω) → float."""
        z_ust = self.stock.zmax
        aday = self.mills()
        if not aday:
            var = any(isinstance(t, Tool) and t.kind is ToolKind.FLAT for t in self.lib.tools)
            kod = "kesme_verisi_yok" if var else "takim_yok"
            self.fail(feature, kod, f"'{self.material}' için ap ve ae kesme verisi olan düz freze yok")
            return
        sigan = [t for t in aday if _sigar(omega_of(t), t)]
        if not sigan:
            self.fail(
                feature,
                "takim_sigmiyor",
                f"Aday frezelerin hiçbiri bölgeye sığmıyor (en küçük Ø{aday[-1].D:g})",
            )
            return
        S = [t for t in sigan if t.flute_length >= z_ust - z_b - 1e-9]
        if not S:
            self.fail(
                feature,
                "kesici_boy_yetmez",
                f"Sığan frezelerin kesici boyu yetmiyor ({z_ust - z_b:g} mm > {sigan[0].flute_length:g} mm)",
            )
            return
        T1 = S[0]
        d_max = d_max_of(omega_of(T1))
        T2 = None
        if T1.D > d_max + 1e-9:
            alt = [t for t in S if t.D <= d_max + 1e-9]
            if alt:
                T2 = alt[0]
            else:
                kucuk = [t for t in S if t.D < T1.D]
                if kucuk:
                    D_min = min(t.D for t in kucuk)
                    T2 = min((t for t in kucuk if t.D == D_min), key=lambda t: t.id)
        if T2 is not None and not rest:
            T1, T2 = T2, None
        self.area_op(kind, feature, omega_of(T1), T1, z_t, z_b, setup)
        son = T1
        if T2 is not None:
            omega2 = omega_of(T2)
            if 2 * T2.D >= T1.D:
                for k, halka in enumerate(omega2.loops):
                    c, sf, a_p, s, _ = self.cut(T2, z_t, z_b, setup, contour=True)
                    tp = ops2d.contour(halka, T2, c, "ic" if k == 0 else "dis")
                    self.add("cep_kalan", setup, feature, tp, sf, a_p, s, T2)
            else:
                self.area_op("cep_kalan", feature, omega2, T2, z_t, z_b, setup)
            son = T2
        omega = omega_of(son)
        if omega is not None:
            V = _corner_area(omega, son.D / 2) * (z_t - z_b)
            if V > 0:
                self.note(feature, "kose_artigi", V, f"T{son.id} (Ø{son.D:g}) köşelere sığmıyor")

    def area_op(self, kind: str, feature: str, omega: Region | None, T: Tool, z_t, z_b, setup: int) -> None:
        c, sf, a_p, s, kisildi = self.cut(T, z_t, z_b, setup, contour=False)
        if kisildi:
            self.note(feature, "yan_paso_kisildi", s, f"T{T.id}: ae > D/2, s = {s:g}")
        tp = ops2d.face(self.stock, T, c) if omega is None else ops2d.pocket(omega, T, c)
        self.add(kind, setup, feature, tp, sf, a_p, s, T)

    # ------------------------------------------------ delikler (§4)

    def drill_for(self, feature: str, d: float, z_dip: float) -> Tool | None:
        tur = [t for t in self.lib.tools if isinstance(t, Tool) and t.kind is ToolKind.DRILL]
        cap = [t for t in tur if abs(t.D - d) <= self.o.drill_tol]
        if not cap:
            self.fail(feature, "takim_yok", f"Ø{d:g} matkap yok (tolerans {self.o.drill_tol:g})")
            return None
        veri = [t for t in cap if self.material in t.cutting]
        if not veri:
            self.fail(feature, "kesme_verisi_yok", f"Ø{d:g} matkapta '{self.material}' kesme verisi yok")
            return None
        boy = [t for t in veri if t.flute_length >= self.stock.zmax - z_dip - 1e-9]
        if not boy:
            self.fail(
                feature,
                "kesici_boy_yetmez",
                f"Ø{d:g} matkabın kesici boyu {self.stock.zmax - z_dip:g} mm'ye yetmiyor",
            )
            return None
        return min(boy, key=lambda t: (t.flute_length, t.id))

    def holes(self, holes) -> None:
        o = self.o
        gruplar: dict[tuple, list[tuple[float, float, int]]] = {}
        araclar: dict[int, Tool] = {}
        for i, hf in enumerate(holes):
            adres = f"holes[{i}]"
            if not hf.top_access:
                self.fail(
                    adres,
                    "ustten_erisilemez",
                    f"Delik ekseni −Z değil ({tuple(float(v) for v in hf.hole.axis)})",
                )
                continue
            h = hf.hole
            z_e = float(h.origin[2])
            if h.through:
                b = min(o.breakthrough, z_e - h.depth - self.stock.zmin)
                z_dip = z_e - h.depth - b
            else:
                b = None
                z_dip = z_e - h.depth
            T = self.drill_for(adres, h.d, z_dip)
            if T is None:
                continue
            if b is not None and b < o.breakthrough:
                self.note(adres, "delik_tasma_kisildi", b, f"Stok altına inilmez: taşma {b:g} mm")
            if h.csk_d > 0:
                self.fail(adres, "havsa_takimi_yok", f"Havşa Ø{h.csk_d:g}: havşa takımı türü yok")
            if h.thread:
                self.fail(adres, "kilavuz_cevrimi_yok", f"Diş {h.thread}: kılavuz çevrimi (G84) yok")
            if h.depth / T.D > o.peck_limit:
                kind, q = "G83", o.peck_q * T.D
            else:
                kind, q = "G81", None
            araclar[T.id] = T
            gruplar.setdefault((T.id, z_e, z_dip, kind, q), []).append(
                (float(h.origin[0]), float(h.origin[1]), i)
            )

        sirali = []
        for key, pts in gruplar.items():
            sirali.append((key, _nearest(pts)))
        sirali.sort(key=lambda g: (-araclar[g[0][0]].D, -g[0][1], g[1][0][:2]))
        for (tid, z_e, z_dip, kind, q), pts in sirali:
            T = araclar[tid]
            sf = milling(T, self.material, o.n_max)
            z_safe = clearance_height(self.setups[0])
            adres = "holes[" + ",".join(str(i) for i in sorted(p[2] for p in pts)) + "]"
            op = DrillOp(
                name="delik",
                tool=T,
                rpm=sf.n,
                start=(pts[0][0], pts[0][1], z_safe),
                holes=[(x, y) for x, y, _ in pts],
                z=z_dip,
                r=z_e + o.clearance,
                feed=sf.F,
                kind=kind,
                q=q,
                retract="G98",
            )
            self.add("delik", 0, adres, op, sf, None, None, T)
            for x, y, i in pts:
                h = holes[i].hole
                if h.cbore_d > 0:
                    omega = Region(Profile.circle((x, y), h.cbore_d / 2))
                    self.area(
                        "lamba",
                        f"holes[{i}]",
                        lambda t, w=omega: w,
                        z_e,
                        z_e - h.cbore_depth,
                        lambda w: math.inf,
                        0,
                        False,
                    )


def _nearest(pts: list[tuple[float, float, int]]) -> list[tuple[float, float, int]]:
    """En yakın komşu sırası: ilk nokta (x, y) sözlük sırasında en küçük; eşit uzaklıkta sözlük sırası."""
    kalan = sorted(pts)
    yol = [kalan.pop(0)]
    while kalan:
        x, y = yol[-1][:2]
        j = min(range(len(kalan)), key=lambda k: (math.hypot(kalan[k][0] - x, kalan[k][1] - y), kalan[k]))
        yol.append(kalan.pop(j))
    return yol


def plan_mill_features(
    features: Features,
    part_zmin: float,
    stock: Stock,
    lib: ToolLibrary,
    material: str,
    wcs: Wcs | None = None,
    fixtures: Sequence[Stock | CylinderStock] = (),
    wcs2: Wcs | None = None,
    fixtures2: Sequence[Stock | CylinderStock] | None = None,
    options: MillOptions = DEFAULT_OPTIONS,
) -> MillPlan:
    """OCCT'siz çekirdek: SPEC 29 §2–5."""
    check_common(material, lib)
    if not isinstance(features, Features):
        raise CamError(f"İşlem planı: features Features olmalı ({type(features).__name__})")
    if not isinstance(stock, Stock):
        raise CamError(f"Freze planı kutu stok (Stock) ister ({type(stock).__name__})")
    _check_options(options)
    o = options
    if not _sayi(part_zmin) or not (stock.zmin - o.tol <= part_zmin < stock.zmax):
        raise CamError(
            f"İşlem planı: parça alt Z'si stok dışında ({part_zmin!r}, stok [{stock.zmin}, {stock.zmax}])"
        )

    s1 = Setup("baglama-1", wcs if wcs is not None else Wcs("G54"), stock, list(fixtures))
    P = _Plan(stock, lib, material, o, [s1])

    # (a) alan işlemleri: z_t azalan, yüz alma < açık bölge < cep, SPEC 27 sırası
    alan = []
    for i, f in enumerate(features.faces):
        alan.append(
            (stock.zmax, 0, i, "yuz_alma", f"faces[{i}]", lambda t: None, f.z, lambda w: math.inf, True)
        )
    for i, f in enumerate(features.opens):
        alan.append(
            (
                f.z_top,
                1,
                i,
                "acik_bolge",
                f"opens[{i}]",
                _open_region(f, o.open_margin),
                f.z_bottom,
                lambda w: 2 * _r_corner(w),
                o.rest,
            )
        )
    for i, f in enumerate(features.pockets):
        alan.append(
            (
                f.z_top,
                2,
                i,
                "cep",
                f"pockets[{i}]",
                lambda t, w=f.region: w,
                f.z_bottom,
                lambda w, d=f.max_tool_d: d,
                o.rest,
            )
        )
    alan.sort(key=lambda a: (-a[0], a[1], a[2]))
    for z_t, _, _, kind, adres, omega_of, z_b, d_max_of, rest in alan:
        P.area(kind, adres, omega_of, z_t, z_b, d_max_of, 0, rest)

    # (b) delikler
    P.holes(features.holes)

    # bağlama 2: alt yüz
    if stock.zmin < part_zmin - o.tol:
        fx2 = fixtures if fixtures2 is None else fixtures2
        P.setups.append(Setup("baglama-2", wcs2 if wcs2 is not None else Wcs("G55"), stock, list(fx2)))
        z_c = (stock.zmin + stock.zmax) / 2
        P.note("alt_yuz", "ikinci_baglama", part_zmin - stock.zmin, "Alt yüz ters bağlamada alınır")
        P.area(
            "yuz_alma",
            "alt_yuz",
            lambda t: None,
            stock.zmax,
            2 * z_c - part_zmin,
            lambda w: math.inf,
            1,
            True,
        )

    ops = []
    for k, (kind, setup, adres, op, sf, a_p, s, tid) in enumerate(sorted(P.ops, key=lambda r: r[1])):
        ad = f"{k + 1:02d}-{kind}-T{tid}"
        op.name = ad
        ops.append(PlannedOp(ad, kind, setup, adres, tid, op, sf, a_p, s))
    unplanned = tuple(sorted(P.unplanned, key=lambda u: (u.feature, u.code)))
    if o.strict and unplanned:
        raise CamError("İşlem planı eksik: " + "; ".join(f"{u.feature}: {u.code}" for u in unplanned))
    return MillPlan(
        material=material,
        features=features,
        setups=tuple(P.setups),
        ops=tuple(ops),
        unplanned=unplanned,
        notes=tuple(sorted(P.notes, key=lambda n: (n.feature, n.code))),
    )


def _open_region(f, m: float):
    """Açık bölge Ω(T) = Region(offset(Region(E), −(r_T + m))[0].outer, adalar); takım başına önbellek."""
    cache: dict[int, Region] = {}

    def omega_of(t: Tool) -> Region:
        if t.id not in cache:
            buyuk = offset(Region(f.boundary), -(t.D / 2 + m))
            cache[t.id] = Region(buyuk[0].outer, holes=list(f.islands))
        return cache[t.id]

    return omega_of


def plan_mill(part: Part, stock: Stock, lib: ToolLibrary, material: str, **kw) -> MillPlan:
    """recognize(part, stock, tol, hole_d_max) + plan_mill_features(...)."""
    o = kw.get("options", DEFAULT_OPTIONS)
    _check_options(o)
    features = recognize(part, stock, tol=o.tol, hole_d_max=o.hole_d_max)
    return plan_mill_features(features, float(part.bbox[0][2]), stock, lib, material, **kw)
