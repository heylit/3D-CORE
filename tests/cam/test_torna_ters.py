"""SPEC 40 B — ters bağlama testleri (K7–K10).

Testler yalnız SPEC 40 metninden ve sabit arayüzlerden (cam/model.py, cam/torna_ek.py imzaları, SPEC 22
RadialMap / simulate_lathe arayüzü) yazıldı; uygulama gövdesi okunmadı. Geometri uydurmadır.

Dönüşüm z' = z_ref − z, x' = x; varsayılan z_ref = zmin + zmax (stok kendine gider).
SPEC 22 (RadialMap, simulate_lathe, profile_rmap) birleşmeden K9–K10 atlanır.

K10 senaryosu (dolu çubuk D = 40, z ∈ [0, 60], hücre 0,5, burun yarıçapı 0,2 < dz/2):
- bağlama 1: alın z = 59, boy x = 15, z ∈ [40, 59]
- ters bağlama (z_ref = 60): bağlama 2'de alın z' = 59, boy x = 17, z' ∈ [35, 59]
- parça (bağlama 2'de): z' ∈ [1, 20] x = 15; [20, 35] x = 20; [35, 59] x = 17
- kaldırılan hacim π·(400·60 − 225·19 − 400·15 − 289·24) = 6789π; kalan 17211π.
Omuzlar hücre sınırında, burun köşe dolgusu (r = 0,2) hücre merkezlerine (sınırdan 0,25) ulaşmaz:
ayrık harita keskin köşeli parçanınkine birebir eşittir.
"""

from __future__ import annotations

import copy
import math

import numpy as np
import pytest

from cam.lathe_ops import TurnCut, face, turn
from cam.model import (
    CamError,
    CylinderStock,
    LatheTool,
    LatheToolKind,
    Setup,
    Stock,
    Wcs,
)
from cam.profile import Arc, Line, Profile
from cam.torna_ek import flip_profile, flip_rmap, flip_setup, flip_stock

TOL = 1e-9
STOCK = CylinderStock(D=40.0, zmin=0.0, zmax=60.0)


def _radial():
    mod = pytest.importorskip("cam.sim.radial", reason="SPEC 22 RadialMap henüz birleşmedi (PR #41)")
    return mod


def _iv_eq(a, b) -> None:
    """Aralık listeleri eşit (1e-9)."""
    A = np.asarray(list(a), dtype=float).reshape(-1, 2)
    B = np.asarray(list(b), dtype=float).reshape(-1, 2)
    assert A.shape == B.shape, f"{list(a)} != {list(b)}"
    assert np.allclose(A, B, rtol=0.0, atol=TOL), f"{list(a)} != {list(b)}"


def _same_seg(a, b) -> None:
    assert type(a) is type(b)
    assert a.p0 == pytest.approx(b.p0, abs=TOL)
    assert a.p1 == pytest.approx(b.p1, abs=TOL)
    if isinstance(a, Arc):
        assert a.c == pytest.approx(b.c, abs=TOL)
        assert a.ccw == b.ccw


def _flip_pt(p, z_ref: float) -> np.ndarray:
    return np.array([z_ref - p[0], p[1]])


def _open_profile() -> Profile:
    # ön→arka: (60,12) → (40,12), ccw dışbükey yay (40,12) → (36,16) merkez (36,12), (36,16) → (10,16)
    return Profile(
        [
            Line((60.0, 12.0), (40.0, 12.0)),
            Arc((40.0, 12.0), (36.0, 16.0), (36.0, 12.0), ccw=True),
            Line((36.0, 16.0), (10.0, 16.0)),
        ],
        closed=False,
    )


def _closed_profile() -> Profile:
    # kapalı yarı kesit: eksen, ön yüz, (40,12) noktası, ccw yay, arka yüz
    return Profile(
        [
            Line((10.0, 0.0), (60.0, 0.0)),
            Line((60.0, 0.0), (60.0, 12.0)),
            Line((60.0, 12.0), (40.0, 12.0)),
            Arc((40.0, 12.0), (36.0, 16.0), (36.0, 12.0), ccw=True),
            Line((36.0, 16.0), (10.0, 16.0)),
            Line((10.0, 16.0), (10.0, 0.0)),
        ],
        closed=True,
    )


