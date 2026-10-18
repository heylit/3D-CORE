"""SPEC 14 — yazıcı ve okuyucu kurulum ekleri: K11 (iş sıfırı, güvenli Z, G43.1), K12 (okuyucu),
K13 (geriye uyum).

Testler sadece SPEC 14 metninden (Ek A altın metinleri) yazıldı; `cam/gcode/` ve SPEC 14 uygulama
kodu okunmadı.

Okuyucu karşılaştırma toleransı SPEC 04 ile aynı: uç nokta koordinat başına 0.5e-3 + 1e-9 mm,
ilerleme 0.05 + 1e-9 mm/dk. Burada tüm değerler yazılan basamakta tam olduğundan fark 0 beklenir.
"""

from __future__ import annotations

import numpy as np
import pytest

from cam.gcode import FANUC, GRBL, DrillOp, fmt, read, write
from cam.model import (
    CamError,
    Move,
    MoveType,
    Setup,
    Stock,
    Tool,
    ToolHolder,
    ToolKind,
    ToolLibrary,
    Toolpath,
    Wcs,
)
from cam.tool_length import ToolSetter, fanuc_offset_table, length_offsets, probe_program

G0, G1 = MoveType.RAPID, MoveType.LINEAR
TOL_END = 0.5e-3 + 1e-9
TOL_FEED = 0.05 + 1e-9

# ---------------------------------------------------------------- Ek A örneği


def tutucu() -> ToolHolder:
    return ToolHolder("BT30-ER", 60.0, ((0.0, 15.0), (40.0, 20.0)))


def T1() -> Tool:
    return Tool(
        1, "freze6", ToolKind.FLAT, D=6.0, flute_length=20.0, flutes=3, stickout=30.0, holder=tutucu()
    )


def T2() -> Tool:
    return Tool(
        2, "matkap5", ToolKind.DRILL, D=5.0, flute_length=40.0, flutes=2, stickout=45.0, holder=tutucu()
    )


def kutuphane() -> ToolLibrary:
    return ToolLibrary([T1(), T2()])


def takimlar() -> dict[int, Tool]:
    return {1: T1(), 2: T2()}


def kurulum(code: str = "G55") -> Setup:
    return Setup(
        "on-yuz",
        Wcs(code, (-250.0, -190.0, -80.0)),
        Stock(0.0, 0.0, -20.0, 50.0, 40.0, 0.0),
        fixtures=[Stock(-15.0, 0.0, -20.0, -5.0, 40.0, 10.0)],
    )


def tp1(z0: float = 15.0) -> Toolpath:
    moves = [Move(G1, (5.0, 5.0, -1.0), 100.0), Move(G1, (15.0, 5.0, -1.0), 300.0)]
    return Toolpath("cep", T1(), (5.0, 5.0, z0), moves, rpm=10000)


def tp2(z0: float = 15.0) -> Toolpath:
    return Toolpath("delik", T2(), (20.0, 20.0, z0), [Move(G1, (20.0, 20.0, -5.0), 150.0)], rpm=3000)


def ops(z0: float = 15.0) -> list[Toolpath]:
    return [tp1(z0), tp2(z0)]


OFSET = {1: 0.0, 2: 15.0}

ALTIN_GRBL = """G21 G90 G17 G94 G55
T1
G43.1 Z0.
S10000 M3
G0 X5. Y5. Z15.
G1 Z-1. F100.
X15. F300.
G0 Z15.
M5
T2 M0
G43.1 Z15.
S3000 M3
G0 X20. Y20. Z15.
G1 Z-5. F150.
G0 Z15.
M5
M30
"""

ALTIN_FANUC = """%
O0001
N10 G21 G90 G17 G94 G40 G49 G80 G55
N20 T1 M6
N30 S10000 M3
N40 G0 G43 X5. Y5. Z15. H1
N50 G1 Z-1. F100.
N60 X15. F300.
N70 G0 Z15.
N80 M5
N90 T2 M6
N100 S3000 M3
N110 G0 G43 X20. Y20. Z15. H2
N120 G1 Z-5. F150.
N130 G0 Z15.
N140 M5
N150 M30
%
"""


def g431siz(metin: str) -> str:
    """Altın GRBL metninden G43.1 satırlarını çıkarır."""
    return "".join(s for s in metin.splitlines(keepends=True) if not s.startswith("G43.1"))


def wcs_siz(metin: str, code: str = "G55", yerine: str = "") -> str:
    """Baş satırdaki iş sıfırı kodunu çıkarır / değiştirir (ilk geçiş)."""
    return metin.replace(f" {code}\n", f"{yerine}\n", 1)


