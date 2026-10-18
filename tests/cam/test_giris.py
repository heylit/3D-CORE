"""SPEC 03c — rampa ve helis giriş testleri (K1–K13).

Testler yalnız SPEC 03c metninden ("Teori", "Arayüz", "Kabul kriterleri") ve onaylı A0 arayüz sözleşmesinden
(`cam/model.py`: `EntryKind`, `EntryMode`, `Tool.ramp_angle_max`) yazıldı; `cam/giris.py` ve `cam/ops2d.py`
uygulama kodu okunmadı. Takım yolu geometrisi (uzaklık, yay süpürmesi, iç/dış) tests/cam/ref2d.py'de
cam.geom2d'den bağımsız hesaplanır.

Kapalı formlar (SPEC 03c "Teori"):
- Helis: n = max(1, ⌈Δz / (2π R_h tan α) − 1e-9⌉) tam tur + z'de bir düz daire;
  boy n·√((2π R_h)² + (Δz/n)²) + 2π R_h.
- Zigzag: H = Δz / tan α, m = max(1, ⌈H/(2ℓ) − 1e-9⌉) ayak; boy m·√((2ℓ)² + (Δz/m)²) + 2ℓ + ℓ.
- Kontur rampası: σ ∈ [0, H] yay boyu, z(σ) = z₀ − σ tan α; boy √(H² + Δz²) (+ P düz halka).
- Açık profil: m = max(1, ⌈H/(2P) − 1e-9⌉) gidiş-dönüş, her tur Δz/m iner.
- Çekirdek kalmaz: R_h ≤ r iken B(c, R_h + r)'deki her nokta R_h yarıçaplı daireye ≤ r.
Sayılar elle (Python math) hesaplandı ve SPEC'teki değerlerle karşılaştırıldı:
141,43531527117…, 150,06664815842…, 174,638…°, 140,1426325903…, 291,538…°, 170,6770700448….
"""

from __future__ import annotations

import functools
import math
import re
from dataclasses import dataclass
from enum import StrEnum

import numpy as np
import pytest

from cam.gcode import GRBL, read, write
from cam.giris import (
    deepest_point,
    helix_moves,
    loop_ramp_moves,
    ramp_direction,
    resolve,
    segment_inside,
    zigzag_moves,
)
from cam.model import CamError, Move, MoveType, Stock, Tool, ToolKind, Toolpath
from cam.ops2d import Cut, contour, depths, face, pocket
from cam.profile import Arc, Line, Profile, Region
from cam.sim.simulate import simulate
from cam.sim.zmap import ZMap
from tests.cam.ref2d import (
    RefBolge,
    curves_of,
    cut_depths,
    cutting_moves,
    grid,
    moves_of,
    sample_xy,
)

# A0 arayüzü (cam/model.py: EntryKind, EntryMode, Tool.ramp_angle_max) henüz birleşmediyse: aynı sözleşmeyle
# yer tutucular tanımlanır ve A0'a bağlı testler (@a0) gövdeleri çalışmadan NotImplementedError ile düşer.
# Böylece yerelde "uygulanmamış", CI'da (--uygulanmamis-hata) kırmızıdır; hiçbiri atlanmaz. A0 gelince bu
# ara katman kendiliğinden devreden çıkar.
try:
    from cam.model import EntryKind, EntryMode

    A0 = "ramp_angle_max" in Tool.__dataclass_fields__
except ImportError:
    A0 = False

    class EntryKind(StrEnum):
        PLUNGE = "dalma"
        RAMP = "rampa"
        HELIX = "helis"

    @dataclass
    class EntryMode:
        kind: EntryKind = EntryKind.PLUNGE
        angle: float = 2.0
        radius: float | None = None
        length: float | None = None


def a0(test):
    """A0 arayüzü yoksa testi NotImplementedError ile düşürür (gövde çalışmaz)."""

    @functools.wraps(test)
    def wrapper(*args, **kwargs):
        if not A0:
            raise NotImplementedError("A0 arayüzü (EntryKind, EntryMode, Tool.ramp_angle_max) yok")
        return test(*args, **kwargs)

    return wrapper


G0, G1, G2, G3 = MoveType.RAPID, MoveType.LINEAR, MoveType.ARC_CW, MoveType.ARC_CCW
ARCS = (G2, G3)
TOL = 1e-9  # mm (SPEC 03c "Kabul kriterleri")
REL = 1e-12  # boylarda göreli
KEEP_TOL = 1e-7  # mm (SPEC 03c "Çapa noktası"; cam/offset.py budama toleransı)
RAMP_FEED = 300.0
FEED = 800.0


def freze(D: float = 10.0, center: bool = True, ramp_max: float | None = None) -> Tool:
    """Uydurma düz parmak freze."""
    kw = dict(ramp_angle_max=ramp_max) if A0 else {}  # A0 yoksa @a0 testleri bu takımı kullanmadan düşer
    return Tool(
        id=1, name=f"freze{D:g}", kind=ToolKind.FLAT, D=D, flute_length=30.0, center_cutting=center, **kw
    )


def yol(start, moves: list[Move], D: float = 10.0) -> Toolpath:
    """Hareketleri doğrulanabilir bir Toolpath'e sarar (takım: merkezden kesen, ramp_angle_max yok)."""
    tool = Tool(id=1, name="f", kind=ToolKind.FLAT, D=D, flute_length=30.0)
    return Toolpath("giris", tool, tuple(float(v) for v in start), list(moves), rpm=10_000.0)


def xy_len(p) -> float:
    """Hareketin yatay boyu s_xy (yayda ρ·|Δθ|)."""
    return p.length_xy()


def numbers_in(msg: str) -> list[float]:
    """Mesajdaki ondalık sayılar (virgül veya nokta)."""
    return [float(s.replace(",", ".")) for s in re.findall(r"\d+(?:[.,]\d+)?", msg)]


def mentions(msg: str, value: float, tol: float = 1e-3) -> bool:
    return any(abs(v - value) <= tol for v in numbers_in(msg))


# ================================================================ K2: helix_moves kapalı form


C_H = (10.0, 5.0)
U_H = (0.0, 1.0)
H_PT = (10.0, 7.5)  # h = c + R_h·u, R_h = 2,5


def helix_case(climb: bool = True, dz: float = 4.0, alpha: float = 2.0, R_h: float = 2.5, u=U_H, c=C_H):
    z0, z = 1.0, 1.0 - dz
    moves = helix_moves(c, R_h, u, z0, z, alpha, climb, RAMP_FEED, FEED)
    h = np.asarray(c) + R_h * np.asarray(u)
    return moves, yol((h[0], h[1], z0), moves), h, z0, z


def test_helix_closed_form_turns_and_length():
    """K2: R_h = 2,5, Δz = 4, α = 2° → n = ⌈4 / (2π·2,5·tan 2°)⌉ = ⌈7,29⌉ = 8 tur + 1 düz daire;
    z adımları 0,5; boy 8·√((5π)² + 0,5²) + 5π = 141,43531527117…"""
    moves, tp, h, z0, z = helix_case()
    tp.validate()
    assert len(moves) == 9
    for k, m in enumerate(moves):
        assert m.type is G3
        assert m.center == pytest.approx(C_H, abs=TOL)
        assert m.end[:2] == pytest.approx(tuple(h), abs=TOL)  # her hareket h'de biter
        z_exp = z0 - 0.5 * (k + 1) if k < 8 else z
        assert m.end[2] == pytest.approx(z_exp, abs=TOL)
    n = 8
    L_exp = n * math.hypot(2 * math.pi * 2.5, 4.0 / n) + 2 * math.pi * 2.5
    assert L_exp == pytest.approx(141.43531527117, abs=1e-10)
    assert tp.length() == pytest.approx(L_exp, rel=REL)


def test_helix_feeds():
    """K2 / "Uygulama kuralı": helis turları ramp_feed, z'deki düz daire feed ile."""
    moves, *_ = helix_case()
    assert [m.feed for m in moves[:-1]] == [RAMP_FEED] * 8
    assert moves[-1].feed == FEED


def test_helix_direction_climb():
    """K2: climb=True → G3 (iç duvarda tırmanma CCW), climb=False → G2."""
    moves, tp, *_ = helix_case(climb=False)
    tp.validate()
    assert all(m.type is G2 for m in moves)
    assert tp.length() == pytest.approx(141.43531527117446, rel=REL)


@pytest.mark.parametrize("k", [1, 3, 5])
def test_helix_exact_multiple_turns(k):
    """K2: Δz = k·2π R_h tan α tam katında n = k (−1e-9 payı; fazladan tur yok)."""
    R_h, alpha = 2.5, 2.0
    dz = k * 2 * math.pi * R_h * math.tan(math.radians(alpha))
    moves, tp, *_ = helix_case(dz=dz)
    tp.validate()
    assert len(moves) == k + 1
    L_exp = k * math.hypot(2 * math.pi * R_h, dz / k) + 2 * math.pi * R_h
    assert tp.length() == pytest.approx(L_exp, rel=REL)


