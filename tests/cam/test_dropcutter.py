"""SPEC 06 — cam/dropcutter.py testleri (K1–K8, K17).

Testler sadece SPEC 06 "Teori" ve "Arayüz" bölümlerinden yazıldı; uygulama kodu okunmadı.
Beklenen değerler kapalı formdur (SPEC 06 "Analitik sonuçlar") veya tests/cam/ref3d.py'deki
bağımsız hesaplardır (nokta–üçgen uzaklığı, disk altındaki en yüksek nokta, kaba kuvvet örnekleme).

Kaynaklar:
- Drop-cutter: Yau, Chuang, Lee (2004), "Efficient NC simulation for multi-axis solid machining
  with a universal APT cutter"; OpenCAMLib BatchDropCutter (köşe / yüz / kenar testleri).
- Eğik düzlem β: küre merkezi düzlemden normal boyunca R uzakta → z_CL = x·tan β + R(1/cos β − 1);
  düz disk yokuş yukarı kenarından değer → z_CL = x·tan β + r·tan β.
- Dışbükey küre / silindir: merkez eksenden ρ + R uzakta → z_CL = √((ρ+R)² − d²) − R.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from cam.dropcutter import NZ_TOL, TOL, TriMesh, drop, drop_one
from cam.model import CamError, Tool, ToolKind
from tests.cam.ref3d import (
    brute_drop,
    cylinder_strip_mesh,
    disc_max_height,
    grid_height,
    grid_mesh,
    point_mesh_distance,
    sample_triangles,
    sphere_cap_mesh,
)

R = 3.0  # küresel uç yarıçapı
r = 4.0  # düz uç yarıçapı
EPS = 1e-9


def ball(radius: float = R) -> Tool:
    return Tool(id=1, name="kuresel", kind=ToolKind.BALL, D=2 * radius, flute_length=30.0)


def flat(radius: float = r) -> Tool:
    return Tool(id=2, name="duz", kind=ToolKind.FLAT, D=2 * radius, flute_length=30.0)


TOOLS = [pytest.param(ball, id="kuresel"), pytest.param(flat, id="duz")]


def mesh_of(V, T) -> TriMesh:
    return TriMesh(V=np.asarray(V, dtype=float), T=np.asarray(T, dtype=int))


def plane_mesh(z0: float = 5.0, half: float = 30.0, n: int = 6):
    xs = np.linspace(-half, half, n + 1)
    return grid_mesh(lambda X, Y: np.full_like(X, z0), xs, xs)


def wavy(
    seed: int = 7, A: float = 2.0, lam: float = 4.0, noise: float = 0.05, half: float = 10.0, h: float = 0.5
):
    """z = A sin(x/λ) cos(y/λ) + gürültü ızgarası: tepeler (dışbükey) ve çukurlar (içbükey) bir arada."""
    xs = np.arange(-half, half + h / 2, h)
    X, Y = np.meshgrid(xs, xs, indexing="ij")
    Z = A * np.sin(X / lam) * np.cos(Y / lam) + noise * np.random.default_rng(seed).standard_normal(X.shape)
    V, T = grid_mesh(Z, xs, xs)
    return V, T, xs, Z


# --- K1 ---------------------------------------------------------------------------------------------


def test_k1_sabitler():
    assert TOL == 1e-9
    assert NZ_TOL == 1e-12


def test_k1_trimesh_gecerli_ve_bbox():
    V = [[0, 0, 0], [2, 0, 1], [0, 3, -1], [2, 3, 4]]
    m = mesh_of(V, [[0, 1, 2], [1, 3, 2]])
    lo, hi = m.bbox()
    np.testing.assert_allclose(lo, [0, 0, -1])
    np.testing.assert_allclose(hi, [2, 3, 4])


@pytest.mark.parametrize(
    "V, T",
    [
        pytest.param([[0, 0, np.nan], [1, 0, 0], [0, 1, 0]], [[0, 1, 2]], id="nan"),
        pytest.param([[0, 0, np.inf], [1, 0, 0], [0, 1, 0]], [[0, 1, 2]], id="inf"),
        pytest.param([[0, 0, 0], [1, 0, 0], [0, 1, 0]], [[0, 1, 3]], id="indeks-buyuk"),
        pytest.param([[0, 0, 0], [1, 0, 0], [0, 1, 0]], [[0, 1, -1]], id="indeks-negatif"),
        pytest.param([[0, 0, 0], [1, 0, 0], [2, 0, 0]], [[0, 1, 2]], id="dogrusal"),
        pytest.param([[0, 0, 0], [1, 0, 0], [0, 1, 0]], [[0, 1, 1]], id="tekrarli-kose"),
        pytest.param(np.zeros((0, 3)), np.zeros((0, 3), dtype=int), id="bos"),
        pytest.param([[0, 0, 0], [1, 0, 0], [0, 1, 0]], np.zeros((0, 3), dtype=int), id="ucgensiz"),
    ],
)
def test_k1_trimesh_hatali(V, T):
    with pytest.raises(CamError):
        mesh_of(V, T)


@pytest.mark.parametrize(
    "tool",
    [
        pytest.param(Tool(id=3, name="matkap", kind=ToolKind.DRILL, D=6.0, flute_length=30.0), id="matkap"),
        pytest.param(
            Tool(id=4, name="torik", kind=ToolKind.FLAT, D=8.0, flute_length=30.0, corner_r=1.0), id="torik"
        ),
    ],
)
def test_k1_desteklenmeyen_takim(tool):
    m = mesh_of(*plane_mesh())
    with pytest.raises(CamError):
        drop(m, tool, np.array([[0.0, 0.0]]))
    with pytest.raises(CamError):
        drop_one(m, tool, 0.0, 0.0)


# --- K2 ---------------------------------------------------------------------------------------------


@pytest.mark.parametrize("make", TOOLS)
def test_k2_yatay_duzlem(make):
    z0 = 5.0
    m = mesh_of(*plane_mesh(z0, half=30.0, n=6))  # köşeler 10 mm aralıklı
    rng = np.random.default_rng(1)
    xy = np.vstack(
        [
            rng.uniform(-15, 15, (40, 2)),
            [[0.0, 0.0], [10.0, -10.0]],  # ağ köşesi
            [[5.0, 0.0], [0.0, 5.0], [3.0, 3.0]],  # kenar (yatay, dikey, köşegen)
            [[6.0, 2.0], [2.0, 6.0]],  # yüz içi
        ]
    )
    z = drop(m, make(), xy)
    assert z.shape == (len(xy),)
    np.testing.assert_allclose(z, z0, atol=EPS, rtol=0)
    for x, y in xy[:5]:
        assert drop_one(m, make(), float(x), float(y)) == pytest.approx(z0, abs=EPS)


# --- K3 ---------------------------------------------------------------------------------------------


@pytest.mark.parametrize("beta_deg", [10.0, 30.0, 60.0])
@pytest.mark.parametrize("make", TOOLS)
def test_k3_egik_duzlem(make, beta_deg):
    tb = math.tan(math.radians(beta_deg))
    xs = np.linspace(-40, 40, 9)
    m = mesh_of(*grid_mesh(lambda X, Y: X * tb, xs, xs))
    rng = np.random.default_rng(2)
    xy = np.vstack([rng.uniform(-12, 12, (30, 2)), [[0.0, 0.0], [10.0, 5.0], [-10.0, -10.0]]])
    tool = make()
    z = drop(m, tool, xy)
    if tool.kind is ToolKind.BALL:
        beklenen = xy[:, 0] * tb + R * (1 / math.cos(math.radians(beta_deg)) - 1)
    else:
        beklenen = xy[:, 0] * tb + r * tb
    np.testing.assert_allclose(z, beklenen, atol=EPS, rtol=0)


# --- K4 ---------------------------------------------------------------------------------------------
# Tek üçgenler, sorgu noktaları üçgenin "arka" tarafında: üçgen tepedeki köşeden / kenardan dik
# biçimde aşağı ve uzağa iner, bu yüzden temas o köşe ya da kenardadır.


def spike():
    """Köşe V = (0, 0, 0); diğer köşeler (100, 0, −1000), (0, 100, −1000). Sorgu: x < 0, y < 0."""
    return mesh_of([[0, 0, 0], [100, 0, -1000], [0, 100, -1000]], [[0, 1, 2]])


@pytest.mark.parametrize("make", TOOLS)
def test_k4_tek_kose(make):
    tool = make()
    rad = tool.D / 2
    m = spike()
    for d in (0.0, 0.3 * rad, 0.7 * rad, 0.99 * rad):
        for ang in (200.0, 225.0, 250.0):
            x, y = d * math.cos(math.radians(ang)), d * math.sin(math.radians(ang))
            z = drop_one(m, tool, x, y)
            beklenen = math.sqrt(rad * rad - d * d) - rad if tool.kind is ToolKind.BALL else 0.0
            assert z == pytest.approx(beklenen, abs=EPS), (d, ang)


@pytest.mark.parametrize("make", TOOLS)
def test_k4_temas_yok(make):
    """d > R (d > r): disk üçgenle örtüşmez → floor döner, floor yoksa CamError."""
    tool = make()
    rad = tool.D / 2
    m = spike()
    for d in (1.01 * rad, 2 * rad):
        x = y = -d / math.sqrt(2)
        assert drop_one(m, tool, x, y, floor=-50.0) == pytest.approx(-50.0, abs=EPS)
        with pytest.raises(CamError):
            drop_one(m, tool, x, y)


@pytest.mark.parametrize("make", TOOLS)
def test_k4_yatay_kenar(make):
    """Kenar y = 0, z = z_e = 2, x ∈ [−50, 50]; üçgen y > 0'a dik iner. Sorgu y < 0."""
    z_e = 2.0
    m = mesh_of([[-50, 0, z_e], [50, 0, z_e], [0, 100, -1000]], [[0, 1, 2]])
    tool = make()
    rad = tool.D / 2
    for d in (0.0, 0.25 * rad, 0.6 * rad, 0.95 * rad):
        for x in (-10.0, 0.0, 7.5):
            z = drop_one(m, tool, x, -d)
            beklenen = z_e + math.sqrt(rad * rad - d * d) - rad if tool.kind is ToolKind.BALL else z_e
            assert z == pytest.approx(beklenen, abs=EPS), (d, x)
    # d > R: temas yok
    assert drop_one(m, tool, 0.0, -1.05 * rad, floor=-99.0) == pytest.approx(-99.0, abs=EPS)


