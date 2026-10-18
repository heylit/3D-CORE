"""
SPEC 12 — sınır yüzeyi ve geometrik seçim (mesh.secim): K2, K7.

Testler sadece specs/12-gmsh.md'den yazıldı; mesh/ uygulama kodu okunmadı.
gmsh'siz testler SPEC 11'in yapılandırılmış Kuhn ağını (tests/benchmarks/tet_ag.py) kullanır; bu ağda
sağ el ve sol el elemanlar bilerek birlikte bulunur. gmsh testleri `gmsh` fikstürü ve `occt` işaretiyle
atlanabilir.
"""

from __future__ import annotations

import functools
import math
from collections import Counter

import numpy as np
import pytest

import mesh
from core.model import Element, Material, Model, ModelError, Node
from tests.benchmarks.tet_ag import kutu_agi

E, NU = 210_000.0, 0.3
L, B, H = 10.0, 4.0, 2.0  # yapılandırılmış kutu [mm]
NX, NY, NZ = 5, 2, 2


def celik() -> Material:
    return Material("celik", E, NU)


@pytest.fixture
def gmsh():
    return pytest.importorskip("gmsh", reason='gmsh kurulu değil (pip install -e ".[mesh]")')


def yapili_ag(kaydirma: float = 0.2) -> Model:
    return kutu_agi(L, B, H, NX, NY, NZ, celik(), kaydirma=kaydirma, tohum=3)


@functools.cache
def gmsh_kutu() -> Model:
    import build123d as bd

    from geometry.part import Part

    return mesh.tet_mesh(Part(bd.Box(30.0, 20.0, 10.0, align=(bd.Align.MIN,) * 3), name="kutu"), 4.0, celik())


@functools.cache
def gmsh_silindir() -> Model:
    import build123d as bd

    from geometry.part import Part

    return mesh.tet_mesh(Part(bd.Cylinder(10.0, 20.0), name="silindir"), 2.5, celik())


def tek_tet(sira: tuple[int, int, int, int] = (1, 2, 3, 4)) -> Model:
    """Köşeleri (0,0,0), (1,0,0), (0,1,0), (0,0,1) olan tek tetrahedron; sira eleman düğüm sırası."""
    nodes = [Node(1, 0.0, 0.0, 0.0), Node(2, 1.0, 0.0, 0.0), Node(3, 0.0, 1.0, 0.0), Node(4, 0.0, 0.0, 1.0)]
    return Model(
        dim=3,
        nodes=nodes,
        elements=[Element(1, "tet4", list(sira), "celik")],
        materials=[celik()],
        name="tek",
    )


# --- testin kendi üçgen hesabı (SPEC Teori) ----------------------------------------


