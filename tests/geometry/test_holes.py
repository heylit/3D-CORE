"""SPEC 23 — geometry/holes.py testleri (K5, K5b, K6, K7, K8). OCCT gerektirir.

Testler SPEC 23'ün "Teori", "Delik kaydı", "Arayüz" ve "Kabul kriterleri" bölümlerinden ve
geometry/part.py arayüzünden yazıldı; delik uygulaması okunmadı. Uydurma geometri: blok 100×60×20.
Koordinat kuralı (SPEC 02): blok min köşesi orijinde; üst yüz z = c; düz delikler üstten −Z.
İki Hole == ile karşılaştırılmaz (numpy alanları); alanlar tek tek karşılaştırılır.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

pytest.importorskip("build123d", reason='build123d kurulu değil (pip install -e ".[cad]")')

from geometry.features import block, chamfer_top, hole  # noqa: E402
from geometry.fillet import fillet_vertical  # noqa: E402
from geometry.holes import (  # noqa: E402
    CBORE_ISO4762,
    THREADS_COARSE,
    counterbore_hole,
    countersink_hole,
    inclined_hole,
    parse_thread,
    tapped_hole,
)
from geometry.part import GeometryError, Hole, Part  # noqa: E402

pytestmark = pytest.mark.occt

A, B, C = 100.0, 60.0, 20.0  # blok kenarları [mm]
V0 = A * B * C
REL = 1e-6
ASAGI = np.array([0.0, 0.0, -1.0])


def blok() -> Part:
    return block(A, B, C)


def kayit_bekle(
    h: Hole,
    origin,
    axis,
    d: float,
    depth: float,
    through: bool,
    *,
    csk_d: float = 0.0,
    csk_angle: float = 0.0,
    cbore_d: float = 0.0,
    cbore_depth: float = 0.0,
    thread: str = "",
    thread_d: float = 0.0,
    pitch: float = 0.0,
    thread_depth: float = 0.0,
) -> None:
    """Hole alanlarını tek tek denetler (sayılar rel 1e-9, vektörler atol 1e-9)."""
    assert isinstance(h, Hole)
    np.testing.assert_allclose(h.origin, origin, atol=1e-9)
    np.testing.assert_allclose(h.axis, axis, atol=1e-9)
    assert h.d == pytest.approx(d, rel=1e-9)
    assert h.depth == pytest.approx(depth, rel=1e-9)
    assert h.through is through
    assert h.csk_d == pytest.approx(csk_d, rel=1e-9)
    assert h.csk_angle == pytest.approx(csk_angle, rel=1e-9)
    assert h.cbore_d == pytest.approx(cbore_d, rel=1e-9)
    assert h.cbore_depth == pytest.approx(cbore_depth, rel=1e-9)
    assert h.thread == thread
    assert h.thread_d == pytest.approx(thread_d, rel=1e-9)
    assert h.pitch == pytest.approx(pitch, rel=1e-9)
    assert h.thread_depth == pytest.approx(thread_depth, rel=1e-9)


# --- El hesabı (SPEC 23 "Teori") ----------------------------------------------------------------


def h_cone(d: float, D: float, alpha: float) -> float:
    """Havşa konisi yüksekliği: h = (D − d) / (2 tan(α/2)), α derece."""
    return (D - d) / (2 * math.tan(math.radians(alpha) / 2))


def dV_countersink(d: float, D: float, alpha: float, t: float) -> float:
    """Kesik koni + silindir: ΔV = (π h / 3)(R² + R r + r²) + π r² (t − h)."""
    h = h_cone(d, D, alpha)
    R, r = D / 2, d / 2
    return math.pi * h / 3 * (R**2 + R * r + r**2) + math.pi * r**2 * (t - h)


def dV_counterbore(d: float, D: float, t_c: float, t: float) -> float:
    """İki eş eksenli silindir: ΔV = π (D² − d²) t_c / 4 + π d² t / 4."""
    return math.pi * (D**2 - d**2) * t_c / 4 + math.pi * d**2 * t / 4


def dV_cyl(d: float, t: float) -> float:
    """Silindirik delik: ΔV = π d² t / 4."""
    return math.pi * d**2 * t / 4


def test_el_hesabi_havsa_90_derece():
    """α = 90° → h = (D − d)/2; d = D sınırında havşa yok, ΔV düz deliğe döner."""
    assert h_cone(6.0, 12.0, 90.0) == pytest.approx(3.0)
    assert dV_countersink(6.0, 6.0, 90.0, 10.0) == pytest.approx(dV_cyl(6.0, 10.0))


# --- K5 countersink_hole ------------------------------------------------------------------------

D_CS, DM_CS = 6.6, 13.0  # delik çapı, havşa ağız çapı [mm]


@pytest.mark.parametrize("alpha", [90.0, 82.0, 60.0])
@pytest.mark.parametrize("depth", [None, 12.0])
def test_k5_countersink_hacim_ve_kayit(alpha, depth):
    p0 = blok()
    x, y = 50.0, 30.0
    p = countersink_hole(p0, x, y, D_CS, DM_CS, csk_angle=alpha, depth=depth)
    t = C if depth is None else depth
    assert p0.volume - p.volume == pytest.approx(dV_countersink(D_CS, DM_CS, alpha, t), rel=REL)
    assert len(p.holes) == 1
    kayit_bekle(p.holes[0], [x, y, C], ASAGI, D_CS, t, depth is None, csk_d=DM_CS, csk_angle=alpha)


def test_k5_countersink_varsayilan_aci_90():
    p0 = blok()
    p = countersink_hole(p0, 30.0, 20.0, D_CS, DM_CS)
    assert p0.volume - p.volume == pytest.approx(dV_countersink(D_CS, DM_CS, 90.0, C), rel=REL)
    assert p.holes[0].csk_angle == pytest.approx(90.0)
    assert p.holes[0].through is True


@pytest.mark.parametrize(
    "kw",
    [
        {"d": 6.6, "csk_d": 6.6},  # csk_d = d
        {"d": 6.6, "csk_d": 5.0},  # csk_d < d
        {"d": 0.0, "csk_d": 13.0},  # d = 0
        {"d": -2.0, "csk_d": 13.0},
        {"d": 6.6, "csk_d": 13.0, "csk_angle": 0.0},
        {"d": 6.6, "csk_d": 13.0, "csk_angle": 180.0},
        {"d": 6.6, "csk_d": 13.0, "csk_angle": -30.0},
        {"d": 6.6, "csk_d": 13.0, "depth": 3.0},  # depth < h (α = 90°: h = 3.2): koni dibe ulaşıyor
        {"d": 6.6, "csk_d": 13.0, "depth": 2.0},  # depth < h
        {"d": 6.6, "csk_d": 13.0, "depth": 25.0},  # depth > yükseklik
    ],
)
def test_k5_countersink_gecersiz_girdi_hata(kw):
    p0 = blok()
    with pytest.raises(GeometryError):
        countersink_hole(p0, 50.0, 30.0, **kw)
    assert p0.volume == pytest.approx(V0, rel=1e-12)
    assert p0.holes == ()


# --- K5b counterbore_hole -----------------------------------------------------------------------

# SPEC 23 tablosu: civata → (d geçiş, D lamba, t_c lamba derinliği), ISO 4762 (d_k, k)
CBORE_SPEC = {
    "M3": (3.4, 6.5, 3.4),
    "M4": (4.5, 8.0, 4.4),
    "M5": (5.5, 10.0, 5.4),
    "M6": (6.6, 11.0, 6.4),
    "M8": (9.0, 15.0, 8.6),
    "M10": (11.0, 18.0, 10.6),
    "M12": (13.5, 20.0, 12.6),
    "M14": (15.5, 24.0, 14.6),
    "M16": (17.5, 26.0, 16.6),
    "M20": (22.0, 33.0, 20.6),
    "M24": (26.0, 40.0, 24.8),
}
ISO4762_BAS = {
    "M3": (5.5, 3.0),
    "M4": (7.0, 4.0),
    "M5": (8.5, 5.0),
    "M6": (10.0, 6.0),
    "M8": (13.0, 8.0),
    "M10": (16.0, 10.0),
    "M12": (18.0, 12.0),
    "M14": (21.0, 14.0),
    "M16": (24.0, 16.0),
    "M20": (30.0, 20.0),
    "M24": (36.0, 24.0),
}


def test_k5b_tablo_spec_ile_ayni():
    assert set(CBORE_ISO4762) == set(CBORE_SPEC)
    for civata, beklenen in CBORE_SPEC.items():
        np.testing.assert_allclose(CBORE_ISO4762[civata], beklenen, rtol=0, atol=1e-12)


@pytest.mark.parametrize("civata", sorted(CBORE_SPEC))
def test_k5b_tablo_tutarliligi(civata):
    """Civata başı lambaya sığar ve gömülür, gövde geçiş deliğinden geçer: D > d_k, t_c > k, d > d_n."""
    d, D, t_c = CBORE_ISO4762[civata]
    d_k, k = ISO4762_BAS[civata]
    d_n = float(civata[1:])
    assert D > d_k
    assert t_c > k
    assert d > d_n


@pytest.mark.parametrize("civata", ["M6", "M8"])
@pytest.mark.parametrize("depth", [None, 14.0])
def test_k5b_counterbore_tablo_hacim_ve_kayit(civata, depth):
    d, D, t_c = CBORE_SPEC[civata]
    p0 = blok()
    x, y = 40.0, 25.0
    p = counterbore_hole(p0, x, y, screw=civata, depth=depth)
    t = C if depth is None else depth
    assert p0.volume - p.volume == pytest.approx(dV_counterbore(d, D, t_c, t), rel=REL)
    assert len(p.holes) == 1
    kayit_bekle(p.holes[0], [x, y, C], ASAGI, d, t, depth is None, cbore_d=D, cbore_depth=t_c)


@pytest.mark.parametrize("depth", [None, 12.0])
def test_k5b_counterbore_acik_olculer(depth):
    d, D, t_c = 5.5, 10.0, 5.0
    p0 = blok()
    p = counterbore_hole(p0, 60.0, 30.0, d=d, cbore_d=D, cbore_depth=t_c, depth=depth)
    t = C if depth is None else depth
    assert p0.volume - p.volume == pytest.approx(dV_counterbore(d, D, t_c, t), rel=REL)
    kayit_bekle(p.holes[0], [60.0, 30.0, C], ASAGI, d, t, depth is None, cbore_d=D, cbore_depth=t_c)


def test_k5b_acik_olcu_tabloyu_ezer():
    """screw="M8" ile cbore_depth = 10 verilir: d = 9 ve D = 15 tablodan, t_c = 10 açık ölçüden."""
    p0 = blok()
    p = counterbore_hole(p0, 50.0, 30.0, screw="M8", cbore_depth=10.0)
    assert p0.volume - p.volume == pytest.approx(dV_counterbore(9.0, 15.0, 10.0, C), rel=REL)
    kayit_bekle(p.holes[0], [50.0, 30.0, C], ASAGI, 9.0, C, True, cbore_d=15.0, cbore_depth=10.0)

    p2 = counterbore_hole(p0, 50.0, 30.0, screw="M8", d=8.5, cbore_d=14.0)
    assert p0.volume - p2.volume == pytest.approx(dV_counterbore(8.5, 14.0, 8.6, C), rel=REL)
    assert p2.holes[0].d == pytest.approx(8.5)
    assert p2.holes[0].cbore_d == pytest.approx(14.0)
    assert p2.holes[0].cbore_depth == pytest.approx(8.6)


@pytest.mark.parametrize(
    "kw",
    [
        {"screw": "M7"},  # tabloda yok
        {"screw": "M8x1"},  # tabloda yok
        {},  # screw yok, ölçü yok
        {"d": 5.5, "cbore_d": 10.0},  # cbore_depth eksik
        {"d": 5.5, "cbore_depth": 5.0},  # cbore_d eksik
        {"cbore_d": 10.0, "cbore_depth": 5.0},  # d eksik
        {"d": 10.0, "cbore_d": 10.0, "cbore_depth": 5.0},  # cbore_d = d
        {"d": 10.0, "cbore_d": 8.0, "cbore_depth": 5.0},  # cbore_d < d
        {"d": 5.5, "cbore_d": 10.0, "cbore_depth": 8.0, "depth": 8.0},  # cbore_depth = depth
        {"d": 5.5, "cbore_d": 10.0, "cbore_depth": 9.0, "depth": 8.0},  # cbore_depth > depth
        {"d": 5.5, "cbore_d": 10.0, "cbore_depth": 20.0},  # boydan boya, cbore_depth = yükseklik
        {"d": 5.5, "cbore_d": 10.0, "cbore_depth": 5.0, "depth": 25.0},  # depth > yükseklik
        {"screw": "M8", "cbore_d": 8.0},  # açık ölçü tabloyu ezince cbore_d < d (= 9)
    ],
)
def test_k5b_counterbore_gecersiz_girdi_hata(kw):
    p0 = blok()
    with pytest.raises(GeometryError):
        counterbore_hole(p0, 50.0, 30.0, **kw)
    assert p0.volume == pytest.approx(V0, rel=1e-12)


# --- K6 parse_thread ve tapped_hole -------------------------------------------------------------

KABA_SPEC = {
    "M3": 0.5,
    "M4": 0.7,
    "M5": 0.8,
    "M6": 1.0,
    "M8": 1.25,
    "M10": 1.5,
    "M12": 1.75,
    "M14": 2.0,
    "M16": 2.0,
    "M20": 2.5,
    "M24": 3.0,
}


def test_k6_kaba_hatve_tablosu_spec_ile_ayni():
    assert set(THREADS_COARSE) == set(KABA_SPEC)
    for ad, P in KABA_SPEC.items():
        assert THREADS_COARSE[ad] == pytest.approx(P, abs=1e-12)


@pytest.mark.parametrize("ad", sorted(KABA_SPEC))
def test_k6_parse_thread_kaba(ad):
    d_n, P = parse_thread(ad)
    assert d_n == pytest.approx(float(ad[1:]))
    assert P == pytest.approx(KABA_SPEC[ad])


@pytest.mark.parametrize(
    "yazim, beklenen",
    [("M8x1", (8.0, 1.0)), ("M10x1.25", (10.0, 1.25)), ("M12x1.5", (12.0, 1.5)), ("M20x2", (20.0, 2.0))],
)
def test_k6_parse_thread_ince(yazim, beklenen):
    d_n, P = parse_thread(yazim)
    assert (d_n, P) == pytest.approx(beklenen)


@pytest.mark.parametrize(
    "yazim",
    [
        "M7",  # kaba tabloda yok
        "M30",  # kaba tabloda yok
        "",
        "M",
        "8",
        "M8x",
        "Mx1",
        "M8y1",
        "M8x1x1",
        "M8x8",  # P = d_n
        "M8x10",  # P > d_n
    ],
)
def test_k6_parse_thread_gecersiz_hata(yazim):
    with pytest.raises(GeometryError):
        parse_thread(yazim)


def test_k6_tapped_kor_varsayilan_dis_derinligi():
    """M8 kör, t = 15: d_m = 8 − 1.25 = 6.75; thread_depth = depth."""
    p0 = blok()
    p = tapped_hole(p0, 30.0, 30.0, "M8", depth=15.0)
    d_m = 8.0 - 1.25
    assert p0.volume - p.volume == pytest.approx(dV_cyl(d_m, 15.0), rel=REL)
    assert len(p.holes) == 1
    kayit_bekle(
        p.holes[0], [30.0, 30.0, C], ASAGI, d_m, 15.0, False,
        thread="M8", thread_d=8.0, pitch=1.25, thread_depth=15.0,
    )  # fmt: skip


def test_k6_tapped_ince_boydan_boya():
    """M10x1 boydan boya: d_m = 9; thread_depth = parça yüksekliği."""
    p0 = blok()
    p = tapped_hole(p0, 70.0, 30.0, "M10x1")
    assert p0.volume - p.volume == pytest.approx(dV_cyl(9.0, C), rel=REL)
    kayit_bekle(
        p.holes[0], [70.0, 30.0, C], ASAGI, 9.0, C, True,
        thread="M10x1", thread_d=10.0, pitch=1.0, thread_depth=C,
    )  # fmt: skip


def test_k6_tapped_acik_dis_derinligi():
    p0 = blok()
    p = tapped_hole(p0, 50.0, 30.0, "M6", depth=15.0, thread_depth=10.0)
    assert p0.volume - p.volume == pytest.approx(dV_cyl(5.0, 15.0), rel=REL)
    h = p.holes[0]
    assert h.depth == pytest.approx(15.0)
    assert h.thread_depth == pytest.approx(10.0)
    assert h.d == pytest.approx(5.0)


@pytest.mark.parametrize(
    "thread, kw",
    [
        ("M8", {"depth": 15.0, "thread_depth": 16.0}),  # thread_depth > depth
        ("M8", {"thread_depth": 21.0}),  # boydan boya, thread_depth > yükseklik
        ("M7", {"depth": 10.0}),  # tabloda yok
        ("M8x", {"depth": 10.0}),  # bozuk yazım
        ("M8", {"depth": 25.0}),  # depth > yükseklik
    ],
)
def test_k6_tapped_gecersiz_girdi_hata(thread, kw):
    p0 = blok()
    with pytest.raises(GeometryError):
        tapped_hole(p0, 50.0, 30.0, thread, **kw)
    assert p0.volume == pytest.approx(V0, rel=1e-12)


# --- K7 inclined_hole ---------------------------------------------------------------------------

D_IN = 8.0  # r = 4
P_UST = np.array([40.0, 30.0, C])  # üst yüzde giriş noktası


def yon(theta: float) -> np.ndarray:
    """−Z ile θ derece açı yapan birim yön, XZ düzleminde +X'e eğik."""
    t = math.radians(theta)
    return np.array([math.sin(t), 0.0, -math.cos(t)])


