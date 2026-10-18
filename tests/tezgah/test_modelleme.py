"""SPEC 26 K4, K6, K9 — tezgah/modelleme.py: model geçmişi, insa(), delik adımı, kontroller.

Testler SPEC 26 "Model geçmişi", "Delik adımı", "tezgah/modelleme.py" ve "Kabul kriterleri" bölümlerinden
yazıldı; tezgah/modelleme.py gövdesi okunmadı. Modeller tests/tezgah/model_ornekler.py'de elle kurulur.
Beklenen hacimler kapalı formdur; delik adımının beklenen sonucu SPEC 02/23 fonksiyonlarının doğrudan
çağrısıdır (SPEC 26 "Delik adımı": "Mevcut fonksiyonlar çağrılır"). OCCT gerektirir.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

pytest.importorskip("build123d", reason='build123d kurulu değil (pip install -e ".[cad]")')

from geometry.features import hole  # noqa: E402
from geometry.holes import counterbore_hole, countersink_hole, inclined_hole, tapped_hole  # noqa: E402
from geometry.part import Part  # noqa: E402
from sketch.model import Circle, Constraint, Plane, Point, Sketch, SketchError  # noqa: E402
from sketch.regions import area, regions  # noqa: E402
from sketch.solver import solve  # noqa: E402
from tests.tezgah import model_ornekler as mo  # noqa: E402
from tezgah.modelleme import AdimRaporu, Rapor, insa, ornek_model  # noqa: E402

pytestmark = pytest.mark.occt

REL = 1e-6
KONTROL_ALANLARI = {"kimlik", "baslik", "deger", "birim", "durum", "aciklama", "spec"}


def hacim(m: dict, k: int | None = None) -> float:
    p, r = insa(m, k)
    assert r.hata is None, r.hata
    assert p is not None
    return p.volume


def adim(r: Rapor, kimlik: str) -> AdimRaporu:
    (a,) = [a for a in r.adimlar if a.kimlik == kimlik]
    return a


def kontrol_denetle(K: list[dict]) -> None:
    for k in K:
        assert set(k) == KONTROL_ALANLARI, k
        assert k["durum"] in {"tamam", "uyari", "hata"}
        assert isinstance(k["spec"], str) and k["spec"].startswith("SPEC "), k
        assert isinstance(k["baslik"], str) and k["baslik"]


def yuz_index(p: Part, normal) -> int:
    n = np.asarray(normal, float)
    adaylar = [f for f in p.planar_faces() if np.allclose(f.normal, n, atol=1e-9)]
    return max(adaylar, key=lambda f: float(f.origin @ n)).index


def kutu_plaka(a: float, b: float, c: float) -> dict:
    return mo.plaka(parametreler={"genislik": str(a), "boy": str(b), "kalinlik": str(c)})


# --- K6: yeniden kurulum ------------------------------------------------------------------------------


def test_plaka_hacmi_ve_rapor():
    p, r = insa(mo.plaka())
    assert isinstance(p, Part)
    assert p.volume == pytest.approx(12000.0, rel=REL)
    b0, b1 = p.bbox
    np.testing.assert_allclose(b0, (0, 0, 0), atol=1e-6)
    np.testing.assert_allclose(b1, (40, 30, 10), atol=1e-6)
    assert isinstance(r, Rapor)
    assert r.hata is None
    assert [a.kimlik for a in r.adimlar] == ["e1", "x1"]
    e1, x1 = r.adimlar
    assert (e1.tur, x1.tur) == ("eskiz", "ekstruzyon")
    assert e1.hata is None and e1.dof == 0
    assert e1.freedom and all(v == 0 for v in e1.freedom.values())
    assert e1.celiski == ()
    assert len(x1.alanlar) == 1 and x1.alanlar[0] == pytest.approx(1200.0, rel=1e-9)
    assert x1.dV == pytest.approx(12000.0, rel=REL)


def test_parametre_degisince_hacim_analitik():
    m = mo.plaka()
    assert hacim(m) == pytest.approx(12000.0, rel=REL)
    m["parametreler"]["genislik"] = "50"
    assert hacim(m) == pytest.approx(50 * 30 * 10, rel=REL)


def test_parametreye_bagli_parametre():
    m = mo.plaka(parametreler={"genislik": "50", "boy": "=genislik*3/4", "kalinlik": "=boy/5"})
    assert hacim(m) == pytest.approx(50 * 37.5 * 7.5, rel=REL)


def test_dogrudan_sayi_ifadeleri():
    m = mo.plaka(genislik=25, boy="12", kalinlik="=2*3", parametreler={})
    assert hacim(m) == pytest.approx(25 * 12 * 6, rel=REL)


@pytest.mark.parametrize("yon, z0, z1", [("ileri", 0, 10), ("geri", -10, 0), ("simetrik", -5, 5)])
def test_ekstruzyon_yonu(yon, z0, z1):
    m = mo.plaka()
    m["adimlar"][1]["yon"] = yon
    p, r = insa(m)
    assert r.hata is None
    assert p.volume == pytest.approx(12000.0, rel=REL)
    assert p.bbox[0][2] == pytest.approx(z0, abs=1e-6)
    assert p.bbox[1][2] == pytest.approx(z1, abs=1e-6)


def test_ilk_k_adim():
    m = mo.flans()
    V_plaka = mo.FL_A * mo.FL_B * mo.FL_C
    V_cep = V_plaka - mo.FL_CEP[2] * mo.FL_CEP[3] * mo.FL_CEP_DERINLIK
    for k in (0, 1):
        p, r = insa(m, k)
        assert p is None  # henüz katı yok
        assert r.hata is None
    assert hacim(m, 2) == pytest.approx(V_plaka, rel=REL)
    assert hacim(m, 3) == pytest.approx(V_plaka, rel=REL)  # eskiz katıyı değiştirmez
    assert hacim(m, 4) == pytest.approx(V_cep, rel=REL)
    assert hacim(m) == pytest.approx(mo.flans_hacmi(), rel=REL)
    assert hacim(m, len(m["adimlar"])) == pytest.approx(mo.flans_hacmi(), rel=REL)
    _, r = insa(m, 4)
    assert [a.kimlik for a in r.adimlar] == ["e1", "x1", "e2", "cep"]


def test_kes_raporu_alan_ve_dV():
    _, r = insa(mo.flans())
    cep = adim(r, "cep")
    assert cep.alanlar == pytest.approx((1200.0,), rel=1e-9)
    assert abs(cep.dV) == pytest.approx(1200.0 * mo.FL_CEP_DERINLIK, rel=REL)
    assert cep.dV < 0


def test_iki_kurulum_ayni():
    m = mo.flans()
    p1, _ = insa(m)
    p2, _ = insa(m)
    assert p1.volume == p2.volume
    assert len(p1.shape.faces()) == len(p2.shape.faces())
    assert p1.holes == p2.holes


def test_girdi_model_degismez():
    m = mo.flans()
    once = mo.kopya(m)
    insa(m)
    insa(m, 3)
    assert m == once


def test_ekle_islemi_boss():
    m = kutu_plaka(100, 60, 20)
    m["adimlar"] += [
        mo.eskiz_adimi(
            "e2", mo.dikdortgen_eskiz(40, 20, 20, 20, plane=mo.duzlem_xy(20)), {"tur": "XY", "ofset": 20}
        ),
        mo.ekstruzyon_adimi("boss", "e2", "15", islem="ekle"),
    ]
    p, r = insa(m)
    assert r.hata is None
    assert p.volume == pytest.approx(100 * 60 * 20 + 400 * 15, rel=REL)
    assert adim(r, "boss").dV == pytest.approx(400 * 15, rel=REL)


def test_boydan_boya_kesim():
    m = kutu_plaka(100, 60, 20)
    m["adimlar"] += [
        mo.eskiz_adimi("e2", mo.daire_eskiz(50, 30, 5, plane=mo.duzlem_xy(20)), {"tur": "XY", "ofset": 20}),
        mo.ekstruzyon_adimi("kanal", "e2", "0", islem="kes", bitis="boydan_boya"),
    ]
    p, r = insa(m)
    assert r.hata is None
    assert p.volume == pytest.approx(100 * 60 * 20 - 25 * math.pi * 20, rel=REL)
    assert p.holes == ()  # kesim delik kaydı üretmez


def _iki_bolgeli_eskiz() -> Sketch:
    sk = mo.dikdortgen_eskiz(0, 0, 40, 30)
    sk.points["m"] = Point(70.0, 15.0, fixed=True)
    sk.entities["o"] = Circle("m", 6.0)
    sk.constraints.append(Constraint("radius", ("o",), 6.0))
    return sk


def test_bolge_secimi():
    """bolgeler: [i] — i, SPEC 17 regions() sırasındaki indeks."""
    sk = _iki_bolgeli_eskiz()
    res = solve(sk)
    cozulu = Sketch.from_dict(sk.to_dict())
    res.apply(cozulu)
    alanlar = [area(b) for b in regions(cozulu)]
    i = int(np.argmin(alanlar))  # daire
    assert alanlar[i] == pytest.approx(36 * math.pi, rel=1e-9)
    m = mo.model(
        [
            mo.eskiz_adimi("e1", sk, {"tur": "XY", "ofset": 0}),
            mo.ekstruzyon_adimi("x1", "e1", 5, bolgeler=[i]),
        ]
    )
    p, r = insa(m)
    assert r.hata is None
    assert p.volume == pytest.approx(36 * math.pi * 5, rel=REL)
    assert adim(r, "x1").alanlar == pytest.approx((36 * math.pi,), rel=1e-9)


def test_xy_ofseti_ifade():
    m = mo.plaka()
    m["parametreler"]["taban"] = "7"
    m["adimlar"][0]["duzlem"] = {"tur": "XY", "ofset": "=taban"}
    m["adimlar"][0]["eskiz"]["plane"] = mo.duzlem_xy(7).to_dict()
    p, r = insa(m)
    assert r.hata is None
    assert p.bbox[0][2] == pytest.approx(7.0, abs=1e-6)
    assert p.bbox[1][2] == pytest.approx(17.0, abs=1e-6)


# --- Yüze bağlı eskiz ---------------------------------------------------------------------------------


def _yuze_bagli_kesim(kalinlik: str) -> dict:
    """Plaka (40 × 30 × kalinlik); kalinlik = 10'daki üst yüz düzlemi saklı eskiz, 10 × 10 kesim 3 mm."""
    m = mo.plaka()
    p10, _ = insa(m)
    i = yuz_index(p10, (0, 0, 1))
    pl = Plane((20.0, 15.0, 10.0), (0, 0, 1), (1, 0, 0))  # üst yüzün ağırlık merkezi (SPEC 26 yüz düzlemi)
    m["adimlar"] += [
        mo.eskiz_adimi(
            "e2",
            mo.dikdortgen_eskiz(-5, -5, 10, 10, plane=pl),
            {"tur": "yuz", "adim": "x1", "yuz": i, "plane": pl.to_dict()},
        ),
        mo.ekstruzyon_adimi("kes", "e2", 3, islem="kes"),
    ]
    m["parametreler"]["kalinlik"] = kalinlik
    return m


