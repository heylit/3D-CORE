"""SPEC 30 Ek B — yay bloğunda yuvarlanmamış model bitişi (`Arc.end`) ve Heidenhain helis bitişi.

Ek B (kullanıcı onayı, 2026-10-18): `Arc`'a isteğe bağlı `end: tuple[float, float, float] | None = None`
eklenir; blok eşitliğine katılmaz (`compare=False`). `plan()` alanı yolun model bitişiyle doldurur.
ISO ve Sinumerik çıktıları `end`'den bağımsızdır (bayt bayt aynı). Heidenhain `CP` bloğu bitişi yazmaz;
biçimleyici `CC`'yi okunan bitiş model bitişine en yakın olacak biçimde seçer: geri okunan uç ≤ 0.5·10⁻³ mm.
Testler yalnız bu ek metninden yazıldı; uygulama kodu okunmadı.
"""

from __future__ import annotations

import dataclasses
import math
from dataclasses import replace

import numpy as np
import pytest

from cam.gcode import FANUC, GRBL
from cam.model import ARCS, Move, Toolpath
from cam.post import HAAS, SINUMERIK, Arc, format, format_sinumerik, plan, post, read_program
from tests.cam.post31_ortak import HEI_M, TOL, altin, ornek
from tests.cam.post_ortak import G1, G2, G3, ortala, takim
from tests.cam.test_gcode_roundtrip import SEED, as_written, assert_paths_close, random_path, safe_z_of


def _alan_var() -> None:
    """`Arc.end` henüz yoksa test "uygulanmamış" sayılır (CI'da kırmızı)."""
    if "end" not in {f.name for f in dataclasses.fields(Arc)}:
        raise NotImplementedError("SPEC 30 Ek B: Arc.end alanı henüz yok")


def _arc_bloklari(tp: Toolpath, dialect=FANUC) -> list[Arc]:
    return [b for b in plan([tp], dialect, safe_z=safe_z_of(tp)) if isinstance(b, Arc)]


# ---------------------------------------------------------------- alanın kendisi


def test_end_varsayilan_none_ve_esitlige_katilmaz():
    _alan_var()
    eski = Arc(1.0, 2.0, None, -1.0, 0.0, True, 300.0)
    assert eski.end is None
    a = Arc(1.0, 2.0, None, -1.0, 0.0, True, 300.0, end=(1.0004, 2.0001, -3.0))
    b = Arc(1.0, 2.0, None, -1.0, 0.0, True, 300.0, end=(0.9996, 1.9999, -3.0))
    assert a == b == eski
    assert hash(a) == hash(b)
    alan = {f.name: f for f in dataclasses.fields(Arc)}["end"]
    assert alan.compare is False
    assert alan.default is None


# ---------------------------------------------------------------- plan() doldurur


@pytest.mark.parametrize("seed", [SEED, 1, 3])
def test_plan_end_model_bitisi(seed):
    """Her yay bloğunun `end`'i yoldaki karşılık gelen yay hareketinin yuvarlanmamış bitişi."""
    _alan_var()
    tp, _ = random_path(seed)
    yaylar = [m for m in tp.moves if m.type in ARCS]
    bloklar = _arc_bloklari(tp)
    assert len(bloklar) == len(yaylar)
    for b, m in zip(bloklar, yaylar, strict=True):
        assert b.end is not None
        assert len(b.end) == 3
        np.testing.assert_allclose(b.end, m.end, rtol=0, atol=1e-12)


@pytest.mark.parametrize("dialect", [GRBL, FANUC, HAAS, SINUMERIK], ids=lambda d: d.name)
def test_plan_end_dilden_bagimsiz(dialect):
    _alan_var()
    tp, _ = random_path(SEED)
    ref = _arc_bloklari(tp, FANUC)
    got = _arc_bloklari(tp, dialect)
    assert [b.end for b in got] == [b.end for b in ref]


# ---------------------------------------------------------------- ISO / Sinumerik bayt eşitliği


def _endsiz(blocks):
    return [replace(b, end=None) if isinstance(b, Arc) else b for b in blocks]


@pytest.mark.parametrize("seed", [SEED, 1])
@pytest.mark.parametrize("dialect", [GRBL, FANUC, HAAS], ids=lambda d: d.name)
def test_iso_cikti_end_bagimsiz(dialect, seed):
    _alan_var()
    tp, _ = random_path(seed)
    blocks = plan([tp], dialect, safe_z=safe_z_of(tp))
    assert format(blocks, dialect) == format(_endsiz(blocks), dialect)


