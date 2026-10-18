"""SPEC 21 — torna G-code yazıcısı testleri (K1–K7): write_lathe, spindle_rpm.

Testler sadece SPEC 21 metninden ve sabit arayüzlerden (cam/model.py, cam.gcode.lathe imzaları) yazıldı;
cam/gcode/lathe.py gövdesi okunmadı. Beklenen değerler el ile türetildi:

- Modelde x yarıçap; G-code'da X = 2·x (3 ondalık). Yay merkezi I = c_x − x̂0 (yarıçap), K = c_z − ẑ0.
- ZX düzleminde (u, v) = (z, x); G3 u'dan v'ye (saat yönü tersi), G2 saat yönü.
- İş mili: G97 S<round(rpm)> M3|M4 veya G50 S<round(rpm)> + G96 S<round(css)> M3|M4.
- Op geçişi: G0 Z<z_tc>, (takım değişiyorsa) G0 X<2x_tc>, M5, T<id><id>, iş mili,
  G0 X<2x_A>, G0 Z<z_A>.
- G96'da devir n = min(1000·Vc / (π·D), n_max), D = 2·|x|.
"""

from __future__ import annotations

import inspect
import math
import re

import pytest

from cam.gcode import write
from cam.gcode.lathe import FANUC_TORNA, LatheDialect, read_lathe, spindle_rpm, write_lathe
from cam.model import (
    CamError,
    FeedMode,
    LatheTool,
    LatheToolKind,
    Move,
    MoveType,
    Plane,
    Tool,
    ToolKind,
    Toolpath,
)

G0, G1, G2, G3 = MoveType.RAPID, MoveType.LINEAR, MoveType.ARC_CW, MoveType.ARC_CCW
TC = (50.0, 50.0)  # takım değiştirme noktası (yarıçap, z) → G0 X100. Z50.


# ------------------------------------------------------------------ yardımcılar


def ttool(id: int = 1, kind: LatheToolKind = LatheToolKind.TURN, tip: int = 3) -> LatheTool:
    return LatheTool(id, f"T{id}", kind, nose_r=0.8, tip=tip, kappa_r=93.0, eps_r=55.0)


def thtool(id: int = 2) -> LatheTool:
    return LatheTool(id, f"D{id}", LatheToolKind.THREAD, nose_r=0.1, tip=8, kappa_r=60.0, eps_r=60.0)


def lpath(
    moves: list[Move],
    start=(30.0, 0.0, 2.0),
    tool: LatheTool | None = None,
    rpm: float = 1000.0,
    css: float | None = None,
    name: str = "yol",
) -> Toolpath:
    return Toolpath(
        name=name,
        tool=ttool() if tool is None else tool,
        start=start,
        moves=moves,
        rpm=rpm,
        plane=Plane.ZX,
        feed_mode=FeedMode.PER_REV,
        css=css,
    )


def simple(
    tool: LatheTool | None = None,
    rpm: float = 1000.0,
    css: float | None = None,
    x: float = 12.0,
    x_A: float = 30.0,
) -> Toolpath:
    """(x_A, 2) → (x, 2) → (x, −10) → (x_A, −10) → (x_A, 2): eksen eksen G0, tek G1."""
    return lpath(
        [
            Move(G0, (x, 0.0, 2.0)),
            Move(G1, (x, 0.0, -10.0), feed=0.2),
            Move(G0, (x_A, 0.0, -10.0)),
            Move(G0, (x_A, 0.0, 2.0)),
        ],
        start=(x_A, 0.0, 2.0),
        tool=tool,
        rpm=rpm,
        css=css,
    )


def golden_path() -> Toolpath:
    """SPEC 21 altın örnek (K1)."""
    tool = LatheTool(1, "dis-kaba", LatheToolKind.TURN, nose_r=0.8, tip=3, kappa_r=93.0, eps_r=55.0)
    return lpath(
        [
            Move(G0, (12.0, 0.0, 1.0)),
            Move(G1, (12.0, 0.0, -10.0), feed=0.2),
            Move(G2, (15.0, 0.0, -13.0), feed=0.2, center=(15.0, -10.0)),
            Move(G1, (21.0, 0.0, -13.0), feed=0.2),
            Move(G0, (21.0, 0.0, 1.0)),
        ],
        start=(21.0, 0.0, 1.0),
        tool=tool,
        rpm=2500.0,
        css=180.0,
    )


