"""SPEC 34 — assy/tolerans.py testleri: tolerans yığılımı (K1–K12, analitik tablo A1–A9).

Testler sadece specs/34-tolerans.md'deki teori, arayüz ve analitik tablodan, A1 arayüzü
(assy.model.Tolerance / Distribution) ve SPEC 08 açık arayüzünden (assy.solver.solve, dof) yazıldı;
assy/tolerans.py gövdesi okunmadı.

Kurallar (SPEC 34, "Teori"):
    μ = x₀ + (l + u)/2,  T = (u − l)/2
    σ: NORMAL T/k (k = sigma_level), UNIFORM T/√3, TRIANGULAR T/√6
    G = c + Σ a_i x_i,  G₀ = c + Σ a_i x₀_i,  μ_G = c + Σ a_i μ_i
    En kötü durum: T_wc = Σ |a_i| T_i,  G ∈ μ_G ± T_wc,  katkı |a_i| T_i / T_wc
    RSS:           σ_G = √Σ a_i² σ_i²,   G ∈ μ_G ± k σ_G,  katkı a_i² σ_i² / σ_G²
    Şartname dışı (RSS): p = Φ((LSL − μ_G)/σ_G) + 1 − Φ((USL − μ_G)/σ_G),  Φ(z) = ½(1 + erf(z/√2))
    3B: a_j = ∂m/∂p_j (örtük fonksiyon teoremi), c = m₀ − Σ a_j p₀_j
Kaynak: Fortini (1967); Chase–Parkinson (1991); Drake, Dimensioning and Tolerancing Handbook, Böl. 9.

Toleranslar (SPEC 34): kapalı form 1e-12 (göreli 1e-12), 3B 1e-9; Monte Carlo istatistiksel sınırlar.
3B montajlarda başlangıç konumu beklenen çözümden birkaç derece / mm kaçık seçildi (SPEC 08 çözücüsü
başlangıca en yakın dalı bulur).
Kod henüz yokken (NotImplementedError) testler kök conftest.py ile "uygulanmamış" (xfail) sayılır.
"""

from __future__ import annotations

import copy
import math

import numpy as np
import pytest

from assy.model import (
    Assembly,
    AssyError,
    Component,
    Distribution,
    Mate,
    MateKind,
    Ref,
    RefKind,
    Tolerance,
    rot_x,
    rot_z,
    transform,
)
from assy.solver import dof, solve
from assy.tolerans import (
    Chain,
    Link,
    Method,
    StackResult,
    assembly_chain,
    measure,
    monte_carlo,
    reject_fraction,
    rss,
    samples,
    worst_case,
)

C, CON, DIS, ANG = MateKind.COINCIDENT, MateKind.CONCENTRIC, MateKind.DISTANCE, MateKind.ANGLE
NORMAL, UNIFORM, TRIANGULAR = Distribution.NORMAL, Distribution.UNIFORM, Distribution.TRIANGULAR
REL = 1e-12  # kapalı form
TOL_3B = 1e-9


def close(x: float, y: float, tol: float = REL) -> bool:
    """|x − y| ≤ tol · max(1, |y|)  (göreli 1e-12, küçük sayılarda mutlak)."""
    return abs(x - y) <= tol * max(1.0, abs(y))


def Phi(z: float) -> float:
    """Standart normal birikimli dağılım: Φ(z) = ½ (1 + erf(z/√2))."""
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def Tn(n: float, t: float, name: str = "") -> Tolerance:
    """SPEC tablosundaki Tn(t): simetrik, NORMAL, k = 3."""
    return Tolerance.symmetric(n, t, name=name)


def chain_of(*pairs, c: float = 0.0) -> Chain:
    """(tolerans, a) çiftlerinden zincir."""
    return Chain(links=tuple(Link(tol=t, a=a) for t, a in pairs), c=c)


def chain_A1() -> Chain:
    """A1: gövde 50 T(0.1) a=+1; burçlar 20 T(0.05), 29.8 T(0.05) a=−1."""
    return chain_of((Tn(50.0, 0.1), 1.0), (Tn(20.0, 0.05), -1.0), (Tn(29.8, 0.05), -1.0))


def chain_A5() -> Chain:
    """A5: iki UNIFORM ±0.1 toplamı (nominal 0)."""
    u = Tolerance.symmetric(0.0, 0.1, distribution=UNIFORM)
    return chain_of((u, 1.0), (u, 1.0))


def half(r: StackResult) -> float:
    return (r.upper - r.lower) / 2.0


# ---------------------------------------------------------------- K1 doğrulama


