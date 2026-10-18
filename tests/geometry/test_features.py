"""SPEC 02 — geometry/features.py testleri (K1–K5). OCCT gerektirir.

Testler SPEC 02'deki teori ve arayüzden yazıldı; uygulama gövdeleri okunmadı.
Uydurma geometri: blok a×b×c = 100×60×30, delik d=10, cep 40×20 r=5 t=8, pah d=3.
Koordinat kuralı (SPEC 02): blok min köşesi orijinde; üst yüz z = c; delik / cep üstten −Z.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

pytest.importorskip("build123d", reason='build123d kurulu değil (pip install -e ".[cad]")')

from geometry.features import block, chamfer_top, cylinder, hole, pocket  # noqa: E402
from geometry.part import GeometryError, Part  # noqa: E402

pytestmark = pytest.mark.occt

A, B, C = 100.0, 60.0, 30.0  # blok kenarları [mm]
V0 = A * B * C  # V = a·b·c = 180000 mm³
S0 = 2 * (A * B + B * C + C * A)  # S = 2(ab + bc + ca) = 2(6000 + 1800 + 3000) = 21600 mm²

D_HOLE = 10.0  # delik çapı [mm]
HX, HY = 20.0, 30.0  # delik ekseni [mm]
T_BLIND = 12.0  # kör delik derinliği [mm]

PW, PL, PR, PT = 40.0, 20.0, 5.0, 8.0  # cep: X boyu, Y boyu, köşe yarıçapı, derinlik [mm]
PX, PY = 65.0, 30.0  # cep merkezi: x ∈ [45, 85], y ∈ [20, 40] (delikle çakışmaz)

D_CH = 3.0  # pah [mm]


# --- El hesabı yardımcıları (SPEC 02 "Teori") ---------------------------------------------------


def dV_hole(d: float, t: float) -> float:
    """Silindirik delik: ΔV = π d² t / 4."""
    return math.pi * d**2 * t / 4


def pocket_area(w: float, l: float, r: float) -> float:  # noqa: E741
    """Köşe yarıçaplı dikdörtgen taban alanı: A_c = w·l − (4 − π) r² (4 köşe kare − çeyrek daire)."""
    return w * l - (4 - math.pi) * r**2


def pocket_perimeter(w: float, l: float, r: float) -> float:  # noqa: E741
    """Çevre: P = 2(w + l) − (8 − 2π) r (8 düz parça r kısalır, 4 çeyrek yay 2π r ekler)."""
    return 2 * (w + l) - (8 - 2 * math.pi) * r


def dV_chamfer_block(a: float, b: float, d: float) -> float:
    """Blok üst kenarları pahı: ΔV = (d²/2)·2(a + b) − 4·d³/3 (köşe kesişimi ∫₀^d (d−w)² dw = d³/3)."""
    return (d**2 / 2) * 2 * (a + b) - 4 * d**3 / 3


def dV_chamfer_hole_rim(d_hole: float, d: float) -> float:
    """Delik ağzı pahı (iç kenar, 45° koni): kesit dik üçgen alanı d²/2, ağırlık merkezi yarıçapı
    R + d/3 (R = d_hole/2). Pappus–Guldin: ΔV = 2π (R + d/3) · d²/2 = π d² (R + d/3)."""
    R = d_hole / 2
    return math.pi * d**2 * (R + d / 3)


def dV_chamfer_pocket_rim(w: float, l: float, r: float, d: float) -> float:  # noqa: E741
    """Köşe yarıçaplı cep ağzı pahı (iç kenar): düz parçalar toplam 2(w + l − 4r) boyunca üçgen prizma
    (d²/2)·L; 4 çeyrek yay = tam tur, Pappus: π d² (r + d/3). Kenarlar teğet sürekli, köşe kesişimi yok."""
    return (d**2 / 2) * 2 * (w + l - 4 * r) + math.pi * d**2 * (r + d / 3)


def snapshot(p: Part) -> tuple[float, float, np.ndarray, np.ndarray]:
    lo, hi = p.bbox
    return p.volume, p.area, p.center_of_mass.copy(), np.concatenate([lo, hi])


# --- K1: block, cylinder -------------------------------------------------------------------------


def test_block_volume_area_com_bbox():
    """K1: V = abc = 180000 mm³, S = 2(ab+bc+ca) = 21600 mm², x̄ = (a/2, b/2, c/2) = (50, 30, 15),
    sınır kutusu [0,0,0]–[a,b,c] (min köşe orijinde)."""
    p = block(A, B, C)
    assert isinstance(p, Part)
    assert p.name == "blok"
    assert p.volume == pytest.approx(V0, rel=1e-6)
    assert p.area == pytest.approx(S0, rel=1e-6)
    np.testing.assert_allclose(p.center_of_mass, [A / 2, B / 2, C / 2], rtol=1e-6, atol=1e-6)
    lo, hi = p.bbox
    np.testing.assert_allclose(lo, [0.0, 0.0, 0.0], atol=1e-6)
    np.testing.assert_allclose(hi, [A, B, C], rtol=1e-6)


def test_block_custom_name():
    assert block(1.0, 2.0, 3.0, name="taslak").name == "taslak"


def test_cylinder_volume_area_com_bbox():
    """K1: r=20, h=50. V = π r² h = 20000π mm³; S = 2π r² + 2π r h = 800π + 2000π = 2800π mm².
    Taban merkezi orijinde, eksen +Z: x̄ = (0, 0, h/2) = (0, 0, 25); kutu [−r,−r,0]–[r,r,h]."""
    r, h = 20.0, 50.0
    p = cylinder(r, h)
    assert isinstance(p, Part)
    assert p.name == "silindir"
    assert p.volume == pytest.approx(math.pi * r**2 * h, rel=1e-6)
    assert p.area == pytest.approx(2 * math.pi * r**2 + 2 * math.pi * r * h, rel=1e-6)
    np.testing.assert_allclose(p.center_of_mass, [0.0, 0.0, h / 2], atol=1e-6)
    lo, hi = p.bbox
    np.testing.assert_allclose(lo, [-r, -r, 0.0], atol=1e-6)
    np.testing.assert_allclose(hi, [r, r, h], atol=1e-6)


@pytest.mark.parametrize("abc", [(0.0, 60.0, 30.0), (100.0, -1.0, 30.0), (100.0, 60.0, 0.0)])
def test_block_invalid_dims(abc):
    """K1: a, b, c > 0 değilse GeometryError."""
    with pytest.raises(GeometryError):
        block(*abc)


@pytest.mark.parametrize("rh", [(0.0, 10.0), (-5.0, 10.0), (5.0, 0.0), (5.0, -1.0)])
def test_cylinder_invalid_dims(rh):
    """K1: r, h > 0 değilse GeometryError."""
    with pytest.raises(GeometryError):
        cylinder(*rh)


# --- K2: hole ------------------------------------------------------------------------------------


def test_blind_hole_dV_dS_and_com_shift():
    """K2: kör delik d=10, t=12, eksen (20, 30).
    ΔV = π d² t / 4 = 300π ≈ 942.478 mm³; ΔS = π d t = 120π (taban dairesi ağız dairesini yerine koyar).
    Ağırlık merkezi: x̄ = (V₀ x̄₀ − ΔV x̄_d) / (V₀ − ΔV), x̄₀ = (50, 30, 15), x̄_d = (20, 30, c − t/2)."""
    p0 = block(A, B, C)
    p = hole(p0, HX, HY, D_HOLE, depth=T_BLIND)
    dV = dV_hole(D_HOLE, T_BLIND)
    assert p0.volume - p.volume == pytest.approx(dV, rel=1e-6)
    assert p.area - p0.area == pytest.approx(math.pi * D_HOLE * T_BLIND, rel=1e-6)
    com0 = np.array([A / 2, B / 2, C / 2])
    com_d = np.array([HX, HY, C - T_BLIND / 2])
    com = (V0 * com0 - dV * com_d) / (V0 - dV)
    np.testing.assert_allclose(p.center_of_mass, com, atol=1e-6)


def test_through_hole_dV_dS_and_com_shift():
    """K2: boydan boya delik (depth=None) d=10, c=30.
    ΔV = π d² c / 4 = 750π ≈ 2356.194 mm³; ΔS = π d c − 2·π d²/4 = 300π − 50π = 250π ≈ 785.398 mm².
    x̄_d = (20, 30, 15) → z̄ ve ȳ değişmez, x̄ = (V₀·50 − ΔV·20)/(V₀ − ΔV)."""
    p0 = block(A, B, C)
    p = hole(p0, HX, HY, D_HOLE)
    dV = dV_hole(D_HOLE, C)
    assert p0.volume - p.volume == pytest.approx(dV, rel=1e-6)
    dS = math.pi * D_HOLE * C - 2 * math.pi * D_HOLE**2 / 4
    assert p.area - p0.area == pytest.approx(dS, rel=1e-6)
    com = (V0 * np.array([A / 2, B / 2, C / 2]) - dV * np.array([HX, HY, C / 2])) / (V0 - dV)
    np.testing.assert_allclose(p.center_of_mass, com, atol=1e-6)
    # sınır kutusu değişmez (delik içeride)
    lo, hi = p.bbox
    np.testing.assert_allclose(lo, [0.0, 0.0, 0.0], atol=1e-6)
    np.testing.assert_allclose(hi, [A, B, C], atol=1e-6)


def test_hole_depth_equal_height_is_through():
    """depth = c sınırda geçerli (depth > yükseklik hata, = değil): ΔV = π d² c / 4."""
    p0 = block(A, B, C)
    p = hole(p0, HX, HY, D_HOLE, depth=C)
    assert p0.volume - p.volume == pytest.approx(dV_hole(D_HOLE, C), rel=1e-6)


def test_hole_on_cylinder_axis():
    """Silindir (r=20, h=50) ekseninde d=10, t=15 kör delik: üst yüz z = h = 50.
    ΔV = π·10²·15/4 = 375π; ΔS = π d t = 150π; x̄ = (0, 0, (V₀·25 − ΔV·(50 − 7.5)) / (V₀ − ΔV))."""
    r, h, d, t = 20.0, 50.0, 10.0, 15.0
    p0 = cylinder(r, h)
    p = hole(p0, 0.0, 0.0, d, depth=t)
    Vc = math.pi * r**2 * h
    dV = dV_hole(d, t)
    assert p0.volume - p.volume == pytest.approx(dV, rel=1e-6)
    assert p.area - p0.area == pytest.approx(math.pi * d * t, rel=1e-6)
    z = (Vc * h / 2 - dV * (h - t / 2)) / (Vc - dV)
    np.testing.assert_allclose(p.center_of_mass, [0.0, 0.0, z], atol=1e-6)


@pytest.mark.parametrize(
    "kw",
    [
        {"d": 0.0},  # d <= 0
        {"d": -10.0},
        {"d": 10.0, "depth": 0.0},  # depth <= 0
        {"d": 10.0, "depth": -5.0},
        {"d": 10.0, "depth": C + 1.0},  # depth > yükseklik
    ],
)
def test_hole_invalid_args(kw):
    """K2: geçersiz delik → GeometryError."""
    with pytest.raises(GeometryError):
        hole(block(A, B, C), HX, HY, **kw)


def test_hole_outside_part_rejected():
    """K2: parçanın tamamen dışındaki delik malzeme kaldırmaz (ΔV = 0 ≤ 1e-9) → GeometryError."""
    with pytest.raises(GeometryError):
        hole(block(A, B, C), 500.0, 500.0, D_HOLE)


# --- K3: pocket ----------------------------------------------------------------------------------


def test_pocket_sharp_corners():
    """K3, r = 0: A_c = w·l = 800 mm², ΔV = A_c·t = 6400 mm³; P = 2(w + l) = 120 mm, ΔS = P·t = 960 mm².
    Cep merkezi (65, 30, c − t/2): x̄ = (V₀ x̄₀ − ΔV x̄_c)/(V₀ − ΔV)."""
    p0 = block(A, B, C)
    p = pocket(p0, PX, PY, PW, PL, PT)
    dV = PW * PL * PT
    assert p0.volume - p.volume == pytest.approx(dV, rel=1e-6)
    assert p.area - p0.area == pytest.approx(2 * (PW + PL) * PT, rel=1e-6)
    com = (V0 * np.array([A / 2, B / 2, C / 2]) - dV * np.array([PX, PY, C - PT / 2])) / (V0 - dV)
    np.testing.assert_allclose(p.center_of_mass, com, atol=1e-6)


def test_pocket_rounded_corners():
    """K3, r = 5: A_c = 800 − (4 − π)·25 ≈ 778.540 mm², ΔV = A_c·t ≈ 6228.319 mm³;
    P = 120 − (8 − 2π)·5 ≈ 111.416 mm, ΔS = P·t ≈ 891.327 mm². (Çift simetrik cep: ağırlık merkezi
    (65, 30, c − t/2).)"""
    p0 = block(A, B, C)
    p = pocket(p0, PX, PY, PW, PL, PT, r=PR)
    dV = pocket_area(PW, PL, PR) * PT
    assert p0.volume - p.volume == pytest.approx(dV, rel=1e-6)
    assert p.area - p0.area == pytest.approx(pocket_perimeter(PW, PL, PR) * PT, rel=1e-6)
    com = (V0 * np.array([A / 2, B / 2, C / 2]) - dV * np.array([PX, PY, C - PT / 2])) / (V0 - dV)
    np.testing.assert_allclose(p.center_of_mass, com, atol=1e-6)


def test_pocket_max_radius_slot():
    """K3 sınır: r = min(w, l)/2 = 10 geçerli (kanal / obround). A_c = 800 − (4 − π)·100 ≈ 714.159;
    P = 120 − (8 − 2π)·10 ≈ 102.832. Formül r = min/2'de de geçerlidir (düz kısa kenar boyu 0)."""
    r = min(PW, PL) / 2
    p0 = block(A, B, C)
    p = pocket(p0, PX, PY, PW, PL, PT, r=r)
    assert p0.volume - p.volume == pytest.approx(pocket_area(PW, PL, r) * PT, rel=1e-6)
    assert p.area - p0.area == pytest.approx(pocket_perimeter(PW, PL, r) * PT, rel=1e-6)


