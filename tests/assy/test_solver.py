"""SPEC 08 — assy/solver.py testleri: Gauss–Newton konum çözücü ve serbestlik sayımı (K4–K13).

Testler sadece specs/08-kisitlar.md'deki teori ve arayüzden yazıldı; assy/solver.py gövdesi okunmadı.
Beklenen konumlar kapalı formda elle türetildi (her testin yorumunda). Başlangıç konumları beklenen
çözümden ≈20° dönük ve ≈10 mm kaçık seçildi: Gauss–Newton (en küçük normlu adım, Nocedal–Wright Böl. 10)
başlangıca en yakın çözümü bulur, bu yüzden başlangıç doğru dalın yakınında (90°'den uzak).
Eksik kısıtlı durumlarda tam T değil, kısıtın belirlediği büyüklükler kontrol edilir.

Toleranslar (SPEC 08): konum 1e-9 mm, yön 1e-9, özdeşlik 1e-12.
Kod henüz yokken (NotImplementedError) testler kök conftest.py ile "uygulanmamış" (xfail) sayılır.
"""

from __future__ import annotations

import copy
import math

import numpy as np
import pytest

from assy.mates import residual
from assy.model import (
    Assembly,
    AssyError,
    Component,
    Mate,
    MateKind,
    Ref,
    RefKind,
    is_rigid,
    rot_x,
    rot_z,
    transform,
)
from assy.solver import SolveResult, dof, residuals, solve

C, CON, DIS, ANG = MateKind.COINCIDENT, MateKind.CONCENTRIC, MateKind.DISTANCE, MateKind.ANGLE
TOL_POS = 1e-9  # mm
TOL_DIR = 1e-9  # birimsiz


# ---------------------------------------------------------------- yardımcılar


def plane(comp: str, origin=(0.0, 0.0, 0.0), normal=(0.0, 0.0, 1.0)) -> Ref:
    return Ref(comp, RefKind.PLANE, origin, normal)


def axis(comp: str, origin=(0.0, 0.0, 0.0), direction=(0.0, 0.0, 1.0)) -> Ref:
    return Ref(comp, RefKind.AXIS, origin, direction)


def point(comp: str, origin=(0.0, 0.0, 0.0)) -> Ref:
    return Ref(comp, RefKind.POINT, origin)


def exp_so3(omega) -> np.ndarray:
    """Testin kendi Rodrigues formülü: exp([ω]×) = I + sin θ K + (1 − cos θ) K²."""
    w = np.asarray(omega, dtype=float)
    th = float(np.linalg.norm(w))
    if th < 1e-15:
        return np.eye(3)
    k = w / th
    K = np.array([[0.0, -k[2], k[1]], [k[2], 0.0, -k[0]], [-k[1], k[0], 0.0]])
    return np.eye(3) + math.sin(th) * K + (1.0 - math.cos(th)) * (K @ K)


def perturbed(T: np.ndarray, deg: float, axis_dir, dt) -> np.ndarray:
    """Başlangıç konumu: T'yi dünya ekseni axis_dir etrafında deg derece döndür (sol çarpım),
    dt kadar kaydır."""
    k = np.asarray(axis_dir, dtype=float)
    k = k / np.linalg.norm(k)
    R0 = exp_so3(math.radians(deg) * k) @ T[:3, :3]
    return transform(R0, T[:3, 3] + np.asarray(dt, dtype=float))


def world_point(T: np.ndarray, p0) -> np.ndarray:
    return T[:3, :3] @ np.asarray(p0, dtype=float) + T[:3, 3]


def world_dir(T: np.ndarray, d0) -> np.ndarray:
    d = np.asarray(d0, dtype=float)
    return T[:3, :3] @ (d / np.linalg.norm(d))


def angle_rad(u: np.ndarray, v: np.ndarray) -> float:
    """İki birim vektör arası açı, atan2(|u × v|, u·v): her açıda iyi koşullu."""
    return math.atan2(float(np.linalg.norm(np.cross(u, v))), float(u @ v))