class TestLinkChain:
    @pytest.mark.parametrize("a", [0.0, math.inf, -math.inf, math.nan])
    def test_gecersiz_a(self, a):
        # etkisiz (a = 0) veya sonsuz halka sessizce yutulmaz
        with pytest.raises(AssyError):
            Link(tol=Tn(10.0, 0.1), a=a)

    def test_bos_zincir(self):
        with pytest.raises(AssyError):
            Chain(links=())

    def test_gecerli_halka(self):
        L = Link(tol=Tn(10.0, 0.1), a=-2.5, name="burc")
        assert L.a == -2.5 and L.name == "burc"
        assert Link(tol=Tn(10.0, 0.1)).a == 1.0  # varsayılan a = +1

    def test_nominal_ve_orta(self):
        # A3: 10 +0.1/−0 → G₀ = 10, μ_G = 10.05; c ve a hesaba katılır
        ch = Chain(links=(Link(tol=Tolerance(10.0, 0.0, 0.1), a=2.0),), c=1.5)
        assert close(ch.nominal, 1.5 + 2.0 * 10.0)
        assert close(ch.mean, 1.5 + 2.0 * 10.05)
        assert close(chain_A1().nominal, 0.2)
        assert close(chain_A1().mean, 0.2)


# ---------------------------------------------------------------- K2 en kötü durum


class TestWorstCase:
    def test_A1(self):
        r = worst_case(chain_A1())
        assert r.method is Method.WORST_CASE
        assert r.sigma is None
        assert close(r.nominal, 0.2) and close(r.mean, 0.2)
        assert close(r.lower, 0.0) and close(r.upper, 0.4)
        assert len(r.contributions) == 3
        for got, exp in zip(r.contributions, (0.5, 0.25, 0.25), strict=True):
            assert close(got, exp)
        assert close(sum(r.contributions), 1.0)

    @pytest.mark.parametrize("n", [1, 4, 9])
    def test_A2_es_halkalar(self, n):
        t = 0.07
        ch = chain_of(*[(Tn(10.0, t), 1.0)] * n)
        r = worst_case(ch)
        assert close(half(r), n * t)
        assert close(r.mean, 10.0 * n)
        assert close(sum(r.contributions), 1.0)
        for c in r.contributions:
            assert close(c, 1.0 / n)

    def test_A3_asimetrik(self):
        r = worst_case(chain_of((Tolerance(10.0, 0.0, 0.1), 1.0)))
        assert close(r.nominal, 10.0)
        assert close(r.mean, 10.05)
        assert close(r.lower, 10.0) and close(r.upper, 10.1)
        assert r.contributions == pytest.approx((1.0,), rel=REL)

    def test_A4_kaldirac(self):
        r = worst_case(chain_of((Tn(5.0, 0.05), 2.0)))
        assert close(r.nominal, 10.0)
        assert close(half(r), 0.1)
        assert close(r.lower, 9.9) and close(r.upper, 10.1)

    def test_negatif_kaldirac_mutlak_deger(self):
        # T_wc = Σ |a_i| T_i: a'nın işareti yarı genişliği azaltmaz
        r = worst_case(chain_of((Tn(5.0, 0.05), -2.0), (Tn(1.0, 0.1), 1.0)))
        assert close(half(r), 0.2)
        assert close(r.mean, -9.0)
        for got, exp in zip(r.contributions, (0.5, 0.5), strict=True):
            assert close(got, exp)


# ---------------------------------------------------------------- K3 RSS


class TestRSS:
    def test_A1(self):
        r = rss(chain_A1())
        assert r.method is Method.RSS
        s = math.sqrt(0.015) / 3.0
        assert close(r.sigma, s)
        assert close(r.sigma, 0.04082482904638630)
        assert close(r.mean, 0.2) and close(r.nominal, 0.2)
        assert close(r.lower, 0.2 - math.sqrt(0.015)) and close(r.upper, 0.2 + math.sqrt(0.015))
        for got, exp in zip(r.contributions, (2 / 3, 1 / 6, 1 / 6), strict=True):
            assert close(got, exp)
        assert close(sum(r.contributions), 1.0)

    @pytest.mark.parametrize("n", [1, 4, 9])
    def test_A2_es_halkalar(self, n):
        t = 0.07
        r = rss(chain_of(*[(Tn(10.0, t), 1.0)] * n), k=3.0)
        assert close(3.0 * r.sigma, math.sqrt(n) * t)
        assert close(half(r), math.sqrt(n) * t)

    def test_A4_kaldirac(self):
        r = rss(chain_of((Tn(5.0, 0.05), 2.0)))
        assert close(r.sigma, 2.0 * 0.05 / 3.0)
        assert close(half(r), 0.1)

    def test_A7_ucgen(self):
        r = rss(chain_of((Tolerance.symmetric(0.0, 0.3, distribution=TRIANGULAR), 1.0)))
        assert close(r.sigma, 0.3 / math.sqrt(6.0))
        assert close(r.sigma, 0.12247448713915890)

    def test_klasik_rss(self):
        # tüm NORMAL ve sigma_level = k → k σ_G = √Σ (a_i T_i)²
        k = 2.5
        tols = [(0.1, 1.0), (0.04, -3.0), (0.2, 0.5), (0.0, 1.0)]
        ch = Chain(links=tuple(Link(tol=Tolerance.symmetric(7.0, t, sigma_level=k), a=a) for t, a in tols))
        r = rss(ch, k=k)
        assert close(k * r.sigma, math.sqrt(sum((a * t) ** 2 for t, a in tols)))
        assert close(sum(r.contributions), 1.0)
        assert close(r.contributions[3], 0.0)  # T = 0 halkanın payı yok

    def test_k_yalniz_sinirlari_olcekler(self):
        ch = chain_A1()
        r3, r2 = rss(ch, k=3.0), rss(ch, k=2.0)
        assert close(r2.sigma, r3.sigma)
        assert close(r2.mean, r3.mean)
        assert r2.contributions == pytest.approx(r3.contributions, rel=REL)
        assert close(half(r2), 2.0 * r3.sigma)
        assert close(half(r2) / half(r3), 2.0 / 3.0)

    @pytest.mark.parametrize("k", [0.0, -1.0])
    def test_k_pozitif_olmali(self, k):
        with pytest.raises(AssyError):
            rss(chain_A1(), k=k)