@pytest.mark.parametrize("theta", [0.0, 30.0, 45.0])
def test_k7_inclined_boydan_boya_cavalieri(theta):
    """ΔV = π r² c / cos θ; kayıt depth = c / cos θ (eksenin parça içindeki boyu)."""
    p0 = blok()
    n = yon(theta)
    p = inclined_hole(p0, P_UST, n, D_IN)
    r = D_IN / 2
    cos_t = math.cos(math.radians(theta))
    assert p0.volume - p.volume == pytest.approx(math.pi * r**2 * C / cos_t, rel=REL)
    assert len(p.holes) == 1
    kayit_bekle(p.holes[0], P_UST, n, D_IN, C / cos_t, True)


@pytest.mark.parametrize("theta", [0.0, 30.0])
def test_k7_inclined_kor_duz_dip(theta):
    """Kör, eksen boyunca t = 12 (t > r tan θ): ΔV = π r² t."""
    p0 = blok()
    n = yon(theta)
    t = 12.0
    p = inclined_hole(p0, P_UST, n, D_IN, depth=t)
    assert p0.volume - p.volume == pytest.approx(math.pi * (D_IN / 2) ** 2 * t, rel=REL)
    kayit_bekle(p.holes[0], P_UST, n, D_IN, t, False)


def test_k7_inclined_yon_normalize_edilir():
    """n birim olmasa da kayıttaki axis birimdir ve hacim aynıdır."""
    p0 = blok()
    n = yon(30.0)
    p = inclined_hole(p0, P_UST, 5.0 * n, D_IN)
    assert p0.volume - p.volume == pytest.approx(math.pi * 16.0 * C / math.cos(math.radians(30.0)), rel=REL)
    np.testing.assert_allclose(p.holes[0].axis, n, atol=1e-9)


