"""SPEC 06b — genel profilli drop-cutter, torik uç, kaba işleme payı ve torik iz testleri
(K4, K5, K7, K9, K10; konik K6 ve K7'nin konik kısmı arayüz eki sonrası).

Testler sadece SPEC 06b "Drop-cutter (genel profil)", "Ofset", "İz yüksekliği ekleri" ve "Arayüz"
bölümlerinden yazıldı; uygulama kodu okunmadı. Beklenen değerler SPEC "Analitik sonuçlar"
kapalı formlarıdır; çakma / temas ve işleme payı bağımsız hesaplarla (tests/cam/ref3d.py,
tests/cam/ref3d_ek.py: ağ örnekleme + yerel sıklaştırma, takım katısına nokta uzaklığı) ölçülür.

Kaynaklar:
- Köşe radyüslü (bull-nose) takımda eğik düzlem: tüp merkezi düzlemden normal boyunca r_c uzakta,
  eksenden R_t uzakta → z_CL = x·tan β + R_t·tan β + r_c(1/cos β − 1) (OpenCAMLib BullCutter).
- Küre üstünde torik uç: tüp merkezi küre merkezinden ρ_s + r_c uzakta.
- Kesin ofset: takım ⊕ δ küre (Minkowski) → düz uç (R) torik (R + δ, δ) olur.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from cam.cutter import Cutter
from cam.dropcutter import TriMesh, drop
from cam.model import Stock, Tool, ToolKind
from cam.ops3d import finish, rough
from cam.scallop import scallop_torus
from tests.cam.ref3d import box_mesh, grid_mesh, point_mesh_distance, sample_triangles, sphere_cap_mesh
from tests.cam.ref3d_ek import profil, torus_tool_distance
from tests.cam.test_ops3d import cl_points, levels_of, plane, raster, section

EPS = 1e-9
R = 4.0
RC = 1.0
RT = R - RC

# (R, r_c) çiftleri: orta, büyük köşe, küçük köşe
TORI = [
    pytest.param(4.0, 1.0, id="R4-rc1"),
    pytest.param(5.0, 3.5, id="R5-rc3.5"),
    pytest.param(3.0, 0.2, id="R3-rc0.2"),
]


def torik_tool(Rad: float = R, rc: float = RC) -> Tool:
    """Köşe radyüslü düz takım; Cutter.from_tool'un torik profili verdiği de doğrulanır."""
    t = Tool(id=5, name="torik", kind=ToolKind.FLAT, D=2 * Rad, flute_length=40.0, corner_r=rc)
    rho = np.linspace(0.0, Rad, 101)
    np.testing.assert_allclose(Cutter.from_tool(t).f(rho), profil("torik", Rad, rc)(rho), atol=EPS, rtol=0)
    return t


def torik(Rad: float, rc: float, tur: str):
    return torik_tool(Rad, rc) if tur == "tool" else Cutter.torus(Rad, rc)


TUR = [pytest.param("tool", id="Tool"), pytest.param("cutter", id="Cutter")]


def mesh_of(V, T) -> TriMesh:
    return TriMesh(V=np.asarray(V, dtype=float), T=np.asarray(T, dtype=int))


def f_star_torus(Rad: float, rc: float, beta: float) -> float:
    return (Rad - rc) * math.tan(beta) + rc * (1 / math.cos(beta) - 1)


# --- K4 ---------------------------------------------------------------------------------------------


@pytest.mark.parametrize("tur", TUR)
@pytest.mark.parametrize("Rad, rc", TORI)
def test_k4_yatay_duzlem(Rad, rc, tur):
    z0 = 5.0
    xs = np.linspace(-30.0, 30.0, 7)
    m = mesh_of(*grid_mesh(lambda X, Y: np.full_like(X, z0), xs, xs))
    rng = np.random.default_rng(3)
    xy = np.vstack([rng.uniform(-15, 15, (30, 2)), [[0.0, 0.0], [10.0, 0.0], [5.0, 5.0], [3.0, 7.0]]])
    z = drop(m, torik(Rad, rc, tur), xy)
    np.testing.assert_allclose(z, z0, atol=EPS, rtol=0)


