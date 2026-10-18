"""
SPEC 52 — Diş ve helis simülasyonu: senkron helis süpürmesi (torna G32/G95 pasoları, kılavuz G84)
ve diş frezeleme zarfı (senkronsuz helis).

Senkron kesim: θ(z) = θ₀ + 360°·(z − z₀)/P; hücre (θ, z) için
z_c(θ) = z₀ + P·(θ − θ₀)/360° + k·P (en yakın k),
dış diş r_dış ← min(r_dış, r_profil(z − z_c)), iç diş r_iç ← max(r_iç, r_profil(z − z_c)).

Yön kuralı (sağ helis = z, θ ile artar): iş mili M3 dönerken takım −z'ye ilerleyince sağ helis çıkar. Parçanın
θ açısında, pasonun z_start'tan |z − z_start|/L tur sonra geçtiği nokta z_c = z_start − s·L·θ/360 + s·L·m
(s = sign(z_end − z_start), m tam sayı; konum pasonun z aralığında). Her paso iş milinin aynı açısında başlar;
çok ağızda (starts = n) her paso n kez, θ₀ + j·360°/n ile uygulanır.

Diş frezeleme: takım dönel zarftır, R(w) profil düzleminden eksenel uzaklığa göre yarıçap. θ ışınında
c merkezli takımın ulaştığı yarıçap c·u ± √(R² − |c|² + (c·u)²). Harita eksenine oturan helis yaylarında
(merkez eksende, z açıyla doğrusal) etki yalnız helisel koordinata bağlıdır: hücre (θ, z), tur k için
s = z − z(θ + 2πk) ve E(s) = max_Δ G(Δ, s + p·Δ/2π) (Δ = θ − φ, p tur başına ilerleme). E ve en iyi Δ ince
s ızgarasında (0.25° Δ ızgarası, sonra altın oran araması; Δφ ≤ Δθ/2 örneklemesinden daha kesin) bir kez
hesaplanır; yay uçlarının dışına düşen en iyi konumda uçtaki konum doğrudan hesaplanır. Diğer kesme
hareketleri Δφ ≤ Δθ/2 adımla örneklenir.
"""

from __future__ import annotations

import math

import numpy as np

from cam.lathe import tip_offset
from cam.model import (
    ARCS,
    CamError,
    FeedMode,
    Frame,
    LatheTool,
    LatheToolKind,
    Move,
    MoveType,
    Tool,
    ToolKind,
    Toolpath,
)
from cam.sim.lathe_shape import cutter_shape, rounded_interval
from cam.sim.polar import PolarMap
from cam.thread_mill import ThreadMillForm, ThreadMillTool

TOL = 1e-9  # mm, eksen / doğrultu denetimi
GOLD = (math.sqrt(5) - 1) / 2


def simulate_thread(
    ops: list[Toolpath], initial: PolarMap, frame: Frame | None = None, starts: int = 1
) -> PolarMap:
    """G32/G95 torna pasoları (feed = P), G84 kılavuz, thread_mill helisi.

    Başka yol → CamError ("diş yolu değil").

    initial kopyalanır, değiştirilmez. starts: diş ağız sayısı (≥ 1).
    frame: harita ekseninin (yerel z) çerçevesi; yalnız freze takımlarında (kılavuz, diş frezesi) kullanılır,
    torna yolu makine z ekseni etrafındadır.
    """
    if not isinstance(initial, PolarMap):
        raise CamError(f"simulate_thread: initial PolarMap olmalı ({type(initial).__name__})")
    if isinstance(starts, bool) or not isinstance(starts, int) or starts < 1:
        raise CamError(f"simulate_thread: ağız sayısı ≥ 1 tam sayı olmalı (starts={starts!r})")
    if frame is not None and not isinstance(frame, Frame):
        raise CamError(f"simulate_thread: frame Frame olmalı ({type(frame).__name__})")
    ops = list(ops)
    if not ops:
        raise CamError("simulate_thread: yol listesi boş")
    m = initial.copy()
    for tp in ops:
        if not isinstance(tp, Toolpath):
            raise CamError(f"simulate_thread: diş yolu değil ({type(tp).__name__})")
        tp.validate()
        if isinstance(tp.tool, LatheTool):
            _lathe(tp, m, starts)
        elif isinstance(tp.tool, ThreadMillTool) and tp.tool.form is not None:
            _mill(tp, m, frame)
        elif isinstance(tp.tool, Tool) and tp.tool.kind is ToolKind.TAP:
            _tap(tp, m, frame, starts)
        else:
            raise CamError(f"Yol '{tp.name}': diş yolu değil (torna diş pasosu, kılavuz veya diş frezesi)")
    return m


