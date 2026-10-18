"""SPEC 50 — yanak (swarf) frezeleme testleri (K4, K5, K9'un yanak kısmı).

Testler yalnız SPEC 50 metninden (Teori, Arayüz, Ek A), `cam/model.py` arayüzünden ve analitik geometriden
yazıldı; `cam/multiaxis/swarf.py` gövdeleri okunmadı (iskelette NotImplementedError).

Kurallar (SPEC 50 Teori + Ek A):
- S(u, v) = (1 − v)·C₀(u) + v·C₁(u); örnekler arasında bilineer. g = norm(C₁ − C₀).
- n = side·norm(∂S/∂u × ∂S/∂v), ∂S/∂u = C_m = (C₀ + C₁)/2 dizisinin merkezi farkı (uçlarda
  tek yanlı); takım +n yanında.
- Uç p_i = C₀,ᵢ + (R + allowance)·n_m + allowance_z·g_i; yol: start = p_0 + clearance·g_0, G1 p_0 … p_{n−1},
  son G0 p_{n−1} + clearance·g_{n−1}; her Move.axis = g_i.
- swarf_error: bilineer yüzeyin takım silindirine (p'den g boyunca [0, flute_length], yarıçap R)
  en büyük girmesi.
- Gelişebilir yüzeyde (silindir, koni) normal cetvel boyunca sabit → hata 0. Bükülmüşte birinci mertebe
  e ≈ R·(1 − cos Δφ), Δφ = ∠(n(u, v), n_m).
"""

from __future__ import annotations

import math
import re

import numpy as np
import pytest

from cam.model import CamError, MoveType, Tool, ToolKind
from cam.multiaxis.swarf import RuledSurface, swarf, swarf_error

R = 5.0  # düz uç yarıçapı
FLUTE = 35.0  # kesici boy (cetvel boyu 30'dan uzun)
FEED, RPM = 800.0, 6000.0
H = 30.0  # cetvel yüksekliği / boyu
C_HP = 200.0  # hiperbolik paraboloid z = x·y / c


def _flat(D: float = 2 * R, flute: float = FLUTE) -> Tool:
    return Tool(id=1, name="swarf", kind=ToolKind.FLAT, D=D, flute_length=flute)


def _birim(v: np.ndarray) -> np.ndarray:
    return v / np.linalg.norm(v, axis=-1, keepdims=True)


# ---------------------------------------------------------------- yüzeyler


def _silindir(rho: float = 40.0, n: int = 37) -> RuledSurface:
    """Dik silindir duvar (dışbükey, takım dışarıda): θ ∈ [0°, 180°] saat yönü tersine, z ∈ [0, H].

    u θ ile artar → ∂S/∂u = θ̂, ∂S/∂v = +ẑ, θ̂ × ẑ = r̂ (dışarı): side = +1 takımı dışarıya koyar.
    """
    th = np.linspace(0.0, math.pi, n)
    C0 = np.stack([rho * np.cos(th), rho * np.sin(th), np.zeros(n)], axis=1)
    C1 = C0 + np.array([0.0, 0.0, H])
    return RuledSurface(C0=C0, C1=C1)


def _koni(rho0: float = 40.0, yari_aci: float = 15.0, n: int = 37) -> RuledSurface:
    """Yukarı daralan koni (dışbükey): alt ray ρ₀, üst ray ρ₀ − H·tan α, z ∈ [0, H].

    Dış normal n = cos α·r̂ + sin α·ẑ, cetvel yönü g = −sin α·r̂ + cos α·ẑ (her ikisi cetvel boyunca sabit).
    """
    a = math.radians(yari_aci)
    th = np.linspace(0.0, math.pi, n)
    r1 = rho0 - H * math.tan(a)
    C0 = np.stack([rho0 * np.cos(th), rho0 * np.sin(th), np.zeros(n)], axis=1)
    C1 = np.stack([r1 * np.cos(th), r1 * np.sin(th), np.full(n, H)], axis=1)
    return RuledSurface(C0=C0, C1=C1)


