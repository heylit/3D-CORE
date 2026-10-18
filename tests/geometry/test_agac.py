"""SPEC 18 K4, K7–K12 — özellik ağacı: pah / yuvarlatma, hata yalıtımı, doğrulama ve düzenleme, önbellek,
JSON, delik ve eskiz uyumu, bağımlılık kuralı.

Testler SPEC 18 metninden (Teori, Arayüz, Kabul kriterleri) yazıldı; uygulama okunmadı. Blok B =
100 × 60 × 20 (min köşe orijinde, üst yüz z = 20). UST_20: uv = dünya xy, normal +Z.
Pah / yuvarlatma: dışbükey 90° kenar, boy L: pah d → d²L/2, d₁/d₂ → d₁d₂L/2, yuvarlatma r → (1 − π/4) r² L;
delik ağzı r: 2π (r_h + x̄)(1 − π/4) r², x̄ = r (10 − 3π) / (3 (4 − π)).
"""

from __future__ import annotations

import ast
import json
import math
from pathlib import Path

import numpy as np
import pytest

from tests.geometry.agac_ortak import (
    KONUM,
    REL,
    TABAN,
    UST_20,
    ad_imzalari,
    cizgi,
    dikdortgen,
    duzlemsel,
    rapor,
    ref,
    yay,
)

KOK = Path(__file__).resolve().parents[2]
V0 = 120000.0


def B():
    from geometry.agac import Blok

    return Blok("blok", 100, 60, 20)


# --- K12: bağımlılık kuralı (OCCT gerekmez) -----------------------------------------------------------------


def _importlar(yol: Path) -> list[str]:
    agac = ast.parse(yol.read_text(encoding="utf-8"))
    adlar = []
    for dugum in ast.walk(agac):
        if isinstance(dugum, ast.Import):
            adlar += [a.name for a in dugum.names]
        elif isinstance(dugum, ast.ImportFrom) and dugum.module and dugum.level == 0:
            if dugum.module == "sketch":
                adlar += [f"sketch.{a.name}" for a in dugum.names]
            else:
                adlar.append(dugum.module)
    return adlar


def test_k12_geometry_sketchten_yalniz_model_tezgahi_hic_import_etmez():
    dosyalar = sorted((KOK / "geometry").rglob("*.py"))
    assert dosyalar
    for yol in dosyalar:
        for ad in _importlar(yol):
            assert not (ad == "tezgah" or ad.startswith("tezgah.")), f"{yol.name}: {ad}"
            if ad == "sketch" or ad.startswith("sketch."):
                assert ad == "sketch.model", f"{yol.name}: {ad}"


# --- Buradan sonrası OCCT gerektirir ------------------------------------------------------------------------

occt = pytest.mark.occt


def _bd():
    return pytest.importorskip("build123d", reason='build123d kurulu değil (pip install -e ".[cad]")')


@pytest.fixture
def ag():
    """geometry.agac modülü (OCCT yoksa test atlanır)."""
    _bd()
    import geometry.agac as m

    return m


@pytest.fixture
def GeometryError():
    from geometry.part import GeometryError as E

    return E


def pah_kenari():
    from geometry.agac import EdgeRef

    return EdgeRef(ref("blok:zmax"), ref("blok:ymin"))


# --- K4: pah ve yuvarlatma (T3, T5, T6) ---------------------------------------------------------------------


@occt
def test_t5_esit_pah(ag):
    s = ag.insa(ag.Agac((B(), ag.Pah("pah", (pah_kenari(),), 2.0))))
    assert s.basarili
    assert V0 - s.part.volume == pytest.approx(200, rel=REL)
    assert abs(rapor(s, "pah").dV) == pytest.approx(200, rel=REL)
    assert rapor(s, "pah").adlar == (ref("pah:0"),)