# SPEC 04 davranışı: setup'sız GRBL ve Fanuc metni (Ek A'dan türetilmiş)
ESKI_GRBL = wcs_siz(g431siz(ALTIN_GRBL))
ESKI_FANUC = wcs_siz(ALTIN_FANUC, yerine=" G54")


def onceki_satirlar(metin: str, hedef: str) -> list[str]:
    satirlar = metin.splitlines()
    return [satirlar[i - 1] for i, s in enumerate(satirlar) if s == hedef]


# ---------------------------------------------------------------- K11 altın metinler


def test_on_ayar_ofsetleri_ek_a():
    assert length_offsets(kutuphane(), [1, 2], ref_id=1) == {1: pytest.approx(0.0), 2: pytest.approx(15.0)}
    assert fanuc_offset_table(kutuphane(), [1, 2]) == {1: pytest.approx(90.0), 2: pytest.approx(105.0)}


def test_grbl_altin_metin():
    assert write(ops(), GRBL, setup=kurulum(), length_offsets=OFSET) == ALTIN_GRBL


def test_grbl_altin_metin_kutuphaneden_ofset():
    ofset = length_offsets(kutuphane(), [1, 2], ref_id=1)
    assert write(ops(), GRBL, setup=kurulum(), length_offsets=ofset) == ALTIN_GRBL


def test_fanuc_altin_metin():
    assert write(ops(), FANUC, setup=kurulum()) == ALTIN_FANUC


def test_grbl_sadece_setup():
    assert write(ops(), GRBL, setup=kurulum()) == g431siz(ALTIN_GRBL)


def test_grbl_sadece_ofset():
    assert write(ops(), GRBL, length_offsets=OFSET) == wcs_siz(ALTIN_GRBL)


@pytest.mark.parametrize("code", ["G54", "G56", "G57", "G58", "G59"])
def test_is_sifiri_kodu_grbl(code):
    metin = write(ops(), GRBL, setup=kurulum(code))
    assert metin.splitlines()[0] == f"G21 G90 G17 G94 {code}"


@pytest.mark.parametrize("code", ["G54", "G56", "G59"])
def test_is_sifiri_kodu_fanuc(code):
    metin = write(ops(), FANUC, setup=kurulum(code))
    assert metin.splitlines()[2] == f"N10 G21 G90 G17 G94 G40 G49 G80 {code}"
    assert metin.count(" G54") == (1 if code == "G54" else 0)


def test_ofset_ondalikli():
    metin = write(ops(), GRBL, length_offsets={1: 0.0, 2: -2.5})
    satirlar = metin.splitlines()
    assert satirlar[satirlar.index("T2 M0") + 1] == f"G43.1 Z{fmt(-2.5, 3)}"
    assert satirlar[satirlar.index("T1") + 1] == "G43.1 Z0."


def test_ofset_delik_op_ile():
    """DrillOp da takım değişimi alır; ondan sonra da G43.1 gelir."""
    d = DrillOp(
        "delikler", T2(), rpm=3000, start=(20.0, 20.0, 15.0), holes=[(20.0, 20.0)], z=-5.0, r=2.0, feed=150.0
    )
    metin = write([tp1(), d], GRBL, setup=kurulum(), length_offsets=OFSET)
    satirlar = metin.splitlines()
    assert satirlar[satirlar.index("T2 M0") + 1] == "G43.1 Z15."


# ---------------------------------------------------------------- K11 güvenli Z


def test_guvenli_z_setupdan():
    """Op başları z = 12 < clearance_height = 15: güvenli Z kurulumdan gelir."""
    metin = write(ops(12.0), GRBL, setup=kurulum())
    assert onceki_satirlar(metin, "M5") == ["G0 Z15.", "G0 Z15."]


def test_guvenli_z_op_basi_daha_yuksekse():
    metin = write(ops(20.0), GRBL, setup=kurulum())
    assert onceki_satirlar(metin, "M5") == ["G0 Z20.", "G0 Z20."]


def test_guvenli_z_verilmis_gecerli():
    """safe_z = 10.5 ≥ clearance_height − CLEARANCE = 10 ve op başlarından (8) yüksek."""
    metin = write(ops(8.0), GRBL, setup=kurulum(), safe_z=10.5)
    assert onceki_satirlar(metin, "M5") == [f"G0 Z{fmt(10.5, 3)}"] * 2


def test_guvenli_z_baglamadan_alcak_hata():
    """safe_z = 9.5 < 10 (çene üstü): çeneye çarpar."""
    with pytest.raises(CamError):
        write(ops(8.0), GRBL, setup=kurulum(), safe_z=9.5)


# ---------------------------------------------------------------- K11 hatalar


def test_fanuc_ofset_verilirse_hata():
    with pytest.raises(CamError):
        write(ops(), FANUC, setup=kurulum(), length_offsets=OFSET)
    with pytest.raises(CamError):
        write(ops(), FANUC, length_offsets=OFSET)


