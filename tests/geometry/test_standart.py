"""SPEC 35 — geometry/standart testleri: ISO ölçü tabloları, tanım ayrıştırma, parametrik parçalar (K1–K6).

Testler sadece specs/35-standart-parca.md'deki "Teori", "Ölçü tabloları", "Arayüz" ve "Kabul kriterleri"
bölümlerinden yazıldı; uygulama gövdeleri okunmadı. Beklenen tablolar SPEC metninden ayrıca yazıldı.
- Tablo ve tanım testleri OCCT'siz koşar (tablo.py saf Python).
- Parça üretici testleri (parcalar.py) `@pytest.mark.occt` işaretlidir.
Basit geometri (SPEC 35): diş / pah / yuvarlatma yok; altıgen köşeleri keskin, A_6 = (√3/2) s².
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from geometry.part import GeometryError
from geometry.standart import tablo
from geometry.standart.tablo import (
    ISO15,
    ISO273,
    ISO2338,
    ISO4017,
    ISO4032,
    ISO4762,
    ISO7089,
    L_SERI_PIM,
    L_SERI_VIDA,
    P_KABA,
    ayristir,
    boyut,
    gecis_olcusu,
    tanim,
    vida_boyu,
)

OLCULER = ["M3", "M4", "M5", "M6", "M8", "M10", "M12", "M14", "M16", "M20", "M24"]
D = {M: float(M[1:]) for M in OLCULER}

# ---------------------------------------------------------------- SPEC metninden beklenen tablolar
# ISO 4762: (d_k, k, s, t, L_min, L_maks)
BEK_4762 = {
    "M3": (5.5, 3, 2.5, 1.3, 5, 30),
    "M4": (7, 4, 3, 2.0, 6, 40),
    "M5": (8.5, 5, 4, 2.5, 8, 50),
    "M6": (10, 6, 5, 3.0, 10, 60),
    "M8": (13, 8, 6, 4.0, 12, 80),
    "M10": (16, 10, 8, 5.0, 16, 100),
    "M12": (18, 12, 10, 6.0, 20, 120),
    "M14": (21, 14, 12, 7.0, 25, 140),
    "M16": (24, 16, 14, 8.0, 25, 160),
    "M20": (30, 20, 17, 10.0, 30, 200),
    "M24": (36, 24, 19, 12.0, 40, 200),
}
# M: (s, k_4017, L_min_4017, L_maks_4017, m_4032, d1, d2, h)
BEK_ALTIGEN = {
    "M3": (5.5, 2.0, 6, 30, 2.4, 3.2, 7, 0.5),
    "M4": (7, 2.8, 8, 40, 3.2, 4.3, 9, 0.8),
    "M5": (8, 3.5, 10, 50, 4.7, 5.3, 10, 1.0),
    "M6": (10, 4.0, 12, 60, 5.2, 6.4, 12, 1.6),
    "M8": (13, 5.3, 16, 80, 6.8, 8.4, 16, 1.6),
    "M10": (16, 6.4, 20, 100, 8.4, 10.5, 20, 2.0),
    "M12": (18, 7.5, 25, 120, 10.8, 13, 24, 2.5),
    "M14": (21, 8.8, 30, 140, 12.8, 15, 28, 2.5),
    "M16": (24, 10.0, 30, 200, 14.8, 17, 30, 3.0),
    "M20": (30, 12.5, 40, 200, 18.0, 21, 37, 3.0),
    "M24": (36, 15.0, 50, 200, 21.5, 25, 44, 4.0),
}
BEK_273 = {
    "M3": (3.2, 3.4, 3.6),
    "M4": (4.3, 4.5, 4.8),
    "M5": (5.3, 5.5, 5.8),
    "M6": (6.4, 6.6, 7.0),
    "M8": (8.4, 9.0, 10.0),
    "M10": (10.5, 11.0, 12.0),
    "M12": (13.0, 13.5, 14.5),
    "M14": (15.0, 15.5, 16.5),
    "M16": (17.0, 17.5, 18.5),
    "M20": (21.0, 22.0, 24.0),
    "M24": (25.0, 26.0, 28.0),
}
BEK_SERI_VIDA = (5, 6, 8, 10, 12, 16, 20, 25, 30, 35, 40, 45, 50, 55, 60, 65, 70, 80, 90, 100,
                 110, 120, 130, 140, 150, 160, 180, 200)  # fmt: skip
BEK_SERI_PIM = (4, 5, 6, 8, 10, 12, 14, 16, 18, 20, 22, 24, 26, 28, 30, 32, 35, 40, 45, 50, 55, 60,
                65, 70, 75, 80, 85, 90, 95, 100, 120, 140, 160, 180, 200)  # fmt: skip
BEK_2338 = {
    2.0: (6, 20),
    2.5: (6, 24),
    3.0: (8, 30),
    4.0: (8, 40),
    5.0: (10, 50),
    6.0: (12, 60),
    8.0: (14, 80),
    10.0: (18, 95),
    12.0: (22, 140),
    16.0: (26, 180),
    20.0: (35, 200),
}
BEK_15 = {
    "6000": (10, 26, 8),
    "6001": (12, 28, 8),
    "6002": (15, 32, 9),
    "6003": (17, 35, 10),
    "6004": (20, 42, 12),
    "6005": (25, 47, 12),
    "6006": (30, 55, 13),
    "6007": (35, 62, 14),
    "6008": (40, 68, 15),
    "6200": (10, 30, 9),
    "6201": (12, 32, 10),
    "6202": (15, 35, 11),
    "6203": (17, 40, 12),
    "6204": (20, 47, 14),
    "6205": (25, 52, 15),
    "6206": (30, 62, 16),
    "6207": (35, 72, 17),
    "6208": (40, 80, 18),
}
# SPEC 23 THREADS_COARSE (tablo.P_KABA bunun kopyası)
BEK_P = {"M3": 0.5, "M4": 0.7, "M5": 0.8, "M6": 1.0, "M8": 1.25, "M10": 1.5, "M12": 1.75,
         "M14": 2.0, "M16": 2.0, "M20": 2.5, "M24": 3.0}  # fmt: skip


def _ayni(gercek, beklenen) -> None:
    assert len(gercek) == len(beklenen)
    for g, b in zip(gercek, beklenen, strict=True):
        assert float(g) == pytest.approx(float(b), abs=1e-12)


def A6(s: float) -> float:
    """Düzgün altıgen alanı, anahtar ağzı s: (√3/2) s²."""
    return math.sqrt(3) / 2 * s**2


# ---------------------------------------------------------------- K1 tablolar
def test_k1_ornek_degerler_birebir():
    """K1: SPEC'teki örnek satırlar birebir."""
    _ayni(ISO4762["M8"], (13, 8, 6, 4, 12, 80))
    _ayni(ISO4017["M8"], (13, 5.3, 16, 80))
    _ayni(ISO4032["M8"], (13, 6.8))
    _ayni(ISO7089["M8"], (8.4, 16, 1.6))
    _ayni(ISO273["M8"], (8.4, 9, 10))
    _ayni(ISO15["6204"], (20, 47, 14))


