"""SPEC 18 K1, K2 — kararlı yüz referansı: ölçü değişimi, araya giren özellik, bastırma, bölünen / birleşen /
silinen yüz (T1–T4).

Testler SPEC 18 "Topolojik adlandırma" teorisinden ve kabul tablosundan yazıldı; uygulama okunmadı.
Blok B = 100 × 60 × 20 (min köşe orijinde). "Cep" = `FaceRef("blok", "zmax")`'a bağlı profil, 40 × 30
dikdörtgen, merkez dünya (50, 30), 8 mm kesim.

Yüze bağlı eskiz düzlemi varsayımı (SPEC 26 `face_plane` kuralı, SPEC 18 bunu ağaçta yeniden hesaplar):
origin = yüzün ağırlık merkezi, normal = dışa bakan normal, xdir = dünya X'in izdüşümü. Bu yüzden cep bölgesi
uv'de (0, 0) merkezli verilir. Araya giren özellik üst yüzün ağırlık merkezini değiştirmeyecek biçimde
(x = 50'ye göre simetrik iki delik) seçildi; böylece test, ağırlık merkezi kaymasının nasıl ele alındığına
bağlı değildir.
"""

from __future__ import annotations

import math

import pytest

pytest.importorskip("build123d", reason='build123d kurulu değil (pip install -e ".[cad]")')

from geometry.agac import Agac, Blok, Delik, EdgeRef, Ekstruzyon, Profil, Yuvarlatma, insa  # noqa: E402
from geometry.part import GeometryError  # noqa: E402
from tests.geometry.agac_ortak import (  # noqa: E402
    KONUM,
    REL,
    TABAN,
    UST_20,
    dikdortgen,
    duzlemsel,
    rapor,
    ref,
    silindirik,
    yakin,
)

pytestmark = pytest.mark.occt


def cep_agaci(c: float = 20.0, araya_delik: bool = False) -> Agac:
    ozellikler = [Blok("blok", 100, 60, c)]
    if araya_delik:  # x = 50'ye göre simetrik: üst yüzün ağırlık merkezi değişmez
        ozellikler.append(Delik("delik", UST_20, ((10, 30), (90, 30)), d=6.0))
    ozellikler += [
        Profil("p", ref("blok:zmax"), (dikdortgen(-20, -15, 20, 15),)),
        Ekstruzyon("cep", "p", 8.0, islem="kes"),
    ]
    return Agac(tuple(ozellikler))


def tek_duzlem(part, ad: str):
    idx = part.find(ref(ad))
    assert len(idx) == 1, f"{ad}: {idx}"
    return duzlemsel(part, idx[0])


# --- T1 ---------------------------------------------------------------------------------------------------


def test_t1_cep_hacmi_ve_taban():
    s = insa(cep_agaci())
    assert s.basarili
    assert s.part.volume == pytest.approx(120000 - 9600, rel=REL)
    son = tek_duzlem(s.part, "cep:son")
    assert son.origin[2] == pytest.approx(12.0, abs=KONUM)
    assert yakin(son.origin, (50, 30, 12))
    assert son.area == pytest.approx(1200, rel=REL)
    assert yakin(son.normal, (0, 0, 1))


def test_t1_cep_yan_yuzleri():
    s = insa(cep_agaci())
    beklenen = {
        "alt": (320, (50, 15)),
        "sag": (240, (70, 30)),
        "ust": (320, (50, 45)),
        "sol": (240, (30, 30)),
    }
    for src, (alan, xy) in beklenen.items():
        f = tek_duzlem(s.part, f"cep:yan:{src}")
        assert f.area == pytest.approx(alan, rel=REL)
        assert yakin(f.origin, (*xy, 16))


