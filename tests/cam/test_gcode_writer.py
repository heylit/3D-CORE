"""SPEC 04 — G-code yazıcı (son işlemci) testleri: K2, K3, K14 ve Ek A yazım kuralları.

Testler sadece SPEC 04 metninden (Teori, Arayüz, Ek A ve altın örnek) yazıldı; `cam/gcode/`
uygulama kodu okunmadı. Altın metinler Ek A'dan birebir kopyalandı. Diğer beklenen metinler
Ek A kurallarından elle türetildi; her satırın gerekçesi yanında yazılı.

Kurallar (SPEC 04 Ek A):
- satırlar `\\n` ile ayrılır, metin `\\n` ile biter, kelimeler tek boşlukla ayrılır;
- kelime sırası `N G X Y Z I J R Q F S T M`;
- modal bastırma yuvarlanmış metin üzerinden: `fmt(yeni) == fmt(durum)` ise yazılmaz;
- G0'da F yazılmaz; yayda I ve J her zaman yazılır;
- op başında takım farklıysa takım değişimi, sonra `S<rpm> M3`, sonra üç eksenli `G0 X Y Z`.
"""

from __future__ import annotations

import pytest

from cam.gcode import FANUC, GRBL, write
from cam.model import CamError, Move, MoveType, Tool, ToolKind, Toolpath

G0, G1, G2, G3 = MoveType.RAPID, MoveType.LINEAR, MoveType.ARC_CW, MoveType.ARC_CCW


def freze6() -> Tool:
    """Ek A altın örneğindeki takım: Tool(1, "freze6", FLAT, D=6, flute_length=20)."""
    return Tool(1, "freze6", ToolKind.FLAT, D=6.0, flute_length=20.0)


def freze10() -> Tool:
    return Tool(2, "freze10", ToolKind.FLAT, D=10.0, flute_length=30.0)


def golden_path() -> Toolpath:
    """Ek A altın örneği: 10x10 kare kontur, üst kenar yerine yarım daire (G3, merkez (5, 10))."""
    return Toolpath(
        name="altin",
        tool=freze6(),
        start=(0.0, 0.0, 5.0),
        rpm=10_000.0,
        moves=[
            Move(G1, (0.0, 0.0, -1.0), feed=100.0),
            Move(G1, (10.0, 0.0, -1.0), feed=300.0),
            Move(G1, (10.0, 10.0, -1.0), feed=300.0),
            Move(G3, (0.0, 10.0, -1.0), feed=300.0, center=(5.0, 10.0)),
            Move(G1, (0.0, 0.0, -1.0), feed=300.0),
            Move(G0, (0.0, 0.0, 5.0)),
        ],
    )


# Ek A "Altın örnek (K2)" — GRBL, birebir.
GOLDEN_GRBL = """\
G21 G90 G17 G94
T1
S10000 M3
G0 X0. Y0. Z5.
G1 Z-1. F100.
X10. F300.
Y10.
G3 X0. I-5. J0.
G1 Y0.
G0 Z5.
M5
M30
"""

# Ek A "Altın örnek (K2)" — Fanuc, birebir.
GOLDEN_FANUC = """\
%
O0001
N10 G21 G90 G17 G94 G40 G49 G80
N20 T1 M6
N30 S10000 M3
N40 G0 X0. Y0. Z5.
N50 G1 Z-1. F100.
N60 X10. F300.
N70 Y10.
N80 G3 X0. I-5. J0.
N90 G1 Y0.
N100 G0 Z5.
N110 M5
N120 M30
%
"""


def lines_of(text: str) -> list[str]:
    """Metin `\\n` ile bitmeli (Ek A); son boş parçayı atıp satır listesi döndürür."""
    assert text.endswith("\n")
    return text[:-1].split("\n")


def body(text: str, n_header: int = 1, n_footer: int = 2) -> list[str]:
    """GRBL çıktısının baş (1 satır) ve son (M5, M30) satırları dışındaki gövdesi."""
    ls = lines_of(text)
    return ls[n_header : len(ls) - n_footer]


# ---------------------------------------------------------------- K2: altın metin


def test_golden_grbl_line_by_line():
    """K2: Ek A GRBL altın metni satır satır (modal bastırma, I/J, baş/son dahil)."""
    out = write([golden_path()], GRBL)
    assert lines_of(out) == lines_of(GOLDEN_GRBL)
    assert out == GOLDEN_GRBL