def ucgen_verisi(model: Model, tris: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """(A, n, c): alanlar (k,), birim dış normaller (k, 3), ağırlık merkezleri (k, 3)."""
    X = {n.id: n.xyz for n in model.nodes}
    P = np.array([[X[int(i)] for i in t] for t in tris])  # (k, 3, 3)
    v = np.cross(P[:, 1] - P[:, 0], P[:, 2] - P[:, 0])
    A2 = np.linalg.norm(v, axis=1)
    return 0.5 * A2, v / A2[:, None], P.mean(axis=1)


def hacim(model: Model) -> float:
    X = {n.id: n.xyz for n in model.nodes}
    T = np.array([[X[n] for n in e.nodes] for e in model.elements])
    return float(np.abs(np.linalg.det(T[:, 1:] - T[:, :1])).sum() / 6.0)


def kapali_yuzey_kontrol(model: Model, tris: np.ndarray, alan: float, V: float) -> None:
    """K2: Σ A = alan; her kenar tam iki üçgende ters yönde; |Σ n A| ≤ 1e-9 Σ A; ⅓ Σ (c · n) A = V."""
    assert tris.ndim == 2 and tris.shape[1] == 3 and len(tris) > 0
    assert np.issubdtype(tris.dtype, np.integer)
    A, n, c = ucgen_verisi(model, tris)
    assert A.sum() == pytest.approx(alan, rel=1e-9)
    yonlu = Counter()
    for i, j, k in tris.tolist():
        yonlu.update([(i, j), (j, k), (k, i)])
    assert all(v == 1 for v in yonlu.values()), "bir yönlü kenar birden fazla üçgende"
    assert all((j, i) in yonlu for (i, j) in yonlu), "kenarın ters yönlüsü yok"
    assert np.linalg.norm((n * A[:, None]).sum(axis=0)) <= 1e-9 * A.sum()
    assert ((c * n).sum(axis=1) * A).sum() / 3.0 == pytest.approx(V, rel=1e-9)


def disa_bakiyor(model: Model, tris: np.ndarray) -> None:
    """Her sınır üçgeninin normali, ait olduğu tetrahedronun dördüncü köşesinden uzağa bakar."""
    X = {n.id: n.xyz for n in model.nodes}
    _, n, c = ucgen_verisi(model, tris)
    sahip = {}
    for e in model.elements:
        for d in e.nodes:
            yuz = frozenset(set(e.nodes) - {d})
            sahip.setdefault(yuz, []).append(d)
    for t, nt, ct in zip(tris.tolist(), n, c, strict=True):
        d = sahip[frozenset(t)]
        assert len(d) == 1, "sınır üçgeni tek bir elemana ait olmalı"
        assert np.dot(ct - X[d[0]], nt) > 0


# --- boundary_triangles: tek tetrahedron (el hesabı) --------------------------------


def test_tek_tet_sinir_ucgenleri_sag_el():
    """Pozitif tet (a, b, c, d): dış yüzler (a, c, b), (a, b, d), (a, d, c), (b, c, d), bu sırada."""
    tris = mesh.boundary_triangles(tek_tet())
    np.testing.assert_array_equal(tris, [[1, 3, 2], [1, 2, 4], [1, 4, 3], [2, 3, 4]])


def test_tek_tet_alan_ve_normal():
    """Yüz alanları ½, ½, ½, √3/2; dış normaller −z, −y, −x, (1, 1, 1)/√3."""
    m = tek_tet()
    tris = np.array([[1, 3, 2], [1, 2, 4], [1, 4, 3], [2, 3, 4]])
    np.testing.assert_allclose(mesh.triangle_areas(m, tris), [0.5, 0.5, 0.5, math.sqrt(3) / 2], rtol=1e-14)
    s = 1 / math.sqrt(3)
    np.testing.assert_allclose(
        mesh.triangle_normals(m, tris), [[0, 0, -1], [0, -1, 0], [-1, 0, 0], [s, s, s]], atol=1e-14
    )


def test_tek_tet_sol_el_yine_disa_bakar():
    """Sol el sıralı (det C < 0) elemanda da sınır üçgenleri dışa bakar; aynı dört yüz."""
    m = tek_tet((1, 3, 2, 4))
    tris = mesh.boundary_triangles(m)
    assert tris.shape == (4, 3)
    assert {frozenset(t) for t in tris.tolist()} == {
        frozenset(s) for s in ((1, 2, 3), (1, 2, 4), (1, 3, 4), (2, 3, 4))
    }
    disa_bakiyor(m, tris)
    kapali_yuzey_kontrol(m, tris, 1.5 + math.sqrt(3) / 2, 1.0 / 6.0)


def test_iki_tet_ortak_yuz_sinirda_degil():
    """Ortak yüzü (2, 3, 4) olan iki tet: sınırda 6 üçgen, ortak yüz yok."""
    nodes = [
        Node(1, 0.0, 0.0, 0.0),
        Node(2, 1.0, 0.0, 0.0),
        Node(3, 0.0, 1.0, 0.0),
        Node(4, 0.0, 0.0, 1.0),
        Node(5, 1.0, 1.0, 1.0),
    ]
    els = [Element(1, "tet4", [1, 2, 3, 4], "celik"), Element(2, "tet4", [5, 2, 4, 3], "celik")]
    m = Model(dim=3, nodes=nodes, elements=els, materials=[celik()])
    tris = mesh.boundary_triangles(m)
    assert tris.shape == (6, 3)
    assert frozenset((2, 3, 4)) not in {frozenset(t) for t in tris.tolist()}
    disa_bakiyor(m, tris)


# --- K2: kapalı yüzey özellikleri ------------------------------------------------------


@pytest.mark.parametrize("kaydirma", [0.0, 0.2])
def test_k2_yapili_ag_kapali_yuzey(kaydirma):
    """Kuhn kutusu (sağ el + sol el elemanlar): Σ A = 2(Lb + bh + hL), V = L b h; dışa bakan."""
    m = yapili_ag(kaydirma)
    tris = mesh.boundary_triangles(m)
    assert len(tris) == 2 * 2 * (NX * NY + NY * NZ + NZ * NX)  # her dış kare yüz 2 üçgen
    kapali_yuzey_kontrol(m, tris, 2 * (L * B + B * H + H * L), L * B * H)
    disa_bakiyor(m, tris)


def test_k2_tekrarlanabilir():
    m = yapili_ag()
    np.testing.assert_array_equal(mesh.boundary_triangles(m), mesh.boundary_triangles(m))


@pytest.mark.occt
def test_k2_gmsh_kutu_kapali_yuzey(gmsh):
    """gmsh kutusu: Σ A = part.area = 2200, ⅓ Σ (c · n) A = V = 6000 (rel 1e-9)."""
    m = gmsh_kutu()
    tris = mesh.boundary_triangles(m)
    kapali_yuzey_kontrol(m, tris, 2 * (30 * 20 + 20 * 10 + 10 * 30), 6000.0)
    disa_bakiyor(m, tris)


@pytest.mark.occt
def test_k2_gmsh_silindir_kapali_yuzey(gmsh):
    """Eğri yüzlü ağda da kapalı, dışa yönlü yüzey; diverjans hacmi = tet hacimleri toplamı."""
    m = gmsh_silindir()
    tris = mesh.boundary_triangles(m)
    A, _, _ = ucgen_verisi(m, tris)
    kapali_yuzey_kontrol(m, tris, A.sum(), hacim(m))


# --- K7: tahminler ------------------------------------------------------------------------


def test_k7_on_plane_vektorel():
    """(n, 3) dizi → (n,) bool; normal birim olmak zorunda değil (n̂ kullanılır)."""
    pred = mesh.on_plane((1.0, 0.0, 0.0), (2.0, 0.0, 0.0), tol=1e-3)
    P = np.array(
        [[1.0, 5.0, -3.0], [1.0005, 0.0, 0.0], [1.002, 0.0, 0.0], [0.0, 0.0, 0.0], [0.9999, 7.0, 7.0]]
    )
    sonuc = pred(P)
    assert isinstance(sonuc, np.ndarray) and sonuc.shape == (5,) and sonuc.dtype == bool
    np.testing.assert_array_equal(sonuc, [True, True, False, False, True])


def test_k7_on_plane_egik_normal():
    """x + y + z = 3 düzlemi: point (1, 1, 1), normal (1, 1, 1)."""
    pred = mesh.on_plane((1.0, 1.0, 1.0), (1.0, 1.0, 1.0))
    P = np.array([[3.0, 0.0, 0.0], [0.0, 1.5, 1.5], [1.0, 1.0, 1.1]])
    np.testing.assert_array_equal(pred(P), [True, True, False])


def test_k7_on_cylinder_vektorel():
    """Eksen (0, 0, 1) üstünden geçen, (5, 0, 0) noktalı silindir, R = 2."""
    pred = mesh.on_cylinder((5.0, 0.0, 0.0), (0.0, 0.0, 3.0), 2.0, tol=1e-3)
    P = np.array(
        [
            [7.0, 0.0, 0.0],
            [5.0, -2.0, 100.0],
            [5.0 + math.sqrt(2), math.sqrt(2), -4.0],
            [5.0, 0.0, 0.0],
            [7.01, 0, 0],
        ]
    )
    sonuc = pred(P)
    assert isinstance(sonuc, np.ndarray) and sonuc.shape == (5,) and sonuc.dtype == bool
    np.testing.assert_array_equal(sonuc, [True, True, True, False, False])


def test_k7_on_cylinder_egik_eksen():
    """Ekseni (1, 1, 0) yönünde, orijinden geçen R = 1 silindir: (0, 0, 1) ve (1/√2, −1/√2, 0) üstünde."""
    pred = mesh.on_cylinder((0.0, 0.0, 0.0), (1.0, 1.0, 0.0), 1.0)
    s = 1 / math.sqrt(2)
    P = np.array([[0.0, 0.0, 1.0], [s + 4.0, -s + 4.0, 0.0], [1.0, 0.0, 0.0]])
    np.testing.assert_array_equal(pred(P), [True, True, False])


@pytest.mark.parametrize(
    "kur",
    [
        lambda: mesh.on_plane((0, 0, 0), (0, 0, 0)),
        lambda: mesh.on_plane((0, 0, 0), (1, 0, 0), tol=0.0),
        lambda: mesh.on_plane((0, 0, 0), (1, 0, 0), tol=-1e-6),
        lambda: mesh.on_cylinder((0, 0, 0), (0, 0, 0), 1.0),
        lambda: mesh.on_cylinder((0, 0, 0), (0, 0, 1), 0.0),
        lambda: mesh.on_cylinder((0, 0, 0), (0, 0, 1), -1.0),
        lambda: mesh.on_cylinder((0, 0, 0), (0, 0, 1), 1.0, tol=0.0),
    ],
    ids=["sifir_normal", "tol_0", "tol_negatif", "sifir_eksen", "R_0", "R_negatif", "sil_tol_0"],
)
def test_k7_gecersiz_tahmin(kur):
    with pytest.raises(ModelError):
        kur()


# --- K7: seçim (yapılandırılmış ağ) --------------------------------------------------------


def test_k7_select_nodes_duzlem():
    """x = L yüzü: (ny + 1)(nz + 1) düğüm, artan sırada, hepsi düzlemde."""
    m = yapili_ag()
    ids = mesh.select_nodes(m, mesh.on_plane((L, 0.0, 0.0), (1.0, 0.0, 0.0)))
    assert isinstance(ids, list)
    assert len(ids) == (NY + 1) * (NZ + 1)
    assert ids == sorted(ids)
    beklenen = sorted(n.id for n in m.nodes if abs(n.x - L) <= 1e-9)
    assert ids == beklenen


def test_k7_select_triangles_duzlem_alani():
    """x = L yüzündeki sınır üçgenleri: Σ A = b · h (rel 1e-12), normaller +x, sayı 2 · ny · nz."""
    m = yapili_ag()
    tris = mesh.select_triangles(m, mesh.on_plane((L, 0.0, 0.0), (1.0, 0.0, 0.0)))
    assert tris.shape == (2 * NY * NZ, 3)
    assert mesh.triangle_areas(m, tris).sum() == pytest.approx(B * H, rel=1e-12)
    np.testing.assert_allclose(
        mesh.triangle_normals(m, tris), np.tile([1.0, 0.0, 0.0], (len(tris), 1)), atol=1e-12
    )


def test_k7_select_triangles_sinir_sirasinda():
    """Seçilen üçgenler boundary_triangles'ın, aynı sırada, alt kümesidir."""
    m = yapili_ag()
    tum = [tuple(t) for t in mesh.boundary_triangles(m).tolist()]
    sec = [tuple(t) for t in mesh.select_triangles(m, mesh.on_plane((0, 0, H), (0, 0, 1))).tolist()]
    assert len(sec) == 2 * NX * NY
    assert sec == [t for t in tum if t in set(sec)]


def test_k7_hic_secim_bos():
    m = yapili_ag()
    pred = mesh.on_plane((L + 5.0, 0, 0), (1, 0, 0))
    assert mesh.select_nodes(m, pred) == []
    assert mesh.select_triangles(m, pred).shape == (0, 3)


def test_k7_uc_alan_ve_normal_sinirla_tutarli():
    """triangle_areas / triangle_normals testin kendi hesabıyla aynı (tüm sınır)."""
    m = yapili_ag()
    tris = mesh.boundary_triangles(m)
    A, n, _ = ucgen_verisi(m, tris)
    np.testing.assert_allclose(mesh.triangle_areas(m, tris), A, rtol=1e-12)
    np.testing.assert_allclose(mesh.triangle_normals(m, tris), n, atol=1e-12)


# --- K7: seçim (gmsh ağları) --------------------------------------------------------------


@pytest.mark.occt
def test_k7_gmsh_kutu_duzlem_secimi(gmsh):
    """gmsh kutusunun x = 30 yüzü: Σ A = 20 · 10 (rel 1e-12); seçilen düğümler o düzlemdeki bütün düğümler."""
    m = gmsh_kutu()
    pred = mesh.on_plane((30.0, 0.0, 0.0), (1.0, 0.0, 0.0))
    tris = mesh.select_triangles(m, pred)
    assert mesh.triangle_areas(m, tris).sum() == pytest.approx(200.0, rel=1e-12)
    ids = mesh.select_nodes(m, pred)
    assert ids == sorted(n.id for n in m.nodes if abs(n.x - 30.0) <= 1e-6)
    assert set(np.unique(tris)) == set(ids)


@pytest.mark.occt
def test_k7_gmsh_silindir_secimi(gmsh):
    """
    on_cylinder(R = 10): seçilen her düğüm yüzeyde; üç köşesi yüzeyde olan her sınır üçgeni seçilmiş,
    başkası seçilmemiş.
    """
    m = gmsh_silindir()
    tol = 1e-6
    pred = mesh.on_cylinder((0.0, 0.0, 0.0), (0.0, 0.0, 1.0), 10.0, tol=tol)
    X = {n.id: n.xyz for n in m.nodes}
    r = {i: math.hypot(x[0], x[1]) for i, x in X.items()}
    ids = mesh.select_nodes(m, pred)
    assert len(ids) > 0
    assert all(abs(r[i] - 10.0) <= tol for i in ids)
    assert ids == sorted(i for i in X if abs(r[i] - 10.0) <= tol)
    tum = mesh.boundary_triangles(m).tolist()
    beklenen = [t for t in tum if all(abs(r[i] - 10.0) <= tol for i in t)]
    sec = mesh.select_triangles(m, pred).tolist()
    assert sec == beklenen
