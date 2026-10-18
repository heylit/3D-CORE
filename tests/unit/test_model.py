"""Veri modeli testleri. Bunlar iskelet teslim edildiği anda GEÇER."""

from __future__ import annotations

import pytest

from core.model import BC, Element, Load, Material, Model, ModelError, Node, Section
from tests.conftest import make_bar


def test_dof_index_1d():
    m = make_bar(n_elem=3)
    assert m.n_dof == 4
    assert m.dof_index(1, "ux") == 0
    assert m.dof_index(4, "ux") == 3


def test_dof_index_follows_list_order_not_id():
    m = Model(dim=1, nodes=[Node(id=10, x=0), Node(id=3, x=5)])
    assert m.dof_index(10, "ux") == 0
    assert m.dof_index(3, "ux") == 1


def test_dof_index_2d():
    m = Model(dim=2, nodes=[Node(id=1, x=0), Node(id=2, x=1)])
    assert m.n_dof == 4
    assert m.dof_index(2, "uy") == 3


def test_uy_not_allowed_in_1d():
    m = make_bar()
    with pytest.raises(ModelError):
        m.dof_index(1, "uy")


def test_json_roundtrip(tmp_path):
    m = make_bar(n_elem=4)
    p = tmp_path / "m.json"
    m.to_json(p)
    m2 = Model.from_json(p)
    assert m2.to_dict() == m.to_dict()


def test_validate_unknown_node():
    m = make_bar()
    m.elements.append(Element(id=99, type="bar1d", nodes=[1, 42], material="celik", section="s1"))
    with pytest.raises(ModelError):
        m.validate()


def test_validate_unknown_material():
    m = make_bar()
    m.elements[0].material = "yok"
    with pytest.raises(ModelError):
        m.validate()


def test_validate_duplicate_node_id():
    m = make_bar()
    m.nodes.append(Node(id=1, x=5.0))
    with pytest.raises(ModelError):
        m.validate()


def test_validate_load_on_unknown_node():
    m = make_bar()
    m.loads.append(Load(node=77, dof="ux", value=1.0))
    with pytest.raises(ModelError):
        m.validate()


def test_negative_E_rejected():
    with pytest.raises(ModelError):
        Material(name="x", E=-1.0)


def test_zero_area_rejected():
    with pytest.raises(ModelError):
        Section(name="x", A=0.0)


def test_example_json_loads():
    m = Model.from_json("examples/01_cubuk.json")
    assert m.dim == 1
    assert len(m.elements) > 0


# ---------- id → indeks sözlükleri (inceleme Y4) ----------


def test_lookup_follows_list_mutations():
    """Sözlük listeye sonradan eklenen / değiştirilen / yeniden atanan kayıtları görür."""
    m = Model(dim=1, nodes=[Node(id=10, x=0), Node(id=3, x=5)])
    assert m.node_index(3) == 1
    m.nodes.append(Node(id=7, x=9))
    assert m.node_index(7) == 2
    m.nodes[0] = Node(id=42, x=1)
    assert m.node_index(42) == 0
    with pytest.raises(ModelError):
        m.node(10)
    m.nodes = [Node(id=3, x=0)]
    assert m.node_index(3) == 0
    assert m.node(3).x == 0
    m.nodes.insert(0, Node(id=5, x=-1))
    assert m.node_index(3) == 1
    assert m.dof_index(5, "ux") == 0


def test_material_section_lookup_after_mutation():
    m = make_bar()
    assert m.material("celik").E > 0
    m.materials.append(Material(name="al", E=70_000.0))
    m.sections[0] = Section(name="s2", A=50.0)
    assert m.material("al").E == 70_000.0
    assert m.section("s2").A == 50.0
    with pytest.raises(ModelError):
        m.section("s1")


def test_index_cache_not_in_dict_or_equality():
    m = make_bar(n_elem=2)
    m.node_index(2)
    assert "_indeks" not in m.to_dict()
    assert m == make_bar(n_elem=2)


def test_lookup_is_not_linear():
    """n düğümde n sorgu: doğrusal aramada ~n²/2 = 2·10⁸ karşılaştırma (onlarca saniye)."""
    import time

    n = 20_000
    m = Model(dim=1, nodes=[Node(id=i, x=float(i)) for i in range(n)])
    t0 = time.perf_counter()
    for i in range(n):
        assert m.node_index(i) == i
    assert time.perf_counter() - t0 < 1.0


# ---------- sonlu sayı kontrolleri (inceleme O3) ----------

NAN, INF = float("nan"), float("inf")


@pytest.mark.parametrize(
    "make",
    [
        lambda: Material(name="m", E=NAN),
        lambda: Material(name="m", E=INF),
        lambda: Material(name="m", E=200e3, nu=NAN),
        lambda: Material(name="m", E=200e3, rho=NAN),
        lambda: Section(name="s", A=NAN),
        lambda: Section(name="s", A=INF),
        lambda: Node(id=1, x=NAN),
        lambda: Node(id=1, x=0.0, y=INF),
        lambda: Node(id=1, x=0.0, z=-INF),
        lambda: BC(node=1, dof="ux", value=NAN),
        lambda: Load(node=1, dof="ux", value=NAN),
        lambda: Load(node=1, dof="ux", value=INF),
    ],
)
def test_non_finite_rejected(make):
    with pytest.raises(ModelError):
        make()


def test_from_dict_extra_field_is_model_error():
    d = make_bar().to_dict()
    d["nodes"][0]["agirlik"] = 1.0
    with pytest.raises(ModelError):
        Model.from_dict(d)


def test_from_dict_missing_field_is_model_error():
    d = make_bar().to_dict()
    del d["materials"][0]["E"]
    with pytest.raises(ModelError):
        Model.from_dict(d)


def test_from_dict_wrong_type_is_model_error():
    d = make_bar().to_dict()
    d["materials"][0]["E"] = "200000"
    with pytest.raises(ModelError):
        Model.from_dict(d)
