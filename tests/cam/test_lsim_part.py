"""SPEC 22 K15, K16 — parça haritası (profile_rmap, mesh_rmap, part_rmap), çakma, kalan malzeme.

Testler SPEC 22 "Parça haritası" ve "Çarpışma ve çakma denetimleri" bölümlerinden yazıldı;
cam.sim kodu okunmadı.

Kaynaklar (SPEC 22):
- profile_rmap: (u, v) = (z, x) düzleminde kapalı bölge; z = z_i doğrusunun sınırla kesişimleri sıralanır,
  çift–tek kuralıyla içte kalan aralıklar; teğet dokunma / köşeden geçişte boyu 0 aralık yazılmaz.
- cakma: adımın kaldırdığı parçalar parça aralıklarıyla gouge_tol'dan (1e-3) uzun çakışırsa; kayıt hücreyi
  ilk kez çakan adıma ait; depth = çakışmanın en uzun parçası.
- V_kalan = Σ π(u² − l²)·dz (malzeme − parça); çakma hacmi = parçanın (stok içinde) malzemede olmayan kısmı.
- Doğrusal hareketin malzeme sonucu: tests/cam/lsimref.py `cut_map` (kesin süpürme, alt adımdan bağımsız).
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from cam.lathe import tip_offset
from cam.lathe_ops import TurnCut, finish, rough
from cam.model import CylinderStock
from cam.profile import Arc, Line, Profile, Region
from cam.sim import RadialMap, mesh_rmap, profile_rmap, simulate_lathe
from tests.cam.lsimref import G0, G1, cut_map, iv_is_valid, lpath, turn_core, turn_tool

STOK = CylinderStock(D=40.0, zmin=-50.0, zmax=0.0)
R_N = 0.8


def _P(*a: float) -> np.ndarray:
    return np.array(a, dtype=float)


def _grid(cell: float = 0.5) -> RadialMap:
    return RadialMap.from_stock(STOK, cell)


def _mil() -> Region:
    """Basamaklı mil: z ∈ [−20, 0] x ≤ 10, z ∈ [−50, −20] x ≤ 15."""
    return Region(Profile.polygon([(0, 0), (0, 10), (-20, 10), (-20, 15), (-50, 15), (-50, 0)]))


def _esit(got, beklenen, tol=1e-9) -> None:
    assert len(got) == len(beklenen), f"{got} ≠ {beklenen}"
    for (a, b), (c, d) in zip(got, beklenen, strict=True):
        assert a == pytest.approx(c, abs=tol) and b == pytest.approx(d, abs=tol), f"{got} ≠ {beklenen}"


# ------------------------------------------------------------------ K15 profile_rmap


def test_K15_basamakli_mil():
    g = _grid()
    pm = profile_rmap(_mil(), g)
    assert (pm.z0, pm.dz, pm.nz) == (g.z0, g.dz, g.nz)
    for i, z in enumerate(g.centers()):
        _esit(pm.intervals(i), [(0.0, 10.0)] if z > -20 else [(0.0, 15.0)])
    V = math.pi * (100 * 20 + 225 * 30)
    assert pm.volume() == pytest.approx(V, rel=1e-12)


def test_K15_profil_de_kabul_edilir():
    """Kapalı Profile, Region gibi."""
    g = _grid()
    prof = Profile.polygon([(0, 0), (0, 10), (-20, 10), (-20, 15), (-50, 15), (-50, 0)])
    pm = profile_rmap(prof, g)
    for i, z in enumerate(g.centers()):
        _esit(pm.intervals(i), [(0.0, 10.0)] if z > -20 else [(0.0, 15.0)])


def test_K15_delikli_burc():
    """Dış halka z ∈ [−30, 0], x ∈ [8, 18]; delik basamağı z < −15'te x ≥ 10."""
    g = _grid()
    burc = Region(Profile.polygon([(0, 8), (0, 18), (-30, 18), (-30, 10), (-15, 10), (-15, 8)]))
    pm = profile_rmap(burc, g)
    for i, z in enumerate(g.centers()):
        if z > -15:
            _esit(pm.intervals(i), [(8.0, 18.0)])
        elif z > -30:
            _esit(pm.intervals(i), [(10.0, 18.0)])
        else:
            assert pm.intervals(i) == []


