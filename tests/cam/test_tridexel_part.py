"""SPEC 43 K8–K9 — parça dexel'i (ışın–üçgen ağı) ve çakma / kalan malzeme.

Testler SPEC 43 "Çarpışma ve çakma" bölümünden yazıldı; cam.sim.raymesh / simulate5 kodu okunmadı.

Kaynaklar:
- Kutu ile ışın: eksen başına dilim (slab) yöntemi, s ∈ ∩ [(lo − o)/u, (hi − o)/u] (Kay–Kajiya).
- Küre: |o + s u − c|² = r² → s = −b ± √(b² − (|o − c|² − r²)), b = (o − c)·u. İkosahedron ağının küreden içe
  sapması ε = r − min (merkezden düzleme uzaklık); eksenden b ≤ r/2 uzak ışında uç sapması
  ≤ ε·r/√(r² − b²) < 1.2ε.
- K9: +X eksenli düz takım (D = 10) x = x_t düzleminde y boyunca geçer: x ∈ [x_t, 40], |z − 15| ≤ 5 bandını
  kaldırır.
  Parça [0, 30]³ (z ≤ 20); hücre 1'de Y/Z ışın merkezleri x = k + ½ → [29.8, 30] katmanını yalnız
  X ışınları görür.
"""

from __future__ import annotations

import numpy as np
import pytest

from cam.dropcutter import TriMesh
from cam.model import CamError, Stock
from cam.sim import part_intervals, simulate5
from tests.cam import tridexref as tr
from tests.cam.simref import flat

# ------------------------------------------------------------------ K8


def _slab(o, u, lo, hi):
    s0, s1 = -np.inf, np.inf
    for k in range(3):
        if abs(u[k]) < 1e-15:
            if not lo[k] <= o[k] <= hi[k]:
                return None
            continue
        a, b = (lo[k] - o[k]) / u[k], (hi[k] - o[k]) / u[k]
        s0, s1 = max(s0, min(a, b)), min(s1, max(a, b))
    return None if s0 > s1 else (s0, s1)


def _pi(mesh, o, u):
    return [(float(a), float(b)) for a, b in part_intervals(mesh, tuple(o), tuple(u))]


KUP = TriMesh(*tr.box_mesh((0.0, 0.0, 0.0), (10.0, 10.0, 10.0)))


def test_K8_kup_rastgele_isinlar():
    rng = np.random.default_rng(8)
    for _ in range(100):
        q = rng.uniform(0.5, 9.5, size=3)
        u = rng.normal(size=3)
        u /= np.linalg.norm(u)
        o = q - 30.0 * u
        beklenen = _slab(o, u, (0, 0, 0), (10, 10, 10))
        got = _pi(KUP, o, u)
        assert len(got) == 1
        assert got[0] == (pytest.approx(beklenen[0], abs=1e-9), pytest.approx(beklenen[1], abs=1e-9))


def test_K8_kup_iskalayan():
    assert _pi(KUP, (20.0, 5.0, -5.0), (0.0, 0.0, 1.0)) == []
    assert _pi(KUP, (-5.0, 5.0, -5.0), (1.0, 0.0, 0.0)) == []


def test_K8_kenara_ve_koseye_denk_gelen_isin():
    """Üst / alt yüz üçgenlerinin ortak köşegeni (0,0)–(10,10) üstündeki ışın ve küpün ana köşegeni
    (iki köşeden geçer): kaydırma ile yine doğru aralık."""
    got = _pi(KUP, (5.0, 5.0, -5.0), (0.0, 0.0, 1.0))
    assert got == [(pytest.approx(5.0, abs=1e-6), pytest.approx(15.0, abs=1e-6))]
    got = _pi(KUP, (2.5, 2.5, -5.0), (0.0, 0.0, 1.0))
    assert got == [(pytest.approx(5.0, abs=1e-6), pytest.approx(15.0, abs=1e-6))]
    u = np.array([1.0, 1.0, 1.0]) / np.sqrt(3.0)
    got = _pi(KUP, (-1.0, -1.0, -1.0), u)
    s3 = np.sqrt(3.0)
    assert got == [(pytest.approx(s3, abs=1e-6), pytest.approx(11 * s3, abs=1e-6))]
    # yan yüz köşegeni üstünden (x = 0 yüzü, (y, z) = (5, 5)) X yönünde
    got = _pi(KUP, (-5.0, 5.0, 5.0), (1.0, 0.0, 0.0))
    assert got == [(pytest.approx(5.0, abs=1e-6), pytest.approx(15.0, abs=1e-6))]


def test_K8_iki_govdeli_ag():
    """İki ayrık kutu: kesişimler sıralanıp çiftlenir → iki aralık."""
    V1, T1 = tr.box_mesh((0.0, 0.0, 0.0), (4.0, 4.0, 4.0))
    V2, T2 = tr.box_mesh((7.0, 0.0, 0.0), (10.0, 4.0, 4.0))
    m = TriMesh(np.vstack([V1, V2]), np.vstack([T1, T2 + len(V1)]))
    got = _pi(m, (-1.0, 1.3, 2.7), (1.0, 0.0, 0.0))
    assert got == [
        (pytest.approx(1.0, abs=1e-9), pytest.approx(5.0, abs=1e-9)),
        (pytest.approx(8.0, abs=1e-9), pytest.approx(11.0, abs=1e-9)),
    ]


