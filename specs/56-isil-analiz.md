# SPEC 56 — Kararlı hal ısı iletimi (tet4) (Dalga 6, G9)

> Onaylandı: kullanıcı, 2026-10-18 14:52 UTC, Dalga 6 toplu onayı (proje sohbeti; 2 dakika içinde itiraz yok,
> kullanıcının 11:14 UTC otomatik kabul kuralı). Taslakta açık soru yoktu.
> Bağımlılık: SPEC 11 (tet4), SPEC 12 (gmsh ağı ve sınır seçimi).
> Kaynak: `yol-haritasi/dalga-6-ve-sonrasi.md` G9, `yol-haritasi/sinirlar-malzeme-analiz.md` (analiz düzeyleri).

## Amaç
Bir parçanın içindeki kararlı hal sıcaklık dağılımını, aynı tet4 ağı üzerinde hesaplamak. Desteklenen sınır koşulları:
- sabit sıcaklık (Dirichlet)
- ısı akısı (Neumann)
- taşınım: film katsayısı `h` ve ortam sıcaklığı `T∞` (Robin)
- hacimsel ısı üretimi

Sonuçlar:
- düğüm sıcaklıkları
- eleman ısı akı vektörü
- tutulan düğümlerdeki tepki ısıları (enerji dengesi)

SPEC 67'nin ısıl yükü bu sıcaklık alanını girdi olarak alır. Mekanik çözücü ve `core/model.py` değişmez.

## Teori

### Birimler (N – mm – s; sıcaklık °C ya da K, yalnız farklar önemlidir)
| Büyüklük | Birim | SI'dan sayı dönüşümü |
|---|---|---|
| Güç, ısı | mW (= N·mm/s) | W × 1000 |
| Isıl iletkenlik `k` | mW/(mm·K) | W/(m·K) × 1 |
| Isı akısı `q` | mW/mm² | W/m² × 1e-3 |
| Film katsayısı `h` | mW/(mm²·K) | W/(m²·K) × 1e-3 |
| Hacimsel üretim `Q` | mW/mm³ | W/m³ × 1e-6 |

Örnekler:
- Durgun havada `h ≈ 10 W/(m²·K)`, yani `0.01`.
- Kesme sıvısında `h ≈ 1000 W/(m²·K)`, yani `1.0`.

Kod dönüşüm yapmaz; testler ve örnekler bu birimlerle yazılır.

### Denklem ve zayıf biçim
```
−∇·(k ∇T) = Q                  Ω içinde
T = T̄                          Γ_T  (sabit sıcaklık)
−k ∂T/∂n = −q̄                  Γ_q  (q̄ > 0: parçaya GİREN akı)
−k ∂T/∂n = h (T − T∞)          Γ_h  (taşınım)
```
`k` her elemanda sabittir (malzeme başına bir sayı) ve izotroptur.

