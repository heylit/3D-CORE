"""
SPEC 40 — Torna ekleri: eksenel delme ve punta, ters bağlama, profilli kanal (Recess).

Koordinatlar SPEC 20 gibi: iş mili ekseni Z, X yarıçap, ön uç büyük z; yollar y = 0, G18, G95.
- Delme: matkap iş mili ekseninde (x = 0) duran freze takımıdır (Tool, DRILL / CONE); programlanan nokta uç.
  L_uç = (D/2)/tan(φ/2), punta derinliği t = (d_c/2)/tan(φ/2).
- Ters bağlama: z' = z_ref − z, x' = x; varsayılan z_ref = zmin + zmax (stok kendine gider).
- Profilli kanal: kanal ucunun alt sınırı [C_L, C_R] ⊕ D(ρ); C_L yolu h_ρ(z_L) = max_{s∈[0,a]} g(z_L + s),
  g = profilin ρ burun merkezi yolu (SPEC 20 nose_path), a = w − 2r.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np

from cam.geom2d import TOL, cross, intersect
from cam.lathe import _nose_frame, check_side, mirror_segments, prepare
from cam.lathe_ops import TurnCut, _check_stock, _check_tool, _frame, _start
from cam.model import (
    CamError,
    CylinderStock,
    FeedMode,
    LatheTool,
    LatheToolKind,
    Move,
    MoveType,
    Plane,
    Setup,
    Tool,
    ToolKind,
    Toolpath,
    Wcs,
)
from cam.ops2d import depths
from cam.profile import Arc, Line, Profile, Segment

if TYPE_CHECKING:
    from cam.sim.radial import RadialMap

MODES = ("tam", "kirma")
TWO_PI = 2 * math.pi


def _finite(ad: str, v) -> float:
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v):
        raise CamError(f"{ad} sonlu bir sayı olmalı ({v!r})")
    return float(v)


# ---------------------------------------------------------------- A. delme ve punta


@dataclass
class DrillCut:
    """Tornada delme parametreleri [mm/dev, dev/dk, mm]."""

    feed: float  # mm/dev (G95)
    rpm: float  # dev/dk, sabit devir (G97)
    peck: float | None = None  # q, paso boyu; None → tek paso
    mode: str = "tam"  # "tam" (G83 mantığı) | "kirma" (G73/G74 mantığı)
    retract: float = 0.5  # e, talaş kırma geri çekilmesi / yeniden yaklaşma payı
    clearance: float = 1.0  # cl, yüzeyden yaklaşma payı

    def __post_init__(self) -> None:
        for ad in ("feed", "rpm", "peck", "retract", "clearance"):
            v = getattr(self, ad)
            if v is None and ad == "peck":
                continue
            if not _finite(f"DrillCut.{ad}", v) > 0:
                raise CamError(f"DrillCut.{ad} pozitif olmalı ({v})")
        if self.mode not in MODES:
            raise CamError(f"DrillCut.mode {MODES} olmalı ({self.mode!r})")


def _tip_angle(tool: Tool, kinds: set[ToolKind], op: str) -> float:
    """Sivri uçlu takımın uç açısı φ [derece]; tür veya açı eksikse CamError."""
    if not isinstance(tool, Tool) or tool.kind not in kinds:
        raise CamError(f"{op}: {'/'.join(k.value for k in kinds)} takımı gerekli")
    if tool.tip_angle is None:
        raise CamError(f"{op}: takım '{tool.name}' uç açısı (tip_angle) yok; varsayılan kabul edilmez")
    return float(tool.tip_angle)


def tip_length(tool: Tool) -> float:
    """L_uç = (D/2) / tan(φ/2)."""
    phi = _tip_angle(tool, {ToolKind.DRILL, ToolKind.CONE}, "Uç boyu")
    return tool.D / 2 / math.tan(math.radians(phi) / 2)


def center_depth(tool: Tool, d_c: float) -> float:
    """Punta derinliği t = (d_c/2) / tan(φ/2)."""
    phi = _tip_angle(tool, {ToolKind.DRILL, ToolKind.CONE}, "Punta derinliği")
    d_c = _finite("Punta çapı d_c", d_c)
    if not 0 < d_c <= tool.D + TOL:
        raise CamError(f"Punta çapı 0 < d_c ≤ D olmalı (d_c={d_c}, D={tool.D})")
    return d_c / 2 / math.tan(math.radians(phi) / 2)


def _axial_path(
    stock: CylinderStock, tool: Tool, cut: DrillCut, z_top: float, z_tip: float, name: str
) -> Toolpath:
    """Ortak denetimler + x = 0 eksenindeki paso dizisi."""
    if not isinstance(stock, CylinderStock):
        raise CamError("Tornada delme CylinderStock ister")
    if not isinstance(cut, DrillCut):
        raise CamError("Tornada delme DrillCut ister")
    if z_top > stock.zmax + TOL:
        raise CamError(f"Delme başlangıcı ham malzemenin önünde (z_top={z_top} > zmax={stock.zmax})")
    H = z_top - z_tip
    if H <= TOL:
        raise CamError(f"Delme boyu pozitif olmalı (z_top={z_top}, uç={z_tip})")
    if z_tip < stock.zmin - TOL:
        raise CamError(f"Matkap ucu ham malzemenin arkasına geçiyor (uç={z_tip} < zmin={stock.zmin})")
    if tool.D <= stock.d + TOL:
        raise CamError(f"Takım çapı delikten büyük değil (D={tool.D} ≤ d={stock.d}): hava delme")
    if H > tool.flute_length + TOL:
        raise CamError(f"Delme boyu kesici boydan uzun (H={H} > {tool.flute_length})")
    tips = [z_tip] if cut.peck is None else depths(z_top, z_tip, cut.peck)
    R = z_top + cut.clearance
    moves: list[Move] = []
    pos = R

    def go(mt: MoveType, z: float) -> None:
        nonlocal pos
        if abs(z - pos) < TOL:
            return
        moves.append(Move(mt, (0.0, 0.0, z), cut.feed if mt is MoveType.LINEAR else None))
        pos = z

    go(MoveType.LINEAR, tips[0])
    for k in range(1, len(tips)):
        if cut.mode == "tam":
            go(MoveType.RAPID, R)
        go(MoveType.RAPID, tips[k - 1] + cut.retract)
        go(MoveType.LINEAR, tips[k])
    go(MoveType.RAPID, R)
    tp = Toolpath(
        name=name,
        tool=tool,
        start=(0.0, 0.0, R),
        moves=moves,
        rpm=cut.rpm,
        plane=Plane.ZX,
        feed_mode=FeedMode.PER_REV,
        css=None,
    )
    tp.validate()
    return tp


def lathe_drill(
    stock: CylinderStock,
    tool: Tool,
    cut: DrillCut,
    z_top: float,
    z_bottom: float,
    full_diameter: bool = False,
    name: str = "delme",
) -> Toolpath:
    """Eksenel delme (x = 0); full_diameter=True ise z_bottom tam çap derinliği, uç L_uç daha derinde."""
    if not isinstance(tool, Tool) or tool.kind is not ToolKind.DRILL:
        raise CamError("Tornada delme matkap (Tool, DRILL) ister")
    z_top = _finite("z_top", z_top)
    z_tip = _finite("z_bottom", z_bottom)
    if full_diameter:
        z_tip -= tip_length(tool)
    return _axial_path(stock, tool, cut, z_top, z_tip, name)


def lathe_center(
    stock: CylinderStock, tool: Tool, cut: DrillCut, z_top: float, d_c: float, name: str = "punta"
) -> Toolpath:
    """Punta delme: tek paso, uç z_top − center_depth(tool, d_c)."""
    t = center_depth(tool, d_c)
    if isinstance(cut, DrillCut) and cut.peck is not None:
        raise CamError("Punta tek pasodur; peck verilmez")
    z_top = _finite("z_top", z_top)
    return _axial_path(stock, tool, cut, z_top, z_top - t, name)


# ---------------------------------------------------------------- B. ters bağlama


def _flip_seg(s: Segment, z_ref: float) -> Segment:
    def f(p):
        return (z_ref - p[0], p[1])

    if isinstance(s, Arc):
        return Arc(f(s.p0), f(s.p1), f(s.c), not s.ccw)
    return Line(f(s.p0), f(s.p1))


def flip_profile(profile: Profile, z_ref: float) -> Profile:
    """(z, x) → (z_ref − z, x); yaylar ccw değiştirir, açık profil ön→arka."""
    if not isinstance(profile, Profile):
        raise CamError("flip_profile: Profile gerekli")
    z_ref = _finite("z_ref", z_ref)
    out = Profile([_flip_seg(s, z_ref) for s in profile.segments], profile.closed)
    if not out.closed and out.start[0] < out.end[0]:
        out = out.reversed()
    return out


def _cyl(stock) -> CylinderStock:
    if not isinstance(stock, CylinderStock):
        raise CamError("Ters bağlama silindir ham malzeme (CylinderStock) ister")
    return stock


def flip_stock(stock: CylinderStock, z_ref: float | None = None) -> CylinderStock:
    """CylinderStock(D, z_ref − zmax, z_ref − zmin, d); z_ref None → zmin + zmax."""
    stock = _cyl(stock)
    z_ref = stock.zmin + stock.zmax if z_ref is None else _finite("z_ref", z_ref)
    return CylinderStock(D=stock.D, zmin=z_ref - stock.zmax, zmax=z_ref - stock.zmin, d=stock.d)


def flip_setup(
    setup: Setup,
    fixtures: Sequence[CylinderStock],
    z_ref: float | None = None,
    wcs: Wcs | None = None,
    name: str | None = None,
) -> Setup:
    """İkinci bağlama: stok ters çevrilir, bağlama elemanları yeniden verilir, wcs varsayılan G55."""
    stock = flip_stock(setup.stock, z_ref)
    for f in fixtures:
        _cyl(f)
    return Setup(
        name=setup.name + "-ters" if name is None else name,
        wcs=Wcs("G55") if wcs is None else wcs,
        stock=stock,
        fixtures=list(fixtures),
    )


def flip_rmap(rmap: RadialMap, setup: Setup, cell: float, z_ref: float | None = None) -> RadialMap:
    """SPEC 22 radyal haritasını ikinci bağlamanın ızgarasına ters çevirerek taşır (sütun i → z_ref − z_i)."""
    stock = _cyl(setup.stock)
    from cam.sim.radial import RadialMap

    z_ref = stock.zmin + stock.zmax if z_ref is None else _finite("z_ref", z_ref)
    grid = RadialMap.from_stock(stock, cell, list(setup.fixtures))
    dz = rmap.dz
    if abs(grid.dz - dz) > 1e-12 * dz:
        raise CamError(f"Ters bağlama: hücre boyu uyuşmuyor (dz={dz}, ikinci bağlama {grid.dz})")
    # hedef sütun j ↔ kaynak sütun i = f − j
    f = (z_ref - (grid.z0 + dz / 2) - (rmap.z0 + dz / 2)) / dz
    k = round(f)
    if abs(f - k) > 1e-9:
        raise CamError(f"Ters bağlama: sütun merkezleri örtüşmüyor (kayma {f - k:.6g}·dz)")
    out = RadialMap.empty_like(grid)
    for i in range(rmap.nz):
        ivs = rmap.intervals(i)
        if not ivs:
            continue
        j = k - i
        if not 0 <= j < out.nz:
            raise CamError(f"Ters bağlama: malzemeli sütun {i} ikinci bağlamanın ızgarası dışında")
        for a, b in ivs:
            out.add(j, a, b)
    return out


# ---------------------------------------------------------------- C. profilli kanal: geometri


def _in_sweep(s: Arc, th: float, eps: float = 1e-12) -> bool:
    raw = ((th - s.a0) if s.ccw else (s.a0 - th)) % TWO_PI
    return raw <= s.sweep + eps or raw >= TWO_PI - eps


def _at_z(s: Segment, z: float) -> list[np.ndarray]:
    """Parçanın apsisi z olan noktaları."""
    if isinstance(s, Line):
        dz = s.p1[0] - s.p0[0]
        if abs(dz) < TOL:
            return []
        t = (z - s.p0[0]) / dz
        if -1e-12 <= t <= 1 + 1e-12:
            return [s.point(min(max(t, 0.0), 1.0))]
        return []
    u = (z - s.c[0]) / s.R
    if abs(u) > 1 + 1e-12:
        return []
    u = min(max(u, -1.0), 1.0)
    out = []
    for th in {math.acos(u), -math.acos(u)}:
        if _in_sweep(s, th):
            out.append(np.array([z, s.c[1] + s.R * math.sin(th)]))
    return out


def _zrange(s: Segment) -> tuple[float, float]:
    zs = [s.p0[0], s.p1[0]]
    if isinstance(s, Arc):
        for th in (0.0, math.pi):
            if _in_sweep(s, th):
                zs.append(s.c[0] + s.R * math.cos(th))
    return min(zs), max(zs)


def _sub(s: Segment, z0: float, z1: float) -> Segment:
    """Z-monoton parçanın [z0, z1] kısmı, z artan yönde."""
    p0, p1 = _at_z(s, z0)[0], _at_z(s, z1)[0]
    if isinstance(s, Arc):
        # ön→arka parçanın tersi: z artan
        return Arc(p0, p1, s.c, not s.ccw if s.p0[0] > s.p1[0] else s.ccw)
    return Line(p0, p1)


def _shift_seg(s: Segment, d: np.ndarray) -> Segment:
    if isinstance(s, Arc):
        return Arc(s.p0 + d, s.p1 + d, s.c + d, s.ccw)
    return Line(s.p0 + d, s.p1 + d)


@dataclass
class _Recess:
    """Dış çerçevede hazırlanmış girinti: profil, g parçaları, erişim aralığı."""

    prof: Profile
    x_top: float
    sgn: int
    r: float
    rho: float
    a: float
    lo: float  # z_L en küçük
    hi: float  # z_L en büyük
    pieces: list[Segment]  # g'nin dik olmayan parçaları

    def g(self, z: float) -> tuple[float, int]:
        best, k = -math.inf, -1
        for i, s in enumerate(self.pieces):
            for p in _at_z(s, z):
                if p[1] > best:
                    best, k = float(p[1]), i
        if k < 0:
            raise CamError(f"Profilli kanal: z = {z} için burun yolu yok (sayısal hata)")
        return best, k

    def peaks(self) -> list[tuple[float, float]]:
        pts = []
        for s in self.pieces:
            pts += [s.p0, s.p1]
            if isinstance(s, Arc) and _in_sweep(s, math.pi / 2):
                pts.append(s.c + np.array([0.0, s.R]))
        return [(float(p[0]), self.g(float(p[0]))[0]) for p in pts]

    def h(self, z: float) -> float:
        """h_ρ(z_L): kayan pencerede g'nin en büyük değeri."""
        v = max(self.g(z)[0], self.g(z + self.a)[0])
        for zm, xm in self.peaks():
            if z < zm < z + self.a:
                v = max(v, xm)
        return v


