# SPEC 03c — Rampa ve helis giriş

> Onaylandı: kullanıcı, 2026-10-18 11:13 (proje sohbeti, yazılı toplu onay "önerilerle"). Dalga 5, hat H1.
> Düzeltme (2026-10-18, test oturumunun bulgusu, koordinatör kararı): K5'teki dikdörtgen beklentisi Teori'deki
> yön kuralıyla çelişiyordu (60×40'ta `k = 2`); K5 kurala uyduruldu, K12'deki bağlantı maddesi K8'e yönlendirildi. Kapsam aynı.

## Amaç
Cep (`cam.ops2d.pocket`) ve konturun (`cam.ops2d.contour`) malzemeye düz dalmak yerine **helis**, **zigzag
rampa** veya **kontur boyunca rampa** ile girebilmesi; böylece merkezden kesmeyen takımın (`center_cutting=False`)
cep ve kontur işleyebilmesi. Her giriş çakmasız olduğu kanıtlanmış bölgede kalır, eğim hiçbir harekette
istenen açıyı aşmaz, giriş bulunamazsa sessizce düz dalmaya dönülmez: `CamError`.

## Bağlam
- SPEC 03 düz dalma kullanır ve rampa / helisi kapsam dışı bırakır ("03b" diye anılıyordu; koordinatör kararıyla
  adı 03c). Ek A2: `center_cutting=False` takımla `pocket` ve `contour` → `CamError`. İkinci inceleme H6 bunu
  "merkezden kesmeyen takımla cep yapılamıyor" diye işaretledi. SPEC 29 (işlem planı) helisi kapsam dışı bırakır.
- Bu SPEC birleşince Ek A2 kuralı yalnız `PLUNGE` girişi için geçerli kalır.
- Ön koşullar: arayüz A0 (`cam/model.py`: `EntryKind`, `EntryMode`, `Tool.ramp_angle_max`; sahibi "CAM model
  arayüzü" thread'i) ve SPEC 03b (PR #49; `pocket`'in halka ağacını değiştirir, bu SPEC yalnız girişi
  değiştirir). Kod iskeleti birleşmemiş dalların üstüne kurulabilir; birleştirme ikisinden sonra.

## Teori

### Gösterim
- `Ω` cep bölgesi, `r = D/2`, `R₀` takım merkezinin geçerli bölgesi (`Ω ⊖ B_r`'nin girişin yapıldığı bileşeni).
  `p ∈ R₀` ⇒ `B(p, r) ⊆ Ω`: merkezi `R₀`'da kalan her hareket çakmasızdır (SPEC 03 K13 ölçütü).
- `N` girilen halkanın düğüm bölgesi (`N ⊆ R₀`), `lp` girilen halka (takım merkezi yolu), `α` giriş açısı,
  `z₀ = z_prev + clearance` giriş başlangıcı, `z` paso derinliği, `Δz = z₀ − z > 0`, `H = Δz / tan α` gereken
  yatay yol.
- Eğim: bir hareketin `Δz / s_xy` oranı (`s_xy` yatay boy; yayda `ρ·|Δθ|`). Her giriş hareketinde
  `|Δz| / s_xy ≤ tan α`.

### Önerme 1 (en yakın nokta)
`c ∈ N`, `q` noktası `∂N`'nin `c`'ye en yakın noktası ise `[c, q] ⊆ N`. Kanıt: `|c − q| = dist(c, ∂N)`;
açık disk `B(c, |c − q|)` `∂N`'yi kesmez ve `c`'yi içerir, yani `N`'nin içindedir; `[c, q)` bu diskte. ∎
`q` yalnız `lp`'nin en yakın noktasıysa (`lp`, `∂N`'nin bir halkası) önerme geçmez; bağlantı ayrıca denetlenir.

### Helis
Merkez `c`, yarıçap `R_h` (takım merkezi yolu). Başlangıç `h = c + R_h·û`, `û = (q − c)/|q − c|`
(`q = c` ise `û = (1, 0)`). Tur sayısı `n = max(1, ⌈Δz / (2π R_h tan α) − 1e-9⌉)`; her tur `h`'den `h`'ye tam
daire helis hareketi, `Δz/n` iner. Sonra `z`'de bir düz tam daire (taban düzlenir). Yön: `climb=True` → `G3`,
değilse `G2` (iç duvarda tırmanma CCW, SPEC 03 ile aynı kural).
- Boy: `n·√((2π R_h)² + (Δz/n)²) + 2π R_h`. Etkin eğim `Δz/(n·2π R_h) ≤ tan α`.
- **Çekirdek kalmaz (`R_h ≤ r`):** `|x − c| = ρ ≤ R_h + r` noktasının daireye uzaklığı `|ρ − R_h|`; `R_h ≤ r`
  ise her `ρ ≥ 0` için `≤ r`. Düz daire tüm `B(c, R_h + r)` diskini `z`'ye indirir. `R_h > r` ise ortada
  `R_h − r` yarıçaplı sütun kalır: yasak.
- **Çakma yok:** `c ∈ R₀` ve `dist(c, ∂R₀) ≥ R_h` ⇒ `B̄(c, R_h) ⊆ R₀`.
- **Bağlantı:** `|q − c| ≥ R_h` ise `h ∈ [c, q]`, bağlantı `[h, q]` = `[c, q]`'nun parçası; aksi halde `[h, q]`
  diskin içinde (dışbükey). Her iki durumda `[h, q] ⊆ R₀` denetimi (aşağıda `segment_inside`) yeterlidir.

### Zigzag rampa (cep)
Doğru parçası `S = [A, B]`, `A = c − ℓu`, `B = c + ℓu`. Yön adayları `u_k = (cos kπ/12, sin kπ/12)`,
`k = 0..11`. `ray(c, u)`: `c`'den `u` yönündeki ışının `∂R₀`'yu ilk kestiği noktaya uzaklık (kesin doğru–doğru /
doğru–yay kesişimi). `ℓ_fit(u) = min(ray(c, u), ray(c, −u))`; seçilen `k` en büyük `ℓ_fit`'i verir (eşitlikte
en küçük `k`). `ℓ = min(L/2, ℓ_fit)`. `S ⊆ R₀` (ışınlar `∂R₀`'ya `ℓ`'den önce değmez).
- Ayak sayısı `m = max(1, ⌈H/(2ℓ) − 1e-9⌉)`; ayaklar `A → B → A …`, her biri `Δz/m` iner. Bitiş ucu `E`
  (`m` tekse `B`), sonra `z`'de `E`'den öbür uca düz geçiş (şerit `S ⊕ B_r` tabanı düzlenir), sonra `c`'ye.