def _hipar(n: int = 401, x_lim: float = 20.0) -> RuledSurface:
    """z = x·y / c, cetveller x = x₀ (y ∈ [−15, 15]); raylar x'te doğru →
    bilineer yüzey tam hiperbolik paraboloid.

    ∂S/∂u ∝ (1, 0, y/c), v = ½'de (1, 0, 0); ∂S/∂v = (0, 30, 30x₀/c) → n_m ∝ (0, −x₀/c, 1):
    side = +1 takım üstte.
    """
    x = np.linspace(-x_lim, x_lim, n)
    C0 = np.stack([x, np.full(n, -H / 2), -H / 2 * x / C_HP], axis=1)
    C1 = np.stack([x, np.full(n, H / 2), H / 2 * x / C_HP], axis=1)
    return RuledSurface(C0=C0, C1=C1)


# ---------------------------------------------------------------- bağımsız referanslar


def _ek_a_uclar(
    s: RuledSurface, side: int, allowance: float, allowance_z: float, r: float = R
) -> tuple[np.ndarray, np.ndarray]:
    """Ek A formülü (bağımsız yeniden hesap): uç noktaları p_i ve eksenler g_i (takım yarıçapı r)."""
    C0, C1 = np.asarray(s.C0, float), np.asarray(s.C1, float)
    Cm = (C0 + C1) / 2
    t = np.empty_like(Cm)
    t[1:-1] = Cm[2:] - Cm[:-2]
    t[0] = Cm[1] - Cm[0]
    t[-1] = Cm[-1] - Cm[-2]
    g = _birim(C1 - C0)
    nm = side * _birim(np.cross(t, C1 - C0))
    return C0 + (r + allowance) * nm + allowance_z * g, g


def _girme(Q: np.ndarray, p: np.ndarray, g: np.ndarray, L: float = FLUTE) -> float:
    """Q noktalarının (p, g, [0, L], R) silindirine en büyük girmesi max(0, R − d⊥)."""
    d = Q - p
    t = d @ g
    ic = (t >= 0) & (t <= L)
    if not np.any(ic):
        return 0.0
    dperp = np.linalg.norm(d[ic] - np.outer(t[ic], g), axis=1)
    return float(max(0.0, np.max(R - dperp)))


def _hipar_ref(x0: float) -> float:
    """Hiperbolik paraboloidde x₀ cetvelindeki takımın gerçek yüzeye girmesi, yoğun örnekleme.

    Takım: p = C₀(x₀) + R·n_m, eksen g = norm(0, 1, x₀/c). Yüzey z = xy/c, x ∈ [−20, 20], y ∈ [−15, 15].
    Önce kaba ızgara, sonra en büyük noktanın çevresinde ince ızgara.
    """
    g = _birim(np.array([0.0, 1.0, x0 / C_HP]))
    nm = _birim(np.array([0.0, -x0 / C_HP, 1.0]))
    p = np.array([x0, -H / 2, -H / 2 * x0 / C_HP]) + R * nm

    def yuzey(xs: np.ndarray, ys: np.ndarray) -> np.ndarray:
        X, Y = np.meshgrid(xs, ys)
        return np.stack([X, Y, X * Y / C_HP], axis=-1).reshape(-1, 3)

    def en_buyuk(xs, ys):
        Q = yuzey(xs, ys)
        d = Q - p
        t = d @ g
        e = R - np.linalg.norm(d - np.outer(t, g), axis=1)
        k = int(np.argmax(e))
        return float(e[k]), Q[k]

    xs = np.clip(np.linspace(x0 - 3.0, x0 + 3.0, 6001), -20.0, 20.0)
    e, q = en_buyuk(xs, np.linspace(-H / 2, H / 2, 301))
    xs = np.clip(np.linspace(q[0] - 2e-3, q[0] + 2e-3, 4001), -20.0, 20.0)
    ys = np.clip(np.linspace(q[1] - 0.1, q[1] + 0.1, 201), -H / 2, H / 2)
    e2, _ = en_buyuk(xs, ys)
    return max(e, e2)