@occt
def test_t5_iki_uzaklikli_pah_yuzleri(ag):
    s = ag.insa(ag.Agac((B(), ag.Pah("pah", (pah_kenari(),), 2.0, d2=3.0))))
    assert s.basarili
    assert V0 - s.part.volume == pytest.approx(300, rel=REL)
    (i,) = s.part.find(ref("pah:0"))
    f = duzlemsel(s.part, i)
    # d₁ = 2 zmax üzerinde (y = 2'ye kadar), d₂ = 3 ymin üzerinde (z = 17'ye kadar)
    assert np.allclose(f.origin, (50, 1, 18.5), atol=KONUM)
    assert np.allclose(f.normal, np.array([0, -3, 2]) / math.sqrt(13), atol=1e-9)
    assert f.area == pytest.approx(100 * math.sqrt(13), rel=REL)
    zmax = duzlemsel(s.part, s.part.find(ref("blok:zmax"))[0])
    assert zmax.area == pytest.approx(100 * 58, rel=REL)


@occt
def test_t3_delik_ve_yuvarlatma(ag):
    a = ag.Agac(
        (
            B(),
            ag.Delik("delik", UST_20, ((20, 30),), d=10.0),
            ag.Yuvarlatma("yuv", (pah_kenari(),), 4.0),
        )
    )
    s = ag.insa(a)
    assert s.basarili
    assert s.part.volume == pytest.approx(V0 - 500 * math.pi - (1 - math.pi / 4) * 16 * 100, rel=REL)
    assert rapor(s, "yuv").adlar == (ref("yuv:0"),)


@occt
def test_t6_delik_agzi_yuvarlatma(ag):
    from geometry.agac import EdgeRef

    a = ag.Agac(
        (
            B(),
            ag.Delik("delik", UST_20, ((20, 30),), d=10.0),
            ag.Yuvarlatma("yuv", (EdgeRef(ref("blok:zmax"), ref("delik:0/duvar")),), 1.0),
        )
    )
    s = ag.insa(a)
    assert s.basarili
    r = 1.0
    xbar = r * (10 - 3 * math.pi) / (3 * (4 - math.pi))
    dV = 2 * math.pi * (5 + xbar) * (1 - math.pi / 4) * r**2
    assert s.part.volume == pytest.approx(V0 - 500 * math.pi - dV, rel=REL)
    assert len(s.part.find(ref("yuv:0"))) >= 1


@occt
def test_k4_ortak_kenarsiz_edgeref_hata(ag):
    from geometry.agac import EdgeRef

    a = ag.Agac((B(), ag.Pah("pah", (EdgeRef(ref("blok:zmax"), ref("blok:zmin")),), 2.0)))
    s = ag.insa(a)
    assert not s.basarili
    assert rapor(s, "pah").durum == "hata"
    assert s.part.volume == pytest.approx(V0, rel=REL)


@occt
def test_k4_iki_kenar_iki_ad(ag):
    from geometry.agac import EdgeRef

    a = ag.Agac(
        (
            B(),
            ag.Pah("pah", (pah_kenari(), EdgeRef(ref("blok:zmax"), ref("blok:ymax"))), 2.0),
        )
    )
    s = ag.insa(a)
    assert s.basarili
    assert V0 - s.part.volume == pytest.approx(2 * 200, rel=REL)
    assert set(rapor(s, "pah").adlar) == {ref("pah:0"), ref("pah:1")}
    y0 = duzlemsel(s.part, s.part.find(ref("pah:0"))[0]).origin[1]
    y1 = duzlemsel(s.part, s.part.find(ref("pah:1"))[0]).origin[1]
    assert y0 == pytest.approx(1.0, abs=KONUM)
    assert y1 == pytest.approx(59.0, abs=KONUM)


# --- K7: hata yalıtımı --------------------------------------------------------------------------------------