# ---------------------------------------------------------------- K4 dağılım karışımı


class TestKarisim:
    def test_A5_iki_duzgun(self):
        r = rss(chain_A5())
        assert close(r.sigma, 0.1 * math.sqrt(2.0 / 3.0))
        assert close(r.sigma, 0.08164965809277260)

    def test_uc_dagilim_ayni_zincirde(self):
        n_ = Tn(10.0, 0.1)
        u_ = Tolerance.symmetric(4.0, 0.1, distribution=UNIFORM)
        t_ = Tolerance.symmetric(2.0, 0.3, distribution=TRIANGULAR)
        r = rss(chain_of((n_, 1.0), (u_, -1.0), (t_, 2.0)))
        v = [(0.1 / 3.0) ** 2, (0.1 / math.sqrt(3.0)) ** 2, 4.0 * (0.3 / math.sqrt(6.0)) ** 2]
        assert close(r.sigma**2, sum(v))
        for got, exp in zip(r.contributions, [x / sum(v) for x in v], strict=True):
            assert close(got, exp)
        assert close(r.mean, 10.0 - 4.0 + 4.0)

    def test_sigma_level_yalniz_normal(self):
        # NORMAL'de σ = T / sigma_level
        r = rss(chain_of((Tolerance.symmetric(0.0, 0.12, sigma_level=4.0), 1.0)))
        assert close(r.sigma, 0.03)


# ---------------------------------------------------------------- K5 Monte Carlo

N_MC = 200_000


class TestMonteCarlo:
    @pytest.mark.parametrize("make", [chain_A1, chain_A5], ids=["A1", "A5"])
    def test_ortalama_ve_std(self, make):
        ch = make()
        s = rss(ch).sigma
        r = monte_carlo(ch, n=N_MC, seed=7)
        assert r.method is Method.MONTE_CARLO
        assert close(r.nominal, ch.nominal)
        assert abs(r.mean - ch.mean) <= 4.0 * s / math.sqrt(N_MC)
        assert abs(r.sigma - s) <= 0.02 * s
        assert close(sum(r.contributions), 1.0, tol=1e-9)
        assert r.contributions == pytest.approx(rss(ch).contributions, abs=0.02)

    def test_sinirlar_yuzdelik(self):
        # A1 tüm halkalar NORMAL: Φ(∓3) yüzdelikleri ≈ μ_G ∓ 3σ_G (yüzdelik hatası ≈ 0.02σ)
        ch = chain_A1()
        s = rss(ch).sigma
        r = monte_carlo(ch, n=N_MC, seed=3, k=3.0)
        assert abs(r.lower - (ch.mean - 3.0 * s)) <= 0.1 * s
        assert abs(r.upper - (ch.mean + 3.0 * s)) <= 0.1 * s
        r2 = monte_carlo(ch, n=N_MC, seed=3, k=2.0)
        assert abs(r2.upper - (ch.mean + 2.0 * s)) <= 0.05 * s

    def test_samples_tekrarlanabilir(self):
        ch = chain_A1()
        x = samples(ch, 1000, seed=11)
        assert isinstance(x, np.ndarray) and x.shape == (1000,)
        assert np.all(np.isfinite(x))
        assert np.array_equal(x, samples(ch, 1000, seed=11))
        assert not np.array_equal(x, samples(ch, 1000, seed=12))

    def test_samples_dagilim_bandi(self):
        # UNIFORM ve TRIANGULAR örnekler bant içinde kalır (NORMAL kesilmez, o yüzden onlar burada)
        u = Tolerance(5.0, -0.1, 0.3, distribution=UNIFORM)
        x = samples(chain_of((u, 1.0)), 20_000, seed=1)
        assert x.min() >= 4.9 and x.max() <= 5.3
        assert abs(x.mean() - 5.1) <= 4.0 * (0.2 / math.sqrt(3.0)) / math.sqrt(20_000)
        t = Tolerance.symmetric(0.0, 0.3, distribution=TRIANGULAR)
        y = samples(chain_of((t, -2.0)), 20_000, seed=1)
        assert y.min() >= -0.6 and y.max() <= 0.6

    def test_normal_kesilmez(self):
        # σ = 0.1/3, n = 200 000: |x − μ| > 3σ beklenen oranı 2(1 − Φ(3)) ≈ %0.27 (≈ 540 örnek)
        x = samples(chain_of((Tn(0.0, 0.1), 1.0)), N_MC, seed=5)
        p = 2.0 * (1.0 - Phi(3.0))
        frac = float(np.mean(np.abs(x) > 0.1))
        assert abs(frac - p) <= 4.0 * math.sqrt(p * (1 - p) / N_MC)

    @pytest.mark.parametrize("n", [0, 1])
    def test_n_en_az_iki(self, n):
        with pytest.raises(AssyError):
            monte_carlo(chain_A1(), n=n)