def test_K15_ada_iki_aralik():
    """Bölge + ada (çift–tek): ada hücrelerinde [0, 5] ∪ [9, 18]."""
    g = _grid()
    reg = Region(Profile.rectangle(-30.0, 0.0, 30.0, 18.0), [Profile.rectangle(-20.0, 5.0, 10.0, 4.0)])
    pm = profile_rmap(reg, g)
    for i, z in enumerate(g.centers()):
        if -20 < z < -10:
            _esit(pm.intervals(i), [(0.0, 5.0), (9.0, 18.0)])
        elif z > -30:
            _esit(pm.intervals(i), [(0.0, 18.0)])


def test_K15_yay():
    """Yarım daire bölge, merkez (−10, 0), R = 8: |z + 10| < 8 → [0, √(64 − (z + 10)²)]."""
    g = _grid()
    yarim = Region(Profile([Line(_P(-18, 0), _P(-2, 0)), Arc(_P(-2, 0), _P(-18, 0), _P(-10, 0), True)]))
    pm = profile_rmap(yarim, g)
    for i, z in enumerate(g.centers()):
        d = z + 10.0
        if abs(d) < 8.0:
            _esit(pm.intervals(i), [(0.0, math.sqrt(64.0 - d * d))])
        else:
            assert pm.intervals(i) == []


def test_K15_kose_ve_teget_gecis():
    """Hücre merkezi z = −10.25 köşelerden geçer → tek aralık; teğet dokunma ve tek köşe → aralık yok."""
    g = _grid()
    zc = g.centers()
    i = int(np.argmin(np.abs(zc + 10.25)))
    assert zc[i] == pytest.approx(-10.25, abs=1e-12)
    # eşkenar dörtgen: üst ve alt köşe z = −10.25 doğrusunda
    elmas = Region(Profile.polygon([(-20.0, 5.0), (-10.25, 10.0), (-0.5, 5.0), (-10.25, 0.0)]))
    pm = profile_rmap(elmas, g)
    _esit(pm.intervals(i), [(0.0, 10.0)])
    for j in range(g.nz):
        assert iv_is_valid(pm.intervals(j))
    # daire z = −10.25 doğrusuna teğet (merkez (−7.25, 5), R = 3)
    daire = Region(Profile.circle((-7.25, 5.0), 3.0))
    pd = profile_rmap(daire, g)
    assert pd.intervals(i) == []
    for j in range(g.nz):
        assert iv_is_valid(pd.intervals(j))
    # üçgenin tek köşesi doğruya değiyor
    ucgen = Region(Profile.polygon([(-12.0, 2.0), (-10.25, 6.0), (-12.0, 8.0)]))
    pu = profile_rmap(ucgen, g)
    assert pu.intervals(i) == []
    assert pu.intervals(i - 1) != []  # z = −10.75 kesiyor


def _silindir_agi(R: float, z0: float, z1: float, r_ic: float = 0.0, n: int = 64):
    """n kenarlı prizma ağı; köşeler (k + ½)·2π/n açılarında (y = 0 düzlemi kenar ortalarından geçer).
    r_ic > 0 → boru (iç yüzey + halka kapaklar), aksi dolu (merkezli yelpaze kapaklar)."""
    th = (np.arange(n) + 0.5) * 2 * np.pi / n
    halka = lambda rr, z: np.column_stack([rr * np.cos(th), rr * np.sin(th), np.full(n, z)])  # noqa: E731
    V = [halka(R, z0), halka(R, z1)]  # 0..n−1 alt dış, n..2n−1 üst dış
    T = []
    for k in range(n):
        j = (k + 1) % n
        T += [[k, j, n + j], [k, n + j, n + k]]
    if r_ic > 0:
        V += [halka(r_ic, z0), halka(r_ic, z1)]  # 2n.. alt iç, 3n.. üst iç
        for k in range(n):
            j = (k + 1) % n
            T += [[2 * n + k, 3 * n + j, 2 * n + j], [2 * n + k, 3 * n + k, 3 * n + j]]  # iç yüzey
            T += [[k, 2 * n + j, j], [k, 2 * n + k, 2 * n + j]]  # alt halka
            T += [[n + k, n + j, 3 * n + j], [n + k, 3 * n + j, 3 * n + k]]  # üst halka
    else:
        V += [np.array([[0.0, 0.0, z0], [0.0, 0.0, z1]])]
        c0, c1 = 2 * n, 2 * n + 1
        for k in range(n):
            j = (k + 1) % n
            T += [[c0, j, k], [c1, n + k, n + j]]
    return np.vstack(V), np.array(T)


