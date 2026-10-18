"""SPEC 65a K5, K6, K7 (JSON), K8 (yüzey), K9 (06 finiş) — B-spline yüzey, kalınlaştırma, yüzeyle kesme.

Testler SPEC 65a metninden ve arayüzden yazıldı; uygulama gövdeleri okunmadı.
K5 ağı: z = (x² + y²)/200 paraboloidinden 7 × 7 nokta, x, y ∈ [−30, 30]; tepe eğrilik yarıçapı 100 mm.
K6: 60 × 60 × 40 blok (min köşe orijinde, SPEC 18 Blok) ile aynı x, y aralığında, z = 20 + ((x−30)² +
(y−30)²)/200 yüzeyi; "alt" kalan hacim ∫∫ z dA = 20·3600 + (1/200)·2·60·(2·30³/3) = 72000 + 10800 = 82800.
Varsayım: noktalar[i][j] = (x_i, y_j, z) sırasında yüzey normali +z'ye bakar ("alt" = düşük z tarafı).
"""

from __future__ import annotations

import json

import numpy as np
import pytest

from tests.geometry.serbest_ortak import eyer_agi, paraboloid_agi, rapor, sessiz_gecmez, yuzler

occt = pytest.mark.occt

V_ALT = 82800.0  # K6 "alt" kalan hacim
V_BLOK = 60.0 * 60.0 * 40.0


@pytest.fixture
def ag():
    pytest.importorskip("build123d", reason='build123d kurulu değil (pip install -e ".[cad]")')
    import geometry.agac as m

    return m


@pytest.fixture
def sb():
    pytest.importorskip("build123d", reason='build123d kurulu değil (pip install -e ".[cad]")')
    import geometry.serbest as m

    return m


def vektor(p):
    import build123d as bd

    return bd.Vector(*(float(v) for v in p))


def test_k6_kapali_form():
    """Beklenen hacim: ∫∫ (u² + v²)/200 dA, [−30, 30]² üzerinde = 10800."""
    xs = np.linspace(-30.0, 30.0, 1201)
    X, Y = np.meshgrid(xs, xs)
    Z = (X * X + Y * Y) / 200.0
    sayisal = np.trapezoid(np.trapezoid(Z, xs, axis=1), xs)
    assert sayisal == pytest.approx(10800.0, rel=1e-5)  # yamuk kuralı hatası ~1.4e-6
    assert 20.0 * 3600.0 + 10800.0 == V_ALT


def test_bspline_arayuzu_varsayilanlar(ag):
    oz = ag.BSplineYuzey("y", paraboloid_agi())
    assert oz.tol == 0.01
    assert oz.kullanim == "kalinlastir"
    assert oz.kalinlik == 1.0
    assert oz.sakla == "alt"


# --- K5: yüzey ağı ---------------------------------------------------------------------------------------


@occt
def test_k5_yuzey_noktalardan_gecer(sb):
    ag_ = paraboloid_agi()
    f = sb.bspline_yuzey(ag_, 0.01)
    for satir in ag_:
        for p in satir:
            assert f.distance_to(vektor(p)) <= 0.01


@occt
def test_k5_hucre_ortalarinda_paraboloide_sapma(sb):
    f = sb.bspline_yuzey(paraboloid_agi(), 0.01)
    orta = np.linspace(-25.0, 25.0, 6)  # 7 × 7 ağın 6 × 6 hücre ortası
    for x in orta:
        for y in orta:
            assert f.distance_to(vektor((x, y, (x * x + y * y) / 200.0))) <= 0.05


@occt
def test_k5_yuzey_sinirli_ve_ag_kapsami(sb):
    """Sınırlı yüz: alanı izdüşüm alanından (3600) büyük, paraboloid yüzey alanına yakın."""
    f = sb.bspline_yuzey(paraboloid_agi(), 0.01)
    xs = np.linspace(-30.0, 30.0, 1201)
    X, Y = np.meshgrid(xs, xs)
    yogunluk = np.sqrt(1.0 + (X / 100.0) ** 2 + (Y / 100.0) ** 2)
    A_parab = np.trapezoid(np.trapezoid(yogunluk, xs, axis=1), xs)
    assert 3600.0 < f.area
    assert f.area == pytest.approx(A_parab, rel=1e-2)


@occt
@pytest.mark.parametrize("t", [3.0, -3.0])
def test_k5_kalinlastirma_hacmi(ag, sb, t):
    A = sb.bspline_yuzey(paraboloid_agi(), 0.01).area
    s = ag.insa(ag.Agac((ag.BSplineYuzey("yuz", paraboloid_agi(), kullanim="kalinlastir", kalinlik=t),)))
    assert s.basarili
    assert rapor(s, "yuz").durum == "tamam"
    assert s.part.volume == pytest.approx(A * 3.0, rel=5e-2)


