"""SPEC 17 K13 — sketch/model.py veri modeli testleri.

Testler SPEC 17 "Arayüz / sketch/model.py" bölümünden yazıldı; hazır test taslakları kullanılmadı.
Kapsam: Plane (ortonormallik, to_world / to_local), öğe ve kısıt veri sınıfları, Sketch.validate hataları,
to_dict → JSON → from_dict gidiş-dönüşü, çıktı tipleri (SegLine, SegArc, SketchRegion).
Kabul edilen ek alan: Constraint.internal (daire–daire TANGENT'inde iç / dış teğet).
"""

from __future__ import annotations

import dataclasses
import json
import math

import numpy as np
import pytest

from sketch.model import (
    Arc,
    Circle,
    Constraint,
    ConstraintType,
    Line,
    Plane,
    Point,
    SegArc,
    SegLine,
    Sketch,
    SketchError,
    SketchRegion,
)

CT = ConstraintType


# --- Yardımcılar --------------------------------------------------------------------------------------


def dikdortgen() -> Sketch:
    """40×30 dikdörtgen + içinde r = 5 daire + yay; her referans türünden birkaç geçerli kısıt."""
    points = {
        "a": Point(0.0, 0.0, fixed=True),
        "b": Point(40.0, 0.0),
        "c": Point(40.0, 30.0),
        "d": Point(0.0, 30.0),
        "m": Point(20.0, 15.0),
        "ac": Point(60.0, 0.0),
        "as": Point(70.0, 0.0),
        "ae": Point(60.0, 10.0),
    }
    entities = {
        "l1": Line("a", "b"),
        "l2": Line("b", "c"),
        "l3": Line("c", "d"),
        "l4": Line("d", "a"),
        "k": Line("a", "c", construction=True),
        "o": Circle("m", 5.0),
        "y": Arc("ac", "as", "ae"),
    }
    constraints = [
        Constraint(CT.HORIZONTAL, ("l1",)),
        Constraint(CT.VERTICAL, ("l2",)),
        Constraint(CT.HORIZONTAL, ("l3",)),
        Constraint(CT.VERTICAL, ("l4",)),
        Constraint(CT.LENGTH, ("l1",), 40.0),
        Constraint(CT.LENGTH, ("l2",), 30.0),
        Constraint(CT.MIDPOINT, ("m", "k")),
        Constraint(CT.RADIUS, ("o",), 5.0),
        Constraint(CT.DIAMETER, ("y",), 20.0),
        Constraint(CT.DISTANCE, ("m", "l1"), 15.0),
        Constraint(CT.HDISTANCE, ("b", "a"), -40.0),
        Constraint(CT.ANGLE, ("l1", "k"), 36.86989764584402),
        Constraint(CT.TANGENT, ("l2", "y"), side=-1),
        Constraint(CT.TANGENT, ("o", "y"), internal=False),
        Constraint(CT.SYMMETRIC, ("a", "b", "k")),
    ]
    return Sketch(plane=Plane.XY(), points=points, entities=entities, constraints=constraints)


def eskiz(points, entities, constraints) -> Sketch:
    return Sketch(plane=Plane.XY(), points=points, entities=entities, constraints=constraints)


def iki_nokta(c: Constraint) -> Sketch:
    return eskiz({"p": Point(0.0, 0.0), "q": Point(3.0, 4.0)}, {}, [c])


def birim(v) -> np.ndarray:
    v = np.asarray(v, dtype=float)
    return v / np.linalg.norm(v)


def rastgele_duzlem(rng: np.random.Generator) -> Plane:
    n = birim(rng.normal(size=3))
    x = rng.normal(size=3)
    x = birim(x - (x @ n) * n)
    return Plane(rng.uniform(-100.0, 100.0, size=3), n, x)


# --- SketchError --------------------------------------------------------------------------------------


def test_sketch_error_is_value_error():
    assert issubclass(SketchError, ValueError)