@pytest.mark.parametrize("make", TOOLS)
def test_k4_egik_kenar(make):
    """Kenar y = 0, z = k·x (k = 0.1), x ∈ [−50, 50]; üçgen y > 0'a dik iner. Sorgu y < 0.
    Küresel: merkezin doğruya uzaklığı² = y² + (z_C − k x)²/(1 + k²) = R² →
    z_C = k x + √((1 + k²)(R² − y²)), z_CL = z_C − R.
    Düz: disk kenarın x ∈ [x − √(r² − y²), x + √(r² − y²)] aralığını örter, en yüksek uç z = k·x_üst."""
    k = 0.1
    m = mesh_of([[-50, 0, -50 * k], [50, 0, 50 * k], [0, 100, -1000]], [[0, 1, 2]])
    tool = make()
    rad = tool.D / 2
    for d in (0.0, 0.4 * rad, 0.9 * rad):
        for x in (-8.0, 0.0, 12.0):
            z = drop_one(m, tool, x, -d)
            if tool.kind is ToolKind.BALL:
                beklenen = k * x + math.sqrt((1 + k * k) * (rad * rad - d * d)) - rad
            else:
                beklenen = k * (x + math.sqrt(rad * rad - d * d))
            assert z == pytest.approx(beklenen, abs=EPS), (d, x)