GOLDEN = """%
O0001
N10 G21 G18 G40 G99 G54
N20 G0 X100. Z50.
N30 T0101
N40 G50 S2500
N50 G96 S180 M3
N60 G0 X42.
N70 Z1.
N80 X24.
N90 G1 Z-10. F0.2
N100 G2 X30. Z-13. I3. K0.
N110 G1 X42.
N120 G0 Z1.
N130 Z50.
N140 X100.
N150 M5
N160 M30
%
"""

_WORD = re.compile(r"([A-Z])([-+]?\d*\.?\d*)")


def blocks(text: str) -> list[list[tuple[str, str]]]:
    """Programın satırları kelime listesi olarak; '%', 'O....' ve N kelimesi atılır."""
    out = []
    for line in text.splitlines():
        if line in ("%", "") or line.startswith("O"):
            continue
        words = [(a, v) for a, v in _WORD.findall(line) if a != "N"]
        out.append(words)
    return out


def body(text: str) -> list[str]:
    """Satır numarası atılmış satırlar ('%' ve 'O....' dahil)."""
    return [re.sub(r"^N\d+ ", "", s) for s in text.splitlines()]


def motion_blocks(text: str) -> list[tuple[int, int, dict[str, str]]]:
    """Eksen kelimesi olan satırlar: (blok indisi, modal hareket kodu, eksen/ofset/F kelimeleri).

    Hareket kodu (0, 1, 2, 3, 32) modaldır: yazılmadıysa önceki geçerlidir."""
    mode = None
    out = []
    for i, words in enumerate(blocks(text)):
        for a, v in words:
            if a == "G" and float(v) in (0, 1, 2, 3, 32):
                mode = int(float(v))
        ax = {a: v for a, v in words if a in "XZUWIKRF"}
        if any(a in ax for a in "XZUW"):
            out.append((i, mode, ax))
    return out


def has_word(words: list[tuple[str, str]], a: str, v: float) -> bool:
    return any(w == a and float(s) == v for w, s in words)


# ------------------------------------------------------------------ K1 altın metin


def test_k1_altin_metin_satir_satir():
    text = write_lathe([golden_path()], spindle="M3", tool_change=TC)
    assert text.splitlines() == GOLDEN.splitlines()
    assert text == GOLDEN  # '\n' ile biter


def test_k1_m4_tek_fark():
    text = write_lathe([golden_path()], spindle="M4", tool_change=TC)
    assert text == GOLDEN.replace("G96 S180 M3", "G96 S180 M4")


def test_k1_varsayilan_dil_ve_program_no():
    assert FANUC_TORNA.header == ("%", "O{program_no:04d}", "G21 G18 G40 G99 G54")
    assert FANUC_TORNA.footer == ("M5", "M30", "%")
    assert (FANUC_TORNA.decimals, FANUC_TORNA.feed_decimals, FANUC_TORNA.lead_decimals) == (3, 3, 4)
    text = write_lathe([golden_path()], spindle="M3", tool_change=TC, dialect=FANUC_TORNA, program_no=42)
    assert text.splitlines()[1] == "O0042"


def test_k1_altin_metin_okunuyor():
    tool = golden_path().tool
    tps = read_lathe(GOLDEN, {1: tool}, spindle="M3")
    assert len(tps) == 1
    tp = tps[0]
    tp.validate()
    assert tp.plane is Plane.ZX and tp.feed_mode is FeedMode.PER_REV
    assert tp.tool == tool
    assert tp.css == 180 and tp.rpm == 2500
    assert tp.start == pytest.approx((21.0, 0.0, 50.0), abs=1e-9)
    beklenen = [
        (G0, (21.0, 0.0, 1.0), None, None),
        (G0, (12.0, 0.0, 1.0), None, None),
        (G1, (12.0, 0.0, -10.0), 0.2, None),
        (G2, (15.0, 0.0, -13.0), 0.2, (15.0, -10.0)),
        (G1, (21.0, 0.0, -13.0), 0.2, None),
        (G0, (21.0, 0.0, 1.0), None, None),
        (G0, (21.0, 0.0, 50.0), None, None),
        (G0, (50.0, 0.0, 50.0), None, None),
    ]
    assert len(tp.moves) == len(beklenen)
    for m, (t, end, feed, center) in zip(tp.moves, beklenen, strict=True):
        assert m.type is t
        assert m.end == pytest.approx(end, abs=1e-9)
        if feed is None:
            assert m.feed is None
        else:
            assert m.feed == pytest.approx(feed, abs=1e-12)
        if center is not None:
            assert m.center == pytest.approx(center, abs=1e-9)


