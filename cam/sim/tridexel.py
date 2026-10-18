"""
SPEC 43 — Tri-dexel: X, Y ve Z yönündeki üç dik ışın ailesi; her ışında SPEC 05 aralık listesi.

Z ışınları XY hücre merkezlerinden (05 ile aynı ızgara), X ışınları YZ, Y ışınları XZ hücre merkezlerinden.
Hacim her aileden ayrı: V_z = Σ (u − l)·dx·dy, V_x = Σ (u − l)·dy·dz, V_y = Σ (u − l)·dx·dz;
rapor edilen V = (V_x + V_y + V_z)/3.

Işın–takım kesişimi takım çerçevesinde (uç orijinde, eksen +z): kesen kısım dışbükey dönel cisim
{ d ≤ R, h(d) ≤ w ≤ L_f }, gövde SPEC 05 basamakları (ρ_j, H_j).

Süpürme (s, t) düzleminde çözülür: ışın Y(s) = o + s·v, uç p(t) = p₀ + t·u, göreli nokta X = Y(s) − p(t)
(s ve t'de afin). Takım parçaları (silindir, kesik koni, küre) X'te ikinci derece kısıt + w = X·a'da
yarı düzlemlerdir; dolayısıyla her parça (s, t)'de bir konik ∩ yarı düzlemler kümesidir. Doğrusal s'nin
dışbükey küme üzerindeki en küçük / en büyük değeri şu adaylardan birindedir:
    (a) konik üzerinde ∂Q/∂t = 0 noktaları, (b) konik ∩ sınır doğruları, (c) iki sınır doğrusunun kesişimi.
Adaylar uygunluk denetiminden geçirilir; parça aralıklarının zarfı süpürülen kümenin ışın aralığıdır
(takım dışbükey olduğundan süpürme de dışbükeydir).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from cam.model import CamError, Stock, Tool
from cam.sim.dexel import DexelMap
from cam.sim.sweep import _radii, body_steps
from cam.sim.zmap import ZMap

AXES = ("x", "y", "z")
# aile → (ışın ekseni, dexel'in "x" ve "y" olarak kullandığı dünya eksenleri)
FAMILY = {"x": (0, 1, 2), "y": (1, 0, 2), "z": (2, 0, 1)}
_EPS_DEJ = 1e-12  # konik katsayılarında sıfır sayma (göreli)


# ---------------------------------------------------------------- ızgara


@dataclass
class TriDexel:
    x0: float
    y0: float
    z0: float
    dx: float
    dy: float
    dz: float
    nx: int
    ny: int
    nz: int
    maps: dict[str, DexelMap] = field(default_factory=dict, repr=False)

    @classmethod
    def from_stock(cls, stock: Stock, cell: float, max_rays: int = 3_000_000) -> TriDexel:
        """Her ışında stok boyunca tek aralık."""
        if not isinstance(stock, Stock):
            raise CamError(f"Tri-dexel yalnız kutu stokla kurulur ({type(stock).__name__})")
        if isinstance(cell, bool) or not (isinstance(cell, int | float) and math.isfinite(cell) and cell > 0):
            raise CamError(f"Hücre boyu pozitif ve sonlu olmalı (cell={cell})")
        lo = (float(stock.xmin), float(stock.ymin), float(stock.zmin))
        hi = (float(stock.xmax), float(stock.ymax), float(stock.zmax))
        n = [max(1, math.ceil((b - a) / cell - 1e-12)) for a, b in zip(lo, hi, strict=True)]
        nx, ny, nz = n
        isin = nx * ny + ny * nz + nx * nz
        if isin > max_rays:
            raise CamError(f"Tri-dexel çok büyük: {isin} ışın > {max_rays} (hücreyi büyütün)")
        d = [(b - a) / k for a, b, k in zip(lo, hi, n, strict=True)]
        td = cls(*lo, *d, nx, ny, nz)
        for ad, (ax, i1, i2) in FAMILY.items():
            shape = (n[i2], n[i1], 1)
            td.maps[ad] = DexelMap(
                lo[i1], lo[i2], d[i1], d[i2], n[i1], n[i2], lo[ax], hi[ax],
                np.full(shape, lo[ax]), np.full(shape, hi[ax]),
            )  # fmt: skip
        return td

    def _map(self, axis: str) -> DexelMap:
        if axis not in AXES:
            raise CamError(f"Tri-dexel: eksen 'x', 'y' veya 'z' olmalı ({axis!r})")
        return self.maps[axis]

    def intervals(self, axis: str, i: int, j: int) -> list[tuple[float, float]]:
        """axis ∈ {"x", "y", "z"}: Z için (i, j) = (x, y) hücresi, X için (y, z), Y için (x, z)."""
        return self._map(axis).intervals(i, j)

    def volumes(self) -> tuple[float, float, float]:
        """(V_x, V_y, V_z)"""
        return tuple(self.maps[a].volume() for a in AXES)

    def volume(self) -> float:
        """V = (V_x + V_y + V_z)/3"""
        return sum(self.volumes()) / 3

    def copy(self) -> TriDexel:
        td = TriDexel(self.x0, self.y0, self.z0, self.dx, self.dy, self.dz, self.nx, self.ny, self.nz)
        td.maps = {a: m.copy() for a, m in self.maps.items()}
        return td

    def bounds(self) -> tuple[np.ndarray, np.ndarray]:
        """Stok kutusu (alt köşe, üst köşe)."""
        lo = np.array([self.x0, self.y0, self.z0])
        return lo, lo + np.array([self.nx * self.dx, self.ny * self.dy, self.nz * self.dz])

    def grid(self, axis: str) -> ZMap:
        """Ailenin ışın ızgarası (pencere ve merkez hesabı için; z alanı kullanılmaz)."""
        m = self._map(axis)
        return ZMap(m.x0, m.y0, m.dx, m.dy, m.nx, m.ny, m.zmin, m.zmax, None)


# ---------------------------------------------------------------- takım parçaları


@dataclass(frozen=True)
class _Cone:
    """Kesik koni (r_a = r_b → silindir): w_a..w_b arasında r(w) doğrusal; geçerli w ∈ [w_lo, w_hi]."""

    r_a: float
    w_a: float
    r_b: float
    w_b: float
    w_lo: float
    w_hi: float


@dataclass(frozen=True)
class _Sphere:
    """Eksen üzerinde h yüksekliğinde merkezli ρ yarıçaplı küre; w ≤ w_hi."""

    h: float
    rho: float
    w_hi: float


def _cyl(r: float, w_lo: float, w_hi: float) -> _Cone:
    return _Cone(r, 0.0, r, 1.0, w_lo, w_hi)


def cutter_pieces(tool: Tool, arc_tol: float = 1e-3) -> list:
    """Kesen kısmın dışbükey parçaları; birleşimleri (zarfları) kesen kısımdır.

    düz: silindir R · küresel: silindir (w ≥ R) + küre · köşe radyüslü: dış silindir (w ≥ r_c), iç silindir
    (R − r_c) ve köşe yayının kirişleriyle kesik koniler (kiriş sapması ≤ arc_tol, içten yaklaşım).
    """
    R, rc = _radii(tool)
    Lf = float(tool.flute_length)
    if rc <= 0:
        return [_cyl(R, 0.0, Lf)]
    parcalar = []
    if Lf > rc:
        parcalar.append(_cyl(R, rc, Lf))
    if rc >= R - 1e-12:
        parcalar.append(_Sphere(R, R, Lf))
        return parcalar
    Rc = R - rc
    parcalar.append(_cyl(Rc, 0.0, Lf))
    adim = 2 * math.acos(1 - arc_tol / rc) if arc_tol < rc else math.pi / 2
    n = max(1, math.ceil((math.pi / 2) / adim - 1e-12))
    phi = np.linspace(0.0, math.pi / 2, n + 1)
    r = Rc + rc * np.sin(phi)
    w = rc - rc * np.cos(phi)
    for k in range(n):
        if w[k] >= Lf:
            break
        parcalar.append(_Cone(r[k], w[k], r[k + 1], w[k + 1], w[k], min(w[k + 1], Lf)))
    return parcalar


def body_pieces(tool: Tool, w_cap: float) -> list[tuple[_Cone, str]]:
    """Gövde basamakları: d ≤ ρ_j, H_j ≤ w ≤ H_{j+1}; sonuncusu sonsuz, w_cap'te kesilir."""
    st = body_steps(tool)
    out = []
    for j, (rho, H, tur) in enumerate(st):
        H2 = st[j + 1][1] if j + 1 < len(st) else max(w_cap, H)
        out.append((_cyl(rho, H, H2), tur))
    return out