@pytest.mark.parametrize("seed", [SEED, 1])
def test_sinumerik_cikti_end_bagimsiz(seed):
    _alan_var()
    tp, _ = random_path(seed)
    blocks = plan([tp], SINUMERIK, safe_z=safe_z_of(tp))
    assert format_sinumerik(blocks, SINUMERIK) == format_sinumerik(_endsiz(blocks), SINUMERIK)


# ---------------------------------------------------------------- Heidenhain helis bitişi


def _helis_zinciri(n: int = 20, seed: int = 7) -> Toolpath:
    """Yuvarlamaya elverişsiz (irrasyonel) yarıçap, açı ve Δz'li ardışık helisler; r ≤ 50 mm."""
    rng = np.random.default_rng(seed)
    p = np.array([math.pi, math.e, 0.0])
    moves = [Move(G1, tuple(p), feed=200.0)]
    for _ in range(n):
        r = float(rng.uniform(1.0, 30.0)) + math.sqrt(2) * 1e-4
        a0 = float(rng.uniform(0.0, 2 * math.pi))
        c = p[:2] - r * np.array([math.cos(a0), math.sin(a0)])
        ccw = bool(rng.random() < 0.5)
        dth = float(rng.uniform(math.radians(20.0), math.radians(340.0)))
        a1 = a0 + dth if ccw else a0 - dth
        dz = float(rng.uniform(-3.0, 3.0)) + 1e-7
        q = np.array([c[0] + r * math.cos(a1), c[1] + r * math.sin(a1), p[2] + dz])
        moves.append(Move(G3 if ccw else G2, tuple(q), feed=300.0, center=(float(c[0]), float(c[1]))))
        p = q
    return Toolpath("helisler", takim(1, L=100.0), (math.pi, math.e, 5.0), rpm=6000.0, moves=moves)


def test_heidenhain_helis_bitisi_K5_icinde():
    """Okunan her helis bitişi model bitişinden koordinat başına ≤ 0.5·10⁻³ mm; merkez ≤ 1e-2 mm."""
    _alan_var()
    m = ornek(HEI_M)
    tp = _helis_zinciri()
    z_s = safe_z_of(tp)
    setup = ortala(m, [tp], 100.0, z_ek=z_s)
    got = read_program(post([tp], m, setup, safe_z=z_s), m, {1: tp.tool})
    assert len(got) == 1
    got[0].validate()
    beklenen = as_written(tp, z_s)
    assert_paths_close(got[0], beklenen)
    for g, e in zip(got[0].moves, beklenen.moves, strict=True):
        assert np.max(np.abs(np.subtract(g.end, e.end))) <= TOL


def test_heidenhain_end_none_eski_davranis():
    """`end = None` blokla da Heidenhain metni üretilir (eski davranış: yuvarlanmış merkezden); uç ≤ 1e-3."""
    _alan_var()
    from cam.post import HEIDENHAIN, format_heidenhain

    m = altin(HEI_M)
    tp = _helis_zinciri(n=10)
    z_s = safe_z_of(tp)
    blocks = _endsiz(plan([tp], HEIDENHAIN, safe_z=z_s))
    text = format_heidenhain(blocks, {"G54": 1}, HEIDENHAIN, "1")
    got = read_program(text, m, {1: tp.tool})
    beklenen = as_written(tp, z_s)
    assert len(got[0].moves) == len(beklenen.moves)
    for g, e in zip(got[0].moves, beklenen.moves, strict=True):
        assert np.max(np.abs(np.subtract(g.end, e.end))) <= 1e-3


def test_helis_zinciri_veri_denetimi():
    """Test verisinin kendisi: yol geçerli, aynı kurslu ISO profilinde yazılıp okununca K5 içinde."""
    from cam.post import builtin_machines

    tp = _helis_zinciri()
    tp.validate()
    m = replace(builtin_machines()["ORNEK-FANUC-DIK"], tool_change_z=None)
    z_s = safe_z_of(tp)
    setup = ortala(m, [tp], 100.0, z_ek=z_s)
    got = read_program(post([tp], m, setup, safe_z=z_s), m, {1: tp.tool})
    assert_paths_close(got[0], as_written(tp, z_s))
