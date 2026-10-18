"""Component ve Node değer eşitliği (T numpy dizisi; dataclass'ın == 'si ValueError veriyordu)."""

import numpy as np

from assy.model import Assembly, Component, Node, rot_z, transform


def test_component_equality():
    T = transform(rot_z(30), [1, 2, 3])
    a, b = Component("c", "p", T), Component("c", "p", T.copy())
    assert a == b
    assert a != Component("c", "p", np.eye(4))
    assert a != Component("c", "p", T, fixed=True)
    assert a != Component("d", "p", T)
    assert a != "c"


def test_assembly_equality_uses_component_equality():
    def kur():
        return Assembly("m", [Component("a", "p"), Component("b", "q", transform(t=[0, 0, 5]))])

    assert kur() == kur()
    assert kur() != Assembly("m", [Component("a", "p")])


def kur_agac(z=5.0):
    return Node(
        "kok",
        children=[
            Node("vida_1", T=transform(t=[0, 0, z]), part="vida"),
            Node("alt", ref="A", children=[Node("pul", part="pul")]),
        ],
    )


def test_node_equality_recursive():
    assert kur_agac() == kur_agac()
    assert kur_agac() != kur_agac(z=6.0)  # derindeki T farkı
    assert Node("a", part="p") != Node("a", part="q")
    assert Node("x", ref="A", children=[Node("a", part="p")]) != Node("x", children=[Node("a", part="p")])
    assert Node("a", part="p") != "a"


def test_node_roundtrip_equal():
    r = kur_agac()
    assert Node.from_dict(r.to_dict()) == r