def _check_recess_profile(p: Profile, x_top: float | None) -> float:
    """Dış çerçevede: x_top uçlar, arka kesim yok, x ≤ x_top. x_top döner."""
    xs = float(p.start[1])
    if x_top is not None and abs(x_top - xs) > TOL:
        raise CamError(f"Girinti profili x_top'ta başlamıyor (başlangıç x={xs}, x_top={x_top})")
    x_top = xs
    if abs(p.end[1] - x_top) > TOL:
        raise CamError(f"Girinti profili x_top'a dönmüyor (bitiş x={p.end[1]}, x_top={x_top})")
    _, hi = p.bbox()
    if hi[1] > x_top + TOL:
        raise CamError(f"Girinti profili x_top'un üstüne çıkıyor (x={hi[1]} > {x_top})")
    for i, s in enumerate(p.segments):
        ts = [s.tangent(0.0), s.tangent(1.0)]
        if isinstance(s, Arc):
            for th in (math.pi / 2, -math.pi / 2):
                if _in_sweep(s, th):
                    tv = np.array([-math.sin(th), math.cos(th)])
                    ts.append(tv if s.ccw else -tv)
        if max(t[0] for t in ts) > TOL:
            raise CamError(f"Girinti profilinde arka kesim (alttan oyuk): parça {i}")
    return x_top