def test_helix_small_depth_one_turn():
    """K2: n = max(1, …): çok küçük Δz'de bile bir tam tur + düz daire."""
    moves, tp, h, z0, z = helix_case(dz=0.01)
    tp.validate()
    assert len(moves) == 2
    assert moves[0].end[2] == pytest.approx(z, abs=TOL)
    assert moves[1].end[2] == pytest.approx(z, abs=TOL)


@pytest.mark.parametrize("dz, alpha", [(4.0, 2.0), (3.0, 5.0), (7.3, 1.0), (0.4, 10.0)])
def test_helix_slope_never_exceeds_alpha(dz, alpha):
    """K2: her helis hareketinde etkin eğim |Δz| / s_xy ≤ tan α; düz daire yatay."""
    moves, tp, *_ = helix_case(dz=dz, alpha=alpha)
    parts = moves_of(tp)
    for p in parts[:-1]:
        drop = p.p0[2] - p.p1[2]
        assert drop > 0
        assert drop / xy_len(p) <= math.tan(math.radians(alpha)) + REL
        assert xy_len(p) == pytest.approx(2 * math.pi * 2.5, rel=REL)  # tam tur
    assert parts[-1].horizontal


def test_helix_start_direction():
    """K2: başlangıç h = c + R_h·û; û = (cos 30°, sin 30°) için de her hareket h'de biter."""
    u = (math.cos(math.pi / 6), math.sin(math.pi / 6))
    moves, tp, h, *_ = helix_case(u=u, c=(-3.0, 4.0), R_h=1.75)
    tp.validate()
    assert h == pytest.approx((-3.0 + 1.75 * u[0], 4.0 + 1.75 * u[1]), abs=TOL)
    for m in moves:
        assert m.end[:2] == pytest.approx(tuple(h), abs=TOL)
        assert m.center == pytest.approx((-3.0, 4.0), abs=TOL)


@pytest.mark.parametrize(
    "R_h, z0, z, alpha",
    [
        (0.0, 1.0, -3.0, 2.0),  # R_h ≤ 0
        (-1.0, 1.0, -3.0, 2.0),
        (2.5, -3.0, -3.0, 2.0),  # z0 ≤ z
        (2.5, -4.0, -3.0, 2.0),
        (2.5, 1.0, -3.0, 0.0),  # α ∉ (0, 90)
        (2.5, 1.0, -3.0, 90.0),
        (2.5, 1.0, -3.0, -2.0),
        (2.5, 1.0, -3.0, float("nan")),
    ],
)
def test_helix_bad_input_raises(R_h, z0, z, alpha):
    """K2 / Arayüz: R_h ≤ 0, z0 ≤ z, α ∉ (0, 90) → CamError."""
    with pytest.raises(CamError):
        helix_moves(C_H, R_h, U_H, z0, z, alpha, True, RAMP_FEED, FEED)


# ================================================================ K3: helis deliği (sütun kalmaz)


@pytest.mark.parametrize("frac", [0.5, 1.0])
def test_helix_no_core_column_analytic(frac):
    """K3: R_h ∈ {0,5r, r}: B(c, R_h + r) içindeki örnek noktalar (merkez dahil) z'deki düz daireye
    ≤ r + 1e-9 (sütun kalmaz)."""
    r = 5.0
    R_h = frac * r
    moves, tp, *_ = helix_case(R_h=R_h, c=(0.0, 0.0), u=(1.0, 0.0))
    flat = moves_of(tp)[-1]
    assert flat.horizontal
    P = grid(-(R_h + r), R_h + r, -(R_h + r), R_h + r, 61, 61)
    P = P[np.hypot(P[:, 0], P[:, 1]) <= R_h + r]
    P = np.vstack([P, [[0.0, 0.0]]])
    d = curves_of([flat]).distance(P)
    assert np.max(d) <= r + 1e-9


@pytest.mark.parametrize("frac", [0.5, 1.0])
def test_helix_hole_simulated(frac):
    """K3: SPEC 05 simulate ile kutu stokta (üst z = 0) helis yolu (z0 = 1 → z = −3, D = 10):
    B(c, R_h + r − cell) hücreleri z'de, B(c, R_h + r + cell) dışı değişmemiş, çakma olayı yok."""
    D, r, cell = 10.0, 5.0, 0.25
    R_h = frac * r
    c = (0.0, 0.0)
    z0, z = 1.0, -3.0
    moves = helix_moves(c, R_h, (1.0, 0.0), z0, z, 2.0, True, RAMP_FEED, FEED)
    h = (R_h, 0.0)
    tp = Toolpath(
        "helis",
        Tool(id=1, name="f10", kind=ToolKind.FLAT, D=D, flute_length=30.0),
        (h[0], h[1], 10.0),
        [Move(G0, (h[0], h[1], z0)), *moves, Move(G0, (h[0], h[1], 10.0))],
        rpm=10_000.0,
    )
    tp.validate()
    stock = Stock(xmin=-16.0, ymin=-16.0, zmin=-10.0, xmax=16.0, ymax=16.0, zmax=0.0)
    g = ZMap.from_stock(stock, cell)
    X, Y = g.centers()
    rho = np.hypot(X - c[0], Y - c[1])
    part_z = np.where(rho < R_h + r, z, 0.0)
    res = simulate([tp], stock, cell=cell, part_z=part_z)
    assert [c for c in res.collisions if c.kind == "cakma"] == []
    zf = res.zmap.z
    inside = rho <= R_h + r - cell
    outside = rho >= R_h + r + cell
    assert inside.any() and outside.any()
    np.testing.assert_allclose(zf[inside], z, atol=1e-6)
    np.testing.assert_allclose(zf[outside], 0.0, atol=0)


# ================================================================ K4: zigzag_moves kapalı form


def zigzag_case(dz: float = 4.0, ell: float = 10.0, c=(30.0, 20.0), u=(1.0, 0.0), alpha: float = 2.0):
    z0, z = 1.0, 1.0 - dz
    moves = zigzag_moves(c, u, ell, z0, z, alpha, RAMP_FEED, FEED)
    A = np.asarray(c) - ell * np.asarray(u)
    B = np.asarray(c) + ell * np.asarray(u)
    return moves, yol((A[0], A[1], z0), moves), A, B, z0, z


def test_zigzag_closed_form_even():
    """K4: ℓ = 10, Δz = 4, α = 2° → H = 114,55, m = ⌈H/20⌉ = 6 ayak (A→B→A…, her biri Δz/6);
    m çift → bitiş ucu E = A; z'de A → B düz geçiş, sonra c.
    Boy 6·√(20² + (4/6)²) + 20 + 10 = 150,06664815842…"""
    moves, tp, A, B, z0, z = zigzag_case()
    tp.validate()
    assert len(moves) == 6 + 2
    for k in range(6):
        m = moves[k]
        assert m.type is G1
        end = B if k % 2 == 0 else A
        assert m.end[:2] == pytest.approx(tuple(end), abs=TOL)
        assert m.end[2] == pytest.approx(z0 - 4.0 * (k + 1) / 6, abs=TOL)
        assert m.feed == RAMP_FEED
    flat, back = moves[6], moves[7]
    assert flat.type is G1 and back.type is G1
    assert flat.end == pytest.approx((B[0], B[1], z), abs=TOL)
    assert back.end == pytest.approx((30.0, 20.0, z), abs=TOL)
    assert flat.feed == FEED and back.feed == FEED
    L_exp = 6 * math.hypot(20.0, 4.0 / 6) + 20.0 + 10.0
    assert L_exp == pytest.approx(150.06664815842, abs=1e-10)
    assert tp.length() == pytest.approx(L_exp, rel=REL)


def test_zigzag_closed_form_odd():
    """K4: Δz = 3 → H = 85,91, m = ⌈4,30⌉ = 5 (tek) → E = B; z'de B → A, sonra c."""
    moves, tp, A, B, z0, z = zigzag_case(dz=3.0)
    tp.validate()
    H = 3.0 / math.tan(math.radians(2.0))
    m = math.ceil(H / 20.0)
    assert m == 5
    assert len(moves) == m + 2
    assert moves[m - 1].end == pytest.approx((B[0], B[1], z), abs=TOL)
    assert moves[m].end == pytest.approx((A[0], A[1], z), abs=TOL)
    assert moves[m + 1].end == pytest.approx((30.0, 20.0, z), abs=TOL)
    L_exp = m * math.hypot(20.0, 3.0 / m) + 20.0 + 10.0
    assert tp.length() == pytest.approx(L_exp, rel=REL)


@pytest.mark.parametrize("k", [1, 2, 4])
def test_zigzag_exact_multiple(k):
    """K4: H = k·2ℓ tam katında m = k."""
    ell, alpha = 7.0, 3.0
    dz = k * 2 * ell * math.tan(math.radians(alpha))
    moves, tp, *_ = zigzag_case(dz=dz, ell=ell, alpha=alpha)
    tp.validate()
    assert len(moves) == k + 2


