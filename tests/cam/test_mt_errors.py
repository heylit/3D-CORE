"""SPEC 49 K10 — hatalar: freze profili, canlı olmayan / bilinmeyen istasyon, torna takımıyla freze işlemi,
koordinat modu / takım uyumsuzluğu → CamError.

Testler SPEC 49 "Arayüz" ve "Kabul kriterleri" bölümlerinden ve iskelet arayüzünden yazıldı; gövdeler
okunmadı. Profil: tests/cam/mtref.py (istasyon 1 sabit, 2 canlı radyal, 3 canlı eksenel; 9 yok).
"""

from __future__ import annotations

import pytest

from cam.millturn.ops import LiveCut, axial_hole, cyl_slot, face_contour, face_pocket, keyway, radial_hole
from cam.model import CamError, Move, MoveType, Toolpath
from cam.ops2d import Cut
from cam.post.millturn import post_mt
from cam.profile import Profile, Region
from cam.sim.millturn import simulate_mt
from tests.cam.lsimref import turn_tool
from tests.cam.mtref import ST_EKSENEL, ST_RADYAL, ST_SABIT, STOK, freze, freze_profili, profil

G0, G1 = MoveType.RAPID, MoveType.LINEAR
KESME = LiveCut(feed=200.0, plunge_feed=100.0, rpm=2000.0)
CEP_KESME = Cut(z_top=0.0, z_bottom=-2.0, a_p=1.0, feed=500.0, plunge_feed=200.0, rpm=3000.0, z_safe=5.0)
CEP = Region(Profile.polygon([(6.0, 2.0), (16.0, 2.0), (16.0, 12.0), (6.0, 12.0)]))
KANAL = Profile.polygon([(0.0, -30.0), (20.0, -30.0)], closed=False)


def _dalis(station: int = ST_RADYAL) -> Toolpath:
    """Elle kurulmuş C indeksli radyal yol (C = 0)."""
    ax = (1.0, 0.0, 0.0)
    return Toolpath(
        "elle",
        freze(5.0),
        (30.0, 0.0, -20.0),
        [
            Move(G0, (21.0, 0.0, -20.0), axis=ax, c=0.0),
            Move(G1, (17.0, 0.0, -20.0), feed=100.0, axis=ax, c=0.0),
        ],
        rpm=2000.0,
        station=station,
    )


# ------------------------------------------------------------------ freze profili


def test_K10_freze_profili_simulasyon():
    with pytest.raises(CamError):
        simulate_mt([_dalis()], STOK, freze_profili(), cell=0.5)


def test_K10_freze_profili_post():
    with pytest.raises(CamError):
        post_mt([_dalis()], freze_profili())


# ------------------------------------------------------------------ istasyon


ISLEMLER = {
    "radyal_delik": lambda st, m: radial_hole(
        STOK, freze(5.0), KESME, 0.0, -20.0, 4.0, station=st, machine=m
    ),
    "eksenel_delik": lambda st, m: axial_hole(STOK, freze(5.0), KESME, 10.0, 0.0, 4.0, station=st, machine=m),
    "kama": lambda st, m: keyway(STOK, freze(6.0), KESME, 0.0, -30.0, -20.0, 2.0, 1.0, station=st, machine=m),
    "alin_cebi": lambda st, m: face_pocket(CEP, freze(6.0), CEP_KESME, station=st, machine=m),
    "alin_konturu": lambda st, m: face_contour(
        CEP.outer, freze(6.0), CEP_KESME, "dis", station=st, machine=m
    ),
    "silindirik_kanal": lambda st, m: cyl_slot(KANAL, freze(4.0), KESME, 20.0, 2.0, station=st, machine=m),
}


@pytest.mark.parametrize("islem", list(ISLEMLER))
def test_K10_canli_olmayan_istasyon(islem):
    """İstasyon 1 sabit (torna) takım istasyonu: canlı takım işlemi → CamError."""
    with pytest.raises(CamError):
        ISLEMLER[islem](ST_SABIT, profil())


@pytest.mark.parametrize("islem", list(ISLEMLER))
def test_K10_bilinmeyen_istasyon(islem):
    with pytest.raises(CamError):
        ISLEMLER[islem](9, profil())


def test_K10_bilinmeyen_istasyon_simulasyon():
    with pytest.raises(CamError):
        simulate_mt([_dalis(station=9)], STOK, profil(), cell=0.5)


def test_K10_bilinmeyen_istasyon_post():
    with pytest.raises(CamError):
        post_mt([_dalis(station=9)], profil())


def test_K10_canli_olmayan_istasyon_post():
    with pytest.raises(CamError):
        post_mt([_dalis(station=ST_SABIT)], profil())


# ------------------------------------------------------------------ torna takımıyla freze işlemi


TORNA = {
    "radyal_delik": lambda: radial_hole(STOK, turn_tool(), KESME, 0.0, -20.0, 4.0, station=ST_RADYAL),
    "eksenel_delik": lambda: axial_hole(STOK, turn_tool(), KESME, 10.0, 0.0, 4.0, station=ST_EKSENEL),
    "kama": lambda: keyway(STOK, turn_tool(), KESME, 0.0, -30.0, -20.0, 2.0, 1.0, station=ST_RADYAL),
    "alin_cebi": lambda: face_pocket(CEP, turn_tool(), CEP_KESME, station=ST_EKSENEL),
    "alin_konturu": lambda: face_contour(CEP.outer, turn_tool(), CEP_KESME, "dis", station=ST_EKSENEL),
    "silindirik_kanal": lambda: cyl_slot(KANAL, turn_tool(), KESME, 20.0, 2.0, station=ST_RADYAL),
}


@pytest.mark.parametrize("islem", list(TORNA))
def test_K10_torna_takimiyla_freze_islemi(islem):
    with pytest.raises(CamError):
        TORNA[islem]()


# ------------------------------------------------------------------ coord / takım uyumsuzluğu


def _torna_polar() -> Toolpath:
    """Torna takımıyla polar yol (coord / takım uyumsuz)."""
    return Toolpath(
        "polar_torna",
        turn_tool(),
        (10.0, 0.0, 2.0),
        [Move(G1, (10.0, 0.0, -1.0), feed=0.1)],
        rpm=1000.0,
        plane="G18",
        coord="polar",
        station=ST_EKSENEL,
    )


def _torna_c() -> Toolpath:
    """Torna yolunda C açısı (yalnız kartezyen freze yolunda verilir)."""
    return Toolpath(
        "c_torna",
        turn_tool(),
        (25.0, 0.0, 2.0),
        [Move(G1, (19.0, 0.0, 2.0), feed=0.1, c=90.0)],
        rpm=1000.0,
        plane="G18",
    )


@pytest.mark.parametrize("yol", [_torna_polar, _torna_c])
def test_K10_coord_takim_uyumsuz_simulasyon(yol):
    with pytest.raises(CamError):
        simulate_mt([yol()], STOK, profil(), cell=0.5)


@pytest.mark.parametrize("yol", [_torna_polar, _torna_c])
def test_K10_coord_takim_uyumsuz_post(yol):
    with pytest.raises(CamError):
        post_mt([yol()], profil())
