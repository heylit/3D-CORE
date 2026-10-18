"""
SPEC 17 — çözülmüş eskizden ekstrüzyona hazır bölgeler ve yaylı döngü alanı.

Kurallar: specs/17-kroki.md "Bölgeler". Alan: A = ½ Σ (u_i v_{i+1} − u_{i+1} v_i) + Σ ½ r² (α − sin α).
"""

from __future__ import annotations

import math
from collections import defaultdict

import numpy as np

from sketch.constraints import union_roots
from sketch.model import Arc, Circle, Line, SegArc, SegLine, Sketch, SketchError, SketchRegion
from sketch.solver import _System

SAT_TOL = 1e-9  # kısıtlar sağlanmış sayılır, mm
EPS = 1e-6  # kesişim / ortak uç yakınlığı, mm
TAU = 2.0 * math.pi

Seg = SegLine | SegArc
Loop = tuple[Seg, ...]


# --- Döngü geometrisi ---------------------------------------------------------------------------------


def _cross(a, b) -> float:
    return float(a[0] * b[1] - a[1] * b[0])


def _start(seg: Seg) -> np.ndarray:
    return np.asarray(seg.p0 if isinstance(seg, SegLine) else seg.start, dtype=float)


def _end(seg: Seg) -> np.ndarray:
    return np.asarray(seg.p1 if isinstance(seg, SegLine) else seg.end, dtype=float)


def _ang(v) -> float:
    return math.atan2(v[1], v[0])


def _sweep(seg: SegArc) -> float:
    """Döngü yönünde işaretli yay açısı α; başlangıç = bitiş → tam daire (±2π)."""
    c, s, e = np.asarray(seg.center, float), _start(seg), _end(seg)
    if np.allclose(s, e, atol=1e-12):
        a = TAU
    else:
        a = (_ang(e - c) - _ang(s - c)) % TAU if seg.ccw else (_ang(s - c) - _ang(e - c)) % TAU
    return a if seg.ccw else -a


def _signed_area(loop: Loop) -> float:
    A = 0.0
    for seg in loop:
        A += 0.5 * _cross(_start(seg), _end(seg))
        if isinstance(seg, SegArc):
            a = _sweep(seg)
            A += 0.5 * seg.r**2 * (a - math.sin(a))
    return A


def _reverse(loop: Loop) -> Loop:
    out = []
    for seg in reversed(loop):
        if isinstance(seg, SegLine):
            out.append(SegLine(seg.p1, seg.p0))
        else:
            out.append(SegArc(seg.center, seg.r, seg.end, seg.start, not seg.ccw))
    return tuple(out)


def _winding(loop: Loop, p: np.ndarray) -> int:
    """Kapalı döngünün p etrafındaki sarım sayısı (yaylar kesin: kiriş açısı + kesit bölgesi ±1)."""
    w = 0.0
    for seg in loop:
        s, e = _start(seg) - p, _end(seg) - p
        w += math.atan2(_cross(s, e), float(s @ e))
        if isinstance(seg, SegArc):
            c = np.asarray(seg.center, float)
            if np.linalg.norm(p - c) >= seg.r:
                continue
            tam = np.allclose(s, e, atol=1e-12)
            # CCW yay kirişin sağında, CW yay solunda; kesit bölgesi daire ∩ o yarı düzlem
            yan = _cross(_end(seg) - _start(seg), p - _start(seg))
            if tam or (yan < 0 if seg.ccw else yan > 0):
                w += TAU if seg.ccw else -TAU
    return round(w / TAU)


# --- Kesişim ------------------------------------------------------------------------------------------


def _on_arc(e: Arc | Circle, c: np.ndarray, pos: dict, q: np.ndarray) -> bool:
    if isinstance(e, Circle):
        return True
    ts = _ang(pos[e.start] - c)
    te = _ang(pos[e.end] - c)
    a = (te - ts) % TAU or TAU
    r = np.linalg.norm(pos[e.start] - c)
    rel = (_ang(q - c) - ts) % TAU
    return rel * r <= a * r + EPS or (TAU - rel) * r <= EPS


