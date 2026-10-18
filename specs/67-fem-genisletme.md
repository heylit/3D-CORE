# SPEC 67 — FEM genişletme: tet10, CAD yüzüne yük ve mesnet, hacim kuvvetleri, ısıl yük, emniyet katsayısı (Dalga 6, G11)

> Onaylandı: kullanıcı, 2026-10-18 ~14:54 UTC, Dalga 6 ilk 8 taslağın toplu onayı (proje sohbetinde 14:52 UTC soruldu;
> kullanıcının 11:14 UTC kuralı "2 dakikadan fazla geçerse öneriyi kabul et" gereği itirazsız onay, önerilerle).
> Bağımlılık: A2 (`FaceRef`), SPEC 11, 12, 13, 45, 56 (ısıl yük için), 66 (`Rp02`, `alpha`, `rho`).
> Kaynak: `yol-haritasi/dalga-6-ve-sonrasi.md` G11, `yol-haritasi/sinirlar-malzeme-analiz.md` (analiz düzeyleri).
>
> **İki PR (paralellik için):**
> - **67a:** tet10 eleman, ikinci dereceden ağ, tet10 sonrası işlem. Durum: `durum/67a-tet10.md`.
> - **67b:** yüz eşlemesi, yüze yük ve mesnet, hacim kuvvetleri, ısıl yük, emniyet katsayısı. Durum: `durum/67b-*.md`.
>
> 67b'nin tet4 bölümleri 67a'yı beklemez; tet10 kabul kriterleri 67a birleşince açılır. Kabul kriterleri iki gruba
> ayrılmıştır.

## Kararlar (onayla birlikte, taslağın önerileri)
- **D1** SPEC iki PR'da uygulanır (67a, 67b). Bu metin ikisini birden tanımlar; her PR yalnız kendi grubunun kabul
  kriterlerini kapatır.
- **D2** Durum dosyası PR başına ayrıdır (`durum/67a-tet10.md`, `durum/67b-*.md`); taslaktaki tek
  `durum/67-fem-genisletme.md` paralel PR'larda çakışacağı için bölündü.
- **D3** K5 (tet10 konsol) eşikleri kod PR'ının ön hesabıyla teyit edilir. Tutmazsa önce kod incelenir; eşik değişikliği
  kullanıcıya sorulur, kod oturumu kendisi değiştirmez.
- **D4** `mesh/` ve `fileio/calculix.py` SPEC 12/13 dosyalarıdır; 67a başlamadan önce başka açık PR'ın bunlara
  dokunmadığı koordinatörle teyit edilir.
- **D5** tet10 düğüm gerilmesi eleman modülündeki `stress_nodes(element, model, u) -> (10, 6)` ile verilir (Teori:
  köşelere doğrusal dış değerleme, kenarlara iki köşenin ortalaması). `post.nodal_stress_tensors`, `stress_nodes`
  sağlayan elemanlarda eleman sabiti yerine bu düğüm değerlerinin hacim ağırlıklı ortalamasını alır; tet4 davranışı
  değişmez.

## Amaç
Bugünkü FEM zinciri (parça → tet4 ağı → çözüm → von Mises) bir öğrenme aracı olarak doğru çalışıyor. Ancak mühendislik
kullanımı için dört eksiği var:

1. **tet4 eğilmede kilitlenir.** SPEC 11 K10'da konsol kiriş en kaba ağda Timoshenko sehiminin yalnız %22'sini veriyor.
   10 düğümlü ikinci dereceden tetrahedron (tet10) doğrusal gerilme alanını tam üretir ve aynı düğüm sayısında çok daha
   hızlı yakınsar.
2. **Yük ve mesnet geometrik tahminle seçiliyor** (`on_plane`, `on_cylinder`). Kullanıcı ise CAD'de bir yüz seçer. Kararlı
   yüz kimliği (`FaceRef`, A2) ile "bu yüze 2 MPa basınç, şu delik sabit" denebilmeli.
