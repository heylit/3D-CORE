"""Regresyon: SPEC 08 `assy.mates.rodrigues` çok küçük açıda dönmeyi atmamalı; SPEC 33 `drive` küçük adımda
ulaşmalı.

Bulgu (SPEC 69 kodlayıcısı): rodrigues |ω| < 1e-12 → I kesmesi yapıyor. Gauss–Newton'un son düzeltmesi
1e-12 rad altında kalınca atılıyor; L = 250 mm krank–biyelde artık 1.24e-10'da (tol 1e-10'un üstünde)
takılıyor ve drive θ = 0 → 0.0355° için "Ulaşılamaz konum" veriyor. SPEC 69 ters dinamiği
hızı ve ivmeyi küçük adımlı merkezi farkla bulduğundan (h = 1e-4·T) bu hata ona doğrudan dokunur.

Beklenen (exp([ω]×) tanımı): küçük θ'da exp([ω]×) = I + [ω]× + ½[ω]×² + O(θ³); 1e-13 rad'da [ω]× terimi
kaybolmamalı. Düzeltme gelene kadar xfail(strict=False): düzeltme gelince XPASS görünür (commit kancasını
kilitlemez), işaret kaldırılır.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from assy.kinematik import drive, joint_value
from assy.mates import rodrigues
from assy.model import Assembly, Component, Joint, JointKind, Ref, RefKind, rot_z, transform

ACIK = "SPEC 08 rodrigues küçük açı düzeltmesi bekleniyor"


@pytest.mark.xfail(strict=False, reason=ACIK)
@pytest.mark.parametrize("theta", [1e-13, 5e-13, 1e-15])
def test_rodrigues_cok_kucuk_aci(theta):
    k = np.array([1.0, -2.0, 2.0]) / 3.0
    R = rodrigues(theta * k)
    K = np.array([[0.0, -k[2], k[1]], [k[2], 0.0, -k[0]], [-k[1], k[0], 0.0]])
    beklenen = np.eye(3) + theta * K  # ½θ²K² ≈ 1e-26: çift duyarlıkta görünmez
    # antisimetrik kısım θK'yı taşımalı (göreli 1e-6)
    np.testing.assert_allclose((R - R.T) / 2, theta * K, rtol=0, atol=1e-6 * theta)
    np.testing.assert_allclose(R, beklenen, rtol=0, atol=1e-6 * theta)


def test_rodrigues_kucuk_aci_ortogonal():
    """Kesme olsa da olmasa da sonuç bir dönme matrisidir (bugün de geçer; regresyonun yan koşulu)."""
    for theta in (1e-13, 1e-9, 1e-6):
        R = rodrigues(theta * np.array([0.0, 0.0, 1.0]))
        np.testing.assert_allclose(R @ R.T, np.eye(3), rtol=0, atol=1e-15)
        assert np.linalg.det(R) == pytest.approx(1.0, abs=1e-15)


R_K, L_B = 50.0, 200.0  # L = 250 mm karakteristik uzunluk


def _krank_biyel(theta: float) -> Assembly:
    """θ'da kapalı formla kurulmuş krank–biyel (x = r cos θ + √(l² − r² sin² θ)), düzlem z = 0."""
    t = math.radians(theta)
    A = np.array([R_K * math.cos(t), R_K * math.sin(t), 0.0])
    x = R_K * math.cos(t) + math.sqrt(L_B**2 - (R_K * math.sin(t)) ** 2)
    phi = math.degrees(math.atan2(-A[1], x - A[0]))

    def eksen(c, o=(0.0, 0.0, 0.0), z=(0.0, 0.0, 1.0)):
        return Ref(c, RefKind.AXIS, o, z)

    comps = [
        Component("zemin", "zemin", np.eye(4), True),
        Component("krank", "krank", transform(rot_z(theta))),
        Component("biyel", "biyel", transform(rot_z(phi), A)),
        Component("piston", "piston", transform(t=(x, 0.0, 0.0))),
    ]
    ex = (1.0, 0.0, 0.0)
    joints = [
        Joint("J_krank", JointKind.REVOLUTE, eksen("zemin"), eksen("krank")),
        Joint("J_A", JointKind.REVOLUTE, eksen("krank", (R_K, 0, 0)), eksen("biyel")),
        Joint("J_B", JointKind.REVOLUTE, eksen("biyel", (L_B, 0, 0)), eksen("piston")),
        Joint("J_kayar", JointKind.PRISMATIC, eksen("zemin", z=ex), eksen("piston", z=ex)),
    ]
    return Assembly(name="krank-biyel", components=comps, mates=[], joints=joints)


@pytest.mark.xfail(strict=False, reason=ACIK)
@pytest.mark.parametrize("dtheta", [0.0355, 0.01])
def test_drive_krank_biyel_kucuk_adim(dtheta):
    """θ = 0'dan küçük adım: varsayılan tol (1e-10) ile ulaşılmalı, krank açısı ve piston x formülle 1e-9."""
    asm = _krank_biyel(0.0)
    res = drive(asm, {"J_krank": dtheta})
    assert res.residual <= 1e-10
    w = _krank_biyel(0.0)
    res.apply(w)
    assert joint_value(w, "J_krank") == pytest.approx(dtheta, abs=1e-9)
    t = math.radians(dtheta)
    x = R_K * math.cos(t) + math.sqrt(L_B**2 - (R_K * math.sin(t)) ** 2)
    assert joint_value(w, "J_kayar") == pytest.approx(x, abs=1e-9)
