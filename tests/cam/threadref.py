"""SPEC 52 testleri için bağımsız referans: ISO 68-1 diş geometrisi, V profil, helis eşleştirme,
diş frezesi zarfı.

cam.sim kodu okunmadı; formüller SPEC 52 "Teori" bölümünden ve temel geometriden.
- ISO 68-1: H = (√3/2)·P, d₂ = d − (3√3/8)·P, dış d₃ = d − 2·(17/24)·H, iç D₁ = D − 2·(5/8)·H.
- Torna diş kalemi kesiti (r, z) yarı düzleminde: burun merkezi (0, x_c), yarıçap r, böğürler radyal yönle
  ±α = ±ε/2 açı yapar. Alt sınır x(u): |u| ≤ r·cos α → x_c − √(r² − u²);
  aksi x_c − r·sin α + (|u| − r·cos α)/tan α.
- Senkron kesim: hücre (θ, z)'de profil u = z − z_c(θ) kaymasıyla, z_c(θ) = c + L·θ/360 (+ k·L/ağız sayısı).
- Diş frezesi (dönel zarf): takım ekseni delik eksenine paralel, merkez c;
  uçtan w eksenel uzaklıkta yarıçap R(w).
  θ yönündeki ışın r·(cos θ, sin θ) diski r ≤ u·c + √(R² − |c|² + (u·c)²) kadar keser.
"""

from __future__ import annotations

import math

import numpy as np
from scipy.optimize import minimize_scalar

from cam.model import Move, MoveType, Toolpath

SQ3 = math.sqrt(3.0)


def H_iso(P: float) -> float:
    """Temel üçgen yüksekliği H = (√3/2)·P."""
    return SQ3 / 2 * P


def d2_iso(d: float, P: float) -> float:
    """Böğür çapı d₂ = d − (3√3/8)·P = d − 0.649519·P."""
    return d - 3 * SQ3 / 8 * P


def d3_iso(d: float, P: float) -> float:
    """Dış diş dibi d₃ = d − 2·(17/24)·H = d − 1.226869·P."""
    return d - 2 * 17 / 24 * H_iso(P)


def D1_iso(D: float, P: float) -> float:
    """İç diş küçük çapı D₁ = D − 2·(5/8)·H = D − 1.082532·P."""
    return D - 2 * 5 / 8 * H_iso(P)


def v_lower(u, x_c: float, r: float, alpha_deg: float = 30.0) -> np.ndarray:
    """Burun yarıçaplı V kalemin (dış diş) alt sınırı x(u); burun merkezi (0, x_c)."""
    u = np.abs(np.asarray(u, dtype=float))
    a = math.radians(alpha_deg)
    ut = r * math.cos(a)
    flank = x_c - r * math.sin(a) + (u - ut) / math.tan(a)
    nose = x_c - np.sqrt(np.maximum(r * r - u * u, 0.0))
    return np.where(u <= ut, nose, flank)


def wrap(u, period: float) -> np.ndarray:
    """u'yu [−period/2, period/2) aralığına kaydır (en yakın yiv)."""
    u = np.asarray(u, dtype=float)
    return u - period * np.floor(u / period + 0.5)


def helix_outer(thetas, zs, c: float, lead: float, starts: int, x_c: float, r: float, r0, alpha_deg=30.0):
    """Dış diş senkron kesim sonucu r_dış(θ, z) = min(r0, profil(sar(z − c − L·θ/360, L/n))), (n_θ, n_z)."""
    th = np.asarray(thetas, dtype=float)[:, None]
    z = np.asarray(zs, dtype=float)[None, :]
    u = wrap(z - c - lead * th / 360.0, lead / starts)
    return np.minimum(np.asarray(r0, dtype=float)[None, :] * np.ones_like(u), v_lower(u, x_c, r, alpha_deg))


def fit_helix(R, thetas, zs, lead: float, starts: int, x_c: float, r: float, r0, alpha_deg=30.0, sign=1):
    """Faz c'yi bul: max |R − helix_outer| en küçük. sign = −1 ters helis (L → −L). Dönüş (c, hata)."""
    period = lead / starts

    def err(c: float) -> float:
        ref = helix_outer(thetas, zs, c, sign * lead, starts, x_c, r, r0, alpha_deg)
        return float(np.max(np.abs(np.asarray(R, dtype=float) - ref)))

    grid = np.linspace(0.0, period, 401, endpoint=False)
    vals = [err(c) for c in grid]
    c0 = grid[int(np.argmin(vals))]
    h = period / 400
    res = minimize_scalar(err, bounds=(c0 - h, c0 + h), method="bounded", options={"xatol": 1e-13})
    return float(res.x), float(res.fun)


