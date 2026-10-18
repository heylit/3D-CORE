"""SPEC 26 K5 — tezgah/ifade.py: güvenli ifade değerlendirici ve parametre tablosu.

Testler SPEC 26 "İfadeler" bölümünden yazıldı; tezgah/ifade.py gövdesi okunmadı. Beklenen değerler elle
hesaplandı. Dil: sayılar, + − * / **, parantez, tekli eksi, parametre adları, pi, sqrt, sin, cos, tan
(derece), abs, min, max. Başka her şey → IfadeError.
"""

from __future__ import annotations

import math

import pytest

from tezgah.ifade import IfadeError, degerlendir, parametreleri_coz

ORTAM = {"genislik": 40.0, "r": 5.0, "boy": 30.0}


# --- Tablo testi --------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "ifade, beklenen",
    [
        ("40", 40.0),
        ("=40", 40.0),
        ("2.5", 2.5),
        ("1e3", 1000.0),
        ("2 + 3 * 4", 14.0),
        ("(2 + 3) * 4", 20.0),
        ("10 - 4 - 3", 3.0),  # soldan birleşir
        ("24 / 4 / 2", 3.0),
        ("10 / 4", 2.5),
        ("-3 + 5", 2.0),
        ("-(2 + 3)", -5.0),
        ("--4", 4.0),
        ("2 * -3", -6.0),
        ("2 ** 3", 8.0),
        ("2 ** 3 ** 2", 512.0),  # sağdan birleşir
        ("-2 ** 2", -4.0),  # ** tekli eksiden önce
        ("(-2) ** 2", 4.0),
        ("2 ** -1", 0.5),
        ("pi", math.pi),
        ("2 * pi", 2 * math.pi),
        ("sqrt(16)", 4.0),
        ("sin(30)", 0.5),  # derece
        ("cos(60)", 0.5),
        ("tan(45)", 1.0),
        ("sin(-90)", -1.0),
        ("abs(-7)", 7.0),
        ("min(3, 1, 2)", 1.0),
        ("max(3, 7)", 7.0),
        ("min(4, max(1, 2))", 2.0),
        ("=genislik/2", 20.0),
        ("=2*r+3", 13.0),
        ("= genislik - 2 * r", 30.0),
        ("sqrt(genislik**2 + boy**2)", 50.0),
    ],
)
def test_tablo(ifade, beklenen):
    v = degerlendir(ifade, ORTAM)
    assert isinstance(v, float)
    assert v == pytest.approx(beklenen, rel=1e-12, abs=1e-12)


@pytest.mark.parametrize("sayi", [0, 7, -3, 2.25, 1e-3])
def test_sayi_girdisi(sayi):
    v = degerlendir(sayi)
    assert isinstance(v, float) and v == float(sayi)


def test_ortam_verilmeden_sabitler():
    assert degerlendir("2*pi") == pytest.approx(2 * math.pi, rel=1e-15)
    assert degerlendir("1 + 2") == 3.0


def test_ortam_degismez():
    ortam = dict(ORTAM)
    degerlendir("=genislik + r", ortam)
    assert ortam == ORTAM


# --- Yasak düğümler -----------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "ifade",
    [
        "__import__('os')",
        "__import__('os').system('true')",
        "genislik.real",  # öznitelik
        "(1).__class__",
        "[1, 2]",  # liste
        "[1, 2][0]",  # indeks
        "(1, 2)",  # demet
        "{1: 2}",
        "lambda: 1",
        "1 < 2",  # karşılaştırma
        "1 == 1",
        "1 if 1 else 2",
        "1 and 2",
        "not 1",
        "a = 1",  # atama
        "x := 1",
        "7 // 2",  # beyaz listede yok
        "7 % 2",
        "3 & 1",
        "1 << 2",
        "'40'",  # metin sabiti
        "open('x')",  # başka çağrı
        "eval('1')",
        "print(1)",
        "sqrt",  # çağrılmayan fonksiyon adı bir sayı değildir
        "sqrt(x=4)",  # anahtar kelimeli argüman
        "sin(*[30])",
        "f'{1}'",
        "",
        "   ",
        "=",
        "2 +",
        "(1",
    ],
)
def test_yasak_ya_da_bozuk(ifade):
    with pytest.raises(IfadeError):
        degerlendir(ifade, ORTAM)


