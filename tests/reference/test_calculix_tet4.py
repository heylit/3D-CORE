"""
SPEC 13 — CalculiX C3D4 / T3D2 çapraz kontrolü (K6, K7).

Aynı model kendi çözücümüzle ve CalculiX ile çözülür. ccx `.dat` dosyasına 7 anlamlı basamak yazdığı için
tolerans büyüklüğe göre mutlaktır: yer değiştirme `≤ 1e-5 · max|u|`, eleman gerilmesi `≤ 1e-5 · max|σ|`,
mesnet tepkisi `≤ 1e-5 · max|R|`. Tepki tanım farkı: ccx `RF = K u`, bizde `R = K u − F` (README.md).

- K6: testlerin kendi C3D4 yazıcısı (`tests/reference/calculix.py`) ile L braket (gmsh, SPEC 12) ve
  gmsh'siz yapılandırılmış ağ.
- K7: ürün yazıcısı `fileio.calculix.to_inp` çıktısı ccx'te çözülür: L braket (C3D4), SPEC 01 örnek
  çubukları (T3D2), yapılandırılmış ağ ve `examples/11_tet4_cekme.json` (C3D4).

ccx yoksa atlanır; L braket ayrıca gmsh, build123d ve `mesh.tet_mesh` (SPEC 12) ister. Geometri uydurmadır.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from core import post
from core.model import BC, Material, Model
from core.solver import solve
from tests.benchmarks.tet_ag import kutu_agi, yuz_dugumleri, yuzey_cekmesi
from tests.reference.calculix import CCX, CcxResult, solve_ccx
from tests.reference.test_calculix import random_bar

TOL = 1e-5
EXAMPLES = Path(__file__).resolve().parents[2] / "examples"
DOFS = ("ux", "uy", "uz")

needs_ccx = pytest.mark.skipif(CCX is None, reason="CalculiX (ccx) kurulu değil")


def mesh_api():
    """SPEC 12 `mesh` arayüzü; gmsh veya `mesh.tet_mesh` yoksa test atlanır."""
    pytest.importorskip("gmsh")
    import mesh

    if not hasattr(mesh, "tet_mesh"):
        pytest.skip("SPEC 12 (mesh.tet_mesh) henüz main'de değil")
    return mesh


def l_braket() -> Model:
    """Uydurma L braket: taban 60 × 40 × 8 (z ∈ [0, 8]), dikme 8 × 40 × 50 (x ∈ [0, 8], z ∈ [8, 58]),
    dikmede x ekseni boyunca Ø10 delik (y = 20, z = 33). Taban alt yüzü ankastre, dikme üst yüzüne
    yanal çekme t = (2, 0.5, 0) MPa."""
    mesh = mesh_api()
    from build123d import Align, Box, Cylinder, Pos, Rot

    from geometry.part import Part

    mn = (Align.MIN, Align.MIN, Align.MIN)
    sekil = Box(60, 40, 8, align=mn) + Pos(0, 0, 8) * Box(8, 40, 50, align=mn)
    sekil = sekil - Pos(4, 20, 33) * Rot(0, 90, 0) * Cylinder(5, 20)
    m = mesh.tet_mesh(Part(sekil, name="l_braket"), h=4.0, material=Material("celik", 210_000.0, 0.3))
    mesh.fix(m, mesh.select_nodes(m, mesh.on_plane((0, 0, 0), (0, 0, 1))))
    mesh.add_traction(m, mesh.select_triangles(m, mesh.on_plane((0, 0, 58), (0, 0, 1))), (2.0, 0.5, 0.0))
    return m


def yapilandirilmis(kaydirma: float = 0.2) -> Model:
    """gmsh'siz kutu ağı (iki düğüm sırası da var), iki malzeme, sol yüz ankastre, sağ yüze eğik çekme."""
    L = 24.0
    m = kutu_agi(L, 10.0, 8.0, 6, 3, 2, Material("celik", 210_000.0, 0.3), kaydirma=kaydirma, tohum=21)
    m.materials.append(Material("al", 70_000.0, 0.33))
    for e in m.elements:
        X = np.mean([m.node(n).xyz for n in e.nodes], axis=0)
        if X[0] > L / 2:
            e.material = "al"
    m.bcs = [BC(n, d, 0.0) for n in yuz_dugumleri(m, 0, 0.0) for d in DOFS]
    m.loads = yuzey_cekmesi(m, 0, L, (3.0, -1.0, 2.0))
    return m


def tutulu_dofs(model: Model) -> list[tuple[int, str]]:
    return sorted({(bc.node, bc.dof) for bc in model.bcs})