# ------------------------------------------------------------------ K2 çap programlama ve bastırma


def k2_path(arc: Move) -> Toolpath:
    return lpath(
        [
            Move(G0, (12.3456, 0.0, 2.0)),
            Move(G1, (12.3456, 0.0, -5.0), feed=0.2),
            Move(G1, (14.0, 0.0, -5.0), feed=0.2),
            arc,
            Move(G1, (-0.8, 0.0, -7.0), feed=0.25),
            Move(G0, (-0.8, 0.0, 2.0)),
            Move(G0, (30.0, 0.0, 2.0)),
        ]
    )


def test_k2_cap_programlama_ve_bastirma():
    # G2 (14, −5) → (16, −7), merkez (x, z) = (16, −5): (u, v)'de −90° → 180°, saat yönü 90°
    tp = k2_path(Move(G2, (16.0, 0.0, -7.0), feed=0.2, center=(16.0, -5.0)))
    tp.validate()
    lines = body(write_lathe([tp], spindle="M3", tool_change=TC))
    beklenen = [
        "G0 X60.",  # x_A = 30, z_tc'de
        "Z2.",  # z_A
        "X24.691",  # 2·12.3456 = 24.6912
        "G1 Z-5. F0.2",  # X değişmedi, yazılmaz
        "X28.",  # aynı G1 ve aynı F yazılmaz
        "G2 X32. Z-7. I2. K0.",  # I yarıçap, başlangıca bağıl; F aynı
        "G1 X-1.6 F0.25",  # negatif x geçerli
        "G0 Z2.",  # G0'da F yok
        "X60.",
        "Z50.",
        "X100.",
        "M5",
        "M30",
        "%",
    ]
    i = lines.index("G0 X60.")
    assert lines[i:] == beklenen
    assert lines[i - 1] == "G97 S1000 M3"


def test_k2_yay_k_bagil():
    # G3 (14, −5) → (16, −7), merkez (x, z) = (14, −7): (u, v)'de 0° → 90°, saat yönü tersi 90°
    tp = k2_path(Move(G3, (16.0, 0.0, -7.0), feed=0.2, center=(14.0, -7.0)))
    tp.validate()
    lines = body(write_lathe([tp], spindle="M3", tool_change=TC))
    assert "G3 X32. Z-7. I0. K-2." in lines


def test_k2_g0_satirlarinda_f_yok():
    text = write_lathe([golden_path(), simple(tool=ttool(2))], spindle="M3", tool_change=TC)
    for _, mode, ax in motion_blocks(text):
        if mode == 0:
            assert "F" not in ax


# ------------------------------------------------------------------ K3 iş mili


def spindle_lines(text: str) -> list[list[tuple[str, str]]]:
    return [w for w in blocks(text) if any(a == "S" for a, _ in w)]


def test_k3_sabit_devir_g97():
    text = write_lathe([simple(rpm=1200.0)], spindle="M3", tool_change=TC)
    assert body(text).count("G97 S1200 M3") == 1
    assert not any(has_word(w, "G", 96) or has_word(w, "G", 50) for w in blocks(text))


def test_k3_sabit_kesme_hizi_g50_g96():
    text = write_lathe([simple(rpm=3000.0, css=200.0)], spindle="M4", tool_change=TC)
    lines = body(text)
    i = lines.index("G50 S3000")
    assert lines[i + 1] == "G96 S200 M4"
    assert not any(has_word(w, "G", 97) for w in blocks(text))


def test_k3_yuvarlama():
    lines = body(write_lathe([simple(rpm=1499.6)], spindle="M3", tool_change=TC))
    assert "G97 S1500 M3" in lines
    lines = body(write_lathe([simple(rpm=2400.4, css=179.6)], spindle="M3", tool_change=TC))
    i = lines.index("G50 S2400")
    assert lines[i + 1] == "G96 S180 M3"


