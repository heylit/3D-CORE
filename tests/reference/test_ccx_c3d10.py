"""
SPEC 67a K9 — CalculiX C3D10 çapraz kontrolü.

Aynı tet10 modeli kendi çözücümüzle ve CalculiX ile çözülür. C3D10 düğüm sırası bizimkiyle aynıdır
(köşe 1–4, kenar 5 (1–2), 6 (2–3), 7 (3–1), 8 (1–4), 9 (2–4), 10 (3–4)); ikisi de 4 noktalı Gauss
kuralı kullandığı için aynı ağda aynı K beklenir.

Tolerans büyüklüğe göredir (ccx `.dat` dosyasına 7 anlamlı basamak yazar): yer değiştirme
`≤ 1e-6 · max|u|`, tepki `≤ 1e-6 · max|R|`. Eleman gerilmesi (4 Gauss noktasının ortalaması)
`≤ 1e-5 · max|σ|`. Tepki tanım farkı: ccx `RF = K u`, bizde `R = K u − F` (README.md).

- Testin kendi C3D10 yazıcısı ve ürün yazıcısı `fileio.calculix.to_inp` ayrı ayrı denenir.
- Ağlar: gmsh'siz Kuhn kutusu (tests/benchmarks/tet10_ag.py) ve K6 delikli plakasının kaba ağı
  (`mesh.tet_mesh(order=2)`, gmsh + build123d).

ccx yoksa atlanır.
"""

from __future__ import annotations

import re

import numpy as np
import pytest

from core import post
from core.model import BC, Material, Model
from core.solver import solve
from tests.benchmarks.tet10_ag import kutu_agi10, yuzey_cekmesi10
from tests.benchmarks.tet_ag import yuz_dugumleri
from tests.reference.calculix import CCX, num, solve_ccx

DOFS = ("ux", "uy", "uz")
TOL_U = 1e-6
TOL_S = 1e-5

needs_ccx = pytest.mark.skipif(CCX is None, reason="CalculiX (ccx) kurulu değil")


def c3d10_inp(model: Model) -> str:
    """Testin kendi C3D10 yazıcısı (tek malzeme kümesi başına bir ELSET); U, RF ve S yazdırılır."""
    out = ["*HEADING", f"3D-CORE C3D10 capraz kontrol: {model.name}", "*NODE, NSET=NALL"]
    out += [f"{n.id}, {num(n.x)}, {num(n.y)}, {num(n.z)}" for n in model.nodes]
    gruplar: dict[str, list] = {}
    for e in model.elements:
        gruplar.setdefault(e.material, []).append(e)
    adlar = {m.name: f"M{i}" for i, m in enumerate(model.materials, start=1)}
    for k, elemanlar in enumerate(gruplar.values(), start=1):
        out.append(f"*ELEMENT, TYPE=C3D10, ELSET=G{k}")
        for e in elemanlar:
            n = [str(i) for i in e.nodes]
            out += [f"{e.id}, " + ", ".join(n[:8]) + ",", ", ".join(n[8:])]  # satır başına en çok 16 giriş
    out.append("*ELSET, ELSET=EALL")
    out += [f"G{k}" for k in range(1, len(gruplar) + 1)]
    for m in model.materials:
        out += [f"*MATERIAL, NAME={adlar[m.name]}", "*ELASTIC", f"{num(m.E)}, {num(m.nu)}"]
    for k, mat in enumerate(gruplar, start=1):
        out.append(f"*SOLID SECTION, ELSET=G{k}, MATERIAL={adlar[mat]}")
    out += ["*STEP", "*STATIC"]
    if model.bcs:
        out.append("*BOUNDARY")
        for bc in model.bcs:
            k = DOFS.index(bc.dof) + 1
            out.append(f"{bc.node}, {k}, {k}, {num(bc.value)}")
    if model.loads:
        out.append("*CLOAD")
        out += [f"{ld.node}, {DOFS.index(ld.dof) + 1}, {num(ld.value)}" for ld in model.loads]
    out += ["*NODE PRINT, NSET=NALL", "U, RF", "*EL PRINT, ELSET=EALL", "S", "*END STEP"]
    return "\n".join(out) + "\n"


_NUM = r"[-+]?\d+\.\d+E[-+]\d+"


