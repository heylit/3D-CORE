"""
SPEC 05 — Takım alt yüzeyi h(d), doğrusal hareketin süpürme zarfı ve kesmeyen gövdenin basamakları.

Uç noktası P(t) = P0 + t·(P1 − P0), t ∈ [0, 1]. Hücre merkezi q için yatay uzaklık d(t) ve uç yüksekliği z(t):
    e(q) = min { z(t) + h(d(t)) : d(t) ≤ R }      (küme boşsa +∞)
d(t)² = a t² + b t + c ikinci derece olduğundan d(t) ≤ ρ aralığı [t_a, t_b] kapalı formdur.
Düz takımda h = 0 → en küçük değer aralık ucunda. Küresel / köşe radyüslüde g(t) = z(t) + h(d(t)) dışbükeydir
(h artan dışbükey, d dışbükey) → altın oran araması tek minimumu bulur.
"""

from __future__ import annotations

import math

import numpy as np

from cam.model import Tool, ToolKind

_GOLDEN_ITER = 80  # aralık 0.618^80 ≈ 2e-17 oranında daralır
_INV_PHI = (math.sqrt(5) - 1) / 2


def _radii(tool: Tool) -> tuple[float, float]:
    """(R, r_c): takım yarıçapı ve köşe radyüsü; matkap düz uçlu kabul edilir."""
    R = tool.D / 2
    rc = 0.0 if tool.kind is ToolKind.DRILL else float(tool.corner_r)
    return R, rc


def tool_height(tool: Tool, d) -> np.ndarray:
    """Takım alt yüzeyinin eksenden d uzaklıkta uca göre yüksekliği h(d); d > R → inf.

    düz: 0 · küresel: R − √(R² − d²) · köşe radyüslü: d ≤ R − r_c → 0, aksi r_c − √(r_c² − (d − R + r_c)²)
    """
    d = np.asarray(d, dtype=float)
    R, rc = _radii(tool)
    h = np.zeros_like(d)
    if rc > 0:
        s = np.clip(d - (R - rc), 0.0, None)
        h = rc - np.sqrt(np.clip(rc * rc - s * s, 0.0, None))
    return np.where(d <= R, h, np.inf)


def _interval(p0, p1, X, Y, rho: float):
    """d(t) ≤ rho olan [t_a, t_b] ⊂ [0, 1] ve geçerlilik maskesi."""
    wx = X - p0[0]
    wy = Y - p0[1]
    ux = p1[0] - p0[0]
    uy = p1[1] - p0[1]
    a = ux * ux + uy * uy
    c = wx * wx + wy * wy - rho * rho
    if a < 1e-24:  # düşey hareket: d sabit
        mask = c <= 0
        return np.zeros_like(X), np.ones_like(X), mask
    b = -2.0 * (wx * ux + wy * uy)
    disc = b * b - 4 * a * c
    mask = disc >= 0
    sq = np.sqrt(np.clip(disc, 0.0, None))
    ta = np.clip((-b - sq) / (2 * a), 0.0, 1.0)
    tb = np.clip((-b + sq) / (2 * a), 0.0, 1.0)
    mask &= ta <= tb
    # aralık [0, 1] dışında kalıyorsa (kırpılınca uç noktada d > rho) geçersiz
    for t in (ta, tb):
        dx = wx - t * ux
        dy = wy - t * uy
        mask &= dx * dx + dy * dy <= rho * rho * (1 + 1e-12) + 1e-18
    return ta, tb, mask


def flat_min_z(p0, p1, X, Y, rho: float) -> np.ndarray:
    """min { z(t) : d(t) ≤ rho } — düz uçlu (yarıçap rho) takımın zarfı; dokunmayan hücre inf."""
    ta, tb, mask = _interval(p0, p1, X, Y, rho)
    dz = p1[2] - p0[2]
    t = ta if dz >= 0 else tb
    return np.where(mask, p0[2] + t * dz, np.inf)


def _dist(p0, p1, X, Y, t):
    return np.hypot(X - (p0[0] + t * (p1[0] - p0[0])), Y - (p0[1] + t * (p1[1] - p0[1])))


