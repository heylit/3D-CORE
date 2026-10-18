"""
FEM çapraz kontrolü: aynı modeli kendi çözücümüz ve CalculiX ile çöz, sonuçları karşılaştır.

ccx kurulu değilse atlanır (Ubuntu/Debian: `apt install calculix-ccx`; Windows: bConverged
CalculiX paketi, `ccx` PATH'te olmalı). Tolerans: ccx .dat dosyasına 7 anlamlı basamak yazar,
bu yüzden göreli 1e-5 (sıfıra yakın değerlerde büyüklüğün 1e-5'i mutlak pay).
Rastgele modeller sabit tohumludur; geometri uydurmadır.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from core.model import BC, Element, Load, Material, Model, Node, Section
from core.solver import solve
from tests.reference.calculix import CCX, parse_dat, solve_ccx, to_inp

REL = 1e-5
EXAMPLES = Path(__file__).resolve().parents[2] / "examples"

needs_ccx = pytest.mark.skipif(CCX is None, reason="CalculiX (ccx) kurulu değil")


def random_bar(seed: int) -> Model:
    """Sabit tohumlu düzensiz çubuk: farklı boylar, 3 malzeme, 4 kesit, karışık id sırası,
    bazı elemanlarda düğüm sırası ters, rastgele yükler; mesnet: sol ankastre, bazen sağ uç da
    tutulu (hiperstatik) veya ona sıfırdan farklı yer değiştirme verilmiş."""
    rng = np.random.default_rng(seed)
    n = int(rng.integers(3, 40))
    x = np.concatenate([[0.0], np.cumsum(rng.uniform(5, 300, n))])
    ids = rng.permutation(np.arange(1, n + 2) * 10)  # düğüm id'leri sıralı değil
    mats = [Material("celik", 210_000.0), Material("al", 70_000.0, nu=0.33), Material("pirinc", 100_000.0)]
    secs = [Section(f"k{i}", float(a)) for i, a in enumerate(rng.uniform(10, 500, 4))]
    elements = []
    for i in range(n):
        a, b = int(ids[i]), int(ids[i + 1])
        if rng.random() < 0.3:
            a, b = b, a
        elements.append(
            Element(int(1000 - i), "bar1d", [a, b], mats[rng.integers(3)].name, secs[rng.integers(4)].name)
        )
    nodes = [Node(int(ids[i]), float(x[i])) for i in rng.permutation(n + 1)]
    loads = [
        Load(int(ids[k]), "ux", float(rng.uniform(-2e4, 2e4)))
        for k in rng.choice(np.arange(1, n + 1), size=int(rng.integers(1, 4)), replace=False)
    ]
    bcs = [BC(int(ids[0]), "ux", 0.0)]
    case = seed % 3
    if case == 1:
        bcs.append(BC(int(ids[-1]), "ux", 0.0))
    elif case == 2:
        bcs.append(BC(int(ids[-1]), "ux", float(rng.uniform(-0.5, 0.5))))
    return Model(
        dim=1,
        nodes=nodes,
        elements=elements,
        materials=mats,
        sections=secs,
        bcs=bcs,
        loads=loads,
        name=f"rastgele_{seed}",
    )


def assert_same(model: Model, tmp_path: Path) -> None:
    ours = solve(model)
    ref = solve_ccx(model, tmp_path)
    u = np.array([ours.displacement(model, n.id) for n in model.nodes])
    u_ref = np.array([ref.u[n.id][0] for n in model.nodes])
    np.testing.assert_allclose(u, u_ref, rtol=REL, atol=REL * np.max(np.abs(u_ref)))
    # Tanım farkı: bizde R = K u − F (SPEC 01), ccx'te RF = K u. Mesnetli düğüme doğrudan yük
    # verildiğinde ikisi o yük kadar ayrışır; karşılaştırma ccx tanımına çevrilerek yapılır.
    tutulu = sorted({bc.node for bc in model.bcs})
    F = {nid: sum(ld.value for ld in model.loads if ld.node == nid) for nid in tutulu}
    R = np.array([ours.reaction(model, nid) + F[nid] for nid in tutulu])
    R_ref = np.array([ref.rf[nid][0] for nid in tutulu])
    np.testing.assert_allclose(R, R_ref, rtol=REL, atol=REL * max(np.max(np.abs(R_ref)), 1.0))
    s = np.array([ours.element_stresses[e.id] for e in model.elements])
    s_ref = np.array([ref.sxx[e.id] for e in model.elements])
    np.testing.assert_allclose(s, s_ref, rtol=REL, atol=REL * max(np.max(np.abs(s_ref)), 1.0))


def test_inp_writer_without_ccx():
    """ccx olmadan da: .inp metni beklenen kartları içerir, .dat okuyucu örnek bloğu okur."""
    m = Model.from_json(EXAMPLES / "01_cubuk.json")
    inp = to_inp(m)
    for card in (
        "*NODE, NSET=NALL",
        "*ELEMENT, TYPE=T3D2",
        "*SOLID SECTION",
        "*STATIC",
        "NALL, 2, 3",
        "*CLOAD",
        "*NODE PRINT, NSET=NALL",
        "*END STEP",
    ):
        assert card in inp
    dat = (
        " displacements (vx,vy,vz) for set NALL and time  0.1000000E+01\n\n"
        "         1  0.000000E+00  0.000000E+00  0.000000E+00\n"
        "         2  1.190476E-01  0.000000E+00  0.000000E+00\n\n"
        " forces (fx,fy,fz) for set NALL and time  0.1000000E+01\n\n"
        "         1 -1.000000E+04  0.000000E+00  0.000000E+00\n\n"
        " stresses (elem, integ.pnt.,sxx,syy,szz,sxy,sxz,syz) for set EALL and time  0.1000000E+01\n\n"
        "         7   1  1.000000E+02  0.000000E+00  0.000000E+00  0.000000E+00  0.000000E+00  0.000000E+00\n"
    )
    r = parse_dat(dat)
    assert r.u[2][0] == pytest.approx(0.1190476) and r.rf[1][0] == -1e4 and r.sxx[7] == 100.0


@needs_ccx
def test_example_bar_matches_calculix(tmp_path):
    assert_same(Model.from_json(EXAMPLES / "01_cubuk.json"), tmp_path)


@needs_ccx
@pytest.mark.parametrize("seed", range(9))
def test_random_bars_match_calculix(seed, tmp_path):
    assert_same(random_bar(seed), tmp_path)
