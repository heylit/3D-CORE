"""
SPEC 17 — eskiz çözücü: Gauss–Newton (en küçük normlu adım), serbestlik, çelişki teşhisi, sürükleme.

Yöntem: specs/17-kroki.md "Çözüm", "Serbestlik derecesi", "Çelişki teşhisi", "Sürükleme".
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field

import numpy as np

from sketch.constraints import _Ctx, arc_row, columns, evaluate, scale_length, sketch_values, tangent_side
from sketch.model import Arc, Circle, Line, Sketch, SketchError
from sketch.model import ConstraintType as CT

RANK_TOL = 1e-8  # σ_i > RANK_TOL · σ_max; öğe serbestliğinde mutlak (N birimdik)


@dataclass
class SolveResult:
    """Çözüm. points: tüm noktalar (sabitler dahil) → (2,); radii: daireler → r; sides: TANGENT dalları."""

    points: dict[str, np.ndarray]
    radii: dict[str, float]
    sides: dict[int, int]
    iterations: int
    residual: float  # son ölçekli max|r|, mm
    dof: int
    freedom: dict[str, int] = field(default_factory=dict)  # nokta / öğe kimliği → kalan serbestlik
    directions: dict[str, np.ndarray] = field(default_factory=dict)  # tek serbestlikli nokta → birim yön
    redundant: tuple[int, ...] = ()  # tutarlı ama gereksiz kısıtların sıraları

    def apply(self, sketch: Sketch) -> None:
        """Konumları, yarıçapları ve side değerlerini eskize yazar."""
        for k, p in self.points.items():
            sketch.points[k].x = float(p[0])
            sketch.points[k].y = float(p[1])
        for k, r in self.radii.items():
            sketch.entities[k].r = float(r)
        for k, s in self.sides.items():
            sketch.constraints[k].side = int(s)


# --- Sistem: bilinmeyenler, satırlar, r(x), J(x) ------------------------------------------------------


class _System:
    """Eskizin çalışma kopyası üzerinde r(x) ve J(x). x: serbest noktaların (x, y)'si ve daire yarıçapları."""

    def __init__(self, sketch: Sketch):
        sketch.validate()
        self.s = copy.deepcopy(sketch)
        pos, rad = sketch_values(self.s)
        self.pos0, self.L = pos, scale_length(pos)
        self.unknowns = [k for k, p in self.s.points.items() if not p.fixed]
        self.unknowns += [k for k, e in self.s.entities.items() if isinstance(e, Circle)]
        self.cols = columns(self.unknowns, self.s)
        self.n = sum(c.stop - c.start for c in self.cols.values())
        self.arcs = [k for k, e in self.s.entities.items() if isinstance(e, Arc)]
        self.sides = self._fix_sides(pos, rad)
        # Satır blokları: önce yay iç satırları (taban), sonra kısıtlar sırayla
        self.blocks: list[tuple[str | int, int]] = [(a, 1) for a in self.arcs]
        self.blocks += [
            (k, 2 if c.type in (CT.COINCIDENT, CT.MIDPOINT, CT.SYMMETRIC) else 1)
            for k, c in enumerate(self.s.constraints)
        ]
        self.m = sum(w for _, w in self.blocks)

    def _fix_sides(self, pos: dict[str, np.ndarray], rad: dict[str, float]) -> dict[int, int]:
        """TANGENT dallarını ilk konumdan sabitler (side = 0 ise) ve çalışma kopyasına yazar."""
        ctx = _Ctx(self.s, pos, rad, self.L)
        sides = {}
        for k, c in enumerate(self.s.constraints):
            if c.type != CT.TANGENT:
                continue
            if c.internal and c.side == 0:
                ca, cb = ctx.circ(c.refs[0])[1], ctx.circ(c.refs[1])[1]
                if np.linalg.norm(cb - ca) < 1e-9:
                    raise SketchError(
                        f"Kısıt {k} (TANGENT): iç teğette merkezler çakışık, dal belirsiz", (k,)
                    )
            c.side = tangent_side(ctx, c)
            sides[k] = c.side
        return sides

    def x0(self) -> np.ndarray:
        _, rad = sketch_values(self.s)
        x = np.zeros(self.n)
        for u, sl in self.cols.items():
            x[sl] = self.pos0[u] if u in self.pos0 else rad[u]
        return x

    def values(self, x: np.ndarray) -> tuple[dict[str, np.ndarray], dict[str, float]]:
        pos = dict(self.pos0)
        rad = {}
        for u, sl in self.cols.items():
            if u in pos:
                pos[u] = x[sl].copy()
            else:
                rad[u] = float(x[sl][0])
        return pos, rad

    def eval(self, x: np.ndarray, jac: bool = True) -> tuple[np.ndarray, np.ndarray | None]:
        pos, rad = self.values(x)
        ctx = _Ctx(self.s, pos, rad, self.L)
        r = np.zeros(self.m)
        J = np.zeros((self.m, self.n)) if jac else None
        i = 0
        for key, w in self.blocks:
            if isinstance(key, str):
                rb, g = arc_row(ctx, key)
            else:
                rb, g = evaluate(self.s, key, pos, rad, self.L)
            r[i : i + w] = rb
            if jac:
                for ident, b in g.items():
                    if ident in self.cols:
                        J[i : i + w, self.cols[ident]] += b
            i += w
        return r, J

    def try_eval(self, x: np.ndarray) -> np.ndarray | None:
        """Deneme adımında r(x); sıfır boy gibi tanımsız konum → None (adım reddedilir)."""
        try:
            return self.eval(x, jac=False)[0]
        except SketchError:
            return None

    def result(self, x: np.ndarray, iterations: int, r: np.ndarray, J: np.ndarray) -> SolveResult:
        pos, rad = self.values(x)
        res = SolveResult(
            points={k: v.copy() for k, v in pos.items()},
            radii=rad,
            sides=dict(self.sides),
            iterations=iterations,
            residual=float(np.abs(r).max()) if r.size else 0.0,
            dof=0,
        )
        _analyse(self, J, res)
        return res


