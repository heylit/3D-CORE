"""
SPEC 03 — 2D ilkel geometri: kesişim, uzaklık, sarım sayısı.

Parçalar `cam.profile.Line` ve `cam.profile.Arc`'tır. Bu modül onları ördek tipiyle tanır
(yayın `c` merkezi vardır), böylece `cam.profile` bu modülü döngüsüz import edebilir.

Tüm karşılaştırmalar tek bir `TOL` ile yapılır; uç uca bağlantı `LINK_TOL` ile kontrol edilir.
"""

from __future__ import annotations

import math

import numpy as np

TOL = 1e-9         # mm: geometrik eşitlik / sıfır boy
LINK_TOL = 1e-7    # mm: parçaların uç uca bağlı sayılması
AREA_TOL = 1e-14   # mm²: bundan küçük alanlı halka sıfır alanlı sayılır
TWO_PI = 2 * math.pi


def is_arc(seg) -> bool:
    return hasattr(seg, "c")


def cross(a, b) -> float:
    """2D çapraz çarpım a × b (z bileşeni)."""
    return float(a[0] * b[1] - a[1] * b[0])


def arc_param(seg, p) -> tuple[float, float]:
    """Yay üzerindeki (veya merkezden bakınca aynı açıdaki) noktanın parametresi.

    Döner: (t, taşma) — t ∈ [0, 1] yayın içinde; dışındaysa t en yakın uca kenetlenir ve taşma > 0
    (açısal fark × R, yani yay boyunca mm cinsinden).
    """
    a = math.atan2(p[1] - seg.c[1], p[0] - seg.c[0])
    sgn = 1.0 if seg.ccw else -1.0
    raw = (sgn * (a - seg.a0)) % TWO_PI
    sweep = seg.sweep
    if raw <= sweep:
        return raw / sweep, 0.0
    over_end = (raw - sweep) * seg.R
    over_start = (TWO_PI - raw) * seg.R
    if over_start < over_end:
        return 0.0, over_start
    return 1.0, over_end


def closest(p, seg) -> tuple[float, float]:
    """Parça üzerinde p'ye en yakın noktanın parametresi ve uzaklık: (t, dist)."""
    p = np.asarray(p, dtype=float)
    if is_arc(seg):
        rho = float(np.hypot(*(p - seg.c)))
        if rho < TOL:
            return 0.0, seg.R
        t, over = arc_param(seg, p)
        if over == 0.0:
            return t, abs(rho - seg.R)
        d0 = float(np.hypot(*(p - seg.p0)))
        d1 = float(np.hypot(*(p - seg.p1)))
        return (0.0, d0) if d0 <= d1 else (1.0, d1)
    v = seg.p1 - seg.p0
    t = float(np.clip(np.dot(p - seg.p0, v) / np.dot(v, v), 0.0, 1.0))
    return t, float(np.hypot(*(p - (seg.p0 + t * v))))


def distance(p, seg) -> float:
    """Noktanın parçaya en kısa uzaklığı [mm]."""
    return closest(p, seg)[1]


def distance_to_region(p, region) -> float:
    """Noktanın bölge sınırına (dış halka + adalar) en kısa uzaklığı [mm]."""
    return min(distance(p, s) for loop in region.loops for s in loop.segments)


def _angle(a, b) -> float:
    """a vektöründen b'ye işaretli açı (−π, π]."""
    return math.atan2(cross(a, b), float(np.dot(a, b)))


def winding(p, profile) -> int:
    """Kapalı profilin p etrafındaki sarım sayısı (CCW +1). Açı toplamıyla, yaylar dahil.

    Yay katkısı = kirişin gördüğü açı + 2π·w; w = ±1 (CCW/CW) eğer p yay ile kiriş arasındaki
    daire parçasının içindeyse (CCW yayda kirişin sağı, CW yayda solu), değilse 0.
    """
    p = np.asarray(p, dtype=float)
    total = 0.0
    for s in profile.segments:
        a = s.p0 - p
        b = s.p1 - p
        if is_arc(s):
            sgn = 1.0 if s.ccw else -1.0
            inside_disk = float(np.hypot(*(p - s.c))) < s.R
            if s.full:
                total += TWO_PI * sgn if inside_disk else 0.0
                continue
            total += _angle(a, b)
            side = cross(s.p1 - s.p0, p - s.p0)        # > 0: kirişin solu
            if inside_disk and sgn * side < 0:
                total += TWO_PI * sgn
        else:
            total += _angle(a, b)
    return int(round(total / TWO_PI))


