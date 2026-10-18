"""
SPEC 17 — eskiz kısıtlarının artıkları ve analitik Jacobian'ları.

Tablo, işaret / dal kuralları ve satır ölçeği (yön satırları · L): specs/17-kroki.md "Kısıt artıkları".
Ortak uçta teğetlik: SPEC 17 Ek A.

Her kısıt (artık r, kısmi türevler) çifti verir. Kısmi türevler kimlik → blok sözlüğüdür:
nokta kimliği → (m, 2) [∂r/∂x, ∂r/∂y], daire kimliği → (m, 1) [∂r/∂r_daire]. Aynı kimliğe gelen
katkılar toplanır; çözücü blokları bilinmeyen sütunlarına yerleştirir.
"""

from __future__ import annotations

import math

import numpy as np

from sketch.model import Arc, Circle, Constraint, Line, Sketch, SketchError
from sketch.model import ConstraintType as CT

Grad = dict[str, np.ndarray]


# --- Ortak yardımcılar --------------------------------------------------------------------------------


def scale_length(points: dict[str, np.ndarray]) -> float:
    """Satır ölçeği L = max(noktaların sınır kutusu köşegeni, 1 mm)."""
    if not points:
        return 1.0
    xy = np.array(list(points.values()), dtype=float)
    return max(float(np.linalg.norm(xy.max(axis=0) - xy.min(axis=0))), 1.0)


def sketch_values(sketch: Sketch) -> tuple[dict[str, np.ndarray], dict[str, float]]:
    """Eskizdeki konumlar (nokta → (2,)) ve daire yarıçapları."""
    pos = {k: np.array([p.x, p.y], dtype=float) for k, p in sketch.points.items()}
    rad = {k: float(e.r) for k, e in sketch.entities.items() if isinstance(e, Circle)}
    return pos, rad


def union_roots(sketch: Sketch) -> dict[str, str]:
    """Nokta kimliği → birleşim kökü (aynı kimlik ya da COINCIDENT ile birleşmiş kimlikler)."""
    ata = {k: k for k in sketch.points}

    def kok(k: str) -> str:
        while ata[k] != k:
            ata[k] = ata[ata[k]]
            k = ata[k]
        return k

    for c in sketch.constraints:
        if c.type == CT.COINCIDENT and all(r in ata for r in c.refs):
            a, b = kok(c.refs[0]), kok(c.refs[1])
            if a != b:
                ata[max(a, b)] = min(a, b)
    return {k: kok(k) for k in ata}


def _cross(a: np.ndarray, b: np.ndarray) -> float:
    return float(a[0] * b[1] - a[1] * b[0])


def _perp(v: np.ndarray) -> np.ndarray:
    """(−v_y, v_x): ∂(d × w)/∂w = perp(d)."""
    return np.array([-v[1], v[0]])


def _add(g: Grad, ident: str, block) -> None:
    b = np.atleast_2d(np.asarray(block, dtype=float))
    g[ident] = g[ident] + b if ident in g else b


def _rows(*grads: Grad) -> Grad:
    """Satır satır verilen türevleri (m, ·) bloklara üst üste koyar."""
    out: Grad = {}
    m = len(grads)
    for i, g in enumerate(grads):
        for k, b in g.items():
            if k not in out:
                out[k] = np.zeros((m, b.shape[1]))
            out[k][i] += b[0]
    return out


def _norm(v: np.ndarray, ne: str) -> float:
    n = float(np.hypot(v[0], v[1]))
    if n < 1e-12:
        raise SketchError(f"{ne}: sıfır uzunluk")
    return n


