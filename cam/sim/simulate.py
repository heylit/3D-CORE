"""
SPEC 05 — Simülasyon sürücüsü: program → z-haritası, süre, olay listesi, çarpışma ve çakma kayıtları.

SPEC 53: block (karo boyu) ve merge (hareket birleştirme) hesabı hızlandırır. merge = True iken bir hareketin
alt adımları ve aynı doğru üzerindeki ardışık G1 hareketleri tek süpürme olarak uygulanır (gövde denetimi
hareket öncesi yüzeyle temiz çıkıyorsa ve parça z-haritası verilmemişse; aksi halde SPEC 05 yolu).

Global adım indeksi k: nokta 0 = ilk yolun başlangıcı, adım k'nin bitişi nokta k. Ardışık iki yol arasında
uçlar farklıysa doğrusal G0 bağlantı adımı eklenir. Her adım alt adımlara (boy ≤ min(R, L_f)/2) bölünür:
malzeme sonucu alt adımdan bağımsızdır (min), çarpışma denetimi hareket içindeki ilerlemeyi görür.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from cam.gcode import GRBL, DrillOp
from cam.model import (
    ARCS,
    CamError,
    FeedMode,
    LatheTool,
    Move,
    MoveType,
    Plane,
    Stock,
    Tool,
    ToolKind,
    Toolpath,
)
from cam.sim.blok import ball_envelope, merge_collinear, tiles
from cam.sim.dexel import DexelMap
from cam.sim.sweep import body_steps, flat_min_z, sweep_envelope, sweep_top
from cam.sim.timing import Machine, arc_geometry, move_time
from cam.sim.zmap import ZMap

KINDS = ("hizli_carpma", "sap_carpma", "tutucu_carpma", "cakma")


@dataclass
class Collision:
    """Çarpışma / çakma kaydı. at: hücre merkezi ve orada takım yüzeyinin Z'si (en derin batma noktası)."""

    kind: str
    k: int
    op: int
    at: tuple[float, float, float]
    depth: float


@dataclass
class SimStep:
    """Bir adım (hareket veya bağlantı). t0: başlangıç zamanı [s] (takım değişimi dahil), removed [mm³]."""

    k: int
    op: int
    type: MoveType
    start: tuple[float, float, float]
    end: tuple[float, float, float]
    center: tuple[float, float] | None
    feed: float | None
    link: bool
    t0: float
    duration: float
    removed: float
    mrr: float


@dataclass
class SimResult:
    zmap: ZMap
    steps: list[SimStep]
    start: tuple[float, float, float]
    total_time: float
    op_times: list[float]
    event_cell: np.ndarray
    event_k: np.ndarray
    event_z: np.ndarray
    offsets: np.ndarray
    collisions: list[Collision] = field(default_factory=list)
    removed_volume: float = 0.0
    part_z: np.ndarray | None = None
    dexel: DexelMap | None = None
    z0: np.ndarray | None = None  # başlangıç üst yüzeyi (olay yoksa zmap_at bunu verir)

    def points(self) -> np.ndarray:
        """Nokta 0 + her adımın bitişi, (n+1, 3)."""
        return np.array([self.start] + [s.end for s in self.steps], dtype=float)

    def cumulative_time(self) -> np.ndarray:
        """Nokta k'ye varış zamanı [s], (n+1,); nokta 0'da 0."""
        return np.array([0.0] + [s.t0 + s.duration for s in self.steps])

    def zmap_at(self, k: int) -> np.ndarray:
        """k adımdan sonraki yüzey: her hücrede k' ≤ k olan son olayın z'si, olay yoksa zmax."""
        n = len(self.steps)
        if isinstance(k, bool) or not isinstance(k, int | np.integer) or not 0 <= k <= n:
            raise CamError(f"zmap_at: k 0..{n} olmalı (k={k})")
        g = self.zmap
        z = np.full(g.nx * g.ny, g.zmax) if self.z0 is None else self.z0.ravel().copy()
        idx = np.nonzero(self.event_k <= k)[0]
        if idx.size:
            c = self.event_cell[idx]
            son = np.ones(idx.size, dtype=bool)
            son[:-1] = c[1:] != c[:-1]  # olaylar (hücre, k) sıralı → hücrenin son olayı
            z[c[son]] = self.event_z[idx[son]]
        return z.reshape(g.ny, g.nx)

    def _part_mask(self) -> tuple[np.ndarray, np.ndarray]:
        if self.part_z is None:
            raise CamError("Parça z-haritası verilmedi")
        g = self.zmap
        return np.clip(self.part_z, g.zmin, g.zmax), self.part_z > g.zmin

    def rest_volume(self) -> float:
        """Kalan malzeme V = Σ max(z − max(z_P, zmin), 0)·dx·dy"""
        zP, _ = self._part_mask()
        g = self.zmap
        return float(np.sum(np.clip(g.z - zP, 0.0, None)) * g.dx * g.dy)

    def gouge_volume(self) -> float:
        """Çakma hacmi V = Σ max(z_P − z, 0)·dx·dy (z_P > zmin hücrelerde)"""
        zP, var = self._part_mask()
        g = self.zmap
        return float(np.sum(np.where(var, np.clip(zP - g.z, 0.0, None), 0.0)) * g.dx * g.dy)


