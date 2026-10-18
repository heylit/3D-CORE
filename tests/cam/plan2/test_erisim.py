"""SPEC 57 §2 — cam/plan2/erisim.py: aday yönler ve erişilebilir özellikler (K3). OCCT gerektirir.

Testler yalnızca SPEC 57 metninden ve iskeletteki imzalardan yazıldı; gövdeler okunmadı.
Aday yön `d` dış yöndür (takım `d`'den gelir): düzlemsel yüzde dış normal, delikte takım ekseni
= −`Hole.axis`.

K3 parçası: 100 × 60 × 40 blok; +X üst kenarında iki pah yüzü, y ∈ [0, 30]'da normali +Z'den +X'e
30°, y ∈ [30, 60]'ta 30.3° (aralarındaki dar üçgen yüz ±Y yönünde, ana yönle kümelenir); üst yüzden
eğik Ø8 boydan delik, delme yönü (0, sin 20°, −cos 20°) → aday (0, −sin 20°, cos 20°).
Beklenen: ang_tol = 0.5° → 6 ana yön + 1 pah (iki yüz tek küme) + 1 delik = 8; ang_tol = 0.1° → 9.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

pytest.importorskip("build123d", reason='build123d kurulu değil (pip install -e ".[cad]")')

import build123d as bd  # noqa: E402

from cam.features import Features  # noqa: E402
from cam.model import Stock  # noqa: E402
from cam.plan2.erisim import accessible, candidate_directions  # noqa: E402
from geometry.features import block, hole, pocket  # noqa: E402
from geometry.holes import inclined_hole  # noqa: E402
from geometry.part import Part  # noqa: E402

pytestmark = pytest.mark.occt

A20 = math.radians(20.0)
ANA = [np.array(v, dtype=float) for v in np.vstack([np.eye(3), -np.eye(3)])]


def _pah_normali(derece: float) -> np.ndarray:
    a = math.radians(derece)
    return np.array([math.sin(a), 0.0, math.cos(a)])


def _pah_kesici(derece: float, y0: float, y1: float):
    """+X üst kenarından, normali _pah_normali(derece) olan düzlemin dışını kesen kutu."""
    kutu = bd.Box(400, y1 - y0, 400, align=(bd.Align.CENTER, bd.Align.MIN, bd.Align.MIN))
    return bd.Pos(90, y0, 40) * bd.Rot(0, derece, 0) * kutu


def k3_parcasi() -> Part:
    shape = block(100, 60, 40).shape - _pah_kesici(30.0, -10, 30) - _pah_kesici(30.3, 30, 70)
    (solid,) = shape.solids()
    p = Part(solid, name="k3")
    n = np.array([0.0, math.sin(A20), -math.cos(A20)])
    return inclined_hole(p, np.array([30.0, 20.0, 40.0]), n, 8.0)


def _aci(u, v) -> float:
    u, v = np.asarray(u, dtype=float), np.asarray(v, dtype=float)
    c = float(np.dot(u, v) / (np.linalg.norm(u) * np.linalg.norm(v)))
    return math.degrees(math.acos(max(-1.0, min(1.0, c))))


def _eslesen(D, v, tol=0.5) -> int:
    return sum(1 for d in D if _aci(d, v) <= tol)


def test_k3_aday_yonler():
    D = candidate_directions(k3_parcasi())
    assert isinstance(D, tuple)
    for d in D:
        assert np.asarray(d).shape == (3,)
        assert float(np.linalg.norm(d)) == pytest.approx(1.0, abs=1e-9)
    assert len(D) == 8
    for v in ANA:
        assert _eslesen(D, v) == 1
    pah = [d for d in D if _aci(d, _pah_normali(30.0)) <= 0.5 and _aci(d, _pah_normali(30.3)) <= 0.5]
    assert len(pah) == 1  # 0.3° farklı iki yüz tek aday
    assert _eslesen(D, np.array([0.0, -math.sin(A20), math.cos(A20)])) == 1


def test_k3_dar_tolerans():
    D = candidate_directions(k3_parcasi(), ang_tol=0.1)
    assert len(D) == 9
    assert _eslesen(D, _pah_normali(30.0), tol=0.1) == 1
    assert _eslesen(D, _pah_normali(30.3), tol=0.1) == 1


def test_duz_blok_alti_yon():
    D = candidate_directions(block(100, 60, 40))
    assert len(D) == 6
    for v in ANA:
        assert _eslesen(D, v, tol=1e-6) == 1


def test_dik_delik_ana_yonle_kumelenir():
    # üstten dik delik: ekseni −Z, aday +Z → ana yönle aynı küme
    D = candidate_directions(hole(block(100, 60, 40), 50, 30, 8))
    assert len(D) == 6


def test_aday_yonler_deterministik():
    p = k3_parcasi()
    a, b = candidate_directions(p), candidate_directions(p)
    assert len(a) == len(b)
    assert all(np.array_equal(np.asarray(x), np.asarray(y)) for x, y in zip(a, b, strict=True))


# ---------------------------------------------------------------- accessible


def _yana_dondur(p: Part) -> Part:
    """Y çevresinde +90°: üst yüz (+Z) +X'e bakar; parça x ∈ [0, 20] olacak şekilde ötelenir."""
    T = np.eye(4)
    T[:3, :3] = [[0.0, 0.0, 1.0], [0.0, 1.0, 0.0], [-1.0, 0.0, 0.0]]
    T[:3, 3] = [0.0, 0.0, 100.0]
    return p.moved(T)


def test_accessible_ustten_cep():
    part = pocket(block(100, 60, 20), 50, 30, 30, 20, 5, r=4)
    stok = Stock(0, 0, 0, 100, 60, 20)
    F = accessible(part, np.array([0.0, 0.0, 1.0]), stok)
    assert isinstance(F, Features)
    assert len(F.pockets) == 1
    alt = accessible(part, np.array([0.0, 0.0, -1.0]), stok)
    assert len(alt.pockets) == 0


def test_accessible_yan_cep():
    part = _yana_dondur(pocket(block(100, 60, 20), 50, 30, 30, 20, 5, r=4))
    lo, hi = part.bbox
    assert lo == pytest.approx([0, 0, 0], abs=1e-6) and hi == pytest.approx([20, 60, 100], abs=1e-6)
    stok = Stock(0, 0, 0, 20, 60, 100)
    assert len(accessible(part, np.array([1.0, 0.0, 0.0]), stok).pockets) == 1
    assert len(accessible(part, np.array([0.0, 0.0, 1.0]), stok).pockets) == 0  # ustten_erisilemez (29)
    assert len(accessible(part, np.array([-1.0, 0.0, 0.0]), stok).pockets) == 0


def test_accessible_egik_delik():
    part = k3_parcasi()
    stok = Stock(0, 0, 0, 100, 60, 40)
    d = np.array([0.0, -math.sin(A20), math.cos(A20)])
    assert sum(h.top_access for h in accessible(part, d, stok).holes) == 1
    ust = accessible(part, np.array([0.0, 0.0, 1.0]), stok)
    assert sum(h.top_access for h in ust.holes) == 0  # 20° eğik: üstten delinemez