def test_t1_kesimde_bas_kapagi_silinir_ve_adlar_raporlanir():
    s = insa(cep_agaci())
    assert ref("cep:bas") not in s.part.names
    r = rapor(s, "cep")
    assert r.durum == "tamam"
    assert abs(r.dV) == pytest.approx(9600, rel=REL)
    assert set(r.adlar) == {
        ref(a) for a in ("cep:son", "cep:yan:alt", "cep:yan:sag", "cep:yan:ust", "cep:yan:sol")
    }


def test_t1_ters_arama():
    s = insa(cep_agaci())
    (i,) = s.part.find(ref("cep:son"))
    assert ref("cep:son") in s.part.face_refs(i)
    (j,) = s.part.find(ref("blok:zmin"))
    assert s.part.face_refs(j) == (ref("blok:zmin"),)


# --- T2: ölçü değişimi --------------------------------------------------------------------------------------


def test_t2_blok_yuksekligi_degisince_eskiz_yuzle_gider():
    s = insa(cep_agaci(c=30.0))
    assert s.basarili
    assert s.part.volume == pytest.approx(180000 - 9600, rel=REL)
    son = tek_duzlem(s.part, "cep:son")
    assert yakin(son.origin, (50, 30, 22))
    assert son.area == pytest.approx(1200, rel=REL)


# --- K1: araya giren özellik, farklı OCCT index'i -----------------------------------------------------------


def test_k1_araya_giren_ozellik_farkli_index_ayni_yuz():
    s1 = insa(cep_agaci())
    s2 = insa(cep_agaci(araya_delik=True))
    assert s1.basarili and s2.basarili
    assert s1.part.volume - s2.part.volume == pytest.approx(2 * math.pi * 9 * 20, rel=REL)
    ortak = sorted(set(s1.part.names) & set(s2.part.names), key=str)
    assert ref("cep:son") in ortak
    # aynı ad, iki kurulumda farklı OCCT index'i (en az bir ad)
    assert any(s1.part.find(r) != s2.part.find(r) for r in ortak)
    # ...ama her ad aynı geometrik yüze çözülür
    for ad in ("cep:son", "cep:yan:alt", "cep:yan:sag", "blok:zmin", "blok:xmax", "blok:ymin"):
        f1, f2 = tek_duzlem(s1.part, ad), tek_duzlem(s2.part, ad)
        assert yakin(f1.origin, f2.origin, tol=1e-6)
        assert yakin(f1.normal, f2.normal)


# --- T3 / T4: bastırma, yuvarlatma kenarı aynı kalır --------------------------------------------------------


def yuvarlatma_agaci(bastir_delik: bool) -> Agac:
    return Agac(
        (
            Blok("blok", 100, 60, 20),
            Delik("delik", UST_20, ((20, 30),), d=10.0, bastir=bastir_delik),
            Yuvarlatma("yuv", (EdgeRef(ref("blok:zmax"), ref("blok:ymin")),), 4.0),
        )
    )


def yuvarlatma_yuzu(part):
    idx = part.find(ref("yuv:0"))
    assert len(idx) == 1
    return silindirik(part, idx[0])


def test_t3_t4_bastirma_sonrasi_ayni_kenar():
    k = (1 - math.pi / 4) * 16 * 100
    s3 = insa(yuvarlatma_agaci(False))
    s4 = insa(yuvarlatma_agaci(True))
    assert s3.basarili and s4.basarili
    assert s3.part.volume == pytest.approx(120000 - 500 * math.pi - k, rel=REL)
    assert s4.part.volume == pytest.approx(120000 - k, rel=REL)
    assert rapor(s4, "delik").durum == "bastirildi"
    for s in (s3, s4):
        f = yuvarlatma_yuzu(s.part)
        assert f.radius == pytest.approx(4.0, rel=REL)
        assert abs(abs(f.axis[0]) - 1.0) < 1e-9  # kenar X yönünde
        assert yakin(f.origin[1:], (4, 16))  # eksen y = 4, z = 16: y = 0, z = 20 kenarı
        assert f.length == pytest.approx(100, rel=REL)