def test_k1_tablolar_spec_ile_ayni():
    """K1: bütün tablolar SPEC metnindeki değerlerle satır satır aynı, fazlası / eksiği yok."""
    assert set(ISO4762) == set(OLCULER)
    assert set(ISO4017) == set(OLCULER)
    assert set(ISO4032) == set(OLCULER)
    assert set(ISO7089) == set(OLCULER)
    assert set(ISO273) == set(OLCULER)
    for M in OLCULER:
        _ayni(ISO4762[M], BEK_4762[M])
        s, k, l0, l1, m, d1, d2, h = BEK_ALTIGEN[M]
        _ayni(ISO4017[M], (s, k, l0, l1))
        _ayni(ISO4032[M], (s, m))
        _ayni(ISO7089[M], (d1, d2, h))
        _ayni(ISO273[M], BEK_273[M])
        assert P_KABA[M] == pytest.approx(BEK_P[M], abs=1e-12)
    assert set(P_KABA) == set(OLCULER)
    assert set(ISO15) == set(BEK_15)
    for kod, satir in BEK_15.items():
        _ayni(ISO15[kod], satir)
    assert {float(d) for d in ISO2338} == set(BEK_2338)
    for d, satir in BEK_2338.items():
        _ayni(ISO2338[d], satir)
    _ayni(L_SERI_VIDA, BEK_SERI_VIDA)
    _ayni(L_SERI_PIM, BEK_SERI_PIM)