def _hipar_dphi_max(x0: float) -> float:
    """Δφ_max = ∠(n(y = ±15), n_m), n ∝ (−y/c, −x₀/c, 1), kapalı form."""
    nm = _birim(np.array([0.0, -x0 / C_HP, 1.0]))
    return max(
        math.acos(float(np.clip(_birim(np.array([-y / C_HP, -x0 / C_HP, 1.0])) @ nm, -1.0, 1.0)))
        for y in (-H / 2, H / 2)
    )


# ---------------------------------------------------------------- K4 gelişebilir


@pytest.mark.parametrize("yuzey", [_silindir, _koni], ids=["silindir", "koni"])
def test_k4_gelisebilir_hata_sifir(yuzey):
    s = yuzey()
    n = len(s.C0)
    for i in range(n):
        assert swarf_error(s, _flat(), i / (n - 1)) <= 1e-9


def _analitik_normal(s: RuledSurface, yari_aci: float) -> np.ndarray:
    """Silindir (α = 0) ve koni için ray noktalarındaki dış normal cos α·r̂ + sin α·ẑ."""
    a = math.radians(yari_aci)
    C0 = np.asarray(s.C0, float)
    rh = _birim(C0 * np.array([1.0, 1.0, 0.0]))
    return math.cos(a) * rh + math.sin(a) * np.array([0.0, 0.0, 1.0])


@pytest.mark.parametrize(("yuzey", "alfa"), [(_silindir, 0.0), (_koni, 15.0)], ids=["silindir", "koni"])
@pytest.mark.parametrize(("allowance", "allowance_z"), [(0.0, 0.0), (0.3, 0.5)])
def test_k4_uc_noktasi(yuzey, alfa, allowance, allowance_z):
    s = yuzey()
    clearance = 5.0
    tp = swarf(
        s, _flat(), allowance=allowance, allowance_z=allowance_z, feed=FEED, rpm=RPM, clearance=clearance
    )
    P, G = _ek_a_uclar(s, +1, allowance, allowance_z)
    n = len(P)
    kes = [m for m in tp.moves if m.type is MoveType.LINEAR]
    assert len(kes) == n
    assert len(tp.moves) == n + 1 and tp.moves[-1].type is MoveType.RAPID
    np.testing.assert_allclose(tp.start, P[0] + clearance * G[0], atol=1e-9)
    np.testing.assert_allclose(tp.moves[-1].end, P[-1] + clearance * G[-1], atol=1e-9)
    for m, p, g in zip(kes, P, G, strict=True):
        assert m.feed == pytest.approx(FEED)
        np.testing.assert_allclose(m.end, p, atol=1e-9)
        np.testing.assert_allclose(m.axis, g, atol=1e-9)
    # iç noktalarda merkezi fark kirişi teğete dik: n_m analitik dış normalle aynı
    # (K4: C₀ + R·n_m + allowance_z·g)
    N = _analitik_normal(s, alfa)
    C0 = np.asarray(s.C0, float)
    for i in range(1, n - 1):
        np.testing.assert_allclose(kes[i].end, C0[i] + (R + allowance) * N[i] + allowance_z * G[i], atol=1e-9)
    assert tp.meta is not None
    assert tp.meta.strategy == "yanak"
    assert tp.meta.axis_mode == "5"


def test_k4_side_ters_takimi_obur_yana_koyar():
    """side = −1: n = −norm(∂S/∂u × ∂S/∂v); silindirde takım içeriye (r̂'nin tersine) geçer."""
    s = _silindir()
    tp = swarf(s, _flat(D=4.0), side=-1, feed=FEED, rpm=RPM)
    P, _ = _ek_a_uclar(s, -1, 0.0, 0.0, r=2.0)
    kes = [m for m in tp.moves if m.type is MoveType.LINEAR]
    for m, p in zip(kes, P, strict=True):
        np.testing.assert_allclose(m.end, p, atol=1e-9)
    C0 = np.asarray(s.C0, float)
    i = len(C0) // 2
    r = np.hypot(kes[i].end[0], kes[i].end[1])
    assert r == pytest.approx(np.hypot(C0[i, 0], C0[i, 1]) - 2.0, abs=1e-9)


