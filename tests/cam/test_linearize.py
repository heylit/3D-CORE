"""SPEC 42 — eklem uzayında doğrusallaştırma ve G93 ters zaman testleri (K7–K9, K10 max_depth).

Testler yalnız SPEC 42 metninden, `cam/model.py` arayüzünden ve SPEC 41 kinematiğinden
(`cam.multiaxis.kinematics.forward / inverse`, main'de) yazıldı; `cam/multiaxis/linearize.py`
gövdeleri okunmadı (iskelette NotImplementedError).

Kurallar: kontrolör eklemleri doğrusal enterpole eder, q(t) = q₀ + t(q₁ − q₀).
e_p(t) = dist(forward(q(t)), [p₀, p₁]), e_a(t) = angle(a(t), slerp(a₀, a₁, t)).
Başlangıç noktasının ekseni ilk hareketin eksenidir (41 `to_machine` kuralı); yollar bu yüzden
ilk hareketi başlangıçla aynı eksenli bir yaklaşma olarak kurar.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from cam.model import CamError, Kinematics, Move, MoveType, RotaryAxis, Tool, ToolKind, Toolpath, Wcs
from cam.multiaxis.kinematics import forward
from cam.multiaxis.linearize import deviation, inverse_time, joint_path, linearize

G1 = MoveType.LINEAR
TOL = 1e-9
L_TAKIM = 50.0
TOOL = Tool(id=1, name="K6", kind=ToolKind.BALL, D=6.0, flute_length=20.0)


# ---------------------------------------------------------------- yardımcılar


def _slerp(a0: np.ndarray, a1: np.ndarray, t: float) -> np.ndarray:
    w = math.acos(float(np.clip(a0 @ a1, -1.0, 1.0)))
    if w < 1e-12:
        return a0.copy()
    return (math.sin((1.0 - t) * w) * a0 + math.sin(t * w) * a1) / math.sin(w)


def _aci(u, v) -> float:
    return math.degrees(math.atan2(np.linalg.norm(np.cross(u, v)), float(np.dot(u, v))))


def _parca_uzaklik(x: np.ndarray, p0: np.ndarray, p1: np.ndarray) -> float:
    d = p1 - p0
    if not d.any():
        return float(np.linalg.norm(x - p0))
    s = float(np.clip((x - p0) @ d / (d @ d), 0.0, 1.0))
    return float(np.linalg.norm(x - (p0 + s * d)))


def _eksenler(tp: Toolpath) -> np.ndarray:
    A = [m.axis if m.axis is not None else (0.0, 0.0, 1.0) for m in tp.moves]
    return np.array([A[0]] + A, dtype=float)


def _yol(start, hareketler, feed: float = 500.0) -> Toolpath:
    moves = [Move(G1, tuple(p), feed=feed, axis=tuple(a)) for p, a in hareketler]
    return Toolpath(name="5x", tool=TOOL, start=tuple(start), moves=moves, rpm=10000.0)


def _a_masa() -> Kinematics:
    return Kinematics(rotary=(RotaryAxis("A", "masa", (1.0, 0.0, 0.0), (0.0, 0.0, 0.0)),))


def _ac_masa() -> Kinematics:
    return Kinematics(
        rotary=(
            RotaryAxis("A", "masa", (1.0, 0.0, 0.0), (0.0, 15.0, -60.0), -120.0, 120.0),
            RotaryAxis("C", "masa", (0.0, 0.0, 1.0), (4.0, -2.0, 0.0)),
        )
    )


def _yay_yolu(r: float = 50.0, delta: float = 30.0, x0: float = 20.0) -> Toolpath:
    """A eksenine r uzak iki uç noktası, radyal eksen: makinede uç yerinde kalır, yalnız A döner."""

    def p(phi):
        f = math.radians(phi)
        return np.array([x0, r * math.sin(f), r * math.cos(f)])

    def a(phi):
        f = math.radians(phi)
        return np.array([0.0, math.sin(f), math.cos(f)])

    # yaklaşma (radyal, A sabit) + dönme hareketi
    return _yol(p(0.0) + 10.0 * a(0.0), [(p(0.0), a(0.0)), (p(delta), a(delta))])


def _m_kapali(r: float, delta: float, tol: float) -> int:
    """r(1 − cos(Δ / 2^{m+1})) ≤ tol olan en küçük m."""
    m = 0
    while r * (1.0 - math.cos(math.radians(delta) / 2 ** (m + 1))) > tol:
        m += 1
    return m


def _sapmalar(tp: Toolpath, kin: Kinematics, wcs: Wcs, ts) -> tuple[float, float]:
    """Her harekette verilen t'lerde en büyük (e_p, e_a), testin kendi forward hesabıyla."""
    Q = joint_path(tp, kin, wcs, L_TAKIM)
    P = tp.points()
    A = _eksenler(tp)
    ep = ea = 0.0
    for i in range(len(tp.moves)):
        for t in ts:
            tip, a = forward(kin, Q[i] + t * (Q[i + 1] - Q[i]), L_TAKIM, wcs)
            ep = max(ep, _parca_uzaklik(tip, P[i], P[i + 1]))
            ea = max(ea, _aci(a, _slerp(A[i], A[i + 1], t)))
    return ep, ea


