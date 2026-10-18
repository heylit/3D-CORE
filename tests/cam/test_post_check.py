"""SPEC 30 — tezgâh sınır denetimi `check_machine` ve `machine_extents` (K5–K10).

Testler SPEC 30 metninden (Teori "Tezgâh koordinatı ve takım boyu", "Yayların kursu", "Devir ve
ilerleme sınırı", "Takım ve program numarası"; Arayüz "Denetim"; K5–K10) yazıldı.

Kurs kuralları (Teori): x + ox ∈ [xmin, xmax], y + oy ∈ [ymin, ymax], z + oz + L ∈ [zmin, zmax];
L = Tool.gauge_length. Yayda süpürülen eksen yönü noktaları c + r·(cos θ, sin θ), θ ∈ {0, π/2, π, 3π/2}.
"""

from __future__ import annotations

import re
from dataclasses import replace

import pytest

from cam.gcode import DrillOp
from cam.model import CamError, FeedMode, Move, Toolpath
from cam.post import AxisLimits, check_machine, machine_extents, post
from tests.cam.post_ortak import G0, G1, G2, G3, altin_yol, boysuz, kurulum, n_siz, profil, satirlar, takim


def sira_var(mesaj: str, n: int) -> bool:
    """Mesajda `n` (1 tabanlı hareket sırası) ayrı sayı olarak geçiyor mu (400.001 içindeki 4 sayılmaz)."""
    return re.search(rf"(?<![\d.]){n}(?![\d.])", mesaj) is not None


def yol(name: str, moves: list[Move], start=(0.0, 0.0, 5.0), rpm: float = 6000.0, tool=None) -> Toolpath:
    return Toolpath(name, tool or boysuz(1), start, moves, rpm=rpm)


# ---------------------------------------------------------------- K5: doğrusal kurs

X500 = dict(x=AxisLimits(0.0, 500.0))  # yalnız X kursu: Z kursu yok → takım boyu gerekmez
O100 = (100.0, 0.0, 0.0)


def x_yolu(x: float, hizli: bool = False) -> Toolpath:
    """Dördüncü hareket (sıra 4) X = x noktasına gider; öncekiler kurs içinde."""
    son = Move(G0, (x, 0.0, 5.0)) if hizli else Move(G1, (x, 0.0, -1.0), feed=500.0)
    return yol(
        "kurs-x",
        [
            Move(G1, (0.0, 0.0, -1.0), feed=100.0),
            Move(G1, (50.0, 0.0, -1.0), feed=500.0),
            Move(G0 if hizli else G1, (50.0, 0.0, 5.0 if hizli else -1.0), feed=None if hizli else 500.0),
            son,
        ],
    )


def test_K5_linear_inside_travel_passes():
    """K5: X kursu [0, 500], origin_x = 100: x = 400 → makinede 500, sınırda, geçer."""
    check_machine(profil(**X500), [x_yolu(400.0)], kurulum(O100))


def test_K5_linear_outside_travel():
    """K5: x = 400.001 → 500.001 > 500: CamError; mesajda op adı ve hareket sırası (4)."""
    with pytest.raises(CamError) as e:
        check_machine(profil(**X500), [x_yolu(400.001)], kurulum(O100))
    assert "kurs-x" in str(e.value)
    assert sira_var(str(e.value), 4), str(e.value)


def test_K5_lower_bound():
    """K5: x = −100 → makinede 0 geçer; −100.001 → CamError."""
    check_machine(profil(**X500), [x_yolu(-100.0)], kurulum(O100))
    with pytest.raises(CamError):
        check_machine(profil(**X500), [x_yolu(-100.001)], kurulum(O100))


def test_K5_rapid_is_checked():
    """K5: G0 hareketi de denetlenir (kursun dışına hızlı gitmek de çarpmadır)."""
    check_machine(profil(**X500), [x_yolu(400.0, hizli=True)], kurulum(O100))
    with pytest.raises(CamError) as e:
        check_machine(profil(**X500), [x_yolu(400.001, hizli=True)], kurulum(O100))
    assert "kurs-x" in str(e.value)
    assert sira_var(str(e.value), 4), str(e.value)