# ---------------------------------------------------------------- blok üstüne blok (K4, K8, K9, K12, K13)
# A: 100 × 80 × 40 blok, köşesi yerel orijinde. Referans düzlemleri (A yereli):
#   üst yüz z = 40, n = +z;  dayama düzlemi x = 10, n = +x;  dayama düzlemi y = 20, n = +y.
# B: 50 × 50 × 20 blok, köşesi yerel orijinde. Referans yüzleri (B yereli, dış normaller):
#   alt yüz (0,0,0), n = −z;  sol yüz y = 0, n = −y;  ön yüz x = 50, n = +x.
# Çakışık düzlem: n_a + n_b = 0 ve (p_b − p_a)·n_a = 0.
#   R(−z) = −z;  R(−y) = −x;  R(+x) = −y  →  R = rot_z(−90): (x, y, z) → (y, −x, z)
#     kontrol: rot_z(−90)(0,−1,0) = (−1, 0, 0) ✓, rot_z(−90)(1,0,0) = (0, −1, 0) ✓
#   alt:  (R·0 + t)_z = t_z = 40
#   sol:  (R·0 + t)_x = t_x = 10
#   ön:   (R(50,0,0) + t)_y = −50 + t_y = 20 → t_y = 70
#   → T_B = transform(rot_z(−90), (10, 70, 40))


def stack_mates(lower: str, upper: str, h: float, xa: float, yb: float, w: float) -> list[Mate]:
    """Alt blokta üst yüz z = h, dayamalar x = xa, y = yb; üst blokta alt/sol/ön (x = w) yüzleri.
    Kapalı form: T_üst(alt bloğa göre) = transform(rot_z(−90), (xa, yb + w, h))."""
    return [
        Mate(C, plane(lower, (0, 0, h), (0, 0, 1)), plane(upper, (0, 0, 0), (0, 0, -1))),
        Mate(C, plane(lower, (xa, 0, 0), (1, 0, 0)), plane(upper, (0, 0, 0), (0, -1, 0))),
        Mate(C, plane(lower, (0, yb, 0), (0, 1, 0)), plane(upper, (w, 0, 0), (1, 0, 0))),
    ]


T_B_EXPECTED = transform(rot_z(-90), (10.0, 70.0, 40.0))


def block_on_block(T_A: np.ndarray | None = None, T_B0: np.ndarray | None = None) -> Assembly:
    T_A = np.eye(4) if T_A is None else T_A
    T_B0 = perturbed(T_B_EXPECTED, 20.0, (1, 2, 3), (6.0, -5.0, 6.0)) if T_B0 is None else T_B0
    return Assembly(
        name="blok_ustune_blok",
        components=[Component("A", "blok100", T=T_A, fixed=True), Component("B", "blok50", T=T_B0)],
        mates=stack_mates("A", "B", h=40.0, xa=10.0, yb=20.0, w=50.0),
    )


def assert_T_close(T, T_expected, atol=TOL_POS):
    T = np.asarray(T, dtype=float)
    assert is_rigid(T)
    np.testing.assert_allclose(T[:3, :3], T_expected[:3, :3], atol=TOL_DIR, rtol=0)
    np.testing.assert_allclose(T[:3, 3], T_expected[:3, 3], atol=atol, rtol=0)


# ---------------------------------------------------------------- K4: blok üstüne blok


def test_block_on_block_closed_form():
    """K4: 3 dik düzlem çifti çakışık; B ≈20° dönük, ≈10 mm kaçık başlangıçtan
    T_B = transform(rot_z(−90), (10, 70, 40))'a iner (1e-9 mm); dof = 0; A yerinde."""
    asm = block_on_block()
    res = solve(asm)
    assert isinstance(res, SolveResult)
    assert_T_close(res.T["B"], T_B_EXPECTED)
    np.testing.assert_array_equal(res.T["A"], np.eye(4))
    assert res.dof == 0
    assert res.residual <= 1e-10
    assert res.iterations >= 1


# ---------------------------------------------------------------- K5: mil–delik


def shaft_in_hole(T_B0: np.ndarray) -> Assembly:
    """Gövde A (sabit, T = I): delik ekseni (20, 30, 0) + s z; üst yüz z = 15, n = +z.
    Mil B (yerel): ekseni orijinden z yönünde; omuz yüzü z = 40'ta, normali −z (gövdeye bakar)."""
    return Assembly(
        name="mil_delik",
        components=[Component("A", "govde", fixed=True), Component("B", "mil", T=T_B0)],
        mates=[
            Mate(CON, axis("A", (20, 30, 0)), axis("B")),
            Mate(C, plane("A", (0, 0, 15)), plane("B", (0, 0, 40), (0, 0, -1))),
        ],
    )


