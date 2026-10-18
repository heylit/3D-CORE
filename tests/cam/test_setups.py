"""SPEC 14 — ham malzeme, iş sıfırı, güvenli yükseklik ve bağlama denetimi: K6, K7, K8.

Testler sadece SPEC 14 metninden yazıldı; `cam/setups.py` uygulama kodu okunmadı.

Bağlama denetimi (SPEC 14 Teori): takım ucu noktası, ρ = R + h/2 kadar şişirilmiş engel; h = 0.25 mm.
Freze D = 6 → ρ = 3.125. Kutu bağlama elemanı [xmin − ρ, xmax + ρ] × [ymin − ρ, ymax + ρ] × [−∞, zmax + h/2].
Testlerde kullanılan mengene çenesi (Ek A): Stock(-15, 0, -20, -5, 40, 10),
ham malzeme Stock(0, 0, -20, 50, 40, 0).
Çarpışma bölgesi x ∈ [−18.125, −1.875], y ∈ [−3.125, 43.125], z ≤ 10.125.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from cam.gcode import DrillOp
from cam.model import (
    CamError,
    CylinderStock,
    LatheTool,
    LatheToolKind,
    Move,
    MoveType,
    Plane,
    Setup,
    Stock,
    Tool,
    ToolKind,
    Toolpath,
    Wcs,
)
from cam.setups import (
    CLEARANCE,
    CLEARANCE_R,
    SAMPLE_STEP,
    bar_stock_from_bbox,
    check_setup,
    clearance_height,
    edge_position,
    safe_radius,
    stock_from_bbox,
    wcs_from_touch,
)

G0, G1, G2, G3 = MoveType.RAPID, MoveType.LINEAR, MoveType.ARC_CW, MoveType.ARC_CCW
NAN = float("nan")


def test_sabitler():
    assert CLEARANCE == 5.0
    assert CLEARANCE_R == 2.0
    assert SAMPLE_STEP == 0.25


# ---------------------------------------------------------------- K6 ham malzeme


def test_stock_from_bbox_paysiz():
    s = stock_from_bbox((0.0, 0.0, -10.0), (100.0, 50.0, 0.0))
    assert s == Stock(0.0, 0.0, -10.0, 100.0, 50.0, 0.0)


def test_stock_from_bbox_tek_sayi_pay():
    s = stock_from_bbox(np.array([0.0, 0.0, -10.0]), np.array([100.0, 50.0, 0.0]), margin=2.0)
    assert s == Stock(-2.0, -2.0, -12.0, 102.0, 52.0, 2.0)


def test_stock_from_bbox_eksen_basina_pay():
    s = stock_from_bbox((0.0, 0.0, -10.0), (100.0, 50.0, 0.0), margin=(1.0, 2.0, 3.0))
    assert s == Stock(-1.0, -2.0, -13.0, 101.0, 52.0, 3.0)


@pytest.mark.parametrize("margin", [-1.0, (1.0, -2.0, 0.0), NAN, (0.0, 0.0, NAN)])
def test_stock_from_bbox_gecersiz_pay(margin):
    with pytest.raises(CamError):
        stock_from_bbox((0.0, 0.0, -10.0), (100.0, 50.0, 0.0), margin=margin)


def test_stock_from_bbox_nan_kutu():
    with pytest.raises(CamError):
        stock_from_bbox((0.0, NAN, -10.0), (100.0, 50.0, 0.0))


# dönel parça: en uzak yanal nokta |xmin| = 12 → D = 24
BMIN = (-12.0, -10.0, -50.0)
BMAX = (10.0, 11.0, 0.0)


def test_bar_stock_paysiz():
    c = bar_stock_from_bbox(BMIN, BMAX)
    assert isinstance(c, CylinderStock)
    assert c.D == pytest.approx(24.0)
    assert c.zmin == pytest.approx(-50.0)
    assert c.zmax == pytest.approx(0.0)
    assert c.d == 0.0


def test_bar_stock_yaricap_payi():
    c = bar_stock_from_bbox(BMIN, BMAX, margin_r=1.0)
    assert c.D == pytest.approx(26.0)


def test_bar_stock_y_ekseni_de_sayilir():
    c = bar_stock_from_bbox((-5.0, -15.0, 0.0), (5.0, 3.0, 10.0))
    assert c.D == pytest.approx(30.0)


def test_bar_stock_z_payi_boyu_uzatir():
    c = bar_stock_from_bbox(BMIN, BMAX, margin_z=3.0)
    assert c.zmin <= -50.0
    assert c.zmax >= 0.0
    assert c.length > 50.0


def test_bar_stock_standart_cap():
    std = [20.0, 25.0, 30.0, 40.0]
    assert bar_stock_from_bbox(BMIN, BMAX, standard=std).D == 25.0  # 24 → 25
    assert bar_stock_from_bbox(BMIN, BMAX, margin_r=1.0, standard=std).D == 30.0  # 26 → 30
    assert bar_stock_from_bbox(BMIN, BMAX, margin_r=0.5, standard=std).D == 25.0  # tam 25 → 25 (≥)


def test_bar_stock_standart_sirasiz():
    assert bar_stock_from_bbox(BMIN, BMAX, standard=[40.0, 30.0, 25.0, 20.0]).D == 25.0


def test_bar_stock_uygun_standart_yok():
    with pytest.raises(CamError):
        bar_stock_from_bbox(BMIN, BMAX, standard=[10.0, 16.0, 20.0])


@pytest.mark.parametrize(("margin_r", "margin_z"), [(-1.0, 0.0), (0.0, -1.0), (NAN, 0.0)])
def test_bar_stock_gecersiz_pay(margin_r, margin_z):
    with pytest.raises(CamError):
        bar_stock_from_bbox(BMIN, BMAX, margin_r=margin_r, margin_z=margin_z)


# ---------------------------------------------------------------- K6 iş sıfırı


def test_wcs_from_touch():
    w = wcs_from_touch("G55", (-250.0, -190.0, -80.0), (0.0, 0.0, 0.0))
    assert isinstance(w, Wcs)
    assert w.code == "G55"
    np.testing.assert_allclose(w.origin, (-250.0, -190.0, -80.0), atol=1e-12)


def test_wcs_from_touch_is_noktasi_sifir_degil():
    """Makinede (-240, -185, -78) dokunulan nokta iş koordinatında (10, 5, 2) → origin = m − w."""
    w = wcs_from_touch("G54", (-240.0, -185.0, -78.0), (10.0, 5.0, 2.0))
    np.testing.assert_allclose(w.origin, (-250.0, -190.0, -80.0), atol=1e-12)
    np.testing.assert_allclose(w.to_machine((10.0, 5.0, 2.0)), (-240.0, -185.0, -78.0), atol=1e-12)


@pytest.mark.parametrize("code", ["G53", "G60", "g54", ""])
def test_wcs_from_touch_gecersiz_kod(code):
    with pytest.raises(CamError):
        wcs_from_touch(code, (0.0, 0.0, 0.0), (0.0, 0.0, 0.0))


def test_wcs_from_touch_nan():
    with pytest.raises(CamError):
        wcs_from_touch("G54", (NAN, 0.0, 0.0), (0.0, 0.0, 0.0))


def test_edge_position():
    assert edge_position(-100.0, 6.0, 1) == pytest.approx(-97.0)
    assert edge_position(-100.0, 6.0, -1) == pytest.approx(-103.0)
    assert edge_position(25.0, 10.0, 1) == pytest.approx(30.0)
    assert edge_position(25.0, 0.0, -1) == pytest.approx(25.0)


@pytest.mark.parametrize(("d", "yon"), [(6.0, 0), (6.0, 2), (6.0, -2), (-1.0, 1), (NAN, 1)])
def test_edge_position_gecersiz(d, yon):
    with pytest.raises(CamError):
        edge_position(-100.0, d, yon)


# ---------------------------------------------------------------- kurulumlar


STOK = Stock(0.0, 0.0, -20.0, 50.0, 40.0, 0.0)
CENE = Stock(-15.0, 0.0, -20.0, -5.0, 40.0, 10.0)  # mengene çenesi, üstü z = 10


def freze_kurulum() -> Setup:
    return Setup("on-yuz", Wcs("G55", (-250.0, -190.0, -80.0)), STOK, fixtures=[CENE])


def freze6(flute_length: float = 20.0, id: int = 1) -> Tool:
    return Tool(id, "freze6", ToolKind.FLAT, D=6.0, flute_length=flute_length, flutes=3)


def matkap5() -> Tool:
    return Tool(2, "matkap5", ToolKind.DRILL, D=5.0, flute_length=40.0, flutes=2)


def yol(name: str, tool, start, moves, **kw) -> Toolpath:
    return Toolpath(name, tool, start, moves, rpm=kw.pop("rpm", 8000), **kw)


AYNA = CylinderStock(D=100.0, zmin=-100.0, zmax=-60.0)  # torna aynası
CUBUK = CylinderStock(D=40.0, zmin=-60.0, zmax=0.0)


def torna_kurulum(fixtures=None) -> Setup:
    return Setup("torna", Wcs("G54"), CUBUK, fixtures=[AYNA] if fixtures is None else fixtures)


def torna_ucu() -> LatheTool:
    return LatheTool(10, "tornalama", LatheToolKind.TURN, nose_r=0.8, tip=3, kappa_r=95.0, eps_r=80.0)


# ---------------------------------------------------------------- K7 güvenli yükseklik


def test_clearance_height_en_yuksek_baglama_elemani():
    assert clearance_height(freze_kurulum()) == pytest.approx(15.0)  # çene üstü 10 + 5
    assert clearance_height(freze_kurulum(), clearance=10.0) == pytest.approx(20.0)


def test_clearance_height_baglamasiz_ham_malzeme_ustu():
    s = Setup("tek", Wcs(), STOK)
    assert clearance_height(s) == pytest.approx(5.0)


def test_clearance_height_ham_malzeme_baglamadan_yuksek():
    alcak = Stock(-15.0, 0.0, -20.0, -5.0, 40.0, -5.0)
    s = Setup("alcak", Wcs(), STOK, fixtures=[alcak])
    assert clearance_height(s) == pytest.approx(5.0)


def test_clearance_height_silindir():
    assert clearance_height(torna_kurulum()) == pytest.approx(5.0)  # çubuk zmax 0


def test_safe_radius_silindir_ayna():
    assert safe_radius(torna_kurulum()) == pytest.approx(52.0)  # ayna R 50 + 2
    assert safe_radius(torna_kurulum(), clearance=5.0) == pytest.approx(55.0)


def test_safe_radius_baglamasiz():
    assert safe_radius(torna_kurulum(fixtures=[])) == pytest.approx(22.0)  # çubuk R 20 + 2


def test_safe_radius_kutu_baglama_elemani_kose():
    kutu = Stock(-30.0, -40.0, -90.0, 30.0, 40.0, -60.0)  # köşe hypot(30, 40) = 50
    assert safe_radius(torna_kurulum(fixtures=[kutu])) == pytest.approx(52.0)
    asimetrik = Stock(-60.0, -10.0, -90.0, 20.0, 10.0, -60.0)
    assert safe_radius(torna_kurulum(fixtures=[asimetrik])) == pytest.approx(math.hypot(60.0, 10.0) + 2.0)


# ---------------------------------------------------------------- K8 bağlama denetimi: geçen yollar


def test_cene_yaninda_R_arti_0_2_gecer():
    """Çene yüzü x = −5; takım ucu x = −5 + 3 + 0.2 = −1.8 boyunca Y'de iner/ilerler: ρ = 3.125 < 3.2."""
    x = -5.0 + 3.0 + 0.2
    tp = yol(
        "yaklas",
        freze6(),
        (x, -10.0, 15.0),
        [
            Move(G0, (x, -10.0, 2.0)),
            Move(G1, (x, -10.0, -1.0), 100.0),
            Move(G1, (x, 50.0, -1.0), 300.0),
            Move(G0, (x, 50.0, 15.0)),
        ],
    )
    check_setup(freze_kurulum(), [tp])


