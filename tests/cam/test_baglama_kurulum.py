"""SPEC 10 — K12 SPEC 14 ve 22 uyumu: `envelope`, `fixture_top`, `Setup(fixtures = zarf)`, `rings`.

Testler sadece SPEC 10 metninden yazıldı; `cam/baglama.py` uygulama kodu okunmadı.
Zarf (Teori, "Montajdan CAM'e" 4. adım ve Arayüz `envelope`): kütüphanede ilkel başına WCS sınır kutusu;
"ozel"de parts[part_ref].bbox köşeleri frame ile taşınarak tek kutu. SPEC 14: clearance_height = en üst Z + 5,
check_setup çene zarfına giren yolda CamError. SPEC 22: Setup.fixtures için CylinderStock halkalar.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from cam.model import CamError, CylinderStock, Move, MoveType, Setup, Stock, Tool, ToolKind, Toolpath, Wcs
from cam.setups import check_setup, clearance_height, safe_radius
from tests.cam.baglama_ara import (
    Fixture,
    chuck_for,
    clamp_for,
    envelope,
    fixture_top,
    make_fixture,
    primitives_wcs,
    vise_for,
)
from tests.cam.baglama_ref import (
    CHUCK_GRIP,
    CHUCK_OLCU,
    CHUCK_STOK,
    CLAMP_OLCU,
    STOK,
    VISE_GRIP,
    VISE_OLCU,
    Rz,
    frame,
    prim_aabb,
)


class SahteParca:
    """OCCT'siz parça: yalnız name ve bbox (geometry.part.Part ile aynı biçim: (min, max) özniteliği)."""

    def __init__(self, name: str, lo, hi) -> None:
        self.name = name
        self.bbox = (np.array(lo, dtype=float), np.array(hi, dtype=float))


def mengene_fx():
    v, fr = vise_for(STOK, VISE_GRIP, "x", **VISE_OLCU)
    return make_fixture("mengene", v, fr)


def ayna_fx():
    c, fr = chuck_for(CHUCK_STOK, CHUCK_GRIP, **CHUCK_OLCU)
    return make_fixture("ayna", c, fr)


def pabuc_fx():
    c, fr = clamp_for(STOK, "y-", 40.0, 8.0, **CLAMP_OLCU)
    return make_fixture("pabuc", c, fr)


def kutu_degerleri(b: Stock) -> list[float]:
    return [b.xmin, b.ymin, b.zmin, b.xmax, b.ymax, b.zmax]


@pytest.mark.parametrize("uret", [mengene_fx, ayna_fx, pabuc_fx], ids=["mengene", "ayna", "pabuc"])
def test_k12_zarf_ilkel_sinir_kutulari(uret):
    fx = uret()
    zarf = envelope(fx)
    pr = primitives_wcs(fx)
    assert len(zarf) == len(pr)
    for b, p in zip(zarf, pr, strict=True):
        assert isinstance(b, Stock)
        lo, hi = prim_aabb(p)
        np.testing.assert_allclose(kutu_degerleri(b), np.concatenate([lo, hi]), atol=1e-9, rtol=0)


def test_k12_mengene_zarf_degerleri():
    # Teori örneği (K2): sabit, hareketli çene, yatak, paraleller
    zarf = [kutu_degerleri(b) for b in envelope(mengene_fx())]
    beklenen = [
        [-10, -20, -5, 90, 0, 10],
        [-10, 50, -5, 90, 70, 10],
        [-10, -20, -45, 90, 130, -5],
        [-10, 0, -5, 90, 6, 0],
        [-10, 44, -5, 90, 50, 0],
    ]
    np.testing.assert_allclose(zarf, beklenen, atol=1e-9, rtol=0)


def test_k12_pabuc_civata_zarfi():
    # cıvata ekseni (40, −32), r = 6, z ∈ [0, 57] → kutu [34, 46] × [−38, −26] × [0, 57]
    zarf = envelope(pabuc_fx())
    np.testing.assert_allclose(kutu_degerleri(zarf[2]), [34, -38, 0, 46, -26, 57], atol=1e-9, rtol=0)