def _kopuk(r: Rapor) -> list[dict]:
    return [k for k in r.kontroller if k["kimlik"] == "eskiz_duzlemi_kopuk"]


def test_yuze_bagli_eskiz_cakisik():
    p, r = insa(_yuze_bagli_kesim("10"))
    assert r.hata is None
    assert p.volume == pytest.approx(12000 - 100 * 3, rel=REL)
    assert all(k["durum"] != "uyari" for k in _kopuk(r))


def test_yuz_kayinca_eskiz_duzlemi_kopuk_uyarisi():
    """kalinlik 10 → 8: saklanan düzlem (z = 10) artık bir yüzle çakışmaz; adım saklanan düzlemle çalışır."""
    p, r = insa(_yuze_bagli_kesim("8"))
    assert r.hata is None
    kopuk = _kopuk(r)
    assert kopuk and all(k["durum"] == "uyari" for k in kopuk)
    kontrol_denetle(kopuk)
    # z ∈ [7, 10] kesilir, parça z ∈ [0, 8]: 1 mm'lik dilim gider (sessiz kayma yok)
    assert p.volume == pytest.approx(40 * 30 * 8 - 100 * 1, rel=REL)


# --- Hata: adım kimliğiyle durur ----------------------------------------------------------------------


def test_ortadaki_adim_hatasi_onceki_parca():
    m = mo.flans()
    # cep bölgesini parçanın dışına taşı: kesim malzeme kaldırmaz → GeometryError
    m["adimlar"][2]["eskiz"] = mo.dikdortgen_eskiz(500, 500, 40, 30, plane=mo.duzlem_xy(mo.FL_C)).to_dict()
    p, r = insa(m)
    assert p is not None
    assert p.volume == pytest.approx(mo.FL_A * mo.FL_B * mo.FL_C, rel=REL)
    assert r.hata is not None
    assert r.hata.kimlik == "cep"
    assert isinstance(r.hata.hata, str) and r.hata.hata
    assert [a.kimlik for a in r.adimlar] == ["e1", "x1", "e2", "cep"]  # kurulum orada durur


