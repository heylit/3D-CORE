"""SPEC 05 K16 — olay listesi (SPEC 24 `sim` ikili dizisi) ve adım hacimleri.

Testler SPEC 05 "Olay listesi" ve "Takım yükü" bölümlerinden yazıldı; cam.sim kodu okunmadı.

Kaynaklar (SPEC 05):
- Olay (c, k, z_sonra), c = j·nx + i, adım k hücreyi alçaltırsa; (c, k) sırasıyla,
  CSR ofsetleri uzunluk nx·ny + 1.
- k anındaki yüzey: her hücrede k' ≤ k olan son olayın z'si, olay yoksa zmax;
  ilk k adımın ayrıca simülasyonuyla birebir aynı.
- ΔV_k = Σ (z_önce − z_sonra)·dx·dy; toplamı removed_volume = stok − son hacim.
"""

from __future__ import annotations

import functools

import numpy as np
import pytest

from cam.model import Toolpath
from cam.sim import simulate
from tests.cam.simref import RANDOM_STOCK, flat, random_program

CELL = 1.0


@functools.cache
def _program() -> Toolpath:
    return random_program(flat(D=6.0, Lf=30.0), n=50)


@functools.cache
def _sonuc():
    # fixture değil: simülasyon test gövdesinde çağrılsın (uygulanmamış kod "uygulanmamış" sayılsın)
    return simulate([_program()], RANDOM_STOCK, cell=CELL)


def _ilk_k(program: Toolpath, k: int) -> Toolpath:
    return Toolpath(program.name, program.tool, program.start, program.moves[:k], program.rpm)


def test_K16_zmap_at_ayri_simulasyonla_birebir():
    program = _program()
    sonuc = _sonuc()
    n = len(program.moves)
    assert len(sonuc.steps) == n
    z0 = sonuc.zmap_at(0)
    assert np.array_equal(z0, np.full(sonuc.zmap.z.shape, RANDOM_STOCK.zmax))
    for k in range(1, n + 1):
        ayri = simulate([_ilk_k(program, k)], RANDOM_STOCK, cell=CELL).zmap.z
        zk = np.asarray(sonuc.zmap_at(k))
        assert np.array_equal(zk, ayri), f"k = {k}"
        assert np.array_equal(zk.astype(np.float32), ayri.astype(np.float32)), f"k = {k}"
    assert np.array_equal(sonuc.zmap_at(n), sonuc.zmap.z)


def test_K16_csr_tutarli():
    sonuc = _sonuc()
    nx, ny = sonuc.zmap.nx, sonuc.zmap.ny
    c, k, z, off = sonuc.event_cell, sonuc.event_k, sonuc.event_z, sonuc.offsets
    assert c.dtype == np.int32 and k.dtype == np.int32
    assert z.dtype == np.float64 and off.dtype == np.int64
    assert len(c) == len(k) == len(z) > 0
    assert off.shape == (nx * ny + 1,)
    assert off[0] == 0 and off[-1] == len(c)
    assert np.all(np.diff(off) >= 0)
    n = len(sonuc.steps)
    for cell in range(nx * ny):
        a, b = off[cell], off[cell + 1]
        assert np.all(c[a:b] == cell)
        kk = k[a:b]
        assert np.all(np.diff(kk) > 0)  # (c, k) sıralı, (c, k) başına tek olay
        assert np.all((kk >= 1) & (kk <= n))
        assert np.all(np.diff(z[a:b]) < 0)  # her olay hücreyi alçaltır
    # olayın z'si o anki yüzey: z_sonra
    for e in range(0, len(c), max(1, len(c) // 200)):
        j, i = divmod(int(c[e]), nx)
        assert sonuc.zmap_at(int(k[e]))[j, i] == z[e]


def test_K16_adim_hacimleri():
    sonuc = _sonuc()
    dxdy = sonuc.zmap.dx * sonuc.zmap.dy
    toplam = sum(s.removed for s in sonuc.steps)
    assert toplam == pytest.approx(sonuc.removed_volume, rel=1e-9)
    assert sonuc.removed_volume == pytest.approx(RANDOM_STOCK.volume - sonuc.zmap.volume(), rel=1e-9)
    onceki = sonuc.zmap_at(0)
    for s in sonuc.steps:
        sonraki = sonuc.zmap_at(s.k)
        assert s.removed >= 0
        assert s.removed == pytest.approx(float(np.sum(onceki - sonraki)) * dxdy, rel=1e-9, abs=1e-9)
        onceki = sonraki


def test_K16_adim_indeksi_ve_noktalar():
    program = _program()
    sonuc = _sonuc()
    assert [s.k for s in sonuc.steps] == list(range(1, len(program.moves) + 1))
    assert all(s.op == 0 and not s.link for s in sonuc.steps)
    P = sonuc.points()
    assert P.shape == (len(program.moves) + 1, 3)
    np.testing.assert_array_equal(P, program.points())
    assert sonuc.start == pytest.approx(program.start)
    for s, m in zip(sonuc.steps, program.moves, strict=True):
        assert s.type is m.type and s.end == m.end