### tet4 eleman matrisleri
Doğrusal şekil fonksiyonları `N_a` (SPEC 11 ile aynı) kullanılır. Gradyan matrisi `B (3×4)` sütunlarında `∇N_a`
bulunur ve eleman içinde sabittir. `V` eleman hacmidir.
```
ke = k V Bᵀ B                       (4×4)  iletkenlik
fQ = Q V / 4 · [1 1 1 1]ᵀ           hacimsel üretim (tutarlı = topaklanmış, doğrusal elemanda)
```
Sınır üçgeninin alanı `A`, köşeleri `i, j, l` olsun:
```
fq = q̄ A / 3 · [1 1 1]ᵀ                                  akı
Hh = h A / 12 · [[2 1 1] [1 2 1] [1 1 2]]                taşınım iletkenliği (K'ya eklenir)
fh = h T∞ A / 3 · [1 1 1]ᵀ                               taşınım yükü
```
Global sistem `K T = F` olur (`K = Σ ke + Σ Hh`, `F = Σ fQ + Σ fq + Σ fh`). Bu sistem simetrik ve pozitif yarı
tanımlıdır. Sabit sıcaklıklı düğümler bölümleme ile ayrılır (SPEC 11'deki mekanik çözüm yolunun aynısı). Kalan sistem
`scipy.sparse.linalg.spsolve` ile çözülür.

**Tepki ısısı**, sabit sıcaklıklı düğümden sisteme giren ısıdır: `R = K T − F`. Tutulan düğümlerin dışında sıfırdır.
Enerji dengesi: `Σ R + Σ F_dış − Σ_Γh h A (T̄_üçgen − T∞) = 0`. Üretim, akı ve taşınım katkıları ayrı raporlanır.

Tekillik: `Γ_T` ve `Γ_h` ikisi de boşsa sıcaklık bir sabite kadar belirsizdir, `K` tekildir → `ModelError`.

Eleman ısı akısı `q_e = −k B T_e` (3 bileşen, eleman içinde sabit), birimi mW/mm². Düğüm akısı, SPEC 13'teki düğüm
gerilmesiyle aynı yolla hacim ağırlıklı ortalama olarak hesaplanır.

### Kapalı formüllü referanslar
1. **Düzlem duvar** (`x = 0`'da `T1`, `x = L`'de `T2`, yanlar yalıtılmış):
   - `T(x) = T1 + (T2 − T1) x/L`
   - `q = k (T1 − T2)/L`
   - toplam `Q = q A`

   Alan doğrusaldır ve tet4 onu **her ağda tam** üretir.
2. **Duvar + taşınım** (`x = 0`'da `T0`, `x = L`'de `h, T∞`):
   - `q = (T0 − T∞) / (L/k + 1/h)`
   - `T(L) = T0 − q L/k`

   Doğrusaldır, tam üretilir.
3. **Duvar + akı** (`x = 0`'da `T0`, `x = L`'den giren `q̄`): `T(x) = T0 + q̄ x / k`. Doğrusaldır, tam üretilir.
4. **Kalın cidarlı silindir** (iç yarıçap `a`'da `T1`, dış yarıçap `b`'de `T2`, uçlar yalıtılmış, boy `Lz`):
   - `T(r) = T1 + (T2 − T1) ln(r/a) / ln(b/a)`
   - `Q = 2π k Lz (T1 − T2) / ln(b/a)`

   Logaritmiktir; tet4 yaklaşır. Düğüm hatası `O(h²)` mertebesindedir.
5. **Isı üreten levha** (`x = 0` ve `x = L` yüzleri `T0`, yanlar yalıtılmış):
   - `T(x) = T0 + Q x (L − x) / (2k)`
   - `T_maks = T0 + Q L² / (8k)`
   - tepki ısılarının toplamı `−Q V`

   Toplam her ağda tamdır; dağılım yaklaşır.

Kaynak: Incropera, DeWitt, Bergman, Lavine, *Fundamentals of Heat and Mass Transfer*, 7. baskı, bölüm 3.1–3.5;
Zienkiewicz, Taylor, *The Finite Element Method*, cilt 1, ısı iletimi bölümü.

### CalculiX eşlemesi (çapraz kontrol)
| Bizde | CalculiX |
|---|---|
| tet4 ısıl | `DC3D4` (aynı doğrusal tetrahedron), `*HEAT TRANSFER, STEADY STATE` |
| `k` | `*MATERIAL`, `*CONDUCTIVITY` |
| sabit sıcaklık | `*BOUNDARY` `node, 11, 11, T` |
| düğüm ısısı (akı ve üretim düğüme dağıtılmış olarak) | `*CFLUX` `node, 11, değer` |
| sıcaklık çıktısı | `*NODE PRINT` `NT` |

Çapraz kontrolde akı ve üretim, bizim tutarlı düğüm yükümüzle `*CFLUX` olarak verilir. Taşınım (`*FILM`) kendi testleriyle
doğrulanır ve ccx karşılaştırmasına girmez. Sayı biçimi SPEC 13'teki gibi `.12e` olur.

## Dosyalar
- **Yeni:**
  - `core/isil.py`
  - `core/elements/tet4.py` içinde yeni isteğe bağlı `kt(element, model, k) -> (4, 4)` (eleman sözleşmesine "ısıl
    eleman" eki; SPEC 45'teki `me` gibi isteğe bağlı)
  - `tests/unit/test_isil.py`, `tests/benchmarks/test_isil.py`, `tests/reference/test_ccx_isil.py`
  - `tests/analiz/test_isil_parca.py`
  - `examples/56_isil_duvar.json`
  - `specs/56-isil-analiz.md`, `durum/56-isil-analiz.md`
- **Değişecek:**
  - `core/elements/__init__.py`: sözleşme metninde `kt` satırı
  - `analiz/__init__.py` ve yeni `analiz/isil.py`: parça → ağ → ısıl çözüm köprüsü (SPEC 45 deseni)
  - `fileio/calculix.py`: yeni `to_inp_thermal`. `to_inp` ve `write_inp` değişmez.
- **Dokunulmayacak:**
  - `core/model.py`: ısıl sınır koşulları `core/isil.py`'deki kendi kayıtlarıdır; `Model.bcs` ve `Model.loads` mekanik
    kalır.
  - `core/solver.py`, `core/assembly.py`, `core/post.py`
  - `mesh/`: yalnız `select_triangles` ve `select_nodes` kullanılır.
  - `malzeme/`: `k`, `Mapping[str, float]` olarak verilir. B2 kaydından `{m.id: m.iste("k")}` ile kurulur; köprü
    `analiz/isil.py`'dedir.

Bağımlılık yönü: `core/isil.py` yalnız numpy, scipy ve `core.model` / `core.elements` kullanır. `analiz/isil.py` → `core`,
`mesh`, `geometry`.

## Arayüz

### `core/isil.py`
```python
@dataclass(frozen=True)
class Temperature:  # sabit sıcaklık
    node: int
    T: float  # °C


@dataclass(frozen=True)
class HeatFlux:  # Γ_q, içeri pozitif
    tris: np.ndarray  # (k, 3) düğüm id'leri (mesh.select_triangles çıktısı)
    q: float  # mW/mm²


@dataclass(frozen=True)
class Convection:  # Γ_h
    tris: np.ndarray  # (k, 3)
    h: float  # mW/(mm²·K), > 0
    T_inf: float  # °C


@dataclass(frozen=True)
class ThermalResult:
    node_ids: np.ndarray  # (n,) model.nodes sırası
    T: np.ndarray  # (n,) °C
    R: np.ndarray  # (n,) mW, tepki ısısı; sabit sıcaklıklı olmayan düğümde 0
    Q_gen: float  # mW, toplam üretim
    Q_flux: float  # mW, Γ_q'dan giren toplam
    Q_conv: float  # mW, Γ_h'den giren toplam (soğutmada negatif)

    def temperature(self, node_id: int) -> float: ...  # bilinmeyen düğüm → ModelError


def conductivity_matrix(model, k) -> sp.csr_matrix: ...  # Σ ke (taşınım hariç)
def solve_thermal(
    model: Model,
    k: float | Mapping[str, float],  # tek sayı ya da Material.name → k
    *,
    temperatures: Sequence[Temperature] = (),
    fluxes: Sequence[HeatFlux] = (),
    convection: Sequence[Convection] = (),
    Q: float | Mapping[str, float] = 0.0,  # mW/mm³, malzeme adına göre de verilebilir
) -> ThermalResult: ...
def heat_flux(model, k, result) -> np.ndarray: ...  # (m, 3) mW/mm², eleman sırası
def nodal_heat_flux(model, k, result) -> np.ndarray: ...  # (n, 3) hacim ağırlıklı ortalama
```

Davranış ve hatalar (hepsi `ModelError`):
- `model.validate()` çağrılır.
- `dim ≠ 3`, ya da `tet4` dışında bir eleman tipi (tet10 ısıl, SPEC 67'nin kapsamı değildir; bkz. Kapsam dışı).
- `k ≤ 0`, `h ≤ 0`, ya da sonlu olmayan bir değer.
- `Mapping` içinde eksik malzeme adı.
- Bilinmeyen düğüm ya da üçgen düğümü.
- Aynı düğüme iki farklı `Temperature` (aynı değer tekrarı kabul edilir).
- Hem `temperatures` hem `convection` boş (tekil sistem).
- Sonlu olmayan çözüm.
- `model.bcs` ve `model.loads` **okunmaz**. Bu davranış docstring'de yazar. Mekanik ve ısıl koşullar aynı modelde
  karışmaz.

### `analiz/isil.py`
```python
def parca_isil(
    part,
    h_ag: float,
    malzeme: "malzeme.model.Malzeme",
    *,
    sabit: Sequence[tuple[Tahmin, float]] = (),  # (yüz seçici, T)
    aki: Sequence[tuple[Tahmin, float]] = (),  # (yüz seçici, q̄)
    tasinim: Sequence[tuple[Tahmin, float, float]] = (),  # (yüz seçici, h, T∞)
    Q: float = 0.0,
) -> tuple[Model, ThermalResult]: ...
```
`mesh.tet_mesh(part, h_ag, malzeme.fem_malzemesi())` çağrılır. Her seçici `mesh.select_nodes` ya da
`mesh.select_triangles` ile uygulanır. `k = malzeme.iste("k")`. Seçici hiçbir şey bulamazsa `ModelError`.
(B2 birleşmeden önce `malzeme` parametresi yerine `Material` ve `k` sayısı kabul eden geçici bir imza **eklenmez**: 56'nın
kod PR'ı B2'yi bekler. Yalnız `core/isil.py` bölümü B2'siz yazılıp test edilebilir.)

### `fileio/calculix.py`
`to_inp_thermal(model, k, temperatures, nodal_heat: Mapping[int, float]) -> str`: Teori'deki eşleme tablosu.

## Kabul kriterleri
Ağlar: unit ve benchmark testleri OCCT'siz, SPEC 11 K10'daki gibi Kuhn bölümlü kutu ağıyla kurulur. `analiz` testleri
`@pytest.mark.occt` ile işaretlenir ve gmsh ağı kullanır.

- [ ] **K1** Eleman matrisi:
  - Birim referans tetrahedronda (`(0,0,0), (1,0,0), (0,1,0), (0,0,1)`) `k = 1` için
    `kt = (1/6)·[[3,−1,−1,−1],[−1,1,0,0],[−1,0,1,0],[−1,0,0,1]]` (abs 1e-14).
  - Rastgele bir tetrahedronda `kt` simetriktir, satır toplamları 0'dır (abs 1e-12·‖kt‖), pozitif yarı tanımlıdır, rankı
    3'tür.
  - Rijit öteleme ve döndürme altında değişmez.
  - `k` ile doğrusal ölçeklenir.
- [ ] **K2** Yama testi: `2×2×2` Kuhn kutusunda dış düğümlere `T = 5 + 2x − 3y + 0.5z` yazılır. İç düğümlerde aynı
  doğrusal alan çıkar (abs 1e-10). Her elemanda `q_e = −k (2, −3, 0.5)` olur (göreli 1e-10).
- [ ] **K3** Düzlem duvar: `100 × 50 × 50` mm kutu, `k = 50`, `T1 = 100`, `T2 = 20`, ağ `k = 1` ve `k = 3`.
  - Her düğümde `T(x)` formülü tutar (abs 1e-9).
  - Her elemanda `q_e = (40, 0, 0)` mW/mm² (göreli 1e-9).
  - Sıcak yüz tepki toplamı `+1.0e5` mW (= 100 W), soğuk yüzünki `−1.0e5` mW (göreli 1e-9).
- [ ] **K4** Taşınım: K3 kutusunda `x = 0`'da `T0 = 100`; `x = L`'de `h = 0.025`, `T∞ = 20`.
  - `q = 80/42 = 1.904762` mW/mm².
  - `T(L) = 96.190476` (abs 1e-9).
  - `Q_conv = −q·A` (göreli 1e-9).
  - Çözüm iki ağda da doğrusaldır.
- [ ] **K5** Akı: K3 kutusunda `x = 0`'da `T0 = 20`, `x = L`'den `q̄ = 2.0` giriyor.
  - `T(L) = 24` (abs 1e-9).
  - Tepki toplamı `−q̄·A = −5000` mW.
- [ ] **K6** Isı üreten levha: `20 × 20 × 20` mm küp, `x = 0` ve `x = 20` yüzleri `T0 = 0`, `k = 15`, `Q = 1.0`.
  - `Σ R = −Q V = −8000` mW her ağda (göreli 1e-10).
  - `T_maks = 400/120 = 3.3333` için `x = 10` düzlemindeki düğümlerin ortalaması: `k = 2` Kuhn ağında %3, `k = 4`'te %1
    içinde.
  - `x = 10` düğüm ortalaması her iki ağda `T_maks`'a göreli 1e-9 içinde (bkz. Kararlar K-1).
- [ ] **K7** Silindir (OCCT, gmsh, `@pytest.mark.occt`): `a = 10, b = 30, Lz = 20`, `T1 = 200, T2 = 50`, `k = 50`.
  - `h_ag = 3` ile düğüm hatası `max |T − T(r)| ≤ 0.02·(T1 − T2)`.
  - `h_ag = 1.5` ile hata en az yarıya iner.
  - İç yüz tepki toplamı `Q = 2π·50·20·150/ln 3 = 857 880` mW değerine `h_ag = 3`'te %3, `h_ag = 1.5`'te %1 içinde.
  - Ön hesap kod PR'ında yapılır. Eşik tutmazsa SPEC değil kod incelenir; eşik değişikliği kullanıcıya sorulur.
- [ ] **K8** Enerji dengesi: K3–K7'nin hepsinde `Σ R + Q_gen + Q_flux + Q_conv = 0` (göreli 1e-9, en büyük terime göre).
- [ ] **K9** Hatalar (her biri `ModelError`):
  - sıcaklık ve taşınım yok
  - `k = 0`, `k = −1`
  - `h = 0`
  - `Q = nan`
  - bilinmeyen düğüm
  - aynı düğüme 10 ve 20 °C
  - eksik malzeme adı içeren `k` sözlüğü
  - tet4 dışı eleman (`bar1d` modeli)
  - `dim = 1`
- [ ] **K10** CalculiX çapraz kontrolü (`tests/reference/`, `ccx` yoksa atlanır): K6 küpü `k = 2` ağında, üretim düğüm
  ısısı olarak `*CFLUX` ile verilir. `NT` bizim `T` ile göreli 1e-6 içinde eşittir (`.dat` 7 basamak).
- [ ] **K11** Parça köprüsü (`analiz.parca_isil`, OCCT): K7 silindiri `Malzeme` kaydıyla (`k = 50`) kurulur ve K7 ile
  aynı sonucu verir. `k` alanı olmayan bir malzeme `ModelError` verir.
- [ ] **K12** `core/isil.py` numpy, scipy ve `core` dışında bir modül import etmez (metin taraması). `ruff` temiz;
  10 s'yi aşan test `@pytest.mark.slow` ile işaretlenir.

## Kararlar
- **K-1 (K6 düzeltmesi, kullanıcı onaylı: proje sohbeti 2026-10-18 15:59 UTC, 2 dakika otomatik kabul):** "Hata `k = 2 → 4` geçişinde en az yarıya
  iner" maddesi kaldırıldı, yerine "`x = 10` düğüm ortalaması her iki ağda `T_maks`'a göreli 1e-9 içinde" geldi.
  Gerekçe: doğrusal eleman ve tutarlı yükle bu 1B problemde düğüm değerleri tam çıkar (ön hesap: göreli hata
  `k = 2`'de 4e-16, `k = 4`'te 1.6e-15); yarıya inme ölçütü yuvarlama gürültüsünü karşılaştırırdı.

## Bağımlılık
- SPEC 11 (tet4, birleşti), SPEC 12 (ağ ve seçim, birleşti), SPEC 13 (`fileio/calculix.py`, birleşti), SPEC 45 (`analiz/`
  deseni, birleşti).
- B2: yalnız `analiz/isil.py` ve K11 için. `core/isil.py` ve K1–K10 B2'siz yazılır.
- Bu SPEC'i kullananlar: 67 (ısıl yük, `ThermalResult.T` girdi), Dalga 7'de geçici ısıl ve termo-mekanik.

## Kapsam dışı
- Geçici (zamana bağlı) ısı iletimi, `ρ cp ∂T/∂t`: Dalga 7 A11. `cp` B2 kaydında hazır bekler.
- Sıcaklığa bağlı `k(T)` (doğrusal olmayan), ışınım, temas ısıl direnci, montajda parçalar arası iletim.
- tet10 ısıl eleman: gerekirse 67'den sonra küçük bir ek SPEC olarak gelir.
- Görselleştirme (sıcaklık renk haritası): SPEC 15 / 47 ekranları.
