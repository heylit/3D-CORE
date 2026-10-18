"""SPEC 06 — cam/ops3d.py testleri (K10–K16).

Testler sadece SPEC 06 "Raster ince işleme", "İz yüksekliği", "Katmanlı kaba işleme" ve "Arayüz"
bölümlerinden yazıldı; uygulama kodu okunmadı. Ölçümler bağımsızdır: iz yüksekliği gerçek CL'lerdeki
takım dairelerinin kesitteki zarfından (tests/cam/ref3d.py), çakma ve işleme payı nokta–üçgen
uzaklığından hesaplanır. `drop` yalnızca K13 / K14 / K15'te "o noktadaki z_CL" referansı olarak
kullanılır; kendisi tests/cam/test_dropcutter.py'de bağımsız doğrulanır.

Kaynaklar:
- Sıra kuralı (SPEC 03 face): m = ⌈(y_max − y_min)/s⌉ + 1, eşit aralıklı, ilk ve son sıra kenarda.
- Uyarlamalı bölme: OpenCAMLib AdaptivePathDropCutter (orta nokta sapması > tol → böl).
- İz yüksekliği eğri yüzeyde eğrilik merkezinden radyal ölçülür (SPEC 06 formülü: sırt noktasının
  eksene uzaklığı − ρ); düzlemde radyal = düşey.
- Kaba işleme payı: büyütülmüş takımla (R + δ) drop + δ (Minkowski toplamı).
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from cam.dropcutter import TriMesh, drop
from cam.model import CamError, MoveType, Stock, Tool, ToolKind, Toolpath
from cam.ops2d import depths
from cam.ops3d import Raster, finish, raster_lines, rough
from cam.scallop import scallop_curved, scallop_flat
from tests.cam.ref3d import (
    box_mesh,
    cylinder_strip_mesh,
    flat_tool_distance,
    grid_mesh,
    point_mesh_distance,
    ridge_heights,
    sample_triangles,
)

R = 3.0  # küresel uç yarıçapı
r = 4.0  # düz uç yarıçapı
EPS = 1e-9
FEED = 800.0
PLUNGE = 200.0
RPM = 12000.0


def ball(radius: float = R) -> Tool:
    return Tool(id=1, name="kuresel", kind=ToolKind.BALL, D=2 * radius, flute_length=30.0)


def flat(radius: float = r) -> Tool:
    return Tool(id=2, name="duz", kind=ToolKind.FLAT, D=2 * radius, flute_length=30.0)


TOOLS = [pytest.param(ball, id="kuresel"), pytest.param(flat, id="duz")]


def raster(**kw) -> Raster:
    p = dict(
        xmin=-5.0,
        xmax=5.0,
        ymin=-6.0,
        ymax=6.0,
        stepover=1.5,
        ds=1.0,
        tol=1e-3,
        ds_min=0.01,
        feed=FEED,
        plunge_feed=PLUNGE,
        rpm=RPM,
        z_safe=30.0,
    )
    p.update(kw)
    return Raster(**p)


def mesh_of(V, T) -> TriMesh:
    return TriMesh(V=np.asarray(V, dtype=float), T=np.asarray(T, dtype=int))


def plane(z0: float = 2.0, half: float = 20.0, n: int = 4) -> TriMesh:
    xs = np.linspace(-half, half, n + 1)
    return mesh_of(*grid_mesh(lambda X, Y: np.full_like(X, z0), xs, xs))


def wavy_mesh(A: float = 2.0, lam: float = 4.0, half: float = 12.0, h: float = 0.2) -> TriMesh:
    xs = np.arange(-half, half + h / 2, h)
    return mesh_of(*grid_mesh(lambda X, Y: A * np.sin(X / lam) * np.cos(Y / lam), xs, xs))


# --- Yol ayrıştırma ---------------------------------------------------------------------------------


def segments(tp: Toolpath):
    """(hareket, başlangıç, bitiş) üçlüleri."""
    pts = tp.points()
    return [(m, pts[i], pts[i + 1]) for i, m in enumerate(tp.moves)]


def is_cut(m, rr: Raster) -> bool:
    return m.type is MoveType.LINEAR and m.feed == rr.feed


def is_plunge(m, rr: Raster) -> bool:
    return m.type is MoveType.LINEAR and m.feed == rr.plunge_feed


def cl_points(tp: Toolpath, rr: Raster) -> np.ndarray:
    """Tüm CL'ler: dalma sonları ve kesme hareketi sonları, (k, 3)."""
    return np.array([m.end for m in tp.moves if is_cut(m, rr) or is_plunge(m, rr)])


