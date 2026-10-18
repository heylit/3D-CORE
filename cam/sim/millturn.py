"""
SPEC 49 — Torna-freze simülasyonu: önce torna işlemleri SPEC 22 RadialMap'te, ilk freze işleminden önce
RadialMap → TriDexel (kutu [−R, R]² × [zmin, zmax]), freze işlemleri parça çerçevesinde SPEC 43 kurallarıyla
(C açısı R_z(−C) ile parçaya çevrilir; polar / silindirik yollar önce kartezyen kirişlere açılır).
Frezeden sonra torna işlemi → CamError.

Ayna (bağlama elemanı, CylinderStock halkası r ∈ [d/2, D/2], z ∈ [zmin, zmax]) freze hareketlerinde ayrıca
denetlenir: takım silindiri (uçtan sap boyuna, yarıçap D/2) örnek noktalarla halkaya batarsa `ayna_carpma`,
derinlik = halka sınırlarına en küçük uzaklığın en büyüğü.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import replace

import numpy as np

from cam.millturn.istasyon import check_ops
from cam.millturn.polar import arc_chords, to_cartesian
from cam.model import ARCS, CamError, CylinderStock, LatheTool, MachineProfile, Setup, Stock, Toolpath, Wcs
from cam.sim.lathe import simulate_lathe
from cam.sim.radial import RadialMap
from cam.sim.simulate import Collision
from cam.sim.simulate5 import SimResult5, simulate5
from cam.sim.timing import Machine
from cam.sim.tridexel import TriDexel

_Z = np.array([0.0, 0.0, 1.0])


def _box(rmap: RadialMap) -> Stock:
    rm = rmap.r_max
    return Stock(-rm, -rm, rmap.z0, rm, rm, rmap.z0 + rmap.nz * rmap.dz)


def _pack(n_rows: int, n_cols: int, ray: np.ndarray, lo: np.ndarray, hi: np.ndarray):
    """Işın başına aralıklar → (n_rows, n_cols, K) lo / hi; boş yuva lo = +inf, hi = −inf."""
    sira = np.lexsort((lo, ray))
    ray, lo, hi = ray[sira], lo[sira], hi[sira]
    n = n_rows * n_cols
    cnt = np.bincount(ray, minlength=n)
    K = max(1, int(cnt.max()) if cnt.size else 1)
    ilk = np.cumsum(cnt) - cnt
    yuva = np.arange(ray.size) - ilk[ray]
    L = np.full((n, K), np.inf)
    H = np.full((n, K), -np.inf)
    L[ray, yuva] = lo
    H[ray, yuva] = hi
    return L.reshape(n_rows, n_cols, K), H.reshape(n_rows, n_cols, K)


def _yan_aile(rmap: RadialMap, m, zc: np.ndarray, uc: np.ndarray):
    """X / Y ailesi: satır z_c, sütun dik eksen u_c;
    dönel bölge r ∈ [a, b] → |w| ∈ [√(a² − u²), √(b² − u²)]."""
    rays, los, his = [], [], []
    U = np.abs(uc)
    for j, z in enumerate(zc):
        i = int(math.floor((z - rmap.z0) / rmap.dz))
        if not 0 <= i < rmap.nz:
            continue
        for a, b in rmap.iv[i]:
            ic = U < b
            if not ic.any():
                continue
            k = np.nonzero(ic)[0]
            sb = np.sqrt(b * b - U[k] ** 2)
            dolu = a <= U[k]
            sa = np.sqrt(np.maximum(a * a - U[k] ** 2, 0.0))
            ray = j * m.nx + k
            # tek aralık [−sb, sb] (a ≤ |u|), değilse iki aralık [−sb, −sa], [sa, sb]
            rays += [ray[dolu], ray[~dolu], ray[~dolu]]
            los += [-sb[dolu], -sb[~dolu], sa[~dolu]]
            his += [sb[dolu], -sa[~dolu], sb[~dolu]]
    if not rays:
        return _pack(m.ny, m.nx, np.zeros(0, int), np.zeros(0), np.zeros(0))
    return _pack(m.ny, m.nx, np.concatenate(rays), np.concatenate(los), np.concatenate(his))


def rmap_to_tridexel(rmap: RadialMap, cell: float, max_rays: int = 3_000_000) -> TriDexel:
    """Dönel haritayı kutu [−r_max, r_max]² × [z0, z0 + nz·dz] üzerinde tri-dexel'e çevirir."""
    if not isinstance(rmap, RadialMap):
        raise CamError(f"RadialMap bekleniyor ({type(rmap).__name__})")
    td = TriDexel.from_stock(_box(rmap), cell, max_rays)
    # Z ailesi: ışın (x_c, y_c) için r_c sabit; hücre z aralıkları birleşir
    m = td.maps["z"]
    X, Y = np.meshgrid(m.xs(), m.ys())
    rc = np.hypot(X, Y)
    occ = np.zeros((rmap.nz + 2, m.ny, m.nx), dtype=bool)
    for i, iv in enumerate(rmap.iv):
        for a, b in iv:
            occ[i + 1] |= (rc >= a) & (rc <= b)
    d = np.diff(occ.astype(np.int8), axis=0)
    i0, j0, k0 = np.nonzero(d == 1)  # başlangıç hücresi i0
    i1, j1, k1 = np.nonzero(d == -1)  # bitiş: hücre i1 − 1'in üstü
    s0 = np.lexsort((i0, j0 * m.nx + k0))
    s1 = np.lexsort((i1, j1 * m.nx + k1))
    ray = (j0 * m.nx + k0)[s0]
    lo = rmap.z0 + i0[s0] * rmap.dz
    hi = rmap.z0 + i1[s1] * rmap.dz
    m.lo, m.hi = _pack(m.ny, m.nx, ray, lo, hi)
    # X ailesi: (y_c, z_c) ızgarası; Y ailesi: (x_c, z_c)
    for ad in ("x", "y"):
        m = td.maps[ad]
        m.lo, m.hi = _yan_aile(rmap, m, m.ys(), m.xs())
    return td