def test_zigzag_slope_and_direction():
    """K4: 45° yönünde de ayaklar S = [A, B] üzerinde; eğim ≤ tan α; düz geçiş ve c'ye dönüş yatay."""
    u = (math.sqrt(0.5), math.sqrt(0.5))
    moves, tp, A, B, z0, z = zigzag_case(dz=2.5, ell=4.0, c=(-1.0, 2.0), u=u, alpha=3.0)
    tp.validate()
    parts = moves_of(tp)
    t = math.tan(math.radians(3.0))
    for p in parts:
        for q in (p.p0[:2], p.p1[:2]):  # tüm uçlar S doğru parçası üzerinde
            w = q - A
            assert abs(u[0] * w[1] - u[1] * w[0]) <= TOL
        if p.p1[2] < p.p0[2] - 1e-12:
            assert (p.p0[2] - p.p1[2]) / xy_len(p) <= t + REL
    assert parts[-1].horizontal and parts[-2].horizontal
    assert parts[-1].p1[:2] == pytest.approx((-1.0, 2.0), abs=TOL)


# ================================================================ K5: ramp_direction


def ray_dist_poly(c, u, pts) -> float:
    """c'den u yönündeki ışının çokgen kenarlarını ilk kestiği noktaya uzaklık (bağımsız hesap)."""
    c = np.asarray(c, dtype=float)
    u = np.asarray(u, dtype=float)
    best = math.inf
    V = np.asarray(pts, dtype=float)
    for i in range(len(V)):
        a, b = V[i], V[(i + 1) % len(V)]
        e = b - a
        den = u[0] * (-e[1]) - u[1] * (-e[0])
        if abs(den) < 1e-15:
            continue
        w = a - c
        t = (w[0] * (-e[1]) - w[1] * (-e[0])) / den
        s = (u[0] * w[1] - u[1] * w[0]) / den
        if t > 1e-12 and -1e-12 <= s <= 1 + 1e-12:
            best = min(best, t)
    return best


def u_k(k: int) -> np.ndarray:
    return np.array([math.cos(k * math.pi / 12), math.sin(k * math.pi / 12)])


def assert_segment_in(ref: RefBolge, c, u, ell) -> None:
    """[A, B] ⊆ R₀: parçadaki örnek noktalar bölgede (sınır dahil)."""
    c, u = np.asarray(c), np.asarray(u)
    t = np.linspace(-1.0, 1.0, 401)
    P = c[None, :] + (ell * t)[:, None] * u[None, :]
    on = ref.boundary().distance(P) <= 1e-9
    assert np.all(ref.contains(P) | on)


@pytest.mark.parametrize("L, ell_exp", [(20.0, 10.0), (100.0, 30.0)])
def test_ramp_direction_rectangle(L, ell_exp):
    """K5: a × b = 60 × 12 dikdörtgen merkezinde k = 0 (u = (1, 0)), ℓ = min(L/2, a/2).

    Not: k = 0'ın en büyük ℓ_fit'i vermesi b/a ≤ sin 15° ister (k = 1'de ℓ_fit = min(b/(2 sin 15°),
    a/(2 cos 15°)) > a/2 olmasın diye); 60 × 40'ta k = 2 kazanır (ℓ_fit = 30/cos 30° = 34,64 > 30).
    Bu yüzden dar dikdörtgen (b/a = 0,2) kullanıldı; ayrıca 60 × 40 durumu aşağıda sınanır."""
    pts = [(0.0, 0.0), (60.0, 0.0), (60.0, 12.0), (0.0, 12.0)]
    u, ell = ramp_direction((30.0, 6.0), Region(Profile.polygon(pts)), L)
    assert np.asarray(u) == pytest.approx((1.0, 0.0), abs=1e-12)
    assert ell == pytest.approx(ell_exp, abs=TOL)
    assert_segment_in(RefBolge(("poly", pts)), (30.0, 6.0), u, ell)


def test_ramp_direction_wide_rectangle_diagonal_wins():
    """K5 (Teori "en büyük ℓ_fit"): 60 × 40 merkezinde ℓ_fit(k) = min(20/|sin θ|, 30/|cos θ|) en büyük
    k = 2'de (30° , 30/cos 30° = 34,641…)."""
    pts = [(0.0, 0.0), (60.0, 0.0), (60.0, 40.0), (0.0, 40.0)]
    u, ell = ramp_direction((30.0, 20.0), Region(Profile.polygon(pts)), 100.0)
    assert np.asarray(u) == pytest.approx(tuple(u_k(2)), abs=1e-12)
    assert ell == pytest.approx(30.0 / math.cos(math.pi / 6), abs=1e-9)
    assert_segment_in(RefBolge(("poly", pts)), (30.0, 20.0), u, ell)


def rotated_channel(c, length: float, width: float, deg: float) -> list[tuple[float, float]]:
    th = math.radians(deg)
    ex = np.array([math.cos(th), math.sin(th)])
    ey = np.array([-math.sin(th), math.cos(th)])
    c = np.asarray(c)
    out = []
    for sx, sy in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
        p = c + sx * length / 2 * ex + sy * width / 2 * ey
        out.append((float(p[0]), float(p[1])))
    return out


def test_ramp_direction_rotated_channel():
    """K5: 30° döndürülmüş 40 × 4 kanal merkezinde k = 2 (u = (cos 30°, sin 30°)), ℓ_fit = 20."""
    pts = rotated_channel((5.0, 3.0), 40.0, 4.0, 30.0)
    u, ell = ramp_direction((5.0, 3.0), Region(Profile.polygon(pts)), 100.0)
    assert np.asarray(u) == pytest.approx(tuple(u_k(2)), abs=1e-12)
    assert ell == pytest.approx(20.0, abs=1e-9)
    assert_segment_in(RefBolge(("poly", pts)), (5.0, 3.0), u, ell)


@pytest.mark.parametrize("L, ell_exp", [(10.0, 5.0), (100.0, 12.0)])
def test_ramp_direction_circle(L, ell_exp):
    """K5: ρ = 12 daire merkezinde tüm yönler eşit → en küçük k = 0; ℓ = min(L/2, ρ)."""
    c = (3.0, -2.0)
    u, ell = ramp_direction(c, Region(Profile.circle(c, 12.0)), L)
    assert np.asarray(u) == pytest.approx((1.0, 0.0), abs=1e-12)
    assert ell == pytest.approx(ell_exp, abs=1e-9)
    assert_segment_in(RefBolge(("circle", c, 12.0)), c, u, ell)


L_PTS = [(0.0, 0.0), (50.0, 0.0), (50.0, 20.0), (20.0, 20.0), (20.0, 45.0), (0.0, 45.0)]
# Eksene paralel olmayan içbükey çokgen (içbükey köşe (19, 17)): eksene paralel kenarlı bölgede simetrik
# yön çiftleri aynı kenara çarpıp ℓ_fit eşitliği verir; burada en büyük ℓ_fit tekil.
SKEW_PTS = [(0.0, 0.0), (47.0, 3.0), (41.0, 22.0), (19.0, 17.0), (14.0, 38.0), (-3.0, 29.0)]


@pytest.mark.parametrize("c", [(8.0, 13.0), (30.0, 10.0), (5.0, 25.0), (12.0, 6.0), (38.0, 12.0)])
def test_ramp_direction_skew_region_matches_max_fit(c):
    """K5: içbükey çokgende seçilen yön, 12 aday içinde ℓ_fit(u) = min(ray(c, u), ray(c, −u)) en büyük olan
    (bağımsız ışın–kenar kesişimiyle); ℓ = min(L/2, ℓ_fit); [A, B] ⊆ R₀."""
    fits = [min(ray_dist_poly(c, u_k(k), SKEW_PTS), ray_dist_poly(c, -u_k(k), SKEW_PTS)) for k in range(12)]
    k_best = int(np.argmax(fits))
    others = [f for k, f in enumerate(fits) if k != k_best]
    assert fits[k_best] - max(others) > 0.1  # öz denetim: eşitlik yok
    region = Region(Profile.polygon(SKEW_PTS))
    u, ell = ramp_direction(c, region, 1000.0)
    assert np.asarray(u) == pytest.approx(tuple(u_k(k_best)), abs=1e-12)
    assert ell == pytest.approx(fits[k_best], abs=1e-9)
    u2, ell2 = ramp_direction(c, region, 4.0)
    assert np.asarray(u2) == pytest.approx(tuple(u_k(k_best)), abs=1e-12)
    assert ell2 == pytest.approx(min(2.0, fits[k_best]), abs=1e-9)
    assert_segment_in(RefBolge(("poly", SKEW_PTS)), c, u, ell)


# ================================================================ K6: loop_ramp_moves kapalı halka


def ring_ok(ring, closed: bool = True) -> None:
    """Halka uç uca bağlı (kapalıysa son bitiş = ilk başlangıç)."""
    for a, b in zip(ring, ring[1:], strict=False):
        assert np.allclose(a.p1, b.p0, atol=1e-7)
    if closed:
        assert np.allclose(ring[-1].p1, ring[0].p0, atol=1e-7)