def test_k1_seriler_artan():
    """K1: boy serileri kesin artan."""
    for seri in (L_SERI_VIDA, L_SERI_PIM):
        assert all(a < b for a, b in zip(seri[:-1], seri[1:], strict=True))


@pytest.mark.parametrize("M", OLCULER)
def test_k1_iso4762_tutarlilik(M):
    """K1: d_k > d, k = d, t < k, lokma köşesi 2s/√3 < d_k."""
    d_k, k, s, t, _, _ = ISO4762[M]
    d = D[M]
    assert d_k > d
    assert k == pytest.approx(d, abs=1e-12)
    assert t < k
    assert 2 * s / math.sqrt(3) < d_k


@pytest.mark.parametrize("M", OLCULER)
def test_k1_altigen_ve_pul_tutarlilik(M):
    """K1: s > d; civata ve somunda s aynı; pul d₁ > d, d₂ > s."""
    s, _, _, _ = ISO4017[M]
    s_somun, _ = ISO4032[M]
    d1, d2, _ = ISO7089[M]
    d = D[M]
    assert s > d
    assert s_somun == pytest.approx(s, abs=1e-12)
    assert d1 > d
    assert d2 > s


def test_k1_iso273_tutarlilik():
    """K1: ince > d, ince < orta < kaba; ardışık satırlarda kaba(M_i) < ince(M_{i+1})."""
    for M in OLCULER:
        ince, orta, kaba = ISO273[M]
        assert ince > D[M]
        assert ince < orta < kaba
    for Mi, Mj in zip(OLCULER[:-1], OLCULER[1:], strict=True):
        assert ISO273[Mi][2] < ISO273[Mj][0]


def test_k1_rulman_ve_pim_tutarlilik():
    """K1: rulmanda d < D, B > 0; pimde aralık uçları L serisinde."""
    for d, Dd, B in ISO15.values():
        assert d < Dd
        assert B > 0
    seri = {float(v) for v in L_SERI_PIM}
    for L_min, L_maks in ISO2338.values():
        assert float(L_min) in seri
        assert float(L_maks) in seri
        assert L_min < L_maks


@pytest.mark.occt
def test_k1_spec23_tablolari_ile_capraz():
    """K1: 273 orta = CBORE_ISO4762[M][0]; lamba çapı CBORE_ISO4762[M][1] > d_k; P_KABA = THREADS_COARSE."""
    from geometry.holes import CBORE_ISO4762, THREADS_COARSE

    for M in OLCULER:
        assert ISO273[M][1] == pytest.approx(CBORE_ISO4762[M][0], abs=1e-12)
        assert CBORE_ISO4762[M][1] > ISO4762[M][0]
        assert P_KABA[M] == pytest.approx(THREADS_COARSE[M], abs=1e-12)


# ---------------------------------------------------------------- K2 boyut, gecis_olcusu, vida_boyu
def test_k2_boyut():
    """K2: "M8" → 8.0; tabloda olmayan ölçü → GeometryError."""
    assert boyut("M8") == pytest.approx(8.0)
    assert boyut("M24") == pytest.approx(24.0)
    for kotu in ("M7", "M30", "8", "m8", ""):
        with pytest.raises(GeometryError):
            boyut(kotu)