def _rz(c_deg: float) -> np.ndarray:
    a = math.radians(c_deg)
    return np.array([[math.cos(a), -math.sin(a), 0.0], [math.sin(a), math.cos(a), 0.0], [0.0, 0.0, 1.0]])


def to_part_frame(tp: Toolpath, arc_tol: float = 1e-3) -> Toolpath:
    """Freze yolunu parça çerçevesinde kartezyen yola çevirir: Move.c ile R_z(−C), polar / silindirik
    açılım."""
    if isinstance(tp.tool, LatheTool):
        raise CamError(f"Yol '{tp.name}': torna yolu parça çerçevesine çevrilmez (zaten parça çerçevesinde)")
    if tp.coord != "kartezyen":
        return to_cartesian(tp, arc_tol)
    tp.validate()
    cs = [m.c for m in tp.moves if m.c is not None]
    if not cs:
        return tp
    if tp.frame is not None:
        raise CamError(f"Yol '{tp.name}': C açılı yolda frame verilemez")
    c = cs[0]
    Rm = _rz(-c)
    start = tuple(float(v) for v in Rm @ np.array(tp.start))
    moves = []
    for m in tp.moves:
        if m.c is not None and m.c != c:
            c = m.c
            Rm = _rz(-c)
        end = tuple(float(v) for v in Rm @ np.array(m.end))
        center = None if m.center is None else tuple(float(v) for v in (Rm @ np.array([*m.center, 0.0]))[:2])
        axis = None if m.axis is None else tuple(float(v) for v in Rm @ np.array(m.axis))
        moves.append(replace(m, end=end, center=center, axis=axis, c=None))
    out = replace(tp, start=start, moves=moves)
    out.validate()
    return out


# ---------------------------------------------------------------- ayna


