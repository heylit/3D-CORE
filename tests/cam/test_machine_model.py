"""SPEC 44 K2 — tezgâh modeli: JSON gidip dönüş, doğrulama, halka dönüşümleri (poses).

Testler SPEC 44 metninden ve `cam/multiaxis/machine.py` modül docstring'indeki kurallardan yazıldı
(zincirler, x ↦ R·x + t, otomatik gövde adları, JSON biçimi); gövdeler okunmadı. Beklenen dönüşümler
tests/cam/machref.ref_poses ile elle kurulur; dönmeler SPEC 41 `rotation` ile.
"""

from __future__ import annotations

import copy
import json
import math
from pathlib import Path

import numpy as np
import pytest

from cam.model import CamError, Kinematics, MachineProfile, RotaryAxis, Setup, Stock, Tool, ToolKind, Wcs
from cam.multiaxis.kinematics import forward
from cam.multiaxis.machine import LINKS_FIXED, Body, Box, Capsule, MachineModel, poses
from tests.cam.machref import Rx, apply, ref_poses

ORNEK = Path(__file__).resolve().parents[2] / "examples" / "tezgah_ac_besik.json"
TOL = 1e-12


def ornek_dict() -> dict:
    return json.loads(ORNEK.read_text(encoding="utf-8"))


def kurulum() -> Setup:
    return Setup(name="s", wcs=Wcs(origin=(0.0, 0.0, -350.0)), stock=Stock(-40, -30, 0, 40, 30, 10))


def takim() -> Tool:
    return Tool(id=1, name="F6", kind=ToolKind.FLAT, D=6.0, flute_length=20.0)


def test_k2_sabit_halkalar():
    assert LINKS_FIXED == ("taban", "X", "Y", "Z", "is_mili", "is_parcasi")


# --- JSON ------------------------------------------------------------------------------------------


def test_k2_json_gidip_donus_birebir():
    d = ornek_dict()
    m = MachineModel.from_dict(d)
    assert json.loads(json.dumps(m.to_dict())) == d
    m2 = MachineModel.from_dict(json.loads(json.dumps(m.to_dict())))
    assert json.loads(json.dumps(m2.to_dict())) == d


def test_k2_ornek_icerik():
    m = MachineModel.from_dict(ornek_dict())
    assert m.linear_carrier == {"X": "kafa", "Y": "masa", "Z": "kafa"}
    adlar = [b.name for b in m.bodies]
    assert adlar == ["kolon", "kafa", "c_tabla", "besik_taban", "besik_sol", "besik_sag", "y_kizak"]
    assert all(isinstance(b.shape, Box) for b in m.bodies)
    kin = m.profile.kinematics
    assert [a.name for a in kin.rotary] == ["A", "C"]


def test_k2_kapsul_json():
    d = ornek_dict()
    d["bodies"].append(
        {
            "name": "kablo",
            "link": "Z",
            "shape": {"type": "kapsul", "p": [0.0, 90.0, 10.0], "q": [0.0, 90.0, 200.0], "r": 8.0},
        }
    )
    d["ignore"] = [["kablo", "kolon"]]
    m = MachineModel.from_dict(d)
    b = m.bodies[-1]
    assert isinstance(b.shape, Capsule)
    assert b.shape.r == 8.0
    assert json.loads(json.dumps(m.to_dict())) == d


# --- doğrulama -------------------------------------------------------------------------------------


def _bozuk(fn) -> dict:
    d = copy.deepcopy(ornek_dict())
    fn(d)
    return d