# ---------------------------------------------------------------- doğrulama


def _check_positive(**vals) -> None:
    for ad, v in vals.items():
        if not (isinstance(v, int | float) and not isinstance(v, bool) and math.isfinite(v) and v > 0):
            raise CamError(f"{ad} pozitif ve sonlu olmalı ({ad}={v})")


def _prepare(ops, dialect) -> list[Toolpath]:
    if not ops:
        raise CamError("Simülasyon: program boş")
    yollar = []
    for op in ops:
        if isinstance(op, DrillOp):
            op = op.to_toolpath(dialect)
        if not isinstance(op, Toolpath):
            raise CamError(f"Simülasyon: Toolpath veya DrillOp bekleniyor ({type(op).__name__})")
        if isinstance(op.tool, LatheTool):
            raise CamError(f"Yol '{op.name}': torna takımı freze simülasyonunda (SPEC 22)")
        if op.plane is not Plane.XY:
            raise CamError(f"Yol '{op.name}': yalnız G17 (XY) yolları simüle edilir")
        if op.feed_mode is not FeedMode.PER_MIN:
            raise CamError(f"Yol '{op.name}': yalnız G94 (mm/dk) ilerleme simüle edilir")
        op.validate()
        yollar.append(op)
    return yollar


# ---------------------------------------------------------------- hareketin parçaları


def _chords(p0: np.ndarray, m: Move, arc_tol: float) -> list[tuple[np.ndarray, np.ndarray]]:
    """Doğru → tek parça; yay → kiriş sapması ≤ arc_tol olan kirişler (Z doğrusal paylaşılır)."""
    p1 = np.array(m.end, dtype=float)
    if m.type not in ARCS:
        return [(p0, p1)]
    cw = m.type is MoveType.ARC_CW
    r, dth, th0 = arc_geometry(p0, p1, m.center, cw)
    adim = 2 * math.acos(1 - arc_tol / r) if arc_tol < r else math.pi / 2
    n = max(1, math.ceil(dth / adim - 1e-12))
    s = -1.0 if cw else 1.0
    cx, cy = m.center
    pts = [p0]
    for i in range(1, n):
        th = th0 + s * dth * i / n
        pts.append(np.array([cx + r * math.cos(th), cy + r * math.sin(th), p0[2] + (p1[2] - p0[2]) * i / n]))
    pts.append(p1)
    return list(zip(pts[:-1], pts[1:], strict=True))


def _substeps(a: np.ndarray, b: np.ndarray, smax: float):
    n = max(1, math.ceil(float(np.linalg.norm(b - a)) / smax - 1e-12))
    for i in range(n):
        yield a + (b - a) * (i / n), a + (b - a) * ((i + 1) / n)


# ---------------------------------------------------------------- sürücü