# ------------------------------------------------------------------ kesişimler


def _line_line(a, b) -> list[tuple[float, float]]:
    u = a.p1 - a.p0
    v = b.p1 - b.p0
    w = b.p0 - a.p0
    den = cross(u, v)
    lu = float(np.hypot(*u))
    lv = float(np.hypot(*v))
    if abs(den) <= TOL * lu * lv:
        # paralel: sadece aynı doğrultudaysa örtüşme uçları
        if abs(cross(u, w)) / lu > TOL:
            return []
        out = []
        for p, tb_known in ((b.p0, 0.0), (b.p1, 1.0)):
            ta, d = closest(p, a)
            if d <= TOL:
                out.append((ta, tb_known))
        for p, ta_known in ((a.p0, 0.0), (a.p1, 1.0)):
            tb, d = closest(p, b)
            if d <= TOL:
                out.append((ta_known, tb))
        return out
    ta = cross(w, v) / den
    tb = cross(w, u) / den
    ea, eb = TOL / lu, TOL / lv
    if -ea <= ta <= 1 + ea and -eb <= tb <= 1 + eb:
        return [(min(max(ta, 0.0), 1.0), min(max(tb, 0.0), 1.0))]
    return []


def _line_circle_pts(line, c, R) -> list[np.ndarray]:
    """Doğru parçasının (uzantısı dahil, t parametresiyle) çemberle kesişim noktaları."""
    d = line.p1 - line.p0
    f = line.p0 - c
    A = float(np.dot(d, d))
    B = 2 * float(np.dot(f, d))
    C = float(np.dot(f, f)) - R * R
    disc = B * B - 4 * A * C
    L = math.sqrt(A)
    # teğet toleransı: çembere en yakın uzaklık |R - h| ≤ TOL
    h = abs(cross(d, f)) / L
    if disc < 0:
        if h - R > TOL:
            return []
        disc = 0.0
    sq = math.sqrt(disc)
    ts = [(-B - sq) / (2 * A), (-B + sq) / (2 * A)]
    if sq * L / A <= TOL:          # tek (teğet) nokta
        ts = [-B / (2 * A)]
    return [line.p0 + t * d for t in ts]


def _circle_circle_pts(c1, R1, c2, R2) -> list[np.ndarray]:
    dv = c2 - c1
    dd = float(np.hypot(*dv))
    if dd < TOL:
        return []          # eş merkezli: aynı çemberse örtüşme ayrıca ele alınır
    if dd > R1 + R2 + TOL or dd < abs(R1 - R2) - TOL:
        return []
    a = (R1 * R1 - R2 * R2 + dd * dd) / (2 * dd)
    h2 = R1 * R1 - a * a
    e = dv / dd
    base = c1 + a * e
    if h2 <= (TOL * max(R1, 1.0)) ** 2:
        return [base]
    h = math.sqrt(h2)
    n = np.array([-e[1], e[0]])
    return [base + h * n, base - h * n]


def _param_on(seg, p) -> float | None:
    """p parça üzerindeyse (TOL) parametresi, değilse None."""
    t, d = closest(p, seg)
    return t if d <= 10 * TOL else None


def intersect(a, b) -> list[tuple[float, float]]:
    """İki parçanın kesişimleri: parametre çiftleri [(t_a, t_b), ...].

    Örtüşen (aynı doğru / aynı çember) parçalarda örtüşmenin uç noktaları döner.
    """
    if not is_arc(a) and not is_arc(b):
        return _line_line(a, b)
    if is_arc(a) and not is_arc(b):
        return [(ta, tb) for tb, ta in intersect(b, a)]
    if is_arc(b) and not is_arc(a):
        pts = _line_circle_pts(a, b.c, b.R)
    else:
        same_circle = float(np.hypot(*(a.c - b.c))) < TOL and abs(a.R - b.R) < TOL
        if same_circle:
            pts = [b.p0, b.p1, a.p0, a.p1]
        else:
            pts = _circle_circle_pts(a.c, a.R, b.c, b.R)
    out = []
    for p in pts:
        ta = _param_on(a, p)
        tb = _param_on(b, p)
        if ta is not None and tb is not None:
            out.append((ta, tb))
    return out