@occt
def test_k5_kalinlastirma_adlari(ag):
    s = ag.insa(ag.Agac((ag.BSplineYuzey("yuz", paraboloid_agi(), kalinlik=3.0),)))
    adlar = {r.name for r in rapor(s, "yuz").adlar}
    assert {"ust", "alt", "kenar_1", "kenar_2", "kenar_3", "kenar_4"} <= adlar
    assert "kenar_5" not in adlar
    assert len(yuzler(s.part, "yuz", "ust")) == 1
    assert len(yuzler(s.part, "yuz", "alt")) == 1


@occt
def test_k5_kalinlastirma_mevcut_govdeye_eklenir(ag, sb):
    """Gövde varken kalınlaştırma eklenir (arayüz: gövde yoksa yeni, varsa ekle)."""
    a = ag.Agac(
        (
            ag.Blok("blok", 10, 10, 10),
            ag.BSplineYuzey("yuz", paraboloid_agi(cx=5.0, cy=5.0, z0=9.0), kalinlik=3.0),
        )
    )
    s = ag.insa(a)
    assert s.basarili
    A = sb.bspline_yuzey(paraboloid_agi(cx=5.0, cy=5.0, z0=9.0), 0.01).area
    assert s.part.volume > 1000.0
    assert s.part.volume < 1000.0 + A * 3.0 * 1.05


# --- K6: yüzeyle kesme -----------------------------------------------------------------------------------


def kesme_agaci(ag, sakla: str = "alt", a: float = 60.0, b: float = 60.0):
    return ag.Agac(
        (
            ag.Blok("blok", a, b, 40),
            ag.BSplineYuzey("kes", paraboloid_agi(cx=30.0, cy=30.0, z0=20.0), kullanim="kes", sakla=sakla),
        )
    )


@occt
def test_k6_alt_kalir(ag):
    s = ag.insa(kesme_agaci(ag, "alt"))
    assert s.basarili
    assert rapor(s, "kes").durum == "tamam"
    assert s.part.volume == pytest.approx(V_ALT, rel=1e-3)
    lo, hi = s.part.bbox
    assert hi[2] == pytest.approx(29.0, abs=0.05)  # köşelerde z = 20 + 9


@occt
def test_k6_ust_kalir(ag):
    s = ag.insa(kesme_agaci(ag, "ust"))
    assert s.basarili
    assert s.part.volume == pytest.approx(V_BLOK - V_ALT, rel=1e-3)
    lo, hi = s.part.bbox
    assert lo[2] == pytest.approx(20.0, abs=0.05)  # tepe noktası z = 20


@occt
def test_k6_kesit_yuzu_adla_bulunur(ag, sb):
    s = ag.insa(kesme_agaci(ag, "alt"))
    kesit = yuzler(s.part, "kes", "kesit")
    assert kesit
    A = sb.bspline_yuzey(paraboloid_agi(cx=30.0, cy=30.0, z0=20.0), 0.01).area
    assert sum(f.area for f in kesit) == pytest.approx(A, rel=1e-3)
    for f in kesit:
        assert f.center().Z > 19.9


@occt
def test_k6_yuzeyi_asan_govde_hata(ag):
    """80 × 80 blok, 60 × 60 yüzeyle baştan başa kesilemez → hata; yüzey uzatılmaz."""
    s = ag.insa(kesme_agaci(ag, "alt", a=80.0, b=80.0))
    assert rapor(s, "kes").durum == "hata"
    assert s.basarili is False
    assert s.part.volume == pytest.approx(80.0 * 80.0 * 40.0, rel=1e-9)


# --- K7: JSON ---------------------------------------------------------------------------------------------


@occt
def test_k7_bspline_json_gidis_donus(ag):
    a = kesme_agaci(ag, "ust")
    d = ag.to_dict(a)
    b = ag.from_dict(json.loads(json.dumps(d)))
    assert ag.to_dict(b) == d
    assert b == a  # nokta ağı tuple olarak döner
    assert ag.insa(b).part.volume == pytest.approx(ag.insa(a).part.volume, rel=1e-9)


@occt
def test_k7_kalinlastirma_json(ag):
    a = ag.Agac((ag.BSplineYuzey("yuz", paraboloid_agi(), tol=0.005, kalinlik=-2.0),))
    b = ag.from_dict(json.loads(json.dumps(ag.to_dict(a))))
    assert b == a


# --- K8: hatalar -----------------------------------------------------------------------------------------


