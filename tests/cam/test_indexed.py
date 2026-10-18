"""SPEC 41 — iş düzlemi (Frame), Euler açıları ve 3+2 indeksli işleme testleri (K2, K3, K8–K10).

Testler yalnız SPEC 41 metninden ve `cam/model.py` arayüzünden (`Frame`, `Toolpath.frame`, `Move.axis`,
`Kinematics`, `RotaryAxis`, `Stock`, `Wcs`) ve `cam.dropcutter.TriMesh`'ten yazıldı;
`cam/multiaxis/indexed.py` ve `kinematics.py` gövdeleri okunmadı (iskelette NotImplementedError).

`Frame.R` modelde satır satır saklanır: `np.array(frame.R)` SPEC'teki R matrisidir, sütunları yerel
x, y, z eksenleri (p_w = o + R·p_l). ZXZ: R = Rz(α)·Rx(β)·Rz(γ); XYZ: R = Rz(c)·Ry(b)·Rx(a).
"""

from __future__ import annotations

import itertools
import math

import numpy as np
import pytest

from cam.dropcutter import TriMesh
from cam.model import (
    CamError,
    Frame,
    Kinematics,
    Move,
    MoveType,
    RotaryAxis,
    Stock,
    Tool,
    ToolKind,
    Toolpath,
    Wcs,
)
from cam.multiaxis.indexed import (
    from_normal,
    from_xyz,
    from_zxz,
    local_mesh,
    local_stock,
    machine_toolpath,
    to_machine,
    to_world,
    xyz_angles,
    zxz_angles,
)
from cam.multiaxis.kinematics import forward, inverse

G0, G1, G2, G3 = MoveType.RAPID, MoveType.LINEAR, MoveType.ARC_CW, MoveType.ARC_CCW
TOL = 1e-9
S30, C30 = 0.5, math.sqrt(3.0) / 2.0


# ---------------------------------------------------------------- yardımcılar


def _Rx(t: float) -> np.ndarray:
    c, s = math.cos(math.radians(t)), math.sin(math.radians(t))
    return np.array([[1.0, 0.0, 0.0], [0.0, c, -s], [0.0, s, c]])


def _Ry(t: float) -> np.ndarray:
    c, s = math.cos(math.radians(t)), math.sin(math.radians(t))
    return np.array([[c, 0.0, s], [0.0, 1.0, 0.0], [-s, 0.0, c]])


def _Rz(t: float) -> np.ndarray:
    c, s = math.cos(math.radians(t)), math.sin(math.radians(t))
    return np.array([[c, -s, 0.0], [s, c, 0.0], [0.0, 0.0, 1.0]])


def _R(frame: Frame) -> np.ndarray:
    return np.array(frame.R, dtype=float)


def _fark(a: float, b: float) -> float:
    return (a - b + 180.0) % 360.0 - 180.0


def _aci_esit(got, beklenen, tol: float = TOL) -> None:
    assert len(got) == len(beklenen)
    for g, b in zip(got, beklenen, strict=True):
        assert abs(_fark(g, b)) < tol, (got, beklenen)


def _kama_cercevesi() -> Frame:
    """30° eğik yüz: normal (0, −sin30, cos30), x ipucu +X, köken yüz üstünde."""
    return from_normal((0.0, 0.0, 20.0), (0.0, -S30, C30), (1.0, 0.0, 0.0))


R_KOSE = 5.0
Z_TABAN, Z_GUVENLI = -2.0, 5.0


def _cep_yolu(frame: Frame | None) -> Toolpath:
    """Yerel çerçevede 40 × 20 dikdörtgen cep turu, köşeler r = 5 saat yönü tersi yaylı (elle kurulmuş)."""
    z = Z_TABAN
    f = 600.0
    moves = [
        Move(G1, (-15.0, -10.0, z), feed=200.0),
        Move(G1, (15.0, -10.0, z), feed=f),
        Move(G3, (20.0, -5.0, z), feed=f, center=(15.0, -5.0)),
        Move(G1, (20.0, 5.0, z), feed=f),
        Move(G3, (15.0, 10.0, z), feed=f, center=(15.0, 5.0)),
        Move(G1, (-15.0, 10.0, z), feed=f),
        Move(G3, (-20.0, 5.0, z), feed=f, center=(-15.0, 5.0)),
        Move(G1, (-20.0, -5.0, z), feed=f),
        Move(G3, (-15.0, -10.0, z), feed=f, center=(-15.0, -5.0)),
        Move(G0, (-15.0, -10.0, Z_GUVENLI)),
    ]
    tool = Tool(id=1, name="F6", kind=ToolKind.FLAT, D=6.0, flute_length=20.0)
    tp = Toolpath(
        name="cep", tool=tool, start=(-15.0, -10.0, Z_GUVENLI), moves=moves, rpm=8000.0, frame=frame
    )
    tp.validate()
    return tp


