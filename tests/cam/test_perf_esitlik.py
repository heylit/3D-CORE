"""SPEC 53 K1–K3, K9 — bloklu simülasyon ve hareket birleştirme eski yolla aynı sonucu veriyor.

Testler SPEC 53 "Bloklu z-map / dexel güncellemesi" bölümünden ve arayüzden yazıldı; cam.sim kodu okunmadı.

Kaynaklar (SPEC 53):
- Karo işleme yalnız sıra ve gruplamayı değiştirir; min birleşmeli ve değişmeli → birleştirme kapalıyken z-map
  bit düzeyinde aynı (np.array_equal).
- Birleştirme: takım ⊕ [p₀, p₂] = (takım ⊕ [p₀, p₁]) ∪ (takım ⊕ [p₁, p₂]) (p₁ doğru üzerinde ve aynı yönde) →
  aynı küme; sayısal fark ≤ 1e-12 mm. SimStep yine her hareket için yazılır: hacimler rel 1e-12, süre birebir.
- Dexel aralık uçları 1e-12 mm, hacim rel 1e-12.
Eski yol: block = None, merge = False.
Not: hücre merkezleri tam takım izinin sınırına (d = R) denk getirilmedi (orada √ kötü koşullu).
"""

from __future__ import annotations

import functools
import math

import numpy as np
import pytest

from cam.model import CamError, Move, MoveType, Toolpath
from cam.sim import simulate
from cam.sim.blok import merge_collinear
from tests.cam import benchref
from tests.cam.simref import G0, G1, RANDOM_STOCK, ball, flat, path, random_program

ESKI = {"block": None, "merge": False}

# ------------------------------------------------------------------ programlar


def _bolunmus(yol: Toolpath, k: int = 7) -> Toolpath:
    """Her G1'i k eşit parçaya böler (aynı doğru, aynı F): birleştirme bunları yeniden tek harekete
    indirebilir."""
    mv: list[Move] = []
    p = np.array(yol.start, dtype=float)
    for m in yol.moves:
        q = np.array(m.end, dtype=float)
        if m.type == MoveType.LINEAR:
            for i in range(1, k + 1):
                r = q if i == k else p + (q - p) * (i / k)
                mv.append(G1(*map(float, r), F=m.feed))
        else:
            mv.append(m)
        p = q
    return Toolpath(yol.name, yol.tool, yol.start, mv, yol.rpm)


def _rastgele(ad: str) -> Toolpath:
    tool = {"duz": flat(D=6.0, Lf=30.0), "kuresel": ball(D=6.0, Lf=30.0)}[ad]
    return random_program(tool, n=50)


def _part_z(cell: float) -> np.ndarray:
    """RANDOM_STOCK üstünde z = −3 düz parça: rastgele programın −3'ün altına inen hareketleri çakma kaydı
    üretir."""
    nx = math.ceil(RANDOM_STOCK.xmax / cell)
    ny = math.ceil(RANDOM_STOCK.ymax / cell)
    return np.full((ny, nx), -3.0)


@functools.cache
def _calistir(anahtar: str, cell: float, model: str, block, merge: bool, parca: bool = False):
    yollar = {
        "duz": lambda: [_rastgele("duz")],
        "kuresel": lambda: [_rastgele("kuresel")],
        "bolunmus": lambda: [_bolunmus(_rastgele("duz"))],
        "B1": lambda: [benchref.b1()],
        "B2": lambda: [benchref.b2(5.0)],
    }[anahtar]()
    stok = benchref.STOK if anahtar in ("B1", "B2") else RANDOM_STOCK
    pz = _part_z(cell) if parca else None
    return simulate(yollar, stok, cell=cell, model=model, block=block, merge=merge, part_z=pz)


# ------------------------------------------------------------------ karşılaştırma


def _ayni_adimlar(a, b, kesin: bool) -> None:
    assert len(a.steps) == len(b.steps)
    eps = 1e-12 * max(1.0, abs(b.removed_volume))
    for sa, sb in zip(a.steps, b.steps, strict=True):
        assert (sa.k, sa.op, sa.type, sa.start, sa.end, sa.center, sa.feed, sa.link) == (
            sb.k,
            sb.op,
            sb.type,
            sb.start,
            sb.end,
            sb.center,
            sb.feed,
            sb.link,
        )
        assert sa.duration == sb.duration
        if kesin:
            assert sa.removed == pytest.approx(sb.removed, rel=1e-12, abs=1e-15)
        else:
            assert sa.removed == pytest.approx(sb.removed, rel=1e-12, abs=eps)
        assert sa.mrr == pytest.approx(sb.mrr, rel=1e-12, abs=eps)
    assert a.total_time == b.total_time
    assert a.op_times == b.op_times
    assert a.removed_volume == pytest.approx(b.removed_volume, rel=1e-12)
    assert len(a.collisions) == len(b.collisions)
    for ca, cb in zip(a.collisions, b.collisions, strict=True):
        assert (ca.kind, ca.k, ca.op) == (cb.kind, cb.k, cb.op)
        if kesin:
            assert ca == cb
        else:
            np.testing.assert_allclose(ca.at, cb.at, rtol=0, atol=1e-12)
            assert ca.depth == pytest.approx(cb.depth, abs=1e-12)