# ------------------------------------------------------------------ K7 flip_profile, flip_stock


class TestK7Profil:
    def test_T4_nokta(self):
        # T4: stok [0, 60], z_ref = 60, (40, 12) → (20, 12)
        fp = flip_profile(_open_profile(), 60.0)
        pts = [s.p0 for s in fp.segments] + [fp.segments[-1].p1]
        assert any(np.allclose(p, (20.0, 12.0), atol=TOL) for p in pts)

    def test_acik_profil_on_arka(self):
        fp = flip_profile(_open_profile(), 60.0)
        assert not fp.closed
        # (60,12)…(10,16) → (0,12)…(50,16); ön→arka: (50,16)'dan (0,12)'ye
        assert fp.start == pytest.approx((50.0, 16.0), abs=TOL)
        assert fp.end == pytest.approx((0.0, 12.0), abs=TOL)
        assert fp.start[0] > fp.end[0]

    def test_acik_profil_geometrisi(self):
        # her parça, özgün parçalardan birinin z' = z_ref − z görüntüsü (yay orta noktası dahil)
        src = _open_profile()
        fp = flip_profile(src, 60.0)
        assert len(fp.segments) == len(src.segments)
        for s, o in zip(fp.segments, reversed(src.segments), strict=True):
            assert type(s) is type(o)
            assert {tuple(np.round(s.p0, 9)), tuple(np.round(s.p1, 9))} == {
                tuple(np.round(_flip_pt(o.p0, 60.0), 9)),
                tuple(np.round(_flip_pt(o.p1, 60.0), 9)),
            }
            for t in (0.25, 0.5, 0.75):
                assert s.point(t) == pytest.approx(_flip_pt(o.point(1 - t), 60.0), abs=TOL)
            if isinstance(s, Arc):
                assert s.c == pytest.approx(_flip_pt(o.c, 60.0), abs=TOL)
                assert s.R == pytest.approx(o.R, abs=TOL)

    def test_kapali_profil_yay_yonu(self):
        # T4: yansıma yönü ters çevirir; kapalı profil yeniden yönlendirilmez → ccw yay cw olur
        src = _closed_profile()
        fp = flip_profile(src, 60.0)
        assert fp.closed
        arcs = [s for s in fp.segments if isinstance(s, Arc)]
        assert len(arcs) == 1
        a = arcs[0]
        assert a.ccw is False
        assert a.c == pytest.approx((24.0, 12.0), abs=TOL)
        assert {tuple(np.round(a.p0, 9)), tuple(np.round(a.p1, 9))} == {(20.0, 12.0), (24.0, 16.0)}
        assert fp.area == pytest.approx(-src.area, rel=1e-12)
        mid = a.point(0.5)
        o = next(s for s in src.segments if isinstance(s, Arc))
        assert mid == pytest.approx(_flip_pt(o.point(0.5), 60.0), abs=TOL)

    @pytest.mark.parametrize("z_ref", [60.0, 0.0, 137.5, -12.25])
    def test_iki_kez_ayni(self, z_ref):
        src = _open_profile()
        back = flip_profile(flip_profile(src, z_ref), z_ref)
        assert back.closed == src.closed
        assert len(back.segments) == len(src.segments)
        for a, b in zip(back.segments, src.segments, strict=True):
            _same_seg(a, b)

    def test_iki_kez_ayni_kapali(self):
        src = _closed_profile()
        back = flip_profile(flip_profile(src, 60.0), 60.0)
        assert back.closed
        assert back.area == pytest.approx(src.area, rel=1e-12)
        for a, b in zip(back.segments, src.segments, strict=True):
            _same_seg(a, b)

    def test_girdi_degismez(self):
        src = _open_profile()
        before = [(s.p0.copy(), s.p1.copy()) for s in src.segments]
        flip_profile(src, 60.0)
        for s, (p0, p1) in zip(src.segments, before, strict=True):
            assert np.array_equal(s.p0, p0) and np.array_equal(s.p1, p1)

    def test_yaricap_degismez(self):
        fp = flip_profile(_open_profile(), 100.0)
        lo, hi = fp.bbox()
        assert lo[1] == pytest.approx(12.0, abs=TOL)
        assert hi[1] == pytest.approx(16.0, abs=TOL)
        assert lo[0] == pytest.approx(40.0, abs=TOL)
        assert hi[0] == pytest.approx(90.0, abs=TOL)

    def test_flip_stock_varsayilan_kendine(self):
        s = CylinderStock(D=40.0, zmin=-15.0, zmax=45.0, d=8.0)
        f = flip_stock(s)
        assert (f.D, f.zmin, f.zmax, f.d) == pytest.approx((40.0, -15.0, 45.0, 8.0), abs=TOL)

    def test_flip_stock_z_ref(self):
        # CylinderStock(D, z_ref − zmax, z_ref − zmin, d)
        s = CylinderStock(D=40.0, zmin=0.0, zmax=60.0, d=8.0)
        f = flip_stock(s, 100.0)
        assert (f.D, f.zmin, f.zmax, f.d) == pytest.approx((40.0, 40.0, 100.0, 8.0), abs=TOL)
        f0 = flip_stock(s, 0.0)
        assert (f0.zmin, f0.zmax) == pytest.approx((-60.0, 0.0), abs=TOL)

    def test_flip_stock_kutu(self):
        with pytest.raises(CamError):
            flip_stock(Stock(-10, -10, 0, 10, 10, 60))

    def test_flip_profile_sonlu_olmayan(self):
        with pytest.raises(CamError):
            flip_profile(_open_profile(), math.nan)