# ---------------------------------------------------------------- ortak


def _z_check(tp: Toolpath, m: PolarMap, z) -> None:
    z = np.asarray(z, dtype=float)
    if z.size and (z.min() < m.z0 - TOL or z.max() > m.z1 + TOL):
        raise CamError(
            f"Yol '{tp.name}': kesen konum haritanın dışında (z ∈ [{z.min()}, {z.max()}], "
            f"harita [{m.z0}, {m.z1}])"
        )


def _apply(m: PolarMap, cut: np.ndarray, side: str, rows=slice(None), cols=slice(None)) -> None:
    """Dış: r_dış ← max(r_iç, min(r_dış, cut)); iç: r_iç ← min(r_dış, max(r_iç, cut)). cut ±inf = etkisiz."""
    if side == "dis":
        m.r_out[rows, cols] = np.maximum(m.r_in[rows, cols], np.minimum(m.r_out[rows, cols], cut))
    else:
        m.r_in[rows, cols] = np.minimum(m.r_out[rows, cols], np.maximum(m.r_in[rows, cols], cut))


def _to_map(tp: Toolpath, frame: Frame | None, p) -> np.ndarray:
    """Yolun noktaları (tp.frame yerel) → harita yereli."""
    p = np.asarray(p, dtype=float)
    if tp.frame is not None:
        p = tp.frame.to_world(p)
    if frame is not None:
        p = frame.to_local(p)
    return p


def _vec_to_map(tp: Toolpath, frame: Frame | None, v) -> np.ndarray:
    v = np.asarray(v, dtype=float)
    if tp.frame is not None:
        v = tp.frame.to_world_vec(v)
    if frame is not None:
        v = frame.to_local_vec(v)
    return v


def _side_of(tp: Toolpath, m: PolarMap) -> str:
    """Taraf (SPEC 22 kuralı): yolun ilk x ≥ stok dış yarıçapı → dış; x ≤ delik yarıçapı → iç."""
    R = float(np.max(m.r_out))
    r = float(np.min(m.r_in))
    for x in tp.points()[:, 0]:
        if x >= R:
            return "dis"
        if r > 0 and x <= r:
            return "ic"
    raise CamError(f"Yol '{tp.name}': taraf belirlenemiyor (hiçbir nokta stok dışında / delik içinde değil)")


# ---------------------------------------------------------------- torna diş pasoları


