"""SPEC 04 — G-code okuyucu testleri: K6 (R biçimi), K7 (yay doğrulama), K8 (hatalar), K9 (ayrıntılar).

Testler sadece SPEC 04 metninden yazıldı; `cam/gcode/` uygulama kodu okunmadı. G-code örnekleri elle
yazıldı, beklenen konum ve merkezler el hesabıdır (her testin docstring'inde).

R biçimi (SPEC 04 Teori; Smid Bölüm 29; LinuxCNC G2/G3 "Radius format arc"):
  L = |p1 − p0|, m = (p0 + p1)/2, h = sqrt(R² − (L/2)²), c = m ± h·n.
  G2 ve R > 0 → merkez kirişin sağında; G3 ve R > 0 → solunda; R < 0 tarafı çevirir.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from cam.gcode import GRBL, read
from cam.model import CamError, MoveType, Tool, ToolKind

G0, G1, G2, G3 = MoveType.RAPID, MoveType.LINEAR, MoveType.ARC_CW, MoveType.ARC_CCW

HEAD = ["G21 G90 G17 G94", "T1", "S1000 M3"]     # satır 1..3


def freze6() -> Tool:
    return Tool(1, "freze6", ToolKind.FLAT, D=6.0, flute_length=20.0)


TOOLS = {1: freze6()}


def prog(*lines: str) -> str:
    """HEAD (satır 1–3) + verilen satırlar (satır 4..) + M5 / M30."""
    return "\n".join([*HEAD, *lines, "M5", "M30"]) + "\n"


def read1(text: str, **kw):
    """Tek yol beklenen programı okur, yolun doğrulandığını da denetler."""
    paths = read(text, TOOLS, **kw)
    assert len(paths) == 1
    paths[0].validate()          # SPEC: çıkan her yol validate()'ten geçer
    return paths[0]


# ---------------------------------------------------------------- K6: R biçimi


# p0 = (0,0), p1 = (10,10), R = 10:  L = 10√2, m = (5,5), h = sqrt(100 − 50) = 5√2.
# Kiriş yönü d = (1,1)/√2; sağ normal (1,−1)/√2 → m + h·(1,−1)/√2 = (10, 0); sol → (0, 10).
#   G2 R+10 → sağ (10, 0): açı 180° → 90°, saat yönünde 90°  (çeyrek yay)
#   G3 R+10 → sol (0, 10): açı −90° → 0°, saat yönü tersi 90°
#   G2 R−10 → sol (0, 10): saat yönünde −90° → 0° = 270°
#   G3 R−10 → sağ (10, 0): saat yönü tersi 180° → 90° = 270°
# Öteleme (x0, y0) merkezi aynı miktar öteler.
@pytest.mark.parametrize("x0, y0", [(0.0, 0.0), (3.0, -2.0)])
@pytest.mark.parametrize(
    "g, R, cx, cy, sweep_deg",
    [
        ("G2", "10.", 10.0, 0.0, 90.0),
        ("G3", "10.", 0.0, 10.0, 90.0),
        ("G2", "-10.", 0.0, 10.0, 270.0),
        ("G3", "-10.", 10.0, 0.0, 270.0),
    ],
)
def test_R_format_center(x0, y0, g, R, cx, cy, sweep_deg):
    """K6: çeyrek yay (R > 0) ve 270° yay (R < 0), G2 ve G3; merkez 1e-9 mm içinde."""
    x1, y1 = x0 + 10.0, y0 + 10.0
    text = prog(f"G0 X{x0:.1f} Y{y0:.1f} Z0.", f"{g} X{x1:.1f} Y{y1:.1f} R{R} F100.")
    tp = read1(text)
    (m,) = tp.moves
    assert m.type is MoveType(g)
    assert m.end == pytest.approx((x1, y1, 0.0), abs=1e-12)
    assert m.center == pytest.approx((x0 + cx, y0 + cy), abs=1e-9)
    # Süpürme açısı kontrolü: yay boyu r·Δθ = 10·sweep (Toolpath.length, cam/model.py)
    assert tp.length() == pytest.approx(10.0 * math.radians(sweep_deg), rel=1e-9)


def test_R_format_helix_center():
    """K6 ek: R biçiminde Z de değişebilir (helis); merkez XY'de aynı hesap: G2 R10 → (10, 0)."""
    tp = read1(prog("G0 X0. Y0. Z0.", "G2 X10. Y10. Z-2. R10. F100."))
    assert tp.moves[0].center == pytest.approx((10.0, 0.0), abs=1e-9)
    assert tp.moves[0].end == pytest.approx((10.0, 10.0, -2.0), abs=1e-12)