def _ac_masa() -> Kinematics:
    return Kinematics(
        rotary=(
            RotaryAxis("A", "masa", (1.0, 0.0, 0.0), (0.0, 10.0, -60.0), -120.0, 120.0),
            RotaryAxis("C", "masa", (0.0, 0.0, 1.0), (5.0, -3.0, 0.0)),
        )
    )


def _yerel_mesafe(p: np.ndarray, tp: Toolpath) -> float:
    """Yerel nokta p'nin cep yolunun (doğru parçaları + yaylar) yerel geometrisine uzaklığı."""
    best = math.inf
    p0 = np.array(tp.start)
    for m in tp.moves:
        p1 = np.array(m.end)
        if m.type in (G2, G3):
            c = np.array([m.center[0], m.center[1]])
            rho = float(np.hypot(*(p[:2] - c)))
            best = min(best, math.hypot(rho - R_KOSE, p[2] - p1[2]))
        else:
            d = p1 - p0
            t = 0.0 if not d.any() else float(np.clip((p - p0) @ d / (d @ d), 0.0, 1.0))
            best = min(best, float(np.linalg.norm(p - (p0 + t * d))))
        p0 = p1
    return best


# ---------------------------------------------------------------- K2 Frame


def test_k2_from_normal_egik_duzlem():
    n = np.array([0.0, -S30, C30])
    x_hint = np.array([1.0, 1.0, 0.0])
    fr = from_normal((1.0, 2.0, 3.0), 4.0 * n, x_hint)  # |n| ≠ 1 normalize edilir
    assert isinstance(fr, Frame)
    R = _R(fr)
    x = x_hint - (x_hint @ n) * n
    x /= np.linalg.norm(x)
    np.testing.assert_allclose(R[:, 2], n, atol=1e-12)
    np.testing.assert_allclose(R[:, 0], x, atol=1e-12)
    np.testing.assert_allclose(R[:, 1], np.cross(n, x), atol=1e-12)
    np.testing.assert_allclose(fr.origin, (1.0, 2.0, 3.0), atol=0)
    np.testing.assert_allclose(R.T @ R, np.eye(3), atol=1e-12)
    assert np.linalg.det(R) > 0


def test_k2_to_world_to_local_birim():
    fr = from_normal((10.0, -20.0, 5.0), (1.0, 2.0, 3.0), (0.0, 1.0, 0.0))
    rng = np.random.default_rng(2)
    P = rng.uniform(-100.0, 100.0, size=(20, 3))
    np.testing.assert_allclose(fr.to_world(fr.to_local(P)), P, atol=1e-12)
    np.testing.assert_allclose(fr.to_local(fr.to_world(P)), P, atol=1e-12)
    # yerel +z → WCS'de normal; köken → origin
    np.testing.assert_allclose(
        fr.to_world_vec((0.0, 0.0, 1.0)), np.array([1.0, 2.0, 3.0]) / math.sqrt(14), atol=1e-12
    )
    np.testing.assert_allclose(fr.to_world((0.0, 0.0, 0.0)), (10.0, -20.0, 5.0), atol=1e-12)


def test_k2_gecersiz_cerceveler():
    with pytest.raises(CamError):  # ortonormal değil
        Frame(origin=(0.0, 0.0, 0.0), R=((1.0, 0.0, 0.0), (0.0, 2.0, 0.0), (0.0, 0.0, 1.0)))
    with pytest.raises(CamError):  # det < 0 (yansıma)
        Frame(origin=(0.0, 0.0, 0.0), R=((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, -1.0)))
    with pytest.raises(CamError):  # n = 0
        from_normal((0.0, 0.0, 0.0), (0.0, 0.0, 0.0), (1.0, 0.0, 0.0))
    with pytest.raises(CamError):  # x_hint ∥ n
        from_normal((0.0, 0.0, 0.0), (0.0, -S30, C30), (0.0, -2.0 * S30, 2.0 * C30))
    with pytest.raises(CamError):  # x_hint ∥ −n
        from_normal((0.0, 0.0, 0.0), (0.0, 0.0, 1.0), (0.0, 0.0, -3.0))


