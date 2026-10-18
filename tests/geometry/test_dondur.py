"""SPEC 18 K3 — geometry/dondur.py: döndürme takım gövdesi (Pappus–Guldinus) ve yan yüz adları.

Testler SPEC 18 "Döndürme" teorisinden ve kabul tablosu T7–T9'dan yazıldı; uygulama okunmadı.
Kesit düzlemi XZ: uv = (x, z); eksen dünya Z = uv'de nokta (0, 0), yön (0, 1).
V = θ · ρ̄ · A; yan yüzey S_k = θ · ρ_k · L_k; θ < 2π ise iki kapak 2A.
"""

from __future__ import annotations

import math

import pytest

pytest.importorskip("build123d", reason='build123d kurulu değil (pip install -e ".[cad]")')

from geometry.agac import Agac, Dondurme, Profil, Silindir, insa  # noqa: E402
from geometry.dondur import revolve  # noqa: E402
from geometry.part import GeometryError  # noqa: E402
from sketch.model import Plane, SketchRegion  # noqa: E402
from tests.geometry.agac_ortak import (  # noqa: E402
    REL,
    cizgi,
    dikdortgen,
    duzlemsel,
    ref,
    silindirik,
    yay,
    yerel_adlar,
)

pytestmark = pytest.mark.occt

XZ = Plane.XZ()
EKSEN_P = (0.0, 0.0)
EKSEN_Z = (0.0, 1.0)


def halka_kesiti() -> SketchRegion:
    """T7: u ∈ [30, 40], v ∈ [0, 20]; kaynaklar alt (z = 0), sag (r = 40), ust (z = 20), sol (r = 30)."""
    return dikdortgen(30, 0, 40, 20)


# --- T7: dikdörtgen kesit, 360° ve 90° ---------------------------------------------------------------


def test_t7_halka_360_hacim_ve_alan():
    p = revolve([halka_kesiti()], XZ, EKSEN_P, EKSEN_Z, 360.0)
    assert p.volume == pytest.approx(14000 * math.pi, rel=REL)
    assert p.area == pytest.approx(2 * math.pi * (40 + 30) * 20 + 2 * math.pi * (1600 - 900), rel=REL)


def test_t7_halka_90_hacim_ve_alan():
    p = revolve([halka_kesiti()], XZ, EKSEN_P, EKSEN_Z, 90.0)
    tam = 2 * math.pi * (40 + 30) * 20 + 2 * math.pi * (1600 - 900)
    assert p.volume == pytest.approx(3500 * math.pi, rel=REL)
    assert p.area == pytest.approx(tam / 4 + 2 * 200, rel=REL)


def test_t7_yan_adlari_kenarlarla_bire_bir_360():
    p = revolve([halka_kesiti()], XZ, EKSEN_P, EKSEN_Z, 360.0)
    adlar = yerel_adlar(p)
    assert set(adlar) == {"yan:alt", "yan:sag", "yan:ust", "yan:sol"}  # 360°'de kapak yok
    for ad in adlar.values():
        assert len(ad) == 1
    dis = silindirik(p, adlar["yan:sag"][0])
    ic = silindirik(p, adlar["yan:sol"][0])
    assert dis.radius == pytest.approx(40, rel=REL)
    assert ic.radius == pytest.approx(30, rel=REL)
    assert abs(abs(dis.axis[2]) - 1.0) < 1e-9
    alt = duzlemsel(p, adlar["yan:alt"][0])
    ust = duzlemsel(p, adlar["yan:ust"][0])
    assert alt.origin[2] == pytest.approx(0.0, abs=1e-9)
    assert ust.origin[2] == pytest.approx(20.0, abs=1e-9)
    assert alt.area == pytest.approx(math.pi * (1600 - 900), rel=REL)


def test_t7_90_derecede_bas_son_kapaklari():
    p = revolve([halka_kesiti()], XZ, EKSEN_P, EKSEN_Z, 90.0)
    adlar = yerel_adlar(p)
    assert set(adlar) == {"yan:alt", "yan:sag", "yan:ust", "yan:sol", "bas", "son"}
    for kapak in ("bas", "son"):
        assert len(adlar[kapak]) == 1
        assert duzlemsel(p, adlar[kapak][0]).area == pytest.approx(200, rel=REL)
    assert silindirik(p, adlar["yan:sag"][0]).angle == pytest.approx(90, rel=REL)


# --- T8: yarım disk, tor, koni ------------------------------------------------------------------------


def test_t8_yarim_disk_kure():
    r = 10.0
    bolge = SketchRegion(
        (
            yay((0, 0), r, (0, -r), (0, r), True, "yay"),  # sağ yarım çember, CCW
            cizgi((0, r), (0, -r), "eksen"),  # eksen üzerinde: yüzey üretmez
        )
    )
    p = revolve([bolge], XZ, EKSEN_P, EKSEN_Z)
    assert p.volume == pytest.approx(4000 * math.pi / 3, rel=REL)
    assert p.area == pytest.approx(4 * math.pi * r**2, rel=REL)
    adlar = yerel_adlar(p)
    assert set(adlar) == {"yan:yay"}


