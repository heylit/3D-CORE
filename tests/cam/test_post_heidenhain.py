"""SPEC 31 — Heidenhain Klartext postprosesörü ve okuyucusu (K2–K9).

Testler esas olarak `post()` ve `read_program()` üzerinden, yalnız SPEC 31 metninden yazıldı; uygulama kodu
okunmadı. Altın metin testleri profilin `tool_change_z = None` kopyasını kullanır (SPEC 30 K12 gibi).
Satır karşılaştırmalarında blok numarası (`<n> `) ayrıca denetlenir, içerik numarasız karşılaştırılır.
"""

from __future__ import annotations

import math
import re
from dataclasses import replace

import numpy as np
import pytest

from cam.model import CamError, Move, Toolpath
from cam.post import HEIDENHAIN, dialect_for, post, read_program
from tests.cam.post31_ortak import (
    DELIKLER,
    HEI_M,
    KURULUM,
    RPM,
    TOL,
    altin,
    ayni_mesaj,
    drill,
    guvenlik_durumlari,
    ornek,
    satir_hatasi,
    satirlar,
)
from tests.cam.post_ortak import G0, G1, G2, G3, altin_yol, iki_takim, kurulum, ortala, takim
from tests.cam.test_gcode_roundtrip import SEED, as_written, assert_paths_close, random_path, safe_z_of

GOLDEN = """\
0 BEGIN PGM 1 MM
1 ; POST ORNEK-HEIDENHAIN-DIK HEIDENHAIN
2 ; DOGRULANMAMIS PROFIL - ILK PARCADA KURU CALISTIRIN
3 CYCL DEF 247 DATUM SETTING ~ Q339=+1
4 TOOL CALL 1 Z S10000
5 L X+0 Y+0 Z+5 R0 FMAX M3
6 L Z-1 R0 F100
7 L X+10 R0 F300
8 L Y+10 R0
9 CC X+5 Y+10
10 C X+0 Y+10 DR+ R0
11 L Y+0 R0
12 L Z+5 R0 FMAX M30
13 END PGM 1 MM
"""

_NO = re.compile(r"^(\d+) (.*)$")


def icerik(text: str) -> list[str]:
    """Blok numaraları 0'dan ardışık olmalı; numarasız satır içerikleri."""
    out = []
    for i, ln in enumerate(satirlar(text)):
        m = _NO.match(ln)
        assert m, ln
        assert int(m.group(1)) == i, ln
        out.append(m.group(2))
    return out


def _oku(text: str, m=None, tools=None):
    return read_program(text, m or altin(HEI_M), tools or {1: takim(1)})


def _yol(moves, start=(5.0, 0.0, 0.0), rpm=10_000.0) -> Toolpath:
    return Toolpath("yol", takim(1), start, rpm=rpm, moves=moves)


# ---------------------------------------------------------------- profil ve dil


def test_profil_ve_dil():
    m = ornek(HEI_M)
    assert m.controller == "heidenhain"
    assert m.verified is False
    assert m.presets == {"G54": 1, "G55": 2}
    m.validate()
    d = dialect_for(m)
    assert d == HEIDENHAIN
    assert d.canned_cycles is False


# ---------------------------------------------------------------- K2


def test_K2_altin_metin():
    m = replace(altin(HEI_M), presets={"G54": 1})
    out = post([altin_yol(takim(1))], m, KURULUM, safe_z=5.0)
    assert satirlar(out) == satirlar(GOLDEN)
    assert out == GOLDEN


def test_K2_ornek_profil_ayni_metin():
    """Örnek profilin kendi presets'i ({"G54": 1, "G55": 2}) G54'te aynı metni verir."""
    assert post([altin_yol(takim(1))], altin(HEI_M), KURULUM, safe_z=5.0) == GOLDEN


def test_K2_altin_geri_okuma():
    tp = altin_yol(takim(1))
    got = _oku(GOLDEN)
    assert len(got) == 1
    got[0].validate()
    assert got[0].tool == tp.tool
    assert got[0].rpm == 10_000
    assert_paths_close(got[0], as_written(tp, 5.0))


def test_program_adi():
    out = post([altin_yol(takim(1))], altin(HEI_M), KURULUM, safe_z=5.0, program_no=42)
    ls = satirlar(out)
    assert ls[0] == "0 BEGIN PGM 42 MM"
    assert ls[-1] == f"{len(ls) - 1} END PGM 42 MM"


# ---------------------------------------------------------------- K3: helis


def _cp(text: str) -> list[str]:
    return [s for s in icerik(text) if s.startswith("CP ")]