# ---------------------------------------------------------------- K5 bükülmüş


@pytest.mark.parametrize("x0", [0.0, 10.0, -10.0])
def test_k5_hipar_yogun_ornekleme(x0):
    s = _hipar()
    u = (x0 + 20.0) / 40.0
    ref = _hipar_ref(x0)
    assert ref > 0.01  # gerçekten bükülmüş: ≈ 0.014 mm
    assert swarf_error(s, _flat(), u) == pytest.approx(ref, abs=1e-6)


@pytest.mark.parametrize("x0", [0.0, 10.0, -10.0])
def test_k5_birinci_mertebe_formul(x0):
    """Küçük bükümde e ≈ R(1 − cos Δφ_max) (%10 içinde)."""
    s = _hipar()
    e = swarf_error(s, _flat(), (x0 + 20.0) / 40.0)
    formul = R * (1.0 - math.cos(_hipar_dphi_max(x0)))
    assert formul == pytest.approx(0.0140, abs=2e-4)  # x₀ = 0: Δφ_max = 0.07486 rad
    assert e == pytest.approx(formul, rel=0.10)


def test_k5_tolerans_icinde_yol_uretilir():
    s = _hipar()
    tp = swarf(s, _flat(), tol_swarf=0.1, feed=FEED, rpm=RPM)
    P, G = _ek_a_uclar(s, +1, 0.0, 0.0)
    kes = [m for m in tp.moves if m.type is MoveType.LINEAR]
    assert len(kes) == len(P)
    for m, p, g in zip(kes, P, G, strict=True):
        np.testing.assert_allclose(m.end, p, atol=1e-9)
        np.testing.assert_allclose(m.axis, g, atol=1e-9)


def test_k5_tolerans_asimi_hata_ve_nokta_indeksi():
    """tol = 0.01397: yalnız orta bölgedeki cetveller (|x₀| küçük) aşar.

    Mesaj aşan bir noktanın indeksini taşır.
    """
    s = _hipar()
    tol = 0.01397
    n = len(s.C0)
    assert _hipar_ref(0.0) > tol + 1e-6 and _hipar_ref(20.0) < tol - 1e-6  # hem aşan hem aşmayan nokta var
    with pytest.raises(CamError) as e:
        swarf(s, _flat(), tol_swarf=tol, feed=FEED, rpm=RPM)
    adaylar = {int(k) for k in re.findall(r"(?<![\d.])\d+(?![\d.])", str(e.value))}
    asan = [i for i in sorted(adaylar) if i < n and _hipar_ref(-20.0 + 40.0 * i / (n - 1)) > tol]
    assert asan, f"mesajda aşan nokta indeksi yok: {e.value}"


def test_k5_varsayilan_tolerans_hipari_reddeder():
    """Varsayılan tol_swarf = 0.01 < ≈0.0139 mm → CamError."""
    with pytest.raises(CamError):
        swarf(_hipar(), _flat(), feed=FEED, rpm=RPM)


# ---------------------------------------------------------------- K9 hatalar (yanak)


def test_k9_uyumsuz_ray_sayisi():
    s = _silindir()
    with pytest.raises(CamError):
        RuledSurface(C0=np.asarray(s.C0)[:-1], C1=np.asarray(s.C1))


def test_k9_sifir_cetvel():
    s = _silindir()
    C1 = np.asarray(s.C1, float).copy()
    C1[5] = np.asarray(s.C0, float)[5]
    with pytest.raises(CamError):
        RuledSurface(C0=np.asarray(s.C0), C1=C1)


def test_k9_cetvel_kesici_boydan_uzun():
    with pytest.raises(CamError):
        swarf(_silindir(), _flat(flute=25.0), feed=FEED, rpm=RPM)


def test_k9_duz_disi_takim():
    ball = Tool(id=2, name="kure", kind=ToolKind.BALL, D=2 * R, flute_length=FLUTE)
    with pytest.raises(CamError):
        swarf(_silindir(), ball, feed=FEED, rpm=RPM)