def section(tp: Toolpath, rr: Raster, x: float) -> np.ndarray:
    """x = sabit kesitteki CL'ler (y, z), y'ye göre sıralı."""
    P = cl_points(tp, rr)
    P = P[np.abs(P[:, 0] - x) < 1e-12]
    return P[np.argsort(P[:, 1])][:, 1:]


def levels_of(tp: Toolpath, rr: Raster) -> list[np.ndarray]:
    """Dalmalara göre seviyelere bölünmüş CL'ler (her seviye: dalma sonu + kesme sonları)."""
    out: list[list] = []
    for m in tp.moves:
        if is_plunge(m, rr):
            out.append([m.end])
        elif is_cut(m, rr):
            out[-1].append(m.end)
    return [np.array(L) for L in out]


def check_motion(tp: Toolpath, rr: Raster, mesh: TriMesh, tool: Tool, exact_approach: bool, n_plunge=None):
    """K15 hareket kuralları."""
    tp.validate()
    assert tp.rpm == rr.rpm
    assert tp.start[2] == pytest.approx(rr.z_safe, abs=EPS)
    assert tp.moves[-1].end[2] == pytest.approx(rr.z_safe, abs=EPS)
    pts = tp.points()
    plunges = []
    for i, m in enumerate(tp.moves):
        assert m.type in (MoveType.RAPID, MoveType.LINEAR), "yay yok"
        if m.type is MoveType.LINEAR:
            assert m.feed in (rr.feed, rr.plunge_feed)
        if is_plunge(m, rr):
            plunges.append(i)
    assert plunges, "en az bir dalma"
    if n_plunge is not None:
        assert len(plunges) == n_plunge
    # ilk dalma yolun başladığı XY'de
    first = tp.moves[plunges[0]].end
    assert tp.start[:2] == pytest.approx(first[:2], abs=EPS)
    for i in plunges:
        p_end = np.array(tp.moves[i].end)
        p_beg = pts[i]  # dalma başı = yaklaşma G0'ının sonu
        assert i > 0 and tp.moves[i - 1].type is MoveType.RAPID
        np.testing.assert_allclose(p_beg[:2], p_end[:2], atol=EPS)  # dikey dalma
        assert p_beg[2] > p_end[2]
        if exact_approach:
            assert p_beg[2] == pytest.approx(p_end[2] + rr.clearance, abs=EPS)
        else:
            assert p_beg[2] >= p_end[2] + rr.clearance - EPS
        # yaklaşma G0'ının başı: aynı XY'de z_safe
        q = pts[i - 1]
        np.testing.assert_allclose(q[:2], p_end[:2], atol=EPS)
        assert q[2] == pytest.approx(rr.z_safe, abs=EPS)
    # G0 hiçbir zaman o noktadaki z_CL'nin altında değil
    t = np.linspace(0, 1, 11)
    for m, a, b in segments(tp):
        if m.type is not MoveType.RAPID:
            continue
        P = a[None, :] + t[:, None] * (b - a)[None, :]
        z_cl = drop(mesh, tool, P[:, :2], floor=-1e3)
        assert np.all(P[:, 2] >= z_cl - EPS)