def test_shaft_in_hole():
    """K5: CONCENTRIC + PLANE–PLANE COINCIDENT. Beklenen (el hesabı):
    eksen: d_b ∥ z ve (p_b − p_a) × z = 0 → milin ekseni (20, 30, ·) doğrusunda;
    omuz: n_b = −z, omuz noktaları z = 15'te; dof = 1 (eksen etrafında dönme serbest).
    Serbest dönme açısı en küçük normlu adıma bağlı olduğundan tam T kontrol edilmez."""
    T_exact = transform(np.eye(3), (20.0, 30.0, 15.0 - 40.0))  # bir çözüm: omuz z = 40 − 25 = 15
    asm = shaft_in_hole(perturbed(T_exact, 20.0, (1, 0, 0), (5.0, -4.0, 7.0)))
    res = solve(asm)
    T = np.asarray(res.T["B"])
    assert is_rigid(T)

    d_b = world_dir(T, (0, 0, 1))
    np.testing.assert_allclose(np.cross(d_b, [0, 0, 1]), 0.0, atol=TOL_DIR)
    np.testing.assert_allclose(d_b, [0, 0, 1], atol=TOL_DIR)  # omuz n_b = −z bunu da sabitler
    for s in (0.0, 40.0, 100.0):  # eksen üstündeki her nokta (20, 30, ·)'da
        np.testing.assert_allclose(world_point(T, (0, 0, s))[:2], [20.0, 30.0], atol=TOL_POS)

    np.testing.assert_allclose(world_dir(T, (0, 0, -1)), [0, 0, -1], atol=TOL_DIR)
    for q in ((0, 0, 40), (8, 0, 40), (0, 8, 40)):  # omuz düzlemindeki noktalar z = 15'te
        assert world_point(T, q)[2] == pytest.approx(15.0, abs=TOL_POS)
    assert res.dof == 1


# ---------------------------------------------------------------- K6: mesafe


def test_distance_plane_plane():
    """K6: DISTANCE PLANE–PLANE D = 7.5: A üst yüz z = 15 (n = +z), B alt yüz (n = −z).
    Beklenen: n_b = −z ve B yüzünün her noktası z = 15 + 7.5 = 22.5'te; dof = 3."""
    T0 = transform(exp_so3(np.radians(12.0) * np.array([1, 1, 0]) / math.sqrt(2)), (3.0, -2.0, 30.0))
    asm = Assembly(
        "mesafe_duzlem",
        [Component("A", "a", fixed=True), Component("B", "b", T=T0)],
        [Mate(DIS, plane("A", (0, 0, 15)), plane("B", (0, 0, 0), (0, 0, -1)), 7.5)],
    )
    res = solve(asm)
    T = np.asarray(res.T["B"])
    np.testing.assert_allclose(world_dir(T, (0, 0, -1)), [0, 0, -1], atol=TOL_DIR)
    for q in ((0, 0, 0), (20, 0, 0), (0, 20, 0)):
        assert world_point(T, q)[2] == pytest.approx(22.5, abs=TOL_POS)
    assert res.dof == 3


@pytest.mark.parametrize("point_first", [True, False], ids=["nokta_duzlem", "duzlem_nokta"])
def test_distance_point_plane_signed(point_first):
    """K6: DISTANCE POINT–PLANE D = 4 (işaretli). Düzlem: A, q = (0,0,10), n = +z. Nokta: B yerel (1,2,3).
    Başlangıç t = (0,0,4) → p_z = 7, (p − q)·n = −3 (yanlış tarafta). Beklenen: (p − q)·n = +4 → p_z = 14;
    dof = 5 (nokta düzleme paralel kayar + 3 dönme)."""
    pt, pl = point("B", (1, 2, 3)), plane("A", (0, 0, 10))
    mate = Mate(DIS, pt, pl, 4.0) if point_first else Mate(DIS, pl, pt, 4.0)
    asm = Assembly(
        "mesafe_nokta_duzlem",
        [Component("A", "a", fixed=True), Component("B", "b", T=transform(None, (0, 0, 4)))],
        [mate],
    )
    res = solve(asm)
    assert world_point(res.T["B"], (1, 2, 3))[2] == pytest.approx(14.0, abs=TOL_POS)
    assert res.dof == 5


