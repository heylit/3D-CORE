"""SPEC 62 — K7 (sarma = düz simülasyon), K8'in sarma kısmı ve K9'un /sarma ucu (tezgah/sarma.py).

Başvuru: `cam.sim.simulate(**girdi).zmap_at(k)` (SPEC 05; durum/62-tezgah-deneyim.md arayüz notu), bit
düzeyinde (`np.array_equal`, dtype dahil). Uygulama gövdeleri okunmadı.

Flanş işi: SPEC 24 `ornek_is("flans-plakasi")` (120 × 80 stok, hücre 1 mm → 120 × 80 z-haritası). Bu işte adım
sayısı n varsayılan N = 200'den küçüktür; N−1, N, N+1 sınırlarının sınanması için testler N'yi küçük verir
(arayüz `Sarici(girdi, N=...)`), varsayılan N ayrıca sınanır. Kare boyu nx·ny·8 bayt.
"""

from __future__ import annotations

import os
import time
from functools import cache

import numpy as np
import pytest

pytest.importorskip("cam.sim", reason="SPEC 05 (cam.sim) yok")

from cam.sim import simulate  # noqa: E402
from core.model import ModelError  # noqa: E402
from tezgah.isler import ornek_is  # noqa: E402
from tezgah.sarma import Sarici  # noqa: E402

HUCRE = 1.0


def girdi() -> dict:
    t = ornek_is("flans-plakasi")
    return {"ops": [i.op for i in t.islemler], "stock": t.kurulum.stock, "cell": HUCRE, "dialect": t.dialect}


@cache
def _basvuru():
    return simulate(**girdi())


def _n() -> int:
    return len(_basvuru().steps)


def _ayni(a: np.ndarray, b: np.ndarray) -> bool:
    return a.dtype == b.dtype and a.shape == b.shape and bool(np.array_equal(a, b))


def test_is_yeterince_uzun():
    """Ön koşul (test verisi): N = 50 ile en az üç kare olacak kadar adım var."""
    assert _n() > 2 * 50 + 1


def test_n_ve_kareler_varsayilan():
    s = Sarici(girdi())
    n = _n()
    assert s.n == n
    assert s.N == 200
    assert s.kareler[0] == 0
    assert all(k % s.N == 0 and 0 <= k <= n for k in s.kareler)
    assert s.kareler == sorted(set(s.kareler))


@pytest.mark.parametrize("N", [50, 64])
def test_kareler_N_katlari(N):
    s = Sarici(girdi(), N=N)
    n = _n()
    assert s.N == N
    assert s.kareler == list(range(0, n + 1, N))[: len(s.kareler)]
    assert s.kareler[-1] > n - N


@pytest.mark.parametrize("N", [50, 200])
def test_k7_ozel_adimlar(N):
    """k ∈ {0, 1, N−1, N, N+1, n/2, n} (n'yi aşanlar atlanır)."""
    s = Sarici(girdi(), N=N)
    ref = _basvuru()
    n = _n()
    for k in sorted({0, 1, N - 1, N, N + 1, n // 2, n}):
        if k > n:
            continue
        z = s.durum(k)
        assert z.dtype == np.float64
        assert _ayni(z, ref.zmap_at(k)), f"k = {k}"


def test_k7_ileri_geri_rastgele():
    """İleri-geri karışık 100 rastgele k (sabit tohum): her biri düz simülasyonla bit düzeyinde aynı."""
    s = Sarici(girdi(), N=50)
    ref = _basvuru()
    rng = np.random.default_rng(62)
    ks = rng.integers(0, _n() + 1, size=100)
    assert np.any(np.diff(ks) < 0) and np.any(np.diff(ks) > 0)
    for k in ks:
        assert _ayni(s.durum(int(k)), ref.zmap_at(int(k))), f"k = {k}"


def test_durum_kopya_doner():
    s = Sarici(girdi(), N=50)
    k = 60
    z = s.durum(k)
    z[...] = -1e9
    assert _ayni(s.durum(k), _basvuru().zmap_at(k))
    assert _ayni(s.durum(0), _basvuru().zmap_at(0))


def test_k7_bellek_kucukse_N_buyur_sonuc_degismez():
    """Bütçe 3.5 kare: N = 16 ile kare sayısı fazla → N ikiye katlanır; sonuç aynı."""
    ref = _basvuru()
    g = ref.zmap
    kare_mb = g.nx * g.ny * 8 / 2**20
    butce = 3.5 * kare_mb
    N0 = 16
    s = Sarici(girdi(), N=N0, bellek_mb=butce)
    assert s.N > N0
    assert s.N % N0 == 0 and (s.N // N0) & (s.N // N0 - 1) == 0  # N0 · 2^j
    assert len(s.kareler) * kare_mb <= butce
    for k in (0, 1, s.N - 1, s.N, s.N + 1, _n() // 2, _n()):
        if k <= _n():
            assert _ayni(s.durum(k), ref.zmap_at(k)), f"k = {k}"


@pytest.mark.parametrize("k", [-1, "n+1"])
def test_gecersiz_k_hata(k):
    s = Sarici(girdi(), N=50)
    if k == "n+1":
        k = _n() + 1
    with pytest.raises(ModelError):
        s.durum(k)


# --- K8 (sarma kısmı): gecikme bütçesi --------------------------------------------------------------


@pytest.mark.slow
def test_k8_durum_gecikmesi():
    """Rastgele k için durum(k) ≤ 100 ms; CI'da yalnız ölçülüp yazılır, yerelde eşik zorunlu."""
    s = Sarici(girdi())
    rng = np.random.default_rng(8)
    sureler = []
    for k in rng.integers(0, _n() + 1, size=30):
        t0 = time.perf_counter()
        s.durum(int(k))
        sureler.append(time.perf_counter() - t0)
    en_kotu = max(sureler)
    print(f"SPEC 62 K8: Sarici.durum en kötü {en_kotu * 1e3:.1f} ms (30 rastgele k)")
    if not os.environ.get("CI"):
        assert en_kotu <= 0.100


# --- K9: GET /api/ekran/komut/sarma/{is}/{k} ---------------------------------------------------------


@pytest.fixture
def istemci():
    pytest.importorskip("fastapi")
    pytest.importorskip("httpx")
    from fastapi.testclient import TestClient

    from tezgah.sunucu import uygulama

    return TestClient(uygulama(dist=None))


@pytest.mark.parametrize("k", [0, 1, "n/2", "n"])
def test_k9_sarma_ucu(istemci, k):
    """SPEC 24 sim_ikili biçimi: kopru.sim_yuzey(veri, k) = simulate(...).zmap_at(k), float32."""
    from tezgah.kopru import sim_yuzey

    n = _n()
    k = {"n/2": n // 2, "n": n}.get(k, k)
    r = istemci.get(f"/api/ekran/komut/sarma/flans-plakasi/{k}")
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith("application/octet-stream")
    z = sim_yuzey(r.content, k)
    beklenen = _basvuru().zmap_at(k).astype(np.float32)
    assert z.dtype == np.float32 and np.array_equal(z, beklenen)


@pytest.mark.parametrize(
    "yol, kod", [("flans-plakasi/-1", 422), ("flans-plakasi/n+1", 422), ("yok-boyle-is/0", 404)]
)
def test_k9_sarma_ucu_hata(istemci, yol, kod):
    """Bilinmeyen iş 404, k ∉ 0..n 422."""
    yol = yol.replace("n+1", str(_n() + 1))
    r = istemci.get(f"/api/ekran/komut/sarma/{yol}")
    assert r.status_code == kod, r.text