def test_cene_ustunden_gecer():
    """Uç z = 11 > 10.125: takım çenenin üstünden geçebilir."""
    tp = yol(
        "ust",
        freze6(),
        (25.0, 20.0, 15.0),
        [Move(G0, (25.0, 20.0, 11.0)), Move(G1, (-30.0, 20.0, 11.0), 500.0)],
    )
    check_setup(freze_kurulum(), [tp])


def test_cw_yay_cene_tarafina_gitmez_gecer():
    """Merkez (5, 20), r = 9: G2 (5, 29) → (5, 11) sağdan (x = 14) döner, çeneye yaklaşmaz."""
    tp = yol(
        "yay",
        freze6(),
        (5.0, 29.0, 15.0),
        [Move(G1, (5.0, 29.0, -1.0), 100.0), Move(G2, (5.0, 11.0, -1.0), 300.0, center=(5.0, 20.0))],
    )
    check_setup(freze_kurulum(), [tp])


def test_stok_tabanina_kadar_gecer():
    """z = zmin = −20 tabla üstüdür (ihlal z < zmin); kesici boy 40 ≥ 20."""
    tp = yol("dip", freze6(flute_length=40.0), (25.0, 20.0, 15.0), [Move(G1, (25.0, 20.0, -20.0), 100.0)])
    check_setup(freze_kurulum(), [tp])