def test_distance_point_point():
    """K6: DISTANCE POINT–POINT D = 25: p_a = A orijini, p_b = B orijini;
    başlangıç |p_b| = |(10,10,10)| ≈ 17.3. Beklenen |p_b − p_a| = 25 (1e-9);
    dof = 5 (küre yüzeyinde 2 + 3 dönme)."""
    asm = Assembly(
        "mesafe_nokta_nokta",
        [Component("A", "a", fixed=True), Component("B", "b", T=transform(rot_x(15), (10, 10, 10)))],
        [Mate(DIS, point("A"), point("B"), 25.0)],
    )
    res = solve(asm)
    assert float(np.linalg.norm(world_point(res.T["B"], (0, 0, 0)))) == pytest.approx(25.0, abs=TOL_POS)
    assert res.dof == 5


def test_distance_axis_axis():
    """K6: DISTANCE AXIS–AXIS D = 12: A ekseni z (orijinden), B ekseni yerel z;
    başlangıç 10° eğik, 15 mm uzak. Beklenen: d_a × d_b = 0 (paralel) ve |(p_b − p_a) × d_a| = 12; dof = 3."""
    T0 = transform(exp_so3(np.radians(10.0) * np.array([1.0, 0, 0])), (15.0, 0.0, 5.0))
    asm = Assembly(
        "mesafe_eksen",
        [Component("A", "a", fixed=True), Component("B", "b", T=T0)],
        [Mate(DIS, axis("A"), axis("B"), 12.0)],
    )
    res = solve(asm)
    T = np.asarray(res.T["B"])
    d_b = world_dir(T, (0, 0, 1))
    np.testing.assert_allclose(np.cross([0, 0, 1], d_b), 0.0, atol=TOL_DIR)
    for s in (0.0, 50.0):  # B ekseninin her noktası z ekseninden 12 mm
        assert float(np.linalg.norm(world_point(T, (0, 0, s))[:2])) == pytest.approx(12.0, abs=TOL_POS)
    assert res.dof == 3


# ---------------------------------------------------------------- K7: açı (menteşe)
# A (sabit, T = I): menteşe ekseni x (orijinden); bilezik alın yüzü x = 0, n = +x; kanat normali +z.
# B (yerel): menteşe ekseni x; alın yüzü x = 0, n = −x; kanat normali +z.
# CONCENTRIC: R x = ±x, t ⟂ x bileşeni 0;  alın çakışık: R(−x) = −x → R x = x, t_x = 0 → T_B = rot_x(φ).
# ANGLE θ: d_a·d_b = z·rot_x(φ) z = cos φ = cos θ → φ = ±θ; başlangıç +θ yakınında → T_B = rot_x(+θ).
# θ = 0: d_a − d_b = 0 → R z = z → φ = 0;  θ = 180: d_a + d_b = 0 → R z = −z → φ = 180.


def hinge(theta: float, T_B0: np.ndarray) -> Assembly:
    return Assembly(
        name="mentese",
        components=[Component("A", "kanat_a", fixed=True), Component("B", "kanat_b", T=T_B0)],
        mates=[
            Mate(CON, axis("A", direction=(1, 0, 0)), axis("B", direction=(1, 0, 0))),
            Mate(C, plane("A", normal=(1, 0, 0)), plane("B", normal=(-1, 0, 0))),
            Mate(ANG, plane("A", (0, 10, 0)), plane("B", (0, 10, 0)), theta),
        ],
    )


