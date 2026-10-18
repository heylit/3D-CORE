"""SPEC 49 K8–K9 — torna-freze postu (Sinumerik 840D sl, Fanuc / MAPPS) ve okuyucuyla gidiş-dönüş.

Testler SPEC 49 "G-code" tablosundan ve iskelet arayüzünden yazıldı; cam/post/millturn.py ve cam/millturn
gövdeleri okunmadı. Program: polar alın cebi + C indeksli üç radyal delik + silindirik kanal.

Beklenen bloklar (SPEC 49):
| İşlev | Sinumerik 840D sl | Fanuc / MAPPS |
| C eksenini aç / kapat | SPOS (CAxis.m_on/m_off varsa yazılır) | CAxis.m_on (M45), m_off (M46) |
| C indeks | SPOS=DC(C) veya C=DC(C) | G0 C |
| Canlı takım devri | SETMS(2) … M2=3 S2=n, sonra SETMS | M13 S n |
| Polar | TRANSMIT … TRAFOOF | G12.1 … G13.1 (X çap) |
| Silindirik | TRACYL(2·r_ref) … TRAFOOF | G7.1 C r_ref … G7.1 C0 |
Gidiş-dönüş: okunan yolların kesme hareketleri (G1/G2/G3) parça çerçevesinde aynı; tolerans yazılan
ondalığa göre (3 ondalık, X çap: 1e-3 mm). C açıları mod 360 karşılaştırılır. Okuyucu yaklaşma / geri
çekme G0'ları ekleyebilir; G0'lar karşılaştırılmaz.
"""

from __future__ import annotations

import functools
import math
import re

import pytest

from cam.millturn.ops import LiveCut, cyl_slot, face_pocket, radial_hole
from cam.model import MoveType
from cam.ops2d import Cut
from cam.post.millturn import post_mt, read_mt
from cam.profile import Profile, Region
from tests.cam.mtref import ST_EKSENEL, ST_RADYAL, STOK, aci_farki, freze, profil

TOL = 1e-3
SAYI = r"(-?\d+(?:\.\d*)?|-?\.\d+)"
TETALAR = (120.0, 240.0, 0.0)  # C = 240, 120, 0
R_REF, T_KANAL = 20.0, 2.0

CEP_KESME = Cut(z_top=0.0, z_bottom=-2.0, a_p=1.0, feed=500.0, plunge_feed=200.0, rpm=3000.0, z_safe=5.0)
CEP = Region(Profile.polygon([(6.0, 2.0), (16.0, 2.0), (16.0, 12.0), (6.0, 12.0)]))
DELIK_KESME = LiveCut(feed=200.0, plunge_feed=100.0, rpm=2000.0)
KANAL_KESME = LiveCut(feed=300.0, plunge_feed=100.0, rpm=2500.0)


def _program(M):
    cep = face_pocket(CEP, freze(6.0, id=6), CEP_KESME, station=ST_EKSENEL, machine=M)
    delikler = [
        radial_hole(STOK, freze(5.0, id=7), DELIK_KESME, th, -20.0, 5.0, station=ST_RADYAL, machine=M)
        for th in TETALAR
    ]
    kanal = cyl_slot(
        Profile.polygon([(0.0, -35.0), (math.pi * R_REF, -35.0)], closed=False),
        freze(4.0, id=8),
        KANAL_KESME,
        R_REF,
        T_KANAL,
        station=ST_RADYAL,
        machine=M,
    )
    return [cep, *delikler, kanal]


def _sayilar(desen: str, metin: str) -> list[float]:
    return [float(m) for m in re.findall(desen, metin)]


def _c_icerir(degerler: list[float], c: float) -> bool:
    return any(abs(aci_farki(v, c)) <= TOL for v in degerler)


def _kesme(tp):
    return [m for m in tp.moves if m.type is not MoveType.RAPID]


def _gidis_donus(ops, metin: str, M) -> None:
    got = read_mt(metin, M)
    assert len(got) == len(ops)
    for o, g in zip(ops, got, strict=True):
        g.validate()
        assert g.coord == o.coord
        if o.coord == "silindirik":
            assert g.cyl_r == pytest.approx(o.cyl_r, abs=TOL)
        ko, kg = _kesme(o), _kesme(g)
        assert len(kg) == len(ko), o.name
        for a, b in zip(ko, kg, strict=True):
            assert b.type is a.type
            assert b.end == pytest.approx(a.end, abs=TOL), o.name
            if a.c is not None:
                assert b.c is not None and abs(aci_farki(b.c, a.c)) <= TOL


