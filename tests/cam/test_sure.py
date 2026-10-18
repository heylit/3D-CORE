"""SPEC 72 — cam/sim/sure.py testleri: S eğrisi, köşe hızı, ileri-geri planlama, eksen sınırları (K1–K7, K13).

Testler yalnız specs/72-cevrim-suresi.md metninden ve iskeletin arayüzünden (imzalar, docstring'ler,
durum/72-cevrim-suresi.md) yazıldı; fonksiyon gövdeleri okunmadı. Beklenen değerlerin kaynağı her testin
yorumunda: SPEC 72 "Teori" formülleri ve el hesabı (Python math).

Birimler (SPEC 72 Arayüz): Dynamics v_max mm/dk, a_max mm/s², j_max mm/s³; scurve_time / junction_speed /
plan_speeds hızları mm/s; Move.feed mm/dk.

Varsayımlar (arayüzün yazmadığı yerler; koordinatöre bildirildi):
- plan_speeds girdisi [(p0, p1, F_mm_dk), ...] ardışık 3B doğrusal parçalar; dönüş n + 1 sınır hızı [mm/s],
  ilk ve son 0 (kodlayıcının arayüz notu).
- Bir segmentin süresi scurve_time(L, v, a_yol, j_yol, v_i, v_{i+1}); v = min(F/60, v_yol) (Teori 2, 4, 5).
- K3: j = None ve tol = 0 iken SPEC 05 move_time ile tam eşitlik eksene paralel doğrularda ve XY yaylarında
  sınanır (koordinatör kararı); çapraz doğruda eksen bazlı a_yol = min a_i/|u_i| ≥ a olduğundan
  toolpath_time ≤ move_time.
- K5'teki "segment bölmek süreyi değiştirmiyor" tol > 0 içindir (tol = 0 her köşede tam duruş, Arayüz).
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from cam.model import CamError, LatheTool, Move, MoveType, Plane, Tool, ToolKind, Toolpath
from cam.sim.sure import Dynamics, junction_speed, plan_speeds, scurve_time, toolpath_time
from cam.sim.timing import Machine, move_time
from tests.cam.lsimref import turn_tool

G0, G1, G2, G3 = MoveType.RAPID, MoveType.LINEAR, MoveType.ARC_CW, MoveType.ARC_CCW
REL = 1e-12


def dyn(
    v=(30000.0, 30000.0, 30000.0),
    a=(1000.0, 1000.0, 1000.0),
    j=(1e4, 1e4, 1e4),
    tol: float = 0.01,
    lookahead: int | None = None,
) -> Dynamics:
    """Uydurma tezgâh dinamiği (eksen başına)."""
    return Dynamics(
        v_max=tuple(v), a_max=tuple(a), j_max=None if j is None else tuple(j), tol=tol, lookahead=lookahead
    )


def freze() -> Tool:
    return Tool(id=1, name="freze10", kind=ToolKind.FLAT, D=10.0, flute_length=30.0)


def path(start, moves: list[Move]) -> Toolpath:
    tp = Toolpath("yol", freze(), tuple(float(v) for v in start), list(moves), rpm=10_000.0)
    tp.validate()
    return tp


def polyline(pts, F: float) -> Toolpath:
    return path(pts[0], [Move(G1, tuple(p), feed=F) for p in pts[1:]])


# ---------------------------------------------------------------- bağımsız S eğrisi referansı (Teori 1)


def ref_phases(L: float, v: float, a: float, j: float) -> list[tuple[float, float]]:
    """Duruştan duruşa yedi evre [(sarsıntı, süre)], Teori 1'in bölgeleriyle (test kendi hesaplar)."""
    if v >= a * a / j:
        s_h = v * (v / a + a / j) / 2
    else:
        s_h = v * math.sqrt(v / j)
    if L >= 2 * s_h:
        vp, Tv = v, (L - 2 * s_h) / v
    elif v >= a * a / j and L >= 2 * a**3 / j**2:
        vp, Tv = (a / 2) * (-a / j + math.sqrt(a * a / (j * j) + 4 * L / a)), 0.0
    else:
        vp, Tv = (j * L * L / 4) ** (1 / 3), 0.0
    if vp >= a * a / j:
        Tj, Ta = a / j, vp / a - a / j
    else:
        Tj, Ta = math.sqrt(vp / j), 0.0
    return [(j, Tj), (0.0, Ta), (-j, Tj), (0.0, Tv), (-j, Tj), (0.0, Ta), (j, Tj)]


def integrate(phases, dt_max: float = 1e-6) -> tuple[float, float, float, float, float]:
    """Sarsıntı profilini sayısal integre eder (adım ≤ dt_max, ivme ve hızda yamuk kuralı).

    Her evre tam sayıda adıma bölünür (adım = T/n ≤ dt_max). Döner: (süre, yol, son hız, en büyük hız,
    en büyük |ivme|).
    """
    t = s = v = acc = 0.0
    vmax = amax = 0.0
    for jerk, T in phases:
        if T <= 0:
            continue
        n = max(1, math.ceil(T / dt_max))
        dt = T / n
        done = 0
        while done < n:  # parça parça (bellek)
            m = min(n - done, 1_000_000)
            k = np.arange(1, m + 1, dtype=float)
            a_k = acc + jerk * dt * k  # ivme adım sonlarında (sarsıntı sabit → tam)
            a_prev = np.concatenate(([acc], a_k[:-1]))
            v_k = v + np.cumsum((a_prev + a_k) / 2 * dt)
            v_prev = np.concatenate(([v], v_k[:-1]))
            s += float(np.sum((v_prev + v_k) / 2 * dt))
            vmax = max(vmax, float(v_k.max()))
            amax = max(amax, float(np.abs(a_k).max()))
            acc, v = float(a_k[-1]), float(v_k[-1])
            done += m
        t += T
    return t, s, v, vmax, amax