@pytest.mark.parametrize("tur", TUR)
@pytest.mark.parametrize("beta_deg", [10.0, 30.0, 60.0])
@pytest.mark.parametrize("Rad, rc", TORI)
def test_k4_egik_duzlem(Rad, rc, beta_deg, tur):
    b = math.radians(beta_deg)
    xs = np.linspace(-30.0, 30.0, 13)
    m = mesh_of(*grid_mesh(lambda X, Y: X * math.tan(b), xs, xs))
    xy = np.random.default_rng(4).uniform(-10, 10, (40, 2))
    z = drop(m, torik(Rad, rc, tur), xy)
    np.testing.assert_allclose(z, xy[:, 0] * math.tan(b) + f_star_torus(Rad, rc, b), atol=EPS, rtol=0)


@pytest.mark.parametrize("tur", TUR)
@pytest.mark.parametrize("Rad, rc", TORI)
def test_k4_tek_kose(Rad, rc, tur):
    """Tepe köşesi üçgenin c'ye en yakın noktası ve en yüksek noktası → z = z_V − f(d)."""
    zV = 7.0
    m = mesh_of([[0.0, 0.0, zV], [-20.0, -5.0, zV - 30.0], [-20.0, 5.0, zV - 30.0]], [[0, 1, 2]])
    f = profil("torik", Rad, rc)
    Rt = Rad - rc
    for d in (0.0, 0.5 * Rt, Rt, Rt + 0.3 * rc, Rt + 0.95 * rc, Rad - 1e-6):
        for phi in (0.0, math.radians(30.0), math.radians(-50.0)):  # tepe köşesinin normal konisi
            xy = np.array([[d * math.cos(phi), d * math.sin(phi)]])
            z = drop(m, torik(Rad, rc, tur), xy)[0]
            assert z == pytest.approx(zV - float(f(d)), abs=EPS), (d, phi)


@pytest.mark.parametrize("tur", TUR)
@pytest.mark.parametrize("Rad, rc", TORI)
def test_k4_yatay_kenar(Rad, rc, tur):
    """Yatay kenar (y = 0, z_e), üçgen y ≤ 0 tarafında ve aşağıda; c = (x, d), d ≥ 0 → z_e − f(d)."""
    ze = 3.0
    m = mesh_of([[-10.0, 0.0, ze], [10.0, 0.0, ze], [0.0, -15.0, ze - 20.0]], [[0, 1, 2]])
    f = profil("torik", Rad, rc)
    Rt = Rad - rc
    for d in (0.0, 0.4 * Rt, Rt + 0.5 * rc, Rt + 0.99 * rc, Rad - 1e-6):
        for x in (-6.0, 0.0, 2.5):
            z = drop(m, torik(Rad, rc, tur), np.array([[x, d]]))[0]
            assert z == pytest.approx(ze - float(f(d)), abs=EPS), (d, x)


@pytest.mark.parametrize("tur", TUR)
@pytest.mark.parametrize("gamma_deg", [20.0, 45.0, 70.0])
@pytest.mark.parametrize("Rad, rc", TORI)
def test_k4_egik_kenar_d0(Rad, rc, gamma_deg, tur):
    """Kenar XZ düzleminde eğik (eğim γ), üçgen y ≤ 0'da aşağı iner; c kenarın üstünde (d = 0)
    → z = z_kenar(c) + f*(tan γ)."""
    g = math.radians(gamma_deg)
    t = math.tan(g)
    m = mesh_of([[-20.0, 0.0, -20.0 * t], [20.0, 0.0, 20.0 * t], [0.0, -25.0, -60.0]], [[0, 1, 2]])
    for x in (-5.0, 0.0, 3.7):
        z = drop(m, torik(Rad, rc, tur), np.array([[x, 0.0]]))[0]
        assert z == pytest.approx(x * t + f_star_torus(Rad, rc, g), abs=EPS), x


# --- K5 ---------------------------------------------------------------------------------------------

RHO_S = 10.0