def _alt_dizi(kucuk: np.ndarray, buyuk: np.ndarray) -> bool:
    j = 0
    for p in kucuk:
        while j < len(buyuk) and np.linalg.norm(buyuk[j] - p) > TOL:
            j += 1
        if j == len(buyuk):
            return False
    return True


# ---------------------------------------------------------------- joint_path


def test_joint_path_41_ters_kinematigiyle_ayni():
    kin, wcs = _ac_masa(), Wcs(origin=(100.0, 50.0, -200.0))
    tp = _rastgele_yol()
    Q = joint_path(tp, kin, wcs, L_TAKIM)
    assert Q.shape == (len(tp.moves) + 1, 5)
    for q, p, a in zip(Q, tp.points(), _eksenler(tp), strict=True):
        tip, ax = forward(kin, q, L_TAKIM, wcs)
        np.testing.assert_allclose(tip, p, atol=TOL)
        np.testing.assert_allclose(ax, a, atol=TOL)


# ---------------------------------------------------------------- K7 analitik


def test_k7_orta_nokta_sapmasi():
    r, delta = 50.0, 30.0
    kin, wcs = _a_masa(), Wcs()
    tp = _yay_yolu(r, delta)
    Q = joint_path(tp, kin, wcs, L_TAKIM)
    np.testing.assert_allclose(Q[1, :3], Q[2, :3], atol=TOL)  # makinede uç yerinde, yalnız A döner
    assert abs(Q[2, 3] - Q[1, 3] - delta) < TOL
    P, A = tp.points(), _eksenler(tp)
    e_p, e_a = deviation(kin, wcs, L_TAKIM, Q[1], Q[2], P[1], P[2], A[1], A[2], 0.5)
    assert abs(e_p - r * (1.0 - math.cos(math.radians(delta / 2)))) < TOL
    assert abs(e_a) < 1e-7
    # t = ¼: yay noktası kirişin ortasından Δ/4 açıda → r(cos(Δ/4) − cos(Δ/2))
    e_p, _ = deviation(kin, wcs, L_TAKIM, Q[1], Q[2], P[1], P[2], A[1], A[2], 0.25)
    assert abs(e_p - r * (math.cos(math.radians(delta / 4)) - math.cos(math.radians(delta / 2)))) < TOL
    # yaklaşma hareketi (A sabit, doğrusal) sapmasız
    e_p, e_a = deviation(kin, wcs, L_TAKIM, Q[0], Q[1], P[0], P[1], A[0], A[1], 0.5)
    assert e_p < TOL and e_a < 1e-7


def test_k7_bolum_sayisi_kapali_form():
    r, delta, tol_p = 50.0, 30.0, 1e-3
    m = _m_kapali(r, delta, tol_p)
    assert m == 6
    kin, wcs = _a_masa(), Wcs()
    tp = _yay_yolu(r, delta)
    lt = linearize(tp, kin, wcs, L_TAKIM, tol_p=tol_p)
    assert lt.frame is None
    assert all(mv.axis is not None for mv in lt.moves)
    assert len(lt.moves) == 1 + 2**m  # yaklaşma bölünmez
    np.testing.assert_allclose(lt.points()[[0, 1, -1]], tp.points(), atol=TOL)
    ep, ea = _sapmalar(lt, kin, wcs, (0.25, 0.5, 0.75))
    assert ep <= tol_p + TOL
    assert ea <= 0.05


# ---------------------------------------------------------------- K8 genel


def _rastgele_yol(seed: int = 8, n: int = 12) -> Toolpath:
    rng = np.random.default_rng(seed)
    p = np.array([0.0, 0.0, 10.0])
    tilt, az = 25.0, 30.0
    hareketler = []

    def yon():
        t, a = math.radians(tilt), math.radians(az)
        return np.array([math.sin(t) * math.cos(a), math.sin(t) * math.sin(a), math.cos(t)])

    start = p + 5.0 * yon()
    hareketler.append((p.copy(), yon()))
    for _ in range(n):
        p = p + rng.uniform(-8.0, 8.0, size=3)
        tilt = float(np.clip(tilt + rng.uniform(-6.0, 6.0), 15.0, 40.0))
        az += rng.uniform(-10.0, 10.0)
        hareketler.append((p.copy(), yon()))
    return _yol(start, hareketler)