def _recess(
    profile: Profile, tool: LatheTool, allowance: float, side: str, x_top: float | None = None
) -> _Recess:
    sgn = check_side(side)
    if not isinstance(tool, LatheTool) or tool.kind is not LatheToolKind.GROOVE:
        raise CamError("Profilli kanal kanal ucu (LatheTool, GROOVE) ister")
    allowance = _finite("Talaş payı", allowance)
    if allowance < 0:
        raise CamError(f"Talaş payı negatif olamaz (δ={allowance})")
    p = prepare(profile, side)
    xt = _check_recess_profile(p, None if x_top is None else sgn * x_top)
    r = tool.nose_r
    rho = r + allowance
    a = tool.width - 2 * r
    z_right, z_left = float(p.start[0]), float(p.end[0])
    lo, hi = z_left + rho, z_right - rho - a
    if hi < lo - TOL:
        raise CamError(f"Kanal takımdan dar (W={z_right - z_left} < w + 2δ = {tool.width + 2 * allowance})")
    hi = max(hi, lo)
    nose = _nose_frame(p, rho, strict=False)
    pieces = [s for s in nose if not (isinstance(s, Line) and abs(s.p1[0] - s.p0[0]) < TOL)]
    return _Recess(p, xt, sgn, r, rho, a, lo, hi, pieces)


