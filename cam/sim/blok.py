"""
SPEC 53 — Bloklu simülasyon: aynı doğru üzerindeki ardışık G1 hareketlerini birleştirme, karo planı ve
küresel uçlu takımın kapalı form süpürme zarfı.

Süpürme kümesi takım ⊕ [p₀, p₂] = (takım ⊕ [p₀, p₁]) ∪ (takım ⊕ [p₁, p₂]); p₁ doğru üzerindeyse (ve
hareket geri dönmüyorsa) birleşmiş hareketin z-map'i aynıdır. Izgara T × T karolara bölünür; karo içindeki
işlemler hücre başına olduğu için sonuç karo boyundan bağımsızdır (bit düzeyinde).

Küresel uç: küre merkezi c(t) = p(t) + (0, 0, R) doğru boyunca süpürülünce kapsül oluşur; hücre merkezinden
geçen düşey ışının kapsülle en alçak kesişimi zarftır e(q) = min_t { c_z(t) − √(R² − d(t)²) }.
Aday noktalar: iki uç küre  e_i = c_iz − √(R² − d_i²)  ve silindir yan yüzeyi. Silindir ekseni û = u/|u|,
ışın noktası c0 + (w_x, w_y, s) için  |v|² − (v·û)² = R²  →  α s² − 2 A û_z s + (W² − A² − R²) = 0,
α = 1 − û_z², A = w_x û_x + w_y û_y, W² = w_x² + w_y²; alt kök s = (A û_z − √(A² û_z² − α γ)) / α,
eksen parametresi t = (A + s û_z) / |u| ∈ [0, 1] ise geçerli.
Kapsül dışbükey → en alçak nokta adayların min'i.
İz sınırına çok yakın hücrelerde (|d² − R²| ≤ 1e-9·R²) √ kötü koşulludur; orada SPEC 05 zarfı (altın oran
araması) kullanılır, böylece teğet hücrelerde iki yol aynı kararı verir.
"""

from __future__ import annotations

import numpy as np

from cam.model import Move, MoveType, Tool
from cam.sim.sweep import sweep_envelope

_PAY = 1e-12  # SPEC 05 _interval ile aynı sınır payı: d² ≤ R²(1 + 1e-12) + 1e-18
_HALKA = 1e-9  # iz sınırı halkası: |d² − R²| ≤ _HALKA·R² olan hücreler SPEC 05 zarfıyla


def merge_collinear(moves: list[Move], tol: float = 1e-9, start=None) -> list[tuple[int, int]]:
    """Birleştirilebilen ardışık hareket aralıkları [(ilk, son), ...] (son dahil), tüm hareketleri örter.

    Aynı tip G1, aynı F, ara noktaların doğruya uzaklığı ≤ tol olanlar tek aralıktır. Hareket doğru üzerinde
    geri dönmez (her parça grubun yönünde ilerler). start: ilk hareketin başlangıç noktası; yoksa ilk hareket
    tek başına kalır.
    """
    n = len(moves)
    araliklar: list[tuple[int, int]] = []
    i = 0
    p_bas = None if start is None else np.asarray(start, dtype=float)
    while i < n:
        j = i
        if p_bas is not None and moves[i].type is MoveType.LINEAR:
            noktalar = [p_bas, np.asarray(moves[i].end, dtype=float)]
            while j + 1 < n and _uyar(moves[i], moves[j + 1]):
                aday = noktalar + [np.asarray(moves[j + 1].end, dtype=float)]
                if not _dogru(np.array(aday), tol):
                    break
                noktalar = aday
                j += 1
        araliklar.append((i, j))
        p_bas = np.asarray(moves[j].end, dtype=float)
        i = j + 1
    return araliklar


def _uyar(a: Move, b: Move) -> bool:
    return b.type is MoveType.LINEAR and b.feed == a.feed


