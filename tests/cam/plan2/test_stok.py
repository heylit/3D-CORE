"""SPEC 57 §1 — cam/plan2/stok.py testleri (K1, K2). OCCT gerektirmez.

Testler yalnızca SPEC 57 metninden ve iskeletteki imzalardan yazıldı; gövdeler okunmadı.
Arayüz (kodlayıcının netleştirmesi, durum/57 madde 4, 21cac89): `select_stock` `bbox`'ı
`(b_min, b_max)` olarak alır (2×3 dizi de olur); dönen 4×4 `T` parçanın dünya koordinatından stok
koordinatına rijit dönüşümdür (stok, katalog satırının yönünde); `load_catalog` JSON'u `StockSize`
alanlarından oluşan nesnelerin listesidir, hatalı satır → CamError.

El hesapları:
- K1: parça 80 × 50 × 30, m = 1, g = 5 → gereken (82, 52, 36). 100×60×40 (240 000 mm³) ve
  90×60×40 (216 000) uyar; 60×90×45 (243 000) parça z çevresinde 90° döndürülünce uyar
  (52 ≤ 60, 82 ≤ 90, 36 ≤ 45) → en küçük 90×60×40. Katalog yalnız 60×90×45 → tek uyan yerleşim:
  parçanın x'i stokun y'sine, y'si x'ine (stok ekseninde 50, 80, 30).
- K2: kesit 40 × 30 → √(40² + 30²) = 50, d ≥ 52 → Ø50 uymaz, Ø55 en küçük uyan; boy
  60 + 1 + 5 + 3 = 69. Diğer eksenler: √(30² + 60²) + 2 = 69.1 ve √(40² + 60²) + 2 = 74.1 > 60
  → çubuk ekseni parçanın z'si.
"""

from __future__ import annotations

import json
import math

import numpy as np
import pytest

from cam.model import CamError, CylinderStock, Stock
from cam.plan2.stok import StockSize, load_catalog, select_stock

BBOX = (np.array([0.0, 0.0, 0.0]), np.array([80.0, 50.0, 30.0]))
KATALOG = (
    StockSize("blok", 100, 60, 40, name="B100"),
    StockSize("blok", 90, 60, 40, name="B90"),
    StockSize("blok", 60, 90, 45, name="B60"),
)
CUBUKLAR = (
    StockSize("cubuk", 50, max_len=1000, name="C50"),
    StockSize("cubuk", 55, max_len=1000, name="C55"),
    StockSize("cubuk", 60, max_len=1000, name="C60"),
)
TOL = 1e-9


def _koseler(bbox) -> np.ndarray:
    lo, hi = (np.asarray(b, dtype=float) for b in bbox)
    return np.array(
        [[(lo, hi)[i][0], (lo, hi)[j][1], (lo, hi)[k][2]] for i in (0, 1) for j in (0, 1) for k in (0, 1)]
    )


def _yerlesim(T: np.ndarray, bbox) -> np.ndarray:
    """Parça sınır kutusu köşelerinin stok koordinatındaki konumu (8×3)."""
    T = np.asarray(T, dtype=float)
    assert T.shape == (4, 4)
    R, t = T[:3, :3], T[:3, 3]
    assert np.allclose(R.T @ R, np.eye(3), atol=1e-9) and np.linalg.det(R) == pytest.approx(1.0)
    assert np.allclose(T[3], [0, 0, 0, 1])
    return _koseler(bbox) @ R.T + t


def _blok_paylari(stok: Stock, T, bbox, m=1.0, g=5.0) -> np.ndarray:
    P = _yerlesim(T, bbox)
    lo, hi = P.min(axis=0), P.max(axis=0)
    assert lo[0] - stok.xmin >= m - TOL and stok.xmax - hi[0] >= m - TOL
    assert lo[1] - stok.ymin >= m - TOL and stok.ymax - hi[1] >= m - TOL
    assert stok.zmax - hi[2] >= m - TOL  # üst işleme payı
    assert lo[2] - stok.zmin >= g - TOL  # alt kavrama payı
    return hi - lo


def _boyut(stok: Stock) -> tuple[float, float, float]:
    return (stok.xmax - stok.xmin, stok.ymax - stok.ymin, stok.zmax - stok.zmin)


# ---------------------------------------------------------------- K1 blok


def test_blok_en_kucuk_hacim():
    stok, T = select_stock(BBOX, KATALOG)
    assert isinstance(stok, Stock)
    assert _boyut(stok) == pytest.approx((90, 60, 40))
    assert _blok_paylari(stok, T, BBOX) == pytest.approx((80, 50, 30))


def test_blok_permutasyon():
    stok, T = select_stock(BBOX, (StockSize("blok", 60, 90, 45, name="B60"),))
    assert _boyut(stok) == pytest.approx((60, 90, 45))
    assert _blok_paylari(stok, T, BBOX) == pytest.approx((50, 80, 30))  # z çevresinde 90° döndürülmüş


def test_blok_esitlikte_ilk_satir():
    # 90×60×40 ve 60×90×40 aynı hacim; ilk satır seçilir (stok satırın yönünde)
    katalog = (StockSize("blok", 60, 90, 40, name="ilk"), StockSize("blok", 90, 60, 40, name="ikinci"))
    stok, T = select_stock(BBOX, katalog)
    assert _boyut(stok) == pytest.approx((60, 90, 40))
    _blok_paylari(stok, T, BBOX)