# ---------------------------------------------------------------- K3 Euler açıları


def test_k3_zxz_matris_tanimi():
    o = (1.0, 2.0, 3.0)
    fr = from_zxz(o, 25.0, 40.0, -70.0)
    np.testing.assert_allclose(_R(fr), _Rz(25.0) @ _Rx(40.0) @ _Rz(-70.0), atol=1e-12)
    np.testing.assert_allclose(fr.origin, o, atol=0)


def test_k3_xyz_matris_tanimi():
    o = (-4.0, 0.0, 9.0)
    fr = from_xyz(o, 15.0, -35.0, 120.0)
    np.testing.assert_allclose(_R(fr), _Rz(120.0) @ _Ry(-35.0) @ _Rx(15.0), atol=1e-12)
    np.testing.assert_allclose(fr.origin, o, atol=0)


def test_k3_zxz_gidip_donus_rastgele():
    rng = np.random.default_rng(3)
    for _ in range(100):
        a, g = rng.uniform(-179.0, 179.0, size=2)
        b = rng.uniform(1.0, 179.0)
        ang = zxz_angles(from_zxz((0.0, 0.0, 0.0), a, b, g))
        _aci_esit(ang, (a, b, g))
        assert 0.0 <= ang[1] <= 180.0


def test_k3_xyz_gidip_donus_rastgele():
    rng = np.random.default_rng(33)
    for _ in range(100):
        a, c = rng.uniform(-179.0, 179.0, size=2)
        b = rng.uniform(-89.0, 89.0)
        ang = xyz_angles(from_xyz((0.0, 0.0, 0.0), a, b, c))
        _aci_esit(ang, (a, b, c))
        assert -90.0 <= ang[1] <= 90.0


def test_k3_zxz_tekil():
    # β = 0: R = Rz(α + γ) → (α + γ, 0, 0)
    _aci_esit(zxz_angles(from_zxz((0.0, 0.0, 0.0), 30.0, 0.0, 20.0)), (50.0, 0.0, 0.0))
    for a, b, g in ((30.0, 0.0, 20.0), (30.0, 180.0, 20.0), (-100.0, 180.0, 75.0)):
        fr = from_zxz((0.0, 0.0, 0.0), a, b, g)
        ang = zxz_angles(fr)
        assert abs(ang[2]) < TOL  # γ = 0 kuralı
        _aci_esit((ang[1],), (b,))
        np.testing.assert_allclose(_R(from_zxz((0.0, 0.0, 0.0), *ang)), _R(fr), atol=TOL)


def test_k3_xyz_tekil():
    for a, b, c in ((40.0, 90.0, 10.0), (40.0, -90.0, 10.0), (-120.0, 90.0, 60.0)):
        fr = from_xyz((0.0, 0.0, 0.0), a, b, c)
        ang = xyz_angles(fr)
        assert abs(ang[2]) < TOL  # c = 0 kuralı
        _aci_esit((ang[1],), (b,))
        np.testing.assert_allclose(_R(from_xyz((0.0, 0.0, 0.0), *ang)), _R(fr), atol=TOL)


def test_k3_ornek_alfa90_beta90():
    fr = from_zxz((0.0, 0.0, 0.0), 90.0, 90.0, 0.0)
    np.testing.assert_allclose(_R(fr)[:, 2], (1.0, 0.0, 0.0), atol=1e-12)
    _aci_esit(zxz_angles(fr), (90.0, 90.0, 0.0))


# ---------------------------------------------------------------- K8 3+2 uçtan uca