def test_eksik_takim_ofseti_hata():
    with pytest.raises(CamError):
        write(ops(), GRBL, setup=kurulum(), length_offsets={1: 0.0})
    with pytest.raises(CamError):
        write(ops(), GRBL, length_offsets={2: 15.0})


def test_baglamaya_carpan_op_hata():
    carpan = Toolpath("carpan", T1(), (25.0, 20.0, 15.0), [Move(G0, (-10.0, 20.0, 5.0))], rpm=10000)
    write([carpan], GRBL)  # kurulumsuz denetim yok (SPEC 04 davranışı)
    with pytest.raises(CamError):
        write([carpan], GRBL, setup=kurulum())
    with pytest.raises(CamError):
        write([carpan], FANUC, setup=kurulum())


# ---------------------------------------------------------------- K13 geriye uyum


def test_parametresiz_cikti_degismedi():
    assert write(ops(), GRBL) == ESKI_GRBL
    assert write(ops(), FANUC) == ESKI_FANUC
    assert write(ops(), GRBL, setup=None, length_offsets=None) == ESKI_GRBL
    assert write(ops(), FANUC, setup=None, length_offsets=None) == ESKI_FANUC


# ---------------------------------------------------------------- K12 okuyucu


def ayni_yollar(a: list[Toolpath], b: list[Toolpath]) -> None:
    assert len(a) == len(b)
    for p, q in zip(a, b, strict=True):
        assert p.tool.id == q.tool.id
        assert p.rpm == q.rpm
        np.testing.assert_allclose(p.start, q.start, atol=TOL_END)
        assert len(p.moves) == len(q.moves)
        for m, n in zip(p.moves, q.moves, strict=True):
            assert m.type == n.type
            np.testing.assert_allclose(m.end, n.end, atol=TOL_END)
            if m.feed is None or n.feed is None:
                assert m.feed is None and n.feed is None
            else:
                assert abs(m.feed - n.feed) <= TOL_FEED


def test_okuyucu_grbl_altin():
    ayni_yollar(read(ALTIN_GRBL, takimlar(), GRBL), read(write(ops(), GRBL), takimlar(), GRBL))


def test_okuyucu_fanuc_altin():
    ayni_yollar(read(ALTIN_FANUC, takimlar(), FANUC), read(write(ops(), FANUC), takimlar(), FANUC))


def test_okuyucu_orijinal_yollarla_ayni():
    """Okunan yolların hareketleri yazılan op'ların hareketlerini içerir: G43.1 Z yola yansımaz."""
    okunan = read(ALTIN_GRBL, takimlar(), GRBL)
    tum_z = [m.end[2] for p in okunan for m in p.moves]
    assert min(tum_z) == pytest.approx(-5.0)
    assert sum(1 for p in okunan for m in p.moves if m.type is G1) == 3


def test_g43_1_hareket_sayilmiyor():
    ofsetli = ESKI_GRBL.replace("T1\n", "T1\nG43.1 Z7.5\n").replace("T2 M0\n", "T2 M0\nG43.1 Z-3.\n")
    assert ofsetli != ESKI_GRBL
    ayni_yollar(read(ofsetli, takimlar(), GRBL), read(ESKI_GRBL, takimlar(), GRBL))


def test_g49_ve_is_sifiri_kodlari_kabul():
    for kod in ("G55", "G56", "G57", "G58", "G59"):
        metin = ESKI_GRBL.replace("G21 G90 G17 G94\n", f"G21 G90 G17 G94 {kod}\nG49\n", 1)
        ayni_yollar(read(metin, takimlar(), GRBL), read(ESKI_GRBL, takimlar(), GRBL))


@pytest.mark.parametrize("satir", ["G43.1 X1. Z0.", "G43.1 Y2. Z5.", "G1 G43.1 Z5. F100.", "G0 G43.1 Z5."])
def test_g43_1_baska_eksen_veya_hareketle_hata(satir):
    metin = ESKI_GRBL.replace("T1\n", f"T1\n{satir}\n")
    with pytest.raises(CamError):
        read(metin, takimlar(), GRBL)


@pytest.mark.parametrize("satir", ["G38.2 Z-5. F100.", "G53 G0 Z-1."])
def test_prob_ve_makine_koordinati_reddedilir(satir):
    metin = ESKI_GRBL.replace("T1\n", f"T1\n{satir}\n")
    with pytest.raises(CamError):
        read(metin, takimlar(), GRBL)


def test_olcum_programi_okunmaz():
    s = ToolSetter(x=-10.0, y=-20.0, z_start=-70.0, z_safe=-1.0, travel=50.0)
    with pytest.raises(CamError):
        read(probe_program([1, 2], s), takimlar(), GRBL)
