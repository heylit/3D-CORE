"""SPEC 22 K3, K4 — takım kesiti (kesici bölge, gövde uzantısı, tutucu) ve süpürme aralığı.

Testler SPEC 22 "Kesici bölge" ve "Doğrusal hareketin süpürmesi" bölümlerinden yazıldı; cam.sim kodu okunmadı.

Kaynaklar (SPEC 22):
- e(α) = (−cos α, sin α), (z, x); e₁ = e(κr), e₂ = e(κr + εr); Q = üçgen(C, C + l·e₁, C + l·e₂).
- GROOVE: T = 3 → C_L = C, T = 4 → C_L = C − (w − 2r, 0); Q = [C_L,z, C_L,z + w − 2r] × [C_L,x, C_L,x + l].
- Gövde: Q_B = {C + s·e₁ + t·e₂ : s, t ≥ 0, s + t ≥ l}; kanalda Q'nun x ≥ C_L,x + l uzantısı.
- İç çerçeve: x → −x aynası. Tutucu K'ye girerse (alan > 1e-9 mm²) CamError.
- S = conv(Q(P0) ∪ Q(P1)) ⊕ D(r); z doğrusuyla kesişim [a, b]; kesişmeyen a = +inf, b = −inf.
- x → r: a ≥ 0 → [a, b]; b ≤ 0 → [−b, −a]; aksi [0, max(−a, b)]; tutucu kalınlığı üst uçta √(x² + b²).
Referans: tests/cam/lsimref.py (kesin dışbükey ⊕ disk kesişimi ve ≥ 10⁵ konumlu kaba kuvvet).
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from cam.model import CamError, LatheHolder
from cam.sim import cutter_shape, sweep_interval, to_radial
from tests.cam.lsimref import (
    bore_tool,
    brute_sweep_x,
    e,
    groove_tool,
    sweep_x,
    thread_tool,
    turn_tool,
)

L = 8.0
R = 0.8


def _ayni_kume(P: np.ndarray, beklenen: np.ndarray, tol: float = 1e-12) -> None:
    """P'nin satırları beklenen noktaların bir permütasyonu (tol içinde)."""
    P = np.asarray(P, dtype=float)
    assert P.shape == beklenen.shape
    kalan = list(range(len(beklenen)))
    for p in P:
        d = [np.max(np.abs(p - beklenen[j])) for j in kalan]
        j = int(np.argmin(d))
        assert d[j] <= tol, f"{p} beklenen köşelerde yok: {beklenen}"
        kalan.pop(j)


def _st(P: np.ndarray, e1: np.ndarray, e2: np.ndarray) -> np.ndarray:
    """P = s·e₁ + t·e₂ çözümü, (n, 2) → (s, t)."""
    M = np.column_stack([e1, e2])
    return np.linalg.solve(M, np.asarray(P, dtype=float).T).T


# ------------------------------------------------------------------ K3 kesici şekil


def test_K3_tornalama_cekirdek_ucgen():
    """T = 3, κr = 93°, εr = 80°: köşeler C, C + l·e(93°), C + l·e(173°) (C = 0)."""
    s = cutter_shape(turn_tool(R, L), "dis")
    beklenen = np.array([[0.0, 0.0], L * e(93.0), L * e(173.0)])
    # kapalı form: e(93°) = (−cos 93°, sin 93°) = (0.05234, 0.99863)
    assert beklenen[1, 0] == pytest.approx(-L * math.cos(math.radians(93.0)), abs=1e-15)
    _ayni_kume(s.core, beklenen)
    assert s.r == pytest.approx(R)
    assert s.holder is None


def test_K3_bore_aynasi():
    t = bore_tool(r=0.4, edge=6.0)
    s = cutter_shape(t, "ic")
    beklenen = np.array([[0.0, 0.0], 6.0 * e(93.0), 6.0 * e(173.0)]) * np.array([1.0, -1.0])
    _ayni_kume(s.core, beklenen)
    assert s.r == pytest.approx(0.4)


