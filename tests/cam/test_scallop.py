"""SPEC 06 — cam/scallop.py testleri (K9).

Testler sadece SPEC 06 "İz (scallop) yüksekliği" ve "Arayüz" bölümlerinden yazıldı; uygulama kodu
okunmadı. Eğri yüzey formülü, iki takım dairesinin alt zarfının açı boyunca sık örneklenmesiyle
(tests/cam/ref3d.envelope_ridge_bruteforce, kapalı form kullanmaz) bağımsız kontrol edilir.

Kaynaklar:
- Düzlem: iki komşu küre kesiti arasında sırt, merkezlerin ortasında: h = R − √(R² − (s/2)²);
  Taylor: h = s²/(8R) + s⁴/(128R³) + … (Altintas, Manufacturing Automation, 2. bas., 8. bölüm).
- Ters formül: (R − h)² + (s/2)² = R² → s = 2√(2Rh − h²).
"""

from __future__ import annotations

import math

import pytest

from cam.model import CamError
from cam.scallop import scallop_curved, scallop_flat, scallop_torus, stepover_flat
from tests.cam.ref3d import envelope_ridge_bruteforce
from tests.cam.ref3d_ek import profil


@pytest.mark.parametrize("R, s", [(3.0, 1.5), (5.0, 0.2), (1.0, 2.0), (2.5, 0.0), (10.0, 7.3)])
def test_k9_duzlem_kesin(R, s):
    assert scallop_flat(R, s) == pytest.approx(R - math.sqrt(R * R - (s / 2) ** 2), abs=1e-12)


def test_k9_duzlem_ozel_degerler():
    assert scallop_flat(3.0, 0.0) == 0.0
    assert scallop_flat(2.0, 4.0) == pytest.approx(2.0, abs=1e-12)  # s = 2R: sırt R yüksekliğinde


@pytest.mark.parametrize("R", [1.0, 3.0, 8.0])
def test_k9_kucuk_s_yaklasimi(R):
    """h / (s²/8R) − 1 = x/4 + x²/8 + …, x = s²/(4R²): küçük s'de yaklaşım hatası s²'yle küçülür."""
    for s in (0.2, 0.05, 0.02):
        h = scallop_flat(R, s)
        rel = h / (s * s / (8 * R)) - 1
        assert rel == pytest.approx(s * s / (16 * R * R), rel=1e-2, abs=1e-12)


@pytest.mark.parametrize("R, h", [(3.0, 0.01), (5.0, 0.05), (1.0, 1.0), (2.0, 0.7), (6.0, 0.2)])
def test_k9_stepover_ters(R, h):
    s = stepover_flat(R, h)
    assert s == pytest.approx(2 * math.sqrt(2 * R * h - h * h), rel=1e-12)
    assert scallop_flat(R, s) == pytest.approx(h, rel=1e-12)


@pytest.mark.parametrize("R, s", [(3.0, 1.5), (4.0, 0.3), (2.0, 3.9)])
def test_k9_gidis_donus(R, s):
    assert stepover_flat(R, scallop_flat(R, s)) == pytest.approx(s, rel=1e-12)


@pytest.mark.parametrize("convex", [True, False], ids=["disbukey", "icbukey"])
def test_k9_egri_duzleme_iner(convex):
    """ρ → ∞, α·ρ = s sabit: eğri formül düzlem formülüne O(1/ρ) ile yaklaşır."""
    R, s = 3.0, 1.5
    hf = scallop_flat(R, s)
    farklar = []
    for rho in (1e2, 1e3, 1e4, 1e5, 1e6):
        farklar.append(abs(scallop_curved(R, rho, s / rho, convex) - hf))
    assert farklar[-1] < 1e-6
    for a, b in zip(farklar, farklar[1:], strict=False):
        assert b < a
    # O(1/ρ): ρ·fark sınırlı
    assert 1e6 * farklar[-1] < 2 * 1e2 * farklar[0]


@pytest.mark.parametrize(
    "R, rho, alpha",
    [(3.0, 20.0, 0.1), (3.0, 20.0, 0.02), (5.0, 8.0, 0.3), (2.0, 30.0, 0.05), (1.0, 4.0, 0.4)],
)
def test_k9_disbukey_kaba_kuvvet(R, rho, alpha):
    beklenen = envelope_ridge_bruteforce(R, rho, alpha, convex=True)
    assert scallop_curved(R, rho, alpha, convex=True) == pytest.approx(beklenen, abs=1e-6)


@pytest.mark.parametrize(
    "R, rho, alpha",
    [(3.0, 20.0, 0.1), (3.0, 20.0, 0.02), (5.0, 8.0, 0.3), (2.0, 30.0, 0.05), (1.0, 4.0, 0.4)],
)
def test_k9_icbukey_kaba_kuvvet(R, rho, alpha):
    beklenen = envelope_ridge_bruteforce(R, rho, alpha, convex=False)
    assert scallop_curved(R, rho, alpha, convex=False) == pytest.approx(beklenen, abs=1e-6)