# ================================================================ K1: S eğrisi, duruştan duruşa


@pytest.mark.parametrize(
    "L, v, a, j, t_exp",
    [
        # sabit hız evresi var, ivme sınırına ulaşılıyor: t = L/v + v/a + a/j = 5 + 0.1 + 0.1
        (500.0, 100.0, 1000.0, 1e4, 5.2),
        # 2a³/j² = 20 ≤ L = 40 < 2·s_h = 1100: v_p = (a/2)(−a/j + √(a²/j² + 4L/a)), t = 2(v_p/a + a/j)
        (40.0, 1000.0, 1000.0, 1e4, 0.5123105625617661),
        # L = 10 < 2a³/j² = 20 (ve < 2s_h = 20): t = 4·(L/(2j))^(1/3) = 4·(5·10⁻⁴)^(1/3)
        (10.0, 100.0, 1000.0, 1e4, 0.31748021039363994),
        # v = 50 < a²/j = 800: t_h = 2√(v/j) = 0.2, s_h = v·t_h/2 = 5 → t = 500/50 + 0.2
        (500.0, 50.0, 2000.0, 5000.0, 10.2),
    ],
)
def test_scurve_closed_forms(L, v, a, j, t_exp):
    """K1: Teori 1 örnekleri (göreli 1e-12)."""
    assert scurve_time(L, v, a, j) == pytest.approx(t_exp, rel=REL)


def test_scurve_reference_values_self_check():
    """Öz denetim: K1'deki ondalık değerler Teori 1 formüllerinden el hesabıyla aynı."""
    vp = 500.0 * (-0.1 + math.sqrt(0.01 + 0.16))
    assert 2 * (vp / 1000.0 + 0.1) == pytest.approx(0.5123105625617661, rel=1e-15)
    assert vp == pytest.approx(156.155, abs=1e-3)
    assert 4 * (10.0 / 2e4) ** (1 / 3) == pytest.approx(0.31748021039363994, rel=1e-15)


@pytest.mark.parametrize(
    "boundary, v, a, j",
    [
        (1100.0, 1000.0, 1000.0, 1e4),  # L = 2·s_h, s_h = v(v/a + a/j)/2 = 550
        (20.0, 1000.0, 1000.0, 1e4),  # L = 2a³/j²
        (20.0, 100.0, 1000.0, 1e4),  # L = 2·s_h = 2a³/j² (v = a²/j)
        (10.0, 50.0, 2000.0, 5000.0),  # v < a²/j: L = 2·s_h = 2v√(v/j)
    ],
)
def test_scurve_continuous_at_region_boundaries(boundary, v, a, j):
    """K1: bölge sınırlarında süre sürekli (iki yandan 1e-9)."""
    h = 1e-9  # mm, iki yandan
    lo = scurve_time(boundary - h, v, a, j)
    mid = scurve_time(boundary, v, a, j)
    hi = scurve_time(boundary + h, v, a, j)
    assert abs(hi - lo) <= 1e-9
    assert abs(mid - lo) <= 1e-9 and abs(hi - mid) <= 1e-9


def test_scurve_monotone_in_length():
    """K1 / K5: süre L ile artar (bölge geçişleri dahil)."""
    Ls = np.geomspace(1e-3, 3000.0, 400)
    t = [scurve_time(float(L), 1000.0, 1000.0, 1e4) for L in Ls]
    assert all(b >= a - 1e-15 for a, b in zip(t, t[1:], strict=False))


@pytest.mark.parametrize("L", [0.5, 5.0, 50.0, 500.0])
def test_scurve_jerk_infinite_is_spec05(L):
    """Teori 1 sınır durumu: j = None (sonsuz) → SPEC 05 trapez L/v + v/a (L ≥ v²/a) veya üçgen 2√(L/a)."""
    v, a = 100.0, 1000.0
    exp = L / v + v / a if L >= v * v / a else 2 * math.sqrt(L / a)
    assert scurve_time(L, v, a, None) == pytest.approx(exp, rel=REL)


def test_scurve_large_jerk_tends_to_trapezoid():
    """Teori 1: j → ∞ iken sonlu j sonucu trapez / üçgen formüllerine yaklaşır."""
    for L, exp in ((500.0, 5.1), (4.0, 2 * math.sqrt(4.0 / 1000.0))):
        assert scurve_time(L, 100.0, 1000.0, 1e12) == pytest.approx(exp, rel=1e-6)


# ================================================================ K2: sayısal sağlama


