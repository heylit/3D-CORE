"""SPEC 10 — bağlama kütüphanesi: K1 ölçü doğrulama ve gidiş-dönüş, K2 mengene, K3 ayna, K4 pabuç.

Testler sadece SPEC 10 metninden yazıldı; `cam/baglama.py` uygulama kodu okunmadı.
Beklenen değerler SPEC 10 Teori bölümündeki tablolar ve sayısal örneklerden elle hesaplandı
(her testin yorumunda). İlkellerin WCS sınır kutuları `baglama_ref.prim_aabb` ile (şekil köşeleri /
silindir ekseni `Frame.to_world` ile taşınarak) bulunur; ilkelin iç temsiline bağlı değildir.
Tolerans: mutlak 1e-9 mm (SPEC kabul kriterleri), hacimde göreli 1e-12.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from cam.model import CamError, CylinderStock, Stock
from tests.cam.baglama_ara import (
    Chuck3,
    Clamp,
    Fixture,
    Primitive,
    Vise,
    chuck_for,
    clamp_for,
    from_fixture,
    make_fixture,
    primitives_wcs,
    vise_for,
)
from tests.cam.baglama_ref import (
    CHUCK_GRIP,
    CHUCK_OLCU,
    CHUCK_STOK,
    CLAMP_OLCU,
    I3,
    STOK,
    VISE_GRIP,
    VISE_OLCU,
    Rz,
    box_center_wcs,
    cyl_axis_wcs,
    frame,
    prim_aabb,
)

NAN = float("nan")
ATOL = 1e-9


def kutu(prim, outer=None):
    lo, hi = prim_aabb(prim, outer)
    return np.concatenate([lo, hi])


def esit_kutu(prim, beklenen, outer=None):
    """beklenen = (xmin, ymin, zmin, xmax, ymax, zmax)"""
    np.testing.assert_allclose(kutu(prim, outer), beklenen, atol=ATOL, rtol=0)


VISE_D = dict(opening=50.0, parallel=5.0, **VISE_OLCU)
CHUCK_D = dict(grip_d=40.0, jaw_length=20.0, **CHUCK_OLCU)
CLAMP_D = dict(support_height=30.0, **CLAMP_OLCU)


def ornek_vise() -> Vise:
    return Vise(**VISE_D)


def ornek_chuck() -> Chuck3:
    return Chuck3(**CHUCK_D)


def ornek_clamp() -> Clamp:
    return Clamp(**CLAMP_D)


# ---------------------------------------------------------------- K1 ölçü doğrulama ve gidiş-dönüş


VISE_ALANLAR = [
    "jaw_width",
    "jaw_thickness",
    "jaw_height",
    "opening",
    "bed_height",
    "bed_extra",
    "parallel_width",
]


@pytest.mark.parametrize("alan", VISE_ALANLAR)
@pytest.mark.parametrize("deger", [0.0, -1.0, NAN])
def test_k1_mengene_olcu_pozitif(alan, deger):
    # SPEC Arayüz: "tüm ölçüler mm, > 0 (parallel ≥ 0)"; paralel varken (p = 5) her ölçü > 0 olmalı
    d = dict(VISE_D)
    d[alan] = deger
    with pytest.raises(CamError):
        Vise(**d)


@pytest.mark.parametrize("deger", [-1.0, NAN])
def test_k1_mengene_paralel_negatif_veya_nan(deger):
    with pytest.raises(CamError):
        Vise(opening=50.0, parallel=deger, **VISE_OLCU)


def test_k1_mengene_paralel_sifir_gecerli():
    v = Vise(opening=50.0, parallel=0.0, **VISE_OLCU)
    assert len(v.primitives()) == 3  # paralel yok: sabit, hareketli çene, yatak


@pytest.mark.parametrize("w_p", [25.0, 30.0])
def test_k1_mengene_paralel_genisligi_yarim_acikligi_asamaz(w_p):
    # w_p < w/2 olmalı; w = 50 → w_p = 25 (eşit) ve 30 hata
    d = dict(VISE_OLCU, parallel_width=w_p)
    with pytest.raises(CamError):
        Vise(opening=50.0, parallel=5.0, **d)


CHUCK_ALANLAR = ["grip_d", "jaw_length", "body_d", "body_length", "jaw_height", "jaw_width"]


@pytest.mark.parametrize("alan", CHUCK_ALANLAR)
@pytest.mark.parametrize("deger", [0.0, -2.0, NAN])
def test_k1_ayna_olcu_pozitif(alan, deger):
    d = dict(CHUCK_D)
    d[alan] = deger
    with pytest.raises(CamError):
        Chuck3(**d)


def test_k1_ayna_cene_genisligi_sqrt3_d():
    # w_j < √3·d olmalı: d = 10 → √3·10 = 17.32…; w_j = 17.4 hata, 17.3 geçer
    with pytest.raises(CamError):
        Chuck3(grip_d=10.0, jaw_length=5.0, jaw_width=17.4)
    with pytest.raises(CamError):
        Chuck3(grip_d=10.0, jaw_length=5.0, jaw_width=math.sqrt(3) * 10.0)
    Chuck3(grip_d=10.0, jaw_length=5.0, jaw_width=17.3)


CLAMP_ALANLAR = [
    "support_height",
    "arm_length",
    "arm_width",
    "arm_thickness",
    "bolt_d",
    "bolt_above",
    "heel_width",
]


@pytest.mark.parametrize("alan", CLAMP_ALANLAR)
@pytest.mark.parametrize("deger", [0.0, -3.0, NAN])
def test_k1_pabuc_olcu_pozitif(alan, deger):
    d = dict(CLAMP_D)
    d[alan] = deger
    with pytest.raises(CamError):
        Clamp(**d)


def test_k1_pabuc_kol_civatadan_dar_olamaz():
    # w_a ≥ d_b olmalı: d_b = 12 → w_a = 11.9 hata, w_a = 12 geçer
    with pytest.raises(CamError):
        Clamp(support_height=30.0, arm_width=11.9, bolt_d=12.0)
    Clamp(support_height=30.0, arm_width=12.0, bolt_d=12.0)


def test_k1_pabuc_topuk_civata_kol_ortasini_gecemez():
    # w_h + d_b/2 < L_a/2 olmalı: L_a = 80, d_b = 12 → w_h < 34; 34 (eşit) ve 35 hata, 33.9 geçer
    for w_h in (34.0, 35.0):
        with pytest.raises(CamError):
            Clamp(support_height=30.0, arm_length=80.0, bolt_d=12.0, heel_width=w_h)
    Clamp(support_height=30.0, arm_length=80.0, bolt_d=12.0, heel_width=33.9)


@pytest.mark.parametrize("uret", [ornek_vise, ornek_chuck, ornek_clamp], ids=["mengene", "ayna", "pabuc"])
def test_k1_params_gidis_donus(uret):
    item = uret()
    p = item.params()
    assert all(isinstance(v, float) for v in p.values())
    assert type(item).from_params(p) == item


@pytest.mark.parametrize(
    ("uret", "kind"),
    [(ornek_vise, "mengene"), (ornek_chuck, "ayna"), (ornek_clamp, "pabuc")],
    ids=["mengene", "ayna", "pabuc"],
)
def test_k1_make_fixture_from_fixture(uret, kind):
    item = uret()
    fr = frame((1.0, 2.0, 3.0), Rz(90))
    fx = make_fixture("bag_1", item, fr)
    assert isinstance(fx, Fixture)
    assert fx.name == "bag_1"
    assert fx.part_ref == "bag_1"  # part_ref = name
    assert fx.kind == kind
    assert fx.frame == fr
    assert fx.params == tuple(sorted(item.params().items()))
    assert from_fixture(fx) == item
    # Fixture.to_dict → from_dict → from_fixture aynı eleman
    fx2 = Fixture.from_dict(fx.to_dict())
    assert fx2 == fx
    assert from_fixture(fx2) == item


def test_k1_from_fixture_ozel_hata():
    fx = Fixture(name="ozel_1", part_ref="parca", kind="ozel")
    with pytest.raises(CamError):
        from_fixture(fx)


@pytest.mark.parametrize("bozma", ["eksik", "fazla", "gecersiz"])
def test_k1_from_fixture_bozuk_params(bozma):
    fx = make_fixture("m", ornek_vise(), frame())
    p = dict(fx.params)
    ilk = sorted(p)[0]
    if bozma == "eksik":
        del p[ilk]
    elif bozma == "fazla":
        p["zzz_fazla"] = 1.0
    else:
        p[ilk] = -1.0  # ölçü kuralı bozuk
    bozuk = Fixture(name="m", part_ref="m", frame=fx.frame, kind="mengene", params=tuple(sorted(p.items())))
    with pytest.raises(CamError):
        from_fixture(bozuk)


def test_k1_ilkel_sozluk_ve_hacim():
    s = Stock(1, 2, 3, 4, 6, 8)
    fr = frame((5.0, 0.0, 0.0), Rz(90))
    p = Primitive(s, fr)
    assert p.to_dict() == {"shape": s.to_dict(), "frame": fr.to_dict()}
    assert p.volume == pytest.approx(3 * 4 * 5, rel=1e-12)
    c = CylinderStock(10, 0, 7)
    assert Primitive(c).volume == pytest.approx(math.pi * 25 * 7, rel=1e-12)
    assert Primitive(c).frame.R == I3
    assert Primitive(c).frame.origin == (0.0, 0.0, 0.0)


# ---------------------------------------------------------------- K2 mengene


def test_k2_mengene_yerel_ilkeller():
    # Teori tablosu, b = 100, t = 20, h_j = 15, w = 50, h_b = 40, s = 60, p = 5, w_p = 6
    pr = ornek_vise().primitives()
    assert len(pr) == 5
    esit_kutu(pr[0], (-50, -45, 0, 50, -25, 15))  # sabit çene: y ∈ [−w/2 − t, −w/2]
    esit_kutu(pr[1], (-50, 25, 0, 50, 45, 15))  # hareketli çene: y ∈ [w/2, w/2 + t]
    esit_kutu(pr[2], (-50, -45, -40, 50, 105, 0))  # yatak: y ∈ [−w/2 − t, w/2 + t + s]
    esit_kutu(pr[3], (-50, -25, 0, 50, -19, 5))  # paraleller
    esit_kutu(pr[4], (-50, 19, 0, 50, 25, 5))


def test_k2_vise_for_teori_ornegi():
    v, fr = vise_for(STOK, VISE_GRIP, "x", **VISE_OLCU)
    assert isinstance(v, Vise)
    # w = ymax − ymin = 50, p = h_j − g = 5, origin = (x_c, y_c, zmin − p) = (40, 25, −5), R = I
    assert v.opening == pytest.approx(50.0, abs=ATOL)
    assert v.parallel == pytest.approx(5.0, abs=ATOL)
    assert v.jaw_width == 100.0 and v.jaw_thickness == 20.0 and v.jaw_height == 15.0
    np.testing.assert_allclose(fr.origin, (40, 25, -5), atol=ATOL)
    np.testing.assert_allclose(np.array(fr.R), np.eye(3), atol=1e-12)
    pr = primitives_wcs(make_fixture("mengene", v, fr))
    assert len(pr) == 5
    # Teori: sabit çene [−10, 90] × [−20, 0] × [−5, 10], hareketli y ∈ [50, 70],
    # yatak y ∈ [−20, 130], z ∈ [−45, −5]; paraleller y ∈ [0, 6] ve [44, 50], z ∈ [−5, 0]
    esit_kutu(pr[0], (-10, -20, -5, 90, 0, 10))
    esit_kutu(pr[1], (-10, 50, -5, 90, 70, 10))
    esit_kutu(pr[2], (-10, -20, -45, 90, 130, -5))
    esit_kutu(pr[3], (-10, 0, -5, 90, 6, 0))
    esit_kutu(pr[4], (-10, 44, -5, 90, 50, 0))
    # V = 2·b·t·h_j + b·(w + 2t + s)·h_b + 2·b·w_p·p = 60000 + 600000 + 6000
    assert sum(p.volume for p in pr) == pytest.approx(666000.0, rel=1e-12)
    assert sum(p.volume for p in v.primitives()) == pytest.approx(666000.0, rel=1e-12)


def test_k2_vise_for_y_ekseni():
    # axis = "y": sıkma WCS X, w = xmax − xmin = 80, R = R_z(90°): (x, y) → (−y, x)
    v, fr = vise_for(STOK, VISE_GRIP, "y", **VISE_OLCU)
    assert v.opening == pytest.approx(80.0, abs=ATOL)
    assert v.parallel == pytest.approx(5.0, abs=ATOL)
    np.testing.assert_allclose(fr.origin, (40, 25, -5), atol=ATOL)
    np.testing.assert_allclose(np.array(fr.R), np.array(Rz(90)), atol=1e-12)
    pr = primitives_wcs(make_fixture("mengene", v, fr))
    # yerel sabit çene x ∈ [−50, 50], y ∈ [−60, −40] → WCS x = 40 − y ∈ [80, 100], y = 25 + x ∈ [−25, 75]
    esit_kutu(pr[0], (80, -25, -5, 100, 75, 10))
    esit_kutu(pr[1], (-20, -25, -5, 0, 75, 10))  # hareketli: yerel y ∈ [40, 60]
    esit_kutu(pr[2], (-80, -25, -45, 100, 75, -5))  # yatak: yerel y ∈ [−60, 120]
    esit_kutu(pr[3], (74, -25, -5, 80, 75, 0))  # paralel yerel y ∈ [−40, −34]
    esit_kutu(pr[4], (0, -25, -5, 6, 75, 0))  # paralel yerel y ∈ [34, 40]
    # V = 60000 + 100·(80 + 40 + 60)·40 + 6000 = 786000
    assert sum(p.volume for p in pr) == pytest.approx(786000.0, rel=1e-12)


def test_k2_vise_for_paralelsiz():
    # g = h_j → p = 0, paralel yok, origin z = zmin
    v, fr = vise_for(STOK, 15.0, "x", **VISE_OLCU)
    assert v.parallel == pytest.approx(0.0, abs=ATOL)
    assert len(v.primitives()) == 3
    np.testing.assert_allclose(fr.origin, (40, 25, 0), atol=ATOL)


def test_k2_vise_for_cene_yetmiyor():
    # p = h_j − g < 0 → CamError (h_j = 15, g = 16)
    with pytest.raises(CamError):
        vise_for(STOK, 16.0, "x", **VISE_OLCU)


@pytest.mark.parametrize("g", [30.0, 31.0])
def test_k2_vise_for_cene_stok_ustune_cikiyor(g):
    # g ≥ zmax − zmin = 30 → CamError (h_j yeterince büyük ki p ≥ 0)
    d = dict(VISE_OLCU, jaw_height=40.0)
    with pytest.raises(CamError):
        vise_for(STOK, g, "x", **d)


# ---------------------------------------------------------------- K3 ayna


def test_k3_chuck_for_teori_ornegi():
    c, fr = chuck_for(CHUCK_STOK, CHUCK_GRIP, **CHUCK_OLCU)
    assert isinstance(c, Chuck3)
    # d = stock.D = 40, L_j = grip = 20, origin = (0, 0, stock.zmin), R = I
    assert c.grip_d == pytest.approx(40.0, abs=ATOL)
    assert c.jaw_length == pytest.approx(20.0, abs=ATOL)
    np.testing.assert_allclose(fr.origin, (0, 0, -60), atol=ATOL)
    np.testing.assert_allclose(np.array(fr.R), np.eye(3), atol=1e-12)


def test_k3_ayna_halkalari():
    c, fr = chuck_for(CHUCK_STOK, CHUCK_GRIP, **CHUCK_OLCU)
    halkalar = c.rings(fr)
    assert len(halkalar) == 2
    cene, govde = halkalar
    assert isinstance(cene, CylinderStock) and isinstance(govde, CylinderStock)
    # r_o = √((d/2 + h)² + (w_j/2)²) = √(45² + 10²) = √2125
    assert cene.D == pytest.approx(2 * math.sqrt(2125), abs=ATOL)
    assert cene.D / 2 == pytest.approx(46.0977222864644, abs=1e-9)
    assert cene.d == pytest.approx(40.0, abs=ATOL)
    assert (cene.zmin, cene.zmax) == pytest.approx((-60.0, -40.0), abs=ATOL)
    # gövde CylinderStock(D_b, z_f − L_b, z_f)
    assert govde.D == pytest.approx(160.0, abs=ATOL)
    assert govde.d == pytest.approx(0.0, abs=ATOL)
    assert (govde.zmin, govde.zmax) == pytest.approx((-140.0, -60.0), abs=ATOL)


def test_k3_ayna_halkasi_alin_z():
    # z_f alnın WCS Z'si: çerçeve 5 mm yukarıda → halkalar 5 mm yukarı
    c = ornek_chuck()
    cene, govde = c.rings(frame((0, 0, 5)))
    assert (cene.zmin, cene.zmax) == pytest.approx((5.0, 25.0), abs=ATOL)
    assert (govde.zmin, govde.zmax) == pytest.approx((-75.0, 5.0), abs=ATOL)


def test_k3_ayna_halkasi_egik_cerceve_hata():
    from tests.cam.baglama_ref import Rx

    with pytest.raises(CamError):
        ornek_chuck().rings(frame((0, 0, 0), Rx(90)))


def test_k3_ayna_ilkelleri_ve_hacim():
    c, fr = chuck_for(CHUCK_STOK, CHUCK_GRIP, **CHUCK_OLCU)
    pr = primitives_wcs(make_fixture("ayna", c, fr))
    assert len(pr) == 4
    # gövde: silindir D_b = 160, z ∈ [−L_b, 0] yerel → WCS [−140, −60], eksen (0, 0)
    xy, r, z0, z1 = cyl_axis_wcs(pr[0])
    assert isinstance(pr[0].shape, CylinderStock)
    np.testing.assert_allclose(xy, (0, 0), atol=ATOL)
    assert (r, z0, z1) == pytest.approx((80.0, -140.0, -60.0), abs=ATOL)
    # çene i ağırlık merkezi R_z(θ_i)·(d/2 + h/2, 0, L_j/2) + origin = R_z(θ)·(32.5, 0, 10) + (0, 0, −60)
    for p, th in zip(pr[1:], (90.0, 210.0, 330.0), strict=True):
        assert isinstance(p.shape, Stock)
        t = math.radians(th)
        np.testing.assert_allclose(
            box_center_wcs(p), (32.5 * math.cos(t), 32.5 * math.sin(t), -50.0), atol=ATOL
        )
        assert p.volume == pytest.approx(25 * 20 * 20, rel=1e-12)  # h·w_j·L_j
    # V = π (D_b/2)² L_b + 3·h·w_j·L_j
    V = math.pi * 80**2 * 80 + 3 * 25 * 20 * 20
    assert sum(p.volume for p in pr) == pytest.approx(V, rel=1e-12)


def test_k3_cene_90_derece_kutusu():
    # θ = 90°: yerel x ∈ [20, 45], y ∈ [−10, 10] → WCS x ∈ [−10, 10], y ∈ [20, 45]; z ∈ [0, 20] + (−60)
    c, fr = chuck_for(CHUCK_STOK, CHUCK_GRIP, **CHUCK_OLCU)
    pr = primitives_wcs(make_fixture("ayna", c, fr))
    esit_kutu(pr[1], (-10, 20, -60, 10, 45, -40))


@pytest.mark.parametrize("grip", [60.0, 61.0])
def test_k3_chuck_for_grip_boy_hata(grip):
    # grip ≥ stock.length = 60 → CamError
    with pytest.raises(CamError):
        chuck_for(CHUCK_STOK, grip, **CHUCK_OLCU)


# ---------------------------------------------------------------- K4 pabuç


def test_k4_pabuc_yerel_ilkeller():
    pr = ornek_clamp().primitives()
    assert len(pr) == 3
    esit_kutu(pr[0], (-80, -10, 0, 0, 10, 12))  # kol: x ∈ [−L_a, 0], z ∈ [0, t_a]
    esit_kutu(pr[1], (-80, -10, -30, -65, 10, 0))  # topuk: x ∈ [−L_a, −L_a + w_h], z ∈ [−H_s, 0]
    xy, r, z0, z1 = cyl_axis_wcs(pr[2])  # cıvata: eksen x = −L_a/2, z ∈ [−H_s, t_a + h_c]
    assert isinstance(pr[2].shape, CylinderStock)
    np.testing.assert_allclose(xy, (-40, 0), atol=ATOL)
    assert (r, z0, z1) == pytest.approx((6.0, -30.0, 27.0), abs=ATOL)


# side → (at, burun origin, kol kutusu, cıvata ekseni XY, topuk kutusu); Stock(0, 0, 0, 80, 50, 30), o = 8.
# R: x- → I, x+ → R_z(180°), y- → R_z(90°), y+ → R_z(−90°); H_s = 30; kol z ∈ [30, 42], topuk z ∈ [0, 30].
PABUC_DURUMLARI = {
    # y-: Teori örneği. origin (at, ymin + o, zmax) = (40, 8, 30); R_z(90): WCS x = 40 − y_l, y = 8 + x_l
    "y-": (40.0, (40, 8, 30), (30, -72, 30, 50, 8, 42), (40, -32), (30, -72, 0, 50, -57, 30)),
    # y+: origin (40, 42, 30); R_z(−90): WCS x = 40 + y_l, y = 42 − x_l
    "y+": (40.0, (40, 42, 30), (30, 42, 30, 50, 122, 42), (40, 82), (30, 107, 0, 50, 122, 30)),
    # x-: origin (xmin + o, at, zmax) = (8, 25, 30); R = I
    "x-": (25.0, (8, 25, 30), (-72, 15, 30, 8, 35, 42), (-32, 25), (-72, 15, 0, -57, 35, 30)),
    # x+: origin (72, 25, 30); R_z(180): WCS x = 72 − x_l, y = 25 − y_l
    "x+": (25.0, (72, 25, 30), (72, 15, 30, 152, 35, 42), (112, 25), (137, 15, 0, 152, 35, 30)),
}
PABUC_R = {"y-": Rz(90), "y+": Rz(-90), "x-": I3, "x+": Rz(180)}


@pytest.mark.parametrize("side", list(PABUC_DURUMLARI))
def test_k4_clamp_for_dort_kenar(side):
    at, org, kol, civata, topuk = PABUC_DURUMLARI[side]
    c, fr = clamp_for(STOK, side, at, 8.0, **CLAMP_OLCU)
    assert isinstance(c, Clamp)
    assert c.support_height == pytest.approx(30.0, abs=ATOL)  # H_s = zmax − zmin
    np.testing.assert_allclose(fr.origin, org, atol=ATOL)
    np.testing.assert_allclose(np.array(fr.R), np.array(PABUC_R[side]), atol=1e-12)
    pr = primitives_wcs(make_fixture("pabuc", c, fr))
    esit_kutu(pr[0], kol)
    esit_kutu(pr[1], topuk)
    xy, r, z0, z1 = cyl_axis_wcs(pr[2])
    np.testing.assert_allclose(xy, civata, atol=ATOL)
    assert (r, z0, z1) == pytest.approx((6.0, 0.0, 57.0), abs=ATOL)


def test_k4_pabuc_hacim():
    c, fr = clamp_for(STOK, "y-", 40.0, 8.0, **CLAMP_OLCU)
    pr = primitives_wcs(make_fixture("pabuc", c, fr))
    # ilkel başına: kol L_a w_a t_a, topuk w_h w_a H_s, cıvata π (d_b/2)² (H_s + t_a + h_c) (tam boy ilkel)
    assert pr[0].volume == pytest.approx(80 * 20 * 12, rel=1e-12)
    assert pr[1].volume == pytest.approx(15 * 20 * 30, rel=1e-12)
    assert pr[2].volume == pytest.approx(math.pi * 36 * (30 + 12 + 15), rel=1e-12)
    # birleşim hacmi (cıvatanın koldaki t_a boyu bir kez): V = 19200 + 9000 + 36π·45
    V = 19200 + 9000 + 36 * math.pi * 45
    birlesim = sum(p.volume for p in pr) - math.pi * 36 * 12
    assert birlesim == pytest.approx(V, rel=1e-12)


@pytest.mark.parametrize("o", [0.0, -1.0])
def test_k4_clamp_for_overlap_pozitif(o):
    with pytest.raises(CamError):
        clamp_for(STOK, "y-", 40.0, o, **CLAMP_OLCU)


@pytest.mark.parametrize("o", [34.0, 35.0])
def test_k4_clamp_for_civata_stoga_giriyor(o):
    # o < L_a/2 − d_b/2 = 34 olmalı
    with pytest.raises(CamError):
        clamp_for(STOK, "y-", 40.0, o, **CLAMP_OLCU)


def test_k4_clamp_for_civata_siniri_ici_gecer():
    c, fr = clamp_for(STOK, "y-", 40.0, 33.5, **CLAMP_OLCU)
    np.testing.assert_allclose(fr.origin, (40, 33.5, 30), atol=ATOL)


def test_k4_clamp_for_overlap_stok_boyunu_asamaz():
    # y kenarında stok boyu 50; L_a = 200 ile cıvata koşulu (o < 94) tutar ama o = 60 > 50
    d = dict(CLAMP_OLCU, arm_length=200.0)
    with pytest.raises(CamError):
        clamp_for(STOK, "y-", 40.0, 60.0, **d)


@pytest.mark.parametrize("at", [5.0, 75.0, -10.0, 100.0])
def test_k4_clamp_for_at_kenar_disi(at):
    # y- kenarı x ∈ [0, 80]; w_a/2 = 10 payla at ∈ [10, 70] olmalı
    with pytest.raises(CamError):
        clamp_for(STOK, "y-", at, 8.0, **CLAMP_OLCU)


def test_k4_clamp_for_at_x_kenari_disi():
    # x- kenarı y ∈ [0, 50]; at = 45 > 50 − 10
    with pytest.raises(CamError):
        clamp_for(STOK, "x-", 45.0, 8.0, **CLAMP_OLCU)
