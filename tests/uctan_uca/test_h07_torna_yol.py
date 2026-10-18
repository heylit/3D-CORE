"""SPEC 46 H7 — milin elle kurulan torna yolları (SPEC 20). K7.

Yol noktaları (x, 0, z), x yarıçap; takım T = 3 hayali uç P = C + q, q = (−r, −r) ((z, x) sırasında),
C burun merkezi. Parça yarı kesiti (z, x): (0, 0) → (60, 0) → (60, 9) → (59, 10) → (0, 10).
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from cam.model import MoveType, Toolpath
from tests.uctan_uca.conftest import L_MIL, PAH, R_MIL

TOL = 1e-6
KESME = {MoveType.LINEAR, MoveType.ARC_CW, MoveType.ARC_CCW}
KESIT = np.array([(0.0, 0.0), (L_MIL, 0.0), (L_MIL, R_MIL - PAH), (L_MIL - PAH, R_MIL), (0.0, R_MIL)])


def ornekler(tp: Toolpath, h: float = 0.05) -> np.ndarray:
    """Kesme hareketlerinden (z, x) örnekleri (yaylar dahil), adım ≤ h."""
    out = []
    p0 = np.array([tp.start[2], tp.start[0]])
    for m in tp.moves:
        p1 = np.array([m.end[2], m.end[0]])
        if m.type in KESME:
            if m.type is MoveType.LINEAR:
                k = max(2, math.ceil(np.linalg.norm(p1 - p0) / h) + 1)
                out.append(p0 + np.linspace(0, 1, k)[:, None] * (p1 - p0))
            else:
                c = np.array([m.center[1], m.center[0]])  # G18 merkezi (x, z) → (z, x)
                a0 = math.atan2(*(p0 - c)[::-1])
                a1 = math.atan2(*(p1 - c)[::-1])
                R = np.linalg.norm(p0 - c)
                # (z, x) düzleminde G2/G3 yönü ters döner; kısa yayı al (finişte yay < 180°)
                da = (a1 - a0 + math.pi) % (2 * math.pi) - math.pi
                t = np.linspace(0, 1, max(2, math.ceil(abs(da) * R / h) + 1))
                out.append(c + R * np.c_[np.cos(a0 + da * t), np.sin(a0 + da * t)])
        p0 = p1
    return np.vstack(out)


def kesite_uzaklik(Q: np.ndarray) -> np.ndarray:
    """(z, x) noktalarının parça yarı kesitine uzaklığı; içerideyse negatif."""
    d = np.full(len(Q), np.inf)
    n = len(KESIT)
    for i in range(n):
        a, b = KESIT[i], KESIT[(i + 1) % n]
        ab = b - a
        t = np.clip(((Q - a) @ ab) / (ab @ ab), 0, 1)
        d = np.minimum(d, np.linalg.norm(Q - (a + t[:, None] * ab), axis=1))
    z, x = Q[:, 0], Q[:, 1]
    sinir = np.where(z <= L_MIL - PAH, R_MIL, R_MIL - (z - (L_MIL - PAH)))
    icinde = (z > 0) & (z < L_MIL) & (x > 0) & (x < sinir)
    return np.where(icinde, -d, d)


def burun_merkezi(tp: Toolpath) -> np.ndarray:
    r = tp.tool.nose_r
    return ornekler(tp) + np.array([r, r])  # C = P − q, q = (−r, −r)


def test_k7_alin_z60a_iner(torna_ops):
    alin = torna_ops[0]
    P = np.array([m.end for m in alin.moves if m.type in KESME])
    assert P[:, 2].min() == pytest.approx(L_MIL, abs=TOL)
    assert P[:, 2].max() == pytest.approx(L_MIL, abs=TOL)


def test_k7_finis_silindir_bolumu_x10(torna_ops):
    finis = torna_ops[2]
    Q = ornekler(finis)
    silindir = Q[(Q[:, 0] > 1.0) & (Q[:, 0] < L_MIL - PAH - 1.0)]
    assert len(silindir) > 0
    assert np.allclose(silindir[:, 1], R_MIL, atol=TOL)


@pytest.mark.parametrize("i, pay", [(0, 0.0), (1, 0.2), (2, 0.0)], ids=["alin", "kaba", "finis"])
def test_k7_burun_parcaya_girmez(torna_ops, i, pay):
    tp = torna_ops[i]
    d = kesite_uzaklik(burun_merkezi(tp))
    assert d.min() >= tp.tool.nose_r + pay - TOL


def test_k7_finis_profile_deger(torna_ops):
    tp = torna_ops[2]
    d = kesite_uzaklik(burun_merkezi(tp))
    assert d.min() == pytest.approx(tp.tool.nose_r, abs=TOL)
