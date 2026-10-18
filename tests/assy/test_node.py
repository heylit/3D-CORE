"""SPEC 07 ön koşulu — assy/model.py `Node` arayüz testleri.

Testler sadece specs/07-montaj-agaci.md'deki `Node` tanımından yazıldı; uygulama kodu okunmadı.
Node bir montaj ağacı oluşumudur: yaprak (part dolu, children boş) ya da alt montaj (part None,
children dolu). `__post_init__` sadece düğümün kendi tutarlılığına bakar; ağaç bütünlüğü (kardeş adları,
boş alt montaj) assy.tree.validate'tedir, çünkü ağaç adım adım kurulabilmeli.

`Node` main'e arayüz PR'ıyla gelene kadar testler "uygulanmamış" (NotImplementedError) sayılır.
"""

from __future__ import annotations

import json

import numpy as np
import pytest

from assy.model import AssyError, is_rigid, rot_x, rot_z, transform


def _uygulanmamis(*_a, **_k):
    raise NotImplementedError("assy.model.Node henüz yok (SPEC 07 arayüz PR'ı)")


try:
    from assy.model import Node
except ImportError:  # arayüz PR'ı gelene kadar testler "uygulanmamış" sayılır
    Node = _uygulanmamis


def alt_montaj() -> Node:
    """Dönmeli iki seviyeli örnek: alt montaj (ref='alt') içinde plaka ve vida."""
    return Node(
        "alt_a",
        T=transform(rot_z(90), (0.0, 100.0, 0.0)),
        ref="alt",
        children=[
            Node("plaka", part="plaka"),
            Node("vida_1", T=transform(rot_x(30), (5.0, -2.5, 7.0)), part="vida"),
        ],
    )


def assert_same_node(a: Node, b: Node) -> None:
    assert b.name == a.name
    assert b.part == a.part
    assert b.ref == a.ref
    assert b.definition == a.definition
    np.testing.assert_allclose(b.T, a.T, rtol=0, atol=1e-12)
    assert len(b.children) == len(a.children)
    for ca, cb in zip(a.children, b.children, strict=True):
        assert_same_node(ca, cb)


# ---------------------------------------------------------------- varsayılanlar ve tanım


def test_varsayilanlar():
    n = Node("kok")
    np.testing.assert_array_equal(n.T, np.eye(4))
    assert n.part is None
    assert n.children == []
    assert n.ref is None


def test_varsayilan_T_ve_children_paylasilmaz():
    a, b = Node("a"), Node("b")
    assert a.T is not b.T
    assert a.children is not b.children


def test_yaprak_tanimi_parca_kimligi():
    n = Node("vida_1", part="M6x20")
    assert n.definition == "M6x20"
    assert n.children == []


def test_alt_montaj_tanimi_ref_yoksa_ad():
    n = Node("grup", children=[Node("pim", part="pim")])
    assert n.part is None
    assert n.definition == "grup"


def test_alt_montaj_tanimi_ref():
    n = alt_montaj()
    assert n.definition == "alt"
    assert [c.name for c in n.children] == ["plaka", "vida_1"]


def test_rijit_T_kabul():
    T = transform(rot_z(37.0) @ rot_x(-12.5), (1.5, -200.0, 3e2))
    n = Node("vida", T=T, part="vida")
    assert is_rigid(n.T)
    np.testing.assert_allclose(n.T, T, rtol=0, atol=0)


def test_cocuksuz_alt_montaj_ve_yinelenen_kardes_kurulabilir():
    """Ağaç adım adım kurulabilmeli: bu durumlar __post_init__ değil validate hatasıdır."""
    bos = Node("bos")
    assert bos.children == [] and bos.part is None
    ikiz = Node("kok", children=[Node("a", part="p"), Node("a", part="p")])
    assert len(ikiz.children) == 2


# ---------------------------------------------------------------- __post_init__ hataları


@pytest.mark.parametrize(
    "T",
    [
        np.diag([2.0, 1.0, 1.0, 1.0]),  # ölçek
        np.diag([-1.0, 1.0, 1.0, 1.0]),  # ayna (det R = -1)
        transform(np.array([[1.0, 0.1, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]])),  # kayma
        np.array([[1.0, 0, 0, 0], [0, 1.0, 0, 0], [0, 0, 1.0, 0], [0, 0, 1.0, 1.0]]),  # son satır bozuk
        np.eye(3),  # 4x4 değil
    ],
    ids=["olcek", "ayna", "kayma", "son_satir", "3x3"],
)
def test_rijit_olmayan_T_hata(T):
    with pytest.raises(AssyError):
        Node("vida", T=T, part="vida")


@pytest.mark.parametrize("name", ["", "alt/vida", "/", "a/"])
def test_bos_veya_bolu_iceren_ad_hata(name):
    with pytest.raises(AssyError):
        Node(name, part="vida")


def test_alt_montaj_adinda_bolu_hata():
    with pytest.raises(AssyError):
        Node("alt/a", children=[Node("vida", part="vida")])


def test_yaprakta_cocuk_hata():
    with pytest.raises(AssyError):
        Node("vida", part="vida", children=[Node("pul", part="pul")])


def test_yaprakta_ref_hata():
    with pytest.raises(AssyError):
        Node("vida", part="vida", ref="baglanti")


# ---------------------------------------------------------------- to_dict / from_dict


def test_to_dict_json_uyumlu_ve_T_liste():
    n = alt_montaj()
    d = n.to_dict()
    assert d["name"] == "alt_a"
    assert isinstance(d["T"], list)
    np.testing.assert_allclose(np.array(d["T"]), n.T, rtol=0, atol=0)
    assert [c["name"] for c in d["children"]] == ["plaka", "vida_1"]
    assert isinstance(d["children"][1]["T"], list)
    json.dumps(d)  # numpy dizisi kalmamalı


def test_gidis_donus_yaprak():
    n = Node("vida_1", T=transform(rot_z(15.0), (1.0, 2.0, 3.0)), part="vida")
    assert_same_node(n, Node.from_dict(n.to_dict()))


def test_gidis_donus_ozyinelemeli():
    kok = Node(
        "montaj",
        T=transform(rot_x(90), (10.0, 0.0, 0.0)),
        children=[Node("govde", part="govde"), alt_montaj()],
    )
    geri = Node.from_dict(json.loads(json.dumps(kok.to_dict())))
    assert isinstance(geri, Node)
    assert_same_node(kok, geri)
    assert isinstance(geri.T, np.ndarray)
    assert isinstance(geri.children[1].children[1].T, np.ndarray)


def test_to_dict_dugumu_degistirmez():
    n = alt_montaj()
    T0 = n.T.copy()
    n.to_dict()
    np.testing.assert_array_equal(n.T, T0)
    assert isinstance(n.T, np.ndarray)


def test_from_dict_rijit_olmayan_T_hata():
    d = Node("vida", part="vida").to_dict()
    d["T"] = np.diag([1.0, 1.0, 2.0, 1.0]).tolist()
    with pytest.raises(AssyError):
        Node.from_dict(d)