def test_kesici_boya_esit_derinlik_gecer():
    tp = yol("derin", freze6(flute_length=10.0), (25.0, 20.0, 15.0), [Move(G1, (25.0, 20.0, -10.0), 100.0)])
    check_setup(freze_kurulum(), [tp])


def test_delik_op_gecer():
    op = DrillOp(
        "delik",
        matkap5(),
        rpm=3000,
        start=(20.0, 20.0, 15.0),
        holes=[(20.0, 20.0), (40.0, 30.0)],
        z=-5.0,
        r=2.0,
        feed=150.0,
    )
    check_setup(freze_kurulum(), [op])


def test_torna_yolu_aynadan_uzak_gecer():
    tp = yol(
        "dis-cap",
        torna_ucu(),
        (25.0, 0.0, 2.0),
        [
            Move(G0, (19.0, 0.0, 2.0)),
            Move(G1, (19.0, 0.0, -50.0), 0.2),
            Move(G0, (25.0, 0.0, -50.0)),
            Move(G0, (25.0, 0.0, 2.0)),
        ],
        rpm=1000,
        plane=Plane.ZX,
    )
    check_setup(torna_kurulum(), [tp])


# ---------------------------------------------------------------- K8 bağlama denetimi: ihlaller


def test_cene_R_den_yakin_hata_mesajda_op_adi():
    x = -5.0 + 2.9  # çene yüzüne 2.9 < R = 3
    tp = yol(
        "yaklas",
        freze6(),
        (x, -10.0, 15.0),
        [Move(G0, (x, -10.0, 2.0)), Move(G1, (x, -10.0, -1.0), 100.0), Move(G1, (x, 50.0, -1.0), 300.0)],
    )
    with pytest.raises(CamError) as e:
        check_setup(freze_kurulum(), [tp])
    assert "yaklas" in str(e.value)


