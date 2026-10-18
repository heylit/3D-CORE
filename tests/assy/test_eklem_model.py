"""A1b — assy/model.py JointKind, Joint ve Assembly.joints testleri.

Testler yalnız onaylı A1 arayüz metninden yazıldı (arayuz/A1-eklem-tolerans-onerisi.md, bölüm 1); uygulama
kodu okunmadı. Eklem yönlüdür: a ebeveyn, b çocuk, z_b = +z_a (b'nin eksen yönü ters alınmaz).
Varsayılan sıfır yönü: dünya taban vektörlerinden |z·e| en küçük olan (eşitlikte x, y, z sırası),
x = birim(e − (e·z) z).
"""

from __future__ import annotations

import json
import math

import numpy as np
import pytest

from assy.model import (
    Assembly,
    AssyError,
    Component,
    Joint,
    JointKind,
    Mate,
    MateKind,
    Ref,
    RefKind,
    rot_z,
    transform,
)


def eksen(comp: str, origin=(0.0, 0.0, 0.0), direction=(0.0, 0.0, 1.0)) -> Ref:
    return Ref(comp, RefKind.AXIS, origin, direction)


def nokta(comp: str, origin=(0.0, 0.0, 0.0)) -> Ref:
    return Ref(comp, RefKind.POINT, origin)


def duzlem(comp: str, origin=(0.0, 0.0, 0.0), direction=(0.0, 0.0, 1.0)) -> Ref:
    return Ref(comp, RefKind.PLANE, origin, direction)


def mentese(**kw) -> Joint:
    """govde–kapak arası z eksenli döner eklem."""
    args = dict(name="J1", kind=JointKind.REVOLUTE, a=eksen("govde"), b=eksen("kapak"))
    args.update(kw)
    return Joint(**args)


def birim(v) -> np.ndarray:
    v = np.asarray(v, dtype=float)
    return v / np.linalg.norm(v)


# ---------------------------------------------------------------- JointKind ve dof


def test_jointkind_degerleri():
    assert JointKind.FIXED.value == "sabit"
    assert JointKind.REVOLUTE.value == "doner"
    assert JointKind.PRISMATIC.value == "kayar"
    assert JointKind.CYLINDRICAL.value == "silindirik"
    assert JointKind.SPHERICAL.value == "kuresel"
    assert len(JointKind) == 5


@pytest.mark.parametrize(
    ("kind", "dof"),
    [
        (JointKind.FIXED, 0),
        (JointKind.REVOLUTE, 1),
        (JointKind.PRISMATIC, 1),
        (JointKind.CYLINDRICAL, 2),
    ],
)
def test_dof_eksenli(kind, dof):
    j = Joint("J", kind, eksen("a"), eksen("b"))
    assert j.dof == dof


def test_dof_kuresel():
    j = Joint("J", JointKind.SPHERICAL, nokta("a"), nokta("b", (1.0, 2.0, 3.0)))
    assert j.dof == 3


def test_varsayilanlar():
    j = mentese()
    assert j.zero_a is None and j.zero_b is None
    assert j.limits is None


# ---------------------------------------------------------------- referans türü


@pytest.mark.parametrize(
    "kind", [JointKind.FIXED, JointKind.REVOLUTE, JointKind.PRISMATIC, JointKind.CYLINDRICAL]
)
@pytest.mark.parametrize("kotu", [nokta, duzlem])
def test_eksenli_eklem_eksen_ister(kind, kotu):
    with pytest.raises(AssyError):
        Joint("J", kind, kotu("a"), eksen("b"))
    with pytest.raises(AssyError):
        Joint("J", kind, eksen("a"), kotu("b"))


@pytest.mark.parametrize("kotu", [eksen, duzlem])
def test_kuresel_nokta_ister(kotu):
    with pytest.raises(AssyError):
        Joint("J", JointKind.SPHERICAL, kotu("a"), nokta("b"))
    with pytest.raises(AssyError):
        Joint("J", JointKind.SPHERICAL, nokta("a"), kotu("b"))


def test_bos_ad_hata():
    with pytest.raises(AssyError):
        mentese(name="")


# ---------------------------------------------------------------- axis_frame


def test_axis_frame_yerel_ve_yonlu():
    """origin ve z referanstan (yerel), b tarafında da z = +b yönü (ters alınmaz)."""
    j = mentese(
        a=eksen("govde", (10.0, 0.0, 5.0), (0.0, 0.0, 2.0)),
        b=eksen("kapak", (0.0, -3.0, 0.0), (0.0, 0.0, -1.0)),
    )
    oa, za, xa = j.axis_frame("a")
    ob, zb, xb = j.axis_frame("b")
    np.testing.assert_allclose(oa, [10.0, 0.0, 5.0], atol=1e-12)
    np.testing.assert_allclose(za, [0.0, 0.0, 1.0], atol=1e-12)
    np.testing.assert_allclose(ob, [0.0, -3.0, 0.0], atol=1e-12)
    np.testing.assert_allclose(zb, [0.0, 0.0, -1.0], atol=1e-12)
    for v in (oa, za, xa, ob, zb, xb):
        assert isinstance(v, np.ndarray) and v.shape == (3,)


