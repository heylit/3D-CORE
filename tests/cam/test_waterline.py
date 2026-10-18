"""SPEC 06b — cam/waterline.py testleri (K12–K15, K17, K18; K16 SPEC sorusu yanıtlanınca).

Testler sadece SPEC 06b "Waterline (sabit Z kontur)" ve "Arayüz" bölümlerinden yazıldı; uygulama
kodu okunmadı. Beklenen konturlar analitiktir: dik duvarlı prizmada {c : dist(c, Q) = R}, yarıkürede
takım türüne göre kapalı form yarıçap; lif aralığı uçları dikdörtgen prizmada kapalı formdan
(tests/cam/ref3d_ek.py). Dalgalı ağda sınır doğruluğu, döngü noktalarının iki yanında `drop`
(SPEC 06 / 06b, tests/cam/test_dropcutter*.py'de bağımsız doğrulanır) ile sınanır.

Kaynaklar:
- Waterline / push-cutter, lif (fiber) ve örgü (weave): OpenCAMLib Waterline ve AdaptiveWaterline;
  Anderson, "Detecting and eliminating collisions in NC machining" (1978) — sabit Z kontur.
- Dik duvarlı prizmada sabit Z'de girişim: takımın en geniş yeri (f(R) yüksekliği) duvara R'den
  yakınsa çakar → kontur Q'nun R ofseti (köşelerde R yarıçaplı yay).
- Yarıküre: küresel uç merkezi küre merkezinden ρ_s + R uzakta; torik uç tüp merkezi ρ_s + r_c;
  düz uç kenar dairesi z yüksekliğinde küre üstünde; konik uç meridyen doğrusu küreye teğet.
"""

from __future__ import annotations

import math

import numpy as np
import pytest
from scipy.optimize import brentq

from cam.cutter import Cutter
from cam.dropcutter import TriMesh, drop
from cam.model import CamError, MoveType, Tool, ToolKind
from cam.scallop import scallop_flat
from cam.waterline import Waterline, waterline, waterline_loops
from tests.cam.ref3d import grid_mesh, point_mesh_distance, sample_triangles, sphere_cap_mesh
from tests.cam.ref3d_ek import dist_to_segments, prism_mesh, profil, segments_of, signed_area

EPS = 1e-9
RAD = 2.0
RC = 0.7
SF = 0.5  # lif aralığı
TOL_WL = 1e-3
DS_MIN = 1e-2
Z_A, Z_B = 0.0, 10.0
ANCHOR = (-1.123, -1.377, -40.0)  # sınır kutusunu genel konuma kaydırır (lif duvara teğet düşmesin)


def ball(R: float = RAD) -> Tool:
    return Tool(id=1, name="kuresel", kind=ToolKind.BALL, D=2 * R, flute_length=30.0)


def flat(R: float = RAD) -> Tool:
    return Tool(id=2, name="duz", kind=ToolKind.FLAT, D=2 * R, flute_length=30.0)


def torus(R: float = RAD, rc: float = RC) -> Tool:
    return Tool(id=3, name="torik", kind=ToolKind.FLAT, D=2 * R, flute_length=30.0, corner_r=rc)


TOOLS = [pytest.param(flat, id="duz"), pytest.param(ball, id="kuresel"), pytest.param(torus, id="torik")]


def ref_f(tool: Tool):
    if tool.kind is ToolKind.BALL:
        return profil("kure", tool.D / 2)
    return profil("torik", tool.D / 2, tool.corner_r)


def mesh_of(V, T) -> TriMesh:
    return TriMesh(V=np.asarray(V, dtype=float), T=np.asarray(T, dtype=int))


def fan(k: int, offset: int = 0) -> list[tuple[int, int, int]]:
    return [(offset, offset + i, offset + i + 1) for i in range(1, k - 1)]


def loops_of(mesh, tool, z, climb=True, fiber_step=SF, tol=TOL_WL, ds_min=DS_MIN):
    L = waterline_loops(mesh, tool, z, fiber_step, tol, ds_min, climb=climb)
    assert isinstance(L, list)
    for loop in L:
        assert loop.ndim == 2 and loop.shape[1] == 2 and len(loop) >= 3
        assert np.linalg.norm(loop[0] - loop[-1]) > 1e-12  # kapanış noktası tekrar edilmez
    return L