@pytest.mark.parametrize(
    "L, v, a, j",
    [
        (500.0, 100.0, 1000.0, 1e4),
        (40.0, 1000.0, 1000.0, 1e4),
        (10.0, 100.0, 1000.0, 1e4),
        (500.0, 50.0, 2000.0, 5000.0),
    ],
)
def test_scurve_numeric_integration(L, v, a, j):
    """K2: Teori 1 evreleri (sarsıntı ±j, 0) adım ≤ 1e-6 s ile integre edilince yol L'yi, süre scurve_time'ı
    1e-4 içinde verir; hız v'yi, ivme a'yı aşmaz, son hız 0."""
    T, s, v_end, vmax, amax = integrate(ref_phases(L, v, a, j))
    assert s == pytest.approx(L, abs=1e-4)
    assert abs(v_end) <= 1e-4
    assert vmax <= v + 1e-6
    assert amax <= a + 1e-6
    assert scurve_time(L, v, a, j) == pytest.approx(T, abs=1e-4)


# ================================================================ Teori 2: giriş / çıkış hızı


def test_scurve_with_entry_exit_speed_closed_form():
    """Teori 2: v₀ = 0 → v₁ = 100, a = 1000, j = 10⁴: Δv = 100 ≥ a²/j → τ = Δv/a + a/j = 0.2, hızlanma yolu
    (0 + 100)·0.2/2 = 10. L = 60: hızlanma + 50 mm sabit hız → t = 0.2 + 0.5 = 0.7."""
    assert scurve_time(60.0, 100.0, 1000.0, 1e4, v0=0.0, v1=100.0) == pytest.approx(0.7, rel=1e-9)


def test_scurve_constant_speed_through():
    """Teori 2: v₀ = v₁ = v → t = L/v."""
    assert scurve_time(37.0, 80.0, 1000.0, 1e4, v0=80.0, v1=80.0) == pytest.approx(37.0 / 80.0, rel=1e-12)


@pytest.mark.parametrize("v0, v1", [(0.0, 30.0), (20.0, 60.0), (5.0, 0.0), (40.0, 40.0)])
def test_scurve_time_reversal_symmetric(v0, v1):
    """Teori 2: S eğrisi zamanda simetrik → (v₀, v₁) ile (v₁, v₀) aynı süre (ikiye bölme 1e-9 mm/s)."""
    t1 = scurve_time(25.0, 100.0, 1000.0, 1e4, v0=v0, v1=v1)
    t2 = scurve_time(25.0, 100.0, 1000.0, 1e4, v0=v1, v1=v0)
    assert t1 == pytest.approx(t2, rel=1e-9)


def test_scurve_entry_speed_never_slower_than_stop():
    """Teori 2: aynı boyda sıfırdan büyük giriş / çıkış hızı süreyi uzatmaz."""
    t0 = scurve_time(25.0, 100.0, 1000.0, 1e4)
    assert scurve_time(25.0, 100.0, 1000.0, 1e4, v0=30.0, v1=30.0) <= t0 + 1e-12


def test_scurve_unreachable_speed_change_raises():
    """K13 / Teori 2: v₀ → v₁ boy içinde ulaşılamıyorsa CamError (sessizce kısaltma yok):
    0 → 100 mm/s en az 10 mm ister, L = 1."""
    with pytest.raises(CamError):
        scurve_time(1.0, 100.0, 1000.0, 1e4, v0=0.0, v1=100.0)


# ================================================================ K13: hatalı girdi


@pytest.mark.parametrize(
    "args",
    [
        (-1.0, 100.0, 1000.0, 1e4),  # L < 0
        (10.0, 0.0, 1000.0, 1e4),  # v ≤ 0
        (10.0, -5.0, 1000.0, 1e4),
        (10.0, 100.0, 0.0, 1e4),  # a ≤ 0
        (10.0, 100.0, 1000.0, -1.0),  # j ≤ 0
        (float("nan"), 100.0, 1000.0, 1e4),
        (10.0, float("nan"), 1000.0, 1e4),
        (10.0, 100.0, float("inf"), 1e4),
    ],
)
def test_scurve_bad_input_raises(args):
    """K13: L < 0, v ≤ 0, nan / inf → CamError."""
    with pytest.raises(CamError):
        scurve_time(*args)


def test_scurve_entry_above_limit_raises():
    """Teori 2: v₀, v₁ ≤ v; aşarsa CamError (sessiz kırpma yok)."""
    with pytest.raises(CamError):
        scurve_time(100.0, 50.0, 1000.0, 1e4, v0=60.0)


def test_scurve_never_nan_or_negative():
    """K13: geniş bir parametre ızgarasında süre sonlu ve ≥ 0, L > 0 için > 0."""
    for L in (1e-6, 1e-3, 0.1, 3.0, 77.0, 5000.0):
        for v in (1.0, 50.0, 1000.0):
            for a in (10.0, 1000.0, 1e5):
                for j in (None, 100.0, 1e4, 1e8):
                    t = scurve_time(L, v, a, j)
                    assert math.isfinite(t) and t > 0


@pytest.mark.parametrize(
    "kw",
    [
        dict(v=(0.0, 30000.0, 30000.0)),
        dict(v=(-1.0, 30000.0, 30000.0)),
        dict(a=(1000.0, float("nan"), 1000.0)),
        dict(a=(1000.0, 1000.0, 0.0)),
        dict(j=(1e4, -1e4, 1e4)),
        dict(j=(1e4, 1e4, float("inf"))),
        dict(tol=-0.01),
        dict(tol=float("nan")),
        dict(lookahead=0),
    ],
)
def test_dynamics_bad_values_raise(kw):
    """Arayüz: pozitif olmayan / sonlu olmayan değer → CamError (tol = 0 serbest: her köşede tam duruş)."""
    with pytest.raises(CamError):
        dyn(**kw)