def test_axis_frame_dunya_donusumunden_bagimsiz():
    """Çerçeve bileşenin YEREL koordinatındadır: Component.T onu değiştirmez."""
    j = mentese(a=eksen("govde", (1.0, 2.0, 3.0), (1.0, 0.0, 0.0)))
    asm = Assembly(
        "m",
        [Component("govde", "p", T=transform(rot_z(90), (100.0, 0.0, 0.0))), Component("kapak", "q")],
        joints=[j],
    )
    o, z, _ = asm.joints[0].axis_frame("a")
    np.testing.assert_allclose(o, [1.0, 2.0, 3.0], atol=1e-12)
    np.testing.assert_allclose(z, [1.0, 0.0, 0.0], atol=1e-12)


@pytest.mark.parametrize(
    ("z", "x"),
    [
        ((0.0, 0.0, 1.0), (1.0, 0.0, 0.0)),  # |z·x| = |z·y| = 0 → x
        ((0.0, 0.0, -1.0), (1.0, 0.0, 0.0)),
        ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0)),  # y ve z eşit → y
        ((-1.0, 0.0, 0.0), (0.0, 1.0, 0.0)),
        ((0.0, 1.0, 0.0), (1.0, 0.0, 0.0)),  # x ve z eşit → x
        ((0.0, 1.0, 1.0), (1.0, 0.0, 0.0)),  # x dik → x
        ((1.0, 1.0, 0.0), (0.0, 0.0, 1.0)),  # yalnız z dik → z
    ],
)
def test_varsayilan_sifir_yonu(z, x):
    j = mentese(a=eksen("govde", direction=z), b=eksen("kapak", direction=z))
    for side in ("a", "b"):
        _, zz, xx = j.axis_frame(side)
        np.testing.assert_allclose(zz, birim(z), atol=1e-12)
        np.testing.assert_allclose(xx, x, atol=1e-12)


def test_varsayilan_sifir_yonu_egik_eksen():
    """z = (1, 2, 3)/√14: en küçük |z·e| x'te → x = birim(e_x − (e_x·z) z)."""
    z = birim((1.0, 2.0, 3.0))
    beklenen = birim(np.array([1.0, 0.0, 0.0]) - z[0] * z)
    _, zz, xx = mentese(a=eksen("govde", direction=(1.0, 2.0, 3.0))).axis_frame("a")
    np.testing.assert_allclose(zz, z, atol=1e-12)
    np.testing.assert_allclose(xx, beklenen, atol=1e-12)


def test_varsayilan_sifir_yonu_esitlikte_x_once():
    """z = (1, 1, 1)/√3: üç taban da eşit → x seçilir."""
    z = birim((1.0, 1.0, 1.0))
    beklenen = birim(np.array([1.0, 0.0, 0.0]) - z[0] * z)
    _, _, xx = mentese(a=eksen("govde", direction=(1.0, 1.0, 1.0))).axis_frame("a")
    np.testing.assert_allclose(xx, beklenen, atol=1e-12)


def test_verilen_sifir_yonu_eksene_dik_bilesen_birimlenir():
    """zero_a = (2, 0, 5), z = +z → x = (1, 0, 0); zero_b yalnız b tarafını etkiler."""
    j = mentese(zero_a=(2.0, 0.0, 5.0), zero_b=(0.0, -3.0, 0.0))
    _, _, xa = j.axis_frame("a")
    _, _, xb = j.axis_frame("b")
    np.testing.assert_allclose(xa, [1.0, 0.0, 0.0], atol=1e-12)
    np.testing.assert_allclose(xb, [0.0, -1.0, 0.0], atol=1e-12)


def test_sifir_yonu_egik_eksende_dik():
    z = birim((0.0, 1.0, 1.0))
    j = mentese(a=eksen("govde", direction=(0.0, 1.0, 1.0)), zero_a=(0.0, 1.0, 0.0))
    _, zz, xx = j.axis_frame("a")
    beklenen = birim(np.array([0.0, 1.0, 0.0]) - z[1] * z)  # (0, 1, −1)/√2
    np.testing.assert_allclose(xx, beklenen, atol=1e-12)
    assert abs(float(np.dot(xx, zz))) < 1e-12


