"""SPEC 49 K6–K7 — torna (22) + freze (43) simülasyonu: RadialMap → TriDexel, toplam hacim, çarpışmalar.

Testler SPEC 49 "Çerçeveler", "Simülasyon: 22 + 43" bölümlerinden ve iskelet arayüzünden yazıldı;
cam/sim/millturn.py ve cam/millturn gövdeleri okunmadı.

Kaynaklar:
- SPEC 49: p_t = R_z(C)·p_p → tezgâh konumundaki takım parçaya R_z(−C) ile çevrilir. RadialMap → TriDexel
  kutusu [−r_max, r_max]² × [z0, z0 + nz·dz]; X / Y ışınları sabit z'de dönel bölgeyle kesin kesilir
  (ışın (x_c, z) için r ∈ [a, b] → |y| ∈ [√(a² − x_c²), √(b² − x_c²)]).
- SPEC 22 (test_lsim_volume.py ile aynı): boy tornalama hacmi π(R² − x_f²)(−z_end) − burun dolgusu,
  dolgu 2π(x_c + d)·r²(1 − π/4), d = r(10 − 3π)/(12 − 3π); tolerans π·R²·Δ.
- SPEC 43: hizli_carpma derinliği = G0'ın kaldırdığı en uzun ışın parçası; bir işlemin ilk hareketi k = 1.
- SPEC 22: ayna_carpma = takım süpürmesi bağlama elemanının [d/2, D/2] aralığıyla çakışır.
Tri-dexel dönüşüm hatası O(Δ): |V_td − V_rmap| ≤ S·Δ, S katının yüzey alanı.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from cam.lathe_ops import TurnCut, turn
from cam.millturn.ops import LiveCut, keyway
from cam.model import CamError, CylinderStock, Move, MoveType, Toolpath
from cam.sim import RadialMap, simulate_lathe
from cam.sim.millturn import rmap_to_tridexel, simulate_mt, to_part_frame
from cam.sim.tridexel import TriDexel
from tests.cam.lsimref import turn_tool
from tests.cam.mtref import ST_RADYAL, STOK, R, freze, kama_hacmi, profil

G0, G1 = MoveType.RAPID, MoveType.LINEAR
R_N = 0.8
X_F, Z_END = 16.0, -20.2
KESME = LiveCut(feed=300.0, plunge_feed=100.0, rpm=3000.0)
B, T = 6.0, 3.5
KINDS = {"hizli_carpma", "sap_carpma", "tutucu_carpma", "cakma", "ayna_carpma"}


def _spandrel(xc: float, r: float) -> float:
    A = r * r * (1 - math.pi / 4)
    d = r * (10 - 3 * math.pi) / (12 - 3 * math.pi)
    return 2 * math.pi * (xc + d) * A


def _boy():
    return turn(STOK, turn_tool(R_N), TurnCut(feed=0.2, rpm=1000.0, a_p=1.5), X_F, Z_END)


def _kama(z0: float, z1: float, theta: float = 0.0, M=None):
    M = profil() if M is None else M
    tp = keyway(STOK, freze(B), KESME, theta, z0, z1, T, 2.0, station=ST_RADYAL, machine=M)
    tp.validate()
    return tp


def _yuzey(Lz: float) -> float:
    return 2 * math.pi * R * Lz + 2 * math.pi * R**2


def _kayitlar_gecerli(res) -> None:
    for c in res.collisions:
        assert c.kind in KINDS


# ------------------------------------------------------------------ K6 RadialMap → TriDexel


@pytest.mark.parametrize("cell", [1.0, 0.5])
def test_K6_dolu_stok_donusumu(cell):
    rmap = RadialMap.from_stock(STOK, cell)
    td = rmap_to_tridexel(rmap, cell)
    assert isinstance(td, TriDexel)
    assert td.x0 == pytest.approx(-rmap.r_max, abs=1e-12)
    assert td.y0 == pytest.approx(-rmap.r_max, abs=1e-12)
    assert td.z0 == pytest.approx(rmap.z0, abs=1e-12)
    assert td.z0 + td.nz * td.dz == pytest.approx(rmap.z0 + rmap.nz * rmap.dz, abs=1e-9)
    Lz = STOK.zmax - STOK.zmin
    assert abs(td.volume() - rmap.volume()) <= _yuzey(Lz) * cell


@pytest.mark.parametrize("cell", [1.0, 0.5])
def test_K6_tornalanmis_mil_donusumu(cell):
    """Kademeli mil (22 sonucu) → tri-dexel: hacim 22 haritasına O(Δ) eşit."""
    rmap = simulate_lathe([_boy()], STOK, cell=cell).rmap
    td = rmap_to_tridexel(rmap, cell)
    Lz = STOK.zmax - STOK.zmin
    S = _yuzey(Lz) + math.pi * (R**2 - X_F**2)  # kademe halkası
    assert abs(td.volume() - rmap.volume()) <= S * cell


def test_K6_x_isini_kesin_kesilir():
    """Dolu stokta X ışını (y_c, z_c): aralık [−√(R² − y_c²), √(R² − y_c²)] (dönel bölgeyle kesin)."""
    cell = 0.5
    rmap = RadialMap.from_stock(STOK, cell)
    td = rmap_to_tridexel(rmap, cell)
    Vx, Vy, Vz = td.volumes()
    # X ve Y ışınlarının hacmi: Σ_{y_c, z_c} 2√(R² − y_c²)·Δy·Δz (her z diliminde aynı)
    n = td.ny
    yc = td.y0 + (np.arange(n) + 0.5) * td.dy
    beklenen = np.sum(2 * np.sqrt(np.maximum(R**2 - yc**2, 0.0))) * td.dy * (STOK.zmax - STOK.zmin)
    assert Vx == pytest.approx(beklenen, rel=1e-9)
    assert Vy == pytest.approx(beklenen, rel=1e-9)


# ------------------------------------------------------------------ K6 toplam hacim


def test_K6_torna_ve_kama_toplam_hacim():
    """Önce boy tornalama (R = 20 → x_f = 16, z_end = −20.2), sonra tornalanmamış bölgede kama
    (z −42 → −30, L = 12): kaldırılan hacim = torna hacmi (22 formülü) + kama hacmi (A·L + V_uç)."""
    cell = 0.5
    M = profil()
    z0, z1 = -42.0, -30.0
    V_torna = math.pi * (R**2 - X_F**2) * (-Z_END) - _spandrel(X_F, R_N)
    V_kama = kama_hacmi(R, B, T, z1 - z0)
    res = simulate_mt([_boy(), _kama(z0, z1, M=M)], STOK, M, cell=cell)
    tol = math.pi * R**2 * cell + (B + 2 * T) * cell * (z1 - z0 + B)
    assert res.removed_volume == pytest.approx(V_torna + V_kama, abs=tol)
    # torna aşaması 22 ile aynı: fark yalnız kama ve dönüşüm hatası
    V22 = simulate_lathe([_boy()], STOK, cell=cell).removed_volume
    assert res.removed_volume - V22 == pytest.approx(V_kama, abs=tol)
    _kayitlar_gecerli(res)


def test_K6_frezeden_sonra_torna_hata():
    M = profil()
    with pytest.raises(CamError):
        simulate_mt([_kama(-42.0, -30.0, M=M), _boy()], STOK, M, cell=0.5)


# ------------------------------------------------------------------ parça çerçevesi


def _dalis_yolu(c: float = 270.0) -> Toolpath:
    """Radyal istasyon, takım ekseni tezgâhta −X (Move.axis uçtan iş miline = +X): z = −30'da G0 ile
    x = 40'tan x = 10'a dalış ve geri çıkış, hepsi C = c'de."""
    ax = (1.0, 0.0, 0.0)
    return Toolpath(
        "g0_dalis",
        freze(6.0),
        (45.0, 0.0, -30.0),
        [
            Move(G0, (40.0, 0.0, -30.0), axis=ax, c=c),
            Move(G0, (10.0, 0.0, -30.0), axis=ax, c=c),
            Move(G0, (40.0, 0.0, -30.0), axis=ax, c=c),
        ],
        rpm=3000.0,
        station=ST_RADYAL,
    )