def check_order(loops: list[np.ndarray]) -> None:
    """Her döngü en küçük x'li (eşitlikte en küçük y'li) noktasından başlar; döngüler başlangıç
    noktalarının (x, y) sözlük sırasında."""
    for L in loops:
        k = np.lexsort((L[:, 1], L[:, 0]))[0]
        assert k == 0
    starts = [tuple(L[0]) for L in loops]
    assert starts == sorted(starts)


CONVEX = np.array([[0.0, 0.0], [9.0, -1.0], [11.0, 5.0], [5.0, 9.0], [-1.0, 6.0]])
L_SHAPE = np.array([[0.0, 0.0], [10.0, 0.0], [10.0, 4.0], [4.0, 4.0], [4.0, 9.0], [0.0, 9.0]])


def poly_mesh(Q: np.ndarray) -> TriMesh:
    assert signed_area(Q) > 0
    return mesh_of(*prism_mesh([Q], fan(len(Q)), Z_A, Z_B, anchor=ANCHOR))


def rect(x0, x1, y0, y1) -> np.ndarray:
    return np.array([[x0, y0], [x1, y0], [x1, y1], [x0, y1]], dtype=float)


# --- K12 --------------------------------------------------------------------------------------------


@pytest.mark.parametrize("Q", [pytest.param(CONVEX, id="disbukey"), pytest.param(L_SHAPE, id="L-icbukey")])
@pytest.mark.parametrize("make", TOOLS)
@pytest.mark.parametrize("z", [3.0, 6.5])
def test_k12_prizma_ofset_konturu(make, Q, z):
    tool = make()
    loops = loops_of(poly_mesh(Q), tool, z)
    assert len(loops) == 1
    A, B = segments_of([Q])
    d = dist_to_segments(loops[0], A, B)
    assert np.all(np.abs(d - RAD) <= EPS), float(np.max(np.abs(d - RAD)))
    assert signed_area(loops[0]) < 0  # tırmanma: dış sınır CW
    check_order(loops)


@pytest.mark.parametrize("Q", [pytest.param(CONVEX, id="disbukey"), pytest.param(L_SHAPE, id="L-icbukey")])
@pytest.mark.parametrize("make", TOOLS)
def test_k12_geleneksel_yon(make, Q):
    mesh = poly_mesh(Q)
    tirmanma = loops_of(mesh, make(), 3.0, climb=True)
    geleneksel = loops_of(mesh, make(), 3.0, climb=False)
    assert len(geleneksel) == 1
    assert signed_area(geleneksel[0]) > 0  # CCW
    A, B = segments_of([Q])
    assert np.all(np.abs(dist_to_segments(geleneksel[0], A, B) - RAD) <= EPS)
    # aynı nokta kümesi, ters yön
    assert len(geleneksel[0]) == len(tirmanma[0])
    check_order(geleneksel)


@pytest.mark.parametrize("make", TOOLS)
def test_k12_uyarlamali_bolme_yayda(make):
    """Köşe yaylarında ardışık iki nokta arasındaki kiriş sapması ≤ tol (ds_min'e takılmayanlar)."""
    Q = rect(0.0, 12.0, 0.0, 7.66)
    loop = loops_of(mesh_of(*prism_mesh([Q], fan(4), Z_A, Z_B, anchor=ANCHOR)), make(), 3.0)[0]
    nxt = np.roll(loop, -1, axis=0)
    L = np.linalg.norm(nxt - loop, axis=1)
    M = (loop + nxt) / 2
    A, B = segments_of([Q])
    serbest = L / 2 >= DS_MIN
    sapma = np.abs(dist_to_segments(M[serbest], A, B) - RAD)
    assert np.all(sapma <= TOL_WL + EPS)


# --- K13 --------------------------------------------------------------------------------------------


def fibers(lo: float, hi: float, R: float, s: float) -> np.ndarray:
    """SPEC 06b lif ızgarası: sınır kutusu R + s büyütülür, x_i = x_min + i·s."""
    start = lo - R - s
    n = math.floor((hi + R + s - start) / s + 1e-9)
    return start + s * np.arange(n + 1)