@pytest.mark.parametrize("ifade", ["None", "...", "1j"])
def test_sayi_olmayan_sabitler(ifade):
    with pytest.raises(IfadeError):
        degerlendir(ifade)


def test_ifade_error_degerhatasi():
    assert issubclass(IfadeError, ValueError)


# --- Değerlendirme hataları ---------------------------------------------------------------------------


def test_bilinmeyen_ad_mesajda():
    with pytest.raises(IfadeError) as e:
        degerlendir("=kalinlik * 2", ORTAM)
    assert "kalinlik" in str(e.value)


@pytest.mark.parametrize("ifade", ["1/0", "=r/(r-5)", "1 / (2 - 2)", "0 ** -1"])
def test_sifira_bolme(ifade):
    with pytest.raises(IfadeError):
        degerlendir(ifade, ORTAM)


@pytest.mark.parametrize("ifade", ["10 ** 400", "1e308 * 10", "sqrt(-1)", "1e308 + 1e308", "(-8) ** 0.5"])
def test_sonsuz_nan_karmasik(ifade):
    with pytest.raises(IfadeError):
        degerlendir(ifade)


@pytest.mark.parametrize("deger", [math.inf, -math.inf, math.nan])
def test_sonlu_olmayan_sayi_girdisi(deger):
    with pytest.raises(IfadeError):
        degerlendir(deger)


def test_ortamda_sonlu_olmayan():
    with pytest.raises(IfadeError):
        degerlendir("=a + 1", {"a": math.nan})


# --- Parametre tablosu --------------------------------------------------------------------------------


def test_parametreler_topolojik_sira():
    """Tanım sırası bağımlılık sırası değil: c önce yazılmış ama b ve a'ya bağlı."""
    P = parametreleri_coz({"c": "=b + a", "b": "=a * 3", "a": "2"})
    assert P == {"a": 2.0, "b": 6.0, "c": 8.0}
    assert all(isinstance(v, float) for v in P.values())


def test_parametreler_sayi_ve_metin_karisik():
    P = parametreleri_coz({"genislik": 40, "yari": "=genislik/2", "r": 5.0, "cap": "=2*r"})
    assert P == {"genislik": 40.0, "yari": 20.0, "r": 5.0, "cap": 10.0}


def test_parametreler_bos():
    assert parametreleri_coz({}) == {}


def test_parametreler_sabit_kullanir():
    assert parametreleri_coz({"cevre": "=2*pi*r", "r": "1"})["cevre"] == pytest.approx(2 * math.pi, rel=1e-15)


def test_iki_parametre_dongusu_adlarla():
    with pytest.raises(IfadeError) as e:
        parametreleri_coz({"a": "=b", "b": "=a"})
    m = str(e.value)
    assert "a" in m and "b" in m


def test_uc_parametre_dongusu_adlarla():
    with pytest.raises(IfadeError) as e:
        parametreleri_coz(
            {"x": "1", "uzunluk": "=derinlik + 1", "derinlik": "=yukseklik * 2", "yukseklik": "=uzunluk"}
        )
    m = str(e.value)
    assert "uzunluk" in m and "derinlik" in m and "yukseklik" in m


def test_kendine_bagli_parametre():
    with pytest.raises(IfadeError) as e:
        parametreleri_coz({"kalinlik": "=kalinlik + 1"})
    assert "kalinlik" in str(e.value)


def test_parametrede_bilinmeyen_ad():
    with pytest.raises(IfadeError) as e:
        parametreleri_coz({"a": "=b + 1"})
    assert "b" in str(e.value)


def test_parametrede_yasak_dugum():
    with pytest.raises(IfadeError):
        parametreleri_coz({"a": "__import__('os')"})


def test_parametrede_sifira_bolme():
    with pytest.raises(IfadeError):
        parametreleri_coz({"a": "0", "b": "=1/a"})