def test_to_part_frame_c_donusumu():
    """C = 270° (θ = 90° özelliği): tezgâh +X → parça R_z(−270°)·X = +Y."""
    tp = to_part_frame(_dalis_yolu(270.0))
    tp.validate()
    assert tp.coord == "kartezyen"
    assert all(m.c is None for m in tp.moves)
    P = tp.points()
    assert P[-3] == pytest.approx([0.0, 40.0, -30.0], abs=1e-12)
    assert P[-2] == pytest.approx([0.0, 10.0, -30.0], abs=1e-12)
    for m in tp.moves[-3:]:
        assert m.axis == pytest.approx((0.0, 1.0, 0.0), abs=1e-12)


@pytest.mark.parametrize("c", [0.0, 30.0, 135.0])
def test_to_part_frame_genel_aci(c):
    tp = to_part_frame(_dalis_yolu(c))
    a = math.radians(-c)
    beklenen = [10.0 * math.cos(a), 10.0 * math.sin(a), -30.0]
    assert tp.points()[-2] == pytest.approx(beklenen, abs=1e-12)


# ------------------------------------------------------------------ K7 çarpışma


def test_K7_c_indeksli_g0_hizli_carpma():
    """C = 270°'de G0 dalış parçada +Y boyunca y = 40 → 10 (x = 0, z = −30), düz uç ρ = 3.
    Kaldırılan en uzun parça Y ışınında: (x_c, z_c) takım içinde, |x_c| en küçük ışın merkezi →
    √(R² − x_c²) − 10 (X ve Z ışınlarında parça ≤ 2ρ = 6). İlk hareket k = 1 → dalış k = 2."""
    cell = 0.5
    M = profil()
    res = simulate_mt([_dalis_yolu(270.0)], STOK, M, cell=cell)
    n = math.ceil(2 * R / cell - 1e-9)
    xc = -R + (np.arange(n) + 0.5) * (2 * R / n)
    x_min = float(np.min(np.abs(xc)))
    k = [c for c in res.collisions if c.kind == "hizli_carpma"]
    assert len(k) == 1
    assert (k[0].k, k[0].op) == (2, 0)
    assert k[0].depth == pytest.approx(math.sqrt(R**2 - x_min**2) - 10.0, abs=1e-6)
    assert res.removed_volume > 0
    _kayitlar_gecerli(res)


