"""SPEC 62 — K4: ISO 286 sınır sapmaları (tezgah/tolerans.py). OCCT ve FastAPI gerektirmez.

Beklenen değerler SPEC 62 Teori §2 ve K4'ten; ek alanlar ISO 286-2 tablolarından (6–10 mm aralığı:
IT6 = 9, IT7 = 15, IT8 = 22, IT9 = 36, IT10 = 58, IT11 = 90 µm; temel sapmalar f = −13, g = −5, k = +1,
m = +6, n = +10, p = +15 µm). Uygulama gövdeleri okunmadı. Girdi ve dönüş mm.
"""

from __future__ import annotations

import pytest

from tezgah.komut import KomutError
from tezgah.tolerans import hedef_cap, sapma

ABS = 1e-12  # mm


@pytest.mark.parametrize(
    "alan, d, ust, alt",
    [
        # SPEC 62 K4
        ("H7", 10.0, 0.015, 0.0),
        ("h7", 10.0, 0.0, -0.015),
        ("g6", 10.0, -0.005, -0.014),
        ("k6", 10.0, 0.010, 0.001),
        ("H7", 20.0, 0.021, 0.0),
        ("H7", 6.0, 0.012, 0.0),
        # aralık sınırı "üstü … dahil": Ø10 → 6–10, Ø10.001 → 10–18 (IT7 = 18)
        ("H7", 10.001, 0.018, 0.0),
    ],
)
def test_k4_sapmalar(alan, d, ust, alt):
    u, a = sapma(alan, d)
    assert u == pytest.approx(ust, abs=ABS)
    assert a == pytest.approx(alt, abs=ABS)


@pytest.mark.parametrize(
    "alan, ust, alt",
    [
        ("H6", 0.009, 0.0),
        ("H8", 0.022, 0.0),
        ("H9", 0.036, 0.0),
        ("H10", 0.058, 0.0),
        ("H11", 0.090, 0.0),
        ("h6", 0.0, -0.009),
        ("h8", 0.0, -0.022),
        ("h9", 0.0, -0.036),
        ("h10", 0.0, -0.058),
        ("h11", 0.0, -0.090),
        ("f7", -0.013, -0.028),
        ("js6", 0.0045, -0.0045),
        ("m6", 0.015, 0.006),
        ("n6", 0.019, 0.010),
        ("p6", 0.024, 0.015),
    ],
)
def test_ilk_surum_alanlari_o10(alan, ust, alt):
    """İlk sürüm alanlarının hepsi tabloda: Ø10 (6–10 aralığı), ISO 286-2."""
    u, a = sapma(alan, 10.0)
    assert u == pytest.approx(ust, abs=ABS)
    assert a == pytest.approx(alt, abs=ABS)


def test_ust_alttan_buyuk_ya_da_esit():
    for alan in ("H6", "H7", "H11", "h6", "h11", "g6", "f7", "js6", "k6", "m6", "n6", "p6"):
        for d in (1.0, 3.0, 10.0, 18.0, 30.0, 120.0, 500.0):
            u, a = sapma(alan, d)
            assert u > a


@pytest.mark.parametrize(
    "alan, d, beklenen",
    [("H7", 10.0, 10.0075), ("h7", 10.0, 9.9925), ("g6", 10.0, 9.9905), ("k6", 10.0, 10.0055)],
)
def test_hedef_cap(alan, d, beklenen):
    """d_hedef = d + (üst + alt)/2."""
    assert hedef_cap(alan, d) == pytest.approx(beklenen, abs=ABS)


@pytest.mark.parametrize(
    "alan, d",
    [("Z9", 10.0), ("H7", 0.0), ("H7", -5.0), ("H7", 600.0), ("H7", 500.001), ("", 10.0), ("H", 10.0)],
)
def test_gecersiz_hata(alan, d):
    with pytest.raises(KomutError):
        sapma(alan, d)


def test_hedef_cap_gecersiz_hata():
    with pytest.raises(KomutError):
        hedef_cap("Z9", 10.0)


def test_sinir_500_dahil():
    """İlk sürüm 1–500 mm: d = 500 tabloda (400–500 aralığı)."""
    u, a = sapma("H7", 500.0)
    assert a == 0.0 and u > 0
