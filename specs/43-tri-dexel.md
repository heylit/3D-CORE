# SPEC 43 — Tri-dexel talaş simülasyonu: her yönde takım ekseni

> **Durum: ONAYLANDI** (kullanıcı, 2026-10-18 10:38 UTC, proje sohbetinde yazılı onay: "SPEC … 41–44 metinlerini onaylıyorum"). Metin kullanıcı onayı olmadan değişmez. Bağımlılık: SPEC 05 (`cam/sim`, tek yönlü dexel; `main`'e girince),
> SPEC 41 (`Frame`, `Move.axis`). 42 ile paralel yürür.

## Amaç
SPEC 05'in tek yönlü (Z) dexel'ini **üç dik ışın ailesine** (X, Y, Z) genişleterek, takım ekseni herhangi bir
yönde olan ve hareket boyunca değişen (3+2 ve eş zamanlı 5 eksen) programları simüle etmek: kaldırılan
malzeme, alttan ve yandan açılan boşluklar (z-haritasının ve Z dexel'in gösteremediği), hızlı harekette
çarpma, sap / tutucu çarpışması ve kapalı parça ağına göre çakma / kalan malzeme.

## Teori

### Izgara ve ışınlar
Kutu stok (`Stock`), hücre `Δ`: SPEC 05 kuralıyla `nx, ny, nz`, `dx, dy, dz`. Üç aile:
- Z ışınları: XY hücre merkezlerinden (05 ile **aynı** ızgara), aralıklar `z` üzerinde.
- X ışınları: YZ hücre merkezlerinden `(y_j, z_k)`, aralıklar `x` üzerinde.
- Y ışınları: XZ hücre merkezlerinden `(x_i, z_k)`, aralıklar `y` üzerinde.
Her ışında 05'teki aralık listesi ve aralık farkı kuralı aynen (sıralı, ayrık, boy > 0). Başlangıç: her
ışında stok boyunca tek aralık.
- Hacim her aileden ayrı: `V_z = Σ (u − l)·dx·dy`, `V_x = Σ (u − l)·dy·dz`, `V_y = Σ (u − l)·dx·dz`.
  Her biri ızgara adımıyla `O(Δ)` yakınsar; rapor edilen hacim `V = (V_x + V_y + V_z)/3`, tutarlılık ölçüsü
  `max |V_i − V|`. Kaynak: Hook, "Real-time shaded NC milling display" (dexel, 1986); Zhu vd., tri-dexel (2010);
  CAM araştırma notları.

### Takım katısı (takım çerçevesinde, uç orijinde, eksen `+z`)
- Kesen kısım: `0 ≤ z ≤ L_f` boyunca dönel cisim, profil SPEC 05 `h(d)` (düz, küresel, köşe radyüslü).
  Katı: `{ (x, y, z): d = √(x² + y²) ≤ R, h(d) ≤ z ≤ L_f }`. Dışbükeydir.
- Gövde: SPEC 05 `body_steps` basamakları `(ρ_j, H_j)`: `d ≤ ρ_j`, `H_j ≤ z ≤ H_{j+1}` (sonuncusu sonsuz).
- Işın–takım kesişimi: ışın takım çerçevesine çevrilir (`Frame` ile), dışbükey katıyla kesişim tek aralıktır;
  silindir, küre ve tor parçaları için kapalı form (tor için dördüncü derece denklem, `numpy.roots` veya
  aralık içinde Newton), hata ≤ 1e-9 mm.

### Hareketin süpürmesi
Hareket `k`: uç `p₀ → p₁` doğrusal, eksen `a₀ → a₁` slerp (`Move.axis`; `None` → yolun `frame`'inin `z`'si, o da
yoksa `+Z`), `t ∈ [0, 1]`.
- **Sabit eksenli hareket** (`angle(a₀, a₁) ≤ 1e-12`): süpürülen küme `takım ⊕ [p₀, p₁]` dışbükeydir; ışınla
  kesişimi tek aralıktır. Uç noktaları (giriş, çıkış) `t` üzerinde dışbükey / içbükey bir fonksiyonun en küçüğü /
  en büyüğüdür; kapalı form ya da altın oran araması serbest, **şart: aralık uçlarının hatası ≤ 1e-6 mm**
  (yoğun örneklemeli kaba kuvvet referansına göre, 05 K5 gibi).
- **Değişen eksenli hareket:** hareket, `n = ⌈θ·ρ_max / σ⌉` alt adıma bölünür (`θ = angle(a₀, a₁)`,
  `ρ_max = √(L_f² + R²)` kesen kısmın uca en uzak noktası, `σ` örnekleme toleransı, varsayılan `Δ/4`); her alt adım
  orta eksenle sabit eksenli harekettir. Hata sınırı: gerçek süpürmeden sapma ≤ `σ/2`.
- Yaylar (`G2/G3`, yalnız sabit eksenli yolda) 05 kuralıyla kirişlere bölünür; simülasyonda tek adım kalır.
- Işın seçimi: hareketin (takımın iki uç konumu ve alt adımları) sınır kutusuyla kesişen ışınlar.

### Çarpışma ve çakma
05 kayıt biçimi aynen (`Collision`, `(kind, k)` başına tek kayıt, eşik `tol`):
- `hizli_carpma`: `G0` hareketinin kaldırdığı en uzun ışın parçası `> tol`.
- `sap_carpma` / `tutucu_carpma`: alt adımdan **önceki** malzemeyle gövde basamağının ışın kesişimi `> tol`
  (batma = kesişim aralığının boyu, üç aileden en büyüğü).
- **Parça dexel'i:** kapalı üçgen ağı (SPEC 06 `TriMesh`) her ışınla kesilir (Möller–Trumbore); kesişimler
  sıralanır, çiftler halinde parça içi aralıkları verir. Tek sayıda kesişim (ağ kapalı değil ya da ışın kenara
  denk geliyor) → ışın `1e-9·Δ` kadar kaydırılıp yeniden denenir; yine tekse `CamError`.
- `cakma`: bir adım parça içinde `gouge_tol`'dan uzun malzeme kaldırıyorsa (`depth` = ışın üzerindeki en uzun
  parça içi kaldırma); `rest_volume` = malzeme ∖ parça, `gouge_volume` = parça ∖ malzeme (her aile için, ortalama).

### 05 ile çapraz kontrol
Takım ekseni `+Z` olan programda Z ailesi 05 dexel'iyle **aynı** sonucu verir (aralık uçları 1e-6 mm, hacim
rel 1e-9 aynı ızgarada); X ve Y aileleri aynı katıyı başka yönden örnekler, hacimleri `O(Δ)` ile aynı değere yakınsar.