def _dogru(P: np.ndarray, tol: float) -> bool:
    """P[0] → P[-1] doğrusuna tüm noktalar ≤ tol uzaklıkta ve doğru boyunca geri dönüşsüz mü?"""
    u = P[-1] - P[0]
    L = float(np.linalg.norm(u))
    if L <= tol:
        return bool(np.all(np.linalg.norm(P - P[0], axis=1) <= tol))
    e = u / L
    w = P - P[0]
    s = w @ e
    dik = np.linalg.norm(w - s[:, None] * e, axis=1)
    return bool(np.all(dik <= tol) and np.all(np.diff(s) >= -tol))


def tiles(w: tuple[slice, slice], T: int | None):
    """Pencereyi ≤ T × T karolara böler (T None → tek parça)."""
    if T is None:
        yield w
        return
    for j in range(w[0].start, w[0].stop, T):
        for i in range(w[1].start, w[1].stop, T):
            yield slice(j, min(j + T, w[0].stop)), slice(i, min(i + T, w[1].stop))


def ball_envelope(p0, p1, R: float, X, Y, tool: Tool | None = None) -> np.ndarray:
    """Küresel uç (yarıçap R) için uç noktası p0 → p1 doğrusal hareketinin zarfı; dokunmayan hücre inf.

    X, Y yayınlanabilir (ör. (1, n) ve (m, 1)); sonuç (m, n). tool verilirse iz sınırı halkasındaki
    hücreler SPEC 05 sweep_envelope ile hesaplanır.
    """
    p0 = np.asarray(p0, dtype=float)
    p1 = np.asarray(p1, dtype=float)
    R2 = R * R
    sinir = R2 * (1 + _PAY) + 1e-18
    c0z, c1z = p0[2] + R, p1[2] + R
    wx = X - p0[0]
    wy = Y - p0[1]
    d0 = wx * wx + wy * wy
    vx = X - p1[0]
    vy = Y - p1[1]
    d1 = vx * vx + vy * vy
    e = np.where(d0 <= sinir, c0z - np.sqrt(np.clip(R2 - d0, 0.0, None)), np.inf)
    e = np.minimum(e, np.where(d1 <= sinir, c1z - np.sqrt(np.clip(R2 - d1, 0.0, None)), np.inf))
    ux, uy, uz = p1[0] - p0[0], p1[1] - p0[1], p1[2] - p0[2]
    Lxy2 = ux * ux + uy * uy
    if Lxy2 < 1e-24:  # düşey hareket: yalnız uç küreler
        return _halka(e, d0, R2, p0, p1, X, Y, tool)
    L = float(np.sqrt(Lxy2 + uz * uz))
    ex, ey, ez = ux / L, uy / L, uz / L
    alfa = Lxy2 / (L * L)
    A = wx * ex + wy * ey
    # xy'de doğruya dik uzaklık² = W² − (w·u_xy)²/|u_xy|²; şerit içi ⇔ disk ≥ 0
    p = wx * ux + wy * uy
    dik2 = d0 - p * p / Lxy2
    disk = np.clip(alfa * (R2 - dik2), 0.0, None)  # = A² û_z² − α γ
    s = (A * ez - np.sqrt(disk)) / alfa
    t = (A + s * ez) / L
    gecerli = (dik2 <= sinir) & (t >= 0.0) & (t <= 1.0)
    e = np.minimum(e, np.where(gecerli, c0z + s, np.inf))
    tp = p / Lxy2  # xy'de parçaya en yakın nokta parametresi
    dseg2 = np.where(tp <= 0.0, d0, np.where(tp >= 1.0, d1, dik2))
    return _halka(e, dseg2, R2, p0, p1, X, Y, tool)


def _halka(e, dseg2, R2: float, p0, p1, X, Y, tool: Tool | None) -> np.ndarray:
    if tool is None:
        return e
    halka = np.abs(dseg2 - R2) <= R2 * _HALKA
    if halka.any():
        Xh = np.broadcast_to(X, e.shape)[halka]
        Yh = np.broadcast_to(Y, e.shape)[halka]
        e = np.array(e, copy=True)
        e[halka] = sweep_envelope(tool, p0, p1, Xh, Yh)
    return e
