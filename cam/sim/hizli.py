"""
SPEC 53 — numba ile derlenmiş hücre döngüleri (kullanıcı onayı 2026-10-18: "SPEC 53 için numba bağımlılığını
onaylıyorum"). numba kurulu değilse VAR = False olur ve simülasyon numpy yoluna döner.

Bir doğrusal hareketin z-haritası güncellemesi tek döngüde: hücre merkezinde zarf e (düz uç: SPEC 05
flat_min_z; küresel uç: kapalı form kapsül zarfı, iz sınırı halkasında SPEC 05 altın oran araması),
z ← max(zmin, min(z, e)), kaldırılan boy toplamı ve değişen hücrelerin olay kaydı. Formüller numpy
sürümleriyle (cam/sim/sweep.py, cam/sim/blok.py) aynı işlem sırasındadır.
"""

from __future__ import annotations

import math

import numpy as np

try:
    from numba import njit

    VAR = True
except ImportError:  # pragma: no cover - numba yoksa numpy yolu
    VAR = False

    def njit(*args, **kwargs):
        def sar(f):
            return f

        return sar


_PAY = 1e-12
_HALKA = 1e-9
_GOLDEN_ITER = 80
_INV_PHI = (math.sqrt(5) - 1) / 2


@njit(cache=True)
def _aralik(p0x, p0y, p1x, p1y, x, y, rho):
    """SPEC 05 _interval'in tek hücre sürümü: (ta, tb, geçerli)."""
    wx = x - p0x
    wy = y - p0y
    ux = p1x - p0x
    uy = p1y - p0y
    a = ux * ux + uy * uy
    c = wx * wx + wy * wy - rho * rho
    if a < 1e-24:
        return 0.0, 1.0, c <= 0
    b = -2.0 * (wx * ux + wy * uy)
    disc = b * b - 4 * a * c
    gec = disc >= 0
    sq = math.sqrt(max(disc, 0.0))
    ta = min(max((-b - sq) / (2 * a), 0.0), 1.0)
    tb = min(max((-b + sq) / (2 * a), 0.0), 1.0)
    gec = gec and ta <= tb
    sinir = rho * rho * (1 + 1e-12) + 1e-18
    for t in (ta, tb):
        dx = wx - t * ux
        dy = wy - t * uy
        gec = gec and dx * dx + dy * dy <= sinir
    return ta, tb, gec


@njit(cache=True)
def _duz(p0x, p0y, p0z, p1x, p1y, p1z, x, y, R):
    """flat_min_z: min z(t), d(t) ≤ R."""
    ta, tb, gec = _aralik(p0x, p0y, p1x, p1y, x, y, R)
    if not gec:
        return np.inf
    dz = p1z - p0z
    t = ta if dz >= 0 else tb
    return p0z + t * dz


@njit(cache=True)
def _h(d, R):
    """Küresel uç yüksekliği h(d) (tool_height, r_c = R)."""
    if not d <= R:
        return np.inf
    s = max(d, 0.0)
    return R - math.sqrt(max(R * R - s * s, 0.0))


@njit(cache=True)
def _g(p0x, p0y, p0z, ux, uy, dz, x, y, R, t):
    return p0z + t * dz + _h(math.hypot(x - (p0x + t * ux), y - (p0y + t * uy)), R)


@njit(cache=True)
def _altin(p0x, p0y, p0z, p1x, p1y, p1z, x, y, R):
    """SPEC 05 sweep_envelope'un küresel uç dalı (altın oran araması), tek hücre."""
    ta, tb, gec = _aralik(p0x, p0y, p1x, p1y, x, y, R)
    if not gec:
        return np.inf
    ux = p1x - p0x
    uy = p1y - p0y
    dz = p1z - p0z
    if dz == 0:
        a = ux * ux + uy * uy
        if a < 1e-24:
            t = 0.0
        else:
            t = min(max(((x - p0x) * ux + (y - p0y) * uy) / a, 0.0), 1.0)
        return _g(p0x, p0y, p0z, ux, uy, dz, x, y, R, t)
    if math.hypot(ux, uy) < 1e-12:
        return min(p0z, p1z) + _h(math.hypot(x - p0x, y - p0y), R)
    lo = ta
    hi = tb
    best = min(_g(p0x, p0y, p0z, ux, uy, dz, x, y, R, lo), _g(p0x, p0y, p0z, ux, uy, dz, x, y, R, hi))
    x1 = hi - _INV_PHI * (hi - lo)
    x2 = lo + _INV_PHI * (hi - lo)
    f1 = _g(p0x, p0y, p0z, ux, uy, dz, x, y, R, x1)
    f2 = _g(p0x, p0y, p0z, ux, uy, dz, x, y, R, x2)
    for _ in range(_GOLDEN_ITER):
        if f1 < f2:
            hi = x2
            xn = hi - _INV_PHI * (hi - lo)
            fn = _g(p0x, p0y, p0z, ux, uy, dz, x, y, R, xn)
            x1, x2 = xn, x1
            f1, f2 = fn, f1
        else:
            lo = x1
            xn = lo + _INV_PHI * (hi - lo)
            fn = _g(p0x, p0y, p0z, ux, uy, dz, x, y, R, xn)
            x1, x2 = x2, xn
            f1, f2 = f2, fn
    best = min(best, min(f1, f2))
    return min(best, _g(p0x, p0y, p0z, ux, uy, dz, x, y, R, 0.5 * (lo + hi)))


