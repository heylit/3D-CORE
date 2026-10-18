"""
SPEC 12 — parçadan tet4 ağı (mesh.tet_mesh, mesh.Refine): K1, K3, K4, K5, K6.

Testler sadece specs/12-gmsh.md'den yazıldı; mesh/ uygulama kodu okunmadı.
gmsh gerektiren testler `gmsh` fikstürüyle (pytest.importorskip("gmsh")) ve `occt` işaretiyle atlanabilir.
build123d kutusu varsayılan olarak orijinde ortalanır; burada köşesi orijinde olsun diye Align.MIN kullanılır.
Ağ üreten yardımcılar test gövdesinde çağrılır (fikstürde değil): iskeletteki NotImplementedError
böylece "uygulanmamış" sayılır.
"""

from __future__ import annotations

import functools
import itertools
import math

import numpy as np
import pytest

import mesh
from core.model import Material, Model, ModelError

E, NU = 210_000.0, 0.3


def celik() -> Material:
    return Material("celik", E, NU)


@pytest.fixture
def gmsh():
    return pytest.importorskip("gmsh", reason='gmsh kurulu değil (pip install -e ".[mesh]")')


# --- parça üreticileri (uydurma geometri) --------------------------------------


def kutu(a: float, b: float, c: float, name: str = "kutu"):
    """[0, a] x [0, b] x [0, c] kutusu."""
    import build123d as bd

    from geometry.part import Part

    return Part(bd.Box(a, b, c, align=(bd.Align.MIN,) * 3), name=name)


def silindir(R: float, L: float):
    """Ekseni z olan silindir, z ∈ [−L/2, L/2]."""
    import build123d as bd

    from geometry.part import Part

    return Part(bd.Cylinder(R, L), name="silindir")


@functools.cache
def kutu_agi(h: float = 4.0) -> Model:
    return mesh.tet_mesh(kutu(30.0, 20.0, 10.0), h, celik())


@functools.cache
def silindir_agi(h: float) -> Model:
    return mesh.tet_mesh(silindir(10.0, 20.0), h, celik())


# --- ağ ölçüleri (testin kendi hesabı, SPEC Teori) ------------------------------


def koordinatlar(model: Model) -> dict[int, np.ndarray]:
    return {n.id: n.xyz for n in model.nodes}


def detC(model: Model) -> np.ndarray:
    """Her eleman için det C = det[x_b − x_a, x_c − x_a, x_d − x_a] (= 6V, işaretli)."""
    X = koordinatlar(model)
    T = np.array([[X[n] for n in e.nodes] for e in model.elements])  # (m, 4, 3)
    return np.linalg.det(T[:, 1:, :] - T[:, :1, :])


def kenarlar(model: Model) -> set[tuple[int, int]]:
    """Ağın tekil kenarları (küçük id önce)."""
    k = set()
    for e in model.elements:
        for i, j in itertools.combinations(e.nodes, 2):
            k.add((min(i, j), max(i, j)))
    return k


# --- K1: kutu ağı ------------------------------------------------------------------


@pytest.mark.occt
def test_k1_kutu_agi_yapisi(gmsh):
    """Bütün elemanlar tet4; düğüm id'leri 1..n, eleman id'leri 1..m; her düğüm bir elemanda."""
    m = kutu_agi()
    assert m.dim == 3
    assert m.name == "kutu"
    assert m.materials == [celik()]
    assert m.bcs == [] and m.loads == []
    assert len(m.elements) > 0
    assert [n.id for n in m.nodes] == list(range(1, len(m.nodes) + 1))
    assert [e.id for e in m.elements] == list(range(1, len(m.elements) + 1))
    for e in m.elements:
        assert e.type == "tet4"
        assert e.material == "celik"
        assert len(e.nodes) == 4 and len(set(e.nodes)) == 4
    kullanilan = {n for e in m.elements for n in e.nodes}
    assert kullanilan == {n.id for n in m.nodes}
    m.validate()