@pytest.mark.parametrize("r_ic", [0.0, 5.0], ids=["dolu", "boru"])
def test_K15_mesh_rmap_prizma(r_ic):
    """y = 0 düzlemi kenar ortalarından geçer: kesit yarıçapı R·cos(π/n) (ve iç r·cos(π/n))."""
    n, R = 64, 10.0
    V, T = _silindir_agi(R, -20.0, 0.0, r_ic, n)
    g = _grid()
    pm = mesh_rmap(V, T, g)
    c = math.cos(math.pi / n)
    for i, z in enumerate(g.centers()):
        if z > -20:
            _esit(pm.intervals(i), [(r_ic * c, R * c)])
        else:
            assert pm.intervals(i) == []


# ------------------------------------------------------------------ K15 çakma


def _bitmis_pay(pay: float) -> RadialMap:
    """Parçanın pay kadar şişirilmişi (yarı bitmiş iş): z > −20 [0, 10 + pay], aksi [0, 15 + pay]."""
    g = _grid()
    m = RadialMap.empty_like(g)
    for i, z in enumerate(g.centers()):
        m.add(i, 0.0, (10.0 if z > -20 else 15.0) + pay)
    return m


def _paso(x_alt: float):
    """Burun alt ucu x_alt'ta z: 5 → −10 boyuna G1 (P_z = −10 → C_z = −9.2), sonra radyal G0 çıkış."""
    return lpath(
        turn_tool(R_N), (25.0, 5.0), [G0(x_alt, 5.0), G1(x_alt, -10.0), G0(25.0, -10.0), G0(25.0, 5.0)]
    )


def test_K15_cakma_kaydi():
    """0.2 mm parçaya giren G1 → cakma, depth = 0.2, k = 2."""
    grid = _grid()
    part = profile_rmap(_mil(), grid)
    sonuc = simulate_lathe([_paso(9.8)], STOK, cell=0.5, part=part, initial=_bitmis_pay(0.5))
    c = [k for k in sonuc.collisions if k.kind == "cakma"]
    assert len(c) == 1
    assert c[0].k == 2 and c[0].op == 0
    assert c[0].depth == pytest.approx(0.2, abs=1e-9)
    assert -10.0 <= c[0].at[2] <= 0.0


def test_K15_dogru_ince_paso_kayit_yok():
    grid = _grid()
    part = profile_rmap(_mil(), grid)
    sonuc = simulate_lathe([_paso(10.0)], STOK, cell=0.5, part=part, initial=_bitmis_pay(0.5))
    assert [k for k in sonuc.collisions if k.kind == "cakma"] == []
    assert sonuc.gouge_volume() == pytest.approx(0.0, abs=1e-9)