def test_K3_dis_ucu_simetrik():
    """60° diş ucu (κr = εr = 60°): e₁ = (−½, √3/2), e₂ = (½, √3/2)."""
    s = cutter_shape(thread_tool(r=0.1, edge=3.0), "dis")
    h = math.sqrt(3) / 2
    _ayni_kume(s.core, np.array([[0.0, 0.0], [-1.5, 3 * h], [1.5, 3 * h]]))


@pytest.mark.parametrize(("tip", "zl"), [(3, 0.0), (4, -2.4)])
def test_K3_kanal_dikdortgeni(tip, zl):
    """w = 3, r = 0.3, l = 6: Q = [C_L,z, C_L,z + 2.4] × [0, 6]; T = 4'te C_L = C − (2.4, 0)."""
    s = cutter_shape(groove_tool(tip=tip, w=3.0, r=0.3, edge=6.0), "dis")
    beklenen = np.array([[zl, 0.0], [zl + 2.4, 0.0], [zl + 2.4, 6.0], [zl, 6.0]])
    _ayni_kume(s.core, beklenen)
    assert s.r == pytest.approx(0.3)
    # gövde: aynı genişlikte, x ≥ l yukarı uzantı
    B = np.asarray(s.body, dtype=float)
    assert np.all(B[:, 0] >= zl - 1e-12) and np.all(B[:, 0] <= zl + 2.4 + 1e-12)
    assert np.all(B[:, 1] >= 6.0 - 1e-12)
    for p in ([zl, 6.0], [zl + 2.4, 6.0]):
        assert np.min(np.max(np.abs(B - np.array(p)), axis=1)) <= 1e-12
    assert B[:, 1].max() >= 6.0 + 1.0


def test_K3_tornalama_govde_uzantisi():
    """Q_B köşeleri s, t ≥ 0, s + t ≥ l; l·e₁ ve l·e₂ köşe; e₁ ve e₂ ışınları boyunca uzanır."""
    s = cutter_shape(turn_tool(R, L), "dis")
    e1, e2 = e(93.0), e(173.0)
    B = np.asarray(s.body, dtype=float)
    st = _st(B, e1, e2)
    assert np.all(st >= -1e-9)
    assert np.all(st.sum(axis=1) >= L - 1e-9)
    for p in (L * e1, L * e2):
        assert np.min(np.max(np.abs(B - p), axis=1)) <= 1e-12
    # iki ışın boyunca l'den uzağa uzanan köşeler
    assert np.any((st[:, 1] <= 1e-9) & (st[:, 0] >= L + 1.0))
    assert np.any((st[:, 0] <= 1e-9) & (st[:, 1] >= L + 1.0))


def test_K3_bore_govde_aynalanir():
    t = bore_tool(r=0.4, edge=6.0)
    B = np.asarray(cutter_shape(t, "ic").body, dtype=float)
    st = _st(B * np.array([1.0, -1.0]), e(93.0), e(173.0))
    assert np.all(st >= -1e-9)
    assert np.all(st.sum(axis=1) >= 6.0 - 1e-9)


def test_K3_tutucu_dis_ve_ic():
    poly = ((-2.0, 10.0), (20.0, 10.0), (20.0, 30.0), (-2.0, 30.0))
    h = LatheHolder("dikdortgen", poly, half_width=6.0)
    s = cutter_shape(turn_tool(R, L, holder=h), "dis")
    _ayni_kume(s.holder, np.array(poly))
    assert s.half_width == pytest.approx(6.0)
    si = cutter_shape(bore_tool(r=0.4, edge=6.0, holder=h), "ic")
    _ayni_kume(si.holder, np.array(poly) * np.array([1.0, -1.0]))
    assert si.half_width == pytest.approx(6.0)


