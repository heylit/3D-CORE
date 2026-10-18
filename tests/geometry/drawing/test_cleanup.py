"""SPEC 16 — K1: kenar sınıflama ve temizleme (geometry/drawing/cleanup.py). OCCT gerektirmez.

Testler SPEC 16 "Gizli çizgi kaldırma ve temizleme" bölümünden yazıldı; uygulama gövdeleri okunmadı.
Beklenen boylar elle hesaplanır (aralık birleşimi), `total_length` ayrıca kendi testinde denetlenir.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from geometry.drawing.cleanup import classify, clean_edges, total_length
from geometry.drawing.types import Arc2D, Line2D, Polyline2D

from ._yardim import en_buyuk_ortusme, toplam_boy

TOL = 1e-9


def L(x0, y0, x1, y1, layer="GORUNUR") -> Line2D:
    return Line2D(np.array([x0, y0], float), np.array([x1, y1], float), layer)


def A(cx, cy, r, a0, a1, layer="GORUNUR") -> Arc2D:
    return Arc2D(np.array([cx, cy], float), float(r), float(a0), float(a1), layer)


def _cember_ornekleri(c, r, a0, a1, n=33) -> np.ndarray:
    t = np.radians(np.linspace(a0, a1, n))
    return np.column_stack([c[0] + r * np.cos(t), c[1] + r * np.sin(t)])


def _aci_farki(a, b) -> float:
    """İki açının 360 modunda farkı, [0, 180]."""
    d = (a - b) % 360.0
    return min(d, 360.0 - d)


# --- classify ---------------------------------------------------------------------------------------


def test_classify_dogru():
    P = np.column_stack([np.linspace(1.0, 11.0, 9), np.linspace(2.0, 7.0, 9)])
    e = classify(P)
    assert isinstance(e, Line2D)
    uclar = {tuple(np.round(e.p0, 9)), tuple(np.round(e.p1, 9))}
    assert uclar == {(1.0, 2.0), (11.0, 7.0)}


def test_classify_dejenere_bspline_dogru():
    """Doğrusal ama düzensiz aralıklı örnekler (dejenere B-spline) de Line2D."""
    s = np.array([0.0, 0.01, 0.05, 0.2, 0.5, 0.51, 0.9, 1.0])
    p0, p1 = np.array([-3.0, 4.0]), np.array([17.0, -6.0])
    P = p0 + s[:, None] * (p1 - p0)
    e = classify(P)
    assert isinstance(e, Line2D)
    for q in (p0, p1):
        assert min(np.linalg.norm(e.p0 - q), np.linalg.norm(e.p1 - q)) < TOL


def test_classify_tam_cember():
    """Kapalı örnek dizisi (ilk = son) çember üzerinde → tarama açısı 360° olan Arc2D."""
    c, r = np.array([20.0, 25.0]), 5.0
    P = _cember_ornekleri(c, r, 0.0, 360.0, n=65)
    P[-1] = P[0]
    e = classify(P)
    assert isinstance(e, Arc2D)
    assert np.linalg.norm(np.asarray(e.c) - c) < 1e-9
    assert e.r == pytest.approx(r, abs=1e-9)
    assert e.a1 - e.a0 == pytest.approx(360.0, abs=1e-9)


def test_classify_yay():
    c, r = np.array([-4.0, 3.0]), 12.5
    P = _cember_ornekleri(c, r, 30.0, 120.0)
    e = classify(P)
    assert isinstance(e, Arc2D)
    assert np.linalg.norm(np.asarray(e.c) - c) < 1e-9
    assert e.r == pytest.approx(r, abs=1e-9)
    assert e.a1 - e.a0 == pytest.approx(90.0, abs=1e-7)
    assert _aci_farki(e.a0, 30.0) < 1e-7
    assert _aci_farki(e.a1, 120.0) < 1e-7


def test_classify_egri_polyline():
    """Ne doğru ne çember olan eğri (parabol) → Polyline2D; uçlar korunur."""
    x = np.linspace(0.0, 10.0, 41)
    P = np.column_stack([x, 0.05 * x**2])
    e = classify(P)
    assert isinstance(e, Polyline2D)
    Q = np.asarray(e.P, float)
    assert Q.ndim == 2 and Q.shape[1] == 2 and len(Q) >= 2
    for q in (P[0], P[-1]):
        assert min(np.linalg.norm(Q[0] - q), np.linalg.norm(Q[-1] - q)) < TOL


def test_classify_tol_disinda_sapma_dogru_degil():
    """Doğrudan 1e-3 mm sapan nokta tol_s = 1e-6'yı aşar: doğru sayılmaz."""
    P = np.array([[0.0, 0.0], [5.0, 1e-3], [10.0, 0.0]])
    assert not isinstance(classify(P), Line2D)