def gauss_ortalama_gerilme(dat: str) -> dict[int, np.ndarray]:
    """`.dat` 'stresses' bloğu: eleman id → integrasyon noktalarındaki σ'ların ortalaması (6,)."""
    toplam: dict[int, list[np.ndarray]] = {}
    blokta = False
    for satir in dat.splitlines():
        kucuk = satir.strip().lower()
        if kucuk.startswith(("displacements", "forces")):
            blokta = False
            continue
        if kucuk.startswith("stresses"):
            blokta = True
            continue
        bas = satir.split()
        if not blokta or not bas or not bas[0].isdigit():
            continue
        sayilar = re.findall(_NUM, satir, flags=re.IGNORECASE)
        toplam.setdefault(int(bas[0]), []).append(np.array([float(v) for v in sayilar[:6]]))
    return {e: np.mean(s, axis=0) for e, s in toplam.items()}


def karsilastir(model: Model, tmp_path, inp: str) -> None:
    ref = solve_ccx(model, tmp_path, inp=inp)
    ours = solve(model)

    u = np.array([[ours.displacement(model, n.id, d) for d in DOFS] for n in model.nodes])
    u_ref = np.array([ref.u[n.id] for n in model.nodes])
    np.testing.assert_allclose(u, u_ref, rtol=0, atol=TOL_U * np.abs(u_ref).max())

    tutulu = sorted({(bc.node, bc.dof) for bc in model.bcs})
    F: dict[tuple[int, str], float] = {}
    for ld in model.loads:
        F[(ld.node, ld.dof)] = F.get((ld.node, ld.dof), 0.0) + ld.value
    R = np.array([ours.reaction(model, n, d) + F.get((n, d), 0.0) for n, d in tutulu])
    R_ref = np.array([ref.rf[n][DOFS.index(d)] for n, d in tutulu])
    np.testing.assert_allclose(R, R_ref, rtol=0, atol=TOL_U * np.abs(R_ref).max())

    s_ref = gauss_ortalama_gerilme((tmp_path / "model.dat").read_text())
    S = post.element_stress_tensors(model, ours.u)
    s = np.array([S[e.id] for e in model.elements])
    s_r = np.array([s_ref[e.id] for e in model.elements])
    np.testing.assert_allclose(s, s_r, rtol=0, atol=TOL_S * np.abs(s_r).max())


def kutu(kaydirma: float) -> Model:
    """gmsh'siz Kuhn tet10 kutusu, iki malzeme, sol yüz ankastre, sağ yüze eğik tri6 çekme."""
    L = 24.0
    m = kutu_agi10(L, 10.0, 8.0, 4, 2, 2, Material("celik", 210_000.0, 0.3), kaydirma=kaydirma, tohum=21)
    m.materials.append(Material("al", 70_000.0, 0.33))
    for e in m.elements:
        if np.mean([m.node(n).x for n in e.nodes[:4]]) > L / 2:
            e.material = "al"
    m.bcs = [BC(n, d, 0.0) for n in yuz_dugumleri(m, 0, 0.0) for d in DOFS]
    m.loads = yuzey_cekmesi10(m, 0, L, (3.0, -1.0, 2.0))
    return m


def fileio_inp(model: Model) -> str:
    from fileio.calculix import to_inp

    return to_inp(model)


@needs_ccx
@pytest.mark.parametrize("kaydirma", [0.0, 0.2])
def test_helper_c3d10_box_matches_ccx(kaydirma, tmp_path):
    m = kutu(kaydirma)
    karsilastir(m, tmp_path, c3d10_inp(m))


@needs_ccx
@pytest.mark.parametrize("kaydirma", [0.0, 0.2])
def test_fileio_c3d10_box_matches_solver(kaydirma, tmp_path):
    m = kutu(kaydirma)
    inp = fileio_inp(m)
    assert re.search(r"\*ELEMENT\s*,\s*TYPE\s*=\s*C3D10", inp, flags=re.IGNORECASE)
    karsilastir(m, tmp_path, inp)


def kaba_plaka() -> Model:
    """K6 delikli plakasının kaba ağı: h = 5, inceltme yok, order = 2."""
    pytest.importorskip("gmsh")
    pytest.importorskip("build123d")
    from tests.benchmarks.test_tet10 import kirsch_modeli

    return kirsch_modeli(5.0)


@needs_ccx
@pytest.mark.occt
def test_helper_c3d10_plate_matches_ccx(tmp_path):
    m = kaba_plaka()
    karsilastir(m, tmp_path, c3d10_inp(m))


@needs_ccx
@pytest.mark.occt
def test_fileio_c3d10_plate_matches_solver(tmp_path):
    m = kaba_plaka()
    karsilastir(m, tmp_path, fileio_inp(m))
