"""SPEC 22 K11–K14 — hızlı çarpma, kesici kenar boyu aşımı, tutucu ve ayna çarpışması.

Testler SPEC 22 "Çarpışma ve çakma denetimleri" bölümünden yazıldı; cam.sim kodu okunmadı.

Kaynaklar (SPEC 22):
- Hücre başına çakışma derinliği: iki aralık listesinin kesişiminin en uzun parçası (r yönünde).
  Aynı (kind, k) için tek kayıt (en büyük depth); eşik tol = 1e-6 mm.
- hizli_carpma: G0 adımının (bağlantı dahil) bir hücrede kaldırdığı en uzun parça; malzeme yine kaldırılır.
- kenar_asimi: gövde uzantısı B = Q_B ⊕ D(r) süpürmesi malzemeyle çakışırsa (Q_B: s, t ≥ 0, s + t ≥ l).
- tutucu_carpma: tutucu H süpürmesi (y yarı kalınlığı b ile üst uç √(x² + b²)) malzemeyle çakışırsa.
- ayna_carpma: kesici, gövde veya tutucu süpürmesi bağlama elemanının [d/2, D/2] aralığıyla çakışırsa;
  bağlama elemanı malzeme değildir, kaldırılmaz.
- Gövde / tutucu / ayna denetimi alt adımın kesici süpürmesi çıkarıldıktan sonraki malzemeyle
  yapılır (11:28 onaylı ek).
- Gövde uzantısı B takımın yarı düzlemine kırpılır: a ← max(a, 0), to_radial'dan önce (11:28 onaylı ek).
- Takım T = 3: C = P − q_T, q_T = r·(−1, −1) (z, x) → C = P + (r, r).
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from cam.lathe_ops import TurnCut, turn
from cam.model import CylinderStock, LatheHolder, Setup, Wcs
from cam.sim import simulate_lathe
from tests.cam.lsimref import G0, G1, bore_tool, e, lpath, sweep_x, turn_core, turn_tool

R_N = 0.8
STOK = CylinderStock(D=40.0, zmin=-50.0, zmax=0.0)


def _tur(sonuc, kind: str) -> list:
    return [c for c in sonuc.collisions if c.kind == kind]


def _gecerli_kayitlar(sonuc) -> None:
    kinds = {"hizli_carpma", "kenar_asimi", "tutucu_carpma", "ayna_carpma", "cakma"}
    ks = [c.k for c in sonuc.collisions]
    assert ks == sorted(ks)
    goruldu = set()
    for c in sonuc.collisions:
        assert c.kind in kinds
        assert (c.kind, c.k) not in goruldu  # aynı (kind, k) için tek kayıt
        goruldu.add((c.kind, c.k))
        assert c.depth > 1e-6
        assert c.at[1] == 0.0


# ------------------------------------------------------------------ K11 hızlı çarpma


def test_K11_stogun_icinden_G0():
    """G0 ile radyal dalış, burun merkezi z = −1.25 hücre merkezinde: geçilen radyal kalınlık 20 − 15 = 5."""
    # P = (15, −2.05) → C = (z, x) = (−1.25, 15.8), burun alt ucu x = 15 (cell = 0.5 → hücre merkezi −1.25)
    yol = lpath(
        turn_tool(R_N), (25.0, 5.0), [G0(25.0, -2.05), G0(15.0, -2.05), G0(25.0, -2.05), G0(25.0, 5.0)]
    )
    sonuc = simulate_lathe([yol], STOK, cell=0.5)
    _gecerli_kayitlar(sonuc)
    h = _tur(sonuc, "hizli_carpma")
    assert len(h) == 1
    assert h[0].k == 2 and h[0].op == 0
    assert h[0].depth == pytest.approx(5.0, abs=1e-9)
    assert h[0].at[2] == pytest.approx(-1.25, abs=1e-12)
    assert sonuc.removed_volume > 0  # malzeme yine kaldırılır
    i = int(np.argmin(np.abs(sonuc.rmap.centers() + 1.25)))
    assert sonuc.rmap.intervals(i) == [pytest.approx((0.0, 15.0), abs=1e-9)]


def test_K11_stok_disindan_G0_kayit_yok():
    yol = lpath(turn_tool(R_N), (25.0, 5.0), [G0(25.0, -30.0), G0(21.0, -30.0), G0(21.0, 5.0), G0(25.0, 5.0)])
    sonuc = simulate_lathe([yol], STOK, cell=0.5)
    assert sonuc.collisions == []
    assert sonuc.removed_volume == 0.0


def test_K11_malzemeden_gecen_baglanti():
    """1. yol (16, −2.05)'te biter; 2. yol (25, −30)'da başlar: aradaki G0 bağlantısı malzemeyi keser."""
    y1 = lpath(turn_tool(R_N), (25.0, 5.0), [G0(25.0, -2.05), G1(16.0, -2.05)], name="dalis")
    y2 = lpath(turn_tool(R_N), (25.0, -30.0), [G0(25.0, 5.0)], name="donus")
    sonuc = simulate_lathe([y1, y2], STOK, cell=0.5)
    _gecerli_kayitlar(sonuc)
    assert [s.link for s in sonuc.steps] == [False, False, True, False]
    h = _tur(sonuc, "hizli_carpma")
    assert len(h) == 1
    assert h[0].k == 3 and h[0].op == 1
    assert sonuc.steps[2].link and sonuc.steps[2].removed > 0


# ------------------------------------------------------------------ K12 kesici kenar boyu


def _boyuna(a_p: float, edge: float = 4.0):
    """Dolu çubukta a_p derinliğinde tek boyuna paso: P_x = 20 − a_p, z: 5 → −55 (stoğun arkasından çıkar;
    geri dönüş kesilmeyen şeride değmesin)."""
    x = 20.0 - a_p
    yol = lpath(
        turn_tool(R_N, edge=edge), (25.0, 5.0), [G0(x, 5.0), G1(x, -55.0), G0(25.0, -55.0), G0(25.0, 5.0)]
    )
    return simulate_lathe([yol], STOK, cell=0.5)


def test_K12_kenar_boyu_asimi():
    """l = 4, a_p = 6: ana kenar burundan l·e₁ = l·(−cos 93°, sin 93°) köşesine kadar keser; köşe
    dairesinin tepesi x = C_x + l·sin 93° + r = 14.8 + 3.9945 + 0.8 = 19.594 < 20. Bu üstteki şerit
    (kapalı form 20 − 19.594 = 0.4055) kesilmez ve gövde ona her hücrede dokunur. Alt adımdan önceki
    malzemeyle denetim yüzünden öndeki hücrede derinlik bundan büyük olabilir (SPEC 22 bilinen sınır),
    bu yüzden kapalı form alt sınırdır."""
    sonuc = _boyuna(6.0)
    _gecerli_kayitlar(sonuc)
    k = _tur(sonuc, "kenar_asimi")
    assert len(k) == 1 and k[0].k == 2
    C_x = 14.0 + R_N
    serit = 20.0 - (C_x + 4.0 * e(93.0)[1] + R_N)
    assert serit == pytest.approx(0.4055, abs=1e-3)
    assert serit - 1e-9 <= k[0].depth <= 6.0
    # kesilmeyen şerit son haritada kalır: boyuna pasonun ortasında [0, 14] ∪ [19.594, 20]
    zc = sonuc.rmap.centers()
    i = int(np.argmin(np.abs(zc + 10.25)))
    iv = sonuc.rmap.intervals(i)
    assert iv == [pytest.approx((0.0, 14.0), abs=1e-9), pytest.approx((20.0 - serit, 20.0), abs=1e-9)]


def test_K12_kenar_boyu_icinde_kayit_yok():
    sonuc = _boyuna(3.0)
    assert _tur(sonuc, "kenar_asimi") == []
    assert sonuc.collisions == []


# ------------------------------------------------------------------ K13 tutucu


# Burun merkezine göre (z, x) dikdörtgen: burnun 1.5–5 mm önünde, x ≥ 2 (K: z ≥ −r = −0.8, kesişmez)
ON_TUTUCU = LatheHolder("on_blok", ((-5.0, 2.0), (-1.5, 2.0), (-1.5, 30.0), (-5.0, 30.0)), half_width=10.0)


def _omuz_programi(holder: LatheHolder | None):
    """1. yol: x_f = 16, z_end = −20 boy tornalama (z < −20'de 20 yarıçaplı yüksek omuz kalır).
    2. yol: burun alt ucu x = 17'de (kesmeden) omuza doğru; C_z = −16'da durur (burun omuza değmez).
    Tutucu alt yüzü C_x + 2 = 17.8 + 2 = 19.8 → omuz hücrelerinde (z ∈ [−21, −20])
    derinlik 20 − 19.8 = 0.2."""
    y1 = turn(STOK, turn_tool(R_N, id=1), TurnCut(feed=0.2, rpm=1000.0, a_p=2.0), 16.0, -20.0)
    y2 = lpath(
        turn_tool(R_N, holder=holder, id=2), (25.0, 5.0), [G0(17.0, 5.0), G1(17.0, -16.8)], name="yaklasma"
    )
    return simulate_lathe([y1, y2], STOK, cell=0.5)


def test_K13_tutucu_omuza_carpar():
    sonuc = _omuz_programi(ON_TUTUCU)
    _gecerli_kayitlar(sonuc)
    t = _tur(sonuc, "tutucu_carpma")
    assert len(t) == 1
    assert t[0].k == len(sonuc.steps) and t[0].op == 1
    assert t[0].depth == pytest.approx(0.2, abs=1e-9)
    assert -21.0 <= t[0].at[2] <= -20.0


def test_K13_tutucusuz_kayit_yok():
    sonuc = _omuz_programi(None)
    assert _tur(sonuc, "tutucu_carpma") == []


def _bor_bari(hw: float):
    """Boru d = 20 (delik yarıçapı 10). Bor barı tutucusu dış çerçevede z ∈ [1, 30], x ∈ [7, 18];
    iç çerçevede aynalanır: gerçek x ∈ [C_x − 18, C_x − 7] = [−9.4, 1.6] (C_x = 8.6).
    Düzlemde |x| ≤ 9.4 < 10 (değmez); kalınlıkla r_üst = √(9.4² + hw²)."""
    boru = CylinderStock(D=40.0, zmin=-50.0, zmax=0.0, d=20.0)
    h = LatheHolder("bor_bari", ((1.0, 7.0), (30.0, 7.0), (30.0, 18.0), (1.0, 18.0)), half_width=hw)
    # T = 2: q = r·(−1, 1) → C = P + (r, −r); P_x = 9 → C_x = 8.6, burun üstü x = 9 < 10 (kesmez)
    yol = lpath(bore_tool(r=0.4, edge=6.0, holder=h), (9.0, 5.0), [G1(9.0, -20.0)])
    return simulate_lathe([yol], boru, cell=0.5)


def test_K13_bor_bari_kalinlikla_degiyor():
    sonuc = _bor_bari(4.0)
    t = _tur(sonuc, "tutucu_carpma")
    assert len(t) == 1 and t[0].k == 1
    assert t[0].depth == pytest.approx(math.hypot(9.4, 4.0) - 10.0, abs=1e-9)


def test_K13_bor_bari_ince_degmiyor():
    """hw = 3: √(9.4² + 3²) = 9.867 < 10 → kayıt yok."""
    sonuc = _bor_bari(3.0)
    assert _tur(sonuc, "tutucu_carpma") == []
    assert sonuc.removed_volume == 0.0


def test_K13_ic_tornalamada_kenar_asimi_yok():
    """BORE (l = 6) boru d = 20'de a_p = 2 boyuna paso: P_x = 12 → C_x = 11.6, burun üstü x = 12.
    İç çerçevede gövde uzantısı −x'e uzanıp ekseni geçer; kırpılmasa |x| ≥ 12 tarafında malzemeye değerdi
    (lsimref ile alt adımlı denetim: kırpmasız en uzun çakışma 8, kırpmalı 0). Kırpmayla kayıt yok."""
    boru = CylinderStock(D=40.0, zmin=-50.0, zmax=0.0, d=20.0)
    yol = lpath(
        bore_tool(r=0.4, edge=6.0), (9.0, 5.0), [G0(12.0, 2.0), G1(12.0, -20.0), G1(9.0, -20.0), G0(9.0, 5.0)]
    )
    sonuc = simulate_lathe([yol], boru, cell=0.5)
    assert _tur(sonuc, "kenar_asimi") == []
    assert sonuc.collisions == []
    for i in range(sonuc.rmap.nz):
        z = sonuc.rmap.z0 + (i + 0.5) * sonuc.rmap.dz
        if -19.5 <= z <= 0.0:
            iv = list(sonuc.rmap.intervals(i))
            assert len(iv) == 1 and iv[0][0] == pytest.approx(12.0, abs=1e-9), f"z = {z}"


# ------------------------------------------------------------------ K14 ayna


CENE = CylinderStock(D=60.0, zmin=-65.0, zmax=-40.0, d=40.0)  # ayna çenesi halkası, stoğun altına taşar
AYNA_STOK = CylinderStock(D=40.0, zmin=-60.0, zmax=0.0)
KURULUM = Setup("ayna", Wcs(), AYNA_STOK, fixtures=[CENE])


def _ayna_yolu(z_end: float):
    """a_p = 2 boyuna paso (P_x = 18, C_x = 18.8) z_end'e kadar, sonra çapraz G0 geri dönüş
    (Δx = 7, Δz = 1.9)."""
    yol = lpath(
        turn_tool(R_N), (25.0, 5.0), [G0(18.0, 5.0), G1(18.0, z_end), G0(25.0, z_end + 1.9), G0(25.0, 5.0)]
    )
    return simulate_lathe([yol], KURULUM, cell=0.5)


def _sol_kenar_x(C: np.ndarray, z: float) -> float:
    """K'nin sol (−Z) sınırı, ana kenarın r ötelemesi: C + s·e₁ + r·n, n = (−e₁x, e₁z); z doğrusunda x."""
    e1 = e(93.0)
    n = np.array([-e1[1], e1[0]])
    s = (z - C[0] - R_N * n[0]) / e1[0]
    assert 0.0 <= s <= 8.0
    return float(C[1] + R_N * n[1] + s * e1[1])


def test_K14_ayna_cenesine_yakin_paso():
    """P_z = −40.4 → C = (−39.6, 18.8); burnun −Z ucu −40.4 çene yüzünü (−40) geçer.
    Hücre z = −40.25'te K: alt uç burun dairesinden, üst uç ana kenar doğrusundan; çene [20, 30] ile çakışma
    üst uç − 20 (kapalı form). Hücre −40.75 burun dairesinin dışında. Gövde ve tutucu bu doğruya ulaşmaz
    (gövdenin sol sınırı z ≥ C_z − 0.38). Geri dönüşün derinliği süpürmenin kesin üst ucundan (lsimref)."""
    sonuc = _ayna_yolu(-40.4)
    _gecerli_kayitlar(sonuc)
    a = _tur(sonuc, "ayna_carpma")
    assert [c.k for c in a] == [2, 3]  # boyuna paso ve çeneden geçen G0 geri dönüşü
    core = turn_core(turn_tool(R_N))
    C0, C1, C2 = np.array([5.8, 18.8]), np.array([-39.6, 18.8]), np.array([-37.7, 25.8])
    d1 = _sol_kenar_x(C1, -40.25) - 20.0
    _, b1 = sweep_x(core, R_N, C0, C1, [-40.25])
    assert b1[0] - 20.0 == pytest.approx(d1, abs=1e-12)
    assert a[0].depth == pytest.approx(d1, abs=1e-9)
    assert a[0].at[2] == pytest.approx(-40.25, abs=1e-12)
    _, b2 = sweep_x(core, R_N, C1, C2, [-40.25])
    assert a[1].depth == pytest.approx(b2[0] - 20.0, abs=1e-9)
    assert a[1].at[2] == pytest.approx(-40.25, abs=1e-12)


def test_K14_ayna_malzemesi_hacimden_dusulmez():
    sonuc = _ayna_yolu(-40.4)
    assert sonuc.rmap.volume() + sonuc.removed_volume == pytest.approx(AYNA_STOK.volume, rel=1e-9)
    zc = sonuc.rmap.centers()
    assert np.sum(zc < -60.0) == 10  # n_alt = ⌈5/0.5⌉
    for i in np.nonzero(zc < -60.0)[0]:
        assert sonuc.rmap.intervals(int(i)) == []


def test_K14_guvenli_z_end_kayit_yok():
    sonuc = _ayna_yolu(-38.5)
    assert sonuc.collisions == []