def rect_interval_ends(Qs, R: float, xs: np.ndarray, ys: np.ndarray) -> np.ndarray:
    """Dikdörtgen prizmalar için her lif aralığının uçları (kapalı form): X lifi y'de, Q'ya y-uzaklığı
    dy < R ise aralık (x0 − w, x1 + w), w = √(R² − dy²); Y lifleri simetrik."""
    out = []
    for x0, x1, y0, y1 in Qs:
        for y in ys:
            dy = max(y0 - y, 0.0, y - y1)
            if dy < R:
                w = math.sqrt(R * R - dy * dy)
                out += [(x0 - w, y), (x1 + w, y)]
        for x in xs:
            dx = max(x0 - x, 0.0, x - x1)
            if dx < R:
                w = math.sqrt(R * R - dx * dx)
                out += [(x, y0 - w), (x, y1 + w)]
    return np.array(out)


def check_interval_ends(loops, mesh: TriMesh, Qs) -> None:
    lo, hi = mesh.bbox()
    xs = fibers(lo[0], hi[0], RAD, SF)
    ys = fibers(lo[1], hi[1], RAD, SF)
    E = rect_interval_ends(Qs, RAD, xs, ys)
    assert len(E) > 20
    P = np.vstack(loops)
    for e in E:
        n = int(np.sum(np.linalg.norm(P - e, axis=1) < 1e-8))
        assert n == 1, (e, n)


RECT_A = (0.0, 12.0, 0.0, 7.66)


@pytest.mark.parametrize("make", TOOLS)
def test_k13_tek_dikdortgen_lif_uclari(make):
    mesh = mesh_of(*prism_mesh([rect(*RECT_A)], fan(4), Z_A, Z_B, anchor=ANCHOR))
    loops = loops_of(mesh, make(), 3.0)
    assert len(loops) == 1
    check_interval_ends(loops, mesh, [RECT_A])


@pytest.mark.parametrize("make", TOOLS)
def test_k13_iki_ayrik_cikinti(make):
    Qa = (0.0, 6.0, 0.0, 5.0)
    Qb = (12.3, 18.3, 0.4, 6.1)  # boşluk 6.3 > 2R + 2s_f = 5
    mesh = mesh_of(*prism_mesh([rect(*Qa), rect(*Qb)], fan(4) + fan(4, 4), Z_A, Z_B, anchor=ANCHOR))
    loops = loops_of(mesh, make(), 3.0)
    assert len(loops) == 2
    check_order(loops)
    for L, Q in zip(loops, (Qa, Qb), strict=True):  # başlangıç x'e göre sıralı: önce Qa
        assert signed_area(L) < 0
        A, B = segments_of([rect(*Q)])
        assert np.all(np.abs(dist_to_segments(L, A, B) - RAD) <= EPS)
    check_interval_ends(loops, mesh, [Qa, Qb])


def hollow_mesh() -> tuple[TriMesh, np.ndarray, np.ndarray]:
    dis = rect(0.0, 14.0, 0.0, 12.0)
    ic = rect(4.0, 10.0, 3.0, 9.0)  # iç teğet çember yarıçapı 3 > R
    top = []
    for k in range(4):
        k1 = (k + 1) % 4
        top += [(k, k1, 4 + k1), (k, 4 + k1, 4 + k)]
    return mesh_of(*prism_mesh([dis, ic], top, Z_A, Z_B, anchor=ANCHOR)), dis, ic


