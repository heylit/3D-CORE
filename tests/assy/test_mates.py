"""SPEC 08 — assy/mates.py testleri: Rodrigues, skew, kısıt artıkları ve Jacobian'ları (K1, K2, K3, K11).

Testler sadece specs/08-kisitlar.md'deki teori ve arayüzden yazıldı; assy/mates.py gövdesi okunmadı.

Kurallar (SPEC 08, "Teori"):
    T = [[R, t], [0, 1]],  p = R p0 + t,  d = R d0                       (Craig, Bölüm 2)
    R' = exp([ω]×) R,  t' = t + Δt,  x = [Δt, ω]                          (Murray–Li–Sastry, Bölüm 2)
    exp([ω]×) = I + sin θ [k]× + (1 − cos θ) [k]×²,  θ = |ω|,  k = ω/θ     (Rodrigues)
Artık tablosu (sıra SPEC'teki gibi, ";" ile ayrılan parçalar ard arda):
    COINCIDENT PLANE–PLANE : n_a + n_b ; (p_b − p_a)·n_a
    COINCIDENT POINT–POINT : p_b − p_a
    COINCIDENT POINT–PLANE : (p − q)·n            (her iki sıra)
    COINCIDENT POINT–AXIS  : (p − q) × d          (her iki sıra)
    CONCENTRIC / COINCIDENT AXIS–AXIS : d_a × d_b ; (p_b − p_a) × d_a
    DISTANCE PLANE–PLANE   : n_a + n_b ; (p_b − p_a)·n_a − D
    DISTANCE POINT–PLANE   : (p − q)·n − D        (her iki sıra, işaretli)
    DISTANCE POINT–POINT   : |p_b − p_a| − D
    DISTANCE AXIS–AXIS     : d_a × d_b ; |(p_b − p_a) × d_a| − D
    ANGLE 0<θ<180          : d_a·d_b − cos θ
    ANGLE θ=0 / θ=180      : d_a − d_b  /  d_a + d_b

Kod henüz yokken (NotImplementedError) testler kök conftest.py ile "uygulanmamış" (xfail) sayılır.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from assy.mates import jacobian, residual, rodrigues, skew
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

C, CON, DIS, ANG = MateKind.COINCIDENT, MateKind.CONCENTRIC, MateKind.DISTANCE, MateKind.ANGLE
S60, C60 = math.sin(math.radians(60)), math.cos(math.radians(60))


# ---------------------------------------------------------------- yardımcılar


def plane(comp: str, origin=(0.0, 0.0, 0.0), normal=(0.0, 0.0, 1.0)) -> Ref:
    return Ref(comp, RefKind.PLANE, origin, normal)


def axis(comp: str, origin=(0.0, 0.0, 0.0), direction=(0.0, 0.0, 1.0)) -> Ref:
    return Ref(comp, RefKind.AXIS, origin, direction)


def point(comp: str, origin=(0.0, 0.0, 0.0)) -> Ref:
    return Ref(comp, RefKind.POINT, origin)


def exp_so3(omega) -> np.ndarray:
    """Testin kendi (bağımsız) Rodrigues formülü: exp([ω]×) = I + sin θ K + (1 − cos θ) K²."""
    w = np.asarray(omega, dtype=float)
    th = float(np.linalg.norm(w))
    if th < 1e-15:
        return np.eye(3)
    k = w / th
    K = np.array([[0.0, -k[2], k[1]], [k[2], 0.0, -k[0]], [-k[1], k[0], 0.0]])
    return np.eye(3) + math.sin(th) * K + (1.0 - math.cos(th)) * (K @ K)


def two_body(mate: Mate, T_B: np.ndarray) -> Assembly:
    """A sabit ve T_A = I (dünya = A'nın yereli); B'nin konumu T_B."""
    return Assembly(
        name="iki_govde",
        components=[Component("A", "blok_a", fixed=True), Component("B", "blok_b", T=T_B)],
        mates=[mate],
    )


# ---------------------------------------------------------------- K1: rodrigues, skew


def test_rodrigues_zero_is_identity():
    """K1: ω = 0 → I (1e-12); |ω| < 1e-12 de birim (SPEC arayüz notu)."""
    np.testing.assert_allclose(rodrigues(np.zeros(3)), np.eye(3), atol=1e-12)
    np.testing.assert_allclose(rodrigues(np.array([1e-14, -2e-14, 0.0])), np.eye(3), atol=1e-12)


def test_rodrigues_z_90_equals_rot_z():
    """K1: ω = (0, 0, π/2) → θ = 90°, k = z → rot_z(90) = [[0,-1,0],[1,0,0],[0,0,1]] (1e-12)."""
    np.testing.assert_allclose(rodrigues(np.array([0.0, 0.0, math.pi / 2])), rot_z(90), atol=1e-12)


def test_rodrigues_x_axis_general_angle():
    """K1: ω = (θ, 0, 0) → rot_x(θ) (eksen etrafında dönme), θ = 37°."""
    th = math.radians(37.0)
    np.testing.assert_allclose(rodrigues(np.array([th, 0.0, 0.0])), rot_x(37.0), atol=1e-12)


@pytest.mark.parametrize("seed", [0, 1, 2, 3, 4])
def test_rodrigues_rigid_and_matches_formula(seed):
    """K1: her ω için exp([ω]×) rijit (RᵀR = I, det = +1, 1e-12); eksen k sabit kalır (R k = k);
    değer bağımsız Rodrigues formülüyle aynı (Murray–Li–Sastry, denk. 2.14)."""
    rng = np.random.default_rng(seed)
    w = rng.normal(size=3) * 1.5
    R = rodrigues(w)
    assert R.shape == (3, 3)
    assert is_rigid(transform(R), tol=1e-12)
    np.testing.assert_allclose(R @ w, w, atol=1e-12)
    np.testing.assert_allclose(R, exp_so3(w), atol=1e-12)


def test_skew_cross_product():
    """skew(a) @ b = a × b ve [a]× antisimetrik (SPEC arayüzü)."""
    rng = np.random.default_rng(7)
    a, b = rng.normal(size=3), rng.normal(size=3)
    S = skew(a)
    np.testing.assert_allclose(S @ b, np.cross(a, b), atol=1e-12)
    np.testing.assert_allclose(S, -S.T, atol=1e-15)


# ---------------------------------------------------------------- K2: artıklar
# Ortak kurulum: A sabit, T_A = I. B: R = rot_z(90) → R (x, y, z) = (−y, x, z), t değişken.
# B'nin yerel (5, 0, 0) noktası → R·(5,0,0) = (0, 5, 0); t = (10, 0, 0) ile dünyada (10, 5, 0).

RZ = rot_z(90)


def TB(t) -> np.ndarray:
    return transform(RZ, t)


RESIDUAL_CASES = [
    # (id, mate, B'nin ötelemesi t, beklenen r) — her satırın el hesabı yorumda
    # COINCIDENT PLANE–PLANE: n_a = z, n_b = R(−z) = −z → n_a + n_b = 0;
    # p_b = (10,5,t_z) → (p_b − p_a)·z = t_z
    (
        "cak_duzlem_duzlem_saglanan",
        Mate(C, plane("A"), plane("B", (5, 0, 0), (0, 0, -1))),
        (10, 0, 0),
        [0, 0, 0, 0],
    ),
    (
        "cak_duzlem_duzlem_5mm",
        Mate(C, plane("A"), plane("B", (5, 0, 0), (0, 0, -1))),
        (10, 0, 5),
        [0, 0, 0, 5],
    ),
    # n_b yerel x → dünya R x = y: n_a + n_b = (0, 1, 1); p_b·z = 0
    (
        "cak_duzlem_duzlem_egik",
        Mate(C, plane("A"), plane("B", (5, 0, 0), (1, 0, 0))),
        (10, 0, 0),
        [0, 1, 1, 0],
    ),
    # COINCIDENT POINT–POINT: p_a = (10,5,0), p_b = (10,5,t_z) → p_b − p_a = (0,0,t_z)
    (
        "cak_nokta_nokta_saglanan",
        Mate(C, point("A", (10, 5, 0)), point("B", (5, 0, 0))),
        (10, 0, 0),
        [0, 0, 0],
    ),
    ("cak_nokta_nokta_5mm", Mate(C, point("A", (10, 5, 0)), point("B", (5, 0, 0))), (10, 0, 5), [0, 0, 5]),
    # COINCIDENT POINT–PLANE: p = (10,5,t_z), q = (3,4,0), n = z → (p − q)·n = t_z  (her iki sıra)
    ("cak_nokta_duzlem_saglanan", Mate(C, point("B", (5, 0, 0)), plane("A", (3, 4, 0))), (10, 0, 0), [0]),
    ("cak_nokta_duzlem_5mm", Mate(C, point("B", (5, 0, 0)), plane("A", (3, 4, 0))), (10, 0, 5), [5]),
    ("cak_duzlem_nokta_5mm", Mate(C, plane("A", (3, 4, 0)), point("B", (5, 0, 0))), (10, 0, 5), [5]),
    # COINCIDENT POINT–AXIS: q = (0,5,0), d = x; p = (10,5,t_z) → p − q = (10,0,t_z);
    # (10,0,5) × (1,0,0) = (0·0 − 5·0, 5·1 − 10·0, 10·0 − 0·1) = (0, 5, 0)
    (
        "cak_nokta_eksen_saglanan",
        Mate(C, point("B", (5, 0, 0)), axis("A", (0, 5, 0), (1, 0, 0))),
        (10, 0, 0),
        [0, 0, 0],
    ),
    (
        "cak_nokta_eksen_5mm",
        Mate(C, point("B", (5, 0, 0)), axis("A", (0, 5, 0), (1, 0, 0))),
        (10, 0, 5),
        [0, 5, 0],
    ),
    (
        "cak_eksen_nokta_5mm",
        Mate(C, axis("A", (0, 5, 0), (1, 0, 0)), point("B", (5, 0, 0))),
        (10, 0, 5),
        [0, 5, 0],
    ),
    # CONCENTRIC AXIS–AXIS: p_a = (10,0,0), d_a = z; p_b = t, d_b = R z = z.
    # t = (10,3,7): p_b − p_a = (0,3,7); (0,3,7) × (0,0,1) = (3·1 − 7·0, 7·0 − 0·1, 0) = (3, 0, 0)
    ("esksen_saglanan", Mate(CON, axis("A", (10, 0, 0)), axis("B")), (10, 0, 0), [0, 0, 0, 0, 0, 0]),
    ("esksen_3mm_kacik", Mate(CON, axis("A", (10, 0, 0)), axis("B")), (10, 3, 7), [0, 0, 0, 3, 0, 0]),
    # Yön serbest (SPEC): d_b = −d_a de sağlanmış sayılır → d_a × d_b = 0
    (
        "esksen_ters_yon",
        Mate(CON, axis("A", (10, 0, 0)), axis("B", direction=(0, 0, -1))),
        (10, 0, 0),
        [0, 0, 0, 0, 0, 0],
    ),
    # d_b yerel x → dünya y: z × y = (0·0 − 1·1, 1·0 − 0·0, 0) = (−1, 0, 0); p_b = p_a
    (
        "esksen_egik",
        Mate(CON, axis("A", (10, 0, 0)), axis("B", direction=(1, 0, 0))),
        (10, 0, 0),
        [-1, 0, 0, 0, 0, 0],
    ),
    # COINCIDENT AXIS–AXIS = CONCENTRIC (aynı artık)
    ("cak_eksen_eksen_3mm", Mate(C, axis("A", (10, 0, 0)), axis("B")), (10, 3, 7), [0, 0, 0, 3, 0, 0]),
    # DISTANCE PLANE–PLANE D = 7.5: (p_b − p_a)·n_a − D = t_z − 7.5
    (
        "mesafe_duzlem_saglanan",
        Mate(DIS, plane("A"), plane("B", (5, 0, 0), (0, 0, -1)), 7.5),
        (10, 0, 7.5),
        [0, 0, 0, 0],
    ),
    (
        "mesafe_duzlem_5mm",
        Mate(DIS, plane("A"), plane("B", (5, 0, 0), (0, 0, -1)), 7.5),
        (10, 0, 12.5),
        [0, 0, 0, 5],
    ),
    # DISTANCE POINT–PLANE D = 4 (işaretli): p = (10,5,t_z), q = 0, n = z → t_z − 4
    ("mesafe_nokta_duzlem_saglanan", Mate(DIS, point("B", (5, 0, 0)), plane("A"), 4.0), (10, 0, 4), [0]),
    ("mesafe_nokta_duzlem_5mm", Mate(DIS, point("B", (5, 0, 0)), plane("A"), 4.0), (10, 0, 9), [5]),
    ("mesafe_nokta_duzlem_ters_taraf", Mate(DIS, point("B", (5, 0, 0)), plane("A"), 4.0), (10, 0, -4), [-8]),
    ("mesafe_duzlem_nokta_5mm", Mate(DIS, plane("A"), point("B", (5, 0, 0)), 4.0), (10, 0, 9), [5]),
    # DISTANCE POINT–POINT D = 5: p_a = (10,5,0), p_b = (0,5,0) + t.
    # t = (13,4,0) → p_b = (13,9,0), fark (3,4,0), |.| = 5 → 0;  t = (16,8,0) → fark (6,8,0), |.| = 10 → 5
    (
        "mesafe_nokta_nokta_saglanan",
        Mate(DIS, point("A", (10, 5, 0)), point("B", (5, 0, 0)), 5.0),
        (13, 4, 0),
        [0],
    ),
    (
        "mesafe_nokta_nokta_5mm",
        Mate(DIS, point("A", (10, 5, 0)), point("B", (5, 0, 0)), 5.0),
        (16, 8, 0),
        [5],
    ),
    # DISTANCE AXIS–AXIS D = 5: p_a = 0, d_a = z, p_b = t, d_b = z.
    # t = (3,4,9): (3,4,9) × z = (4, −3, 0), |.| = 5 → 0;  t = (6,8,0): |.| = 10 → 5
    ("mesafe_eksen_eksen_saglanan", Mate(DIS, axis("A"), axis("B"), 5.0), (3, 4, 9), [0, 0, 0, 0]),
    ("mesafe_eksen_eksen_5mm", Mate(DIS, axis("A"), axis("B"), 5.0), (6, 8, 0), [0, 0, 0, 5]),
    # ANGLE 60°: d_a = z (düzlem normali). d_b yerel (sin60, 0, cos60) → dünya (0, sin60, cos60);
    # d_a·d_b = cos60 → 0.  d_b yerel x → dünya y: z·y − cos60 = −0.5
    ("aci_60_saglanan", Mate(ANG, plane("A"), axis("B", direction=(S60, 0, C60)), 60.0), (0, 0, 0), [0]),
    ("aci_60_dik", Mate(ANG, plane("A"), axis("B", direction=(1, 0, 0)), 60.0), (0, 0, 0), [-0.5]),
    # ANGLE 90° PLANE–PLANE: n_b = R x = y ⟂ z → 0 − cos 90° = 0
    ("aci_90_duzlem_duzlem", Mate(ANG, plane("A"), plane("B", normal=(1, 0, 0)), 90.0), (0, 0, 0), [0]),
    # ANGLE 0°: d_a − d_b. d_b = z → 0; d_b = R x = y → z − y = (0, −1, 1)
    ("aci_0_saglanan", Mate(ANG, plane("A"), plane("B"), 0.0), (0, 0, 0), [0, 0, 0]),
    ("aci_0_dik", Mate(ANG, plane("A"), plane("B", normal=(1, 0, 0)), 0.0), (0, 0, 0), [0, -1, 1]),
    # ANGLE 180°: d_a + d_b. d_b = −z → 0; d_b = y → (0, 1, 1)
    ("aci_180_saglanan", Mate(ANG, axis("A"), axis("B", direction=(0, 0, -1)), 180.0), (0, 0, 0), [0, 0, 0]),
    ("aci_180_dik", Mate(ANG, axis("A"), axis("B", direction=(1, 0, 0)), 180.0), (0, 0, 0), [0, 1, 1]),
]


@pytest.mark.parametrize(
    "mate, t, expected", [c[1:] for c in RESIDUAL_CASES], ids=[c[0] for c in RESIDUAL_CASES]
)
def test_residual_table(mate, t, expected):
    """K2: her tablo satırı — sağlanan konumda r = 0, bilinen bozulmada el hesabı değer (1e-12)."""
    r = np.asarray(residual(two_body(mate, TB(t)), mate), dtype=float)
    assert r.shape == (len(expected),)
    np.testing.assert_allclose(r, expected, atol=1e-12)


def test_residual_point_plane_both_orders_equal():
    """K2: POINT–PLANE "her iki sıra" — a/b yer değiştirince artık aynı: (p − q)·n."""
    T = TB((1.0, -2.0, 6.5))
    m1 = Mate(C, point("B", (5, 0, 0)), plane("A", (3, 4, 1.5)))
    m2 = Mate(C, plane("A", (3, 4, 1.5)), point("B", (5, 0, 0)))
    # p = R(5,0,0) + t = (0,5,0) + (1,−2,6.5) = (1,3,6.5); (p − q)·z = 6.5 − 1.5 = 5
    np.testing.assert_allclose(residual(two_body(m1, T), m1), [5.0], atol=1e-12)
    np.testing.assert_allclose(residual(two_body(m2, T), m2), [5.0], atol=1e-12)


# ---------------------------------------------------------------- K11: desteklenmeyen çift, D = 0


@pytest.mark.parametrize(
    "mate",
    [
        Mate(CON, plane("A"), point("B")),  # SPEC'te örnek: CONCENTRIC PLANE–POINT
        Mate(CON, point("A"), point("B")),  # CONCENTRIC sadece AXIS–AXIS
        Mate(CON, plane("A"), plane("B")),
        Mate(C, plane("A"), axis("B")),  # COINCIDENT PLANE–AXIS tabloda yok
        Mate(DIS, axis("A"), plane("B"), 3.0),  # DISTANCE AXIS–PLANE tabloda yok
        Mate(ANG, point("A"), axis("B"), 30.0),  # ANGLE sadece PLANE/AXIS
    ],
    ids=[
        "esksen_duzlem_nokta",
        "esksen_nokta_nokta",
        "esksen_duzlem_duzlem",
        "cak_duzlem_eksen",
        "mesafe_eksen_duzlem",
        "aci_nokta_eksen",
    ],
)
def test_residual_unsupported_pair_raises(mate):
    """K11: tabloda olmayan kısıt/referans çifti → AssyError."""
    with pytest.raises(AssyError):
        residual(two_body(mate, np.eye(4)), mate)


@pytest.mark.parametrize(
    "mate",
    [Mate(DIS, point("A"), point("B", (3, 0, 0)), 0.0), Mate(DIS, axis("A"), axis("B", (3, 0, 0)), 0.0)],
    ids=["nokta_nokta", "eksen_eksen"],
)
def test_residual_normed_distance_zero_raises(mate):
    """K11: normlu mesafe artığında D = 0 türevsiz → AssyError ("COINCIDENT kullanın")."""
    with pytest.raises(AssyError):
        residual(two_body(mate, np.eye(4)), mate)


# ---------------------------------------------------------------- K3: Jacobian = merkezi fark

# Her tablo satırı için genel (eksenlere hizalı olmayan) yerel referanslar.
JAC_MATES = {
    "cak_duzlem_duzlem": Mate(C, plane("A", (3, -2, 5), (1, 2, 2)), plane("B", (-4, 1, 2), (0, -3, 4))),
    "cak_nokta_nokta": Mate(C, point("A", (3, -2, 5)), point("B", (-4, 1, 2))),
    "cak_nokta_duzlem": Mate(C, point("A", (3, -2, 5)), plane("B", (-4, 1, 2), (2, -1, 2))),
    "cak_duzlem_nokta": Mate(C, plane("A", (3, -2, 5), (2, -1, 2)), point("B", (-4, 1, 2))),
    "cak_nokta_eksen": Mate(C, point("A", (3, -2, 5)), axis("B", (-4, 1, 2), (1, 1, 0))),
    "cak_eksen_nokta": Mate(C, axis("A", (3, -2, 5), (1, 1, 0)), point("B", (-4, 1, 2))),
    "cak_eksen_eksen": Mate(C, axis("A", (3, -2, 5), (0, 1, 1)), axis("B", (-4, 1, 2), (1, 0, 2))),
    "esksen": Mate(CON, axis("A", (3, -2, 5), (0, 1, 1)), axis("B", (-4, 1, 2), (1, 0, 2))),
    "mesafe_duzlem_duzlem": Mate(
        DIS, plane("A", (3, -2, 5), (1, 2, 2)), plane("B", (-4, 1, 2), (0, 3, 4)), 7.5
    ),
    "mesafe_nokta_duzlem": Mate(DIS, point("A", (3, -2, 5)), plane("B", (-4, 1, 2), (2, -1, 2)), 4.0),
    "mesafe_duzlem_nokta": Mate(DIS, plane("A", (3, -2, 5), (2, -1, 2)), point("B", (-4, 1, 2)), 4.0),
    "mesafe_nokta_nokta": Mate(DIS, point("A", (3, -2, 5)), point("B", (-4, 1, 2)), 5.0),
    "mesafe_eksen_eksen": Mate(DIS, axis("A", (3, -2, 5), (0, 1, 1)), axis("B", (-4, 1, 2), (1, 0, 2)), 5.0),
    "aci_duzlem_eksen": Mate(ANG, plane("A", (3, -2, 5), (1, 2, 2)), axis("B", (-4, 1, 2), (1, 0, 2)), 30.0),
    "aci_eksen_eksen": Mate(ANG, axis("A", (3, -2, 5), (0, 1, 1)), axis("B", (-4, 1, 2), (1, 0, 2)), 120.0),
    "aci_0": Mate(ANG, plane("A", (3, -2, 5), (1, 2, 2)), plane("B", (-4, 1, 2), (0, 3, 4)), 0.0),
    "aci_180": Mate(ANG, axis("A", (3, -2, 5), (0, 1, 1)), plane("B", (-4, 1, 2), (0, 3, 4)), 180.0),
}

# Bilinmeyen düzenleri: (sabit bileşenler, bilinmeyenler listesi)
#   "B": A sabit, B bilinmeyen;  "A": B sabit, A bilinmeyen;
#   "BCA": ikisi de bilinmeyen + kısıtta olmayan C (sütunları sıfır olmalı), sıra B, C, A
UNKNOWN_SETS = {"B": ["B"], "A": ["A"], "BCA": ["B", "C", "A"]}


def random_T(rng: np.random.Generator) -> np.ndarray:
    """Rastgele rijit dönüşüm: R = exp([ω]×), |ω| ~ 1 rad; t ∈ [−50, 50]³ mm."""
    return transform(exp_so3(rng.normal(size=3)), rng.uniform(-50.0, 50.0, size=3))


def fd_jacobian(asm: Assembly, mate: Mate, unknowns: list[str], h: float = 1e-6) -> np.ndarray:
    """Merkezi fark: J[:, 6i + k] = (r(x + h e_k) − r(x − h e_k)) / 2h,
    bozma SPEC'teki güncelleme ile: R' = exp([ω]×) R, t' = t + Δt (ω ve Δt dünya ekseninde)."""
    cols = []
    for name in unknowns:
        comp = asm.component(name)
        T0 = comp.T.copy()
        for k in range(6):
            r_pm = []
            for s in (+1.0, -1.0):
                x = np.zeros(6)
                x[k] = s * h
                T = T0.copy()
                T[:3, :3] = exp_so3(x[3:]) @ T0[:3, :3]
                T[:3, 3] = T0[:3, 3] + x[:3]
                comp.T = T
                r_pm.append(np.asarray(residual(asm, mate), dtype=float))
            comp.T = T0
            cols.append((r_pm[0] - r_pm[1]) / (2.0 * h))
    return np.column_stack(cols)


@pytest.mark.parametrize("seed", [11, 22, 33])
@pytest.mark.parametrize("order", list(UNKNOWN_SETS))
@pytest.mark.parametrize("name", list(JAC_MATES))
def test_jacobian_matches_fd(name, order, seed):
    """K3: analitik Jacobian = merkezi fark Jacobian'ı (h = 1e-6, mutlak 1e-6), her tablo satırı,
    rastgele (sabit tohumlu) konumlarda; bir uç sabit / iki uç bilinmeyen; sütun düzeni [Δt, ω]."""
    mate = JAC_MATES[name]
    unknowns = UNKNOWN_SETS[order]
    rng = np.random.default_rng(seed)
    comps = [
        Component("Z", "zemin", fixed=True),
        Component("A", "pa", T=random_T(rng), fixed="A" not in unknowns),
        Component("B", "pb", T=random_T(rng), fixed="B" not in unknowns),
        Component("C", "pc", T=random_T(rng)),
    ]
    asm = Assembly("jac", components=comps, mates=[mate])

    J = np.asarray(jacobian(asm, mate, unknowns), dtype=float)
    J_fd = fd_jacobian(asm, mate, unknowns)

    m = np.asarray(residual(asm, mate)).size
    assert J.shape == (m, 6 * len(unknowns))
    np.testing.assert_allclose(J, J_fd, atol=1e-6, rtol=0)
    if "C" in unknowns:
        # C kısıtta yok: ∂r/∂x_C = 0 (analitik olarak tam sıfır)
        i = unknowns.index("C")
        np.testing.assert_allclose(J[:, 6 * i : 6 * i + 6], 0.0, atol=1e-14)


def test_jacobian_rotation_of_point_known_value():
    """K3 (el hesabı): COINCIDENT POINT–POINT, A sabit, B = I, p0_B = (1, 0, 0).
    r = p_b − p_a → ∂r/∂Δt = I, ∂r/∂ω = −[R p0]× = −[(1,0,0)]× = [[0,0,0],[0,0,1],[0,−1,0]]."""
    mate = Mate(C, point("A"), point("B", (1, 0, 0)))
    J = np.asarray(jacobian(two_body(mate, np.eye(4)), mate, ["B"]), dtype=float)
    expected = np.hstack([np.eye(3), [[0, 0, 0], [0, 0, 1], [0, -1, 0]]])
    np.testing.assert_allclose(J, expected, atol=1e-12)