@pytest.mark.parametrize(
    ("d", "M"),
    [
        (6.6, "M6"),
        (9.0, "M8"),
        (10.0, "M8"),
        (8.4, "M8"),  # ince uç
        (8.4 - 1e-7, "M8"),  # uç toleransı 1e-6 içinde
        (10.0 + 1e-7, "M8"),
        (3.2, "M3"),
        (28.0, "M24"),
        (13.0, "M12"),
        (8.0, None),  # M6 kaba (7.0) ile M8 ince (8.4) arası
        (8.4 - 1e-5, None),
        (10.0 + 1e-5, None),
        (3.0, None),
        (28.1, None),
    ],
)
def test_k2_gecis_olcusu(d, M):
    """K2: ISO 273 ince − 1e-6 ≤ d ≤ kaba + 1e-6 olan tek M; yoksa None."""
    assert gecis_olcusu(d) == M


def test_k2_gecis_olcusu_her_satir():
    """K2: her satırın ince, orta, kaba çapı kendi M'sini verir."""
    for M, satir in ISO273.items():
        for d in satir:
            assert gecis_olcusu(d) == M


@pytest.mark.parametrize(
    ("M", "L_min", "seri", "L"),
    [
        ("M8", 9.4, "4762", 12.0),
        ("M8", 28.0, "4762", 30.0),
        ("M8", 81.0, "4762", None),
        ("M8", 37.5, "4017", 40.0),
        ("M8", 12.0, "4762", 12.0),  # eşit boy kabul
        ("M8", 12.0 + 1e-10, "4762", 12.0),  # L ≥ L_min − 1e-9
        ("M8", 12.0 + 1e-6, "4762", 16.0),
        ("M8", 1.0, "4762", 12.0),  # aralığın altı → aralığın ilk seri boyu
        ("M8", 1.0, "4017", 16.0),
        ("M8", 80.0, "4762", 80.0),
        ("M8", 80.0, "4017", 80.0),
        ("M3", 31.0, "4762", None),
        ("M24", 41.0, "4762", 45.0),
        ("M16", 165.0, "4017", 180.0),
        ("M16", 165.0, "4762", None),
    ],
)
def test_k2_vida_boyu(M, L_min, seri, L):
    """K2: seri ∩ aralıkta L ≥ L_min − 1e-9 olan en küçük boy; yoksa None."""
    sonuc = vida_boyu(M, L_min, seri=seri)
    if L is None:
        assert sonuc is None
    else:
        assert sonuc == pytest.approx(L, abs=1e-12)


def test_k2_vida_boyu_varsayilan_seri_4762():
    """K2: seri verilmezse ISO 4762."""
    assert vida_boyu("M8", 9.4) == pytest.approx(12.0)


# ---------------------------------------------------------------- K2 ayristir / tanim
def test_k2_ayristir_imbus_ornek():
    """K2: SPEC örneği "ISO 4762 M8x25" → ("4762", {"M": "M8", "L": 25.0})."""
    std, olcu = ayristir("ISO 4762 M8x25")
    assert std == "4762"
    assert olcu == {"M": "M8", "L": 25.0}


def test_k2_ayristir_digerleri():
    """K2: civata, somun, pul, pim, rulman tanımları ayrışıyor."""
    assert ayristir("ISO 4017 M8x40") == ("4017", {"M": "M8", "L": 40.0})
    assert ayristir("ISO 4032 M8") == ("4032", {"M": "M8"})
    assert ayristir("ISO 7089 M8") == ("7089", {"M": "M8"})
    std, olcu = ayristir("ISO 2338 6x30")
    assert std == "2338"
    assert sorted(float(v) for v in olcu.values()) == [6.0, 30.0]
    std, olcu = ayristir("ISO 15 6204")
    assert std == "15"
    assert "6204" in [str(v) for v in olcu.values()]


