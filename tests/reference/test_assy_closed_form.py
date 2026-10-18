"""
Montaj çözücüsünün kapalı form çözümlerle çapraz kontrolü (inceleme Y1).

SPEC 08 testleri kısıtları tek tek dener. Burada çok gövdeli kapalı bir döngü (dört çubuk
mekanizması) ve eğik eksenli uzaysal bir montaj, çözücünün artık tanımından bağımsız olarak
trigonometriyle hesaplanan konumlarla karşılaştırılır. Kontrol "artık sıfır mı" değil, "bileşenler
mekanizmanın gerçek konumunda mı": artık tanımında ortak bir hata olsa da yakalanır.

Kapalı form (dört çubuk, Norton, Design of Machinery, Bölüm 4): zemin O2 = (0, 0), O4 = (d, 0);
krank ucu A = a (cos θ2, sin θ2); B, merkezi A yarıçapı b ve merkezi O4 yarıçapı c olan iki çemberin
kesişimi (açık / çapraz iki dal). Uzaysal döndürmeler scipy.spatial.transform ile (assy.mates'ten
bağımsız). Başlangıç konumları çözümden ≈ 8° ve birkaç mm kaçık: Gauss–Newton yakın dalı bulur.
Geometri uydurmadır.
"""

from __future__ import annotations

import math

import numpy as np
import pytest
from scipy.spatial.transform import Rotation

from assy.model import Assembly, Component, Mate, MateKind, Ref, RefKind, transform
from assy.solver import solve

C, CON, DIS, ANG = MateKind.COINCIDENT, MateKind.CONCENTRIC, MateKind.DISTANCE, MateKind.ANGLE
TOL = 1e-7  # mm ve birimsiz yön


def ax(comp, origin, direction=(0, 0, 1)):
    return Ref(comp, RefKind.AXIS, origin, direction)


def pl(comp, origin, normal=(0, 0, 1)):
    return Ref(comp, RefKind.PLANE, origin, normal)


def pt(comp, origin):
    return Ref(comp, RefKind.POINT, origin)


def planar(theta_deg: float, x: float, y: float) -> np.ndarray:
    return transform(Rotation.from_euler("z", theta_deg, degrees=True).as_matrix(), (x, y, 0.0))


def circle_intersections(p: np.ndarray, r1: float, q: np.ndarray, r2: float) -> list[np.ndarray]:
    """İki çemberin kesişim noktaları (lisede öğretilen kapalı form)."""
    d = float(np.linalg.norm(q - p))
    a = (r1 * r1 - r2 * r2 + d * d) / (2 * d)
    h = math.sqrt(r1 * r1 - a * a)
    m = p + a * (q - p) / d
    n = np.array([-(q - p)[1], (q - p)[0]]) / d
    return [m + h * n, m - h * n]


def fourbar_closed_form(a, b, c, d, th2_deg):
    """Krank açısı θ2 için iki dalın (A, B) noktaları."""
    th2 = math.radians(th2_deg)
    A = np.array([a * math.cos(th2), a * math.sin(th2)])
    O4 = np.array([d, 0.0])
    return A, circle_intersections(A, b, O4, c)


def fourbar(a, b, c, d, th2_deg, branch: int, start_err_deg: float = 8.0) -> tuple[Assembly, dict]:
    """Dört çubuk: zemin (sabit), krank, biyel, sarkaç. Her döner mafsal = eş eksen (z) + nokta–düzlem.

    Krank açısı, krankın x ekseni ile zeminin x ekseni arasındaki ANGLE kısıtıyla verilir. Döndürür:
    montaj (başlangıç konumu kaçık) ve kapalı formdan beklenen T'ler.
    """
    A, Bs = fourbar_closed_form(a, b, c, d, th2_deg)
    B = Bs[branch]
    O4 = np.array([d, 0.0])
    th3 = math.degrees(math.atan2(*(B - A)[::-1]))
    th4 = math.degrees(math.atan2(*(B - O4)[::-1]))
    exp = {
        "zemin": planar(0, 0, 0),
        "krank": planar(th2_deg, 0, 0),
        "biyel": planar(th3, *A),
        "sarkac": planar(th4, *O4),
    }
    e = start_err_deg
    comps = [
        Component("zemin", "zemin", exp["zemin"], fixed=True),
        Component("krank", "krank", planar(th2_deg + e, 1.0, -1.5)),
        Component("biyel", "biyel", planar(th3 - e, A[0] + 2.0, A[1] + 1.0)),
        Component("sarkac", "sarkac", planar(th4 + e, d - 1.0, 2.0)),
    ]

    def revolute(p, p_local, q, q_local):
        return [Mate(CON, ax(p, p_local), ax(q, q_local)), Mate(C, pt(q, q_local), pl(p, p_local))]

    mates = (
        revolute("zemin", (0, 0, 0), "krank", (0, 0, 0))
        + revolute("krank", (a, 0, 0), "biyel", (0, 0, 0))
        + revolute("biyel", (b, 0, 0), "sarkac", (c, 0, 0))
        + revolute("zemin", (d, 0, 0), "sarkac", (0, 0, 0))
        + [Mate(ANG, ax("zemin", (0, 0, 0), (1, 0, 0)), ax("krank", (0, 0, 0), (1, 0, 0)), th2_deg)]
    )
    return Assembly("dort_cubuk", comps, mates), exp


