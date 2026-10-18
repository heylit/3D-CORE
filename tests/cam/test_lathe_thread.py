"""SPEC 20 — diş çekme testleri (K14–K15): iso_thread_depth, thread_depths, thread.

Testler sadece SPEC 20 metninden ve sabit arayüzlerden yazıldı; cam/lathe_ops.py gövdeleri okunmadı.

- ISO 68-1: H = (√3/2)·P; dış diş h = 17/24·H, iç diş h = 5/8·H.
- Fanuc G76: h_i = Δd·√i; h_i − h_{i−1} < Δd_min ise h_i = h_{i−1} + Δd_min; h_i ≥ h olan ilk paso h'ye
  kırpılır ve son pasodur (SPEC genel toleransı 1e-9 karşılaştırmada da geçerli); ardından k boş paso.
- Paso: G1, feed = hatve; dışta T = 8 ile P_x = x0 − h_i, içte T = 6 ile P_x = x0 + h_i;
  "yanak" dalmada paso başı ve sonu Δz_i = s·h_i·tan(εr/2) kayar, s = sign(z_end − z_start).
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from cam.lathe_ops import TurnCut, iso_thread_depth, thread, thread_depths
from cam.model import CamError, CylinderStock, LatheTool, LatheToolKind, MoveType, Toolpath

TOL = 1e-9
STOCK = CylinderStock(D=20.0, zmin=-50.0, zmax=0.0)  # dış diş M20
TUBE = CylinderStock(D=40.0, zmin=-50.0, zmax=0.0, d=16.0)  # iç diş, delik yarıçapı 8


def ref_depths(h: float, first: float, minimum: float = 0.0, spring: int = 0) -> list[float]:
    """SPEC 20 Fanuc G76 kuralının doğrudan yazımı (beklenen değer)."""
    out: list[float] = []
    prev = 0.0
    i = 1
    while True:
        hi = first * math.sqrt(i)
        if hi - prev < minimum:
            hi = prev + minimum
        if hi >= h - TOL:
            out.append(h)
            break
        out.append(hi)
        prev = hi
        i += 1
    return out + [h] * spring


def thread_tool(tip: int = 8, kind=LatheToolKind.THREAD, eps: float = 60.0) -> LatheTool:
    return LatheTool(id=3, name="D", kind=kind, nose_r=0.1, tip=tip, kappa_r=60.0, eps_r=eps)


def tcut(css: float | None = None) -> TurnCut:
    return TurnCut(feed=0.1, rpm=800.0, css=css)


def g1_passes(tp: Toolpath):
    """G1 pasoları [(a, b, feed)] (z, x) koordinatında."""
    out = []
    a = np.array([tp.start[2], tp.start[0]])
    for m in tp.moves:
        b = np.array([m.end[2], m.end[0]])
        if m.type is MoveType.LINEAR:
            out.append((a, b, m.feed))
        a = b
    return out


# ------------------------------------------------------------------ K14 iso_thread_depth, thread_depths


def test_k14_iso_derinlik_p15():
    assert iso_thread_depth(1.5) == pytest.approx(0.920152, abs=5e-7)
    assert iso_thread_depth(1.5, external=False) == pytest.approx(0.811899, abs=5e-7)
    H = math.sqrt(3.0) / 2.0 * 1.5
    assert iso_thread_depth(1.5) == pytest.approx(17.0 / 24.0 * H, rel=1e-12)
    assert iso_thread_depth(1.5, external=True) == pytest.approx(17.0 / 24.0 * H, rel=1e-12)
    assert iso_thread_depth(1.5, external=False) == pytest.approx(5.0 / 8.0 * H, rel=1e-12)


@pytest.mark.parametrize("P", [0.5, 1.0, 1.75, 3.0])
def test_k14_iso_derinlik_katsayilari(P):
    assert iso_thread_depth(P) == pytest.approx(0.613435 * P, rel=1e-6)
    assert iso_thread_depth(P, external=False) == pytest.approx(0.541266 * P, rel=1e-6)


@pytest.mark.parametrize("P", [0.0, -1.0, math.nan, math.inf])
def test_k14_iso_derinlik_hatali(P):
    with pytest.raises(CamError):
        iso_thread_depth(P)


def test_k14_kok_i_dizisi():
    d = thread_depths(1.0, 0.3)
    beklenen = [0.3 * math.sqrt(i) for i in range(1, 12)] + [1.0]
    assert len(d) == math.ceil((1.0 / 0.3) ** 2) == 12
    np.testing.assert_allclose(d, beklenen, rtol=0, atol=1e-12)
    assert d[-1] == 1.0  # son paso tam h


def test_k14_minimum_artis():
    d = thread_depths(1.0, 0.3, minimum=0.1)
    s2 = 0.3 * math.sqrt(2.0)
    beklenen = [0.3, s2, s2 + 0.1, s2 + 0.2, s2 + 0.3, s2 + 0.4, s2 + 0.5, 1.0]
    np.testing.assert_allclose(d, beklenen, rtol=0, atol=1e-12)
    assert d == pytest.approx(ref_depths(1.0, 0.3, 0.1), abs=1e-12)
    artis = np.diff([0.0, *d])
    assert np.all(artis[:-1] >= 0.1 - 1e-12)  # kırpılan son paso hariç


def test_k14_bos_pasolar():
    d = thread_depths(1.0, 0.3, spring=2)
    assert len(d) == 14
    assert d[-3:] == [1.0, 1.0, 1.0]


@pytest.mark.parametrize("first", [1.0, 1.5])
def test_k14_first_h_den_buyuk(first):
    assert thread_depths(1.0, first) == [1.0]
    assert thread_depths(1.0, first, spring=1) == [1.0, 1.0]


def test_k14_toleransli_paso_sayisi():
    # 0.3·√9 = 0.8999999999999999 < 0.9: 1e-9 toleransla 9. paso h'ye ulaşmış sayılır
    d = thread_depths(0.9, 0.3)
    assert len(d) == 9
    assert d[-1] == 0.9


@pytest.mark.parametrize(
    ("h", "first", "minimum", "spring"),
    [
        (1.0, 0.3, 0.05, 1),
        (0.920152, 0.25, 0.05, 2),
        (0.811899, 0.2, 0.0, 0),
        (2.5, 0.4, 0.15, 3),
    ],
)
def test_k14_referans_kurala_uyuyor(h, first, minimum, spring):
    d = thread_depths(h, first, minimum, spring)
    assert d == pytest.approx(ref_depths(h, first, minimum, spring), abs=1e-12)
    assert all(b >= a for a, b in zip(d[:-1], d[1:], strict=True))


@pytest.mark.parametrize(
    "args",
    [
        (0.0, 0.3, 0.0, 0),
        (-1.0, 0.3, 0.0, 0),
        (1.0, 0.0, 0.0, 0),
        (1.0, -0.3, 0.0, 0),
        (1.0, 0.3, -0.1, 0),
        (1.0, 0.3, 0.0, -1),
        (1.0, 0.3, 0.0, 1.5),
        (math.nan, 0.3, 0.0, 0),
        (1.0, math.inf, 0.0, 0),
        (1.0, 0.3, math.nan, 0),
    ],
)
def test_k14_hatali_girdi(args):
    with pytest.raises(CamError):
        thread_depths(*args)


# ------------------------------------------------------------------ K15 thread


def test_k15_radyal_dis_dis():
    tool = thread_tool()
    P = 1.5
    h = iso_thread_depth(P)
    x0, z_start, z_end = 10.0, 3.0, -20.0
    tp = thread(
        STOCK, tool, tcut(), z_start=z_start, z_end=z_end, x0=x0, pitch=P, depth=h, first=0.3, minimum=0.05
    )
    depths = ref_depths(h, 0.3, 0.05, spring=1)
    passes = g1_passes(tp)
    assert len(passes) == len(depths)
    for (a, b, f), hi in zip(passes, depths, strict=True):
        assert f == P
        assert a[1] == pytest.approx(x0 - hi, abs=TOL) and b[1] == pytest.approx(x0 - hi, abs=TOL)
        assert a[0] == pytest.approx(z_start, abs=TOL)
        assert b[0] == pytest.approx(z_end, abs=TOL)
    assert passes[-1][0][1] == pytest.approx(x0 - h, abs=TOL)
    # G0'lar ilerlemesiz
    assert all(m.feed is None for m in tp.moves if m.type is MoveType.RAPID)


@pytest.mark.parametrize(("z_start", "z_end"), [(3.0, -20.0), (-20.0, -2.0)])
def test_k15_yanak_dalma(z_start, z_end):
    tool = thread_tool(eps=60.0)
    P = 2.0
    h = iso_thread_depth(P)
    x0 = 10.0
    tp = thread(
        STOCK,
        tool,
        tcut(),
        z_start=z_start,
        z_end=z_end,
        x0=x0,
        pitch=P,
        depth=h,
        first=0.35,
        minimum=0.05,
        spring=1,
        infeed="yanak",
    )
    depths = ref_depths(h, 0.35, 0.05, spring=1)
    s = math.copysign(1.0, z_end - z_start)
    passes = g1_passes(tp)
    assert len(passes) == len(depths)
    for (a, b, f), hi in zip(passes, depths, strict=True):
        dz = s * hi * math.tan(math.radians(30.0))
        assert f == P
        assert a[1] == pytest.approx(x0 - hi, abs=TOL)
        assert a[0] == pytest.approx(z_start + dz, abs=TOL)
        assert b[0] == pytest.approx(z_end + dz, abs=TOL)


def test_k15_ic_dis_aynada():
    tool = thread_tool(tip=6)
    P = 1.5
    h = iso_thread_depth(P, external=False)
    x0 = 8.0
    tp = thread(
        TUBE, tool, tcut(), z_start=2.0, z_end=-15.0, x0=x0, pitch=P, depth=h, first=0.25, spring=1, side="ic"
    )
    depths = ref_depths(h, 0.25, 0.0, spring=1)
    passes = g1_passes(tp)
    assert len(passes) == len(depths)
    for (a, b, f), hi in zip(passes, depths, strict=True):
        assert f == P
        assert a[1] == pytest.approx(x0 + hi, abs=TOL) and b[1] == pytest.approx(x0 + hi, abs=TOL)
        assert a[0] == pytest.approx(2.0, abs=TOL) and b[0] == pytest.approx(-15.0, abs=TOL)


@pytest.mark.parametrize("tip", [0, 9])
def test_k15_merkez_uclu_takim(tip):
    # T = 0 / 9: P = C, C_x = x0 − h_i + r
    tool = thread_tool(tip=tip)
    h = 0.9
    tp = thread(
        STOCK, tool, tcut(), z_start=3.0, z_end=-20.0, x0=10.0, pitch=1.5, depth=h, first=0.3, spring=0
    )
    depths = ref_depths(h, 0.3, 0.0, spring=0)
    passes = g1_passes(tp)
    assert len(passes) == len(depths) == 9
    for (a, _, _), hi in zip(passes, depths, strict=True):
        assert a[1] == pytest.approx(10.0 - hi + tool.nose_r, abs=TOL)


def base_args() -> dict:
    return {
        "z_start": 3.0,
        "z_end": -20.0,
        "x0": 10.0,
        "pitch": 1.5,
        "depth": 0.92,
        "first": 0.3,
        "minimum": 0.0,
        "spring": 1,
        "infeed": "radyal",
        "side": "dis",
    }


@pytest.mark.parametrize(
    ("kw", "tool_kw", "stock"),
    [
        ({}, {"tip": 3}, STOCK),  # dışta uç 3
        ({}, {"tip": 6}, STOCK),  # dışta uç 6
        ({}, {"kind": LatheToolKind.TURN, "tip": 8}, STOCK),  # yanlış takım türü
        ({"side": "ic", "x0": 8.0}, {"tip": 8}, TUBE),  # içte uç 8
        ({"side": "ic", "x0": 8.0}, {"tip": 6}, STOCK),  # dolu çubukta iç diş
        ({"x0": 0.5}, {}, STOCK),  # x0 − h ≤ 0
        ({"x0": 0.92}, {}, STOCK),
        ({"pitch": 0.0}, {}, STOCK),
        ({"pitch": -1.5}, {}, STOCK),
        ({"z_end": 3.0}, {}, STOCK),  # z_start = z_end
        ({"infeed": "eksenel"}, {}, STOCK),
        ({"side": "yan"}, {}, STOCK),
        ({"depth": 0.0}, {}, STOCK),
        ({"first": 0.0}, {}, STOCK),
    ],
)
def test_k15_hatali_girdi(kw, tool_kw, stock):
    tool = thread_tool(**tool_kw)
    with pytest.raises(CamError):
        thread(stock, tool, tcut(), **(base_args() | kw))


def test_k15_css_verilirse_hata():
    with pytest.raises(CamError):
        thread(STOCK, thread_tool(), tcut(css=150.0), **base_args())
