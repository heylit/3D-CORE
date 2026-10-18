"""
SPEC 22 — Torna talaş simülasyonu (radyal dexel), süre, hızlı çarpma, kenar boyu aşımı, tutucu ve ayna
çarpışması, çakma; SPEC 24 olay listesi.

Burun merkezi C = P − q_T; takım noktaları (z, x) düzlemindedir. Her adım alt adımlara (boy ≤ min(l, 2r, 1)/2)
bölünür. Alt adımda (Ek 1): kesici süpürmesi (hareketin başından alt adımın sonuna) her hücreden çıkarılır,
sonra gövde, tutucu ve ayna denetimleri kalan malzemeyle yapılır. Malzeme sonucu alt adımlardan bağımsızdır.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from cam.lathe import tip_offset
from cam.model import ARCS, CamError, CylinderStock, LatheTool, Move, MoveType, Plane, Setup, Tool, Toolpath
from cam.sim.lathe_shape import LatheShape, cutter_shape, rounded_interval, sweep_hull, to_radial
from cam.sim.lathe_time import lathe_move_time, zx_arc
from cam.sim.radial import RadialMap, iv_overlap, iv_subtract, iv_volume
from cam.sim.simulate import Collision, SimStep
from cam.sim.timing import Machine

KINDS = ("hizli_carpma", "kenar_asimi", "tutucu_carpma", "ayna_carpma", "cakma")
X_TOL = 1e-9  # mm, eksenel takımda |x| sınırı


@dataclass
class LatheSimResult:
    rmap: RadialMap
    steps: list[SimStep]
    start: tuple[float, float, float]
    total_time: float
    op_times: list[float]
    event_cell: np.ndarray  # int32
    event_k: np.ndarray  # int32
    event_iv_off: np.ndarray  # int64, olay sayısı + 1
    event_iv: np.ndarray  # float64 (M, 2)
    offsets: np.ndarray  # int64, nz + 1
    collisions: list[Collision] = field(default_factory=list)
    removed_volume: float = 0.0
    part: RadialMap | None = None
    _start: RadialMap | None = field(default=None, repr=False)  # başlangıç haritası

    def points(self) -> np.ndarray:
        """Nokta 0 + her adımın bitişi, (n+1, 3)."""
        return np.array([self.start] + [s.end for s in self.steps], dtype=float)

    def cumulative_time(self) -> np.ndarray:
        """Nokta k'ye varış zamanı [s], (n+1,); nokta 0'da 0."""
        return np.array([0.0] + [s.t0 + s.duration for s in self.steps])

    def section_at(self, k: int) -> list[list[tuple[float, float]]]:
        """k adımdan sonraki kesit; 0 ≤ k ≤ n, aksi CamError."""
        n = len(self.steps)
        if isinstance(k, bool) or not isinstance(k, int | np.integer) or not 0 <= k <= n:
            raise CamError(f"section_at: k 0..{n} olmalı (k={k})")
        base = self._start if self._start is not None else RadialMap.empty_like(self.rmap)
        sec = [list(iv) for iv in base.iv]
        idx = np.nonzero(self.event_k <= k)[0]
        if idx.size:
            c = self.event_cell[idx]
            son = np.ones(idx.size, dtype=bool)
            son[:-1] = c[1:] != c[:-1]  # olaylar (hücre, k) sıralı → hücrenin son olayı
            for j in idx[son]:
                a, b = self.event_iv_off[j], self.event_iv_off[j + 1]
                sec[int(self.event_cell[j])] = [(float(lo), float(hi)) for lo, hi in self.event_iv[a:b]]
        return sec

    def _part(self) -> RadialMap:
        if self.part is None:
            raise CamError("Parça haritası verilmedi")
        return self.part

    def rest_volume(self) -> float:
        """V_kalan = Σ π(u² − l²)·dz, malzeme aralıkları − parça aralıkları."""
        part = self._part()
        V = 0.0
        for mat, par in zip(self.rmap.iv, part.iv, strict=True):
            kalan = list(mat)
            for lo, hi in par:
                kalan = iv_subtract(kalan, lo, hi)
            V += iv_volume(kalan, self.rmap.dz)
        return V

    def gouge_volume(self) -> float:
        """Çakma hacmi: parça aralıklarının (stok içinde) malzemede olmayan kısmı."""
        part = self._part()
        base = self._start if self._start is not None else self.rmap
        V = 0.0
        for mat, par, bas in zip(self.rmap.iv, part.iv, base.iv, strict=True):
            ic = [(max(a, c), min(b, d)) for a, b in par for c, d in bas if min(b, d) - max(a, c) > 0]
            for lo, hi in mat:
                ic = iv_subtract(ic, lo, hi)
            V += iv_volume(ic, self.rmap.dz)
        return V


# ---------------------------------------------------------------- doğrulama


def _check_positive(**vals) -> None:
    for ad, v in vals.items():
        if not (isinstance(v, int | float) and not isinstance(v, bool) and math.isfinite(v) and v > 0):
            raise CamError(f"{ad} pozitif ve sonlu olmalı ({ad}={v})")


def _prepare(ops) -> list[Toolpath]:
    if not ops:
        raise CamError("Torna simülasyonu: program boş")
    yollar = []
    for op in ops:
        if not isinstance(op, Toolpath):
            raise CamError(f"Torna simülasyonu: Toolpath bekleniyor ({type(op).__name__})")
        if op.plane is not Plane.ZX:
            raise CamError(f"Yol '{op.name}': torna simülasyonu yalnız G18 (ZX) yolları alır")
        if not isinstance(op.tool, LatheTool | Tool):
            raise CamError(f"Yol '{op.name}': bilinmeyen takım ({type(op.tool).__name__})")
        op.validate()
        yollar.append(op)
    return yollar


def _side(tp: Toolpath, stock: CylinderStock) -> str | None:
    """Taraf: yolun bu kuralı sağlayan ilk noktası (start önce): x ≥ D/2 → dış; d > 0 ve x ≤ d/2 → iç.

    Eksenel takımda taraf yok; bütün noktalar x = 0'da olmalı, yay olmamalı.
    """
    if isinstance(tp.tool, Tool):
        for m in tp.moves:
            if m.type in ARCS:
                raise CamError(f"Yol '{tp.name}': eksenel takımla yay olmaz")
        if np.any(np.abs(tp.points()[:, 0]) > X_TOL):
            raise CamError(f"Yol '{tp.name}': eksenel takımın bütün noktaları x = 0'da olmalı")
        return None
    for x in tp.points()[:, 0]:  # start, sonra sırayla hareket bitişleri (Ek 3)
        if x >= stock.D / 2:
            return "dis"
        if stock.d > 0 and x <= stock.d / 2:
            return "ic"
    raise CamError(f"Yol '{tp.name}': taraf belirlenemiyor (hiçbir nokta stok dışında / delik içinde değil)")


def _zx_points(p0: np.ndarray, m: Move, arc_tol: float) -> list[np.ndarray]:
    """Doğru → uçlar; G18 yayı → kiriş sapması ≤ arc_tol olan kiriş uçları (y doğrusal paylaşılır)."""
    p1 = np.array(m.end, dtype=float)
    if m.type not in ARCS:
        return [p0, p1]
    cw = m.type is MoveType.ARC_CW
    R, dth, th0, cu, cv = zx_arc(p0, p1, m.center, cw)
    adim = 2 * math.acos(1 - arc_tol / R) if arc_tol < R else math.pi / 2
    n = max(1, math.ceil(dth / adim - 1e-12))
    s = -1.0 if cw else 1.0
    pts = [p0]
    for i in range(1, n):
        th = th0 + s * dth * i / n
        pts.append(np.array([cv + R * math.sin(th), p0[1] + (p1[1] - p0[1]) * i / n, cu + R * math.cos(th)]))
    pts.append(p1)
    return pts


# ---------------------------------------------------------------- sürücü


@dataclass
class _Tool:
    """Bir yolun simülasyondaki takımı: şekil, uç kayması q, alt adım boyu, gövde kırpma."""

    shape: LatheShape
    q: np.ndarray
    smax: float
    clip: bool


class _LSim:
    def __init__(self, m: RadialMap, part, fixtures, tol: float, gouge_tol: float) -> None:
        self.m = m
        self.zc = m.centers()
        self.outer = m.outer()
        self.inner = m.inner()
        self.part = part
        self.tol = tol
        self.gouge_tol = gouge_tol
        self.gouged = np.zeros(m.nz, dtype=bool)
        self.fix: list[list[tuple[float, float]]] = [[] for _ in range(m.nz)]
        for f in fixtures:
            for i in np.nonzero((self.zc >= f.zmin) & (self.zc <= f.zmax))[0]:
                self.fix[int(i)].append((f.d / 2, f.D / 2))
        self.has_fix = np.array([bool(f) for f in self.fix])
        self.coll: dict[tuple[str, int], Collision] = {}
        self.ev_cell: list[int] = []
        self.ev_k: list[int] = []
        self.ev_iv: list[list[tuple[float, float]]] = []

    def _record(self, kind: str, k: int, op: int, depth: float, r_at: float, z: float) -> None:
        if not depth > (self.gouge_tol if kind == "cakma" else self.tol):
            return
        c = self.coll.get((kind, k))
        if c is None or depth > c.depth:
            self.coll[(kind, k)] = Collision(kind, k, op, (float(r_at), 0.0, float(z)), float(depth))

    def _radial(self, poly, r, p0, p1, clip=False, hw=0.0) -> tuple[int, np.ndarray, np.ndarray]:
        """Süpürmenin hücre penceresi i0 ve r aralıkları (lo, hi)."""
        H = sweep_hull(poly, p0, p1)
        i0 = int(np.searchsorted(self.zc, H[:, 0].min() - r, "left"))
        i1 = int(np.searchsorted(self.zc, H[:, 0].max() + r, "right"))
        a, b = rounded_interval(H, r, self.zc[i0:i1])
        if clip:
            a = np.maximum(a, 0.0)
        lo, hi = to_radial(a, b, hw)
        return i0, lo, hi

    def _touch(self, i0: int, lo: np.ndarray, hi: np.ndarray) -> np.ndarray:
        """Malzemeyle çakışabilecek hücreler (dış / iç yarıçap ön elemesi)."""
        sl = slice(i0, i0 + len(lo))
        return i0 + np.nonzero((hi > lo) & (lo < self.outer[sl]) & (hi > self.inner[sl]))[0]

    def _cut(self, i0, lo, hi, before: dict) -> None:
        iv = self.m.iv
        for i in self._touch(i0, lo, hi):
            j = i - i0
            if i not in before:
                before[i] = iv[i]
            iv[i] = iv_subtract(iv[i], float(lo[j]), float(hi[j]))
            self.outer[i] = iv[i][-1][1] if iv[i] else 0.0
            self.inner[i] = iv[i][0][0] if iv[i] else 0.0

    def _hit(self, kind, k, op, i0, lo, hi) -> None:
        for i in self._touch(i0, lo, hi):
            j = i - i0
            d, r_at = iv_overlap(self.m.iv[i], float(lo[j]), float(hi[j]))
            self._record(kind, k, op, d, r_at, self.zc[i])

    def _fixture(self, k, op, i0, lo, hi) -> None:
        sl = slice(i0, i0 + len(lo))
        for j in np.nonzero(self.has_fix[sl] & (hi > lo))[0]:
            i = i0 + j
            d, r_at = iv_overlap(self.fix[i], float(lo[j]), float(hi[j]))
            self._record("ayna_carpma", k, op, d, r_at, self.zc[i])

    def step(self, k: int, op: int, t: _Tool, pts: list[np.ndarray], rapid: bool) -> float:
        s = t.shape
        before: dict[int, list] = {}
        C = [np.array([p[2], p[0]]) - t.q for p in pts]
        for c0, c1 in zip(C[:-1], C[1:], strict=True):
            n = max(1, math.ceil(float(np.linalg.norm(c1 - c0)) / t.smax - 1e-12))
            prev = c0
            for j in range(1, n + 1):
                pj = c1 if j == n else c0 + (c1 - c0) * (j / n)
                self._cut(*self._radial(s.core, s.r, c0, pj), before)
                body = self._radial(s.body, s.r, prev, pj, clip=t.clip)
                self._hit("kenar_asimi", k, op, *body)
                holder = None
                if s.holder is not None:
                    holder = self._radial(s.holder, 0.0, prev, pj, hw=s.half_width)
                    self._hit("tutucu_carpma", k, op, *holder)
                if self.has_fix.any():
                    self._fixture(k, op, *self._radial(s.core, s.r, prev, pj))
                    self._fixture(k, op, *body)
                    if holder is not None:
                        self._fixture(k, op, *holder)
                prev = pj
        return self._finish_step(k, op, before, rapid)

    def _finish_step(self, k: int, op: int, before: dict, rapid: bool) -> float:
        removed = 0.0
        dz = self.m.dz
        for i in sorted(before):
            B, A = before[i], self.m.iv[i]
            if A == B:
                continue
            removed += iv_volume(B, dz) - iv_volume(A, dz)
            self.ev_cell.append(int(i))
            self.ev_k.append(k)
            self.ev_iv.append(list(A))
            pieces = list(B)
            for lo, hi in A:
                pieces = iv_subtract(pieces, lo, hi)
            if rapid and pieces:
                lo, hi = max(pieces, key=lambda p: p[1] - p[0])
                self._record("hizli_carpma", k, op, hi - lo, hi, self.zc[i])
            if self.part is not None and not self.gouged[i]:
                best, r_at = 0.0, 0.0
                for a, b in self.part.iv[i]:
                    d, r = iv_overlap(pieces, a, b)
                    if d > best:
                        best, r_at = d, r
                if best > self.gouge_tol:
                    self._record("cakma", k, op, best, r_at, self.zc[i])
                    self.gouged[i] = True
        return removed


def _tool_for(tp: Toolpath, stock: CylinderStock, reach: float) -> _Tool:
    side = _side(tp, stock)
    tool = tp.tool
    if isinstance(tool, Tool):
        shape = cutter_shape(tool, None, reach=reach)
        return _Tool(shape, np.zeros(2), min(tool.flute_length, 1.0) / 2, False)
    shape = cutter_shape(tool, side, reach=reach)
    l, r = tool.edge_len, tool.nose_r  # noqa: E741
    smax = (min(l, 2 * r, 1.0) if r > 0 else min(l, 1.0)) / 2
    return _Tool(shape, tip_offset(tool.tip, r), smax, True)


def _grid_match(m, grid: RadialMap, ad: str) -> RadialMap:
    if not isinstance(m, RadialMap):
        raise CamError(f"{ad} bir RadialMap olmalı ({type(m).__name__})")
    if not m.same_grid(grid):
        raise CamError(f"{ad} ızgarası stok ve hücre boyundan kurulan ızgarayla uyuşmuyor")
    return m


def simulate_lathe(
    ops: list[Toolpath],
    stock: CylinderStock | Setup,
    cell: float = 0.5,
    machine: Machine | None = None,
    part: RadialMap | None = None,
    arc_tol: float = 1e-3,
    tol: float = 1e-6,
    gouge_tol: float = 1e-3,
    max_cells: int = 1_000_000,
    initial: RadialMap | None = None,
) -> LatheSimResult:
    """Torna programını silindir stok üzerinde radyal dexel ile simüle eder (SPEC 22)."""
    _check_positive(arc_tol=arc_tol, tol=tol, gouge_tol=gouge_tol)
    if machine is None:
        machine = Machine()
    if not isinstance(machine, Machine):
        raise CamError(f"machine bir Machine olmalı ({type(machine).__name__})")
    fixtures: list = []
    if isinstance(stock, Setup):
        fixtures = list(stock.fixtures)
        stock = stock.stock
    if not isinstance(stock, CylinderStock):
        raise CamError(f"Torna simülasyonu CylinderStock ister ({type(stock).__name__})")
    yollar = _prepare(ops)
    grid = RadialMap.from_stock(stock, cell, fixtures, max_cells)
    if part is not None:
        _grid_match(part, grid, "part")
    if initial is not None:
        grid = _grid_match(initial, grid, "initial").copy()
    start_map = grid.copy()
    reach_ek = 2 * (grid.nz * grid.dz + 2 * grid.r_max)
    takimlar = []
    for tp in yollar:
        L0 = tp.tool.flute_length if isinstance(tp.tool, Tool) else (tp.tool.edge_len or 0.0)
        takimlar.append(_tool_for(tp, stock, L0 + reach_ek))
    sim = _LSim(grid, part, fixtures, tol, gouge_tol)

    steps: list[SimStep] = []
    op_times = [0.0] * len(yollar)
    t = 0.0
    pos: np.ndarray | None = None
    onceki_takim: int | None = None

    def adim(op: int, tp: Toolpath, p0: np.ndarray, m: Move, link: bool, ek: float) -> np.ndarray:
        nonlocal t
        k = len(steps) + 1
        sure = lathe_move_time(p0, m.end, m, tp, machine)
        t0 = t + ek
        removed = sim.step(k, op, takimlar[op], _zx_points(p0, m, arc_tol), m.type is MoveType.RAPID)
        steps.append(
            SimStep(
                k=k,
                op=op,
                type=m.type,
                start=tuple(float(v) for v in p0),
                end=m.end,
                center=m.center,
                feed=m.feed,
                link=link,
                t0=t0,
                duration=sure,
                removed=removed,
                mrr=removed / sure if sure > 0 else 0.0,
            )
        )
        t = t0 + sure
        op_times[op] += ek + sure
        return np.array(m.end, dtype=float)

    for i, tp in enumerate(yollar):
        ek = 0.0
        if onceki_takim is not None and tp.tool.id != onceki_takim:
            ek = machine.tool_change
        onceki_takim = tp.tool.id
        p_bas = np.array(tp.start, dtype=float)
        if pos is not None and not np.array_equal(pos, p_bas):
            pos = adim(i, tp, pos, Move(MoveType.RAPID, tp.start), True, ek)
            ek = 0.0
        elif pos is None:
            pos = p_bas
        for m in tp.moves:
            pos = adim(i, tp, pos, m, False, ek)
            ek = 0.0
        if ek:  # hareketsiz yolda takım değişimi yine sayılır
            t += ek
            op_times[i] += ek

    cell_ = np.array(sim.ev_cell, dtype=np.int32)
    k_ = np.array(sim.ev_k, dtype=np.int32)
    sira = np.lexsort((k_, cell_)) if len(cell_) else np.zeros(0, dtype=np.int64)
    cell_, k_ = cell_[sira], k_[sira]
    listeler = [sim.ev_iv[j] for j in sira]
    iv_off = np.zeros(len(listeler) + 1, dtype=np.int64)
    np.cumsum([len(x) for x in listeler], out=iv_off[1:])
    event_iv = np.array([p for x in listeler for p in x], dtype=np.float64).reshape(-1, 2)
    offsets = np.zeros(grid.nz + 1, dtype=np.int64)
    np.cumsum(np.bincount(cell_, minlength=grid.nz), out=offsets[1:])
    collisions = sorted(sim.coll.values(), key=lambda c: (c.k, KINDS.index(c.kind)))
    removed_volume = float(sum(s.removed for s in steps))
    return LatheSimResult(
        rmap=grid,
        steps=steps,
        start=tuple(float(v) for v in yollar[0].start),
        total_time=t,
        op_times=op_times,
        event_cell=cell_,
        event_k=k_,
        event_iv_off=iv_off,
        event_iv=event_iv,
        offsets=offsets,
        collisions=collisions,
        removed_volume=removed_volume,
        part=part,
        _start=start_map,
    )
