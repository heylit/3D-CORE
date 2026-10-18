"""SPEC 62 — K1, K2, K3, K9 (birinci aşama): komut paleti dilbilgisi, hata / öneri, yerleşim ve /cozumle ucu.

Testler SPEC 62 metninden (Teori §1, Arayüz, Kabul kriterleri) ve iskeletin sabitlediği arayüzden
(`tezgah/komut.py` modül açıklaması: adım anahtarları; `durum/62-tezgah-deneyim.md` arayüz notları) yazıldı;
uygulama gövdeleri okunmadı. `tests/tezgah/test_komut.py` SPEC 24'ün CLI testidir, bu dosya ondan ayrıdır.

Beklenen değerlerin kaynağı:
- d_hedef = d + (ES + EI)/2, Ø10 H7 = +0.015 / 0 → 10.0075 (SPEC 62 Teori §2, K4).
- M8 → d = 6.8, M8x1 → d = 7.0 (SPEC 62 K1, kılavuz matkabı).
- Hacim farkı π d²/4 · derinlik (SPEC 26 hacim denetimi, K3).
"""

from __future__ import annotations

import copy
import math

import pytest

from tezgah.komut import Cozum, KomutError, cozumle, normallestir, ornekler, yerlestir

# --- K1: dilbilgisi tablosu -------------------------------------------------------------------------

DELIK_10_20 = {"tur": "delik", "cesit": "duz", "d": 10.0, "derinlik": 20.0}

K1 = [
    ("Ø10 delik, 20 derin", DELIK_10_20),
    ("ø10 delik, 20 derin, H7", {**DELIK_10_20, "tolerans": "H7", "d_hedef": 10.0075}),
    ("delik ⌀6,8 boydan boya", {"tur": "delik", "cesit": "duz", "d": 6.8, "derinlik": None}),
    ("M8 dis, derin 16", {"tur": "delik", "cesit": "dis", "thread": "M8", "d": 6.8, "derinlik": 16.0}),
    ("M8x1 dis, derin 16", {"tur": "delik", "cesit": "dis", "thread": "M8x1", "d": 7.0, "derinlik": 16.0}),
    (
        "Ø6.6 delik, boydan boya, havşa 12x90",
        {"tur": "delik", "cesit": "havsa", "d": 6.6, "derinlik": None, "csk_d": 12.0, "csk_angle": 90.0},
    ),
    (
        "Ø9 delik, boydan boya, lamba Ø15 derin 9",
        {"tur": "delik", "cesit": "lamba", "d": 9.0, "derinlik": None, "cbore_d": 15.0, "cbore_depth": 9.0},
    ),
    ("cep 40x20 derin 5", {"tur": "cep", "w": 40.0, "l": 20.0, "r": 0.0, "derinlik": 5.0}),
    ("cep 40 × 20, r 3, derin 5", {"tur": "cep", "w": 40.0, "l": 20.0, "r": 3.0, "derinlik": 5.0}),
    ("pah 1x45", {"tur": "pah", "d": 1.0, "aci": 45.0}),
    ("pah 2", {"tur": "pah", "d": 2.0, "aci": 45.0}),
    ("fillet 3", {"tur": "fillet", "r": 3.0}),
    ("kanal 8x4", {"tur": "kanal", "genislik": 8.0, "derinlik": 4.0}),
    ("Ø10 delik, 20 derin, adet 4, aralık 25", {**DELIK_10_20, "adet": 4, "aralik": 25.0}),
    ("Ø10 DELİK, 20 DERİN", DELIK_10_20),
]


def adim_esit(gercek: dict, beklenen: dict) -> None:
    """Sözlük eşitliği; sayılar float (adet int), float'lar 1e-12 içinde, diğerleri tam eşit."""
    assert set(gercek) == set(beklenen), f"anahtarlar: {sorted(gercek)} ≠ {sorted(beklenen)}"
    for k, b in beklenen.items():
        g = gercek[k]
        if b is None:
            assert g is None, k
        elif isinstance(b, float):
            assert type(g) is float, f"{k}: {type(g).__name__} (float bekleniyor)"
            assert g == pytest.approx(b, rel=1e-12, abs=1e-12), k
        elif isinstance(b, int):
            assert type(g) is int and g == b, k
        else:
            assert g == b, k


