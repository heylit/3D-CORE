"""SPEC 00 Ek 2 — K16: G-code yazıcısı (SPEC 04) henüz desteklemediği yolları reddeder.

Yazıcı şimdilik yalnız G17 / G94 / sabit devirli freze yollarını yazar. `plane != XY`,
`feed_mode != PER_MIN`, `css` verilmiş veya takım `LatheTool` ise `CamError`: sessizce G17 yayı
yazmamalı. SPEC 21 torna yazıcısıyla bu korumayı kaldırır (bu dosya o zaman güncellenir).

Testler sadece SPEC 00 Ek 2 metninden ve `cam.gcode.write` imzasından yazıldı.
"""

from __future__ import annotations

import functools

import pytest

import cam.model as M
from cam.gcode import FANUC, GRBL, write
from cam.model import CamError, Move, MoveType, Tool, ToolKind, Toolpath

G0, G1, G3 = MoveType.RAPID, MoveType.LINEAR, MoveType.ARC_CCW
DIALECTS = pytest.mark.parametrize("dialect", [GRBL, FANUC], ids=["grbl", "fanuc"])


def ek2(test):
    """Ek 2 tipleri yoksa testi NotImplementedError ile düşürür ("uygulanmamış")."""

    @functools.wraps(test)
    def sarici(*args, **kwargs):
        eksik = [ad for ad in ("Plane", "FeedMode", "LatheToolKind", "LatheTool") if not hasattr(M, ad)]
        if eksik:
            raise NotImplementedError(f"SPEC 00 Ek 2 uygulanmamış: cam.model içinde yok: {eksik}")
        return test(*args, **kwargs)

    return sarici


def freze() -> Tool:
    return Tool(id=1, name="freze10", kind=ToolKind.FLAT, D=10.0, flute_length=22.0)


def xy_yolu(**kw) -> Toolpath:
    """Geçerli G17 freze yolu; yeni alanlar anahtar sözcükle."""
    moves = [
        Move(G1, (10.0, 0.0, -1.0), feed=300.0),
        Move(G3, (0.0, 10.0, -1.0), feed=300.0, center=(0.0, 0.0)),
    ]
    return Toolpath(name="xy", tool=freze(), start=(10.0, 0.0, 5.0), moves=moves, rpm=8000.0, **kw)


def zx_freze_yolu() -> Toolpath:
    """Geçerli G18 freze yolu: (0, 0, 10) → G3 → (10, 0, 0), merkez (x, z) = (0, 0)."""
    moves = [Move(G3, (10.0, 0.0, 0.0), feed=300.0, center=(0.0, 0.0))]
    return Toolpath(
        name="zx", tool=freze(), start=(0.0, 0.0, 10.0), moves=moves, rpm=8000.0, plane=M.Plane.ZX
    )


def torna_yolu(**kw) -> Toolpath:
    """Geçerli torna yolu (ZX, y = 0), G94 ve sabit devir: tek ret sebebi takımın LatheTool olması."""
    tool = M.LatheTool(
        id=11, name="CNMG", kind=M.LatheToolKind.TURN, nose_r=0.8, tip=3, kappa_r=95.0, eps_r=80.0
    )
    moves = [Move(G1, (20.0, 0.0, -30.0), feed=150.0), Move(G1, (25.0, 0.0, -30.0), feed=150.0)]
    args = dict(name="torna", tool=tool, start=(20.0, 0.0, 5.0), moves=moves, rpm=1500.0, plane=M.Plane.ZX)
    args.update(kw)
    return Toolpath(**args)


@DIALECTS
def test_xy_freze_yolu_hala_yaziliyor(dialect):
    """Koruma Dalga 1 yollarını etkilemez."""
    text = write([xy_yolu()], dialect)
    assert "G3" in text


@DIALECTS
@ek2
def test_zx_duzlemi_reddedilir(dialect):
    tp = zx_freze_yolu()
    tp.validate()  # yol kendi başına geçerli; reddeden yazıcı
    with pytest.raises(CamError):
        write([tp], dialect)


@DIALECTS
@ek2
def test_devir_basi_ilerleme_reddedilir(dialect):
    tp = xy_yolu(feed_mode=M.FeedMode.PER_REV)
    tp.validate()
    with pytest.raises(CamError):
        write([tp], dialect)


@DIALECTS
@ek2
def test_sabit_kesme_hizi_reddedilir(dialect):
    tp = xy_yolu(css=200.0)
    tp.validate()
    with pytest.raises(CamError):
        write([tp], dialect)


@DIALECTS
@ek2
def test_torna_takimi_reddedilir(dialect):
    tp = torna_yolu()
    tp.validate()
    with pytest.raises(CamError):
        write([tp], dialect)


@DIALECTS
@ek2
def test_desteklenmeyen_yol_listede_ikinci_sirada_da_reddedilir(dialect):
    """Geçerli bir freze yolundan sonra gelen ZX yolu da yazdırılmaz (kısmi program yok)."""
    with pytest.raises(CamError):
        write([xy_yolu(), zx_freze_yolu()], dialect)