@pytest.mark.parametrize("kind", list(JointKind))
def test_cerceve_ortonormal(kind):
    if kind is JointKind.SPHERICAL:
        j = Joint("J", kind, nokta("a", (1.0, 1.0, 1.0)), nokta("b"))
    else:
        j = Joint("J", kind, eksen("a", direction=(3.0, -1.0, 2.0)), eksen("b", direction=(0.0, 1.0, 0.0)))
    for side in ("a", "b"):
        _, z, x = j.axis_frame(side)
        assert np.linalg.norm(z) == pytest.approx(1.0, abs=1e-12)
        assert np.linalg.norm(x) == pytest.approx(1.0, abs=1e-12)
        assert abs(float(np.dot(z, x))) < 1e-12


@pytest.mark.parametrize("side", ["c", "A", "", "ab"])
def test_bilinmeyen_taraf_hata(side):
    with pytest.raises(AssyError):
        mentese().axis_frame(side)


# ---------------------------------------------------------------- sıfır yönü doğrulaması


@pytest.mark.parametrize("alan", ["zero_a", "zero_b"])
@pytest.mark.parametrize(
    "zero",
    [(0.0, 0.0, 1.0), (0.0, 0.0, -4.0), (0.0, 0.0, 0.0), (math.nan, 0.0, 0.0), (math.inf, 0.0, 0.0)],
)
def test_kotu_sifir_yonu_hata(alan, zero):
    """Eksene paralel, sıfır veya sonlu olmayan sıfır yönü (eksen z)."""
    with pytest.raises(AssyError):
        mentese(**{alan: zero})


def test_neredeyse_paralel_ama_gecerli_sifir_yonu():
    """|birim(zero) × z| = 1e-6 > 1e-9: geçerli, dik bileşeni birimlenir."""
    _, _, x = mentese(zero_a=(1e-6, 0.0, 1.0)).axis_frame("a")
    np.testing.assert_allclose(x, [1.0, 0.0, 0.0], atol=1e-9)


# ---------------------------------------------------------------- limits


@pytest.mark.parametrize("limits", [None, (-90.0, 90.0), (-180.0, 180.0), (0.0, 0.0), (10.0, 45.0)])
def test_doner_sinir_gecerli(limits):
    mentese(limits=limits)


@pytest.mark.parametrize(
    "limits", [(90.0, -90.0), (-181.0, 0.0), (0.0, 180.5), (-math.inf, 0.0), (0.0, math.nan)]
)
def test_doner_sinir_hata(limits):
    with pytest.raises(AssyError):
        mentese(limits=limits)


@pytest.mark.parametrize("limits", [None, (0.0, 50.0), (-500.0, 1000.0), (-10.0, -2.0)])
def test_kayar_sinir_gecerli(limits):
    Joint("K", JointKind.PRISMATIC, eksen("a"), eksen("b"), limits=limits)


@pytest.mark.parametrize("limits", [(50.0, 0.0), (0.0, math.inf), (math.nan, 1.0)])
def test_kayar_sinir_hata(limits):
    with pytest.raises(AssyError):
        Joint("K", JointKind.PRISMATIC, eksen("a"), eksen("b"), limits=limits)


@pytest.mark.parametrize(
    "limits",
    [None, ((-90.0, 90.0), (0.0, 20.0)), (None, (0.0, 20.0)), ((-45.0, 45.0), None), (None, None)],
)
def test_silindirik_sinir_gecerli(limits):
    Joint("S", JointKind.CYLINDRICAL, eksen("a"), eksen("b"), limits=limits)


@pytest.mark.parametrize(
    "limits",
    [
        ((-90.0, 90.0),),  # tek eleman
        ((-90.0, 90.0), (0.0, 20.0), None),  # üç eleman
        ((90.0, -90.0), None),  # açı alt > üst
        (None, (20.0, 0.0)),  # öteleme alt > üst
        (None, (0.0, math.inf)),  # sonlu değil
    ],
)
def test_silindirik_sinir_hata(limits):
    with pytest.raises(AssyError):
        Joint("S", JointKind.CYLINDRICAL, eksen("a"), eksen("b"), limits=limits)


def test_sabit_sinir_hata():
    with pytest.raises(AssyError):
        Joint("F", JointKind.FIXED, eksen("a"), eksen("b"), limits=(0.0, 0.0))


def test_kuresel_sinir_hata():
    with pytest.raises(AssyError):
        Joint("K", JointKind.SPHERICAL, nokta("a"), nokta("b"), limits=(-10.0, 10.0))


# ---------------------------------------------------------------- Assembly.joints ve validate


def montaj(joints=None) -> Assembly:
    comps = [Component("govde", "braket", fixed=True), Component("kapak", "kapak1"), Component("pim", "pim6")]
    return Assembly("m", comps, [], joints if joints is not None else [mentese()])