class _Ctx:
    """Bir değerlendirme için güncel değerler."""

    def __init__(self, sketch: Sketch, pos: dict[str, np.ndarray], rad: dict[str, float], L: float):
        self.s, self.pos, self.rad, self.L = sketch, pos, rad, L
        self._roots: dict[str, str] | None = None

    @property
    def roots(self) -> dict[str, str]:
        if self._roots is None:
            self._roots = union_roots(self.s)
        return self._roots

    def line(self, ident: str) -> tuple[str, str, np.ndarray, np.ndarray]:
        e = self.s.entities[ident]
        return e.p0, e.p1, self.pos[e.p0], self.pos[e.p1]

    def circ(self, ident: str) -> tuple[str, np.ndarray, float, Grad]:
        """Merkez kimliği, merkez, yarıçap ve yarıçapın türevi (daire: kendi sütunu; yay: |s − c|)."""
        e = self.s.entities[ident]
        c = self.pos[e.center]
        if isinstance(e, Circle):
            return e.center, c, self.rad[ident], {ident: np.array([[1.0]])}
        v = self.pos[e.start] - c
        r = _norm(v, f"yay {ident}")
        u = v / r
        return e.center, c, r, {e.start: u[None, :], e.center: -u[None, :]}


def _signed_dist(
    q: np.ndarray, p0: np.ndarray, p1: np.ndarray
) -> tuple[float, np.ndarray, np.ndarray, np.ndarray]:
    """f = d × (q − p0) / |d| ve ∂f/∂q, ∂f/∂p0, ∂f/∂p1."""
    d = p1 - p0
    n = _norm(d, "çizgi")
    w = q - p0
    cr = _cross(d, w)
    f = cr / n
    df_dw = _perp(d) / n
    df_dd = np.array([w[1], -w[0]]) / n - cr * d / n**3
    return f, df_dw, -df_dw - df_dd, df_dd


def _sd_grad(ids: tuple[str, str, str], parts) -> Grad:
    g: Grad = {}
    for ident, b in zip(ids, parts[1:], strict=True):
        _add(g, ident, b)
    return g


def _scaled(f: float, g: Grad, k: float) -> tuple[float, Grad]:
    return f * k, {i: b * k for i, b in g.items()}


def _minus_r(g: Grad, rg: Grad, k: float = 1.0) -> None:
    for i, b in rg.items():
        _add(g, i, -k * b)


def _shared_end(ctx: _Ctx, a: str, b: str) -> str | None:
    """a ile b'nin (çizgi ya da yay) paylaştığı uç; a'nın o uçtaki nokta kimliği. Yoksa None."""

    def uclar(ident: str) -> tuple[str, ...]:
        e = ctx.s.entities[ident]
        if isinstance(e, Line):
            return (e.p0, e.p1)
        if isinstance(e, Arc):
            return (e.start, e.end)
        return ()

    rb = {ctx.roots[p] for p in uclar(b)}
    for p in uclar(a):
        if ctx.roots[p] in rb:
            return p
    return None


def tangent_side(ctx: _Ctx, c: Constraint) -> int:
    """TANGENT dalı σ: side doluysa o; değilse güncel konumdan (çizgi–daire: merkezin tarafı;
    iç teğet: sign(r_a − r_b)); sıfırsa +1."""
    if c.side:
        return c.side
    a, b = c.refs
    if ctx.s.kind(a) == "L":
        _, _, p0, p1 = ctx.line(a)
        _, cc, _, _ = ctx.circ(b)
        v = _signed_dist(cc, p0, p1)[0]
    elif c.internal:
        v = ctx.circ(a)[2] - ctx.circ(b)[2]
    else:
        return 1
    return -1 if v < 0 else 1


# --- Kısıt başına artık ve türev ----------------------------------------------------------------------


