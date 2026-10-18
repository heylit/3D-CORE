"""SPEC 67b — CAD yüzü eşlemesi ve yüze yük (K11, K12). gmsh + OCCT gerektirir.

Testler sadece specs/67-fem-genisletme.md (67b) metninden ve mesh/yuz_esleme.py arayüzünden (modül
docstring'indeki biçim kuralları) yazıldı; gövde okunmadı.
- `face_tris[i]`: OCCT yüz indeksi i → (k, 3) / (k, 6); bütün yüzler anahtar;
  `boundary_triangles`'ın bölüntüsü.
- `triangles(part, ref)`, `nodes(part, ref)`: `part.find(ref)` yüzleri; bulunamayan ref → ModelError.
Kutu 100 × 40 × 20 (min köşe orijinde). FaceRef'ler `Part(names=...)` ile ya da özellik
ağacından (SPEC 18, A2).
Yüze basınç p: toplam kuvvet −p n A (düz yüz). tet10'da (67a) düz üçgende köşeler 0, kenarlar p A/3 alır.
"""

from __future__ import annotations

import numpy as np
import pytest

pytestmark = pytest.mark.occt

LX, LY, LZ = 100.0, 40.0, 20.0
R_DELIK = 6.0
H = 8.0
CELIK_ARGS = ("celik", 210_000.0, 0.3, 7.85e-9)


def _mesh():
    pytest.importorskip("gmsh")
    import mesh

    return mesh


def _yuz_adlari(sekil):
    """Düzlemsel yüzlere eksen adları (xmin, xmax, ...), silindirik iç yüze 'delik'."""
    from geometry.part import FaceRef, Part

    gecici = Part(sekil, name="gecici")
    adlar = {}
    for f in gecici.planar_faces():
        k = int(np.argmax(np.abs(f.normal)))
        adlar[FaceRef("kutu", "xyz"[k] + ("max" if f.normal[k] > 0 else "min"))] = (f.index,)
    for f in gecici.cylindrical_faces():
        adlar[FaceRef("kutu", "delik")] = (f.index,)
    return adlar


def kutu(delikli: bool = False):
    from build123d import Align, Box, Cylinder, Pos

    from geometry.part import Part

    sekil = Box(LX, LY, LZ, align=(Align.MIN, Align.MIN, Align.MIN))
    if delikli:
        sekil = sekil - Pos(LX / 2, LY / 2, LZ / 2) * Cylinder(R_DELIK, 2 * LZ)
    return Part(sekil, name="kutu", names=_yuz_adlari(sekil))


def ref(ad: str):
    from geometry.part import FaceRef

    return FaceRef("kutu", ad)


def _ag(part, order: int):
    from core.model import Material

    return _mesh().mesh_part(part, H, Material(*CELIK_ARGS), order=order)


def _alan(model, tris) -> float:
    """Düz köşe üçgenlerinin alanı (ilk üç sütun)."""
    X = np.array([[model.node(int(n)).xyz for n in t[:3]] for t in tris])
    return float(0.5 * np.linalg.norm(np.cross(X[:, 1] - X[:, 0], X[:, 2] - X[:, 0]), axis=1).sum())


def _satirlar(tris) -> set[tuple[int, ...]]:
    """Üçgen kümesi, yön ve başlangıç köşesinden bağımsız (sıralı köşeler + sıralı kenar düğümleri)."""
    return {tuple(sorted(int(n) for n in t[:3])) + tuple(sorted(int(n) for n in t[3:])) for t in tris}


# ---------- K11 yüz eşlemesi ----------


@pytest.mark.parametrize("order", [1, 2])
def test_all_six_faces_mapped_with_areas(order):
    part = kutu()
    pm = _ag(part, order)
    assert set(pm.face_tris) == set(range(6))
    for f in part.planar_faces():
        tris = np.asarray(pm.face_tris[f.index])
        assert tris.ndim == 2 and tris.shape[1] == (3 if order == 1 else 6)
        assert _alan(pm.model, tris) == pytest.approx(f.area, rel=1e-9)


@pytest.mark.parametrize("order", [1, 2])
def test_face_tris_partition_boundary(order):
    """face_tris boundary_triangles'ın bölüntüsü: her sınır üçgeni tam bir yüzde."""
    mesh = _mesh()
    pm = _ag(kutu(delikli=True), order)
    hepsi = [tuple(t) for tris in pm.face_tris.values() for t in np.asarray(tris).tolist()]
    sinir = [tuple(t) for t in mesh.boundary_triangles(pm.model).tolist()]
    assert len(hepsi) == len(set(hepsi)) == len(sinir)
    assert _satirlar(hepsi) == _satirlar(sinir)