def test_celiskili_eskiz_raporu():
    m = mo.plaka()
    sk = mo.dikdortgen_eskiz(0, 0, 40, 30)
    sk.constraints.append(Constraint("length", ("ust",), 45.0))  # alt = 40 ile çelişir
    m["adimlar"][0]["eskiz"] = sk.to_dict()
    with pytest.raises(SketchError) as e:
        solve(sk)
    beklenen = tuple(sorted(e.value.constraints))
    assert beklenen
    p, r = insa(m)
    assert p is None
    assert r.hata is not None and r.hata.kimlik == "e1"
    assert r.hata.hata
    assert tuple(sorted(r.hata.celiski)) == beklenen
    assert [a.kimlik for a in r.adimlar] == ["e1"]


def test_olcu_celiskisi_parametreden():
    """Ölçü ifadesi çözülemeyen değer verir (alt kenar −5): adım hata verir, sessiz değer yok."""
    m = mo.plaka()
    m["parametreler"]["genislik"] = "-5"
    p, r = insa(m)
    assert p is None
    assert r.hata is not None and r.hata.kimlik == "e1"


def test_ilk_adim_eskiz_degilse_katisiz_kesim_hatasi():
    m = mo.plaka()
    m["adimlar"][1]["islem"] = "kes"
    p, r = insa(m)
    assert p is None
    assert r.hata is not None and r.hata.kimlik == "x1"