def test_K5_y_second_op_violation():
    """Y kursu da denetlenir; hata ikinci op'taysa mesajda onun adı ve o op içindeki sıra (2)."""
    m = profil(y=AxisLimits(-50.0, 50.0))
    ilk = yol("birinci", [Move(G1, (0.0, 40.0, -1.0), feed=100.0)])
    ikinci = yol(
        "ikinci", [Move(G1, (0.0, 0.0, -1.0), feed=100.0), Move(G1, (0.0, -60.001, -1.0), feed=100.0)]
    )
    check_machine(m, [ilk, replace(ikinci, moves=ikinci.moves[:1])], kurulum((0.0, 10.0, 0.0)))
    with pytest.raises(CamError) as e:
        check_machine(m, [ilk, ikinci], kurulum((0.0, 10.0, 0.0)))
    assert "ikinci" in str(e.value)
    assert sira_var(str(e.value), 2), str(e.value)


def test_K5_post_does_not_write_out_of_travel():
    """`post` önce denetler: kurs dışı → CamError, metin üretilmez."""
    with pytest.raises(CamError):
        post([x_yolu(400.001)], profil(**X500), kurulum(O100))


# ---------------------------------------------------------------- K6: yayların kursu

XY = dict(x=AxisLimits(0.0, 500.0), y=AxisLimits(-100.0, 100.0))
C = (490.0, 0.0)  # r = 20: 0° noktası (510, 0) kurs dışında, uçlar (490, ±20) içinde


def yay_yolu(tip, bas, son, merkez) -> Toolpath:
    return yol(
        "yay",
        [
            Move(G1, (bas[0], bas[1], -1.0), feed=100.0),
            Move(tip, (son[0], son[1], -1.0), feed=300.0, center=merkez),
            Move(G0, (son[0], son[1], 5.0)),
        ],
        start=(bas[0], bas[1], 5.0),
    )


def test_K6_ccw_arc_sweeping_0deg():
    """K6: G3 (490, −20) → (490, 20), merkez (490, 0): 0° noktası süpürülür → CamError (hareket 2)."""
    with pytest.raises(CamError) as e:
        check_machine(profil(**XY), [yay_yolu(G3, (490.0, -20.0), (490.0, 20.0), C)], kurulum())
    assert "yay" in str(e.value)
    assert sira_var(str(e.value), 2), str(e.value)


def test_K6_cw_arc_sweeping_0deg():
    """K6: G2 (490, 20) → (490, −20): saat yönünde 0°'den geçer → CamError."""
    with pytest.raises(CamError):
        check_machine(profil(**XY), [yay_yolu(G2, (490.0, 20.0), (490.0, -20.0), C)], kurulum())


def test_K6_reverse_arcs_pass():
    """K6: aynı yayların tersi 180° tarafından döner (0° süpürülmez, en büyük x = 490) → geçer."""
    check_machine(profil(**XY), [yay_yolu(G2, (490.0, -20.0), (490.0, 20.0), C)], kurulum())
    check_machine(profil(**XY), [yay_yolu(G3, (490.0, 20.0), (490.0, -20.0), C)], kurulum())


@pytest.mark.parametrize(
    "aci,merkez,bas",
    [
        ("0", (490.0, 0.0), (490.0, 20.0)),  # (510, 0) dışarıda
        ("90", (250.0, 90.0), (250.0, 70.0)),  # (250, 110) dışarıda
        ("180", (10.0, 0.0), (10.0, 20.0)),  # (−10, 0) dışarıda
        ("270", (250.0, -90.0), (250.0, -70.0)),  # (250, −110) dışarıda
    ],
)
@pytest.mark.parametrize("tip", [G2, G3], ids=["G2", "G3"])
def test_K6_full_circle_checks_all_four_points(aci, merkez, bas, tip):
    """K6: tam daire (başlangıç = bitiş) dört eksen yönü noktasının hepsini içerir."""
    with pytest.raises(CamError):
        check_machine(profil(**XY), [yay_yolu(tip, bas, bas, merkez)], kurulum())


def test_K6_full_circle_inside_passes():
    check_machine(profil(**XY), [yay_yolu(G3, (250.0, 20.0), (250.0, 20.0), (250.0, 0.0))], kurulum())