def circle_ramp(alpha: float, dz: float = 4.0, ccw: bool = True):
    segs = Profile.circle((0.0, 0.0), 15.0, ccw=ccw).segments
    z0, z = 1.0, 1.0 - dz
    moves, ring = loop_ramp_moves(segs, True, z0, z, alpha, RAMP_FEED)
    return moves, ring, yol((15.0, 0.0, z0), moves), z0, z


@pytest.mark.parametrize(
    "alpha, deg_exp, total_exp",
    [(5.0, 174.638335083, 140.1426325903), (3.0, 291.538293471, 170.6770700448)],
)
def test_loop_ramp_circle_single_arc(alpha, deg_exp, total_exp):
    """K6: ρ = 15 daire, Δz = 4: H = Δz/tan α < P = 30π → tek helis yayı, bitiş açısı H/ρ,
    boy √(H² + Δz²); halka e'den başlayan tam daire, toplam √(H² + Δz²) + 2πρ."""
    moves, ring, tp, z0, z = circle_ramp(alpha)
    tp.validate()
    H = 4.0 / math.tan(math.radians(alpha))
    assert len(moves) == 1
    m = moves[0]
    assert m.type is G3
    assert m.center == pytest.approx((0.0, 0.0), abs=TOL)
    assert m.feed == RAMP_FEED
    ang = math.degrees(math.atan2(m.end[1], m.end[0])) % 360.0
    assert ang == pytest.approx(math.degrees(H / 15.0), abs=1e-9)
    assert ang == pytest.approx(deg_exp, abs=1e-6)
    assert m.end[2] == pytest.approx(z, abs=TOL)
    assert tp.length() == pytest.approx(math.hypot(H, 4.0), rel=REL)
    ring_ok(ring)
    assert np.allclose(ring[0].p0, m.end[:2], atol=1e-9)
    P = sum(s.length for s in ring)
    assert P == pytest.approx(2 * math.pi * 15.0, rel=REL)
    assert tp.length() + P == pytest.approx(total_exp, abs=1e-9)


def test_loop_ramp_circle_cw_is_g2():
    """K6: CW halkada rampa yayı G2."""
    moves, ring, tp, *_ = circle_ramp(5.0, ccw=False)
    tp.validate()
    assert [m.type for m in moves] == [G2]
    ang = math.degrees(math.atan2(moves[0].end[1], moves[0].end[0])) % 360.0
    assert ang == pytest.approx(360.0 - math.degrees(4.0 / math.tan(math.radians(5.0)) / 15.0), abs=1e-9)


def test_loop_ramp_circle_multiple_turns():
    """K6: α = 1° → H = 229,16 > P = 94,25: ⌊H/P⌋ = 2 tam tur (her biri P tan α iner) + kalan yay
    (H mod P)/ρ = 155,326…°; rampa boyu √(H² + Δz²)."""
    moves, ring, tp, z0, z = circle_ramp(1.0)
    tp.validate()
    t = math.tan(math.radians(1.0))
    H = 4.0 / t
    P = 2 * math.pi * 15.0
    assert math.floor(H / P) == 2
    assert len(moves) == 3
    for k in range(2):
        assert moves[k].type is G3
        assert moves[k].end[:2] == pytest.approx((15.0, 0.0), abs=1e-9)
        assert moves[k].end[2] == pytest.approx(z0 - (k + 1) * P * t, abs=1e-9)
    ang = math.degrees(math.atan2(moves[2].end[1], moves[2].end[0])) % 360.0
    assert ang == pytest.approx(math.degrees((H % P) / 15.0), abs=1e-9)
    assert ang == pytest.approx(155.326135976, abs=1e-6)
    assert moves[2].end[2] == pytest.approx(z, abs=TOL)
    assert tp.length() == pytest.approx(math.hypot(H, 4.0), rel=REL)
    ring_ok(ring)
    assert np.allclose(ring[0].p0, moves[2].end[:2], atol=1e-9)


RECT_SEGS = Profile.rectangle(0.0, 0.0, 40.0, 20.0).segments  # (0,0) → (40,0) → (40,20) → (0,20), CCW


def test_loop_ramp_rectangle_corners_and_split():
    """K6: 40 × 20 halka, Δz = 4, α = 3° → H = 76,32: köşelerde z = z₀ − σ_i tan α (σ = 40, 60),
    e = (40 − (H − 60), 20)'de bölünme; ikinci değer e'den başlayan tam halka (5 parça, çevre 120)."""
    alpha = 3.0
    t = math.tan(math.radians(alpha))
    z0, z = 1.0, -3.0
    H = 4.0 / t
    moves, ring = loop_ramp_moves(RECT_SEGS, True, z0, z, alpha, RAMP_FEED)
    tp = yol((0.0, 0.0, z0), moves)
    tp.validate()
    e = (40.0 - (H - 60.0), 20.0)
    assert [m.type for m in moves] == [G1, G1, G1]
    assert moves[0].end == pytest.approx((40.0, 0.0, z0 - 40.0 * t), abs=TOL)
    assert moves[1].end == pytest.approx((40.0, 20.0, z0 - 60.0 * t), abs=TOL)
    assert moves[2].end == pytest.approx((e[0], e[1], z), abs=TOL)
    assert all(m.feed == RAMP_FEED for m in moves)
    for p in moves_of(tp):  # eğim tam α
        assert (p.p0[2] - p.p1[2]) / xy_len(p) == pytest.approx(t, rel=1e-12)
    assert tp.length() == pytest.approx(math.hypot(H, 4.0), rel=REL)
    ring_ok(ring)
    starts = [tuple(s.p0) for s in ring]
    exp = [e, (0.0, 20.0), (0.0, 0.0), (40.0, 0.0), (40.0, 20.0)]
    assert len(ring) == 5
    for a, b in zip(starts, exp, strict=True):
        assert a == pytest.approx(b, abs=1e-9)
    assert sum(s.length for s in ring) == pytest.approx(120.0, rel=REL)


def test_loop_ramp_end_snaps_to_corner():
    """K6: e bir köşeye ≤ LINK_TOL yakınsa köşeye oturtulur: H = 60 (Δz = 60 tan α) → iki hareket,
    halka (40, 20)'den başlayan 4 parça (sıfıra yakın boylu parça yok)."""
    alpha = 3.0
    t = math.tan(math.radians(alpha))
    z0 = 1.0
    z = z0 - 60.0 * t
    moves, ring = loop_ramp_moves(RECT_SEGS, True, z0, z, alpha, RAMP_FEED)
    yol((0.0, 0.0, z0), moves).validate()
    assert len(moves) == 2
    assert moves[-1].end == pytest.approx((40.0, 20.0, z), abs=1e-9)
    assert len(ring) == 4
    ring_ok(ring)
    assert np.allclose(ring[0].p0, (40.0, 20.0), atol=1e-9)
    assert min(s.length for s in ring) == pytest.approx(20.0, abs=1e-9)


def test_loop_ramp_arc_segment_split():
    """K6: yay içeren halkada (stadyum) e yayın ortasında: doğru G1, yay parçası aynı merkezli G3 helis;
    z yay boyuna doğrusal; halka e = (25, 5)'ten başlar, çevre 40 + 10π."""
    segs = [
        Line((0.0, 0.0), (20.0, 0.0)),
        Arc((20.0, 0.0), (20.0, 10.0), (20.0, 5.0), True),
        Line((20.0, 10.0), (0.0, 10.0)),
        Arc((0.0, 10.0), (0.0, 0.0), (0.0, 5.0), True),
    ]
    alpha = 3.0
    t = math.tan(math.radians(alpha))
    H = 20.0 + 2.5 * math.pi  # ilk yayın yarısı
    z0 = 1.0
    z = z0 - H * t
    moves, ring = loop_ramp_moves(segs, True, z0, z, alpha, RAMP_FEED)
    tp = yol((0.0, 0.0, z0), moves)
    tp.validate()
    assert [m.type for m in moves] == [G1, G3]
    assert moves[0].end == pytest.approx((20.0, 0.0, z0 - 20.0 * t), abs=TOL)
    assert moves[1].center == pytest.approx((20.0, 5.0), abs=TOL)
    assert moves[1].end == pytest.approx((25.0, 5.0, z), abs=1e-9)
    for p in moves_of(tp):
        assert (p.p0[2] - p.p1[2]) / xy_len(p) == pytest.approx(t, rel=1e-12)
    ring_ok(ring)
    assert np.allclose(ring[0].p0, (25.0, 5.0), atol=1e-9)
    assert isinstance(ring[0], Arc) and isinstance(ring[-1], Arc)
    assert sum(s.length for s in ring) == pytest.approx(40.0 + 10.0 * math.pi, rel=REL)


# ================================================================ K7: açık profil