# --- Plane --------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "plane, n, x",
    [
        (Plane.XY(), (0, 0, 1), (1, 0, 0)),
        (Plane.XZ(), None, None),
        (Plane.YZ(), None, None),
    ],
)
def test_hazir_duzlemler_ortonormal(plane, n, x):
    """Hazır düzlemler orijinden geçer, normal ve xdir birim ve dik; ydir = normal × xdir."""
    assert np.allclose(plane.origin, 0.0)
    assert np.linalg.norm(plane.normal) == pytest.approx(1.0, abs=1e-12)
    assert np.linalg.norm(plane.xdir) == pytest.approx(1.0, abs=1e-12)
    assert abs(float(np.dot(plane.normal, plane.xdir))) < 1e-12
    assert np.allclose(plane.ydir, np.cross(plane.normal, plane.xdir), atol=1e-12)
    if n is not None:
        assert np.allclose(plane.normal, n) and np.allclose(plane.xdir, x)


@pytest.mark.parametrize("plane, eksik", [(Plane.XY(), 2), (Plane.XZ(), 1), (Plane.YZ(), 0)])
def test_hazir_duzlem_normali_adina_uygun(plane, eksik):
    """XY düzleminin normali Z ekseni, XZ'ninki Y, YZ'ninki X ekseni boyuncadır (işaret serbest)."""
    e = np.zeros(3)
    e[eksik] = 1.0
    assert abs(float(np.dot(plane.normal, e))) == pytest.approx(1.0, abs=1e-12)


def test_ydir_xy():
    assert np.allclose(Plane.XY().ydir, (0.0, 1.0, 0.0), atol=1e-12)


def test_to_world_xy():
    assert np.allclose(Plane.XY().to_world((3.0, 4.0)), (3.0, 4.0, 0.0), atol=1e-12)


def test_to_world_shape_and_to_local_shape():
    pl = Plane.XY()
    assert np.asarray(pl.to_world((1.0, 2.0))).shape == (3,)
    assert np.asarray(pl.to_local((1.0, 2.0, 0.0))).shape == (2,)


def test_to_world_kaydirilmis_duzlem():
    """origin + u·xdir + v·ydir."""
    o = np.array([10.0, -5.0, 7.0])
    pl = Plane(o, (0.0, 0.0, 1.0), (0.0, 1.0, 0.0))  # ydir = z × y = −x
    assert np.allclose(pl.to_world((2.0, 3.0)), o + 2.0 * np.array([0, 1, 0]) + 3.0 * np.array([-1, 0, 0]))


def test_to_world_to_local_gidis_donus():
    """Rastgele düzlemlerde to_world(to_local(p)) = p ve to_local(to_world(uv)) = uv (1e-12 göreli)."""
    rng = np.random.default_rng(17)
    for _ in range(20):
        pl = rastgele_duzlem(rng)
        uv = rng.uniform(-50.0, 50.0, size=2)
        p = pl.to_world(uv)
        assert np.allclose(pl.to_local(p), uv, rtol=0.0, atol=1e-12 * 200)
        assert np.allclose(pl.to_world(pl.to_local(p)), p, rtol=0.0, atol=1e-12 * 200)


def test_to_local_duzlem_disi_hata():
    """Düzlemden uzaklık > 1e-9 mm → SketchError."""
    pl = Plane.XY()
    with pytest.raises(SketchError):
        pl.to_local((1.0, 2.0, 1e-6))
    with pytest.raises(SketchError):
        pl.to_local((1.0, 2.0, -0.5))


def test_to_local_tolerans_icinde_kabul():
    """1e-9'un altındaki dik bileşen atılır."""
    uv = Plane.XY().to_local((1.0, 2.0, 1e-12))
    assert np.allclose(uv, (1.0, 2.0), atol=1e-12)


@pytest.mark.parametrize(
    "normal, xdir",
    [
        ((0.0, 0.0, 2.0), (1.0, 0.0, 0.0)),  # normal birim değil
        ((0.0, 0.0, 1.0), (1.0, 1.0, 0.0)),  # xdir birim değil
        ((0.0, 0.0, 1.0), (math.sqrt(0.5), 0.0, math.sqrt(0.5))),  # dik değil
        ((0.0, 0.0, 1.0), (0.0, 0.0, 1.0)),  # paralel
        ((0.0, 0.0, 0.0), (1.0, 0.0, 0.0)),  # sıfır normal
    ],
)
def test_ortonormal_olmayan_duzlem_hata(normal, xdir):
    with pytest.raises(SketchError):
        Plane((0.0, 0.0, 0.0), normal, xdir)