@pytest.mark.parametrize("make", TOOLS)
@pytest.mark.parametrize("climb", [True, False], ids=["tirmanma", "geleneksel"])
def test_k13_ici_bos_prizma(make, climb):
    mesh, dis, ic = hollow_mesh()
    loops = loops_of(mesh, make(), 3.0, climb=climb)
    assert len(loops) == 2
    check_order(loops)
    alan = [abs(signed_area(L)) for L in loops]
    o, i = (loops[0], loops[1]) if alan[0] > alan[1] else (loops[1], loops[0])
    A, B = segments_of([dis, ic])
    for L in loops:
        assert np.all(np.abs(dist_to_segments(L, A, B) - RAD) <= EPS)
    # iç döngü: deliğin R kadar içeri ofseti (köşeleri keskin dikdörtgen [6, 8] × [5, 7])
    assert np.all(
        (i[:, 0] >= 6.0 - EPS) & (i[:, 0] <= 8.0 + EPS) & (i[:, 1] >= 5.0 - EPS) & (i[:, 1] <= 7.0 + EPS)
    )
    assert abs(signed_area(i)) == pytest.approx(4.0, abs=0.05)  # köşeler kirişle kesilebilir
    if climb:
        assert signed_area(o) < 0 and signed_area(i) > 0  # dış CW, iç CCW
    else:
        assert signed_area(o) > 0 and signed_area(i) < 0


@pytest.mark.parametrize("make", TOOLS)
def test_k13_girisim_yok(make):
    mesh = poly_mesh(CONVEX)
    assert loops_of(mesh, make(), Z_B + 0.5) == []
    assert loops_of(mesh, make(), Z_B) == []  # z_CL ≤ z_b: I(z_b) boş


# --- K14 --------------------------------------------------------------------------------------------

RHO_S = 10.0
CONE_R, CONE_TH = 4.0, 45.0


def r_contour(kind: str, rho: float, z: float) -> float:
    if kind == "kuresel":
        return math.sqrt((rho + RAD) ** 2 - (z + RAD) ** 2)
    if kind == "torik":
        return (RAD - RC) + math.sqrt((rho + RC) ** 2 - (z + RC) ** 2)
    if kind == "duz":
        return math.sqrt(rho * rho - z * z) + RAD
    th = math.radians(CONE_TH)
    return (rho - z * math.sin(th)) / math.cos(th)


@pytest.fixture(scope="module")
def yarikure():
    V, T = sphere_cap_mesh(RHO_S, math.pi / 2, n_ring=45, n_seg=180)
    eps = RHO_S - point_mesh_distance([0.0, 0.0, 0.0], V, T)
    assert 0 < eps < 2e-2
    return mesh_of(V, T), eps


@pytest.mark.slow
@pytest.mark.parametrize(
    "kind, make, zs",
    [
        pytest.param("duz", flat, (1.0, 4.0, 7.0), id="duz"),
        pytest.param("kuresel", ball, (1.0, 4.0, 7.0), id="kuresel"),
        pytest.param("torik", torus, (1.0, 4.0, 7.0), id="torik"),
        pytest.param("konik", lambda: Cutter.cone(CONE_R, CONE_TH), (4.0, 6.0), id="konik"),
    ],
)
def test_k14_yarikure(yarikure, kind, make, zs):
    """İç teğet ağ ρ_s − ε ile ρ_s arasında: r(ρ_s − ε) ≤ |c| ≤ r(ρ_s)."""
    mesh, eps = yarikure
    if kind == "konik":
        th = math.radians(CONE_TH)
        for z in zs:  # teğet noktası koninin [uç, kenar] parçasında
            assert 0 <= math.tan(th) * (RHO_S * math.sin(th) - z) <= CONE_R
    for z in zs:
        loops = loops_of(mesh, make(), z)
        assert len(loops) == 1
        r = np.hypot(loops[0][:, 0], loops[0][:, 1])
        assert np.all(r >= r_contour(kind, RHO_S - eps, z) - EPS), z
        assert np.all(r <= r_contour(kind, RHO_S, z) + EPS), z
        assert signed_area(loops[0]) < 0


# --- K15 --------------------------------------------------------------------------------------------


def wavy_mesh(seed: int = 13, half: float = 8.0, h: float = 0.5) -> TriMesh:
    xs = np.arange(-half, half + h / 2, h)
    X, Y = np.meshgrid(xs, xs, indexing="ij")
    Z = 2.0 * np.sin(X / 3) * np.cos(Y / 3) + 0.05 * np.random.default_rng(seed).standard_normal(X.shape)
    return mesh_of(*grid_mesh(Z, xs, xs))