def test_loop_ramp_open_line_round_trips():
    """K7: P = 30 boylu doğru, Δz = 4, α = 2° → H = 114,55, m = ⌈H/60⌉ = 2 gidiş-dönüş; her tur p₀'da
    Δz/m daha aşağıda biter, son tur p₀'da z'de; ikinci değer segs (p₀ → p₁ kesimi için)."""
    segs = [Line((0.0, 0.0), (30.0, 0.0))]
    z0, z = 1.0, -3.0
    alpha = 2.0
    moves, ring = loop_ramp_moves(segs, False, z0, z, alpha, RAMP_FEED)
    tp = yol((0.0, 0.0, z0), moves)
    tp.validate()
    H = 4.0 / math.tan(math.radians(alpha))
    m = math.ceil(H / 60.0)
    assert m == 2
    assert len(moves) == 2 * m
    for k in range(m):
        out, back = moves[2 * k], moves[2 * k + 1]
        assert out.end[:2] == pytest.approx((30.0, 0.0), abs=TOL)
        assert back.end[:2] == pytest.approx((0.0, 0.0), abs=TOL)
        assert back.end[2] == pytest.approx(z0 - (k + 1) * 4.0 / m, abs=TOL)
        assert z0 - k * 4.0 / m > out.end[2] > back.end[2]
    assert moves[-1].end == pytest.approx((0.0, 0.0, z), abs=TOL)
    t = math.tan(math.radians(alpha))
    for p in moves_of(tp):
        assert p.p1[2] < p.p0[2]
        assert (p.p0[2] - p.p1[2]) / xy_len(p) <= t + REL
    assert all(mv.feed == RAMP_FEED for mv in moves)
    assert len(ring) == 1
    assert np.allclose(ring[0].p0, (0.0, 0.0)) and np.allclose(ring[0].p1, (30.0, 0.0))


def test_loop_ramp_open_polyline_one_trip():
    """K7: (0,0) → (20,0) → (20,10), P = 30, Δz = 1, α = 2° → H = 28,6 ≤ 2P → m = 1:
    p₀ → p₁ → p₀ köşelerden geçer, p₀'da z'de biter."""
    segs = Profile.polygon([(0.0, 0.0), (20.0, 0.0), (20.0, 10.0)], closed=False).segments
    z0, z = 1.0, 0.0
    moves, ring = loop_ramp_moves(segs, False, z0, z, 2.0, RAMP_FEED)
    yol((0.0, 0.0, z0), moves).validate()
    ends = [m.end[:2] for m in moves]
    exp = [(20.0, 0.0), (20.0, 10.0), (20.0, 0.0), (0.0, 0.0)]
    assert len(ends) == 4
    for a, b in zip(ends, exp, strict=True):
        assert a == pytest.approx(b, abs=TOL)
    assert moves[-1].end[2] == pytest.approx(z, abs=TOL)
    assert len(ring) == 2


@pytest.mark.parametrize("k", [1, 3])
def test_loop_ramp_open_exact_multiple(k):
    """K7: H = k·2P tam katında m = k."""
    segs = [Line((0.0, 0.0), (10.0, 0.0))]
    alpha = 4.0
    dz = k * 20.0 * math.tan(math.radians(alpha))
    moves, _ = loop_ramp_moves(segs, False, 1.0, 1.0 - dz, alpha, RAMP_FEED)
    assert len(moves) == 2 * k


# ================================================================ K8: deepest_point, segment_inside


@pytest.mark.parametrize("a, b", [(60.0, 40.0), (12.0, 30.0)])
def test_deepest_point_rectangle(a, b):
    """K8: a × b dikdörtgende lo → min(a, b)/2 (1e-6·D, D = 10); dist(c, ∂N) ≥ lo − KEEP_TOL."""
    pts = [(0.0, 0.0), (a, 0.0), (a, b), (0.0, b)]
    c, lo = deepest_point(Region(Profile.polygon(pts)))
    assert lo == pytest.approx(min(a, b) / 2, abs=1e-5)
    ref = RefBolge(("poly", pts))
    c = np.asarray(c, dtype=float)
    assert ref.contains(c[None, :])[0]
    assert ref.boundary().distance(c[None, :])[0] >= lo - KEEP_TOL


def test_deepest_point_circle():
    """K8: ρ = 12 dairede lo → ρ; c merkeze ≤ 1e-4 (dist(c, ∂N) = ρ − |c − merkez| ≥ lo − KEEP_TOL)."""
    c, lo = deepest_point(Region(Profile.circle((5.0, -7.0), 12.0)))
    assert lo == pytest.approx(12.0, abs=1e-5)
    ref = RefBolge(("circle", (5.0, -7.0), 12.0))
    c = np.asarray(c, dtype=float)
    assert ref.boundary().distance(c[None, :])[0] >= lo - KEEP_TOL
    assert math.dist(c, (5.0, -7.0)) <= 1e-4


def test_deepest_point_island_region_brute_force():
    """K8: adalı bölgede (60 × 40, (30, 20)'de R = 6 ada) lo, ızgarada kaba kuvvetle bulunan en büyük
    iç uzaklıkla 0,05 içinde aynı; dist(c, ∂N) ≥ lo − KEEP_TOL ve c adanın dışında."""
    ref = RefBolge(
        ("poly", [(0.0, 0.0), (60.0, 0.0), (60.0, 40.0), (0.0, 40.0)]), [("circle", (30.0, 20.0), 6.0)]
    )
    region = Region(Profile.rectangle(0.0, 0.0, 60.0, 40.0), [Profile.circle((30.0, 20.0), 6.0)])
    c, lo = deepest_point(region)
    P = grid(0.0, 60.0, 0.0, 40.0, 1201, 801)
    P = P[ref.contains(P)]
    best = float(np.max(ref.boundary().distance(P)))
    assert abs(lo - best) <= 0.05
    c = np.asarray(c, dtype=float)
    assert ref.contains(c[None, :])[0]
    assert ref.boundary().distance(c[None, :])[0] >= lo - KEEP_TOL


L_REGION = Region(Profile.polygon(L_PTS))


@pytest.mark.parametrize(
    "p, q, exp",
    [
        ((10.0, 35.0), (35.0, 10.0), False),  # içbükey köşeden (20, 20) dışarı taşar
        ((5.0, 5.0), (15.0, 40.0), True),  # tamamen içte
        ((10.0, 10.0), (45.0, 15.0), True),
        ((10.0, 10.0), (50.0, 10.0), True),  # sınıra uçtan değer
        ((0.0, 10.0), (50.0, 10.0), True),  # iki ucu sınırda, gövdesi içte
        ((10.0, 10.0), (70.0, 10.0), False),  # uç bölge dışında
        ((-5.0, 30.0), (10.0, 30.0), False),
        ((30.0, 10.0), (10.0, 40.0), False),  # (20, 25) civarında dışarıda
    ],
)
def test_segment_inside_l_region(p, q, exp):
    """K8: L bölgede köşeden geçen parça False, içteki True, sınıra uçtan değen True."""
    assert segment_inside(p, q, L_REGION) is exp


@pytest.mark.parametrize(
    "p, q, exp",
    [
        ((5.0, 20.0), (55.0, 20.0), False),  # adanın içinden geçer
        ((5.0, 5.0), (55.0, 5.0), True),
        ((5.0, 30.0), (55.0, 30.0), True),  # adaya 4 uzakta
        ((30.0, 30.0), (30.0, 26.0), True),  # adaya uçtan değer
        ((30.0, 30.0), (30.0, 25.0), False),  # uç adanın içinde
    ],
)
def test_segment_inside_island(p, q, exp):
    """K8: adalı bölgede adayı kesen parça False; ada sınırına uçtan değen True."""
    region = Region(Profile.rectangle(0.0, 0.0, 60.0, 40.0), [Profile.circle((30.0, 20.0), 6.0)])
    assert segment_inside(p, q, region) is exp


# ================================================================ K1: resolve ve Cut


@a0
def test_resolve_defaults():
    """K1: None → PLUNGE; HELIX'te R_h = r/2 (HELIX_R_FACTOR = 0,5), RAMP'ta L = 2D (RAMP_L_FACTOR = 2)."""
    tool = freze(10.0)
    e = resolve(tool, None, "cep")
    assert e.kind is EntryKind.PLUNGE
    h = resolve(tool, EntryMode(kind=EntryKind.HELIX), "cep")
    assert h.kind is EntryKind.HELIX
    assert h.radius == pytest.approx(2.5, abs=1e-12)
    assert h.angle == pytest.approx(2.0)
    z = resolve(tool, EntryMode(kind=EntryKind.RAMP), "cep")
    assert z.length == pytest.approx(20.0, abs=1e-12)
    zk = resolve(tool, EntryMode(kind=EntryKind.RAMP), "kontur")
    assert zk.kind is EntryKind.RAMP


@a0
def test_resolve_keeps_given_values():
    """K1: verilen radius / length / angle korunur."""
    tool = freze(10.0)
    h = resolve(tool, EntryMode(kind=EntryKind.HELIX, angle=4.0, radius=4.0), "cep")
    assert h.radius == 4.0 and h.angle == 4.0
    z = resolve(tool, EntryMode(kind=EntryKind.RAMP, length=7.5), "cep")
    assert z.length == 7.5