@occt
def test_k7_hata_bagimlilari_atlar_bagimsizlar_devam_eder(ag):
    from geometry.agac import EdgeRef

    a = ag.Agac(
        (
            B(),
            ag.Pah("pah", (EdgeRef(ref("blok:zmax"), ref("blok:zmin")),), 2.0),  # hata: ortak kenar yok
            ag.Profil("p2", ref("pah:0"), (dikdortgen(-1, -1, 1, 1),)),  # doğrudan bağımlı
            ag.Ekstruzyon("e2", "p2", 1.0, islem="kes"),  # dolaylı bağımlı
            ag.Delik("delik", UST_20, ((50, 30),), d=10.0),  # bağımsız
        )
    )
    s = ag.insa(a)
    assert s.basarili is False
    assert rapor(s, "blok").durum == "tamam"
    assert rapor(s, "pah").durum == "hata"
    assert rapor(s, "pah").mesaj  # çekirdeğin mesajı boş değil
    for k in ("p2", "e2"):
        assert rapor(s, k).durum == "atlandi"
        assert rapor(s, k).neden == "pah"
    assert rapor(s, "delik").durum == "tamam"
    assert s.part.volume == pytest.approx(V0 - 500 * math.pi, rel=REL)
    assert [r.kimlik for r in s.rapor] == ["blok", "pah", "p2", "e2", "delik"]  # hiçbiri sessizce atlanmaz


@occt
def test_k7_bastirilanin_bagimlilari_atlanir(ag):
    from geometry.agac import EdgeRef

    a = ag.Agac(
        (
            B(),
            ag.Delik("delik", UST_20, ((20, 30),), d=10.0, bastir=True),
            ag.Yuvarlatma("yuv", (EdgeRef(ref("blok:zmax"), ref("delik:0/duvar")),), 1.0),
            ag.Pah("pah", (pah_kenari(),), 2.0),
        )
    )
    s = ag.insa(a)
    assert rapor(s, "delik").durum == "bastirildi"
    assert rapor(s, "yuv").durum == "atlandi"
    assert rapor(s, "yuv").neden == "delik"
    assert rapor(s, "pah").durum == "tamam"
    assert s.part.volume == pytest.approx(V0 - 200, rel=REL)
    assert len(s.part.holes) == 0


@occt
def test_k7_ikinci_yeni_govde_hata(ag):
    a = ag.Agac(
        (
            B(),
            ag.Profil("p", TABAN, (dikdortgen(200, 0, 210, 10),)),
            ag.Ekstruzyon("e", "p", 5.0, islem="yeni"),
        )
    )
    s = ag.insa(a)
    assert not s.basarili
    assert rapor(s, "e").durum == "hata"
    assert s.part.volume == pytest.approx(V0, rel=REL)


# --- K8: doğrulama ve düzenleme ----------------------------------------------------------------------------


def ornek_agac(ag):
    """blok ← p ← cep ← p2 ← e2; delik (bağımsız) ← yuv (blok + delik), desen (delik)."""
    from geometry.agac import EdgeRef

    return ag.Agac(
        (
            B(),
            ag.Profil("p", ref("blok:zmax"), (dikdortgen(-20, -15, 20, 15),)),
            ag.Ekstruzyon("cep", "p", 8.0, islem="kes"),
            ag.Delik("delik", UST_20, ((10, 30),), d=6.0),
            ag.Profil("p2", ref("cep:son"), (dikdortgen(-5, -5, 5, 5),)),
            ag.Ekstruzyon("e2", "p2", 2.0, islem="kes"),
            ag.Yuvarlatma("yuv", (EdgeRef(ref("blok:zmax"), ref("delik:0/duvar")),), 1.0),
            ag.DogrusalDesen("desen", ("delik",), (0.0, 1.0, 0.0), 10.0, 2),
        )
    )


def kimlikler(agac) -> list[str]:
    return [o.kimlik for o in agac.ozellikler]