def test_K3_helis_iki_tur():
    """r = 5, 2 tam tur, Δz = −2 → `CP IPA+720 IZ-2 DR+`.

    Model bir harekette en çok bir tam tur taşır; iki tur ardışık iki tam daire helisidir. Biçimleyicinin
    bunları tek `CP IPA+720 IZ-2` bloğuna birleştirmesi (SPEC metni) ya da iki `CP IPA+360 IZ-1` yazması
    kabul edilir; toplam süpürme ve Δz aynı olmalı."""
    tp = _yol(
        [
            Move(G1, (5.0, 0.0, 0.0), feed=100.0),
            Move(G3, (5.0, 0.0, -1.0), feed=300.0, center=(0.0, 0.0)),
            Move(G3, (5.0, 0.0, -2.0), feed=300.0, center=(0.0, 0.0)),
        ],
        start=(5.0, 0.0, 5.0),
    )
    out = post([tp], altin(HEI_M), KURULUM, safe_z=5.0)
    cp = _cp(out)
    tek = [s for s in cp if re.match(r"CP IPA\+720 IZ-2 DR\+ R0( F\S+)?$", s)]
    cift = [s for s in cp if re.match(r"CP IPA\+360 IZ-1 DR\+ R0( F\S+)?$", s)]
    assert (len(tek), len(cp)) == (1, 1) or (len(cift), len(cp)) == (2, 2), cp
    # Her CP'den önce merkez: CC X+0 Y+0
    ic = icerik(out)
    for i, s in enumerate(ic):
        if s.startswith("CP "):
            assert ic[i - 1] == "CC X+0 Y+0", ic[i - 1]
    # Geri okuma: uç ≤ 0.5e-3, merkez aynı, toplam Δz −2
    got = _oku(out)
    assert len(got) == 1
    got[0].validate()
    son = got[0].moves[-1]
    pts = got[0].points()
    assert np.max(np.abs(pts[-1] - np.array([5.0, 0.0, 5.0]))) <= TOL  # program sonu geri çekme
    helis = [mv for mv in got[0].moves if mv.type is G3]
    assert helis and all(math.dist(mv.center, (0.0, 0.0)) <= 1e-9 for mv in helis)
    z_dip = min(p[2] for p in pts)
    assert abs(z_dip - (-2.0)) <= TOL
    assert son.type is G0


@pytest.mark.parametrize(
    "tip,son,ipa,dr",
    [(G3, (0.0, 5.0, -0.5), "+90", "+"), (G2, (0.0, -5.0, -0.5), "-90", "-")],
)
def test_K3_helis_doksan_derece(tip, son, ipa, dr):
    tp = _yol(
        [Move(G1, (5.0, 0.0, 0.0), feed=100.0), Move(tip, son, feed=300.0, center=(0.0, 0.0))],
        start=(5.0, 0.0, 5.0),
    )
    out = post([tp], altin(HEI_M), KURULUM, safe_z=5.0)
    cp = _cp(out)
    assert len(cp) == 1
    assert re.match(rf"CP IPA{re.escape(ipa)} IZ-0\.5 DR{re.escape(dr)} R0( F300)?$", cp[0]), cp[0]
    got = _oku(out)
    yay = [mv for mv in got[0].moves if mv.type is tip]
    assert len(yay) == 1
    assert np.max(np.abs(np.subtract(yay[0].end, son))) <= TOL
    assert math.dist(yay[0].center, (0.0, 0.0)) <= 1e-9


def test_kartezyen_yay_ve_tam_daire():
    """Z değişmeyen yay `C X Y DR± R0` (X ve Y her zaman); tam daire: C'nin bitişi başlangıca eşit."""
    tp = _yol(
        [
            Move(G1, (5.0, 0.0, -1.0), feed=100.0),
            Move(G2, (5.0, 0.0, -1.0), feed=300.0, center=(0.0, 0.0)),
            Move(G3, (0.0, 5.0, -1.0), feed=300.0, center=(0.0, 0.0)),
        ],
        start=(5.0, 0.0, 5.0),
    )
    out = post([tp], altin(HEI_M), KURULUM, safe_z=5.0)
    ic = icerik(out)
    c = [s for s in ic if s.startswith("C ")]
    assert c == ["C X+5 Y+0 DR- R0 F300", "C X+0 Y+5 DR+ R0"]
    assert sum(s == "CC X+0 Y+0" for s in ic) == 2  # CC her yayda yazılır
    got = _oku(out)
    assert [mv.type for mv in got[0].moves if mv.type in (G2, G3)] == [G2, G3]


