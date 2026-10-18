"""SPEC 21 — torna G-code okuyucusu testleri (K8–K9): read_lathe.

Testler sadece SPEC 21 metninden ve sabit arayüzlerden yazıldı; cam/gcode/lathe.py gövdesi okunmadı.
Programlar elle yazıldı; beklenen noktalar X/2 (yarıçap), U/2 ve W artımlarıyla elle hesaplandı.

- R biçimli yay (SPEC 04): R > 0 süpürme ≤ 180°, R < 0 > 180°. ZX'te (u, v) = (z, x), G3 saat yönü tersi.
  (x, z) = (12, −10) → (15, −13), R = 3: G2 R3 ve G3 R−3 merkezi (15, −10); G2 R−3 ve G3 R3 merkezi (12, −13).
- Hata mesajında 'satır <n>' (1 tabanlı metin satırı).
"""

from __future__ import annotations

import pytest

from cam.gcode.lathe import read_lathe
from cam.model import CamError, FeedMode, LatheTool, LatheToolKind, MoveType, Plane

G0, G1, G2, G3 = MoveType.RAPID, MoveType.LINEAR, MoveType.ARC_CW, MoveType.ARC_CCW
T1 = LatheTool(1, "dis", LatheToolKind.TURN, nose_r=0.8, tip=3, kappa_r=93.0, eps_r=55.0)
T2 = LatheTool(2, "dis-dis", LatheToolKind.THREAD, nose_r=0.1, tip=8, kappa_r=60.0, eps_r=60.0)
TOOLS = {1: T1, 2: T2}
TOL = 1e-9

# satır 1..8; satır 9'dan sonrası gövde
HEAD = ["%", "O0001", "G21 G18 G40 G99 G54", "G0 X100. Z50.", "T0101", "G97 S1000 M3", "G0 X40.", "Z2."]
TAIL = ["G0 X100.", "Z50.", "M5", "M30", "%"]


def prog(*lines: str, head: list[str] | None = None) -> str:
    return "\n".join((HEAD if head is None else head) + list(lines) + TAIL) + "\n"


def head_with(**repl: str) -> list[str]:
    """HEAD'in satır numarası (1 tabanlı) verilen satırlarını değiştirir: head_with(l5='T0303')."""
    h = list(HEAD)
    for k, v in repl.items():
        h[int(k[1:]) - 1] = v
    return h


def check_moves(tp, beklenen):
    assert len(tp.moves) == len(beklenen)
    for m, (t, end, feed) in zip(tp.moves, beklenen, strict=True):
        assert m.type is t
        assert m.end == pytest.approx(end, abs=TOL)
        if feed is None:
            assert m.feed is None
        else:
            assert m.feed == pytest.approx(feed, abs=1e-12)


def check_path(tp):
    tp.validate()
    assert tp.plane is Plane.ZX and tp.feed_mode is FeedMode.PER_REV
    for p in tp.points():
        assert p[1] == 0.0


# ------------------------------------------------------------------ K8 okuyucu ayrıntıları


def test_k8_temel_program_ve_ilk_t_oncesi_g0_yola_girmiyor():
    (tp,) = read_lathe(prog("G1 Z-10. F0.2"), TOOLS, spindle="M3")
    check_path(tp)
    assert tp.tool == T1
    assert tp.name.startswith("T1-")
    assert tp.rpm == 1000 and tp.css is None
    assert tp.start == pytest.approx((20.0, 0.0, 50.0), abs=TOL)  # T sonrası ilk G0'ın bitişi
    check_moves(
        tp,
        [
            (G0, (20.0, 0.0, 2.0), None),
            (G1, (20.0, 0.0, -10.0), 0.2),
            (G0, (50.0, 0.0, -10.0), None),
            (G0, (50.0, 0.0, 50.0), None),
        ],
    )


def test_k8_u_w_artimsal():
    text = prog(
        "G1 U-10. F0.2",  # X40 → X30: x = 15
        "W-12.",  # z = 2 − 12 = −10
        "G0 U20.",  # X30 → X50: x = 25
        "W12.",  # z = 2
        head=head_with(l8="W-48."),  # z = 50 − 48 = 2
    )
    (tp,) = read_lathe(text, TOOLS)
    check_path(tp)
    assert tp.start == pytest.approx((20.0, 0.0, 50.0), abs=TOL)
    check_moves(
        tp,
        [
            (G0, (20.0, 0.0, 2.0), None),
            (G1, (15.0, 0.0, 2.0), 0.2),
            (G1, (15.0, 0.0, -10.0), 0.2),
            (G0, (25.0, 0.0, -10.0), None),
            (G0, (25.0, 0.0, 2.0), None),
            (G0, (50.0, 0.0, 2.0), None),
            (G0, (50.0, 0.0, 50.0), None),
        ],
    )


