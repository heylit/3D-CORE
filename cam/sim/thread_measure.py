"""
SPEC 52 — Simüle diş yüzeyinden ölçüm: hatve (öz-ilişki), büyük çap, böğür çapı (dolu oranı ½),
diş dibi, helis tutarlılığı.

ISO 68-1: H = (√3/2)·P, d₂ = d − (3√3/8)·P, dış d₃ = d − 2·(17/24)·H, iç D₁ = D − 2·(5/8)·H.

- Hatve: her θ'da r(z) dizisinin öz-ilişkisi (çakışan boyla normlanmış, θ'lar üzerinden toplanmış); sıfırı ilk
  geçtikten sonraki ilk tepe, parabolle alt-hücre doğruluğunda.
- Büyük çap / diş dibi: bölgedeki en büyük / en küçük r × 2.
- Böğür çapı: r(z) hücre merkezleri arasında doğrusal; bölge tam sayıda hatveye kırpılır ([a, a + n·P]); her θ
  için malzemenin (dış: r_dış ≥ ρ, iç: r_iç ≤ ρ) boy oranı ½ olan ρ ikiye bölmeyle; θ'ların ortalaması × 2.
- Helis tutarlılığı: lead_err = max |r(θ, z) − r(θ₀, z − P·(θ − θ₀)/360°)| (θ₀ ilk sütun, doğrusal ara değer;
  sağ helis kuralı: z, θ ile artar).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from cam.model import CamError
from cam.sim.polar import PolarMap


@dataclass
class ThreadMeasure:
    """Ölçülen değerler [mm]: hatve, büyük çap, böğür çapı, diş dibi çapı, helis tutarlılık hatası."""

    P: float
    d: float
    d2: float
    d_root: float
    lead_err: float


def thread_measure(m: PolarMap, side: str, z_range: tuple[float, float]) -> ThreadMeasure:
    """side "dis" (r_out) veya "ic" (r_in); z_range ölçüm bölgesi (z_min, z_max). Hatalı girdi → CamError."""
    if not isinstance(m, PolarMap):
        raise CamError(f"thread_measure: PolarMap gerekir ({type(m).__name__})")
    if side not in ("dis", "ic"):
        raise CamError(f"thread_measure: taraf 'dis' veya 'ic' olmalı ({side!r})")
    try:
        a, b = (float(v) for v in z_range)
    except (TypeError, ValueError) as e:
        raise CamError(f"thread_measure: z_range (z_min, z_max) olmalı ({z_range!r})") from e
    if not (math.isfinite(a) and math.isfinite(b) and a < b):
        raise CamError(f"thread_measure: z_min < z_max sonlu olmalı ({z_range!r})")
    if a < m.z0 or b > m.z1:
        raise CamError(f"thread_measure: bölge haritanın dışında ([{a}, {b}] ⊄ [{m.z0}, {m.z1}])")
    z = m.centers()
    w = (z >= a) & (z <= b)
    if np.count_nonzero(w) < 8:
        raise CamError("thread_measure: bölgede en az 8 hücre olmalı")
    r_all = m.r_out if side == "dis" else m.r_in
    r = r_all[:, w]
    P = _pitch(r, m.dz)
    d = 2 * float(np.max(r))
    d_root = 2 * float(np.min(r))
    d2 = 2 * _pitch_radius(r_all, z, a, b, P, side)
    lead_err = _lead_err(r_all, z, w, m.thetas(), P)
    return ThreadMeasure(P, d, d2, d_root, lead_err)


def _pitch(r: np.ndarray, dz: float) -> float:
    x = r - r.mean(axis=1, keepdims=True)
    n = x.shape[1]
    lags = np.arange(n // 2 + 1)
    ac = np.array([np.sum(x[:, : n - k] * x[:, k:]) / (n - k) for k in lags])
    if not ac[0] > 0:
        raise CamError("thread_measure: bölgede diş yok (yüzey düz)")
    neg = np.nonzero(ac < 0)[0]
    if neg.size == 0:
        raise CamError("thread_measure: hatve bulunamadı (bölge en az iki hatve içermeli)")
    k = None
    for i in range(int(neg[0]) + 1, len(ac) - 1):
        if ac[i] >= ac[i - 1] and ac[i] >= ac[i + 1]:
            k = i
            break
    if k is None:
        raise CamError("thread_measure: hatve bulunamadı (bölge en az iki hatve içermeli)")
    y0, y1, y2 = ac[k - 1], ac[k], ac[k + 1]
    den = y0 - 2 * y1 + y2
    off = 0.5 * (y0 - y2) / den if den != 0 else 0.0
    return float((k + off) * dz)


def _covered(r: np.ndarray, z: np.ndarray, a: float, b: float, rho: np.ndarray, dis: bool) -> np.ndarray:
    """Her θ satırında [a, b] içinde malzeme boyu: doğrusal r(z), dış r ≥ ρ, iç r ≤ ρ."""
    f = (r - rho[:, None]) if dis else (rho[:, None] - r)  # ≥ 0 → malzeme
    z0, z1 = z[:-1], z[1:]
    f0, f1 = f[:, :-1], f[:, 1:]
    lo = np.clip(z0, a, b)
    hi = np.clip(z1, a, b)
    # parçanın [lo, hi] kısmında f ≥ 0 boyu (doğrusal f)
    t_lo = (lo - z0) / (z1 - z0)
    t_hi = (hi - z0) / (z1 - z0)
    g_lo = f0 + (f1 - f0) * t_lo
    g_hi = f0 + (f1 - f0) * t_hi
    L = hi - lo
    both = (g_lo >= 0) & (g_hi >= 0)
    none = (g_lo < 0) & (g_hi < 0)
    with np.errstate(divide="ignore", invalid="ignore"):
        t0 = g_lo / (g_lo - g_hi)  # sıfır geçişinin [lo, hi] içindeki oranı
        part = np.where(g_lo >= 0, t0, 1.0 - t0) * L
    out = np.where(both, L, np.where(none, 0.0, part))
    return out.sum(axis=1)


def _pitch_radius(r: np.ndarray, z: np.ndarray, a: float, b: float, P: float, side: str) -> float:
    n = math.floor((b - a) / P + 1e-9)
    if n < 1:
        raise CamError("thread_measure: bölge en az bir hatve boyunda olmalı")
    lo_z, hi_z = max(a, z[0]), min(a + n * P, z[-1])
    span = hi_z - lo_z
    dis = side == "dis"
    lo = np.full(r.shape[0], float(np.min(r)))
    hi = np.full(r.shape[0], float(np.max(r)))
    for _ in range(60):
        mid = 0.5 * (lo + hi)
        frac = _covered(r, z, lo_z, hi_z, mid, dis) / span
        # dış: ρ büyüdükçe dolu oranı azalır; iç: artar
        up = frac > 0.5 if dis else frac < 0.5
        lo = np.where(up, mid, lo)
        hi = np.where(up, hi, mid)
    return float(np.mean(0.5 * (lo + hi)))


def _lead_err(r: np.ndarray, z: np.ndarray, w: np.ndarray, th: np.ndarray, P: float) -> float:
    zw = z[w]
    err = 0.0
    for j in range(len(th)):
        zs = zw - P * (th[j] - th[0]) / 360.0
        ok = (zs >= z[0]) & (zs <= z[-1])
        if ok.any():
            ref = np.interp(zs[ok], z, r[0])
            err = max(err, float(np.max(np.abs(r[j, w][ok] - ref))))
    return err