@pytest.mark.occt
def test_k1_sag_el_sirasi_ve_hacim(gmsh):
    """Her elemanda det C > 0 (sağ el); Σ V = 30·20·10 = 6000 mm³ (düzlemsel yüzler: tam)."""
    d = detC(kutu_agi())
    assert np.all(d > 0)
    assert d.sum() / 6.0 == pytest.approx(6000.0, rel=1e-9)


@pytest.mark.occt
def test_k1_dugumler_parcanin_icinde(gmsh):
    """Bütün düğümler kutunun içinde veya yüzeyinde (yuvarlama payıyla)."""
    X = np.array([n.xyz for n in kutu_agi().nodes])
    assert np.all(X >= -1e-9)
    assert np.all(X <= np.array([30.0, 20.0, 10.0]) + 1e-9)


# --- K3: silindir ---------------------------------------------------------------------


@pytest.mark.occt
def test_k3_silindir_sinir_dugumleri_yuzeyde(gmsh):
    """Sınır üçgenlerinde, uç düzlemlerinde (z = ±10) olmayan her düğüm |r − R| ≤ 1e-6 R."""
    R = 10.0
    m = silindir_agi(2.5)
    X = koordinatlar(m)
    sinir = {int(n) for n in mesh.boundary_triangles(m).ravel()}
    yan = [n for n in sinir if abs(abs(X[n][2]) - 10.0) > 1e-9]
    assert len(yan) > 0
    r = np.array([math.hypot(X[n][0], X[n][1]) for n in yan])
    assert np.all(np.abs(r - R) <= 1e-6 * R)


@pytest.mark.occt
def test_k3_silindir_hacim_yakinsamasi(gmsh):
    """
    İçten çizilmiş çokyüzlü: hacim hatası e = 1 − V_ağ / (π R² L) > 0 ve h küçüldükçe azalır.
    h = 2.5'te ≤ %1, h = 1.25'te ≤ %0.5 (ön hesap: %1.35, %0.72, %0.19).
    """
    V0 = math.pi * 10.0**2 * 20.0
    e = [1.0 - detC(silindir_agi(h)).sum() / 6.0 / V0 for h in (5.0, 2.5, 1.25)]
    assert all(x > 0 for x in e), e
    assert e[0] > e[1] > e[2], e
    assert e[1] <= 0.01, e
    assert e[2] <= 0.005, e


@pytest.mark.occt
def test_k3_silindir_sag_el(gmsh):
    """Eğri yüzlü parçada da her elemanda det C > 0."""
    assert np.all(detC(silindir_agi(2.5)) > 0)


# --- K4: tekrarlanabilirlik ---------------------------------------------------------


@pytest.mark.occt
def test_k4_ayni_argumanlar_ayni_model(gmsh):
    """Aynı parça ve argümanlarla iki çağrı == olan iki Model verir (düğüm sırası dahil)."""
    p = kutu(30.0, 20.0, 10.0)
    m1 = mesh.tet_mesh(p, 4.0, celik())
    m2 = mesh.tet_mesh(p, 4.0, celik())
    assert m1 == m2
    r = [mesh.Refine((15.0, 10.0, 5.0), 4.0, 1.5)]
    assert mesh.tet_mesh(p, 4.0, celik(), refine=r) == mesh.tet_mesh(p, 4.0, celik(), refine=r)


# --- K5: yerel inceltme ---------------------------------------------------------------

BLOK = (100.0, 50.0, 10.0)
MERKEZ = np.array([50.0, 25.0, 5.0])


@functools.cache
def blok_agi(inceltme: bool) -> Model:
    r = [mesh.Refine(tuple(MERKEZ), 8.0, 1.0)] if inceltme else []
    return mesh.tet_mesh(kutu(*BLOK, name="blok"), 5.0, celik(), refine=r)


def kenar_boylari(model: Model, sadece_kure: bool) -> np.ndarray:
    X = koordinatlar(model)
    boylar = []
    for i, j in kenarlar(model):
        if sadece_kure and (np.linalg.norm(X[i] - MERKEZ) > 8.0 or np.linalg.norm(X[j] - MERKEZ) > 8.0):
            continue
        boylar.append(np.linalg.norm(X[i] - X[j]))
    return np.array(boylar)