def test_K6_arc_with_origin_offset():
    """Yay noktaları da makineye `origin` ile taşınır: merkez (390, 0) + ox 100 → 0° noktası 510."""
    op = yay_yolu(G3, (390.0, -20.0), (390.0, 20.0), (390.0, 0.0))
    with pytest.raises(CamError):
        check_machine(profil(**XY), [op], kurulum((100.0, 0.0, 0.0)))
    check_machine(profil(**XY), [op], kurulum())


def test_K6_drill_op_canonical_expansion_checked():
    """Delik op'ları kanonik açılımıyla denetlenir: delik X'i kurs dışındaysa CamError."""
    m = profil(**XY)
    op = DrillOp("delik", takim(1), rpm=3000.0, start=(0.0, 0.0, 5.0), holes=[(10.0, 0.0), (500.0, 0.0)],
                 z=-5.0, r=1.0, feed=100.0)  # fmt: skip
    check_machine(m, [op], kurulum())
    with pytest.raises(CamError) as e:
        check_machine(m, [replace(op, holes=[(10.0, 0.0), (500.001, 0.0)])], kurulum())
    assert "delik" in str(e.value)


# ---------------------------------------------------------------- K7: Z kursu ve takım boyu

Z400 = dict(z=AxisLimits(-400.0, 0.0))
OZ = (0.0, 0.0, -350.0)  # z_ölçü = z − 350 + 100 = z − 250


def z_yolu(z: float, tool=None) -> Toolpath:
    """Üçüncü hareket Z = z'ye iner/çıkar; diğer noktalar kurs içinde (z_ölçü ∈ (−400, 0))."""
    return yol(
        "kurs-z",
        [
            Move(G1, (0.0, 0.0, 0.0), feed=100.0),
            Move(G1, (10.0, 0.0, 0.0), feed=300.0),
            Move(G1, (10.0, 0.0, z), feed=100.0),
        ],
        tool=tool or takim(1, L=100.0),
    )


def test_K7_upper_z():
    """K7: z = 250 → z_ölçü = 0 geçer; 250.001 → CamError (hareket 3)."""
    check_machine(profil(**Z400), [z_yolu(250.0)], kurulum(OZ))
    with pytest.raises(CamError) as e:
        check_machine(profil(**Z400), [z_yolu(250.001)], kurulum(OZ))
    assert "kurs-z" in str(e.value)
    assert sira_var(str(e.value), 3), str(e.value)


def test_K7_lower_z():
    """K7: z = −150 → z_ölçü = −400 geçer; −150.001 → CamError."""
    check_machine(profil(**Z400), [z_yolu(-150.0)], kurulum(OZ))
    with pytest.raises(CamError):
        check_machine(profil(**Z400), [z_yolu(-150.001)], kurulum(OZ))


def test_K7_gauge_length_shifts_z():
    """L takım boyu: aynı yol L = 100.001 ile üst sınırı aşar (z_ölçü = z + oz + L)."""
    check_machine(profil(**Z400), [z_yolu(250.0, takim(1, L=100.0))], kurulum(OZ))
    with pytest.raises(CamError):
        check_machine(profil(**Z400), [z_yolu(250.0, takim(1, L=100.001))], kurulum(OZ))


def test_K7_unknown_gauge_length():
    """K7: Z kursu varken gauge_length None → CamError (varsayılan boy kabul edilmez)."""
    with pytest.raises(CamError):
        check_machine(profil(**Z400), [z_yolu(0.0, boysuz(1))], kurulum(OZ))


def test_K7_unknown_gauge_length_without_z_travel_ok():
    """Z kursu yoksa takım boyu gerekmez."""
    check_machine(profil(**X500), [z_yolu(0.0, boysuz(1))], kurulum())


@pytest.mark.parametrize("kurs", [X500, Z400, dict(y=AxisLimits(-1.0, 1.0))], ids=["x", "z", "y"])
def test_K7_setup_required_with_travel(kurs):
    """K7 / teknik karar 3: profilde eksen kursu varken setup yok → CamError (origin 0 kabul edilmez)."""
    with pytest.raises(CamError):
        check_machine(profil(**kurs), [z_yolu(0.0)])
    with pytest.raises(CamError):
        post([z_yolu(0.0)], profil(**kurs))


def test_setup_not_required_without_travel():
    check_machine(profil(), [z_yolu(0.0)])


# ---------------------------------------------------------------- K8: devir ve ilerleme


