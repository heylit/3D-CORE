# SPEC 39 — 3B kalan malzeme ve işlenmiş parça ikizi

> **Durum: TASLAK** (kullanıcı onayı bekliyor). Onaydan sonra metin kullanıcı onayı olmadan değişmez.

## Amaç
SPEC 05 simülasyonunun bıraktığı stok durumundan (z-haritası ya da dexel) **3B kalan malzemeyi** ölçen,
bölgelere ayıran ve SPEC 06 / 06b yollarını yalnız malzemeye giren hareketlere indirerek **kalan malzeme
işlemesi** üreten; aynı durumdan kapalı bir **işlenmiş parça ağı** (STL) ve CAD parçasına göre işaretli
**sapma haritası** çıkaran saf numpy modülü. Bu adım bitince büyük takımla ince işlenmiş iç köşede küçük takımın
kalan malzeme yolu yalnız köşe bandında keser ve köşede kalan kesit `(1 − π/4)·R₂²`'ye iner; simüle edilen
parçanın ağı z-haritası hacmini birebir taşır ve sapma haritası bilinen fazlalık ve çakmayı doğru işaretle verir
(SPEC 25'in kapsam dışı bıraktığı "işlenmiş şekil").

## Teori

### Çerçeve
- Her şey iş koordinatında (WCS), birim mm. Takım ekseni +Z (3 eksen). Hareket noktası takımın uç noktasıdır (SPEC 05).
- **Durum** (`state`): SPEC 05'in `ZMap`'i ya da `DexelMap`'i (ör. `SimResult.zmap`, `SimResult.dexel`). Izgara,
  hücre merkezleri ve hacim tanımları SPEC 05'tekiyle aynıdır; bu SPEC yalnız okur, `cam/sim/` dosyalarını değiştirmez.
- **Parça**: üçgen ağı `(V, T)` (SPEC 02 `Part.mesh(tol)`, SPEC 06 `TriMesh`) ve aynı ızgarada parça
  z-haritası `z_P = mesh_zmap(V, T, grid)` (SPEC 05; parça yoksa `−∞`).
- Hücre `(i, j)` merkezi `q = (x_i, y_j)`; z-haritasında üst yüzey `z(q)`, dexel'de aralık listesi `I(q)` ve
  `top(q) = max u` (aralık yoksa `zmin`).

### Kalan malzeme kalınlığı
Pay `δ ≥ 0` (bilerek bırakılan, ör. ince işleme payı) ile hücrenin **taban** yüksekliği
`b(q) = max(z_P(q) + δ, zmin)`. Düşey kalan kalınlık:
- z-haritası: `t(q) = max(z(q) − b(q), 0)`,
- dexel: `t(q) = Σ_{[l,u] ∈ I(q)} max(u − max(l, b(q)), 0)` (tabanın üstündeki tüm aralıkların toplamı;
  SPEC 05'in `rest_volume`'u yalnız üst yüzeyi kullanır, burada ikinci bağlamanın alttan bıraktığı boşluk da sayılır).

`V_kalan = Σ t(q)·dx·dy`. Kutu stokta ve gövde çarpışmasız programda iki model aynı `t`'yi verir (SPEC 05 K19).

### Kalan malzeme bölgeleri
Maske `M = { q : t(q) > t_min }`. Bölgeler `M`'nin **8 komşulu** bağlı bileşenleridir (köşeden değen iki hücre
aynı bölge: köşede kalan ince malzeme şeridi çapraz örneklenince kopmasın). Her bölge için: hücre sayısı,
hacim `Σ t·dx·dy`, en büyük kalınlık `t_max` ve yeri, XY sınır kutusu (hücre kenarlarıyla, merkezlerle değil).
Bölgeler hacme göre azalan, eşitlikte en küçük hücre indeksine (`c = j·nx + i`) göre sıralanır.