# --- K10 --------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "lo, hi, s, beklenen",
    [
        (0.0, 10.0, 2.5, [0.0, 2.5, 5.0, 7.5, 10.0]),
        (0.0, 10.0, 3.0, [0.0, 2.5, 5.0, 7.5, 10.0]),  # m = ⌈10/3⌉ + 1 = 5
        (-6.0, 6.0, 1.5, [-6.0 + 1.5 * k for k in range(9)]),
        (2.0, 3.0, 5.0, [2.0, 3.0]),  # s > genişlik: iki kenar sırası
        (0.0, 7.0, 2.0, [0.0, 1.75, 3.5, 5.25, 7.0]),  # m = ⌈3.5⌉ + 1 = 5
    ],
)
@pytest.mark.parametrize("direction", ["x", "y"])
def test_k10_raster_lines(lo, hi, s, beklenen, direction):
    if direction == "x":  # X'e paralel sıralar: sabit y
        rr = raster(ymin=lo, ymax=hi, stepover=s, direction="x")
    else:  # Y'ye paralel sıralar: sabit x
        rr = raster(xmin=lo, xmax=hi, stepover=s, direction="y")
    L = raster_lines(rr)
    m = math.ceil((hi - lo) / s) + 1
    assert len(L) == m
    np.testing.assert_allclose(L, beklenen, atol=1e-12)
    d = np.diff(L)
    assert np.all(d <= s + 1e-12)
    np.testing.assert_allclose(d, d[0], atol=1e-12)  # eşit aralık


# --- K11 --------------------------------------------------------------------------------------------


@pytest.mark.parametrize("make", TOOLS)
def test_k11_duzlemde_her_cl_z0(make):
    z0 = 2.0
    tool = make()
    rr = raster()
    tp = finish(plane(z0), tool, rr)
    P = cl_points(tp, rr)
    np.testing.assert_allclose(P[:, 2], z0, atol=EPS)


def test_k11_duzlemde_iz_yuksekligi():
    """x = 0 kesitinde küre kesitlerinin alt zarfı; sırt = zarf − z₀ en büyüğü = scallop_flat(R, s)."""
    z0 = 2.0
    rr = raster(stepover=1.5)  # 12 / 1.5 = 8: gerçek sıra aralığı tam s
    tp = finish(plane(z0), ball(), rr)
    S = section(tp, rr, 0.0)
    np.testing.assert_allclose(S[:, 0], raster_lines(rr), atol=1e-12)
    yc, zc = S[:, 0], S[:, 1] + R
    ys = np.concatenate([np.linspace(yc[0], yc[-1], 4001), (yc[:-1] + yc[1:]) / 2])
    dy = ys[:, None] - yc[None, :]
    alt = np.where(np.abs(dy) <= R, zc[None, :] - np.sqrt(np.maximum(R * R - dy * dy, 0)), np.inf)
    zarf = alt.min(axis=1)
    sirt = float(np.max(zarf - z0))
    assert sirt == pytest.approx(scallop_flat(R, 1.5), abs=EPS)


# --- K12 --------------------------------------------------------------------------------------------


def k12_case(kind: str):
    """(mesh, rho, z_axis, convex, raster). Ağ kiriş hatası ε ≤ 1e-6 mm."""
    rho = 20.0
    if kind == "silindir":
        V, T, eps = cylinder_strip_mesh(rho, 0.0, -2.0, 2.0, th_max=0.45, eps=1e-6, convex=True)
        assert eps <= 1e-6
        return mesh_of(V, T), rho, 0.0, True, raster(xmin=-1.0, xmax=1.0, ds=1.0, ymin=-6.0, ymax=6.0)
    if kind == "oluk":
        z_axis = 25.0
        V, T, eps = cylinder_strip_mesh(rho, z_axis, -2.0, 2.0, th_max=0.45, eps=1e-6, convex=False)
        assert eps <= 1e-6
        return mesh_of(V, T), rho, z_axis, False, raster(xmin=-1.0, xmax=1.0, ds=1.0, ymin=-4.5, ymax=4.5)
    # küre: x = 0 kesitine yakın ince şerit (merkez orijinde)
    h = 0.008
    xs = np.arange(-9, 10) * h
    ys = np.arange(-800, 801) * h
    V, T = grid_mesh(lambda X, Y: np.sqrt(rho * rho - X * X - Y * Y), xs, ys)
    eps = rho - point_mesh_distance([0.0, 0.0, 0.0], V, T)
    assert 0 < eps <= 1e-6
    return mesh_of(V, T), rho, 0.0, True, raster(xmin=-0.04, xmax=0.04, ds=0.04, ymin=-4.5, ymax=4.5)


