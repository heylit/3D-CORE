# SPEC 06 — 3D yüzey işleme: drop-cutter, raster ince işleme, katmanlı kaba işleme

## Amaç
Üçgen ağı (STL / `Part.mesh()`) olarak verilen bir 3D yüzey üzerinde küresel ve düz uçlu takım için
**drop-cutter** (takımı Z boyunca yüzeye değene kadar indirme) yazmak; bunun üstüne çakmasız
**raster ince işleme** ve **katmanlı kaba işleme** takım yolları (`cam.model.Toolpath`) üretmek;
iz yüksekliğinin (scallop) düzlem, silindir ve küre üzerinde kapalı form formülle tuttuğunu göstermek.

## Teori

### Çerçeve ve tanımlar
- 3 eksen: takım ekseni her zaman +Z. Takım dönel simetriktir; profili alttan yukarı monotondur
  (yukarı çıktıkça genişler veya sabit kalır). Bu yüzden takım Z boyunca indirilirken parçaya **ilk alt
  yüzeyi** değer; sap ve gövde ayrıca denetlenmez (dikey indirmede alt yüzey her zaman önce değer).
- **CL** (cutter location): G-code'a yazılan nokta = **takım ucu** (en alt nokta, eksen üzerinde).
  **CC** (cutter contact): takımın yüzeye değdiği nokta.
- Takımlar (`cam.model.Tool`):
  - Küresel (`BALL`), yarıçap `R = D/2`: küre merkezi `C = CL + R·ẑ`.
  - Düz (`FLAT`, `corner_r = 0`), yarıçap `r = D/2`: alt yüzey, merkezi CL olan yatay disk.
  - Köşe radyüslü düz (torik), matkap → `CamError` (kapsam dışı).
- Yüzey: üçgen ağı `V (n,3)`, `T (m,3)`. Üçgenin birim normali `n`; drop-cutter yukarı bakan normal
  kullanır (`n_z < 0` ise `n → −n`). Dik üçgenler (`|n_z| < NZ_TOL = 1e-12`) yüz testine girmez;
  onları kenar ve köşe testleri yakalar.

### Drop-cutter (Yau vd. 2004; OpenCAMLib `BatchDropCutter` yapısı)
Verilen `(x, y)` için temas yüksekliği, takımın XY izdüşüm diskiyle örtüşen her üçgenin **köşe, yüz ve
kenar** testlerinin en büyüğüdür:
`z_CL(x, y) = max( max_köşe, max_yüz, max_kenar )`. Hiçbir üçgen diskle örtüşmüyorsa sonuç tanımsızdır
(aşağıda `floor`).