def test_duzlem_frozen():
    pl = Plane.XY()
    with pytest.raises(dataclasses.FrozenInstanceError):
        pl.origin = np.array([1.0, 0.0, 0.0])


# --- Öğeler ve kısıt ----------------------------------------------------------------------------------


def test_oge_varsayilanlari():
    p = Point(1.0, 2.0)
    assert (p.x, p.y, p.fixed) == (1.0, 2.0, False)
    assert Line("a", "b").construction is False
    c = Circle("m", 5.0)
    assert (c.center, c.r, c.construction) == ("m", 5.0, False)
    a = Arc("c", "s", "e")
    assert (a.center, a.start, a.end, a.construction) == ("c", "s", "e", False)


def test_constraint_varsayilanlari():
    c = Constraint(CT.LENGTH, ("l1",), 10.0)
    assert c.type == CT.LENGTH
    assert c.refs == ("l1",)
    assert c.value == 10.0
    assert c.side == 0
    assert c.internal is False
    assert Constraint(CT.HORIZONTAL, ("l1",)).value is None


SPEC_TURLERI = (
    "COINCIDENT POINT_ON_LINE POINT_ON_CIRCLE MIDPOINT HORIZONTAL VERTICAL PARALLEL PERPENDICULAR ANGLE "
    "EQUAL LENGTH DISTANCE HDISTANCE VDISTANCE RADIUS DIAMETER TANGENT SYMMETRIC"
).split()


def test_constraint_type_spec_tablosu():
    """Tablodaki her tür ConstraintType'ta var."""
    adlar = {t.name for t in ConstraintType}
    assert set(SPEC_TURLERI) <= adlar


# --- validate: geçerli eskizler -----------------------------------------------------------------------


def test_gecerli_eskiz_validate_gecer():
    dikdortgen().validate()


def test_bos_eskiz_gecerli():
    Sketch(plane=Plane.XY(), points={}, entities={}, constraints=[]).validate()


def gecerli_tum_satirlar() -> list[Constraint]:
    """SPEC tablosundaki her (tür, referans) satırı için bir geçerli kısıt (dikdortgen() kimlikleriyle)."""
    return [
        Constraint(CT.COINCIDENT, ("b", "as")),
        Constraint(CT.POINT_ON_LINE, ("m", "l1")),
        Constraint(CT.POINT_ON_CIRCLE, ("b", "o")),
        Constraint(CT.POINT_ON_CIRCLE, ("b", "y")),
        Constraint(CT.MIDPOINT, ("m", "l3")),
        Constraint(CT.HORIZONTAL, ("l1",)),
        Constraint(CT.HORIZONTAL, ("a", "b")),
        Constraint(CT.VERTICAL, ("l2",)),
        Constraint(CT.VERTICAL, ("b", "c")),
        Constraint(CT.PARALLEL, ("l1", "l3")),
        Constraint(CT.PERPENDICULAR, ("l1", "l2")),
        Constraint(CT.ANGLE, ("l1", "l2"), 90.0),
        Constraint(CT.ANGLE, ("l1", "l2"), -30.0),
        Constraint(CT.EQUAL, ("l1", "l3")),
        Constraint(CT.EQUAL, ("o", "y")),
        Constraint(CT.LENGTH, ("l1",), 40.0),
        Constraint(CT.DISTANCE, ("a", "c"), 50.0),
        Constraint(CT.DISTANCE, ("m", "l1"), 15.0),
        Constraint(CT.DISTANCE, ("m", "l1"), -15.0),  # işaretli
        Constraint(CT.DISTANCE, ("m", "l1"), 0.0),  # nokta–çizgi: D = 0 serbest
        Constraint(CT.HDISTANCE, ("a", "b"), 40.0),
        Constraint(CT.HDISTANCE, ("b", "a"), -40.0),
        Constraint(CT.VDISTANCE, ("a", "d"), 30.0),
        Constraint(CT.VDISTANCE, ("d", "a"), -30.0),
        Constraint(CT.RADIUS, ("o",), 5.0),
        Constraint(CT.RADIUS, ("y",), 10.0),
        Constraint(CT.DIAMETER, ("o",), 10.0),
        Constraint(CT.TANGENT, ("l2", "o")),
        Constraint(CT.TANGENT, ("l2", "y"), side=1),
        Constraint(CT.TANGENT, ("l2", "y"), side=-1),
        Constraint(CT.TANGENT, ("o", "y")),
        Constraint(CT.TANGENT, ("o", "y"), internal=True),
        Constraint(CT.TANGENT, ("o", "y"), side=-1, internal=True),
        Constraint(CT.SYMMETRIC, ("a", "b", "k")),
    ]


