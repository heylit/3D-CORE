"""
SPEC 43 — Çok eksenli simülasyon sürücüsü: program → tri-dexel, süre, çarpışma ve çakma kayıtları.

Hareket k: uç p₀ → p₁ doğrusal, eksen a₀ → a₁ slerp. Sabit eksenli harekette süpürülen küme
takım ⊕ [p₀, p₁] dışbükeydir; değişen eksenli hareket n = ⌈θ·ρ_max / σ⌉ alt adıma bölünür
(ρ_max = √(L_f² + R²)), her alt adım orta eksenle sabit eksenlidir. Ayrıca 05 gibi alt adım boyu
≤ min(R, L_f)/2: gövde denetimi alt adım sonundaki konumda, alt adımdan önceki malzemeyle yapılır.

Takım ekseni +Z iken Z ailesi 05'in kapalı formlarıyla (sweep_envelope, sweep_top) kaldırılır:
05 dexel'iyle aynı sonuç. Gövde malzeme kaldırmaz, yalnız çarpışma kaydı üretir.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from cam.dropcutter import TriMesh
from cam.model import ARCS, CamError, FeedMode, LatheTool, Move, MoveType, Plane, Stock, Tool, Toolpath
from cam.sim.raymesh import family_part
from cam.sim.simulate import KINDS, Collision, SimStep, _check_positive, _chords
from cam.sim.sweep import _radii, sweep_envelope, sweep_top
from cam.sim.timing import Machine, move_time
from cam.sim.tridexel import (
    AXES,
    FAMILY,
    TriDexel,
    body_pieces,
    cutter_pieces,
    piece_interval,
    piece_rmax,
    piece_wrange,
    sweep_interval,
)

_EKSEN_TOL = 1e-12  # [rad] sabit eksen sayılan açı
_Z = np.array([0.0, 0.0, 1.0])


@dataclass
class SimResult5:
    tridexel: TriDexel
    steps: list[SimStep]
    collisions: list[Collision] = field(default_factory=list)
    removed_volume: float = 0.0
    total_time: float = 0.0
    part: dict[str, tuple[np.ndarray, np.ndarray]] | None = field(default=None, repr=False)

    def _hacimler(self) -> tuple[float, float]:
        if self.part is None:
            raise CamError("Parça ağı verilmedi")
        kalan = cakma = 0.0
        for ad in AXES:
            m = self.tridexel.maps[ad]
            plo, phi = self.part[ad]
            mat = np.where(m.hi > m.lo, m.hi - m.lo, 0.0).sum(axis=2)
            par = np.where(phi > plo, phi - plo, 0.0).sum(axis=2)
            ort = _kesisim(m.lo, m.hi, plo, phi)
            alan = m.dx * m.dy
            kalan += float(np.sum(mat - ort)) * alan
            cakma += float(np.sum(par - ort)) * alan
        return kalan / 3, cakma / 3

    def rest_volume(self) -> float:
        """Kalan malzeme: malzeme ∖ parça (aileler ortalaması); parça yoksa CamError."""
        return self._hacimler()[0]

    def gouge_volume(self) -> float:
        """Çakma hacmi: parça ∖ malzeme (aileler ortalaması); parça yoksa CamError."""
        return self._hacimler()[1]


# ---------------------------------------------------------------- yardımcılar


def _kesisim(lo, hi, plo, phi) -> np.ndarray:
    """Işın başına iki aralık listesinin kesişim boyu: (..., K) × (..., Kp) → (...)."""
    a = np.maximum(lo[..., :, None], plo[..., None, :])
    b = np.minimum(hi[..., :, None], phi[..., None, :])
    return np.where(b > a, b - a, 0.0).sum(axis=(-1, -2))


def _overlap(lo, hi, a, b):
    """Malzeme ∩ [a, b]: (ışın başına toplam boy, en alçak nokta; yoksa inf)."""
    k_lo = np.maximum(lo, a[..., None])
    k_hi = np.minimum(hi, b[..., None])
    m = (hi > lo) & (k_hi > k_lo)
    return np.where(m, k_hi - k_lo, 0.0).sum(axis=-1), np.where(m, k_lo, np.inf).min(axis=-1)


def _angle(a0: np.ndarray, a1: np.ndarray) -> float:
    return math.atan2(float(np.linalg.norm(np.cross(a0, a1))), float(a0 @ a1))


def _slerp(a0: np.ndarray, a1: np.ndarray, t: float) -> np.ndarray:
    """a₀'ı a₀ × a₁ ekseni etrafında θ·t döndürür (Rodrigues)."""
    th = _angle(a0, a1)
    if th <= _EKSEN_TOL:
        return a0
    k = np.cross(a0, a1)
    if np.linalg.norm(k) < 1e-12:  # zıt yön: herhangi bir dik eksen
        k = np.cross(a0, np.eye(3)[int(np.argmin(np.abs(a0)))])
    k = k / np.linalg.norm(k)
    f = th * t
    return a0 * math.cos(f) + np.cross(k, a0) * math.sin(f) + k * (k @ a0) * (1 - math.cos(f))


