"""
Tolerans yığılımı (SPEC 34).

1B ölçü zinciri  G = c + Σ a_i x_i : en kötü durum, istatistiksel (RSS), Monte Carlo; katkı payları ve
şartname dışı oranı. 3B: montajdaki DISTANCE / ANGLE kısıt değerlerine verilen toleranslar, SPEC 08
Jacobian'ı ve örtük fonksiyon teoremiyle doğrusal zincire çevrilir.

Kaynak: Fortini, Dimensioning for Interchangeable Manufacture (1967); Chase–Parkinson (1991);
Drake, Dimensioning and Tolerancing Handbook, Bölüm 9.

Birimler: mm, açı derece. Tüm hatalar AssyError.
"""

from __future__ import annotations

import copy
import math
from dataclasses import dataclass, replace
from enum import StrEnum

import numpy as np

from assy.mates import jacobian, residual, skew
from assy.model import Assembly, AssyError, Distribution, Mate, MateKind, Ref, RefKind, Tolerance
from assy.solver import solve

# Sayısal rank ve serbest yön eşiği (SPEC 08 ile aynı): σ_i > 1e-8 σ_max
_RANK_TOL = 1e-8
# 3B hassasiyet katsayısı bunun altındaysa tolerans ölçüyü etkilemiyor sayılır
_A_SIFIR = 1e-12
# ANGLE türevi için merkezi fark adımı (derece); artık cos θ'da düzgün, hata ~h²
_H_ACI = 1e-4


class Method(StrEnum):
    WORST_CASE = "en_kotu"
    RSS = "rss"
    MONTE_CARLO = "monte_carlo"


def _sonlu(x: float, ad: str) -> float:
    if not isinstance(x, (int, float, np.floating, np.integer)) or not math.isfinite(x):
        raise AssyError(f"{ad} sonlu bir sayı olmalı ({x!r})")
    return float(x)


def _phi(z: float) -> float:
    """Standart normal dağılım fonksiyonu Φ(z) = ½ erfc(−z/√2) (kuyrukta hassas)."""
    return 0.5 * math.erfc(-z / math.sqrt(2.0))


@dataclass(frozen=True)
class Link:
    """Zincir halkası: tolerans ve hassasiyet katsayısı a (sonlu, sıfırdan farklı)."""

    tol: Tolerance
    a: float = 1.0
    name: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.tol, Tolerance):
            raise AssyError(f"Halka toleransı Tolerance olmalı ({self.tol!r})")
        a = _sonlu(self.a, "Hassasiyet katsayısı a")
        if a == 0.0:
            raise AssyError(f"Halka '{self.name}': a = 0 (etkisiz halka)")
        object.__setattr__(self, "a", a)


@dataclass(frozen=True)
class Chain:
    """G = c + Σ a_i x_i. Boş zincir → AssyError."""

    links: tuple[Link, ...]
    c: float = 0.0

    def __post_init__(self) -> None:
        links = tuple(self.links)
        if not links:
            raise AssyError("Boş ölçü zinciri")
        for i, link in enumerate(links):
            if not isinstance(link, Link):
                raise AssyError(f"Zincir elemanı {i} Link değil ({link!r})")
        object.__setattr__(self, "links", links)
        object.__setattr__(self, "c", _sonlu(self.c, "Sabit terim c"))

    @property
    def a(self) -> np.ndarray:
        return np.array([link.a for link in self.links])

    @property
    def nominal(self) -> float:
        """G₀ = c + Σ a_i x₀_i"""
        return self.c + float(self.a @ np.array([link.tol.nominal for link in self.links]))

    @property
    def mean(self) -> float:
        """μ_G = c + Σ a_i μ_i"""
        return self.c + float(self.a @ np.array([link.tol.mean for link in self.links]))

    @property
    def sigma(self) -> float:
        """σ_G = √(Σ a_i² σ_i²)"""
        return math.sqrt(float(np.sum((self.a * self._sigmas()) ** 2)))

    def _sigmas(self) -> np.ndarray:
        return np.array([link.tol.sigma for link in self.links])

    def _var_paylari(self) -> tuple[float, ...]:
        v = (self.a * self._sigmas()) ** 2
        return _paylar(v)