@pytest.mark.parametrize("kind", ["silindir", pytest.param("kure", marks=pytest.mark.slow), "oluk"])
def test_k12_egri_yuzeyde_iz(kind):
    mesh, rho, z_axis, convex, rr = k12_case(kind)
    tp = finish(mesh, ball(), rr)
    S = section(tp, rr, 0.0)
    np.testing.assert_allclose(S[:, 0], raster_lines(rr), atol=1e-12)
    centers = np.column_stack([S[:, 0], S[:, 1] + R - z_axis])  # eksene göre (y, z)
    olcum = ridge_heights(centers, R, rho, convex)
    assert len(olcum) == len(S) - 1
    for alpha, h in olcum:
        assert h == pytest.approx(scallop_curved(R, rho, alpha, convex), abs=5e-6), alpha


# --- K13 --------------------------------------------------------------------------------------------


def _k13(tool: Tool, direction: str):
    mesh = wavy_mesh()
    rr = raster(xmin=-8.0, xmax=8.0, ymin=-8.0, ymax=8.0, stepover=2.0, ds=1.0, tol=5e-3, ds_min=1e-3,
                direction=direction)  # fmt: skip
    tp = finish(mesh, tool, rr)
    segs = [(a, b) for m, a, b in segments(tp) if is_cut(m, rr)]
    A = np.array([a for a, _ in segs])
    B = np.array([b for _, b in segs])
    return mesh, rr, A, B


@pytest.mark.parametrize("direction", ["x", "y"])
@pytest.mark.parametrize("make", TOOLS)
def test_k13_orta_nokta_toleransi(make, direction):
    """ds_min'e takılmayan (XY boyu > 2·ds_min) her aralığın ortasında |z_doğru − drop| ≤ tol;
    sıra geçişleri dahil (tüm kesme hareketleri)."""
    tool = make()
    mesh, rr, A, B = _k13(tool, direction)
    L = np.hypot(*(B - A)[:, :2].T)
    assert np.all(L <= rr.ds + 1e-9)
    M = (A + B) / 2
    z = drop(mesh, tool, M[:, :2])
    serbest = L > 2 * rr.ds_min + 1e-12
    assert np.all(np.abs(M[serbest, 2] - z[serbest]) <= rr.tol + EPS)
    # her CL drop üstünde (CL'ler drop-cutter'dan gelir)
    z_uc = drop(mesh, tool, B[:, :2])
    np.testing.assert_allclose(B[:, 2], z_uc, atol=EPS)


@pytest.mark.parametrize("direction", ["x", "y"])
def test_k13_cakma_dogru_boyunca(direction):
    """Küresel uç, ardışık CL'ler arasındaki doğru üzerinde örnek noktalarda z_doğru − drop ≥ −tol."""
    tool = ball()
    mesh, rr, A, B = _k13(tool, direction)
    t = np.linspace(0, 1, 9)[1:-1]
    P = (A[:, None, :] + t[None, :, None] * (B - A)[:, None, :]).reshape(-1, 3)
    z = drop(mesh, tool, P[:, :2])
    assert np.all(P[:, 2] - z >= -rr.tol - EPS)


