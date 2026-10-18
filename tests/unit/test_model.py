"""Veri modeli testleri. Bunlar iskelet teslim edildiği anda GEÇER."""

from __future__ import annotations

import pytest

from core.model import Element, Load, Material, Model, ModelError, Node, Section
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