@a0
def test_resolve_accepts_limits():
    """K1: sınır değerler kabul: angle = ramp_angle_max; merkezden kesmeyende R_h = r/2; R_h = r."""
    nc = freze(10.0, center=False, ramp_max=5.0)
    assert resolve(nc, EntryMode(kind=EntryKind.RAMP, angle=5.0), "cep").angle == 5.0
    assert resolve(nc, EntryMode(kind=EntryKind.HELIX, angle=3.0, radius=2.5), "cep").radius == 2.5
    assert resolve(nc, EntryMode(kind=EntryKind.HELIX, angle=3.0), "cep").radius == pytest.approx(2.5)
    assert resolve(freze(10.0), EntryMode(kind=EntryKind.HELIX, radius=5.0), "cep").radius == 5.0
    # merkezden kesen takımda ramp_angle_max yoksa açı sınırı yok
    assert resolve(freze(10.0), EntryMode(kind=EntryKind.RAMP, angle=45.0), "kontur").angle == 45.0


@pytest.mark.parametrize(
    "tool, entry, op",
    [
        (freze(10.0, center=False, ramp_max=5.0), None, "cep"),  # merkezden kesmeyen + PLUNGE
        (freze(10.0, center=False, ramp_max=5.0), EntryMode(), "kontur"),
        (freze(10.0, center=False), EntryMode(kind=EntryKind.RAMP, angle=1.0), "cep"),  # ramp_angle_max yok
        (freze(10.0, center=False), EntryMode(kind=EntryKind.HELIX, angle=1.0), "cep"),
        (freze(10.0, center=False, ramp_max=5.0), EntryMode(kind=EntryKind.RAMP, angle=5.5), "cep"),
        (freze(10.0, ramp_max=3.0), EntryMode(kind=EntryKind.HELIX, angle=3.1), "cep"),  # merkezden kesen
        (freze(10.0), EntryMode(kind=EntryKind.HELIX, radius=5.01), "cep"),  # R_h > r
        (freze(10.0, center=False, ramp_max=5.0), EntryMode(kind=EntryKind.HELIX, radius=2.45), "cep"),
        (freze(10.0), EntryMode(kind=EntryKind.HELIX), "kontur"),  # helis yalnız cepte
    ],
    ids=[
        "mk_dalma_cep",
        "mk_dalma_kontur",
        "mk_rampa_sinirsiz",
        "mk_helis_sinirsiz",
        "aci_sinir_ustu",
        "aci_sinir_ustu_mk_degil",
        "Rh_r_ustu",
        "mk_Rh_r2_alti",
        "kontur_helis",
    ],
)
@a0
def test_resolve_errors(tool, entry, op):
    """K1 hata tablosu → CamError."""
    with pytest.raises(CamError):
        resolve(tool, entry, op)


def make_cut(**kw) -> Cut:
    """z 0 → −4, a_p 2 (2 paso), z_safe 10, clearance 1."""
    args = dict(z_top=0.0, z_bottom=-4.0, a_p=2.0, feed=FEED, plunge_feed=200.0, rpm=10_000.0, z_safe=10.0)
    args.update(kw)
    return Cut(**args)


@pytest.mark.parametrize("ramp_feed", [0.0, -100.0, float("nan")])
@a0
def test_cut_bad_ramp_feed(ramp_feed):
    """K1: ramp_feed verilirse > 0 (kurulumda veya kullanımda) → CamError."""
    with pytest.raises(CamError):
        cut = make_cut(stepover=5.0, entry=EntryMode(kind=EntryKind.HELIX), ramp_feed=ramp_feed)
        pocket(Region(Profile.rectangle(0.0, 0.0, 60.0, 40.0)), freze(10.0), cut)


@pytest.mark.parametrize("entry", ["helis", EntryKind.HELIX, {"kind": "helis"}, 2.0])
@a0
def test_cut_bad_entry_type(entry):
    """K1: entry EntryMode ya da None değilse → CamError."""
    with pytest.raises(CamError):
        cut = make_cut(stepover=5.0, entry=entry)
        pocket(Region(Profile.rectangle(0.0, 0.0, 60.0, 40.0)), freze(10.0), cut)


# ================================================================ K9: pocket + HELIX / RAMP


RECT = ("poly", [(0.0, 0.0), (60.0, 0.0), (60.0, 40.0), (0.0, 40.0)])
L_SHAPE = ("poly", L_PTS)
ISLAND = ("circle", (30.0, 20.0), 6.0)
K9_POCKETS = {
    "dikdortgen": (RefBolge(RECT), 10.0),
    "L": (RefBolge(L_SHAPE), 6.0),
    "ada": (RefBolge(RECT, [ISLAND]), 6.0),
}


def to_profile(ring) -> Profile:
    return Profile.polygon(ring[1]) if ring[0] == "poly" else Profile.circle(ring[1], ring[2])


def to_region(ref: RefBolge) -> Region:
    return Region(to_profile(ref.outer), [to_profile(h) for h in ref.holes])


def reachable(ref: RefBolge, P: np.ndarray, r: float) -> np.ndarray:
    """Takımın (yarıçap r) bölgenin içinden erişebildiği örnek noktalar: p ∈ (Ω ⊖ B_r) ⊕ B_r
    (SPEC 03 testlerindeki ölçütün r parametreli kopyası; aday merkezler gerçek merkez olduğundan
    maske yalnız gerçekten erişilebilir noktaları seçer)."""
    bnd = ref.boundary()
    d = bnd.distance(P)
    in_closed = ref.contains(P) | (d <= 1e-9)
    ok = in_closed & (d >= r)
    phi = np.linspace(0.0, 2 * math.pi, 72, endpoint=False)
    U = np.stack([np.cos(phi), np.sin(phi)], axis=1)
    for i in np.flatnonzero(in_closed & ~ok):
        C = np.vstack([P[i] + rho * r * U for rho in (0.3, 0.6, 0.9, 1.0)])
        ok[i] = bool(np.any(ref.contains(C) & (bnd.distance(C) >= r - 1e-12)))
    return ok


def k9_path(name: str, kind: EntryKind, s_frac: float, ramp_feed: float | None = RAMP_FEED):
    ref, D = K9_POCKETS[name]
    tool = freze(D, center=False, ramp_max=5.0)
    cut = make_cut(stepover=s_frac * D, entry=EntryMode(kind=kind, angle=3.0), ramp_feed=ramp_feed)
    return pocket(to_region(ref), tool, cut), cut, ref, D


K9_CASES = [
    (name, kind, s) for name in K9_POCKETS for kind in (EntryKind.HELIX, EntryKind.RAMP) for s in (0.5, 0.8)
]
K9_IDS = [f"{n}-{k.value}-{s}D" for n, k, s in K9_CASES]


@pytest.fixture(scope="module")
def k9_paths():
    cache: dict = {}

    def get(name, kind, s):
        key = (name, kind, s)
        if key not in cache:
            cache[key] = k9_path(name, kind, s)
        return cache[key]

    return get


@pytest.mark.parametrize("name, kind, s", K9_CASES, ids=K9_IDS)
@a0
def test_pocket_entry_no_gouge(k9_paths, name, kind, s):
    """K9 / SPEC 03 K13: giriş hareketleri dahil tüm kesme hareketlerindeki örnek noktalar
    dist(p, ∂Ω) ≥ r − 1e-9 ve p ∈ Ω."""
    tp, cut, ref, D = k9_paths(name, kind, s)
    parts = [p for p in moves_of(tp) if p.type is not G0]
    assert parts
    P = sample_xy(parts, step=0.25)
    assert np.min(ref.boundary().distance(P)) >= D / 2 - 1e-9
    assert np.all(ref.contains(P))


@pytest.mark.parametrize("name, kind, s", K9_CASES, ids=K9_IDS)
@a0
def test_pocket_entry_no_residue(k9_paths, name, kind, s):
    """K9 / SPEC 03 K14: her pasoda erişilebilir her ızgara noktası z'deki bir kesme hareketine ≤ r + 1e-9."""
    tp, cut, ref, D = k9_paths(name, kind, s)
    r = D / 2
    pts = np.asarray(ref.outer[1])
    (x0, y0), (x1, y1) = pts.min(axis=0), pts.max(axis=0)
    P = grid(float(x0), float(x1), float(y0), float(y1), 45, 45)
    P = P[reachable(ref, P, r)]
    assert len(P) > 0
    for z in depths(cut.z_top, cut.z_bottom, cut.a_p):
        dist = curves_of(cutting_moves(tp, z)).distance(P)
        worst = int(np.argmax(dist))
        assert dist[worst] <= r + 1e-9, f"z={z}: kalan malzeme {P[worst]} uzaklık {dist[worst]}"


