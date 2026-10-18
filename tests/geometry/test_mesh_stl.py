"""SPEC 02 — geometry/mesh.py testleri (K7, K8). OCCT gerektirir (mesh_volume testleri saf numpy).

Testler SPEC 02 teorisinden yazıldı; uygulama gövdeleri okunmadı.
Ağ hacmi (diverjans teoremi): V = (1/6) Σ p₁ · (p₂ × p₃), dışa bakan üçgenlerle.
Silindir ağı içe çizilmiş n-gen prizma: V_ağ = (n/2) r² sin(2π/n) h < π r² h.
"""

from __future__ import annotations

import math
from collections import Counter
from pathlib import Path

import numpy as np
import pytest

from geometry.features import block, cylinder, hole
from geometry.mesh import mesh_volume, read_stl, tessellate
from geometry.part import GeometryError, Part

pytestmark = pytest.mark.occt

A, B, C = 100.0, 60.0, 30.0  # blok [mm]

# Birim tetrahedron: köşeler O, e_x, e_y, e_z; dışa bakan yüzler (sağ el kuralı, normal dışarı).
# V = (1/6)|det[e_x, e_y, e_z]| = 1/6.
TET_V = np.array([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]])
TET_T = np.array([[0, 2, 1], [0, 1, 3], [0, 3, 2], [1, 2, 3]])

# Birim küp [0,1]³: köşe i = (bit0, bit1, bit2); her yüz 2 üçgen, dışa bakan.
CUBE_V = np.array([[i & 1, (i >> 1) & 1, (i >> 2) & 1] for i in range(8)], dtype=float)
CUBE_T = np.array(
    [
        [0, 2, 3], [0, 3, 1],  # z = 0, normal −Z
        [4, 5, 7], [4, 7, 6],  # z = 1, normal +Z
        [0, 1, 5], [0, 5, 4],  # y = 0, normal −Y
        [2, 6, 7], [2, 7, 3],  # y = 1, normal +Y
        [0, 4, 6], [0, 6, 2],  # x = 0, normal −X
        [1, 3, 7], [1, 7, 5],  # x = 1, normal +X
    ]
)  # fmt: skip


# --- yardımcılar ---------------------------------------------------------------------------------


def assert_closed_oriented(T: np.ndarray) -> None:
    """Kapalı ve tutarlı yönlü ağ: her yönlü kenar (i, j) tam bir kez, tersi (j, i) tam bir kez geçer
    (her kenar tam iki üçgende, zıt yönlerde)."""
    T = np.asarray(T)
    edges = Counter()
    for i, j, k in T:
        for e in ((i, j), (j, k), (k, i)):
            edges[(int(e[0]), int(e[1]))] += 1
    assert all(n == 1 for n in edges.values()), "bir yönlü kenar birden fazla geçiyor"
    missing = [e for e in edges if (e[1], e[0]) not in edges]
    assert not missing, f"ağ açık: {len(missing)} kenarın komşusu yok"


def stl_triangles(path: Path) -> np.ndarray:
    """STL dosyasını (ikili veya ASCII) bağımsız oku → (m, 3, 3) üçgen köşeleri.
    İkili STL: 80 bayt başlık + uint32 üçgen sayısı + üçgen başına 50 bayt (normal, 3 köşe, uint16)."""
    raw = path.read_bytes()
    if len(raw) >= 84:
        n = int(np.frombuffer(raw[80:84], dtype="<u4")[0])
        if len(raw) == 84 + 50 * n:
            dt = np.dtype([("n", "<f4", 3), ("v", "<f4", (3, 3)), ("attr", "<u2")])
            return np.frombuffer(raw[84:], dtype=dt, count=n)["v"].astype(float)
    pts = [
        [float(x) for x in line.split()[1:4]]
        for line in raw.decode("ascii", errors="replace").splitlines()
        if line.strip().startswith("vertex")
    ]
    return np.array(pts, dtype=float).reshape(-1, 3, 3)


def soup_volume(tri: np.ndarray) -> float:
    """Üçgen çorbası hacmi (diverjans): V = (1/6) Σ p₁·(p₂×p₃). Bağımsız referans."""
    return float(np.einsum("ij,ij->i", tri[:, 0], np.cross(tri[:, 1], tri[:, 2])).sum() / 6.0)