def test_dynamics_valid():
    """Arayüz: j_max = None (sonsuz sarsıntı) ve tol = 0 geçerli."""
    d = dyn(j=None, tol=0.0)
    assert d.j_max is None and d.tol == 0.0


# ================================================================ K4: köşe hızı


def u(deg: float) -> tuple[float, float, float]:
    return (math.cos(math.radians(deg)), math.sin(math.radians(deg)), 0.0)


def test_junction_speed_90_degrees():
    """K4: ε = 0.01, φ = 90°, a = 1000, F büyük: R = ε·cos45°/(1 − cos45°) = 0.024142…,
    v_k = √(a·R) = 4.9135 mm/s = 294.80788362157386 mm/dk (1e-9)."""
    R = 0.01 * math.cos(math.pi / 4) / (1 - math.cos(math.pi / 4))
    assert R == pytest.approx(0.024142, abs=1e-6)
    assert math.sqrt(1000.0 * R) * 60 == pytest.approx(294.80788362157386, rel=1e-12)
    v = junction_speed(u(0), u(90), 1e6, 1000.0, 0.01, 100.0, 100.0)
    assert v * 60 == pytest.approx(294.80788362157386, rel=1e-9)


def test_junction_speed_straight_and_reverse():
    """K4: φ = 0 → v_k = F; φ = 180° (geri dönüş) → 0."""
    assert junction_speed(u(30), u(30), 50.0, 1000.0, 0.01, 10.0, 10.0) == pytest.approx(50.0, rel=1e-12)
    assert junction_speed(u(30), u(210), 50.0, 1000.0, 0.01, 10.0, 10.0) == pytest.approx(0.0, abs=1e-12)


def test_junction_speed_capped_by_feed():
    """K4: v_k = min(F, √(a·R)): küçük F'de F."""
    assert junction_speed(u(0), u(90), 2.0, 1000.0, 0.01, 100.0, 100.0) == pytest.approx(2.0, rel=1e-12)


def test_junction_speed_short_segment_tangent_limit():
    """K4: çok kısa segmentte teğet boy sınırı: R·tan(φ/2) ≤ min(L1, L2)/2. φ = 90°, L1 = 0.02, L2 = 5:
    serbest R = 0.0241 > 0.01 → R = 0.01/tan45° = 0.01, v_k = √(1000·0.01) = √10."""
    v = junction_speed(u(0), u(90), 1e6, 1000.0, 0.01, 0.02, 5.0)
    assert v == pytest.approx(math.sqrt(10.0), rel=1e-9)
    assert junction_speed(u(0), u(90), 1e6, 1000.0, 0.01, 5.0, 0.02) == pytest.approx(v, rel=1e-12)


@pytest.mark.parametrize("phi", [10.0, 45.0, 120.0, 170.0])
def test_junction_speed_formula(phi):
    """K4: genel φ: R = ε·cos(φ/2)/(1 − cos(φ/2)), v_k = min(F, √(a·R)) (uzun segmentler)."""
    c = math.cos(math.radians(phi) / 2)
    R = 0.02 * c / (1 - c)
    v = junction_speed(u(0), u(phi), 1e6, 800.0, 0.02, 1e3, 1e3)
    assert v == pytest.approx(math.sqrt(800.0 * R), rel=1e-9)


def test_junction_speed_tol_zero_full_stop():
    """Arayüz: tol = 0 → her köşede tam duruş (v_k = 0), φ > 0."""
    assert junction_speed(u(0), u(30), 50.0, 1000.0, 0.0, 10.0, 10.0) == pytest.approx(0.0, abs=1e-12)


# ================================================================ Teori 4: plan_speeds


def segs_of(pts, F: float):
    return [(tuple(pts[i]), tuple(pts[i + 1]), F) for i in range(len(pts) - 1)]


def test_plan_speeds_shape_and_ends():
    """Teori 4: n + 1 sınır hızı, ilk ve son 0; hepsi ≥ 0 ve ≤ F/60."""
    pts = [(0, 0, 0), (30, 0, 0), (30, 20, 0), (10, 25, 0), (12, 40, -2)]
    v = plan_speeds(segs_of(pts, 3000.0), dyn())
    assert len(v) == len(pts)
    assert v[0] == 0.0 and v[-1] == 0.0
    assert all(0.0 <= x <= 3000.0 / 60 + 1e-12 for x in v)


def test_plan_speeds_corner_and_straight():
    """Teori 3–4: uzun segmentlerde iç sınır hızı köşe hızına eşit; düz devamda (φ = 0) F/60."""
    d = dyn()
    v = plan_speeds(segs_of([(0, 0, 0), (100, 0, 0), (100, 100, 0)], 6000.0), d)
    vk = junction_speed(u(0), u(90), 100.0, 1000.0, 0.01, 100.0, 100.0)
    assert v[1] == pytest.approx(vk, rel=1e-9)
    v2 = plan_speeds(segs_of([(0, 0, 0), (100, 0, 0), (200, 0, 0)], 6000.0), d)
    assert v2[1] == pytest.approx(100.0, rel=1e-9)