def test_k7_inclined_yan_yuzden_boydan_boya():
    """Yan yüzden (x = 0) +X yönünde boydan boya: ΔV = π r² a, depth = a."""
    p0 = blok()
    p_yan = np.array([0.0, 30.0, 10.0])
    n = np.array([1.0, 0.0, 0.0])
    d = 6.0
    p = inclined_hole(p0, p_yan, n, d)
    assert p0.volume - p.volume == pytest.approx(math.pi * 9.0 * A, rel=REL)
    kayit_bekle(p.holes[0], p_yan, n, d, A, True)


@pytest.mark.parametrize(
    "p, n",
    [
        ([40.0, 30.0, 25.0], [0.0, 0.0, -1.0]),  # p parçanın üstünde, yüzeyde değil
        ([40.0, 30.0, 10.0], [0.0, 0.0, -1.0]),  # p parçanın içinde, yüzeyde değil
        ([40.0, 30.0, C + 1e-3], [0.0, 0.0, -1.0]),  # yüzeye 1e-3 mm > 1e-6 mm
        ([40.0, 30.0, C], [0.0, 0.0, 0.0]),  # |n| = 0
        ([40.0, 30.0, C], [0.0, 0.0, 1.0]),  # n malzemeden dışa
        ([40.0, 30.0, C], [0.5, 0.0, 0.5]),  # n dışa eğik
    ],
)
def test_k7_inclined_gecersiz_girdi_hata(p, n):
    p0 = blok()
    with pytest.raises(GeometryError):
        inclined_hole(p0, np.array(p), np.array(n), D_IN)
    assert p0.volume == pytest.approx(V0, rel=1e-12)


