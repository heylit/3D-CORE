"""
SPEC 15 — viz.plot doğrulama testleri (K10–K14). Hepsi ekransız (off_screen=True).

Beklenen değerler: parça / bileşen sınır kutuları el hesabı (p' = R p + t), takım yolu sınırları
tp.bbox() ve tol (SPEC 15, K4), piksel kontrolünde en/boy oranı paralel izdüşümde a/b.
viz/ kodu okunmadan yazıldı.
"""

from __future__ import annotations

import struct

import numpy as np
import pytest

pv = pytest.importorskip("pyvista")

from assy.model import Assembly, Component, rot_z, transform  # noqa: E402
from cam.model import Move, MoveType, Stock, Tool, ToolKind, Toolpath  # noqa: E402
from viz.plot import plot_assembly, plot_part, plot_toolpath, screenshot  # noqa: E402
from viz.scene import VizError  # noqa: E402

TOOL = Tool(id=1, name="T1 d6", kind=ToolKind.FLAT, D=6.0, flute_length=20.0)
F = 500.0


def blok(a, b, c, name="blok"):
    bd = pytest.importorskip("build123d")
    from geometry.part import Part

    return Part(bd.Box(a, b, c, align=(bd.Align.MIN, bd.Align.MIN, bd.Align.MIN)), name=name)


def sinir(plotter, ad: str) -> tuple[np.ndarray, np.ndarray]:
    """Aktörün sınırları (xmin, xmax, ymin, ymax, zmin, zmax) → (min, max)."""
    assert ad in plotter.actors, f"aktör yok: {ad} (var olanlar: {list(plotter.actors)})"
    b = np.array(plotter.actors[ad].GetBounds(), dtype=float)
    return b[0::2], b[1::2]


def ornek_yol() -> Toolpath:
    return Toolpath(
        name="ornek",
        tool=TOOL,
        start=(0, 0, 10),
        rpm=8000.0,
        moves=[
            Move(MoveType.RAPID, (10, 0, 2)),
            Move(MoveType.LINEAR, (10, 0, -1), feed=F),
            Move(MoveType.ARC_CCW, (-10, 0, -1), feed=F, center=(0.0, 0.0)),
            Move(MoveType.LINEAR, (-10, -5, -1), feed=F),
            Move(MoveType.RAPID, (-10, -5, 10)),
        ],
    )


def png_boyutu(path) -> tuple[int, int]:
    """PNG IHDR: imza (8 bayt) + uzunluk (4) + 'IHDR' (4) + genişlik (4) + yükseklik (4), büyük endian."""
    with open(path, "rb") as f:
        bas = f.read(24)
    assert bas[:8] == b"\x89PNG\r\n\x1a\n"
    w, h = struct.unpack(">II", bas[16:24])
    return w, h


# ---------- K10 ----------


@pytest.mark.occt
def test_k10_plot_part_aktor_ve_sinir():
    parca = blok(100, 60, 20, name="kapak")
    p = plot_part(parca, off_screen=True)
    try:
        lo, hi = sinir(p, "part:kapak")
        plo, phi = parca.bbox
        np.testing.assert_allclose(lo, plo, atol=1e-6)
        np.testing.assert_allclose(hi, phi, atol=1e-6)
    finally:
        p.close()


@pytest.mark.occt
def test_k10_plot_assembly_aktorler_ve_sinirlar():
    """b bileşeni: rot_z(90°) + t = (5, 6, 7) → x ∈ [−55, 5], y ∈ [6, 106], z ∈ [7, 27]."""
    parca = blok(100, 60, 20)
    assy = Assembly(
        "m",
        components=[
            Component("a", "blok"),
            Component("b", "blok", T=transform(rot_z(90), (5, 6, 7))),
        ],
    )
    p = plot_assembly(assy, {"blok": parca}, off_screen=True)
    try:
        lo, hi = sinir(p, "comp:a")
        np.testing.assert_allclose(lo, (0, 0, 0), atol=1e-6)
        np.testing.assert_allclose(hi, (100, 60, 20), atol=1e-6)
        lo, hi = sinir(p, "comp:b")
        np.testing.assert_allclose(lo, (-55, 6, 7), atol=1e-6)
        np.testing.assert_allclose(hi, (5, 106, 27), atol=1e-6)
    finally:
        p.close()


# ---------- K11 ----------


