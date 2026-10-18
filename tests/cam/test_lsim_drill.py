"""SPEC 22 K19 — eksenel takım (SPEC 40 ek E4: matkap, punta matkabı) ile tornada delme.

Testler SPEC 22 "Eksenel takım" bölümünden yazıldı; cam.sim kodu okunmadı.

Kaynaklar (SPEC 22, E4):
- Takım iş mili ekseninde (x = 0), programlanan nokta takım ucu (C = P), −Z yönünde ilerler.
- Kesici bölge (z, x), uca göre, r = 0: core = (0, 0), (L_uç, D/2), (L_f, D/2), (L_f, −D/2), (L_uç, −D/2);
  L_uç = (D/2) / tan(φ/2), tip_angle = None → L_uç = 0 (dikdörtgen); L_uç ≥ L_f → CamError.
- Gövde = sap [L_f, ∞) × [−d_s/2, d_s/2] (d_s = Tool.shank); malzemeyle çakışması kenar_asimi.
- Taraf kuralı yok (side yok sayılır); to_radial aralığı [0, D/2].
- Yolun bütün noktaları |x| ≤ 1e-9, yay yok; FLAT / BALL → CamError.
- Gövde denetimi alt adımın kesici süpürmesi çıkarıldıktan sonraki malzemeyle yapılır (11:28 onaylı ek).
"""

from __future__ import annotations

import functools
import math

import numpy as np
import pytest

from cam.model import CamError, CylinderStock, Move, MoveType, Tool, ToolKind
from cam.sim import cutter_shape, simulate_lathe
from tests.cam.lsimref import G0, G1, centers, lpath

STOK = CylinderStock(D=40.0, zmin=-50.0, zmax=0.0)
CELL = 0.5
D = 8.0
R = D / 2
PHI = 118.0
L_UC = R / math.tan(math.radians(PHI) / 2)  # 2.4034…
H = 20.3  # delik derinliği (uç); hücre sınırlarına denk gelmez


def _matkap(L_f: float = 40.0, phi: float | None = PHI, shank_d: float | None = None, D_: float = D) -> Tool:
    return Tool(10, "matkap", ToolKind.DRILL, D_, L_f, shank_d=shank_d, tip_angle=phi)


def _delme(tool: Tool, derinlik: float):
    """Eksende yaklaşma, H derinliğe G1 delme, G0 geri çıkış: k = 1, 2, 3."""
    return lpath(tool, (0.0, 5.0), [G0(0.0, 2.0), G1(0.0, -derinlik, F=0.1), G0(0.0, 5.0)])


def _ayni_kume(P, beklenen: np.ndarray, tol: float = 1e-12) -> None:
    """P'nin satırları beklenen noktaların bir permütasyonu (tol içinde)."""
    P = np.asarray(P, dtype=float)
    assert P.shape == beklenen.shape
    kalan = list(range(len(beklenen)))
    for p in P:
        d = [np.max(np.abs(p - beklenen[j])) for j in kalan]
        j = int(np.argmin(d))
        assert d[j] <= tol, f"{p} beklenen köşelerde yok: {beklenen}"
        kalan.pop(j)


def _dogrusal_olmayan(P) -> np.ndarray:
    """Komşularıyla aynı doğru üzerindeki köşeleri at (dikdörtgende (0, 0) verilmiş olabilir)."""
    P = np.asarray(P, dtype=float)
    n = len(P)
    tut = []
    for i in range(n):
        a, b, c = P[i - 1], P[i], P[(i + 1) % n]
        u, v = b - a, c - b
        if abs(u[0] * v[1] - u[1] * v[0]) > 1e-12:
            tut.append(i)
    return P[tut]


@functools.cache
def _dolu():
    # fixture değil: simülasyon test gövdesinde çağrılsın (uygulanmamış kod "uygulanmamış" sayılsın)
    return simulate_lathe([_delme(_matkap(), H)], STOK, cell=CELL)


# ------------------------------------------------------------------ cutter_shape


