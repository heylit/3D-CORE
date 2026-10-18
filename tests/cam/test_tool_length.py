"""SPEC 14 — takım boyu: K9 (ofsetler, doğrulama, Fanuc tablosu), K10 (GRBL ölçüm programı).

Testler sadece SPEC 14 metninden yazıldı; `cam/tool_length.py` uygulama kodu okunmadı.

L_n = Tool.gauge_length = tutucu ölçü boyu + taşma. Ek A: tutucu 60, T1 taşma 30 → 90, T2 taşma 45 → 105.
GRBL: ΔL_n = L_n − L_ref (ön ayar) veya z_n − z_ref (prob); uzun takımda pozitif.
"""

from __future__ import annotations

import pytest

from cam.gcode import fmt
from cam.model import CamError, LatheTool, LatheToolKind, Tool, ToolHolder, ToolKind, ToolLibrary
from cam.tool_length import (
    ToolSetter,
    fanuc_offset_table,
    length_offsets,
    offsets_from_probe,
    probe_program,
    verify_offsets,
)

NAN = float("nan")


def tutucu() -> ToolHolder:
    return ToolHolder("BT30-ER", 60.0, ((0.0, 15.0), (40.0, 20.0)))


def kutuphane() -> ToolLibrary:
    h = tutucu()
    return ToolLibrary(
        [
            Tool(
                1, "freze6", ToolKind.FLAT, D=6.0, flute_length=20.0, flutes=3, stickout=30.0, holder=h
            ),  # 90
            Tool(
                2, "matkap5", ToolKind.DRILL, D=5.0, flute_length=40.0, flutes=2, stickout=45.0, holder=h
            ),  # 105
            Tool(3, "tutucusuz", ToolKind.FLAT, D=8.0, flute_length=20.0, stickout=30.0),  # None
            Tool(4, "tasmasiz", ToolKind.FLAT, D=8.0, flute_length=20.0, holder=h),  # None
            Tool(5, "kisa", ToolKind.FLAT, D=4.0, flute_length=12.0, stickout=25.0, holder=h),  # 85
            LatheTool(10, "tornalama", LatheToolKind.TURN, nose_r=0.8, tip=3, kappa_r=95.0, eps_r=80.0),
        ]
    )


def yaklasik(d: dict[int, float]) -> dict:
    return {k: pytest.approx(v, abs=1e-12) for k, v in d.items()}


# ---------------------------------------------------------------- K9 ön ayardan ofset


def test_gauge_length_on_kosul():
    lib = kutuphane()
    assert lib.get(1).gauge_length == 90.0
    assert lib.get(2).gauge_length == 105.0
    assert lib.get(5).gauge_length == 85.0


def test_length_offsets_ek_a():
    assert length_offsets(kutuphane(), [1, 2], ref_id=1) == yaklasik({1: 0.0, 2: 15.0})


def test_length_offsets_referans_degisince():
    assert length_offsets(kutuphane(), [1, 2], ref_id=2) == yaklasik({1: -15.0, 2: 0.0})
    assert length_offsets(kutuphane(), [5, 1, 2], ref_id=1) == yaklasik({1: 0.0, 2: 15.0, 5: -5.0})


def test_length_offsets_anahtarlar_sadece_istenenler():
    assert set(length_offsets(kutuphane(), [2, 5], ref_id=5)) == {2, 5}


@pytest.mark.parametrize("ids", [[1, 3], [1, 4]])
def test_length_offsets_gauge_length_yoksa_hata(ids):
    with pytest.raises(CamError):
        length_offsets(kutuphane(), ids, ref_id=1)


def test_length_offsets_referans_listede_yoksa_hata():
    with pytest.raises(CamError):
        length_offsets(kutuphane(), [1, 2], ref_id=5)


def test_length_offsets_takim_yoksa_hata():
    with pytest.raises(CamError):
        length_offsets(kutuphane(), [1, 99], ref_id=1)


# ---------------------------------------------------------------- K9 prob ile ölçüm


def test_offsets_from_probe():
    """Uzun takım ölçerde daha yukarıda tetiklenir: ΔL = z_n − z_ref."""
    okunan = {1: -62.5, 2: -47.5, 5: -67.5}
    assert offsets_from_probe(okunan, ref_id=1) == yaklasik({1: 0.0, 2: 15.0, 5: -5.0})
    assert offsets_from_probe(okunan, ref_id=2) == yaklasik({1: -15.0, 2: 0.0, 5: -20.0})


def test_offsets_from_probe_referans_yoksa_hata():
    with pytest.raises(CamError):
        offsets_from_probe({1: -62.5, 2: -47.5}, ref_id=5)


def test_offsets_from_probe_nan_hata():
    with pytest.raises(CamError):
        offsets_from_probe({1: -62.5, 2: NAN}, ref_id=1)


# ---------------------------------------------------------------- K9 doğrulama


def test_verify_offsets_tolerans_icinde():
    verify_offsets({1: 0.0, 2: 15.03}, {1: 0.0, 2: 15.0})
    verify_offsets({1: 0.0, 2: 14.96, 5: -5.04}, {1: 0.0, 2: 15.0, 5: -5.0})


def test_verify_offsets_tolerans_asimi_mesajda_takim():
    with pytest.raises(CamError) as e:
        verify_offsets({1: 0.0, 2: 15.08}, {1: 0.0, 2: 15.0})
    assert "T2" in str(e.value)


