"""
SPEC 20 — Torna işlemleri: alın, boy, kaba çevrim (G71 tip I), ince profil, kanal, diş.

Yol takımın hayali uç noktasının (P = C + q_T) yoludur; burun yarıçapı telafisi burada yapılır.
Hesap dış çerçevede (side="dis") yapılır; iç işlemler x → −x aynasıyla aynı algoritmadan geçer.
Noktalar (x, 0, z), yaylar G18 (ZX), merkez (x, z); ilerleme mm/dev (G95).

Güvenli noktalar (burun merkezi): A = (z_max + cl + r, X_s + cl + r), ön düzlem C_z = z_max + cl + r,
güvenli yarıçap C_x = X_s + cl + r. X_s ham malzeme yüzeyi: dışta D/2, iç çerçevede −d/2.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from cam.geom2d import TOL, arc_param
from cam.lathe import (
    _monotone_frame,
    _nose_frame,
    _reach_frame,
    _right,
    check_side,
    mirror_tip,
    prepare,
    tip_offset,
)
from cam.model import (
    CamError,
    CylinderStock,
    FeedMode,
    LatheTool,
    LatheToolKind,
    Move,
    MoveType,
    Plane,
    Toolpath,
)
from cam.ops2d import depths
from cam.profile import Arc, Line, Profile, Segment

INFEEDS = ("radyal", "yanak")


@dataclass
class TurnCut:
    """Torna kesme parametreleri [mm/dev, dev/dk, m/dk, mm]."""

    feed: float  # mm/dev (G95)
    rpm: float  # dev/dk; css verilirse devir sınırı (G50)
    css: float | None = None  # m/dk, sabit kesme hızı (G96)
    a_p: float | None = None  # radyal (alında eksenel) paso derinliği
    clearance: float = 1.0  # yaklaşma payı
    retract: float = 0.5  # kaba pasoda 45° geri çekilme

    def __post_init__(self) -> None:
        for ad in ("feed", "rpm", "css", "a_p", "clearance", "retract"):
            v = getattr(self, ad)
            if v is None and ad in ("css", "a_p"):
                continue
            if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v):
                raise CamError(f"TurnCut.{ad} sonlu bir sayı olmalı ({v!r})")
            if not v > 0:
                raise CamError(f"TurnCut.{ad} pozitif olmalı ({v})")

    def need_ap(self) -> float:
        if self.a_p is None:
            raise CamError("Bu işlem için a_p (paso derinliği) gerekli")
        return self.a_p


def _check_stock(stock: CylinderStock, sgn: int) -> float:
    """Dış çerçevede ham malzeme yüzey yarıçapı X_s."""
    if not isinstance(stock, CylinderStock):
        raise CamError("Torna işlemleri CylinderStock ister")
    if sgn > 0:
        return stock.D / 2
    if stock.d <= 0:
        raise CamError("İç işlem için delikli ham malzeme (d > 0) gerekli")
    return -stock.d / 2


def _check_tool(tool: LatheTool, kinds: set[LatheToolKind], tips: set[int], sgn: int, op: str) -> int:
    """Takım türü ve (dış çerçevedeki) uç numarası kontrolü; çerçeve uç numarasını döndürür."""
    if not isinstance(tool, LatheTool):
        raise CamError(f"{op}: torna takımı (LatheTool) gerekli")
    if tool.kind not in kinds:
        raise CamError(f"{op}: takım türü {tool.kind.value} uygun değil")
    tip = tool.tip if sgn > 0 else mirror_tip(tool.tip)
    if tip not in tips:
        raise CamError(f"{op}: uç numarası T{tool.tip} bu işlem ve taraf için uygun değil")
    return tip


# ---------------------------------------------------------------- hareket kurucu


@dataclass
class _Path:
    """Dış çerçevede burun merkezi (C) konumlarıyla hareket kurar; P = C + q, x işaretiyle gerçeğe döner."""

    sgn: int
    q: np.ndarray
    feed: float
    pos: np.ndarray
    moves: list[Move] = field(default_factory=list)

    def out(self, c) -> tuple[float, float, float]:
        p = np.asarray(c, dtype=float) + self.q
        return (float(self.sgn * p[1]), 0.0, float(p[0]))

    def _go(self, mt: MoveType, c, feed=None, center=None) -> None:
        c = np.asarray(c, dtype=float)
        if center is None and np.hypot(*(c - self.pos)) < TOL:
            return
        cen = None
        if center is not None:
            k = np.asarray(center, dtype=float) + self.q
            cen = (float(self.sgn * k[1]), float(k[0]))
        self.moves.append(Move(mt, self.out(c), feed, cen))
        self.pos = c

    def rapid(self, z, x) -> None:
        self._go(MoveType.RAPID, (z, x))

    def line(self, z, x, feed=None) -> None:
        self._go(MoveType.LINEAR, (z, x), feed or self.feed)

    def seg(self, s: Segment) -> None:
        if isinstance(s, Arc):
            ccw = s.ccw if self.sgn > 0 else not s.ccw
            mt = MoveType.ARC_CCW if ccw else MoveType.ARC_CW
            self._go(mt, s.p1, self.feed, s.c)
        else:
            self.line(*s.p1)


@dataclass
class _Frame:
    sgn: int
    r: float
    Xs: float
    zmax: float
    cl: float

    @property
    def zf(self) -> float:  # ön düzlem (burun merkezi)
        return self.zmax + self.cl + self.r

    @property
    def xs(self) -> float:  # güvenli yarıçap (burun merkezi)
        return self.Xs + self.cl + self.r

    @property
    def A(self) -> np.ndarray:
        return np.array([self.zf, self.xs])


def _start(fr: _Frame, tool: LatheTool, tip: int, cut: TurnCut, q: np.ndarray | None = None) -> _Path:
    if q is None:
        q = tip_offset(tip, tool.nose_r)
    return _Path(fr.sgn, q, cut.feed, fr.A.copy())


def _finish_tp(name: str, tool: LatheTool, cut: TurnCut, fr: _Frame, b: _Path) -> Toolpath:
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


def _frame(stock: CylinderStock, tool: LatheTool, cut: TurnCut, sgn: int) -> _Frame:
    return _Frame(sgn, tool.nose_r, _check_stock(stock, sgn), stock.zmax, cut.clearance)


# ---------------------------------------------------------------- alın


def face(stock: CylinderStock, tool: LatheTool, cut: TurnCut, z_face: float, name: str = "alin") -> Toolpath:
    """Alın tornalama: n = ⌈H/a_p⌉ eşit paso, burun −Z ucu z_i'de, −X yönünde merkeze (borude d/2 − cl'ye)."""
    tip = _check_tool(tool, {LatheToolKind.TURN}, {3, 0, 9}, 1, "Alın tornalama")
    a_p = cut.need_ap()
    fr = _frame(stock, tool, cut, 1)
    if not (math.isfinite(z_face) and stock.zmin < z_face < stock.zmax):
        raise CamError(f"Alın düzlemi ham malzemenin içinde olmalı (zmin < z_face < zmax, z_face={z_face})")
    r = tool.nose_r
    x_end = 0.0 if stock.d == 0 else max(0.0, stock.d / 2 - cut.clearance)
    b = _start(fr, tool, tip, cut)
    for z in depths(stock.zmax, z_face, a_p):
        cz = z + r
        b.rapid(cz, fr.xs)
        b.line(cz, x_end)
        b.rapid(cz + cut.clearance, x_end)
        b.rapid(cz + cut.clearance, fr.xs)
    return _finish_tp(name, tool, cut, fr, b)


# ---------------------------------------------------------------- kaba çevrim


def _first_hit(bnd: list[Segment], cx: float) -> float:
    """Monoton sınırın ön→arka gezide x ≥ cx'e ilk ulaştığı noktanın z'si; sondan +X uzatılmış."""
    for s in bnd:
        if s.p0[1] >= cx - TOL:
            return float(s.p0[0])
        if isinstance(s, Line):
            if s.p1[1] >= cx - TOL:
                t = (cx - s.p0[1]) / (s.p1[1] - s.p0[1])
                return float(s.point(min(max(t, 0.0), 1.0))[0])
            continue
        top = s.c[1] + s.R
        if max(s.p1[1], top if _passes_top(s) else -math.inf) < cx - TOL:
            continue
        sn = min(max((cx - s.c[1]) / s.R, -1.0), 1.0)
        best = None
        for th in (math.asin(sn), math.pi - math.asin(sn)):
            p = s.c + s.R * np.array([math.cos(th), math.sin(th)])
            t, over = arc_param(s, p)
            if over <= TOL and (best is None or t < best):
                best = t
        if best is not None:
            return float(s.point(best)[0])
    end = bnd[-1].p1
    if cx >= end[1] - TOL:
        return float(end[0])
    raise CamError("Kaba paso sınırla kesişmiyor (sayısal hata)")


def _passes_top(s: Arc) -> bool:
    d = ((math.pi / 2 - s.a0) if s.ccw else (s.a0 - math.pi / 2)) % (2 * math.pi)
    return d <= s.sweep


def _contour(b: _Path, fr: _Frame, bnd: list[Segment]) -> None:
    """Sınır boyunca kontur pasosu: ön düzlemden F → C0 girişi, +X çıkışı."""
    c0 = bnd[0].p0
    fz = max(fr.zf, float(c0[0]))
    b.rapid(fz, b.pos[1])
    b.rapid(fz, c0[1])
    b.line(*c0)
    for s in bnd:
        b.seg(s)
    end = b.pos.copy()
    if end[1] < fr.xs:
        b.line(end[0], fr.xs)


def _rough_frame(
    p: Profile, tool: LatheTool, cut: TurnCut, fr: _Frame, tip: int, delta: float, name: str
) -> Toolpath:
    a_p = cut.need_ap()
    if not math.isfinite(delta) or delta < 0:
        raise CamError(f"Talaş payı negatif olamaz (δ={delta})")
    if not _monotone_frame(p):
        raise CamError("Kaba çevrim (G71 tip I) monoton profil ister: x arkaya doğru azalmamalı, z artmamalı")
    _reach_frame(p, tool)
    if p.start[0] < fr.zmax - TOL:
        raise CamError(f"Profil ham malzemenin ön yüzünden başlamalı (z0={p.start[0]} < zmax={fr.zmax})")
    if p.end[1] < fr.Xs - TOL:
        raise CamError("Profil sonu ham malzeme yüzeyine çıkmalı (son x < ham yarıçap)")
    r = tool.nose_r
    bnd = _nose_frame(p, r + delta, strict=False)
    s0 = p.segments[0]
    x_low = float(s0.p0[1] + delta * _right(s0.tangent(0.0))[1])
    H = fr.Xs - x_low
    if H <= TOL:
        raise CamError(f"Kaba talaş yok (H = {H})")
    n = max(1, math.ceil(H / a_p - 1e-9))
    e = cut.retract
    b = _start(fr, tool, tip, cut)
    for k in range(1, n):
        cx = fr.Xs - k * H / n + r
        z_end = _first_hit(bnd, cx)
        if fr.zf - z_end <= TOL:
            continue
        b.rapid(fr.zf, b.pos[1])
        b.rapid(fr.zf, cx)
        b.line(z_end, cx)
        b.line(z_end + e, cx + e)
        b.rapid(fr.zf, cx + e)
    _contour(b, fr, bnd)
    return _finish_tp(name, tool, cut, fr, b)


_TURN_TIPS = {3, 0, 9}


def _turn_tool(tool: LatheTool, sgn: int, op: str) -> int:
    kind = LatheToolKind.TURN if sgn > 0 else LatheToolKind.BORE
    return _check_tool(tool, {kind}, _TURN_TIPS, sgn, op)


def rough(
    profile: Profile,
    stock: CylinderStock,
    tool: LatheTool,
    cut: TurnCut,
    allowance: float = 0.0,
    side: str = "dis",
    name: str = "kaba",
) -> Toolpath:
    """Boyuna kaba çevrim (G71 tip I): n − 1 boyuna paso + δ talaş paylı kontur pasosu."""
    sgn = check_side(side)
    tip = _turn_tool(tool, sgn, "Kaba çevrim")
    fr = _frame(stock, tool, cut, sgn)
    return _rough_frame(prepare(profile, side), tool, cut, fr, tip, allowance, name)


def turn(
    stock: CylinderStock,
    tool: LatheTool,
    cut: TurnCut,
    x_final: float,
    z_end: float,
    side: str = "dis",
    name: str = "boy",
) -> Toolpath:
    """Boy tornalama: (zmax, X_f) → (z_end, X_f) → (z_end, X_s) profilinin δ = 0 kaba çevrimi."""
    sgn = check_side(side)
    R = stock.D / 2
    if not (math.isfinite(z_end) and stock.zmin <= z_end < stock.zmax):
        raise CamError(f"Boy sonu ham malzemenin içinde olmalı (zmin ≤ z_end < zmax, z_end={z_end})")
    if sgn > 0:
        if not (math.isfinite(x_final) and 0 <= x_final < R):
            raise CamError(f"Dış boy tornalamada 0 ≤ x_final < D/2 olmalı ({x_final})")
        x_wall = R
    else:
        _check_stock(stock, sgn)
        if not (math.isfinite(x_final) and stock.d / 2 < x_final < R):
            raise CamError(f"İç boy tornalamada d/2 < x_final < D/2 olmalı ({x_final})")
        x_wall = stock.d / 2
    prof = Profile.polygon([(stock.zmax, x_final), (z_end, x_final), (z_end, x_wall)], closed=False)
    return rough(prof, stock, tool, cut, 0.0, side, name)


# ---------------------------------------------------------------- ince profil


def finish(
    profile: Profile,
    stock: CylinderStock,
    tool: LatheTool,
    cut: TurnCut,
    side: str = "dis",
    name: str = "ince",
) -> Toolpath:
    """Burun yarıçapı telafili ince profil (sıkı mod: erişilemeyen profil → CamError)."""
    sgn = check_side(side)
    tip = _turn_tool(tool, sgn, "İnce profil")
    fr = _frame(stock, tool, cut, sgn)
    p = prepare(profile, side)
    _reach_frame(p, tool)
    bnd = _nose_frame(p, tool.nose_r, strict=True)
    b = _start(fr, tool, tip, cut)
    _contour(b, fr, bnd)
    return _finish_tp(name, tool, cut, fr, b)


# ---------------------------------------------------------------- kanal


def groove(
    stock: CylinderStock,
    tool: LatheTool,
    cut: TurnCut,
    z_left: float,
    z_right: float,
    x_top: float,
    x_bottom: float,
    side: str = "dis",
    name: str = "kanal",
) -> Toolpath:
    """Dalarak radyal kanal: m = ⌈(W − w)/(w − 2r)⌉ + 1 dalış, kenarlar eşit aralıklı."""
    sgn = check_side(side)
    tip = _check_tool(tool, {LatheToolKind.GROOVE}, {3, 4}, sgn, "Kanal")
    fr = _frame(stock, tool, cut, sgn)
    for ad, v in (("z_left", z_left), ("z_right", z_right), ("x_top", x_top), ("x_bottom", x_bottom)):
        if not math.isfinite(v):
            raise CamError(f"Kanal: {ad} sonlu olmalı ({v})")
    if x_bottom < 0:
        raise CamError(f"Kanal tabanı eksenin altında olamaz (x_bottom={x_bottom})")
    xt, xb = sgn * x_top, sgn * x_bottom
    if not xb < xt:
        raise CamError("Kanal tabanı malzemede olmalı (dışta x_bottom < x_top, içte x_bottom > x_top)")
    r, w = tool.nose_r, tool.width
    W = z_right - z_left
    if W < w - TOL:
        raise CamError(f"Kanal takımdan dar olamaz (W={W}, w={w})")
    if W - w <= TOL:
        zl = [z_left]
    else:
        flat = w - 2 * r
        if flat <= TOL:
            raise CamError("Tam yarıçaplı uçla çok dalışlı kanal kapsam dışı (w − 2r = 0)")
        m = math.ceil((W - w) / flat - 1e-9) + 1
        zl = [z_left + j * (W - w) / (m - 1) for j in range(m)]
    # referans burun merkezi: T3 sol köşe, T4 sağ köşe
    dz = r if tip == 3 else w - r
    b = _start(fr, tool, tip, cut)
    top = xt + cut.clearance + r
    b.rapid(zl[0] + dz, fr.xs)
    for z in zl:
        b.rapid(z + dz, top)
        b.line(z + dz, xb + r)
        b.rapid(z + dz, top)
    b.rapid(b.pos[0], fr.xs)
    return _finish_tp(name, tool, cut, fr, b)


# ---------------------------------------------------------------- diş


def iso_thread_depth(pitch: float, external: bool = True) -> float:
    """ISO 68-1: H = (√3/2)·P; dış diş h = 17/24·H, iç diş h = 5/8·H."""
    if not (math.isfinite(pitch) and pitch > 0):
        raise CamError(f"Hatve pozitif olmalı (P={pitch})")
    H = math.sqrt(3) / 2 * pitch
    return 17 / 24 * H if external else 5 / 8 * H


def thread_depths(h: float, first: float, minimum: float = 0.0, spring: int = 0) -> list[float]:
    """Fanuc G76 kümülatif derinlikler: h_i = Δd·√i, artış ≥ Δd_min, son paso tam h; + spring boş paso."""
    for ad, v in (("h", h), ("first", first), ("minimum", minimum)):
        if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v):
            raise CamError(f"thread_depths: {ad} sonlu olmalı ({v!r})")
    if not (h > 0 and first > 0 and minimum >= 0):
        raise CamError(f"thread_depths: h > 0, first > 0, minimum ≥ 0 olmalı ({h}, {first}, {minimum})")
    if isinstance(spring, bool) or not isinstance(spring, int) or spring < 0:
        raise CamError(f"thread_depths: boş paso sayısı ≥ 0 tam sayı olmalı ({spring!r})")
    out: list[float] = []
    prev, i = 0.0, 1
    while True:
        hi = first * math.sqrt(i)
        if hi - prev < minimum:
            hi = prev + minimum
        if hi >= h - TOL:
            out.append(float(h))
            break
        out.append(hi)
        prev, i = hi, i + 1
    return out + [float(h)] * spring


def thread(
    stock: CylinderStock,
    tool: LatheTool,
    cut: TurnCut,
    z_start: float,
    z_end: float,
    x0: float,
    pitch: float,
    depth: float,
    first: float,
    minimum: float = 0.0,
    spring: int = 1,
    infeed: str = "radyal",
    side: str = "dis",
    name: str = "dis",
) -> Toolpath:
    """Diş çekme: her paso G1, feed = hatve (mm/dev); radyal veya yanak (Δz = s·h_i·tan(εr/2)) dalma."""
    sgn = check_side(side)
    tip = _check_tool(tool, {LatheToolKind.THREAD}, {8, 0, 9}, sgn, "Diş")
    fr = _frame(stock, tool, cut, sgn)
    if cut.css is not None:
        raise CamError("Diş sabit devirle çekilir: css verilemez")
    if infeed not in INFEEDS:
        raise CamError(f"Dalma yönü 'radyal' veya 'yanak' olmalı ({infeed!r})")
    for ad, v in (("z_start", z_start), ("z_end", z_end), ("x0", x0), ("pitch", pitch), ("depth", depth)):
        if not math.isfinite(v):
            raise CamError(f"Diş: {ad} sonlu olmalı ({v})")
    if not pitch > 0:
        raise CamError(f"Hatve pozitif olmalı (P={pitch})")
    if abs(z_end - z_start) <= TOL:
        raise CamError("Diş boyu sıfır olamaz (z_start = z_end)")
    if sgn > 0 and x0 - depth <= 0:
        raise CamError(f"Diş dibi eksenin altında (x0 − h = {x0 - depth})")
    hs = thread_depths(depth, first, minimum, spring)
    s = 1.0 if z_end > z_start else -1.0
    tan_half = math.tan(math.radians(tool.eps_r / 2))
    r = tool.nose_r
    xf = sgn * x0
    top = xf + cut.clearance + r
    b = _start(fr, tool, tip, cut)
    b.feed = pitch
    for hi in hs:
        dz = s * hi * tan_half if infeed == "yanak" else 0.0
        cx = xf - hi + r
        b.rapid(z_start + dz, top)
        b.rapid(z_start + dz, cx)
        b.line(z_end + dz, cx, pitch)
        b.rapid(z_end + dz, top)
    return _finish_tp(name, tool, cut, fr, b)