def piece_rmax(p) -> float:
    return p.rho if isinstance(p, _Sphere) else max(p.r_a, p.r_b)


def piece_wrange(p) -> tuple[float, float]:
    if isinstance(p, _Sphere):
        return p.h - p.rho, min(p.h + p.rho, p.w_hi)
    return p.w_lo, p.w_hi


# ---------------------------------------------------------------- konik çözücü


def _roots(a, b, c, small):
    """a x² + b x + c = 0 kökleri (x1, x2); small → doğrusal (tek kök); kök yoksa nan."""
    a, b, c = np.broadcast_arrays(np.asarray(a, float), np.asarray(b, float), np.asarray(c, float))
    small = np.broadcast_to(small, a.shape)
    with np.errstate(divide="ignore", invalid="ignore", over="ignore"):
        disc = b * b - 4 * a * c
        ref = b * b + np.abs(4 * a * c)
        disc = np.where((disc < 0) & (disc > -1e-12 * ref), 0.0, disc)
        sq = np.sqrt(np.where(disc >= 0, disc, np.nan))
        q = -0.5 * (b + np.copysign(sq, b))
        x1 = np.where(q == 0, 0.0, q / a)
        x2 = np.where(q == 0, 0.0, c / q)
        lin = np.where(b != 0, -c / b, np.nan)
    x1 = np.where(small, lin, x1)
    x2 = np.where(small, np.nan, x2)
    return x1, x2