def sphere_z(rho: float, d: float, Rad: float, rc: float) -> float:
    """Küre (merkez orijin, ρ yarıçap) üstünde torik uç: d ≤ R_t → ρ; değilse tüp temas formülü."""
    Rt = Rad - rc
    if d <= Rt:
        return rho
    return math.sqrt((rho + rc) ** 2 - (d - Rt) ** 2) - rc


@pytest.fixture(scope="module")
def kure_agi():
    V, T = sphere_cap_mesh(RHO_S, math.radians(70.0), n_ring=70, n_seg=360)
    eps = RHO_S - point_mesh_distance([0.0, 0.0, 0.0], V, T)
    assert 0 < eps < 1e-2
    return mesh_of(V, T), eps


@pytest.mark.parametrize(
    "Rad, rc", [pytest.param(4.0, 1.0, id="R4-rc1"), pytest.param(5.0, 3.5, id="R5-rc3.5")]
)
def test_k5_kure_agi(kure_agi, Rad, rc):
    """İç teğet ağ ρ_s − ε ile ρ_s küreleri arasında: z(ρ_s − ε) ≤ z_CL ≤ z(ρ_s)."""
    m, eps = kure_agi
    Rt = Rad - rc
    tool = torik_tool(Rad, rc)
    rng = np.random.default_rng(5)
    for d in (0.0, 0.5 * Rt, Rt - 1e-3, Rt + 0.2 * rc, Rt + 0.6 * rc, Rt + 0.9 * rc):
        phi = rng.uniform(0, 2 * math.pi)
        z = drop(m, tool, np.array([[d * math.cos(phi), d * math.sin(phi)]]))[0]
        assert sphere_z(RHO_S - eps, d, Rad, rc) - EPS <= z <= sphere_z(RHO_S, d, Rad, rc) + EPS, d


# --- K7 ---------------------------------------------------------------------------------------------


def wavy(
    seed: int, A: float = 2.0, lam: float = 4.0, noise: float = 0.05, half: float = 10.0, h: float = 0.5
):
    xs = np.arange(-half, half + h / 2, h)
    X, Y = np.meshgrid(xs, xs, indexing="ij")
    Z = A * np.sin(X / lam) * np.cos(Y / lam) + noise * np.random.default_rng(seed).standard_normal(X.shape)
    return grid_mesh(Z, xs, xs)


def _h(P: np.ndarray, c, f, Rad: float) -> np.ndarray:
    d = np.hypot(P[:, 0] - c[0], P[:, 1] - c[1])
    return np.where(d <= Rad, P[:, 2] - f(np.minimum(d, Rad)), -np.inf)


def ref_contact(V, T, c, f, Rad: float, n: int = 8) -> tuple[float, float]:
    """(örneklerin en büyüğü, sıklaştırılmış en büyük): max_P (P_z − f(d)). Örnekler ağın gerçek
    noktalarıdır (çakma kontrolü); en iyi üçgenlerde ağırlık merkezli koordinatta yakınlaştırma."""
    A, B, C = V[T[:, 0]], V[T[:, 1]], V[T[:, 2]]
    lo = np.minimum.reduce([A[:, :2], B[:, :2], C[:, :2]])
    hi = np.maximum.reduce([A[:, :2], B[:, :2], C[:, :2]])
    yakin = np.all((lo <= np.asarray(c) + Rad) & (hi >= np.asarray(c) - Rad), axis=1)
    Ty = T[yakin]
    S = sample_triangles(V, Ty, n).reshape(len(Ty), -1, 3)
    H = _h(S.reshape(-1, 3), c, f, Rad).reshape(len(Ty), -1)
    ornek = float(H.max())
    best = ornek
    i, j = np.meshgrid(np.arange(n + 1), np.arange(n + 1), indexing="ij")
    ok = (i + j) <= n
    ab = np.column_stack([i[ok] / n, j[ok] / n])
    for k in np.argsort(H.max(axis=1))[-6:]:
        a0, b0 = ab[int(np.argmax(H[k]))]
        Pa, Pb, Pc = V[Ty[k]]
        w = 1.0 / n
        for _ in range(45):
            ga, gb = np.meshgrid(
                np.linspace(a0 - w, a0 + w, 11), np.linspace(b0 - w, b0 + w, 11), indexing="ij"
            )
            ga, gb = ga.ravel(), gb.ravel()
            g = (ga >= 0) & (gb >= 0) & (ga + gb <= 1)
            ga, gb = ga[g], gb[g]
            P = Pa + ga[:, None] * (Pb - Pa) + gb[:, None] * (Pc - Pa)
            hv = _h(P, c, f, Rad)
            q = int(np.argmax(hv))
            if hv[q] > -np.inf:
                a0, b0 = ga[q], gb[q]
                best = max(best, float(hv[q]))
            w *= 0.6
    return ornek, best