def write_ascii_stl(path: Path, tris: list[list[tuple[float, float, float]]]) -> None:
    lines = ["solid elle"]
    for tri in tris:
        lines += ["  facet normal 0 0 0", "    outer loop"]
        lines += [f"      vertex {x} {y} {z}" for x, y, z in tri]
        lines += ["    endloop", "  endfacet"]
    lines.append("endsolid elle")
    path.write_text("\n".join(lines) + "\n")


# --- mesh_volume (saf numpy) ---------------------------------------------------------------------


def test_mesh_volume_unit_tetrahedron():
    """V = 1/6 (birim tetrahedron, el hesabı)."""
    assert mesh_volume(TET_V, TET_T) == pytest.approx(1.0 / 6.0, rel=1e-12)


def test_mesh_volume_unit_cube():
    """V = 1 (birim küp, 12 dışa bakan üçgen)."""
    assert_closed_oriented(CUBE_T)  # referans verinin kendisi doğru mu
    assert mesh_volume(CUBE_V, CUBE_T) == pytest.approx(1.0, rel=1e-12)


def test_mesh_volume_scaled_translated_cube():
    """Kapalı yüzeyde formül ötelemeden bağımsız; ölçek s ile V = s³: s=(100,60,30) → 180000."""
    V = CUBE_V * np.array([A, B, C]) + np.array([-250.0, 40.0, 1000.0])
    assert mesh_volume(V, CUBE_T) == pytest.approx(A * B * C, rel=1e-12)


def test_mesh_volume_inverted_is_negative():
    """Üçgen yönü ters (içe bakan) → işaretli hacim −V."""
    assert mesh_volume(CUBE_V, CUBE_T[:, ::-1]) == pytest.approx(-1.0, rel=1e-12)


# --- K7: tessellate ------------------------------------------------------------------------------


def test_tessellate_block_exact_volume_closed_outward():
    """K7: düz yüzlü blokta ağ geometriyi tam temsil eder: mesh_volume = abc = 180000 rel 1e-9;
    ağ kapalı ve dışa bakan (hacim > 0); köşeler sınır kutusu içinde."""
    V, T = tessellate(block(A, B, C))
    assert V.ndim == 2 and V.shape[1] == 3
    assert T.ndim == 2 and T.shape[1] == 3
    assert np.issubdtype(V.dtype, np.floating)
    assert np.issubdtype(T.dtype, np.integer)
    assert T.min() >= 0 and T.max() < len(V)
    assert_closed_oriented(T)
    vol = mesh_volume(V, T)
    assert vol > 0
    assert vol == pytest.approx(A * B * C, rel=1e-9)
    assert np.all(V >= -1e-9) and np.all(V <= np.array([A, B, C]) + 1e-9)


def test_tessellate_holed_block_closed():
    """K7: delikli blok (cins 1 yüzey) da kapalı ve dışa bakan; V_ağ ≥ V_tam (delik içe çizilmiş
    çokgen → daha az malzeme kalkar), fark küçük."""
    p = hole(block(A, B, C), 20.0, 30.0, 10.0)
    V, T = tessellate(p, tol=0.01)
    assert_closed_oriented(T)
    vol = mesh_volume(V, T)
    assert vol >= p.volume * (1 - 1e-12)
    assert vol == pytest.approx(p.volume, rel=1e-3)


def test_tessellate_cylinder_converges_from_below():
    """K7: silindir r=50, h=20. V_tam = π r² h = 50000π. İçe çizilmiş çokgen: V_ağ ≤ V_tam.
    tol küçüldükçe hata azalır (artmaz) ve en kaba → en ince arasında kesin azalır.
    Ayrıca üst daire üzerindeki n köşe sayılarak V_ağ = (n/2) r² sin(2π/n) h (rel 1e-9)."""
    r, h = 50.0, 20.0
    p = cylinder(r, h)
    V_exact = math.pi * r**2 * h
    errs = []
    for tol in (2.0, 0.5, 0.05):
        V, T = tessellate(p, tol=tol)
        assert_closed_oriented(T)
        vol = mesh_volume(V, T)
        assert 0 < vol <= V_exact * (1 + 1e-12)
        on_top_rim = (np.abs(V[:, 2] - h) < 1e-6) & (np.abs(np.hypot(V[:, 0], V[:, 1]) - r) < 1e-6)
        n = len(np.unique(np.round(V[on_top_rim], 6), axis=0))
        assert n >= 3
        assert vol == pytest.approx((n / 2) * r**2 * math.sin(2 * math.pi / n) * h, rel=1e-9)
        errs.append(V_exact - vol)
    assert errs[1] <= errs[0] and errs[2] <= errs[1]
    assert errs[2] < errs[0]