@occt
def test_k8_bagimlilar(ag):
    a = ornek_agac(ag)
    assert ag.bagimlilar(a, "blok") == ("p", "cep", "p2", "e2", "yuv")
    assert ag.bagimlilar(a, "p") == ("cep", "p2", "e2")
    assert ag.bagimlilar(a, "delik") == ("yuv", "desen")
    assert ag.bagimlilar(a, "e2") == ()


@occt
@pytest.mark.parametrize(
    "bozuk",
    ["tekrar", "bos", "iki_nokta", "egik_cizgi", "ileri_kimlik", "ileri_faceref", "bilinmeyen_profil", "tur"],
)
def test_k8_dogrulama_hatalari(ag, GeometryError, bozuk):
    oz = list(ornek_agac(ag).ozellikler)
    if bozuk == "tekrar":
        oz.append(ag.Blok("cep", 1, 1, 1))
    elif bozuk == "bos":
        oz[3] = ag.Delik("", UST_20, ((10, 30),), d=6.0)
    elif bozuk == "iki_nokta":
        oz[3] = ag.Delik("de:lik", UST_20, ((10, 30),), d=6.0)
    elif bozuk == "egik_cizgi":
        oz[3] = ag.Delik("de/lik", UST_20, ((10, 30),), d=6.0)
    elif bozuk == "ileri_kimlik":
        oz[1], oz[2] = oz[2], oz[1]  # cep, p'den önce
    elif bozuk == "ileri_faceref":
        oz.insert(1, ag.Profil("px", ref("cep:son"), (dikdortgen(-1, -1, 1, 1),)))
    elif bozuk == "bilinmeyen_profil":
        oz.append(ag.Ekstruzyon("ex", "yok", 1.0, islem="kes"))
    elif bozuk == "tur":
        oz.append(object())
    a = ag.Agac(tuple(oz))
    with pytest.raises(GeometryError):
        ag.dogrula(a)
    with pytest.raises(GeometryError):
        ag.insa(a)


@occt
def test_k8_tasi(ag, GeometryError):
    a = ornek_agac(ag)
    b = ag.tasi(a, "delik", 1)  # delik yalnız sabit düzleme bağlı: başa yakın taşınabilir
    assert kimlikler(b) == ["blok", "delik", "p", "cep", "p2", "e2", "yuv", "desen"]
    assert kimlikler(a)[3] == "delik"  # girdi değişmez
    with pytest.raises(GeometryError) as e:
        ag.tasi(a, "cep", 1)  # p'den önceye: bağımlılık bozulur
    assert "cep" in str(e.value) and "p" in str(e.value)
    with pytest.raises(GeometryError) as e:
        ag.tasi(a, "delik", 7)  # yuv ve desen'in arkasına
    assert "delik" in str(e.value)
    with pytest.raises(GeometryError):
        ag.tasi(a, "yok", 0)


@occt
def test_k8_sil(ag, GeometryError):
    a = ornek_agac(ag)
    with pytest.raises(GeometryError) as e:
        ag.sil(a, "delik")
    assert "yuv" in str(e.value) and "desen" in str(e.value)
    b = ag.sil(a, "delik", zincir=True)
    assert kimlikler(b) == ["blok", "p", "cep", "p2", "e2"]
    c = ag.sil(a, "e2")  # yaprak
    assert kimlikler(c) == ["blok", "p", "cep", "delik", "p2", "yuv", "desen"]
    with pytest.raises(GeometryError):
        ag.sil(a, "yok")


# --- K9: önbellek, belirlenimcilik, kadar -------------------------------------------------------------------


def _ayni(s1, s2):
    assert s1.part.volume == pytest.approx(s2.part.volume, rel=1e-12)
    assert set(s1.part.names) == set(s2.part.names)
    assert ad_imzalari(s1.part) == ad_imzalari(s2.part)
    assert s1.part.holes == s2.part.holes
    assert len(s1.part.shape.faces()) == len(s2.part.shape.faces())