def _ayni_zmap(a, b, kesin: bool) -> None:
    za, zb = a.zmap.z, b.zmap.z
    assert za.shape == zb.shape
    if kesin:
        assert np.array_equal(za, zb)
    else:
        np.testing.assert_allclose(za, zb, rtol=0, atol=1e-12)
    _ayni_adimlar(a, b, kesin)


def _ayni_dexel(a, b) -> None:
    da, db = a.dexel, b.dexel
    assert (da.nx, da.ny) == (db.nx, db.ny)
    for i in range(db.nx):
        for j in range(db.ny):
            ia = np.array(da.intervals(i, j), dtype=float).reshape(-1, 2)
            ib = np.array(db.intervals(i, j), dtype=float).reshape(-1, 2)
            assert ia.shape == ib.shape, (i, j, ia, ib)
            np.testing.assert_allclose(ia, ib, rtol=0, atol=1e-12)
    assert da.volume() == pytest.approx(db.volume(), rel=1e-12)
    _ayni_adimlar(a, b, kesin=False)


# ------------------------------------------------------------------ K1 z-map

HIZLI = ["duz", "kuresel", "bolunmus", "B1"]


@pytest.mark.parametrize("block", [256, 32, 7])
@pytest.mark.parametrize("prog", HIZLI)
def test_K1_bloklu_birlestirmesiz_bit_duzeyinde(prog, block):
    cell = 1.0
    eski = _calistir(prog, cell, "zmap", None, False)
    yeni = _calistir(prog, cell, "zmap", block, False)
    _ayni_zmap(yeni, eski, kesin=True)


@pytest.mark.parametrize("block", [256, 7, None])
@pytest.mark.parametrize("prog", HIZLI)
def test_K1_birlestirmeli_1e12(prog, block):
    cell = 1.0
    eski = _calistir(prog, cell, "zmap", None, False)
    yeni = _calistir(prog, cell, "zmap", block, True)
    _ayni_zmap(yeni, eski, kesin=False)


@pytest.mark.parametrize("prog", ["duz", "bolunmus"])
def test_K1_cakma_ve_carpma_kayitlari_ayni(prog):
    """Parça yüksekliğiyle (çakma) ve stoğa giren G0'larla (hızlı çarpma): Collision listesi aynı."""
    eski = _calistir(prog, 1.0, "zmap", None, False, parca=True)
    assert {c.kind for c in eski.collisions} >= {"cakma"}
    _ayni_zmap(_calistir(prog, 1.0, "zmap", 7, False, parca=True), eski, kesin=True)
    _ayni_zmap(_calistir(prog, 1.0, "zmap", 256, True, parca=True), eski, kesin=False)


def test_K1_varsayilan_yeni_yol_eskiyle_ayni():
    """Varsayılan (block = 256, merge = True) eski yolla 1e-12 içinde aynı."""
    prog = _rastgele("duz")
    eski = _calistir("duz", 1.0, "zmap", None, False)
    yeni = simulate([prog], RANDOM_STOCK, cell=1.0)
    _ayni_zmap(yeni, eski, kesin=False)


@pytest.mark.slow
@pytest.mark.parametrize(("block", "merge", "kesin"), [(32, False, True), (256, True, False)])
def test_K1_B2(block, merge, kesin):
    """B2 (yan adım 5 mm'ye seyreltilmiş, aynı yüzey ve takım), hücre 2 mm: 100 × 100 ızgara, 32'lik
    karolar."""
    eski = _calistir("B2", 2.0, "zmap", None, False)
    _ayni_zmap(_calistir("B2", 2.0, "zmap", block, merge), eski, kesin=kesin)


# ------------------------------------------------------------------ K2 dexel


@pytest.mark.parametrize(("block", "merge"), [(256, False), (7, False), (256, True), (7, True)])
@pytest.mark.parametrize("prog", HIZLI)
def test_K2_dexel(prog, block, merge):
    cell = 2.0 if prog == "B1" else 1.0
    eski = _calistir(prog, cell, "dexel", None, False)
    _ayni_dexel(_calistir(prog, cell, "dexel", block, merge), eski)


@pytest.mark.slow
def test_K2_dexel_B2():
    eski = _calistir("B2", 2.0, "dexel", None, False)
    _ayni_dexel(_calistir("B2", 2.0, "dexel", 32, True), eski)


# ------------------------------------------------------------------ K3 birleştirme

BAS = (-5.0, 3.3, -2.0)
SON = (35.0, 17.1, -2.7)


