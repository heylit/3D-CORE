"""SPEC 22 K17 — olay listesi (SPEC 24), adım hacimleri ve `initial` ile parçalı simülasyon.

Testler SPEC 22 "Olay listesi", "Takım yükü" ve "Arayüz" bölümlerinden yazıldı; cam.sim kodu okunmadı.

Kaynaklar (SPEC 22):
- Adım k bir hücrenin aralık listesini değiştirirse olay (i, k, yeni liste); olaylar (i, k) sırasıyla;
  offsets (nz + 1) CSR; event_iv (M, 2), event_iv_off (olay sayısı + 1).
- section_at(k): her hücrede k' ≤ k olan son olayın listesi, yoksa başlangıç; ilk k adımın ayrı
  simülasyonuyla birebir.
- ΔV_k = Σ π(u² − l²)·dz (adımın kaldırdığı); toplamı removed_volume = stok − son hacim (rel 1e-9).
- initial: o haritadan başlar (kopyalanır, değiştirilmez); iki parçada simülasyon tek seferdekiyle aynı.
"""

from __future__ import annotations

import functools
import math

import numpy as np
import pytest

from cam.model import CylinderStock, Move, MoveType, Toolpath
from cam.sim import RadialMap, simulate_lathe
from tests.cam.lsimref import G0, G1, iv_is_valid, lpath, turn_tool

STOK = CylinderStock(D=30.0, zmin=-30.0, zmax=0.0)
CELL = 0.5


def _rastgele_program(n: int = 40, seed: int = 2022) -> Toolpath:
    """Sabit tohumlu rastgele torna programı: G0 / G1 / G2 / G3, x ∈ [4, 20], z ∈ [−25, 4]."""
    rng = np.random.default_rng(seed)
    x, z = 20.0, 5.0
    moves: list[Move] = []
    while len(moves) < n:
        u = rng.random()
        if u < 0.2:  # yay: merkez rastgele, bitiş aynı yarıçapta
            Rr = rng.uniform(2.0, 6.0)
            phi = rng.uniform(0, 2 * math.pi)
            cz, cx = z + Rr * math.cos(phi), x + Rr * math.sin(phi)
            a0 = math.atan2(x - cx, z - cz)
            ccw = rng.random() < 0.5
            a1 = a0 + (1 if ccw else -1) * rng.uniform(0.3, 1.5)
            ez, ex = cz + Rr * math.cos(a1), cx + Rr * math.sin(a1)
            # yay boyunca x ≥ 2 kalsın (eksenden uzak), bölge içinde bitsin
            ts = np.linspace(0, 1, 50)
            xs = cx + Rr * np.sin(a0 + (a1 - a0) * ts)
            if xs.min() < 2.0 or not (4.0 <= ex <= 20.0 and -25.0 <= ez <= 4.0):
                continue
            t = MoveType.ARC_CCW if ccw else MoveType.ARC_CW
            moves.append(Move(t, (ex, 0.0, ez), 0.2, center=(cx, cz)))
            x, z = ex, ez
            continue
        x, z = rng.uniform(4.0, 20.0), rng.uniform(-25.0, 4.0)
        moves.append(G0(x, z) if u < 0.4 else G1(x, z))
    return lpath(turn_tool(), (20.0, 5.0), moves, name="rastgele")


@functools.cache
def _program() -> Toolpath:
    return _rastgele_program()


@functools.cache
def _sonuc():
    # fixture değil: simülasyon test gövdesinde çağrılsın (uygulanmamış kod "uygulanmamış" sayılsın)
    return simulate_lathe([_program()], STOK, cell=CELL)


def _ilk_k(program: Toolpath, k: int) -> Toolpath:
    return Toolpath(
        program.name,
        program.tool,
        program.start,
        program.moves[:k],
        program.rpm,
        program.plane,
        program.feed_mode,
    )


def _harita(rmap: RadialMap) -> list[list[tuple[float, float]]]:
    return [list(rmap.intervals(i)) for i in range(rmap.nz)]


def _ayni(a, b) -> bool:
    if len(a) != len(b):
        return False
    return all(
        np.array_equal(np.asarray(x, float).reshape(-1, 2), np.asarray(y, float).reshape(-1, 2))
        for x, y in zip(a, b, strict=True)
    )


def test_K17_program_gecerli():
    p = _program()
    assert len(p.moves) == 40
    assert any(m.type in (MoveType.ARC_CW, MoveType.ARC_CCW) for m in p.moves)
    sonuc = _sonuc()
    assert len(sonuc.steps) == 40
    assert sonuc.removed_volume > 0