@pytest.mark.parametrize(
    "kw",
    [
        {"depth": C},  # depth >= yükseklik: cep deler
        {"depth": C + 5.0},
        {"depth": 0.0},  # depth <= 0
        {"depth": -1.0},
        {"depth": PT, "r": min(PW, PL) / 2 + 0.5},  # r > min(w, l)/2
        {"depth": PT, "r": -1.0},  # r < 0
    ],
)
def test_pocket_invalid_args(kw):
    """K3: delen cep, sıfır / negatif derinlik, büyük veya negatif r → GeometryError."""
    with pytest.raises(GeometryError):
        pocket(block(A, B, C), PX, PY, PW, PL, **kw)


# --- K4: chamfer_top -----------------------------------------------------------------------------


def test_chamfer_top_block():
    """K4: a=100, b=60, d=3. ΔV = (d²/2)·2(a + b) − 4d³/3 = 4.5·320 − 36 = 1404 mm³ (SPEC: OCCT ön deneme
    1404.000). Pah üst kenarları keser; sınır kutusu değişmez (alt kenarlar ve yan yüzler yerinde)."""
    p0 = block(A, B, C)
    p = chamfer_top(p0, D_CH)
    assert dV_chamfer_block(A, B, D_CH) == pytest.approx(1404.0, abs=1e-12)
    assert p0.volume - p.volume == pytest.approx(1404.0, rel=1e-6)
    lo, hi = p.bbox
    np.testing.assert_allclose(lo, [0.0, 0.0, 0.0], atol=1e-6)
    np.testing.assert_allclose(hi, [A, B, C], atol=1e-6)