def _conic(p, Q0: np.ndarray, V: np.ndarray, U: np.ndarray, a: np.ndarray):
    """Parçanın Q(s, t) = A_ss s² + 2A_st st + A_tt t² + 2b_s s + 2b_t t + c katsayıları, yarı düzlemler."""
    Q0a = Q0 @ a
    Va = float(V @ a)
    Ua = float(U @ a)
    if isinstance(p, _Sphere):
        D = Q0 - p.h * a
        Ass, Ast, Att = float(V @ V), -float(V @ U), float(U @ U)
        bs, bt, c = D @ V, -(D @ U), np.einsum("ij,ij->i", D, D) - p.rho**2
        w_lo, w_hi = -math.inf, p.w_hi
    else:
        k = (p.r_b - p.r_a) / (p.w_b - p.w_a)
        Q0p = Q0 - Q0a[:, None] * a
        Vp = V - Va * a
        Up = U - Ua * a
        m0 = p.r_a + k * (Q0a - p.w_a)
        ms, mt = k * Va, k * Ua
        Ass = float(Vp @ Vp) - ms * ms
        Ast = -float(Vp @ Up) + ms * mt
        Att = float(Up @ Up) - mt * mt
        bs = Q0p @ Vp - m0 * ms
        bt = -(Q0p @ Up) + m0 * mt
        c = np.einsum("ij,ij->i", Q0p, Q0p) - m0 * m0
        w_lo, w_hi = p.w_lo, p.w_hi
    lines = [(0.0, -1.0, np.zeros_like(Q0a)), (0.0, 1.0, np.ones_like(Q0a))]
    if math.isfinite(w_hi):
        lines.append((Va, -Ua, w_hi - Q0a))
    if math.isfinite(w_lo):
        lines.append((-Va, Ua, Q0a - w_lo))
    return (Ass, Ast, Att, bs, bt, c), lines


