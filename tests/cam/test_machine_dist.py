"""SPEC 44 K1 — kapsül–kapsül, kapsül–kutu uzaklıkları ve kutu–kutu SAT kesişimi.

Testler SPEC 44 metninden ve `cam.multiaxis.machine` / `collision` imzalarından yazıldı; gövdeler okunmadı
(iskelette NotImplementedError). Beklenen değerler elle hesaplanmış kapalı formlar veya
tests/cam/machref.py'deki bağımsız referanslardır (Ericson parça–parça, kenetlemeli nokta–kutu,
doğrusal programla kutu kesişimi).

Kurallar (SPEC 44 "Uzaklık", koordinatör yorumu 2026-10-18): kapsül uzaklıkları işaretli (girişimde negatif),
kapsülün kutu içindeki noktası için nokta–kutu uzaklığı 0; kutu–kutuda değme kesişim sayılır.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from cam.model import CamError
from cam.multiaxis.collision import boxes_overlap, dist_capsule_box, dist_capsule_capsule
from cam.multiaxis.machine import Box, Capsule
from tests.cam.machref import Rx, Rz, boxes_intersect_lp, face_axes_separate, seg_box, seg_seg

S2 = math.sqrt(2.0)


def rows(R: np.ndarray) -> tuple:
    return tuple(tuple(float(v) for v in r) for r in R)


def cap(p, q, r) -> Capsule:
    return Capsule(p=tuple(map(float, p)), q=tuple(map(float, q)), r=float(r))


def box(c, h, R=None) -> Box:
    R = np.eye(3) if R is None else np.asarray(R)
    return Box(center=tuple(map(float, c)), half=tuple(map(float, h)), R=rows(R))


# --- doğrulama -------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "kw",
    [
        pytest.param({"half": (0.0, 1.0, 1.0)}, id="half-sifir"),
        pytest.param({"half": (1.0, -1.0, 1.0)}, id="half-negatif"),
        pytest.param({"center": (math.nan, 0.0, 0.0)}, id="center-nan"),
        pytest.param({"R": ((1.0, 0.0, 0.0), (0.0, 2.0, 0.0), (0.0, 0.0, 1.0))}, id="R-dik-degil"),
        pytest.param({"R": ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0))}, id="R-2x3"),
    ],
)
def test_k1_box_hatali(kw):
    p = {"center": (0.0, 0.0, 0.0), "half": (1.0, 1.0, 1.0)}
    p.update(kw)
    with pytest.raises(CamError):
        Box(**p)


@pytest.mark.parametrize(
    "kw",
    [
        pytest.param({"r": 0.0}, id="r-sifir"),
        pytest.param({"r": -1.0}, id="r-negatif"),
        pytest.param({"r": math.nan}, id="r-nan"),
        pytest.param({"p": (0.0, math.inf, 0.0)}, id="p-inf"),
    ],
)
def test_k1_capsule_hatali(kw):
    p = {"p": (0.0, 0.0, 0.0), "q": (1.0, 0.0, 0.0), "r": 1.0}
    p.update(kw)
    with pytest.raises(CamError):
        Capsule(**p)


def test_k1_gecerli_sekiller():
    box((0, 0, 0), (1, 2, 3), Rz(30) @ Rx(10))
    cap((0, 0, 0), (0, 0, 0), 1.0)  # p = q: küre


# --- kapsül–kapsül (kapalı form, 1e-12) ------------------------------------------------------------


@pytest.mark.parametrize(
    "a, b, beklenen",
    [
        # kesişen: X ve Y eksenleri boyunca, merkezde kesişiyor → 0 − 0.2 − 0.3
        pytest.param(((-1, 0, 0), (1, 0, 0), 0.2), ((0, -1, 0), (0, 1, 0), 0.3), -0.5, id="kesisen"),
        # paralel, izdüşümleri örtüşen: aralarında 3
        pytest.param(((0, 0, 0), (2, 0, 0), 0.5), ((1, 0, 3), (4, 0, 3), 0.5), 2.0, id="paralel-ortusen"),
        # paralel, örtüşmeyen: uçlar (1,0,0)–(3,0,4)
        pytest.param(
            ((0, 0, 0), (1, 0, 0), 0.5), ((3, 0, 4), (5, 0, 4), 0.25), math.sqrt(20.0) - 0.75, id="paralel-uc"
        ),
        # çapraz (aykırı): X boyunca z = 0, Y boyunca z = 2
        pytest.param(((-1, 0, 0), (1, 0, 0), 0.1), ((0, -1, 2), (0, 1, 2), 0.4), 1.5, id="capraz"),
        # aynı doğru üstünde uç–uç
        pytest.param(((0, 0, 0), (1, 0, 0), 0.5), ((3, 0, 0), (5, 0, 0), 0.5), 1.0, id="uc-uc"),
        # çapraz, en yakın noktalar uçlarda: (1,0,0) ile (2,1,0)…(2,3,0) parçasının (2,1,0) ucu
        pytest.param(((0, 0, 0), (1, 0, 0), 0.0 + 0.1), ((2, 1, 0), (2, 3, 0), 0.1), S2 - 0.2, id="uc-ic"),
        # küre–küre
        pytest.param(((0, 0, 0), (0, 0, 0), 1.0), ((3, 4, 0), (3, 4, 0), 1.5), 2.5, id="kure-kure"),
        # küre–kapsül iç bölge
        pytest.param(((0, 0, 5), (0, 0, 5), 1.0), ((-4, 0, 0), (4, 0, 0), 1.0), 3.0, id="kure-kapsul"),
    ],
)
def test_k1_kapsul_kapsul_kapali_form(a, b, beklenen):
    A, B = cap(*a), cap(*b)
    assert dist_capsule_capsule(A, B) == pytest.approx(beklenen, abs=1e-12)
    assert dist_capsule_capsule(B, A) == pytest.approx(beklenen, abs=1e-12)  # simetrik


def test_k1_kapsul_kapsul_rastgele():
    rng = np.random.default_rng(1)
    for _ in range(300):
        p1, q1, p2, q2 = rng.uniform(-5, 5, (4, 3))
        if rng.uniform() < 0.2:  # paralel
            q2 = p2 + (q1 - p1) * rng.uniform(0.2, 2.0)
        ra, rb = rng.uniform(0.1, 1.0, 2)
        beklenen = seg_seg(p1, q1, p2, q2) - ra - rb
        assert dist_capsule_capsule(cap(p1, q1, ra), cap(p2, q2, rb)) == pytest.approx(beklenen, abs=1e-9)


# --- kapsül–kutu (elle hesap, 1e-9) ----------------------------------------------------------------


def kutu() -> Box:
    """x ∈ [−2, 2], y ∈ [−1, 1], z ∈ [−1, 1]."""
    return box((0, 0, 0), (2, 1, 1))


@pytest.mark.parametrize(
    "c, beklenen",
    [
        # yüz bölgesi: üst yüzün 2 mm üstünde, yüze paralel
        pytest.param(((-1, 0, 3), (1, 0, 3), 0.5), 1.5, id="yuz"),
        # yüz bölgesi, eğik parça: en alçak ucu (1, 0.5, 1.5) → 0.5
        pytest.param(((1, 0.5, 1.5), (0, 0, 4), 0.25), 0.25, id="yuz-egik"),
        # kenar bölgesi: x = 2, z = 1 kenarına paralel, √2 uzakta
        pytest.param(((3, -0.5, 2), (3, 0.5, 2), 0.5), S2 - 0.5, id="kenar"),
        # köşe bölgesi: küre (3, 2, 2), köşe (2, 1, 1)
        pytest.param(((3, 2, 2), (3, 2, 2), 0.5), math.sqrt(3.0) - 0.5, id="kose"),
        # içinden geçen parça → nokta–kutu uzaklığı 0 → −r
        pytest.param(((-5, 0, 0), (5, 0, 0), 0.75), -0.75, id="icinden"),
        # tümüyle içeride
        pytest.param(((-0.5, 0, 0), (0.5, 0, 0), 0.25), -0.25, id="icinde"),
        # kenara çapraz yaklaşan parça: (3, 0, 2)–(2.5, 0, 3) en yakın uç (3, 0, 2) → kenar √2
        pytest.param(((3, 0, 2), (2.5, 0, 3), 0.1), S2 - 0.1, id="kenar-uc"),
    ],
)
def test_k1_kapsul_kutu_elle(c, beklenen):
    assert dist_capsule_box(cap(*c), kutu()) == pytest.approx(beklenen, abs=1e-9)


def test_k1_kapsul_kutu_45_derece():
    """Z etrafında 45° döndürülmüş birim yarı boylu kutu: XY'de köşesi (√2, 0)'da."""
    K = box((0, 0, 0), (1, 1, 1), Rz(45))
    # dikey kenara (x = √2, y = 0) dik uzaklık
    assert dist_capsule_box(cap((3, 0, 0), (3, 0, 0), 0.5), K) == pytest.approx(3 - S2 - 0.5, abs=1e-9)
    # kenara paralel dikey parça
    assert dist_capsule_box(cap((3, 0, -0.5), (3, 0, 0.5), 0.5), K) == pytest.approx(3 - S2 - 0.5, abs=1e-9)
    # yan yüz (normal (1,1,0)/√2, yüz düzlemi merkezden 1): nokta (2, 2, 0) → 2√2 − 1
    assert dist_capsule_box(cap((2, 2, 0), (2, 2, 0), 0.25), K) == pytest.approx(2 * S2 - 1 - 0.25, abs=1e-9)
    # üst yüz: z = 3 düzleminde X boyunca uzun parça → 2
    assert dist_capsule_box(cap((-5, 0, 3), (5, 0, 3), 0.5), K) == pytest.approx(1.5, abs=1e-9)


def test_k1_kapsul_kutu_rastgele():
    rng = np.random.default_rng(2)
    for _ in range(200):
        R = Rz(rng.uniform(0, 360)) @ Rx(rng.uniform(0, 360)) @ Rz(rng.uniform(0, 360))
        c0 = rng.uniform(-1, 1, 3)
        h = rng.uniform(0.5, 2.0, 3)
        p, q = rng.uniform(-6, 6, (2, 3))
        r = rng.uniform(0.05, 0.5)
        beklenen = seg_box(p, q, c0, h, R) - r
        assert dist_capsule_box(cap(p, q, r), box(c0, h, R)) == pytest.approx(beklenen, abs=1e-9)


# --- kutu–kutu (SAT) -------------------------------------------------------------------------------


def test_k1_kutu_kutu_ayrik_ve_degen():
    a = box((0, 0, 0), (1, 1, 1))
    assert not boxes_overlap(a, box((3, 0, 0), (1, 1, 1)))  # 1 mm boşluk
    assert not boxes_overlap(a, box((2 + 1e-6, 0, 0), (1, 1, 1)))  # neredeyse değiyor
    assert boxes_overlap(a, box((2, 0, 0), (1, 1, 1)))  # değen yüzler: kesişim sayılır
    assert boxes_overlap(a, box((2, 2, 2), (1, 1, 1)))  # köşede değme
    assert boxes_overlap(a, box((1.5, 0.3, -0.2), (1, 1, 1)))  # örtüşen


def test_k1_kutu_kutu_ic_ice():
    assert boxes_overlap(box((0, 0, 0), (5, 5, 5)), box((1, -1, 0.5), (0.5, 0.5, 0.5), Rz(30)))
    assert boxes_overlap(box((1, -1, 0.5), (0.5, 0.5, 0.5), Rz(30)), box((0, 0, 0), (5, 5, 5)))


@pytest.mark.parametrize("yon", [(1, 1, 0), (1, 0, 1), (-1, 0, -1), (0, 1, 1)])
def test_k1_kutu_kutu_kenar_kenar_45(yon):
    """B = Rx(45)·Rz(45) döndürülmüş birim kutu, köşegen yönde 2√2 uzakta kenar–kenar değiyor.
    Biraz uzakta yalnız kenar×kenar ekseni ayırır (6 yüz ekseni ayırmaz)."""
    Rb = Rx(45) @ Rz(45)
    d = np.array(yon, dtype=float) / np.linalg.norm(yon)
    h = np.ones(3)
    a = box((0, 0, 0), h)
    uzak = 2 * S2 + 1e-3
    yakin = 2 * S2 - 1e-3
    # durum gerçekten kenar–kenar: yüz eksenleri ayırmıyor, LP ayrık diyor
    assert not face_axes_separate(np.zeros(3), h, np.eye(3), uzak * d, h, Rb)
    assert not boxes_intersect_lp(np.zeros(3), h, np.eye(3), uzak * d, h, Rb)
    assert boxes_intersect_lp(np.zeros(3), h, np.eye(3), yakin * d, h, Rb)
    assert not boxes_overlap(a, box(uzak * d, h, Rb))
    assert boxes_overlap(a, box(yakin * d, h, Rb))


def test_k1_kutu_kutu_margin():
    """Her kutu margin/2 büyütülür: 1 mm boşluk margin = 1'de değer, 0.9'da ayrık kalır."""
    a = box((0, 0, 0), (1, 1, 1))
    b = box((3, 0, 0), (1, 1, 1))
    assert boxes_overlap(a, b, margin=1.0)
    assert boxes_overlap(a, b, margin=1.5)
    assert not boxes_overlap(a, b, margin=0.9)
    assert not boxes_overlap(a, b)


def test_k1_kutu_kutu_rastgele_lp():
    rng = np.random.default_rng(3)
    n = 0
    while n < 150:
        Ra = Rz(rng.uniform(0, 360)) @ Rx(rng.uniform(0, 360))
        Rb = Rx(rng.uniform(0, 360)) @ Rz(rng.uniform(0, 360))
        ha, hb = rng.uniform(0.3, 2.0, (2, 3))
        ca, cb = rng.uniform(-2.5, 2.5, (2, 3))
        ic = boxes_intersect_lp(ca, ha * (1 - 1e-6), Ra, cb, hb * (1 - 1e-6), Rb)
        dis = boxes_intersect_lp(ca, ha * (1 + 1e-6), Ra, cb, hb * (1 + 1e-6), Rb)
        if ic != dis:
            continue  # sınıra çok yakın: atla
        n += 1
        assert boxes_overlap(box(ca, ha, Ra), box(cb, hb, Rb)) == ic