**Küresel uç** (`d`: XY'de yatay uzaklık):
- Köşe `P`: `d ≤ R` ise `z = P_z + √(R² − d²) − R`.
- Yüz (düzlem `n·(p − P₀) = 0`, `n_z > 0`): merkez normal boyunca `R` uzakta → CC'nin XY'si
  `(x, y) − R·n_xy`. CC üçgenin içindeyse (ağırlık merkezli koordinatlar ≥ −TOL)
  `z = z_düzlem(CC_xy) + R·n_z − R`.
- Kenar `P₀P₁` (birim yön `u`, boy `L`): merkez `C = (x, y, z_C)` kenarın taşıdığı doğruya `R` uzakta:
  `w = C − P₀`, `|w|² − (w·u)² = R²` → `z_C`'de ikinci derece denklem, büyük kök alınır;
  `0 ≤ w·u ≤ L` ise geçerli, `z = z_C − R`. `|u_z| ≈ 1` (dik kenar) köşe testine bırakılır.

**Düz uç** (yarıçap `r`):
- Köşe: `d ≤ r` ise `z = P_z`.
- Yüz: disk düzleme yokuş yukarı kenarından değer: `n_xy ≠ 0` ise CC_xy = `(x, y) − r·n_xy/|n_xy|`,
  `n_xy = 0` (yatay) ise CC_xy = `(x, y)`. CC üçgenin içindeyse `z = z_düzlem(CC_xy)`.
- Kenar: kenarın XY izdüşümünün `(x, y)` merkezli `r` yarıçaplı daire içinde kalan aralığı
  `[t₀, t₁]` (doğru–daire kesişimi); kenar Z'de doğrusal olduğu için `z = max(z(t₀), z(t₁))`.

Hepsi kapalı formdur; numpy ile noktalar üzerinde vektörlenir. Aday üçgenler XY sınır kutusuyla
süzülür (düzenli ızgara veya `scipy.spatial.cKDTree`; scipy zaten bağımlılık).

Analitik sonuçlar (testler bunlara dayanır):
- Yatay düzlem `z = z₀` (yeterince geniş): her iki takımda `z_CL = z₀`.
- Eğimi `β` olan düzlem `z = x·tan β`: küresel uçta `z_CL = x·tan β + R(1/cos β − 1)`,
  düz uçta `z_CL = x·tan β + r·tan β` (disk yokuş yukarı kenarından değer).
- Tek köşe (tek küçük üçgen, yüzü ve kenarları uzakta): küresel `z_V + √(R² − d²) − R`, düz `z_V`.
- Yatay tek kenar (yükseklik `z_e`, XY'de uzaklık `d`): küresel `z_e + √(R² − d²) − R`, düz `z_e` (`d ≤ r`).
- `R` yarıçaplı küre / `ρ` yarıçaplı silindir (dışbükey) üstünde küresel uç: merkez `ρ + R` uzakta →
  küre için `z_CL = √((ρ+R)² − d²) − R` (`d` küre merkezine XY uzaklığı). Ağ yaklaşık olduğu için
  tolerans ağın kiriş hatası `ε` kadardır.
- **Çakma yok:** her CL'de küresel uç için küre merkezinin ağa uzaklığı `≥ R − TOL`; düz uçta diskin
  hiçbir noktası ağın altına girmez. Ve temas var: en az bir test `z_CL`'yi verir (uzaklık = `R`).

### Raster ince işleme
XY'de dikdörtgen bir alan `[x_min, x_max] × [y_min, y_max]` üzerinde, `direction="x"` için X'e paralel,
`s` aralıklı çizgiler: sıra sayısı `m = ⌈(y_max − y_min)/s⌉ + 1`, sıralar `y_min`'den `y_max`'a eşit aralıklı
(ilk ve son sıra kenarda; SPEC 03 `face` kuralı). `direction="y"` aynısını Y'ye paralel yapar.
Her çizgi üzerinde:
1. `ds` aralıklı noktalar (uçlar dahil), her birine drop-cutter.
2. **Uyarlamalı bölme** (OpenCAMLib `AdaptivePathDropCutter`): ardışık iki CL'nin ortasında drop-cutter
   tekrar çalışır; `|z_orta − (z₀ + z₁)/2| > tol` ise araya eklenir, aralık `ds_min`'e inene kadar tekrarlanır.
Zigzag: sıralar sırayla ters yönde gezilir; iki sıra arasındaki geçiş de drop-cutter ile örneklenmiş bir
çizgidir (sıra ucu boyunca), yani geçiş de çakmasızdır. Kesme hareketleri `G1`; yay yok.

Sonuç (testlerle ölçülür): ardışık iki CL arasındaki doğru üzerinde her noktada
`z_doğru − z_CL(drop) ≥ −tol` (çakma `tol`'u aşmaz) ve `ds_min` sınırına takılmayan her aralıkta
`|z_doğru − z_CL| ≤ tol` orta noktada.

### İz (scallop) yüksekliği
Küresel uç `R`, iki komşu pasonun takım merkezleri arasındaki uzaklık `s` (düzlemde) veya merkezlerin
yüzey eğrilik merkezinden görülme açısı `α` (eğri yüzeyde).

- **Düzlem** (kesin): `h = R − √(R² − (s/2)²)`; küçük `s` için `h ≈ s²/(8R)`. `s > 2R` → `CamError`.
  Ters formül: `s = 2√(2Rh − h²)`.
- **Dışbükey silindir / küre** (yüzey eğrilik yarıçapı `ρ`): merkezler `c = ρ + R` yarıçaplı çemberde,
  aralarındaki açı `α`. İki küre kesitinin açıortaydaki yakın kesişimi sırtın tepesidir:
  `h = c·cos(α/2) − √(R² − c²·sin²(α/2)) − ρ`.
- **İçbükey silindir / küre** (`ρ > R`): `c = ρ − R`, sırt açıortaydaki uzak kesişimdedir:
  `h = ρ − c·cos(α/2) − √(R² − c²·sin²(α/2))`.
- `R < c·sin(α/2)` (küreler kesişmiyor) → `CamError`; içbükeyde `ρ ≤ R` → `CamError`.
- `ρ → ∞` ve `α·ρ → s` iken iki eğri formül de düzlem formülüne iner. Türetme: iki çemberin kesişimi
  (kosinüs teoremi `t² − 2tc·cos(α/2) + c² − R² = 0`); CAM araştırma notları (proje belgesi), sayısal olarak
  kaba kuvvet zarf hesabıyla kontrol edildi.

Raster yolda `α`, eksene dik kesitte iki komşu pasonun küre merkezlerinin açı farkıdır. X'e paralel
raster ve X ekseni boyunca uzanan silindirde merkezlerin açısı `φ = asin(y / c)` olduğundan `α` eşit
aralıklı `y` için sabit değildir; testler `α`'yı gerçek CL'lerden hesaplar.

**Ölçüm** (testin bağımsız işi): bir kesitte işlenmiş yüzey, CL'lerdeki takım alt yüzeylerinin alt zarfıdır
(küresel: `z_zarf(p) = min_CL (C_z − √(R² − |p − C|²_xy))`). Sırt = zarf ile gerçek yüzey arasındaki en büyük
fark. Gerçek yüzey (silindir / küre) analitik bilinir; ağın kiriş hatası `ε ≤ 1e-6 mm` olacak kadar sık
ağ kullanılır.

### Katmanlı kaba işleme
Ham malzeme `Stock` ve parça ağı. Kaba işleme, yüzeyi `δ ≥ 0` **işleme payı** bırakarak boşaltır:
- Pay ile drop-cutter: küresel uçta `z_δ = drop(R + δ) + δ` (kesin: büyütülmüş kürenin ucu asıl uçtan `δ`
  aşağıdadır, Minkowski toplamı). Düz uçta `z_δ = drop(r + δ) + δ` (tutucu: `r` diskine `δ` küre eklenmiş
  şekli kapsar; yatay ve dik yüzeylerde pay tam `δ`, eğik yüzeylerde `≥ δ`).
- Seviyeler SPEC 03 `cam.ops2d.depths(z_top, z_bottom, a_p)` ile: `z_top = stock.zmax`.
- Her seviye `z_i` için raster (yukarıdaki sıra kuralı, `s` yan paso) ve
  `z_CL = max(z_δ(x, y), z_i)`. Takım parçanın üstünden aşarak geçer (havada kesme bu SPEC'te
  optimize edilmez).
- Sonuç (testlerle ölçülür): her noktada bir seviyenin kestiği derinlik
  `max(z_δ, z_{i−1}) − max(z_δ, z_i) ≤ a_p`; hiçbir CL'de takım parçaya `δ − TOL`'dan yakın değil;
  parçanın olmadığı yerde son seviye tam `z_bottom`; yatay üst yüzeyde son yükseklik tam `z_üst + δ`.
- Seviyeler arası: seviye bitince `G0` ile `z_safe`'e, sonraki seviyenin ilk noktasının üstüne `G0`,
  `G0` ile `max(z_CL_ilk, z_{i−1}) + clearance`'a, `G1 plunge_feed` ile ilk CL'ye.

## Dosyalar
- Yeni: `cam/dropcutter.py`, `cam/scallop.py`, `cam/ops3d.py`,
  `tests/cam/test_dropcutter.py`, `tests/cam/test_scallop.py`, `tests/cam/test_ops3d.py`,
  `tests/reference/test_ocl_dropcutter.py` (isteğe bağlı OpenCAMLib çapraz kontrolü, kurulu değilse atlanır),
  `durum/06-cam-3d.md`.
- Kullanılır (değişmez): `cam/model.py` (`Tool`, `Stock`, `Move`, `Toolpath`, `CamError`),
  `cam/ops2d.py` (`Cut`, `depths`), `geometry/part.py` (`Part.mesh`).
- Dokunulmayacak: `cam/model.py` dahil tüm `*/model.py`, diğer paketler, ortak dosyalar. Üçgen ağı tipi
  bu SPEC'te `cam/dropcutter.py`'de tanımlanır; 05 kullanmak isterse `cam/model.py`'ye taşınması ayrı arayüz PR'ıdır.

## Arayüz

### `cam/dropcutter.py`
- `TOL = 1e-9` [mm], `NZ_TOL = 1e-12`.
- `@dataclass TriMesh(V: np.ndarray (n,3), T: np.ndarray (m,3) int)` — `V` sonlu değil, `T` aralık dışı indeks,
  sıfır alanlı üçgen (alan < `TOL²`) veya boş ağ → `CamError`. `bbox() -> (min(3,), max(3,))`.
  - `TriMesh.from_part(part, tol=0.01)` — `part.mesh(tol)` ile (`@pytest.mark.occt`).
- `drop(mesh: TriMesh, tool: Tool, xy: array (k,2), floor: float | None = None) -> np.ndarray (k,)` —
  her nokta için `z_CL`. Diskle örtüşen üçgen yoksa: `floor` verilmişse `floor`, yoksa `CamError`.
  `floor` verilmişse sonuç `max(z_CL, floor)`. `BALL` ve `FLAT` (`corner_r == 0`) dışındaki takım → `CamError`.
- `drop_one(mesh, tool, x, y, floor=None) -> float` — kısayol.

### `cam/scallop.py`
- `scallop_flat(R, s) -> float` — `h = R − √(R² − (s/2)²)`; `R ≤ 0`, `s < 0`, `s > 2R` → `CamError`.
- `stepover_flat(R, h) -> float` — `s = 2√(2Rh − h²)`; `h ≤ 0` veya `h > R` → `CamError`.
- `scallop_curved(R, rho, alpha, convex: bool) -> float` — yukarıdaki iki formül; `alpha < 0`,
  `rho ≤ 0`, içbükeyde `rho ≤ R`, kesişmeyen küreler → `CamError`.

### `cam/ops3d.py`
- `@dataclass Raster(xmin, xmax, ymin, ymax, stepover, ds, tol, ds_min, feed, plunge_feed, rpm, z_safe,
  direction="x", clearance=1.0)` — `xmax > xmin`, `ymax > ymin`, `stepover > 0`, `0 < ds_min ≤ ds`, `tol > 0`,
  `feed > 0`, `plunge_feed > 0`, `rpm > 0`, `clearance ≥ 0`, `direction ∈ {"x", "y"}`. Aksi `CamError`.
- `raster_lines(r: Raster) -> list[float]` — sıraların sabit koordinatları (`y` veya `x`), yukarıdaki kural.
- `finish(mesh: TriMesh, tool: Tool, r: Raster, floor: float | None = None) -> Toolpath` — raster ince işleme.
  `z_safe` en yüksek CL'nin `clearance` üstünde değilse → `CamError`.
- `rough(mesh: TriMesh, stock: Stock, tool: Tool, r: Raster, a_p: float, z_bottom: float,
  allowance: float = 0.0) -> Toolpath` — katmanlı kaba işleme. Alan `r`'nin XY dikdörtgenidir;
  `stock.zmin ≤ z_bottom < stock.zmax`, `a_p > 0`, `allowance ≥ 0`, `z_safe > stock.zmax`; aksi `CamError`.
  Ağın altında kalmayan noktalar için `floor = z_bottom`.
- Hareket kuralları (ikisi için):
  - Yol `(x₀, y₀, z_safe)`'te başlar ve `z_safe`'te biter; ilk CL'nin üstüne `G0`, `G0` ile `z_CL + clearance`'a,
    `G1 plunge_feed` ile CL'ye. Kesme hareketleri `G1 feed`.
  - `G0` hareketleri hiçbir zaman o noktadaki `z_CL`'nin altında değil.
  - Dönen yol `validate()`'ten geçer; `rpm` `r.rpm`.

## Kabul kriterleri
Geometrik değerlerde tolerans aksi yazılmadıkça mutlak `1e-9 mm`.
- [ ] K1 `TriMesh` doğrulamaları (nan, kötü indeks, sıfır alanlı üçgen, boş ağ) ve desteklenmeyen takım
  (matkap, köşe radyüslü düz) → `CamError` — `tests/cam/test_dropcutter.py`
- [ ] K2 Yatay düzlem: her iki takımda, rastgele XY noktalarında `z_CL = z₀`; ağ köşesi, kenarı ve yüzü üstündeki
  noktalar dahil — `tests/cam/test_dropcutter.py`
- [ ] K3 Eğik düzlem (`β` = 10°, 30°, 60°): küresel `x·tan β + R(1/cos β − 1)`, düz `x·tan β + r·tan β` — `tests/cam/test_dropcutter.py`
- [ ] K4 Köşe ve kenar testleri tek başına: tek köşe (küresel `z_V + √(R² − d²) − R`, düz `z_V`), tek yatay ve
  eğik kenar (kapalı form), `d > R` / `d > r` iken o üçgenden temas yok — `tests/cam/test_dropcutter.py`
- [ ] K5 `floor`: ağın dışındaki noktada `floor` döner; `floor` yokken `CamError`; `floor` ağın üstündeyse sonuç `floor` — `tests/cam/test_dropcutter.py`
- [ ] K6 Küre ve silindir ağı (kiriş hatası `ε`): küresel uçta `z_CL = √((ρ+R)² − d²) − R` (± `ε`) — `tests/cam/test_dropcutter.py`
- [ ] K7 Çakma yok + temas var: rastgele dışbükey/içbükey yüzey ağlarında (ör. `z = A sin(x/λ) cos(y/λ)` ızgarası)
  her CL'de küresel uç için küre merkezinin ağa en kısa uzaklığı `R ± 1e-9`; düz uçta diskin ağa
  dikey uzaklığı `≥ −1e-9` ve en az bir temas `≤ 1e-9` — `tests/cam/test_dropcutter.py`
- [ ] K8 Kaba kuvvet karşılaştırması: aynı rastgele ağda drop-cutter = takım yüzeyini sık örnekleyen kaba kuvvet
  yüksekliği (örnekleme hatası sınırı içinde) — `tests/cam/test_dropcutter.py`
- [ ] K9 Scallop formülleri: `scallop_flat` kesin ve küçük `s` yaklaşımı `s²/8R`; `stepover_flat` tersi (gidiş-dönüş 1e-12 rel);
  `scallop_curved` → `ρ → ∞`'da düzlem formülü; dışbükey ve içbükeyde bağımsız kaba kuvvet zarfıyla 1e-6; hatalı girdiler → `CamError` — `tests/cam/test_scallop.py`
- [ ] K10 Raster sıraları: `raster_lines` sayı `m`, aralık ≤ `s`, ilk/son sıra kenarda; `direction="y"` — `tests/cam/test_ops3d.py`
- [ ] K11 `finish` düzlemde: yatay düzlemde ölçülen iz yüksekliği `scallop_flat(R, s)` (zarf ölçümü, 1e-9);
  her CL `z₀` — `tests/cam/test_ops3d.py`
- [ ] K12 `finish` silindir ve kürede (dışbükey; içbükey silindir oluk): ölçülen sırt yüksekliği, gerçek CL'lerden
  hesaplanan `α` ile `scallop_curved` (tolerans `5e-6 mm`, ağ `ε ≤ 1e-6`) — `tests/cam/test_ops3d.py`
- [ ] K13 `finish` uyarlamalı bölme ve çakma: ardışık CL'ler arasındaki doğru üzerinde örnek noktalarda
  `z_doğru − drop ≥ −tol`; `ds_min`'e takılmayan aralıkların ortasında `|z_doğru − drop| ≤ tol`;
  sıra geçişleri de bu koşulu sağlar — `tests/cam/test_ops3d.py`
- [ ] K14 `rough`: seviyeler `depths` ile aynı; her seviyede kesme derinliği `≤ a_p`; hiçbir CL'de takım parçaya `allowance − 1e-9`'dan
  yakın değil; parça olmayan yerde son seviye `z_bottom`; kutu parçanın yatay üstünde son yükseklik `z_üst + allowance`;
  her iki takım — `tests/cam/test_ops3d.py`
- [ ] K15 Hareket kuralları: yol `z_safe`'te başlar/biter, `validate()` geçer, `G0` hiçbir zaman `z_CL`'nin altında değil,
  kesme hareketleri `G1 feed`, `rpm` doğru — `tests/cam/test_ops3d.py`
- [ ] K16 Hatalı girdiler (`Raster` alanları, `rough` parametreleri, yetersiz `z_safe`) → `CamError` — `tests/cam/test_ops3d.py`
- [ ] K17 `TriMesh.from_part`: `geometry.features.block` ve `cylinder` parçalarında drop-cutter üst yüzde `z_max`,
  silindir kenarı dışında `floor` (`@pytest.mark.occt`) — `tests/cam/test_dropcutter.py`
- [ ] K18 (isteğe bağlı) OpenCAMLib kuruluysa aynı ağ ve takımda `drop` ↔ `ocl.BatchDropCutter` 1e-6 mm; değilse atlanır — `tests/reference/test_ocl_dropcutter.py`
- [ ] `pytest` 0 failed, bu SPEC'in testlerinde 0 "uygulanmamış"; `ruff check .` ve `ruff format --check .` temiz;
  10 saniyeden uzun testler `@pytest.mark.slow`

## Kapsam dışı
- Torik (köşe radyüslü) ve konik takım; kenar testinde kök bulma (Brent) gerektiren durumlar. Sonraki adım (06b).
- Waterline / Z-seviyesi ince işleme (push-cutter, fiber, weave). Sonraki adım (06b).
- Sabit iz yüksekliği (eğriliğe göre değişen yan paso), spiral / radyal / kalem (pencil) yolları, kalan malzeme (rest) işleme.
- Kaba işlemede havada kesmeyi atlama, 03 cebini kesitlerle kullanan ofset kaba işleme (polygon boolean
  gerektirir, 09'dan sonra), rampa / helis giriş.
- Takım tutucu ve sap çarpışması, talaş simülasyonu (05), G-code yazımı (04 zaten `Toolpath` okur).
- Yol düzeltme (doğrusal noktaları birleştirme, yay uydurma), TSP.
- 4/5 eksen, eğik takım ekseni.
- NURBS / B-rep üzerinde doğrudan drop-cutter: yüzey her zaman üçgen ağıdır.