def _aabb(p: np.ndarray, a: np.ndarray, r: float, w0: float, w1: float) -> tuple[np.ndarray, np.ndarray]:
    """Uç p, eksen a: w ∈ [w0, w1], yarıçap r silindirinin eksen hizalı sınır kutusu."""
    c0 = p + w0 * a
    c1 = p + w1 * a
    ext = r * np.sqrt(np.clip(1.0 - a * a, 0.0, None))
    return np.minimum(c0, c1) - ext, np.maximum(c0, c1) + ext


def _prepare5(ops) -> list[Toolpath]:
    if not ops:
        raise CamError("Simülasyon: program boş")
    yollar = []
    for op in ops:
        if not isinstance(op, Toolpath):
            raise CamError(f"Simülasyon: Toolpath bekleniyor ({type(op).__name__})")
        if isinstance(op.tool, LatheTool) or not isinstance(op.tool, Tool):
            raise CamError(f"Yol '{op.name}': torna takımı freze simülasyonunda (SPEC 22)")
        if op.plane is not Plane.XY:
            raise CamError(f"Yol '{op.name}': yalnız G17 (XY) yolları simüle edilir")
        if op.feed_mode is not FeedMode.PER_MIN:
            raise CamError(f"Yol '{op.name}': yalnız G94 (mm/dk) ilerleme simüle edilir")
        op.validate()
        yollar.append(op)
    return yollar


def _world_axis(tp: Toolpath, m: Move) -> np.ndarray:
    a = np.array(m.axis if m.axis is not None else (0.0, 0.0, 1.0), dtype=float)
    if tp.frame is not None:
        a = tp.frame.to_world_vec(a)
    return a / np.linalg.norm(a)


def _to_world(tp: Toolpath, p) -> np.ndarray:
    p = np.asarray(p, dtype=float)
    return p if tp.frame is None else tp.frame.to_world(p)


# ---------------------------------------------------------------- simülasyon çekirdeği