@pytest.mark.parametrize(
    "t",
    [
        "ISO 4762 M8x25",
        "ISO 4762 M3x5",
        "ISO 4762 M24x200",
        "ISO 4017 M8x40",
        "ISO 4017 M16x180",
        "ISO 4032 M8",
        "ISO 4032 M20",
        "ISO 7089 M8",
        "ISO 7089 M3",
        "ISO 2338 6x30",
        "ISO 2338 2.5x10",
        "ISO 2338 20x200",
        "ISO 15 6204",
        "ISO 15 6000",
    ],
)
def test_k2_ayristir_tanim_gidis_donus(t):
    """K2: tanim(*ayristir(t)) == t (kanonik yazım)."""
    std, olcu = ayristir(t)
    assert tanim(std, **olcu) == t


def test_k2_tanim_tamsayi_ondaliksiz():
    """K2: tanim("4762", M="M8", L=25) → "ISO 4762 M8x25"; L tamsayı değerliyse ondalıksız."""
    assert tanim("4762", M="M8", L=25) == "ISO 4762 M8x25"
    assert tanim("4762", M="M8", L=25.0) == "ISO 4762 M8x25"
    assert tanim("4017", M="M8", L=40.0) == "ISO 4017 M8x40"
    assert tanim("4032", M="M8") == "ISO 4032 M8"
    assert tanim("7089", M="M8") == "ISO 7089 M8"


@pytest.mark.parametrize(
    "kotu",
    [
        "ISO 4762 M8x27",  # seride yok
        "ISO 4762 M7x20",  # tabloda olmayan ölçü
        "iso 4762 M8x25",  # küçük harf
        "ISO 15 6309",  # tabloda olmayan rulman
        "ISO 4762 M8x10",  # seride var, aralık (12–80) dışı
        "ISO 4762 M8x90",  # seride var, aralık dışı
        "ISO 4017 M8x12",  # 4017 M8 aralığı 16–80
        "ISO  4762 M8x25",  # çift boşluk
        "ISO 4762 m8x25",
        "ISO 4762 M8",  # boy eksik
        "ISO 4032 M8x25",  # somunda boy olmaz
        "ISO 9999 M8x25",  # bilinmeyen standart
        "ISO 2338 6x70",  # d6 aralığı 12–60
        "ISO 2338 7x30",  # tabloda olmayan pim çapı
        "ISO 2338 6x31",  # pim serisinde yok
        "",
        "M8x25",
    ],
)
def test_k2_ayristir_hatali(kotu):
    """K2: bozuk yazım, bilinmeyen standart / ölçü, seride veya aralıkta olmayan L → GeometryError."""
    with pytest.raises(GeometryError):
        ayristir(kotu)


def test_tablo_occt_import_etmez():
    """Paket sınırı: tablo modülü saf Python (build123d'yi modül düzeyinde içe aktarmaz)."""
    assert "build123d" not in vars(tablo)
    assert "bd" not in vars(tablo)


# ---------------------------------------------------------------- K3–K5 parçalar (OCCT)
def _kutu(p):
    lo, hi = p.bbox
    return np.asarray(lo, dtype=float), np.asarray(hi, dtype=float)


@pytest.mark.occt
@pytest.mark.parametrize(("M", "L"), [("M3", 10.0), ("M8", 25.0), ("M24", 100.0)])
def test_k3_imbus_vida(M, L):
    """K3: V = π d_k² k/4 − A_6(s) t + π d² L/4; kutu x,y ∈ ±d_k/2, z ∈ [−L, k]; ağırlık merkezi eksende."""
    from geometry.standart.parcalar import socket_screw

    d_k, k, s, t, _, _ = BEK_4762[M]
    d = D[M]
    p = socket_screw(M, L)
    V = math.pi * d_k**2 * k / 4 - A6(s) * t + math.pi * d**2 * L / 4
    assert p.volume == pytest.approx(V, rel=1e-6)
    lo, hi = _kutu(p)
    np.testing.assert_allclose(lo, [-d_k / 2, -d_k / 2, -L], atol=1e-6)
    np.testing.assert_allclose(hi, [d_k / 2, d_k / 2, k], atol=1e-6)
    c = np.asarray(p.center_of_mass, dtype=float)
    assert abs(c[0]) <= 1e-6 and abs(c[1]) <= 1e-6
    assert p.name == tanim("4762", M=M, L=L)
    assert tuple(p.holes) == ()