3. **Hacim kuvvetleri ve ısıl yük yok.** Yerçekimi, dönen parçada merkezkaç ve SPEC 56'nın sıcaklık alanından gelen ısıl
   gerinme eksik.
4. **Sonuç bir karar vermiyor.** Emniyet katsayısı `n = Rp0.2 / σ_vM` hem düğüm başına hem en küçük değer olarak
   raporlanmalı.

## Teori

### tet10 eleman (67a)
Hacim koordinatları `L1..L4` (`ΣL = 1`) kullanılır. Düğüm sırası CalculiX/Abaqus C3D10 ile aynıdır, böylece çapraz
kontrolde yeniden sıralama gerekmez:
```
köşe:   1, 2, 3, 4
kenar:  5 (1–2), 6 (2–3), 7 (3–1), 8 (1–4), 9 (2–4), 10 (3–4)
N_i = L_i (2 L_i − 1)        i = 1..4
N_5 = 4 L1 L2,  N_6 = 4 L2 L3,  N_7 = 4 L3 L1,  N_8 = 4 L1 L4,  N_9 = 4 L2 L4,  N_10 = 4 L3 L4
```
Fonksiyonlar izoparametriktir: geometri de aynı `N` ile eşlenir, gmsh'in yüzeye oturttuğu kenar düğümleri eğri kenar
verir.

`B` (6×30) Jacobian üzerinden hesaplanır:
```
ke = Σ_g w_g Bᵀ D B det J
```
İntegrasyon 4 noktalı Gauss kuralıyla yapılır (2. derece). Noktalar `a = 0.5854101966249685`,
`b = 0.1381966011250105`, ağırlık `w = 1/24` (referans hacmi `1/6`). Kenarları düz elemanda `BᵀDB` 2. dereceden olduğu için
bu kural tamdır. CalculiX C3D10 de 4 nokta kullanır, aynı ağda aynı `K` beklenir.

`det J ≤ 0` olan bir Gauss noktası çıkarsa `ModelError` verilir; mesajda eleman id'si geçer.

Kütle matrisi (`me`, SPEC 45 sözleşmesi) 67a'nın kapsamına girer. Tutarlı kütle 4 noktalı kuralla tam değildir (4. derece
gerekir), bu yüzden 15 noktalı Keast kuralı kullanılır. Topaklanmış kütle istenirse `ModelError` verilir, çünkü tet10'da
satır toplamı köşelerde negatif ağırlık üretir.

Eleman gerilmesi Gauss noktalarında hesaplanır. Düğüme taşıma şöyle yapılır:
- 4 Gauss değerinden doğrusal dış değerleme ile köşe düğümlerine
- kenar düğümlerine iki köşenin ortalaması olarak

SPEC 13'teki hacim ağırlıklı düğüm ortalaması bu düğüm değerleri üzerinden yapılır.

**Saf eğilme alanı** tam üretilmesi gereken 2. dereceden yer değiştirmedir (yama testi). `x` kiriş ekseni, eğrilik `κ`:
```
u_x = κ x z,    u_y = −ν κ y z,    u_z = −κ (x² + ν (z² − y²)) / 2
ε_xx = κ z,  ε_yy = ε_zz = −ν κ z,  γ = 0       →   σ_xx = E κ z, diğerleri 0
```

### İkinci dereceden ağ (67a)
- `mesh.tet_mesh(..., order=2)` gmsh'te `Mesh.ElementOrder = 2` ve `Mesh.HighOrderOptimize = 0` ayarlarını kullanır.
- gmsh tet10 düğüm sırası C3D10 sırasına çevrilir. gmsh'te 9. ve 10. düğüm (`2–4` ve `3–4` kenarları) farklı sıradadır; kod
  bunu sabit bir permütasyonla düzeltir ve test edilir (K2: her kenar düğümü düz elemanda kenar ortasındadır).