@pytest.mark.parametrize("order", [1, 2])
def test_hole_face_matches_on_cylinder(order):
    """Delik yüzünün üçgenleri on_cylinder seçimiyle aynı küme."""
    mesh = _mesh()
    part = kutu(delikli=True)
    pm = _ag(part, order)
    sec = mesh.select_triangles(
        pm.model, mesh.on_cylinder((LX / 2, LY / 2, 0.0), (0, 0, 1), R_DELIK, tol=1e-6)
    )
    assert _satirlar(pm.triangles(part, ref("delik"))) == _satirlar(sec)
    assert len(sec) > 0


@pytest.mark.parametrize("order", [1, 2])
def test_triangles_and_nodes_by_ref(order):
    """triangles(part, ref) = face_tris[find(ref)]; nodes = o üçgenlerin bütün düğümleri, artan, tekrarsız."""
    part = kutu()
    pm = _ag(part, order)
    (i,) = part.find(ref("xmax"))
    np.testing.assert_array_equal(pm.triangles(part, ref("xmax")), np.asarray(pm.face_tris[i]))
    dugumler = pm.nodes(part, ref("xmax"))
    assert dugumler == sorted({int(n) for n in np.asarray(pm.face_tris[i]).ravel()})
    assert all(abs(pm.model.node(n).x - LX) <= 1e-9 for n in dugumler)


def test_unknown_ref_raises():
    from core.model import ModelError

    part = kutu()
    pm = _ag(part, 1)
    with pytest.raises(ModelError):
        pm.triangles(part, ref("yok"))
    with pytest.raises(ModelError):
        pm.nodes(part, ref("yok"))


def test_feature_tree_ref():
    """Özellik ağacından gelen FaceRef (Blok "blok", ad xmax) ile triangles aynı yüzü döndürür."""
    from geometry.agac import Agac, Blok, insa
    from geometry.part import FaceRef

    s = insa(Agac((Blok("blok", LX, LY, LZ),)))
    part = s.part
    pm = _ag(part, 1)
    r = FaceRef("blok", "xmax")
    (i,) = part.find(r)
    tris = pm.triangles(part, r)
    np.testing.assert_array_equal(tris, np.asarray(pm.face_tris[i]))
    X = np.array([pm.model.node(int(n)).xyz for n in np.asarray(tris).ravel()])
    xmax = max(n.x for n in pm.model.nodes)
    np.testing.assert_allclose(X[:, 0], xmax, atol=1e-9)
    assert _alan(pm.model, tris) == pytest.approx(LY * LZ, rel=1e-9)


# ---------- K12 yüze yük ----------


def _toplam(model) -> np.ndarray:
    F = np.zeros(3)
    for ld in model.loads:
        F["xyz".index(ld.dof[1])] += ld.value
    return F


@pytest.mark.parametrize("order", [1, 2])
def test_pressure_on_face_total(order):
    """+x yüzüne p = 2: toplam (−2·40·20, 0, 0) = (−1600, 0, 0) N (göreli 1e-12), tet4 ve tet10'da aynı."""
    mesh = _mesh()
    part = kutu()
    pm = _ag(part, order)
    mesh.add_pressure(pm.model, pm.triangles(part, ref("xmax")), 2.0)
    np.testing.assert_allclose(_toplam(pm.model), [-1600.0, 0.0, 0.0], rtol=1e-12, atol=1e-12 * 1600)


def test_pressure_tet10_corner_zero_edge_third():
    """tet10: köşe düğümleri 0, kenar düğümleri Σ p A_üçgen / 3 (düz üçgen)."""
    mesh = _mesh()
    part = kutu()
    pm = _ag(part, 2)
    tris = np.asarray(pm.triangles(part, ref("xmax")))
    mesh.add_pressure(pm.model, tris, 2.0)
    Fx: dict[int, float] = {}
    for ld in pm.model.loads:
        if ld.dof == "ux":
            Fx[ld.node] = Fx.get(ld.node, 0.0) + ld.value
    beklenen: dict[int, float] = {}
    for t in tris:
        A = _alan(pm.model, [t])
        for n in t[3:]:
            beklenen[int(n)] = beklenen.get(int(n), 0.0) - 2.0 * A / 3
    for n in {int(k) for k in tris[:, :3].ravel()}:
        assert Fx.get(n, 0.0) == pytest.approx(0.0, abs=1e-9)
    for n, v in beklenen.items():
        assert Fx.get(n, 0.0) == pytest.approx(v, rel=1e-9)


@pytest.mark.parametrize("order", [1, 2])
def test_internal_pressure_on_hole_balances(order):
    """Delik yüzüne iç basınçta toplam kuvvet ≈ 0 (abs 1e-3 · p A)."""
    mesh = _mesh()
    part = kutu(delikli=True)
    pm = _ag(part, order)
    p = 5.0
    tris = pm.triangles(part, ref("delik"))
    mesh.add_pressure(pm.model, tris, p)
    A = 2 * np.pi * R_DELIK * LZ
    assert np.linalg.norm(_toplam(pm.model)) <= 1e-3 * p * A