def test_k3_sadece_is_mili_degisince_taret_donmuyor():
    a = simple(rpm=2000.0, css=180.0)
    b = simple(rpm=1200.0, css=None, x=14.0, x_A=28.0)
    text = write_lathe([a, b], spindle="M3", tool_change=TC)
    bl = blocks(text)
    assert sum(1 for w in bl if any(k == "T" for k, _ in w)) == 1  # tek T0101
    assert sum(1 for w in bl if has_word(w, "M", 5)) == 1  # sadece program sonunda
    # X100. (2·x_tc) sadece programın başında ve sonunda
    assert sum(1 for _, _, ax in motion_blocks(text) if "X" in ax and float(ax["X"]) == 100.0) == 2
    sp = spindle_lines(text)
    assert any(has_word(w, "G", 97) and has_word(w, "S", 1200) for w in sp)
    # iki op arasında Z50.'ye çekilip yeni op'un başına eksen eksen gidiliyor
    mb = motion_blocks(text)
    i_sp = next(i for i, w in enumerate(bl) if has_word(w, "G", 97))
    before = [m for m in mb if m[0] < i_sp][-1]
    after = [m for m in mb if m[0] > i_sp][:2]
    assert before[1] == 0 and before[2] == {"Z": "50."}
    assert after[0][1] == 0 and after[0][2] == {"X": "56."}
    assert after[1][1] == 0 and after[1][2] == {"Z": "2."}


def test_k3_spindle_zorunlu_parametre():
    params = inspect.signature(write_lathe).parameters
    assert params["spindle"].default is inspect.Parameter.empty
    assert params["tool_change"].default is inspect.Parameter.empty


@pytest.mark.parametrize("spindle", [None, "", "M6", "M5", "m3", "M03"])
def test_k3_gecersiz_spindle_hata(spindle):
    with pytest.raises(CamError):
        write_lathe([simple()], spindle=spindle, tool_change=TC)


# ------------------------------------------------------------------ K4 takım değişimi, hızlı hareketler


def test_k4_iki_takim_sirasi():
    a = simple(tool=ttool(1), rpm=2000.0, css=180.0)
    b = lpath(
        [
            Move(G0, (10.0, 0.0, 3.0)),
            Move(G1, (10.0, 0.0, -5.0), feed=0.1),
            Move(G0, (28.0, 0.0, -5.0)),
            Move(G0, (28.0, 0.0, 3.0)),
        ],
        start=(28.0, 0.0, 3.0),
        tool=ttool(2),
        rpm=800.0,
    )
    text = write_lathe([a, b], spindle="M3", tool_change=TC)
    bl = blocks(text)
    i = bl.index([("T", "0202")])
    mb = {m[0]: m for m in motion_blocks(text)}
    # önce: G0 Z<z_tc>, G0 X<2x_tc>, M5
    assert bl[i - 1] == [("M", "5")]
    assert mb[i - 2][1] == 0 and mb[i - 2][2] == {"X": "100."}
    assert mb[i - 3][1] == 0 and mb[i - 3][2] == {"Z": "50."}
    # sonra: iş mili, G0 X<2x_A>, G0 Z<z_A>
    assert has_word(bl[i + 1], "G", 97) and has_word(bl[i + 1], "S", 800) and has_word(bl[i + 1], "M", 3)
    assert mb[i + 2][1] == 0 and mb[i + 2][2] == {"X": "56."}
    assert mb[i + 3][1] == 0 and mb[i + 3][2] == {"Z": "3."}
    assert sum(1 for w in bl if has_word(w, "M", 5)) == 2


def test_k4_ayni_takimli_ikinci_op_t_yazmiyor():
    text = write_lathe([simple(), simple(x=14.0)], spindle="M3", tool_change=TC)
    bl = blocks(text)
    assert sum(1 for w in bl if any(k == "T" for k, _ in w)) == 1
    assert sum(1 for w in bl if has_word(w, "M", 5)) == 1


@pytest.mark.parametrize(("id", "t"), [(1, "T0101"), (7, "T0707"), (12, "T1212"), (99, "T9999")])
def test_k4_t_bicimi(id, t):
    text = write_lathe([simple(tool=ttool(id))], spindle="M3", tool_change=TC)
    assert body(text).count(t) == 1


@pytest.mark.parametrize("id", [0, 100, -1])
def test_k4_takim_no_aralik_disi_hata(id):
    with pytest.raises(CamError):
        write_lathe([simple(tool=ttool(id))], spindle="M3", tool_change=TC)