@pytest.mark.parametrize("c", gecerli_tum_satirlar(), ids=lambda c: f"{c.type.name}-{'-'.join(c.refs)}")
def test_tablo_satiri_gecerli(c):
    s = dikdortgen()
    s.constraints = [c]
    s.validate()


# --- validate: hatalar --------------------------------------------------------------------------------


def hata_beklenir(s: Sketch, sira: int | None = None) -> SketchError:
    with pytest.raises(SketchError) as ei:
        s.validate()
    if sira is not None:
        assert str(sira) in str(ei.value), f"mesajda kısıt sırası {sira} yok: {ei.value}"
    return ei.value


def test_cizgide_bilinmeyen_nokta():
    hata_beklenir(eskiz({"a": Point(0, 0)}, {"l": Line("a", "yok")}, []))


def test_dairede_bilinmeyen_merkez():
    hata_beklenir(eskiz({}, {"o": Circle("yok", 5.0)}, []))


def test_yayda_bilinmeyen_nokta():
    hata_beklenir(eskiz({"c": Point(0, 0), "s": Point(1, 0)}, {"y": Arc("c", "s", "yok")}, []))


def test_kisitta_bilinmeyen_kimlik_sirasi_mesajda():
    s = dikdortgen()
    s.constraints.append(Constraint(CT.LENGTH, ("yok",), 5.0))
    hata_beklenir(s, len(s.constraints) - 1)


def test_cizgi_ayni_uc_noktalar_hata():
    """Line: p0 != p1."""
    hata_beklenir(eskiz({"a": Point(0, 0)}, {"l": Line("a", "a")}, []))


@pytest.mark.parametrize("ids", [("c", "c", "e"), ("c", "s", "c"), ("c", "s", "s")])
def test_yay_kimlikleri_farkli_olmali(ids):
    pts = {"c": Point(0, 0), "s": Point(1, 0), "e": Point(0, 1)}
    hata_beklenir(eskiz(pts, {"y": Arc(*ids)}, []))


@pytest.mark.parametrize("r", [0.0, -1.0, math.inf, math.nan])
def test_daire_yaricapi_pozitif_sonlu(r):
    hata_beklenir(eskiz({"m": Point(0, 0)}, {"o": Circle("m", r)}, []))


@pytest.mark.parametrize(
    "c, sira_mesajda",
    [
        (Constraint(CT.HORIZONTAL, ("o",)), True),  # daire HORIZONTAL olamaz
        (Constraint(CT.VERTICAL, ("a",)), True),  # tek nokta
        (Constraint(CT.LENGTH, ("o",), 5.0), True),  # LENGTH çizgi ister
        (Constraint(CT.RADIUS, ("l1",), 5.0), True),  # RADIUS daire/yay ister
        (Constraint(CT.DIAMETER, ("a",), 5.0), True),
        (Constraint(CT.COINCIDENT, ("a", "l1")), True),
        (Constraint(CT.POINT_ON_LINE, ("a", "o")), True),
        (Constraint(CT.POINT_ON_CIRCLE, ("a", "l1")), True),
        (Constraint(CT.PARALLEL, ("l1", "o")), True),
        (Constraint(CT.EQUAL, ("l1", "o")), True),  # çizgi–daire EQUAL tabloda yok
        (Constraint(CT.TANGENT, ("l1", "l2")), True),  # çizgi–çizgi TANGENT tabloda yok
        (Constraint(CT.TANGENT, ("a", "o")), True),
        (Constraint(CT.HDISTANCE, ("a", "l1"), 3.0), True),
        (Constraint(CT.SYMMETRIC, ("a", "b")), True),  # çizgi eksik
        (Constraint(CT.SYMMETRIC, ("a", "l1", "b")), True),  # sıra yanlış
        (Constraint(CT.MIDPOINT, ("l1", "m")), True),  # referans sırası tabloya uymuyor
    ],
    ids=lambda v: f"{v.type.name}-{'-'.join(v.refs)}" if isinstance(v, Constraint) else "",
)
def test_yanlis_referans_turu(c, sira_mesajda):
    s = dikdortgen()
    s.constraints.append(c)
    hata_beklenir(s, len(s.constraints) - 1 if sira_mesajda else None)