def test_k8_ac_masada_yogun_ornekleme():
    kin, wcs = _ac_masa(), Wcs(origin=(100.0, 50.0, -200.0))
    tp = _rastgele_yol()
    tol_p, tol_a = 1e-3, 0.05
    ep0, ea0 = _sapmalar(tp, kin, wcs, (0.5,))
    assert ep0 > tol_p  # bölmeden önce tolerans aşılıyor (test anlamlı)
    lt = linearize(tp, kin, wcs, L_TAKIM, tol_p=tol_p, tol_a=tol_a)
    assert len(lt.moves) > len(tp.moves)
    assert _alt_dizi(tp.points(), lt.points())  # özgün noktalar sırayla korunuyor
    ep, ea = _sapmalar(lt, kin, wcs, np.linspace(0.0, 1.0, 101))
    assert ep <= tol_p + TOL
    assert ea <= tol_a + 1e-9


def test_k8_uc_eksende_yol_degismiyor():
    kin, wcs = Kinematics(), Wcs(origin=(10.0, 0.0, -50.0))
    z = (0.0, 0.0, 1.0)
    tp = _yol((0.0, 0.0, 20.0), [((0.0, 0.0, 5.0), z), ((40.0, 10.0, 2.0), z), ((-5.0, 30.0, 0.0), z)])
    lt = linearize(tp, kin, wcs, L_TAKIM)
    assert len(lt.moves) == len(tp.moves)
    np.testing.assert_allclose(lt.points(), tp.points(), atol=1e-12)
    assert [m.type for m in lt.moves] == [m.type for m in tp.moves]


# ---------------------------------------------------------------- K9 ters zaman


def _ters_zaman_yolu() -> Toolpath:
    # Uç A ekseni üstünde: (30, 0, 0)'da yalnız yönelim değişir (L = 0).
    z = np.array([0.0, 0.0, 1.0])
    a30 = np.array([0.0, math.sin(math.radians(30.0)), math.cos(math.radians(30.0))])
    return Toolpath(
        name="g93",
        tool=TOOL,
        start=(10.0, 0.0, 0.0),
        moves=[
            Move(G1, (30.0, 0.0, 0.0), feed=500.0, axis=tuple(z)),  # L = 20 → 25
            Move(G1, (30.0, 0.0, 0.0), feed=500.0, axis=tuple(a30)),  # yalnız A: 30°
            Move(G1, (30.0, 10.0, 0.0), feed=800.0, axis=tuple(a30)),  # L = 10 → 80
        ],
        rpm=10000.0,
    )


def test_k9_ters_zaman_degerleri():
    kin, wcs = _a_masa(), Wcs()
    tp = _ters_zaman_yolu()
    q = joint_path(tp, kin, wcs, L_TAKIM)
    assert abs(q[2, 3] - q[1, 3] - 30.0) < TOL
    F = inverse_time(tp, q, F_rot=600.0)
    assert F.shape == (3,)
    # 1: F/L = 500/20; 2: t = 30°/600 = 0.05 dk → 20; 3: 800/10
    np.testing.assert_allclose(F, [25.0, 20.0, 80.0], rtol=1e-12)


def test_k9_rastgele_f_bolu_l():
    kin, wcs = _ac_masa(), Wcs()
    tp = _rastgele_yol(seed=9, n=6)
    q = joint_path(tp, kin, wcs, L_TAKIM)
    P = tp.points()
    beklenen = [m.feed / np.linalg.norm(P[i + 1] - P[i]) for i, m in enumerate(tp.moves)]
    np.testing.assert_allclose(inverse_time(tp, q), beklenen, rtol=1e-12)


def test_k9_hatalar():
    kin, wcs = _a_masa(), Wcs()
    tp = _ters_zaman_yolu()
    q = joint_path(tp, kin, wcs, L_TAKIM)
    with pytest.raises(CamError):  # L = 0 ve F_rot yok
        inverse_time(tp, q)
    with pytest.raises(CamError):  # 80 > 40
        inverse_time(tp, q, F_rot=600.0, inv_max=40.0)
    kisa = Toolpath(
        name="kisa",
        tool=TOOL,
        start=(0.0, 0.0, 0.0),
        moves=[Move(G1, (1e-6, 0.0, 0.0), feed=1000.0, axis=(0.0, 0.0, 1.0))],
        rpm=10000.0,
    )
    with pytest.raises(CamError):  # 1000 / 1e-6 = 1e9 > 99999
        inverse_time(kisa, joint_path(kisa, kin, wcs, L_TAKIM))


# ---------------------------------------------------------------- K10 max_depth


def test_k10_max_depth_asimi():
    kin, wcs = _a_masa(), Wcs()
    with pytest.raises(CamError):  # gereken derinlik 6
        linearize(_yay_yolu(), kin, wcs, L_TAKIM, tol_p=1e-3, max_depth=3)