def _eval(ctx: _Ctx, c: Constraint) -> tuple[np.ndarray, Grad]:
    t, refs = c.type, c.refs
    kinds = tuple(ctx.s.kind(r) for r in refs)
    I2 = np.eye(2)
    pos = ctx.pos

    if t == CT.COINCIDENT and kinds == ("P", "P"):
        p, q = refs
        g: Grad = {}
        _add(g, q, I2)
        _add(g, p, -I2)
        return pos[q] - pos[p], g

    if t in (CT.POINT_ON_LINE, CT.DISTANCE) and kinds == ("P", "L"):
        q, ln = refs
        i0, i1, p0, p1 = ctx.line(ln)
        sd = _signed_dist(pos[q], p0, p1)
        D = c.value if t == CT.DISTANCE else 0.0
        return np.array([sd[0] - D]), _sd_grad((q, i0, i1), sd)

    if t == CT.POINT_ON_CIRCLE:
        q, ce = refs
        ic, cc, r, rg = ctx.circ(ce)
        v = pos[q] - cc
        n = _norm(v, f"nokta {q} merkezde")
        u = v / n
        g = {}
        _add(g, q, u)
        _add(g, ic, -u)
        _minus_r(g, rg)
        return np.array([n - r]), g

    if t == CT.MIDPOINT:
        q, ln = refs
        i0, i1, p0, p1 = ctx.line(ln)
        g = {}
        _add(g, q, I2)
        _add(g, i0, -0.5 * I2)
        _add(g, i1, -0.5 * I2)
        return pos[q] - 0.5 * (p0 + p1), g

    if t in (CT.HORIZONTAL, CT.VERTICAL):
        j = 1 if t == CT.HORIZONTAL else 0
        if kinds == ("L",):
            a, b, pa, pb = ctx.line(refs[0])
        else:
            a, b = refs
            pa, pb = pos[a], pos[b]
        e = I2[j][None, :]
        g = {}
        _add(g, b, e)
        _add(g, a, -e)
        return np.array([pb[j] - pa[j]]), g

    if t in (CT.PARALLEL, CT.PERPENDICULAR, CT.ANGLE, CT.EQUAL) and kinds == ("L", "L"):
        a0, a1, q0, q1 = ctx.line(refs[0])
        b0, b1, r0, r1 = ctx.line(refs[1])
        da, db = q1 - q0, r1 - r0
        na, nb = _norm(da, refs[0]), _norm(db, refs[1])
        if t == CT.EQUAL:
            f, ga, gb = na - nb, da / na, -db / nb
        elif t == CT.PARALLEL:
            f = _cross(da, db) / (na * nb)
            ga = np.array([db[1], -db[0]]) / (na * nb) - f * da / na**2
            gb = _perp(da) / (na * nb) - f * db / nb**2
        elif t == CT.PERPENDICULAR:
            f = float(da @ db) / (na * nb)
            ga = db / (na * nb) - f * da / na**2
            gb = da / (na * nb) - f * db / nb**2
        else:
            phi = math.atan2(_cross(da, db), float(da @ db))
            f = math.remainder(phi - math.radians(c.value), 2 * math.pi)
            if f <= -math.pi:
                f += 2 * math.pi
            ga = np.array([da[1], -da[0]]) / na**2
            gb = _perp(db) / nb**2
        k = 1.0 if t == CT.EQUAL else ctx.L
        g = {}
        _add(g, a1, k * ga)
        _add(g, a0, -k * ga)
        _add(g, b1, k * gb)
        _add(g, b0, -k * gb)
        return np.array([k * f]), g

    if t == CT.EQUAL and kinds == ("C", "C"):
        _, _, ra, ga = ctx.circ(refs[0])
        _, _, rb, gb = ctx.circ(refs[1])
        g = {}
        _minus_r(g, ga, -1.0)
        _minus_r(g, gb)
        return np.array([ra - rb]), g

    if t == CT.LENGTH:
        i0, i1, p0, p1 = ctx.line(refs[0])
        d = p1 - p0
        n = _norm(d, refs[0])
        g = {}
        _add(g, i1, d / n)
        _add(g, i0, -d / n)
        return np.array([n - c.value]), g

    if t == CT.DISTANCE and kinds == ("P", "P"):
        p, q = refs
        v = pos[q] - pos[p]
        n = _norm(v, f"{p}–{q} mesafesi")
        g = {}
        _add(g, q, v / n)
        _add(g, p, -v / n)
        return np.array([n - c.value]), g

    if t in (CT.HDISTANCE, CT.VDISTANCE):
        j = 0 if t == CT.HDISTANCE else 1
        p, q = refs
        e = I2[j][None, :]
        g = {}
        _add(g, q, e)
        _add(g, p, -e)
        return np.array([pos[q][j] - pos[p][j] - c.value]), g

    if t in (CT.RADIUS, CT.DIAMETER):
        _, _, r, rg = ctx.circ(refs[0])
        k = 1.0 if t == CT.RADIUS else 2.0
        g = {}
        _minus_r(g, rg, -k)
        return np.array([k * r - c.value]), g

    if t == CT.TANGENT and kinds == ("L", "C"):
        ln, ce = refs
        i0, i1, p0, p1 = ctx.line(ln)
        ic, cc, r, rg = ctx.circ(ce)
        q_id = _shared_end(ctx, ln, ce)
        if q_id is not None:
            # Ek A: merkez → ortak uç vektörü çizgiye dik
            d = p1 - p0
            n = _norm(d, ln)
            v = pos[q_id] - cc
            h = float(v @ d) / n
            dv = d / n
            dd = v / n - h * d / n**2
            g = {}
            _add(g, q_id, dv)
            _add(g, ic, -dv)
            _add(g, i1, dd)
            _add(g, i0, -dd)
            return np.array([h]), g
        sigma = tangent_side(ctx, c)
        sd = _signed_dist(cc, p0, p1)
        g = _sd_grad((ic, i0, i1), sd)
        _minus_r(g, rg, sigma)
        return np.array([sd[0] - sigma * r]), g

    if t == CT.TANGENT and kinds == ("C", "C"):
        a, b = refs
        ia, ca, ra, ga = ctx.circ(a)
        ib, cb, rb, gb = ctx.circ(b)
        q_id = _shared_end(ctx, a, b)
        if q_id is not None:
            # Ek A: iki merkez ve ortak uç doğrudaş
            q = pos[q_id]
            va, vb = q - ca, q - cb
            nb_ = _norm(vb, f"yay {b}")
            f = _cross(va, vb) / nb_
            dva = np.array([vb[1], -vb[0]]) / nb_
            dvb = _perp(va) / nb_ - f * vb / nb_**2
            g = {}
            _add(g, q_id, dva + dvb)
            _add(g, ia, -dva)
            _add(g, ib, -dvb)
            return np.array([f]), g
        v = cb - ca
        n = _norm(v, f"{a}–{b} merkezleri çakışık")
        g = {}
        _add(g, ib, v / n)
        _add(g, ia, -v / n)
        if c.internal:
            sigma = tangent_side(ctx, c)
            _minus_r(g, ga, sigma)
            _minus_r(g, gb, -sigma)
            return np.array([n - sigma * (ra - rb)]), g
        _minus_r(g, ga)
        _minus_r(g, gb)
        return np.array([n - (ra + rb)]), g

    if t == CT.SYMMETRIC:
        p, q, ln = refs
        i0, i1, p0, p1 = ctx.line(ln)
        m = 0.5 * (pos[p] + pos[q])
        sd = _signed_dist(m, p0, p1)
        g1: Grad = {}
        _add(g1, p, 0.5 * sd[1])
        _add(g1, q, 0.5 * sd[1])
        _add(g1, i0, sd[2])
        _add(g1, i1, sd[3])
        d = p1 - p0
        n = _norm(d, ln)
        w = pos[q] - pos[p]
        h = float(w @ d) / n
        dd = w / n - h * d / n**2
        g2: Grad = {}
        _add(g2, q, d / n)
        _add(g2, p, -d / n)
        _add(g2, i1, dd)
        _add(g2, i0, -dd)
        return np.array([sd[0], h]), _rows(g1, g2)

    raise SketchError(f"Desteklenmeyen kısıt: {t} {kinds}")