def test_plan_speeds_zigzag_zero():
    """Teori 3: φ = 180° köşelerde sınır hızı 0."""
    pts = [(0, 0, 0), (10, 0, 0), (0, 0, 0), (10, 0, 0)]
    v = plan_speeds(segs_of(pts, 3000.0), dyn())
    assert v == pytest.approx([0.0, 0.0, 0.0, 0.0], abs=1e-12)


def test_plan_speeds_reachable_backward_forward():
    """Teori 4: kısa segmentlerde sınır hızları komşu segmentte S eğrisiyle ulaşılabilir:
    her i için scurve_time(L_i, v, a, j, v_i, v_{i+1}) CamError vermez ve sonlu."""
    pts = [(0, 0, 0)] + [(0.5 * (k + 1), 0.3 * ((k + 1) % 2), 0) for k in range(30)]
    d = dyn()
    v = plan_speeds(segs_of(pts, 6000.0), d)
    for i in range(len(pts) - 1):
        L = math.dist(pts[i], pts[i + 1])
        t = scurve_time(L, 100.0, 1000.0, 1e4, v0=v[i], v1=v[i + 1])
        assert math.isfinite(t) and t > 0


# ================================================================ toolpath_time ile segment toplamı


def test_toolpath_time_is_sum_of_planned_segments():
    """Teori 2, 4: köşeli G1 yolunun kesme süresi Σ scurve_time(L_i, F/60, a, j, v_i, v_{i+1}) (eksene paralel
    segmentler: a_yol = a, j_yol = j); G0 yok → rapid = 0."""
    pts = [(0.0, 0.0, 0.0), (40.0, 0.0, 0.0), (40.0, 25.0, 0.0), (5.0, 25.0, 0.0)]
    F = 3000.0
    d = dyn()
    v = plan_speeds(segs_of(pts, F), d)
    exp = sum(
        scurve_time(math.dist(pts[i], pts[i + 1]), F / 60, 1000.0, 1e4, v[i], v[i + 1])
        for i in range(len(pts) - 1)
    )
    pt = toolpath_time(polyline(pts, F), d)
    assert pt.cut == pytest.approx(exp, rel=1e-9)
    assert pt.rapid == 0.0
    assert pt.n_moves == 3
    assert pt.total == pytest.approx(pt.cut, rel=1e-15)


# ================================================================ K3: SPEC 05'e iniş


def spec05_total(tp: Toolpath, machine: Machine) -> float:
    p0 = np.array(tp.start)
    t = 0.0
    for m in tp.moves:
        p1 = np.array(m.end)
        t += move_time(p0, p1, m, Plane.XY, machine)
        p0 = p1
    return t


RAPID = (12000.0, 12000.0, 8000.0)


def k3_dyn(a: float = 800.0) -> Dynamics:
    return dyn(v=RAPID, a=(a, a, a), j=None, tol=0.0)


def rect_pocket_path() -> Toolpath:
    """Uydurma dikdörtgen cep: eksene paralel G0 / G1 (iç içe iki dikdörtgen halka, dalma, geri çekme)."""
    z_s, z = 10.0, -2.0
    mv = [Move(G0, (5.0, 5.0, z_s)), Move(G0, (5.0, 5.0, 1.0)), Move(G1, (5.0, 5.0, z), feed=200.0)]
    for x0, y0, x1, y1 in ((5.0, 5.0, 55.0, 35.0), (10.0, 10.0, 50.0, 30.0)):
        if mv[-1].end[:2] != (x0, y0):  # halkalar arası geçiş de eksene paralel (K3: çapraz doğru eşit değil)
            mv.append(Move(G1, (x0, mv[-1].end[1], z), feed=900.0))
            mv.append(Move(G1, (x0, y0, z), feed=900.0))
        mv += [Move(G1, (x1, y0, z), feed=900.0), Move(G1, (x1, y1, z), feed=900.0)]
        mv += [Move(G1, (x0, y1, z), feed=900.0), Move(G1, (x0, y0, z), feed=900.0)]
    mv.append(Move(G0, (10.0, 10.0, z_s)))
    return path((0.0, 0.0, z_s), [Move(G0, (5.0, 0.0, z_s))] + mv)


def contour_arc_path() -> Toolpath:
    """Uydurma kontur: eksene paralel doğrular + XY'de G2 / G3 yaylar (biri merkezcil sınırda, r = 0.5)."""
    z = -1.0
    mv = [
        Move(G0, (0.0, 0.0, 1.0)),
        Move(G1, (0.0, 0.0, z), feed=300.0),
        Move(G1, (40.0, 0.0, z), feed=1200.0),
        Move(G3, (50.0, 10.0, z), feed=1200.0, center=(40.0, 10.0)),
        Move(G1, (50.0, 30.0, z), feed=1200.0),
        Move(G2, (51.0, 30.0, z), feed=3000.0, center=(50.5, 30.0)),  # r = 0.5: √(a·r) = 20 < 50 mm/s
        Move(G1, (51.0, 40.0, z), feed=1200.0),
        Move(G3, (51.0, 40.0, z), feed=1500.0, center=(46.0, 40.0)),  # tam daire
        Move(G0, (51.0, 40.0, 10.0)),
    ]
    return path((0.0, 0.0, 10.0), mv)


