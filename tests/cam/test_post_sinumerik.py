"""SPEC 31 — Siemens Sinumerik doğal dil postprosesörü ve okuyucusu (K1, K5–K9).

Testler esas olarak `post()` ve `read_program()` üzerinden, yalnız SPEC 31 metninden yazıldı; uygulama kodu
okunmadı. Altın metin testleri profilin `tool_change_z = None` kopyasını kullanır (SPEC 30 K12 gibi).
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from cam.model import CamError
from cam.post import SINUMERIK, dialect_for, post, read_program
from tests.cam.post31_ortak import (
    DELIKLER,
    KURULUM,
    RPM,
    SIN_M,
    altin,
    ayni_mesaj,
    drill,
    guvenlik_durumlari,
    ornek,
    satir_hatasi,
    satirlar,
)
from tests.cam.post_ortak import altin_yol, iki_takim, kurulum, ortala, takim
from tests.cam.test_gcode_roundtrip import SEED, as_written, assert_paths_close, random_path, safe_z_of

GOLDEN = """\
; POST ORNEK-SINUMERIK-DIK SINUMERIK
; DOGRULANMAMIS PROFIL - ILK PARCADA KURU CALISTIRIN
G71 G90 G17 G94 G40 G54
T1 M6
D1
S10000 M3
G0 X0 Y0 Z5
G1 Z-1 F100
X10 F300
Y10
G3 X0 I-5 J0
G1 Y0
G0 Z5
M5
M30
"""


def _oku(text: str, m=None, tools=None):
    m = m or altin(SIN_M)
    return read_program(text, m, tools or {1: takim(1)})


# ---------------------------------------------------------------- profil ve dil


def test_profil_ve_dil():
    m = ornek(SIN_M)
    assert m.controller == "sinumerik"
    assert m.verified is False
    assert m.presets is None
    m.validate()
    d = dialect_for(m)
    assert d == SINUMERIK
    assert d.canned_cycles is False


# ---------------------------------------------------------------- K1


def test_K1_altin_metin():
    out = post([altin_yol(takim(1))], altin(SIN_M), KURULUM, safe_z=5.0)
    assert satirlar(out) == satirlar(GOLDEN)
    assert out == GOLDEN


def test_K1_altin_geri_okuma():
    """Altın metin okununca SPEC 04 Ek A yolu (yazıldığı biçimiyle) geri gelir."""
    tp = altin_yol(takim(1))
    got = _oku(GOLDEN)
    assert len(got) == 1
    got[0].validate()
    assert got[0].tool == tp.tool
    assert got[0].rpm == 10_000
    assert_paths_close(got[0], as_written(tp, 5.0))


def test_dogrulanmis_profil_tek_yorum():
    m = replace(altin(SIN_M), verified=True)
    ls = satirlar(post([altin_yol(takim(1))], m, KURULUM, safe_z=5.0))
    assert ls[0] == "; POST ORNEK-SINUMERIK-DIK SINUMERIK"
    assert sum(ln.startswith(";") for ln in ls) == 1


# ---------------------------------------------------------------- K5


@pytest.mark.parametrize("seed", [SEED, 1, 3])
def test_K5_rastgele_gidis_donus(seed):
    """SPEC 04 K4 rastgele yolları (tam daire, helis dahil): tipler, uç ≤ 0.5e-3, merkez ≤ 1e-2, devir."""
    m = ornek(SIN_M)
    tp0, _ = random_path(seed)
    tp = replace(tp0, tool=takim(1, L=100.0), rpm=RPM)
    z_s = safe_z_of(tp)
    setup = ortala(m, [tp], 100.0, z_ek=z_s)
    got = read_program(post([tp], m, setup, safe_z=z_s), m, {1: tp.tool})
    assert len(got) == 1
    got[0].validate()
    assert got[0].tool == tp.tool
    assert got[0].rpm == RPM
    assert_paths_close(got[0], as_written(tp, z_s))


# ---------------------------------------------------------------- K6


@pytest.mark.parametrize("kind,retract", DELIKLER)
def test_K6_delik_kanonik_acilim(kind, retract):
    m = altin(SIN_M)
    op = drill(kind, retract)
    out = post([op], m, KURULUM, safe_z=5.0)
    assert "CYCLE" not in out
    assert "G81" not in out and "G83" not in out
    got = read_program(out, m, {1: op.tool})
    assert len(got) == 1
    got[0].validate()
    assert_paths_close(got[0], as_written(op.to_toolpath(SINUMERIK), 5.0))


# ---------------------------------------------------------------- K7


@pytest.mark.parametrize("ad,ops,setup,kw", guvenlik_durumlari(), ids=[g[0] for g in guvenlik_durumlari()])
def test_K7_guvenlik_ayni_mesaj(ad, ops, setup, kw):
    ayni_mesaj(ornek(SIN_M), ops, setup, kw)


def test_K7_iki_takim_geri_cekme_ve_M5():
    """İki takımlı program: takım değişiminden önce geri çekme ve M5; sonra `D1`.

    840D sl varsayılanında D numarası takımın kesici ağzıdır: her takımın ilk ağzı D1."""
    m = altin(SIN_M)
    ops = iki_takim(takim(1, L=100.0), takim(2, L=100.0, D=10.0))
    ls = satirlar(post(ops, m, KURULUM))
    i = ls.index("T2 M6")
    assert ls[i - 2 : i] == ["G0 Z5", "M5"]
    assert ls[i + 1] == "D1"
    got = read_program("\n".join(ls) + "\n", m, {1: ops[0].tool, 2: ops[1].tool})
    assert [g.tool.id for g in got] == [1, 2]
    assert [g.rpm for g in got] == [10_000, 8_000]


def test_length_offsets_hata():
    with pytest.raises(CamError):
        post([altin_yol(takim(1))], altin(SIN_M), KURULUM, safe_z=5.0, length_offsets={1: 0.0})


# ---------------------------------------------------------------- K8


@pytest.mark.parametrize("code", ["G55", "G56", "G57"])
def test_K8_is_sifiri_basta(code):
    out = post([altin_yol(takim(1))], altin(SIN_M), kurulum((0.0, 0.0, -200.0), code), safe_z=5.0)
    ls = satirlar(out)
    assert ls[2] == f"G71 G90 G17 G94 G40 {code}"
    assert sum(code in ln for ln in ls) == 1
    got = read_program(out, altin(SIN_M), {1: takim(1)})
    assert_paths_close(got[0], as_written(altin_yol(takim(1)), 5.0))


@pytest.mark.parametrize("code", ["G58", "G59"])
def test_K8_eksen_ofseti_hata(code):
    """G58 / G59 Siemens'te eksen ofsetidir, iş sıfırı değil → CamError."""
    with pytest.raises(CamError):
        post([altin_yol(takim(1))], altin(SIN_M), kurulum((0.0, 0.0, -200.0), code), safe_z=5.0)