# ------------------------------------------------------------------ K8 flip_setup

CHUCK = CylinderStock(D=80.0, zmin=-10.0, zmax=8.0, d=30.0)  # ayna çenesi zarfı (halka)
CHUCK2 = CylinderStock(D=80.0, zmin=-12.0, zmax=6.0, d=34.0)


class TestK8Baglama:
    def _setup(self) -> Setup:
        return Setup(name="bag1", wcs=Wcs("G54", (0.0, 0.0, 250.0)), stock=STOCK, fixtures=[CHUCK])

    def test_varsayilanlar(self):
        s1 = self._setup()
        s2 = flip_setup(s1, [CHUCK2])
        assert s2.name == "bag1-ters"
        assert s2.wcs.code == "G55"
        assert isinstance(s2.stock, CylinderStock)
        f = flip_stock(STOCK)
        assert (s2.stock.D, s2.stock.zmin, s2.stock.zmax, s2.stock.d) == pytest.approx(
            (f.D, f.zmin, f.zmax, f.d), abs=TOL
        )
        assert list(s2.fixtures) == [CHUCK2]  # aynen, dönüştürülmeden

    def test_verilen_degerler(self):
        s1 = self._setup()
        w = Wcs("G56", (0.0, 0.0, 300.0))
        s2 = flip_setup(s1, [], z_ref=100.0, wcs=w, name="ikinci")
        assert s2.name == "ikinci"
        assert s2.wcs is w or (s2.wcs.code, s2.wcs.origin) == ("G56", (0.0, 0.0, 300.0))
        assert (s2.stock.zmin, s2.stock.zmax) == pytest.approx((40.0, 100.0), abs=TOL)
        assert list(s2.fixtures) == []

    def test_baglama_elemani_birinciden_tasinmaz(self):
        s2 = flip_setup(self._setup(), [])
        assert list(s2.fixtures) == []

    def test_girdi_degismez(self):
        s1 = self._setup()
        before = copy.deepcopy(s1.to_dict())
        flip_setup(s1, [CHUCK2], z_ref=90.0)
        assert s1.to_dict() == before

    def test_kutu_stok(self):
        s = Setup(name="kutu", wcs=Wcs(), stock=Stock(-10, -10, 0, 10, 10, 60))
        with pytest.raises(CamError):
            flip_setup(s, [])


# ------------------------------------------------------------------ K9 flip_rmap