# --- K8 kayıt zinciri ---------------------------------------------------------------------------


def test_k8_kayit_zinciri():
    """blok → hole → countersink → counterbore → tapped → inclined → chamfer_top → fillet_vertical.

    Sonda 5 kayıt sırayla taşınır; her ara parça kendi anındaki kayıtları korur (girdi değişmez).
    Delikler birbirinden ve köşelerden uzak; eğimli delik yan yüzden girer (ağzı üst yüzde değil).
    """
    p0 = blok()
    p1 = hole(p0, 15.0, 15.0, 6.0)  # boydan boya düz delik
    p2 = countersink_hole(p1, 40.0, 15.0, 6.6, 13.0)  # boydan boya, 90°
    p3 = counterbore_hole(p2, 65.0, 15.0, screw="M6")  # boydan boya
    p4 = tapped_hole(p3, 40.0, 45.0, "M8", depth=15.0)
    p_yan = np.array([0.0, 45.0, 10.0])
    n_yan = yon(60.0)  # (sin 60°, 0, −cos 60°): yan yüzden (x = 0) içeri, aşağı eğik
    p5 = inclined_hole(p4, p_yan, n_yan, 5.0, depth=10.0)
    # pah 1 + fillet 2: ham OCCT ön denemesinde bu çift kurulabiliyor (pah 0.5 + fillet 2 kurulamıyor)
    p6 = chamfer_top(p5, 1.0)
    p7 = fillet_vertical(p6, 2.0)

    zincir = [p0, p1, p2, p3, p4, p5, p6, p7]
    beklenen_sayi = [0, 1, 2, 3, 4, 5, 5, 5]
    assert [len(p.holes) for p in zincir] == beklenen_sayi

    h = p7.holes
    kayit_bekle(h[0], [15.0, 15.0, C], ASAGI, 6.0, C, True)
    kayit_bekle(h[1], [40.0, 15.0, C], ASAGI, 6.6, C, True, csk_d=13.0, csk_angle=90.0)
    kayit_bekle(h[2], [65.0, 15.0, C], ASAGI, 6.6, C, True, cbore_d=11.0, cbore_depth=6.4)
    kayit_bekle(
        h[3], [40.0, 45.0, C], ASAGI, 6.75, 15.0, False,
        thread="M8", thread_d=8.0, pitch=1.25, thread_depth=15.0,
    )  # fmt: skip
    kayit_bekle(h[4], p_yan, n_yan, 5.0, 10.0, False)

    # ara parçaların kayıtları son parçanınkiyle aynı sırada ve aynı değerde
    for p in zincir[1:]:
        for k_ara, k_son in zip(p.holes, h, strict=False):
            np.testing.assert_allclose(k_ara.origin, k_son.origin)
            np.testing.assert_allclose(k_ara.axis, k_son.axis)
            assert (k_ara.d, k_ara.depth, k_ara.through) == (k_son.d, k_son.depth, k_son.through)
            assert (k_ara.csk_d, k_ara.cbore_d, k_ara.thread) == (k_son.csk_d, k_son.cbore_d, k_son.thread)

    # her işlem malzeme kaldırdı, girdi hacmi değişmedi
    hacimler = [p.volume for p in zincir]
    assert all(v1 > v2 for v1, v2 in zip(hacimler, hacimler[1:], strict=False))
    assert p0.volume == pytest.approx(V0, rel=1e-12)