# ---------------------------------------------------------------- K6 şartname dışı


class TestRejectFraction:
    def test_A6_rss_kesin(self):
        ch = chain_of((Tn(10.0, 0.1), 1.0))
        s = 0.1 / 3.0
        p = reject_fraction(ch, 10.0 - 3.0 * s, 10.0 + 3.0 * s, method=Method.RSS)
        assert abs(p - 2.0 * (1.0 - Phi(3.0))) <= 1e-12
        assert abs(p - 0.0026997960632601866) <= 1e-12

    def test_rss_asimetrik_sinir(self):
        # μ_G kaymış: p = Φ((LSL − μ)/σ) + 1 − Φ((USL − μ)/σ)
        ch = chain_of((Tolerance(10.0, 0.0, 0.1), 1.0))  # μ = 10.05, σ = 0.05/3
        s = 0.05 / 3.0
        p = reject_fraction(ch, 10.0, 10.08)
        assert abs(p - (Phi((10.0 - 10.05) / s) + 1.0 - Phi((10.08 - 10.05) / s))) <= 1e-12

    def test_A5_monte_carlo(self):
        n = N_MC
        p = reject_fraction(chain_A5(), -0.15, 0.15, method=Method.MONTE_CARLO, n=n, seed=2)
        assert abs(p - 0.0625) <= 4.0 * math.sqrt(0.0625 * 0.9375 / n)

    def test_sifir_sigma_kesin(self):
        ch = chain_of((Tolerance(10.0), 1.0), (Tolerance(3.0), -1.0))  # G = 7, σ = 0
        assert reject_fraction(ch, 6.0, 8.0) == 0.0
        assert reject_fraction(ch, 7.5, 8.0) == 1.0
        assert reject_fraction(ch, 5.0, 6.5) == 1.0

    @pytest.mark.parametrize("lsl, usl", [(1.0, 1.0), (2.0, 1.0)])
    def test_gecersiz_sinirlar(self, lsl, usl):
        with pytest.raises(AssyError):
            reject_fraction(chain_A1(), lsl, usl)

    def test_en_kotu_durum_olasilik_vermez(self):
        with pytest.raises(AssyError):
            reject_fraction(chain_A1(), 0.0, 0.4, method=Method.WORST_CASE)


# ---------------------------------------------------------------- K7 sıfır genişlik


class TestSifirGenislik:
    def test_tum_T_sifir(self):
        ch = Chain(links=(Link(Tolerance(10.0), 1.0), Link(Tolerance(4.0), -2.0)), c=0.5)
        g0 = 0.5 + 10.0 - 8.0
        for r in (worst_case(ch), rss(ch)):
            assert close(r.nominal, g0) and close(r.mean, g0)
            assert close(r.lower, g0) and close(r.upper, g0)
            assert r.contributions == (0.0, 0.0)
            vals = [r.nominal, r.mean, r.lower, r.upper, *r.contributions]
            assert all(math.isfinite(v) for v in vals)
        assert rss(ch).sigma == 0.0


# ---------------------------------------------------------------- 3B yardımcılar


def plane(comp: str, origin=(0.0, 0.0, 0.0), normal=(0.0, 0.0, 1.0)) -> Ref:
    return Ref(comp, RefKind.PLANE, origin, normal)


def axis(comp: str, origin=(0.0, 0.0, 0.0), direction=(0.0, 0.0, 1.0)) -> Ref:
    return Ref(comp, RefKind.AXIS, origin, direction)