class _ZField:
    """Z-haritası: kaldırma z ← max(zmin, min(z, e))."""

    def __init__(self, g: ZMap) -> None:
        self.g = g

    def top(self, w) -> np.ndarray:
        return self.g.z[w]

    def remove(self, w, tool: Tool, a, b, X, Y, env=sweep_envelope) -> tuple[np.ndarray, np.ndarray]:
        z_once = self.g.z[w]
        z_yeni = np.maximum(self.g.zmin, np.minimum(z_once, env(tool, a, b, X, Y)))
        boy = z_once - z_yeni
        self.g.z[w] = z_yeni
        return boy, np.where(boy > 0, z_yeni, np.inf)


class _DField:
    """Dexel: kesen kısmın aralığı [e, e_üst] çıkarılır."""

    def __init__(self, d: DexelMap) -> None:
        self.d = d

    def top(self, w) -> np.ndarray:
        t = self.d.hi[w].max(axis=2)
        return np.where(np.isfinite(t), t, self.d.zmin)

    def remove(self, w, tool: Tool, a, b, X, Y, env=sweep_envelope) -> tuple[np.ndarray, np.ndarray]:
        return self.d.remove(w, env(tool, a, b, X, Y), sweep_top(tool, a, b, X, Y))


def _rel(w, W):
    """Mutlak pencere w'nin, onu kapsayan W penceresine göre dilimleri."""
    return tuple(slice(s.start - S.start, s.stop - S.start) for s, S in zip(w, W, strict=True))