@occt
def test_k9_onbellek_yalniz_degisen_ozelligi_kurar(ag):
    a = ornek_agac(ag)
    ob = ag.Onbellek()
    s1 = ag.insa(a, onbellek=ob)
    assert s1.basarili
    assert set(s1.yeniden_hesaplanan) == set(kimlikler(a))
    oz = list(a.ozellikler)
    oz[-1] = ag.DogrusalDesen("desen", ("delik",), (0.0, 1.0, 0.0), 10.0, 3)  # son özellik değişti
    a2 = ag.Agac(tuple(oz))
    s2 = ag.insa(a2, onbellek=ob)
    assert tuple(s2.yeniden_hesaplanan) == ("desen",)
    _ayni(s2, ag.insa(a2))
    assert len(s2.part.holes) == 3


@occt
def test_k9_ortadaki_degisiklik_sonrasini_yeniden_kurar(ag):
    a = ornek_agac(ag)
    ob = ag.Onbellek()
    ag.insa(a, onbellek=ob)
    oz = list(a.ozellikler)
    oz[2] = ag.Ekstruzyon("cep", "p", 6.0, islem="kes")
    a2 = ag.Agac(tuple(oz))
    s2 = ag.insa(a2, onbellek=ob)
    assert tuple(s2.yeniden_hesaplanan) == ("cep", "delik", "p2", "e2", "yuv", "desen")
    _ayni(s2, ag.insa(a2))
    assert duzlemsel(s2.part, s2.part.find(ref("cep:son"))[0]).origin[2] == pytest.approx(14.0, abs=KONUM)


@occt
def test_k9_belirlenimcilik(ag):
    a = ornek_agac(ag)
    _ayni(ag.insa(a), ag.insa(a))


@occt
def test_k9_kadar(ag, GeometryError):
    a = ornek_agac(ag)
    s = ag.insa(a, kadar="cep")
    assert s.part.volume == pytest.approx(V0 - 9600, rel=REL)
    assert len(s.part.holes) == 0
    assert ref("cep:son") in s.part.names
    s = ag.insa(a, kadar="blok")
    assert s.part.volume == pytest.approx(V0, rel=REL)
    with pytest.raises(GeometryError):
        ag.insa(a, kadar="yok")


# --- K10: JSON ----------------------------------------------------------------------------------------------


def tam_agac(ag):
    """Her özellik türünden en az biri (kurulması gerekmez, referanslar geriye doğru)."""
    from geometry.agac import EdgeRef
    from sketch.model import Plane, Sketch, SketchRegion

    daire = SketchRegion((yay((0, 0), 3.0, (3, 0), (3, 0), True, "c"),))
    halka = SketchRegion(
        (
            cizgi((30, 0), (40, 0), "a"),
            cizgi((40, 0), (40, 20), "b"),
            yay((35, 20), 5.0, (40, 20), (30, 20), True, "y"),
            cizgi((30, 20), (30, 0), "d"),
        )
    )
    return ag.Agac(
        (
            ag.Blok("blok", 100, 60, 20),
            ag.Silindir("sil", 5.0, 10.0, bastir=True),
            ag.Profil("p", ref("blok:zmax"), (dikdortgen(-20, -15, 20, 15), daire)),
            ag.Profil("pe", UST_20, (), eskiz=Sketch()),
            ag.Profil("pr", Plane.XZ(), (halka,)),
            ag.Ekstruzyon("cep", "p", 8.0, islem="kes", yon="simetrik", bolge_sec=(0,)),
            ag.Ekstruzyon("kanal", "p", 1.0, islem="kes", yon="geri", bitis="boydan_boya"),
            ag.Dondurme("don", "pr", (0.0, 0.0), (0.0, 1.0), 90.0, "ekle"),
            ag.Delik(
                "delik",
                UST_20,
                ((10, 30), (90, 30)),
                d=6.0,
                derinlik=12.0,
                cesit="havsa",
                csk_d=12.0,
                csk_angle=90.0,
            ),
            ag.Delik(
                "lamba", ref("blok:zmin"), ((5, 5),), d=6.6, cesit="lamba", cbore_d=11.0, cbore_depth=6.4
            ),
            ag.Delik("dis", UST_20, ((50, 50),), d=6.8, derinlik=15.0, cesit="dis", thread="M8"),
            ag.Pah("pah", (EdgeRef(ref("blok:zmax"), ref("blok:ymin")),), 2.0, d2=3.0),
            ag.Yuvarlatma("yuv", (EdgeRef(ref("blok:zmax"), ref("delik:0/duvar")),), 1.0),
            ag.DogrusalDesen(
                "dd", ("delik", "cep"), (1.0, 0.0, 0.0), 20.0, 2, e2=(0.0, 1.0, 0.0), s2=5.0, n2=2
            ),
            ag.DaireselDesen("cd", ("kanal",), (50.0, 30.0, 0.0), (0.0, 0.0, 1.0), 3, aci=120.0),
            ag.Ayna("a1", Plane((50, 0, 0), (1, 0, 0), (0, 1, 0)), ("don",)),
            ag.Ayna("a2", ref("blok:xmax"), None),
        )
    )