def _paylar(w: np.ndarray) -> tuple[float, ...]:
    """w / Σw; Σw = 0 → hepsi 0 (bölme yok)."""
    toplam = float(np.sum(w))
    if toplam == 0.0:
        return tuple(0.0 for _ in w)
    return tuple(float(x) for x in w / toplam)


def _k(k: float) -> float:
    k = _sonlu(k, "Kapsama katsayısı k")
    if k <= 0:
        raise AssyError(f"Kapsama katsayısı k pozitif olmalı ({k})")
    return k


@dataclass(frozen=True)
class StackResult:
    method: Method
    nominal: float
    mean: float
    lower: float
    upper: float
    sigma: float | None  # WORST_CASE: None
    contributions: tuple[float, ...]  # halka sırasıyla, toplam 1 (hepsi T = 0 ise 0)


def worst_case(chain: Chain) -> StackResult:
    """T_wc = Σ |a_i| T_i,  G ∈ [μ_G − T_wc, μ_G + T_wc]."""
    w = np.abs(chain.a) * np.array([link.tol.half_width for link in chain.links])
    T_wc = float(np.sum(w))
    mu = chain.mean
    return StackResult(Method.WORST_CASE, chain.nominal, mu, mu - T_wc, mu + T_wc, None, _paylar(w))


def rss(chain: Chain, k: float = 3.0) -> StackResult:
    """σ_G = √(Σ a_i² σ_i²),  G ∈ [μ_G − k σ_G, μ_G + k σ_G]."""
    k = _k(k)
    mu, s = chain.mean, chain.sigma
    return StackResult(Method.RSS, chain.nominal, mu, mu - k * s, mu + k * s, s, chain._var_paylari())


def _n(n: int, en_az: int) -> int:
    if isinstance(n, bool) or not isinstance(n, (int, np.integer)) or n < en_az:
        raise AssyError(f"Örnek sayısı n en az {en_az} olan bir tamsayı olmalı ({n!r})")
    return int(n)


def _ornekle(tol: Tolerance, rng: np.random.Generator, n: int) -> np.ndarray:
    """Tek ölçünün n örneği; bant μ ± T. NORMAL kesilmez."""
    mu, T = tol.mean, tol.half_width
    if T == 0.0:
        return np.full(n, mu)
    if tol.distribution is Distribution.NORMAL:
        return rng.normal(mu, tol.sigma, n)
    if tol.distribution is Distribution.UNIFORM:
        return rng.uniform(mu - T, mu + T, n)
    if tol.distribution is Distribution.TRIANGULAR:
        return rng.triangular(mu - T, mu, mu + T, n)
    raise AssyError(f"Bilinmeyen dağılım: {tol.distribution!r}")


def samples(chain: Chain, n: int, seed: int = 0) -> np.ndarray:
    """G örnekleri (n,); aynı seed → aynı dizi."""
    n = _n(n, 1)
    rng = np.random.default_rng(seed)
    G = np.full(n, chain.c)
    for link in chain.links:
        G += link.a * _ornekle(link.tol, rng, n)
    return G


def monte_carlo(chain: Chain, n: int = 100_000, seed: int = 0, k: float = 3.0) -> StackResult:
    """Örnek ortalaması, örnek std (ddof=1), sınırlar Φ(−k) ve Φ(k) ampirik yüzdelikleri."""
    k = _k(k)
    G = samples(chain, _n(n, 2), seed)
    alt, ust = np.quantile(G, [_phi(-k), _phi(k)])
    return StackResult(
        Method.MONTE_CARLO,
        chain.nominal,
        float(np.mean(G)),
        float(alt),
        float(ust),
        float(np.std(G, ddof=1)),
        chain._var_paylari(),
    )