@pytest.mark.parametrize("name, kind, s", K9_CASES, ids=K9_IDS)
@a0
def test_pocket_entry_no_plunge(k9_paths, name, kind, s):
    """K9: düz dalma yok: Δz < 0 olan her kesme hareketinin (G1/G2/G3) yatay boyu ≥ TOL ve
    |Δz| / s_xy ≤ tan α + 1e-12 (α = 3°)."""
    tp, *_ = k9_paths(name, kind, s)
    t = math.tan(math.radians(3.0))
    downs = [p for p in moves_of(tp) if p.type is not G0 and p.p1[2] < p.p0[2] - 1e-12]
    assert downs, "giriş hareketi yok"
    for p in downs:
        L = xy_len(p)
        assert L >= TOL
        assert (p.p0[2] - p.p1[2]) / L <= t + 1e-12


@pytest.mark.parametrize("name, kind, s", K9_CASES, ids=K9_IDS)
@a0
def test_pocket_entry_move_rules(k9_paths, name, kind, s):
    """K9 / SPEC 03 K15: validate geçer, yol z_safe'te başlar ve biter, yatay paso derinlikleri depths(...);
    XY değiştiren G0 iki ucu z_safe'te; aşağı inen G0 z_prev + clearance'a iner (paso derinliğine inmez)."""
    tp, cut, ref, D = k9_paths(name, kind, s)
    tp.validate()
    assert tp.start[2] == pytest.approx(cut.z_safe, abs=1e-12)
    assert tp.moves[-1].end[2] == pytest.approx(cut.z_safe, abs=1e-12)
    zs = depths(cut.z_top, cut.z_bottom, cut.a_p)
    assert cut_depths(tp) == pytest.approx(zs, abs=1e-12)
    allowed = {cut.z_top + cut.clearance} | {z + cut.clearance for z in zs[:-1]}
    for p in moves_of(tp):
        if p.type is not G0:
            continue
        if math.hypot(*(p.p1[:2] - p.p0[:2])) > 1e-12:
            assert p.p0[2] == pytest.approx(cut.z_safe, abs=1e-12)
            assert p.p1[2] == pytest.approx(cut.z_safe, abs=1e-12)
        elif p.p1[2] < p.p0[2]:
            assert any(abs(p.p1[2] - a) <= 1e-12 for a in allowed), p.p1[2]


@pytest.mark.parametrize("name, kind, s", K9_CASES[:4], ids=K9_IDS[:4])
@a0
def test_pocket_entry_feeds(k9_paths, name, kind, s):
    """Uygulama kuralı: rampa / helis inişleri ramp_feed, yatay kesme hareketleri feed ile."""
    tp, cut, *_ = k9_paths(name, kind, s)
    for p in moves_of(tp):
        if p.type is G0:
            continue
        if p.p1[2] < p.p0[2] - 1e-12:
            assert p.feed == RAMP_FEED
        elif p.horizontal:
            assert p.feed == FEED


@a0
def test_pocket_entry_ramp_feed_none_uses_feed():
    """Uygulama kuralı: ramp_feed = None → inişler de feed ile."""
    tp, *_ = k9_path("dikdortgen", EntryKind.HELIX, 0.5, ramp_feed=None)
    downs = [p for p in moves_of(tp) if p.type is not G0 and p.p1[2] < p.p0[2] - 1e-12]
    assert downs
    assert all(p.feed == FEED for p in downs)


@a0
def test_pocket_helix_full_circles_present():
    """K9: helisli cepte her paso girişinde aynı merkezli tam daire helisler (başlangıç = bitiş XY, Δz < 0)
    ve z'de bir düz tam daire var; yarıçap R_h = r/2 = 2,5."""
    tp, cut, *_ = k9_path("dikdortgen", EntryKind.HELIX, 0.5)
    parts = moves_of(tp)
    full = [p for p in parts if p.type in ARCS and np.allclose(p.p0[:2], p.p1[:2], atol=1e-9)]
    helis = [p for p in full if p.p1[2] < p.p0[2] - 1e-12]
    flat = [p for p in full if p.horizontal]
    n_pass = len(depths(cut.z_top, cut.z_bottom, cut.a_p))
    assert len(helis) >= n_pass
    assert len(flat) >= n_pass
    for p in helis:
        assert math.dist(p.p0[:2], p.center) == pytest.approx(2.5, abs=1e-9)


# ================================================================ K10: contour + RAMP


def contour_case(profile: Profile, side: str, kind=EntryKind.RAMP, D: float = 6.0, alpha: float = 3.0):
    tool = freze(D, center=False, ramp_max=5.0)
    cut = make_cut(z_bottom=-5.0, a_p=2.0, entry=EntryMode(kind=kind, angle=alpha), ramp_feed=RAMP_FEED)
    return contour(profile, tool, cut, side), cut


def plain_contour(profile: Profile, side: str, D: float = 6.0):
    cut = make_cut(z_bottom=-5.0, a_p=2.0)
    return contour(profile, freze(D), cut, side)


CONTOURS = {
    "daire_ic": (Profile.circle((30.0, 20.0), 20.0), "ic", 2 * math.pi * 17.0),
    "dikdortgen_dis": (Profile.rectangle(0.0, 0.0, 40.0, 20.0), "dis", 120.0 + 2 * math.pi * 3.0),
}


@pytest.mark.parametrize("name", list(CONTOURS))
@a0
def test_contour_ramp_rings_at_depth(name):
    """K10: SPEC 03 K12 yolları z'de aynen var: her paso derinliğinde yatay kesme hareketlerinin boyu P ve
    eğrileri düz dalmalı konturunkilerle 1e-9 içinde çakışık (iki yönde)."""
    profile, side, P = CONTOURS[name]
    tp, cut = contour_case(profile, side)
    tp.validate()
    ref = plain_contour(profile, side)
    for z in depths(cut.z_top, cut.z_bottom, cut.a_p):
        got = cutting_moves(tp, z)
        exp = cutting_moves(ref, z)
        assert sum(p.length_xy() for p in got) == pytest.approx(P, rel=1e-9)
        assert np.max(curves_of(got).distance(sample_xy(exp, 0.5))) <= 1e-9
        assert np.max(curves_of(exp).distance(sample_xy(got, 0.5))) <= 1e-9


@pytest.mark.parametrize("name", list(CONTOURS))
@a0
def test_contour_ramp_slope_exact_and_length(name):
    """K10: rampa eğimi tam α (her inen harekette |Δz| / s_xy = tan α), toplam kesme boyu
    Σ (√(H² + Δz²) + P), Δz = z_prev + clearance − z, H = Δz / tan α."""
    profile, side, P = CONTOURS[name]
    tp, cut = contour_case(profile, side)
    t = math.tan(math.radians(3.0))
    downs = [p for p in moves_of(tp) if p.type is not G0 and p.p1[2] < p.p0[2] - 1e-12]
    assert downs
    for p in downs:
        assert (p.p0[2] - p.p1[2]) / xy_len(p) == pytest.approx(t, rel=1e-9)
        assert p.feed == RAMP_FEED
    zs = depths(cut.z_top, cut.z_bottom, cut.a_p)
    prev = [cut.z_top, *zs[:-1]]
    total = 0.0
    for zp, z in zip(prev, zs, strict=True):
        dz = zp + cut.clearance - z
        total += math.hypot(dz / t, dz) + P
    assert tp.length({G1, G2, G3}) == pytest.approx(total, rel=1e-9)


@a0
def test_contour_ramp_inner_circle_arcs_on_path():
    """K10: dairesel iç konturda rampa yayları da merkez (30, 20), yarıçap 17 olan yol üzerinde."""
    tp, _ = contour_case(*CONTOURS["daire_ic"][:2])
    for p in moves_of(tp):
        if p.type in ARCS:
            assert p.center == pytest.approx((30.0, 20.0), abs=1e-9)
            assert math.dist(p.p0[:2], p.center) == pytest.approx(17.0, abs=1e-9)


@a0
def test_contour_ramp_open_profile():
    """K10 / K7: açık profilde (side = "uzerinde") gidiş-dönüş rampa, sonra z'de p₀ → p₁ kesimi;
    düz dalma yok, eğim ≤ tan α."""
    profile = Profile.polygon([(0.0, 0.0), (30.0, 0.0)], closed=False)
    tp, cut = contour_case(profile, "uzerinde")
    tp.validate()
    t = math.tan(math.radians(3.0))
    for p in moves_of(tp):
        if p.type is not G0 and p.p1[2] < p.p0[2] - 1e-12:
            assert xy_len(p) >= TOL
            assert (p.p0[2] - p.p1[2]) / xy_len(p) <= t + 1e-12
    for z in depths(cut.z_top, cut.z_bottom, cut.a_p):
        got = cutting_moves(tp, z)
        assert sum(p.length_xy() for p in got) == pytest.approx(30.0, rel=1e-9)
        assert got[-1].p1[:2] == pytest.approx((30.0, 0.0), abs=1e-9)


# ================================================================ K11: geriye uyum