@pytest.mark.parametrize("tc", [(50.0, 1.9), (29.9, 50.0), (-50.0, 50.0)])
def test_k4_takim_degistirme_noktasi_bbox_altinda_hata(tc):
    # simple(): bbox en büyük z = 2, en büyük x = 30
    with pytest.raises(CamError):
        write_lathe([simple()], spindle="M3", tool_change=tc)


def test_k4_takim_degistirme_noktasi_yay_siskinligi():
    # G3 (20, 0) → (20, −4), merkez (20, −2): (u, v)'de 0 → π, x = 22'den geçer
    tp = lpath(
        [
            Move(G0, (20.0, 0.0, 0.0)),
            Move(G3, (20.0, 0.0, -4.0), feed=0.2, center=(20.0, -2.0)),
            Move(G0, (21.0, 0.0, -4.0)),
            Move(G0, (21.0, 0.0, 0.0)),
        ],
        start=(21.0, 0.0, 0.0),
    )
    tp.validate()
    with pytest.raises(CamError):
        write_lathe([tp], spindle="M3", tool_change=(21.5, 50.0))
    text = write_lathe([tp], spindle="M3", tool_change=(22.5, 50.0))
    assert "G3" in text


def test_k4_capraz_g0_hata():
    tp = lpath([Move(G0, (12.0, 0.0, 1.0)), Move(G1, (12.0, 0.0, -10.0), feed=0.2)])
    with pytest.raises(CamError):
        write_lathe([tp], spindle="M3", tool_change=TC)


# ------------------------------------------------------------------ K5 diş (G32)


def thread_path(moves: list[Move] | None = None, css: float | None = None) -> Toolpath:
    P = 1.8143
    if moves is None:
        moves = []
        for x in (9.6, 9.3, 9.1, 9.1):
            moves += [
                Move(G0, (x, 0.0, 3.0)),
                Move(G1, (x, 0.0, -20.0), feed=P),
                Move(G0, (11.0, 0.0, -20.0)),
                Move(G0, (11.0, 0.0, 3.0)),
            ]
    return lpath(moves, start=(11.0, 0.0, 3.0), tool=thtool(), rpm=800.0, css=css)


def test_k5_dis_g32():
    tp = thread_path()
    tp.validate()
    text = write_lathe([tp], spindle="M3", tool_change=TC)
    assert "G97 S800 M3" in body(text)
    cuts = [(mode, ax) for _, mode, ax in motion_blocks(text) if mode not in (0, None)]
    assert len(cuts) == 4
    for mode, ax in cuts:
        assert mode == 32  # G1 değil
        assert "X" not in ax and float(ax["Z"]) == -20.0
    # hatve 4 ondalıkla; modal F her kesmede hatve
    f_words = [ax["F"] for _, _, ax in motion_blocks(text) if "F" in ax]
    assert f_words and set(f_words) == {"1.8143"}
    assert not any(has_word(w, "G", 1) for w in blocks(text))


def test_k5_dis_css_hata():
    with pytest.raises(CamError):
        write_lathe([thread_path(css=150.0)], spindle="M3", tool_change=TC)


def test_k5_dis_konik_g1_hata():
    moves = [Move(G0, (9.6, 0.0, 3.0)), Move(G1, (9.4, 0.0, -20.0), feed=1.5), Move(G0, (11.0, 0.0, -20.0))]
    with pytest.raises(CamError):
        write_lathe([thread_path(moves)], spindle="M3", tool_change=TC)


def test_k5_dis_yay_hata():
    moves = [
        Move(G0, (9.0, 0.0, 3.0)),
        Move(G3, (9.0, 0.0, -1.0), feed=1.5, center=(9.0, 1.0)),
        Move(G0, (11.0, 0.0, -1.0)),
    ]
    with pytest.raises(CamError):
        write_lathe([thread_path(moves)], spindle="M3", tool_change=TC)


def test_k5_freze_yazicisi_torna_yolunu_reddediyor():
    tp = golden_path()
    write_lathe([tp], spindle="M3", tool_change=TC)  # torna yazıcısı yazar
    with pytest.raises(CamError, match="write_lathe"):
        write([tp])


# ------------------------------------------------------------------ K6 diğer yazıcı hataları