class _Sim5:
    def __init__(self, td: TriDexel, part, tol: float, gouge_tol: float, sigma: float, arc_tol: float):
        self.td = td
        self.part = part
        self.tol = tol
        self.gouge_tol = gouge_tol
        self.sigma = sigma
        self.arc_tol = arc_tol
        self.lo_box, self.hi_box = td.bounds()
        self.fam = {}
        for ad in AXES:
            ax, i1, i2 = FAMILY[ad]
            g = td.grid(ad)
            self.fam[ad] = (ax, i1, i2, g, g.xs(), g.ys(), np.eye(3)[ax])
        self.coll: dict[tuple[str, int], Collision] = {}

    # -- ışınlar
    def _window(self, ad: str, lo: np.ndarray, hi: np.ndarray):
        ax, i1, i2, g, *_ = self.fam[ad]
        return g.window(lo[i1], hi[i1], lo[i2], hi[i2])

    def _origins(self, ad: str, w) -> np.ndarray:
        ax, i1, i2, g, xs, ys, _ = self.fam[ad]
        C1, C2 = np.meshgrid(xs[w[1]], ys[w[0]])
        Ob = np.zeros((C1.size, 3))
        Ob[:, i1] = C1.ravel()
        Ob[:, i2] = C2.ravel()
        return Ob

    def _point(self, ad: str, w, j: int, s: float) -> tuple[float, float, float]:
        Ob = self._origins(ad, w)[j]
        Ob[self.fam[ad][0]] = s
        return tuple(float(v) for v in Ob)

    def _flat(self, ad: str, w) -> np.ndarray:
        g = self.fam[ad][3]
        rows, cols = np.arange(w[0].start, w[0].stop), np.arange(w[1].start, w[1].stop)
        jj, ii = np.meshgrid(rows, cols, indexing="ij")
        return (jj * g.nx + ii).ravel()

    def _record(self, kind: str, k: int, op: int, depth: float, at) -> None:
        if not depth > self.tol:
            return
        old = self.coll.get((kind, k))
        if old is None or depth > old.depth:
            self.coll[(kind, k)] = Collision(kind, k, op, at, float(depth))

    # -- adım
    def step(self, k: int, op: int, tool: Tool, chords, a0: np.ndarray, a1: np.ndarray, rapid: bool) -> float:
        """Adım k'yi uygular; kaldırılan hacmi [mm³] döndürür."""
        R, _ = _radii(tool)
        Lf = float(tool.flute_length)
        smax = min(R, Lf) / 2
        pieces = cutter_pieces(tool, self.arc_tol)
        theta = _angle(a0, a1)
        n_eksen = math.ceil(theta * math.hypot(Lf, R) / self.sigma - 1e-12) if theta > _EKSEN_TOL else 1
        topla = {ad: [] for ad in AXES}  # (düz indeks, kaldırılan boy, çakma boyu, en alçak s)
        hacim = 0.0
        for pa, pb in chords:
            n = max(1, math.ceil(float(np.linalg.norm(pb - pa)) / smax - 1e-12), n_eksen)
            for i in range(n):
                sa = pa + (pb - pa) * (i / n)
                sb = pa + (pb - pa) * ((i + 1) / n)
                a = a0 if theta <= _EKSEN_TOL else _slerp(a0, a1, (i + 0.5) / n)
                self._body(k, op, tool, sb, a)
                for ad in AXES:
                    hacim += self._remove(ad, tool, pieces, sa, sb, a, topla[ad])
        for ad in AXES:
            if not topla[ad]:
                continue
            idx, boy, cak, low = (np.concatenate(x) for x in zip(*topla[ad], strict=True))
            u, ters = np.unique(idx, return_inverse=True)
            if rapid:
                self._kayit_toplam("hizli_carpma", k, op, ad, u, ters, boy, low)
            if self.part is not None:
                self._kayit_toplam("cakma", k, op, ad, u, ters, cak, low, esik=self.gouge_tol)
        return hacim / 3

    def _kayit_toplam(self, kind, k, op, ad, u, ters, deger, low, esik=None) -> None:
        top = np.bincount(ters, weights=deger)
        j = int(np.argmax(top))
        d = float(top[j])
        if esik is not None and not d > esik:
            return
        en_alt = np.full(u.size, np.inf)
        np.minimum.at(en_alt, ters, np.where(deger > 0, low, np.inf))
        g = self.fam[ad][3]
        jj, ii = divmod(int(u[j]), g.nx)
        w = (slice(jj, jj + 1), slice(ii, ii + 1))
        self._record(kind, k, op, d, self._point(ad, w, 0, float(en_alt[j])))

    def _remove(self, ad, tool, pieces, sa, sb, a, topla) -> float:
        m = self.td.maps[ad]
        if ad == "z" and np.max(np.abs(a - _Z)) <= 1e-12:
            R = tool.D / 2
            g = self.fam[ad][3]
            lo, hi = np.minimum(sa, sb) - R, np.maximum(sa, sb) + R
            w = g.window(lo[0], hi[0], lo[1], hi[1])
            if w is None:
                return 0.0
            X, Y = np.meshgrid(self.fam[ad][4][w[1]], self.fam[ad][5][w[0]])
            lo_, hi_ = sweep_envelope(tool, sa, sb, X, Y), sweep_top(tool, sa, sb, X, Y)
        else:
            R, _ = _radii(tool)
            l0, h0 = _aabb(sa, a, R, 0.0, float(tool.flute_length))
            l1, h1 = _aabb(sb, a, R, 0.0, float(tool.flute_length))
            w = self._window(ad, np.minimum(l0, l1), np.maximum(h0, h1))
            if w is None:
                return 0.0
            Ob = self._origins(ad, w)
            s0, s1 = sweep_interval(pieces, Ob - sa, self.fam[ad][6], sb - sa, a)
            shape = (w[0].stop - w[0].start, w[1].stop - w[1].start)
            lo_, hi_ = s0.reshape(shape), s1.reshape(shape)
        if not (hi_ > lo_).any():
            return 0.0
        cak = np.zeros(lo_.shape)
        if self.part is not None:
            plo, phi = self.part[ad]
            k_lo = np.maximum(m.lo[w], lo_[..., None])
            k_hi = np.minimum(m.hi[w], hi_[..., None])
            k_hi = np.where((m.hi[w] > m.lo[w]) & (k_hi > k_lo), k_hi, k_lo)
            cak = _kesisim(k_lo, k_hi, plo[w], phi[w])
        boy, low = m.remove(w, lo_, hi_)
        if (boy > 0).any():
            topla.append((self._flat(ad, w), boy.ravel(), cak.ravel(), low.ravel()))
        return float(boy.sum()) * m.dx * m.dy

    def _body(self, k, op, tool, p, a) -> None:
        """Gövde basamakları alt adımın sonundaki konumda (uç p, eksen a), alt adımdan önceki malzemeyle:
        batma = basamağın ışın kirişi ∩ malzeme boyu (üç aileden en büyüğü)."""
        uzak = max(float(np.linalg.norm(p - c)) for c in (self.lo_box, self.hi_box))
        sifir = np.zeros(3)
        for parca, tur in body_pieces(tool, uzak + 1.0):
            w0, w1 = piece_wrange(parca)
            lo, hi = _aabb(p, a, piece_rmax(parca), w0, w1)
            lo = np.maximum(lo, self.lo_box)
            hi = np.minimum(hi, self.hi_box)
            if np.any(lo > hi):
                continue
            for ad in AXES:
                w = self._window(ad, lo, hi)
                if w is None:
                    continue
                m = self.td.maps[ad]
                ax = self.fam[ad][0]
                mlo, mhi = m.lo[w], m.hi[w]
                if not ((mhi > mlo) & (mhi > lo[ax]) & (mlo < hi[ax])).any():
                    continue
                Ob = self._origins(ad, w)
                s0, s1 = piece_interval(parca, Ob - p, self.fam[ad][6], sifir, a)
                shape = mlo.shape[:2]
                boy, low = _overlap(mlo, mhi, s0.reshape(shape), s1.reshape(shape))
                j = int(np.argmax(boy))
                if boy.flat[j] > self.tol:
                    at = self._point(ad, w, j, float(low.flat[j]))
                    self._record(f"{tur}_carpma", k, op, float(boy.flat[j]), at)


