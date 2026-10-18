"""SPEC 50 — eksen düzgünleştirme testleri (K8, K9'un `w` kısmı).

Testler yalnız SPEC 50 metninden (Teori, Arayüz, Ek A), `cam/model.py`, `cam/dropcutter.py` (`TriMesh`),
`cam/ops3d.py` (`Raster`) ve `cam/multiaxis/toolpath5.py` arayüzlerinden (`finish5`, `Orientation`) yazıldı;
`cam/multiaxis/smooth.py` gövdeleri okunmadı (iskelette NotImplementedError).

Kurallar (SPEC 50 Teori + Ek A):
- J = Σ_k |∠(a_k, a_{k+1}) − ∠(a_{k−1}, a_k)|; düzgünleştirme J'yi artıramaz.
- Pencere yalnız kesintisiz bir G1 kesme dizisinin içinde, eşit ağırlık, uçlarda kırpılır; sonuç birimlenir.
- Küresel uçta küre merkezi korunur: p = c − R·a_yeni (c = p + R·a). `w` tek ve ≥ 1, değilse CamError.

Giriş yolu: SPEC 42 `finish5` ile yarım kürede "normal" yönelimli yol; eksenlere sabit tohumlu gürültü
eklenir, uçlar aynı küre merkezinden yeniden konumlanır (merkez korunduğu için giriş de çakmasızdır).
"""

from __future__ import annotations

import dataclasses
import math

import numpy as np
import pytest

from cam.dropcutter import TriMesh
from cam.model import CamError, Move, MoveType, Tool, ToolKind, Toolpath
from cam.multiaxis.smooth import smooth_axes
from cam.multiaxis.toolpath5 import Orientation, finish5
from cam.ops3d import Raster
from tests.cam.ref3d import point_mesh_distance, sample_triangles, sphere_cap_mesh

R = 3.0  # küresel uç yarıçapı
FLUTE = 20.0
RHO = 30.0
FEED, PLUNGE, RPM = 1000.0, 300.0, 8000.0
SIGMA = 0.05  # eksen gürültüsü (≈ 3°)


def _ball() -> Tool:
    return Tool(id=1, name="kure", kind=ToolKind.BALL, D=2 * R, flute_length=FLUTE)


def _raster() -> Raster:
    return Raster(
        xmin=-12.0, xmax=12.0, ymin=-12.0, ymax=12.0, stepover=4.0, ds=2.0, tol=0.01, ds_min=0.5,
        feed=FEED, plunge_feed=PLUNGE, rpm=RPM, z_safe=60.0,
    )  # fmt: skip


_KURE = None


def _kure() -> tuple[TriMesh, np.ndarray, np.ndarray, np.ndarray]:
    global _KURE
    if _KURE is None:
        V, T = sphere_cap_mesh(RHO, math.pi / 2, 30, 120)
        _KURE = (TriMesh(V=V, T=T), V, T, sample_triangles(V, T, 4))
    return _KURE


def _aci(u: np.ndarray, v: np.ndarray) -> float:
    return math.atan2(float(np.linalg.norm(np.cross(u, v))), float(u @ v))


def _diziler(tp: Toolpath) -> list[list[int]]:
    """Kesintisiz G1 kesme dizileri (ilerleme Raster.feed olan ardışık G1'lerin hareket indeksleri)."""
    diziler, cur = [], []
    for k, m in enumerate(tp.moves):
        if m.type is MoveType.LINEAR and m.feed == pytest.approx(FEED):
            cur.append(k)
        elif cur:
            diziler.append(cur)
            cur = []
    if cur:
        diziler.append(cur)
    return diziler


def _J(tp: Toolpath) -> float:
    """Bağımsız J: her kesme dizisinde Σ |∠(a_k, a_{k+1}) − ∠(a_{k−1}, a_k)|."""
    J = 0.0
    for d in _diziler(tp):
        A = [np.array(tp.moves[k].axis) for k in d]
        for i in range(1, len(A) - 1):
            J += abs(_aci(A[i], A[i + 1]) - _aci(A[i - 1], A[i]))
    return J


def _gurultulu(tp: Toolpath, seed: int = 50) -> Toolpath:
    """Kesme hareketlerinin eksenine gürültü; uç p' = c − R·a', c = p + R·a (küre merkezi aynı)."""
    rng = np.random.default_rng(seed)
    yeni = []
    for m in tp.moves:
        if m.type is MoveType.LINEAR and m.feed == pytest.approx(FEED):
            a = np.array(m.axis)
            c = np.array(m.end) + R * a
            a2 = a + SIGMA * rng.standard_normal(3)
            a2 /= np.linalg.norm(a2)
            m = Move(MoveType.LINEAR, tuple(c - R * a2), feed=m.feed, axis=tuple(a2))
        yeni.append(m)
    return dataclasses.replace(tp, moves=yeni)