def ag_3x5():
    xs, ys = np.linspace(-30, 30, 3), np.linspace(-30, 30, 5)
    return tuple(tuple((float(x), float(y), 0.0) for y in ys) for x in xs)


def duzensiz_ag():
    a = [list(s) for s in paraboloid_agi()]
    a[3] = a[3][:-1]  # bir satır kısa
    return tuple(tuple(s) for s in a)


@occt
@pytest.mark.parametrize(
    ("noktalar", "tol"),
    [
        pytest.param(ag_3x5(), 0.01, id="3x5"),
        pytest.param(tuple(zip(*ag_3x5(), strict=True)), 0.01, id="5x3"),
        pytest.param(duzensiz_ag(), 0.01, id="duzensiz"),
        pytest.param(paraboloid_agi(), 0.0, id="tol-0"),
        pytest.param(paraboloid_agi(), -0.01, id="tol-negatif"),
    ],
)
def test_k8_yuzey_hatalari_dogrudan(sb, noktalar, tol):
    from geometry.part import GeometryError

    with pytest.raises(GeometryError):
        sb.bspline_yuzey(noktalar, tol)


@occt
@pytest.mark.parametrize("hangi", ["3x5", "tol-0"])
def test_k8_yuzey_hatalari_agacta(ag, hangi):
    oz = {
        "3x5": ag.BSplineYuzey("yuz", ag_3x5(), kalinlik=3.0),
        "tol-0": ag.BSplineYuzey("yuz", paraboloid_agi(), tol=0.0, kalinlik=3.0),
    }[hangi]
    sessiz_gecmez(ag, ag.Agac((oz,)), "yuz")


@occt
@pytest.mark.parametrize("t", [30.0, -30.0])
def test_k8_egrilik_yaricapindan_kalin(ag, t):
    """Eyer yüzeyi: merkezde iki yönde de eğrilik yarıçapı 10 mm; 30 mm kalınlık iki yönde de başarısız."""
    sessiz_gecmez(ag, ag.Agac((ag.BSplineYuzey("yuz", eyer_agi(), kalinlik=t),)), "yuz")


@occt
def test_k8_hata_bagimlilari_atlar(ag):
    """Hatalı yüzey unsuru uygulanmaz; sonraki bağımsız unsur devam eder."""
    a = ag.Agac(
        (
            ag.Blok("blok", 60, 60, 40),
            ag.BSplineYuzey("kes", ag_3x5(), kullanim="kes"),
            ag.Delik("delik", _ust_40(), ((30.0, 30.0),), d=10.0),
        )
    )
    s = ag.insa(a)
    assert rapor(s, "kes").durum == "hata"
    assert rapor(s, "delik").durum == "tamam"
    assert s.part.volume == pytest.approx(V_BLOK - 25 * np.pi * 40, rel=1e-6)


def _ust_40():
    from sketch.model import Plane

    return Plane((0, 0, 40), (0, 0, 1), (1, 0, 0))


# --- K9: SPEC 06 paralel finiş ---------------------------------------------------------------------------


@occt
@pytest.mark.slow
def test_k9_paralel_finis_yuzeye_yakin(ag, sb):
    """Küresel uçlu takım: CL = takım ucu, küre merkezi CL + (0, 0, R); |d(merkez, yüzey) − R| ≤ tol + 1e-3.

    Ağ ve raster toleransı tol = 0.01; tarama kenarlardan R'den fazla içeride (x, y ∈ [10, 50]).
    """
    from cam.dropcutter import TriMesh
    from cam.model import MoveType, Tool, ToolKind
    from cam.ops3d import Raster, finish

    tol = 0.01
    s = ag.insa(kesme_agaci(ag, "alt"))
    V, T = s.part.mesh(tol)
    R = 3.0
    takim = Tool(id=1, name="kuresel", kind=ToolKind.BALL, D=2 * R, flute_length=30.0)
    r = Raster(
        xmin=10.0,
        xmax=50.0,
        ymin=10.0,
        ymax=50.0,
        stepover=4.0,
        ds=1.0,
        tol=tol,
        ds_min=0.05,
        feed=800.0,
        plunge_feed=200.0,
        rpm=12000.0,
        z_safe=60.0,
    )
    tp = finish(TriMesh(V=np.asarray(V, float), T=np.asarray(T, int)), takim, r)
    cl = [m.end for m in tp.moves if m.type is MoveType.LINEAR and m.feed == r.feed]
    assert len(cl) > 100
    f = sb.bspline_yuzey(paraboloid_agi(cx=30.0, cy=30.0, z0=20.0), 0.01)
    for p in cl:
        d = f.distance_to(vektor((p[0], p[1], p[2] + R)))
        assert abs(d - R) <= tol + 1e-3
