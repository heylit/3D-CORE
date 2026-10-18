"""SPEC 49 K4–K5 — kama ve delik hacimleri: simüle edilen kaldırılan hacim formüle yakınsar.

Testler SPEC 49 "Y ekseni", "Hacim formülleri" ve "Simülasyon: 22 + 43" bölümlerinden ve iskelet arayüzünden
yazıldı; cam/millturn ve cam/sim/millturn.py gövdeleri okunmadı.

Kaynaklar (SPEC 49, formüller tests/cam/mtref.py'de, integraller scipy quad ile 1e-10 göreli doğrulukta):
- Kama: V = A·L + V_uç, A = (b/2)√(R² − b²/4) + R²·asin(b/2R) − b(R − t).
- Kaçık düz tabanlı delik: V = ∫_{−ρ}^{ρ} 2√(ρ² − y²)(√(R² − (y + e)²) − x_b) dy; e = 0 radyal delik.
- Eksenel alın deliği: πρ²·depth.
Tolerans: tri-dexel hacim hatası P·Δ·L mertebesinde (P kesitin malzemeyle temas eden çevresi, L boyu);
uçlar / taban için bir Δ'lık pay eklenir. Δ yarıya inince hata azalır.
Delik tabanı x_b yolun kendisinden okunur: radyal işlemde takım ekseni −X (C ile döndürülmeden önce),
taban = hareketlerin en küçük x'i (e = 0'da x_b = R − depth ayrıca denetlenir).
"""

from __future__ import annotations

import math

import pytest

from cam.millturn.ops import LiveCut, axial_hole, keyway, radial_hole
from cam.model import CamError, MoveType
from cam.sim.millturn import simulate_mt
from tests.cam.mtref import (
    ST_EKSENEL,
    ST_RADYAL,
    STOK,
    R,
    freze,
    kacik_delik_hacmi,
    kama_hacmi,
    kama_kesit,
    kama_kesit_quad,
    profil,
)

KESME = LiveCut(feed=300.0, plunge_feed=100.0, rpm=3000.0)
B, T, L = 6.0, 3.5, 30.0  # kama genişliği (takım çapı), derinlik, uç merkezleri arası boy
Z0, Z1 = -40.0, -10.0
INCE = pytest.param(0.25, marks=pytest.mark.slow)


def test_kama_kesit_formulu_quad_ile():
    """Kapalı form ile integral aynı (referansın kendi tutarlılığı)."""
    assert kama_kesit(R, B, T) == pytest.approx(kama_kesit_quad(R, B, T), rel=1e-10)


# ------------------------------------------------------------------ K4 kama


def _kama(theta: float = 30.0, machine=None):
    M = profil() if machine is None else machine
    tp = keyway(STOK, freze(B), KESME, theta, Z0, Z1, T, 2.0, station=ST_RADYAL, machine=M)
    tp.validate()
    return tp, M


def _kama_hata(cell: float) -> tuple[float, float, float]:
    tp, M = _kama()
    V = kama_hacmi(R, B, T, L)
    res = simulate_mt([tp], STOK, M, cell=cell)
    tol = (B + 2 * T) * cell * (L + B)
    return res.removed_volume - V, tol, V


@pytest.mark.parametrize("cell", [0.5, INCE])
def test_K4_kama_hacmi(cell):
    """R = 20, b = 6, t = 3.5, L = 30: kaldırılan hacim A·L + V_uç, tolerans (b + 2t)·Δ·(L + b)."""
    hata, tol, V = _kama_hata(cell)
    assert V > 0
    assert abs(hata) <= tol


@pytest.mark.slow
def test_K4_kama_hacmi_yakinsar():
    """Δ = 0.5 → 0.25: hata azalır (hata zaten V'nin binde biri altındaysa yakınsama sayılır)."""
    h1, _, V = _kama_hata(0.5)
    h2, _, _ = _kama_hata(0.25)
    assert abs(h2) < abs(h1) or abs(h2) <= 1e-3 * V


