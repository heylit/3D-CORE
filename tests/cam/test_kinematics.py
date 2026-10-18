"""SPEC 41 — tezgâh kinematiği testleri (K1, K4–K7).

Testler yalnız SPEC 41 metninden ve `cam/model.py` arayüzünden (`Kinematics`, `RotaryAxis`, `Wcs`)
yazıldı; `cam/multiaxis/kinematics.py` gövdeleri okunmadı (iskelette NotImplementedError).

Kurallar (SPEC 41 Teori):
- Rodrigues: R_u(θ) = I + sin θ·K + (1 − cos θ)·K², K = [u]×; açılar derece.
- q = (X, Y, Z, θ…), döner açılar `kin.rotary` sırasında. Masa W = Rot(t1)∘Rot(t2),
  kafa H = Trans(X, Y, Z)∘Rot(h1)∘Rot(h2); tip₀ = g − L·s;
  tip_w = W⁻¹(H(tip₀)) − o_wcs, a_w = R_Wᵀ·R_H·s.
- AC masa-masa (u_A = +X, u_C = +Z, s = +Z): a_w = (sin A sin C, sin A cos C, cos A);
  temel çözümler (A, C) ve (−A, C + 180°).
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from cam.model import CamError, Kinematics, RotaryAxis, Wcs
from cam.multiaxis.kinematics import (
    all_solutions,
    forward,
    inverse,
    inverse_axes,
    rotate_about,
    rotation,
)

TOL = 1e-9
S2 = math.sqrt(0.5)


# ---------------------------------------------------------------- yardımcılar


def _rodrigues(u, theta_deg: float) -> np.ndarray:
    """Testin kendi Rodrigues formülü (SPEC 41)."""
    u = np.asarray(u, dtype=float)
    u = u / np.linalg.norm(u)
    K = np.array([[0.0, -u[2], u[1]], [u[2], 0.0, -u[0]], [-u[1], u[0], 0.0]])
    t = math.radians(theta_deg)
    return np.eye(3) + math.sin(t) * K + (1.0 - math.cos(t)) * K @ K


def _fark(a: float, b: float) -> float:
    """Açı farkı (−180°, 180°] aralığına sarılmış [derece]."""
    return (a - b + 180.0) % 360.0 - 180.0


def _yon(tilt_deg: float, az_deg: float) -> np.ndarray:
    """+Z'den tilt kadar eğik, XY'de az açılı birim yön."""
    t, a = math.radians(tilt_deg), math.radians(az_deg)
    return np.array([math.sin(t) * math.cos(a), math.sin(t) * math.sin(a), math.cos(t)])


def _ac(
    a_min=-120.0, a_max=120.0, c_min=None, c_max=None, a_pivot=(0.0, 0.0, -50.0), c_pivot=(10.0, 5.0, 0.0)
):
    """AC masa-masa: A (t1, +X) tabanda, C (t2, +Z) üstünde."""
    return Kinematics(
        rotary=(
            RotaryAxis("A", "masa", (1.0, 0.0, 0.0), a_pivot, a_min, a_max),
            RotaryAxis("C", "masa", (0.0, 0.0, 1.0), c_pivot, c_min, c_max),
        )
    )


def _bc():
    return Kinematics(
        rotary=(
            RotaryAxis("B", "masa", (0.0, 1.0, 0.0), (5.0, 0.0, -80.0), -120.0, 120.0),
            RotaryAxis("C", "masa", (0.0, 0.0, 1.0), (0.0, -7.0, 0.0)),
        )
    )


def _ab_kafa():
    return Kinematics(
        rotary=(
            RotaryAxis("A", "kafa", (1.0, 0.0, 0.0), (0.0, 0.0, 200.0), -100.0, 100.0),
            RotaryAxis("B", "kafa", (0.0, 1.0, 0.0), (0.0, 3.0, 150.0), -100.0, 100.0),
        ),
        gauge=(0.0, 0.0, 120.0),
    )


def _b_kafa_c_masa():
    return Kinematics(
        rotary=(
            RotaryAxis("B", "kafa", (0.0, 1.0, 0.0), (0.0, 0.0, 180.0), -120.0, 120.0),
            RotaryAxis("C", "masa", (0.0, 0.0, 1.0), (20.0, 10.0, 0.0)),
        )
    )


def _nutasyonlu():
    """45° eğik B masa ekseni (t1) üstünde C masa (t2): ulaşılabilir eğim en çok 90°."""
    return Kinematics(
        rotary=(
            RotaryAxis("B", "masa", (0.0, -S2, S2), (0.0, 0.0, -40.0)),
            RotaryAxis("C", "masa", (0.0, 0.0, 1.0), (0.0, 0.0, 0.0)),
        )
    )


def _gidip_don(kin: Kinematics, max_tilt: float, n: int = 40, seed: int = 41) -> None:
    """Rastgele ulaşılabilir (p_w, a_w): forward(inverse(…)) = (p_w, a_w) 1e-9."""
    rng = np.random.default_rng(seed)
    wcs = Wcs(origin=(12.0, -8.0, 30.0))
    L = 90.0
    prev = None
    for _ in range(n):
        a_w = _yon(rng.uniform(5.0, max_tilt), rng.uniform(-180.0, 180.0))
        p_w = rng.uniform(-50.0, 50.0, size=3)
        q = inverse(kin, p_w, a_w, L, wcs, prev)
        assert q.shape == (3 + len(kin.rotary),)
        tip, a = forward(kin, q, L, wcs)
        np.testing.assert_allclose(tip, p_w, atol=TOL)
        np.testing.assert_allclose(a, a_w, atol=TOL)
        prev = tuple(float(v) for v in q[3:])


# ---------------------------------------------------------------- K1 dönme


def test_k1_rotation_bilinen_acilar():
    np.testing.assert_allclose(rotation((0, 0, 1), 90.0), [[0, -1, 0], [1, 0, 0], [0, 0, 1]], atol=1e-12)
    np.testing.assert_allclose(rotation((1, 0, 0), 180.0), np.diag([1.0, -1.0, -1.0]), atol=1e-12)
    np.testing.assert_allclose(rotation((0, 1, 0), 90.0), [[0, 0, 1], [0, 1, 0], [-1, 0, 0]], atol=1e-12)
    np.testing.assert_allclose(rotation((0, 0, 1), 0.0), np.eye(3), atol=1e-12)


def test_k1_rotation_rastgele_formul_ortonormal():
    rng = np.random.default_rng(1)
    for _ in range(50):
        u = rng.normal(size=3)
        u /= np.linalg.norm(u)
        t = rng.uniform(-360.0, 360.0)
        R = rotation(u, t)
        assert R.shape == (3, 3)
        np.testing.assert_allclose(R, _rodrigues(u, t), atol=1e-12)
        np.testing.assert_allclose(R.T @ R, np.eye(3), atol=1e-12)
        assert abs(np.linalg.det(R) - 1.0) < 1e-12
        np.testing.assert_allclose(R @ u, u, atol=1e-12)  # eksen sabit


def test_k1_rotate_about_pivot_sabit_ve_toplu():
    u = np.array([1.0, 2.0, 2.0]) / 3.0
    c = np.array([10.0, -5.0, 3.0])
    np.testing.assert_allclose(rotate_about(c, u, c, 73.0), c, atol=1e-12)
    # pivottan geçen eksen üstündeki her nokta sabit
    np.testing.assert_allclose(rotate_about(c + 7.0 * u, u, c, 73.0), c + 7.0 * u, atol=1e-12)
    x = np.array([[1.0, 2.0, 3.0], [-4.0, 0.0, 9.0], [c[0], c[1], c[2]]])
    y = rotate_about(x, u, c, 73.0)
    assert y.shape == (3, 3)
    beklenen = c + (x - c) @ _rodrigues(u, 73.0).T
    np.testing.assert_allclose(y, beklenen, atol=1e-12)
    # tek nokta (3,) toplu sonuçla aynı
    np.testing.assert_allclose(rotate_about(x[0], u, c, 73.0), beklenen[0], atol=1e-12)


def test_k1_rotate_about_elle():
    # +Z etrafında (1, 1, 0) pivotlu 90°: (2, 1, 5) → (1, 2, 5)
    np.testing.assert_allclose(
        rotate_about((2.0, 1.0, 5.0), (0, 0, 1), (1.0, 1.0, 0.0), 90.0), [1, 2, 5], atol=1e-12
    )


# ---------------------------------------------------------------- K4 ileri kinematik


def test_k4_ac_takim_ekseni_formulu():
    kin = _ac(a_min=None, a_max=None)
    wcs = Wcs(origin=(3.0, 4.0, 5.0))
    rng = np.random.default_rng(4)
    for _ in range(50):
        A, C = rng.uniform(-180.0, 180.0, size=2)
        xyz = rng.uniform(-100.0, 100.0, size=3)
        _, a = forward(kin, (*xyz, A, C), 75.0, wcs)
        a_ = math.radians(A)
        c_ = math.radians(C)
        beklenen = [math.sin(a_) * math.sin(c_), math.sin(a_) * math.cos(c_), math.cos(a_)]
        np.testing.assert_allclose(a, beklenen, atol=1e-12)


def test_k4_pivot_ofsetli_masa_a90_uc_noktasi():
    # A: +X, pivot (0, 20, −30); C: +Z, pivot orijin; L = 100, g = 0, s = +Z, o_wcs = (10, 0, 0).
    # tip₀ = (0, 0, −100); H(tip₀) = (5, 40, −50); W⁻¹ = Rot_A(−90°) pivot etrafında:
    # x − c = (5, 20, −20) → Rx(−90°): (x, z, −y) = (5, −20, −20) → + c = (5, 0, −50);
    # − o_wcs → (−5, 0, −50). a_w = Rx(−90°)·z = (0, 1, 0).
    kin = _ac(a_min=None, a_max=None, a_pivot=(0.0, 20.0, -30.0), c_pivot=(0.0, 0.0, 0.0))
    tip, a = forward(kin, (5.0, 40.0, 50.0, 90.0, 0.0), 100.0, Wcs(origin=(10.0, 0.0, 0.0)))
    np.testing.assert_allclose(tip, [-5.0, 0.0, -50.0], atol=TOL)
    np.testing.assert_allclose(a, [0.0, 1.0, 0.0], atol=1e-12)


def test_k4_uc_eksen_ileri():
    # Döner eksen yok: tip = (X, Y, Z) + g − L·s − o_wcs
    kin = Kinematics(gauge=(0.0, 0.0, 10.0))
    tip, a = forward(kin, (1.0, 2.0, 3.0), 50.0, Wcs(origin=(10.0, 20.0, 30.0)))
    np.testing.assert_allclose(tip, [-9.0, -18.0, -67.0], atol=TOL)
    np.testing.assert_allclose(a, [0.0, 0.0, 1.0], atol=1e-12)


def test_k4_kafa_b90_uc_noktasi():
    # B kafa: +Y, pivot (0, 0, 150); B = 90°, L = 100, X = Y = Z = 0.
    # tip₀ = (0, 0, −100); x − c = (0, 0, −250) → Ry(90°): (−250, 0, 0) → + c = (−250, 0, 150).
    kin = Kinematics(rotary=(RotaryAxis("B", "kafa", (0.0, 1.0, 0.0), (0.0, 0.0, 150.0)),))
    tip, a = forward(kin, (0.0, 0.0, 0.0, 90.0), 100.0, Wcs())
    np.testing.assert_allclose(tip, [-250.0, 0.0, 150.0], atol=TOL)
    np.testing.assert_allclose(a, [1.0, 0.0, 0.0], atol=1e-12)


# ---------------------------------------------------------------- K5 ters kinematik


def test_k5_gidip_don_ac_masa():
    _gidip_don(_ac(), max_tilt=110.0)


def test_k5_gidip_don_bc_masa():
    _gidip_don(_bc(), max_tilt=110.0)


def test_k5_gidip_don_ab_kafa():
    _gidip_don(_ab_kafa(), max_tilt=70.0)


def test_k5_gidip_don_b_kafa_c_masa():
    _gidip_don(_b_kafa_c_masa(), max_tilt=110.0)


def test_k5_gidip_don_nutasyonlu_b():
    _gidip_don(_nutasyonlu(), max_tilt=85.0)


def test_k5_ac_iki_temel_cozum():
    kin = _ac()
    a_w = _yon(40.0, 90.0 - 30.0)  # A = 40°, C = 30° → (sin40 sin30, sin40 cos30, cos40)
    np.testing.assert_allclose(
        a_w,
        [
            math.sin(math.radians(40)) * 0.5,
            math.sin(math.radians(40)) * math.sqrt(3) / 2,
            math.cos(math.radians(40)),
        ],
    )
    sol = all_solutions(kin, a_w)
    assert len(sol) == 2
    for s in sol:
        assert len(s) == 2
        assert all(-180.0 < v <= 180.0 + 1e-9 for v in s)
    sirali = sorted(sol)
    beklenen = [(-40.0, -150.0), (40.0, 30.0)]
    for s, b in zip(sirali, beklenen, strict=True):
        assert abs(_fark(s[0], b[0])) < TOL
        assert abs(_fark(s[1], b[1])) < TOL


def test_k5_nutasyonlu_90_derece_ustu_ulasilamaz():
    kin = _nutasyonlu()
    for a_w in (_yon(100.0, 0.0), _yon(135.0, 60.0), np.array([0.0, 0.0, -1.0])):
        with pytest.raises(CamError):
            inverse_axes(kin, a_w)
        with pytest.raises(CamError):
            inverse(kin, (0.0, 0.0, 0.0), a_w, 90.0, Wcs())


# ---------------------------------------------------------------- K6 çözüm seçimi


def _ac_yonu(A: float, C: float) -> np.ndarray:
    a, c = math.radians(A), math.radians(C)
    return np.array([math.sin(a) * math.sin(c), math.sin(a) * math.cos(c), math.cos(a)])


def _esit(got, beklenen) -> None:
    assert len(got) == len(beklenen)
    for g, b in zip(got, beklenen, strict=True):
        assert abs(g - b) < TOL, (got, beklenen)


def test_k6_sinir_disi_cozum_eleniyor():
    # A ∈ [0, 120]: (−40, −150) elenir, önceki ona yakın olsa da (40, 30) seçilir.
    kin = _ac(a_min=0.0, a_max=120.0)
    _esit(inverse_axes(kin, _ac_yonu(40.0, 30.0), prev=(-40.0, -140.0)), (40.0, 30.0))


def test_k6_onceki_konuma_en_yakin():
    kin = _ac()
    a_w = _ac_yonu(40.0, 30.0)
    _esit(inverse_axes(kin, a_w, prev=(-35.0, -160.0)), (-40.0, -150.0))
    _esit(inverse_axes(kin, a_w, prev=(35.0, 20.0)), (40.0, 30.0))
    # önceki yoksa önceki = 0: |40| + |30| < |−40| + |−150|
    _esit(inverse_axes(kin, a_w), (40.0, 30.0))


def test_k6_esitlikte_birinci_eksen_kucuk():
    # (40, 90) ve (−40, −90): önceki 0'a uzaklık eşit (130) → A küçük olan.
    _esit(inverse_axes(_ac(), _ac_yonu(40.0, 90.0), prev=(0.0, 0.0)), (-40.0, -90.0))


def test_k6_surekli_c_sarma():
    # önceki C = 350°, hedef 10° → 370°
    _esit(inverse_axes(_ac(), _ac_yonu(40.0, 10.0), prev=(40.0, 350.0)), (40.0, 370.0))


def test_k6_gecerli_aday_yok():
    kin = _ac(a_min=50.0, a_max=120.0)
    with pytest.raises(CamError):
        inverse_axes(kin, _ac_yonu(40.0, 30.0))
    with pytest.raises(CamError):
        inverse(kin, (0.0, 0.0, 0.0), _ac_yonu(40.0, 30.0), 90.0, Wcs())


def test_k6_inverse_secimi_kullaniyor():
    kin = _ac()
    a_w = _ac_yonu(40.0, 10.0)
    q = inverse(kin, (1.0, 2.0, 3.0), a_w, 90.0, Wcs(), prev=(40.0, 350.0))
    _esit(tuple(q[3:]), (40.0, 370.0))


# ---------------------------------------------------------------- K7 tekillik, 4 ve 3 eksen


def test_k7_ac_dusey_eksen_c_onceki_degerde():
    kin = _ac()
    _esit(inverse_axes(kin, (0.0, 0.0, 1.0), prev=(20.0, 77.0)), (0.0, 77.0))
    _esit(inverse_axes(kin, (0.0, 0.0, 1.0)), (0.0, 0.0))
    q = inverse(kin, (4.0, 5.0, 6.0), (0.0, 0.0, 1.0), 90.0, Wcs(origin=(1.0, 1.0, 1.0)), prev=(20.0, 77.0))
    _esit(tuple(q[3:]), (0.0, 77.0))
    tip, a = forward(kin, q, 90.0, Wcs(origin=(1.0, 1.0, 1.0)))
    np.testing.assert_allclose(tip, [4.0, 5.0, 6.0], atol=TOL)
    np.testing.assert_allclose(a, [0.0, 0.0, 1.0], atol=TOL)


def test_k7_dort_eksen_tek_a():
    kin = Kinematics(rotary=(RotaryAxis("A", "masa", (1.0, 0.0, 0.0), (0.0, 0.0, 0.0), -120.0, 120.0),))
    # a_w = Rx(−A)·z = (0, sin A, cos A)
    a_w = (0.0, math.sin(math.radians(30.0)), math.cos(math.radians(30.0)))
    _esit(inverse_axes(kin, a_w), (30.0,))
    wcs = Wcs(origin=(0.0, 0.0, 100.0))
    q = inverse(kin, (2.0, 3.0, 4.0), a_w, 60.0, wcs)
    assert q.shape == (4,)
    tip, a = forward(kin, q, 60.0, wcs)
    np.testing.assert_allclose(tip, [2.0, 3.0, 4.0], atol=TOL)
    np.testing.assert_allclose(a, a_w, atol=TOL)
    with pytest.raises(CamError):  # ω·p = 0, ω·q = 1
        inverse_axes(kin, (1.0, 0.0, 0.0))
    with pytest.raises(CamError):
        inverse_axes(kin, _yon(30.0, 45.0))


def test_k7_uc_eksen():
    kin = Kinematics()
    assert tuple(inverse_axes(kin, (0.0, 0.0, 1.0))) == ()
    # (X, Y, Z) = p_w + o_wcs − tip₀, tip₀ = g − L·s = (0, 0, −50)
    q = inverse(kin, (1.0, 2.0, 3.0), (0.0, 0.0, 1.0), 50.0, Wcs(origin=(10.0, 20.0, 30.0)))
    assert q.shape == (3,)
    np.testing.assert_allclose(q, [11.0, 22.0, 83.0], atol=TOL)
    with pytest.raises(CamError):
        inverse_axes(kin, (0.0, 1.0, 0.0))
    with pytest.raises(CamError):
        inverse(kin, (1.0, 2.0, 3.0), (0.0, S2, S2), 50.0, Wcs())


def test_k7_ulasilamaz_yon_temel_cozumlerde():
    # Alt problem 2'de γ² < 0: nutasyonlu masa, eğim 150° → sınırdan bağımsız çözüm de yok.
    with pytest.raises(CamError):
        all_solutions(_nutasyonlu(), _yon(150.0, 10.0))