@pytest.mark.parametrize(
    ("line", "t", "center"),
    [
        ("G2 X30. Z-13. R3. F0.2", G2, (15.0, -10.0)),
        ("G3 X30. Z-13. R-3. F0.2", G3, (15.0, -10.0)),
        ("G2 X30. Z-13. R-3. F0.2", G2, (12.0, -13.0)),
        ("G3 X30. Z-13. R3. F0.2", G3, (12.0, -13.0)),
    ],
)
def test_k8_r_bicimli_yay(line, t, center):
    text = prog(line, head=head_with(l7="G0 X24.", l8="Z-10."))
    (tp,) = read_lathe(text, TOOLS)
    check_path(tp)
    arc = tp.moves[1]
    assert arc.type is t
    assert arc.end == pytest.approx((15.0, 0.0, -13.0), abs=TOL)
    assert arc.center == pytest.approx(center, abs=TOL)


def test_k8_ik_yay_merkezi_bagil_yaricap():
    # (x, z) = (12, −10), I3. K0. → merkez (15, −10)
    text = prog("G2 X30. Z-13. I3. K0. F0.2", head=head_with(l7="G0 X24.", l8="Z-10."))
    (tp,) = read_lathe(text, TOOLS)
    check_path(tp)
    assert tp.moves[1].type is G2
    assert tp.moves[1].center == pytest.approx((15.0, -10.0), abs=TOL)


def test_k8_yorumlar_kucuk_harf_bosluksuz_n_o_yuzde():
    text = "\n".join(
        [
            "%",
            "O0003 (deneme programi)",
            "g21 g18 g40 g99 g54",
            "; tam satir yorum",
            "n20g0x100.z50.",
            "N30 T0101 (takim 1)",
            "N40 G97 S1000 M3 ; yorum",
            "N50 M8",
            "N60 G0 X40.",
            "N70 Z2.",
            "n80g1x30.f0.2",
            "N90 M1",
            "N100 G0 X100.",
            "N110 Z50.",
            "N120 M9",
            "N130 M5",
            "N140 M0",
            "N150 M30",
            "%",
        ]
    )
    (tp,) = read_lathe(text + "\n", TOOLS, spindle="M3")
    check_path(tp)
    assert tp.start == pytest.approx((20.0, 0.0, 50.0), abs=TOL)
    check_moves(
        tp,
        [
            (G0, (20.0, 0.0, 2.0), None),
            (G1, (15.0, 0.0, 2.0), 0.2),
            (G0, (50.0, 0.0, 2.0), None),
            (G0, (50.0, 0.0, 50.0), None),
        ],
    )


def test_k8_g96_yolunda_css_ve_rpm():
    text = prog("G1 Z-10. F0.2", head=head_with(l6="G50 S2500\nG96 S180 M3"))
    (tp,) = read_lathe(text, TOOLS)
    check_path(tp)
    assert tp.css == 180 and tp.rpm == 2500


def test_k8_is_mili_degisince_yeni_yol():
    text = prog("G1 Z-10. F0.2", "G0 Z2.", "G97 S1500 M3", "G0 X30.", "G1 Z-5. F0.1")
    tps = read_lathe(text, TOOLS)
    assert len(tps) == 2
    a, b = tps
    for tp in tps:
        check_path(tp)
        assert tp.tool == T1 and tp.name.startswith("T1-")
    assert a.name != b.name
    assert (a.rpm, b.rpm) == (1000, 1500)
    assert a.moves[-1].end == pytest.approx((20.0, 0.0, 2.0), abs=TOL)
    assert b.start == pytest.approx((15.0, 0.0, 2.0), abs=TOL)
    assert b.moves[0].type is G1 and b.moves[0].end == pytest.approx((15.0, 0.0, -5.0), abs=TOL)


def test_k8_yeni_takimda_yeni_yol_ve_g32():
    text = prog(
        "G1 Z-10. F0.2",
        "G0 Z50.",
        "X100.",
        "M5",
        "T0202",
        "G97 S800 M4",
        "G0 X19.2",
        "Z3.",
        "G32 Z-20. F1.8143",
        "G0 X22.",
        "Z3.",
        head=head_with(l6="G97 S1000 M4"),
    )
    a, b = read_lathe(text, TOOLS, spindle="M4")
    check_path(a)
    check_path(b)
    assert a.tool == T1 and b.tool == T2
    assert b.name.startswith("T2-") and b.rpm == 800 and b.css is None
    assert b.start == pytest.approx((9.6, 0.0, 50.0), abs=TOL)
    cut = b.moves[1]
    assert cut.type is G1
    assert cut.end == pytest.approx((9.6, 0.0, -20.0), abs=TOL)
    assert cut.feed == pytest.approx(1.8143, abs=1e-12)