_NUMPYSIZ = (
    "Blok",
    "Silindir",
    "Ekstruzyon",
    "Dondurme",
    "Pah",
    "Yuvarlatma",
    "DogrusalDesen",
    "DaireselDesen",
)


@occt
def test_k10_json_gidis_donus(ag):
    a = tam_agac(ag)
    d = ag.to_dict(a)
    assert d["sema"] == 1
    d2 = json.loads(json.dumps(d))  # JSON uyumlu
    b = ag.from_dict(d2)
    assert isinstance(b, ag.Agac)
    assert len(b.ozellikler) == len(a.ozellikler)
    for x, y in zip(a.ozellikler, b.ozellikler, strict=True):
        assert type(x) is type(y)
        assert x.kimlik == y.kimlik and x.bastir == y.bastir
        if type(x).__name__ in _NUMPYSIZ:
            assert x == y  # tuple alanlar tuple olarak döner
    # Plane / SegLine numpy alanlı olduğundan bütün ağaç sözlük üzerinden karşılaştırılır
    assert ag.to_dict(b) == d
    assert b.ozellikler[1].bastir is True
    assert b.ozellikler[3].eskiz is not None
    assert b.ozellikler[16].ozellikler is None
    assert b.ozellikler[2].duzlem == ref("blok:zmax")
    seg = b.ozellikler[4].bolgeler[0].outer[2]
    assert seg.src == "y" and seg.ccw is True


@occt
def test_k10_json_numpysiz_agac_esitligi(ag):
    from geometry.agac import EdgeRef

    a = ag.Agac(
        (
            ag.Blok("blok", 100, 60, 20),
            ag.Pah("pah", (EdgeRef(ref("blok:zmax"), ref("blok:ymin")),), 2.0),
            ag.Ayna("ayna", ref("blok:xmax"), None),
        )
    )
    assert ag.from_dict(ag.to_dict(a)) == a


@occt
def test_k10_sema_ve_bilinmeyen_tur(ag, GeometryError):
    a = ag.Agac((ag.Blok("b1", 100, 60, 20), ag.Silindir("s1", 5, 10)))
    d = ag.to_dict(a)
    with pytest.raises(GeometryError):
        ag.from_dict({**d, "sema": 2})
    # tür alanı: Blok ve Silindir sözlüklerinde farklı olan, kimlik dışı metin değer
    o0, o1 = d["ozellikler"]
    tur = [k for k, v in o0.items() if isinstance(v, str) and v != "b1" and o1.get(k) != v]
    assert len(tur) == 1
    bozuk = json.loads(json.dumps(d))
    bozuk["ozellikler"][0][tur[0]] = "Kure"
    with pytest.raises(GeometryError):
        ag.from_dict(bozuk)