class _Sim:
    def __init__(
        self,
        field,
        grid: ZMap,
        part_z,
        tol: float,
        gouge_tol: float,
        arc_tol: float,
        block: int | None = None,
        merge: bool = False,
    ) -> None:
        self.f = field
        self.g = grid  # yalnız ızgara bilgisi (pencere, merkezler)
        self.xs = grid.xs()
        self.ys = grid.ys()
        self.part_z = part_z
        self.tol = tol
        self.gouge_tol = gouge_tol
        self.arc_tol = arc_tol
        self.gouged = None if part_z is None else np.zeros_like(part_z, dtype=bool)
        self.coll: dict[tuple[str, int], Collision] = {}
        self.ev_cell: list[np.ndarray] = []
        self.ev_k: list[np.ndarray] = []
        self.ev_z: list[np.ndarray] = []
        self.say = np.zeros(grid.nx * grid.ny, dtype=np.int64)
        self.block = block
        self.merge = merge

    def _record(self, kind: str, k: int, op: int, depth: np.ndarray, X, Y, zs) -> None:
        j = int(np.argmax(depth))
        d = float(depth.flat[j])
        if not d > self.tol:
            return
        old = self.coll.get((kind, k))
        if old is None or d > old.depth:
            at = (float(X.flat[j]), float(Y.flat[j]), float(np.asarray(zs).flat[j]))
            self.coll[(kind, k)] = Collision(kind, k, op, at, d)

    def _win(self, pts: list[np.ndarray], rho: float):
        P = np.array(pts)
        lo = P.min(axis=0) - rho
        hi = P.max(axis=0) + rho
        return self.g.window(lo[0], hi[0], lo[1], hi[1])

    def _xy(self, w):
        return np.meshgrid(self.xs[w[1]], self.ys[w[0]])

    def _remove(self, w, tool: Tool, a, b, boy: np.ndarray, W, env=sweep_envelope) -> np.ndarray | None:
        """Penceredeki kaldırma, ≤ block × block karolar halinde (hücre başına işlem → sonuç aynı).

        Kaldırılan boy W penceresine göre boy dizisine eklenir. Dönüş: parça z-haritası varsa pencerenin en
        alçak kaldırılan z'si (çakma denetimi için), yoksa None.
        """
        en_alt = None if self.part_z is None else np.empty((w[0].stop - w[0].start, w[1].stop - w[1].start))
        for t in tiles(w, self.block):
            X, Y = self._xy(t)
            b_sub, e_sub = self.f.remove(t, tool, a, b, X, Y, env)
            boy[_rel(t, W)] += b_sub
            if en_alt is not None:
                en_alt[_rel(t, w)] = e_sub
        return en_alt

    def _events(self, W, degisen: np.ndarray, z: np.ndarray, k) -> None:
        """Değişen hücrelerin olayları; k skaler ya da hücre başına dizi."""
        jj, ii = np.nonzero(degisen)
        cell = ((jj + W[0].start) * self.g.nx + (ii + W[1].start)).astype(np.int32)
        self.ev_cell.append(cell)
        self.ev_k.append(k)  # skaler ya da hücre başına
        self.ev_z.append(z)
        self.say[cell] += 1  # bir çağrıda hücreler tekil

    def step(self, k: int, op: int, tool: Tool, p0: np.ndarray, m: Move) -> float:
        """Adım k'yi uygular; kaldırılan hacmi [mm³] döndürür."""
        R = tool.D / 2
        smax = min(R, tool.flute_length) / 2
        steps = body_steps(tool)
        rho_max = max(R, steps[-1][0])
        H_min = steps[0][1]
        chords = _chords(p0, m, self.arc_tol)
        W = self._win([c[0] for c in chords] + [chords[-1][1]], R)
        if W is not None:
            top_once = self.f.top(W).copy()
            boy = np.zeros_like(top_once)
        for a, b in chords:
            for sa, sb in _substeps(a, b, smax):
                self._body(k, op, sa, sb, steps, rho_max, H_min)
                w = self._win([sa, sb], R)
                if w is None:
                    continue
                en_alt = self._remove(w, tool, sa, sb, boy, W)
                if en_alt is not None:
                    X, Y = self._xy(w)
                    self._gouge(k, op, w, en_alt, X, Y)
        if W is None or not (boy > 0).any():
            return 0.0
        if m.type is MoveType.RAPID:  # hızlı harekette malzemeye giriş: hücre başına kaldırılan boy
            X, Y = self._xy(W)
            self._record("hizli_carpma", k, op, boy, X, Y, self.f.top(W))
        top_sonra = self.f.top(W)
        degisen = top_sonra < top_once
        if degisen.any():
            self._events(W, degisen, top_sonra[degisen], k)
        return float(np.sum(boy) * self.g.dx * self.g.dy)

    def group(self, k0: int, op: int, tool: Tool, p0: np.ndarray, moves: list[Move]) -> list[float]:
        """Adımlar k0, k0+1, … (aynı doğru üzerindeki G1'ler ya da tek hareket) → hareket başına hacim.

        merge kapalıysa, parça z-haritası varsa veya gövde hareket öncesi yüzeye yaklaşabiliyorsa
        SPEC 05 yolu.
        """
        pts = [p0] + [np.array(m.end, dtype=float) for m in moves]
        chords = _chords(p0, moves[0], self.arc_tol) if len(moves) == 1 else [(p0, pts[-1])]
        kose = [c[0] for c in chords] + [chords[-1][1]]
        if not self.merge or self.part_z is not None or not self._body_clear(tool, pts + kose):
            return [self.step(k0 + i, op, tool, pts[i], m) for i, m in enumerate(moves)]
        R = tool.D / 2
        W = self._win(kose, R)
        if W is None:
            return [0.0] * len(moves)
        env = _ball if tool.kind is not ToolKind.DRILL and tool.corner_r == R else sweep_envelope
        top_once = self.f.top(W).copy()
        boy = np.zeros_like(top_once)
        for a, b in chords:
            w = self._win([a, b], R)
            if w is not None:
                self._remove(w, tool, a, b, boy, W, env)
        if not (boy > 0).any():
            return [0.0] * len(moves)
        top_sonra = self.f.top(W)
        if moves[0].type is MoveType.RAPID:
            X, Y = self._xy(W)
            self._record("hizli_carpma", k0, op, boy, X, Y, top_sonra)
        degisen = top_sonra < top_once
        dA = self.g.dx * self.g.dy
        if len(moves) == 1:
            if degisen.any():
                self._events(W, degisen, top_sonra[degisen], k0)
            return [float(np.sum(boy) * dA)]
        # pencere farkı: hücre, penceresi onu ilk kapsayan harekete yazılır
        sahip = np.full(boy.shape, len(moves) - 1)
        bos = np.ones(boy.shape, dtype=bool)
        for i in range(len(moves) - 1):
            w = self._win([pts[i], pts[i + 1]], R)
            if w is None:
                continue
            r = _rel(w, W)
            yeni = bos[r]
            sahip[r] = np.where(yeni, i, sahip[r])
            bos[r] = False
        hacim = np.bincount(sahip.ravel(), weights=boy.ravel(), minlength=len(moves)) * dA
        if degisen.any():
            self._events(W, degisen, top_sonra[degisen], k0 + sahip[degisen])
        return [float(v) for v in hacim]

    def _body_clear(self, tool: Tool, pts: list[np.ndarray]) -> bool:
        """Gövde denetimi bu harekette tetiklenebilir mi?

        Hareket öncesi yüzey en alçak uç + en alçak gövde basamağı + tol'un altındaysa hiçbir alt adımda
        tetiklenmez (yüzey yalnız alçalır, alt adım pencereleri hareket penceresinin içinde).
        """
        steps = body_steps(tool)
        rho_max = max(tool.D / 2, steps[-1][0])
        wb = self._win(pts, rho_max)
        if wb is None:
            return True
        z_alt = min(float(p[2]) for p in pts)
        return not self.f.top(wb).max() > z_alt + steps[0][1] + self.tol

    def _body(self, k, op, a, b, steps, rho_max, H_min) -> None:
        """Gövde (sap, tutucu) denetimi: alt adımdan önceki üst yüzeyle."""
        wb = self._win([a, b], rho_max)
        if wb is None:
            return
        zb = self.f.top(wb)
        if not zb.max() > min(a[2], b[2]) + H_min + self.tol:
            return
        X, Y = self._xy(wb)
        for rho, H, tur in steps:
            eB = flat_min_z(a, b, X, Y, rho) + H
            depth = np.where(np.isfinite(eB), zb - eB, -np.inf)
            self._record(f"{tur}_carpma", k, op, depth, X, Y, eB)

    def _gouge(self, k, op, w, en_alt, X, Y) -> None:
        """Çakma: alt adımda en alçak kaldırılan nokta parça üst yüzeyinin gouge_tol'dan fazla altında."""
        if self.part_z is None:
            return
        zP = self.part_z[w]
        yeni = np.isfinite(en_alt) & (en_alt < zP - self.gouge_tol) & ~self.gouged[w]
        if yeni.any():
            self._record("cakma", k, op, np.where(yeni, zP - en_alt, -np.inf), X, Y, en_alt)
            self.gouged[w] |= yeni