def point(comp: str, origin=(0.0, 0.0, 0.0)) -> Ref:
    return Ref(comp, RefKind.POINT, origin)


def exp_so3(omega) -> np.ndarray:
    """Testin kendi Rodrigues formülü: exp([ω]×) = I + sin θ K + (1 − cos θ) K²."""
    w = np.asarray(omega, dtype=float)
    th = float(np.linalg.norm(w))
    if th < 1e-15:
        return np.eye(3)
    k = w / th
    K = np.array([[0.0, -k[2], k[1]], [k[2], 0.0, -k[0]], [-k[1], k[0], 0.0]])
    return np.eye(3) + math.sin(th) * K + (1.0 - math.cos(th)) * (K @ K)


def nudge(T: np.ndarray, deg: float, dt) -> np.ndarray:
    """Başlangıç konumu: T'yi dünya (1, 2, 3) yönü etrafında deg derece döndür, dt kadar kaydır."""
    k = np.array([1.0, 2.0, 3.0]) / math.sqrt(14.0)
    return transform(exp_so3(math.radians(deg) * k) @ T[:3, :3], T[:3, 3] + np.asarray(dt, dtype=float))


def solved(asm: Assembly, tol: float = 1e-10) -> Assembly:
    """Çözülmüş kopya (girdi değişmez)."""
    work = copy.deepcopy(asm)
    solve(asm, tol=tol).apply(work)
    return work


# A8: üst üste bloklar. A sabit (yükseklik 10), B (20) ve C (15). Alt yüz – üst yüz mesafeleri D₁, D₂;
# yan yüzler (x ve y) aynı yönde çakışık (flip) → B ve C'nin serbestliği 0.
H_A, H_B, H_C = 10.0, 20.0, 15.0
D1, D2 = 5.0, 7.0


def stack_A8() -> tuple[Assembly, Ref, Ref]:
    comps = [
        Component("A", "blok_a", fixed=True),
        Component("B", "blok_b", T=nudge(transform(t=(0, 0, H_A + D1)), 3.0, (0.8, -0.5, 1.2))),
        Component("C", "blok_c", T=nudge(transform(t=(0, 0, H_A + D1 + H_B + D2)), -4.0, (-0.6, 1.0, -0.9))),
    ]
    sx, sy = (-1.0, 0.0, 0.0), (0.0, -1.0, 0.0)
    mates = [
        Mate(DIS, plane("A", (0, 0, H_A)), plane("B", (0, 0, 0), (0, 0, -1)), D1),  # 0: D₁
        Mate(C, plane("A", (0, 0, 0), sx), plane("B", (0, 0, 0), sx), flip=True),
        Mate(C, plane("A", (0, 0, 0), sy), plane("B", (0, 0, 0), sy), flip=True),
        Mate(DIS, plane("B", (0, 0, H_B)), plane("C", (0, 0, 0), (0, 0, -1)), D2),  # 3: D₂
        Mate(C, plane("B", (0, 0, 0), sx), plane("C", (0, 0, 0), sx), flip=True),
        Mate(C, plane("B", (0, 0, 0), sy), plane("C", (0, 0, 0), sy), flip=True),
    ]
    # ölçü: A alt yüzü (normal +z, PLANE–PLANE m = (p_b − p_a)·n_a) – C üst yüzü
    return Assembly("yigin", comps, mates), plane("A", (0, 0, 0), (0, 0, 1)), plane("C", (0, 0, H_C))


M0_A8 = H_A + D1 + H_B + D2 + H_C  # 57

# A9: menteşe. A sabit; kol B: CONCENTRIC (z ekseni) + düzlem çakışık + ANGLE θ (x eksenleri arası).
# Kol ucu menteşeden L uzakta; ölçü: uç noktası – A'nın taban düzlemi (y = 0, normal +y).
L_KOL, THETA = 100.0, 30.0


def hinge_A9(theta: float = THETA, start_deg: float | None = None) -> tuple[Assembly, Ref, Ref]:
    s = theta - 4.0 if start_deg is None else start_deg
    comps = [
        Component("A", "taban", fixed=True),
        Component("B", "kol", T=transform(rot_z(s) @ rot_x(2.0), (0.4, -0.3, 0.5))),
    ]
    mates = [
        Mate(CON, axis("A"), axis("B")),  # 0
        Mate(C, plane("A"), plane("B", (0, 0, 0), (0, 0, -1))),  # 1
        Mate(ANG, axis("A", (0, 0, 0), (1, 0, 0)), axis("B", (0, 0, 0), (1, 0, 0)), theta),  # 2: θ
    ]
    return Assembly("mentese", comps, mates), point("B", (L_KOL, 0, 0)), plane("A", (0, 0, 0), (0, 1, 0))


# ---------------------------------------------------------------- K8 measure