def test_k9_egrilik_yonu():
    """Aynı α ve ρ'da dışbükey yüzeyde sırt düzlemden büyük, içbükeyde küçük (aynı yay boyu s = αρ)."""
    R, rho, alpha = 3.0, 20.0, 0.1
    hf = scallop_flat(R, alpha * rho)
    assert scallop_curved(R, rho, alpha, True) > hf > scallop_curved(R, rho, alpha, False)


def test_k9_alpha_sifir():
    assert scallop_curved(3.0, 20.0, 0.0, True) == pytest.approx(0.0, abs=1e-12)
    assert scallop_curved(3.0, 20.0, 0.0, False) == pytest.approx(0.0, abs=1e-12)


@pytest.mark.parametrize(
    "R, s",
    [(0.0, 1.0), (-1.0, 1.0), (3.0, -0.1), (3.0, 6.0001), (3.0, math.nan), (math.nan, 1.0)],
)
def test_k9_duzlem_hatali(R, s):
    with pytest.raises(CamError):
        scallop_flat(R, s)


@pytest.mark.parametrize("R, h", [(3.0, 0.0), (3.0, -0.1), (3.0, 3.0001), (0.0, 0.1), (3.0, math.nan)])
def test_k9_stepover_hatali(R, h):
    with pytest.raises(CamError):
        stepover_flat(R, h)


@pytest.mark.parametrize(
    "R, rho, alpha, convex",
    [
        pytest.param(3.0, 20.0, -0.01, True, id="alpha-negatif"),
        pytest.param(3.0, 0.0, 0.1, True, id="rho-sifir"),
        pytest.param(3.0, -5.0, 0.1, False, id="rho-negatif"),
        pytest.param(3.0, 3.0, 0.1, False, id="icbukey-rho-esit-R"),
        pytest.param(3.0, 2.0, 0.1, False, id="icbukey-rho-kucuk"),
        # c·sin(α/2) > R: küreler kesişmiyor (c = 23, α = 0.3 → 3.43 > 3)
        pytest.param(3.0, 20.0, 0.3, True, id="disbukey-kesismiyor"),
        # c = 17, α = 0.4 → 3.38 > 3
        pytest.param(3.0, 20.0, 0.4, False, id="icbukey-kesismiyor"),
        pytest.param(3.0, 20.0, math.nan, True, id="nan"),
    ],
)
def test_k9_egri_hatali(R, rho, alpha, convex):
    with pytest.raises(CamError):
        scallop_curved(R, rho, alpha, convex)


# --- SPEC 06b K11: torik uç ----------------------------------------------------------------------
# Yatay düzlemde iki komşu torik profil (aralık s) alt zarfının sırtı orta noktadadır: h = f(s/2);
# f SPEC 06b profil tablosundan (tests/cam/ref3d_ek.profil) bağımsız hesaplanır.


@pytest.mark.parametrize(
    "R, r_c, s", [(4.0, 1.0, 6.5), (4.0, 1.0, 8.0), (5.0, 3.5, 4.0), (3.0, 0.2, 5.9), (2.0, 2.0, 1.5)]
)
def test_k11_torik_formul(R, r_c, s):
    Rt = R - r_c
    beklenen = 0.0 if s <= 2 * Rt else r_c - math.sqrt(r_c * r_c - (s / 2 - Rt) ** 2)
    h = scallop_torus(R, r_c, s)
    assert h == pytest.approx(beklenen, abs=1e-12)
    assert h == pytest.approx(float(profil("torik", R, r_c)(s / 2)), abs=1e-12)


@pytest.mark.parametrize("s", [0.0, 1.0, 5.9, 6.0])
def test_k11_torik_duz_bolge_sifir(s):
    assert scallop_torus(4.0, 1.0, s) == 0.0  # s ≤ 2R_t = 6


@pytest.mark.parametrize("s", [0.0, 3.0, 7.9, 8.0])
def test_k11_torik_rc0_sifir(s):
    assert scallop_torus(4.0, 0.0, s) == pytest.approx(0.0, abs=1e-12)  # düz uç, s ≤ 2R


@pytest.mark.parametrize("R, s", [(3.0, 1.5), (5.0, 0.2), (2.0, 4.0), (4.0, 7.3)])
def test_k11_torik_rcR_kuresel(R, s):
    assert scallop_torus(R, R, s) == pytest.approx(scallop_flat(R, s), abs=1e-12)


@pytest.mark.parametrize(
    "R, r_c, s",
    [
        pytest.param(0.0, 0.0, 1.0, id="R=0"),
        pytest.param(-2.0, 0.5, 1.0, id="R<0"),
        pytest.param(4.0, -0.1, 1.0, id="rc<0"),
        pytest.param(4.0, 4.1, 1.0, id="rc>R"),
        pytest.param(4.0, 1.0, -0.5, id="s<0"),
        pytest.param(4.0, 1.0, 8.01, id="s>2R"),
        pytest.param(4.0, 1.0, math.nan, id="s-nan"),
    ],
)
def test_k11_torik_hatali(R, r_c, s):
    with pytest.raises(CamError):
        scallop_torus(R, r_c, s)