@pytest.mark.parametrize(
    "poly",
    [
        ((-1.0, -1.0), (1.0, -1.0), (1.0, 1.0), (-1.0, 1.0)),  # burun merkezini örtüyor
        ((2.0, 0.5), (12.0, 0.5), (12.0, 20.0), (2.0, 20.0)),  # çekirdek üçgenin içine giriyor
        (
            (-5.0, 8.5),
            (5.0, 8.5),
            (5.0, 20.0),
            (-5.0, 20.0),
        ),  # yalnız burun dairesi şişirmesine (l·e₁ ⊕ r) giriyor
    ],
)
def test_K3_tutucu_K_ye_girerse_hata(poly):
    h = LatheHolder("carpik", poly, half_width=5.0)
    with pytest.raises(CamError):
        cutter_shape(turn_tool(R, L, holder=h), "dis")


# ------------------------------------------------------------------ K4 süpürme aralığı


def _sw(poly, r, p0, p1, z):
    a, b = sweep_interval(np.asarray(poly, dtype=float), r, p0, p1, np.asarray(z, dtype=float))
    return np.asarray(a, dtype=float), np.asarray(b, dtype=float)


def test_K4_durağan_daire():
    """Nokta çokgen ⊕ D(r): |z − z_c| ≤ r → x_c ± √(r² − (z − z_c)²)."""
    zc, xc, r = 3.0, 7.0, 1.5
    z = np.array([1.0, 1.6, 2.2, 3.0, 3.9, 4.4, 5.2])
    a, b = _sw([[0.0, 0.0]], r, (zc, xc), (zc, xc), z)
    for zi, ai, bi in zip(z, a, b, strict=True):
        d = zi - zc
        if abs(d) <= r:
            s = math.sqrt(r * r - d * d)
            assert ai == pytest.approx(xc - s, abs=1e-12)
            assert bi == pytest.approx(xc + s, abs=1e-12)
        else:
            assert ai == math.inf and bi == -math.inf


def test_K4_durağan_yuvarlatilmis_ucgen():
    poly = np.array([[0.0, 0.0], L * e(93.0), L * e(173.0)])
    p = (2.0, 5.0)
    z = np.linspace(0.5, 11.5, 45)
    a, b = _sw(poly, R, p, p, z)
    ra, rb = sweep_x(poly, R, p, p, z)
    np.testing.assert_allclose(a, ra, rtol=0, atol=1e-12)
    np.testing.assert_allclose(b, rb, rtol=0, atol=1e-12)
    # z_c − r'nin solu ve sağ köşenin ötesi kesişmez
    a2, b2 = _sw(poly, R, p, p, np.array([2.0 - R - 0.01, 2.0 + L * e(173.0)[0] + R + 0.01]))
    assert np.all(a2 == math.inf) and np.all(b2 == -math.inf)


def test_K4_yatay_hareket_daire():
    """(z, x): (0, 5) → (10, 5), r = 1: 0 ≤ z ≤ 10'da [4, 6], uçlarda disk."""
    z = np.array([-1.5, -0.5, 0.0, 3.3, 10.0, 10.6, 11.2])
    a, b = _sw([[0.0, 0.0]], 1.0, (0.0, 5.0), (10.0, 5.0), z)
    for zi, ai, bi in zip(z, a, b, strict=True):
        d = max(0.0, -zi, zi - 10.0)
        if d <= 1.0:
            s = math.sqrt(1.0 - d * d)
            assert (ai, bi) == (pytest.approx(5.0 - s, abs=1e-12), pytest.approx(5.0 + s, abs=1e-12))
        else:
            assert ai == math.inf and bi == -math.inf


def test_K4_dusey_hareket_daire():
    """(0, 2) → (0, 8), r = 1: [2 − s, 8 + s], s = √(1 − z²)."""
    z = np.array([-0.9, -0.3, 0.0, 0.5, 0.99])
    a, b = _sw([[0.0, 0.0]], 1.0, (0.0, 2.0), (0.0, 8.0), z)
    s = np.sqrt(1.0 - z**2)
    np.testing.assert_allclose(a, 2.0 - s, rtol=0, atol=1e-12)
    np.testing.assert_allclose(b, 8.0 + s, rtol=0, atol=1e-12)