def test_K8_kure_agi():
    c = np.array([3.0, -2.0, 5.0])
    r = 10.0
    V, T = tr.icosphere(c, r, 3)
    eps = tr.sagitta(V, T, c, r)
    assert 0 < eps < 0.1
    m = TriMesh(V, T)
    rng = np.random.default_rng(11)
    for _ in range(80):
        u = rng.normal(size=3)
        u /= np.linalg.norm(u)
        # eksenden b ≤ r/2 uzak ışın
        w = rng.normal(size=3)
        w -= (w @ u) * u
        w *= rng.uniform(0, 0.5 * r) / np.linalg.norm(w)
        o = c + w - 25.0 * u
        b = (o - c) @ u
        kok = np.sqrt(b * b - ((o - c) @ (o - c) - r * r))
        s0, s1 = -b - kok, -b + kok
        got = _pi(m, o, u)
        assert len(got) == 1
        g0, g1 = got[0]
        assert s0 - 1e-9 <= g0 <= s0 + 1.2 * eps
        assert s1 - 1.2 * eps <= g1 <= s1 + 1e-9


def test_K8_kapali_olmayan_ag():
    V, T = tr.box_mesh((0.0, 0.0, 0.0), (10.0, 10.0, 10.0))
    m = TriMesh(V, T[1:])  # alt yüzün bir üçgeni eksik
    # eksik üçgenin (0, 2, 1) içinden geçen düşey ışın: tek kesişim
    q = V[[0, 2, 1]].mean(axis=0)
    with pytest.raises(CamError):
        part_intervals(m, (q[0], q[1], -5.0), (0.0, 0.0, 1.0))


# ------------------------------------------------------------------ K9

P_STOK = Stock(0.0, 0.0, 0.0, 40.0, 30.0, 20.0)
PARCA = TriMesh(*tr.box_mesh((0.0, 0.0, 0.0), (30.0, 30.0, 20.0)))


def _yan_yuz_alma(xt: float):
    """3+2: eksen +X (yatay), uç düzlemi x = x_t; y = −10 → 40 boyunca z = 15'te."""
    tool = flat(D=10.0, Lf=20.0)
    return tr.tilted_path(tool, (1.0, 0.0, 0.0), [(xt, -10.0, 15.0), (xt, 40.0, 15.0)])


def test_K9_02mm_cakma():
    res = simulate5([_yan_yuz_alma(29.8)], P_STOK, cell=1.0, part=PARCA)
    k = [c for c in res.collisions if c.kind == "cakma"]
    assert len(k) == 1
    assert (k[0].k, k[0].op) == (1, 0)
    assert k[0].depth == pytest.approx(0.2, abs=1e-6)


def test_K9_teget_kayit_yok_ve_hacimler():
    res = simulate5([_yan_yuz_alma(30.0)], P_STOK, cell=1.0, part=PARCA)
    assert [c for c in res.collisions if c.kind == "cakma"] == []
    # kalan = (stok ∖ parça) − kaldırılan = 10·30·20 − 10·30·10 = 3000; her ailede kesin
    assert res.rest_volume() == pytest.approx(3000.0, rel=1e-9)
    assert res.gouge_volume() == pytest.approx(0.0, abs=1e-9)


def test_K9_2mm_cakma_hacmi():
    """x_t = 28: parçadan 2 × 30 × 10 = 600 mm³ kesilir (ızgaraya hizalı: her aile kesin)."""
    res = simulate5([_yan_yuz_alma(28.0)], P_STOK, cell=1.0, part=PARCA)
    assert res.gouge_volume() == pytest.approx(600.0, rel=1e-9)
    assert res.rest_volume() == pytest.approx(3000.0, rel=1e-9)
    assert any(c.kind == "cakma" and c.k == 1 for c in res.collisions)


def test_K9_islenmemis():
    """Havada geçen yol: kalan = stok − parça = 6000, çakma 0."""
    tool = flat(D=10.0, Lf=20.0)
    yol = tr.tilted_path(tool, (1.0, 0.0, 0.0), [(60.0, -10.0, 15.0), (60.0, 40.0, 15.0)])
    res = simulate5([yol], P_STOK, cell=1.0, part=PARCA)
    assert res.rest_volume() == pytest.approx(6000.0, rel=1e-9)
    assert res.gouge_volume() == pytest.approx(0.0, abs=1e-9)


def test_K9_parca_yoksa_hacim_hatasi():
    res = simulate5([_yan_yuz_alma(30.0)], P_STOK, cell=1.0)
    with pytest.raises(CamError):
        res.rest_volume()
    with pytest.raises(CamError):
        res.gouge_volume()