def test_hinge_angle_30():
    """K7: menteşe + ANGLE 30°. Beklenen T_B = rot_x(30) (el hesabı yukarıda); kanat normalleri arası
    açı 30° (1e-9 rad); menteşe ekseni üstündeki B noktası (5,0,0) dünyada (5,0,0)'da; dof = 0."""
    T0 = perturbed(transform(rot_x(20)), 3.0, (0, 1, 0), (0.5, -0.4, 0.3))
    res = solve(hinge(30.0, T0))
    T = np.asarray(res.T["B"])
    assert angle_rad(np.array([0.0, 0, 1]), world_dir(T, (0, 0, 1))) == pytest.approx(
        math.radians(30.0), abs=1e-9
    )
    np.testing.assert_allclose(world_point(T, (5, 0, 0)), [5, 0, 0], atol=TOL_POS)
    assert_T_close(T, transform(rot_x(30)))
    assert res.dof == 0


@pytest.mark.parametrize(
    "theta, start_deg, phi",
    [(0.0, 15.0, 0.0), (180.0, 160.0, 180.0)],
    ids=["aci_0", "aci_180"],
)
def test_hinge_angle_0_and_180(theta, start_deg, phi):
    """K7: θ = 0 (d_a − d_b) ve θ = 180 (d_a + d_b) dalları: T_B = rot_x(θ) (1e-9);
    ayrı artık sayesinde Jacobian dejenere değil → dof = 0 (SPEC: cos θ artığı burada türevsiz)."""
    T0 = perturbed(transform(rot_x(start_deg)), 3.0, (0, 1, 0), (0.5, -0.4, 0.3))
    res = solve(hinge(theta, T0))
    assert_T_close(res.T["B"], transform(rot_x(phi)))
    assert res.dof == 0


# ---------------------------------------------------------------- K8: zincir


def test_chain_three_blocks():
    """K8: A sabit (T = I), B → A (blok üstüne blok), C → B (B'nin yerel referanslarıyla).
    B'de: üst yüz z = 20, dayamalar x = 5, y = 5; C genişliği w = 30.
    T_C/B = transform(rot_z(−90), (5, 5 + 30, 20)) = transform(rot_z(−90), (5, 35, 20)).
    T_C = T_B · T_C/B:  R = rot_z(−90)·rot_z(−90) = rot_z(180);
                         t = rot_z(−90)(5, 35, 20) + (10, 70, 40)
                           = (35, −5, 20) + (10, 70, 40) = (45, 65, 60).
    → T_C = transform(rot_z(180), (45, 65, 60)) (1e-9 mm); dof = 0."""
    T_C_expected = transform(rot_z(180), (45.0, 65.0, 60.0))
    np.testing.assert_allclose(T_B_EXPECTED @ transform(rot_z(-90), (5, 35, 20)), T_C_expected, atol=1e-12)

    asm = Assembly(
        name="zincir",
        components=[
            Component("A", "blok100", fixed=True),
            Component("B", "blok50", T=perturbed(T_B_EXPECTED, 15.0, (1, 2, 3), (6.0, -5.0, 6.0))),
            Component("C", "blok30", T=perturbed(T_C_expected, 15.0, (-2, 1, 1), (-5.0, 4.0, 6.0))),
        ],
        mates=stack_mates("A", "B", 40.0, 10.0, 20.0, 50.0) + stack_mates("B", "C", 20.0, 5.0, 5.0, 30.0),
    )
    res = solve(asm)
    assert_T_close(res.T["B"], T_B_EXPECTED)
    assert_T_close(res.T["C"], T_C_expected)
    assert res.dof == 0


# ---------------------------------------------------------------- K9: serbestlik sayımı (rank)
# Hepsi sağlanmış konumda (A = B = I): DOF = 6·n_serbest − rank(J). Beklenenler SPEC tablosundaki
# "kaldırdığı serbestlik" sütunundan: düzlem 3, eş eksen 4, nokta–nokta 3, nokta–düzlem 1, nokta–eksen 2.

PL = Mate(C, plane("A", (0, 0, 0)), plane("B", (0, 0, 0), (0, 0, -1)))
CO = Mate(CON, axis("A", (0, 0, 0)), axis("B", (0, 0, 0)))
PL_TOP = Mate(C, plane("A", (0, 0, 10)), plane("B", (0, 0, 10), (0, 0, -1)))


def two_body_at_identity(mates: list[Mate]) -> Assembly:
    return Assembly("dof", [Component("A", "a", fixed=True), Component("B", "b")], mates)