def test_t8_daire_tor():
    r, R = 5.0, 20.0
    bolge = SketchRegion((yay((R, 0), r, (R + r, 0), (R + r, 0), True, "daire"),))  # tam daire
    p = revolve([bolge], XZ, EKSEN_P, EKSEN_Z)
    assert p.volume == pytest.approx(1000 * math.pi**2, rel=REL)
    assert p.area == pytest.approx(4 * math.pi**2 * R * r, rel=REL)
    assert set(yerel_adlar(p)) == {"yan:daire"}


def test_t8_dik_ucgen_koni():
    R, h = 10.0, 30.0
    bolge = SketchRegion(
        (
            cizgi((0, 0), (R, 0), "taban"),
            cizgi((R, 0), (0, h), "hipotenus"),
            cizgi((0, h), (0, 0), "eksen"),
        )
    )
    p = revolve([bolge], XZ, EKSEN_P, EKSEN_Z)
    assert p.volume == pytest.approx(1000 * math.pi, rel=REL)
    s = math.hypot(R, h)
    assert p.area == pytest.approx(math.pi * R**2 + math.pi * R * s, rel=REL)
    assert set(yerel_adlar(p)) == {"yan:taban", "yan:hipotenus"}


def test_eksen_kaydirilmis_pappus():
    """Eksen uv'de (100, 0) noktasından geçer; hacim yalnız ρ̄ ve A'ya bağlıdır."""
    p = revolve([dikdortgen(130, 0, 140, 20)], XZ, (100.0, 0.0), EKSEN_Z, 180.0)
    assert p.volume == pytest.approx(math.pi * 35 * 200, rel=REL)


# --- K3 hatalar ---------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("bolge", "aci", "eksen_y"),
    [
        ("kesen", 360.0, EKSEN_Z),  # bölge ekseni kesiyor
        ("halka", 0.0, EKSEN_Z),
        ("halka", -90.0, EKSEN_Z),
        ("halka", 360.5, EKSEN_Z),
        ("halka", 720.0, EKSEN_Z),
        ("halka", 360.0, (0.0, 0.0)),  # sıfır eksen yönü
        ("halka", math.nan, EKSEN_Z),
        ("halka", math.inf, EKSEN_Z),
    ],
)
def test_k3_hatalar(bolge, aci, eksen_y):
    b = dikdortgen(-5, 0, 5, 20) if bolge == "kesen" else halka_kesiti()
    with pytest.raises(GeometryError):
        revolve([b], XZ, EKSEN_P, eksen_y, aci)


def test_k3_bos_bolge_hata():
    with pytest.raises(GeometryError):
        revolve([], XZ, EKSEN_P, EKSEN_Z)


# --- T9: ağaçta döndürmeyle kesim (oluk) --------------------------------------------------------------


def oluk_agaci(islem: str = "kes") -> Agac:
    return Agac(
        (
            Silindir("sil", 20, 50),
            Profil("op", XZ, (dikdortgen(16, 20, 25, 30),)),
            Dondurme("oluk", "op", EKSEN_P, EKSEN_Z, 360.0, islem),
        )
    )


def test_t9_oluk_hacmi_ve_ic_yuz():
    s = insa(oluk_agaci())
    assert s.basarili
    assert s.part.volume == pytest.approx(math.pi * 400 * 50 - 1440 * math.pi, rel=REL)
    idx = s.part.find(ref("oluk:yan:sol"))  # iç kenar u = 16
    assert len(idx) == 1
    f = silindirik(s.part, idx[0])
    assert f.radius == pytest.approx(16, rel=REL)
    assert f.concave is False  # oluk dibi: malzeme içeride, yüz dışbükey silindir
    assert f.length == pytest.approx(10, rel=REL)


def test_t9_parca_disindaki_yan_yuz_silinir():
    s = insa(oluk_agaci())
    assert ref("oluk:yan:sag") not in s.part.names  # r = 25 yüzü parçanın dışında kalır
    with pytest.raises(GeometryError):
        s.part.find(ref("oluk:yan:sag"))
    # oluk silindirin yan yüzünü ikiye böler: ad iki parçaya taşınır
    assert len(s.part.find(ref("sil:yan"))) == 2


def test_dondurme_yeni_govde_agacta_adlarla():
    a = Agac(
        (
            Profil("p", XZ, (halka_kesiti(),)),
            Dondurme("d", "p", EKSEN_P, EKSEN_Z, 90.0, "yeni"),
        )
    )
    s = insa(a)
    assert s.basarili
    assert s.part.volume == pytest.approx(3500 * math.pi, rel=REL)
    for ad in ("d:yan:alt", "d:yan:sag", "d:yan:ust", "d:yan:sol", "d:bas", "d:son"):
        assert len(s.part.find(ref(ad))) == 1