def _carved(rm, stock: CylinderStock, cell: float, fixtures=()):
    """Asimetrik oyulmuş harita: hücre i'de dış yarıçap z'ye göre doğrusal azalır, bir iç delik ön tarafta."""
    m = rm.RadialMap.from_stock(stock, cell, list(fixtures))
    zc = m.centers()
    R = stock.D / 2
    for i, z in enumerate(zc):
        if not stock.zmin < z < stock.zmax:
            continue
        u = R - 0.1 * (z - stock.zmin) / (stock.zmax - stock.zmin) * R  # [0.9R, R]
        if u < R:
            m.subtract(i, u, R + 1.0)
        if z > stock.zmax - 10.0:
            m.subtract(i, 0.0, 3.0 + 0.01 * i)
    return m


def _stock_cells(m, stock: CylinderStock) -> list[int]:
    zc = m.centers()
    return [i for i, z in enumerate(zc) if stock.zmin < z < stock.zmax]


class TestK9Harita:
    def test_ters_sira_ve_hacim(self):
        rm = _radial()
        s1 = Setup("b1", Wcs(), STOCK, [CHUCK])
        m1 = _carved(rm, STOCK, 0.5, [CHUCK])
        s2 = flip_setup(s1, [CHUCK2])
        m2 = flip_rmap(m1, s2, 0.5)
        grid = rm.RadialMap.from_stock(s2.stock, 0.5, list(s2.fixtures))
        assert (m2.z0, m2.dz, m2.nz) == pytest.approx((grid.z0, grid.dz, grid.nz), abs=1e-12)
        assert m2.volume() == pytest.approx(m1.volume(), rel=1e-12)
        z_ref = STOCK.zmin + STOCK.zmax
        c1, c2 = m1.centers(), m2.centers()
        for i in _stock_cells(m1, STOCK):
            j = int(np.argmin(np.abs(c2 - (z_ref - c1[i]))))
            assert c2[j] == pytest.approx(z_ref - c1[i], abs=1e-9 * m1.dz)
            _iv_eq(m2.intervals(j), m1.intervals(i))

    def test_baglama_elemani_hucreleri_bos(self):
        # ikinci bağlamada eleman stoğun altından (ayna) ve üstünden (punta zarfı) taşar
        rm = _radial()
        tail = CylinderStock(D=20.0, zmin=55.0, zmax=67.0)
        s2 = flip_setup(Setup("b1", Wcs(), STOCK, []), [CHUCK2, tail])
        m1 = _carved(rm, STOCK, 0.5)
        m2 = flip_rmap(m1, s2, 0.5)
        zc = m2.centers()
        assert zc.min() < STOCK.zmin and zc.max() > STOCK.zmax  # ek hücreler var
        for j, z in enumerate(zc):
            if not STOCK.zmin < z < STOCK.zmax:
                _iv_eq(m2.intervals(j), [])
        assert m2.volume() == pytest.approx(m1.volume(), rel=1e-12)

    def test_z_ref_kaydirma_tam_kat(self):
        # z_ref − (zmin + zmax) = 3 = 6·dz: sütun merkezleri örtüşür
        rm = _radial()
        s2 = flip_setup(Setup("b1", Wcs(), STOCK, []), [], z_ref=63.0)
        m1 = _carved(rm, STOCK, 0.5)
        m2 = flip_rmap(m1, s2, 0.5, z_ref=63.0)
        assert m2.volume() == pytest.approx(m1.volume(), rel=1e-12)
        c1, c2 = m1.centers(), m2.centers()
        for i in _stock_cells(m1, STOCK):
            j = int(np.argmin(np.abs(c2 - (63.0 - c1[i]))))
            _iv_eq(m2.intervals(j), m1.intervals(i))

    def test_varsayilan_z_ref_ikinci_stoktan(self):
        # z_ref None → ikinci bağlamanın stoğundan zmin + zmax (= 60)
        rm = _radial()
        s2 = flip_setup(Setup("b1", Wcs(), STOCK, []), [])
        m1 = _carved(rm, STOCK, 0.5)
        a = flip_rmap(m1, s2, 0.5)
        b = flip_rmap(m1, s2, 0.5, z_ref=60.0)
        for j in range(a.nz):
            _iv_eq(a.intervals(j), b.intervals(j))

    def test_girdi_degismez(self):
        rm = _radial()
        m1 = _carved(rm, STOCK, 0.5)
        before = [list(m1.intervals(i)) for i in range(m1.nz)]
        flip_rmap(m1, flip_setup(Setup("b1", Wcs(), STOCK, []), []), 0.5)
        assert [list(m1.intervals(i)) for i in range(m1.nz)] == before

    def test_dz_farkli(self):
        rm = _radial()
        m1 = _carved(rm, STOCK, 0.5)
        with pytest.raises(CamError):
            flip_rmap(m1, flip_setup(Setup("b1", Wcs(), STOCK, []), []), 0.4)

    def test_sutun_kaymasi_tam_kat_degil(self):
        # bağlama z_ref = 60 ile kuruldu, haritaya z_ref = 60,2 verildi: sütunlar 0,2 = 0,4·dz kayar
        rm = _radial()
        m1 = _carved(rm, STOCK, 0.5)
        s2 = flip_setup(Setup("b1", Wcs(), STOCK, []), [])
        with pytest.raises(CamError):
            flip_rmap(m1, s2, 0.5, z_ref=60.2)

    def test_kutu_stok(self):
        rm = _radial()
        m1 = _carved(rm, STOCK, 0.5)
        with pytest.raises(CamError):
            flip_rmap(m1, Setup("k", Wcs(), Stock(-10, -10, 0, 10, 10, 60)), 0.5)