@pytest.mark.occt
@pytest.mark.parametrize(("M", "L"), [("M6", 30.0), ("M8", 40.0), ("M20", 100.0)])
def test_k4_altigen_civata(M, L):
    """K4: V = A_6(s) k + π d² L/4; kutu x ∈ ±s/2, y ∈ ±s/√3, z ∈ [−L, k]."""
    from geometry.standart.parcalar import hex_bolt

    s, k, _, _, _, _, _, _ = BEK_ALTIGEN[M]
    d = D[M]
    p = hex_bolt(M, L)
    assert p.volume == pytest.approx(A6(s) * k + math.pi * d**2 * L / 4, rel=1e-6)
    lo, hi = _kutu(p)
    np.testing.assert_allclose(lo, [-s / 2, -s / math.sqrt(3), -L], atol=1e-6)
    np.testing.assert_allclose(hi, [s / 2, s / math.sqrt(3), k], atol=1e-6)
    c = np.asarray(p.center_of_mass, dtype=float)
    assert abs(c[0]) <= 1e-6 and abs(c[1]) <= 1e-6
    assert p.name == tanim("4017", M=M, L=L)


@pytest.mark.occt
@pytest.mark.parametrize("M", ["M6", "M8", "M20"])
def test_k4_somun(M):
    """K4: V = (A_6(s) − π d²/4) m; kutu x ∈ ±s/2, y ∈ ±s/√3, z ∈ [0, m]."""
    from geometry.standart.parcalar import hex_nut

    s, _, _, _, m, _, _, _ = BEK_ALTIGEN[M]
    d = D[M]
    p = hex_nut(M)
    assert p.volume == pytest.approx((A6(s) - math.pi * d**2 / 4) * m, rel=1e-6)
    lo, hi = _kutu(p)
    np.testing.assert_allclose(lo, [-s / 2, -s / math.sqrt(3), 0.0], atol=1e-6)
    np.testing.assert_allclose(hi, [s / 2, s / math.sqrt(3), m], atol=1e-6)
    assert p.name == tanim("4032", M=M)


@pytest.mark.occt
@pytest.mark.parametrize("M", ["M6", "M8", "M20"])
def test_k4_pul(M):
    """K4: V = π (d₂² − d₁²) h/4; kutu x,y ∈ ±d₂/2, z ∈ [0, h]."""
    from geometry.standart.parcalar import washer

    _, _, _, _, _, d1, d2, h = BEK_ALTIGEN[M]
    p = washer(M)
    assert p.volume == pytest.approx(math.pi * (d2**2 - d1**2) * h / 4, rel=1e-6)
    lo, hi = _kutu(p)
    np.testing.assert_allclose(lo, [-d2 / 2, -d2 / 2, 0.0], atol=1e-6)
    np.testing.assert_allclose(hi, [d2 / 2, d2 / 2, h], atol=1e-6)
    assert p.name == tanim("7089", M=M)


@pytest.mark.occt
@pytest.mark.parametrize(("d", "L"), [(6.0, 30.0), (10.0, 18.0)])
def test_k5_pim(d, L):
    """K5: V = π d² L/4; kutu x,y ∈ ±d/2, z ∈ [0, L]; parca(tanım) aynı ad ve hacim."""
    from geometry.standart.parcalar import dowel_pin, parca

    p = dowel_pin(d, L)
    assert p.volume == pytest.approx(math.pi * d**2 * L / 4, rel=1e-6)
    lo, hi = _kutu(p)
    np.testing.assert_allclose(lo, [-d / 2, -d / 2, 0.0], atol=1e-6)
    np.testing.assert_allclose(hi, [d / 2, d / 2, L], atol=1e-6)
    t = f"ISO 2338 {d:g}x{L:g}"
    assert p.name == t
    q = parca(t)
    assert q.name == t
    assert q.volume == pytest.approx(p.volume, rel=1e-9)