def test_k6_freze_takimli_yol_hata():
    mill = Tool(1, "freze", ToolKind.FLAT, D=10.0, flute_length=20.0)
    tp = simple()
    tp.tool = mill
    with pytest.raises(CamError):
        write_lathe([tp], spindle="M3", tool_change=TC)


def test_k6_per_min_hata():
    tp = simple()
    tp.feed_mode = FeedMode.PER_MIN
    with pytest.raises(CamError):
        write_lathe([tp], spindle="M3", tool_change=TC)


def test_k6_bos_liste_hata():
    with pytest.raises(CamError):
        write_lathe([], spindle="M3", tool_change=TC)


def test_k6_gecersiz_yol_validate_hata():
    tp = simple()
    tp.moves[1].feed = None  # ilerlemesiz G1
    with pytest.raises(CamError):
        write_lathe([tp], spindle="M3", tool_change=TC)


DELTA = 2e-5  # rad; r = 5'te uçlar arası ~1e-4 mm


def short_arc_path(t: MoveType) -> Toolpath:
    """Merkez (x, z) = (10, −5), r = 5; (10, 0)'dan (u, v)'de 0 → δ.

    G3: süpürme δ (< π); G2: süpürme 2π − δ (≥ π). Uçlar X20. Z0. olarak aynı metne yuvarlanır."""
    x1 = 10.0 + 5.0 * math.sin(DELTA)
    z1 = -5.0 + 5.0 * math.cos(DELTA)
    return lpath(
        [
            Move(G0, (10.0, 0.0, 0.0)),
            Move(t, (x1, 0.0, z1), feed=0.2, center=(10.0, -5.0)),
            Move(G0, (20.0, 0.0, z1)),
        ],
        start=(20.0, 0.0, 0.0),
    )


def test_k6_cok_kisa_yay_pi_alti_g1_yaziliyor():
    tp = short_arc_path(G3)
    tp.validate()
    text = write_lathe([tp], spindle="M3", tool_change=TC)
    assert all(mode not in (2, 3) for _, mode, _ in motion_blocks(text))
    (rp,) = read_lathe(text, {1: tp.tool})
    rp.validate()
    assert rp.length({G1, G2, G3}) <= 1e-3


def test_k6_cok_kisa_yay_pi_ustu_hata():
    tp = short_arc_path(G2)
    tp.validate()
    with pytest.raises(CamError):
        write_lathe([tp], spindle="M3", tool_change=TC)


# ------------------------------------------------------------------ K7 spindle_rpm


def test_k7_spindle_rpm_bilinen_deger():
    n = spindle_rpm(180.0, 25.0, 1e9)
    assert n == pytest.approx(180000.0 / (50.0 * math.pi), rel=1e-12)
    assert n == pytest.approx(1145.9156, abs=1e-4)


def test_k7_spindle_rpm_negatif_x_cap_mutlak():
    assert spindle_rpm(180.0, -25.0, 1e9) == pytest.approx(180000.0 / (50.0 * math.pi), rel=1e-12)


def test_k7_spindle_rpm_sinir():
    assert spindle_rpm(180.0, 25.0, 1000.0) == 1000.0
    assert spindle_rpm(180.0, 25.0, 2000.0) == pytest.approx(180000.0 / (50.0 * math.pi), rel=1e-12)


def test_k7_spindle_rpm_eksende_sinir():
    assert spindle_rpm(180.0, 0.0, 2500.0) == 2500.0


@pytest.mark.parametrize(
    ("css", "x", "rpm_max"),
    [
        (0.0, 25.0, 1000.0),
        (-180.0, 25.0, 1000.0),
        (180.0, 25.0, 0.0),
        (180.0, 25.0, -1000.0),
        (math.nan, 25.0, 1000.0),
        (180.0, math.nan, 1000.0),
        (180.0, 25.0, math.nan),
        (math.inf, 25.0, 1000.0),
        (180.0, math.inf, 1000.0),
        (180.0, 25.0, math.inf),
    ],
)
def test_k7_spindle_rpm_hatali_girdi(css, x, rpm_max):
    with pytest.raises(CamError):
        spindle_rpm(css, x, rpm_max)


def test_lathe_dialect_dondurulmus():
    d = LatheDialect("deneme", 3, 3, 4, True, 10, ("%",), ("M30", "%"))
    with pytest.raises(AttributeError):
        d.decimals = 4  # type: ignore[misc]