def test_golden_fanuc_line_by_line():
    """K2: Ek A Fanuc altın metni satır satır (% / O0001, N10.. her satırda, T1 M6)."""
    out = write([golden_path()], FANUC)
    assert lines_of(out) == lines_of(GOLDEN_FANUC)
    assert out == GOLDEN_FANUC


def test_default_dialect_is_grbl():
    """Arayüz: write(ops, dialect=GRBL, program_no=1)."""
    assert write([golden_path()]) == GOLDEN_GRBL


def test_fanuc_program_number():
    """Ek A: program numarası `O{program_no:04d}` → program_no = 42 için `O0042`."""
    ls = lines_of(write([golden_path()], FANUC, program_no=42))
    assert ls[0] == "%"
    assert ls[1] == "O0042"
    assert ls[-1] == "%"


def test_words_single_space_no_trailing():
    """Ek A: kelimeler tek boşlukla ayrılır; satır başı/sonu boşluk yok, boş satır yok."""
    for out in (write([golden_path()], GRBL), write([golden_path()], FANUC)):
        for ln in lines_of(out):
            assert ln
            assert ln == ln.strip()
            assert "  " not in ln


# ---------------------------------------------------------------- K3: modal bastırma


def test_modal_feed_and_g1_written_once():
    """K3: aynı F ve aynı hareket tipindeki ardışık G1'lerde F ve G1 bir kez; değişmeyen eksen yok.

    Hareketler (başlangıç (0,0,5)): dalma Z-1 F200, sonra XY'de üç doğru, hepsi F200.
    Beklenen gövde Ek A kurallarından elle:
      G0 X0. Y0. Z5.     ← op başı, üç eksen her zaman
      G1 Z-1. F200.      ← sadece Z değişti; ilk F
      X10.               ← G1 ve F modal, Y/Z değişmedi
      X20.
      Y5.
    """
    tp = Toolpath(
        "k3",
        freze6(),
        (0.0, 0.0, 5.0),
        rpm=10_000.0,
        moves=[
            Move(G1, (0.0, 0.0, -1.0), feed=200.0),
            Move(G1, (10.0, 0.0, -1.0), feed=200.0),
            Move(G1, (20.0, 0.0, -1.0), feed=200.0),
            Move(G1, (20.0, 5.0, -1.0), feed=200.0),
        ],
    )
    out = write([tp], GRBL)
    assert body(out)[2:] == ["G0 X0. Y0. Z5.", "G1 Z-1. F200.", "X10.", "X20.", "Y5."]
    words = out.split()
    assert words.count("G1") == 1
    assert sum(w.startswith("F") for w in words) == 1


def test_modal_suppression_uses_rounded_text():
    """Ek A: bastırma yuvarlanmış metin üzerinden: fmt(10.0003) == fmt(10.0001) == "10." → X yazılmaz;
    fmt(200.04, 1) == fmt(200, 1) == "200." → F yazılmaz."""
    tp = Toolpath(
        "yuvarlama",
        freze6(),
        (0.0, 0.0, 5.0),
        rpm=10_000.0,
        moves=[
            Move(G1, (10.0001, 0.0, 5.0), feed=200.0),
            Move(G1, (10.0003, 5.0, 5.0), feed=200.04),
        ],
    )
    assert body(write([tp], GRBL))[2:] == ["G0 X0. Y0. Z5.", "G1 X10. F200.", "Y5."]


def test_g0_has_no_feed_and_feed_stays_modal_across_g0():
    """Ek A: G0'da F yazılmaz. F modaldır (Teori): G0'dan sonra aynı F ile gelen G1 F yazmaz,
    ama hareket tipi değiştiği için G1 kelimesi yeniden yazılır."""
    tp = Toolpath(
        "g0f",
        freze6(),
        (0.0, 0.0, 5.0),
        rpm=10_000.0,
        moves=[
            Move(G1, (0.0, 0.0, -1.0), feed=150.0),
            Move(G0, (0.0, 0.0, 5.0)),
            Move(G0, (20.0, 0.0, 5.0)),
            Move(G1, (20.0, 0.0, -1.0), feed=150.0),
            Move(G1, (30.0, 0.0, -1.0), feed=400.0),
        ],
    )
    assert body(write([tp], GRBL))[2:] == [
        "G0 X0. Y0. Z5.",
        "G1 Z-1. F150.",
        "G0 Z5.",
        "X20.",          # G0 modal, F yok
        "G1 Z-1.",       # F150 durumda zaten var
        "X30. F400.",
    ]


