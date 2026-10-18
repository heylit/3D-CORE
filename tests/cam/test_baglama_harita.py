"""SPEC 10 — bağlama üst yüzey haritası: K6 ilkel haritası, K7 ağ haritası, K15 `fixture_map` hataları.

Testler sadece SPEC 10 metninden yazıldı; `cam/baglama.py` uygulama kodu okunmadı.
Teori ("Bağlama üst yüzey haritası"): hücre değeri z_F(c) = max{ z_üst(p) : p ∈ hücrenin kapalı dikdörtgeni },
değmeyen hücre −inf. Kutu (R = R_z(φ)): ayak izi döndürülmüş dikdörtgen, kapalı kesişim (2B ayırma ekseni);
Z silindiri: hücre dikdörtgeninin disk merkezine uzaklığı ≤ r. Beklenen haritalar bu testte bağımsız
yazılmış ayırma ekseni ve disk–dikdörtgen uzaklığı hesabıyla kurulur.
Hücre (i, j): x ∈ [x0 + i·dx, x0 + (i + 1)·dx], y ∈ [y0 + j·dy, y0 + (j + 1)·dy]; dizi indisi top[j, i].
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from cam.model import CamError, CylinderStock, Stock
from tests.cam.baglama_ara import (
    Fixture,
    FixtureMap,
    Primitive,
    fixture_map,
    make_fixture,
    mesh_topmap,
    primitive_topmap,
    primitives_wcs,
    vise_for,
)
from tests.cam.baglama_ref import STOK, VISE_GRIP, VISE_OLCU, Rx, Rz, frame

NINF = -np.inf


def izgara(x0: float, y0: float, d: float, nx: int, ny: int, dy: float | None = None) -> FixtureMap:
    dy = d if dy is None else dy
    return FixtureMap("test", x0, y0, d, dy, nx, ny, np.full((ny, nx), NINF))


def hucreler(g: FixtureMap):
    """Hücre köşeleri xa, xb, ya, yb, her biri (ny, nx)."""
    xa = g.x0 + np.arange(g.nx) * g.dx
    ya = g.y0 + np.arange(g.ny) * g.dy
    XA, YA = np.meshgrid(xa, ya)
    return XA, XA + g.dx, YA, YA + g.dy


def ayirma_ekseni_haritasi(g: FixtureMap, kose: np.ndarray, phi: float, z: float) -> np.ndarray:
    """Döndürülmüş dikdörtgen (köşeler (4, 2), kenar yönü φ) ile her hücre dikdörtgeni kapalı kesişiyorsa z.

    Eksenler: x, y (hücre normalleri) ve dikdörtgenin iki kenar normali.
    Kapalı örtüşme: max1 ≥ min2 ve max2 ≥ min1.
    """
    XA, XB, YA, YB = hucreler(g)
    hucre_kose = [(XA, YA), (XB, YA), (XB, YB), (XA, YB)]
    kesisir = np.ones(XA.shape, dtype=bool)
    eksenler = [(1.0, 0.0), (0.0, 1.0), (math.cos(phi), math.sin(phi)), (-math.sin(phi), math.cos(phi))]
    for ax, ay in eksenler:
        p_dik = kose @ np.array([ax, ay])
        h = np.stack([X * ax + Y * ay for X, Y in hucre_kose])
        kesisir &= (h.max(axis=0) >= p_dik.min()) & (p_dik.max() >= h.min(axis=0))
    return np.where(kesisir, z, NINF)


def disk_haritasi(g: FixtureMap, cx: float, cy: float, r: float, z: float) -> np.ndarray:
    XA, XB, YA, YB = hucreler(g)
    ux = np.maximum.reduce([XA - cx, np.zeros_like(XA), cx - XB])
    uy = np.maximum.reduce([YA - cy, np.zeros_like(YA), cy - YB])
    return np.where(np.hypot(ux, uy) <= r, z, NINF)


# ---------------------------------------------------------------- K6 ilkel haritası


def test_k6_hizali_kutu_sinira_degen_hucre_dahil():
    # kutu x ∈ [2, 5], y ∈ [3, 7], z üst 4; ızgara 1 mm. Kapalı kesişim: i ∈ 1..5, j ∈ 2..7
    g = izgara(0.0, 0.0, 1.0, 10, 10)
    top = primitive_topmap([Primitive(Stock(2, 3, 0, 5, 7, 4))], g)
    assert top.shape == (10, 10)
    beklenen = np.full((10, 10), NINF)
    beklenen[2:8, 1:6] = 4.0
    np.testing.assert_array_equal(top, beklenen)


def test_k6_hizali_kutu_1e9_disaridaki_haric():
    # kutu sınırları hücre sınırlarından 1e-9 içeride: komşu hücreye değmez → i ∈ 2..4, j ∈ 3..6
    e = 1e-9
    g = izgara(0.0, 0.0, 1.0, 10, 10)
    top = primitive_topmap([Primitive(Stock(2 + e, 3 + e, 0, 5 - e, 7 - e, 4))], g)
    beklenen = np.full((10, 10), NINF)
    beklenen[3:7, 2:5] = 4.0
    np.testing.assert_array_equal(top, beklenen)


def test_k6_cerceveli_hizali_kutu():
    # yerel Stock(0, 0, 0, 3, 4, 2), çerçeve origin (2.25, 3.25, 2), R_z(90°):
    # WCS x = 2.25 − y_l, y = 3.25 + x_l
    # → ayak izi x ∈ [−1.75, 2.25], y ∈ [3.25, 6.25], üst z = 4 (sınırlar hücre sınırlarından 0.25 uzak)
    g = izgara(-5.0, 0.0, 1.0, 10, 10)
    top = primitive_topmap([Primitive(Stock(0, 0, 0, 3, 4, 2), frame((2.25, 3.25, 2), Rz(90)))], g)
    beklenen = np.full((10, 10), NINF)
    # x (x0 = −5): [i − 5, i − 4] ∩ [−1.75, 2.25] → i ∈ 3..7; y: [j, j + 1] ∩ [3.25, 6.25] → j ∈ 3..6
    beklenen[3:7, 3:8] = 4.0
    np.testing.assert_array_equal(top, beklenen)


def test_k6_dondurulmus_kutu_ayirma_ekseni():
    # Stock(−3, −1, 0, 3, 1, 2), çerçeve (5.3, 4.7, 1), R_z(30°); üst z = 3
    phi = math.radians(30)
    fr = frame((5.3, 4.7, 1.0), Rz(30))
    g = izgara(0.0, 0.0, 0.5, 21, 19)
    top = primitive_topmap([Primitive(Stock(-3, -1, 0, 3, 1, 2), fr)], g)
    yerel = np.array([[-3, -1, 0], [3, -1, 0], [3, 1, 0], [-3, 1, 0]], dtype=float)
    kose = fr.to_world(yerel)[:, :2]
    beklenen = ayirma_ekseni_haritasi(g, kose, phi, 3.0)
    assert np.isfinite(beklenen).sum() > 20  # test anlamlı: çok hücre değiyor
    np.testing.assert_array_equal(top, beklenen)


def test_k6_z_silindiri_disk_dikdortgen():
    # CylinderStock(D = 6, z ∈ [0, 5]) çerçeve (5.2, 4.9, −1) → eksen (5.2, 4.9), r = 3, üst z = 4
    g = izgara(0.0, 0.0, 0.5, 21, 19)
    top = primitive_topmap([Primitive(CylinderStock(6, 0, 5), frame((5.2, 4.9, -1.0)))], g)
    beklenen = disk_haritasi(g, 5.2, 4.9, 3.0, 4.0)
    assert np.isfinite(beklenen).sum() > 20
    np.testing.assert_array_equal(top, beklenen)


def test_k6_birden_cok_ilkel_hucre_basina_en_buyuk():
    g = izgara(0.0, 0.0, 0.5, 21, 19)
    kutu = Primitive(Stock(1.1, 1.3, 0, 7.7, 6.1, 4))
    silindir = Primitive(CylinderStock(4, 0, 6), frame((7.3, 6.2, 0.0)))
    top = primitive_topmap([kutu, silindir], g)
    a = ayirma_ekseni_haritasi(g, np.array([[1.1, 1.3], [7.7, 1.3], [7.7, 6.1], [1.1, 6.1]]), 0.0, 4.0)
    b = disk_haritasi(g, 7.3, 6.2, 2.0, 6.0)
    np.testing.assert_array_equal(top, np.maximum(a, b))


def test_k6_degmeyen_ilkel_bos_harita():
    g = izgara(0.0, 0.0, 1.0, 4, 4)
    top = primitive_topmap([Primitive(Stock(10, 10, 0, 11, 11, 1))], g)
    assert np.all(top == NINF)


@pytest.mark.parametrize("R", [Rx(30), Rx(90)])
def test_k6_egik_ilkel_hata(R):
    g = izgara(0.0, 0.0, 1.0, 10, 10)
    with pytest.raises(CamError):
        primitive_topmap([Primitive(Stock(0, 0, 0, 2, 2, 2), frame((5, 5, 0), R))], g)


def test_k6_egik_silindir_hata():
    g = izgara(0.0, 0.0, 1.0, 10, 10)
    with pytest.raises(CamError):
        primitive_topmap([Primitive(CylinderStock(2, 0, 3), frame((5, 5, 0), Rx(45)))], g)


# ---------------------------------------------------------------- K7 ağ haritası


def kutu_agi(x0, y0, z0, x1, y1, z1) -> tuple[np.ndarray, np.ndarray]:
    """Elle kurulmuş 12 üçgenli kutu ağı (dışa yönlü)."""
    V = np.array(
        [
            [x0, y0, z0],
            [x1, y0, z0],
            [x1, y1, z0],
            [x0, y1, z0],
            [x0, y0, z1],
            [x1, y0, z1],
            [x1, y1, z1],
            [x0, y1, z1],
        ],
        dtype=float,
    )
    F = np.array(
        [
            [0, 2, 1], [0, 3, 2],  # alt
            [4, 5, 6], [4, 6, 7],  # üst
            [0, 1, 5], [0, 5, 4],  # y = y0
            [1, 2, 6], [1, 6, 5],  # x = x1
            [2, 3, 7], [2, 7, 6],  # y = y1
            [3, 0, 4], [3, 4, 7],  # x = x0
        ],
        dtype=np.int64,
    )  # fmt: skip
    return V, F


def test_k7_kutu_agi_ilkel_haritasiyla_ayni():
    # yerel kutu [2.3, 6.7] × [1.2, 8.6] × [0, 3], çerçeve (0.1, 0.2, 1) → WCS [2.4, 6.8] × [1.4, 8.8], üst 4;
    # ızgara 1 mm (sınırlar tam sayı), yüzler sınırlardan ≥ 0.2 uzak
    fr = frame((0.1, 0.2, 1.0))
    V, F = kutu_agi(2.3, 1.2, 0.0, 6.7, 8.6, 3.0)
    assert F.shape == (12, 3)
    g = izgara(0.0, 0.0, 1.0, 10, 10)
    agdan = mesh_topmap(V, F, fr, g)
    ilkelden = primitive_topmap([Primitive(Stock(2.3, 1.2, 0.0, 6.7, 8.6, 3.0), fr)], g)
    np.testing.assert_array_equal(agdan, ilkelden)
    beklenen = np.full((10, 10), NINF)
    beklenen[1:9, 2:7] = 4.0  # x ∈ [2.4, 6.8] → i ∈ 2..6; y ∈ [1.4, 8.8] → j ∈ 1..8
    np.testing.assert_array_equal(agdan, beklenen)


def test_k7_dondurulmus_kutu_agi_ilkel_haritasiyla_ayni():
    # R_z(90°) çerçeve: yerel kutu [0.3, 4.6] × [0.2, 2.9] × [0, 2], origin (7.4, 1.3, 0.5)
    # → WCS x = 7.4 − y ∈ [4.5, 7.2], y = 1.3 + x ∈ [1.5, 5.9]; ızgara 0.5 mm, sınırlara uzaklık ≥ 0.1
    fr = frame((7.4, 1.3, 0.5), Rz(90))
    V, F = kutu_agi(0.3, 0.2, 0.0, 4.6, 2.9, 2.0)
    g = izgara(0.0, 0.0, 0.5, 20, 16)
    agdan = mesh_topmap(V, F, fr, g)
    ilkelden = primitive_topmap([Primitive(Stock(0.3, 0.2, 0.0, 4.6, 2.9, 2.0), fr)], g)
    np.testing.assert_array_equal(agdan, ilkelden)


def kama_agi(L: float, W: float, H: float) -> tuple[np.ndarray, np.ndarray]:
    """Eğik kama: x ∈ [0, L], y ∈ [0, W], alt z = 0, üst yüzey z = (H/L)·x (x = L'de dik yüz)."""
    V = np.array(
        [[0, 0, 0], [L, 0, 0], [L, W, 0], [0, W, 0], [L, 0, H], [L, W, H]],
        dtype=float,
    )
    F = np.array(
        [
            [0, 2, 1], [0, 3, 2],  # alt
            [0, 1, 4],  # y = 0 yan üçgen
            [3, 5, 2],  # y = W yan üçgen
            [1, 2, 5], [1, 5, 4],  # x = L dik yüz
            [0, 4, 5], [0, 5, 3],  # eğik üst
        ],
        dtype=np.int64,
    )  # fmt: skip
    return V, F


def test_k7_egik_kama_temkinli_ve_sinirli():
    # kama L = 7.3, W = 4.6, H = 3.1, çerçeve (1.15, 0.85, 0.5): WCS üst yüzey
    # z(x) = 0.5 + (H/L)·(x − 1.15), x ∈ [1.15, 8.45], y ∈ [0.85, 5.45]. Δ_min = 0.5.
    # Kesin hücre en büyüğü: z(min(xb, 8.45)) (hücre ayak izine değiyorsa). SPEC: sonuç ≥ kesin ve
    # ≤ hücre XY'de √2·Δ_min şişirilince kesin en büyük (burada kare şişirme: daha geniş, güvenli üst sınır).
    L, W, H = 7.3, 4.6, 3.1
    ox, oy, oz = 1.15, 0.85, 0.5
    V, F = kama_agi(L, W, H)
    g = izgara(0.0, 0.0, 0.5, 20, 14)
    top = mesh_topmap(V, F, frame((ox, oy, oz)), g)
    XA, XB, YA, YB = hucreler(g)
    s = H / L

    def kesin(pay: float) -> np.ndarray:
        degiyor = (XB + pay >= ox) & (XA - pay <= ox + L) & (YB + pay >= oy) & (YA - pay <= oy + W)
        z = oz + s * (np.minimum(XB + pay, ox + L) - ox)
        return np.where(degiyor, z, NINF)

    alt = kesin(0.0)
    ust = kesin(math.sqrt(2) * 0.5)
    assert np.all(top >= alt - 1e-12)
    assert np.all(top <= ust + 1e-12)
    # kama dışındaki (ayak izine değmeyen) hücreler −inf, değenler sonlu
    np.testing.assert_array_equal(np.isfinite(top), np.isfinite(alt))


# ---------------------------------------------------------------- fixture_map


def mengene_fx() -> Fixture:
    v, fr = vise_for(STOK, VISE_GRIP, "x", **VISE_OLCU)
    return make_fixture("mengene", v, fr)


def test_fixture_map_izgara_kurali():
    # WCS XY sınır kutusu x ∈ [−10, 90], y ∈ [−20, 130]; nx = ⌈100/0.5⌉ = 200, ny = ⌈150/0.5⌉ = 300
    fx = mengene_fx()
    m = fixture_map(fx, 0.5)
    assert isinstance(m, FixtureMap)
    assert m.fixture == "mengene"
    assert (m.x0, m.y0) == pytest.approx((-10.0, -20.0), abs=1e-12)
    assert (m.nx, m.ny) == (200, 300)
    assert (m.dx, m.dy) == pytest.approx((0.5, 0.5), abs=1e-12)
    assert m.top.shape == (300, 200)
    X, Y = m.centers()
    assert X.shape == (300, 200) and Y.shape == (300, 200)
    assert (X[0, 0], Y[0, 0]) == pytest.approx((-9.75, -19.75), abs=1e-12)
    assert (X[-1, -1], Y[-1, -1]) == pytest.approx((89.75, 129.75), abs=1e-12)
    np.testing.assert_array_equal(m.top, primitive_topmap(primitives_wcs(fx), m))


def test_fixture_map_degerleri():
    m = fixture_map(mengene_fx(), 0.5)
    X, Y = m.centers()

    def deger(x, y):
        j, i = np.unravel_index(np.argmin(np.hypot(X - x, Y - y)), X.shape)
        return m.top[j, i]

    assert deger(40.25, -10.25) == 10.0  # sabit çene üstü
    assert deger(40.25, 60.25) == 10.0  # hareketli çene üstü
    assert deger(40.25, 3.25) == 0.0  # paralel üstü
    assert deger(40.25, 25.25) == -5.0  # yalnız yatak
    assert deger(40.25, 100.25) == -5.0  # yatak uzantısı
    assert np.all(np.isfinite(m.top))  # mengene ayak izi sınır kutusunu tam doldurur


def test_fixture_map_tam_bolunmeyen_hucre():
    # cell = 0.7: nx = ⌈100/0.7⌉ = 143, dx = 100/143; ny = ⌈150/0.7⌉ = 215, dy = 150/215
    m = fixture_map(mengene_fx(), 0.7)
    assert (m.nx, m.ny) == (143, 215)
    assert m.dx == pytest.approx(100 / 143, abs=1e-12)
    assert m.dy == pytest.approx(150 / 215, abs=1e-12)


# ---------------------------------------------------------------- K15 fixture_map hataları


@pytest.mark.parametrize("cell", [0.0, -1.0, math.inf, math.nan])
def test_k15_fixture_map_hucre_hata(cell):
    with pytest.raises(CamError):
        fixture_map(mengene_fx(), cell)


def test_k15_fixture_map_max_cells():
    # 0.5 mm'de 200 × 300 = 60000 hücre > 1000
    with pytest.raises(CamError):
        fixture_map(mengene_fx(), 0.5, max_cells=1000)


def test_k15_fixture_map_ozel_parts_yok():
    fx = Fixture(name="ozel", part_ref="govde", kind="ozel")
    with pytest.raises(CamError):
        fixture_map(fx, 1.0)


def test_k15_fixture_map_ozel_kimlik_yok():
    fx = Fixture(name="ozel", part_ref="govde", kind="ozel")
    with pytest.raises(CamError):
        fixture_map(fx, 1.0, parts={"baska": object()})