# ------------------------------------------------------------------ K8 Sinumerik


@functools.cache
def _postla(controller: str):
    """(profil, işlemler, program metni). Fixture değil: iskeletteki NotImplementedError testin
    içinde düşsün."""
    M = profil(controller)
    ops = _program(M)
    return M, ops, post_mt(ops, M)


def sinumerik():
    return _postla("sinumerik")


def test_K8_sinumerik_bloklar():
    _, _, metin = sinumerik()
    for blok in ("TRANSMIT", "TRAFOOF", "SPOS", "SETMS(2)", "M2=3", "S2=", "TRACYL("):
        assert blok in metin, blok
    assert metin.index("TRANSMIT") < metin.index("TRAFOOF")
    assert metin.index("SETMS(2)") < metin.index("M2=3")
    assert metin.index("TRACYL(") < metin.rindex("TRAFOOF")


def test_K8_sinumerik_c_indeks():
    """SPOS=DC(C) ya da C=DC(C): üç delik için C = −θ (mod 360)."""
    _, _, metin = sinumerik()
    cs = _sayilar(r"(?:SPOS|\bC)\s*=\s*DC\(\s*" + SAYI + r"\s*\)", metin)
    for th in TETALAR:
        assert _c_icerir(cs, -th), (th, cs)


def test_K8_sinumerik_tracyl_cap():
    _, _, metin = sinumerik()
    assert _sayilar(r"TRACYL\(\s*" + SAYI, metin) == [pytest.approx(2 * R_REF, abs=TOL)]


def test_K8_sinumerik_canli_devir():
    _, _, metin = sinumerik()
    devir = _sayilar(r"S2\s*=\s*" + SAYI, metin)
    for n in (3000.0, 2000.0, 2500.0):
        assert any(abs(v - n) <= 0.5 for v in devir), (n, devir)


def test_K8_sinumerik_gidis_donus():
    M, ops, metin = sinumerik()
    _gidis_donus(ops, metin, M)


# ------------------------------------------------------------------ K9 Fanuc / MAPPS


def fanuc():
    return _postla("fanuc")


def test_K9_fanuc_bloklar():
    _, _, metin = fanuc()
    for blok in ("M45", "M46", "G12.1", "G13.1", "G7.1"):
        assert blok in metin, blok
    assert re.search(r"\bM13\b", metin)
    assert metin.index("M45") < metin.index("G12.1") < metin.index("G13.1")
    assert metin.rindex("M46") > metin.rindex("G7.1")


def test_K9_fanuc_c_indeks():
    """G0 C: delikler polar bloktan sonra, silindirik bloktan önce."""
    _, _, metin = fanuc()
    i0 = metin.index("G13.1")
    i1 = metin.index("G7.1", i0)
    cs = _sayilar(r"\bG0?0\b[^\n]*?\bC" + SAYI, metin[i0:i1])
    for th in TETALAR:
        assert _c_icerir(cs, -th), (th, cs)


def test_K9_fanuc_g12_1_x_cap():
    """G12.1 ile G13.1 arasında X çap olarak yazılır: en büyük X = 2·(cep kesme hareketlerinin
    en büyük x'i)."""
    _, ops, metin = fanuc()
    blok = metin[metin.index("G12.1") : metin.index("G13.1")]
    xs = _sayilar(r"\bX" + SAYI, blok)
    assert xs
    x_max = max(m.end[0] for m in _kesme(ops[0]))
    assert max(xs) == pytest.approx(2 * x_max, abs=2 * TOL)


def test_K9_fanuc_g7_1():
    """G7.1 C<r_ref> … G7.1 C0."""
    _, _, metin = fanuc()
    degerler = _sayilar(r"G7\.1\s*C" + SAYI, metin)
    assert degerler[0] == pytest.approx(R_REF, abs=TOL)
    assert degerler[-1] == pytest.approx(0.0, abs=TOL)


def test_K9_fanuc_gidis_donus():
    M, ops, metin = fanuc()
    _gidis_donus(ops, metin, M)
