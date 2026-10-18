# SPEC 34 — Tolerans yığılımı (Dalga 5, hat H8)

## Amaç
Bir ölçü zincirinin (1B) ve kısıtlarla kurulmuş bir montajın (3B) kapanış ölçüsünü toleranslardan
**en kötü durum**, **istatistiksel (RSS)** ve **Monte Carlo** ile hesaplayan, her toleransın katkı payını ve
şartname dışı oranını veren saf numpy modülü (`assy/tolerans.py`).

## Ön koşullar
- SPEC 08 (`assy/mates.py`, `assy/solver.py`) — `main`'de.
- Arayüz A1: `assy/model.py`'ye `Tolerance` ve `Distribution` (sahibi "Dalga 2 arayüz ekleri" thread'i,
  ayrı arayüz PR'ı). Bu SPEC'in beklediği tam arayüz aşağıda "Arayüz → A1" başlığındadır; SPEC 34 PR'ı
  `assy/model.py`'yi değiştirmez.

## Teori

### Tek toleranslı ölçü
Bir ölçü `x`, nominal `x₀` ve sapmalarla verilir: `x ∈ [x₀ + l, x₀ + u]`, `l ≤ u` (ISO 286 gibi:
`10 +0.1/−0` → `l = 0`, `u = 0.1`).
```
orta değer   μ = x₀ + (l + u)/2
yarı genişlik T = (u − l)/2
```
Standart sapma dağılıma göre (bant `μ ± T`):

| Dağılım | σ | Not |
|---|---|---|
| NORMAL | `T / k` | `k = sigma_level` (varsayılan 3: bant ±3σ, Cp = 1) |
| UNIFORM (düzgün) | `T / √3` | |
| TRIANGULAR (üçgen, simetrik) | `T / √6` | |

`T = 0` (temel ölçü) izinlidir: `σ = 0`, ölçü sabittir.
Kaynak: Fortini, *Dimensioning for Interchangeable Manufacture* (1967); Chase–Parkinson, "A survey of research
in the application of tolerance analysis to the design of mechanical assemblies", *Research in Engineering
Design* 3 (1991); Drake, *Dimensioning and Tolerancing Handbook*, Bölüm 9.

