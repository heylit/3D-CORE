"""SPEC 53 K5–K6 — girişim aday çiftleri için sınır kutusu ağacı (BVH).

Testler SPEC 53 "Girişimde sınır kutusu ağacı" bölümünden ve arayüzden yazıldı; assy/bvh.py kodu okunmadı.

Ölçüt (SPEC 09, değişmez): kutu boşluğu g = ‖max(0, lo_b − hi_a, lo_a − hi_b)‖ (eksen başına ayrılma
vektörünün
boyu); çift aday ⇔ g < esik_c veya g ≤ tol_d. Aday kümesi sort-and-sweep ile aynı, sıralı (i < j).
Başvuru: aşağıdaki kaba (her çift) tarama; tamsayı koordinatlı kutularda g tam olarak eşiğe eşit olabilir.

"Uzun mil üstünde n halka": mil ekseni z, mil kutusu [−10, 10]² × [0, 5n]; k. halka [−20, 20]² × [5k − 4.5,
5k − 0.5]
(k = 1..n). Halkaların x aralığı aynı → x'te sort-and-sweep her çifti dener (O(n²)); komşu halkalar arası g
= 1.
Beklenen: esik_c ≤ 1 iken yalnız (mil, halka) çiftleri; esik_c > 1 iken ek olarak komşu halka çiftleri.
"""

from __future__ import annotations

import time

import numpy as np
import pytest

from assy.bvh import Bvh
from assy.girisim import check
from assy.model import AssyError, Node
from tests.assy.test_girisim import kutu, satirlar


def _g(lo_a, hi_a, lo_b, hi_b) -> np.ndarray:
    return np.linalg.norm(np.maximum(0.0, np.maximum(lo_b - hi_a, lo_a - hi_b)), axis=-1)


def kaba(boxes, esik_c: float, tol_d: float) -> list[tuple[int, int]]:
    lo = np.array([b[0] for b in boxes], dtype=float)
    hi = np.array([b[1] for b in boxes], dtype=float)
    ciftler = []
    for i in range(len(boxes) - 1):
        g = _g(lo[i], hi[i], lo[i + 1 :], hi[i + 1 :])
        for j in np.nonzero((g < esik_c) | (g <= tol_d))[0]:
            ciftler.append((i, i + 1 + int(j)))
    return sorted(ciftler)


def rastgele_kutular(n: int, seed: int, tamsayi: bool = False):
    rng = np.random.default_rng(seed)
    if tamsayi:
        lo = rng.integers(0, 30, size=(n, 3)).astype(float)
        hi = lo + rng.integers(1, 6, size=(n, 3))
    else:
        L = 10.0 * n ** (1 / 3)  # yoğunluk n'den bağımsız
        lo = rng.uniform(0, L, size=(n, 3))
        hi = lo + rng.uniform(0.5, 8.0, size=(n, 3))
    return [(lo[i], hi[i]) for i in range(n)]


def mil_halka(n: int):
    boxes = [(np.array([-10.0, -10.0, 0.0]), np.array([10.0, 10.0, 5.0 * n]))]
    for k in range(1, n + 1):
        boxes.append((np.array([-20.0, -20.0, 5.0 * k - 4.5]), np.array([20.0, 20.0, 5.0 * k - 0.5])))
    return boxes


def _pairs(boxes, esik_c, tol_d):
    p = Bvh.build(boxes).pairs(esik_c, tol_d)
    return [(int(i), int(j)) for i, j in p]


# ------------------------------------------------------------------ K5


@pytest.mark.parametrize("esik_c", [0.0, 0.5, 3.0])
@pytest.mark.parametrize(("n", "seed"), [(10, 1), (100, 2), (1000, 3)])
def test_K5_rastgele_kutular(n, seed, esik_c):
    boxes = rastgele_kutular(n, seed)
    beklenen = kaba(boxes, esik_c, 1e-6)
    assert len(beklenen) > 0 or n == 10
    assert _pairs(boxes, esik_c, 1e-6) == beklenen


@pytest.mark.parametrize(("esik_c", "tol_d"), [(0.0, 0.0), (1.0, 0.0), (0.0, 1.0), (2.0, 1.0), (1.0, 1e-6)])
@pytest.mark.parametrize("n", [10, 100, 1000])
def test_K5_tamsayi_kutular_esik_sinirlari(n, esik_c, tol_d):
    """Tamsayı koordinatlar: g = 0, 1, √2, 2 ... tam olarak eşiğe eşit çiftler (g = esik_c dışarıda, g =
    tol_d içeride)."""
    boxes = rastgele_kutular(n, 100 + n, tamsayi=True)
    assert _pairs(boxes, esik_c, tol_d) == kaba(boxes, esik_c, tol_d)


@pytest.mark.parametrize("n", [10, 100, 1000])
def test_K5_esige_tam_esit_bosluk(n):
    """g = esik_c olan çiftler aday değil, g = tol_d olanlar aday (rastgele tamsayı kutularda her iki durum
    var)."""
    boxes = rastgele_kutular(n, 100 + n, tamsayi=True)
    lo = np.array([b[0] for b in boxes])
    hi = np.array([b[1] for b in boxes])
    g1 = [(i, j) for i, j in kaba(boxes, 2.0, 0.0) if _g(lo[i], hi[i], lo[j], hi[j]) == 1.0]
    if n >= 100:
        assert g1
    sonuc = set(_pairs(boxes, 1.0, 0.0))
    assert not sonuc & set(g1)
    assert set(g1) <= set(_pairs(boxes, 0.0, 1.0))