def test_K8_rpm_max_rounding():
    """K8: rpm_max = 8000: rpm = 8000.4 → S = 8000 geçer ve programda S8000 (kırpma değil, aynı değer)."""
    m = profil(rpm_max=8000.0)
    op = replace(altin_yol(boysuz(1)), rpm=8000.4)
    check_machine(m, [op])
    assert "S8000 M3" in n_siz(post([op], m))


def test_K8_rpm_above_max():
    """K8: S = round(rpm) > rpm_max → CamError; mesajda op adı, sınır ve SPEC 14 `n_max` önerisi.

    Not: K8 metnindeki 8000.5 Python `round` ile 8000'e yuvarlanır (çifte yuvarlama); bu yüzden
    yuvarlaması tartışmasız 8000.6 (S = 8001) kullanıldı."""
    m = profil(rpm_max=8000.0)
    op = replace(altin_yol(boysuz(1)), rpm=8000.6)
    with pytest.raises(CamError) as e:
        check_machine(m, [op])
    assert "altin" in str(e.value)
    assert "8000" in str(e.value)
    assert "n_max" in str(e.value)
    with pytest.raises(CamError):
        post([op], m)  # metin hiç üretilmez


def test_K8_rpm_below_min():
    """K8: rpm_min = 100, rpm = 50 → CamError."""
    with pytest.raises(CamError) as e:
        check_machine(profil(rpm_min=100.0), [replace(altin_yol(boysuz(1)), rpm=50.0)])
    assert "altin" in str(e.value)


def ilerleme_yolu(tip, F: float) -> Toolpath:
    moves = [Move(G1, (0.0, 0.0, -1.0), feed=100.0)]
    if tip is G1:
        moves.append(Move(G1, (10.0, 0.0, -1.0), feed=F))
    else:
        moves.append(Move(tip, (10.0, 0.0, -1.0), feed=F, center=(5.0, 0.0)))
    moves.append(Move(G0, (10.0, 0.0, 5.0)))
    return yol("ilerleme", moves)


@pytest.mark.parametrize("tip", [G1, G2, G3], ids=["G1", "G2", "G3"])
def test_K8_cutting_feed_limit(tip):
    """K8: feed_max = 5000: F = 5000 geçer; 5000.01 → CamError (G1, G2, G3)."""
    m = profil(feed_max=5000.0)
    check_machine(m, [ilerleme_yolu(tip, 5000.0)])
    with pytest.raises(CamError) as e:
        check_machine(m, [ilerleme_yolu(tip, 5000.01)])
    assert "ilerleme" in str(e.value)


def test_K8_drill_feed_limit():
    """K8: DrillOp ilerlemesi de denetlenir."""
    m = profil(feed_max=5000.0)
    op = DrillOp("delik", takim(1), rpm=3000.0, start=(0.0, 0.0, 5.0), holes=[(0.0, 0.0)], z=-5.0, r=1.0,
                 feed=5000.0)  # fmt: skip
    check_machine(m, [op])
    with pytest.raises(CamError):
        check_machine(m, [replace(op, feed=5000.01)])
    with pytest.raises(CamError):
        check_machine(m, [replace(op, feed=5000.01, kind="G83", q=2.0)])


def test_K8_rapid_feed_not_checked():
    """K8: G0 ilerlemesi tezgâhındır; G0 hareketinde feed alanı olsa da denetlenmez."""
    op = yol("hizli", [Move(G1, (0.0, 0.0, -1.0), feed=100.0), Move(G0, (0.0, 0.0, 5.0), feed=99_999.0)])
    check_machine(profil(feed_max=5000.0), [op])


# ---------------------------------------------------------------- K9: takım ve program numarası


def test_K9_tool_slots():
    """K9: tool_slots = 20: T20 geçer, T21 → CamError."""
    m = profil(tool_slots=20)
    check_machine(m, [altin_yol(boysuz(20))])
    with pytest.raises(CamError) as e:
        check_machine(m, [altin_yol(boysuz(21))])
    assert "21" in str(e.value)


def test_K9_manual_tool_change():
    """K9: tool_slots = None (elle değişim) → her T ≥ 1 geçer; T0 → CamError."""
    m = profil(tool_slots=None)
    check_machine(m, [altin_yol(boysuz(99))])
    with pytest.raises(CamError):
        check_machine(m, [altin_yol(boysuz(0))])