# --- Gauss–Newton -------------------------------------------------------------------------------------


def _gauss_newton(
    sys: _System, x: np.ndarray, tol: float, max_iter: int
) -> tuple[np.ndarray, int, np.ndarray, np.ndarray]:
    """r(x) = 0'a en küçük normlu adımlar. Durağan nokta / max_iter → SketchError (çelişki kümesi)."""
    r, J = sys.eval(x)
    it = 0
    while r.size and np.abs(r).max() > tol:
        if it >= max_iter or np.linalg.norm(J.T @ r) <= 1e-14 * sys.L:
            _conflict(sys, r, tol)
        dx = np.linalg.lstsq(J, -r, rcond=None)[0]
        n0 = np.linalg.norm(r)
        a = 1.0
        while a >= 2.0**-10:
            rt = sys.try_eval(x + a * dx)
            if rt is not None and np.linalg.norm(rt) < n0:
                break
            a *= 0.5
        else:
            _conflict(sys, r, tol)
        x = x + a * dx
        r, J = sys.eval(x)
        it += 1
    return x, it, r, J


def _conflict(sys: _System, r: np.ndarray, tol: float) -> None:
    esik = max(tol, 1e-6 * float(np.abs(r).max()))
    kume, i = [], 0
    for key, w in sys.blocks:
        if isinstance(key, int) and np.abs(r[i : i + w]).max() > esik:
            kume.append(key)
        i += w
    adlar = ", ".join(f"{k} ({sys.s.constraints[k].type})" for k in kume)
    raise SketchError(f"Kısıtlar çelişiyor: {adlar}; max|r| = {np.abs(r).max():.3g} mm", tuple(kume))


# --- Serbestlik, gereksiz kısıtlar --------------------------------------------------------------------


def _svd(J: np.ndarray, n: int) -> tuple[int, np.ndarray]:
    """rank(J) ve sıfır uzayının birimdik tabanı N (n, n − rank)."""
    if J.shape[0] == 0 or n == 0:
        return 0, np.eye(n)
    _, S, Vt = np.linalg.svd(J)
    rank = int(np.sum(S > RANK_TOL * S[0])) if S.size and S[0] > 0 else 0
    return rank, Vt[rank:].T


def _rank(A: np.ndarray, esik: float) -> int:
    if A.size == 0:
        return 0
    return int(np.sum(np.linalg.svd(A, compute_uv=False) > esik))