@pytest.mark.parametrize(
    ("esik_c", "tol_d", "komsu"),
    [(0.5, 1e-6, False), (1.0, 1e-6, False), (1.0, 1.0, True), (1.5, 1e-6, True)],
)
def test_K5_uzun_mil_500_halka(esik_c, tol_d, komsu):
    n = 500
    boxes = mil_halka(n)
    beklenen = [(0, k) for k in range(1, n + 1)]
    if komsu:
        beklenen += [(k, k + 1) for k in range(1, n)]
    beklenen.sort()
    assert kaba(boxes, esik_c, tol_d) == beklenen
    assert _pairs(boxes, esik_c, tol_d) == beklenen


def test_K5_bos_ve_tek_kutu():
    assert _pairs(rastgele_kutular(1, 5), 1.0, 1e-6) == []
    assert _pairs(rastgele_kutular(2, 5)[:1] * 2, 0.0, 0.0) == [(0, 1)]  # aynı kutu iki kez


def test_K5_ozdes_kutular():
    """Birçok özdeş kutu (medyan bölmesinde eşit merkezler): her çift aday."""
    b = (np.zeros(3), np.ones(3))
    assert _pairs([b] * 40, 0.0, 0.0) == [(i, j) for i in range(40) for j in range(i + 1, 40)]


def test_K5_tuple_ve_liste_girdisi():
    boxes = [((0, 0, 0), (1, 1, 1)), ([1.5, 0, 0], [2, 1, 1]), ((10, 10, 10), (11, 11, 11))]
    assert _pairs(boxes, 1.0, 1e-6) == [(0, 1)]


def _montaj(n: int, seed: int):
    """Tamsayı koordinatlı n kutuluk düz montaj (SPEC 09 sahte kutularıyla)."""
    boxes = rastgele_kutular(n, seed, tamsayi=True)
    parts = {f"p{i}": kutu(lo, hi, f"p{i}") for i, (lo, hi) in enumerate(boxes)}
    root = Node("m", children=[Node(f"p{i}", part=f"p{i}") for i in range(n)])
    return root, parts


@pytest.mark.parametrize("clearance", [0.0, 1.0, 2.5])
def test_K5_check_bvh_sweep_ayni(clearance):
    root, parts = _montaj(80, 7)
    a = check(root, parts, clearance=clearance, broadphase="bvh")
    b = check(root, parts, clearance=clearance, broadphase="sweep")
    assert satirlar(a) == satirlar(b)
    assert len(a) > 0
    for ca, cb in zip(a, b, strict=True):
        assert ca.volume == cb.volume and ca.distance == cb.distance


def test_K5_check_varsayilan_bvh():
    root, parts = _montaj(60, 8)
    assert satirlar(check(root, parts, clearance=1.0)) == satirlar(
        check(root, parts, clearance=1.0, broadphase="bvh")
    )


# ------------------------------------------------------------------ K6


def _sweep_ref(boxes, esik_c: float, tol_d: float) -> list[tuple[int, int]]:
    """SPEC 09 sort-and-sweep (x ekseni): x'e göre sıralı, x boşluğu eşiği aşınca iç döngü kesilir."""
    sira = sorted(range(len(boxes)), key=lambda i: boxes[i][0][0])
    ciftler = []
    for s, i in enumerate(sira):
        lo_i, hi_i = boxes[i]
        for j in sira[s + 1 :]:
            lo_j, hi_j = boxes[j]
            gx = lo_j[0] - hi_i[0]
            if gx >= esik_c and gx > tol_d:
                break
            g = float(np.linalg.norm(np.maximum(0.0, np.maximum(lo_j - hi_i, lo_i - hi_j))))
            if g < esik_c or g <= tol_d:
                ciftler.append((min(i, j), max(i, j)))
    return sorted(ciftler)


@pytest.mark.slow
def test_K6_uzun_mil_2000_halka_10_kat_hizli():
    """Aday bulma süresi (ağaç kurulumu dahil) sort-and-sweep'in en az 10 katı hızlı, aynı makinede aynı
    süreçte."""
    boxes = mil_halka(2000)
    t0 = time.perf_counter()
    p_bvh = Bvh.build(boxes).pairs(0.5, 1e-6)
    t_bvh = time.perf_counter() - t0
    t0 = time.perf_counter()
    p_sweep = _sweep_ref(boxes, 0.5, 1e-6)
    t_sweep = time.perf_counter() - t0
    print(f"\n[SPEC 53 K6] BVH {t_bvh:.3f} s, sort-and-sweep {t_sweep:.3f} s, oran {t_sweep / t_bvh:.1f}")
    assert [(int(i), int(j)) for i, j in p_bvh] == p_sweep == [(0, k) for k in range(1, 2001)]
    assert t_sweep >= 10.0 * t_bvh


@pytest.mark.slow
def test_K6_check_uzun_mil_bvh_sweep_ayni():
    """2000 halkalı montajda check'in iki yolu aynı satırları verir."""
    boxes = mil_halka(2000)
    parts = {f"p{i}": kutu(lo, hi, f"p{i}") for i, (lo, hi) in enumerate(boxes)}
    root = Node("m", children=[Node(f"p{i}", part=f"p{i}") for i in range(len(boxes))])
    a = check(root, parts, clearance=0.5, broadphase="bvh")
    b = check(root, parts, clearance=0.5, broadphase="sweep")
    assert satirlar(a) == satirlar(b)
    assert len(a) == 2000


# ------------------------------------------------------------------ K9


@pytest.mark.parametrize("bp", ["", "BVH", "kaba", None])
def test_K9_bilinmeyen_broadphase(bp):
    root, parts = _montaj(5, 9)
    with pytest.raises(AssyError):
        check(root, parts, broadphase=bp)