def test_R_semicircle_center_is_midpoint():
    """R = L/2 tam yarım daire: h = 0 → merkez kiriş ortası. p0 = (0,0), p1 = (10,0), R5 → (5, 0)."""
    tp = read1(prog("G0 X0. Y0. Z0.", "G3 X10. Y0. R5. F100."))
    assert tp.moves[0].center == pytest.approx((5.0, 0.0), abs=1e-9)


def test_R_slightly_below_half_chord_within_arc_tol_accepted():
    """SPEC: sadece |R| < L/2 − arc_tol hata. L/2 = 5, R = 4.999 (5 − 0.001 > 5 − 0.005) → kabul.

    Karar (SPEC'te açık değil): h² < 0 durumunda h = 0 alınır → merkez kiriş ortası (5, 0); bu sayede
    r0 = r1 = 5 ve yol validate()'ten geçer. Merkez 1e-6 içinde beklenir.
    """
    tp = read1(prog("G0 X0. Y0. Z0.", "G2 X10. Y0. R4.999 F100."))
    assert tp.moves[0].center == pytest.approx((5.0, 0.0), abs=1e-6)


def test_R_too_small_raises():
    """K6: L/2 = 5, |R| = 4 < 5 − 0.005 → CamError, satır 5."""
    with pytest.raises(CamError, match=r"satır 5\b"):
        read(prog("G0 X0. Y0. Z0.", "G2 X10. Y0. R4. F100."), TOOLS)


@pytest.mark.parametrize("line", ["G2 X0. Y0. R5. F100.", "G3 R5. F100.", "G2 Z-1. R5. F100."])
def test_R_full_circle_raises(line):
    """K6: R ile tam daire (p0 = p1 XY'de) tanımsız → CamError, satır 5."""
    with pytest.raises(CamError, match=r"satır 5\b"):
        read(prog("G0 X0. Y0. Z0.", line), TOOLS)


# ---------------------------------------------------------------- K7: yay doğrulama, merkez düzeltme


def test_arc_radius_mismatch_raises():
    """K7: p0 = (0,0), merkez (5, 0) (I5 J0), p1 = (10.01, 0): r0 = 5, r1 = 5.01; fark 0.01 > 0.005."""
    with pytest.raises(CamError, match=r"satır 5\b"):
        read(prog("G0 X0. Y0. Z0.", "G2 X10.01 Y0. I5. J0. F100."), TOOLS)


def test_arc_center_projected_to_perpendicular_bisector():
    """K7: tolerans içindeki yayda merkez orta dikmeye izdüşer, yol validate()'ten geçer.

    p0 = (0, 0), I5 J1 → c = (5, 1), p1 = (10.004, 0):
      r0 = √26 = 5.09902, r1 = √(5.004² + 1) = 5.10294, |r0 − r1| = 0.00392 ≤ 0.005 → kabul.
      m = (5.002, 0), orta dikme yönü u = (0, 1) (kiriş X ekseninde)
      c' = m + ((c − m)·u) u = (5.002, 1).
    """
    tp = read1(prog("G0 X0. Y0. Z0.", "G3 X10.004 Y0. I5. J1. F100."))
    m = tp.moves[0]
    assert m.center == pytest.approx((5.002, 1.0), abs=1e-9)
    r0 = math.dist((0.0, 0.0), m.center)
    r1 = math.dist((10.004, 0.0), m.center)
    assert abs(r0 - r1) <= 1e-9