@pytest.mark.parametrize(
    "mates, expected",
    [
        ([], 6),  # kısıtsız
        ([PL], 3),  # düzlem çakışık: 1 öteleme + 2 dönme
        ([CO], 2),  # eş eksen: eksen boyu kayma + dönme
        ([CO, PL_TOP], 1),  # mil–delik: eksen etrafında dönme
        ([Mate(C, point("A", (1, 2, 3)), point("B", (1, 2, 3)))], 3),  # küresel mafsal
        ([Mate(C, point("B", (4, 5, 0)), plane("A", (0, 0, 0)))], 5),  # nokta düzlemde
        ([Mate(C, point("B", (0, 0, 7)), axis("A", (0, 0, 0)))], 4),  # nokta eksende
        ([PL, PL], 3),  # aynı kısıt iki kez: rank değişmez
        ([CO, PL_TOP, PL_TOP, CO], 1),
    ],
    ids=[
        "kisitsiz",
        "duzlem",
        "esksen",
        "esksen_duzlem",
        "nokta_nokta",
        "nokta_duzlem",
        "nokta_eksen",
        "duzlem_iki_kez",
        "esksen_duzlem_iki_kez",
    ],
)
def test_dof_counts(mates, expected):
    """K9: DOF sayımı sayısal rank ile (SPEC: σ_i > 1e-8 σ_max); yinelenen kısıt sayıyı değiştirmez."""
    assert dof(two_body_at_identity(mates)) == expected


def test_dof_three_plane_pairs_zero_and_duplicate():
    """K9: 3 düzlem çifti (çözülmüş blok üstüne blok) → 0; bir çift iki kez yazılınca yine 0 (rank)."""
    asm = block_on_block(T_B0=T_B_EXPECTED.copy())
    assert dof(asm) == 0
    asm.mates.append(copy.deepcopy(asm.mates[1]))
    assert dof(asm) == 0


def test_dof_two_free_components_sum():
    """K9: iki serbest bileşen: B düzlem çakışık (3) + C eş eksen (2) = 5; C kısıtsız ise 3 + 6 = 9;
    C, A yerine B'ye bağlı (zincir) olsa da 3 + 2 = 5."""
    comps = [Component("A", "a", fixed=True), Component("B", "b"), Component("C", "c")]
    co_ac = Mate(CON, axis("A", (30, 0, 0)), axis("C", (30, 0, 0)))
    co_bc = Mate(CON, axis("B", (30, 0, 0)), axis("C", (30, 0, 0)))
    assert dof(Assembly("iki", copy.deepcopy(comps), [PL, co_ac])) == 5
    assert dof(Assembly("iki", copy.deepcopy(comps), [PL])) == 9
    assert dof(Assembly("iki", copy.deepcopy(comps), [PL, co_bc])) == 5


def test_unconstrained_component_does_not_move():
    """K9 / SPEC kenar durum: kısıtsız bileşen hareket etmez, 6 serbestlik sayılır."""
    T_B = transform(rot_x(33), (1.0, 2.0, 3.0))
    asm = Assembly("kisitsiz", [Component("A", "a", fixed=True), Component("B", "b", T=T_B)], [])
    res = solve(asm)
    np.testing.assert_allclose(res.T["B"], T_B, atol=1e-12)
    assert res.dof == 6


# ---------------------------------------------------------------- K10: çelişki


def test_conflicting_distances_raise():
    """K10: aynı düzlem çiftine D = 5 ve D = 7 → en küçük kareler 6'da takılır, |r| > 0 → AssyError;
    mesaj kısıt türünü yazar (SPEC)."""
    pa, pb = plane("A"), plane("B", normal=(0, 0, -1))
    asm = Assembly(
        "celiski",
        [Component("A", "a", fixed=True), Component("B", "b", T=transform(None, (0, 0, 3)))],
        [Mate(DIS, pa, pb, 5.0), Mate(DIS, pa, pb, 7.0)],
    )
    with pytest.raises(AssyError) as e:
        solve(asm)
    assert ("mesafe" in str(e.value).lower()) or ("distance" in str(e.value).lower())