@pytest.mark.occt
def test_k5_kure_icinde_kenar_boyu(gmsh):
    """İki ucu kürenin (r = 8) içinde olan kenarların ortalama boyu ≤ 1.5 · h_yerel = 1.5 (ön hesap 1.33)."""
    boy = kenar_boylari(blok_agi(True), sadece_kure=True)
    assert len(boy) > 0
    assert boy.mean() <= 1.5


@pytest.mark.occt
def test_k5_inceltmesiz_kenar_boyu(gmsh):
    """İnceltmesiz ağda bütün kenarların ortalaması ≤ 1.5 h = 7.5 (ön hesap 1.21 h)."""
    assert kenar_boylari(blok_agi(False), sadece_kure=False).mean() <= 1.5 * 5.0


@pytest.mark.occt
def test_k5_inceltme_eleman_sayisini_artirir(gmsh):
    """İnceltmeli ağ daha çok eleman içerir (ön hesap 13205 > 2341); hacim yine tam."""
    m1, m0 = blok_agi(True), blok_agi(False)
    assert len(m1.elements) > len(m0.elements)
    assert detC(m1).sum() / 6.0 == pytest.approx(100.0 * 50.0 * 10.0, rel=1e-9)
    assert np.all(detC(m1) > 0)


# --- K6: hatalar ------------------------------------------------------------------------


@pytest.mark.occt
@pytest.mark.parametrize("h", [0.0, -1.0, math.nan, math.inf])
def test_k6_gecersiz_h(gmsh, h):
    with pytest.raises(ModelError):
        mesh.tet_mesh(kutu(30.0, 20.0, 10.0), h, celik())


@pytest.mark.parametrize(
    "radius, h",
    [(0.0, 1.0), (-1.0, 1.0), (1.0, 0.0), (1.0, -2.0), (math.nan, 1.0), (1.0, math.inf)],
)
def test_k6_gecersiz_refine(radius, h):
    """Refine yarıçapı / boyu ≤ 0 veya sonlu değil → ModelError (gmsh gerekmez)."""
    with pytest.raises(ModelError):
        mesh.Refine((0.0, 0.0, 0.0), radius, h)


def test_k6_refine_sonlu_olmayan_merkez():
    with pytest.raises(ModelError):
        mesh.Refine((0.0, math.nan, 0.0), 1.0, 1.0)


def test_k6_refine_gecerli_ve_dondurulmus():
    r = mesh.Refine((1.0, 2.0, 3.0), 4.0, 0.5)
    assert (tuple(r.center), r.radius, r.h) == ((1.0, 2.0, 3.0), 4.0, 0.5)
    with pytest.raises(AttributeError):  # dataclasses.FrozenInstanceError
        r.h = 1.0  # type: ignore[misc]


@pytest.mark.occt
def test_k6_max_nodes_asimi(gmsh):
    with pytest.raises(ModelError):
        mesh.tet_mesh(kutu(30.0, 20.0, 10.0), 4.0, celik(), max_nodes=10)


@pytest.mark.occt
@pytest.mark.parametrize("girdi", ["kutu", None, "build123d_kutu"])
def test_k6_part_olmayan_girdi(gmsh, girdi):
    if girdi == "build123d_kutu":
        import build123d as bd

        girdi = bd.Box(10.0, 10.0, 10.0)  # Shape, Part değil
    with pytest.raises(ModelError):
        mesh.tet_mesh(girdi, 4.0, celik())


@pytest.mark.occt
def test_k6_iki_ayrik_kati(gmsh):
    """İki ayrık kutudan oluşan parça tek katı değil → ModelError."""
    import build123d as bd

    from geometry.part import Part

    iki = bd.Box(10.0, 10.0, 10.0) + bd.Pos(50.0, 0.0, 0.0) * bd.Box(10.0, 10.0, 10.0)
    with pytest.raises(ModelError):
        mesh.tet_mesh(Part(iki, name="iki_kutu"), 4.0, celik())