# --- K4: delik adımı ----------------------------------------------------------------------------------

UST = {"p1": (20.0, 20.0), "p2": (70.0, 40.0)}


def _delikli_model(cesit: str, d, derinlik, **ek) -> dict:
    m = kutu_plaka(100, 60, 20)
    m["adimlar"] += [
        mo.eskiz_adimi("e2", mo.nokta_eskiz(UST, plane=mo.duzlem_xy(20)), {"tur": "XY", "ofset": 20}),
        mo.delik_adimi("h", "e2", list(UST), cesit, d, derinlik, **ek),
    ]
    return m


def _karsilastir(m: dict, dogrudan) -> None:
    p0, _ = insa(m, len(m["adimlar"]) - 1)
    beklenen = p0
    for x, y in UST.values():
        beklenen = dogrudan(beklenen, x, y)
    p, r = insa(m)
    assert r.hata is None, r.hata
    assert p.holes == beklenen.holes
    assert len(p.holes) == 2
    assert p.volume == pytest.approx(beklenen.volume, rel=REL)
    assert adim(r, "h").tur == "delik"


def test_duz_delik_boydan_boya():
    _karsilastir(_delikli_model("duz", 6, None), lambda p, x, y: hole(p, x, y, 6.0, None))


def test_duz_delik_kor_ifadeli():
    m = _delikli_model("duz", "=cap", "=2*cap")
    m["parametreler"]["cap"] = "5"
    _karsilastir(m, lambda p, x, y: hole(p, x, y, 5.0, 10.0))


def test_havsali_delik():
    m = _delikli_model("havsa", 6.6, None, csk_d=12.0, csk_angle=90.0)
    _karsilastir(m, lambda p, x, y: countersink_hole(p, x, y, 6.6, 12.0, 90.0, None))


def test_lambali_delik():
    m = _delikli_model("lamba", 6.6, None, cbore_d=11.0, cbore_depth=6.4)
    _karsilastir(
        m, lambda p, x, y: counterbore_hole(p, x, y, d=6.6, cbore_d=11.0, cbore_depth=6.4, depth=None)
    )


def test_disli_delik():
    m = _delikli_model("dis", 6.75, 12, thread="M8")
    _karsilastir(m, lambda p, x, y: tapped_hole(p, x, y, "M8", depth=12.0))