- Sol el elemanlarda köşe 2 ↔ 3 yer değiştirir; kenar düğümleri buna göre yeniden eşlenir.
- `boundary_triangles` tet10'da 6 düğümlü üçgen (`(k, 6)`: 3 köşe, sonra `1–2, 2–3, 3–1` kenarları) döndürür. Seçim
  işlevleri köşe düğümlerine göre karar verir.

### CAD yüzü eşlemesi (67b)
`mesh.mesh_part(part, h, material, *, order=1, refine=()) -> PartMesh`:
- `PartMesh.model`: Model, `tet_mesh` ile aynı
- `PartMesh.face_tris: Mapping[int, np.ndarray]`: OCCT yüz indeksi → sınır üçgenleri `(k, 3)` ya da `(k, 6)`

Yüz indeksi `Part.names`'in kullandığı sıradır (`geometry/part.py`). gmsh yüzey etiketi bu indeksle aynı olmak
zorunda değildir. Eşleme her gmsh yüzeyinin alanı ve kütle merkezi ile OCCT yüzünün alanı ve kütle merkezi
karşılaştırılarak kurulur. Ölçüt göreli 1e-6'dır (alan) ve parça köşegeninin 1e-6 katıdır (merkez). Eşleşme bire bir
değilse `ModelError` verilir; simetrik ikiz yüzler alan ve merkezde ayrışır, ayrışmazsa bu da hatadır. OCCT yüz özellikleri
`mesh/` içinde `part.to_step` ile zaten bağımlı olunan OCCT/build123d üzerinden okunur. `geometry/part.py` arayüzü
**değişmez**.

`PartMesh.triangles(ref: FaceRef) -> np.ndarray`, `part.find(ref)` ile gelen bütün yüzlerin üçgenlerini birleştirir.
Bulunamayan `ref` için `ModelError` (`Part.find` zaten verir) fırlatılır.

### Yüzey yükleri: tutarlı düğüm kuvveti (67b)
- tri3 (tet4 ağı): düzgün çekme `t` için her köşeye `t A/3`. Bu SPEC 12 `add_traction` ile aynıdır.
- tri6 (tet10 ağı):
  ```
  f_a = ∫ N_a t dA
  ```
  Düzgün `t` ve düz üçgende köşeler 0, kenar düğümleri `t A/3` alır. Eğri yüzde integrasyon 6 noktalı Dunavant (4. derece)
  kuralıyla yapılır: `N_a` 2. derece, `n dA = (∂x/∂ξ × ∂x/∂η) dξ dη` 2. derece. Basınç `p` yüzey normali boyunca içeri
  etkir: `t = −p n`.
- Toplam kuvvet her iki eleman tipinde `∫ t dA`'ya eşittir. Düz yüzde bu `t · A_yüz` olur.

### Hacim kuvvetleri (67b)
Kuvvet yoğunluğu `b` (N/mm³) için `f_a = ∫ N_a b dV`. Birimler: `ρ` t/mm³, ivme mm/s², sonuç t·mm/s²/mm³ = N/mm³.
- **Yerçekimi:** `b = ρ g`, `g` vektör (mm/s²). Dünya için `|g| = 9810`; kod sabit tutmaz, çağıran verir.
  - tet4'te her düğüme `ρ g V/4`.
  - tet10'da köşelere `−ρ g V/20`, kenarlara `ρ g V/5` (toplam `ρ g V`).
- **Merkezkaç:** eksen noktası `p0`, birim eksen `â`, açısal hız `ω` (rad/s).
  ```
  b(x) = ρ ω² r⊥(x),    r⊥ = (x − p0) − ((x − p0)·â) â
  ```
  `b` konumla doğrusaldır. tet4'te 4 noktalı kural tamdır, tet10'da `N_a`·doğrusal 3. derecedir ve 15 noktalı Keast kuralı
  kullanılır.