def test_k8_spindle_none_iki_yon_de_kabul():
    for d in ("M3", "M4"):
        (tp,) = read_lathe(prog("G1 Z-10. F0.2", head=head_with(l6=f"G97 S1000 {d}")), TOOLS)
        check_path(tp)
        (tp,) = read_lathe(prog("G1 Z-10. F0.2", head=head_with(l6=f"G97 S1000 {d}")), TOOLS, spindle=d)
        check_path(tp)


# ------------------------------------------------------------------ K9 okuyucu hataları

# satır 9'daki gövde satırı hatalı
SATIR9 = [
    "G90",
    "G91",
    "G92",
    "G94",
    "G95",
    "G98",
    "G20",
    "G17",
    "G19",
    "G41",
    "G42",
    "G28 U0. W0.",
    "G70",
    "G71",
    "G72",
    "G73",
    "G74",
    "G75",
    "G76",
    "G50 X100. Z50.",
    "G50 Z50.",
    "G1 Y5. F0.2",
    "G2 X46. Z-1. I3. J0. K0. F0.2",
    "G1 X30. U-2. F0.2",
    "G1 Z-5. W-1. F0.2",
    "G1 Z-10.",  # ilerlemesiz G1
    "G2 X46. Z-1. I3. K0.",  # ilerlemesiz G2
    "G3 X46. Z5. I3. K0.",  # ilerlemesiz G3
    "G2 X46. Z-1. I3.5 K0. F0.2",  # tutmayan yay: r0 = 3.5, r1 = 3.04
    "G2 X40. Z2. I3. K0. F0.2",  # tam daire
    "G2 X40. Z2. R3. F0.2",  # R ile tam daire
    "G2 X46. Z-1. R1. F0.2",  # |R| < L/2
    "G32 Z-10. F1.5",  # THREAD olmayan takımla G32
]


def test_k9_temel_program_gecerli():
    (tp,) = read_lathe(prog("G2 X46. Z-1. I3. K0. F0.2"), TOOLS, spindle="M3")
    check_path(tp)
    assert tp.moves[1].center == pytest.approx((23.0, 2.0), abs=TOL)


@pytest.mark.parametrize("line", SATIR9)
def test_k9_satir9_hata(line):
    with pytest.raises(CamError, match=r"satır 9\b"):
        read_lathe(prog(line), TOOLS)


@pytest.mark.parametrize(
    ("head", "n", "spindle"),
    [
        (head_with(l6="G96 S180 M3"), 6, None),  # G50 olmadan G96
        (head_with(l5="T0303"), 5, None),  # bilinmeyen takım
        (head_with(l5="T0102"), 5, None),  # ofset no. uyuşmuyor
        (head_with(l5="T0100"), 5, None),  # ofset iptali
        (HEAD, 6, "M4"),  # spindle verilmişken diğer yön
        (head_with(l7="G1 X40. F0.2"), 7, None),  # T / iş mili sonrası ilk hareket G0 değil
        (head_with(l4="G0 Z50.", l7="G0 U10."), 7, None),  # X konumu bilinmiyor
        (head_with(l4="G1 X100. Z50. F0.2"), 4, None),  # ilk T'den önce G1
    ],
)
def test_k9_bas_satir_hata(head, n, spindle):
    with pytest.raises(CamError, match=rf"satır {n}\b"):
        read_lathe(prog("G1 Z-10. F0.2", head=head), TOOLS, spindle=spindle)


def test_k9_is_mili_degisimi_sonrasi_ilk_hareket_g0_degil():
    with pytest.raises(CamError, match=r"satır 10\b"):
        read_lathe(prog("G97 S1200 M3", "G1 Z-10. F0.2"), TOOLS)


def test_k9_ilerlemesiz_g32():
    head = head_with(l5="T0202", l6="G97 S800 M3")
    with pytest.raises(CamError, match=r"satır 9\b"):
        read_lathe(prog("G32 Z-10.", head=head), TOOLS)


def test_k9_g32_dis_takimiyla_gecerli():
    head = head_with(l5="T0202", l6="G97 S800 M3")
    (tp,) = read_lathe(prog("G32 Z-10. F1.5", head=head), TOOLS)
    check_path(tp)
    assert tp.moves[1].type is G1 and tp.moves[1].feed == pytest.approx(1.5, abs=1e-12)