def _yan_yuz_model(cesit: str, **ek) -> tuple[dict, Part]:
    m = kutu_plaka(100, 60, 20)
    p0, _ = insa(m)
    i = yuz_index(p0, (1, 0, 0))
    pl = Plane((100.0, 30.0, 10.0), (1, 0, 0), (0, 1, 0))  # ağırlık merkezi; X izdüşümü 0 → xdir = Y
    m["adimlar"] += [
        mo.eskiz_adimi(
            "e2",
            mo.nokta_eskiz({"s": (5.0, 2.0)}, plane=pl),
            {"tur": "yuz", "adim": "x1", "yuz": i, "plane": pl.to_dict()},
        ),
        mo.delik_adimi("yan", "e2", ["s"], cesit, 6, 20, **ek),
    ]
    return m, p0


def test_yan_yuzde_duz_delik_inclined_hole():
    m, p0 = _yan_yuz_model("duz")
    beklenen = inclined_hole(p0, np.array([100.0, 35.0, 12.0]), np.array([-1.0, 0.0, 0.0]), 6.0, 20.0)
    p, r = insa(m)
    assert r.hata is None, r.hata
    assert p.holes == beklenen.holes
    assert p.volume == pytest.approx(beklenen.volume, rel=REL)


@pytest.mark.parametrize(
    "cesit, ek",
    [("havsa", {"csk_d": 12.0, "csk_angle": 90.0}), ("lamba", {"cbore_d": 11.0, "cbore_depth": 5.0})],
)
def test_yan_yuzde_havsa_lamba_hata(cesit, ek):
    m, p0 = _yan_yuz_model(cesit, **ek)
    p, r = insa(m)
    assert r.hata is not None and r.hata.kimlik == "yan"
    assert r.hata.hata
    assert p.volume == pytest.approx(p0.volume, rel=REL)
    assert p.holes == ()


# --- K9: kanıtlar -------------------------------------------------------------------------------------


def test_kontroller_tam_tanimli_hepsi_tamam():
    _, r = insa(mo.plaka())
    K = r.kontroller
    kontrol_denetle(K)
    assert len(K) >= 3  # en az: eskiz DOF, hacim = A·|d|, STEP gidiş-dönüş
    assert all(k["durum"] == "tamam" for k in K), K
    specler = {k["spec"] for k in K}
    assert "SPEC 26" in specler or "SPEC 17" in specler


def test_kontroller_eksik_tanimli_eskiz_uyari():
    m = mo.plaka(tam=False)
    p, r = insa(m)
    assert r.hata is None
    assert adim(r, "e1").dof == 1
    assert p.volume == pytest.approx(12000.0, rel=REL)  # eksik tanımlı eskiz de kurulur
    kontrol_denetle(r.kontroller)
    assert any(k["durum"] == "uyari" for k in r.kontroller)
    assert not any(k["durum"] == "hata" for k in r.kontroller)


def test_kontroller_her_ekstruzyon_icin():
    _, r1 = insa(mo.plaka())
    m = mo.plaka()
    m["adimlar"] += [
        mo.eskiz_adimi(
            "e2", mo.dikdortgen_eskiz(10, 10, 5, 5, plane=mo.duzlem_xy(10)), {"tur": "XY", "ofset": 10}
        ),
        mo.ekstruzyon_adimi("boss", "e2", 4, islem="ekle"),
    ]
    _, r2 = insa(m)
    kontrol_denetle(r2.kontroller)
    assert len(r2.kontroller) > len(r1.kontroller)
    assert all(k["durum"] == "tamam" for k in r2.kontroller), r2.kontroller


# --- Örnek model ----------------------------------------------------------------------------------------


def test_ornek_flans_kurulur():
    m = ornek_model("flans")
    assert m["sema"] == 1
    turler = [a["tur"] for a in m["adimlar"]]
    assert "eskiz" in turler and "ekstruzyon" in turler and "delik" in turler
    p, r = insa(m)
    assert r.hata is None, r.hata
    assert len([h for h in p.holes if h.through]) == 4
    kes = [
        a for a in m["adimlar"] if a["tur"] == "ekstruzyon" and a["islem"] == "kes" and a["bitis"] == "mesafe"
    ]
    assert len(kes) == 1
    kontrol_denetle(r.kontroller)


def test_ornek_model_varsayilan_flans():
    assert ornek_model() == ornek_model("flans")


def test_ornek_model_bilinmeyen():
    with pytest.raises((KeyError, ValueError)):
        ornek_model("yok-boyle-model")