# --- K5 ---------------------------------------------------------------------------------------------


@pytest.mark.parametrize("make", TOOLS)
def test_k5_floor(make):
    z0 = 5.0
    m = mesh_of(*plane_mesh(z0, half=10.0, n=2))
    tool = make()
    rad = tool.D / 2
    disari = np.array([[10.0 + rad + 1.0, 0.0], [-30.0, -30.0]])
    np.testing.assert_allclose(drop(m, tool, disari, floor=-7.0), -7.0, atol=EPS)
    with pytest.raises(CamError):
        drop(m, tool, disari)
    with pytest.raises(CamError):
        drop(m, tool, np.vstack([[0.0, 0.0], disari]))  # bir nokta bile temassızsa
    ic = np.array([[0.0, 0.0], [3.0, -4.0]])
    np.testing.assert_allclose(drop(m, tool, ic, floor=z0 + 3.0), z0 + 3.0, atol=EPS)  # floor üstte
    np.testing.assert_allclose(drop(m, tool, ic, floor=z0 - 3.0), z0, atol=EPS)  # floor altta
    karisik = drop(m, tool, np.vstack([ic, disari]), floor=0.0)
    np.testing.assert_allclose(karisik, [z0, z0, 0.0, 0.0], atol=EPS)


# --- K6 ---------------------------------------------------------------------------------------------