def test_k8_to_world_egik_duzlem_ve_kiris():
    fr = _kama_cercevesi()
    tp = _cep_yolu(fr)
    tol = 1e-3
    wt = to_world(tp, arc_tol=tol)
    assert wt.frame is None
    wt.validate()
    n = _R(fr)[:, 2]
    assert all(m.type in (G0, G1) for m in wt.moves)  # yaylar kirişlere bölündü
    for m in wt.moves:
        assert m.axis is not None
        np.testing.assert_allclose(m.axis, n, atol=1e-12)
    # her nokta eğik düzlemlerde: n·(p − o) ∈ {taban, güvenli}
    P = wt.points()
    h = (P - np.array(fr.origin)) @ n
    assert np.all(np.minimum(np.abs(h - Z_TABAN), np.abs(h - Z_GUVENLI)) < TOL)
    np.testing.assert_allclose(P[0], fr.to_world(tp.start), atol=TOL)
    np.testing.assert_allclose(P[-1], fr.to_world(tp.moves[-1].end), atol=TOL)
    # özgün uç noktaları sırayla korunuyor
    Pl = fr.to_local(P)
    j = 0
    for m in tp.moves:
        while j < len(Pl) and np.linalg.norm(Pl[j] - np.array(m.end)) > TOL:
            j += 1
        assert j < len(Pl), m
    # kiriş sapması ≤ arc_tol: her parçanın her noktası yerel yola tol yakın
    for a, b in itertools.pairwise(Pl):
        for t in np.linspace(0.0, 1.0, 11):
            assert _yerel_mesafe(a + t * (b - a), tp) <= tol + TOL
    # kiriş sayısı SPEC 05: n = ⌈|Δθ| / (2·acos(1 − ε/r))⌉, her köşe 90°
    n_kiris = math.ceil((math.pi / 2) / (2.0 * math.acos(1.0 - tol / R_KOSE)))
    assert len(wt.moves) == 6 + 4 * n_kiris


def test_k8_to_machine_ileri_kinematikle_tutarli():
    fr = _kama_cercevesi()
    wt = to_world(_cep_yolu(fr))
    kin = _ac_masa()
    wcs = Wcs(origin=(150.0, 80.0, -250.0))
    L = 100.0
    Q = to_machine(wt, kin, wcs, L)
    P = wt.points()
    assert Q.shape == (len(P), 5)
    n = _R(fr)[:, 2]
    # a_w = (sin A sin C, sin A cos C, cos A) = (0, −sin30, cos30) → (30, 180) veya (−30, 0);
    # önceki 0 → (−30, 0)
    np.testing.assert_allclose(Q[:, 3], -30.0, atol=TOL)
    np.testing.assert_allclose(Q[:, 4], 0.0, atol=TOL)
    for q, p in zip(Q, P, strict=True):
        tip, a = forward(kin, q, L, wcs)
        np.testing.assert_allclose(tip, p, atol=TOL)
        np.testing.assert_allclose(a, n, atol=TOL)


def test_k8_machine_toolpath_ac_masa():
    fr = _kama_cercevesi()
    tp = _cep_yolu(fr)
    kin = _ac_masa()
    wcs = Wcs(origin=(150.0, 80.0, -250.0))
    L = 100.0
    mt, ang = machine_toolpath(tp, kin, wcs, L)
    _aci_esit(ang, (-30.0, 0.0))
    assert mt.frame is None
    assert mt.plane.value == "G17"
    mt.validate()
    assert [m.type for m in mt.moves] == [m.type for m in tp.moves]  # yaylar yay kalıyor
    M = mt.points()
    Pl = tp.points()
    # cep tabanı aynı makine Z'sinde, güvenli düzlem 7 mm yukarıda
    taban = np.abs(Pl[:, 2] - Z_TABAN) < TOL
    assert taban.sum() >= 9
    z0 = M[taban, 2][0]
    np.testing.assert_allclose(M[taban, 2], z0, atol=TOL)
    np.testing.assert_allclose(M[~taban, 2], z0 + (Z_GUVENLI - Z_TABAN), atol=TOL)
    # katı hareket: noktalar arası uzaklıklar korunuyor
    for i, j in itertools.combinations(range(len(Pl)), 2):
        assert abs(np.linalg.norm(M[i] - M[j]) - np.linalg.norm(Pl[i] - Pl[j])) < TOL
    # yay yarıçapları korunuyor (makine XY'sinde)
    m_prev = M[0]
    for m in mt.moves:
        if m.type in (G2, G3):
            c = np.array(m.center)
            assert abs(np.hypot(*(np.array(m.end[:2]) - c)) - R_KOSE) < TOL
            assert abs(np.hypot(*(m_prev[:2] - c)) - R_KOSE) < TOL
        m_prev = np.array(m.end)
    # eklem değerleriyle (ters kinematik) aynı yol, en çok sabit bir ötelemeyle (ölçü noktası / takım boyu)
    n = _R(fr)[:, 2]
    J = np.array([inverse(kin, fr.to_world(p), n, L, wcs)[:3] for p in Pl])
    np.testing.assert_allclose(M - J, np.broadcast_to((M - J)[0], M.shape), atol=TOL)