def sweep_envelope(tool: Tool, p0, p1, X, Y) -> np.ndarray:
    """Doğrusal hareketin hücre merkezlerinde bıraktığı yükseklik e(q); dokunmayan hücre inf."""
    p0 = np.asarray(p0, dtype=float)
    p1 = np.asarray(p1, dtype=float)
    X = np.asarray(X, dtype=float)
    Y = np.asarray(Y, dtype=float)
    R, rc = _radii(tool)
    if rc == 0:
        return flat_min_z(p0, p1, X, Y, R)
    ta, tb, mask = _interval(p0, p1, X, Y, R)
    dz = p1[2] - p0[2]

    def g(t):
        return p0[2] + t * dz + tool_height(tool, _dist(p0, p1, X, Y, t))

    if dz == 0:
        # yatay: en yakın nokta, kapalı form
        u = p1[:2] - p0[:2]
        a = float(u @ u)
        if a < 1e-24:
            t = np.zeros_like(X)
        else:
            t = np.clip(((X - p0[0]) * u[0] + (Y - p0[1]) * u[1]) / a, 0.0, 1.0)
        return np.where(mask, g(t), np.inf)
    if np.hypot(*(p1[:2] - p0[:2])) < 1e-12:
        # düşey: d sabit, en alçak uç
        return np.where(mask, min(p0[2], p1[2]) + tool_height(tool, _dist(p0, p1, X, Y, 0.0)), np.inf)
    lo = np.where(mask, ta, 0.0)
    hi = np.where(mask, tb, 0.0)
    best = np.minimum(g(lo), g(hi))
    x1 = hi - _INV_PHI * (hi - lo)
    x2 = lo + _INV_PHI * (hi - lo)
    f1 = g(x1)
    f2 = g(x2)
    for _ in range(_GOLDEN_ITER):
        # g dışbükey: f1 < f2 ise minimum [lo, x2]'de, değilse [x1, hi]'de; her adımda tek yeni nokta
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


def body_steps(tool: Tool, dz: float = 1.0) -> list[tuple[float, float, str]]:
    """Kesmeyen gövdenin basamakları (ρ_j, H_j, tür): d ≤ ρ_j için gövde alt yüzeyi uca göre H_j'de.

    Sap: (shank/2, L_f). Tutucu (holder ve stickout varsa): profilin her kesik konisi ≤ dz yüksekliğinde
    dilimlere bölünür; dilim yarıçapı dilimdeki büyük uç, alt yüzeyi stickout + ζ_alt (tutucu şişirilir →
    güvenli taraf). Daha alçak ve daha geniş bir basamağın gölgesinde kalanlar atılır; sonuç ρ ve H'de
    kesin artan.
    """
    adaylar: list[tuple[float, float, str]] = [(tool.shank / 2, float(tool.flute_length), "sap")]
    if tool.holder is not None and tool.stickout is not None:
        so = float(tool.stickout)
        P = tool.holder.profile
        for (za, ra), (zb, rb) in zip(P[:-1], P[1:], strict=True):
            boy = zb - za
            if boy <= 0:
                adaylar.append((max(ra, rb), so + za, "tutucu"))
                continue
            n = max(1, math.ceil(boy / dz - 1e-12))
            h = boy / n
            for m in range(n):
                r_lo = ra + (rb - ra) * m / n
                r_hi = ra + (rb - ra) * (m + 1) / n
                adaylar.append((max(r_lo, r_hi), so + za + m * h, "tutucu"))
    # H artan (eşitlikte geniş önce) sırala, ρ'su öncekilerin en genişini aşmayanları at
    adaylar.sort(key=lambda s: (s[1], -s[0]))
    sonuc: list[tuple[float, float, str]] = []
    for rho, H, tur in adaylar:
        if sonuc and rho <= sonuc[-1][0]:
            continue
        sonuc.append((rho, H, tur))
    return sonuc


def sweep_top(tool: Tool, p0, p1, X, Y) -> np.ndarray:
    """Kesen kısmın ışındaki üst ucu e_üst(q) = L_f + max{ z(t) : d(t) ≤ R }; dokunmayan hücre −inf."""
    p0 = np.asarray(p0, dtype=float)
    p1 = np.asarray(p1, dtype=float)
    ta, tb, mask = _interval(p0, p1, np.asarray(X, dtype=float), np.asarray(Y, dtype=float), tool.D / 2)
    dz = p1[2] - p0[2]
    t = tb if dz >= 0 else ta
    return np.where(mask, tool.flute_length + p0[2] + t * dz, -np.inf)