def test_arc_center_projection_oblique_chord():
    """K7 eğik kiriş: orta dikme eksenlere paralel değil.

    p0 = (0, 0), c = (5, 0) (I5 J0), p1 = (8.003, 4): r0 = 5, r1 = √(3.003² + 4²) = 5.0018;
    |r0 − r1| = 0.0018 ≤ 0.005 → kabul. m = (p0 + p1)/2, d = p1 − p0, u = (−d_y, d_x)/|d|,
    c' = m + ((c − m)·u) u  (SPEC 04 K7 formülü; aşağıda numpy ile aynı formülden).
    """
    tp = read1(prog("G0 X0. Y0. Z0.", "G2 X8.003 Y4. I5. J0. F100."))
    p0, p1, c = np.array([0.0, 0.0]), np.array([8.003, 4.0]), np.array([5.0, 0.0])
    m = (p0 + p1) / 2
    d = p1 - p0
    u = np.array([-d[1], d[0]]) / np.hypot(*d)
    c_exp = m + np.dot(c - m, u) * u
    assert tp.moves[0].center == pytest.approx(tuple(c_exp), abs=1e-9)


def test_arc_tol_parameter():
    """K7: arc_tol okuyucu parametresi. Aynı yay (fark 0.00392) arc_tol = 0.001 ile → CamError."""
    text = prog("G0 X0. Y0. Z0.", "G3 X10.004 Y0. I5. J1. F100.")
    with pytest.raises(CamError, match=r"satır 5\b"):
        read(text, TOOLS, GRBL, arc_tol=0.001)
    read(text, TOOLS, GRBL, arc_tol=0.005)


def test_full_circle_ij_not_corrected():
    """SPEC: tam dairede (p0 = p1) düzeltme yok. G2 I5. J0. (0,0)'dan → bitiş (0,0), merkez (5, 0)."""
    tp = read1(prog("G0 X0. Y0. Z0.", "G2 I5. J0. F100."))
    m = tp.moves[0]
    assert m.type is G2
    assert m.end == pytest.approx((0.0, 0.0, 0.0), abs=1e-12)
    assert m.center == pytest.approx((5.0, 0.0), abs=1e-12)
    assert tp.length() == pytest.approx(2 * math.pi * 5.0, rel=1e-12)   # tam daire boyu 2πr


# ---------------------------------------------------------------- K8: okuyucu hataları


# Her durumda hata satırı bilinen numarada; mesaj "satır <n>" içermeli (Ek A, 1 tabanlı).
ERROR_CASES = [
    # (açıklama, satırlar (HEAD sonrası, satır 4'ten), hatalı satır no)
    ("G20 inç", ["G0 X0. Y0. Z5.", "G20"], 5),
    ("G18 düzlem", ["G0 X0. Y0. Z5.", "G18"], 5),
    ("G19 düzlem", ["G0 X0. Y0. Z5.", "G19 G1 X1. F100."], 5),
    ("bilinmeyen G (G28)", ["G0 X0. Y0. Z5.", "G28"], 5),
    ("bilinmeyen G (G33)", ["G0 X0. Y0. Z5.", "G33 Z-1. F100."], 5),
    ("G41 telafi (kapsam dışı)", ["G0 X0. Y0. Z5.", "G41 G1 X1. F100."], 5),
    ("G42 telafi (kapsam dışı)", ["G0 X0. Y0. Z5.", "G42"], 5),
    ("G73 çevrimi (kapsam dışı)", ["G0 X0. Y0. Z5.", "G73 X1. Y1. Z-2. R1. Q1. F100."], 5),
    ("bilinmeyen M (M98)", ["G0 X0. Y0. Z5.", "M98"], 5),
    ("bilinmeyen M (M13)", ["G0 X0. Y0. Z5.", "M13"], 5),
    ("M4 ters devir", ["G0 X0. Y0. Z5.", "M4"], 5),
    ("K kelimesi", ["G0 X0. Y0. Z0.", "G2 X10. Y0. I5. J0. K0. F100."], 5),
    ("ilerlemesiz G1", ["G0 X0. Y0. Z5.", "G1 X10."], 5),
    ("ilerlemesiz G2", ["G0 X0. Y0. Z0.", "G2 X10. Y0. I5. J0."], 5),
    ("ilerlemesiz G3", ["G0 X0. Y0. Z0.", "G3 X10. Y0. R5."], 5),
    ("eksik başlangıç ekseni (Z yok)", ["G0 X0. Y0."], 4),
    ("eksik başlangıç ekseni (sadece Z)", ["G0 Z5."], 4),
    ("T sonrası ilk hareket G1", ["G1 X0. Y0. Z5. F100."], 4),
    ("T sonrası ilk hareket G2", ["G2 X0. Y0. Z5. I1. J0. F100."], 4),
    ("tutmayan yay", ["G0 X0. Y0. Z0.", "G2 X10.01 Y0. I5. J0. F100."], 5),
    ("G91 altında çevrim", ["G0 X0. Y0. Z10.", "G91", "G98 G81 X1. Y1. Z-5. R2. F100."], 6),
]