@pytest.mark.parametrize("x_alt", [9.8, 10.0])
def test_K15_kalan_ve_cakma_hacmi(x_alt):
    """rest = Σ π dz (malzeme − parça), gouge = Σ π dz (parça − malzeme); malzeme bağımsız referansla."""
    grid = _grid()
    part = profile_rmap(_mil(), grid)
    tp = _paso(x_alt)
    sonuc = simulate_lathe([tp], STOK, cell=0.5, part=part, initial=_bitmis_pay(0.5))
    zc = grid.centers()
    init = [[(0.0, (10.0 if z > -20 else 15.0) + 0.5)] for z in zc]
    pts = [(p[0], p[2]) for p in tp.points()]
    son = cut_map(init, zc, turn_core(turn_tool(R_N)), R_N, tip_offset(3, R_N), pts)
    rest = gouge = 0.0
    for i, z in enumerate(zc):
        xp = 10.0 if z > -20 else 15.0
        top = max((u for _, u in son[i]), default=0.0)  # tek aralık [0, top] kalır
        rest += math.pi * grid.dz * max(top * top - xp * xp, 0.0)
        gouge += math.pi * grid.dz * max(xp * xp - top * top, 0.0)
    assert sonuc.rest_volume() == pytest.approx(rest, rel=1e-9, abs=1e-9)
    assert sonuc.gouge_volume() == pytest.approx(gouge, rel=1e-9, abs=1e-9)
    if x_alt < 10.0:
        assert gouge > 0


def test_K15_parca_yoksa_hacim_hatasi():
    from cam.model import CamError

    sonuc = simulate_lathe([_paso(10.0)], STOK, cell=0.5)
    assert sonuc.part is None
    with pytest.raises(CamError):
        sonuc.rest_volume()
    with pytest.raises(CamError):
        sonuc.gouge_volume()


# ------------------------------------------------------------------ K16 OCCT


def _occt_mil():
    bd = pytest.importorskip("build123d")
    from geometry.part import Part

    al = (bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN)
    s1 = bd.Pos(0, 0, -50) * bd.Cylinder(16.0, 15.0, align=al)
    s2 = bd.Pos(0, 0, -35) * bd.Cylinder(15.0, 15.0, align=al)
    s3 = bd.Pos(0, 0, -20) * bd.Cylinder(10.0, 20.0, align=al)
    return Part(s1 + s2 + s3, name="basamakli_mil")


def _occt_profil() -> Profile:
    """Aynı milin torna profili (ön uçtan arkaya)."""
    return Profile.polygon([(0, 10), (-20, 10), (-20, 15), (-35, 15), (-35, 16)], closed=False)


def _occt_bolge() -> Region:
    return Region(
        Profile.polygon([(0, 0), (0, 10), (-20, 10), (-20, 15), (-35, 15), (-35, 16), (-50, 16), (-50, 0)])
    )


@pytest.mark.occt
def test_K16_part_rmap_profile_rmap_ile_ayni():
    from cam.sim import part_rmap

    part = _occt_mil()
    stok = CylinderStock(D=32.0, zmin=-50.0, zmax=0.0)
    g = RadialMap.from_stock(stok, 0.5)
    tol = 0.01
    pm = part_rmap(part, g, tol)
    pr = profile_rmap(_occt_bolge(), g)
    for i in range(g.nz):
        a, b = pm.intervals(i), pr.intervals(i)
        assert len(a) == len(b) == 1
        assert a[0][0] == pytest.approx(b[0][0], abs=1e-9)
        assert a[0][1] == pytest.approx(b[0][1], abs=tol + 1e-9)


@pytest.mark.occt
def test_K16_occt_simulasyon_cakma_yok_hacim():
    from cam.sim import part_rmap

    part = _occt_mil()
    stok = CylinderStock(D=32.0, zmin=-50.0, zmax=0.0)
    cell = 0.5
    g = RadialMap.from_stock(stok, cell)
    tool = turn_tool(R_N)
    cut = TurnCut(feed=0.2, rpm=1000.0, a_p=2.0)
    ops = [rough(_occt_profil(), stok, tool, cut, allowance=0.3), finish(_occt_profil(), stok, tool, cut)]
    sonuc = simulate_lathe(ops, stok, cell=cell, part=part_rmap(part, g, 0.01), arc_tol=1e-5)
    assert [c for c in sonuc.collisions if c.kind == "cakma"] == []
    Pk = _occt_profil().length
    assert sonuc.rmap.volume() == pytest.approx(part.volume, abs=Pk * cell * 2 * math.pi * 16.0)