# --- K11: delik ve eskiz uyumu ------------------------------------------------------------------------------


@occt
def test_k11_duz_kor_delik_dogrudan_cagriyla_ayni(ag):
    from geometry.features import block, hole

    s = ag.insa(ag.Agac((B(), ag.Delik("d1", UST_20, ((20, 30), (70, 30)), d=8.0, derinlik=12.0))))
    dogrudan = hole(hole(block(100, 60, 20), 20, 30, 8.0, 12.0), 70, 30, 8.0, 12.0)
    assert s.part.volume == pytest.approx(dogrudan.volume, rel=1e-9)
    assert s.part.holes == dogrudan.holes
    for ad in ("d1:0/duvar", "d1:1/duvar", "d1:0/dip", "d1:1/dip"):
        assert len(s.part.find(ref(ad))) == 1
    dip = duzlemsel(s.part, s.part.find(ref("d1:1/dip"))[0])
    assert np.allclose(dip.origin, (70, 30, 8), atol=KONUM)


@occt
def test_k11_havsa_ve_lamba_dogrudan_cagriyla_ayni(ag):
    from geometry.features import block
    from geometry.holes import counterbore_hole, countersink_hole

    s = ag.insa(
        ag.Agac(
            (
                B(),
                ag.Delik("hv", UST_20, ((30, 30),), d=6.0, cesit="havsa", csk_d=12.0, csk_angle=90.0),
                ag.Delik("lb", UST_20, ((70, 30),), d=6.6, cesit="lamba", cbore_d=11.0, cbore_depth=6.4),
            )
        )
    )
    p = countersink_hole(block(100, 60, 20), 30, 30, 6.0, 12.0, 90.0)
    p = counterbore_hole(p, 70, 30, d=6.6, cbore_d=11.0, cbore_depth=6.4)
    assert s.basarili
    assert s.part.volume == pytest.approx(p.volume, rel=1e-9)
    assert s.part.holes == p.holes
    for ad in ("hv:0/duvar", "hv:0/havsa", "lb:0/duvar", "lb:0/lamba_duvar", "lb:0/lamba_dip"):
        assert len(s.part.find(ref(ad))) >= 1
    ld = duzlemsel(s.part, s.part.find(ref("lb:0/lamba_dip"))[0])
    assert ld.origin[2] == pytest.approx(20 - 6.4, abs=KONUM)


@occt
def test_k11_profil_eskiz_coz_ile_cozulur(ag):
    from sketch.model import Sketch

    cagrilar = []

    def coz(eskiz, duzlem):
        cagrilar.append((eskiz, duzlem))
        return [dikdortgen(30, 15, 70, 45)]

    a = ag.Agac(
        (
            B(),
            ag.Profil("p", UST_20, eskiz=Sketch()),
            ag.Ekstruzyon("cep", "p", 8.0, islem="kes"),
        )
    )
    s = ag.insa(a, coz=coz)
    assert s.basarili
    assert len(cagrilar) == 1
    assert np.allclose(cagrilar[0][1].origin, (0, 0, 20))
    assert s.part.volume == pytest.approx(V0 - 9600, rel=REL)


@occt
def test_k11_coz_yoksa_profil_hata(ag):
    from sketch.model import Sketch

    a = ag.Agac(
        (
            B(),
            ag.Profil("p", UST_20, eskiz=Sketch()),
            ag.Ekstruzyon("cep", "p", 8.0, islem="kes"),
        )
    )
    s = ag.insa(a)
    assert not s.basarili
    assert rapor(s, "p").durum == "hata"
    assert rapor(s, "cep").durum == "atlandi"
    assert rapor(s, "cep").neden == "p"
    assert s.part.volume == pytest.approx(V0, rel=REL)