### Malzemeye girme (engagement)
Doğrusal bir hareketin hücrede kestiği düşey küme SPEC 05'teki gibi tek aralıktır: `[e(q), e_üst(q)]`,
`e(q) = min{ z(t) + f(d(t)) : d(t) ≤ R }`, `e_üst(q) = L_f + max{ z(t) : d(t) ≤ R }` (`L_f` = `flute_length`).
Burada `f` takımın alt profilidir: `f = Cutter.from_tool(tool).f` (SPEC 06b; düz, küresel, torik, konik).
`f` dışbükey ve azalmayan, `d(t)` dışbükey olduğundan `g(t) = z(t) + f(d(t))` dışbükeydir ve tek minimumu
vardır (SPEC 05'teki gerekçe); şart: `e(q)` hatası ≤ 1e-6 mm. Düz, küresel ve torik takımda sonuç SPEC 05
`sweep_envelope` ile aynıdır (1e-9).

Hareketin hücrede **kaldıracağı boy**:
- z-haritası: `r(q) = max(z(q) − max(e(q), zmin), 0)`,
- dexel: `r(q) = |I(q) ∩ [e(q), e_üst(q)]|` (aralıklarla kesişimin toplam boyu).

Hareketin **girme derinliği** `g_k = max_q r(q)`. Yaylar SPEC 05 kuralıyla kirişlere bölünür
(`n = ⌈|Δθ| / (2·acos(1 − ε_yay / r))⌉`); yayın `g_k`'sı kirişlerinin en büyüğüdür, yay tek hareket olarak kalır.

### Kalan malzeme süzgeci
Girdi bir 3 eksen `Toolpath` (SPEC 03, 06, 06b yolu) ve başlangıç durumu. Hareketler sırayla gezilir; çalışan bir
**süzgeç durumu** tutulur (başlangıçta `state`'in kopyası):
1. `G0` hareketleri atılır (bağlantılar aşağıda yeniden kurulur).
2. Bir kesme hareketi (`G1`, `G2`, `G3`) için süzgeç durumuna göre `g_k` hesaplanır.
   - `g_k > t_min` → hareket **tutulur** ve süzgeç durumundan kaldırılır (`z ← max(zmin, min(z, e))`; dexel'de aralık farkı).
   - aksi → hareket **atılır** ve durum değişmez.
3. Tutulan ardışık hareketler bir **koşu** oluşturur: bir tutulan hareketin başlangıcı, bir önceki tutulan hareketin
   bitişine eşitse (1e-9) aynı koşudadır. Koşular arasına **bağlantı** eklenir:
   `G0` `z_safe`'e, `G0` XY ile hedefin üstüne, `G0` `z_yak`'a, `G1 plunge_feed` ile koşunun ilk noktasına.
   `z_yak = min(z_safe, max(C_z, max_{d(q,C) ≤ R} top(q)) + clearance)`; `C` koşunun ilk noktası, `top` süzgeç
   durumunun o andaki üst yüzeyi. Yol `(x₀, y₀, z_safe)`'te başlar (ilk koşunun üstü) ve son noktadan `G0` ile `z_safe`'e çıkarak biter.

**Özellikler (testlerin dayandığı):**
- *Güvenlik:* bağlantılar `z_safe > zmax` olduğundan malzemeye girmez; `z_yak`'tan inen dalma, koşunun ilk
  hareketinin `t = 0` anındaki takım konumunun kestiğinin alt kümesini keser. Bu yüzden süzülmüş yol SPEC 05 ile
  `initial = state` alınarak simüle edilince son yüzey süzgecin son durumuyla aynıdır (1e-9) ve hızlı çarpma yoktur.
- *Sınır:* aynı yolun süzülmemiş hali ile karşılaştırınca her hücrede `0 ≤ z_süzülmüş − z_tam ≤ t_min`.
  Gerekçe: `z_tam = min(z₀, min_k e_k)`; minimum tutulan bir hareketteyse eşitlik, atılan `m` hareketindeyse
  atıldığı anda `z_süzgeç(m) − e_m ≤ t_min` ve sonrası yalnız alçalır. (Dexel'de aynı eşitsizlik her aralık için,
  kalınlık toplamı üzerinden: `0 ≤ t_süzülmüş − t_tam ≤ t_min·(aralık sayısı)`; testler kutu stokta tek aralıkla yapılır.)
- *Tek yönlülük:* malzeme yalnız azaldığından, başlangıç durumuna göre `g_k ≤ t_min` olan bir hareket sonra da
  girmez; süzgeç hiçbir gerekli hareketi yalnız sıra yüzünden atmaz.
- Hiç hareket tutulmazsa sonuç yolu yoktur (`None`): kalan malzeme zaten `t_min` altında.

### Kalan malzeme işlemesi (SPEC 06 / 06b ile)
- **Kalan ince işleme:** `rest_finish` = SPEC 06 `finish(mesh, tool, r, floor)` yolu + süzgeç. Büyük takımın
  ulaşamadığı iç köşe, dar kanal ve küçük radyüslerde yalnız malzemeye giren raster parçaları kalır.
- **Kalan kaba işleme:** `rest_rough` = SPEC 06 `rough(mesh, stock, tool, r, a_p, z_bottom, allowance)` yolu +
  süzgeç. Önceki kaba işlemenin (ör. 05 ile simüle edilmiş büyük takım) bıraktığı basamak ve köşe malzemesi.
- 06'nın yolları değişmez; süzgeç onların çıktısını işler. Takım: 06b'nin `Cutter.from_tool` ile kabul ettiği
  takımlar (düz, köşe radyüslü, küresel, konik); `DRILL` ve `LatheTool` → `CamError`.

**Analitik referans: iç köşe.** Düşey duvar (`x = 0`, malzeme `x < 0`) ve yatay taban (`z = 0`) arasında, köşe
boyunca (Y) `L` uzunlukta. Küresel `R₁` takım tabana ve duvara teğet kalır: merkezi `(R₁, R₁)`, `0 ≤ x ≤ R₁` için
erişilen en alçak yüzey `z₁(x) = R₁ − √(R₁² − (R₁ − x)²)`. Kalan kesit alanı
`A(R) = ∫₀^R (R − √(R² − (R − x)²)) dx = R² − πR²/4 = (1 − π/4)·R²`. Kalan malzeme bandının genişliği
`w(t) = R − √(R² − (R − t)²)` (`t(x) > t` olan `x` aralığı). Küresel `R₂ < R₁` ile kalan işleme sonrası kalan
kesit `A(R₂)`, kaldırılan `A(R₁) − A(R₂)`. Düz takımla 2B iç köşede (dikdörtgen cep köşesi) aynı alan düşey
kesitte değil yatay kesitte geçerlidir: köşe başına `(1 − π/4)·R²·H`.

### İşlenmiş parça ağı (ikiz)
**Kolon ağı (kesin):** her hücre, z-haritasında `[zmin, z(q)]`, dexel'de her aralığı `[l, u]` için
`[x_i ± dx/2] × [y_j ± dy/2] × [l, u]` dik prizmasıdır. Ağ, bu prizmaların birleşiminin sınırıdır:
- Her aralık için üst yüz (`z = u`, normal +Z) ve alt yüz (`z = l`, normal −Z), her biri 2 üçgen.
- İki komşu hücre (ya da hücre ile stok dışı) arasındaki dik duvar: iki hücrenin aralık kümelerinin
  **simetrik farkı** kadar dikdörtgen parça; normal, malzemesi olan hücreden dışarı. Her parça 2 üçgen.
- Boyu sıfır aralık yoktur (SPEC 05 dexel kuralı); z-haritasında `z = zmin` olan hücre prizmasızdır.
- Köşeleri ortak kullanan, kaynaklanmış (indeksli) ağ: aynı koordinatlı köşe tek kez.
Özellikler: **kapalı** (her yönlü kenar `(a, b)` sayısı, ters yönlü `(b, a)` sayısına eşit; yalnız çapraz değen
hücrelerde bir kenar dört üçgende olabilir), **dışa yönlü**, hacmi (diverjans teoremi
`V = Σ (v₀ · (v₁ × v₂))/6`) durumun `volume()`'ıyla **aynı** (rel 1e-12). Her üst yüz üçgeni ait olduğu hücrenin
indeksini taşır (`face_cell`; duvar ve alt yüzlerde −1): Tezgah sapma rengini hücreden üçgene böyle taşır.

**Yüzey ağı (görüntü için, yalnız z-haritası):** düğümler hücre köşelerinde `(nx + 1) × (ny + 1)`; düğüm yüksekliği
komşu (1, 2 ya da 4) hücrenin `z` ortalaması. Her ızgara karesi sabit köşegenle (`(i, j) – (i+1, j+1)`) iki üçgen;
dört yan perde stok sınırında `zmin`'e iner, taban `zmin`'de. Kapalı ve dışa yönlü. Sabit yükseklikli haritada
hacim kesin; genel durumda hacim hatası ≤ `P·Δ·H` (`P` yüksekliği değişen hücre sınırlarının toplam boyu,
`H` en büyük yükseklik farkı, `Δ = max(dx, dy)`): dik duvarlar yarım hücre kayar.

**STL (ikili):** 80 bayt başlık (ad, ASCII, boşlukla doldurulmuş, `solid` ile başlamaz), `uint32` üçgen sayısı,
her üçgen 50 bayt: `float32` normal (üçgenin birim normali, sağ el kuralı), üç köşe (`float32 × 3` her biri),
`uint16` 0. Küçük sonlu (little-endian). Koordinat `float32`'ye yuvarlanır.

### Sapma haritası
Her hücre için ölçüm noktası `p = (x_i, y_j, top(q))`. İşaretli sapma:
- `z_P(q) = −∞` ve `top(q) = zmin` → `s = 0` (ne malzeme ne parça).
- aksi: `s = σ · dist(p, parça ağı)`, `σ = +1` eğer `top(q) > z_P(q)` (fazlalık: nokta parçanın dışında),
  `σ = −1` eğer `top(q) < z_P(q)` (çakma: nokta parçanın içinde), eşitse `s = 0`.
- `dist(p, ağ) = min_üçgen dist(p, üçgen)`: kesin nokta–üçgen uzaklığı (Ericson, *Real-Time Collision Detection*,
  5.1.5: yüz, kenar ve köşe Voronoi bölgeleri). Hızlandırma yapısı serbesttir; sonuç kaba kuvvetle (tüm üçgenler) aynı
  olmalı (1e-12).
- Ayrıca düşey fark `dz = top(q) − max(z_P(q), zmin)` verilir (SPEC 05 `rest/gouge_volume` ile tutarlı).
Neden 3B uzaklık: dik duvarda kalan `0.3 mm` malzeme, duvara bitişik hücrede düşey farkı duvar yüksekliği kadar
gösterir; 3B uzaklık doğru olarak `≤ 0.3`'tür. Neden üst yüzey: 3 eksende takım yukarıdan geldiği için parçanın
üst yüzeyi (`z_P`) altında kesmek çakmadır (SPEC 05 ile aynı varsayım); parçanın alttan (ikinci bağlama)
yüzeyleri bu SPEC'te ölçülmez.

**Özet:** `max_excess = max(s)` (≥ 0), `max_gouge = max(−s)` (≥ 0), `rms = √(mean(s²))` (yalnız `s` tanımlı ve
`z_P > −∞` ya da `top > zmin` olan hücrelerde), ve tolerans bandı sayımı: verilen kenarlar `b_0 < b_1 < … < b_m`
için her `[b_i, b_{i+1})` aralığına düşen hücre sayısı, ayrıca `< b_0` ve `≥ b_m`. `within(lo, hi)`: tüm ölçülen
hücrelerde `−lo ≤ s ≤ hi` mi (ör. çizim toleransı `+0.1 / −0.0`).

## Dosyalar
- Yeni: `cam/kalan3d.py` (kalınlık, bölgeler, girme derinliği, süzgeç, `rest_finish`, `rest_rough`),
  `cam/sim/ikiz.py` (kolon ve yüzey ağı, ağ hacmi, STL yazıcı, nokta–üçgen uzaklığı, sapma haritası);
  `tests/cam/test_kalan3d.py`, `tests/cam/test_ikiz.py`; `durum/39-kalan3d-ikiz.md`
- Dokunulmayacak: `cam/model.py` ve tüm `*/model.py`, `geometry/part.py`, `cam/sim/` içindeki mevcut dosyalar
  (05'in imzaları değişmez; `cam/sim/__init__.py` de değişmez, `ikiz` modülü `cam.sim.ikiz` olarak içe aktarılır),
  `cam/ops3d.py`, `cam/dropcutter.py`, `cam/cutter.py` (06 / 06b), `cam/gcode/`, `pyproject.toml`, `.github/`,
  `CLAUDE.md`, `BASLANGIC.md`, `DURUM.md`, `docs/yol-haritasi.md`, `core/**`
- Bağımlılık: numpy. `cam.kalan3d` → `cam.model`, `cam.sim` (ızgara, dexel, `sweep_envelope`, `sweep_top`),
  `cam.cutter` (06b `Cutter`), `cam.ops3d` (06 `finish`, `rough`, `Raster`), `cam.dropcutter` (`TriMesh`).
  `cam.sim.ikiz` → `cam.sim`, `cam.model`. OCCT yalnız `@pytest.mark.occt` testlerinde (`Part.mesh`). Yeni bağımlılık yok.
- `cam/model.py` eki **gerekmiyor**.

## Arayüz
Hatalar `cam.model.CamError`. `State = ZMap | DexelMap`.

### `cam/kalan3d.py`
- `rest_thickness(state: State, part_z: np.ndarray | None = None, allowance: float = 0.0) -> np.ndarray` —
  `(ny, nx)` `t(q)`. `part_z=None` → her yerde `−∞`. `allowance < 0`, sonlu olmayan, `part_z` şekli uyuşmuyor → `CamError`.
- `@dataclass RestRegion(cells: np.ndarray (k, 2) int [i, j], volume: float, t_max: float,
  at: tuple[float, float, float], bbox: tuple[float, float, float, float])` — `at` = en kalın hücrenin merkezi ve
  `top`'u; `bbox = (xmin, xmax, ymin, ymax)` hücre kenarlarıyla.
- `rest_regions(state: State, t: np.ndarray, t_min: float) -> list[RestRegion]` — yukarıdaki kural ve sıra.
  `t_min < 0` veya `t` şekli uyuşmuyor → `CamError`. Bölge yoksa `[]`.
- `engagement(tool: Tool, p0, move: Move, state: State, arc_tol: float = 1e-3) -> float` — `g_k` (durum değişmez).
- `@dataclass RestPath(toolpath: Toolpath | None, state: State, kept: list[int], removed: float)` — `kept` girdi
  yolundaki tutulan hareketlerin indeksleri (artan), `state` süzgecin son durumu (girdi değişmez, kopya),
  `removed` = başlangıç ve son hacim farkı.
- `rest_filter(path: Toolpath, state: State, t_min: float = 0.02, z_safe: float | None = None,
  clearance: float = 1.0, plunge_feed: float | None = None, arc_tol: float = 1e-3) -> RestPath` —
  `z_safe=None` → `path.start[2]`; `plunge_feed=None` → yolun ilk `G1` beslemesi. `CamError`: `path.validate()`
  hatası, `LatheTool`, `DRILL`, `plane != XY`, `feed_mode != PER_MIN`, `t_min < 0`, `clearance < 0`,
  `plunge_feed ≤ 0`, `z_safe ≤ state.zmax`, `arc_tol ≤ 0`. Çıkan yolun adı `girdi.name + " (kalan)"`, `rpm` girdiyle aynı.
- `rest_finish(mesh: TriMesh, tool: Tool, r: Raster, state: State, t_min: float = 0.02,
  floor: float | None = None) -> RestPath` — `rest_filter(finish(mesh, tool, r, floor), state, t_min,
  r.z_safe, r.clearance, r.plunge_feed)`.
- `rest_rough(mesh: TriMesh, stock: Stock, tool: Tool, r: Raster, a_p: float, z_bottom: float, state: State,
  allowance: float = 0.0, t_min: float = 0.02) -> RestPath` — `rest_filter(rough(...), state, t_min, r.z_safe,
  r.clearance, r.plunge_feed)`. `state`'in ızgarası `stock`'un XY ve Z sınırlarıyla aynı değilse → `CamError`.

### `cam/sim/ikiz.py`
- `@dataclass TwinMesh(V: np.ndarray (n, 3), T: np.ndarray (m, 3) int, face_cell: np.ndarray (m,) int)`
  - `volume() -> float` (diverjans teoremi), `is_closed() -> bool` (yönlü kenar dengesi), `to_stl(path, name="ikiz")`.
- `twin_mesh(state: State, mode: str = "kolon") -> TwinMesh` — `mode ∈ {"kolon", "yuzey"}`; `"yuzey"` yalnız
  `ZMap`; aksi `CamError`. Malzemesi hiç kalmamış durum → `CamError` (boş katı).
- `mesh_volume(V, T) -> float` — `Σ v₀·(v₁ × v₂) / 6`.
- `write_stl(path, V, T, name: str = "ikiz") -> None` — yukarıdaki ikili biçim; `T` aralık dışı indeks, sonlu
  olmayan `V`, ASCII olmayan ya da 80 bayttan uzun ad → `CamError`.
- `point_triangle_distance(p: np.ndarray (k, 3), a, b, c) -> np.ndarray (k,)` — tek üçgen, kesin.
- `point_mesh_distance(p: np.ndarray (k, 3), V, T) -> np.ndarray (k,)` — tüm ağa en kısa uzaklık.
- `@dataclass Deviation(s: np.ndarray (ny, nx), dz: np.ndarray (ny, nx), measured: np.ndarray (ny, nx) bool,
  max_excess: float, max_gouge: float, rms: float)`
  - `bands(edges: list[float]) -> np.ndarray (m + 2,) int` — kesin artan kenarlar, aksi `CamError`.
  - `within(lo: float, hi: float) -> bool` — `lo, hi ≥ 0`.
- `deviation(state: State, V: np.ndarray, T: np.ndarray, part_z: np.ndarray | None = None) -> Deviation` —
  `part_z=None` → `mesh_zmap(V, T, grid)` (SPEC 05). Boş ağ, aralık dışı indeks, şekil uyuşmazlığı → `CamError`.

## Kabul kriterleri
Testlerde uydurma geometri; beklenen değerin kaynağı test yorumunda. Durumlar elle kurulur (`ZMap.from_stock` +
`z` atama, `DexelMap.subtract`) ya da SPEC 05 `simulate` ile üretilir.
- [ ] K1 Kalınlık: elle kurulmuş z-haritası ve parça z-haritasında hücre başına formül (birebir); `part_z = −∞`
  hücrede `z − zmin`; `allowance` tabanı yükseltir, `zmin`'in altına inmez; dexel'de iki aralıklı hücrede
  aralık toplamı; `allowance < 0`, şekil uyuşmazlığı → `CamError` — `tests/cam/test_kalan3d.py`
- [ ] K2 Bölgeler: elle maskelerde (iki ayrık blok, köşeden değen iki hücre = tek bölge, halka, boş) bölge
  sayısı, hücre kümesi, hacim (rel 1e-12), `t_max` ve yeri, kenarlı `bbox`, sıralama kuralı — `test_kalan3d.py`
- [ ] K3 Girme derinliği: düz, küresel ve torik takımda `e(q)` SPEC 05 `sweep_envelope` ile 1e-9; konik takımda
  yoğun örneklemeli (≥ 10⁵ t) kaba kuvvetle ≤ 1e-6; `g_k` elle hesaplanan basamaklı yüzeyde (yatay hareket,
  bilinen basamak) kapalı formla 1e-9; dexel'de iki aralıklı hücrede kesişim boyu — `test_kalan3d.py`
- [ ] K4 Süzgeç uç durumları: tamamen havada (stok üstünde) bir yol → `toolpath is None`, `kept == []`, durum
  değişmez; tamamen malzemede bir yol → tüm kesme hareketleri tutulur, sırası ve uç noktaları aynı; girdi durumu
  değişmez — `test_kalan3d.py`
- [ ] K5 Süzgeç özellikleri: rastgele (sabit tohum) 3 eksen program ve rastgele başlangıç yüzeyinde (z-haritası ve
  dexel, düz ve küresel takım): (a) süzülmüş yol `validate()` geçer, `z_safe`'te başlar ve biter; (b) SPEC 05
  `simulate(..., initial=state)` ile son yüzey `RestPath.state` ile 1e-9 ve hiç `hizli_carpma` yok;
  (c) süzülmemiş yolun simülasyonuna göre her hücrede `0 ≤ z_süzülmüş − z_tam ≤ t_min + 1e-9`;
  (d) her tutulan hareketin, kendisinden önceki tutulanlar uygulanmış durumdaki `g_k`'sı `> t_min`, her atılanınki `≤ t_min` — `test_kalan3d.py`
- [ ] K6 İç köşe, ince işleme: duvar + taban ağı (köşe boyunca `L`), başlangıç durumu küresel `R₁`'in bıraktığı
  analitik yüzey `z₁(x)`; `rest_finish` küresel `R₂ < R₁` ile (raster köşeye paralel, yan paso `s`):
  (a) tutulan kesme hareketlerinin tamamı `x ≤ w(t_min) + R₂ + s` bandında; (b) SPEC 05 ile simüle edilen son
  durumda köşe kesiti `rest_thickness` toplamı `/ L` = `A(R₂)`, hata ≤ `R₁·(Δ + scallop_flat(R₂, s))`;
  (c) çakma yok (`part_z` ile SPEC 05 `cakma` kaydı yok) — `test_kalan3d.py`
- [ ] K7 İç köşe, kaba işleme: dikdörtgen cep parçası (köşeleri keskin), başlangıç durumu düz `R₁` ile işlenmiş
  cep (SPEC 05 ile simüle); `rest_rough` düz `R₂ < R₁` ile → `rest_regions` dört köşe bölgesi, her biri hacmi
  `(1 − π/4)·R₁²·H`'den `(1 − π/4)·R₂²·H`'ye iner (ızgara toleransı `P·Δ·H`, `P` = köşe yayı boyu); tutulan
  hareketler köşelerin `R₁ + R₂` yakınında; kalan kaba yolun boyu tam `rough` yolunun boyundan kısa — `test_kalan3d.py`
- [ ] K8 Konik ve torik takım (06b): K6 kurgusu torik `(R, r_c)` takımla; kalan kesit kapalı form
  (torik köşe: `(1 − π/4)·r_c²`, `r_c → 0`'da 0) ızgara toleransıyla; konik takım süzgeçte kabul ediliyor — `test_kalan3d.py`
- [ ] K9 Hatalar: `LatheTool`, `DRILL`, `G18` yol, `G95`, geçersiz `Toolpath`, `t_min < 0`, `clearance < 0`,
  `plunge_feed ≤ 0`, `z_safe ≤ zmax`, `arc_tol ≤ 0`, `rest_rough` ızgara/stok uyuşmazlığı → `CamError` — `test_kalan3d.py`
- [ ] K10 Kolon ağı: elle durumlarda (tek hücre, basamaklı harita, çapraz değen iki kolon, cep, iki aralıklı
  dexel hücresi, iki bağlamalı dexel: SPEC 05 K21 kurgusu): `is_closed()`, `volume()` = `state.volume()` rel 1e-12,
  her üçgenin normali dışa (üçgen merkezinden normal yönünde `1e-6` adımdaki nokta katının dışında, tersinde
  içinde, düşey ışın parite testiyle), yinelenen köşe yok, `face_cell` üst yüzlerde doğru hücre — `tests/cam/test_ikiz.py`
- [ ] K11 Yüzey ağı: sabit yükseklikte hacim kesin (rel 1e-12); eğik düzlem `z = ax + by + c` haritasında iç
  düğümler düzlem üstünde (1e-12); simüle edilmiş cepte hacim farkı ≤ `P·Δ·H`; kapalı; dexel → `CamError` — `test_ikiz.py`
- [ ] K12 STL: yazılan dosya boyu `84 + 50·m`; başlık, sayı, normaller ve köşeler numpy ile okununca `float32`
  yuvarlamasıyla aynı; okunan ağın hacmi `float32` toleransında; hatalı ad, indeks, `nan` → `CamError` — `test_ikiz.py`
- [ ] K13 Nokta–üçgen uzaklığı: yüz içi (düzleme dik uzaklık), üç kenar ve üç köşe bölgesinde kapalı form 1e-12;
  rastgele noktalarda üçgenin yoğun örneklenmesiyle (≥ 10⁵ nokta, referans örneklem hatası kadar) karşılaştırma;
  `point_mesh_distance` = tüm üçgenler üzerinde kaba kuvvet minimumu 1e-12 — `test_ikiz.py`
- [ ] K14 Sapma, analitik: kutu parça ağı (12 üçgen) üzerinde (a) parçanın üstünde `δ` kalınlıkta düzgün tabaka →
  parça izdüşümünde kenarlardan `δ`'dan uzak hücrelerde `s = δ` (1e-12); (b) duvar dışında parçanın üst yüksekliğinde
  `w` genişlikte bırakılmış şerit → şerit hücrelerinde `s` = duvara yatay uzaklık (1e-12), `dz` = duvar yüksekliği;
  (c) üst yüzden `0.2` derin çakma cebi (kenarlardan uzak) → `s = −0.2`, `max_gouge = 0.2`; (d) malzemesiz ve parçasız
  hücre `s = 0`, `measured = False` — `test_ikiz.py`
- [ ] K15 Sapma özeti: `max_excess`, `max_gouge`, `rms` elle hesapla; `bands` toplamı ölçülen hücre sayısı, kenar
  eşitliği sağ aralığa; `within(0, 0.1)` K14(a)'da `δ ≤ 0.1` için `True`, `δ > 0.1` için `False`; hatalı kenar ve
  negatif `lo/hi` → `CamError` — `test_ikiz.py`
- [ ] K16 Uçtan uca (simülasyon → ikiz): SPEC 05 ile cep + kontur işlenmiş blok; `twin_mesh` hacmi
  `SimResult.zmap.volume()` rel 1e-12; `deviation` parça ağına göre `max_gouge ≤ gouge_tol`, `max_excess` duvar payı
  kadar (ızgara toleransı `Δ`) — `test_ikiz.py`
- [ ] K17 OCCT uçtan uca (`@pytest.mark.occt`): SPEC 02 ile kurulan iç köşe radyüssüz cepli blok `Part`'ı,
  `Part.mesh` → `TriMesh`, SPEC 06 `finish` (küresel `R₁`) + 05 simülasyon + `rest_finish` (küresel `R₂`) + 05;
  `rest_thickness` toplamı azalıyor, çakma yok, `twin_mesh(...).to_stl` yazılıyor ve `deviation.max_gouge ≤ 1e-3` —
  `test_kalan3d.py`
- [ ] Tüm testler yeşil, `ruff check .` ve `ruff format --check .` temiz, bu SPEC'in testlerinde 0 "uygulanmamış";
  10 s'den uzun testler `@pytest.mark.slow`

## Kapsam dışı
- Kalan malzemeye özel yol stratejileri (köşe izleme / "pencil", kalan bölgeye göre kırpılmış raster sınırı,
  bölge başına ayrı yol): bu SPEC yalnız süzgeç kullanır; 06 / 06b yolu tüm alanı tarar, süzgeç havayı atar.
- 05'in simülasyonunda konik takım (05'in `h(d)` tablosunda yok): konik takımla kalan yol üretilir ama 05 ile
  simüle edilmez (06b ya da 05 eki).
- İşlenmiş ağdan `Part` (OCCT katısı) kurma ve montaja işlenmiş şekil olarak girme: `geometry/part.py` arayüz
  değişikliği ister (ayrı arayüz PR'ı).
- Dexel'de alt yüzeylerin (ikinci bağlama, alttan açılan boşluk) parçaya göre sapması: parça yalnız üst yüzeyle
  (`z_P`) ölçülür; kolon ağı ise alt yüzeyleri doğru taşır.
- Pürüzsüz yüzey çıkarma (marching cubes, dual contouring), dexel'den yüzey ağı, ağ seyreltme.
- Tri-dexel ve 5 eksen (SPEC 43), torna parçası ikizi (SPEC 22), Tezgah ekranı ve ikili veri köprüsü (Tezgah SPEC'leri).
- `cam/model.py`, `cam/sim/` mevcut dosyaları ve 06 / 06b dosyalarında değişiklik.