def test_conflict_between_two_fixed_components_raises():
    """K10: iki ucu da sabit bileşende, sağlanmayan kısıt (düzlemler 3 mm ayrık) → AssyError."""
    asm = Assembly(
        "sabit_sabit",
        [
            Component("A", "a", fixed=True),
            Component("B", "b", T=transform(None, (0, 0, 3)), fixed=True),
            Component("C", "c"),
        ],
        [Mate(C, plane("A"), plane("B", normal=(0, 0, -1)))],
    )
    with pytest.raises(AssyError):
        solve(asm)


def test_satisfied_between_two_fixed_components_ok():
    """K10 karşıtı: iki sabit arasında sağlanmış kısıt çelişki değil;
    serbest C kısıtsız → dof 6, 0 iterasyon."""
    asm = Assembly(
        "sabit_sabit_ok",
        [Component("A", "a", fixed=True), Component("B", "b", fixed=True), Component("C", "c")],
        [Mate(C, plane("A"), plane("B", normal=(0, 0, -1)))],
    )
    res = solve(asm)
    assert res.dof == 6
    assert res.iterations == 0


def test_wrong_branch_parallel_normals_raises():
    """K10 / SPEC kenar durum: çakışık düzlemlerin normalleri tam aynı yönde (n_b = n_a) →
    n_a + n_b = 2n, gradyeni n·(ω × n) = 0, çözücü ilerleyemez → AssyError (yerel minimum / çelişki)."""
    asm = Assembly(
        "yanlis_dal",
        [Component("A", "a", fixed=True), Component("B", "b", T=transform(None, (0, 0, 2)))],
        [Mate(C, plane("A"), plane("B"))],
    )
    with pytest.raises(AssyError):
        solve(asm)


# ---------------------------------------------------------------- K11: hata durumları


def test_no_fixed_component_raises():
    """K11: hiç sabit bileşen yok → AssyError (montaj dünyaya bağlı değil)."""
    asm = Assembly("sabitsiz", [Component("A", "a"), Component("B", "b")], [PL])
    with pytest.raises(AssyError):
        solve(asm)


@pytest.mark.parametrize(
    "mate",
    [
        Mate(CON, plane("A"), point("B")),
        Mate(DIS, point("A"), point("B", (3, 0, 0)), 0.0),
        Mate(DIS, axis("A"), axis("B", (3, 0, 0)), 0.0),
    ],
    ids=["desteklenmeyen_cift", "nokta_nokta_D0", "eksen_eksen_D0"],
)
def test_solve_invalid_mate_raises(mate):
    """K11: desteklenmeyen çift (CONCENTRIC PLANE–POINT) ve normlu mesafede D = 0 → solve AssyError."""
    with pytest.raises(AssyError):
        solve(two_body_at_identity([mate]))


@pytest.mark.parametrize("bad", ["bilinmeyen", "ayni_bilesen", "yinelenen_ad"])
def test_solve_runs_validate(bad):
    """K11: solve önce assembly.validate() çağırır →
    bilinmeyen bileşen / iki ucu aynı / yinelenen ad AssyError."""
    asm = two_body_at_identity([PL])
    if bad == "bilinmeyen":
        asm.mates.append(Mate(C, plane("A"), plane("YOK", normal=(0, 0, -1))))
    elif bad == "ayni_bilesen":
        asm.mates.append(Mate(DIS, plane("B"), plane("B", (0, 0, 5)), 5.0))
    else:
        asm.components.append(Component("B", "baska"))
    with pytest.raises(AssyError):
        solve(asm)


# ---------------------------------------------------------------- K12: girdi korunur, rijitlik, apply


def test_solve_does_not_modify_input_and_rigid():
    """K12: solve girdiyi değiştirmez (kopya üzerinde çalışır); sonuç T'leri rijit; sabitler aynen."""
    T_A = transform(rot_x(10), (1, 2, 3))
    asm = block_on_block(T_A=T_A, T_B0=T_A @ perturbed(T_B_EXPECTED, 20.0, (1, 2, 3), (6.0, -5.0, 6.0)))
    before = copy.deepcopy(asm.to_dict())
    T_B_before = asm.component("B").T.copy()
    res = solve(asm)
    assert asm.to_dict() == before
    np.testing.assert_array_equal(asm.component("B").T, T_B_before)
    assert set(res.T) == {"A", "B"}
    for T in res.T.values():
        assert is_rigid(np.asarray(T))
    np.testing.assert_array_equal(res.T["A"], transform(rot_x(10), (1, 2, 3)))