def test_arc_always_writes_I_J_and_full_circle():
    """Ek A: yayda I ve J her zaman (0 olsa da), X/Y/Z sadece değiştiyse.

    Başlangıç (0,0,-1), merkez (5,0):
      tam daire (bitiş = başlangıç): I = 5 − 0 = 5, J = 0 − 0 = 0 → `G2 I5. J0. F500.`
      helis tam daire Z −1 → −3:                                 → `Z-3. I5. J0.` (G2 modal)
      yarım daire (10,0,-3) G3, merkez (5,0): I = 5 − 0 = 5, J = 0 → `G3 X10. I5. J0.`
    """
    tp = Toolpath(
        "daire",
        freze6(),
        (0.0, 0.0, -1.0),
        rpm=10_000.0,
        moves=[
            Move(G2, (0.0, 0.0, -1.0), feed=500.0, center=(5.0, 0.0)),
            Move(G2, (0.0, 0.0, -3.0), feed=500.0, center=(5.0, 0.0)),
            Move(G3, (10.0, 0.0, -3.0), feed=500.0, center=(5.0, 0.0)),
        ],
    )
    assert body(write([tp], GRBL))[2:] == [
        "G0 X0. Y0. Z-1.",
        "G2 I5. J0. F500.",
        "Z-3. I5. J0.",
        "G3 X10. I5. J0.",
    ]


def test_arc_ij_from_rounded_center_and_start():
    """Teori: I = round(cx) − round(x0) (yuvarlanmış merkez − yuvarlanmış başlangıç).

    x0 = 0.0004 → "0.";  cx = 5.0006 → "5.001";  I = 5.001 − 0 = 5.001 → `I5.001`.
    (Ham fark cx − x0 = 5.0002 → `I5.` olurdu; test ikisini ayırt eder.)
    Bitiş başlangıcın merkeze göre tam karşısı: x1 = 2·cx − x0 = 10.0008 → `X10.001`; r0 = r1 = 5.0002.
    """
    x0, cx = 0.0004, 5.0006
    tp = Toolpath(
        "ij",
        freze6(),
        (x0, 0.0, 0.0),
        rpm=10_000.0,
        moves=[Move(G2, (2 * cx - x0, 0.0, 0.0), feed=500.0, center=(cx, 0.0))],
    )
    assert body(write([tp], GRBL))[2:] == ["G0 X0. Y0. Z0.", "G2 X10.001 I5.001 J0. F500."]


# ---------------------------------------------------------------- Çok takım, devir


def three_ops() -> list[Toolpath]:
    """İki takım, üç op: op1 ve op2 T1 / 10000 dev/dk, op3 T2 / 8000 dev/dk."""
    t1, t2 = freze6(), freze10()
    op1 = Toolpath(
        "op1",
        t1,
        (0.0, 0.0, 5.0),
        rpm=10_000.0,
        moves=[
            Move(G1, (0.0, 0.0, -1.0), feed=100.0),
            Move(G1, (20.0, 0.0, -1.0), feed=300.0),
            Move(G0, (20.0, 0.0, 5.0)),
        ],
    )
    op2 = Toolpath(
        "op2",
        t1,
        (40.0, 0.0, 5.0),
        rpm=10_000.0,
        moves=[
            Move(G1, (40.0, 0.0, -2.0), feed=100.0),
            Move(G2, (50.0, 0.0, -2.0), feed=300.0, center=(45.0, 0.0)),
            Move(G0, (50.0, 0.0, 5.0)),
        ],
    )
    op3 = Toolpath(
        "op3",
        t2,
        (0.0, 30.0, 5.0),
        rpm=8_000.0,
        moves=[
            Move(G1, (0.0, 30.0, -3.0), feed=80.0),
            Move(G1, (30.0, 30.0, -3.0), feed=150.0),
            Move(G0, (30.0, 30.0, 5.0)),
        ],
    )
    return [op1, op2, op3]