# ---------------------------------------------------------------- K4: FMAX modal değil


def _fmax_yolu(f2: float) -> Toolpath:
    return _yol(
        [
            Move(G1, (0.0, 0.0, -1.0), feed=300.0),
            Move(G1, (10.0, 0.0, -1.0), feed=300.0),
            Move(G0, (10.0, 0.0, 2.0)),
            Move(G0, (20.0, 0.0, 2.0)),
            Move(G1, (20.0, 0.0, -1.0), feed=f2),
        ],
        start=(0.0, 0.0, 5.0),
    )


def test_K4_fmax_sonrasi_F_yazilmaz():
    out = post([_fmax_yolu(300.0)], altin(HEI_M), KURULUM, safe_z=5.0)
    ic = icerik(out)
    assert "L X+10 Z+2 R0 FMAX" not in ic  # yalnız değişen eksen: Z
    assert "L Z+2 R0 FMAX" in ic
    assert "L X+20 R0 FMAX" in ic
    i = ic.index("L X+20 R0 FMAX")
    assert ic[i + 1] == "L Z-1 R0"  # FMAX'tan sonraki kesme F'yi tekrar yazmaz
    assert all("FMAX" in s for s in ic if s.startswith("L ") and "Z+2" in s)
    got = _oku(out)
    kesme = [mv for mv in got[0].moves if mv.type is G1]
    assert [mv.feed for mv in kesme] == [300.0, 300.0, 300.0]


def test_K4_fmax_sonrasi_F_degisirse_yazilir():
    out = post([_fmax_yolu(200.0)], altin(HEI_M), KURULUM, safe_z=5.0)
    ic = icerik(out)
    i = ic.index("L X+20 R0 FMAX")
    assert ic[i + 1] == "L Z-1 R0 F200"
    got = _oku(out)
    assert [mv.feed for mv in got[0].moves if mv.type is G1] == [300.0, 300.0, 200.0]


def test_K4_okuyucu_fmax_modal_F_degistirmez():
    """Elle yazılmış metin: FMAX bloğu modal F'yi değiştirmez; F'siz kesme önceki F'yi kullanır."""
    text = GOLDEN.replace("8 L Y+10 R0\n", "8 L Y+10 R0 FMAX\n", 1)
    got = _oku(text)
    m = got[0].moves
    # 8. blok hızlı, sonraki yay F300 (modal)
    i = next(k for k, mv in enumerate(m) if mv.type is G3)
    assert m[i - 1].type is G0
    assert m[i].feed == 300.0


# ---------------------------------------------------------------- K5


@pytest.mark.parametrize("seed", [SEED, 1, 3])
def test_K5_rastgele_gidis_donus(seed):
    m = ornek(HEI_M)
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
    m = altin(HEI_M)
    op = drill(kind, retract)
    out = post([op], m, KURULUM, safe_z=5.0)
    assert not re.search(r"CYCL DEF 20\d", out)
    assert "CYCLE" not in out
    got = read_program(out, m, {1: op.tool})
    assert len(got) == 1
    got[0].validate()
    assert_paths_close(got[0], as_written(op.to_toolpath(HEIDENHAIN), 5.0))


# ---------------------------------------------------------------- K7


@pytest.mark.parametrize("ad,ops,setup,kw", guvenlik_durumlari(), ids=[g[0] for g in guvenlik_durumlari()])
def test_K7_guvenlik_ayni_mesaj(ad, ops, setup, kw):
    ayni_mesaj(ornek(HEI_M), ops, setup, kw)


def test_K7_iki_takim_geri_cekme_ve_M5():
    m = altin(HEI_M)
    ops = iki_takim(takim(1, L=100.0), takim(2, L=100.0, D=10.0))
    out = post(ops, m, KURULUM)
    ic = icerik(out)
    i = ic.index("TOOL CALL 2 Z S8000")
    assert ic[i - 1] == "L Z+5 R0 FMAX M5"
    assert ic.count("TOOL CALL 1 Z S10000") == 1
    # İkinci takımın ilk hareket bloğunda M3
    sonraki = next(s for s in ic[i + 1 :] if s.startswith("L "))
    assert sonraki.endswith(" M3") and "FMAX" in sonraki
    got = read_program(out, m, {1: ops[0].tool, 2: ops[1].tool})
    assert [g.tool.id for g in got] == [1, 2]
    assert [g.rpm for g in got] == [10_000, 8_000]