def assert_same(model: Model, ref: CcxResult) -> None:
    """Bizim çözüm ↔ ccx: yer değiştirme, eleman gerilmesi, mesnet tepkisi."""
    ours = solve(model)
    dofs = DOFS[: model.dofs_per_node]
    u = np.array([[ours.displacement(model, n.id, d) for d in dofs] for n in model.nodes])
    u_ref = np.array([ref.u[n.id][: len(dofs)] for n in model.nodes])
    np.testing.assert_allclose(u, u_ref, rtol=0, atol=TOL * np.max(np.abs(u_ref)))
    if model.dim == 1:  # 1B: ccx'te yanal serbestlikler tutulu olmalı (ccx ~1e-20 artık yazabilir)
        diger = np.array([ref.u[n.id][1:] for n in model.nodes])
        assert np.max(np.abs(diger)) <= TOL * np.max(np.abs(u_ref))

    tutulu = tutulu_dofs(model)
    F = {(ld.node, ld.dof): 0.0 for ld in model.loads}
    for ld in model.loads:
        F[(ld.node, ld.dof)] += ld.value
    R = np.array([ours.reaction(model, n, d) + F.get((n, d), 0.0) for n, d in tutulu])
    R_ref = np.array([ref.rf[n][DOFS.index(d)] for n, d in tutulu])
    np.testing.assert_allclose(R, R_ref, rtol=0, atol=TOL * np.max(np.abs(R_ref)))

    if model.dim == 1:
        s = np.array([ours.element_stresses[e.id] for e in model.elements])
        s_ref = np.array([ref.sxx[e.id] for e in model.elements])
    else:
        tensorler = post.element_stress_tensors(model, ours.u)
        s = np.array([tensorler[e.id] for e in model.elements])
        s_ref = np.array([ref.s[e.id] for e in model.elements])
    np.testing.assert_allclose(s, s_ref, rtol=0, atol=TOL * np.max(np.abs(s_ref)))


def fileio_inp(model: Model) -> str:
    from fileio.calculix import to_inp

    return to_inp(model)


# --- K6: testlerin C3D4 yazıcısı ---------------------------------------------------------


@needs_ccx
@pytest.mark.parametrize("kaydirma", [0.0, 0.2])
def test_helper_structured_c3d4_matches_ccx(kaydirma, tmp_path):
    m = yapilandirilmis(kaydirma)
    assert_same(m, solve_ccx(m, tmp_path))


@needs_ccx
@pytest.mark.occt
def test_bracket_c3d4_matches_ccx(tmp_path):
    """K6: L braket, tet_mesh(h = 4), testlerin kendi C3D4 yazıcısıyla."""
    m = l_braket()
    assert_same(m, solve_ccx(m, tmp_path))


# --- K7: ürün yazıcısı fileio.calculix.to_inp ---------------------------------------------


@needs_ccx
@pytest.mark.occt
def test_fileio_inp_bracket_matches_solver(tmp_path):
    """K7: L braket (C3D4), `fileio.calculix.to_inp` çıktısıyla."""
    m = l_braket()
    assert_same(m, solve_ccx(m, tmp_path, inp=fileio_inp(m)))


@needs_ccx
@pytest.mark.parametrize("kaydirma", [0.0, 0.2])
def test_fileio_inp_structured_c3d4_matches_solver(kaydirma, tmp_path):
    m = yapilandirilmis(kaydirma)
    assert_same(m, solve_ccx(m, tmp_path, inp=fileio_inp(m)))


@needs_ccx
def test_fileio_inp_example_tet4_json_matches_solver(tmp_path):
    m = Model.from_json(EXAMPLES / "11_tet4_cekme.json")
    assert_same(m, solve_ccx(m, tmp_path, inp=fileio_inp(m)))


@needs_ccx
def test_fileio_inp_example_bar_matches_solver(tmp_path):
    """K7: SPEC 01 örnek çubuğu (T3D2)."""
    m = Model.from_json(EXAMPLES / "01_cubuk.json")
    assert_same(m, solve_ccx(m, tmp_path, inp=fileio_inp(m)))


@needs_ccx
@pytest.mark.parametrize("seed", range(6))
def test_fileio_inp_random_bars_match_solver(seed, tmp_path):
    """K7: düzensiz çubuklar (karışık id sırası, ters düğüm sırası, hiperstatik, zorlanmış yer değiştirme)."""
    m = random_bar(seed)
    assert_same(m, solve_ccx(m, tmp_path, inp=fileio_inp(m)))