def test_uclari_disarida_dogru_ceneyi_keser():
    """Uç noktalar çarpışma bölgesinin dışında, aradaki doğru çenenin içinden geçiyor (örnekleme)."""
    tp = yol(
        "gecis",
        freze6(),
        (-30.0, 20.0, 15.0),
        [Move(G0, (-30.0, 20.0, 5.0)), Move(G1, (20.0, 20.0, 5.0), 500.0)],
    )
    with pytest.raises(CamError):
        check_setup(freze_kurulum(), [tp])


def test_hizli_hareket_cenede_hata():
    tp = yol("hizli", freze6(), (25.0, 20.0, 15.0), [Move(G0, (-10.0, 20.0, 5.0))])
    with pytest.raises(CamError):
        check_setup(freze_kurulum(), [tp])


def test_cene_ustu_alcak_gecis_hata():
    tp = yol(
        "ust",
        freze6(),
        (25.0, 20.0, 15.0),
        [Move(G0, (25.0, 20.0, 9.0)), Move(G1, (-30.0, 20.0, 9.0), 500.0)],
    )
    with pytest.raises(CamError):
        check_setup(freze_kurulum(), [tp])


def test_ccw_yay_ceneyi_siyirir():
    """Merkez (5, 20), r = 9: G3 (5, 29) → (5, 11) soldan döner; en sol x = −4, çene yüzüne 1 mm.
    Yayın uç noktaları çeneden 10 mm uzakta: yay örneklenmeli."""
    tp = yol(
        "yay",
        freze6(),
        (5.0, 29.0, 15.0),
        [Move(G1, (5.0, 29.0, -1.0), 100.0), Move(G3, (5.0, 11.0, -1.0), 300.0, center=(5.0, 20.0))],
    )
    with pytest.raises(CamError):
        check_setup(freze_kurulum(), [tp])