def test_K4_dusey_hareket_ucgen_kapali_form():
    """Burun ⊕ üçgen x yönünde 10 mm iner: alt uç ilk konumdan değil son konumdan, üst uç ilk konumdan."""
    poly = np.array([[0.0, 0.0], L * e(93.0), L * e(173.0)])
    p0, p1 = (0.0, 20.0), (0.0, 10.0)
    z = np.linspace(-0.7, 8.6, 32)
    a, b = _sw(poly, R, p0, p1, z)
    a1, _ = sweep_x(poly, R, p1, p1, z)
    _, b0 = sweep_x(poly, R, p0, p0, z)
    np.testing.assert_allclose(a, a1, rtol=0, atol=1e-12)
    np.testing.assert_allclose(b, b0, rtol=0, atol=1e-12)


@pytest.mark.parametrize(
    ("p0", "p1"),
    [
        ((5.0, 12.0), (-4.0, 12.0)),  # yatay (−Z, boyuna paso)
        ((1.0, 15.0), (1.0, 3.0)),  # düşey (−X, alın / dalma)
        ((6.0, 14.0), (-3.0, 6.5)),  # eğik (koni)
        ((-2.0, 4.0), (5.0, 9.0)),  # eğik (geri çekilme)
    ],
)
def test_K4_ucgen_kaba_kuvvetle(p0, p1):
    poly = np.array([[0.0, 0.0], L * e(93.0), L * e(173.0)])
    z = np.linspace(-6.0, 15.0, 57)
    a, b = _sw(poly, R, p0, p1, z)
    A, B = brute_sweep_x(poly, R, p0, p1, z)
    kes = np.isfinite(A)
    assert np.array_equal(np.isfinite(a), kes)
    assert np.all(a[~kes] == math.inf) and np.all(b[~kes] == -math.inf)
    np.testing.assert_allclose(a[kes], A[kes], rtol=0, atol=1e-6)
    np.testing.assert_allclose(b[kes], B[kes], rtol=0, atol=1e-6)


def test_K4_kanal_dikdortgeni_kaba_kuvvetle():
    poly = np.array([[0.0, 0.0], [2.4, 0.0], [2.4, 6.0], [0.0, 6.0]])
    p0, p1 = (3.0, 25.0), (1.0, 16.0)
    z = np.linspace(0.0, 6.5, 40)
    a, b = _sw(poly, 0.3, p0, p1, z)
    A, B = brute_sweep_x(poly, 0.3, p0, p1, z)
    kes = np.isfinite(A)
    assert np.array_equal(np.isfinite(a), kes)
    np.testing.assert_allclose(a[kes], A[kes], rtol=0, atol=1e-6)
    np.testing.assert_allclose(b[kes], B[kes], rtol=0, atol=1e-6)


@pytest.mark.parametrize(
    ("a", "b", "hw", "beklenen"),
    [
        (3.0, 4.0, 0.0, (3.0, 4.0)),
        (-4.0, -3.0, 0.0, (3.0, 4.0)),
        (-2.0, 5.0, 0.0, (0.0, 5.0)),  # eksen geçişi
        (-6.0, 1.5, 0.0, (0.0, 6.0)),
        (0.0, 2.0, 0.0, (0.0, 2.0)),
        (3.0, 4.0, 3.0, (3.0, 5.0)),  # √(4² + 3²) = 5
        (-4.0, -3.0, 3.0, (3.0, 5.0)),
        (-9.4, 1.6, 4.0, (0.0, math.hypot(9.4, 4.0))),
    ],
)
def test_K4_to_radial(a, b, hw, beklenen):
    lo, hi = to_radial(np.array([a]), np.array([b]), hw)
    assert float(np.asarray(lo)[0]) == pytest.approx(beklenen[0], abs=1e-12)
    assert float(np.asarray(hi)[0]) == pytest.approx(beklenen[1], abs=1e-12)


def test_K4_to_radial_vektor():
    a = np.array([1.0, -3.0, -1.0])
    b = np.array([2.0, -2.0, 0.5])
    lo, hi = to_radial(a, b)
    np.testing.assert_allclose(lo, [1.0, 2.0, 0.0], atol=1e-15)
    np.testing.assert_allclose(hi, [2.0, 3.0, 1.0], atol=1e-15)