@pytest.mark.parametrize("lines, bad", [c[1:] for c in ERROR_CASES], ids=[c[0] for c in ERROR_CASES])
def test_reader_errors_with_line_number(lines, bad):
    """K8: her CamError durumu ve mesajda satır numarası."""
    with pytest.raises(CamError, match=rf"satır {bad}\b"):
        read(prog(*lines), TOOLS)


def test_unknown_tool_raises():
    """K8: `tools`'ta olmayan takım (T7) → CamError, satır 2."""
    text = "G21 G90 G17 G94\nT7\nS1000 M3\nG0 X0. Y0. Z5.\nM30\n"
    with pytest.raises(CamError, match=r"satır 2\b"):
        read(text, TOOLS)


def test_first_move_after_S_change_must_be_G0():
    """K8: `S` değişimi yeni yol başlatır; ardından ilk hareket G1 → CamError, satır 7."""
    text = prog("G0 X0. Y0. Z5.", "G1 Z0. F100.", "S2000 M3", "G1 X10.")
    with pytest.raises(CamError, match=r"satır 7\b"):
        read(text, TOOLS)


def test_error_line_number_counts_every_text_line():
    """Ek A: n metindeki 1 tabanlı satır sırası; %, O, yorum ve boş satırlar da sayılır.

    1 %, 2 O0001, 3 (yorum), 4 boş, 5 N10 G21.., 6 N20 T1 M6, 7 N30 S1000 M3, 8 N40 G0.., 9 N50 G20.
    """
    text = (
        "%\nO0001\n(yorum)\n\nN10 G21 G90 G17 G94\nN20 T1 M6\nN30 S1000 M3\n"
        "N40 G0 X0. Y0. Z5.\nN50 G20\n%\n"
    )
    with pytest.raises(CamError, match=r"satır 9\b"):
        read(text, TOOLS)


# ---------------------------------------------------------------- K9: okuyucu ayrıntıları


# Altın yolla aynı geometri, ama yorumlar, N, %, O, küçük harf, boşluksuz kelimeler ve G91 ile:
#   N40 G0X0.Y0.Z5.            → başlangıç (0, 0, 5)
#   N50 G1 (dalma) Z-1. F100.  → (0, 0, −1)
#   N60 g91                    → artımsal
#   N70 x10. f300.             → (0, 0, −1) + (10, 0, 0) = (10, 0, −1)      (G1 modal, F300)
#   N80 G1X0.Y10.              → (10, 10, −1)
#   N90 G3 X-10. Y0. I-5. J0.  → bitiş (0, 10, −1); merkez başlangıca göre: (10 − 5, 10 + 0) = (5, 10)
#   N100 G90                   → mutlak
#   N110 G1 Y0.                → (0, 0, −1)   (F300 modal)
#   N120 G0 Z5.                → (0, 0, 5)
DETAIL_TEXT = """\
%
O0001
(program yorumu: altin yol)
n10 g21 g90 g17 g94 g40 g49 g80 g54
N20 T1 M6 ; takim
N30 S1000 M3 M8
N40 G0X0.Y0.Z5.
N50 G1 (dalma) Z-1. F100.
N60 g91
N70 x10. f300.
N80 G1X0.Y10.
N90 G3 X-10. Y0. I-5. J0. ; yarim daire
N100 G90
N110 G1 Y0.
N120 G0 Z5.
N130 M9
N140 M5
N150 M30
%
"""