def _solve(coef, lines, tolQ: float):
    """min s ve max s: {Q ≤ 0} ∩ {α s + β t ≤ γ}; boş küme → (inf, −inf)."""
    Ass, Ast, Att, bs, bt, c = coef
    N = c.shape[0]
    olcek = abs(Ass) + abs(Ast) + abs(Att) + 1e-300
    cand_s: list[np.ndarray] = []
    cand_t: list[np.ndarray] = []

    def Q(s, t):
        return Ass * s * s + 2 * Ast * s * t + Att * t * t + 2 * bs * s + 2 * bt * t + c

    # (a) ∂Q/∂t = 0 → t = −(A_st s + b_t)/A_tt
    if abs(Att) > _EPS_DEJ * olcek:
        lead = Ass * Att - Ast * Ast
        small = abs(lead) <= _EPS_DEJ * olcek * olcek
        for s in _roots(np.full(N, lead), 2 * (bs * Att - Ast * bt), c * Att - bt * bt, small):
            cand_s.append(s)
            cand_t.append(-(Ast * s + bt) / Att)
    # (b) konik ∩ doğrular
    for al, be, ga in lines:
        if al == 0 and be == 0:  # ışın başına sabit kısıt: yalnız uygunlukta
            continue
        if abs(be) >= abs(al):
            g0, g1 = ga / be, -al / be
            A2 = Ass + 2 * Ast * g1 + Att * g1 * g1
            A1 = 2 * (Ast * g0 + Att * g0 * g1 + bs + bt * g1)
            A0 = Att * g0 * g0 + 2 * bt * g0 + c
            small = abs(A2) <= _EPS_DEJ * olcek * (1 + g1 * g1)
            for s in _roots(np.full(N, A2), A1, A0, small):
                cand_s.append(s)
                cand_t.append(g0 + g1 * s)
        else:
            h0, h1 = ga / al, -be / al
            A2 = Ass * h1 * h1 + 2 * Ast * h1 + Att
            A1 = 2 * (Ass * h0 * h1 + Ast * h0 + bs * h1 + bt)
            A0 = Ass * h0 * h0 + 2 * bs * h0 + c
            small = abs(A2) <= _EPS_DEJ * olcek * (1 + h1 * h1)
            for t in _roots(np.full(N, A2), A1, A0, small):
                cand_s.append(h0 + h1 * t)
                cand_t.append(t)
    # (c) doğru ∩ doğru
    for i in range(len(lines)):
        a1, b1, g1_ = lines[i]
        for j in range(i + 1, len(lines)):
            a2, b2, g2_ = lines[j]
            det = a1 * b2 - a2 * b1
            if abs(det) <= 1e-14 * (abs(a1) + abs(b1)) * (abs(a2) + abs(b2)):
                continue
            cand_s.append((g1_ * b2 - g2_ * b1) / det)
            cand_t.append((a1 * g2_ - a2 * g1_) / det)
    S = np.array(cand_s)
    T = np.array(cand_t)
    with np.errstate(invalid="ignore", over="ignore"):
        ok = np.isfinite(S) & np.isfinite(T) & (Q(S, T) <= tolQ)
        for al, be, ga in lines:
            ok &= al * S + be * T - ga <= 1e-9 * (1 + np.abs(ga))
    smin = np.where(ok, S, np.inf).min(axis=0)
    smax = np.where(ok, S, -np.inf).max(axis=0)
    return smin, smax


def piece_interval(p, Q0, V, U, a) -> tuple[np.ndarray, np.ndarray]:
    """Parçanın p₀ → p₀ + U süpürmesinin ışınlarla (Q0 = o − p₀, yön V) kesişimi (s_min, s_max)."""
    coef, lines = _conic(p, Q0, V, U, a)
    r = piece_rmax(p)
    return _solve(coef, lines, 1e-9 * (1.0 + r * r))


def sweep_interval(pieces, Q0, V, U, a) -> tuple[np.ndarray, np.ndarray]:
    """Parçalar zarfı: dışbükey takımın süpürmesi tek aralıktır."""
    smin = np.full(Q0.shape[0], np.inf)
    smax = np.full(Q0.shape[0], -np.inf)
    for p in pieces:
        a_, b_ = piece_interval(p, Q0, V, U, a)
        smin = np.minimum(smin, a_)
        smax = np.maximum(smax, b_)
    return smin, smax


# ---------------------------------------------------------------- tek ışın, sabit takım


def _vec3(nerede: str, v) -> np.ndarray:
    try:
        v = np.asarray(v, dtype=float)
    except (TypeError, ValueError) as e:
        raise CamError(f"{nerede}: 3 bileşenli sonlu vektör olmalı ({v!r})") from e
    if v.shape != (3,) or not np.all(np.isfinite(v)):
        raise CamError(f"{nerede}: 3 bileşenli sonlu vektör olmalı ({v})")
    return v


def unit_axis(nerede: str, a) -> np.ndarray:
    a = _vec3(nerede, a)
    if abs(float(np.linalg.norm(a)) - 1.0) > 1e-9:
        raise CamError(f"{nerede}: takım ekseni birim vektör olmalı (|a| = {np.linalg.norm(a)})")
    return a