def test_k8_kafa_ekseninde_yayli_yol_hata():
    kin = Kinematics(
        rotary=(
            RotaryAxis("B", "kafa", (0.0, 1.0, 0.0), (0.0, 0.0, 180.0), -120.0, 120.0),
            RotaryAxis("C", "masa", (0.0, 0.0, 1.0), (0.0, 0.0, 0.0)),
        )
    )
    with pytest.raises(CamError):
        machine_toolpath(_cep_yolu(_kama_cercevesi()), kin, Wcs(), 100.0)


# ---------------------------------------------------------------- K9 4 eksen indeksleme


def test_k9_dort_eksen_silindir_cevresi():
    # Yatay A (+X) masa ekseni WCS kökenine hizalı; R = 30 silindir yüzünde dört iş düzlemi.
    kin = Kinematics(rotary=(RotaryAxis("A", "masa", (1.0, 0.0, 0.0), (100.0, 0.0, 50.0), -10.0, 300.0),))
    wcs = Wcs(origin=(100.0, 0.0, 50.0))
    L = 80.0
    tool = Tool(id=2, name="M8", kind=ToolKind.DRILL, D=8.0, flute_length=40.0)
    yollar, makine = [], []
    for phi in (0.0, 90.0, 180.0, 270.0):
        n = np.array([0.0, math.sin(math.radians(phi)), math.cos(math.radians(phi))])
        fr = from_normal(30.0 * n, n, (1.0, 0.0, 0.0))
        tp = Toolpath(
            name=f"delik{int(phi)}",
            tool=tool,
            start=(5.0, 0.0, 5.0),
            moves=[Move(G1, (5.0, 0.0, -10.0), feed=100.0), Move(G0, (5.0, 0.0, 5.0))],
            rpm=3000.0,
            frame=fr,
        )
        mt, ang = machine_toolpath(tp, kin, wcs, L)
        # a_w = Rx(−A)·z = (0, sin A, cos A) → A = φ
        _aci_esit(ang, (phi,))
        yollar.append(mt)
        Q = to_machine(to_world(tp), kin, wcs, L)
        np.testing.assert_allclose(Q[:, 3], phi, atol=TOL)
        makine.append(Q[:, :3])
    for mt, Q in zip(yollar[1:], makine[1:], strict=True):
        assert [m.type for m in mt.moves] == [m.type for m in yollar[0].moves]
        np.testing.assert_allclose(mt.points(), yollar[0].points(), atol=TOL)
        np.testing.assert_allclose(Q, makine[0], atol=TOL)


# ---------------------------------------------------------------- K10 local_stock, local_mesh


def test_k10_local_stock_koseleri_kapsiyor():
    st = Stock(0.0, 0.0, 0.0, 100.0, 60.0, 40.0)
    fr = from_normal((50.0, 30.0, 40.0), (0.0, -S30, C30), (1.0, 0.0, 0.0))
    ls = local_stock(st, fr)
    assert isinstance(ls, Stock)
    K = np.array(list(itertools.product((st.xmin, st.xmax), (st.ymin, st.ymax), (st.zmin, st.zmax))))
    Kl = fr.to_local(K)
    lo = np.array([ls.xmin, ls.ymin, ls.zmin])
    hi = np.array([ls.xmax, ls.ymax, ls.zmax])
    assert np.all(Kl >= lo - TOL) and np.all(Kl <= hi + TOL)
    for i in range(3):  # her yüzde en az bir köşe
        assert np.min(np.abs(Kl[:, i] - lo[i])) < TOL
        assert np.min(np.abs(Kl[:, i] - hi[i])) < TOL


def test_k10_local_mesh_geri_cevirme():
    V = np.array([[10.0, 10.0, 0.0], [60.0, 10.0, 0.0], [10.0, 50.0, 0.0], [20.0, 20.0, 30.0]])
    T = np.array([[0, 1, 2], [0, 1, 3], [1, 2, 3], [0, 2, 3]])
    mesh = TriMesh(V=V, T=T)
    fr = from_zxz((5.0, -7.0, 12.0), 35.0, 50.0, -20.0)
    lm = local_mesh(mesh, fr)
    assert isinstance(lm, TriMesh)
    np.testing.assert_array_equal(lm.T, T)
    np.testing.assert_allclose(lm.V, fr.to_local(V), atol=1e-12)
    np.testing.assert_allclose(fr.to_world(lm.V), V, atol=1e-12)