- Boy: `m·√((2ℓ)² + (Δz/m)²) + 2ℓ + ℓ`. Etkin eğim `Δz/(2mℓ) ≤ tan α`.
- Bağlantı `[c, q]`, denetimli.

### Kontur boyunca rampa
Kapalı halka `lp` (çevre `P`), başlangıç `p₀`: takım `p₀`'dan halka yönünde yay boyu `σ ∈ [0, H]` boyunca
ilerler, `z(σ) = z₀ − σ tan α` (eğim tam `α`). `H > P` ise halka `⌊H/P⌋` kez tam dolanılır. Rampa `e`
noktasında biter (`σ = H`, yay boyu `H mod P`); `e`'de bölünen parça iki harekete ayrılır (doğruda `G1`,
yayda aynı merkezli helis `G2`/`G3`; `z` yay boyuna doğrusal, G-code helisiyle aynı). Sonra `z`'de `e`'den
başlayan tam halka. `e`, bir köşeye `≤ LINK_TOL` yakınsa köşeye oturtulur.
- Boy: `√(H² + Δz²) + P`. Yol `lp`'nin üstünde kaldığından SPEC 03'teki çakmasızlık aynen geçer.
- Açık profil (`side="uzerinde"`, kapalı değil, boy `P`): gidiş-dönüş `p₀ → p₁ → p₀`, tur sayısı
  `m = max(1, ⌈H/(2P) − 1e-9⌉)`, her tur `Δz/m` iner, `p₀`'da `z`'de biter; sonra SPEC 03'teki `p₀ → p₁` kesimi.

### Merkezden kesmeyen takım
Ölü bölge (çekirdek) yarıçapı `r_c` olan takımda düz ilerleyen yolun ekseni altındaki malzeme, ekseni `r_c`
geride olan kesici kenarlarca `r_c·tan α` kalınlığa kadar alınmıştır; izin verilen açı üreticinin verdiği
`ramp_angle_max`'tır (modelde yoksa giriş yapılamaz). Eğrilik merkezinde `R_h < r_c` olursa helis merkezindeki
nokta hep çekirdeğin altında kalır; `r_c` modelde olmadığından güvenli alt sınır `r/2` alınır
(helis delik çapı `≥ 1,5D`, üretici kataloglarındaki yaygın alt sınır). Aynı sınırın kontur rampasındaki
karşılığı `P ≥ π r` (yarıçapı `r/2` olan daire), zigzag ayağında `2ℓ ≥ r`.