def test_nokta_nokta_mesafe_sifir_hata():
    """DISTANCE nokta–nokta D = 0 → SketchError (COINCIDENT kullanılmalı)."""
    hata_beklenir(iki_nokta(Constraint(CT.DISTANCE, ("p", "q"), 0.0)), 0)


@pytest.mark.parametrize(
    "c",
    [
        Constraint(CT.DISTANCE, ("p", "q"), -5.0),
        Constraint(CT.LENGTH, ("l1",), 0.0),
        Constraint(CT.LENGTH, ("l1",), -1.0),
        Constraint(CT.RADIUS, ("o",), 0.0),
        Constraint(CT.RADIUS, ("o",), -2.0),
        Constraint(CT.DIAMETER, ("o",), 0.0),
        Constraint(CT.DIAMETER, ("y",), -10.0),
    ],
    ids=lambda c: f"{c.type.name}-{c.value}",
)
def test_pozitif_olmasi_gereken_degerler(c):
    s = dikdortgen()
    s.points["p"] = Point(0.0, 0.0)
    s.points["q"] = Point(3.0, 4.0)
    s.constraints.append(c)
    hata_beklenir(s, len(s.constraints) - 1)


@pytest.mark.parametrize("v", [math.inf, -math.inf, math.nan])
@pytest.mark.parametrize(
    "tur, refs",
    [
        (CT.LENGTH, ("l1",)),
        (CT.DISTANCE, ("a", "c")),
        (CT.DISTANCE, ("m", "l1")),
        (CT.HDISTANCE, ("a", "b")),
        (CT.VDISTANCE, ("a", "b")),
        (CT.RADIUS, ("o",)),
        (CT.DIAMETER, ("o",)),
        (CT.ANGLE, ("l1", "l2")),
    ],
)
def test_sonsuz_deger_hata(tur, refs, v):
    s = dikdortgen()
    s.constraints.append(Constraint(tur, refs, v))
    hata_beklenir(s, len(s.constraints) - 1)


@pytest.mark.parametrize("tur, refs", [(CT.LENGTH, ("l1",)), (CT.RADIUS, ("o",)), (CT.DISTANCE, ("a", "c"))])
def test_deger_gereken_kisitta_deger_yok(tur, refs):
    s = dikdortgen()
    s.constraints.append(Constraint(tur, refs))
    hata_beklenir(s, len(s.constraints) - 1)


@pytest.mark.parametrize("side", [2, -2, 5])
def test_side_aralik_disi_hata(side):
    s = dikdortgen()
    s.constraints.append(Constraint(CT.TANGENT, ("l2", "o"), side=side))
    hata_beklenir(s, len(s.constraints) - 1)


@pytest.mark.parametrize("side", [-1, 0, 1])
def test_side_gecerli(side):
    s = dikdortgen()
    s.constraints.append(Constraint(CT.TANGENT, ("l2", "o"), side=side))
    s.validate()


def test_hata_mesajinda_dogru_sira():
    """Birden çok kısıt varken mesaj hatalı olanın sırasını taşır (başka sırayı değil)."""
    s = dikdortgen()
    n = len(s.constraints)
    s.constraints.append(Constraint(CT.RADIUS, ("o",), -1.0))
    err = hata_beklenir(s)
    assert str(n) in str(err)


# --- to_dict / from_dict ------------------------------------------------------------------------------


def esit_eskiz(a: Sketch, b: Sketch) -> None:
    for alan in ("origin", "normal", "xdir"):
        assert np.array_equal(getattr(a.plane, alan), getattr(b.plane, alan))
    assert a.points == b.points
    assert a.entities == b.entities
    assert list(a.points) == list(b.points)
    assert list(a.entities) == list(b.entities)
    assert len(a.constraints) == len(b.constraints)
    for ca, cb in zip(a.constraints, b.constraints, strict=True):
        assert ca.type == cb.type
        assert isinstance(cb.type, ConstraintType)
        assert tuple(ca.refs) == tuple(cb.refs)
        assert ca.value == cb.value
        assert ca.side == cb.side
        assert ca.internal == cb.internal
    for k, e in a.entities.items():
        assert type(e) is type(b.entities[k])