def test_k6_kure():
    rho = 10.0
    V, T = sphere_cap_mesh(rho, theta_max=1.2, n_ring=60, n_seg=240)
    eps = rho - point_mesh_distance([0, 0, 0], V, T)  # ağın kiriş hatası
    assert 0 < eps < 2e-3
    m = mesh_of(V, T)
    c = rho + R
    rng = np.random.default_rng(3)
    ang = rng.uniform(0, 2 * np.pi, 40)
    d = 0.5 * c * np.sqrt(rng.uniform(0, 1, 40))
    xy = np.column_stack([d * np.cos(ang), d * np.sin(ang)])
    z = drop(m, ball(), xy)
    zc = np.sqrt(c * c - d * d)
    beklenen = zc - R
    # ağ küreye içten çizili: merkez yarıçapı [c − ε, c] → düşey fark ≤ ε·c/z_C
    assert np.all(z <= beklenen + EPS)
    assert np.all(z >= beklenen - 1.01 * eps * c / zc - EPS)


def test_k6_silindir():
    rho = 12.0
    V, T, eps = cylinder_strip_mesh(rho, z_axis=0.0, x0=-30.0, x1=30.0, th_max=1.0, eps=1e-4, convex=True)
    m = mesh_of(V, T)
    c = rho + R
    rng = np.random.default_rng(4)
    xy = np.column_stack([rng.uniform(-10, 10, 40), rng.uniform(-0.5 * c, 0.5 * c, 40)])
    z = drop(m, ball(), xy)
    zc = np.sqrt(c * c - xy[:, 1] ** 2)
    beklenen = zc - R
    assert np.all(z <= beklenen + EPS)
    assert np.all(z >= beklenen - 1.01 * eps * c / zc - EPS)


# --- K7 ---------------------------------------------------------------------------------------------


@pytest.mark.parametrize("seed", [7, 11])
def test_k7_kuresel_cakma_yok_temas_var(seed):
    V, T, *_ = wavy(seed)
    m = mesh_of(V, T)
    xy = np.random.default_rng(seed + 100).uniform(-5, 5, (40, 2))
    z = drop(m, ball(), xy)
    for (x, y), zi in zip(xy, z, strict=True):
        dist = point_mesh_distance([x, y, zi + R], V, T)
        assert dist == pytest.approx(R, abs=EPS), (x, y)


