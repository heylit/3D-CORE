"""SPEC 53 K4 — hız: B1 ve B2, 0.1 mm z-map, her biri < 10 s (CI çalıştırıcısında).

Testler SPEC 53 "Ölçüt programları" bölümünden yazıldı; cam.sim kodu okunmadı.
Süre: simulate(...) çağrısının duvar saati, aynı süreçte ikinci çalıştırma (ilk çalıştırma ısınma, sayılmaz).
Ölçülen süre test çıktısına yazılır (pytest -s ile görünür). Başlangıç çizgisi (eski yol: block = None,
merge = False) aynı ızgarada çok uzun sürdüğü için yalnız SPEC53_BASLANGIC=1 ortam değişkeniyle ölçülüp
yazılır; ölçülmüş değeri
durum/53-performans.md'dedir.
"""

from __future__ import annotations

import os
import time

import pytest

from cam.sim import simulate
from cam.sim.blok import merge_collinear
from tests.cam import benchref

HUCRE = 0.1
HEDEF = 10.0


def _sure(yol, **kw) -> tuple[float, object]:
    t0 = time.perf_counter()
    res = simulate([yol], benchref.STOK, cell=HUCRE, **kw)
    return time.perf_counter() - t0, res


def _olc(ad: str, yol) -> None:
    gruplar = merge_collinear(yol.moves, start=yol.start)
    print(f"\n[SPEC 53 K4] {ad}: {len(yol.moves)} hareket, birleştirmeden sonra {len(gruplar)} süpürme")
    _sure(yol)  # ısınma
    t, res = _sure(yol)
    assert res.zmap.z.shape == (2000, 2000)
    print(f"[SPEC 53 K4] {ad}: 0.1 mm z-map süresi {t:.2f} s (hedef < {HEDEF:.0f} s)")
    if os.environ.get("SPEC53_BASLANGIC") == "1":
        t_eski, _ = _sure(yol, block=None, merge=False)
        print(f"[SPEC 53 K4] {ad}: başlangıç çizgisi (block=None, merge=False) {t_eski:.2f} s")
    assert t < HEDEF


@pytest.mark.slow
def test_K4_B1_hiz():
    _olc("B1", benchref.b1())


@pytest.mark.slow
def test_K4_B2_hiz():
    _olc("B2", benchref.b2())