def _envelope_frame(rc: _Recess) -> list[Segment]:
    """C_L yolu (dış çerçeve), arkadan öne."""
    lo, hi, a = rc.lo, rc.hi, rc.a
    if hi - lo <= TOL:
        return []
    peaks = rc.peaks()
    bps = {lo, hi}
    span = (lo - 1.0, hi + a + 1.0)
    shifted = [_shift_seg(s, np.array([-a, 0.0])) for s in rc.pieces]
    for s in rc.pieces:
        z0, z1 = _zrange(s)
        bps |= {z0, z1, z0 - a, z1 - a}
    for zm, xm in peaks:
        bps |= {zm, zm - a}
        flat = Line((span[0], xm), (span[1], xm))
        for s in rc.pieces + shifted:
            for t, _ in intersect(s, flat):
                bps.add(float(s.point(t)[0]))
    if a > TOL:
        for s in rc.pieces:
            for u in shifted:
                for t, _ in intersect(s, u):
                    bps.add(float(s.point(t)[0]))
    zs = sorted(z for z in bps if lo - TOL <= z <= hi + TOL)
    zs = [min(max(z, lo), hi) for z in zs]
    out: list[tuple[tuple, float, float]] = []  # (aday, z0, z1)
    for z0, z1 in zip(zs[:-1], zs[1:], strict=True):
        if z1 - z0 <= TOL:
            continue
        m = 0.5 * (z0 + z1)
        cands = []
        vL, kL = rc.g(m)
        cands.append((vL, ("L", kL)))
        vR, kR = rc.g(m + a)
        cands.append((vR, ("R", kR)))
        for zm, xm in peaks:
            if m < zm < m + a:
                cands.append((xm, ("P", round(xm, 12))))
        top = max(v for v, _ in cands)
        key = next(c for v, c in cands if v >= top - 1e-12)
        if out and out[-1][0] == key:
            out[-1] = (key, out[-1][1], z1)
        else:
            out.append((key, z0, z1))
    segs: list[Segment] = []
    for (kind, k), z0, z1 in out:
        if kind == "L":
            segs.append(_sub(rc.pieces[k], z0, z1))
        elif kind == "R":
            segs.append(_shift_seg(_sub(rc.pieces[k], z0 + a, z1 + a), np.array([-a, 0.0])))
        else:
            segs.append(Line((z0, k), (z1, k)))
    return segs