def test_blok_paylar():
    # m = 2, g = 8 → gereken (84, 54, 40): 90×60×40 hâlâ uyar, 60×90×45'te z 30 + 2 + 8 = 40 ≤ 45
    stok, T = select_stock(BBOX, KATALOG, m=2.0, g=8.0)
    assert _boyut(stok) == pytest.approx((90, 60, 40))
    _blok_paylari(stok, T, BBOX, m=2.0, g=8.0)
    # g = 10 → z 41: 90×60×40 artık uymaz; 100×60×40 de uymaz; 60×90×45 uyar
    stok, T = select_stock(BBOX, KATALOG, m=1.0, g=10.0)
    assert _boyut(stok) == pytest.approx((60, 90, 45))
    _blok_paylari(stok, T, BBOX, m=1.0, g=10.0)


def test_blok_oteleme_parca_konumundan_bagimsiz():
    kayik = (BBOX[0] + [7.0, -3.0, 12.0], BBOX[1] + [7.0, -3.0, 12.0])
    stok, T = select_stock(kayik, KATALOG)
    assert _boyut(stok) == pytest.approx((90, 60, 40))
    _blok_paylari(stok, T, kayik)


def test_stok_yok():
    with pytest.raises(CamError, match="stok_yok"):
        select_stock(BBOX, (StockSize("blok", 81, 51, 35), StockSize("blok", 60, 60, 60)))
    with pytest.raises(CamError, match="stok_yok"):
        select_stock(BBOX, ())


# ---------------------------------------------------------------- K2 çubuk


def test_cubuk_cap():
    bbox = (np.zeros(3), np.array([40.0, 30.0, 60.0]))
    stok, T = select_stock(bbox, CUBUKLAR)
    assert isinstance(stok, CylinderStock)
    assert stok.D == pytest.approx(55.0)
    assert stok.d == 0.0
    assert stok.zmax - stok.zmin == pytest.approx(60 + 1 + 5 + 3)
    P = _yerlesim(T, bbox)
    r_max = float(np.max(np.hypot(P[:, 0], P[:, 1])))
    assert r_max <= stok.D / 2 - 1.0 + TOL  # dairesel kesit tam kapsar, yanda m payı
    assert P[:, 2].max() - P[:, 2].min() == pytest.approx(60.0)  # çubuk ekseni parçanın z'si
    assert stok.zmax - P[:, 2].max() >= 1.0 - TOL
    assert P[:, 2].min() - stok.zmin >= 5.0 - TOL


def test_cubuk_sinir_capi():
    # tam sınır: d = 52 uyar
    bbox = (np.zeros(3), np.array([40.0, 30.0, 60.0]))
    stok, _ = select_stock(bbox, (StockSize("cubuk", 50), StockSize("cubuk", 52), StockSize("cubuk", 60)))
    assert stok.D == pytest.approx(52.0)


def test_cubuk_boy_siniri():
    bbox = (np.zeros(3), np.array([40.0, 30.0, 60.0]))
    with pytest.raises(CamError, match="stok_yok"):
        select_stock(bbox, (StockSize("cubuk", 55, max_len=68.0),))  # gereken boy 69
    stok, _ = select_stock(bbox, (StockSize("cubuk", 55, max_len=69.0),))
    assert stok.zmax - stok.zmin == pytest.approx(69.0)


def test_cubuk_testere_payi():
    bbox = (np.zeros(3), np.array([40.0, 30.0, 60.0]))
    stok, _ = select_stock(bbox, CUBUKLAR, m=1.0, g=5.0, saw=0.0)
    assert stok.zmax - stok.zmin == pytest.approx(66.0)
    assert math.isclose(stok.D, 55.0)


# ---------------------------------------------------------------- katalog dosyası


def test_load_catalog(tmp_path):
    satirlar = [
        {"kind": "blok", "a": 100, "b": 60, "c": 40, "name": "B100"},
        {"kind": "cubuk", "a": 55, "max_len": 1000, "name": "C55"},
    ]
    yol = tmp_path / "katalog.json"
    yol.write_text(json.dumps(satirlar), encoding="utf-8")
    katalog = load_catalog(yol)
    assert isinstance(katalog, tuple)
    assert katalog == (
        StockSize("blok", 100.0, 60.0, 40.0, name="B100"),
        StockSize("cubuk", 55.0, max_len=1000.0, name="C55"),
    )
    assert load_catalog(str(yol)) == katalog


def test_load_catalog_dizi_bbox():
    stok, _ = select_stock(np.array([[0.0, 0.0, 0.0], [80.0, 50.0, 30.0]]), KATALOG)  # 2×3 dizi
    assert _boyut(stok) == pytest.approx((90, 60, 40))


@pytest.mark.parametrize(
    "satir",
    [
        {"kind": "blok", "a": 100, "b": 60, "c": 40, "renk": "mavi"},  # bilinmeyen anahtar
        {"a": 100, "b": 60, "c": 40},  # kind yok
        {"kind": "cubuk", "max_len": 1000},  # a yok
        {"kind": "blok", "a": 100, "b": 0, "c": 40},  # pozitif olmayan ölçü
        {"kind": "cubuk", "a": -55, "max_len": 1000},
    ],
)
def test_load_catalog_hatali(tmp_path, satir):
    yol = tmp_path / "hatali.json"
    yol.write_text(json.dumps([satir]), encoding="utf-8")
    with pytest.raises(CamError):
        load_catalog(yol)