# ------------------------------------------------------------------ K10 iki bağlamalı senaryo

TOOL = LatheTool(
    id=1, name="DCMT", kind=LatheToolKind.TURN, nose_r=0.2, tip=3, kappa_r=95.0, eps_r=80.0, edge_len=6.0
)
CUT = TurnCut(feed=0.2, rpm=1500.0, a_p=2.0)


def _part_profile() -> Profile:
    # bağlama 2 koordinatında iki yüzü işlenmiş parçanın yarı kesiti (keskin köşeli)
    return Profile.polygon(
        [(1, 0), (59, 0), (59, 17), (35, 17), (35, 20), (20, 20), (20, 15), (1, 15)], closed=True
    )


def _expected_outer(z: float) -> float:
    if 1 < z < 20:
        return 15.0
    if 20 < z < 35:
        return 20.0
    if 35 < z < 59:
        return 17.0
    return 0.0


class TestK10IkiBaglama:
    def test_iki_yuz(self):
        rm = _radial()
        sim = pytest.importorskip("cam.sim.lathe", reason="SPEC 22 simulate_lathe henüz birleşmedi (PR #41)")
        s1 = Setup("bag1", Wcs("G54"), STOCK, [])
        ops1 = [face(STOCK, TOOL, CUT, 59.0), turn(STOCK, TOOL, CUT, 15.0, 40.0)]
        r1 = sim.simulate_lathe(ops1, s1, cell=0.5)

        s2 = flip_setup(s1, [])
        init = flip_rmap(r1.rmap, s2, 0.5)
        st2 = s2.stock
        ops2 = [face(st2, TOOL, CUT, 59.0), turn(st2, TOOL, CUT, 17.0, 35.0)]
        r2 = sim.simulate_lathe(ops2, s2, cell=0.5, initial=init)

        removed = r1.removed_volume + r2.removed_volume
        assert removed == pytest.approx(6789.0 * math.pi, rel=1e-9)
        assert r2.rmap.volume() == pytest.approx(17211.0 * math.pi, rel=1e-9)
        assert STOCK.volume - r2.rmap.volume() == pytest.approx(removed, rel=1e-9)

        # hücre hücre: keskin köşeli parça
        for i, z in enumerate(r2.rmap.centers()):
            u = _expected_outer(z)
            iv = r2.rmap.intervals(i)
            _iv_eq(iv, [] if u == 0.0 else [(0.0, u)])

        # profile_rmap ile birebir
        part = rm.profile_rmap(_part_profile(), r2.rmap)
        for i in range(r2.rmap.nz):
            _iv_eq(r2.rmap.intervals(i), part.intervals(i))