def test_reader_details_comments_case_spacing_incremental():
    """K9: yorumlar, N, %, O, küçük harf, boşluksuz kelimeler, G91 artımsal → bilinen mutlak noktalar."""
    tp = read1(DETAIL_TEXT)
    assert tp.name == "T1-1"
    assert tp.rpm == 1000
    assert tp.tool == TOOLS[1]
    assert tp.start == pytest.approx((0.0, 0.0, 5.0), abs=1e-12)
    assert [m.type for m in tp.moves] == [G1, G1, G1, G3, G1, G0]
    exp = [(0, 0, -1), (10, 0, -1), (10, 10, -1), (0, 10, -1), (0, 0, -1), (0, 0, 5)]
    for m, e in zip(tp.moves, exp, strict=True):
        assert m.end == pytest.approx(e, abs=1e-12)
    assert tp.moves[3].center == pytest.approx((5.0, 10.0), abs=1e-12)
    assert [m.feed for m in tp.moves[:5]] == pytest.approx([100.0, 300.0, 300.0, 300.0, 300.0])


def test_incremental_rapid_and_back_to_absolute():
    """K9: G91 altında G0 de artımsal: (1,2,3) + (−1, 0.5, 2) = (0, 2.5, 5); G90 sonrası mutlak."""
    tp = read1(prog("G0 X1. Y2. Z3.", "G91", "G0 X-1. Y0.5 Z2.", "G90", "G1 X4. F50."))
    assert tp.moves[0].end == pytest.approx((0.0, 2.5, 5.0), abs=1e-12)
    assert tp.moves[1].end == pytest.approx((4.0, 2.5, 5.0), abs=1e-12)


def test_accepted_codes_do_not_change_path():
    """K9: desteklenen ama yola yansımayan kodlar (G17 G21 G40 G49 G54 G80 G94, M0 M1 M7 M8 M9)."""
    tp = read1(
        prog(
            "G0 X0. Y0. Z5.",
            "G17 G21 G40 G49 G54 G80 G94",
            "M7",
            "M8",
            "M1",
            "M0",
            "G1 Z-1. F100.",
            "M9",
        )
    )
    assert [m.type for m in tp.moves] == [G1]
    assert tp.moves[0].end == pytest.approx((0.0, 0.0, -1.0), abs=1e-12)


def test_m2_program_end_accepted():
    """K9: M2 program sonu olarak kabul edilir (M30 yerine)."""
    text = "G21 G90 G17 G94\nT1\nS1000 M3\nG0 X0. Y0. Z5.\nG1 Z0. F100.\nM5\nM2\n"
    tp = read1(text)
    assert tp.moves[0].end == pytest.approx((0.0, 0.0, 0.0), abs=1e-12)


def test_second_tool_start_inherits_known_axes():
    """SPEC: konumu bilinmeyen eksen sadece programın ilk hareketinde hata. İkinci takımdan sonra
    `G0 X30.` → yol başlangıcı (30, önceki Y, önceki Z) = (30, 0, 5)."""
    t2 = Tool(2, "freze10", ToolKind.FLAT, D=10.0, flute_length=30.0)
    text = prog("G0 X0. Y0. Z5.", "G1 Z0. F100.", "G0 Z5.", "T2 M6", "S2000 M3", "G0 X30.", "G1 Z-1. F80.")
    paths = read(text, {1: TOOLS[1], 2: t2})
    assert [p.name for p in paths] == ["T1-1", "T2-2"]
    assert paths[1].tool == t2
    assert paths[1].rpm == 2000
    assert paths[1].start == pytest.approx((30.0, 0.0, 5.0), abs=1e-12)
    assert paths[1].moves[0].end == pytest.approx((30.0, 0.0, -1.0), abs=1e-12)
    assert paths[1].moves[0].feed == pytest.approx(80.0)