def _dogru(n: int = 1000, sapma: float = 0.0, F: float = 600.0) -> list[Move]:
    """BAS → SON doğrusunda n kısa G1; sapma > 0 ise tek indisli uç noktalar doğrudan dik yönde sapma kadar
    kayık."""
    p0, p1 = np.array(BAS), np.array(SON)
    d = p1 - p0
    nrm = np.cross(d, (0.0, 0.0, 1.0))
    nrm /= np.linalg.norm(nrm)
    mv = []
    for k in range(1, n + 1):
        q = p0 + d * (k / n) + (sapma * nrm if k % 2 == 1 else 0.0)
        mv.append(G1(*map(float, q), F=F))
    return mv


def test_K3_1000_kisa_hareket_tek_harekete_iner():
    assert merge_collinear(_dogru(), start=BAS) == [(0, 999)]


def test_K3_kirik_dogruda_birlesme_yok():
    """Sapma 1e-6 > tol = 1e-9: hiçbir ardışık çift aynı doğruda değil."""
    assert merge_collinear(_dogru(sapma=1e-6), start=BAS) == [(i, i) for i in range(1000)]


def test_K3_tolerans_parametresi():
    """tol = 1e-5 ≥ sapma 1e-6: tüm uç noktalar BAS–SON doğrusuna ≤ tol → tek aralık."""
    assert merge_collinear(_dogru(sapma=1e-6), tol=1e-5, start=BAS) == [(0, 999)]


def test_K3_farkli_ilerleme_birlesmez():
    mv = _dogru(n=10, F=600.0)
    mv[5:] = [G1(*m.end, F=900.0) for m in mv[5:]]
    assert merge_collinear(mv, start=BAS) == [(0, 4), (5, 9)]


def test_K3_geri_donus_birlesmez():
    """Aynı doğruda yön değişimi: [p₀, p₂] süpürmesi [p₀, p₁] ∪ [p₁, p₂]'den kısa olur → ayrı aralıklar."""
    mv = [G1(float(x), 5.0, -2.0) for x in range(1, 11)] + [G1(float(x), 5.0, -2.0) for x in range(9, -1, -1)]
    assert merge_collinear(mv, start=(0.0, 5.0, -2.0)) == [(0, 9), (10, 19)]


def test_K3_yalniz_g1_birlesir():
    """G0 ve yaylar birleştirilmez (SPEC: aynı doğru üzerindeki ardışık G1 hareketleri)."""
    mv = [G0(1.0, 0.0, 5.0), G0(2.0, 0.0, 5.0), G0(3.0, 0.0, 5.0)]
    mv += [G1(4.0, 0.0, 5.0), G1(5.0, 0.0, 5.0)]
    mv += [Move(MoveType.ARC_CCW, (5.0, 2.0, 5.0), 600.0, center=(5.0, 1.0))]
    mv += [Move(MoveType.ARC_CCW, (5.0, 0.0, 5.0), 600.0, center=(5.0, 1.0))]
    assert merge_collinear(mv, start=(0.0, 0.0, 5.0)) == [(0, 0), (1, 1), (2, 2), (3, 4), (5, 5), (6, 6)]


def test_K3_araliklar_tum_hareketleri_ortuyor():
    for yol in (_rastgele("duz"), _bolunmus(_rastgele("duz")), benchref.b1()):
        g = merge_collinear(yol.moves, start=yol.start)
        assert g[0][0] == 0 and g[-1][1] == len(yol.moves) - 1
        for (a0, a1), (b0, _) in zip(g[:-1], g[1:], strict=True):
            assert a0 <= a1 and b0 == a1 + 1
        for a0, a1 in g:
            if a1 > a0:
                assert all(m.type == MoveType.LINEAR for m in yol.moves[a0 : a1 + 1])


def test_K3_bolunmus_programda_birlesme_var():
    """Her G1 7 parçaya bölündü: en az orijinal G1 sayısı kadar 7'li aralık."""
    asil = _rastgele("duz")
    n_g1 = sum(m.type == MoveType.LINEAR for m in asil.moves)
    yol = _bolunmus(asil)
    g = merge_collinear(yol.moves, start=yol.start)
    assert sum(1 for a, b in g if b - a + 1 >= 7) >= n_g1


@pytest.mark.slow
@pytest.mark.parametrize("sapma", [0.0, 1e-6])
@pytest.mark.parametrize("tool", ["duz", "kuresel"])
def test_K3_birlesmis_ve_birlesmemis_zmap_ayni(tool, sapma):
    t = {"duz": flat(D=6.0, Lf=30.0), "kuresel": ball(D=6.0, Lf=30.0)}[tool]
    yol = path(t, BAS, _dogru(sapma=sapma))
    eski = simulate([yol], RANDOM_STOCK, cell=1.0, **ESKI)
    for block in (None, 256, 7):
        yeni = simulate([yol], RANDOM_STOCK, cell=1.0, block=block, merge=True)
        _ayni_zmap(yeni, eski, kesin=False)
    assert len(eski.steps) == 1000


# ------------------------------------------------------------------ K9


@pytest.mark.parametrize("block", [0, -1, -256])
def test_K9_block_pozitif_olmali(block):
    with pytest.raises(CamError):
        simulate([_rastgele("duz")], RANDOM_STOCK, cell=1.0, block=block)
