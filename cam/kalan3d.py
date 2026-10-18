"""
SPEC 39 — 3B kalan malzeme: kalan kalınlık, bölgeler, girme derinliği ve kalan malzeme süzgeci.

Durum (state) SPEC 05'in ZMap'i ya da DexelMap'idir; bu modül yalnız okur. Süzgeç bir 3 eksen
yolunun (SPEC 03, 06, 06b) malzemeye t_min'den derin girmeyen kesme hareketlerini atar ve koşular
arasına güvenli bağlantı kurar. rest_finish / rest_rough SPEC 06 finish / rough yolunu süzer.

Taban b(q) = max(z_P(q) + δ, zmin); z-haritası t = max(z − b, 0); dexel t = Σ max(u − max(l, b), 0).
Girme: hareketin hücrede kaldıracağı boy r(q); g_k = max_q r(q). Durum güncellemesi SPEC 05 simülasyonuyla
aynı adımlarla yapılır (yay kirişleri, alt adımlar, zarf), böylece süzülmüş yolun simülasyonu süzgecin
son durumunu birebir verir.

Birimler: mm, mm/dk.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from scipy import ndimage

from cam.dropcutter import TriMesh
from cam.model import CamError, FeedMode, LatheTool, Move, MoveType, Plane, Stock, Tool, ToolKind, Toolpath
from cam.ops3d import Raster, finish, rough
from cam.sim import DexelMap, ZMap, sweep_envelope, sweep_top
from cam.sim.simulate import _chords, _substeps

State = ZMap | DexelMap

KESME = (MoveType.LINEAR, MoveType.ARC_CW, MoveType.ARC_CCW)
_GOLDEN_ITER = 80
_INV_PHI = (math.sqrt(5) - 1) / 2


# ---------------------------------------------------------------- yardımcılar


def _top(state: State) -> np.ndarray:
    """Üst yüzey (ny, nx)."""
    return state.z if isinstance(state, ZMap) else state.top()


def _check_state(state) -> None:
    if not isinstance(state, ZMap | DexelMap):
        raise CamError(f"Durum ZMap ya da DexelMap olmalı ({type(state).__name__})")


def _part_z(state: State, part_z) -> np.ndarray:
    if part_z is None:
        return np.full((state.ny, state.nx), -np.inf)
    zP = np.asarray(part_z, dtype=float)
    if zP.shape != (state.ny, state.nx):
        raise CamError(f"part_z şekli ızgarayla uyuşmuyor ({zP.shape} ≠ {(state.ny, state.nx)})")
    return zP


def _check_tool(tool) -> None:
    """Freze takımı; matkap ve torna takımı kalan malzeme işlemesinde yok."""
    if isinstance(tool, LatheTool) or not isinstance(tool, Tool):
        raise CamError(f"Kalan malzeme: freze takımı gerekli ({type(tool).__name__})")
    if tool.kind is ToolKind.DRILL:
        raise CamError("Kalan malzeme: matkap (DRILL) desteklenmez")


def _profile_envelope(f, R: float, p0, p1, X, Y) -> np.ndarray:
    """Genel dışbükey profil f(ρ) ile e(q) = min{ z(t) + f(d(t)) : d(t) ≤ R } (altın oran araması)."""
    p0 = np.asarray(p0, dtype=float)
    p1 = np.asarray(p1, dtype=float)
    wx, wy = X - p0[0], Y - p0[1]
    ux, uy = p1[0] - p0[0], p1[1] - p0[1]
    dz = p1[2] - p0[2]
    a = ux * ux + uy * uy
    c = wx * wx + wy * wy - R * R
    if a < 1e-24:  # düşey: d sabit, en alçak uç
        d = np.hypot(wx, wy)
        return np.where(c <= 0, min(p0[2], p1[2]) + f(np.minimum(d, R)), np.inf)
    b = -2.0 * (wx * ux + wy * uy)
    disc = b * b - 4 * a * c
    sq = np.sqrt(np.clip(disc, 0.0, None))
    lo = np.clip((-b - sq) / (2 * a), 0.0, 1.0)
    hi = np.clip((-b + sq) / (2 * a), 0.0, 1.0)
    mask = (disc >= 0) & (lo <= hi)
    for t in (lo, hi):
        mask &= (wx - t * ux) ** 2 + (wy - t * uy) ** 2 <= R * R * (1 + 1e-12) + 1e-18
    lo = np.where(mask, lo, 0.0)
    hi = np.where(mask, hi, 0.0)

    def g(t):
        d = np.minimum(np.hypot(wx - t * ux, wy - t * uy), R)
        return p0[2] + t * dz + f(d)

    best = np.minimum(g(lo), g(hi))
    x1 = hi - _INV_PHI * (hi - lo)
    x2 = lo + _INV_PHI * (hi - lo)
    f1, f2 = g(x1), g(x2)
    for _ in range(_GOLDEN_ITER):
        left = f1 < f2
        hi = np.where(left, x2, hi)
        lo = np.where(left, lo, x1)
        x_yeni = np.where(left, hi - _INV_PHI * (hi - lo), lo + _INV_PHI * (hi - lo))
        f_yeni = g(x_yeni)
        x1, x2 = np.where(left, x_yeni, x2), np.where(left, x1, x_yeni)
        f1, f2 = np.where(left, f_yeni, f2), np.where(left, f1, f_yeni)
    best = np.minimum(best, np.minimum(f1, f2))
    best = np.minimum(best, g(0.5 * (lo + hi)))
    return np.where(mask, best, np.inf)


def _envelope_fn(tool: Tool):
    """Takımın zarf fonksiyonu: konikte 06b Cutter profili, diğerlerinde SPEC 05 sweep_envelope."""
    if tool.kind is ToolKind.FLAT or tool.kind is ToolKind.BALL:
        return lambda a, b, X, Y: sweep_envelope(tool, a, b, X, Y)
    from cam.cutter import Cutter  # SPEC 06b

    cutter = Cutter.from_tool(tool)
    return lambda a, b, X, Y: _profile_envelope(cutter.f, cutter.R, a, b, X, Y)


def _window(state: State, pts, rho: float):
    P = np.array(pts, dtype=float)
    lo = P.min(axis=0) - rho
    hi = P.max(axis=0) + rho
    return state.window(lo[0], hi[0], lo[1], hi[1])


def _rel(w, W):
    return tuple(slice(s.start - S.start, s.stop - S.start) for s, S in zip(w, W, strict=True))


class _Saha:
    """Durum üzerinde SPEC 05 adımlarıyla kaldırma; geri alınabilir."""

    def __init__(self, state: State, tool: Tool, arc_tol: float) -> None:
        self.s = state
        self.tool = tool
        self.R = tool.D / 2
        self.smax = min(self.R, tool.flute_length) / 2
        self.env = _envelope_fn(tool)
        self.arc_tol = arc_tol
        self.xs = state.xs()
        self.ys = state.ys()

    def _sakla(self, W):
        if isinstance(self.s, ZMap):
            return self.s.z[W].copy()
        return self.s.lo[W].copy(), self.s.hi[W].copy()

    def geri_al(self, W, kayit) -> None:
        if isinstance(self.s, ZMap):
            self.s.z[W] = kayit
            return
        lo, hi = kayit
        K = self.s.lo.shape[2]
        if lo.shape[2] < K:  # dizi büyüdüyse boş yuvalarla doldur
            ek = (lo.shape[0], lo.shape[1], K - lo.shape[2])
            lo = np.concatenate([lo, np.full(ek, np.inf)], axis=2)
            hi = np.concatenate([hi, np.full(ek, -np.inf)], axis=2)
        self.s.lo[W] = lo
        self.s.hi[W] = hi

    def uygula(self, p0, m: Move):
        """Hareketi uygular. Dönüş: (g_k, pencere, geri alma kaydı); pencere yoksa (0, None, None)."""
        chords = _chords(np.asarray(p0, dtype=float), m, self.arc_tol)
        W = _window(self.s, [c[0] for c in chords] + [chords[-1][1]], self.R)
        if W is None:
            return 0.0, None, None
        kayit = self._sakla(W)
        boy = np.zeros((W[0].stop - W[0].start, W[1].stop - W[1].start))
        for a, b in chords:
            for sa, sb in _substeps(a, b, self.smax):
                w = _window(self.s, [sa, sb], self.R)
                if w is None:
                    continue
                X, Y = np.meshgrid(self.xs[w[1]], self.ys[w[0]])
                e = self.env(sa, sb, X, Y)
                if isinstance(self.s, ZMap):
                    z_once = self.s.z[w]
                    z_yeni = np.maximum(self.s.zmin, np.minimum(z_once, e))
                    boy[_rel(w, W)] += z_once - z_yeni
                    self.s.z[w] = z_yeni
                else:
                    b_sub, _ = self.s.remove(w, e, sweep_top(self.tool, sa, sb, X, Y))
                    boy[_rel(w, W)] += b_sub
        return float(boy.max()), W, kayit

    def z_yak(self, C, z_safe: float, clearance: float) -> float:
        """min(z_safe, max(C_z, max_{d(q,C) ≤ R} top(q)) + clearance)."""
        w = _window(self.s, [C], self.R)
        ust = -np.inf
        if w is not None:
            X, Y = np.meshgrid(self.xs[w[1]], self.ys[w[0]])
            ic = np.hypot(X - C[0], Y - C[1]) <= self.R
            if ic.any():
                ust = float(_top(self.s)[w][ic].max())
        return min(z_safe, max(C[2], ust) + clearance)


# ---------------------------------------------------------------- kalınlık ve bölgeler


def rest_thickness(state: State, part_z: np.ndarray | None = None, allowance: float = 0.0) -> np.ndarray:
    """Hücre başına düşey kalan kalınlık t(q), şekil (ny, nx)."""
    _check_state(state)
    if not (math.isfinite(allowance) and allowance >= 0):
        raise CamError(f"Pay (allowance) sonlu ve ≥ 0 olmalı ({allowance})")
    zP = _part_z(state, part_z)
    b = np.maximum(zP + allowance, state.zmin)
    if isinstance(state, ZMap):
        return np.maximum(state.z - b, 0.0)
    bk = b[..., None]
    gecerli = state.hi > state.lo
    parca = np.where(gecerli, state.hi - np.maximum(state.lo, bk), 0.0)
    return np.maximum(parca, 0.0).sum(axis=2)


@dataclass
class RestRegion:
    """Kalan malzeme bölgesi: hücreler [i, j], hacim, en kalın nokta ve XY sınır kutusu."""

    cells: np.ndarray
    volume: float
    t_max: float
    at: tuple[float, float, float]
    bbox: tuple[float, float, float, float]


def rest_regions(state: State, t: np.ndarray, t_min: float) -> list[RestRegion]:
    """t > t_min maskesinin 8 komşulu bileşenleri; hacme göre azalan sırada."""
    _check_state(state)
    if not (math.isfinite(t_min) and t_min >= 0):
        raise CamError(f"t_min sonlu ve ≥ 0 olmalı ({t_min})")
    t = np.asarray(t, dtype=float)
    if t.shape != (state.ny, state.nx):
        raise CamError(f"t şekli ızgarayla uyuşmuyor ({t.shape} ≠ {(state.ny, state.nx)})")
    etiket, n = ndimage.label(t > t_min, structure=np.ones((3, 3), dtype=int))
    top = _top(state)
    bolgeler: list[tuple[float, int, RestRegion]] = []
    for k in range(1, n + 1):
        jj, ii = np.nonzero(etiket == k)  # satır sırası: c = j·nx + i artan
        c = jj * state.nx + ii
        tk = t[jj, ii]
        m = int(np.flatnonzero(tk == tk.max())[0])  # eşitlikte en küçük c
        i_m, j_m = int(ii[m]), int(jj[m])
        V = float(tk.sum() * state.dx * state.dy)
        reg = RestRegion(
            cells=np.column_stack([ii, jj]),
            volume=V,
            t_max=float(tk[m]),
            at=(
                state.x0 + (i_m + 0.5) * state.dx,
                state.y0 + (j_m + 0.5) * state.dy,
                float(top[j_m, i_m]),
            ),
            bbox=(
                state.x0 + ii.min() * state.dx,
                state.x0 + (ii.max() + 1) * state.dx,
                state.y0 + jj.min() * state.dy,
                state.y0 + (jj.max() + 1) * state.dy,
            ),
        )
        bolgeler.append((V, int(c.min()), reg))
    bolgeler.sort(key=lambda b: (-b[0], b[1]))
    return [b[2] for b in bolgeler]


# ---------------------------------------------------------------- girme ve süzgeç


def engagement(
    tool: Tool, p0: tuple[float, float, float], move: Move, state: State, arc_tol: float = 1e-3
) -> float:
    """Hareketin durumdan kaldıracağı en büyük hücre boyu g_k [mm]; durum değişmez."""
    _check_state(state)
    _check_tool(tool)
    if not (math.isfinite(arc_tol) and arc_tol > 0):
        raise CamError(f"arc_tol pozitif olmalı ({arc_tol})")
    gk, _, _ = _Saha(state.copy(), tool, arc_tol).uygula(p0, move)
    return gk


@dataclass
class RestPath:
    """Süzgeç sonucu: süzülmüş yol (yoksa None), son durum, tutulan hareket indeksleri, kaldırılan hacim."""

    toolpath: Toolpath | None
    state: State
    kept: list[int]
    removed: float


def _G0(x: float, y: float, z: float) -> Move:
    return Move(MoveType.RAPID, (x, y, z))


def rest_filter(
    path: Toolpath,
    state: State,
    t_min: float = 0.02,
    z_safe: float | None = None,
    clearance: float = 1.0,
    plunge_feed: float | None = None,
    arc_tol: float = 1e-3,
) -> RestPath:
    """Sıralı kalan malzeme süzgeci (SPEC 39 Teori)."""
    _check_state(state)
    if not isinstance(path, Toolpath):
        raise CamError(f"Süzgeç bir Toolpath ister ({type(path).__name__})")
    _check_tool(path.tool)
    if path.plane is not Plane.XY:
        raise CamError("Kalan malzeme süzgeci yalnız XY (G17) yolları işler")
    if path.feed_mode is not FeedMode.PER_MIN:
        raise CamError("Kalan malzeme süzgeci yalnız mm/dk (G94) ilerleme kabul eder")
    path.validate()
    for ad, v in (("t_min", t_min), ("clearance", clearance)):
        if not (math.isfinite(v) and v >= 0):
            raise CamError(f"{ad} sonlu ve ≥ 0 olmalı ({v})")
    if not (math.isfinite(arc_tol) and arc_tol > 0):
        raise CamError(f"arc_tol pozitif olmalı ({arc_tol})")
    if z_safe is None:
        z_safe = path.start[2]
    if not (math.isfinite(z_safe) and z_safe > state.zmax):
        raise CamError(f"z_safe stok üstünün (zmax = {state.zmax}) üstünde olmalı ({z_safe})")
    if plunge_feed is None:
        plunge_feed = next((m.feed for m in path.moves if m.type is MoveType.LINEAR and m.feed), None)
        if plunge_feed is None:
            raise CamError("plunge_feed verilmedi ve yolda G1 ilerlemesi yok")
    if not (math.isfinite(plunge_feed) and plunge_feed > 0):
        raise CamError(f"plunge_feed pozitif olmalı ({plunge_feed})")

    S = state.copy()
    saha = _Saha(S, path.tool, arc_tol)
    kept: list[int] = []
    out: list[Move] = []
    bas: tuple[float, float, float] | None = None
    son: tuple[float, float, float] | None = None  # son tutulan hareketin bitişi
    p0 = path.start
    for k, m in enumerate(path.moves):
        if m.type in KESME:
            C = tuple(float(v) for v in p0)
            yeni_kosu = son is None or max(abs(a - b) for a, b in zip(C, son, strict=True)) > 1e-9
            zy = saha.z_yak(C, z_safe, clearance) if yeni_kosu else None
            gk, W, kayit = saha.uygula(p0, m)
            if gk > t_min:
                kept.append(k)
                if yeni_kosu:
                    if son is None:
                        bas = (C[0], C[1], z_safe)
                    else:
                        if son[2] != z_safe:
                            out.append(_G0(son[0], son[1], z_safe))
                        out.append(_G0(C[0], C[1], z_safe))
                    if zy < z_safe:
                        out.append(_G0(C[0], C[1], zy))
                    if C[2] < zy:
                        out.append(Move(MoveType.LINEAR, C, plunge_feed))
                out.append(Move(m.type, m.end, m.feed, m.center))
                son = m.end
            elif W is not None:
                saha.geri_al(W, kayit)
        p0 = m.end
    removed = state.volume() - S.volume()
    if not kept:
        return RestPath(None, S, [], 0.0)
    if son[2] != z_safe:
        out.append(_G0(son[0], son[1], z_safe))
    tp = Toolpath(
        f"{path.name} (kalan)",
        path.tool,
        bas,
        out,
        path.rpm,
        plane=path.plane,
        feed_mode=path.feed_mode,
        css=path.css,
    )
    tp.validate()
    return RestPath(tp, S, kept, removed)


# ---------------------------------------------------------------- SPEC 06 yolları üstünde


def rest_finish(
    mesh: TriMesh,
    tool: Tool,
    r: Raster,
    state: State,
    t_min: float = 0.02,
    floor: float | None = None,
) -> RestPath:
    """SPEC 06 finish yolu + kalan malzeme süzgeci."""
    _check_tool(tool)
    yol = finish(mesh, tool, r, floor)
    return rest_filter(yol, state, t_min, r.z_safe, r.clearance, r.plunge_feed)


def rest_rough(
    mesh: TriMesh,
    stock: Stock,
    tool: Tool,
    r: Raster,
    a_p: float,
    z_bottom: float,
    state: State,
    allowance: float = 0.0,
    t_min: float = 0.02,
) -> RestPath:
    """SPEC 06 rough yolu + kalan malzeme süzgeci."""
    _check_state(state)
    _check_tool(tool)
    if not isinstance(stock, Stock):
        raise CamError(f"rest_rough kutu stok ister ({type(stock).__name__})")
    ayni = (
        state.x0 == stock.xmin
        and state.y0 == stock.ymin
        and state.zmin == stock.zmin
        and state.zmax == stock.zmax
        and abs(state.x0 + state.nx * state.dx - stock.xmax) <= 1e-9
        and abs(state.y0 + state.ny * state.dy - stock.ymax) <= 1e-9
    )
    if not ayni:
        raise CamError("Durumun ızgarası stok sınırlarıyla uyuşmuyor")
    yol = rough(mesh, stock, tool, r, a_p, z_bottom, allowance)
    return rest_filter(yol, state, t_min, r.z_safe, r.clearance, r.plunge_feed)