def _torus_points(tool: Tool, Q0: np.ndarray, V: np.ndarray, a: np.ndarray) -> list[float]:
    """Köşe radyüslü takımın tor tüpü ∩ {w ≤ L_f} sınırındaki ışın noktaları (dördüncü derece, kesin)."""
    R, rc = _radii(tool)
    Rc = R - rc
    Lf = float(tool.flute_length)
    Y0 = Q0 - rc * a
    A2, A1, A0 = float(V @ V), 2 * float(Y0 @ V), float(Y0 @ Y0)
    va, y0a = float(V @ a), float(Y0 @ a)
    K = Rc * Rc - rc * rc
    P = np.array([
        A2 * A2,
        2 * A2 * A1,
        A1 * A1 + 2 * A2 * (A0 + K) - 4 * Rc * Rc * (A2 - va * va),
        2 * A1 * (A0 + K) - 4 * Rc * Rc * (A1 - 2 * y0a * va),
        (A0 + K) ** 2 - 4 * Rc * Rc * (A0 - y0a * y0a),
    ])  # fmt: skip
    dP = np.polyder(P)
    pts = []
    olcek = 1.0 + abs(A0) ** 0.5 + R
    for r in np.roots(P):
        if abs(r.imag) > 1e-6 * olcek:
            continue
        s = float(r.real)
        for _ in range(6):  # Newton ile cilala
            d = np.polyval(dP, s)
            if d == 0:
                break
            s -= np.polyval(P, s) / d
        if Q0 @ a + s * va <= Lf + 1e-12:
            pts.append(s)
    if abs(va) > 0:  # w = L_f düzlemi tüpün içinden geçiyorsa
        s = (Lf - Q0 @ a) / va
        Y = Y0 + s * V
        ya = float(Y @ a)
        rp = float(np.linalg.norm(Y - ya * a))
        if (rp - Rc) ** 2 + ya * ya <= rc * rc * (1 + 1e-12):
            pts.append(float(s))
    return pts


def ray_tool(tool: Tool, origin, direction, tip, axis, part: str = "kesen") -> tuple[float, float] | None:
    """Işın origin + s·direction ile takım katısının kesişimi [s_giriş, s_çıkış]; kesişim yoksa None.

    part = "kesen": kesen kısım (kesin; köşe radyüsünde tor dördüncü derece denklemle);
    part = "govde": gövde basamakları, en uzun (en derin) basamak kesişimi.
    """
    if not isinstance(tool, Tool):
        raise CamError(f"ray_tool: freze takımı bekleniyor ({type(tool).__name__})")
    o = _vec3("ray_tool: origin", origin)
    v = _vec3("ray_tool: direction", direction)
    if not np.linalg.norm(v) > 0:
        raise CamError("ray_tool: ışın yönü sıfır olamaz")
    p = _vec3("ray_tool: tip", tip)
    a = unit_axis("ray_tool", axis)
    Q0 = (o - p)[None, :]
    U = np.zeros(3)
    if part == "kesen":
        R, rc = _radii(tool)
        if 0 < rc < R - 1e-12:
            Lf = float(tool.flute_length)
            pieces = [_cyl(R - rc, 0.0, Lf)] + ([_cyl(R, rc, Lf)] if Lf > rc else [])
            s0, s1 = sweep_interval(pieces, Q0, v, U, a)
            pts = [float(s0[0]), float(s1[0])] + _torus_points(tool, Q0[0], v, a)
            pts = [s for s in pts if math.isfinite(s)]
            return (min(pts), max(pts)) if pts else None
        s0, s1 = sweep_interval(cutter_pieces(tool), Q0, v, U, a)
        if not s0[0] <= s1[0]:
            return None
        return float(s0[0]), float(s1[0])
    if part == "govde":
        best = None
        cap = 1e12
        for p_, _ in body_pieces(tool, cap):
            s0, s1 = piece_interval(p_, Q0, v, U, a)
            if s0[0] <= s1[0] and (best is None or s1[0] - s0[0] > best[1] - best[0]):
                best = (float(s0[0]), float(s1[0]))
        if best is None:
            return None
        # sonsuz basamağın kesme düzlemine varan uç → sonsuz
        uzak = cap * 1e-3 / float(np.linalg.norm(v))
        return tuple(math.copysign(math.inf, s) if abs(s) > uzak else s for s in best)
    raise CamError(f"ray_tool: part 'kesen' veya 'govde' olmalı ({part!r})")