def test_verify_offsets_her_asim_mesajda():
    with pytest.raises(CamError) as e:
        verify_offsets({1: 0.0, 2: 15.1, 5: -5.2}, {1: 0.0, 2: 15.0, 5: -5.0})
    assert "T2" in str(e.value)
    assert "T5" in str(e.value)


def test_verify_offsets_tol_parametresi():
    verify_offsets({1: 0.0, 2: 15.1}, {1: 0.0, 2: 15.0}, tol=0.2)
    with pytest.raises(CamError):
        verify_offsets({1: 0.0, 2: 15.03}, {1: 0.0, 2: 15.0}, tol=0.01)


@pytest.mark.parametrize(
    ("olculen", "beklenen"),
    [({1: 0.0}, {1: 0.0, 2: 15.0}), ({1: 0.0, 2: 15.0}, {1: 0.0}), ({1: 0.0, 3: 15.0}, {1: 0.0, 2: 15.0})],
)
def test_verify_offsets_anahtarlar_ayni_olmali(olculen, beklenen):
    with pytest.raises(CamError):
        verify_offsets(olculen, beklenen)


def test_verify_offsets_nan_hata():
    with pytest.raises(CamError):
        verify_offsets({1: 0.0, 2: NAN}, {1: 0.0, 2: 15.0})


# ---------------------------------------------------------------- K9 Fanuc tablosu


def test_fanuc_offset_table_ek_a():
    assert fanuc_offset_table(kutuphane(), [1, 2]) == yaklasik({1: 90.0, 2: 105.0})


def test_fanuc_offset_table_gauge_length_yoksa_hata():
    with pytest.raises(CamError):
        fanuc_offset_table(kutuphane(), [1, 3])


# ---------------------------------------------------------------- K10 ölçüm programı

ALTIN_PROB = """G21 G90 G17 G94
M5
G49
T1
G53 G0 Z-1.
G53 G0 X-10. Y-20.
G53 G0 Z-70.
G91
G38.2 Z-50. F200.
G0 Z2.
G38.2 Z-3. F20.
G90
G53 G0 Z-1.
T2 M0
G53 G0 Z-1.
G53 G0 X-10. Y-20.
G53 G0 Z-70.
G91
G38.2 Z-50. F200.
G0 Z2.
G38.2 Z-3. F20.
G90
G53 G0 Z-1.
M30
"""


def test_toolsetter_varsayilanlar():
    s = ToolSetter(x=-10.0, y=-20.0, z_start=-70.0, z_safe=-1.0, travel=50.0)
    assert (s.feed_fast, s.feed_slow, s.backoff) == (200.0, 20.0, 2.0)


def test_probe_program_altin_metin():
    s = ToolSetter(x=-10, y=-20, z_start=-70, z_safe=-1, travel=50)
    assert probe_program([1, 2], s) == ALTIN_PROB


def test_probe_program_tek_takim():
    s = ToolSetter(x=-10, y=-20, z_start=-70, z_safe=-1, travel=50)
    satirlar = ALTIN_PROB.splitlines()
    beklenen = "\n".join(satirlar[:13] + satirlar[-1:]) + "\n"
    assert probe_program([1], s) == beklenen


def test_probe_program_ondalik_ve_besleme_bicimi():
    """Koordinatlar `decimals`, F değerleri 1 basamak (fmt)."""
    s = ToolSetter(
        x=-10.25,
        y=-20.5,
        z_start=-70.125,
        z_safe=-1.5,
        travel=40.0,
        feed_fast=150.0,
        feed_slow=12.5,
        backoff=1.5,
    )
    metin = probe_program([7], s, decimals=2)
    satirlar = metin.splitlines()
    assert satirlar[3] == "T7"
    assert satirlar[4] == f"G53 G0 Z{fmt(-1.5, 2)}"
    assert satirlar[5] == f"G53 G0 X{fmt(-10.25, 2)} Y{fmt(-20.5, 2)}"
    assert satirlar[6] == f"G53 G0 Z{fmt(-70.125, 2)}"
    assert satirlar[8] == f"G38.2 Z{fmt(-40.0, 2)} F{fmt(150.0, 1)}"
    assert satirlar[9] == f"G0 Z{fmt(1.5, 2)}"
    assert satirlar[10] == f"G38.2 Z{fmt(-2.25, 2)} F{fmt(12.5, 1)}"
    assert metin.endswith("M30\n")


@pytest.mark.parametrize(
    "kw",
    [
        {"z_safe": -80.0},  # z_safe < z_start
        {"travel": 0.0},
        {"travel": -50.0},
        {"feed_fast": 0.0},
        {"feed_slow": -20.0},
        {"backoff": 0.0},
        {"backoff": -2.0},
        {"travel": 3.0},  # 1.5·backoff = 3 ≥ travel
        {"x": NAN},
        {"z_start": NAN},
        {"travel": float("inf")},
    ],
)
def test_toolsetter_gecersiz(kw):
    args = {"x": -10.0, "y": -20.0, "z_start": -70.0, "z_safe": -1.0, "travel": 50.0} | kw
    with pytest.raises(CamError):
        ToolSetter(**args)


def test_toolsetter_sinir_gecerli():
    ToolSetter(x=-10.0, y=-20.0, z_start=-70.0, z_safe=-70.0, travel=3.01)  # z_safe = z_start, 3 < 3.01