@pytest.mark.parametrize("make", [rect_pocket_path, contour_arc_path], ids=["cep", "kontur_yay"])
@pytest.mark.parametrize("a", [200.0, 800.0, 5000.0])
def test_reduces_to_spec05(make, a):
    """K3: j = None, tol = 0, eşit eksen ivmeleri, v_max = rapid: toolpath_time.total = Σ SPEC 05 move_time
    (Machine(rapid, accel=a)), göreli 1e-12."""
    tp = make()
    pt = toolpath_time(tp, k3_dyn(a))
    exp = spec05_total(tp, Machine(rapid=RAPID, accel=a))
    assert pt.total == pytest.approx(exp, rel=1e-12)
    assert pt.n_moves == len(tp.moves)


def test_reduces_to_spec05_split_cut_and_rapid():
    """K3: kesme ve hızlı ayrı ayrı da SPEC 05 ile aynı."""
    tp = contour_arc_path()
    machine = Machine(rapid=RAPID, accel=800.0)
    pt = toolpath_time(tp, k3_dyn(800.0))
    p0 = np.array(tp.start)
    cut = rapid = 0.0
    for m in tp.moves:
        p1 = np.array(m.end)
        t = move_time(p0, p1, m, Plane.XY, machine)
        if m.type is G0:
            rapid += t
        else:
            cut += t
        p0 = p1
    assert pt.cut == pytest.approx(cut, rel=1e-12)
    assert pt.rapid == pytest.approx(rapid, rel=1e-12)


def test_diagonal_not_slower_than_spec05():
    """K3 (koordinatör kararı): çapraz doğruda a_yol = min a_i/|u_i| ≥ a → toolpath_time ≤ move_time."""
    tp = polyline([(0.0, 0.0, 0.0), (30.0, 40.0, 0.0), (60.0, 0.0, -5.0)], 2400.0)
    pt = toolpath_time(tp, k3_dyn(800.0))
    assert pt.total <= spec05_total(tp, Machine(rapid=RAPID, accel=800.0)) + 1e-12


# ================================================================ K5: tekdüzelik


def k5_path(F: float = 3000.0) -> Toolpath:
    pts = [
        (0, 0, 0),
        (30, 0, 0),
        (30, 20, 0),
        (10, 25, 0),
        (12, 40, -2),
        (50, 45, -2),
        (49, 46, -2),
        (80, 0, 0),
    ]
    tp = polyline([tuple(map(float, p)) for p in pts], F)
    tp.moves.append(Move(G0, (0.0, 0.0, 20.0)))
    return tp


def nonincreasing(ts) -> bool:
    return all(b <= a + 1e-12 for a, b in zip(ts, ts[1:], strict=False))


def test_monotone_in_tolerance():
    """K5: ε artınca toplam süre artmıyor."""
    ts = [toolpath_time(k5_path(), dyn(tol=e)).total for e in (0.0, 0.001, 0.01, 0.1, 1.0)]
    assert nonincreasing(ts)


def test_monotone_in_accel():
    """K5: a artınca toplam süre artmıyor."""
    ts = [toolpath_time(k5_path(), dyn(a=(a, a, a))).total for a in (100.0, 300.0, 1000.0, 5000.0)]
    assert nonincreasing(ts)


def test_monotone_in_jerk():
    """K5: j artınca toplam süre artmıyor (None = sonsuz en sonda)."""
    ts = [
        toolpath_time(k5_path(), dyn(j=None if j is None else (j, j, j))).total
        for j in (500.0, 5e3, 5e4, None)
    ]
    assert nonincreasing(ts)


def test_monotone_in_feed():
    """K5: F artınca toplam süre artmıyor."""
    ts = [toolpath_time(k5_path(F), dyn()).total for F in (300.0, 1000.0, 3000.0, 9000.0)]
    assert nonincreasing(ts)


@pytest.mark.parametrize("t_split", [0.5, 0.137])
def test_split_segment_same_time(t_split):
    """K5: aynı doğruyu iki parçaya ayırmak (φ = 0) süreyi değiştirmiyor (1e-9), tol > 0."""
    a, b = np.array([0.0, 0.0, 0.0]), np.array([60.0, 25.0, -3.0])
    m = tuple(a + t_split * (b - a))
    one = toolpath_time(polyline([tuple(a), tuple(b)], 4000.0), dyn()).total
    two = toolpath_time(polyline([tuple(a), m, tuple(b)], 4000.0), dyn()).total
    assert two == pytest.approx(one, abs=1e-9)


# ================================================================ K6: ileri-geri planlama


def test_many_short_collinear_segments_equal_single():
    """K6: 1000 eşit kısa segmentli düz çizgi (100 mm, 0.1 mm parçalar) = tek segment süresi (1e-9).
    Tek segment: scurve_time(100, 100, 1000, 10⁴) = 1 + 0.2 = 1.2 s."""
    pts = [(0.1 * k, 0.0, 0.0) for k in range(1001)]
    pt = toolpath_time(polyline(pts, 6000.0), dyn())
    assert pt.n_moves == 1000
    assert pt.total == pytest.approx(1.2, abs=1e-9)
    assert pt.total == pytest.approx(scurve_time(100.0, 100.0, 1000.0, 1e4), abs=1e-9)