# ---------------------------------------------------------------- sürücü


def simulate5(
    ops: list[Toolpath],
    stock: Stock,
    cell: float = 1.0,
    machine: Machine | None = None,
    part: TriMesh | None = None,
    sigma: float | None = None,
    arc_tol: float = 1e-3,
    tol: float = 1e-6,
    gouge_tol: float = 1e-3,
    max_rays: int = 3_000_000,
    initial: TriDexel | None = None,
) -> SimResult5:
    """Çok eksenli programı kutu stok üzerinde tri-dexel ile simüle eder (SPEC 43)."""
    _check_positive(arc_tol=arc_tol, tol=tol, gouge_tol=gouge_tol)
    if sigma is not None:
        _check_positive(sigma=sigma)
    if machine is None:
        machine = Machine()
    if not isinstance(machine, Machine):
        raise CamError(f"machine bir Machine olmalı ({type(machine).__name__})")
    if not isinstance(stock, Stock):
        raise CamError(f"Çok eksenli simülasyon kutu stok ister ({type(stock).__name__})")
    yollar = _prepare5(ops)
    td = TriDexel.from_stock(stock, cell, max_rays)
    if initial is not None:
        if not isinstance(initial, TriDexel):
            raise CamError(f"initial TriDexel olmalı ({type(initial).__name__})")
        alanlar = ("x0", "y0", "z0", "dx", "dy", "dz", "nx", "ny", "nz")
        if any(getattr(initial, f) != getattr(td, f) for f in alanlar):
            raise CamError("initial ızgarası stok ve hücre boyundan kurulan ızgarayla uyuşmuyor")
        td = initial.copy()
    if part is not None and not isinstance(part, TriMesh):
        raise CamError(f"part TriMesh olmalı ({type(part).__name__})")

    # hareketler: dünya koordinatında kirişler ve eksenler; yaylarda eksen sabit olmalı
    plan = []  # (op, tool, Move, p0, p1, kirişler, a0, a1, link, süre)
    pos: np.ndarray | None = None
    a_pos: np.ndarray | None = None
    for i, tp in enumerate(yollar):
        eksenler = [_world_axis(tp, m) for m in tp.moves]
        a_bas = eksenler[0] if eksenler else (a_pos if a_pos is not None else _Z)
        p_bas = _to_world(tp, tp.start)
        plan.append((i, tp.tool, None, None, None, None, None, None, None, None))  # yol başı (takım değişimi)
        if pos is not None and (not np.array_equal(pos, p_bas) or _angle(a_pos, a_bas) > _EKSEN_TOL):
            m = Move(MoveType.RAPID, tuple(float(v) for v in p_bas))
            sure = move_time(pos, p_bas, m, Plane.XY, machine)
            plan.append((i, tp.tool, m, pos, p_bas, [(pos, p_bas)], a_pos, a_bas, True, sure))
        pos, a_pos = p_bas, a_bas
        p_yerel = np.array(tp.start, dtype=float)
        for m, a1 in zip(tp.moves, eksenler, strict=True):
            p1_yerel = np.array(m.end, dtype=float)
            p1 = _to_world(tp, p1_yerel)
            if m.type in ARCS:
                if _angle(a_pos, a1) > _EKSEN_TOL:
                    raise CamError(f"Yol '{tp.name}': yayda takım ekseni değişemez")
                kir = [(_to_world(tp, q0), _to_world(tp, q1)) for q0, q1 in _chords(p_yerel, m, arc_tol)]
                sure = move_time(p_yerel, p1_yerel, m, Plane.XY, machine)
            else:
                kir = [(pos, p1)]
                sure = move_time(pos, p1, m, Plane.XY, machine)
            plan.append((i, tp.tool, m, pos, p1, kir, a_pos, a1, False, sure))
            pos, a_pos, p_yerel = p1, a1, p1_yerel

    part_rays = None
    if part is not None:
        part_rays = {}
        for ad in AXES:
            g = td.grid(ad)
            ax, i1, i2 = FAMILY[ad]
            C1, C2 = np.meshgrid(g.xs(), g.ys())
            Ob = np.zeros((C1.size, 3))
            Ob[:, i1] = C1.ravel()
            Ob[:, i2] = C2.ravel()
            plo, phi = family_part(part, Ob, np.eye(3)[ax], cell)
            part_rays[ad] = (plo.reshape(g.ny, g.nx, -1), phi.reshape(g.ny, g.nx, -1))
    sim = _Sim5(td, part_rays, tol, gouge_tol, cell / 4 if sigma is None else float(sigma), arc_tol)

    steps: list[SimStep] = []
    t = 0.0
    ek = 0.0
    onceki_takim: int | None = None
    for op, tool, m, p0, p1, kir, a0, a1, link, sure in plan:
        if m is None:  # yol başı
            if onceki_takim is not None and tool.id != onceki_takim:
                ek += machine.tool_change
            onceki_takim = tool.id
            continue
        k = len(steps) + 1
        removed = sim.step(k, op, tool, kir, a0, a1, m.type is MoveType.RAPID)
        steps.append(
            SimStep(
                k=k,
                op=op,
                type=m.type,
                start=tuple(float(v) for v in p0),
                end=tuple(float(v) for v in p1),
                center=m.center,
                feed=m.feed,
                link=link,
                t0=t + ek,
                duration=sure,
                removed=removed,
                mrr=removed / sure if sure > 0 else 0.0,
            )
        )
        t += ek + sure
        ek = 0.0
    t += ek  # hareketsiz son yolda takım değişimi yine sayılır
    collisions = sorted(sim.coll.values(), key=lambda c: (c.k, KINDS.index(c.kind)))
    return SimResult5(
        tridexel=td,
        steps=steps,
        collisions=collisions,
        removed_volume=float(sum(s.removed for s in steps)),
        total_time=t,
        part=part_rays,
    )