def _redundant(sys: _System, J: np.ndarray, rank: int) -> tuple[int, ...]:
    if rank == J.shape[0]:
        return ()
    esik = RANK_TOL * np.linalg.svd(J, compute_uv=False)[0]
    out, i, onceki = [], 0, 0
    for key, w in sys.blocks:
        i += w
        rk = _rank(J[:i], esik)
        if isinstance(key, int) and rk == onceki:
            out.append(key)
        onceki = rk
    return tuple(out)


def _analyse(sys: _System, J: np.ndarray, res: SolveResult) -> None:
    rank, N = _svd(J, sys.n)
    res.dof = sys.n - rank
    res.redundant = _redundant(sys, J, rank)

    def k_of(idents: list[str]) -> tuple[int, np.ndarray | None]:
        rows = [N[sys.cols[u]] for u in idents if u in sys.cols]
        if not rows or N.shape[1] == 0:
            return 0, None
        A = np.vstack(rows)
        U, S, _ = np.linalg.svd(A, full_matrices=False)
        return int(np.sum(S > RANK_TOL)), U[:, 0]

    for p in sys.s.points:
        k, u = k_of([p])
        res.freedom[p] = k
        if k == 1:
            if u[0] < 0 or (u[0] == 0 and u[1] < 0):
                u = -u
            res.directions[p] = u / np.linalg.norm(u)
    for ident, e in sys.s.entities.items():
        if isinstance(e, Line):
            ids = [e.p0, e.p1]
        elif isinstance(e, Arc):
            ids = [e.center, e.start, e.end]
        else:
            ids = [e.center, ident]
        res.freedom[ident] = k_of(ids)[0]


# --- Arayüz -------------------------------------------------------------------------------------------


def solve(sketch: Sketch, tol: float = 1e-10, max_iter: int = 50) -> SolveResult:
    """Eskizi çözer; girdiyi değiştirmez. Çelişki → SketchError (constraints = çelişki kümesi)."""
    sys = _System(sketch)
    x, it, r, J = _gauss_newton(sys, sys.x0(), tol, max_iter)
    return sys.result(x, it, r, J)


def drag(sketch: Sketch, point: str, target, tol: float = 1e-10, max_iter: int = 50) -> SolveResult:
    """point'i kısıtları bozmadan target'a (uv, mm) yerel olarak en yakın konuma taşır; girdiyi değiştirmez.

    Sabit nokta → SketchError.
    """
    if point not in sketch.points:
        raise SketchError(f"Bilinmeyen nokta: {point!r}")
    if sketch.points[point].fixed:
        raise SketchError(f"Sabit nokta sürüklenemez: {point!r}")
    hedef = np.asarray(target, dtype=float).reshape(2)
    sys = _System(sketch)
    x, it, r, J = _gauss_newton(sys, sys.x0(), tol, max_iter)
    sl = sys.cols[point]
    for _ in range(max_iter):
        _, N = _svd(J, sys.n)
        if N.shape[1] == 0:
            break
        dx = N @ (np.linalg.pinv(N[sl]) @ (hedef - x[sl]))
        if np.linalg.norm(dx) <= 1e-12 * sys.L:
            break
        uzak = np.linalg.norm(hedef - x[sl])
        a = 1.0
        while a >= 2.0**-10:
            try:
                xt, k, rt, Jt = _gauss_newton(sys, x + a * dx, tol, max_iter)
            except SketchError:
                xt = None
            if xt is not None and np.linalg.norm(hedef - xt[sl]) < uzak:
                break
            a *= 0.5
        else:
            break
        x, r, J, it = xt, rt, Jt, it + k + 1
    return sys.result(x, it, r, J)


def dof(sketch: Sketch) -> int:
    """Kalan serbestlik derecesi; girdiyi değiştirmez ve konum döndürmez.

    Sayım çözülmüş konumda yapılır ("Serbestlik derecesi"): sağlanmamış eskizde rank genel konumda
    yapay olarak yüksek çıkar (ör. dik olmayan dörtgende PARALLEL). Bu yüzden kopya üzerinde çözülür;
    çelişkili eskizde mevcut konumda sayılır.
    """
    sys = _System(sketch)
    try:
        J = _gauss_newton(sys, sys.x0(), 1e-10, 50)[3]
    except SketchError:
        J = sys.eval(sys.x0())[1]
    rank, _ = _svd(J, sys.n)
    return sys.n - rank