def arc_row(ctx: _Ctx, ident: str) -> tuple[np.ndarray, Grad]:
    """Yayın iç satırı |s − c| − |e − c| = 0."""
    e = ctx.s.entities[ident]
    c = ctx.pos[e.center]
    vs, ve = ctx.pos[e.start] - c, ctx.pos[e.end] - c
    ns, ne = _norm(vs, f"yay {ident}"), _norm(ve, f"yay {ident}")
    g: Grad = {}
    _add(g, e.start, vs / ns)
    _add(g, e.end, -ve / ne)
    _add(g, e.center, -vs / ns + ve / ne)
    return np.array([ns - ne]), g


def evaluate(
    sketch: Sketch, k: int, pos: dict[str, np.ndarray], rad: dict[str, float], L: float
) -> tuple[np.ndarray, Grad]:
    """k. kısıtın artığı ve türev blokları (çözücü için; L dışarıdan sabit)."""
    c = sketch.constraints[k]
    try:
        r, g = _eval(_Ctx(sketch, pos, rad, L), c)
    except SketchError as err:
        raise SketchError(f"Kısıt {k} ({c.type}): {err}", (k,)) from None
    return np.asarray(r, dtype=float), g


def _merged(sketch: Sketch, x_map: dict) -> tuple[dict[str, np.ndarray], dict[str, float]]:
    pos, rad = sketch_values(sketch)
    for k, v in x_map.items():
        if k in pos:
            pos[k] = np.asarray(v, dtype=float).reshape(2)
        elif k in rad:
            rad[k] = float(v)
        else:
            raise SketchError(f"x_map: bilinmeyen kimlik {k!r}")
    return pos, rad