@pytest.mark.slow
@pytest.mark.parametrize("seed", [7, 11])
@pytest.mark.parametrize(
    "Rad, rc", [pytest.param(4.0, 1.0, id="R4-rc1"), pytest.param(3.0, 2.2, id="R3-rc2.2")]
)
def test_k7_cakma_yok_temas_var(Rad, rc, seed):
    V, T = wavy(seed)
    m = mesh_of(V, T)
    f = profil("torik", Rad, rc)
    xy = np.random.default_rng(seed + 100).uniform(-5, 5, (25, 2))
    z = drop(m, torik_tool(Rad, rc), xy)
    for c, zc in zip(xy, z, strict=True):
        ornek, best = ref_contact(V, T, c, f, Rad)
        assert ornek <= zc + EPS  # çakma yok (her örnek ağın gerçek noktası)
        assert best <= zc + EPS
        assert best >= zc - 1e-7  # temas var (sıklaştırma çözünürlüğü içinde)


# --- K9 ---------------------------------------------------------------------------------------------

BOX = 20.0
DELTA = 0.5


def _rough_box(tool: Tool):
    V, T = box_mesh(BOX, BOX, BOX)
    mesh = mesh_of(V, T)
    stock = Stock(-15.0, -15.0, 0.0, 35.0, 35.0, 30.0)
    rr = raster(xmin=-12.0, xmax=32.0, ymin=-12.0, ymax=32.0, stepover=2.0, ds=1.0, tol=0.01, ds_min=0.05,
                z_safe=40.0)  # fmt: skip
    tp = rough(mesh, stock, tool, rr, a_p=4.0, z_bottom=5.0, allowance=DELTA)
    return V, T, rr, tp


def _rect_dist(xy: np.ndarray) -> np.ndarray:
    dx = np.maximum(np.maximum(-xy[:, 0], xy[:, 0] - BOX), 0)
    dy = np.maximum(np.maximum(-xy[:, 1], xy[:, 1] - BOX), 0)
    return np.hypot(dx, dy)


ROUGH_TOOLS = [
    pytest.param(lambda: torik_tool(R, RC), RC, id="torik"),
    pytest.param(
        lambda: Tool(id=2, name="duz", kind=ToolKind.FLAT, D=2 * R, flute_length=40.0), 0.0, id="duz"
    ),
]


@pytest.mark.slow
@pytest.mark.parametrize("make, rc", ROUGH_TOOLS)
def test_k9_rough_pay_mesafesi(make, rc):
    """Hiçbir CL'de takım katısı ağa allowance − 1e-9'dan yakın değil."""
    V, T, rr, tp = _rough_box(make())
    P = cl_points(tp, rr)
    yakin = P[_rect_dist(P[:, :2]) <= R + DELTA + 0.5]
    assert len(yakin)
    S = np.vstack([sample_triangles(V, T, 40), V])
    for cl in yakin:
        assert torus_tool_distance(S, cl, R, rc) >= DELTA - EPS, cl


@pytest.mark.slow
@pytest.mark.parametrize("make, rc", ROUGH_TOOLS)
def test_k9_rough_ust_yuzey(make, rc):
    """Son seviyede üst yüzeyin üstündeki her CL tam z_üst + allowance."""
    *_, rr, tp = _rough_box(make())
    P = levels_of(tp, rr)[-1]
    ust = P[(P[:, 0] > 1e-6) & (P[:, 0] < BOX - 1e-6) & (P[:, 1] > 1e-6) & (P[:, 1] < BOX - 1e-6)]
    assert len(ust)
    np.testing.assert_allclose(ust[:, 2], BOX + DELTA, atol=EPS)