def _circle_of(e: Arc | Circle, pos: dict, rad: dict, ident: str) -> tuple[np.ndarray, float]:
    c = pos[e.center]
    return c, (rad[ident] if isinstance(e, Circle) else float(np.linalg.norm(pos[e.start] - c)))


def _intersections(ia: str, a, ib: str, b, pos: dict, rad: dict) -> list[np.ndarray]:
    """İki profil öğesinin kesişim noktaları (çakışık örtüşmede örtüşme uçları)."""
    if isinstance(b, Line) and not isinstance(a, Line):
        return _intersections(ib, b, ia, a, pos, rad)
    if isinstance(a, Line) and isinstance(b, Line):
        p, d = pos[a.p0], pos[a.p1] - pos[a.p0]
        q, f = pos[b.p0], pos[b.p1] - pos[b.p0]
        den = _cross(d, f)
        if abs(den) < 1e-12 * np.linalg.norm(d) * np.linalg.norm(f):
            if abs(_cross(d, q - p)) / np.linalg.norm(d) > EPS:
                return []
            dd = float(d @ d)
            t0, t1 = sorted((float((q - p) @ d) / dd, float((q + f - p) @ d) / dd))
            lo, hi = max(t0, 0.0), min(t1, 1.0)
            return [p + lo * d, p + hi * d] if hi >= lo else []
        t = _cross(q - p, f) / den
        u = _cross(q - p, d) / den
        tol_t, tol_u = EPS / np.linalg.norm(d), EPS / np.linalg.norm(f)
        if -tol_t <= t <= 1 + tol_t and -tol_u <= u <= 1 + tol_u:
            return [p + t * d]
        return []
    if isinstance(a, Line):
        c, r = _circle_of(b, pos, rad, ib)
        p, d = pos[a.p0], pos[a.p1] - pos[a.p0]
        dd = float(d @ d)
        w = p - c
        B, C = float(w @ d) / dd, (float(w @ w) - r * r) / dd
        D = B * B - C
        if D < 0:
            return []
        tol_t = EPS / math.sqrt(dd)
        ts = {-B - math.sqrt(D), -B + math.sqrt(D)}
        out = [p + t * d for t in ts if -tol_t <= t <= 1 + tol_t]
        return [q for q in out if _on_arc(b, c, pos, q)]
    ca, ra = _circle_of(a, pos, rad, ia)
    cb, rb = _circle_of(b, pos, rad, ib)
    v = cb - ca
    n = float(np.linalg.norm(v))
    if n < EPS and abs(ra - rb) < EPS:
        # aynı çember: yaylar örtüşüyorsa uç noktalar kesişimdir
        uclar = [pos[x] for e in (a, b) if isinstance(e, Arc) for x in (e.start, e.end)]
        if not uclar:
            return [ca + np.array([ra, 0.0])]
        return [q for q in uclar if _on_arc(a, ca, pos, q) and _on_arc(b, cb, pos, q)]
    if n > ra + rb + EPS or n < abs(ra - rb) - EPS or n < EPS:
        return []
    x = (n * n + ra * ra - rb * rb) / (2 * n)
    h = math.sqrt(max(ra * ra - x * x, 0.0))
    u = v / n
    m = ca + x * u
    pts = [m + h * np.array([-u[1], u[0]]), m - h * np.array([-u[1], u[0]])]
    return [q for q in pts if _on_arc(a, ca, pos, q) and _on_arc(b, cb, pos, q)]


def _ends(e) -> tuple[str, ...]:
    if isinstance(e, Line):
        return (e.p0, e.p1)
    if isinstance(e, Arc):
        return (e.start, e.end)
    return ()


def _check_crossings(prof: dict, pos: dict, rad: dict, roots: dict) -> None:
    ids = list(prof)
    for i, ia in enumerate(ids):
        for ib in ids[i + 1 :]:
            a, b = prof[ia], prof[ib]
            ortak = {roots[p] for p in _ends(a)} & {roots[p] for p in _ends(b)}
            uc = [pos[p] for p in _ends(a) + _ends(b) if roots[p] in ortak]
            for q in _intersections(ia, a, ib, b, pos, rad):
                if not any(np.linalg.norm(q - o) <= EPS for o in uc):
                    raise SketchError(
                        f"Profil öğeleri {ia} ve {ib} kesişiyor ({q[0]:.6g}, {q[1]:.6g}); döngüler kesişemez"
                    )