def test_K7_havada_g0_kayit_yok():
    """Aynı dalış x = 25'e kadar (stok yüzeyi R = 20): çarpışma yok, hacim 0."""
    tp = _dalis_yolu(270.0)
    tp.moves[1] = Move(G0, (25.0, 0.0, -30.0), axis=(1.0, 0.0, 0.0), c=270.0)
    res = simulate_mt([tp], STOK, profil(), cell=0.5)
    assert res.collisions == []
    assert res.removed_volume == pytest.approx(0.0, abs=1e-12)


CENE = CylinderStock(D=60.0, zmin=-55.0, zmax=-40.0, d=40.0)  # ayna çenesi halkası r ∈ [20, 30]


def test_K7_aynaya_giren_kama():
    """Kama z −46 → −30 (uç −49'a kadar): takım gövdesi x ≥ R − t = 16.5, |y| ≤ 3, çene bölgesinde
    (z ≤ −40) r ∈ [20, 30] halkasıyla çakışır → ayna_carpma."""
    M = profil()
    res = simulate_mt([_kama(-46.0, -30.0, M=M)], STOK, M, cell=0.5, fixtures=(CENE,))
    a = [c for c in res.collisions if c.kind == "ayna_carpma"]
    assert a
    assert all(c.op == 0 and c.depth > 1e-6 for c in a)
    _kayitlar_gecerli(res)


def test_K7_aynadan_uzak_kama_kayit_yok():
    """Kama z −30 → −12 (uçlar −33 … −9): çene z ≤ −40 → ayna_carpma yok."""
    M = profil()
    res = simulate_mt([_kama(-30.0, -12.0, M=M)], STOK, M, cell=0.5, fixtures=(CENE,))
    assert [c for c in res.collisions if c.kind == "ayna_carpma"] == []