def test_k11_plot_toolpath_aktorler_ve_sinirlar():
    tp = ornek_yol()
    tol = 0.05
    p = plot_toolpath(tp, tol=tol, off_screen=True)
    try:
        rlo, rhi = sinir(p, "toolpath:rapid")
        flo, fhi = sinir(p, "toolpath:feed")
        lo, hi = np.minimum(rlo, flo), np.maximum(rhi, fhi)
        blo, bhi = tp.bbox()
        assert np.all(lo >= blo - 1e-9) and np.all(hi <= bhi + 1e-9)
        assert np.all(lo - blo <= tol + 1e-9) and np.all(bhi - hi <= tol + 1e-9)
        # hızlı hareketler: başlangıç (0,0,10) → (10,0,2) ve (−10,−5,−1) → (−10,−5,10)
        np.testing.assert_allclose(rlo, (-10, -5, -1), atol=1e-9)
        np.testing.assert_allclose(rhi, (10, 0, 10), atol=1e-9)
    finally:
        p.close()


def test_k11_ham_malzeme_aktoru():
    st = Stock(-20, -15, -5, 20, 15, 0)
    p = plot_toolpath(ornek_yol(), stock=st, off_screen=True)
    try:
        lo, hi = sinir(p, "stock")
        np.testing.assert_allclose(lo, (-20, -15, -5), atol=1e-9)
        np.testing.assert_allclose(hi, (20, 15, 0), atol=1e-9)
    finally:
        p.close()


# ---------- K12, K13: piksel kontrolleri ----------


def nesne_maskesi(img: np.ndarray) -> np.ndarray:
    """Beyaz arka plandan belirgin farklı pikseller."""
    return img.astype(int).sum(axis=2) < 3 * 255 - 30


@pytest.mark.occt
def test_k12_blok_en_boy_orani():
    """Paralel izdüşüm, üstten (xy): görüntüdeki blok en/boy = 100/60 (± %3)."""
    p = plot_part(blok(100, 60, 20), off_screen=True)
    try:
        img = screenshot(p, window_size=(400, 300), view="xy", parallel=True)
    finally:
        p.close()
    assert img.shape == (300, 400, 3)
    assert img.dtype == np.uint8
    m = nesne_maskesi(img)
    satir = np.flatnonzero(m.any(axis=1))
    sutun = np.flatnonzero(m.any(axis=0))
    assert len(satir) > 20 and len(sutun) > 20
    en = sutun[-1] - sutun[0] + 1
    boy = satir[-1] - satir[0] + 1
    assert en / boy == pytest.approx(100 / 60, rel=0.03)


def test_k13_renk_ayrimi_sol_hizli_sag_kesme():
    """Sol yarı tek G0, sağ yarı tek G1; sahne x'te simetrik → kamera ortası x = 0."""
    tp = Toolpath(
        name="renk",
        tool=TOOL,
        start=(-50, -10, 0),
        rpm=8000.0,
        moves=[Move(MoveType.RAPID, (0, 0, 0)), Move(MoveType.LINEAR, (50, 10, 0), feed=F)],
    )
    p = plot_toolpath(tp, off_screen=True)
    try:
        img = screenshot(p, window_size=(400, 300), view="xy", parallel=True).astype(int)
    finally:
        p.close()
    r, g, b = img[..., 0], img[..., 1], img[..., 2]
    kirmizi = (r > 150) & (g < 100) & (b < 100)
    mavi = (b > 150) & (r < 100) & (g < 100)
    assert kirmizi.any() and mavi.any()
    w = img.shape[1]
    assert np.flatnonzero(kirmizi.any(axis=0)).max() <= w / 2 + 2
    assert np.flatnonzero(mavi.any(axis=0)).min() >= w / 2 - 2


# ---------- K14 ----------


@pytest.mark.occt
def test_k14_ayni_sahne_ve_png(tmp_path):
    parca = blok(40, 30, 10, name="p")
    p = plot_part(parca, off_screen=True)
    try:
        p2 = plot_toolpath(ornek_yol(), plotter=p, off_screen=True)
        assert p2 is p
        for ad in ("part:p", "toolpath:rapid", "toolpath:feed"):
            assert ad in p.actors
        yol = tmp_path / "sahne.png"
        img = screenshot(p, yol, window_size=(320, 240))
    finally:
        p.close()
    assert img.shape == (240, 320, 3)
    assert yol.is_file()
    assert png_boyutu(yol) == (320, 240)


def test_k14_gecersiz_gorunum_hata():
    p = plot_toolpath(ornek_yol(), off_screen=True)
    try:
        with pytest.raises(VizError):
            screenshot(p, view="ust")
    finally:
        p.close()


def test_k14_bos_sahne_hata():
    p = pv.Plotter(off_screen=True)
    try:
        with pytest.raises(VizError):
            screenshot(p)
    finally:
        p.close()