def test_K19_matkap_besgen():
    s = cutter_shape(_matkap(), None)
    beklenen = np.array([[0.0, 0.0], [L_UC, R], [40.0, R], [40.0, -R], [L_UC, -R]])
    _ayni_kume(s.core, beklenen)
    assert s.r == 0.0


def test_K19_konik_takim_besgen():
    """CONE D = 6, φ = 90° → L_uç = 3."""
    t = Tool(11, "punta", ToolKind.CONE, 6.0, 10.0, tip_angle=90.0)
    s = cutter_shape(t, None)
    beklenen = np.array([[0.0, 0.0], [3.0, 3.0], [10.0, 3.0], [10.0, -3.0], [3.0, -3.0]])
    _ayni_kume(s.core, beklenen)
    assert s.r == 0.0


def test_K19_uc_acisi_yok_dikdortgen():
    s = cutter_shape(_matkap(phi=None), None)
    beklenen = np.array([[0.0, R], [40.0, R], [40.0, -R], [0.0, -R]])
    _ayni_kume(_dogrusal_olmayan(s.core), beklenen)
    assert s.r == 0.0


def test_K19_taraf_yok_sayilir():
    t = _matkap()
    s0 = np.asarray(cutter_shape(t, None).core, dtype=float)
    for side in ("dis", "ic"):
        np.testing.assert_array_equal(np.asarray(cutter_shape(t, side).core, dtype=float), s0)


def test_K19_govde_sap():
    """Gövde = sap [L_f, ∞) × [−d_s/2, d_s/2] (kesilmiş); tutucu kullanılmaz."""
    s = cutter_shape(_matkap(L_f=15.0, shank_d=10.0), None)
    B = np.asarray(s.body, dtype=float)
    assert B.min(axis=0)[0] == pytest.approx(15.0, abs=1e-12)
    assert B.max(axis=0)[0] > 15.0
    assert B.min(axis=0)[1] == pytest.approx(-5.0, abs=1e-12)
    assert B.max(axis=0)[1] == pytest.approx(5.0, abs=1e-12)
    assert s.holder is None


def test_K19_uc_boyu_kesici_boydan_uzun():
    """DRILL D = 8, φ = 20° → L_uç = 4 / tan 10° = 22.7 ≥ L_f = 20 → CamError."""
    with pytest.raises(CamError):
        cutter_shape(_matkap(L_f=20.0, phi=20.0), None)


# ------------------------------------------------------------------ dolu çubuğa delik


def test_K19_dolu_cubuk_hacim():
    sonuc = _dolu()
    beklenen = math.pi * R**2 * (H - L_UC) + math.pi * R**2 * L_UC / 3
    assert sonuc.removed_volume == pytest.approx(beklenen, abs=math.pi * R**2 * sonuc.rmap.dz)
    assert sonuc.removed_volume == pytest.approx(STOK.volume - sonuc.rmap.volume(), rel=1e-9)
    assert sonuc.collisions == []


def test_K19_delik_hucreleri():
    """z_i > −H + L_uç: [(D/2, 20)]; koni bölgesinde iç yarıçap (z_i + H)·(D/2)/L_uç;
    z_i < −H dokunulmamış."""
    sonuc = _dolu()
    zc = centers(STOK, CELL)
    assert sonuc.rmap.nz == len(zc)
    n_delik = n_koni = 0
    for i, z in enumerate(zc):
        iv = list(sonuc.rmap.intervals(i))
        if z < -H:
            assert iv == [(0.0, 20.0)], f"z = {z}"
            continue
        rho = R if z > -H + L_UC else (z + H) * R / L_UC
        n_delik += z > -H + L_UC
        n_koni += z <= -H + L_UC
        assert len(iv) == 1, f"z = {z}"
        assert iv[0][0] == pytest.approx(rho, abs=1e-9)
        assert iv[0][1] == pytest.approx(20.0, abs=1e-12)
    assert n_delik == 36 and n_koni == 5