def test_K9_drill_tool_number():
    op = DrillOp("delik", takim(21), rpm=3000.0, start=(0.0, 0.0, 5.0), holes=[(0.0, 0.0)], z=-5.0, r=1.0,
                 feed=100.0)  # fmt: skip
    with pytest.raises(CamError):
        check_machine(profil(tool_slots=20), [op])


def test_K9_program_number_range():
    """K9: Fanuc profili aralığı 1–7999: 7999 geçer, 8000 → CamError (check ve post); 0 → CamError."""
    m = profil(program_no_range=(1, 7999))
    op = altin_yol(boysuz(1))
    check_machine(m, [op], program_no=7999)
    with pytest.raises(CamError):
        check_machine(m, [op], program_no=8000)
    with pytest.raises(CamError):
        post([op], m, program_no=8000)
    with pytest.raises(CamError):
        check_machine(m, [op], program_no=0)


def test_K9_haas_program_number_written():
    """K9: Haas `program_no = 12345` → programda `O12345`."""
    m = profil(controller="haas", program_no_range=(1, 99_999))
    ls = satirlar(post([altin_yol(boysuz(1))], m, program_no=12345))
    assert "O12345" in ls


# ---------------------------------------------------------------- op ve profil geçerliliği


def test_ops_are_validated():
    """Arayüz: op'lar önce kendi validate()'inden geçer (rpm = 0 → CamError)."""
    with pytest.raises(CamError):
        check_machine(profil(), [replace(altin_yol(boysuz(1)), rpm=0.0)])


@pytest.mark.parametrize(
    "alan", [{"feed_mode": FeedMode.PER_REV}, {"css": 200.0}], ids=["G95", "G96"]
)  # fmt: skip
def test_lathe_style_ops_rejected_on_mill(alan):
    """Arayüz: G95 / G96 op ve kind = 'mill' → CamError."""
    with pytest.raises(CamError):
        check_machine(profil(), [replace(altin_yol(boysuz(1)), **alan)])


def test_invalid_profile_rejected():
    """Geçersiz profille denetim yapılmaz (feed_max = 0 → CamError)."""
    with pytest.raises(CamError):
        check_machine(profil(feed_max=0.0), [altin_yol(boysuz(1))])


# ---------------------------------------------------------------- K10: machine_extents


def test_K10_extents_golden_path():
    """K10: Ek A yolu (kare + yarım daire, tepe (5, 15)), origin (100.5, −20.25, −300), L = 150:
    x ∈ [100.5, 110.5], y ∈ [−20.25, −5.25], z_ölçü ∈ [−1 − 150, 5 − 150] = [−151, −145]."""
    ext = machine_extents(profil(), [altin_yol(takim(1, L=150.0))], kurulum((100.5, -20.25, -300.0)))
    assert set(ext) == {"x", "y", "z_ölçü"}
    assert ext["x"] == pytest.approx((100.5, 110.5), abs=1e-12)
    assert ext["y"] == pytest.approx((-20.25, -5.25), abs=1e-12)
    assert ext["z_ölçü"] == pytest.approx((-151.0, -145.0), abs=1e-12)


def test_K10_extents_multiple_ops_and_tools():
    """İki op, iki takım boyu: z_ölçü her op'un kendi L'siyle; aralık birleşimdir."""
    a = altin_yol(takim(1, L=150.0))
    b = Toolpath(
        "b",
        takim(2, L=80.0),
        (50.0, 0.0, 5.0),
        [
            Move(G1, (50.0, 0.0, -3.0), feed=100.0),
            Move(G3, (70.0, 0.0, -3.0), feed=100.0, center=(60.0, 0.0)),
        ],
        rpm=5000.0,
    )
    ext = machine_extents(profil(), [a, b], kurulum((0.0, 0.0, -300.0)))
    assert ext["x"] == pytest.approx((0.0, 70.0), abs=1e-12)
    assert ext["y"] == pytest.approx((-10.0, 15.0), abs=1e-12)  # G3 (50,0)→(70,0) merkez (60,0): 270° noktası
    assert ext["z_ölçü"] == pytest.approx((-3.0 - 300 + 80, 5.0 - 300 + 150), abs=1e-12)