@pytest.mark.parametrize("tol", [0.0, -0.1])
def test_tessellate_invalid_tol(tol):
    """K7: tol <= 0 → GeometryError."""
    with pytest.raises(GeometryError):
        tessellate(block(A, B, C), tol=tol)


# --- K8: STL -------------------------------------------------------------------------------------


def test_stl_roundtrip_block(tmp_path):
    """K8: düz yüzlü blok to_stl → read_stl: hacim abc = 180000 rel 1e-6, sınır kutusu korunur."""
    path = tmp_path / "blok.stl"
    block(A, B, C).to_stl(path)
    p = read_stl(path, name="okunan_blok")
    assert isinstance(p, Part)
    assert p.name == "okunan_blok"
    assert p.volume == pytest.approx(A * B * C, rel=1e-6)
    lo, hi = p.bbox
    np.testing.assert_allclose(lo, [0.0, 0.0, 0.0], atol=1e-4)
    np.testing.assert_allclose(hi, [A, B, C], atol=1e-4)


def test_stl_roundtrip_holed_block(tmp_path):
    """K8: delikli blok (d=10 boydan) to_stl → read_stl. Silindirik delik çokgenle temsil edildiğinden
    okunan hacim, dosyadaki üçgen ağının hacmine (bağımsız STL ayrıştırıcı + diverjans) rel 1e-6 eşit;
    ağ hacmi tam hacimden biraz büyük (içe çizilmiş delik daha az malzeme kaldırır)."""
    p0 = hole(block(A, B, C), 20.0, 30.0, 10.0)
    path = tmp_path / "delikli.stl"
    p0.to_stl(path, tolerance=0.01)
    V_mesh = soup_volume(stl_triangles(path))
    assert V_mesh >= p0.volume * (1 - 1e-7)
    assert V_mesh == pytest.approx(p0.volume, rel=1e-3)
    p = read_stl(path)
    assert isinstance(p, Part)
    assert p.volume == pytest.approx(V_mesh, rel=1e-6)


def test_read_stl_ascii_tetrahedron(tmp_path):
    """Elle yazılmış ASCII STL, kapalı tetrahedron (kenar 10): V = 10³/6 ≈ 166.667 mm³."""
    s = 10.0
    P = [tuple(float(x) for x in s * TET_V[i]) for i in range(4)]
    path = tmp_path / "tet.stl"
    write_ascii_stl(path, [[P[i] for i in tri] for tri in TET_T])
    p = read_stl(path, name="tet")
    assert p.volume == pytest.approx(s**3 / 6, rel=1e-6)


def test_read_stl_single_triangle_open(tmp_path):
    """K8: tek üçgenlik ASCII STL açık ağdır → GeometryError."""
    path = tmp_path / "tek.stl"
    write_ascii_stl(path, [[(0.0, 0.0, 0.0), (10.0, 0.0, 0.0), (0.0, 10.0, 0.0)]])
    with pytest.raises(GeometryError):
        read_stl(path)


def test_read_stl_tetra_missing_face_open(tmp_path):
    """K8: bir yüzü eksik tetrahedron (3 üçgen) kapalı değil → GeometryError."""
    s = 10.0
    P = [tuple(float(x) for x in s * TET_V[i]) for i in range(4)]
    path = tmp_path / "eksik.stl"
    write_ascii_stl(path, [[P[i] for i in tri] for tri in TET_T[:3]])
    with pytest.raises(GeometryError):
        read_stl(path)


def test_read_stl_missing_file(tmp_path):
    """K8: dosya yok → GeometryError."""
    with pytest.raises(GeometryError):
        read_stl(tmp_path / "yok.stl")