### Çapa noktası `c` (cep)
`c = deepest_point(N)`: `T = ½·min(bbox genişliği, yüksekliği)`, `lo = 0`, `hi = T`; `ANCHOR_N = 40` kez
`t = (lo + hi)/2`, `offset(N, t)` boş değilse `lo = t` değilse `hi = t`. `c = offset(N, lo)[0].outer` ilk
parçasının başlangıcı; `dist(c, ∂N) ≥ lo − KEEP_TOL`. Hiç başarılı adım yoksa (`lo = 0`) → `CamError`.
`q = lp`'nin `c`'ye en yakın noktası (eşitlikte ilk parça); halka `q`'dan başlayacak biçimde döndürülür
(SPEC 03'teki inmeden geçiş kuralıyla aynı döndürme).

### Uygulama kuralı (`pocket`, `contour`)
SPEC 03'teki her "giriş" (`G0` XY → `G0` `z₀` → `G1` dalma) yerine, `Cut.entry` türüne göre:
| Tür | `pocket` | `contour` |
|---|---|---|
| `None` / `PLUNGE` | SPEC 03 (değişmez; merkezden kesmeyen → `CamError`, Ek A2) | SPEC 03 |
| `HELIX` | `c`'de helis, `[h, q]`, halka `q`'dan | `CamError` ("helis yalnız cepte") |
| `RAMP` | `c`'de zigzag, `[c, q]`, halka `q`'dan | kontur boyunca rampa |
Giriş başı: `z_safe`'te başlangıç noktası (`h`, `A` veya `p₀`) üstüne `G0`, `G0` ile `z₀`'a, sonra giriş
hareketleri. Rampa / helis inişleri `Cut.ramp_feed` ile (`None` → `feed`), düz tamamlama ve bağlantılar `feed` ile.
`face` değişmez (girişleri ham malzemenin dışında).

### Doğrulama ve hata
Giriş öncesi (her `enter` için): `c ∈ R₀`; helis için `dist(c, ∂R₀) ≥ R_h − TOL`, zigzag için
`2ℓ ≥ L_min` (`L_min = r` merkezden kesmeyende, `TOL` diğerinde), kontur rampası için merkezden kesmeyende
`P ≥ π r`; bağlantı `segment_inside([h|c], q, R₀)`. Herhangi biri tutmazsa `CamError`; mesaj girişi, bulunan
en büyük değeri (`dist(c, ∂R₀)`, `2ℓ_fit`, `P`) ve gerekeni verir. Otomatik başka türe geçiş yoktur
(SPEC 29 gibi çağıranlar sırayla dener).

## Dosyalar
- Yeni: `cam/giris.py`, `tests/cam/test_giris.py`, `durum/03c-rampa-helis.md`
- Değişecek: `cam/ops2d.py` (`Cut.entry`, `Cut.ramp_feed`; `_Builder.enter` girişi `cam.giris`'e bırakır;
  `pocket`/`contour` girişe düğüm bölgesini, kökü ve halkayı verir; `_check_plunge` yalnız `PLUNGE`'da).
  03b de bu dosyayı değiştirir: 03b birleştikten sonra (ya da dalının üstüne) yazılır.
- Dokunulmayacak: `cam/model.py` (A0 arayüz PR'ı ekler), `cam/rest.py`, `cam/offset.py`, `cam/gcode/`,
  `cam/sim/`, `face`, `tests/cam/test_ops2d.py` (bu SPEC'in testleri yalnız `test_giris.py`'de), ortak dosyalar.

## Arayüz

### `cam/model.py` (A0, ayrı arayüz PR'ı; burada yalnız beklenen biçim)
- `class EntryKind(StrEnum)`: `PLUNGE = "dalma"`, `RAMP = "rampa"`, `HELIX = "helis"`.
- `@dataclass EntryMode(kind=EntryKind.PLUNGE, angle=2.0, radius=None, length=None)`: `angle` [derece]
  sonlu, `0 < angle < 90`; `radius` [mm] > 0 yalnız `HELIX`'te; `length` [mm] > 0 yalnız `RAMP`'ta; aksi
  `CamError`. `to_dict` / `from_dict` (bilinmeyen alan → `CamError`).
- `Tool.ramp_angle_max: float | None = None` [derece], `0 < · ≤ 90`, `to_dict` / `from_dict`'e eklenir.

### `cam/giris.py`
Sabitler: `ANCHOR_N = 40`, `RAMP_DIRS = 12`, `HELIX_R_FACTOR = 0.5` (`R_h` varsayılanı `r/2`),
`RAMP_L_FACTOR = 2.0` (`L` varsayılanı `2D`), `NONCENTER_MIN = 0.5` (merkezden kesmeyende `R_h ≥ r/2`).
- `resolve(tool: Tool, entry: EntryMode | None, op: str) -> EntryMode` — `op ∈ {"cep", "kontur"}`. `None` →
  `EntryMode()`. Varsayılan `radius`/`length` doldurulur. Denetim: `PLUNGE` + merkezden kesmeyen → `CamError`;
  `RAMP`/`HELIX`: `ramp_angle_max` varsa `angle ≤ ramp_angle_max` (+1e-12), yoksa ve merkezden kesmiyorsa
  → `CamError`; `HELIX`: `R_h ≤ r` (+`TOL`), merkezden kesmeyende `R_h ≥ r/2` (−`TOL`); `op == "kontur"` ve
  `HELIX` → `CamError`.
- `deepest_point(region: Region) -> tuple[np.ndarray, float]` — yukarıdaki ikiye bölme; `(c, lo)`.
- `segment_inside(p, q, region: Region) -> bool` — `p, q ∈ region` (sınır dahil) ve `[p, q]` `∂region`'ı
  uçlarından (`≤ LINK_TOL`) başka yerde kesmez, orta noktası `region` içinde.
- `ramp_direction(c, region: Region, L: float) -> tuple[np.ndarray, float]` — `(u, ℓ)`.
- `helix_moves(c, R_h: float, u, z0: float, z: float, alpha: float, climb: bool, ramp_feed: float, feed: float) -> list[Move]`
  — takım `h`'de `z0`'dayken: `n` helis turu + düz daire. `R_h ≤ 0`, `z0 ≤ z`, `alpha ∉ (0, 90)` → `CamError`.
- `zigzag_moves(c, u, ell: float, z0: float, z: float, alpha: float, ramp_feed: float, feed: float) -> list[Move]`
  — takım `A`'da `z0`'dayken: `m` ayak + düz geçiş + `c`'ye.
- `loop_ramp_moves(segs: list[Segment], closed: bool, z0: float, z: float, alpha: float, ramp_feed: float) -> tuple[list[Move], list[Segment]]`
  — takım `segs[0].p0`'da `z0`'dayken rampa hareketleri; ikinci değer `z`'de kesilecek halka (kapalıda `e`'den
  döndürülmüş, açıkta `segs`).
Dönen hareketler `Toolpath.validate()`'ten geçer (yay yarıçapları `ARC_TOL` içinde).

### `cam/ops2d.py`
- `Cut(..., entry: EntryMode | None = None, ramp_feed: float | None = None)` — `ramp_feed` verilirse `> 0`;
  `entry` `EntryMode` ya da `None` değilse `CamError`.
- `pocket`, `contour` imzaları aynı; giriş yukarıdaki tabloya göre.

## Kabul kriterleri
Tolerans aksi yazılmadıkça mutlak `1e-9 mm`, boylarda göreli `1e-12`.
- [ ] K1 `resolve` ve `Cut`: varsayılanlar (`R_h = r/2`, `L = 2D`, `None` → `PLUNGE`); hata tablosu (merkezden
  kesmeyen + `PLUNGE`; merkezden kesmeyen + `ramp_angle_max=None`; `angle > ramp_angle_max`; `R_h > r`;
  merkezden kesmeyende `R_h < r/2`; konturda `HELIX`; `ramp_feed ≤ 0`; `entry` yanlış tür) → `CamError`
- [ ] K2 `helix_moves` kapalı form: `R_h = 2,5`, `Δz = 4`, `α = 2°` → `n = 8` tur + 1 düz daire, her hareket
  `h`'de biter, `z` adımları `0,5`, boy `141,43531527117…`; `Δz = k·2πR_h tan α` tam katında `n = k`;
  `climb` → `G3`, değilse `G2`; merkez `c`; etkin eğim `≤ tan α`
- [ ] K3 Helis deliği: `R_h ∈ {0,5r, r}` için `B(c, R_h + r)` içindeki örnek noktalar düz daireye `≤ r + 1e-9`
  (sütun yok); SPEC 05 `simulate` ile kutu stokta helis yolu: `B(c, R_h + r − cell)` hücreleri `z`'de,
  `B(c, R_h + r + cell)` dışı değişmemiş, çakma olayı yok
- [ ] K4 `zigzag_moves` kapalı form: `ℓ = 10`, `Δz = 4`, `α = 2°` → `m = 6` ayak, her biri `Δz/6` iner, sonra
  düz geçiş ve `c`; boy `150,06664815842…`; `m` tek/çift bitiş ucu
- [ ] K5 `ramp_direction` (Teori'deki "en büyük `ℓ_fit`" kuralı): dar `a×b` dikdörtgen merkezinde
  (`b/a ≤ sin 15°`, ör. 60×12) `k = 0`, `ℓ = min(L/2, a/2)`; 60×40'ta `k = 2` (`ℓ_fit = 30/cos 30° = 34,64 > 30`);
  30° döndürülmüş dar kanal → `k = 2`; `ρ` yarıçaplı daire merkezinde `k = 0`, `ℓ = min(L/2, ρ)`; `[A, B] ⊆ R₀`
- [ ] K6 `loop_ramp_moves` kapalı halka: `ρ = 15` daire, `Δz = 4`: `α = 5°` → tek helis yayı, bitiş açısı
  `H/ρ = 174,638…°`, boy `√(H² + Δz²) + 2πρ = 140,1426325903…`; `α = 3°` → `H = 76,3245… < P`, açı `291,538…°`,
  boy `170,6770700448…`; `H > P` (`α = 1°`) → `⌊H/P⌋` tam tur + kalan; dikdörtgen halkada her köşede
  `z = z₀ − σ_i tan α`, `e`'de bölünme, ikinci değer `e`'den başlayan tam halka
- [ ] K7 Açık profil: `P` boylu doğru, `m = ⌈H/(2P)⌉` gidiş-dönüş, `p₀`'da `z`'de bitiş, sonra `p₀ → p₁`
- [ ] K8 `deepest_point` ve `segment_inside`: dikdörtgende `lo → min(a, b)/2` (1e-6·D), dairede `lo → ρ`;
  `dist(c, ∂N) ≥ lo − KEEP_TOL`; L bölgede köşeden geçen parça `False`, içteki `True`, sınıra uçtan değen `True`
- [ ] K9 `pocket` + `HELIX`/`RAMP`, `center_cutting=False`, `ramp_angle_max = 5`: dikdörtgen (60×40, D = 10),
  L cep (50×45, D = 6), adalı cep, `s ∈ {0,5D}` (03b sonrası `0,8D` de): SPEC 03 K13 çakma yok (giriş hareketleri
  dahil), K14 kalan malzeme yok, K15 hareket kuralları; **düz dalma yok**: `Δz < 0` olan hiçbir kesme hareketinin (`G1`/`G2`/`G3`)
  yatay boyu `< TOL` değil ve her inişte `|Δz|/s_xy ≤ tan α + 1e-12`
- [ ] K10 `contour` + `RAMP`: dairesel iç kontur ve dikdörtgen dış konturda K12 yolları `z`'de aynen var,
  rampa eğimi tam `α`, toplam boy `Σ(√(H² + Δz²) + P)` paso başına
- [ ] K11 Geriye uyum: `entry=None` ve `EntryMode()` ile `pocket`, `contour`, `face` hareketleri SPEC 03 (ve 03b)
  sonucuyla birebir aynı
- [ ] K12 Sığmayan giriş → `CamError` (sessiz düz dalma yok): genişliği `2(r + R_h)`'den dar kanal cepte helis
  (mesajda `dist(c, ∂R₀)`); merkezden kesmeyende `2ℓ_fit < r` zigzag; `P < π r` kontur rampası (bağlantının `R₀`'dan çıktığı durum `segment_inside` düzeyinde K8'de sınanır)
- [ ] K13 G-code: helisli cep SPEC 04 `write` ile yazılıp `read` ile okununca hareketler `decimals`
  toleransında aynı; tam daire helisler `G2`/`G3` + `Z` olarak yazılıyor
- [ ] `pytest` 0 failed, bu SPEC'in testlerinde 0 "uygulanmamış"; `ruff check .` temiz; 10 s'den uzun testler `slow`

## Kapsam dışı
- Giriş-çıkış (lead-in / lead-out) yayları ve teğet yaklaşma; ayrı SPEC.
- Otomatik tür değişimi (helis sığmazsa rampa, o da sığmazsa dalma): çağıran karar verir (29).
- Önceden kesilmiş bölgede (alt halkalar kesildikten sonra) girişi atlayıp düz inme gibi süre iyileştirmeleri;
  her giriş aynı kuralla yapılır.
- Takım çekirdek çapı (`r_c`) modeli; güvenli alt sınır `r/2` kullanılır.
- 3B işlemlerde (06, 06b) ve torna yollarında giriş; delik helisle frezeleme (thread mill / helisel delik) ayrı.
- SPEC 05'in rampa sınırı (alt adım içindeki ilerleme) üzerinde değişiklik.