def _ball(tool: Tool, a, b, X, Y) -> np.ndarray:
    return ball_envelope(a, b, tool.D / 2, X, Y, tool)


def simulate(
    ops: list[Toolpath | DrillOp],
    stock: Stock,
    cell: float = 1.0,
    machine: Machine | None = None,
    part_z: np.ndarray | None = None,
    arc_tol: float = 1e-3,
    tol: float = 1e-6,
    gouge_tol: float = 1e-3,
    dialect=GRBL,
    max_cells: int = 20_000_000,
    model: str = "zmap",
    initial: ZMap | DexelMap | None = None,
    block: int | None = 256,
    merge: bool = True,
) -> SimResult:
    """Freze programını kutu stok üzerinde z-haritasıyla simüle eder (SPEC 05)."""
    _check_positive(arc_tol=arc_tol, tol=tol, gouge_tol=gouge_tol)
    if block is not None and (isinstance(block, bool) or not isinstance(block, int) or block <= 0):
        raise CamError(f"block pozitif tam sayı veya None olmalı (block={block!r})")
    if machine is None:
        machine = Machine()
    if not isinstance(machine, Machine):
        raise CamError(f"machine bir Machine olmalı ({type(machine).__name__})")
    if not isinstance(stock, Stock):
        raise CamError(f"Freze simülasyonu kutu stok ister ({type(stock).__name__})")
    yollar = _prepare(ops, dialect)
    if model not in ("zmap", "dexel"):
        raise CamError(f"Bilinmeyen stok modeli: {model!r} (zmap veya dexel)")
    grid = ZMap.from_stock(stock, cell, max_cells)
    if initial is not None:
        tur = ZMap if model == "zmap" else DexelMap
        if not isinstance(initial, tur):
            raise CamError(f"initial {tur.__name__} olmalı ({type(initial).__name__})")
        alanlar = ("x0", "y0", "dx", "dy", "nx", "ny", "zmin", "zmax")
        if any(getattr(initial, a) != getattr(grid, a) for a in alanlar):
            raise CamError("initial ızgarası stok ve hücre boyundan kurulan ızgarayla uyuşmuyor")
    if model == "zmap":
        if initial is not None:
            grid = initial.copy()
        field = _ZField(grid)
        dexel = None
    else:
        dexel = DexelMap.from_stock(stock, cell, max_cells) if initial is None else initial.copy()
        field = _DField(dexel)
    z0 = field.top((slice(None), slice(None))).copy()
    if part_z is not None:
        part_z = np.asarray(part_z, dtype=float)
        if part_z.shape != grid.z.shape:
            raise CamError(f"part_z şekli ızgarayla uyuşmuyor ({part_z.shape} ≠ {grid.z.shape})")
    sim = _Sim(field, grid, part_z, tol, gouge_tol, arc_tol, block, merge)

    steps: list[SimStep] = []
    op_times = [0.0] * len(yollar)
    t = 0.0
    pos: np.ndarray | None = None
    onceki_takim: int | None = None
    start = yollar[0].start

    def adim(op: int, tool: Tool, p0: np.ndarray, ms: list[Move], link: bool, ek: float) -> np.ndarray:
        """ms: tek hareket ya da birleştirilen G1 grubu; her hareket ayrı SimStep."""
        nonlocal t
        hacimler = sim.group(len(steps) + 1, op, tool, p0, ms)
        for m, removed in zip(ms, hacimler, strict=True):
            k = len(steps) + 1
            sure = move_time(p0, m.end, m, Plane.XY, machine)
            t0 = t + ek
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
            ek = 0.0
            p0 = np.array(m.end, dtype=float)
        return p0

    for i, tp in enumerate(yollar):
        ek = 0.0
        if onceki_takim is not None and tp.tool.id != onceki_takim:
            ek = machine.tool_change
        onceki_takim = tp.tool.id
        p_bas = np.array(tp.start, dtype=float)
        if pos is not None and not np.array_equal(pos, p_bas):
            pos = adim(i, tp.tool, pos, [Move(MoveType.RAPID, tp.start)], True, ek)
            ek = 0.0
        elif pos is None:
            pos = p_bas
        gruplar = merge_collinear(tp.moves, start=pos) if merge else [(j, j) for j in range(len(tp.moves))]
        for a, b in gruplar:
            pos = adim(i, tp.tool, pos, tp.moves[a : b + 1], False, ek)
            ek = 0.0
        if ek:  # hareketsiz yolda takım değişimi yine sayılır
            t += ek
            op_times[i] += ek

    # olaylar (hücre, k) sıralı: hücre başına sayım + sıra → doğrudan yerleştirme (lexsort ile aynı sonuç)
    offsets = np.zeros(grid.nx * grid.ny + 1, dtype=np.int64)
    np.cumsum(sim.say, out=offsets[1:])
    cell_ = np.repeat(np.arange(grid.nx * grid.ny, dtype=np.int32), sim.say)
    k_ = np.empty(cell_.size, dtype=np.int32)
    z_ = np.empty(cell_.size)
    yer0 = offsets[:-1].copy()  # hücrenin sıradaki boş yeri
    for c, kk, zz in zip(sim.ev_cell, sim.ev_k, sim.ev_z, strict=True):
        yer = yer0[c]
        k_[yer] = kk
        z_[yer] = zz
        yer0[c] += 1
    collisions = sorted(sim.coll.values(), key=lambda c: (c.k, KINDS.index(c.kind)))
    if dexel is not None:
        grid.z = dexel.top()
    return SimResult(
        zmap=grid,
        dexel=dexel,
        z0=z0,
        steps=steps,
        start=start,
        total_time=t,
        op_times=op_times,
        event_cell=cell_.astype(np.int32, copy=False),
        event_k=k_.astype(np.int32, copy=False),
        event_z=z_,
        offsets=offsets,
        collisions=collisions,
        removed_volume=float(sum(s.removed for s in steps)),
        part_z=part_z,
    )