# --- clean_edges: birleştirme ---------------------------------------------------------------------


def test_ortusen_dogrular_birlesir():
    out = clean_edges([L(0, 0, 5, 0), L(3, 0, 10, 0)], [])
    lines = [e for e in out if isinstance(e, Line2D) and e.layer == "GORUNUR"]
    assert len(lines) == 1
    assert toplam_boy(out, "GORUNUR") == pytest.approx(10.0, rel=TOL)
    xs = sorted([lines[0].p0[0], lines[0].p1[0]])
    assert xs == pytest.approx([0.0, 10.0], abs=TOL)


def test_degen_ve_ters_yonlu_dogrular_birlesir():
    """[0,5] ile [10,5] (ters yönlü, 5'te değiyor) tek parça [0,10]."""
    out = clean_edges([L(0, 2, 5, 2), L(10, 2, 5, 2)], [])
    lines = [e for e in out if e.layer == "GORUNUR"]
    assert len(lines) == 1
    assert toplam_boy(out, "GORUNUR") == pytest.approx(10.0, rel=TOL)


def test_egik_dogruda_birlestirme():
    d = np.array([3.0, 4.0]) / 5.0
    p = [np.array([1.0, 1.0]) + s * d for s in (0.0, 4.0, 2.0, 9.0)]
    out = clean_edges([L(*p[0], *p[1]), L(*p[2], *p[3])], [])
    assert len([e for e in out if e.layer == "GORUNUR"]) == 1
    assert toplam_boy(out, "GORUNUR") == pytest.approx(9.0, rel=TOL)


def test_ayrik_dogrular_ayri_kalir():
    out = clean_edges([L(0, 0, 3, 0), L(5, 0, 10, 0)], [])
    assert len([e for e in out if e.layer == "GORUNUR"]) == 2
    assert toplam_boy(out, "GORUNUR") == pytest.approx(8.0, rel=TOL)


def test_paralel_ama_farkli_dogrular_birlesmez():
    """y = 0 ve y = 1e-3 (tol_s'den uzak) iki ayrı doğru."""
    out = clean_edges([L(0, 0, 10, 0), L(0, 1e-3, 10, 1e-3)], [])
    assert len([e for e in out if e.layer == "GORUNUR"]) == 2
    assert toplam_boy(out, "GORUNUR") == pytest.approx(20.0, rel=TOL)


def test_yaylar_birlesir():
    """Aynı merkez / yarıçap: [0°, 90°] ∪ [45°, 180°] = [0°, 180°] → boy π r."""
    r = 4.0
    out = clean_edges([A(1, 2, r, 0, 90), A(1, 2, r, 45, 180)], [])
    arcs = [e for e in out if isinstance(e, Arc2D) and e.layer == "GORUNUR"]
    assert len(arcs) == 1
    assert toplam_boy(out, "GORUNUR") == pytest.approx(math.pi * r, rel=TOL)


def test_yarim_cemberler_tam_cember_olur():
    r = 5.0
    out = clean_edges([A(0, 0, r, 0, 180), A(0, 0, r, 180, 360)], [])
    arcs = [e for e in out if e.layer == "GORUNUR"]
    assert len(arcs) == 1
    assert arcs[0].a1 - arcs[0].a0 == pytest.approx(360.0, abs=1e-9)
    assert toplam_boy(out, "GORUNUR") == pytest.approx(2 * math.pi * r, rel=TOL)


