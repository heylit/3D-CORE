"""
SPEC 03 — Bölge ofseti (takım yarıçapı telafisi): ham ofset + budama, yaylar korunur.

d > 0: iç ofset  Ω ⊖ B_d  = { p ∈ Ω : dist(p, ∂Ω) ≥ d }
d < 0: dış ofset Ω ⊕ B_|d|

Adımlar (Held, *On the Computational Geometry of Pocket Machining*, Bölüm 2–3):
1. Her halka (içi solda) soluna d kadar kaydırılır: doğru → paralel doğru, yay → R ∓ d yarıçaplı yay.
2. Köşelerde ofset tarafında boşluk varsa köşe merkezli |d| yarıçaplı yay, örtüşme varsa q → V → p doğruları.
3. Tüm ham parçalar ikili kesişimlerinden bölünür.
4. Orta noktası sınıra |d|'den yakın ya da yanlış tarafta olan alt parçalar atılır.
5. Kalanlar uç uca bağlanıp halkalar, halkalardan bölgeler kurulur.
"""

from __future__ import annotations

import math

import numpy as np

from cam.geom2d import AREA_TOL, LINK_TOL, TOL, cross, distance_to_region, intersect, winding
from cam.model import CamError
from cam.profile import Arc, Line, Profile, Region, Segment

KEEP_TOL = 1e-7    # mm: budamada "sınıra tam |d| uzaklıkta" sayma toleransı
SLIVER_TOL = 1e-6  # mm: kapanmayan zincir bundan inceyse çökmüş şerit sayılır (boş)


def _left(t: np.ndarray) -> np.ndarray:
    return np.array([-t[1], t[0]])


def _offset_point(s: Segment, t: float, d: float) -> np.ndarray:
    """Parçanın t noktasının soluna d kaydırılmış hali."""
    return s.point(t) + d * _left(s.tangent(t))


def _raw_offset(loop: Profile, d: float) -> list[Segment]:
    """Halkanın ham ofset eğrisi (budanmamış), uç uca kapalı zincir."""
    segs = loop.segments
    n = len(segs)
    out: list[Segment] = []
    for i, s in enumerate(segs):
        a = _offset_point(s, 0.0, d)
        b = _offset_point(s, 1.0, d)
        if isinstance(s, Line):
            out.append(Line(a, b))
        else:
            Rn = s.R - d if s.ccw else s.R + d
            if Rn > TOL:
                out.append(Arc(a, a if s.full else b, s.c, s.ccw))
            else:
                # çöken yay: merkezden geçen iki doğru (budamada atılır)
                for p, q in ((a, s.c), (s.c, b)):
                    if np.hypot(*(q - p)) > TOL:
                        out.append(Line(p, q))
        # köşe bağlantısı (i → i+1)
        nxt = segs[(i + 1) % n]
        e = b
        sp = _offset_point(nxt, 0.0, d)
        if np.hypot(*(sp - e)) <= LINK_TOL:
            continue
        V = s.p1
        k = cross(s.tangent(1.0), nxt.tangent(0.0))
        gap = (k < 0) if d > 0 else (k > 0)
        if gap:
            out.append(Arc(e, sp, V, ccw=(d < 0)))
        else:
            for p, q in ((e, V), (V, sp)):
                if np.hypot(*(q - p)) > TOL:
                    out.append(Line(p, q))
    return out


def _split_all(pieces: list[Segment]) -> list[Segment]:
    """Parçaları birbirleriyle kesişim noktalarından böler."""
    params: list[list[float]] = [[0.0, 1.0] for _ in pieces]
    for i in range(len(pieces)):
        for j in range(i + 1, len(pieces)):
            for ti, tj in intersect(pieces[i], pieces[j]):
                params[i].append(ti)
                params[j].append(tj)
    out: list[Segment] = []
    for s, ts in zip(pieces, params, strict=True):
        ts = sorted(ts)
        L = s.length
        for t0, t1 in zip(ts[:-1], ts[1:], strict=True):
            if (t1 - t0) * L > LINK_TOL:
                out.append(s.sub(t0, t1))
    return out


def _mid(s: Segment) -> np.ndarray:
    return s.point(0.5)