def test_K4_kama_yolu():
    """Kama: C = −θ sabit, takım −X yönünde x = R − t'ye dalar, Z boyunca z0 → z1; genişlik takım çapı."""
    tp, _ = _kama(theta=30.0)
    cs = {round(m.c, 9) % 360.0 for m in tp.moves if m.c is not None}
    assert cs == {330.0}
    kesme = [m for m in tp.moves if m.type is not MoveType.RAPID]
    assert min(m.end[0] for m in tp.moves) == pytest.approx(R - T, abs=1e-9)
    taban = [m.end for m in kesme if abs(m.end[0] - (R - T)) <= 1e-9]
    assert min(p[2] for p in taban) == pytest.approx(Z0, abs=1e-9)
    assert max(p[2] for p in taban) == pytest.approx(Z1, abs=1e-9)
    assert all(abs(m.end[1]) <= 1e-12 for m in tp.moves)


# ------------------------------------------------------------------ K5 delikler

RHO = 4.0
DERIN = 6.0


def _radyal(e: float):
    M = profil()
    tp = radial_hole(STOK, freze(2 * RHO), KESME, 75.0, -25.0, DERIN, e=e, station=ST_RADYAL, machine=M)
    tp.validate()
    return tp, M


def _taban(tp) -> float:
    return min(m.end[0] for m in tp.moves)


def test_K5_radyal_delik_tabani():
    """e = 0: giriş stok yüzeyinden (x = R), taban x = R − depth; takım y = 0'da."""
    tp, _ = _radyal(0.0)
    assert _taban(tp) == pytest.approx(R - DERIN, abs=1e-9)
    assert all(abs(m.end[1]) <= 1e-12 for m in tp.moves)


def test_K5_kacik_delik_y_konumu():
    """e = 8: takım merkezi y = e doğrusunda; delik tamamen malzemede (x_b ≤ √(R² − (ρ + e)²) = 16)."""
    tp, _ = _radyal(8.0)
    kesme = [m for m in tp.moves if m.type is not MoveType.RAPID]
    assert kesme
    assert all(abs(m.end[1] - 8.0) <= 1e-12 for m in kesme)
    assert _taban(tp) <= math.sqrt(R**2 - (RHO + 8.0) ** 2) + 1e-9


@pytest.mark.parametrize("e", [0.0, 8.0])
@pytest.mark.parametrize("cell", [0.5, INCE])
def test_K5_radyal_ve_kacik_delik_hacmi(e, cell):
    tp, M = _radyal(e)
    x_b = _taban(tp)
    V = kacik_delik_hacmi(R, RHO, e, x_b)
    if e == 0.0:
        assert V == pytest.approx(kacik_delik_hacmi(R, RHO, 0.0, R - DERIN), rel=1e-9)
    res = simulate_mt([tp], STOK, M, cell=cell)
    tol = 2 * math.pi * RHO * cell * (R - x_b) + math.pi * RHO**2 * cell
    assert abs(res.removed_volume - V) <= tol


@pytest.mark.parametrize("cell", [0.5, INCE])
def test_K5_eksenel_delik_hacmi(cell):
    """Alında (zmax) r = 10, θ = 45°, ρ = 3, depth = 8: V = πρ²·depth."""
    M = profil()
    rho, depth = 3.0, 8.0
    tp = axial_hole(STOK, freze(2 * rho), KESME, 10.0, 45.0, depth, station=ST_EKSENEL, machine=M)
    tp.validate()
    assert min(m.end[2] for m in tp.moves) == pytest.approx(STOK.zmax - depth, abs=1e-9)
    res = simulate_mt([tp], STOK, M, cell=cell)
    V = math.pi * rho**2 * depth
    tol = 2 * math.pi * rho * cell * depth + math.pi * rho**2 * cell
    assert abs(res.removed_volume - V) <= tol


@pytest.mark.parametrize("e", [15.0, -10.5])
def test_K5_y_kursu_disinda_hata(e):
    """Y kursu ±10: e = 15 ve −10.5 dışarıda → CamError."""
    with pytest.raises(CamError):
        radial_hole(STOK, freze(2 * RHO), KESME, 0.0, -25.0, 3.0, e=e, station=ST_RADYAL, machine=profil())