def groove_volume_per_turn(h: float, r0: float, alpha_deg: float = 30.0) -> float:
    """Sivri V yiv (derinlik h, tepe yarıçapı r0) Pappus hacmi: A·2π·r_c, A = h²·tan α, r_c = r0 − h/3."""
    A = h * h * math.tan(math.radians(alpha_deg))
    return A * 2 * math.pi * (r0 - h / 3)


# ------------------------------------------------------------------ yol örnekleme (diş frezesi)


def _move_eval(p0: np.ndarray, m: Move):
    """Hareketi t ∈ [0, 1] ile parametreleyen fonksiyon ve süpürme açısı [rad] (doğruda 0)."""
    p1 = np.array(m.end, dtype=float)
    if m.type in (MoveType.ARC_CW, MoveType.ARC_CCW):
        cx, cy = m.center
        a0 = math.atan2(p0[1] - cy, p0[0] - cx)
        a1 = math.atan2(p1[1] - cy, p1[0] - cx)
        rr = math.hypot(p0[0] - cx, p0[1] - cy)
        if m.type is MoveType.ARC_CCW:
            d = (a1 - a0) % (2 * math.pi)
            d = d if d > 1e-12 else 2 * math.pi
        else:
            d = -((a0 - a1) % (2 * math.pi))
            d = d if d < -1e-12 else -2 * math.pi

        def f(t):
            t = np.asarray(t, dtype=float)
            a = a0 + d * t
            return np.stack([cx + rr * np.cos(a), cy + rr * np.sin(a), p0[2] + (p1[2] - p0[2]) * t], axis=-1)

        return f, d

    def g(t):
        t = np.asarray(t, dtype=float)[..., None]
        return p0 + (p1 - p0) * t

    return g, 0.0


def feed_moves(tp: Toolpath):
    """Kesme hareketleri (G0 hariç): [(f, süpürme, boy)], yerel koordinatta (Frame birim kabul)."""
    out = []
    p0 = np.array(tp.start, dtype=float)
    for m in tp.moves:
        f, d = _move_eval(p0, m)
        if m.type is not MoveType.RAPID:
            ln = float(np.linalg.norm(np.array(m.end) - p0))
            out.append((f, d, ln))
        p0 = np.array(m.end, dtype=float)
    return out


def cone_R(w, D: float, eps_deg: float, nose_r: float = 0.0) -> np.ndarray:
    """Tek profilli diş frezesi: uçtan eksenel w uzaklıkta yarıçap (≥ 0). D/2 fiziksel uç (burun dahil)
    yarıçapı;
    burun merkezi D/2 − r: |w| ≤ r·cos α → (D/2 − r) + √(r² − w²),
    aksi (D/2 − r) + r·sin α − (|w| − r·cos α)/tan α."""
    w = np.abs(np.asarray(w, dtype=float))
    a = math.radians(eps_deg / 2)
    Rc = D / 2 - nose_r
    wt = nose_r * math.cos(a)
    nose = Rc + np.sqrt(np.maximum(nose_r * nose_r - w * w, 0.0))
    flank = Rc + nose_r * math.sin(a) - (w - wt) / math.tan(a)
    return np.maximum(np.where(w <= wt, nose, flank), 0.0)


def _reach(theta_deg: float, z, C: np.ndarray, D: float, eps_deg: float, nose_r: float) -> np.ndarray:
    """θ ışınında takımın ulaştığı en büyük r, (n_z, n_c); kesmezse −inf. C: (n_c, 3) takım ucu merkezleri."""
    th = math.radians(theta_deg)
    ux, uy = math.cos(th), math.sin(th)
    uc = C[:, 0] * ux + C[:, 1] * uy
    cc = C[:, 0] ** 2 + C[:, 1] ** 2
    R = cone_R(np.asarray(z, dtype=float)[:, None] - C[None, :, 2], D, eps_deg, nose_r)
    disc = R * R - cc[None, :] + uc[None, :] ** 2
    return np.where((disc >= 0) & (R > 0), uc[None, :] + np.sqrt(np.maximum(disc, 0.0)), -np.inf)