@pytest.mark.parametrize("make, rc", ROUGH_TOOLS)
def test_k9_rough_egik_duzlem_kesin_pay(make, rc):
    """z = x·tan β düzleminde kesin ofset: z_δ = drop(ofset(δ)) + δ
    = x tan β + R_t tan β + (r_c + δ)/cos β − r_c; düz uçta takımın düzleme uzaklığı tam δ."""
    tool = make()
    b = math.radians(30.0)
    xs = np.linspace(-20.0, 20.0, 9)
    mesh = mesh_of(*grid_mesh(lambda X, Y: X * math.tan(b), xs, xs))
    rr = raster(xmin=-8.0, xmax=8.0, ymin=-8.0, ymax=8.0, stepover=2.0, ds=1.0, tol=0.01, ds_min=0.05,
                z_safe=40.0)  # fmt: skip
    kesin = Cutter.from_tool(tool).offset(DELTA)
    stock = Stock(-20.0, -20.0, -15.0, 20.0, 20.0, 15.0)
    tp = rough(mesh, stock, tool, rr, a_p=30.0, z_bottom=-14.0, allowance=DELTA)
    P = levels_of(tp, rr)[-1]
    assert np.all(P[:, 2] > -14.0 + 1.0)  # seviye tabanı hiç devreye girmez
    beklenen = P[:, 0] * math.tan(b) + (R - rc) * math.tan(b) + (rc + DELTA) / math.cos(b) - rc
    np.testing.assert_allclose(P[:, 2], beklenen, atol=EPS, rtol=0)
    np.testing.assert_allclose(P[:, 2], drop(mesh, kesin, P[:, :2]) + DELTA, atol=EPS, rtol=0)
    if rc == 0.0:
        # düz uç: alt kenar köşesinin düzleme dik uzaklığı tam δ
        gap = (P[:, 2] - (P[:, 0] + R) * math.tan(b)) * math.cos(b)
        np.testing.assert_allclose(gap, DELTA, atol=EPS)


# --- K10 --------------------------------------------------------------------------------------------

R10, RC10 = 4.0, 1.5  # R_t = 2.5, 2R_t = 5


@pytest.mark.parametrize("s", [pytest.param(6.0, id="s>2Rt"), pytest.param(4.0, id="s<=2Rt")])
def test_k10_finish_torik_iz(s):
    """x = 0 kesitinde torik profillerin alt zarfı; sırt = scallop_torus(R, r_c, s)."""
    h_bek = scallop_torus(R10, RC10, s)
    Rt = R10 - RC10
    kapali = 0.0 if s <= 2 * Rt else RC10 - math.sqrt(RC10**2 - (s / 2 - Rt) ** 2)
    assert h_bek == pytest.approx(kapali, abs=EPS)
    z0 = 2.0
    rr = raster(stepover=s)  # y ∈ [−6, 6]: 12 / s tam sayı → sıra aralığı tam s
    tp = finish(plane(z0), torik_tool(R10, RC10), rr)
    S = section(tp, rr, 0.0)
    yc, zc = S[:, 0], S[:, 1]
    assert np.all(np.abs(np.diff(yc) - s) < 1e-12)
    f = profil("torik", R10, RC10)
    ys = np.concatenate([np.linspace(yc[0], yc[-1], 4001), (yc[:-1] + yc[1:]) / 2])
    dy = np.abs(ys[:, None] - yc[None, :])
    zarf = np.min(np.where(dy <= R10, zc[None, :] + f(np.minimum(dy, R10)), np.inf), axis=1)
    assert float(np.max(zarf - z0)) == pytest.approx(h_bek, abs=EPS)


# --- K6 ---------------------------------------------------------------------------------------------

RK, THK = 4.0, 30.0  # konik: R, yarı açı θ [derece]; tam uç açısı 60°


def konik_tool(Rad: float = RK, th: float = THK) -> Tool:
    t = Tool(id=6, name="konik", kind=ToolKind.CONE, D=2 * Rad, flute_length=40.0, tip_angle=2 * th)
    rho = np.linspace(0.0, Rad, 101)
    np.testing.assert_allclose(
        Cutter.from_tool(t).f(rho), profil("konik", Rad, theta=th)(rho), atol=EPS, rtol=0
    )
    return t