@pytest.mark.parametrize("seed", [7, 11])
def test_k7_duz_cakma_yok_temas_var(seed):
    V, T, xs, Z = wavy(seed)
    m = mesh_of(V, T)
    rng = np.random.default_rng(seed + 200)
    xy = rng.uniform(-5, 5, (40, 2))
    z = drop(m, flat(), xy)
    for (x, y), zi in zip(xy, z, strict=True):
        # tam: disk altındaki en yüksek nokta (dikey uzaklık = 0)
        assert zi - disc_max_height(V, T, x, y, r) == pytest.approx(0.0, abs=EPS), (x, y)
        # örnekleme: disk hiçbir örnekte ağın altına girmez
        rr = r * np.sqrt(rng.uniform(0, 1, 4000))
        ph = rng.uniform(0, 2 * np.pi, 4000)
        hz = grid_height(xs, xs, Z, x + rr * np.cos(ph), y + rr * np.sin(ph))
        assert zi - np.nanmax(hz) >= -EPS


# --- K8 ---------------------------------------------------------------------------------------------


@pytest.mark.parametrize("make", TOOLS)
def test_k8_kaba_kuvvet(make):
    """Kaba kuvvet her örnekte gerçek bir alt sınırdır (≤ drop); sıklaştırma sonrası örnekleme hatası
    < 1e-4 mm (ref3d.brute_drop)."""
    V, T, xs, Z = wavy(5)
    m = mesh_of(V, T)
    tool = make()
    rad = tool.D / 2
    xy = np.random.default_rng(55).uniform(-5, 5, (12, 2))
    z = drop(m, tool, xy)

    def height(x, y):
        return grid_height(xs, xs, Z, x, y)

    for (x, y), zi in zip(xy, z, strict=True):
        b = brute_drop(height, V, T, x, y, rad, ball=tool.kind is ToolKind.BALL)
        assert b <= zi + EPS, (x, y)
        assert zi - b < 1e-4, (x, y)


def test_k8_dik_ucgenler_kenar_ile():
    """Dik duvarlı basamak: dik üçgenler yüz testine girmez, kenar/köşe testleri teması yakalar."""
    from tests.cam.ref3d import box_mesh

    V, T = box_mesh(10.0, 10.0, 4.0)
    m = mesh_of(V, T)
    pts = sample_triangles(V, T, 40)
    for x in (-2.0, -0.5, 0.0, 0.5, 11.0, 12.5):
        y = 5.0
        zb = drop_one(m, ball(), x, y, floor=-100.0)
        zf = drop_one(m, flat(), x, y, floor=-100.0)
        # düz: disk altındaki en yüksek nokta
        assert zf == pytest.approx(disc_max_height(V, T, x, y, r), abs=EPS)
        # küresel: temas varsa merkez ağa tam R uzakta; yoksa floor
        if zb > -100.0 + 1.0:
            assert point_mesh_distance([x, y, zb + R], V, T) == pytest.approx(R, abs=EPS)
        else:
            assert np.min(np.hypot(pts[:, 0] - x, pts[:, 1] - y)) > R - 1e-6


# --- K17 --------------------------------------------------------------------------------------------


@pytest.mark.occt
@pytest.mark.parametrize("make", TOOLS)
def test_k17_from_part(make):
    from geometry.features import block, cylinder

    tool = make()
    rad = tool.D / 2
    blok = TriMesh.from_part(block(30.0, 20.0, 5.0))
    assert drop_one(blok, tool, 15.0, 10.0) == pytest.approx(5.0, abs=EPS)
    assert drop_one(blok, tool, 30.0 + rad + 2.0, 10.0, floor=-1.0) == pytest.approx(-1.0, abs=EPS)
    sil = TriMesh.from_part(cylinder(10.0, 8.0), tol=0.01)
    lo, hi = sil.bbox()
    assert hi[2] == pytest.approx(8.0, abs=1e-6)
    assert drop_one(sil, tool, 0.0, 0.0) == pytest.approx(8.0, abs=EPS)
    assert drop_one(sil, tool, 10.0 + rad + 1.0, 0.0, floor=-1.0) == pytest.approx(-1.0, abs=EPS)
    with pytest.raises(CamError):
        drop_one(sil, tool, 10.0 + rad + 1.0, 0.0)