def _lathe(tp: Toolpath, m: PolarMap, starts: int) -> None:
    tool = tp.tool
    if tool.kind is not LatheToolKind.THREAD:
        raise CamError(f"Yol '{tp.name}': diş yolu değil (takım {tool.kind.value}, diş kalemi gerekir)")
    if tp.feed_mode is not FeedMode.PER_REV:
        raise CamError(f"Yol '{tp.name}': torna diş pasosu G95 (mm/dev) olmalı")
    side = _side_of(tp, m)
    shape = cutter_shape(tool, side)
    q = tip_offset(tool.tip, tool.nose_r)  # (z, x)
    passes = []
    p0 = np.array(tp.start, dtype=float)
    for mv in tp.moves:
        p1 = np.array(mv.end, dtype=float)
        if mv.type in ARCS:
            raise CamError(f"Yol '{tp.name}': diş yolu değil (diş pasosunda yay olmaz)")
        if mv.type is MoveType.LINEAR:
            if abs(p1[0] - p0[0]) > TOL or abs(p1[2] - p0[2]) <= TOL:
                raise CamError(f"Yol '{tp.name}': diş yolu değil (diş pasosu z eksenine paralel olmalı)")
            # Burun merkezi C = P − q_T
            passes.append((p0[2] - q[0], p1[2] - q[0], p0[0] - q[1], float(mv.feed)))
        p0 = p1
    if not passes:
        raise CamError(f"Yol '{tp.name}': diş yolu değil (kesme pasosu yok)")
    _z_check(tp, m, [v for p in passes for v in p[:2]])
    th = m.thetas()
    polys = [(shape.core, shape.r), (shape.body, shape.r)]
    dis = side == "dis"

    def kesim(u: np.ndarray) -> np.ndarray:
        """Burun merkezine göre kesici sınırı: dış alt uç a(u), iç üst uç b(u); kesmezse ±inf."""
        a = np.full(u.size, math.inf)
        b = np.full(u.size, -math.inf)
        for poly, r in polys:
            aa, bb = rounded_interval(poly, r, u.ravel())
            a, b = np.minimum(a, aa), np.maximum(b, bb)
        return (a if dis else b).reshape(u.shape)

    sinir = float(np.max(m.r_out)) if dis else float(np.min(m.r_in))
    for zs, ze, xc, L in passes:
        # Malzemeye değebilen kesici bandı |u| ≤ U (dz/4 adımla taranır, bir hücre pay)
        ug = np.arange(-50.0, 50.0 + m.dz / 8, m.dz / 4)
        etkin = (xc + kesim(ug) < sinir) if dis else (xc + kesim(ug) > sinir)
        if not etkin.any():
            continue
        U = float(np.max(np.abs(ug[etkin]))) + m.dz
        nb = int(math.ceil(2 * U / m.dz)) + 2
        s = 1.0 if ze > zs else -1.0
        n_rev = abs(ze - zs) / L
        for j in range(starts):
            # Parçanın θ açısında pasonun geçtiği turlar: n = mm − θ'/360 ∈ [0, n_rev]
            tq = (th - j * 360.0 / starts) % 360.0
            for mm in range(0, math.floor(n_rev) + 2):
                n = mm - tq / 360.0
                ok = (n >= -TOL) & (n <= n_rev + TOL)
                if not ok.any():
                    continue
                rows = np.nonzero(ok)[0]
                z_c = zs + s * L * n[ok]
                i0 = np.floor((z_c - U - m.z0) / m.dz).astype(int)
                idx = i0[:, None] + np.arange(nb)[None, :]
                ic_ = (idx >= 0) & (idx < m.n_z)
                rr = np.broadcast_to(rows[:, None], idx.shape)[ic_]
                ii = idx[ic_]
                u = m.z0 + (ii + 0.5) * m.dz - np.broadcast_to(z_c[:, None], idx.shape)[ic_]
                _apply(m, xc + kesim(u), side, rr, ii)


# ---------------------------------------------------------------- kılavuz (G84)