def test_stok_altina_inen_yol_hata():
    tp = yol("dalis", freze6(flute_length=40.0), (25.0, 20.0, 15.0), [Move(G1, (25.0, 20.0, -21.0), 100.0)])
    with pytest.raises(CamError) as e:
        check_setup(freze_kurulum(), [tp])
    assert "dalis" in str(e.value)


def test_kesici_boydan_derin_kesim_hata():
    tp = yol("derin", freze6(flute_length=10.0), (25.0, 20.0, 15.0), [Move(G1, (25.0, 20.0, -12.0), 100.0)])
    with pytest.raises(CamError) as e:
        check_setup(freze_kurulum(), [tp])
    assert "derin" in str(e.value)


def test_delik_op_cenede_hata():
    """Delik (−3, 20): çene yüzüne 2 < R = 2.5; kanonik açılımla denetlenir."""
    op = DrillOp(
        "delik",
        matkap5(),
        rpm=3000,
        start=(20.0, 20.0, 15.0),
        holes=[(20.0, 20.0), (-3.0, 20.0)],
        z=-5.0,
        r=2.0,
        feed=150.0,
    )
    with pytest.raises(CamError):
        check_setup(freze_kurulum(), [op])


def test_ikinci_op_ihlalinde_hata():
    iyi = yol("iyi", freze6(), (25.0, 20.0, 15.0), [Move(G1, (25.0, 20.0, -1.0), 100.0)])
    kotu = yol("kotu", freze6(), (25.0, 20.0, 15.0), [Move(G0, (-10.0, 20.0, 5.0))])
    with pytest.raises(CamError) as e:
        check_setup(freze_kurulum(), [iyi, kotu])
    assert "kotu" in str(e.value)


def test_torna_yolu_aynaya_girer():
    tp = yol(
        "dis-cap",
        torna_ucu(),
        (25.0, 0.0, 2.0),
        [Move(G0, (19.0, 0.0, 2.0)), Move(G1, (19.0, 0.0, -62.0), 0.2)],
        rpm=1000,
        plane=Plane.ZX,
    )
    with pytest.raises(CamError):
        check_setup(torna_kurulum(), [tp])