def test_takim_degisim_z_M91():
    """tool_change_z (makine koordinatı): `L Z+<v> R0 FMAX M91`; okuyucu yola yansıtmaz."""
    m = replace(ornek(HEI_M), tool_change_z=-12.5)
    ops = iki_takim(takim(1, L=100.0), takim(2, L=100.0, D=10.0))
    out = post(ops, m, KURULUM)
    ic = icerik(out)
    assert ic.count("L Z-12.5 R0 FMAX M91") == 2
    i = ic.index("TOOL CALL 2 Z S8000")
    assert ic[i - 1] == "L Z-12.5 R0 FMAX M91"
    assert "L Z+5 R0 FMAX M5" in ic[:i]
    tools = {1: ops[0].tool, 2: ops[1].tool}
    got = read_program(out, m, tools)
    exp = read_program(post(ops, replace(m, tool_change_z=None), KURULUM), m, tools)
    assert len(got) == len(exp) == 2
    for g, e in zip(got, exp, strict=True):
        assert_paths_close(g, e)


def test_length_offsets_hata():
    with pytest.raises(CamError):
        post([altin_yol(takim(1))], altin(HEI_M), KURULUM, safe_z=5.0, length_offsets={1: 0.0})


# ---------------------------------------------------------------- K8


def test_K8_preset_G55():
    out = post([altin_yol(takim(1))], altin(HEI_M), kurulum((0.0, 0.0, -200.0), "G55"), safe_z=5.0)
    ic = icerik(out)
    assert "CYCL DEF 247 DATUM SETTING ~ Q339=+2" in ic
    assert not any("Q339=+1" in s for s in ic)


@pytest.mark.parametrize("presets,code", [({"G54": 1}, "G55"), ({"G54": 1, "G55": 2}, "G56"), ({}, "G54")])
def test_K8_preset_yoksa_hata(presets, code):
    """Eşleme yoksa CamError (varsayılan eşleme yapılmaz)."""
    m = replace(altin(HEI_M), presets=presets)
    with pytest.raises(CamError):
        post([altin_yol(takim(1))], m, kurulum((0.0, 0.0, -200.0), code), safe_z=5.0)


def test_K8_presets_none_hata():
    m = replace(altin(HEI_M), presets=None)
    with pytest.raises(CamError):
        post([altin_yol(takim(1))], m, KURULUM, safe_z=5.0)


# ---------------------------------------------------------------- K9


def _degis(eski: str, yeni: str) -> str:
    assert eski in GOLDEN
    return GOLDEN.replace(eski, yeni, 1)


HATALI = {
    "atlanan blok": _degis("8 L Y+10 R0\n", ""),
    "RL": _degis("7 L X+10 R0 F300", "7 L X+10 RL F300"),
    "RR": _degis("7 L X+10 R0 F300", "7 L X+10 RR F300"),
    "IX": _degis("7 L X+10 R0 F300", "7 L IX+10 R0 F300"),
    "RND": _degis("8 L Y+10 R0\n", "8 RND R2\n"),
    "CHF": _degis("8 L Y+10 R0\n", "8 CHF 1\n"),
    "LP": _degis("8 L Y+10 R0\n", "8 LP PR+10 PA+90 R0\n"),
    "CT": _degis("8 L Y+10 R0\n", "8 CT X+0 Y+10 R0\n"),
    "FN": _degis("8 L Y+10 R0\n", "8 FN 0: Q1 = +5\n"),
    "Q parametresi": _degis("7 L X+10 R0 F300", "7 L X+Q1 R0 F300"),
    "baska cevrim": _degis("3 CYCL DEF 247 DATUM SETTING ~ Q339=+1", "3 CYCL DEF 200 DRILLING"),
    "END PGM yok": _degis("13 END PGM 1 MM\n", ""),
    "blok 0'dan baslamiyor": "\n".join(
        f"{int(s.split(' ', 1)[0]) + 1} {s.split(' ', 1)[1]}" for s in satirlar(GOLDEN)
    )
    + "\n",
}


@pytest.mark.parametrize("ad", list(HATALI))
def test_K9_okuyucu_hatalari(ad):
    satir_hatasi(_oku, HATALI[ad])


def test_K9_atlanan_blok_numarasi_mesajda():
    """8. blok silindi: 9 numaralı blok 8 beklenirken geldi; mesaj o satırı gösterir."""
    with pytest.raises(CamError, match=r"satır (8|9|10)\b"):
        _oku(HATALI["atlanan blok"])


def test_okuyucu_yorumlari_yok_sayar():
    got = _oku(GOLDEN)
    assert len(got) == 1
    assert_paths_close(got[0], as_written(altin_yol(takim(1)), 5.0))
