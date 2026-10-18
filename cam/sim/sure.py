"""
SPEC 72 — Sarsıntı sınırlı (S eğrisi) hareket süresi, köşe hızı, ileri-geri hız planlaması, eksen sınırları.

SPEC 05'in `move_time`'ı (tam duruş, sonsuz sarsıntı) aynen kalır; bu modül onun genellemesidir:
j → ∞ ve tol = 0 iken süreler SPEC 05 ile aynıdır (K3).

Birimler: hız mm/s (iç hesap), girdi F ve eksen hızları mm/dk; ivme mm/s², sarsıntı mm/s³;
döner eksen hızı derece/dk, ivmesi derece/s².
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from cam.model import ARCS, CamError, FeedMode, LatheTool, MoveType, Plane, Toolpath
from cam.sim.lathe_time import lathe_move_time
from cam.sim.timing import Machine

BISECT_TOL = 1e-9  # mm/s, ikiye bölmenin mutlak hız toleransı (Teori 2)
STRAIGHT_TOL = 1e-12  # 1 − u₁·u₂ bundan küçükse düz devam (φ = 0), 1 + u₁·u₂ küçükse geri dönüş (φ = π)
AXIS_EPS = 1e-15  # yön bileşeni bundan küçükse o eksen sınırı etkisiz (SPEC 05 _axis_limit)


def _finite_pos(ad: str, x) -> float:
    if isinstance(x, bool) or not isinstance(x, int | float) or not math.isfinite(x) or x <= 0:
        raise CamError(f"{ad} pozitif sonlu olmalı ({x})")
    return float(x)


def _finite_nonneg(ad: str, x) -> float:
    if isinstance(x, bool) or not isinstance(x, int | float) or not math.isfinite(x) or x < 0:
        raise CamError(f"{ad} ≥ 0 sonlu olmalı ({x})")
    return float(x)


def _pos_tuple(ad: str, vals) -> tuple[float, ...]:
    try:
        t = tuple(vals)
    except TypeError:
        raise CamError(f"Dynamics.{ad} sayı dizisi olmalı ({vals})") from None
    return tuple(_finite_pos(f"Dynamics.{ad}[{i}]", v) for i, v in enumerate(t))


@dataclass(frozen=True)
class Dynamics:
    """Eksen başına dinamik sınırlar (X, Y, Z [+ döner]).

    v_max mm/dk, a_max mm/s², j_max mm/s³ (None → sonsuz sarsıntı); rot_v derece/dk, rot_a derece/s²;
    tol = yol toleransı ε [mm] (0 → her köşede tam duruş); lookahead = ileri bakış ufku (None → sınırsız).
    Pozitif olmayan / sonlu olmayan değer → CamError.
    """

    v_max: tuple[float, ...]
    a_max: tuple[float, ...]
    j_max: tuple[float, ...] | None
    rot_v: tuple[float, ...] = ()
    rot_a: tuple[float, ...] = ()
    tol: float = 0.0
    lookahead: int | None = None

    def __post_init__(self) -> None:
        v = _pos_tuple("v_max", self.v_max)
        a = _pos_tuple("a_max", self.a_max)
        if len(v) < 3 or len(a) != len(v):
            raise CamError(f"Dynamics: v_max ve a_max en az X, Y, Z için aynı uzunlukta olmalı ({v}, {a})")
        j = None if self.j_max is None else _pos_tuple("j_max", self.j_max)
        if j is not None and len(j) != len(v):
            raise CamError(f"Dynamics: j_max uzunluğu v_max ile aynı olmalı ({j})")
        rv = _pos_tuple("rot_v", self.rot_v)
        ra = _pos_tuple("rot_a", self.rot_a)
        if len(rv) != len(ra):
            raise CamError(f"Dynamics: rot_v ve rot_a aynı uzunlukta olmalı ({rv}, {ra})")
        tol = _finite_nonneg("Dynamics.tol", self.tol)
        n = self.lookahead
        if n is not None and (isinstance(n, bool) or not isinstance(n, int) or n < 1):
            raise CamError(f"Dynamics.lookahead pozitif tam sayı veya None olmalı ({n})")
        for ad, val in (("v_max", v), ("a_max", a), ("j_max", j), ("rot_v", rv), ("rot_a", ra), ("tol", tol)):
            object.__setattr__(self, ad, val)


@dataclass(frozen=True)
class PathTime:
    """Bir takım yolunun süresi [s]: kesme (G1/G2/G3) ve hızlı (G0) ayrı."""

    cut: float
    rapid: float
    n_moves: int

    @property
    def total(self) -> float:
        return self.cut + self.rapid


# ---------------------------------------------------------------- Teori 1–2: S eğrisi


def _tau(dv: float, a: float, j: float | None) -> float:
    """Δv hız değişiminin süresi: Δv/a + a/j (Δv ≥ a²/j) ya da 2√(Δv/j); j = None → Δv/a."""
    if dv <= 0:
        return 0.0
    if j is None:
        return dv / a
    if dv >= a * a / j:
        return dv / a + a / j
    return 2 * math.sqrt(dv / j)


def _dist(w0: float, w1: float, a: float, j: float | None) -> float:
    """w0 → w1 hız değişiminin yolu: (w0 + w1)·τ(|Δv|)/2."""
    return (w0 + w1) * _tau(abs(w1 - w0), a, j) / 2


def _stop_to_stop(L: float, v: float, a: float, j: float | None) -> float:
    """Duruştan duruşa kapalı formlar (Teori 1)."""
    if j is None:
        if L >= v * v / a:
            return L / v + v / a
        return 2 * math.sqrt(L / a)
    if v >= a * a / j:
        s_h = v * (v / a + a / j) / 2
        if L >= 2 * s_h:
            return L / v + v / a + a / j
        if L >= 2 * a**3 / j**2:
            vp = (a / 2) * (-a / j + math.sqrt(a * a / (j * j) + 4 * L / a))
            return 2 * (vp / a + a / j)
        return 4 * (L / (2 * j)) ** (1 / 3)
    t_h = 2 * math.sqrt(v / j)
    if L >= v * t_h:  # 2·s_h = v·t_h
        return L / v + t_h
    return 4 * (L / (2 * j)) ** (1 / 3)


def _bisect(f, lo: float, hi: float) -> float:
    """f artan; f(x) ≤ 0 olan en büyük x (mutlak BISECT_TOL'a kadar, güvenli taraf lo)."""
    for _ in range(200):
        if hi - lo <= BISECT_TOL:
            break
        mid = (lo + hi) / 2
        if f(mid) <= 0:
            lo = mid
        else:
            hi = mid
    return lo


def _check_scurve(L, v, a, j, v0, v1) -> None:
    _finite_nonneg("scurve_time: L", L)
    _finite_pos("scurve_time: v", v)
    _finite_pos("scurve_time: a", a)
    if j is not None:
        _finite_pos("scurve_time: j", j)
    _finite_nonneg("scurve_time: v0", v0)
    _finite_nonneg("scurve_time: v1", v1)
    if v0 > v * (1 + 1e-12) or v1 > v * (1 + 1e-12):
        raise CamError(f"scurve_time: giriş / çıkış hızı v'yi aşıyor (v0={v0}, v1={v1}, v={v})")


def scurve_time(L: float, v: float, a: float, j: float | None, v0: float = 0.0, v1: float = 0.0) -> float:
    """L boyunu v0 hızla girip v1 hızla çıkarak, v, a, j sınırlarıyla geçme süresi [s] (Teori 1–2)."""
    _check_scurve(L, v, a, j, v0, v1)
    v0, v1 = min(v0, v), min(v1, v)
    if v0 == 0 and v1 == 0:
        return _stop_to_stop(L, v, a, j) if L > 0 else 0.0
    need = _dist(v0, v1, a, j)
    if need > L * (1 + 1e-9) + 1e-12:
        raise CamError(
            f"scurve_time: {v0} → {v1} mm/s hız değişimi L = {L} mm içinde yapılamıyor (gereken {need})"
        )
    d_up = _dist(v0, v, a, j) + _dist(v, v1, a, j)
    if d_up <= L:  # sabit hız evresi var
        return _tau(v - v0, a, j) + _tau(v - v1, a, j) + (L - d_up) / v
    w = max(v0, v1)
    vp = _bisect(lambda x: _dist(v0, x, a, j) + _dist(x, v1, a, j) - L, w, v)
    return _tau(vp - v0, a, j) + _tau(vp - v1, a, j)


def _reach(w: float, L: float, v: float, a: float, j: float | None) -> float:
    """v_hız(w, L): w'den başlayıp L boyda ulaşılabilen en büyük hız (≤ v) (Teori 4)."""
    if w >= v:
        return v
    if _dist(w, v, a, j) <= L:
        return v
    return _bisect(lambda x: _dist(w, x, a, j) - L, w, v)


# ---------------------------------------------------------------- Teori 3: köşe hızı


def _unit(u) -> np.ndarray:
    u = np.asarray(u, dtype=float)
    n = float(np.linalg.norm(u))
    if not math.isfinite(n) or n == 0:
        raise CamError(f"junction_speed: yön vektörü sıfır veya sonlu değil ({u})")
    return u / n


def junction_speed(u1, u2, F: float, a: float, tol: float, L1: float, L2: float) -> float:
    """İki doğrusal segment arasındaki köşe hızı [mm/s] (Teori 3); F mm/s."""
    F = _finite_nonneg("junction_speed: F", F)
    a = _finite_pos("junction_speed: a", a)
    tol = _finite_nonneg("junction_speed: tol", tol)
    L1 = _finite_pos("junction_speed: L1", L1)
    L2 = _finite_pos("junction_speed: L2", L2)
    if tol == 0:
        return 0.0  # her köşede tam duruş
    c = float(np.clip(np.dot(_unit(u1), _unit(u2)), -1.0, 1.0))
    if 1 - c <= STRAIGHT_TOL:
        return F  # φ = 0: düz devam
    if 1 + c <= STRAIGHT_TOL:
        return 0.0  # φ = π: geri dönüş
    phi = math.acos(c)
    ch = math.cos(phi / 2)
    R = tol * ch / (2 * math.sin(phi / 4) ** 2)  # 1 − cos(φ/2) = 2 sin²(φ/4)
    t = math.tan(phi / 2)
    R = min(R, min(L1, L2) / 2 / t)  # teğet boyu R·tan(φ/2) ≤ min(L1, L2)/2
    return min(F, math.sqrt(a * R))


# ---------------------------------------------------------------- eksen sınırları (Teori 5)


def _path_limit(u: np.ndarray, lim: tuple[float, ...]) -> float:
    """Yön u (birim, 3B) için eksen sınırlarını aşmayan en büyük yol değeri: min lim_i / |u_i|."""
    return min(lim[i] / abs(u[i]) for i in range(3) if abs(u[i]) > AXIS_EPS)


@dataclass
class _Seg:
    """Planlanacak kesme segmenti: boy, giriş / çıkış teğeti, hız / ivme / sarsıntı sınırı, blok boyları."""

    L: float
    t0: np.ndarray
    t1: np.ndarray
    v: float  # mm/s
    a: float
    j: float | None
    line: bool = True
    blocks: list[float] = field(default_factory=list)


def _line_seg(p0, p1, F_mm_s: float, dyn: Dynamics) -> _Seg:
    d = np.asarray(p1, dtype=float) - np.asarray(p0, dtype=float)
    L = float(np.linalg.norm(d))
    u = d / L
    v = min(F_mm_s, _path_limit(u, dyn.v_max) / 60)
    j = None if dyn.j_max is None else _path_limit(u, dyn.j_max)
    return _Seg(L, u, u, v, _path_limit(u, dyn.a_max), j, True, [L])


def _plan(segs: list[_Seg], dyn: Dynamics) -> list[float]:
    """Sınır hızları (ilk ve son 0): köşe hızı, ileri bakış ufku, geri ve ileri geçiş (Teori 3–4)."""
    n = len(segs)
    vb = [0.0] * (n + 1)
    N = dyn.lookahead
    if N is not None:
        _apply_lookahead(segs, N)
    for i in range(1, n):
        s, t = segs[i - 1], segs[i]
        vb[i] = junction_speed(s.t1, t.t0, min(s.v, t.v), min(s.a, t.a), dyn.tol, s.L, t.L)
    for i in range(n - 1, 0, -1):  # geri geçiş
        s = segs[i]
        vb[i] = min(vb[i], _reach(vb[i + 1], s.L, s.v, s.a, s.j))
    for i in range(1, n):  # ileri geçiş
        s = segs[i - 1]
        vb[i] = min(vb[i], _reach(vb[i - 1], s.L, s.v, s.a, s.j))
    return vb


def _apply_lookahead(segs: list[_Seg], N: int) -> None:
    """Ufuk N blok: her blok başında hız, sonraki N bloğun toplam boyunda durabilecek kadar (Karar 3).

    Ufku zincirin sonuna (tam duruşa) uzanan bloklarda sınır, geri geçişin duruş sınırıyla aynıdır ve
    atlanır. Birleştirilmiş segmentin seyir hızı, içindeki blok başlarının en küçük sınırına indirilir.
    """
    blocks = [(k, L) for k, s in enumerate(segs) for L in s.blocks]
    nb = len(blocks)
    csum = np.concatenate(([0.0], np.cumsum([L for _, L in blocks])))
    for b in range(nb - N):
        k = blocks[b][0]
        s = segs[k]
        window = float(csum[b + N] - csum[b])  # Σ lengths[b : b + N]
        s.v = min(s.v, _reach(0.0, window, s.v, s.a, s.j))


def _merge(segs: list[_Seg]) -> list[_Seg]:
    """Aynı doğrultuda (φ = 0) ve aynı sınırlı ardışık doğru segmentleri tek segmentte birleştirir.

    S eğrisinde blok sınırında ivme sıfırlanmaz; bölmek süreyi değiştirmemeli (K5, K6).
    """
    out: list[_Seg] = []
    for s in segs:
        if out:
            p = out[-1]
            if (
                p.line
                and s.line
                and 1 - float(np.dot(p.t1, s.t0)) <= STRAIGHT_TOL
                and math.isclose(p.v, s.v, rel_tol=1e-12)
            ):
                p.L += s.L
                p.blocks += s.blocks
                p.v = min(p.v, s.v)
                p.a = min(p.a, s.a)
                p.j = None if p.j is None or s.j is None else min(p.j, s.j)
                continue
        out.append(s)
    return out


def _chain_time(segs: list[_Seg], dyn: Dynamics) -> float:
    if not segs:
        return 0.0
    if dyn.tol > 0:
        segs = _merge(segs)
    vb = _plan(segs, dyn)
    return sum(scurve_time(s.L, s.v, s.a, s.j, vb[i], vb[i + 1]) for i, s in enumerate(segs))


def plan_speeds(segments, dyn: Dynamics) -> list[float]:
    """Segment sınır hızları [mm/s], ileri-geri geçişle (Teori 4); ilk ve son 0.

    segments: [(p0, p1, F mm/dk), ...] ardışık 3B doğrusal parçalar.
    """
    if not isinstance(dyn, Dynamics):
        raise CamError("plan_speeds: Dynamics bekleniyor")
    segs = []
    for i, (p0, p1, F) in enumerate(segments):
        F = _finite_pos(f"plan_speeds: segment {i} F", F)
        if float(np.linalg.norm(np.asarray(p1, float) - np.asarray(p0, float))) <= 0:
            raise CamError(f"plan_speeds: segment {i} sıfır boylu")
        segs.append(_line_seg(p0, p1, F / 60, dyn))
    if not segs:
        return [0.0]
    return _plan(segs, dyn)


# ---------------------------------------------------------------- takım yolu


_UVW = {Plane.XY: (0, 1, 2), Plane.ZX: (2, 0, 1)}


def _arc(p0: np.ndarray, p1: np.ndarray, center, plane: Plane, cw: bool):
    """Yay: (r, |Δθ|, L, t0, t1); (u, v) düzlemi XY → (x, y), ZX → (z, x); merkez XY (x, y), ZX (x, z)."""
    iu, iv, iw = _UVW[plane]
    cu, cv = (center[0], center[1]) if plane is Plane.XY else (center[1], center[0])
    a0 = math.atan2(p0[iv] - cv, p0[iu] - cu)
    a1 = math.atan2(p1[iv] - cv, p1[iu] - cu)
    r = math.hypot(p0[iu] - cu, p0[iv] - cv)
    dth = (a0 - a1) if cw else (a1 - a0)
    dth %= 2 * math.pi
    if dth < 1e-12:
        dth = 2 * math.pi
    dw = float(p1[iw] - p0[iw])
    L = math.hypot(r * dth, dw)
    sgn = -1.0 if cw else 1.0

    def tangent(th: float) -> np.ndarray:
        t = np.zeros(3)
        t[iu] = -sgn * math.sin(th) * r * dth
        t[iv] = sgn * math.cos(th) * r * dth
        t[iw] = dw
        return t / np.linalg.norm(t)

    return r, dth, L, tangent(a0), tangent(a0 + sgn * dth)


def _arc_seg(p0, p1, m, tp: Toolpath, F_mm_s: float, dyn: Dynamics) -> _Seg:
    plane = tp.plane
    r, _, L, t0, t1 = _arc(p0, p1, m.center, plane, m.type is MoveType.ARC_CW)
    iu, iv, _ = _UVW[plane]
    a = min(dyn.a_max[iu], dyn.a_max[iv])
    j = None if dyn.j_max is None else min(dyn.j_max[iu], dyn.j_max[iv])
    v = min(F_mm_s, min(dyn.v_max[iu], dyn.v_max[iv]) / 60, math.sqrt(a * r))
    return _Seg(L, t0, t1, v, a, j, False, [L])


def _move_length(p0, p1, m, tp: Toolpath) -> float:
    if m.type in ARCS:
        return _arc(p0, p1, m.center, tp.plane, m.type is MoveType.ARC_CW)[2]
    return float(np.linalg.norm(p1 - p0))


def _check_extras(tp: Toolpath, dyn: Dynamics, q, inv_feed) -> tuple[np.ndarray | None, np.ndarray | None]:
    n = len(tp.moves)
    if q is not None:
        q = np.asarray(q, dtype=float)
        k = len(dyn.rot_v)
        if q.ndim != 2 or q.shape != (n + 1, 3 + k) or not np.all(np.isfinite(q)):
            raise CamError(f"toolpath_time: q (n+1, 3+k) = ({n + 1}, {3 + k}) sonlu olmalı (şekil {q.shape})")
    if inv_feed is not None:
        inv_feed = np.asarray(inv_feed, dtype=float)
        if inv_feed.shape != (n,) or not np.all(np.isfinite(inv_feed)) or np.any(inv_feed <= 0):
            raise CamError(f"toolpath_time: inv_feed ({n},) pozitif sonlu olmalı (şekil {inv_feed.shape})")
    return q, inv_feed


def _rot_time(q: np.ndarray | None, i: int, dyn: Dynamics) -> float:
    """Döner eksen sınırı: max_r |Δq_r| / ω_r [s] (ω_r = rot_v_r / 60 derece/s)."""
    if q is None or not dyn.rot_v:
        return 0.0
    dq = np.abs(q[i + 1, 3:] - q[i, 3:])
    return float(np.max(dq / (np.array(dyn.rot_v) / 60)))


def toolpath_time(
    tp: Toolpath,
    dyn: Dynamics,
    *,
    q: np.ndarray | None = None,
    tcp: bool = False,
    inv_feed: np.ndarray | None = None,
) -> PathTime:
    """Takım yolunun süresi (Teori 1–5).

    q: (n+1, 3+k) eklem değerleri (SPEC 42 `inverse_time` biçimi); q[:, 3:] döner eksenler [derece],
    `dyn.rot_v` sırasıyla. Doğrusal mesafe tp noktalarından alınır. Döner sınır t_r = |Δq_r| / ω_r.
    tcp: G43.4 / TRAORI / M128 (G1'de F uç hızı). inv_feed: (n,) G93 değerleri [1/dk], t = 60 / F_inv.

    Döner hareketli, G93'lü ve G0 hareketleri duruştan duruşadır; aradaki kesme blokları birlikte planlanır.
    tcp yalnız anlamı belgeler: F her durumda tp noktalarındaki yol hızıdır, döner sınır t = max(t, t_r).
    """
    if not isinstance(tp, Toolpath):
        raise CamError("toolpath_time: Toolpath bekleniyor")
    if not isinstance(dyn, Dynamics):
        raise CamError("toolpath_time: Dynamics bekleniyor")
    tp.validate()
    lathe = isinstance(tp.tool, LatheTool)
    if lathe and tp.plane is not Plane.ZX:
        raise CamError(f"Takım yolu '{tp.name}': torna yolu G18 (ZX) düzleminde olmalı")
    q, inv_feed = _check_extras(tp, dyn, q, inv_feed)
    m22 = Machine(rapid=dyn.v_max[:3], accel=None) if lathe else None

    cut = rapid = 0.0
    chain: list[_Seg] = []
    pts = tp.points()
    for i, m in enumerate(tp.moves):
        p0, p1 = pts[i], pts[i + 1]
        L = _move_length(p0, p1, m, tp)
        t_rot = _rot_time(q, i, dyn)
        if m.type is MoveType.RAPID:
            cut += _chain_time(chain, dyn)
            chain = []
            t = 0.0
            if L > 0:
                u = (p1 - p0) / L
                j = None if dyn.j_max is None else _path_limit(u, dyn.j_max)
                t = scurve_time(L, _path_limit(u, dyn.v_max) / 60, _path_limit(u, dyn.a_max), j)
            rapid += max(t, t_rot)
            continue
        if inv_feed is not None:
            cut += _chain_time(chain, dyn)
            chain = []
            cut += 60 / float(inv_feed[i])
            continue
        if L == 0:
            if t_rot > 0:
                cut += _chain_time(chain, dyn) + t_rot
                chain = []
            continue
        seg = _cut_seg(p0, p1, m, tp, dyn, L, m22)
        if t_rot > 0:
            cut += _chain_time(chain, dyn)
            chain = []
            cut += max(scurve_time(seg.L, seg.v, seg.a, seg.j), t_rot)
            continue
        chain.append(seg)
    cut += _chain_time(chain, dyn)
    return PathTime(cut=cut, rapid=rapid, n_moves=len(tp.moves))


def _cut_seg(p0, p1, m, tp: Toolpath, dyn: Dynamics, L: float, m22: Machine | None) -> _Seg:
    """Kesme hareketinin segmenti. Torna: v_eş = L / t_22 (SPEC 22, sınırsız ivme) (Teori 7)."""
    if m22 is not None:
        v = L / lathe_move_time(p0, p1, m, tp, m22)
    elif tp.feed_mode is FeedMode.PER_REV:
        v = m.feed * tp.rpm / 60
    else:
        v = m.feed / 60
    if m.type in ARCS:
        return _arc_seg(p0, p1, m, tp, v, dyn)
    return _line_seg(p0, p1, v, dyn)
