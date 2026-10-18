"""Testlerde ortak kullanılan model üreticileri."""

from __future__ import annotations

import pytest

from core.model import BC, Element, Load, Material, Model, Node, Section

STEEL_E = 210_000.0   # MPa
AL_E = 70_000.0       # MPa


def make_bar(
    n_elem: int = 1,
    L: float = 1000.0,
    E: float = STEEL_E,
    A: float = 100.0,
    tip_load: float | None = 10_000.0,
    fix_left: bool = True,
) -> Model:
    """Sol ucu ankastre, sağ ucundan çekilen düzgün çubuk. Düğümler 1..n+1, elemanlar 1..n."""
    nodes = [Node(id=i + 1, x=L * i / n_elem) for i in range(n_elem + 1)]
    elements = [
        Element(id=i + 1, type="bar1d", nodes=[i + 1, i + 2], material="celik", section="s1")
        for i in range(n_elem)
    ]
    bcs = [BC(node=1, dof="ux", value=0.0)] if fix_left else []
    loads = [Load(node=n_elem + 1, dof="ux", value=tip_load)] if tip_load is not None else []
    return Model(
        dim=1,
        name=f"cubuk_{n_elem}",
        nodes=nodes,
        elements=elements,
        materials=[Material(name="celik", E=E)],
        sections=[Section(name="s1", A=A)],
        bcs=bcs,
        loads=loads,
    )


@pytest.fixture
def bar_model() -> Model:
    return make_bar()