# --- Döngüleri bulma ----------------------------------------------------------------------------------


def _loops(prof: dict, pos: dict, rad: dict, roots: dict) -> list[Loop]:
    edges = {k: e for k, e in prof.items() if not isinstance(e, Circle)}
    adj: dict[str, list[str]] = defaultdict(list)
    for k, e in edges.items():
        for p in _ends(e):
            adj[roots[p]].append(k)
    for node, ks in adj.items():
        if len(ks) != 2:
            ad = [p for p in pos if roots.get(p) == node]
            tur = "açık zincir" if len(ks) == 1 else "dallanma"
            raise SketchError(
                f"Profilde {tur}: nokta {', '.join(ad)} öğeler {', '.join(ks)} (derece {len(ks)})"
            )

    loops: list[Loop] = []
    for k, e in prof.items():
        if isinstance(e, Circle):
            q = pos[e.center] + np.array([rad[k], 0.0])
            loops.append((SegArc(tuple(pos[e.center]), rad[k], tuple(q), tuple(q), True),))
    gorulen: set[str] = set()
    for k0 in edges:
        if k0 in gorulen:
            continue
        dongu: list[Seg] = []
        k, giris = k0, roots[_ends(edges[k0])[0]]
        while k not in gorulen:
            gorulen.add(k)
            e = edges[k]
            a, b = _ends(e)
            ileri = roots[a] == giris
            s, t = (a, b) if ileri else (b, a)
            if isinstance(e, Line):
                dongu.append(SegLine(tuple(pos[s]), tuple(pos[t])))
            else:
                c = pos[e.center]
                r = float(np.linalg.norm(pos[e.start] - c))
                dongu.append(SegArc(tuple(c), r, tuple(pos[s]), tuple(pos[t]), ileri))
            giris = roots[t]
            k = next((x for x in adj[giris] if x != k), k)
            if k == k0:
                break
        loops.append(tuple(dongu))
    return loops


def _sample(loop: Loop) -> np.ndarray:
    return _start(loop[0])


# --- Arayüz -------------------------------------------------------------------------------------------


def regions(sketch: Sketch) -> list[SketchRegion]:
    """Profil öğelerinden bölgeler (dış CCW, delik CW). Sağlanmamış kısıt, açık zincir, dallanma,
    kesişen döngü → SketchError."""
    sys = _System(sketch)
    r, _ = sys.eval(sys.x0(), jac=False)
    if r.size and np.abs(r).max() > SAT_TOL:
        raise SketchError(f"Kısıtlar sağlanmıyor (max|r| = {np.abs(r).max():.3g} mm); önce çöz")
    pos, rad = sys.values(sys.x0())
    roots = union_roots(sketch)
    prof = {k: e for k, e in sketch.entities.items() if not e.construction}

    loops = _loops(prof, pos, rad, roots)
    _check_crossings(prof, pos, rad, roots)

    # İç içelik: döngüyü içeren diğer döngüler
    kaplar = [
        [j for j, B in enumerate(loops) if j != i and _winding(B, _sample(A)) != 0]
        for i, A in enumerate(loops)
    ]
    derin = [len(k) for k in kaplar]
    yon = [lp if _signed_area(lp) > 0 else _reverse(lp) for lp in loops]  # hepsi CCW
    dis = {i: [] for i in range(len(loops)) if derin[i] % 2 == 0}
    for i in range(len(loops)):
        if derin[i] % 2 == 1:
            ana = max(kaplar[i], key=lambda j: derin[j])
            dis[ana].append(_reverse(yon[i]))
    return [SketchRegion(outer=yon[i], holes=tuple(h)) for i, h in dis.items()]


def area(region: SketchRegion) -> float:
    """Bölge alanı, delikler düşülmüş (mm²)."""
    return _signed_area(region.outer) + sum(_signed_area(h) for h in region.holes)