### Doğrusal zincir
Kapanış ölçüsü (boşluk) `G`, hassasiyet katsayıları `a_i` ile:
```
G = c + Σ a_i x_i
```
`a_i = +1` artıran, `−1` azaltan halka; `|a_i| ≠ 1` kaldıraç / eğik ölçü (3B'de Jacobian'dan gelir).
`c`: sabit terim (1B'de çoğunlukla 0; 3B doğrusallaştırmada kullanılır).
```
nominal   G₀ = c + Σ a_i x₀_i
orta      μ_G = c + Σ a_i μ_i
```

**En kötü durum (aritmetik):**
```
T_wc = Σ |a_i| T_i          G ∈ [μ_G − T_wc, μ_G + T_wc]
katkı_i = |a_i| T_i / T_wc
```

**İstatistiksel (RSS), bağımsız halkalar:**
```
σ_G = √( Σ a_i² σ_i² )      G ∈ [μ_G − k σ_G, μ_G + k σ_G]      (k: sonucun kapsama katsayısı, varsayılan 3)
katkı_i = a_i² σ_i² / σ_G²
```
Tüm halkalar NORMAL ve `sigma_level = k` iken bu, klasik `T_rss = √(Σ (a_i T_i)²)` ile aynıdır.

**Monte Carlo:** her halka kendi dağılımından bağımsız örneklenir (`np.random.default_rng(seed)`),
`G` örnekleri doğrudan toplanır. NORMAL örnekler **kesilmez** (bant dışı parça üretimde de olur).
Sonuç: örnek ortalaması, örnek standart sapması (`ddof = 1`), ve `G` sınırları olarak
`Φ(−k)` ve `Φ(k)` ampirik yüzdelikleri (`k = 3` → %0.135 ve %99.865).

**Şartname dışı oranı** (alt/üst sınır `LSL`, `USL`):
```
RSS (normal yaklaşım):  p = Φ((LSL − μ_G)/σ_G) + 1 − Φ((USL − μ_G)/σ_G)
Monte Carlo:            p = (G < LSL veya G > USL olan örnek sayısı) / n
Φ(z) = ½ (1 + erf(z/√2))        (math.erf; scipy gerekmez)
```
`σ_G = 0` iken RSS oranı kesindir: `μ_G` sınırlar içindeyse 0, dışındaysa 1.

### 3B: montajdan doğrusal zincir (SPEC 08 Jacobian'ı)
Tolerans parametreleri `p`: montajdaki **DISTANCE** (mm) ve **ANGLE** (derece) kısıtlarının `value`'su.
Ölçülen büyüklük `m(q)`: iki referans arasında, SPEC 08 mesafe tanımlarıyla aynı işaretle:

| Referans çifti | m |
|---|---|
| POINT–PLANE (her iki sıra) | `(p − q)·n` (işaretli, normal tarafı +) |
| PLANE–PLANE | `(p_b − p_a)·n_a` |
| POINT–POINT | `|p_b − p_a|` |

Çözülmüş konumda kısıtlar `r(q, p) = 0`. Örtük fonksiyon teoremiyle, SPEC 08 çözücüsüyle tutarlı (en küçük normlu):
```
δq = −J_q⁺ J_p δp            J_q = ∂r/∂q (SPEC 08 jacobian), J_p = ∂r/∂p
a_j = ∂m/∂p_j = ∇_q m · (δq/δp_j)
∂r/∂D = −1 (mesafe satırı)     ∂r/∂θ = sin θ · π/180 (açı satırı, derece başına)
```
SPEC 08'in ölçekli artıkları (yön satırları `L` ile çarpılmış) satır ölçeklemesidir; `δq`'yu değiştirmez.
Zincir: `a_j` katsayıları, `c = m₀ − Σ a_j p₀_j` (`m₀`: nominal konumda ölçü). Böylece 3B sonuç aynı
`worst_case` / `rss` / `monte_carlo` işlevleriyle hesaplanır. Doğrusallaştırmadır: büyük açı toleranslarında
gerçek dağılımdan sapar (Kapsam dışı: doğrusal olmayan 3B Monte Carlo).

**Belirsiz ölçü:** montajda serbestlik kaldıysa (`dof > 0`) ve `∇_q m` serbest yönlerde bileşen içeriyorsa
(`|∇_q m · N| > 1e-8 · max(1, |∇_q m|)`, `N`: `J_q` sıfır uzayının birim tabanı), ölçü kısıtlarca belirlenmiyordur
→ `AssyError` ("ölçü belirsiz"). Serbest yön ölçüyü etkilemiyorsa (ör. milin kendi ekseni etrafında dönmesi)
hesap yapılır.

## Dosyalar
- Yeni: `assy/tolerans.py`, `tests/assy/test_tolerans.py`, `durum/34-tolerans.md`
- Okunur (değişmez): `assy/model.py` (A1 sonrası), `assy/mates.py`, `assy/solver.py`
- Dokunulmayacak: diğer paketler, ortak dosyalar (`assy/model.py` dahil; A1 ayrı PR)

## Arayüz

### A1 — `assy/model.py` (ayrı arayüz PR'ı, bu SPEC'in beklentisi)
```python
class Distribution(StrEnum):
    NORMAL = "normal"
    UNIFORM = "duzgun"
    TRIANGULAR = "ucgen"


@dataclass(frozen=True)
class Tolerance:
    """Toleranslı ölçü. lower/upper: nominale göre sapma (mm veya derece), lower ≤ upper."""

    nominal: float
    lower: float = 0.0
    upper: float = 0.0
    distribution: Distribution = Distribution.NORMAL
    sigma_level: float = 3.0  # yalnız NORMAL: bant = ±sigma_level·σ
    name: str = ""

    @property
    def mean(self) -> float: ...  # nominal + (lower + upper)/2
    @property
    def half_width(self) -> float: ...  # (upper − lower)/2
    @property
    def sigma(self) -> float: ...  # tablo: T/k, T/√3, T/√6
    def to_dict(self) -> dict: ...  # distribution .value olarak
    @classmethod
    def from_dict(cls, d: dict) -> Tolerance: ...
```
`__post_init__`: `distribution` dizeden çevrilir; `nominal, lower, upper, sigma_level` sonlu;
`lower ≤ upper`; `sigma_level > 0`; aksi → `AssyError`.
Ayrıca simetrik kısa yol: `Tolerance.symmetric(nominal, t, distribution=NORMAL, sigma_level=3.0, name="")` →
`lower = −t, upper = +t`, `t ≥ 0`.

### `assy/tolerans.py`
- `@dataclass(frozen=True) Link`: `tol: Tolerance`, `a: float = 1.0`, `name: str = ""` —
  `a` sonlu ve sıfırdan farklı, aksi → `AssyError` (etkisiz halka sessizce yutulmaz).
- `@dataclass(frozen=True) Chain`: `links: tuple[Link, ...]`, `c: float = 0.0` — boş zincir → `AssyError`.
  `nominal`, `mean` özellikleri (yukarıdaki `G₀`, `μ_G`).
- `class Method(StrEnum)`: `WORST_CASE = "en_kotu"`, `RSS = "rss"`, `MONTE_CARLO = "monte_carlo"`.
- `@dataclass(frozen=True) StackResult`:
  - `method: Method`, `nominal: float`, `mean: float`, `lower: float`, `upper: float`
  - `sigma: float | None` — WORST_CASE'te `None`, diğerlerinde `σ_G` (MC: örnek std)
  - `contributions: tuple[float, ...]` — halka sırasıyla, toplam 1 (WC: `|a|T` payı; RSS ve MC: varyans payı).
    Tüm `T = 0` ise hepsi 0 (bölme yok).
- `worst_case(chain) -> StackResult`
- `rss(chain, k: float = 3.0) -> StackResult` — `k > 0`
- `monte_carlo(chain, n: int = 100_000, seed: int = 0, k: float = 3.0) -> StackResult` — `n ≥ 2`
- `samples(chain, n: int, seed: int = 0) -> np.ndarray (n,)` — `G` örnekleri; aynı `seed` → aynı dizi
- `reject_fraction(chain, lsl: float, usl: float, method=Method.RSS, n=100_000, seed=0) -> float` —
  `lsl < usl`; WORST_CASE yöntemi → `AssyError` (olasılık vermez)
- `measure(assembly, a: Ref, b: Ref) -> float` — teori tablosundaki `m`, mevcut `T`'lerle; desteklenmeyen
  çift → `AssyError`
- `assembly_chain(assembly, tolerances: dict[int, Tolerance], a: Ref, b: Ref, tol=1e-10) -> Chain` —
  anahtar: `assembly.mates` içindeki kısıt sırası. Önce `assy.solver.solve` (girdi değişmez), sonra teori
  bölümündeki `a_j` ve `c`. Halka adı: tolerans adı, boşsa `"kisit <j>"`.
  Hatalar → `AssyError`: sıra aralık dışında; kısıt DISTANCE veya ANGLE değil; ANGLE `0`/`180` (vektör artığı,
  `θ`'ya bağlı satır yok); `|tolerans.nominal − mate.value| > 1e-12`; ölçü belirsiz; boş sözlük.

Tüm hatalar `AssyError` (sessiz hata yok; `nan` dönmez).

## Analitik test tablosu
`Tn(t)` = `Tolerance.symmetric(n, t)` (NORMAL, k = 3).

| # | Durum | Beklenen (kapalı form) |
|---|---|---|
| A1 | Gövde 50 T(0.1), `a=+1`; burç 20 T(0.05) ve 29.8 T(0.05), `a=−1` | `G₀ = 0.2`; WC `[0.0, 0.4]`; RSS `σ_G = √0.015/3 = 0.0408248…`, `[0.2 ∓ 0.1224745…]`; WC katkılar `0.5, 0.25, 0.25`; RSS katkılar `2/3, 1/6, 1/6` |
| A2 | `n` eş halka T(t), `a=+1`, `n = 1, 4, 9` | `T_wc = n t`, `kσ_G = √n t` |
| A3 | Asimetrik: `10 +0.1/−0` tek halka | `μ = 10.05`, WC `[10.0, 10.1]`, `G₀ = 10` |
| A4 | Kaldıraç `a = 2`, T(0.05) | WC `±0.1`, `σ_G = 2·0.05/3` |
| A5 | İki UNIFORM ±0.1 toplamı | `σ_G = 0.1·√(2/3) = 0.0816497…`; `P(|G| > 0.15) = ((0.2 − 0.15)/0.2)² = 0.0625` (üçgen yoğunluk) |
| A6 | Tek NORMAL, sınırlar `μ ± 3σ` | RSS `reject_fraction = 2(1 − Φ(3)) = 0.0026998…` |
| A7 | TRIANGULAR ±0.3 | `σ = 0.3/√6 = 0.1224745…` |
| A8 | 3B üst üste bloklar: `A` sabit, `B` ve `C` PLANE–PLANE DISTANCE `D₁ = 5 ± 0.1`, `D₂ = 7 ± 0.2` (+ yanal kısıtlar), ölçü `A` alt yüzü – `C` üst yüzü | `a = (1, 1)`; zincir A2/A1 ile aynı sonuç; `m₀` kapalı formda |
| A9 | 3B menteşe: `A` sabit, kol `B` CONCENTRIC + düzlem + ANGLE `θ = 30° ± 0.1°`, kol ucu menteşeden `L = 100` mm, ölçü uç noktası – taban düzlemi | `m₀ = L sin θ = 50`; `a = L cos θ · π/180 = 1.5114995…` mm/°; WC `±0.1511499…` |

## Kabul kriterleri
Toleranslar aksi yazmadıkça: kapalı form `1e-12` (göreli `1e-12`), 3B `1e-9`.
- [ ] K1 `Link`/`Chain` doğrulaması: `a = 0`, `a` sonsuz, boş zincir → `AssyError` — `tests/assy/test_tolerans.py`
- [ ] K2 En kötü durum: A1, A2, A3, A4 kapalı form; katkılar toplamı 1; `sigma is None`
- [ ] K3 RSS: A1, A2, A4, A7 kapalı form; tüm halkalar NORMAL ve `sigma_level = k` iken `k σ_G = √Σ(a_i T_i)²`;
  `k` değişince yalnız sınırlar ölçeklenir; katkılar toplamı 1
- [ ] K4 Dağılım karışımı: NORMAL, UNIFORM, TRIANGULAR aynı zincirde → `σ_G² = Σ a_i² σ_i²` (A5, A7 değerleriyle)
- [ ] K5 Monte Carlo (`n = 200 000`): ortalama `μ_G`'ye `4 σ_G/√n` içinde; std `σ_G`'ye %2 içinde (A1, A5);
  aynı `seed` → aynı `samples` dizisi, farklı `seed` → farklı dizi; `samples` uzunluğu `n`
- [ ] K6 Şartname dışı: A6 RSS kesin (1e-12); A5 Monte Carlo `0.0625`'e `4√(p(1−p)/n)` içinde;
  `σ_G = 0` zincirde RSS oranı 0 ya da 1; `lsl ≥ usl` ve WORST_CASE → `AssyError`
- [ ] K7 Sıfır genişlik: tüm `T = 0` → WC ve RSS sınırları `G₀`'a eşit, katkılar 0, `nan` yok
- [ ] K8 `measure`: POINT–PLANE (iki sıra), PLANE–PLANE, POINT–POINT elle kurulmuş konumda kapalı form; desteklenmeyen çift → `AssyError`
- [ ] K9 `assembly_chain` A8: `a = (1, 1)` (1e-9), `c` ile `G₀ = m₀`; `worst_case`/`rss` sonucu 1B zincirle aynı (1e-9)
- [ ] K10 `assembly_chain` A9: `a = L cos θ π/180` (1e-9), `m₀ = 50` (1e-9); menteşe ekseni etrafındaki serbestlik ölçüyü
  etkilemiyorsa hata yok
- [ ] K11 Merkezi fark kontrolü: rastgele bir montajda her `a_j`, `p_j ± h` ile `solve` + `measure` merkezi farkına (h = 1e-6) mutlak `1e-6` içinde eşit
- [ ] K12 Hatalar → `AssyError`: sıra aralık dışında; COINCIDENT/CONCENTRIC kısıta tolerans; ANGLE 0°/180°;
  nominal ≠ `mate.value`; boş sözlük; ölçü belirsiz (serbest kalan öteleme ölçü yönünde); `solve` girdiyi değiştirmez
- [ ] Tüm testler yeşil: `pytest` → 0 failed, bu SPEC'te 0 "uygulanmamış"; `ruff check .` temiz

## Kapsam dışı
- Doğrusal olmayan 3B Monte Carlo (her örnekte yeniden `solve`); yalnız doğrusallaştırılmış 3B
- Parça içi ölçü toleransları (referans `origin`'lerine tolerans), geometrik toleranslar (GD&T: konum, düzlemsellik,
  paralellik, malzeme koşulu MMC/LMC), ISO 286 alıştırma tabloları (H7/g6)
- Halkalar arası korelasyon, kayık ortalama (mean shift) / Cpk modelleri, Bender / değiştirilmiş RSS katsayıları
- Tolerans dağıtımı (sentez, maliyet en küçükleme): yalnız analiz
- Kesilmiş NORMAL örnekleme, NORMAL dışı ampirik dağılımlar
- Tezgah ekranı / görselleştirme (histogram); JSON dosya biçimi (`Tolerance.to_dict` dışında)