@pytest.mark.occt
@pytest.mark.parametrize("kod", ["6000", "6204", "6208"])
def test_k5_rulman(kod):
    """K5: zarf halka V = π (D² − d²) B/4; kutu x,y ∈ ±D/2, z ∈ [0, B]; parca(tanım) aynı ad ve hacim."""
    from geometry.standart.parcalar import bearing, parca

    d, Dd, B = BEK_15[kod]
    p = bearing(kod)
    assert p.volume == pytest.approx(math.pi * (Dd**2 - d**2) * B / 4, rel=1e-6)
    lo, hi = _kutu(p)
    np.testing.assert_allclose(lo, [-Dd / 2, -Dd / 2, 0.0], atol=1e-6)
    np.testing.assert_allclose(hi, [Dd / 2, Dd / 2, B], atol=1e-6)
    t = f"ISO 15 {kod}"
    assert p.name == t
    q = parca(t)
    assert q.name == t
    assert q.volume == pytest.approx(p.volume, rel=1e-9)


@pytest.mark.occt
@pytest.mark.parametrize(
    ("t", "uretici", "args"),
    [
        ("ISO 4762 M8x25", "socket_screw", ("M8", 25.0)),
        ("ISO 4017 M8x40", "hex_bolt", ("M8", 40.0)),
        ("ISO 4032 M8", "hex_nut", ("M8",)),
        ("ISO 7089 M8", "washer", ("M8",)),
    ],
)
def test_k5_parca_dogrudan_ureticiyle_ayni(t, uretici, args):
    """K5: parca(tanım).name == tanım; doğrudan üretici ile aynı hacim; her çağrıda aynı hacim."""
    from geometry.standart import parcalar

    p = parcalar.parca(t)
    q = getattr(parcalar, uretici)(*args)
    assert p.name == t
    assert q.name == t
    assert p.volume == pytest.approx(q.volume, rel=1e-9)
    assert parcalar.parca(t).volume == pytest.approx(p.volume, rel=1e-12)


# ---------------------------------------------------------------- K6 üretici hataları
@pytest.mark.occt
@pytest.mark.parametrize(
    ("uretici", "args"),
    [
        ("socket_screw", ("M8", 27.0)),  # seride yok
        ("socket_screw", ("M8", 10.0)),  # aralık dışı (12–80)
        ("socket_screw", ("M8", 90.0)),
        ("socket_screw", ("M7", 20.0)),  # tablo dışı M
        ("hex_bolt", ("M8", 10.0)),  # aralık dışı (16–80)
        ("hex_bolt", ("M8", 90.0)),
        ("hex_bolt", ("M8", 37.0)),
        ("hex_nut", ("M7",)),
        ("washer", ("M30",)),
        ("bearing", ("6309",)),
        ("dowel_pin", (6.0, 70.0)),  # d6 aralığı 12–60
        ("dowel_pin", (6.0, 10.0)),
        ("dowel_pin", (6.0, 31.0)),  # pim serisinde yok
        ("dowel_pin", (7.0, 30.0)),  # tablo dışı d
    ],
)
def test_k6_uretici_hatalari(uretici, args):
    """K6: tablo dışı ölçü, seri / aralık dışı L → GeometryError (sessiz yuvarlama yok)."""
    from geometry.standart import parcalar

    with pytest.raises(GeometryError):
        getattr(parcalar, uretici)(*args)


@pytest.mark.occt
@pytest.mark.parametrize("kotu", ["ISO 4762 M8x27", "ISO 4762 M8x90", "ISO 15 6309", "iso 4032 M8"])
def test_k6_parca_hatali_tanim(kotu):
    """K6: parca() hatalı tanımda GeometryError."""
    from geometry.standart.parcalar import parca

    with pytest.raises(GeometryError):
        parca(kotu)