def signature(tp: Toolpath) -> list:
    return [(m.type, m.end, m.feed, m.center) for m in tp.moves]


@a0
def test_backward_compat_pocket():
    """K11: entry=None ve EntryMode() ile pocket hareketleri entry verilmemiş Cut'la birebir aynı;
    paso başına tek düşey dalma (SPEC 03)."""
    region = Region(Profile.rectangle(0.0, 0.0, 60.0, 40.0), [Profile.circle((30.0, 20.0), 6.0)])
    base = pocket(region, freze(6.0), make_cut(stepover=3.0))
    for entry in (None, EntryMode(), EntryMode(kind=EntryKind.PLUNGE, angle=30.0)):
        tp = pocket(region, freze(6.0), make_cut(stepover=3.0, entry=entry))
        assert signature(tp) == signature(base)
    rect_region = Region(Profile.rectangle(0.0, 0.0, 60.0, 40.0))
    rect = pocket(rect_region, freze(6.0), make_cut(stepover=3.0, entry=None))
    plunges = [p for p in moves_of(rect) if p.is_plunge]
    assert len(plunges) == len(depths(0.0, -4.0, 2.0))


@pytest.mark.parametrize("side", ["dis", "ic", "uzerinde"])
@a0
def test_backward_compat_contour(side):
    """K11: contour için de entry=None / EntryMode() aynı."""
    profile = Profile.rectangle(0.0, 0.0, 40.0, 20.0)
    base = contour(profile, freze(6.0), make_cut(), side)
    for entry in (None, EntryMode()):
        assert signature(contour(profile, freze(6.0), make_cut(entry=entry), side)) == signature(base)


@pytest.mark.parametrize(
    "entry",
    [None, EntryMode(), EntryMode(kind=EntryKind.RAMP), EntryMode(kind=EntryKind.HELIX)],
    ids=["None", "dalma", "rampa", "helis"],
)
@a0
def test_backward_compat_face(entry):
    """K11 / Uygulama kuralı: face değişmez (girişleri ham malzemenin dışında)."""
    stock = Stock(xmin=0.0, ymin=0.0, zmin=-20.0, xmax=100.0, ymax=50.0, zmax=0.0)
    kw = dict(z_top=0.0, z_bottom=-1.0, a_p=0.6, stepover=5.5)
    base = face(stock, freze(6.0), make_cut(**kw))
    assert signature(face(stock, freze(6.0), make_cut(entry=entry, **kw))) == signature(base)


# ================================================================ K12: sığmayan giriş → CamError


@a0
def test_helix_does_not_fit_narrow_channel():
    """K12: 60 × 14 kanal, D = 10 (genişlik 14 < 2(r + R_h) = 15): R₀ 4 geniş → dist(c, ∂R₀) = 2 < R_h = 2,5
    → CamError (merkezden kesen takımla da; sessiz düz dalma yok); mesajda 2 ve 2,5."""
    region = Region(Profile.rectangle(0.0, 0.0, 60.0, 14.0))
    cut = make_cut(stepover=5.0, entry=EntryMode(kind=EntryKind.HELIX))
    with pytest.raises(CamError) as e:
        pocket(region, freze(10.0), cut)
    assert mentions(str(e.value), 2.0), str(e.value)
    assert mentions(str(e.value), 2.5), str(e.value)


@a0
def test_helix_fits_slightly_wider_channel():
    """K12 karşı denetim: 60 × 15,5 kanalda dist(c, ∂R₀) = 2,75 ≥ 2,5 → helis yapılır."""
    region = Region(Profile.rectangle(0.0, 0.0, 60.0, 15.5))
    tp = pocket(region, freze(10.0), make_cut(stepover=5.0, entry=EntryMode(kind=EntryKind.HELIX)))
    tp.validate()
    assert not any(p.is_plunge for p in moves_of(tp))


@a0
def test_zigzag_too_short_non_center():
    """K12: 12 × 12 cep, D = 10 → R₀ 2 × 2 kare; en büyük 2ℓ_fit = 2√2 < r = 5 → merkezden kesmeyende
    CamError, mesajda 2√2 ve 5."""
    region = Region(Profile.rectangle(0.0, 0.0, 12.0, 12.0))
    cut = make_cut(stepover=5.0, entry=EntryMode(kind=EntryKind.RAMP, angle=3.0))
    with pytest.raises(CamError) as e:
        pocket(region, freze(10.0, center=False, ramp_max=5.0), cut)
    assert mentions(str(e.value), 2 * math.sqrt(2.0)), str(e.value)
    assert mentions(str(e.value), 5.0), str(e.value)


@a0
def test_zigzag_short_ok_center_cutting():
    """K12 karşı denetim: aynı cep merkezden kesen takımla (L_min = TOL) kabul; düz dalma yok."""
    region = Region(Profile.rectangle(0.0, 0.0, 12.0, 12.0))
    cut = make_cut(stepover=5.0, entry=EntryMode(kind=EntryKind.RAMP, angle=3.0))
    tp = pocket(region, freze(10.0), cut)
    tp.validate()
    assert not any(p.is_plunge for p in moves_of(tp))


@a0
def test_contour_ramp_loop_too_short_non_center():
    """K12: R = 7 iç daire, D = 10 → yol yarıçapı 2, P = 4π < π r = 5π → merkezden kesmeyende CamError;
    mesajda P = 12,566 ve π r = 15,708."""
    cut = make_cut(entry=EntryMode(kind=EntryKind.RAMP, angle=3.0))
    with pytest.raises(CamError) as e:
        contour(Profile.circle((0.0, 0.0), 7.0), freze(10.0, center=False, ramp_max=5.0), cut, "ic")
    assert mentions(str(e.value), 4 * math.pi), str(e.value)
    assert mentions(str(e.value), 5 * math.pi), str(e.value)


@a0
def test_contour_ramp_loop_long_enough_non_center():
    """K12 karşı denetim: R = 8 → P = 6π ≥ 5π: kabul."""
    cut = make_cut(entry=EntryMode(kind=EntryKind.RAMP, angle=3.0))
    tp = contour(Profile.circle((0.0, 0.0), 8.0), freze(10.0, center=False, ramp_max=5.0), cut, "ic")
    tp.validate()
    assert not any(p.is_plunge for p in moves_of(tp))


# ================================================================ K13: G-code gidiş-dönüş


TOL_END = 0.5e-3 + 1e-9  # mm, koordinat başına (SPEC 04, 3 basamak)
TOL_FEED = 0.05 + 1e-9
TOL_CENTER = 1e-2


def as_written(tp: Toolpath, safe_z: float) -> Toolpath:
    """SPEC 04 Ek B: yazıcı yol başı güvenli Z'den alçaksa önce güvenli Z'de konumlar, program sonunda
    güvenli Z'nin altındaysa G0 Z<safe_z> ekler (tests/cam/test_gcode_roundtrip.py ile aynı kural)."""
    x0, y0, z0 = tp.start
    moves = [Move(G0, (x0, y0, z0)), *tp.moves] if round(z0, 3) < round(safe_z, 3) else list(tp.moves)
    x, y, z = moves[-1].end
    if round(z, 3) < round(safe_z, 3):
        moves.append(Move(G0, (x, y, safe_z)))
    return Toolpath(tp.name, tp.tool, (x0, y0, safe_z), moves, tp.rpm)


@a0
def test_helix_pocket_gcode_roundtrip():
    """K13: helisli cep SPEC 04 write ile yazılıp read ile okununca hareketler decimals toleransında aynı;
    tam daire helisler G2/G3 + Z (+ I/J) satırı olarak yazılır ve tam daire helis olarak geri okunur."""
    tp, cut, *_ = k9_path("dikdortgen", EntryKind.HELIX, 0.5)
    tp.validate()
    safe_z = cut.z_safe
    text = write([tp], GRBL, safe_z=safe_z)
    got = read(text, {tp.tool.id: tp.tool}, GRBL)
    assert len(got) == 1
    g = got[0]
    g.validate()
    exp = as_written(tp, safe_z)
    assert len(g.moves) == len(exp.moves)
    for i, (a, b) in enumerate(zip(g.moves, exp.moves, strict=True)):
        assert a.type is b.type, i
        assert np.max(np.abs(np.subtract(a.end, b.end))) <= TOL_END, (i, a.end, b.end)
        if b.type is not G0:
            assert abs(a.feed - b.feed) <= TOL_FEED, i
        if b.type in ARCS:
            assert math.dist(a.center, b.center) <= TOL_CENTER, i

    def full_helices(t: Toolpath) -> int:
        return sum(
            1
            for p in moves_of(t)
            if p.type in ARCS and np.allclose(p.p0[:2], p.p1[:2], atol=1e-6) and p.p1[2] < p.p0[2] - 1e-6
        )

    assert full_helices(tp) > 0
    assert full_helices(g) == full_helices(tp)
    arc_z_lines = [ln for ln in text.splitlines() if "Z" in ln and ("I" in ln or "J" in ln)]
    assert len(arc_z_lines) >= full_helices(tp)