@pytest.mark.slow
@pytest.mark.parametrize("climb", [True, False], ids=["tirmanma", "geleneksel"])
@pytest.mark.parametrize("make", TOOLS)
def test_k15_sinir_dogrulugu(make, climb):
    tool = make()
    mesh = wavy_mesh()
    z = 0.5
    tol, ds_min = 2e-3, 1e-3
    loops = loops_of(mesh, tool, z, climb=climb, fiber_step=0.4, tol=tol, ds_min=ds_min)
    assert loops
    check_order(loops)
    eta = 1e-7

    def z_cl(P):
        return drop(mesh, tool, P, floor=-1e3)

    for L in loops:
        t = np.roll(L, -1, axis=0) - np.roll(L, 1, axis=0)
        n = np.column_stack([-t[:, 1], t[:, 0]]) / np.linalg.norm(t, axis=1)[:, None]  # sol normal
        if not climb:
            n = -n  # I(z) hareketin solunda → dışarı bakan normal sağda
        assert np.all(z_cl(L + eta * n) <= z), "dış taraf girişimsiz olmalı"
        assert np.all(z_cl(L - eta * n) > z), "iç taraf girişim bölgesinde olmalı"
        # parça orta noktaları: sınır, dik doğrultuda tol içinde
        nxt = np.roll(L, -1, axis=0)
        seg = nxt - L
        Ls = np.linalg.norm(seg, axis=1)
        k = Ls / 2 >= ds_min
        M = ((L + nxt) / 2)[k]
        nm = np.column_stack([-seg[k, 1], seg[k, 0]]) / Ls[k, None]
        if not climb:
            nm = -nm
        ic = z_cl(M) > z
        w = tol * (1 + 1e-6) + EPS
        if np.any(ic):
            assert np.all(z_cl(M[ic] + w * nm[ic]) <= z)
        if np.any(~ic):
            assert np.all(z_cl(M[~ic] - w * nm[~ic]) > z)


# --- K16 --------------------------------------------------------------------------------------------
# Onaylı ek (kullanıcı, 2026-10-18 11:13): tam dik duvarda takımın silindir gövdesi sırtı sıfırlar; iz
# neredeyse dik (α = 75°) duvarda ölçülür. Ardışık seviyelerin profil kesitleri düzleme paralel bir
# doğru üzerinde L = Δz / sin α aralıklı → küresel scallop_flat(R, L), torik scallop_flat(r_c, L).

ALFA = math.radians(75.0)
H_DUVAR = 10.0


def steep_wall_mesh() -> TriMesh:
    """x ≤ 0'da z = H plato, x ≥ 0'da z = H − x·tan α eğik duvar (y ∈ [−10, 10])."""
    x1 = (H_DUVAR + 20.0) / math.tan(ALFA)
    xs = np.concatenate([np.linspace(-10.0, 0.0, 11), np.linspace(0.0, x1, 21)[1:]])
    ys = np.linspace(-10.0, 10.0, 21)
    return mesh_of(*grid_mesh(lambda X, Y: np.where(X <= 0, H_DUVAR, H_DUVAR - X * math.tan(ALFA)), xs, ys))


def wall_profile(x_k: float, z_k: float, f, R: float) -> tuple[np.ndarray, np.ndarray]:
    """Eksen kesitinde takımın duvar (−x) tarafındaki alt yüzeyi + silindir gövdesi, düzlem
    koordinatlarında (s: düzlem boyunca aşağı, n: düzleme dik yukarı), s'ye göre artan."""
    rho = np.linspace(0.0, R, 200001)
    h = np.linspace(0.0, 3 * R, 2001)[1:]
    x = np.concatenate([x_k - rho, np.full_like(h, x_k - R)])
    z = np.concatenate([z_k + f(rho), z_k + float(f(R)) + h])
    dx, dz = x, z - H_DUVAR
    s = dx * math.cos(ALFA) - dz * math.sin(ALFA)
    n = dx * math.sin(ALFA) + dz * math.cos(ALFA)
    return s[::-1], n[::-1]