def test_k12_ozel_zarf_tek_kutu():
    # parça bbox [0, 4] × [0, 2] × [0, 3], çerçeve R_z(90°), origin (10, 0, 0): WCS x = 10 − y, y = x
    # → [8, 10] × [0, 4] × [0, 3]
    fx = Fixture(name="ozel", part_ref="govde", frame=frame((10, 0, 0), Rz(90)), kind="ozel")
    zarf = envelope(fx, {"govde": SahteParca("govde", (0, 0, 0), (4, 2, 3))})
    assert len(zarf) == 1
    np.testing.assert_allclose(kutu_degerleri(zarf[0]), [8, 0, 0, 10, 4, 3], atol=1e-9, rtol=0)


def test_k12_ozel_zarf_parts_yok_hata():
    fx = Fixture(name="ozel", part_ref="govde", kind="ozel")
    with pytest.raises(CamError):
        envelope(fx)
    with pytest.raises(CamError):
        envelope(fx, {"baska": SahteParca("baska", (0, 0, 0), (1, 1, 1))})


def test_k12_fixture_top():
    assert fixture_top([mengene_fx()]) == pytest.approx(10.0, abs=1e-9)  # çene üstü
    assert fixture_top([pabuc_fx()]) == pytest.approx(57.0, abs=1e-9)  # cıvata üstü H_s + t_a + h_c
    assert fixture_top([mengene_fx(), pabuc_fx()]) == pytest.approx(57.0, abs=1e-9)
    assert fixture_top([ayna_fx()]) == pytest.approx(-40.0, abs=1e-9)  # çene üstü z = −60 + L_j


def test_k12_clearance_height_zarfla():
    # en yüksek bağlama (cıvata üstü 57) stoktan (30) yüksek → 57 + 5
    setup = Setup("pabuclu", Wcs(), STOK, fixtures=envelope(pabuc_fx()))
    assert clearance_height(setup) == pytest.approx(62.0, abs=1e-9)


def test_k12_check_setup_cene_zarfi():
    takim = Tool(1, "f10", ToolKind.FLAT, 10.0, 40.0)
    setup = Setup("mengeneli", Wcs(), STOK, fixtures=envelope(mengene_fx()))
    # sabit çene üstünden y = −10, z = 5'te geçen yol çene zarfına girer
    giren = Toolpath(
        "giren",
        takim,
        (-40, -10, 50),
        [
            Move(MoveType.RAPID, (-40, -10, 5)),
            Move(MoveType.LINEAR, (120, -10, 5), feed=500.0),
            Move(MoveType.RAPID, (120, -10, 50)),
        ],
        rpm=3000.0,
    )
    with pytest.raises(CamError):
        check_setup(setup, [giren])
    # çenelerin (üst 10) yeterince üstünden geçen yol temiz
    ustten = Toolpath(
        "ustten",
        takim,
        (-40, -10, 50),
        [Move(MoveType.LINEAR, (120, -10, 40), feed=500.0)],
        rpm=3000.0,
    )
    check_setup(setup, [ustten])


def test_k12_ayna_halkalari_spec22_bicimi():
    c, fr = chuck_for(CHUCK_STOK, CHUCK_GRIP, **CHUCK_OLCU)
    halkalar = c.rings(fr)
    assert all(isinstance(h, CylinderStock) for h in halkalar)
    assert halkalar[0].d == pytest.approx(CHUCK_STOK.D, abs=1e-9)  # d = tutulan çap
    setup = Setup("torna", Wcs(), CHUCK_STOK, fixtures=halkalar)
    # SPEC 14 safe_radius: en büyük yarıçap (gövde D_b/2 = 80) + 2; çene halkası r_o = √2125 < 80
    assert safe_radius(setup) == pytest.approx(82.0, abs=1e-9)
    assert halkalar[0].D / 2 == pytest.approx(math.sqrt(2125), abs=1e-9)
    # Setup sözlük gidiş-dönüşü (SPEC 22 alan biçimi)
    assert Setup.from_dict(setup.to_dict()).fixtures == halkalar