class TestMeasure:
    @staticmethod
    def asm() -> Assembly:
        TA = transform(rot_z(30.0), (1.0, 2.0, 3.0))
        TB = transform(rot_x(90.0), (10.0, -4.0, 6.0))
        return Assembly("olcu", [Component("A", "a", T=TA, fixed=True), Component("B", "b", T=TB)])

    @staticmethod
    def world(T, p) -> np.ndarray:
        return T[:3, :3] @ np.asarray(p, dtype=float) + T[:3, 3]

    def test_nokta_duzlem_iki_sira(self):
        asm = self.asm()
        TA, TB = asm.component("A").T, asm.component("B").T
        P = point("B", (1.0, 2.0, 3.0))
        Q = plane("A", (0.5, -1.0, 2.0), (1.0, 1.0, 0.0))
        p, q = self.world(TB, P.origin), self.world(TA, Q.origin)
        n = TA[:3, :3] @ np.array([1.0, 1.0, 0.0]) / math.sqrt(2.0)
        m = float((p - q) @ n)  # işaretli: normal tarafı +
        assert close(measure(asm, P, Q), m)
        assert close(measure(asm, Q, P), m)

    def test_nokta_duzlem_isaret(self):
        # nokta normalin öbür tarafında → negatif
        asm = Assembly("s", [Component("A", "a", fixed=True), Component("B", "b", T=transform(t=(0, 0, -4)))])
        assert close(measure(asm, point("B"), plane("A")), -4.0)

    def test_duzlem_duzlem(self):
        asm = self.asm()
        TA, TB = asm.component("A").T, asm.component("B").T
        Pa = plane("A", (0.0, 1.0, 0.0), (0.0, 0.0, 1.0))
        Pb = plane("B", (2.0, 0.0, 5.0), (0.0, 1.0, 0.0))
        na = TA[:3, :3] @ np.array([0.0, 0.0, 1.0])
        m = float((self.world(TB, Pb.origin) - self.world(TA, Pa.origin)) @ na)
        assert close(measure(asm, Pa, Pb), m)
        # sıra değişince n_a da değişir: (p_a − p_b)·n_b
        nb = TB[:3, :3] @ np.array([0.0, 1.0, 0.0])
        m2 = float((self.world(TA, Pa.origin) - self.world(TB, Pb.origin)) @ nb)
        assert close(measure(asm, Pb, Pa), m2)

    def test_nokta_nokta(self):
        asm = self.asm()
        TA, TB = asm.component("A").T, asm.component("B").T
        Pa, Pb = point("A", (1.0, 0.0, 0.0)), point("B", (0.0, 3.0, -2.0))
        m = float(np.linalg.norm(self.world(TB, Pb.origin) - self.world(TA, Pa.origin)))
        assert close(measure(asm, Pa, Pb), m)
        assert close(measure(asm, Pb, Pa), m)

    @pytest.mark.parametrize(
        "a, b",
        [
            (axis("A"), axis("B")),
            (axis("A"), point("B")),
            (point("A"), axis("B")),
            (plane("A"), axis("B")),
        ],
    )
    def test_desteklenmeyen_cift(self, a, b):
        with pytest.raises(AssyError):
            measure(self.asm(), a, b)


# ---------------------------------------------------------------- K9 A8 üst üste bloklar


class TestA8:
    def test_kurulum(self):
        # testin kendi sağlaması: çözülmüş konumda ölçü kapalı formda, serbestlik 0
        asm, a, b = stack_A8()
        assert dof(asm) == 0
        assert abs(measure(solved(asm), a, b) - M0_A8) <= TOL_3B

    def test_katsayilar_ve_sabit(self):
        asm, a, b = stack_A8()
        ch = assembly_chain(asm, {0: Tn(D1, 0.1, name="D1"), 3: Tn(D2, 0.2)}, a, b)
        assert len(ch.links) == 2
        assert [L.name for L in ch.links] == ["D1", "kisit 3"]
        assert abs(ch.links[0].a - 1.0) <= TOL_3B
        assert abs(ch.links[1].a - 1.0) <= TOL_3B
        assert abs(ch.c - (M0_A8 - D1 - D2)) <= TOL_3B
        assert abs(ch.nominal - M0_A8) <= TOL_3B  # G₀ = m₀

    def test_1b_zincirle_ayni(self):
        asm, a, b = stack_A8()
        ch3 = assembly_chain(asm, {0: Tn(D1, 0.1), 3: Tn(D2, 0.2)}, a, b)
        ch1 = chain_of((Tn(D1, 0.1), 1.0), (Tn(D2, 0.2), 1.0), c=M0_A8 - D1 - D2)
        for f in (worst_case, rss):
            r3, r1 = f(ch3), f(ch1)
            for attr in ("nominal", "mean", "lower", "upper"):
                assert abs(getattr(r3, attr) - getattr(r1, attr)) <= TOL_3B
            assert r3.contributions == pytest.approx(r1.contributions, abs=TOL_3B)
        assert abs(worst_case(ch3).upper - (M0_A8 + 0.3)) <= TOL_3B
        assert abs(rss(ch3).sigma - math.sqrt(0.05) / 3.0) <= TOL_3B

    def test_tolerans_nesnesi_korunur(self):
        # halka toleransı verilen nesnedir (dağılım ve sapmalar korunur)
        asm, a, b = stack_A8()
        t = Tolerance(D2, -0.1, 0.3, distribution=UNIFORM, name="pul")
        ch = assembly_chain(asm, {3: t}, a, b)
        assert ch.links[0].tol == t
        assert abs(ch.mean - (M0_A8 + 0.1)) <= TOL_3B