def _tap(tp: Toolpath, m: PolarMap, frame: Frame | None, starts: int) -> None:
    """Kılavuz profili (ISO 68-1 iç diş, temel profil): R(u) = min(D/2, D/2 + H/8 − √3·|sar(u)|);
    giriş pahında (uçtan lead·P boyunca) yarıçap D₁/2'den D/2'ye doğrusal. Kılavuz senkron helis üzerinde
    gidip döndüğü için hücrenin faz u'su konuma bağlı değildir: en derin uç konumu belirleyicidir."""
    tool = tp.tool
    P = float(tool.pitch)
    D = float(tool.D)
    H = math.sqrt(3) / 2 * P
    r1 = D / 2 - 5 / 8 * H  # D₁/2
    feeds = []
    p0 = _to_map(tp, frame, tp.start)
    for mv in tp.moves:
        p1 = _to_map(tp, frame, mv.end)
        if mv.type in ARCS:
            raise CamError(f"Yol '{tp.name}': diş yolu değil (kılavuzda yay olmaz)")
        if mv.type is MoveType.LINEAR:
            if max(abs(p0[0]), abs(p0[1]), abs(p1[0]), abs(p1[1])) > 1e-6 or abs(p1[2] - p0[2]) <= TOL:
                raise CamError(f"Yol '{tp.name}': kılavuz harita ekseni boyunca ilerlemeli")
            feeds.append((p0[2], p1[2]))
        p0 = p1
    if not feeds:
        raise CamError(f"Yol '{tp.name}': diş yolu değil (kılavuz kesme hareketi yok)")
    if tp.feed_mode is FeedMode.PER_MIN and tp.rpm > 0:
        for mv in tp.moves:
            if mv.type is MoveType.LINEAR and abs(mv.feed / tp.rpm - P) > 1e-6 * max(1.0, P):
                raise CamError(
                    f"Yol '{tp.name}': kılavuz ilerlemesi F = S·P olmalı ({mv.feed} ≠ {tp.rpm}·{P})"
                )
    _z_check(tp, m, [z for f in feeds for z in f])
    z_anchor, z_next = feeds[0]
    s = 1.0 if z_next > z_anchor else -1.0
    t_lo = min(min(f) for f in feeds)
    t_hi = max(max(f) for f in feeds)
    zc = m.centers()
    th = m.thetas()
    w = zc - t_lo  # en derin uçtan eksenel uzaklık
    pah = float(tool.lead) * P
    cap = np.where(w < 0, -math.inf, r1 + (D / 2 - r1) * np.clip(w / pah, 0.0, 1.0))
    cap = np.where(zc > t_hi + float(tool.flute_length), -math.inf, cap)
    L = P * starts
    for j in range(starts):
        # Uç fazı: θ'da diş tepesi z_anchor − s·L·θ/360 + k·P (torna kuralıyla aynı yön)
        z_c = z_anchor - s * L * (th - j * 360.0 / starts) / 360.0
        u = zc[None, :] - z_c[:, None]
        u = u - P * np.floor(u / P + 0.5)
        R = np.minimum(D / 2, D / 2 + H / 8 - math.sqrt(3) * np.abs(u))
        _apply(m, np.minimum(R, cap[None, :]), "ic")


# ---------------------------------------------------------------- diş frezeleme


def _reach(form: ThreadMillForm, ic: bool, cxy: np.ndarray, cz, th_rad, z) -> np.ndarray:
    """θ ışınında c merkezli takımın ulaştığı yarıçap (iç: uzak uç, dış: yakın uç); kesmezse ∓inf.
    cxy (…, 2), cz (…), th_rad ve z yayınlanır."""
    ux, uy = np.cos(th_rad), np.sin(th_rad)
    uc = cxy[..., 0] * ux + cxy[..., 1] * uy
    cc = cxy[..., 0] ** 2 + cxy[..., 1] ** 2
    R = form.radius(z - cz)
    disc = R * R - cc + uc * uc
    ok = (disc >= 0) & (R > 0)
    sq = np.sqrt(np.maximum(disc, 0.0))
    if ic:
        return np.where(ok, uc + sq, -math.inf)
    return np.where(ok, uc - sq, math.inf)


def _G(form: ThreadMillForm, ic: bool, rho: float, D, w) -> np.ndarray:
    """Merkez ρ yarıçapında, ışından Δ açı uzakta, eksenel w: ulaşılan yarıçap."""
    R = form.radius(w)
    disc = R * R - (rho * np.sin(D)) ** 2
    ok = (disc >= 0) & (R > 0) & (np.abs(D) <= math.pi)
    sq = np.sqrt(np.maximum(disc, 0.0))
    if ic:
        return np.where(ok, rho * np.cos(D) + sq, -math.inf)
    return np.where(ok, rho * np.cos(D) - sq, math.inf)


def _golden(f, lo: np.ndarray, hi: np.ndarray, it: int = 60) -> np.ndarray:
    """Her eleman için [lo, hi]'de f'nin en büyüğü (altın oran araması), dizi olarak."""
    x1 = hi - GOLD * (hi - lo)
    x2 = lo + GOLD * (hi - lo)
    f1, f2 = f(x1), f(x2)
    for _ in range(it):
        sol = f1 >= f2  # tepe [lo, x2] içinde
        hi = np.where(sol, x2, hi)
        lo = np.where(sol, lo, x1)
        xn = np.where(sol, hi - GOLD * (hi - lo), lo + GOLD * (hi - lo))
        fn = f(xn)
        x1, x2, f1, f2 = (
            np.where(sol, xn, x2),
            np.where(sol, x1, xn),
            np.where(sol, fn, f2),
            np.where(sol, f1, fn),
        )
    return 0.5 * (lo + hi)