# ---------------------------------------------------------------- K9


def _degis(eski: str, yeni: str) -> str:
    assert eski in GOLDEN
    return GOLDEN.replace(eski, yeni, 1)


HATALI = {
    "G70 inc": _degis("G71 G90", "G70 G90"),
    "D0": _degis("D1\n", "D0\n"),
    "D'siz hareket": _degis("D1\n", ""),
    "CR=": _degis("G3 X0 I-5 J0", "G3 X0 CR=5"),
    "G91": _degis("X10 F300\n", "G91\nX10 F300\n"),
    "bilinmeyen kod": _degis("Y10\n", "Y10\nG33\n"),
    "bilinmeyen M": _degis("Y10\n", "Y10 M8\n"),
    "AC": _degis("X10 F300", "X=AC(10) F300"),
    "degisken": _degis("Y10\n", "R1=5\nY10\n"),
    "cevrim": _degis("Y10\n", "Y10\nCYCLE81(5, 0, 1, -5)\n"),
}


@pytest.mark.parametrize("ad", list(HATALI))
def test_K9_okuyucu_hatalari(ad):
    satir_hatasi(_oku, HATALI[ad])


def test_K9_satir_numarasi_dogru_satiri_gosterir():
    """`CR=` hatası 11. satırda (1'den sayılır) ya da 0'dan sayılınca 10'da: mesaj o satırı göstermeli."""
    with pytest.raises(CamError, match=r"satır (10|11)\b"):
        _oku(HATALI["CR="])


def test_okuyucu_yorumlari_yok_sayar():
    """`; yorum` satırları ve satır sonu yorumları yola yansımaz."""
    text = GOLDEN.replace("Y10\n", "Y10 ; ust kenar\n; ara yorum\n", 1)
    got = _oku(text)
    assert_paths_close(got[0], as_written(altin_yol(takim(1)), 5.0))