# ---------------------------------------------------------------- K10 A9 menteşe


class TestA9:
    def test_kurulum(self):
        asm, tip, base = hinge_A9()
        assert dof(asm) == 0
        assert abs(measure(solved(asm), tip, base) - 50.0) <= TOL_3B

    def test_aci_katsayisi(self):
        asm, tip, base = hinge_A9()
        ch = assembly_chain(asm, {2: Tn(THETA, 0.1)}, tip, base)
        a_exp = L_KOL * math.cos(math.radians(THETA)) * math.pi / 180.0
        assert abs(a_exp - 1.5114994701951815) <= 1e-12  # testin kendi sağlaması
        assert abs(ch.links[0].a - a_exp) <= TOL_3B
        assert ch.links[0].name == "kisit 2"
        assert abs(ch.nominal - 50.0) <= TOL_3B
        r = worst_case(ch)
        assert abs(half(r) - 0.1 * a_exp) <= TOL_3B
        assert abs(r.upper - (50.0 + 0.15114994701951815)) <= TOL_3B

    def test_eksen_etrafinda_serbestlik_olcuyu_etkilemez(self):
        # mil: CONCENTRIC + omuz mesafesi → dof 1 (kendi ekseni etrafında dönme). Eksen dışındaki
        # noktanın taban düzlemine uzaklığı bu dönmeyle değişmez → hata yok, a = 1
        comps = [
            Component("A", "govde", fixed=True),
            Component("S", "mil", T=transform(rot_z(20.0) @ rot_x(3.0), (10.5, 19.6, 5.4))),
        ]
        mates = [
            Mate(CON, axis("A", (10.0, 20.0, 0.0)), axis("S")),
            Mate(DIS, plane("A"), plane("S", (0, 0, 0), (0, 0, -1)), 5.0),
        ]
        asm = Assembly("mil", comps, mates)
        assert dof(asm) == 1
        tip, base = point("S", (3.0, 0.0, 40.0)), plane("A", (0, 0, -10.0))
        ch = assembly_chain(asm, {1: Tn(5.0, 0.1)}, tip, base)
        assert abs(ch.links[0].a - 1.0) <= TOL_3B
        assert abs(ch.nominal - 55.0) <= TOL_3B


# ---------------------------------------------------------------- K11 merkezi fark


def random_assembly(seed: int) -> tuple[Assembly, Ref, Ref, dict[int, Tolerance]]:
    """Rastgele dönük sabit blok A, üstünde blok B (D₁), B'ye menteşeli kol K (eksen kaçık, D₂, θ).
    Ölçü: kol ucu – A'nın eğik düzlemi. Tüm a_j sıfırdan farklı."""
    rng = np.random.default_rng(seed)
    TA = transform(exp_so3(rng.uniform(-0.6, 0.6, 3)), rng.uniform(-50.0, 50.0, 3))
    d1, d2 = float(rng.uniform(3.0, 8.0)), float(rng.uniform(1.0, 4.0))
    th = float(rng.uniform(25.0, 65.0))
    hA, hB, L = float(rng.uniform(5, 15)), float(rng.uniform(10, 30)), float(rng.uniform(60, 120))
    cx, cy = float(rng.uniform(-5, 5)), float(rng.uniform(-5, 5))
    TB = TA @ transform(t=(0, 0, hA + d1))
    TK = TA @ transform(rot_z(th), (cx, cy, hA + d1 + hB + d2))
    comps = [
        Component("A", "a", T=TA, fixed=True),
        Component("B", "b", T=nudge(TB, 2.0, (0.4, -0.3, 0.5))),
        Component("K", "kol", T=nudge(TK, -2.0, (-0.3, 0.6, 0.2))),
    ]
    sx, sy = (-1.0, 0.0, 0.0), (0.0, -1.0, 0.0)
    mates = [
        Mate(DIS, plane("A", (0, 0, hA)), plane("B", (0, 0, 0), (0, 0, -1)), d1),  # 0
        Mate(C, plane("A", (0, 0, 0), sx), plane("B", (0, 0, 0), sx), flip=True),  # 1
        Mate(C, plane("A", (0, 0, 0), sy), plane("B", (0, 0, 0), sy), flip=True),  # 2
        Mate(CON, axis("B", (cx, cy, hB)), axis("K")),  # 3
        Mate(DIS, plane("B", (0, 0, hB)), plane("K", (0, 0, 0), (0, 0, -1)), d2),  # 4
        Mate(ANG, axis("B", (0, 0, 0), (1, 0, 0)), axis("K", (0, 0, 0), (1, 0, 0)), th),  # 5
    ]
    tols = {0: Tn(d1, 0.1), 4: Tn(d2, 0.05), 5: Tn(th, 0.2)}
    n = (0.0, 1.0, 1.0)
    return Assembly("rastgele", comps, mates), point("K", (L, 0, 2.0)), plane("A", (0, 0, 0), n), tols