@pytest.mark.parametrize("metin, beklenen", K1, ids=[m for m, _ in K1])
def test_k1_dilbilgisi(metin, beklenen):
    c = cozumle(metin)
    assert isinstance(c, Cozum)
    adim_esit(c.adim, beklenen)
    assert isinstance(c.aciklama, str) and c.aciklama.strip()


def test_k1_secim_adimi_degistirmez():
    """secim yalnız açıklama içindir: yerleşimsiz adım aynı kalır."""
    secim = {"duzlem": {"tur": "XY", "ofset": 12.0}, "nokta": [50.0, 10.0]}
    adim_esit(cozumle("Ø10 delik, 20 derin", secim).adim, DELIK_10_20)


def test_ornekler_kendi_ile_tutarli():
    """Paletin yardım listesi K1 tablosuyla aynı kaynaktır: her örnek, verdiği adıma çözülür."""
    liste = ornekler()
    assert liste
    for metin, adim in liste:
        adim_esit(cozumle(metin).adim, adim)
    beklenen = dict(K1)
    for metin, adim in liste:
        if metin in beklenen:
            adim_esit(adim, beklenen[metin])


# --- normalleştirme (Teori §1) ----------------------------------------------------------------------


def test_normallestir_turkce_kucuk_harf():
    assert normallestir("DELİK") == "delik"
    assert normallestir("DERİN") == "derin"
    assert normallestir("KILAVUZ") == "kılavuz"  # I → ı


def test_normallestir_cap_isaretleri():
    tek = {normallestir(s) for s in ("Ø10", "ø10", "⌀10")}
    assert len(tek) == 1
    assert "Ø" in tek.pop()
    n = normallestir("çap 10")
    assert "Ø" in n and "çap" not in n


def test_normallestir_ondalik_virgul_ve_ayrac():
    assert "6.8" in normallestir("⌀6,8")
    n = normallestir("Ø10 delik, 20 derin")
    assert "," in n  # ardından boşluk gelen virgül ayraçtır


def test_normallestir_carpi():
    assert normallestir("40*20") == normallestir("40×20") == normallestir("40X20") == "40x20"


def test_normallestir_derin_esanlamlilari():
    assert normallestir("derinlik 20") == "derin 20"
    n = normallestir("d=20")
    assert "derin" in n and "d=" not in n


def test_normallestir_tek_bosluk():
    assert normallestir("cep   40x20    derin  5") == "cep 40x20 derin 5"


# --- K2: hata ve öneri ------------------------------------------------------------------------------


def test_k2_oneri_levenshtein():
    with pytest.raises(KomutError) as e:
        cozumle("deilk Ø10 20 derin")
    assert any("delik" in o for o in e.value.oneriler)


def test_k2_derinlik_eksik():
    with pytest.raises(KomutError) as e:
        cozumle("Ø10 delik")
    m = str(e.value)
    assert "derinliği eksik" in m.lower()
    assert "Ø10 delik, 20 derin" in m
    assert "Ø10 delik, boydan boya" in m


def test_k2_iki_anlamli_r():
    """ "r 5" tek başına: fillet mi, cep köşesi mi? Tahmin edilmez, iki okuma listelenir."""
    with pytest.raises(KomutError) as e:
        cozumle("r 5")
    ok = e.value.okumalar
    assert len(ok) >= 2
    assert any("fillet" in o.lower() for o in ok)
    assert any("cep" in o.lower() for o in ok)


@pytest.mark.parametrize("metin", ["derin 20, derin 25", "Ø10 delik, derin 20, derin 25"])
def test_k2_ayni_nitelik_iki_kez(metin):
    with pytest.raises(KomutError):
        cozumle(metin)


@pytest.mark.parametrize(
    "metin",
    [
        "",
        "   ",
        "12",
        "10 20",
        "Ø0 delik, 20 derin",
        "Ø-10 delik, 20 derin",
        "Ø10 delik, derin 0",
        "Ø10 delik, derin -5",
        "cep 40x0 derin 5",
        "cep 40x20 derin -5",
        "pah 0",
        "fillet 0",
        "kanal 8x0",
    ],
)
def test_k2_gecersiz_girdi(metin):
    with pytest.raises(KomutError):
        cozumle(metin)


def test_k2_komut_hatasi_valueerror():
    assert issubclass(KomutError, ValueError)


# --- K3: seçimsiz / seçimli yerleşim ----------------------------------------------------------------


def _flans():
    from tezgah.modelleme import ornek_model

    return ornek_model("flans")