# --- Arayüz -------------------------------------------------------------------------------------------


def residual(sketch: Sketch, k: int, x_map: dict[str, np.ndarray | float]) -> np.ndarray:
    """k. kısıtın artığı (satır sayısı türe göre 1 ya da 2; ölçek dahil, mm).

    x_map: güncel değerler; nokta kimliği → (2,) konum, daire kimliği → yarıçap r. Haritada olmayan
    noktalar / daireler eskizdeki değerleriyle alınır. L eskizdeki noktalardan. Desteklenmeyen tür /
    referans çifti → SketchError.
    """
    sketch._kisit(k, sketch.constraints[k])
    pos, rad = _merged(sketch, x_map)
    L = scale_length(sketch_values(sketch)[0])
    return evaluate(sketch, k, pos, rad, L)[0]


def jacobian(sketch: Sketch, k: int, unknowns: list[str]) -> np.ndarray:
    """k. kısıtın Jacobian'ı, (satır, sütun) — eskizdeki güncel değerlerde.

    Sütun düzeni: unknowns sırasıyla; nokta kimliği → 2 sütun (x, y), daire kimliği → 1 sütun (r).
    Listede olmayan (sabit) noktaların sütunu yok.
    """
    sketch._kisit(k, sketch.constraints[k])
    pos, rad = sketch_values(sketch)
    r, g = evaluate(sketch, k, pos, rad, scale_length(pos))
    return assemble(r.size, g, unknowns, sketch)


def columns(unknowns: list[str], sketch: Sketch) -> dict[str, slice]:
    """Bilinmeyen kimliği → sütun aralığı."""
    out, j = {}, 0
    for u in unknowns:
        w = 2 if u in sketch.points else 1
        out[u] = slice(j, j + w)
        j += w
    return out


def assemble(
    m: int, g: Grad, unknowns: list[str], sketch: Sketch, cols: dict[str, slice] | None = None
) -> np.ndarray:
    cols = cols or columns(unknowns, sketch)
    n = sum(s.stop - s.start for s in cols.values())
    J = np.zeros((m, n))
    for ident, b in g.items():
        if ident in cols:
            J[:, cols[ident]] += b
    return J