@pytest.mark.parametrize("seed", [0, 1, 2])
def test_K11_merkezi_fark(seed):
    asm, tip, base, tols = random_assembly(seed)
    ch = assembly_chain(asm, tols, tip, base)
    assert len(ch.links) == len(tols)
    base_asm = solved(asm)  # sıcak başlangıç: aynı dal
    m0 = measure(base_asm, tip, base)
    assert abs(ch.nominal - m0) <= TOL_3B
    h = 1e-6
    for L, j in zip(ch.links, sorted(tols), strict=True):
        m = []
        for s in (+1.0, -1.0):
            w = copy.deepcopy(base_asm)
            w.mates[j].value += s * h
            m.append(measure(solved(w), tip, base))
        fd = (m[0] - m[1]) / (2.0 * h)
        assert abs(fd) > 1e-3  # testin kendi sağlaması: etkisiz halka yok
        assert abs(L.a - fd) <= 1e-6


# ---------------------------------------------------------------- K12 hatalar


class TestHatalar:
    @pytest.mark.parametrize("j", [3, 7, -1])
    def test_sira_aralik_disinda(self, j):
        asm, tip, base = hinge_A9()
        with pytest.raises(AssyError):
            assembly_chain(asm, {j: Tn(THETA, 0.1)}, tip, base)

    @pytest.mark.parametrize("j", [0, 1])
    def test_mesafe_aci_disi_kisit(self, j):
        # 0: CONCENTRIC, 1: COINCIDENT → tolerans verilemez
        asm, tip, base = hinge_A9()
        with pytest.raises(AssyError):
            assembly_chain(asm, {j: Tn(0.0, 0.1)}, tip, base)

    @pytest.mark.parametrize("theta, start", [(0.0, 3.0), (180.0, 177.0)])
    def test_aci_0_180(self, theta, start):
        asm, tip, base = hinge_A9(theta=theta, start_deg=start)
        with pytest.raises(AssyError):
            assembly_chain(asm, {2: Tn(theta, 0.1)}, tip, base)

    def test_nominal_kisit_degerinden_farkli(self):
        asm, tip, base = hinge_A9()
        with pytest.raises(AssyError):
            assembly_chain(asm, {2: Tn(THETA + 0.001, 0.1)}, tip, base)
        a8, a, b = stack_A8()
        with pytest.raises(AssyError):
            assembly_chain(a8, {0: Tn(D1 + 1e-9, 0.1)}, a, b)

    def test_bos_sozluk(self):
        asm, tip, base = hinge_A9()
        with pytest.raises(AssyError):
            assembly_chain(asm, {}, tip, base)

    def test_olcu_belirsiz(self):
        # B yalnız x yüzleri arası mesafeyle bağlı: z yönünde serbest öteleme ölçüyü (z) değiştirir
        comps = [Component("A", "a", fixed=True), Component("B", "b", T=transform(t=(5.3, 0.2, 12.0)))]
        mates = [Mate(DIS, plane("A", (0, 0, 0), (1, 0, 0)), plane("B", (0, 0, 0), (-1, 0, 0)), 5.0)]
        asm = Assembly("belirsiz", comps, mates)
        assert dof(asm) > 0
        with pytest.raises(AssyError):
            assembly_chain(asm, {0: Tn(5.0, 0.1)}, point("B", (0, 0, 8.0)), plane("A"))

    def test_desteklenmeyen_olcu_cifti(self):
        asm, _, _ = hinge_A9()
        with pytest.raises(AssyError):
            assembly_chain(asm, {2: Tn(THETA, 0.1)}, axis("B"), axis("A"))

    def test_girdi_degismez(self):
        asm, tip, base = hinge_A9()
        T0 = {c.name: c.T.copy() for c in asm.components}
        v0 = [m.value for m in asm.mates]
        assembly_chain(asm, {2: Tn(THETA, 0.1)}, tip, base)
        for c in asm.components:
            assert np.array_equal(c.T, T0[c.name])
        assert [m.value for m in asm.mates] == v0