@pytest.mark.slow
def test_K17_section_at_ayri_simulasyonla_birebir():
    program = _program()
    sonuc = _sonuc()
    n = len(program.moves)
    bas = RadialMap.from_stock(STOK, CELL)
    assert _ayni(sonuc.section_at(0), _harita(bas))
    for k in range(1, n + 1):
        ayri = simulate_lathe([_ilk_k(program, k)], STOK, cell=CELL).rmap
        assert _ayni(sonuc.section_at(k), _harita(ayri)), f"k = {k}"
    assert _ayni(sonuc.section_at(n), _harita(sonuc.rmap))


def test_K17_csr_tutarli():
    sonuc = _sonuc()
    nz = sonuc.rmap.nz
    c, k = sonuc.event_cell, sonuc.event_k
    off, ivo, iv = sonuc.offsets, sonuc.event_iv_off, sonuc.event_iv
    assert c.dtype == np.int32 and k.dtype == np.int32
    assert off.dtype == np.int64 and ivo.dtype == np.int64 and iv.dtype == np.float64
    ne = len(c)
    assert ne == len(k) > 0
    assert off.shape == (nz + 1,) and off[0] == 0 and off[-1] == ne
    assert np.all(np.diff(off) >= 0)
    assert ivo.shape == (ne + 1,) and ivo[0] == 0 and ivo[-1] == len(iv)
    assert np.all(np.diff(ivo) >= 0)
    assert iv.ndim == 2 and iv.shape[1] == 2
    n = len(sonuc.steps)
    for cell in range(nz):
        a, b = off[cell], off[cell + 1]
        assert np.all(c[a:b] == cell)
        kk = k[a:b]
        assert np.all(np.diff(kk) > 0)  # (i, k) sıralı, (i, k) başına tek olay
        assert np.all((kk >= 1) & (kk <= n))
    for j in range(ne):
        liste = [tuple(p) for p in iv[ivo[j] : ivo[j + 1]]]
        assert iv_is_valid(liste)
        assert _ayni(sonuc.section_at(int(k[j]))[int(c[j])], liste)


def test_K17_adim_hacimleri():
    sonuc = _sonuc()
    dz = sonuc.rmap.dz
    toplam = sum(s.removed for s in sonuc.steps)
    assert toplam == pytest.approx(sonuc.removed_volume, rel=1e-9)
    assert sonuc.removed_volume == pytest.approx(STOK.volume - sonuc.rmap.volume(), rel=1e-9)

    def hacim(sec) -> float:
        return sum(math.pi * (u * u - lo * lo) * dz for iv in sec for lo, u in iv)

    onceki = hacim(sonuc.section_at(0))
    for s in sonuc.steps:
        sonraki = hacim(sonuc.section_at(s.k))
        assert s.removed >= 0
        assert s.removed == pytest.approx(onceki - sonraki, rel=1e-9, abs=1e-9)
        onceki = sonraki


def test_K17_adim_indeksi_ve_noktalar():
    program = _program()
    sonuc = _sonuc()
    assert [s.k for s in sonuc.steps] == list(range(1, len(program.moves) + 1))
    assert all(s.op == 0 and not s.link for s in sonuc.steps)
    np.testing.assert_array_equal(sonuc.points(), program.points())
    for s, m in zip(sonuc.steps, program.moves, strict=True):
        assert s.type is m.type and s.end == m.end


def test_K17_initial_ile_iki_parca():
    program = _program()
    tek = _sonuc()
    m = 17
    ilk = simulate_lathe([_ilk_k(program, m)], STOK, cell=CELL)
    kalan = Toolpath(
        program.name,
        program.tool,
        program.moves[m - 1].end,
        program.moves[m:],
        program.rpm,
        program.plane,
        program.feed_mode,
    )
    once = _harita(ilk.rmap)
    ikinci = simulate_lathe([kalan], STOK, cell=CELL, initial=ilk.rmap)
    assert _harita(ilk.rmap) == once  # initial kopyalanır, değiştirilmez
    a, b = _harita(ikinci.rmap), _harita(tek.rmap)
    assert len(a) == len(b)
    for x, y in zip(a, b, strict=True):
        assert len(x) == len(y)
        np.testing.assert_allclose(
            np.asarray(x, float).reshape(-1, 2), np.asarray(y, float).reshape(-1, 2), rtol=0, atol=1e-12
        )
    assert ilk.removed_volume + ikinci.removed_volume == pytest.approx(tek.removed_volume, rel=1e-9)
    assert _ayni(ikinci.section_at(0), once)