def test_to_dict_sema_1():
    d = dikdortgen().to_dict()
    assert isinstance(d, dict)
    assert d["sema"] == 1


def test_json_gidis_donus_kayipsiz():
    s = dikdortgen()
    metin = json.dumps(s.to_dict())
    t = Sketch.from_dict(json.loads(metin))
    esit_eskiz(s, t)
    # İkinci tur da aynı sözlüğü üretir.
    assert json.loads(json.dumps(t.to_dict())) == json.loads(metin)


def test_json_gidis_donus_egik_duzlem_ve_tum_satirlar():
    """Rastgele düzlem, kesirli koordinatlar, side ve internal değerleri dahil kayıpsız."""
    rng = np.random.default_rng(1717)
    s = dikdortgen()
    s.plane = rastgele_duzlem(rng)
    for p in s.points.values():
        p.x += float(rng.uniform(-1, 1)) / 3.0
        p.y += float(rng.uniform(-1, 1)) / 7.0
    s.constraints = gecerli_tum_satirlar()
    s.validate()
    t = Sketch.from_dict(json.loads(json.dumps(s.to_dict())))
    esit_eskiz(s, t)


def test_json_gidis_donus_internal_ve_side_korunur():
    s = dikdortgen()
    s.constraints = [Constraint(CT.TANGENT, ("o", "y"), side=-1, internal=True)]
    t = Sketch.from_dict(json.loads(json.dumps(s.to_dict())))
    c = t.constraints[0]
    assert (c.side, c.internal) == (-1, True)


def test_json_gidis_donus_bos_eskiz():
    s = Sketch(plane=Plane.YZ(), points={}, entities={}, constraints=[])
    t = Sketch.from_dict(json.loads(json.dumps(s.to_dict())))
    esit_eskiz(s, t)


def test_to_dict_girdiyi_degistirmez():
    s = dikdortgen()
    once = json.dumps(s.to_dict(), sort_keys=True)
    s.to_dict()
    assert json.dumps(s.to_dict(), sort_keys=True) == once


# --- Çıktı tipleri ------------------------------------------------------------------------------------


def test_segline_frozen_ve_alanlar():
    s = SegLine(np.array([0.0, 0.0]), np.array([40.0, 0.0]))
    assert np.allclose(s.p0, (0.0, 0.0)) and np.allclose(s.p1, (40.0, 0.0))
    with pytest.raises(dataclasses.FrozenInstanceError):
        s.p0 = np.array([1.0, 1.0])


def test_segarc_frozen_ve_alanlar():
    a = SegArc(np.array([0.0, 0.0]), 5.0, np.array([5.0, 0.0]), np.array([0.0, 5.0]), True)
    assert a.r == 5.0 and a.ccw is True
    assert np.allclose(a.center, (0.0, 0.0))
    assert np.allclose(a.start, (5.0, 0.0)) and np.allclose(a.end, (0.0, 5.0))
    with pytest.raises(dataclasses.FrozenInstanceError):
        a.r = 6.0


def test_sketch_region_frozen_ve_alanlar():
    kare = (
        SegLine(np.array([0.0, 0.0]), np.array([10.0, 0.0])),
        SegLine(np.array([10.0, 0.0]), np.array([10.0, 10.0])),
        SegLine(np.array([10.0, 10.0]), np.array([0.0, 10.0])),
        SegLine(np.array([0.0, 10.0]), np.array([0.0, 0.0])),
    )
    delik = (SegArc(np.array([5.0, 5.0]), 2.0, np.array([7.0, 5.0]), np.array([7.0, 5.0]), False),)
    r = SketchRegion(outer=kare, holes=(delik,))
    assert len(r.outer) == 4
    assert len(r.holes) == 1 and len(r.holes[0]) == 1
    with pytest.raises(dataclasses.FrozenInstanceError):
        r.outer = ()
