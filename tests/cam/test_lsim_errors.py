"""SPEC 22 K18 — hatalı girdiler CamError verir (sessiz hata yok).

Testler SPEC 22 "Arayüz" bölümünden yazıldı; cam.sim kodu okunmadı.

SPEC 22: boş ops; Stock (kutu); Tool (freze); plane ≠ ZX; edge_len = None; taraf belirlenemiyor veya takım
türüyle uyuşmuyor (TURN yalnız dış, BORE yalnız iç, GROOVE dışta T ∈ {3, 4}, içte T ∈ {1, 2}); tutucu K'ye
giriyor; part / initial ızgarası uyuşmuyor; arc_tol, tol, gouge_tol ≤ 0; section_at aralık dışı.
"""

from __future__ import annotations

import pytest

from cam.model import (
    CamError,
    CylinderStock,
    LatheHolder,
    LatheTool,
    LatheToolKind,
    Plane,
    Stock,
    Tool,
    ToolKind,
    Toolpath,
)
from cam.sim import RadialMap, simulate_lathe
from tests.cam.lsimref import G0, G1, bore_tool, groove_tool, lpath, turn_tool

STOK = CylinderStock(D=40.0, zmin=-50.0, zmax=0.0)
BORU = CylinderStock(D=40.0, zmin=-50.0, zmax=0.0, d=20.0)


def _yol(tool=None, start=(25.0, 5.0)):
    tool = turn_tool() if tool is None else tool
    return lpath(tool, start, [G0(start[0], -10.0), G0(start[0], start[1])])


def test_K18_bos_program():
    with pytest.raises(CamError):
        simulate_lathe([], STOK)


def test_K18_kutu_stok():
    with pytest.raises(CamError):
        simulate_lathe([_yol()], Stock(-20, -20, -50, 20, 20, 0))


def test_K18_freze_takimi():
    tp = Toolpath(
        "freze", Tool(1, "duz", ToolKind.FLAT, 6.0, 20.0), (25.0, 0.0, 5.0), [G0(25.0, -10.0)], 1000.0
    )
    tp.plane = Plane.ZX
    with pytest.raises(CamError):
        simulate_lathe([tp], STOK)


def test_K18_g17_yol():
    tp = Toolpath("g17", turn_tool(), (25.0, 0.0, 5.0), [G0(25.0, -10.0)], 1000.0, plane=Plane.XY)
    with pytest.raises(CamError):
        simulate_lathe([tp], STOK)


def test_K18_edge_len_yok():
    t = LatheTool(1, "kenarsiz", LatheToolKind.TURN, 0.8, 3, 93.0, 80.0)
    assert t.edge_len is None
    with pytest.raises(CamError):
        simulate_lathe([_yol(t)], STOK)


def test_K18_taraf_belirsiz():
    """Boruda d/2 < start.x < D/2 → ne dış ne iç; dolu çubukta start.x < D/2 → iç değil (d = 0)."""
    with pytest.raises(CamError):
        simulate_lathe([_yol(start=(15.0, 5.0))], BORU)
    with pytest.raises(CamError):
        simulate_lathe([_yol(start=(10.0, 5.0))], STOK)


def test_K18_turn_icte():
    with pytest.raises(CamError):
        simulate_lathe([_yol(turn_tool(), start=(8.0, 5.0))], BORU)


def test_K18_bore_dista():
    with pytest.raises(CamError):
        simulate_lathe([_yol(bore_tool(), start=(25.0, 5.0))], BORU)


def test_K18_kanal_uc_numarasi_tarafla_uyusmuyor():
    with pytest.raises(CamError):
        simulate_lathe([_yol(groove_tool(tip=3), start=(8.0, 5.0))], BORU)  # içte T ∈ {1, 2}
    with pytest.raises(CamError):
        simulate_lathe([_yol(groove_tool(tip=1), start=(25.0, 5.0))], BORU)  # dışta T ∈ {3, 4}


def test_K18_dogru_taraflar_hata_vermez():
    """Kontrol: aynı yollar uygun takımla hatasız."""
    simulate_lathe([_yol(turn_tool(), start=(25.0, 5.0))], BORU)
    simulate_lathe([_yol(bore_tool(), start=(8.0, 5.0))], BORU)
    simulate_lathe([_yol(groove_tool(tip=4), start=(25.0, 5.0))], BORU)
    simulate_lathe([_yol(groove_tool(tip=2), start=(8.0, 5.0))], BORU)


def test_K18_tutucu_K_ye_giriyor():
    h = LatheHolder("carpik", ((-1.0, -1.0), (1.0, -1.0), (1.0, 1.0), (-1.0, 1.0)), half_width=5.0)
    with pytest.raises(CamError):
        simulate_lathe([_yol(turn_tool(holder=h))], STOK)


def test_K18_part_izgarasi_uyusmuyor():
    yanlis = RadialMap.from_stock(STOK, 0.7)
    with pytest.raises(CamError):
        simulate_lathe([_yol()], STOK, cell=0.5, part=yanlis)


def test_K18_initial_izgarasi_uyusmuyor():
    yanlis = RadialMap.from_stock(STOK, 0.7)
    with pytest.raises(CamError):
        simulate_lathe([_yol()], STOK, cell=0.5, initial=yanlis)
    kayik = RadialMap.from_stock(CylinderStock(D=40.0, zmin=-49.0, zmax=1.0), 0.5)  # aynı dz ve nz, farklı z0
    with pytest.raises(CamError):
        simulate_lathe([_yol()], STOK, cell=0.5, initial=kayik)


@pytest.mark.parametrize("ad", ["arc_tol", "tol", "gouge_tol"])
@pytest.mark.parametrize("deger", [0.0, -1e-3])
def test_K18_toleranslar(ad, deger):
    with pytest.raises(CamError):
        simulate_lathe([_yol()], STOK, **{ad: deger})


def test_K18_section_at_araligi():
    sonuc = simulate_lathe([_yol()], STOK, cell=0.5)
    n = len(sonuc.steps)
    sonuc.section_at(0)
    sonuc.section_at(n)
    for k in (-1, n + 1):
        with pytest.raises(CamError):
            sonuc.section_at(k)


def test_K18_g94_kabul_edilir():
    """feed_mode = PER_MIN (G94) kabul edilir."""
    from cam.model import FeedMode

    tp = lpath(turn_tool(), (25.0, 5.0), [G1(25.0, -10.0, F=200.0)], feed_mode=FeedMode.PER_MIN)
    simulate_lathe([tp], STOK)