def _unframe(segs: list[Segment], sgn: int) -> list[Segment]:
    return segs if sgn > 0 else mirror_segments(segs)


# ---------------------------------------------------------------- C. kalan malzeme


def _points_at(s: Segment, z: float) -> list[np.ndarray]:
    """Parçanın apsisi z olan noktaları; uç noktalar dahil (dik doğruda iki uç)."""
    if isinstance(s, Line) and abs(s.p1[0] - s.p0[0]) < TOL:
        return [s.p0, s.p1] if abs(s.p0[0] - z) <= TOL else []
    return _at_z(s, z)


def _lowest_disk(s: Segment, rho: float, z: float) -> float:
    """S ⊕ D(ρ) bölgesinin apsis z'deki en alçak noktası (yoksa +inf)."""
    best = math.inf
    for e in (s.p0, s.p1):
        d = z - e[0]
        if abs(d) <= rho:
            best = min(best, e[1] - math.sqrt(max(rho * rho - d * d, 0.0)))
    if isinstance(s, Line):
        t = s.tangent(0.0)
        n = np.array([-t[1], t[0]])
        for sg in (1.0, -1.0):
            best = min(best, *(p[1] for p in _points_at(_shift_seg(s, sg * rho * n), z)), math.inf)
    else:
        for Rn in (s.R + rho, s.R - rho):
            if Rn <= TOL:
                continue
            u = (z - s.c[0]) / Rn
            if abs(u) > 1:
                continue
            for th in (math.acos(u), -math.acos(u)):
                if _in_sweep(s, th):
                    best = min(best, s.c[1] + Rn * math.sin(th))
    return best