@pytest.mark.parametrize(
    "boz",
    [
        pytest.param(lambda d: d["bodies"][0].update(link="B"), id="bilinmeyen-halka-B"),
        pytest.param(lambda d: d["bodies"][0].update(link="tavan"), id="bilinmeyen-halka"),
        pytest.param(lambda d: d["bodies"][2].update(name="kolon"), id="yinelenen-ad"),
        pytest.param(lambda d: d["bodies"][0].update(name="takim"), id="ayrilmis-ad-takim"),
        pytest.param(lambda d: d["bodies"][0].update(name="ham_malzeme"), id="ayrilmis-ad-ham"),
        pytest.param(lambda d: d["bodies"][0].update(name="fikstur_0"), id="ayrilmis-ad-fikstur"),
        pytest.param(lambda d: d["bodies"][0].update(name="tutucu_0"), id="ayrilmis-ad-tutucu"),
        pytest.param(lambda d: d["bodies"][0].update(name="sap"), id="ayrilmis-ad-sap"),
        pytest.param(
            lambda d: d["profile"]["kinematics"]["rotary"][1].update(u=[1.0, 0.0, 0.0]), id="paralel-doner"
        ),
        pytest.param(lambda d: d["linear_carrier"].update(X="tavan"), id="tasiyici-hatali"),
        pytest.param(lambda d: d["linear_carrier"].pop("Y"), id="tasiyici-eksik"),
        pytest.param(lambda d: d["linear_carrier"].update(W="masa"), id="bilinmeyen-eksen"),
        pytest.param(lambda d: d["bodies"][0]["shape"].update(half=[300.0, 0.0, 400.0]), id="kutu-half-0"),
        pytest.param(lambda d: d["bodies"][0]["shape"].update(type="silindir"), id="sekil-turu"),
    ],
)
def test_k2_hatali_model(boz):
    with pytest.raises(CamError):
        MachineModel.from_dict(_bozuk(boz))


def test_k2_kurucu_dogrulama():
    m = MachineModel.from_dict(ornek_dict())
    b = Body("x", "taban", Box(center=(0.0, 0.0, 0.0), half=(1.0, 1.0, 1.0)))
    with pytest.raises(CamError):
        MachineModel(m.profile, dict(m.linear_carrier), [b, Body("x", "Z", b.shape)])  # yinelenen ad
    with pytest.raises(CamError):
        MachineModel(m.profile, dict(m.linear_carrier), [Body("y", "A2", b.shape)])  # bilinmeyen halka
    # 3 eksen (kinematik yok): döner halka adı bilinmez
    prof3 = MachineProfile(name="UC EKSEN", controller="fanuc", rpm_max=10000, feed_max=5000)
    with pytest.raises(CamError):
        MachineModel(prof3, {"X": "kafa", "Y": "kafa", "Z": "kafa"}, [Body("y", "A", b.shape)])
    MachineModel(prof3, {"X": "kafa", "Y": "kafa", "Z": "kafa"}, [Body("y", "Z", b.shape)])


# --- poses -----------------------------------------------------------------------------------------


def _assert_pose(got, beklenen, tol=TOL):
    R, t = got
    np.testing.assert_allclose(np.asarray(R, dtype=float), beklenen[0], atol=tol, rtol=0)
    np.testing.assert_allclose(np.asarray(t, dtype=float), beklenen[1], atol=tol, rtol=0)


def test_k2_poses_sifirda_birim():
    m = MachineModel.from_dict(ornek_dict())
    P = poses(m, (0.0, 0.0, 0.0, 0.0, 0.0), kurulum(), takim())
    assert set(P) >= {"taban", "X", "Y", "Z", "A", "C", "is_mili", "is_parcasi"}
    for ad in ("taban", "X", "Y", "Z", "A", "C", "is_mili", "is_parcasi"):
        _assert_pose(P[ad], (np.eye(3), np.zeros(3)))


def test_k2_poses_a90_besik():
    """A = 90°: beşik tabanı (merkez (0, 0, −410), A ekseni pivotu (0, 0, −350)) Rx(90) ile pivot
    etrafında döner → merkez (0, 60, −350). Kafa gövdesi X, Z ile ötelenir; masa Y ile −Y'ye gider."""
    m = MachineModel.from_dict(ornek_dict())
    P = poses(m, (0.0, 0.0, 0.0, 90.0, 0.0), kurulum(), takim())
    piv = np.array([0.0, 0.0, -350.0])
    _assert_pose(P["A"], (Rx(90), piv - Rx(90) @ piv))
    np.testing.assert_allclose(apply(P["A"], (0.0, 0.0, -410.0)), (0.0, 60.0, -350.0), atol=TOL)
    np.testing.assert_allclose(apply(P["A"], (-240.0, 0.0, -350.0)), (-240.0, 0.0, -350.0), atol=TOL)
    # beşik yan gövdesinin kutu köşesi (260, 160, −300) → (260, −50 − 350 … ): Rx(90)(y, z+350) − 350
    np.testing.assert_allclose(apply(P["A"], (260.0, 160.0, -300.0)), (260.0, -50.0, -190.0), atol=TOL)