# --- K2: bölünen, birleşen, silinen yüz ---------------------------------------------------------------------


def test_k2_kanal_ust_yuzu_boler():
    a = Agac(
        (
            Blok("blok", 100, 60, 20),
            Profil("pk", UST_20, (dikdortgen(45, -5, 55, 65),)),
            Ekstruzyon("kanal", "pk", 5.0, islem="kes"),
        )
    )
    s = insa(a)
    assert s.basarili
    idx = s.part.find(ref("blok:zmax"))
    assert len(idx) == 2
    yuzler = [duzlemsel(s.part, i) for i in idx]
    for f in yuzler:
        assert f.origin[2] == pytest.approx(20.0, abs=KONUM)
    assert sum(f.area for f in yuzler) == pytest.approx(6000 - 10 * 60, rel=REL)
    assert list(idx) == sorted(set(idx))  # artan, tekrarsız
    taban = tek_duzlem(s.part, "kanal:son")
    assert taban.origin[2] == pytest.approx(15.0, abs=KONUM)
    assert taban.area == pytest.approx(600, rel=REL)


def test_k2_es_duzlemli_fuzyon_adlari_birlestirir():
    a = Agac(
        (
            Blok("blok", 100, 60, 20),
            Profil("pe", TABAN, (dikdortgen(100, 0, 140, 60),)),
            Ekstruzyon("ek", "pe", 20.0, islem="ekle"),
        )
    )
    s = insa(a)
    assert s.basarili
    assert s.part.volume == pytest.approx(120000 + 48000, rel=REL)
    ust = s.part.find(ref("blok:zmax"))
    assert len(ust) == 1
    assert s.part.find(ref("ek:son")) == ust
    f = duzlemsel(s.part, ust[0])
    assert f.area == pytest.approx(140 * 60, rel=REL)
    assert set(s.part.face_refs(ust[0])) >= {ref("blok:zmax"), ref("ek:son")}
    # birleşen yan yüzler de iki adı taşır; eski temas yüzleri silinir
    assert s.part.find(ref("blok:ymin")) == s.part.find(ref("ek:yan:alt"))
    assert ref("blok:xmax") not in s.part.names
    assert ref("ek:yan:sol") not in s.part.names


def test_k2_silinen_yuzun_adi_duser():
    a = Agac(
        (
            Blok("blok", 100, 60, 20),
            Profil("pk", UST_20, (dikdortgen(90, -5, 110, 65),)),
            Ekstruzyon("kes", "pk", 1.0, islem="kes", bitis="boydan_boya"),
        )
    )
    s = insa(a)
    assert s.basarili
    assert s.part.volume == pytest.approx(90 * 60 * 20, rel=REL)
    assert ref("blok:xmax") not in s.part.names
    with pytest.raises(GeometryError, match="referans bulunamadı"):
        s.part.find(ref("blok:xmax"))
    # en yakın yüze geri dönüş yok: kesimin x = 90 duvarı yalnız kendi adını taşır
    duvar = tek_duzlem(s.part, "kes:yan:sol")
    assert duvar.origin[0] == pytest.approx(90.0, abs=KONUM)
    assert ref("blok:xmax") not in s.part.face_refs(s.part.find(ref("kes:yan:sol"))[0])


def test_k2_silinen_yuze_bagli_ozellik_hata_verir():
    a = Agac(
        (
            Blok("blok", 100, 60, 20),
            Profil("pk", UST_20, (dikdortgen(90, -5, 110, 65),)),
            Ekstruzyon("kes", "pk", 1.0, islem="kes", bitis="boydan_boya"),
            Profil("p2", ref("blok:xmax"), (dikdortgen(-5, -5, 5, 5),)),
        )
    )
    s = insa(a)
    assert not s.basarili
    assert rapor(s, "p2").durum == "hata"
    assert s.part.volume == pytest.approx(90 * 60 * 20, rel=REL)