def _lowest_flat(s: Segment, z0: float, z1: float) -> float:
    """Parçanın z ∈ [z0, z1] kısmındaki en küçük x (yoksa +inf)."""
    pts = []
    for e in (s.p0, s.p1):
        if z0 - TOL <= e[0] <= z1 + TOL:
            pts.append(e)
    pts += _at_z(s, z0) + _at_z(s, z1)
    if isinstance(s, Arc) and _in_sweep(s, -math.pi / 2):
        q = s.c - np.array([0.0, s.R])
        if z0 <= q[0] <= z1:
            pts.append(q)
    return min((float(p[1]) for p in pts), default=math.inf)


def _swept_low(env: list[Segment], r: float, a: float, z: float) -> float:
    """İnce paso boyunca süpürülen takımın apsis z'deki en alçak noktası E(z)."""
    best = math.inf
    for s in env:
        best = min(best, _lowest_disk(s, r, z))
        if a > TOL:
            best = min(best, _lowest_disk(_shift_seg(s, np.array([a, 0.0])), r, z))
            best = min(best, _lowest_flat(s, z - a, z) - r)
    return best


def _excluded(rc: _Recess) -> list[tuple[np.ndarray, float]]:
    """Keskin içbükey köşeler ve r/tan(θ/2) komşuluk yarıçapları."""
    out = []
    segs = rc.prof.segments
    for s0, s1 in zip(segs[:-1], segs[1:], strict=True):
        t1, t2 = s0.tangent(1.0), s1.tangent(0.0)
        k = cross(t1, t2)
        if k < -TOL:
            turn = math.atan2(abs(k), float(np.dot(t1, t2)))
            theta = math.pi - turn
            out.append((s0.p1, rc.r / math.tan(theta / 2)))
    return out


def _rest_frame(rc: _Recess) -> float:
    env = _envelope_frame(rc)
    if not env:
        env = [Line((rc.lo, rc.h(rc.lo)), (rc.lo + 1e-6, rc.h(rc.lo)))]
    excl = _excluded(rc)
    r, a = rc.r, rc.a

    def gap(p: np.ndarray) -> float:
        if p[1] > rc.x_top - r + TOL:
            return -math.inf
        for V, d in excl:
            if math.hypot(*(p - V)) < d + 1e-9:
                return -math.inf
        return _swept_low(env, r, a, float(p[0])) - float(p[1])

    best = 0.0
    for s in rc.prof.segments:
        ts = list(np.linspace(0.0, 1.0, 201))
        if isinstance(s, Arc):
            for th in (-math.pi / 2, 0.0, math.pi):
                if _in_sweep(s, th):
                    raw = ((th - s.a0) if s.ccw else (s.a0 - th)) % TWO_PI
                    ts.append(min(raw / s.sweep, 1.0))
        ts = sorted(set(ts))
        vals = [gap(s.point(t)) for t in ts]
        i = int(np.argmax(vals))
        if vals[i] <= best:
            continue
        best = vals[i]
        # en iyi örneğin komşuluğunda altın oran araması
        lo_t, hi_t = ts[max(i - 1, 0)], ts[min(i + 1, len(ts) - 1)]
        g = (math.sqrt(5) - 1) / 2
        for _ in range(100):
            c = hi_t - g * (hi_t - lo_t)
            d = lo_t + g * (hi_t - lo_t)
            if gap(s.point(c)) >= gap(s.point(d)):
                hi_t = d
            else:
                lo_t = c
        best = max(best, gap(s.point(0.5 * (lo_t + hi_t))))
    return max(best, 0.0)


# ---------------------------------------------------------------- C. profilli kanal: arayüz