@pytest.mark.parametrize(
    "make, r_iz",
    [pytest.param(ball, RAD, id="kuresel"), pytest.param(torus, RC, id="torik")],
)
def test_k16_dike_yakin_duvarda_iz(make, r_iz):
    tool = make()
    f = ref_f(tool)
    dz = 0.3
    zs = [4.0 - k * dz for k in range(5)]
    m = math.tan(ALFA)
    Rt = tool.D / 2 - tool.corner_r
    f_star = Rt * math.tan(ALFA) + tool.corner_r * (1 / math.cos(ALFA) - 1)
    mesh = steep_wall_mesh()
    egriler = []
    for z in zs:
        loops = loops_of(mesh, tool, z)
        P = np.vstack(loops)
        P = P[(np.abs(P[:, 1]) < 4.0) & (P[:, 0] > 0.0)]
        assert len(P) >= 2
        x_k = (H_DUVAR + f_star - z) / m  # eğik düzlemde z_CL = z_düzlem + f*(tan α)
        np.testing.assert_allclose(P[:, 0], x_k, atol=EPS)
        assert x_k - RAD > 0.5  # temas eğik yüzde, plato takımın altında değil
        egriler.append(wall_profile(float(P[:, 0].mean()), z, f, RAD))
    temas = [float(s[int(np.argmin(n))]) for s, n in egriler]  # her seviyenin düzleme değdiği s
    L = dz / math.sin(ALFA)
    beklenen = scallop_flat(r_iz, L)
    for k in range(len(egriler) - 1):
        (s0, n0), (s1, n1) = egriler[k], egriler[k + 1]
        a, c = sorted((temas[k], temas[k + 1]))
        assert c - a == pytest.approx(L, abs=1e-6)

        def fark(t, s0=s0, n0=n0, s1=s1, n1=n1):
            return float(np.interp(t, s0, n0) - np.interp(t, s1, n1))

        s_r = brentq(fark, a, c, xtol=1e-14)  # komşu iki profilin kesiştiği sırt
        sirt = float(np.interp(s_r, s0, n0))
        diger = [float(np.interp(s_r, s, n, left=np.inf, right=np.inf)) for s, n in egriler]
        assert min(diger) == pytest.approx(sirt, abs=1e-12)  # sırt zarfın üstünde
        assert sirt == pytest.approx(beklenen, abs=1e-6)


# --- K17 --------------------------------------------------------------------------------------------

FEED, PLUNGE, RPM = 800.0, 200.0, 12000.0


def wl(**kw) -> Waterline:
    p = dict(z_levels=[6.0, 4.5, 3.0], fiber_step=SF, tol=TOL_WL, ds_min=DS_MIN, feed=FEED,
             plunge_feed=PLUNGE, rpm=RPM, z_safe=15.0, clearance=1.0)  # fmt: skip
    p.update(kw)
    return Waterline(**p)


def rect_mesh() -> tuple[TriMesh, np.ndarray, np.ndarray]:
    V, T = prism_mesh([rect(*RECT_A)], fan(4), Z_A, Z_B, anchor=ANCHOR)
    return mesh_of(V, T), V, T


@pytest.mark.parametrize("climb", [True, False], ids=["tirmanma", "geleneksel"])
@pytest.mark.parametrize("make", [pytest.param(flat, id="duz"), pytest.param(torus, id="torik")])
def test_k17_waterline_yolu(make, climb):
    tool = make()
    mesh, V, T = rect_mesh()
    w = wl(climb=climb)
    tp = waterline(mesh, tool, w)
    tp.validate()
    assert tp.tool == tool
    assert tp.rpm == RPM
    assert tp.start[2] == pytest.approx(w.z_safe, abs=EPS)
    assert tp.moves[-1].end[2] == pytest.approx(w.z_safe, abs=EPS)
    f = ref_f(tool)
    S = np.vstack([sample_triangles(V, T, 20), V])
    i = 0
    mv = tp.moves
    for z in w.z_levels:
        loops = waterline_loops(mesh, tool, z, w.fiber_step, w.tol, w.ds_min, climb=w.climb)
        assert loops
        for L in loops:
            xs, ys = L[0]
            assert mv[i].type is MoveType.RAPID
            np.testing.assert_allclose(mv[i].end, (xs, ys, w.z_safe), atol=EPS)
            assert mv[i + 1].type is MoveType.RAPID
            np.testing.assert_allclose(mv[i + 1].end, (xs, ys, z + w.clearance), atol=EPS)
            assert mv[i + 2].type is MoveType.LINEAR and mv[i + 2].feed == PLUNGE
            np.testing.assert_allclose(mv[i + 2].end, (xs, ys, z), atol=EPS)
            i += 3
            hedef = np.vstack([L[1:], L[:1]])
            for p in hedef:
                assert mv[i].type is MoveType.LINEAR and mv[i].feed == FEED
                np.testing.assert_allclose(mv[i].end, (p[0], p[1], z), atol=EPS)
                i += 1
            assert mv[i].type is MoveType.RAPID
            np.testing.assert_allclose(mv[i].end, (xs, ys, w.z_safe), atol=EPS)
            i += 1
            # dalma noktasında takım ağa girmez (sınırdaki teğet temas serbest)
            d = np.hypot(S[:, 0] - xs, S[:, 1] - ys)
            icte = d < tool.D / 2 - 1e-7
            assert np.all(S[icte, 2] <= z + f(d[icte]) + EPS)
    assert i == len(mv)