_YOL = None


def _yol() -> Toolpath:
    global _YOL
    if _YOL is None:
        mesh = _kure()[0]
        _YOL = finish5(mesh, _ball(), _raster(), Orientation("normal"))
    return _YOL


# ---------------------------------------------------------------- K8


def test_k8_gurultulu_dizi_duzgunlesir():
    mesh, V, T, Q = _kure()
    giris = _gurultulu(_yol())
    assert _J(giris) > 0.5  # gürültü gerçekten var
    cikis, J_eski, J_yeni = smooth_axes(giris, mesh, _ball(), w=5)
    assert J_yeni < J_eski
    assert _J(cikis) < _J(giris)
    assert len(cikis.moves) == len(giris.moves)
    for m0, m1 in zip(giris.moves, cikis.moves, strict=True):
        assert m1.type is m0.type
        assert m1.feed == m0.feed
    for d in _diziler(giris):
        for k in d:
            m0, m1 = giris.moves[k], cikis.moves[k]
            a1 = np.array(m1.axis)
            assert np.linalg.norm(a1) == pytest.approx(1.0, abs=1e-12)
            # küresel uçta küre merkezi korunur
            np.testing.assert_allclose(
                np.array(m1.end) + R * a1, np.array(m0.end) + R * np.array(m0.axis), atol=1e-9
            )


def test_k8_cakmasiz_ve_govde_carpismasiz():
    """Her kesme noktasında küre merkezinin ağa uzaklığı ≥ R; sap (merkezden eksen boyunca kesici boya kadar,
    yarıçap R) ağın örnek noktalarına ≥ R uzakta (kapsül uzaklığı)."""
    mesh, V, T, Q = _kure()
    cikis, _, _ = smooth_axes(_gurultulu(_yol()), mesh, _ball(), w=5)
    kes = [cikis.moves[k] for d in _diziler(cikis) for k in d]
    assert kes
    for m in kes[::7]:
        a = np.array(m.axis)
        c = np.array(m.end) + R * a
        assert point_mesh_distance(c, V, T) >= R - 1e-9
        ust = np.array(m.end) + FLUTE * a
        d = Q - c
        t = np.clip(d @ (ust - c) / float((ust - c) @ (ust - c)), 0.0, 1.0)
        dist = np.linalg.norm(d - np.outer(t, ust - c), axis=1)
        assert float(dist.min()) >= R - 1e-9


def test_k8_duzgun_dizi_degismez():
    """Sabit eksen: pencere ortalaması aynı vektör → yol değişmez (1e-12), J = 0."""
    mesh = _kure()[0]
    a = (math.sin(math.radians(10.0)), 0.0, math.cos(math.radians(10.0)))
    giris = finish5(mesh, _ball(), _raster(), Orientation("sabit", a=a))
    cikis, J_eski, J_yeni = smooth_axes(giris, mesh, _ball(), w=5)
    assert J_eski == pytest.approx(0.0, abs=1e-12)
    assert J_yeni == pytest.approx(0.0, abs=1e-12)
    assert len(cikis.moves) == len(giris.moves)
    np.testing.assert_allclose(cikis.start, giris.start, atol=1e-12)
    for m0, m1 in zip(giris.moves, cikis.moves, strict=True):
        assert m1.type is m0.type
        np.testing.assert_allclose(m1.end, m0.end, atol=1e-12)
        if m0.axis is not None:
            np.testing.assert_allclose(m1.axis, m0.axis, atol=1e-12)


def test_k8_genis_pencere_daha_duzgun_degil_ama_artirmaz():
    """w = 1 tek noktalık pencere: ortalama noktanın kendisi → J değişmez; hiçbir w J'yi artırmaz."""
    mesh = _kure()[0]
    giris = _gurultulu(_yol())
    _, J_eski, J_yeni = smooth_axes(giris, mesh, _ball(), w=1)
    assert J_yeni == pytest.approx(J_eski, abs=1e-12)
    for w in (3, 7):
        _, J_eski, J_yeni = smooth_axes(giris, mesh, _ball(), w=w)
        assert J_yeni <= J_eski + 1e-12


# ---------------------------------------------------------------- K9 (w)


@pytest.mark.parametrize("w", [0, 2, 4, -3])
def test_k9_w_tek_ve_pozitif_olmali(w):
    mesh = _kure()[0]
    with pytest.raises(CamError):
        smooth_axes(_yol(), mesh, _ball(), w=w)