_TABLES: dict = {}


def _helix_table(form: ThreadMillForm, ic: bool, rho: float, p: float, esik: float):
    """E(s) ve en iyi Δ*(s), s ızgarası adımı ≤ 1e-4 mm. Δ: 0.25° ızgarada en iyi, sonra altın oran araması.
    esik: bu değeri aşamayan (iç) / altına inemeyen (dış) Δ'lar atlanır (R = D/2 ile üst sınır)."""
    key = (form.D, form.eps_deg, form.nose_r, ic, round(rho, 9), round(p, 9), round(esik, 9))
    if key in _TABLES:
        return _TABLES[key]
    sgn = 1.0 if ic else -1.0
    W = form.half_width()
    smax = W + abs(p) / 2 + 1e-6
    S = np.linspace(-smax, smax, max(3, math.ceil(2 * smax / 1e-4) + 1))
    h = math.radians(0.25)
    Dg = np.arange(-math.pi, math.pi + h / 2, h)
    tavan = sgn * _G_max(form, rho, Dg, ic)
    Dg = Dg[tavan > sgn * esik]
    best = np.full(S.shape, -math.inf)
    arg = np.zeros(S.shape)
    for i in range(0, len(Dg), 64):
        Dd = Dg[None, i : i + 64]
        v = sgn * _G(form, ic, rho, Dd, S[:, None] + p * Dd / (2 * math.pi))
        k = np.argmax(v, axis=1)
        vk = v[np.arange(len(S)), k]
        better = vk > best
        best[better] = vk[better]
        arg[better] = Dd[0, k[better]]

    def f(Dd):
        return sgn * _G(form, ic, rho, Dd, S + p * Dd / (2 * math.pi))

    fin = np.isfinite(best)
    xm = _golden(f, np.maximum(arg - h, -math.pi), np.minimum(arg + h, math.pi))
    fm = f(xm)
    gain = fin & (fm > best)
    best[gain] = fm[gain]
    arg[gain] = xm[gain]
    best = np.where(np.isfinite(best), best, -1e30)  # kesmeyen s: ara değerde nan olmasın
    _TABLES[key] = out = (S, sgn * best, arg)
    if len(_TABLES) > 16:
        _TABLES.pop(next(iter(_TABLES)))
    return out


def _G_max(form: ThreadMillForm, rho: float, D, ic: bool) -> np.ndarray:
    """R = D/2 ile G'nin sınırı (iç: üst, dış: alt)."""
    R = form.D / 2
    disc = R * R - (rho * np.sin(D)) ** 2
    sq = np.sqrt(np.maximum(disc, 0.0))
    if ic:
        return np.where(disc >= 0, rho * np.cos(D) + sq, -math.inf)
    return np.where(disc >= 0, rho * np.cos(D) - sq, math.inf)


def _uinterp(x: np.ndarray, S: np.ndarray, Y: np.ndarray) -> np.ndarray:
    """Eşit aralıklı S ızgarasında doğrusal ara değer (x ∈ [S₀, S_son])."""
    h = (S[-1] - S[0]) / (len(S) - 1)
    t = (x - S[0]) / h
    i = np.clip(np.floor(t).astype(np.int64), 0, len(S) - 2)
    f = t - i
    return Y[i] * (1 - f) + Y[i + 1] * f