@pytest.mark.parametrize("direction", ["x", "y"])
def test_k13_siralar_ve_zigzag(direction):
    tool = ball()
    mesh, rr, A, B = _k13(tool, direction)
    lines = raster_lines(rr)
    sabit, akan = (1, 0) if direction == "x" else (0, 1)
    uclar = (rr.xmin, rr.xmax) if direction == "x" else (rr.ymin, rr.ymax)
    # her kesme hareketi ya bir sıra üstünde ya da sıra ucu boyunca geçiştir
    sirada = np.min(np.abs(B[:, sabit][:, None] - np.array(lines)[None, :]), axis=1) < 1e-12
    gecis = np.min(np.abs(B[:, akan][:, None] - np.array(uclar)[None, :]), axis=1) < 1e-12
    assert np.all(sirada | gecis)
    # her sıra uçtan uca kesilir ve yönler sırayla değişir
    yonler = []
    for c in lines:
        on = (np.abs(A[:, sabit] - c) < 1e-12) & (np.abs(B[:, sabit] - c) < 1e-12)
        assert np.any(on)
        a = np.concatenate([A[on, akan], B[on, akan]])
        assert a.min() == pytest.approx(uclar[0], abs=EPS)
        assert a.max() == pytest.approx(uclar[1], abs=EPS)
        yonler.append(np.sign(np.sum(B[on, akan] - A[on, akan])))
    assert all(y1 == -y0 for y0, y1 in zip(yonler, yonler[1:], strict=False))


# --- K14 --------------------------------------------------------------------------------------------

BOX = 20.0  # kutu [0, 20]³
DELTA = 0.5


def _k14(tool: Tool):
    V, T = box_mesh(BOX, BOX, BOX)
    mesh = mesh_of(V, T)
    stock = Stock(-15.0, -15.0, 0.0, 35.0, 35.0, 30.0)
    rr = raster(xmin=-12.0, xmax=32.0, ymin=-12.0, ymax=32.0, stepover=2.0, ds=1.0, tol=0.01, ds_min=0.05,
                z_safe=40.0)  # fmt: skip
    a_p, z_bottom = 4.0, 5.0
    tp = rough(mesh, stock, tool, rr, a_p=a_p, z_bottom=z_bottom, allowance=DELTA)
    return V, T, mesh, stock, rr, a_p, z_bottom, tp


def _big(tool: Tool) -> Tool:
    rad = tool.D / 2 + DELTA
    return ball(rad) if tool.kind is ToolKind.BALL else flat(rad)


def _rect_dist(xy: np.ndarray) -> np.ndarray:
    """XY'de kutu karesine [0, BOX]² uzaklık (içeride 0)."""
    dx = np.maximum(np.maximum(-xy[:, 0], xy[:, 0] - BOX), 0)
    dy = np.maximum(np.maximum(-xy[:, 1], xy[:, 1] - BOX), 0)
    return np.hypot(dx, dy)


@pytest.mark.slow
@pytest.mark.parametrize("make", TOOLS)
def test_k14_seviyeler_ve_cl(make):
    tool = make()
    V, T, mesh, stock, rr, a_p, z_bottom, tp = _k14(tool)
    zs = depths(stock.zmax, z_bottom, a_p)
    L = levels_of(tp, rr)
    assert len(L) == len(zs)
    for P, zi in zip(L, zs, strict=True):
        assert P[:, 2].min() == pytest.approx(zi, abs=EPS)  # parçanın dışında seviyenin kendisi
        z_delta = drop(mesh, _big(tool), P[:, :2], floor=z_bottom - 100.0) + DELTA
        np.testing.assert_allclose(P[:, 2], np.maximum(z_delta, zi), atol=EPS)