def test_zigzag_is_sum_of_stop_to_stop():
    """K6: zigzag (φ = 180°) = segment başına duruştan duruşa toplamı."""
    pts = [(0.0, 0.0, 0.0)] + [((k % 2 == 0) * 15.0, 0.0, 0.0) for k in range(1, 9)]
    pts = [(15.0 if k % 2 else 0.0, 0.0, 0.0) for k in range(9)]
    pt = toolpath_time(polyline(pts, 6000.0), dyn())
    assert pt.total == pytest.approx(8 * scurve_time(15.0, 100.0, 1000.0, 1e4), rel=1e-9)


def test_lookahead_horizon_monotone():
    """Karar 3: ileri bakış ufku büyüdükçe süre artmaz; ufuk segment sayısından büyükse
    sınırsızla aynı."""
    pts = [(0.1 * k, 0.0, 0.0) for k in range(301)]
    tp = polyline(pts, 6000.0)
    ts = [toolpath_time(tp, dyn(lookahead=N)).total for N in (1, 5, 50, 1000)]
    assert all(b <= a + 1e-12 for a, b in zip(ts, ts[1:], strict=False))
    assert ts[-1] == pytest.approx(toolpath_time(tp, dyn()).total, abs=1e-9)


# ================================================================ K7: eksen başına sınır


def test_axis_accel_diagonal():
    """K7: a_X = 500, a_Y = 1000, 45° doğruda a_yol = min(a_i/|u_i|) = 500/cos45° = 500√2 (j = None)."""
    d = dyn(a=(500.0, 1000.0, 1000.0), j=None)
    L = 50.0 * math.sqrt(2)
    tp = polyline([(0.0, 0.0, 0.0), (50.0, 50.0, 0.0)], 3000.0)
    exp = scurve_time(L, 50.0, 500.0 * math.sqrt(2), None)
    assert toolpath_time(tp, d).total == pytest.approx(exp, rel=1e-12)


def test_axis_limit_irrelevant_axis():
    """K7: yalnız Y hareketinde X sınırı etkisiz: a_yol = a_Y."""
    d = dyn(a=(50.0, 1000.0, 1000.0), j=None)
    tp = polyline([(0.0, 0.0, 0.0), (0.0, 80.0, 0.0)], 3000.0)
    assert toolpath_time(tp, d).total == pytest.approx(scurve_time(80.0, 50.0, 1000.0, None), rel=1e-12)


def test_axis_jerk_diagonal():
    """Teori 5: j_yol = min j_i/|u_i|; 45° doğruda j_X = 2000, j_Y = 10⁴ → j_yol = 2000√2."""
    d = dyn(a=(1000.0, 1000.0, 1000.0), j=(2000.0, 1e4, 1e4))
    tp = polyline([(0.0, 0.0, 0.0), (30.0, 30.0, 0.0)], 3000.0)
    exp = scurve_time(30.0 * math.sqrt(2), 50.0, 1000.0 * math.sqrt(2), 2000.0 * math.sqrt(2))
    assert toolpath_time(tp, d).total == pytest.approx(exp, rel=1e-12)


def test_axis_speed_limit_on_feed_and_rapid():
    """Teori 5: kesmede v = min(F/60, v_yol), v_yol = min v_i/|u_i| (mm/dk → /60); G0'da v = v_yol.
    X hızı 1200 mm/dk: X yönünde F = 6000 → v = 20 mm/s; G0 X'te de 20 mm/s."""
    d = dyn(v=(1200.0, 30000.0, 30000.0), j=None)
    cut = polyline([(0.0, 0.0, 0.0), (100.0, 0.0, 0.0)], 6000.0)
    assert toolpath_time(cut, d).cut == pytest.approx(scurve_time(100.0, 20.0, 1000.0, None), rel=1e-12)
    rap = path((0.0, 0.0, 0.0), [Move(G0, (100.0, 0.0, 0.0))])
    pt = toolpath_time(rap, d)
    assert pt.rapid == pytest.approx(scurve_time(100.0, 20.0, 1000.0, None), rel=1e-12)
    assert pt.cut == 0.0


def test_rapid_is_full_stop():
    """Teori 4: G0 tam duruştur: G1 – G0 – G1 zincirinde G0 kendi başına duruştan duruşa."""
    d = dyn(j=None)
    tp = path(
        (0.0, 0.0, 0.0),
        [
            Move(G1, (50.0, 0.0, 0.0), feed=3000.0),
            Move(G0, (100.0, 0.0, 0.0)),
            Move(G1, (150.0, 0.0, 0.0), feed=3000.0),
        ],
    )
    pt = toolpath_time(tp, d)
    assert pt.rapid == pytest.approx(scurve_time(50.0, 500.0, 1000.0, None), rel=1e-12)
    assert pt.cut == pytest.approx(2 * scurve_time(50.0, 50.0, 1000.0, None), rel=1e-12)


# ================================================================ K13: torna düzlemi


def test_lathe_tool_in_xy_plane_raises():
    """K13: G18 dışı torna düzlemi uyumsuzluğu → CamError."""
    tool: LatheTool = turn_tool()
    tp = Toolpath(
        "torna", tool, (20.0, 0.0, 2.0), [Move(G1, (20.0, 0.0, -10.0), feed=0.2)], rpm=1000.0, plane=Plane.XY
    )
    with pytest.raises(CamError):
        toolpath_time(tp, dyn())