## Dosyalar
- Yeni: `cam/sim/tridexel.py` (`TriDexel`, ışın–takım kesişimi, süpürme), `cam/sim/raymesh.py` (parça dexel'i),
  `cam/sim/simulate5.py` (`simulate5` sürücüsü), `tests/cam/test_tridexel_*.py`, `durum/43-tri-dexel.md`.
- Kullanılır (değişmez): `cam/model.py`, `cam/sim/dexel.py` (aralık farkı), `cam/sim/sweep.py` (`tool_height`,
  `body_steps`), `cam/sim/timing.py` (`Machine`, süre), `cam/dropcutter.py` (`TriMesh`), `cam/multiaxis/indexed.py`.
- Dokunulmayacak: tüm `*/model.py`, SPEC 05'in mevcut dosyaları (`simulate`, `ZMap`, `DexelMap` imzaları), ortak dosyalar.

## Arayüz
Hepsi `cam.sim`'den de dışa açılır (05'in `__init__.py`'sine yalnız import satırı eklenir).
- `@dataclass TriDexel(x0, y0, z0, dx, dy, dz, nx, ny, nz)` — iç saklama serbest.
  - `TriDexel.from_stock(stock: Stock, cell: float, max_rays: int = 3_000_000)` — `cell ≤ 0`, sonsuz, ışın sayısı
    `nx·ny + ny·nz + nx·nz > max_rays` → `CamError`.
  - `intervals(axis: str, i: int, j: int) -> list[tuple[float, float]]` — `axis ∈ {"x", "y", "z"}`; Z için `(i, j)` = (x, y)
    hücresi, X için (y, z), Y için (x, z).
  - `volumes() -> tuple[float, float, float]` (`V_x, V_y, V_z`), `volume() -> float`, `copy()`.
- `ray_tool(tool: Tool, origin, direction, tip, axis, part: str = "kesen") -> tuple[float, float] | None` —
  ışın parametresinde kesişim aralığı; `part ∈ {"kesen", "govde"}` (gövdede basamak adıyla en derin kesişim).
- `part_intervals(mesh: TriMesh, origin, direction) -> list[tuple[float, float]]`.
- `simulate5(ops: list[Toolpath], stock: Stock, cell=1.0, machine: Machine | None = None,
  part: TriMesh | None = None, sigma: float | None = None, arc_tol=1e-3, tol=1e-6, gouge_tol=1e-3,
  max_rays=3_000_000, initial: TriDexel | None = None) -> SimResult5`
  - `@dataclass SimResult5(tridexel: TriDexel, steps: list[SimStep], collisions: list[Collision],
    removed_volume: float, total_time: float)`, `rest_volume()`, `gouge_volume()` (parça yoksa `CamError`).
  - `SimStep`, `Collision`, `Machine` 05'tekiyle aynı sınıflar; süre 05 kuralıyla uç yolu boyundan.
  - `CamError`: boş `ops`, `CylinderStock`, `LatheTool`, `G95`, geçersiz `Toolpath`, birim olmayan `Move.axis`,
    değişen eksenli yay, `sigma ≤ 0`, `tol/arc_tol/gouge_tol ≤ 0`, `initial` ızgarası uyuşmuyor.

## Kabul kriterleri
Testlerde uydurma geometri; beklenen değerin kaynağı test yorumunda.
- [ ] K1 Izgara: `from_stock` üç ailenin ışın sayısı ve merkezleri; başlangıçta `V_x = V_y = V_z = Stock.volume` rel 1e-12;
  hatalar `CamError` — `tests/cam/test_tridexel_grid.py`
- [ ] K2 Işın–takım: düz, küresel ve köşe radyüslü takımda eğik eksenle ışın kesişimi kapalı form / yoğun örnekleme
  referansıyla 1e-9; gövde basamakları — `tests/cam/test_tridexel_ray.py`
- [ ] K3 Eğik delik: eksen düşeyle `θ = 0°, 20°, 40°`, düz takım `H` kalınlıklı stoktan eksen boyunca tam geçiyor →
  kaldırılan hacim `πR²H / cos θ` (Cavalieri); her aile ve ortalama `P·Δ·L` mertebesi toleransla, Δ = 1, 0.5, 0.25 mm'de
  hata azalıyor — `tests/cam/test_tridexel_volume.py`
- [ ] K4 Yan delik: eksen `+X` (yatay), küresel takım `x = xmax` yüzünden `d ≥ R` derine dalıyor → hacim
  `πR²(d − R) + ⅔πR³`; Z ailesinin üst yüzeyi değişmiyor (z-haritası bu boşluğu göremez), X ailesinde kesin
  aralıklar 1e-6 — `test_tridexel_volume.py`
- [ ] K5 Sabit eksenli süpürme: eğik eksenli düz ve küresel takımla doğrusal kanal; ışın aralık uçları yoğun
  örneklemeli kaba kuvvet referansıyla ≤ 1e-6 mm — `test_tridexel_ray.py`
- [ ] K6 Değişen eksen: uç sabit, eksen 0°'dan 30°'ye dönen düz takım; kaba kuvvet referansıyla (yoğun açısal örnekleme)
  aralık sapması ≤ `σ/2`; `σ` yarıya inince hata azalıyor — `test_tridexel_ray.py`
- [ ] K7 05 ile çapraz kontrol: 05 K16 tipi rastgele (sabit tohum) dikey eksenli program: Z ailesi aralıkları 05 dexel'iyle
  1e-6, hacim rel 1e-9; X ve Y hacimleri `O(Δ)` toleransta aynı — `tests/cam/test_tridexel_cross.py`
- [ ] K8 Parça dexel'i: elle kurulmuş küp (12 üçgen) ve bilinen ağlı küre (kiriş hatası `ε`) için ışın başına parça
  aralıkları formülle; kenara denk gelen ışında kaydırma çalışıyor; kapalı olmayan ağ → `CamError` — `tests/cam/test_tridexel_part.py`
- [ ] K9 Çakma: 3+2 eğik eksenle blok yüzüne 0.2 mm giren yol → `cakma`, `depth = 0.2` (yüzeye dik ışın ailesinde 1e-6);
  teğet yolda kayıt yok; `rest_volume` / `gouge_volume` beklenen (ızgara toleransıyla) — `test_tridexel_part.py`
- [ ] K10 Çarpışma: stoktan geçen eğik `G0` → `hizli_carpma` doğru `k`, `depth` geçilen kalınlık (1e-6); kısa kesici boylu
  eğik takımla derin yan kanal → `sap_carpma` `depth` bilinen değer; tutucu basamağı → `tutucu_carpma` — `tests/cam/test_tridexel_collision.py`
- [ ] K11 Hatalar: `simulate5` hata listesi → `CamError` — `tests/cam/test_tridexel_errors.py`
- [ ] Tüm testler yeşil, `ruff check .` ve `ruff format --check .` temiz, 0 "uygulanmamış"; 10 s'den uzun testler `slow`

## Kapsam dışı
- Tri-dexel'den yüzey ağı çıkarma (görselleştirme, SPEC 24 / 25 köprüsü ayrı iş); voksel / oktree.
- Parça ağından ya da dökme stoktan başlangıç tri-dexel'i, `CylinderStock` (torna-freze).
- Alt kesik takımlar (T kanal, kırlangıç), matkap uç konisi, takım sehimi ve kesme kuvveti.
- Tezgâh gövdeleri, fikstür ve eksen sınırı çarpışması: SPEC 44.
- 05'in `simulate`'inin değişmesi: 43 yalnız yeni sürücü ekler.