# --- clean_edges: gizli / görünen önceliği ---------------------------------------------------------


def test_gorunen_gizliyi_orter():
    """H = [0,10], V = [2,5] → H ∖ V = [0,2] ∪ [5,10], boy 7."""
    out = clean_edges([L(2, 0, 5, 0)], [L(0, 0, 10, 0, "GIZLI")])
    assert toplam_boy(out, "GORUNUR") == pytest.approx(3.0, rel=TOL)
    assert toplam_boy(out, "GIZLI") == pytest.approx(7.0, rel=TOL)
    assert len([e for e in out if e.layer == "GIZLI"]) == 2


def test_tamamen_ortulen_gizli_kalkar():
    out = clean_edges([L(0, 0, 10, 0)], [L(2, 0, 8, 0, "GIZLI"), L(10, 0, 0, 0, "GIZLI")])
    assert [e for e in out if e.layer == "GIZLI"] == []
    assert toplam_boy(out, "GORUNUR") == pytest.approx(10.0, rel=TOL)


def test_tol_s_den_kisa_gizli_artik_atilir():
    out = clean_edges([L(0, 0, 5, 0)], [L(0, 0, 5 + 1e-7, 0, "GIZLI")])
    assert [e for e in out if e.layer == "GIZLI"] == []


def test_gorunen_yay_gizli_yayi_orter():
    """Görünen tam çember, aynı çember üzerindeki gizli yayı tamamen örter."""
    out = clean_edges([A(3, 3, 2, 0, 360)], [A(3, 3, 2, 10, 100, "GIZLI")])
    assert toplam_boy(out, "GIZLI") == pytest.approx(0.0, abs=1e-9)
    assert toplam_boy(out, "GORUNUR") == pytest.approx(4 * math.pi, rel=TOL)


def test_baska_dogrudaki_gizli_kalir():
    out = clean_edges([L(0, 0, 10, 0)], [L(0, 1, 10, 1, "GIZLI")])
    assert toplam_boy(out, "GIZLI") == pytest.approx(10.0, rel=TOL)


def test_cikti_katmanlari():
    out = clean_edges([L(0, 0, 1, 0)], [L(0, 5, 1, 5, "GIZLI")])
    assert {e.layer for e in out} == {"GORUNUR", "GIZLI"}


def test_cikti_ortusmesiz_karisik_girdi():
    """Karışık girdi: çıktıda hiçbir iki doğru parçası (görünen / gizli fark etmez) örtüşmez.

    Doğru y = 0: V = [0,4] ∪ [3,6] ∪ [8,9], H = [1,10] → V = [0,6] ∪ [8,9] (7), H = [6,8] ∪ [9,10] (3).
    Doğru x = 2: V = [0,1], H = [0,3] ∪ [2,5] → H = [1,5] (4).
    """
    V = [L(0, 0, 4, 0), L(6, 0, 3, 0), L(8, 0, 9, 0), L(2, 0, 2, 1)]
    H = [L(1, 0, 10, 0, "GIZLI"), L(2, 0, 2, 3, "GIZLI"), L(2, 5, 2, 2, "GIZLI")]
    out = clean_edges(V, H)
    assert toplam_boy(out, "GORUNUR") == pytest.approx(7.0 + 1.0, rel=TOL)
    assert toplam_boy(out, "GIZLI") == pytest.approx(3.0 + 4.0, rel=TOL)
    assert en_buyuk_ortusme(out) < 1e-6


# --- total_length ------------------------------------------------------------------------------------


def test_total_length():
    edges = [
        L(0, 0, 3, 4),  # 5
        A(0, 0, 2, 0, 90),  # π
        Polyline2D(np.array([[0.0, 0.0], [1.0, 0.0], [1.0, 2.0]]), "GORUNUR"),  # 3
        L(0, 0, 10, 0, "GIZLI"),
    ]
    assert total_length(edges, "GORUNUR") == pytest.approx(8.0 + math.pi, rel=TOL)
    assert total_length(edges, "GIZLI") == pytest.approx(10.0, rel=TOL)
    assert total_length(edges, "EKSEN") == 0.0