def konik(tur: str, Rad: float = RK, th: float = THK):
    return konik_tool(Rad, th) if tur == "tool" else Cutter.cone(Rad, th)


@pytest.mark.parametrize("tur", TUR)
@pytest.mark.parametrize(
    "beta_deg", [pytest.param(b, id=f"beta{b:g}") for b in (10.0, 45.0, 59.0, 60.0, 61.0, 75.0)]
)
def test_k6_egik_duzlem_iki_dal(beta_deg, tur):
    """β ≤ 90° − θ: uç değer (z_CL = düzlem); β > 90° − θ: kenar değer R(tan β − cot θ)."""
    b = math.radians(beta_deg)
    xs = np.linspace(-40.0, 40.0, 17)
    m = mesh_of(*grid_mesh(lambda X, Y: X * math.tan(b), xs, xs))
    xy = np.random.default_rng(6).uniform(-10, 10, (30, 2))
    cot = 1 / math.tan(math.radians(THK))
    ek = 0.0 if math.tan(b) <= cot else RK * (math.tan(b) - cot)
    z = drop(m, konik(tur), xy)
    np.testing.assert_allclose(z, xy[:, 0] * math.tan(b) + ek, atol=EPS, rtol=0)


@pytest.mark.parametrize("tur", TUR)
def test_k6_tek_kose(tur):
    zV = 7.0
    m = mesh_of([[0.0, 0.0, zV], [-20.0, -5.0, zV - 30.0], [-20.0, 5.0, zV - 30.0]], [[0, 1, 2]])
    f = profil("konik", RK, theta=THK)
    for d in (0.0, 1.0, 2.5, RK - 1e-6):
        for phi in (0.0, math.radians(30.0), math.radians(-50.0)):
            z = drop(m, konik(tur), np.array([[d * math.cos(phi), d * math.sin(phi)]]))[0]
            assert z == pytest.approx(zV - float(f(d)), abs=EPS), (d, phi)


def cone_sphere_z(rho: float, d: float, Rad: float = RK, th_deg: float = THK) -> float:
    """ρ yarıçaplı küre (merkez orijin) üstünde konik uç: teğet noktası koninin [uç, kenar]
    parçasındaysa (ρ − d cos θ)/sin θ; değilse uç √(ρ² − d²) veya kenar √(ρ² − (d − R)²) − h_c."""
    th = math.radians(th_deg)
    t = d - rho * math.cos(th)  # teğet noktasının eksene uzaklığı
    if t < 0:
        return math.sqrt(rho * rho - d * d)
    if t > Rad:
        return math.sqrt(rho * rho - (d - Rad) ** 2) - Rad / math.tan(th)
    return (rho - d * math.cos(th)) / math.sin(th)


@pytest.mark.parametrize("tur", TUR)
def test_k6_kure_agi(kure_agi, tur):
    m, eps = kure_agi
    rng = np.random.default_rng(8)
    for d in (2.0, 7.0, 9.0, 10.5, 12.0, 13.0):  # uç, uç, teğet, teğet, teğet, kenar
        phi = rng.uniform(0, 2 * math.pi)
        z = drop(m, konik(tur), np.array([[d * math.cos(phi), d * math.sin(phi)]]))[0]
        assert cone_sphere_z(RHO_S - eps, d) - EPS <= z <= cone_sphere_z(RHO_S, d) + EPS, d


@pytest.mark.slow
@pytest.mark.parametrize("seed", [7, 11])
def test_k7_konik_cakma_yok_temas_var(seed):
    V, T = wavy(seed)
    m = mesh_of(V, T)
    f = profil("konik", RK, theta=THK)
    xy = np.random.default_rng(seed + 200).uniform(-5, 5, (25, 2))
    z = drop(m, konik_tool(), xy)
    for c, zc in zip(xy, z, strict=True):
        ornek, best = ref_contact(V, T, c, f, RK)
        assert ornek <= zc + EPS
        assert best <= zc + EPS
        assert best >= zc - 1e-7