def mill_envelope_inner(
    tp: Toolpath, thetas, zs, D: float, eps_deg: float, nose_r: float, r_in0: float
) -> np.ndarray:
    """İç diş frezesi zarfı r_iç(θ, z) = max(r_iç0, max_konum reach). Kaba örnekleme (yayda 0.05°,
    doğruda 0.005 mm),
    sonra en iyi kaba örneğin ±1 adımında 401 noktalı ince örnekleme. (n_θ, n_z)."""
    zs = np.asarray(zs, dtype=float)
    moves = []
    for f, d, ln in feed_moves(tp):
        n = max(2, int(math.ceil(abs(d) / math.radians(0.05))) + 1, int(math.ceil(ln / 0.005)) + 1)
        ts = np.linspace(0.0, 1.0, n)
        moves.append((f, ts, f(ts)))
    out = np.full((len(thetas), len(zs)), r_in0, dtype=float)
    for j, th in enumerate(thetas):
        best_r = np.full(len(zs), -np.inf)
        best_m = np.zeros(len(zs), dtype=int)
        best_t = np.zeros(len(zs))
        for k, (_f, ts, C) in enumerate(moves):
            reach = _reach(th, zs, C, D, eps_deg, nose_r)
            a = np.argmax(reach, axis=1)
            r = reach[np.arange(len(zs)), a]
            better = r > best_r
            best_r[better], best_m[better], best_t[better] = r[better], k, ts[a[better]]
        for i in range(len(zs)):
            if not np.isfinite(best_r[i]):
                continue
            f, ts, _C = moves[best_m[i]]
            dt = ts[1] - ts[0]
            tf = np.clip(best_t[i] + np.linspace(-dt, dt, 401), 0.0, 1.0)
            rf = _reach(th, zs[i : i + 1], f(tf), D, eps_deg, nose_r)
            out[j, i] = max(out[j, i], best_r[i], float(np.max(rf)))
    return out


# ------------------------------------------------------------------ torna diş düzeneği (K2–K4, K8, K9)

Z_ST, Z_EN = -0.5, -24.0  # paso başı / sonu: boyun (z > −2) ve kanal (−26 < z < −22) içinde, malzemesiz
MIL_Z = (-22.0, -2.0)  # tam çaplı mil bölgesi (20 mm)


def mil_rmap(D: float, r_bos: float, dz: float = 0.05):
    """Ø D mil, z ∈ [−30, 5];
    z > −2 boyun ve −26 < z < −22 kanal r_bos yarıçapına inmiş (diş dibinin altında).
    Paso giriş / çıkışları malzemeye değmez; tam çaplı bölge MIL_Z."""
    from cam.model import CylinderStock
    from cam.sim import RadialMap

    g = RadialMap.from_stock(CylinderStock(D=D, zmin=-30.0, zmax=5.0), dz)
    for i, z in enumerate(g.centers()):
        if z > MIL_Z[1] or MIL_Z[0] - 4.0 < z < MIL_Z[0]:
            g.subtract(i, r_bos, D / 2)
    return g


def dis_kalemi(nose_r: float, id: int = 4):
    """60° diş kalemi, T = 8 (uç −X'e bakar), κr = εr = 60° → böğürler radyal yönle ±30°."""
    from cam.model import LatheTool, LatheToolKind

    return LatheTool(id, "dis_kalemi", LatheToolKind.THREAD, nose_r, 8, 60.0, 60.0, edge_len=5.0)


def torna_disi(D: float, P: float, kalem, derinlik: float, z_st: float = Z_ST, z_en: float = Z_EN, lead=None):
    """SPEC 20 thread: radyal dalma, son paso tam derinlik + 1 boş paso;
    feed = hatve boyu (lead, verilmezse P)."""
    from cam.lathe_ops import TurnCut, thread
    from cam.model import CylinderStock

    L = P if lead is None else lead
    stok = CylinderStock(D=D, zmin=-30.0, zmax=0.0)
    return thread(
        stok, kalem, TurnCut(feed=L, rpm=300.0), z_st, z_en, D / 2, L, derinlik, first=0.3, spring=1
    )