# Ek A kurallarından elle: op2 aynı takım + devir → takım/S satırı yok, ama op başı `G0 X Y Z`
# her zaman üç eksenle; op3'te GRBL ikinci takım `T2 M0`, ardından her zaman `S8000 M3`.
# op2 yayı: I = 45 − 40 = 5, J = 0; F 100'den 300'e değiştiği için yazılır.
MULTI_GRBL = """\
G21 G90 G17 G94
T1
S10000 M3
G0 X0. Y0. Z5.
G1 Z-1. F100.
X20. F300.
G0 Z5.
G0 X40. Y0. Z5.
G1 Z-2. F100.
G2 X50. I5. J0. F300.
G0 Z5.
T2 M0
S8000 M3
G0 X0. Y30. Z5.
G1 Z-3. F80.
X30. F150.
G0 Z5.
M5
M30
"""


def test_multi_tool_grbl_text():
    """GRBL: ilk takım `T1`, sonraki `T2 M0` (Ek A); aynı takımlı op arasında T/S yok."""
    assert write(three_ops(), GRBL) == MULTI_GRBL


def test_multi_tool_fanuc_text():
    """Fanuc: aynı gövde, her satır N10'dan 10'ar artan numaralı, takım değişimi `T<n> M6` (Ek A)."""
    govde = lines_of(MULTI_GRBL)[1:]                      # GRBL başı hariç
    govde = [{"T1": "T1 M6", "T2 M0": "T2 M6"}.get(ln, ln) for ln in govde]
    satirlar = ["G21 G90 G17 G94 G40 G49 G80"] + govde
    beklenen = ["%", "O0001"] + [f"N{10 * (i + 1)} {ln}" for i, ln in enumerate(satirlar)] + ["%"]
    assert lines_of(write(three_ops(), FANUC)) == beklenen


def test_rpm_change_only_writes_S_and_rounds_rpm():
    """Ek A: devir tek başına değişirse sadece `S<rpm> M3`; devir tam sayıya yuvarlanır.

    op1 rpm 9999.6 → `S10000`; op2 aynı takım, rpm 12000.3 → `S12000 M3`, T satırı yok.
    """
    t1 = freze6()
    op1 = Toolpath("a", t1, (0.0, 0.0, 5.0), rpm=9_999.6, moves=[Move(G1, (0.0, 0.0, 0.0), feed=100.0)])
    op2 = Toolpath("b", t1, (10.0, 0.0, 5.0), rpm=12_000.3, moves=[Move(G1, (10.0, 0.0, 0.0), feed=100.0)])
    assert lines_of(write([op1, op2], GRBL)) == [
        "G21 G90 G17 G94",
        "T1",
        "S10000 M3",
        "G0 X0. Y0. Z5.",
        "G1 Z0. F100.",
        "S12000 M3",
        "G0 X10. Y0. Z5.",
        "G1 Z0.",
        "M5",
        "M30",
    ]


# ---------------------------------------------------------------- K14: geçersiz yol reddi


@pytest.mark.parametrize(
    "moves, rpm",
    [
        ([Move(G1, (10.0, 0.0, 0.0))], 10_000.0),                                 # ilerlemesiz G1 (K14)
        ([Move(G1, (10.0, 0.0, 0.0), feed=0.0)], 10_000.0),                       # F = 0
        ([Move(G2, (10.0, 0.0, 0.0), feed=100.0)], 10_000.0),                     # merkezsiz yay
        ([Move(G3, (10.0, 0.0, 0.0), feed=100.0, center=(4.0, 0.0))], 10_000.0),  # r0 = 4, r1 = 6
        ([Move(G1, (10.0, 0.0, 0.0), feed=100.0)], 0.0),                          # devir 0
    ],
)
def test_write_rejects_invalid_toolpath(moves, rpm):
    """K14: write önce Toolpath.validate() çağırır → geçersiz yolda CamError (her iki dilde)."""
    tp = Toolpath("bozuk", freze6(), (0.0, 0.0, 0.0), moves=moves, rpm=rpm)
    with pytest.raises(CamError):
        tp.validate()                       # kontrol: örnek gerçekten geçersiz (cam/model.py)
    with pytest.raises(CamError):
        write([tp], GRBL)
    with pytest.raises(CamError):
        write([tp], FANUC)


def test_write_rejects_invalid_toolpath_in_second_op():
    """K14: doğrulama her op için; ikinci op bozuksa da CamError (kısmi çıktı yok)."""
    iyi = golden_path()
    bozuk = Toolpath("bozuk", freze6(), (0.0, 0.0, 0.0), rpm=1000.0, moves=[Move(G1, (1.0, 0.0, 0.0))])
    with pytest.raises(CamError):
        write([iyi, bozuk], GRBL)