# ================================================================ K8: döner eksen
#
# Arayüz eki (kodlayıcı, koordinatör aracılığıyla; durum/72): toolpath_time(tp, dyn, *, q=None, tcp=False,
# inv_feed=None). q: (n + 1, 3 + k) eklem değerleri, satır i hareket i'den önceki durum, q[:, 3:] derece,
# dyn.rot_v (derece/dk) ile aynı sırada. Döner sınır saf hız sınırı: t_r = |Δq_r| / (rot_v_r/60).
# G0 ve G1 (tcp=True ya da değil): t = max(t_doğrusal, max_r t_r). G93: inv_feed (n,) [1/dk] → G1/G2/G3 süresi
# 60/inv_feed[i] s; G0 hızlı kalır.


def rot_dyn(omega_deg_s: float, a: float = 1000.0) -> Dynamics:
    return Dynamics(
        v_max=(6000.0, 6000.0, 6000.0),
        a_max=(a, a, a),
        j_max=None,
        rot_v=(omega_deg_s * 60.0,),
        rot_a=(500.0,),
        tol=0.0,
    )


def one_move(move: Move) -> Toolpath:
    return path((0.0, 0.0, 0.0), [move])


def q_of(tp: Toolpath, b0: float, b1: float) -> np.ndarray:
    pts = tp.points()
    return np.column_stack([pts, [b0, b1]])


@pytest.mark.parametrize("omega, rotary_wins", [(30.0, True), (1e5, False)])
def test_rotary_rapid(omega, rotary_wins):
    """K8: B 90° dönüşü ve 1 mm doğrusal G0: t = max(t_doğrusal, 90/ω_B). ω = 30 °/s → 3 s; ω çok büyükse
    doğrusal S eğrisi (v = 6000/60 = 100 mm/s, a = 1000, j = ∞): scurve_time(1, 100, 1000, None)."""
    tp = one_move(Move(G0, (1.0, 0.0, 0.0)))
    t_lin = scurve_time(1.0, 100.0, 1000.0, None)
    pt = toolpath_time(tp, rot_dyn(omega), q=q_of(tp, 0.0, 90.0))
    exp = max(t_lin, 90.0 / omega)
    assert pt.total == pytest.approx(exp, rel=1e-12)
    assert pt.rapid == pytest.approx(exp, rel=1e-12)
    assert (exp == 90.0 / omega) is rotary_wins


def test_rotary_tcp_feed_limited_by_rotary_speed():
    """K8: TCP'li G1'de döner hız sınırı aşılınca süre |Δq|/ω: 10 mm, F = 600
    (doğrusal ≈ 1 s), B 0 → 90° ω = 30 °/s → 3 s."""
    tp = one_move(Move(G1, (10.0, 0.0, 0.0), feed=600.0))
    pt = toolpath_time(tp, rot_dyn(30.0), q=q_of(tp, 0.0, 90.0), tcp=True)
    assert pt.cut == pytest.approx(3.0, rel=1e-12)
    t_lin = scurve_time(10.0, 10.0, 1000.0, None)
    assert t_lin < 3.0
    pt2 = toolpath_time(tp, rot_dyn(1e5), q=q_of(tp, 0.0, 90.0), tcp=True)
    assert pt2.cut == pytest.approx(t_lin, rel=1e-12)


def test_rotary_negative_direction_uses_abs():
    """K8: |Δq|: B 90 → 0 de 3 s."""
    tp = one_move(Move(G0, (1.0, 0.0, 0.0)))
    assert toolpath_time(tp, rot_dyn(30.0), q=q_of(tp, 90.0, 0.0)).total == pytest.approx(3.0, rel=1e-12)


def test_no_q_ignores_rotary():
    """Arayüz eki: q = None → döner hareket yok sayılır (rot_v verilmiş olsa da)."""
    tp = one_move(Move(G0, (1.0, 0.0, 0.0)))
    assert toolpath_time(tp, rot_dyn(30.0)).total == pytest.approx(
        scurve_time(1.0, 100.0, 1000.0, None), rel=1e-12
    )


def test_inverse_time_feed():
    """Teori 5: ters zaman (G93): süre 1/F dakika → inv_feed = 2 /dk → 30 s; G0 hızlı kalır."""
    tp = path((0.0, 0.0, 0.0), [Move(G1, (10.0, 0.0, 0.0), feed=600.0), Move(G0, (10.0, 0.0, 20.0))])
    pt = toolpath_time(tp, rot_dyn(30.0), inv_feed=np.array([2.0, 1.0]))
    assert pt.cut == pytest.approx(30.0, rel=1e-12)
    assert pt.rapid == pytest.approx(scurve_time(20.0, 100.0, 1000.0, None), rel=1e-12)


@pytest.mark.parametrize(
    "kw",
    [
        dict(q=np.zeros((3, 4))),  # satır sayısı n + 1 = 2 değil
        dict(q=np.zeros((2, 5))),  # 3 + k, k = len(rot_v) = 1 değil
        dict(inv_feed=np.array([1.0, 2.0, 3.0])),  # uzunluk n = 1 değil
        dict(inv_feed=np.array([0.0])),
    ],
)
def test_rotary_bad_shapes_raise(kw):
    """Arayüz eki: uyumsuz şekil / pozitif olmayan ters zaman → CamError."""
    tp = one_move(Move(G1, (10.0, 0.0, 0.0), feed=600.0))
    with pytest.raises(CamError):
        toolpath_time(tp, rot_dyn(30.0), **kw)