Kapalı formüllü referanslar:
1. **Kendi ağırlığıyla asılı çubuk:** boy `L`, üst uç `z = L`'de `u_z = 0`, `ν = 0`, `g = (0, 0, −9810)`.
   - `σ_zz(z) = ρ g z` (alttan ölçülen yükseklik)
   - `u_z(z) = −ρ g (L² − z²) / (2E)`
   - uç sehimi `δ = ρ g L² / (2E)`

   `ν = 0` iken tam çözüm 2. derecedir ve üst yüz düz kalır, yani mesnet tam çözümle çelişmez. tet10 tam üretir, tet4
   yaklaşır.
2. **Dönen ince disk** (yarıçap `b`, kalınlık `t ≪ b`, delik yok, düzlem gerilme):
   ```
   σ_r = (3 + ν)/8 · ρ ω² (b² − r²)
   σ_θ = ρ ω² / 8 · [(3 + ν) b² − (1 + 3ν) r²]
   ```
   Merkezde `σ_r = σ_θ = (3 + ν)/8 · ρ ω² b²`. Örnek: çelik, `b = 100`, `ω = 1000` rad/s için `ρ ω² b² = 78.5` MPa,
   merkezde `32.38` MPa, kenarda `σ_θ = 13.74` MPa. Kaynak: Timoshenko–Goodier, *Theory of Elasticity*, § 32.

### Isıl yük (67b)
Sıcaklık alanı `T` (SPEC 56 `ThermalResult` ya da düğüm sözlüğü) ve referans sıcaklık `T_ref` (gerilmesiz durum)
kullanılır:
```
ε0 = α (T − T_ref) [1, 1, 1, 0, 0, 0]ᵀ
f_e = ∫ Bᵀ D ε0 dV
σ = D (B u − ε0)
```
- tet4'te `T` eleman içinde 4 düğümün ortalamasıyla sabit alınır.
- tet10'da `T` doğrusal alınır: SPEC 56 tet4 alanı, kenar düğümünde iki ucun ortalamasıdır. 4 noktalı kuralla integre
  edilir.