def test_already_satisfied_zero_iterations():
    """K12: zaten sağlanmış montaj (B kapalı form konumda) → 0 iterasyon ve T aynen (1e-12)."""
    asm = block_on_block(T_B0=T_B_EXPECTED.copy())
    res = solve(asm)
    assert res.iterations == 0
    np.testing.assert_allclose(res.T["B"], T_B_EXPECTED, atol=1e-12)
    assert res.residual <= 1e-10


def test_apply_writes_transforms():
    """K12: apply sonuç T'lerini bileşenlere yazar; ardından tüm artıklar ≤ tol ve dof aynı."""
    asm = block_on_block()
    res = solve(asm)
    res.apply(asm)
    np.testing.assert_array_equal(asm.component("B").T, res.T["B"])
    assert float(np.max(np.abs(residuals(asm)))) <= 1e-10
    assert dof(asm) == res.dof == 0


def test_residuals_concatenates_in_order():
    """residuals(): kısıt artıkları ard arda, kısıt sırasıyla. A = I, B = transform(I, (0,0,5)):
    düzlem çakışık (A z=0 n=+z, B alt n=−z) → [0,0,0,5];  nokta–nokta (0,0,0)–B(0,0,0) → (0,0,5).
    Toplam 7 bileşen: [0,0,0,5, 0,0,5]; her parça mates.residual ile aynı."""
    asm = Assembly(
        "artiklar",
        [Component("A", "a", fixed=True), Component("B", "b", T=transform(None, (0, 0, 5)))],
        [Mate(C, plane("A"), plane("B", normal=(0, 0, -1))), Mate(C, point("A"), point("B"))],
    )
    r = np.asarray(residuals(asm), dtype=float)
    np.testing.assert_allclose(r, [0, 0, 0, 5, 0, 0, 5], atol=1e-12)
    np.testing.assert_allclose(r, np.concatenate([residual(asm, m) for m in asm.mates]), atol=1e-15)
    assert np.asarray(residuals(two_body_at_identity([]))).size == 0


# ---------------------------------------------------------------- K13: değişmezlik


@pytest.mark.parametrize("seed", [5, 6])
def test_rigid_motion_invariance(seed):
    """K13: tüm montaj (sabit A dahil) keyfi rijit G ile taşınınca çözüm G·T olur (1e-9).
    Tam kısıtlı (izole çözüm) montajlarda: blok üstüne blok ve 3'lü zincir.
    Kısıtlar bileşenlerin yerel referanslarıyla yazıldığı için göreli konum G'den bağımsızdır."""
    rng = np.random.default_rng(seed)
    G = transform(exp_so3(rng.normal(size=3)), rng.uniform(-200.0, 200.0, size=3))

    # blok üstüne blok
    T_B0 = perturbed(T_B_EXPECTED, 20.0, (1, 2, 3), (6.0, -5.0, 6.0))
    res = solve(block_on_block(T_A=G.copy(), T_B0=G @ T_B0))
    np.testing.assert_allclose(res.T["A"], G, atol=1e-12)
    assert_T_close(res.T["B"], G @ T_B_EXPECTED)
    assert res.dof == 0

    # zincir A → B → C
    T_C = transform(rot_z(180), (45.0, 65.0, 60.0))
    asm = Assembly(
        name="zincir_G",
        components=[
            Component("A", "a", T=G.copy(), fixed=True),
            Component("B", "b", T=G @ perturbed(T_B_EXPECTED, 15.0, (1, 2, 3), (6.0, -5.0, 6.0))),
            Component("C", "c", T=G @ perturbed(T_C, 15.0, (-2, 1, 1), (-5.0, 4.0, 6.0))),
        ],
        mates=stack_mates("A", "B", 40.0, 10.0, 20.0, 50.0) + stack_mates("B", "C", 20.0, 5.0, 5.0, 30.0),
    )
    res = solve(asm)
    assert_T_close(res.T["B"], G @ T_B_EXPECTED)
    assert_T_close(res.T["C"], G @ T_C)