@pytest.mark.parametrize("d", [0.0, -1.0, 35.0])
def test_chamfer_top_invalid(d):
    """K4: d <= 0 veya aşırı büyük pah (d = 35 > c = 30 ve > b/2 = 30) → GeometryError."""
    with pytest.raises(GeometryError):
        chamfer_top(block(A, B, C), d)


# --- K5: girdi değişmez, zincir ------------------------------------------------------------------


def test_operations_do_not_modify_input():
    """K5: her işlem yeni Part döner; girdinin V, S, x̄, sınır kutusu aynı kalır."""
    p0 = block(A, B, C)
    before = snapshot(p0)
    results = [
        hole(p0, HX, HY, D_HOLE),
        hole(p0, HX, HY, D_HOLE, depth=T_BLIND),
        pocket(p0, PX, PY, PW, PL, PT, r=PR),
        chamfer_top(p0, D_CH),
    ]
    after = snapshot(p0)
    assert after[0] == pytest.approx(before[0], rel=1e-12)
    assert after[1] == pytest.approx(before[1], rel=1e-12)
    np.testing.assert_allclose(after[2], before[2], atol=1e-12)
    np.testing.assert_allclose(after[3], before[3], atol=1e-12)
    for r in results:
        assert isinstance(r, Part)
        assert r is not p0
        assert r.volume < p0.volume