- `α` malzeme başına `Mapping[str, float]` olarak verilir (SPEC 56'daki `k` gibi; `core/model.py` değişmez).

Kapalı formüllü referanslar:
1. **Serbest genleşme:** düzgün `ΔT` uygulanır, yalnız rijit gövde hareketi tutulur (3-2-1 mesnet).
   - `u = α ΔT (x − x0)`
   - `σ = 0`
2. **Eksenel tutulu çubuk:** iki uç `u_x = 0`, yanal yönler serbest, düzgün `ΔT` uygulanır.
   - `σ_xx = −E α ΔT`
   - Örnek: `E = 210000`, `α = 1.2e-5`, `ΔT = 50` için `−126` MPa.
3. **Doğrusal sıcaklık alanında serbest gövde:** gerilmesizdir (doğrusal `T` uyumlu gerinme verir).
   - tet10'da tam sağlanır.
   - tet4'te eleman başına sabit `ε0` uyumsuz olduğu için ağ inceldikçe sıfıra gider.

### Emniyet katsayısı (67b)
- Düğüm başına `n_i = Rp0.2 / σ_vM,i`. `σ_vM` SPEC 13'teki düğüm gerilmesidir.
- `σ_vM,i = 0` ise `n_i = +inf`. Bu sessiz hata değildir, tanım gereğidir ve docstring'de yazar. Bütün düğümlerde
  `σ_vM = 0` ise `n_min = inf` olur.
- Rapor: `n_min`, o düğümün id'si ve konumu, `σ_vM,maks`.
- `Rp0.2` her malzeme için `Malzeme.iste("Rp02")` ile alınır. Çok malzemeli ağda her düğüm, kendi elemanlarının
  malzemesiyle değerlendirilir. Bir düğüm farklı `Rp0.2` değerli elemanlara ortaksa en küçük `Rp0.2` kullanılır
  (muhafazakâr seçim).
- Sünek malzemeler için akma ölçütüdür. Gevrek malzemeler (dökme demir) ve yorulma kapsam dışıdır. Gevrek grup için
  sonuç bir uyarı bayrağı taşır (`gevrek=True`).

## Dosyalar
- **67a, yeni:**
  - `core/elements/tet10.py`
  - `tests/unit/test_tet10.py`, `tests/benchmarks/test_tet10.py`, `tests/reference/test_ccx_c3d10.py`
  - `durum/67a-tet10.md`
- **67a, değişecek:**
  - `core/elements/__init__.py` (kayıt)
  - `core/post.py`: tet10 eleman gerilmesi Gauss noktalarında, düğüme taşıma
  - `mesh/gmsh_ag.py`: `order` parametresi
  - `mesh/secim.py`: tet10 sınır üçgenleri
  - `mesh/yukler.py`: tri6 tutarlı yük
  - `fileio/calculix.py`: `C3D10` yazımı
- **67b, yeni:**
  - `core/yukler.py`: hacim kuvveti ve ısıl yük vektörleri
  - `mesh/yuz_esleme.py` (`mesh_part`, `PartMesh`)
  - `analiz/dayanim.py` (emniyet katsayısı, `parca_dayanimi` köprüsü)
  - `tests/unit/test_hacim_yuku.py`, `tests/benchmarks/test_isil_yuk.py`, `tests/benchmarks/test_dongu_disk.py`
  - `tests/analiz/test_yuz_yuku.py`, `tests/analiz/test_dayanim.py`
- **67b, değişecek:** `mesh/__init__.py`, `analiz/__init__.py` (yeni adlar).
- **Ortak:** `specs/67-fem-genisletme.md`.
- **Dokunulmayacak:**
  - `core/model.py`: yeni eleman tipi `"tet10"` yalnız bir metindir, `Element.nodes` 10 id taşır. `α` ve `Rp0.2` eşlemle
    gelir.
  - `core/solver.py`: çözücü eleman tipinden bağımsızdır. Hacim ve ısıl yük `Model.loads`'a düğüm `Load`'u olarak eklenir,
    çözücü değişmez.
  - `core/assembly.py`: tipten bağımsızdır, değişmez. Eleman sözleşmesi yeterlidir.
  - `geometry/part.py`: `FaceRef` ve `find` olduğu gibi kullanılır.
  - `malzeme/`, `core/isil.py` (SPEC 56).

Sahiplik notu: `mesh/` ve `fileio/calculix.py` SPEC 12/13 dosyalarıdır, ikisi de birleşti. 67a aynı anda başka bir açık
PR'ın bu dosyalara dokunmadığını koordinatörle teyit eder. 67b'nin `analiz/` dosyaları 56'nın `analiz/isil.py`'siyle
çakışmaz; `analiz/__init__.py` ortak satırdır ve sonra gelen PR `main`'i birleştirerek çözer.

## Arayüz

### 67a
- `core/elements/tet10.py`: `ke(element, model)` (30×30), `dofs`, `volume(element, model)`,
  `me(element, model, lumped=False)`, `stress_gauss(element, model, u) -> (4, 6)`,
  `stress(element, model, u) -> (6,)` (Gauss ortalaması, SPEC 13 eleman gerilmesi sözleşmesi),
  `stress_nodes(element, model, u) -> (10, 6)` (D5).
- `mesh.tet_mesh(part, h, material, *, order: int = 1, refine=(), max_nodes=200_000)`. `order ∉ {1, 2}` için
  `ModelError`. `order=2` için eleman tipi `"tet10"`.
- `mesh.boundary_triangles(model)`: tet4 → `(m, 3)`, tet10 → `(m, 6)`. Karışık tipte `ModelError`.
- `mesh.add_traction` / `add_pressure`: `(k, 3)` ve `(k, 6)` üçgen dizilerinin ikisini de kabul eder.
- `fileio.calculix.to_inp`: tet10 → `*ELEMENT, TYPE=C3D10`.

### 67b
```python
# core/yukler.py  (numpy + core; düğüm Load listesi döndürür, modeli DEĞİŞTİRMEZ)
def gravity_loads(model, g: Sequence[float]) -> list[Load]: ...  # rho Material.rho'dan; rho ≤ 0 → ModelError
def centrifugal_loads(model, omega: float, point, axis) -> list[Load]: ...
def thermal_loads(
    model, T: Mapping[int, float] | ThermalResult, T_ref: float, alpha: float | Mapping[str, float]
) -> list[Load]: ...
def thermal_strain_stress(model, u, T, T_ref, alpha) -> np.ndarray: ...  # (m, 6) σ = D(Bu − ε0)
def add_loads(model, loads: Iterable[Load]) -> None: ...  # aynı (node, dof) toplanır, tek Load kalır


# mesh/yuz_esleme.py
@dataclass(frozen=True)
class PartMesh:
    model: Model
    face_tris: Mapping[int, np.ndarray]

    def triangles(self, part: Part, ref: FaceRef) -> np.ndarray: ...
    def nodes(self, part: Part, ref: FaceRef) -> list[int]: ...  # yüzdeki tüm düğümler (kenar düğümü dahil)


def mesh_part(part, h, material, *, order=1, refine=()) -> PartMesh: ...


# analiz/dayanim.py
@dataclass(frozen=True)
class Dayanim:
    n: np.ndarray  # (n_dugum,) emniyet katsayısı, inf olabilir
    n_min: float
    dugum: int  # n_min'in düğümü
    konum: np.ndarray  # (3,)
    sigma_vM_maks: float
    gevrek: bool


def emniyet(
    model, u, Rp02: float | Mapping[str, float], *, gevrek: bool = False, T=None, T_ref=0.0, alpha=None
) -> Dayanim: ...  # T verilirse ısıl gerinme düşülür
def parca_dayanimi(
    part,
    h,
    malzeme,
    *,
    order=2,
    sabit: Sequence[FaceRef] = (),
    basinc: Sequence[tuple[FaceRef, float]] = (),
    kuvvet: Sequence[tuple[FaceRef, Sequence[float]]] = (),  # yüze toplam kuvvet, alanla dağıtılır
    g=None,
    omega=None,
    eksen=None,
    T=None,
    T_ref=0.0,
) -> tuple[PartMesh, np.ndarray, Dayanim]: ...
```
`parca_dayanimi`'nin hataları (`ModelError`):
- `sabit` boş ve hiçbir hacim veya ısıl yük yok
- `ref` bulunamadı
- malzemede `Rp02` yok
- `g` ya da `omega` verilmiş ama `rho` yok
- `T` verilmiş ama `alpha` yok

## Kabul kriterleri

### 67a (tet10)
- [ ] **K1** Şekil fonksiyonları: her Gauss noktasında `Σ N = 1` ve `Σ ∂N/∂x = 0` (abs 1e-14). Düğümlerde `N_i(x_j) = δ_ij`.
  Referans tetrahedronda `∫ N_köşe dV = −V/20` ve `∫ N_kenar dV = V/5` (abs 1e-14).
- [ ] **K2** Ağ: birim küp `order=2` ile ağlanır.
  - Her eleman 10 düğümlüdür.
  - Düz yüzlü bölgede her kenar düğümü ilgili köşelerin orta noktasındadır (abs 1e-9). Bu, gmsh → C3D10 permütasyonunu
    doğrular.
  - Bütün Gauss noktalarında `det J > 0`.
  - Toplam hacim `1.0` (göreli 1e-12).
- [ ] **K3** Eleman matrisi: `ke` simetriktir ve 6 sıfır özdeğeri vardır (rijit gövde; göreli 1e-10). Kalan özdeğerler
  pozitiftir. `ke`, öteleme altında ve döndürme altında (`T ke Tᵀ` ile) değişmez.
- [ ] **K4** Yama testleri (`2×2×2` Kuhn kutusu, tet10):
  - doğrusal alan: iç düğümler abs 1e-10, gerilme her Gauss noktasında sabit
  - **saf eğilme alanı** (Teori): sınırda yazılan 2. derece `u` iç düğümlerde abs 1e-10 tutar; her Gauss noktasında
    `σ_xx = E κ z`, diğer bileşenler abs 1e-8·`E κ`
- [ ] **K5** Konsol yakınsaması (SPEC 11 K10 kirişi, aynı Kuhn ağları ama tet10):
  - `k = 1` için `δ_uç/δ_T ≥ 0.95`
  - `k = 2` ve `k = 4` için `|1 − δ_uç/δ_T| ≤ 0.015`
  - `k = 1`'de tet10 hatası, `k = 4` tet4 hatasından (0.21) küçüktür

  Eşikler kod PR'ının ön hesabıyla teyit edilir. Tutmazsa kod incelenir; eşik değişikliği kullanıcıya sorulur.
- [ ] **K6** Kirsch (SPEC 13'ün delikli plakası, `order=2`): kalınlık ortalamalı `Kt_g`, `h = 5` ve
  `Refine(r = 8, h = 0.5)` ile `3.032`'ye %2 içinde. Aynı doğruluk tet4'te `h_local = 0.25` istiyordu.
- [ ] **K7** Lamé kalın silindir (SPEC 12 testi, `order=2`): iç yarıçapta `u_r` hatası `h = 4` ile ≤ %1. tet4 aynı
  ağda %6.1 veriyordu.
- [ ] **K8** Kütle: tet10 tutarlı kütle matrisinde `Σ_ab M_ab` (bir yön) `ρ V`'dir (göreli 1e-12). SPEC 45 ankastre çubuk
  ilk eksenel frekansı `k = 2` ağında kapalı forma %0.5 içindedir. `lumped=True` ise `ModelError`.
- [ ] **K9** CalculiX C3D10 (`tests/reference/`, `ccx` yoksa atlanır): K6 plakasının kaba ağında yer değiştirmeler göreli
  1e-6, tepkiler göreli 1e-6 içinde eşittir.
- [ ] **K10** Hatalar (`ModelError`):
  - ters çevrilmiş (`det J < 0`) eleman
  - 9 düğümlü `"tet10"` elemanı
  - `order = 3`
  - karışık tet4 + tet10 ile `boundary_triangles`

### 67b (yük, mesnet, ısıl, emniyet)
- [ ] **K11** Yüz eşlemesi (OCCT):
  - `100 × 40 × 20` kutuda 6 yüzün hepsi eşlenir.
  - Her yüzün üçgen alanları toplamı yüz alanına eşittir (göreli 1e-9).
  - Delikli kutuda silindirik delik yüzünün üçgenleri `on_cylinder` seçimiyle aynı küme olur (`order` 1 ve 2).
  - Unsur ağacından gelen bir `FaceRef` (A2) ile `triangles` aynı yüzü döndürür.
- [ ] **K12** Yüze yük:
  - Kutunun `+x` yüzüne `p = 2` basınç uygulanır. Toplam kuvvet `(−2·40·20, 0, 0) = (−1600, 0, 0)` N olur (göreli 1e-12)
    ve tet4 ile tet10'da aynıdır. tet10'da köşe düğümleri 0, kenar düğümleri `p A/3` alır.
  - Delik yüzüne iç basınçta toplam kuvvet ≈ 0 olur (abs 1e-3·`p A`; çokgen yaklaşımı tam kapanmaz).
- [ ] **K13** Asılı çubuk (`20 × 20 × 200`, `ν = 0`, çelik `ρ = 7.85e-9`, `g = (0, 0, −9810)`):
  - tet10 her ağda tamdır: uç `δ = ρ g L²/(2E) = 7.334e-6` mm (göreli 1e-8), `σ_zz(z) = ρ g z` (Gauss noktalarında göreli
    1e-8).
  - tet4'te `δ` hatası `k = 1 → 2 → 4` boyunca her adımda en az yarıya iner.
  - Tepkilerin toplamı `−m g` olur, `m = ρ V` (göreli 1e-12).
- [ ] **K14** Dönen disk (`b = 100`, `t = 5`, çelik, `ν = 0.3`, `ω = 1000`, `order=2`, `h = 5`):
  - Merkez civarında (`r < 10`) orta düzlem `σ_r` ve `σ_θ` ortalaması 32.38 MPa'ya %3 içinde.
  - Kenarda `σ_θ` 13.74 MPa'ya %3 içinde.
  - Merkezkaç yükünün toplamı `ρ ω² Σ_e V_e r⊥(merkez_e)` değerine eşittir (göreli 1e-12, yük integrasyonu tam) ve
    büyüklüğü `≤ 1e-3·ρ ω² b V` (ağ simetriye yakın).
  - Eşikler ön hesapla teyit edilir.
- [ ] **K15** Isıl yük:
  - serbest genleşme (`ΔT = 50`, 3-2-1 mesnet): tet4 ve tet10'da `u = α ΔT (x − x0)` göreli 1e-9, `σ_vM ≤ 1e-9·E α ΔT`
  - eksenel tutulu çubuk: her elemanda `σ_xx = −126` MPa (göreli 1e-9), diğer bileşenler ≈ 0
  - SPEC 56 düzlem duvarının (`T1 = 100`, `T2 = 20`) doğrusal alanı serbest gövdede: tet10'da `σ_vM ≤ 1e-8·E α ΔT`
  - aynı durumda tet4'te `max σ_vM` `k = 1 → 2 → 4` boyunca azalır
  - SPEC 56 `ThermalResult` doğrudan verilebilir; düğüm sözlüğüyle aynı sonucu verir
- [ ] **K16** Emniyet katsayısı:
  - `10 × 10 × 100` çubuk, uca `+x` yüzü yoluyla 10000 N çekme, `Rp02 = 355`: her düğümde `n = 3.55` (uç bölgesi
    dışında, göreli 1e-6), `n_min ≤ 3.55`.
  - Yüksüz modelde `n_min = inf`.
  - Gevrek grup (`dokme_demir`) için `gevrek=True` bayrağı taşınır.
  - `Rp02` olmayan malzeme `ModelError` verir.
- [ ] **K17** Uçtan uca (`analiz.parca_dayanimi`, OCCT): delikli plaka (SPEC 13) şu girdilerle kurulur:
  - `FaceRef` ile bir uç yüzü sabit
  - karşı yüze basınç
  - SPEC 66'nın `1.0577` (S355J2) kaydı

  Beklenen sonuçlar:
  - `n_min = Rp02 / (Kt_g σ_nom)` değerine %3 içinde.
  - Düğüm delik kenarındadır.
- [ ] **K18** `core/yukler.py` numpy, scipy ve `core` dışında import etmez. `ruff` temiz; 10 s'yi aşan testler
  `@pytest.mark.slow` ile işaretlenir.

## Bağımlılık
- **67a:** SPEC 11, 12, 13, 45 (hepsi birleşti). B2, 56 ve 66'yı beklemez.
- **67b:**
  - A2 `FaceRef` (birleşti; unsur ağacı adlandırması SPEC 18 / #73 ile zenginleşir, K11'in ağaç testi #73 birleşince açılır).
  - 56: K15'in `ThermalResult` maddesi için.
  - 66: K17 için (`Rp02`, `alpha`, `rho` kayıtları).
  - Bunlar olmadan `core/yukler.py` ve `mesh/yuz_esleme.py` yazılabilir.
- Bu SPEC'i kullananlar: Dalga 7 burkulma, termo-mekanik, yorulma (A10–A12), SPEC 47 analiz ekranı.

## Kapsam dışı
- Burkulma, geçici ısıl, harmonik, yorulma, mekanizma dinamiği, CalculiX köprüsünün tam akışı: Dalga 7 (A10–A13).
- Temas, doğrusal olmayan malzeme (plastisite), büyük yer değiştirme.
- tet10 ısıl eleman (56'nın eki olarak sonra gelebilir) ve hex/wedge elemanlar.
- Uyarlamalı ağ inceltme ve hata tahmini (ZZ / SPR).
- Montajda parçalar arası yük aktarımı (bağlantı elemanları, cıvata ön gerilmesi).