@pytest.mark.parametrize(
    "a,b,c,d",
    [
        (40.0, 120.0, 80.0, 100.0),  # Grashof krank–sarkaç
        (25.0, 90.0, 70.0, 60.0),  # Grashof krank–sarkaç, kısa zemin
    ],
)
@pytest.mark.parametrize("th2", [15.0, 60.0, 90.0, 135.0, 170.0])
@pytest.mark.parametrize("branch", [0, 1])
def test_fourbar_matches_closed_form(a, b, c, d, th2, branch):
    asm, exp = fourbar(a, b, c, d, th2, branch)
    res = solve(asm)
    assert res.dof == 0
    for name, T in exp.items():
        np.testing.assert_allclose(res.T[name], T, atol=TOL, err_msg=name)


def test_fourbar_loop_closes_through_a_crank_sweep():
    """Krank 10°'den 170°'ye döndürülürken (her adım öncekinden başlar) sarkaç açısı kapalı formu izler."""
    a, b, c, d = 40.0, 120.0, 80.0, 100.0
    prev = None
    for th2 in np.arange(10.0, 171.0, 20.0):
        asm, exp = fourbar(a, b, c, d, float(th2), branch=0)
        if prev is not None:
            for comp in asm.components:
                comp.T = prev[comp.name].copy()
        res = solve(asm)
        np.testing.assert_allclose(res.T["sarkac"], exp["sarkac"], atol=TOL)
        np.testing.assert_allclose(res.T["biyel"], exp["biyel"], atol=TOL)
        prev = res.T


@pytest.mark.parametrize("theta", [20.0, 75.0, 120.0])
@pytest.mark.parametrize("D", [0.0, 12.5, 40.0])
def test_sleeve_on_tilted_axis(theta, D):
    """Eğik bir mil (u ∝ (1, 2, 2)) üzerinde kovan: eş eksen + uç noktası mil düzlemine D mesafede
    + kovanın x ekseni ile zemindeki v (u'ya dik) arasında θ açısı. Kapalı form:
    kovan orijini = p0 + D·u, R e_z = ±u, (R e_x)·v = cos θ, (R e_x)·u = 0."""
    u = np.array([1.0, 2.0, 2.0]) / 3.0
    v = np.array([2.0, -1.0, 0.0]) / math.sqrt(5.0)  # u'ya dik
    p0 = np.array([10.0, -5.0, 3.0])
    # Beklenen: z'yi u'ya, x'i v'den u etrafında θ dönmüş yöne götüren dönme
    w = np.cross(u, v)
    ex = math.cos(math.radians(theta)) * v + math.sin(math.radians(theta)) * w
    R_exp = np.column_stack([ex, np.cross(u, ex), u])
    t_exp = p0 + D * u
    # Başlangıç: beklenenden küçük bir dönme ve öteleme kaçık
    R0 = Rotation.from_rotvec([0.08, -0.05, 0.1]).as_matrix() @ R_exp
    comps = [
        Component("govde", "govde", np.eye(4), fixed=True),
        Component("kovan", "kovan", transform(R0, t_exp + np.array([1.5, -2.0, 1.0]))),
    ]
    mates = [
        Mate(CON, ax("govde", p0, u), ax("kovan", (0, 0, 0))),
        Mate(C, pt("kovan", (0, 0, 0)), pl("govde", p0, u))
        if D == 0
        else Mate(DIS, pt("kovan", (0, 0, 0)), pl("govde", p0, u), D),
        Mate(ANG, ax("govde", p0, v), ax("kovan", (0, 0, 0), (1, 0, 0)), theta),
    ]
    res = solve(Assembly("kovan", comps, mates))
    T = res.T["kovan"]
    assert res.dof == 0
    np.testing.assert_allclose(T[:3, 3], t_exp, atol=TOL)
    R = T[:3, :3]
    assert abs(abs(R[:, 2] @ u) - 1.0) < TOL  # eksen u'ya paralel
    assert R[:, 0] @ v == pytest.approx(math.cos(math.radians(theta)), abs=TOL)
    assert R[:, 0] @ u == pytest.approx(0.0, abs=TOL)
    np.testing.assert_allclose(R, R_exp, atol=1e-6)  # yakın dal: beklenen dönmenin kendisi