def recess_envelope(
    profile: Profile, tool: LatheTool, allowance: float = 0.0, side: str = "dis"
) -> list[Segment]:
    """C_L yolu h_ρ (ρ = r + allowance), erişim aralığında, arkadan öne."""
    rc = _recess(profile, tool, allowance, side)
    return _unframe(_envelope_frame(rc), rc.sgn)


def recess_rest(profile: Profile, tool: LatheTool, side: str = "dis") -> float:
    """İnce pasodan sonra ölçülen bölgede en büyük kalan kalınlık e_max."""
    return _rest_frame(_recess(profile, tool, 0.0, side))


def _recess_path(rc: _Recess, stock: CylinderStock, tool: LatheTool, cut: TurnCut, op: str):
    if not isinstance(cut, TurnCut):
        raise CamError(f"{op}: TurnCut gerekli")
    _check_stock(stock, rc.sgn)
    tip = _check_tool(tool, {LatheToolKind.GROOVE}, {3, 4}, rc.sgn, op)
    fr = _frame(stock, tool, cut, rc.sgn)
    off = rc.a if tip == 4 else 0.0  # C_ref = C_L + (off, 0): T3 sol, T4 sağ köşe
    b = _start(fr, tool, tip, cut)
    top = rc.x_top + cut.clearance + rc.r
    return fr, b, off, top


def _done(name: str, tool: LatheTool, cut: TurnCut, fr, b) -> Toolpath:
    b.rapid(*fr.A)
    tp = Toolpath(
        name=name,
        tool=tool,
        start=b.out(fr.A),
        moves=b.moves,
        rpm=cut.rpm,
        plane=Plane.ZX,
        feed_mode=FeedMode.PER_REV,
        css=cut.css,
    )
    tp.validate()
    return tp


def recess_rough(
    profile: Profile,
    x_top: float,
    stock: CylinderStock,
    tool: LatheTool,
    cut: TurnCut,
    allowance: float = 0.0,
    side: str = "dis",
    name: str = "girinti_kaba",
) -> Toolpath:
    """Dalarak kaba: m dalış, tabanlar h_ρ(z_L,j)."""
    x_top = _finite("x_top", x_top)
    rc = _recess(profile, tool, allowance, side, x_top)
    fr, b, off, top = _recess_path(rc, stock, tool, cut, "Profilli kanal kaba")
    span = rc.hi - rc.lo
    if span <= TOL:
        zl = [0.5 * (rc.lo + rc.hi)]
    else:
        if rc.a <= TOL:
            raise CamError("Tam yarıçaplı uçla çok dalışlı profilli kanal tanımsız (w − 2r = 0)")
        m = math.ceil(span / rc.a - 1e-9) + 1
        zl = [rc.lo + j * span / (m - 1) for j in range(m)]
    b.rapid(zl[0] + off, fr.xs)
    for z in zl:
        b.rapid(z + off, top)
        b.line(z + off, rc.h(z))
        b.rapid(z + off, top)
    b.rapid(b.pos[0], fr.xs)
    return _done(name, tool, cut, fr, b)


def recess_finish(
    profile: Profile,
    x_top: float,
    stock: CylinderStock,
    tool: LatheTool,
    cut: TurnCut,
    rest_max: float = 0.0,
    side: str = "dis",
    name: str = "girinti_ince",
) -> Toolpath:
    """Yanal ince paso önden arkaya; e_max > rest_max → CamError."""
    x_top = _finite("x_top", x_top)
    rest_max = _finite("rest_max", rest_max)
    if rest_max < 0:
        raise CamError(f"rest_max negatif olamaz ({rest_max})")
    rc = _recess(profile, tool, 0.0, side, x_top)
    fr, b, off, top = _recess_path(rc, stock, tool, cut, "Profilli kanal ince")
    e = _rest_frame(rc)
    if e > rest_max + 1e-9:
        raise CamError(f"Profilli kanal: kalan malzeme e_max = {e:.6f} mm > rest_max = {rest_max} mm")
    d = np.array([off, 0.0])
    env = [_shift_seg(s, d) for s in _envelope_frame(rc)]
    z0 = rc.hi + off
    b.rapid(z0, fr.xs)
    b.rapid(z0, top)
    b.line(z0, rc.h(rc.hi))
    for s in reversed(env):
        b.seg(s.reversed())
    zb = rc.lo + off
    b.line(zb, top)
    b.rapid(zb, fr.xs)
    return _done(name, tool, cut, fr, b)