@njit(cache=True)
def _kure(p0x, p0y, p0z, p1x, p1y, p1z, x, y, R):
    """ball_envelope (kapalı form kapsül, iz sınırı halkasında _altin), tek hücre."""
    R2 = R * R
    sinir = R2 * (1 + _PAY) + 1e-18
    wx = x - p0x
    wy = y - p0y
    d0 = wx * wx + wy * wy
    vx = x - p1x
    vy = y - p1y
    d1 = vx * vx + vy * vy
    e = np.inf
    if d0 <= sinir:
        e = p0z + R - math.sqrt(max(R2 - d0, 0.0))
    if d1 <= sinir:
        e = min(e, p1z + R - math.sqrt(max(R2 - d1, 0.0)))
    ux = p1x - p0x
    uy = p1y - p0y
    uz = p1z - p0z
    Lxy2 = ux * ux + uy * uy
    if Lxy2 < 1e-24:
        dseg2 = d0
    else:
        L = math.sqrt(Lxy2 + uz * uz)
        ex = ux / L
        ey = uy / L
        ez = uz / L
        alfa = Lxy2 / (L * L)
        A = wx * ex + wy * ey
        p = wx * ux + wy * uy
        dik2 = d0 - p * p / Lxy2
        disk = max(alfa * (R2 - dik2), 0.0)
        s = (A * ez - math.sqrt(disk)) / alfa
        t = (A + s * ez) / L
        if dik2 <= sinir and t >= 0.0 and t <= 1.0:
            e = min(e, p0z + R + s)
        tp = p / Lxy2
        dseg2 = d0 if tp <= 0.0 else (d1 if tp >= 1.0 else dik2)
    if abs(dseg2 - R2) <= R2 * _HALKA:
        e = _altin(p0x, p0y, p0z, p1x, p1y, p1z, x, y, R)
    return e


@njit(cache=True)
def zmap_hareket(z, zmin, x0, dx, y0, dy, j0, j1, i0, i1, p0, p1, R, kure, ev_c, ev_z, say):
    """Pencere [j0, j1) × [i0, i1) üzerinde hareketin kaldırması.

    Dönüş: (kaldırılan boy toplamı, olay sayısı). Değişen hücreler ev_c / ev_z'ye (satır sıralı) yazılır,
    say[hücre] artar. Küresel uçta iki erken çıkış (sonucu değiştirmez): iz dışındaki hücre (zarf ∞) ve
    alt sınırın e ≥ min(z_uç) + h(d_parça) bile üstünde kalan hücre (kaldırma olamaz).
    """
    nx = z.shape[1]
    toplam = 0.0
    n = 0
    R2 = R * R
    dis = max(R2 * (1 + _PAY) + 1e-18, R2 + R2 * _HALKA)  # bunun ötesinde zarf ∞ (halka dahil)
    ux = p1[0] - p0[0]
    uy = p1[1] - p0[1]
    Lxy2 = ux * ux + uy * uy
    z_uc = min(p0[2], p1[2])
    for j in range(j0, j1):
        y = y0 + (j + 0.5) * dy
        wy = y - p0[1]
        for i in range(i0, i1):
            x = x0 + (i + 0.5) * dx
            z_once = z[j, i]
            if z_once <= zmin:
                continue
            if kure:
                wx = x - p0[0]
                d0 = wx * wx + wy * wy
                if Lxy2 < 1e-24:
                    dseg2 = d0
                else:
                    tp = (wx * ux + wy * uy) / Lxy2
                    if tp <= 0.0:
                        dseg2 = d0
                    elif tp >= 1.0:
                        vx = x - p1[0]
                        vy = y - p1[1]
                        dseg2 = vx * vx + vy * vy
                    else:
                        dseg2 = d0 - tp * (wx * ux + wy * uy)
                if dseg2 > dis:
                    continue
                if z_once <= z_uc + R - math.sqrt(max(R2 - dseg2, 0.0)) - 1e-9:
                    continue
                e = _kure(p0[0], p0[1], p0[2], p1[0], p1[1], p1[2], x, y, R)
            else:
                e = _duz(p0[0], p0[1], p0[2], p1[0], p1[1], p1[2], x, y, R)
            z_yeni = max(zmin, min(z_once, e))
            if z_yeni < z_once:
                toplam += z_once - z_yeni
                z[j, i] = z_yeni
                c = j * nx + i
                ev_c[n] = c
                ev_z[n] = z_yeni
                say[c] += 1
                n += 1
    return toplam, n


@njit(cache=True)
def pencere_max(z, j0, j1, i0, i1):
    m = -np.inf
    for j in range(j0, j1):
        for i in range(i0, i1):
            if z[j, i] > m:
                m = z[j, i]
    return m


@njit(cache=True)
def yerlestir(c, zs, bas, k, yer0, k_out, z_out):
    """Olayları (hücre, k) sırasına yerleştirir: parça p = [bas[p], bas[p+1]) adım k[p]'nin olayları,
    hücrenin sıradaki boş yeri yer0[hücre]."""
    for p in range(k.size):
        kp = k[p]
        for e in range(bas[p], bas[p + 1]):
            h = c[e]
            y = yer0[h]
            k_out[y] = kp
            z_out[y] = zs[e]
            yer0[h] = y + 1