@pytest.mark.slow
@pytest.mark.parametrize("make", TOOLS)
def test_k14_kesme_derinligi(make):
    """Aynı XY'de ardışık iki seviyenin CL farkı ≤ a_p (ilk seviye için ham malzeme üstü)."""
    tool = make()
    *_, stock, rr, a_p, z_bottom, tp = _k14(tool)
    L = levels_of(tp, rr)
    onceki = None
    for P in L:
        simdi = {(round(x, 9), round(y, 9)): z for x, y, z in P}
        if onceki is None:
            assert all(stock.zmax - z <= a_p + EPS for z in simdi.values())
        else:
            ortak = simdi.keys() & onceki.keys()
            assert ortak
            assert all(onceki[k] - simdi[k] <= a_p + EPS for k in ortak)
            assert all(onceki[k] - simdi[k] >= -EPS for k in ortak)
        onceki = simdi


@pytest.mark.slow
@pytest.mark.parametrize("make", TOOLS)
def test_k14_isleme_payi(make):
    """Hiçbir CL'de takım parçaya allowance − 1e-9'dan yakın değil."""
    tool = make()
    V, T, mesh, stock, rr, a_p, z_bottom, tp = _k14(tool)
    P = cl_points(tp, rr)
    rad = tool.D / 2
    if tool.kind is ToolKind.BALL:
        yakin = P[_rect_dist(P[:, :2]) <= rad + DELTA + 0.5]
        assert len(yakin)
        for x, y, z in yakin:
            assert point_mesh_distance([x, y, z + R], V, T) >= R + DELTA - EPS
    else:
        S = sample_triangles(V, T, 40)
        yakin = P[_rect_dist(P[:, :2]) <= rad + DELTA + 0.5]
        assert len(yakin)
        for cl in yakin:
            assert flat_tool_distance(S, cl, rad) >= DELTA - EPS


@pytest.mark.slow
@pytest.mark.parametrize("make", TOOLS)
def test_k14_son_seviye(make):
    tool = make()
    *_, rr, a_p, z_bottom, tp = _k14(tool)
    P = levels_of(tp, rr)[-1]
    rad = tool.D / 2
    disari = P[_rect_dist(P[:, :2]) > rad + DELTA + 1e-6]
    assert len(disari)
    np.testing.assert_allclose(disari[:, 2], z_bottom, atol=EPS)
    k = rad + DELTA
    ust = P[(P[:, 0] >= k) & (P[:, 0] <= BOX - k) & (P[:, 1] >= k) & (P[:, 1] <= BOX - k)]
    assert len(ust)
    np.testing.assert_allclose(ust[:, 2], BOX + DELTA, atol=EPS)


# --- K15 --------------------------------------------------------------------------------------------


@pytest.mark.parametrize("direction", ["x", "y"])
@pytest.mark.parametrize("make", TOOLS)
def test_k15_finish_hareket_kurallari(make, direction):
    tool = make()
    mesh = wavy_mesh()
    rr = raster(xmin=-6.0, xmax=6.0, ymin=-6.0, ymax=6.0, stepover=2.0, tol=0.01, z_safe=15.0,
                clearance=2.0, direction=direction)  # fmt: skip
    tp = finish(mesh, tool, rr)
    assert tp.tool == tool
    check_motion(tp, rr, mesh, tool, exact_approach=True, n_plunge=1)


@pytest.mark.slow
@pytest.mark.parametrize("make", TOOLS)
def test_k15_rough_hareket_kurallari(make):
    tool = make()
    V, T, mesh, stock, rr, a_p, z_bottom, tp = _k14(tool)
    check_motion(tp, rr, mesh, tool, exact_approach=False, n_plunge=len(depths(stock.zmax, z_bottom, a_p)))
    # seviyeler arası G0 z_safe'e çıkar (check_motion: her yaklaşmadan önce z_safe)


