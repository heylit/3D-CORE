"""SPEC 16 testleri için ortak el hesabı yardımcıları (uygulama kodu kullanılmaz).

Boy, alan, nokta-çokgen ve örtüşme denetimleri burada bağımsız olarak hesaplanır; böylece testler
`cleanup.total_length` gibi test edilen fonksiyonlara dayanmaz.
"""

from __future__ import annotations

import math

import numpy as np

from geometry.drawing.types import Arc2D, Line2D, Polyline2D


def boy(e) -> float:
    """Tek varlığın boyu: doğru |p1 − p0|, yay r·Δθ, çoklu çizgi Σ|Pᵢ₊₁ − Pᵢ|; metin 0."""
    if isinstance(e, Line2D):
        return float(np.linalg.norm(np.asarray(e.p1, float) - np.asarray(e.p0, float)))
    if isinstance(e, Arc2D):
        return float(e.r * math.radians(e.a1 - e.a0))
    if isinstance(e, Polyline2D):
        P = np.asarray(e.P, float)
        return float(np.linalg.norm(np.diff(P, axis=0), axis=1).sum())
    return 0.0


def toplam_boy(entities, layer: str) -> float:
    """Katmandaki toplam boy."""
    return sum(boy(e) for e in entities if getattr(e, "layer", None) == layer)


def katmandakiler(entities, layer: str, tip=None) -> list:
    return [e for e in entities if e.layer == layer and (tip is None or isinstance(e, tip))]


def tam_cemberler(entities, layer: str = "GORUNUR") -> list[Arc2D]:
    return [e for e in katmandakiler(entities, layer, Arc2D) if abs((e.a1 - e.a0) - 360.0) < 1e-9]


def dikey_dogrular(entities, layer: str, u: float, tol: float = 1e-6) -> list[Line2D]:
    """u = sabit dikey doğru parçaları."""
    return [
        e
        for e in katmandakiler(entities, layer, Line2D)
        if abs(e.p0[0] - u) < tol and abs(e.p1[0] - u) < tol and abs(e.p1[1] - e.p0[1]) > tol
    ]


def yatay_dogrular(entities, layer: str, v: float, tol: float = 1e-6) -> list[Line2D]:
    """v = sabit yatay doğru parçaları."""
    return [
        e
        for e in katmandakiler(entities, layer, Line2D)
        if abs(e.p0[1] - v) < tol and abs(e.p1[1] - v) < tol and abs(e.p1[0] - e.p0[0]) > tol
    ]


def isaretli_alan(P: np.ndarray) -> float:
    """Ayakkabı bağı formülü: A = ½ Σ (xᵢ yᵢ₊₁ − xᵢ₊₁ yᵢ); CCW → pozitif."""
    P = np.asarray(P, float)
    x, y = P[:, 0], P[:, 1]
    return 0.5 * float(np.sum(x * np.roll(y, -1) - np.roll(x, -1) * y))


def bolge_alani(region) -> float:
    """Dış sınır alanı − delik alanları (delikler CW olduğu için işaretli alanlar toplanır)."""
    return isaretli_alan(region.outer) + sum(isaretli_alan(h) for h in region.holes)


def cokgen_icinde(p, P) -> bool:
    """Işın atma (çift-tek kuralı)."""
    x, y = float(p[0]), float(p[1])
    P = np.asarray(P, float)
    ic = False
    n = len(P)
    for i in range(n):
        x0, y0 = P[i]
        x1, y1 = P[(i + 1) % n]
        if (y0 > y) != (y1 > y):
            xk = x0 + (y - y0) * (x1 - x0) / (y1 - y0)
            if xk > x:
                ic = not ic
    return ic


def bolge_icinde(p, region) -> bool:
    return cokgen_icinde(p, region.outer) and not any(cokgen_icinde(p, h) for h in region.holes)


def kenara_uzaklik(p, P) -> float:
    """p noktasının kapalı çokgen sınırına en kısa uzaklığı."""
    p = np.asarray(p, float)
    P = np.asarray(P, float)
    A = P
    B = np.roll(P, -1, axis=0)
    AB = B - A
    t = np.clip(np.einsum("ij,ij->i", p - A, AB) / np.einsum("ij,ij->i", AB, AB), 0.0, 1.0)
    Q = A + t[:, None] * AB
    return float(np.min(np.linalg.norm(Q - p, axis=1)))


def bolge_sinirina_uzaklik(p, region) -> float:
    return min(kenara_uzaklik(p, P) for P in (region.outer, *region.holes))


def dogru_ortusmesi(e1: Line2D, e2: Line2D, tol: float = 1e-6) -> float:
    """İki doğru parçası aynı doğru üzerindeyse ortak kısmın boyu; değilse 0."""
    p0, p1 = np.asarray(e1.p0, float), np.asarray(e1.p1, float)
    q0, q1 = np.asarray(e2.p0, float), np.asarray(e2.p1, float)
    L = np.linalg.norm(p1 - p0)
    if L < tol or np.linalg.norm(q1 - q0) < tol:
        return 0.0
    t = (p1 - p0) / L
    n = np.array([-t[1], t[0]])
    if abs(n @ (q0 - p0)) > tol or abs(n @ (q1 - p0)) > tol:
        return 0.0
    s0, s1 = sorted((t @ (q0 - p0), t @ (q1 - p0)))
    return max(0.0, min(L, s1) - max(0.0, s0))


def en_buyuk_ortusme(entities, layers=("GORUNUR", "GIZLI")) -> float:
    """Verilen katmanlardaki tüm doğru parçası çiftlerinin en büyük örtüşme boyu."""
    L = [e for e in entities if isinstance(e, Line2D) and e.layer in layers]
    m = 0.0
    for i in range(len(L)):
        for j in range(i + 1, len(L)):
            m = max(m, dogru_ortusmesi(L[i], L[j]))
    return m