def test_K19_boruda_delme_farkla():
    """Boru d = 6: kaldırılan = π(R² − 3²)(H − L_uç) + ∫_{h₃}^{L_uç} π((h·R/L_uç)² − 3²) dh, h₃ = 3·L_uç/R."""
    boru = CylinderStock(D=40.0, zmin=-50.0, zmax=0.0, d=6.0)
    sonuc = simulate_lathe([_delme(_matkap(), H)], boru, cell=CELL)
    h3 = 3.0 * L_UC / R
    koni = math.pi * ((R / L_UC) ** 2 * (L_UC**3 - h3**3) / 3 - 9.0 * (L_UC - h3))
    beklenen = math.pi * (R**2 - 9.0) * (H - L_UC) + koni
    assert sonuc.removed_volume == pytest.approx(beklenen, abs=math.pi * R**2 * sonuc.rmap.dz)
    fark = _dolu().removed_volume - sonuc.removed_volume
    assert fark == pytest.approx(
        math.pi * 9.0 * (H - h3) + math.pi * R**2 * h3**3 / (3 * L_UC**2), abs=2 * math.pi * R**2 * CELL
    )
    assert sonuc.collisions == []


# ------------------------------------------------------------------ sap malzemeye giriyor


def test_K19_sap_malzemeye_giriyor():
    """L_f = 15, d_s = 10, H = 20: sap z ∈ [−5, 0]'da delik duvarına (r = 4) girer, depth = 5 − 4 = 1."""
    sonuc = simulate_lathe([_delme(_matkap(L_f=15.0, shank_d=10.0), 20.0)], STOK, cell=CELL)
    k = [c for c in sonuc.collisions if c.kind == "kenar_asimi" and c.k == 2]
    assert len(k) == 1
    assert k[0].depth == pytest.approx(1.0, abs=1e-9)
    assert -5.0 <= k[0].at[2] <= 0.0
    assert all(c.kind == "kenar_asimi" for c in sonuc.collisions)


def test_K19_sap_malzemeye_girmiyor():
    """Aynı takım, H = 12 < L_f: sap stok yüzünün (z = 0) üstünde kalır → kayıt yok."""
    sonuc = simulate_lathe([_delme(_matkap(L_f=15.0, shank_d=10.0), 12.0)], STOK, cell=CELL)
    assert sonuc.collisions == []


# ------------------------------------------------------------------ hatalar


@pytest.mark.parametrize("kind", [ToolKind.FLAT, ToolKind.BALL])
def test_K19_freze_takimi_hata(kind):
    t = Tool(12, "freze", kind, 8.0, 30.0)
    with pytest.raises(CamError):
        simulate_lathe([_delme(t, H)], STOK, cell=CELL)


def test_K19_baslangic_eksende_degil():
    yol = lpath(_matkap(), (0.5, 5.0), [G0(0.0, 2.0), G1(0.0, -10.0, F=0.1)])
    with pytest.raises(CamError):
        simulate_lathe([yol], STOK, cell=CELL)


def test_K19_nokta_eksende_degil():
    yol = lpath(_matkap(), (0.0, 5.0), [G0(0.0, 2.0), G1(1e-6, -10.0, F=0.1)])
    with pytest.raises(CamError):
        simulate_lathe([yol], STOK, cell=CELL)


def test_K19_eksen_toleransi_icinde():
    """|x| = 5e-10 ≤ 1e-9 kabul."""
    yol = lpath(_matkap(), (0.0, 5.0), [G0(5e-10, 2.0), G1(-5e-10, -10.0, F=0.1), G0(0.0, 5.0)])
    sonuc = simulate_lathe([yol], STOK, cell=CELL)
    assert sonuc.removed_volume > 0


def test_K19_yayli_yol_hata():
    """Uçları eksende yay (ZX, merkez (x, z) = (0, 0)) → CamError."""
    yay = Move(MoveType.ARC_CW, (0.0, 0.0, -2.0), 0.1, center=(0.0, 0.0))
    yol = lpath(_matkap(), (0.0, 5.0), [G0(0.0, 2.0), yay])
    with pytest.raises(CamError):
        simulate_lathe([yol], STOK, cell=CELL)