def test_k15_finish_floor():
    """Ağın dışına taşan alan: floor verilmişse orada CL = floor, yol yine kurallara uyar."""
    tool = ball()
    mesh = plane(2.0, half=4.0, n=2)
    rr = raster(xmin=-10.0, xmax=10.0, ymin=-10.0, ymax=10.0, stepover=2.0, z_safe=10.0)
    with pytest.raises(CamError):
        finish(mesh, tool, rr)
    tp = finish(mesh, tool, rr, floor=-1.0)
    check_motion(tp, rr, mesh, tool, exact_approach=True, n_plunge=1)
    P = cl_points(tp, rr)
    uzak = np.maximum(np.abs(P[:, 0]), np.abs(P[:, 1])) > 4.0 + R + 1e-6
    np.testing.assert_allclose(P[uzak, 2], -1.0, atol=EPS)
    np.testing.assert_allclose(
        P[~uzak, 2], np.maximum(drop(mesh, tool, P[~uzak, :2], floor=-1.0), -1.0), atol=EPS
    )


# --- K16 --------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "kw",
    [
        pytest.param({"xmax": -5.0}, id="xmax=xmin"),
        pytest.param({"xmax": -6.0}, id="xmax<xmin"),
        pytest.param({"ymax": -6.0}, id="ymax=ymin"),
        pytest.param({"stepover": 0.0}, id="stepover=0"),
        pytest.param({"stepover": -1.0}, id="stepover<0"),
        pytest.param({"ds_min": 0.0}, id="ds_min=0"),
        pytest.param({"ds_min": 2.0}, id="ds_min>ds"),
        pytest.param({"tol": 0.0}, id="tol=0"),
        pytest.param({"feed": 0.0}, id="feed=0"),
        pytest.param({"plunge_feed": -1.0}, id="plunge_feed<0"),
        pytest.param({"rpm": 0.0}, id="rpm=0"),
        pytest.param({"clearance": -0.1}, id="clearance<0"),
        pytest.param({"direction": "z"}, id="direction"),
    ],
)
def test_k16_raster_hatali(kw):
    with pytest.raises(CamError):
        raster(**kw)


def test_k16_raster_sinirlar_gecerli():
    raster(ds_min=1.0)  # ds_min = ds
    raster(clearance=0.0)
    raster(direction="y")


@pytest.mark.parametrize("z_safe", [2.5, 1.0])
def test_k16_finish_yetersiz_z_safe(z_safe):
    """Düzlem z₀ = 2: en yüksek CL 2, clearance 1 → z_safe 3'ün altında olamaz."""
    with pytest.raises(CamError):
        finish(plane(2.0), ball(), raster(z_safe=z_safe))


def test_k16_finish_desteklenmeyen_takim():
    torik = Tool(id=4, name="torik", kind=ToolKind.FLAT, D=8.0, flute_length=30.0, corner_r=1.0)
    with pytest.raises(CamError):
        finish(plane(2.0), torik, raster())


@pytest.mark.parametrize(
    "kw",
    [
        pytest.param({"z_bottom": -1.0}, id="z_bottom<zmin"),
        pytest.param({"z_bottom": 30.0}, id="z_bottom=zmax"),
        pytest.param({"z_bottom": 31.0}, id="z_bottom>zmax"),
        pytest.param({"a_p": 0.0}, id="a_p=0"),
        pytest.param({"a_p": -2.0}, id="a_p<0"),
        pytest.param({"allowance": -0.1}, id="allowance<0"),
        pytest.param({"z_safe": 30.0}, id="z_safe=zmax"),
        pytest.param({"z_safe": 20.0}, id="z_safe<zmax"),
    ],
)
def test_k16_rough_hatali(kw):
    mesh = mesh_of(*box_mesh(BOX, BOX, BOX))
    stock = Stock(-15.0, -15.0, 0.0, 35.0, 35.0, 30.0)
    p = {"a_p": 4.0, "z_bottom": 5.0, "allowance": 0.0, "z_safe": 40.0}
    p.update(kw)
    rr = raster(xmin=-12.0, xmax=32.0, ymin=-12.0, ymax=32.0, z_safe=p.pop("z_safe"))
    with pytest.raises(CamError):
        rough(mesh, stock, ball(), rr, **p)