def reject_fraction(
    chain: Chain,
    lsl: float,
    usl: float,
    method: Method = Method.RSS,
    n: int = 100_000,
    seed: int = 0,
) -> float:
    """G < LSL veya G > USL olasılığı (RSS: normal yaklaşım, MONTE_CARLO: örnek oranı)."""
    lsl, usl = _sonlu(lsl, "LSL"), _sonlu(usl, "USL")
    if lsl >= usl:
        raise AssyError(f"LSL < USL olmalı ({lsl} ≥ {usl})")
    method = Method(method)
    if method is Method.WORST_CASE:
        raise AssyError("En kötü durum yöntemi olasılık vermez; RSS veya MONTE_CARLO kullanın")
    if method is Method.MONTE_CARLO:
        G = samples(chain, _n(n, 2), seed)
        return float(np.mean((G < lsl) | (G > usl)))
    mu, s = chain.mean, chain.sigma
    if s == 0.0:
        return 0.0 if lsl <= mu <= usl else 1.0
    return _phi((lsl - mu) / s) + _phi(-(usl - mu) / s)


# --- 3B ---------------------------------------------------------------------------------------------


def _dunya(
    assembly: Assembly, ref: Ref, unknowns: list[str]
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Dünya origin'i p, birim yön d ve türevleri ∂p/∂q, ∂d/∂q (3, 6·n).

    δp = Δt − [R p0]× ω,  δd = −[d]× ω  (SPEC 08)."""
    p, d = assembly.world(ref)
    dp = np.zeros((3, 6 * len(unknowns)))
    dd = np.zeros((3, 6 * len(unknowns)))
    if ref.component in unknowns:
        i = unknowns.index(ref.component)
        R = assembly.component(ref.component).T[:3, :3]
        dp[:, 6 * i : 6 * i + 3] = np.eye(3)
        dp[:, 6 * i + 3 : 6 * i + 6] = -skew(R @ np.array(ref.origin))
        dd[:, 6 * i + 3 : 6 * i + 6] = -skew(d)
    return p, d, dp, dd


def _olcu(assembly: Assembly, a: Ref, b: Ref, unknowns: list[str]) -> tuple[float, np.ndarray]:
    """Ölçü m ve gradyeni ∇_q m (6·n,)."""
    pa, da, dpa, dda = _dunya(assembly, a, unknowns)
    pb, db, dpb, ddb = _dunya(assembly, b, unknowns)
    ka, kb = a.kind, b.kind
    if {ka, kb} == {RefKind.POINT, RefKind.PLANE}:
        if ka is RefKind.POINT:
            p, dp, q, dq, n, dn = pa, dpa, pb, dpb, db, ddb
        else:
            p, dp, q, dq, n, dn = pb, dpb, pa, dpa, da, dda
        v = p - q
        return float(v @ n), n @ (dp - dq) + v @ dn
    if ka is kb is RefKind.PLANE:
        v = pb - pa
        return float(v @ da), da @ (dpb - dpa) + v @ dda
    if ka is kb is RefKind.POINT:
        v = pb - pa
        L = float(np.linalg.norm(v))
        if L < 1e-12:
            raise AssyError("POINT–POINT ölçüsünde noktalar çakışık: türev tanımsız")
        return L, (v / L) @ (dpb - dpa)
    raise AssyError(f"Desteklenmeyen ölçü çifti: {ka.name}–{kb.name}")


def measure(assembly: Assembly, a: Ref, b: Ref) -> float:
    """POINT–PLANE (p − q)·n, PLANE–PLANE (p_b − p_a)·n_a, POINT–POINT |p_b − p_a|."""
    pa, da = assembly.world(a)
    pb, db = assembly.world(b)
    ka, kb = a.kind, b.kind
    if {ka, kb} == {RefKind.POINT, RefKind.PLANE}:
        p, q, n = (pa, pb, db) if ka is RefKind.POINT else (pb, pa, da)
        return float((p - q) @ n)
    if ka is kb is RefKind.PLANE:
        return float((pb - pa) @ da)
    if ka is kb is RefKind.POINT:
        return float(np.linalg.norm(pb - pa))
    raise AssyError(f"Desteklenmeyen ölçü çifti: {ka.name}–{kb.name}")


def _dr_dp(assembly: Assembly, mate: Mate) -> np.ndarray:
    """∂r/∂p: kısıt değerine göre artığın türevi (mesafe: −1 son satırda; açı: sin θ · π/180).

    flip ve satır düzeni SPEC 08'deki gibi kalsın diye artık değer değiştirilerek hesaplanır:
    mesafede artık D'ye doğrusal (ileri fark kesin), açıda merkezi fark."""
    v = mate.value
    if mate.kind is MateKind.DISTANCE:
        h = 1.0
        return residual(assembly, replace(mate, value=v + h)) - residual(assembly, mate)
    h = _H_ACI
    return (
        residual(assembly, replace(mate, value=v + h)) - residual(assembly, replace(mate, value=v - h))
    ) / (2 * h)


def assembly_chain(
    assembly: Assembly, tolerances: dict[int, Tolerance], a: Ref, b: Ref, tol: float = 1e-10
) -> Chain:
    """Montajdan doğrusal zincir: a_j = ∂m/∂p_j (δq = −J_q⁺ J_p δp), c = m₀ − Σ a_j p₀_j."""
    if not tolerances:
        raise AssyError("Tolerans sözlüğü boş")
    mates = assembly.mates
    for j, t in tolerances.items():
        if isinstance(j, bool) or not isinstance(j, (int, np.integer)) or not 0 <= j < len(mates):
            raise AssyError(f"Kısıt sırası aralık dışında: {j!r} (kısıt sayısı {len(mates)})")
        if not isinstance(t, Tolerance):
            raise AssyError(f"Kısıt {j}: tolerans Tolerance olmalı ({t!r})")
        m = mates[j]
        if m.kind not in (MateKind.DISTANCE, MateKind.ANGLE):
            raise AssyError(f"Kısıt {j}: yalnız DISTANCE ve ANGLE kısıtına tolerans verilir ({m.kind.name})")
        if m.kind is MateKind.ANGLE and m.value in (0.0, 180.0):
            raise AssyError(f"Kısıt {j}: 0°/180° açı kısıtına tolerans verilemez (θ'ya bağlı satır yok)")
        if abs(t.nominal - m.value) > 1e-12:
            raise AssyError(f"Kısıt {j}: tolerans nominali {t.nominal} ≠ kısıt değeri {m.value}")

    work = copy.deepcopy(assembly)
    solve(work, tol=tol).apply(work)
    unknowns = [c.name for c in work.components if not c.fixed]

    m0, grad = _olcu(work, a, b, unknowns)
    sira = sorted(tolerances)
    satirlar = [residual(work, m).size for m in mates]
    bas = np.concatenate([[0], np.cumsum(satirlar)]).astype(int)
    Jq = (
        np.vstack([jacobian(work, m, unknowns) for m in mates]) if mates else np.zeros((0, 6 * len(unknowns)))
    )
    Jp = np.zeros((Jq.shape[0], len(sira)))
    for k, j in enumerate(sira):
        Jp[bas[j] : bas[j + 1], k] = _dr_dp(work, mates[j])

    # Belirsiz ölçü: ∇_q m, J_q'nun sıfır uzayında bileşen içeriyorsa
    if Jq.size:
        _, s, Vt = np.linalg.svd(Jq)
        rank = int(np.sum(s > _RANK_TOL * s[0])) if s.size and s[0] > 0 else 0
        N = Vt[rank:]
    else:
        N = np.eye(6 * len(unknowns))
    if N.size and np.max(np.abs(N @ grad)) > 1e-8 * max(1.0, float(np.linalg.norm(grad))):
        raise AssyError("Ölçü belirsiz: montajda ölçüyü değiştiren serbestlik kaldı")

    if Jq.size:
        dq_dp = -np.linalg.lstsq(Jq, Jp, rcond=None)[0]  # en küçük normlu
        a_j = grad @ dq_dp
    else:
        a_j = np.zeros(len(sira))

    links = []
    for k, j in enumerate(sira):
        t = tolerances[j]
        if abs(a_j[k]) <= _A_SIFIR:
            raise AssyError(f"Kısıt {j}: toleransı ölçüyü etkilemiyor (a = {a_j[k]:.3g})")
        links.append(Link(t, float(a_j[k]), t.name or f"kisit {j}"))
    c = m0 - sum(link.a * link.tol.nominal for link in links)
    return Chain(tuple(links), c)