def test_eski_cagri_joints_bos():
    """Mevcut Assembly(name, components, mates) çağrıları değişmez; joints boş liste."""
    asm = Assembly("m", [Component("a", "p")], [])
    assert asm.joints == []
    assert Assembly("n").joints == []
    assert Assembly("x").joints is not Assembly("y").joints


def test_validate_gecerli():
    montaj([mentese(), mentese(name="J2", a=eksen("kapak"), b=eksen("pim"))]).validate()


def test_validate_yinelenen_eklem_adi():
    with pytest.raises(AssyError):
        montaj([mentese(), mentese(a=eksen("kapak"), b=eksen("pim"))]).validate()


def test_validate_bilinmeyen_bilesen():
    with pytest.raises(AssyError):
        montaj([mentese(b=eksen("yok"))]).validate()
    with pytest.raises(AssyError):
        montaj([mentese(a=eksen("yok"))]).validate()


def test_validate_ayni_bilesen():
    with pytest.raises(AssyError):
        montaj([mentese(b=eksen("govde", (5.0, 0.0, 0.0)))]).validate()


# ---------------------------------------------------------------- to_dict / from_dict


def ayni_eklem(j1: Joint, j2: Joint) -> None:
    assert j2.name == j1.name
    assert j2.kind is j1.kind
    assert j2.a == j1.a and j2.b == j1.b
    for side in ("a", "b"):
        for v1, v2 in zip(j1.axis_frame(side), j2.axis_frame(side), strict=True):
            np.testing.assert_allclose(v2, v1, atol=1e-12)
    for alan in ("zero_a", "zero_b"):
        v1, v2 = getattr(j1, alan), getattr(j2, alan)
        assert (v1 is None) == (v2 is None)
        if v1 is not None:
            np.testing.assert_allclose(v2, v1, atol=1e-12)
    l1, l2 = j1.limits, j2.limits
    assert (l1 is None) == (l2 is None)
    if l1 is not None and j1.kind is JointKind.CYLINDRICAL:
        assert len(l2) == 2
        for p1, p2 in zip(l1, l2, strict=True):
            assert (p1 is None) == (p2 is None)
            if p1 is not None:
                np.testing.assert_allclose(p2, p1)
    elif l1 is not None:
        np.testing.assert_allclose(l2, l1)


def zengin_montaj() -> Assembly:
    asm = montaj(
        [
            mentese(zero_a=(1.0, 1.0, 0.0), limits=(-30.0, 120.0)),
            Joint(
                "K1",
                JointKind.PRISMATIC,
                eksen("kapak", direction=(1.0, 0.0, 0.0)),
                eksen("pim"),
                limits=(0.0, 40.0),
            ),
            Joint(
                "S1",
                JointKind.CYLINDRICAL,
                eksen("govde", (0.0, 5.0, 0.0)),
                eksen("pim"),
                zero_b=(0.0, 1.0, 0.0),
                limits=(None, (-5.0, 5.0)),
            ),
            Joint("B1", JointKind.SPHERICAL, nokta("pim", (0.0, 0.0, 8.0)), nokta("kapak")),
            Joint("F1", JointKind.FIXED, eksen("govde"), eksen("kapak")),
        ]
    )
    asm.mates.append(Mate(MateKind.CONCENTRIC, eksen("govde"), eksen("pim")))
    return asm


def test_to_dict_joints_anahtari():
    d = zengin_montaj().to_dict()
    assert "joints" in d
    assert len(d["joints"]) == 5
    assert d["joints"][0]["kind"] == "doner"
    assert {j["kind"] for j in d["joints"]} == {"doner", "kayar", "silindirik", "kuresel", "sabit"}
    json.dumps(d)


def test_to_dict_bos_joints():
    """Eklemsiz montaj: "joints" yazılırsa boş liste; gidiş-dönüşte joints boş."""
    d = Assembly("m", [Component("a", "p")]).to_dict()
    assert d.get("joints", []) == []
    assert Assembly.from_dict(json.loads(json.dumps(d))).joints == []


def test_gidis_donus():
    asm = zengin_montaj()
    asm2 = Assembly.from_dict(json.loads(json.dumps(asm.to_dict())))
    assert len(asm2.joints) == len(asm.joints)
    for j1, j2 in zip(asm.joints, asm2.joints, strict=True):
        ayni_eklem(j1, j2)
    assert len(asm2.mates) == 1
    asm2.validate()


def test_eski_json_joints_yok():
    """ "joints" anahtarı olmayan eski JSON → boş liste."""
    d = montaj([]).to_dict()
    d.pop("joints", None)
    asm = Assembly.from_dict(d)
    assert asm.joints == []
    assert [c.name for c in asm.components] == ["govde", "kapak", "pim"]