def _helix(tp, m: PolarMap, form, ic: bool, rho, phi_a, phi_b, z_a, z_b) -> None:
    """Eksene oturan helis yayı: φ ∈ [φ_a, φ_b] (yönlü), z doğrusal."""
    p = 2 * math.pi * (z_b - z_a) / (phi_b - phi_a)  # tur başına eksenel ilerleme (işaretli)
    esik = float(np.min(m.r_in)) if ic else float(np.max(m.r_out))
    S, E, A = _helix_table(form, ic, rho, p, esik)
    lo_phi, hi_phi = min(phi_a, phi_b), max(phi_a, phi_b)
    th = np.radians(m.thetas())
    zc = m.centers()
    side = "ic" if ic else "dis"
    k0 = math.floor((lo_phi - math.pi) / (2 * math.pi)) - 1
    k1 = math.ceil((hi_phi + math.pi) / (2 * math.pi)) + 1
    for k in range(k0, k1 + 1):
        phi_c = th + 2 * math.pi * k  # (n_θ,): Δ = 0'daki konum
        z_phi = z_a + p * (phi_c - phi_a) / (2 * math.pi)
        s = zc[None, :] - z_phi[:, None]
        inside = (s >= S[0]) & (s <= S[-1])
        if not inside.any():
            continue
        rr, cc = np.nonzero(inside)
        si = s[rr, cc]
        val, Ds = _uinterp(si, S, E), _uinterp(si, S, A)
        phi_s = phi_c[rr] - Ds
        out = (phi_s < lo_phi) | (phi_s > hi_phi)
        if out.any():
            # En iyi konum yayın dışında: tek tepeli varsayımıyla en iyi izinli konum yay ucu.
            ph = np.clip(phi_s[out], lo_phi, hi_phi)
            Dd = phi_c[rr[out]] - ph
            w = zc[cc[out]] - (z_a + p * (ph - phi_a) / (2 * math.pi))
            val[out] = _G(form, ic, rho, Dd, w)
        _apply(m, val, side, rr, cc)


def _samples(p0: np.ndarray, mv: Move, ds: float):
    """Hareket boyunca (yerel, tp.frame) eşit aralıklı noktalar, adım ≤ ds."""
    p1 = np.array(mv.end, dtype=float)
    if mv.type in ARCS:
        cx, cy = mv.center
        a0 = math.atan2(p0[1] - cy, p0[0] - cx)
        a1 = math.atan2(p1[1] - cy, p1[0] - cx)
        r = math.hypot(p0[0] - cx, p0[1] - cy)
        if mv.type is MoveType.ARC_CCW:
            d = (a1 - a0) % (2 * math.pi) or 2 * math.pi
        else:
            d = -((a0 - a1) % (2 * math.pi) or 2 * math.pi)
        n = max(2, math.ceil(math.hypot(r * abs(d), p1[2] - p0[2]) / ds) + 1)
        t = np.linspace(0.0, 1.0, n)
        a = a0 + d * t
        return np.stack([cx + r * np.cos(a), cy + r * np.sin(a), p0[2] + (p1[2] - p0[2]) * t], axis=-1)
    n = max(2, math.ceil(float(np.linalg.norm(p1 - p0)) / ds) + 1)
    t = np.linspace(0.0, 1.0, n)[:, None]
    return p0 + (p1 - p0) * t


def _w_limit(form: ThreadMillForm, need: float) -> float:
    """R(w) ≥ need olan en büyük |w| (R, |w| ile azalır; ThreadMillForm.radius'un tersi); hiç yoksa −1."""
    a = math.radians(form.eps_deg / 2)
    r = form.nose_r
    Rc = form.D / 2 - r
    if need <= 0:
        return form.half_width()
    if need > Rc + r:
        return -1.0
    if need > Rc + r * math.sin(a):  # burun yayında
        return math.sqrt(max(r * r - (need - Rc) ** 2, 0.0))
    return r * math.cos(a) + (Rc + r * math.sin(a) - need) * math.tan(a)