def test_k2_poses_genel():
    m = MachineModel.from_dict(ornek_dict())
    kin = m.profile.kinematics
    rng = np.random.default_rng(4)
    for _ in range(20):
        q = (*rng.uniform(-100, 100, 3), rng.uniform(-90, 90), rng.uniform(-180, 180))
        P = poses(m, q, kurulum(), takim())
        B = ref_poses(kin, m.linear_carrier, q)
        for ad, beklenen in B.items():
            _assert_pose(P[ad], beklenen, tol=1e-9)
    q = (10.0, 20.0, -30.0, 0.0, 0.0)
    P = poses(m, q, kurulum(), takim())
    _assert_pose(P["X"], (np.eye(3), (10.0, 0.0, 0.0)))  # kafa
    _assert_pose(P["Y"], (np.eye(3), (0.0, -20.0, 0.0)))  # masa: −Y
    _assert_pose(P["Z"], (np.eye(3), (10.0, 0.0, -30.0)))  # kafa zinciri: X sonra Z
    _assert_pose(P["is_mili"], (np.eye(3), (10.0, 0.0, -30.0)))
    _assert_pose(P["is_parcasi"], (np.eye(3), (0.0, -20.0, 0.0)))


def test_k2_poses_ileri_kinematikle_tutarli():
    """is_parcasi⁻¹(is_mili(tip₀)) − o_wcs = SPEC 41 forward() uç noktası (göreli hareket aynı)."""
    m = MachineModel.from_dict(ornek_dict())
    kin = m.profile.kinematics
    s = kurulum()
    L = 100.0
    tip0 = np.array(kin.gauge) - L * np.array(kin.spindle)
    rng = np.random.default_rng(5)
    for _ in range(20):
        q = (*rng.uniform(-100, 100, 3), rng.uniform(-90, 90), rng.uniform(-180, 180))
        P = poses(m, q, s, takim())
        R_w, t_w = (np.asarray(v, dtype=float) for v in P["is_parcasi"])
        tip_m = apply(P["is_mili"], tip0)
        tip_w = R_w.T @ (tip_m - t_w) - np.array(s.wcs.origin)
        beklenen, _ = forward(kin, q, L, s.wcs)
        np.testing.assert_allclose(tip_w, beklenen, atol=1e-9)


def test_k2_poses_kafa_doner_eksen():
    """Kafada B ekseni: is_mili = Trans(X, Y, Z) ∘ Rot_B; masa halkası birim."""
    kin = Kinematics(rotary=(RotaryAxis("B", "kafa", (0.0, 1.0, 0.0), (0.0, 0.0, 150.0), -110.0, 110.0),))
    prof = MachineProfile(name="B KAFA", controller="fanuc", rpm_max=10000, feed_max=5000, kinematics=kin)
    car = {"X": "kafa", "Y": "kafa", "Z": "kafa"}
    m = MachineModel(
        prof, car, [Body("govde", "B", Capsule(p=(0.0, 0.0, 100.0), q=(0.0, 0.0, 300.0), r=40.0))]
    )
    q = (5.0, -7.0, 12.0, 30.0)
    P = poses(m, q, kurulum(), takim())
    B = ref_poses(kin, car, q)
    for ad in ("taban", "X", "Y", "Z", "B", "is_mili", "is_parcasi"):
        _assert_pose(P[ad], B[ad])
    c, s_ = math.cos(math.radians(30)), math.sin(math.radians(30))
    # (0, 0, 0), pivot (0, 0, 150) etrafında Ry(30) → (−150 sin30, 0, 150 − 150 cos30) + (5, −7, 12)
    np.testing.assert_allclose(
        apply(P["B"], (0.0, 0.0, 0.0)), (5 - 150 * s_, -7.0, 12 + 150 - 150 * c), atol=TOL
    )