def _tool_samples(tool, cell: float) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Takım silindiri örnekleri (w, ρ, φ) → yerel (w, u, v) katsayıları."""
    R = tool.D / 2
    Lb = max(float(tool.flute_length), float(tool.stickout or 0.0))
    nw = max(2, math.ceil(Lb / (cell / 2)) + 1)
    w = np.linspace(0.0, Lb, nw)
    nphi = max(8, math.ceil(2 * math.pi * R / (cell / 2)))
    phi = np.linspace(0, 2 * math.pi, nphi, endpoint=False)
    halka = [(0.0, 0.0)] + [(rho * math.cos(f), rho * math.sin(f)) for rho in (R / 2, R) for f in phi]
    uv = np.array(halka)
    W = np.repeat(w, len(uv))
    UV = np.tile(uv, (nw, 1))
    return W, UV[:, 0], UV[:, 1]


def _basis(a: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    e = np.eye(3)[int(np.argmin(np.abs(a)))]
    u = np.cross(a, e)
    u /= np.linalg.norm(u)
    return u, np.cross(a, u)


def _ayna_derinlik(P: np.ndarray, fixtures) -> tuple[float, np.ndarray | None]:
    r = np.hypot(P[:, 0], P[:, 1])
    z = P[:, 2]
    en, at = 0.0, None
    for f in fixtures:
        d = np.minimum.reduce([r - f.d / 2, f.D / 2 - r, z - f.zmin, f.zmax - z])
        j = int(np.argmax(d))
        if d[j] > en:
            en, at = float(d[j]), P[j]
    return en, at


def _ayna(parts: list[Toolpath], fixtures, cell: float, arc_tol: float, tol: float) -> list[Collision]:
    """simulate5 ile aynı adım numaraları (yollar arası bağlantı dahil) üzerinde ayna denetimi."""
    out: list[Collision] = []
    k = 0
    pos: np.ndarray | None = None
    a_pos: np.ndarray | None = None

    def denetle(op: int, tool, pts: list[np.ndarray], a: np.ndarray) -> None:
        W, U, V = _tool_samples(tool, cell)
        u, v = _basis(a)
        Q = W[:, None] * a + U[:, None] * u + V[:, None] * v
        smax = max(min(cell, tool.D / 2) / 2, 1e-6)
        en, at = 0.0, None
        for p0, p1 in zip(pts[:-1], pts[1:], strict=True):
            n = max(1, math.ceil(float(np.linalg.norm(p1 - p0)) / smax))
            for t in np.linspace(0.0, 1.0, n + 1):
                d, q = _ayna_derinlik(p0 + (p1 - p0) * t + Q, fixtures)
                if d > en:
                    en, at = d, q
        if en > tol:
            out.append(Collision("ayna_carpma", k, op, tuple(float(x) for x in at), en))

    for i, tp in enumerate(parts):
        eksenler = [np.array(m.axis if m.axis is not None else _Z, dtype=float) for m in tp.moves]
        a_bas = eksenler[0] if eksenler else (a_pos if a_pos is not None else _Z)
        p_bas = np.array(tp.start, dtype=float)
        if pos is not None and (not np.array_equal(pos, p_bas) or not np.allclose(a_pos, a_bas, atol=1e-12)):
            k += 1
            denetle(i, tp.tool, [pos, p_bas], a_bas)
        pos, a_pos = p_bas, a_bas
        for m, a1 in zip(tp.moves, eksenler, strict=True):
            k += 1
            pts = arc_chords(pos, m, arc_tol) if m.type in ARCS else [np.array(m.end, dtype=float)]
            denetle(i, tp.tool, [pos, *pts], a1)
            pos, a_pos = np.array(m.end, dtype=float), a1
    return out


# ---------------------------------------------------------------- sürücü


def simulate_mt(
    ops: list[Toolpath],
    stock: CylinderStock,
    machine: MachineProfile,
    cell: float = 0.5,
    part=None,
    fixtures: Sequence[CylinderStock] = (),
    timing: Machine | None = None,
    arc_tol: float = 1e-3,
    tol: float = 1e-6,
    gouge_tol: float = 1e-3,
) -> SimResult5:
    """Torna + freze programını simüle eder; machine.kind != "millturn" → CamError."""
    check_ops(ops, machine)
    if not isinstance(stock, CylinderStock):
        raise CamError(f"Torna-freze simülasyonu CylinderStock ister ({type(stock).__name__})")
    fixtures = list(fixtures)
    for f in fixtures:
        if not isinstance(f, CylinderStock):
            raise CamError(f"Ayna / bağlama elemanı CylinderStock olmalı ({type(f).__name__})")
    torna = [isinstance(tp.tool, LatheTool) for tp in ops]
    n_t = torna.index(False) if False in torna else len(ops)
    if any(torna[n_t:]):
        raise CamError("Frezeden sonra torna işlemi simüle edilemez (tri-dexel → dönel harita yok)")
    timing = Machine() if timing is None else timing

    steps, collisions, removed, t = [], [], 0.0, 0.0
    if n_t:
        st = Setup("torna-freze", Wcs(), stock, fixtures) if fixtures else stock
        lres = simulate_lathe(ops[:n_t], st, cell, timing, None, arc_tol, tol, gouge_tol)
        rmap = lres.rmap
        steps, collisions = list(lres.steps), list(lres.collisions)
        removed, t = lres.removed_volume, lres.total_time
    else:
        rmap = RadialMap.from_stock(stock, cell, fixtures)
    td = rmap_to_tridexel(rmap, cell)
    if n_t == len(ops):
        return SimResult5(td, steps, collisions, removed, t)

    parts = [to_part_frame(tp, arc_tol) for tp in ops[n_t:]]
    r5 = simulate5(parts, _box(rmap), cell, timing, part, None, arc_tol, tol, gouge_tol, initial=td)
    if n_t and ops[n_t - 1].tool.id != parts[0].tool.id:
        t += timing.tool_change
    dk = len(steps)
    steps += [replace(s, k=s.k + dk, op=s.op + n_t, t0=s.t0 + t) for s in r5.steps]
    mill_coll = list(r5.collisions)
    if fixtures:
        mill_coll += _ayna(parts, fixtures, cell, arc_tol, tol)
    collisions += sorted(
        (replace(c, k=c.k + dk, op=c.op + n_t) for c in mill_coll), key=lambda c: (c.k, c.kind)
    )
    return SimResult5(r5.tridexel, steps, collisions, removed + r5.removed_volume, t + r5.total_time, r5.part)