def test_chain_block_hole_pocket_volume():
    """K5: blok → boydan delik → cep (r=5): V = abc − π d² c/4 − A_c·t (bölgeler ayrık, ΔV'ler toplanır)."""
    p = pocket(hole(block(A, B, C), HX, HY, D_HOLE), PX, PY, PW, PL, PT, r=PR)
    V = V0 - dV_hole(D_HOLE, C) - pocket_area(PW, PL, PR) * PT
    assert p.volume == pytest.approx(V, rel=1e-6)


def test_chain_block_hole_pocket_chamfer_volume():
    """K5: blok → delik → cep → pah. SPEC: pah üst yüzün (zmax) TÜM kenarlarına uygulanır; işlenmiş
    parçada üst yüzün kenarları: dış dikdörtgen + delik ağzı + cep ağzı. Pah ΔV'si (el hesabı):
      dış: (d²/2)·2(a+b) − 4d³/3 = 1404
      delik ağzı (Pappus): π d² (R + d/3), R = 5            → 9π·6 = 54π ≈ 169.646
      cep ağzı: (d²/2)·2(w + l − 4r) + π d² (r + d/3)       → 4.5·80 + 54π ≈ 529.646
    V = abc − π d_h² c/4 − A_c t − ΣΔV_pah ≈ 180000 − 2356.194 − 6228.319 − 2103.292.
    (Ön deneme build123d ile: pah ΔV 2103.2920066, formülle 1e-12 tutuyor.)"""
    p1 = hole(block(A, B, C), HX, HY, D_HOLE)
    p2 = pocket(p1, PX, PY, PW, PL, PT, r=PR)
    p3 = chamfer_top(p2, D_CH)
    dV_ch = (
        dV_chamfer_block(A, B, D_CH)
        + dV_chamfer_hole_rim(D_HOLE, D_CH)
        + dV_chamfer_pocket_rim(PW, PL, PR, D_CH)
    )
    assert p2.volume - p3.volume == pytest.approx(dV_ch, rel=1e-6)
    V = V0 - dV_hole(D_HOLE, C) - pocket_area(PW, PL, PR) * PT - dV_ch
    assert p3.volume == pytest.approx(V, rel=1e-6)
    # zincirde ara parçalar değişmedi
    assert p1.volume == pytest.approx(V0 - dV_hole(D_HOLE, C), rel=1e-6)