def test_k3_secimsiz_hata_model_degismez():
    model = _flans()
    once = copy.deepcopy(model)
    adim = {"tur": "delik", "cesit": "duz", "d": 10.0, "derinlik": 5.0}
    with pytest.raises(KomutError) as e:
        yerlestir(adim, None, model)
    assert "Önce bir yüz seçin" in str(e.value)
    assert model == once


def test_k3_cep_ilk_surumde_yerlesmez():
    """SPEC 26'da cep adımı yok: ilk sürümde yerleşim reddedilir (iskelet arayüzü)."""
    model = _flans()
    once = copy.deepcopy(model)
    secim = {"duzlem": {"tur": "XY", "ofset": 12.0}, "nokta": [50.0, 35.0]}
    with pytest.raises(KomutError):
        yerlestir({"tur": "cep", "w": 10.0, "l": 10.0, "r": 0.0, "derinlik": 2.0}, secim, model)
    assert model == once


@pytest.mark.occt
def test_k3_secili_yuzde_delik_hacmi():
    """Flanş üst yüzü (z = 12), nokta (50, 10): Ø10 × 5 kör delik → ΔV = π d²/4 · t (rel 1e-6).

    Nokta cebe (32–68 × 23–47) ve köşe deliklerine (12/88, 12/58) değmez; delik 5 ≤ y ≤ 15, 7 ≤ z ≤ 12.
    """
    pytest.importorskip("build123d", reason='build123d kurulu değil (pip install -e ".[cad]")')
    from tezgah.modelleme import HACIM_REL, insa

    model = _flans()
    once = copy.deepcopy(model)
    d, t = 10.0, 5.0
    adim = cozumle("Ø10 delik, 5 derin").adim
    secim = {"duzlem": {"tur": "XY", "ofset": 12.0}, "nokta": [50.0, 10.0]}
    yeni_adimlar = yerlestir(adim, secim, model)
    assert model == once
    assert isinstance(yeni_adimlar, list) and yeni_adimlar
    assert yeni_adimlar[-1]["tur"] == "delik"
    eski_kimlikler = {a["kimlik"] for a in model["adimlar"]}
    yeni_kimlikler = [a["kimlik"] for a in yeni_adimlar]
    assert len(set(yeni_kimlikler)) == len(yeni_kimlikler)
    assert not eski_kimlikler & set(yeni_kimlikler)

    yeni = copy.deepcopy(model)
    yeni["adimlar"] = model["adimlar"] + yeni_adimlar
    p0, r0 = insa(model)
    p1, r1 = insa(yeni)
    assert r0.hata is None and r1.hata is None
    assert p0.volume - p1.volume == pytest.approx(math.pi * d**2 / 4 * t, rel=HACIM_REL)


# --- K9: /api/ekran/komut/cozumle ucu ---------------------------------------------------------------


@pytest.fixture
def istemci():
    pytest.importorskip("fastapi")
    pytest.importorskip("httpx")
    from fastapi.testclient import TestClient

    from tezgah.sunucu import uygulama

    return TestClient(uygulama(dist=None))


UC = "/api/ekran/komut/cozumle"


@pytest.mark.parametrize("metin, beklenen", [K1[0], K1[1]], ids=["duz", "H7"])
def test_k9_cozumle_ucu(istemci, metin, beklenen):
    r = istemci.post(UC, json={"metin": metin, "secim": None})
    assert r.status_code == 200, r.text
    g = r.json()
    assert g["sema"] == 1
    adim_esit(g["adim"], beklenen)
    adim_esit(g["adim"], cozumle(metin).adim)
    assert isinstance(g["aciklama"], str) and g["aciklama"]


def test_k9_cozumle_ucu_422_oneriler(istemci):
    r = istemci.post(UC, json={"metin": "deilk Ø10 20 derin"})
    assert r.status_code == 422, r.text
    g = r.json()  # SPEC 62 Uçlar: 422 {detail, oneriler, okumalar}
    assert isinstance(g["detail"], str) and g["detail"]
    assert any("delik" in o for o in g["oneriler"])
    assert isinstance(g["okumalar"], list)


def test_k9_ekran_kaydinda():
    pytest.importorskip("fastapi")
    from tezgah.ekranlar import KABUK_KISAYOLLARI, ekranlar

    kayit = {e.ad: e for e in ekranlar()}
    assert "komut" in kayit
    e = kayit["komut"]
    assert e.hazir is None or e.hazir() is None
    assert e.tus not in KABUK_KISAYOLLARI