def _generic(m: PolarMap, form: ThreadMillForm, ic: bool, C: np.ndarray) -> None:
    """Örneklenmiş takım merkezleri C (n, 3), harita yereli. Malzemeye ulaşamayan sütun / hücreler atlanır:
    iç dişte ulaşılan yarıçap ≤ |c| + R(w), dış dişte ≥ |c| − R(w)."""
    th = np.radians(m.thetas())
    ux, uy = np.cos(th), np.sin(th)
    Rmax = form.D / 2
    side = "ic" if ic else "dis"
    esik = float(np.min(m.r_in)) if ic else float(np.max(m.r_out))
    for c in C:
        rc = math.hypot(c[0], c[1])
        wl = _w_limit(form, esik - rc if ic else rc - esik)
        if wl < 0:
            continue
        uc = c[0] * ux + c[1] * uy
        disc = Rmax * Rmax - rc * rc + uc * uc
        sq = np.sqrt(np.maximum(disc, 0.0))
        cols = np.nonzero((disc >= 0) & ((uc + sq > esik) if ic else (uc - sq < esik)))[0]
        i0 = max(0, int(math.floor((c[2] - wl - m.z0) / m.dz)))
        i1 = min(m.n_z, int(math.ceil((c[2] + wl - m.z0) / m.dz)) + 1)
        if i0 >= i1 or cols.size == 0:
            continue
        val = _reach(form, ic, c[None, None, :2], c[2], th[cols, None], m.centers()[None, i0:i1])
        _apply(m, val, side, cols[:, None], np.arange(i0, i1)[None, :])


def _mill(tp: Toolpath, m: PolarMap, frame: Frame | None) -> None:
    form = tp.tool.form
    axis = _vec_to_map(tp, frame, (0.0, 0.0, 1.0))
    if abs(abs(axis[2]) - 1.0) > 1e-9:
        raise CamError(f"Yol '{tp.name}': diş frezesi ekseni harita eksenine paralel olmalı")
    ic = _mill_side(tp, m, frame)
    # Örnek adımı: eksenden ≥ 1 mm uzaktaki merkezlerde Δφ ≤ Δθ/2, eksenel ≤ Δz/4
    ds = min(0.5 * math.radians(m.dtheta), m.dz / 4)
    p0 = np.array(tp.start, dtype=float)
    zs = []
    for mv in tp.moves:
        p1 = np.array(mv.end, dtype=float)
        if mv.type is not MoveType.RAPID:
            a, b = _to_map(tp, frame, p0), _to_map(tp, frame, p1)
            zs += [a[2], b[2]]
            hx = _as_helix(tp, frame, p0, mv) if mv.type in ARCS else None
            if hx is not None:
                _z_check(tp, m, zs)
                _helix(tp, m, form, ic, *hx)
            else:
                _z_check(tp, m, zs)
                _generic(m, form, ic, _to_map(tp, frame, _samples(p0, mv, ds)))
        p0 = p1
    if not zs:
        raise CamError(f"Yol '{tp.name}': diş yolu değil (kesme hareketi yok)")


def _mill_side(tp: Toolpath, m: PolarMap, frame: Frame | None) -> bool:
    """İç diş: bütün takım merkezleri deliğin içinde (r < en büyük r_iç); aksi dış diş."""
    pts = _to_map(tp, frame, tp.points())
    return bool(np.max(np.hypot(pts[:, 0], pts[:, 1])) < float(np.max(m.r_in)))


def _as_helix(tp: Toolpath, frame: Frame | None, p0: np.ndarray, mv: Move):
    """Yay harita ekseni etrafında helis ise (ρ, φ_a, φ_b, z_a, z_b), değilse None."""
    p1 = np.array(mv.end, dtype=float)
    cx, cy = mv.center
    c = _to_map(tp, frame, (cx, cy, p0[2]))
    if math.hypot(c[0], c[1]) > 1e-7:
        return None
    a, b = _to_map(tp, frame, p0), _to_map(tp, frame, p1)
    rho = math.hypot(a[0], a[1])
    phi_a = math.atan2(a[1], a[0])
    ccw = mv.type is MoveType.ARC_CCW
    if _vec_to_map(tp, frame, (0.0, 0.0, 1.0))[2] < 0:
        ccw = not ccw
    d = math.atan2(b[1], b[0]) - phi_a
    if ccw:
        d = d % (2 * math.pi) or 2 * math.pi
    else:
        d = -((-d) % (2 * math.pi) or 2 * math.pi)
    return rho, phi_a, phi_a + d, a[2], b[2]