def _chain(pieces: list[Segment]) -> list[list[Segment]]:
    """Yönlü parçaları uç uca bağlayıp kapalı halkalar kurar.

    Bir uçta birden çok aday varsa en çok sola dönen seçilir (içi solda kalan küçük halkayı izler).
    """
    unused = list(range(len(pieces)))
    loops = []
    while unused:
        cur = [pieces[unused.pop(0)]]
        start = cur[0].p0
        while np.hypot(*(cur[-1].p1 - start)) > LINK_TOL:
            end = cur[-1].p1
            cands = [k for k in unused if np.hypot(*(pieces[k].p0 - end)) <= LINK_TOL]
            if not cands:
                break
            t_in = cur[-1].tangent(1.0)

            def turn(k, t_in=t_in):
                t_out = pieces[k].tangent(0.0)
                return math.atan2(cross(t_in, t_out), float(np.dot(t_in, t_out)))

            k = max(cands, key=turn)
            unused.remove(k)
            cur.append(pieces[k])
        if np.hypot(*(cur[-1].p1 - start)) <= LINK_TOL:
            loops.append(cur)
        elif _thickness(cur) > SLIVER_TOL:
            raise CamError("Ofset halkası kapanmadı (sayısal hata)")
        # aksi halde: çökmek üzere olan şerit (kalınlık ≤ SLIVER_TOL), boş sayılır
    return loops


def _thickness(chain: list[Segment]) -> float:
    """Parça zincirinin en ince doğrultudaki genişliği (noktaların temel eksenlere göre yayılımı)."""
    pts = np.array([s.point(t) for s in chain for t in (0.0, 0.5, 1.0)])
    pts = pts - pts.mean(axis=0)
    if len(pts) < 3:
        return 0.0
    return float(2 * np.sqrt(max(np.linalg.eigvalsh(pts.T @ pts / len(pts))[0], 0.0)))


def _mergeable(a: Segment, b: Segment) -> bool:
    if isinstance(a, Line) and isinstance(b, Line):
        ta, tb = a.tangent(0), b.tangent(0)
        return abs(cross(ta, tb)) < TOL and float(np.dot(ta, tb)) > 0
    if isinstance(a, Arc) and isinstance(b, Arc):
        return (a.ccw == b.ccw and np.hypot(*(a.c - b.c)) < 1e-8 and abs(a.R - b.R) < 1e-8)
    return False


def _merge2(a: Segment, b: Segment) -> Segment:
    if isinstance(a, Line):
        return Line(a.p0, b.p1)
    total = a.sweep + b.sweep
    end = a.p0 if total >= 2 * math.pi - 1e-9 else b.p1
    return Arc(a.p0, end, a.c, a.ccw)


def merge_segments(segs: list[Segment], closed: bool = True) -> list[Segment]:
    """Ardışık aynı doğrultudaki doğruları ve aynı çember üzerindeki yayları birleştirir."""
    out = list(segs)
    changed = True
    while changed and len(out) > 1:
        changed = False
        for i in range(len(out) - (0 if closed else 1)):
            j = (i + 1) % len(out)
            if j == i:
                break
            if _mergeable(out[i], out[j]):
                m = _merge2(out[i], out[j])
                if j == 0:
                    out = [m] + out[1:i]
                else:
                    out[i:j + 1] = [m]
                changed = True
                break
    return out


def _to_regions(loops: list[Profile]) -> list[Region]:
    """Halkaları bölgelere ayırır: CCW halkalar dış, CW halkalar en küçük kapsayan dışa ada olur."""
    outers = [lp for lp in loops if lp.area > 0]
    holes = [lp for lp in loops if lp.area < 0]
    outers.sort(key=lambda p: p.area)
    groups: list[list[Profile]] = [[] for _ in outers]
    for h in holes:
        p = h.segments[0].point(0.5)
        for gi, o in enumerate(outers):
            if winding(p, o) != 0:
                groups[gi].append(h)
                break
    return [Region(o, g) for o, g in zip(outers, groups, strict=True)]


def offset(region: Region, d: float) -> list[Region]:
    """Bölgenin d ofseti; d > 0 iç, d < 0 dış. Boş olabilir. Dar boğazda birden çok bölge döner."""
    if not isinstance(region, Region):
        raise CamError("offset: Region bekleniyor")
    d = float(d)
    if abs(d) < TOL:
        raise CamError("offset: d sıfır olamaz")
    raw: list[Segment] = []
    for loop in region.loops:
        raw.extend(_raw_offset(loop, d))
    pieces = _split_all(raw)
    keep = []
    for s in pieces:
        m = _mid(s)
        if distance_to_region(m, region) < abs(d) - KEEP_TOL:
            continue
        if region.contains(m) != (d > 0):
            continue
        keep.append(s)
    loops = []
    for chain in _chain(keep):
        segs = merge_segments(chain)
        p = Profile(segs)
        if abs(p.area) > AREA_TOL:
            loops.append(p)
    return _to_regions(loops)


def offset_profile(profile: Profile, d: float) -> list[Region]:
    """Kapalı profilin sınırladığı bölgenin d ofseti (kısayol)."""
    return offset(Region(profile), d)