def test_k17_seviyeler_azalan_sirada():
    tool = flat()
    mesh, *_ = rect_mesh()
    tp = waterline(mesh, tool, wl())
    zs = [m.end[2] for m in tp.moves if m.type is MoveType.LINEAR and m.feed == PLUNGE]
    assert zs == sorted(zs, reverse=True)
    assert sorted(set(zs), reverse=True) == [6.0, 4.5, 3.0]


# --- K18 --------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "kw",
    [
        pytest.param({"z_levels": []}, id="z_levels-bos"),
        pytest.param({"z_levels": [3.0, 4.5]}, id="z_levels-artan"),
        pytest.param({"z_levels": [6.0, 4.5, 4.5]}, id="z_levels-esit"),
        pytest.param({"z_levels": [6.0, math.nan]}, id="z_levels-nan"),
        pytest.param({"fiber_step": 0.0}, id="fiber_step=0"),
        pytest.param({"fiber_step": -0.5}, id="fiber_step<0"),
        pytest.param({"tol": 0.0}, id="tol=0"),
        pytest.param({"ds_min": 0.0}, id="ds_min=0"),
        pytest.param({"ds_min": -1.0}, id="ds_min<0"),
        pytest.param({"feed": 0.0}, id="feed=0"),
        pytest.param({"plunge_feed": -1.0}, id="plunge_feed<0"),
        pytest.param({"rpm": 0.0}, id="rpm=0"),
        pytest.param({"clearance": -0.1}, id="clearance<0"),
        pytest.param({"z_safe": math.inf}, id="z_safe-inf"),
        pytest.param({"feed": math.nan}, id="feed-nan"),
    ],
)
def test_k18_waterline_hatali(kw):
    with pytest.raises(CamError):
        wl(**kw)


def test_k18_waterline_sinirlar_gecerli():
    wl(clearance=0.0)
    wl(z_levels=[3.0])


@pytest.mark.parametrize("z_safe", [10.5, 5.0])
def test_k18_yetersiz_z_safe(z_safe):
    """Ağın en yükseği 10, clearance 1 → z_safe 11'in altında olamaz."""
    mesh, *_ = rect_mesh()
    with pytest.raises(CamError):
        waterline(mesh, flat(), wl(z_safe=z_safe))


def test_k18_matkap():
    mesh, *_ = rect_mesh()
    drill = Tool(id=9, name="matkap", kind=ToolKind.DRILL, D=6.0, flute_length=30.0)
    with pytest.raises(CamError):
        waterline(mesh, drill, wl())
    with pytest.raises(CamError):
        waterline_loops(mesh, drill, 3.0, SF, TOL_WL, DS_MIN)


@pytest.mark.parametrize(
    "fiber_step, tol, ds_min",
    [
        (0.0, TOL_WL, DS_MIN),
        (-0.1, TOL_WL, DS_MIN),
        (SF, 0.0, DS_MIN),
        (SF, -1e-3, DS_MIN),
        (SF, TOL_WL, 0.0),
    ],
)
def test_k18_loops_hatali(fiber_step, tol, ds_min):
    mesh, *_ = rect_mesh()
    with pytest.raises(CamError):
        waterline_loops(mesh, flat(), 3.0, fiber_step, tol, ds_min)
