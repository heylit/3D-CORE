# SPEC 06b — 3D yüzey işleme eki: torik ve konik takım, waterline (sabit Z kontur)

> **Onaylandı** (kullanıcı, 2026-10-18 10:38 UTC; konik takımla birlikte).

## Amaç
SPEC 06'nın drop-cutter'ını tek bir **dışbükey takım profili** üzerine kurup **köşe radyüslü (torik)** ve
**konik** takımı eklemek; bunun üstüne dik duvarlar için **waterline** (sabit Z seviyesinde kontur) ince
işleme yolu yazmak: lifler (fiber) üzerinde kesin girişim aralıkları, aralıklardan kapalı döngüler (weave),
uyarlamalı bölme. Sonuç `cam.model.Toolpath`.

## Teori

### Çerçeve
SPEC 06'nın çerçevesi aynen geçerlidir: 3 eksen, takım ekseni +Z, CL = takım ucu (eksen üzerindeki en alt
nokta), yüzey üçgen ağı (`TriMesh`), birimler mm, `TOL = 1e-9`.

### Takım profili
Dönel simetrik takımın alt yüzeyi, eksenden `ρ` uzaklıkta uca göre yüksekliği veren
**profil fonksiyonu** `f(ρ)`, `ρ ∈ [0, R]` (`R = D/2`) ile tanımlanır; `ρ = R`'nin üstünde takım dik silindirdir
(sap / gövde sonsuza uzanır). Profil şartları: `f(0) = 0`, `f` azalmayan ve **dışbükey**. Profil meridyen
düzleminde doğru ve çember yaylarından oluşan parçalı bir eğridir. `ρ > R` için `f = +∞`.

| Takım | `cam.model` | Profil `f(ρ)` |
|---|---|---|
| Düz | `FLAT`, `corner_r = 0` | `0` |
| Küresel | `BALL` (`corner_r = R`) | `R − √(R² − ρ²)` |
| Torik | `FLAT`, `0 < r_c = corner_r < R` | `ρ ≤ R_t` ise `0`; değilse `r_c − √(r_c² − (ρ − R_t)²)`, `R_t = R − r_c` |
| Konik | `CONE` (arayüz eki, aşağıda), uç açısı `φ`, yarı açı `θ = φ/2` | `ρ·cot θ`; kenar yüksekliği `h_c = R·cot θ` |

Düz ve küresel, torikin `r_c = 0` ve `r_c = R` uçlarıdır; formüller sürekli geçer.

**Destek (Legendre) fonksiyonu.** Eğimi `m = tan β ≥ 0` olan düzlem için
`f*(m) = max_{ρ ∈ [0, R]} (m·ρ − f(ρ))`, en büyüğü veren `ρ*(m)` (birden çoksa en küçüğü). Kapalı formlar:
- Düz: `f* = m·R`, `ρ* = R` (`m = 0`'da `ρ* = 0`).
- Küresel: `f* = R(1/cos β − 1)`, `ρ* = R sin β`.
- Torik: `f* = R_t·tan β + r_c(1/cos β − 1)`, `ρ* = R_t + r_c sin β` (`β = 0`'da `ρ* = 0`).
- Konik: `m ≤ cot θ` ise `f* = 0`, `ρ* = 0` (uç değer); değilse `f* = R(m − cot θ)`, `ρ* = R` (kenar değer).

**Ofset (işleme payı).** Takım katısının `δ` yarıçaplı küreyle Minkowski toplamının alt yüzeyi yine dışbükey
bir profildir; ucu `δ` aşağıdadır. `ofset(δ)` bu profili ucu `0`'a kaydırılmış olarak verir:
- Küresel `R` → küresel `R + δ`. Düz `R` → torik (`R + δ`, `r_c = δ`). Torik (`R`, `r_c`) → torik (`R + δ`, `r_c + δ`).
- Konik (`R`, `θ`) → uçta `δ` yarıçaplı küre, ona teğet `θ` yarı açılı koni, kenarda `δ` yarıçaplı yay
  (merkezi eski kenar noktası `(R, h_c)`), dış yarıçap `R + δ`.
Pay ile yükseklik: `z_δ(x, y) = drop(ofset(δ), x, y) + δ` (kesin, Minkowski). SPEC 06'daki düz uç için
tutucu kural (`drop(r + δ) + δ`) bu kesin kuralla değişir; küresel uçta sonuç aynıdır.

### Drop-cutter (genel profil)
Bir üçgende takımın temas yüksekliği
`z_tri(c) = max { P_z − f(|P_xy − c|) : P üçgende, |P_xy − c| ≤ R }`; `z_CL(c) = max_tri z_tri(c)`
(SPEC 06 ile aynı tanım; düz ve küresel uçta sonuçlar değişmez).

**Önerme (içbükeylik).** `h(P, c) = P_z − f(|P_xy − c|)`, `(P, c)`'ye göre birlikte içbükeydir (`f` dışbükey ve
azalmayan, `|·|` dışbükey, `P_z` doğrusal). Dışbükey bir küme üzerinde kısmi en büyük içbükeyliği korur; bu
yüzden `z_tri(c)` kendi tanım bölgesi `{c : dist(c, üçgen_xy) ≤ R}` üzerinde **içbükeydir**. Sonuçlar:
1. Kenar testi tek boyutlu içbükey bir fonksiyonun en büyüğüdür → altın oran / Brent araması global en
   büyüğü bulur (yerel tuzak yok).
2. `{c : z_tri(c) > z}` dışbükeydir → bir doğru (lif) ile kesişimi tek bir **aralıktır** (waterline'ın temeli).

Testler (her biri bir aday değer verir; sonuç en büyükleri):
- **Köşe** `P`: `d = |P_xy − c| ≤ R` ise `z = P_z − f(d)`.
- **Yüz** (birim normal `n`, `n_z > 0`, `n_xy ≠ 0`; yokuş yukarı yön `u = −n_xy/|n_xy|`, `m = |n_xy|/n_z`):
  CC_xy = `c + ρ*(m)·u`; CC üçgenin içindeyse `z = z_düzlem(c) + f*(m)`. Yatay yüzde (`n_xy = 0`)
  CC_xy = `c`, `z = z_düzlem`. Dik yüzler (`|n_z| < NZ_TOL`) yüz testine girmez.
- **Kenar** `P(t) = P₀ + t(P₁ − P₀)`, `t ∈ [0, 1]`: `[t₀, t₁]` kenarın XY izdüşümünün `c` merkezli `R` diskinin
  içinde kalan kısmıdır (doğru–daire kesişimi); boşsa test yok. `g(t) = P_z(t) − f(d(t))` bu aralıkta içbükeydir;
  `z = max g`. Düz ve küresel uçta SPEC 06'nın kapalı formları geçerlidir; torik ve konik uçta sabit sayıda
  adımlı, numpy ile vektörlü altın oran araması (aralığı ilk boyunun `1e-12` katına daraltacak kadar adım) kullanılır.
  Dik kenar (`|u_z| ≈ 1`) köşe testine bırakılır.

Analitik sonuçlar (testler bunlara dayanır):
- Yatay düzlem `z₀`: her takımda `z_CL = z₀`.
- Eğik düzlem `z = x·tan β` (yeterince geniş): `z_CL = x·tan β + f*(tan β)` → torik
  `R_t tan β + r_c(1/cos β − 1)`; konik `β ≤ 90° − θ` iken `0`, değilse `R(tan β − cot θ)`.
- Tek köşe: `z_V − f(d)`. Yatay tek kenar (XY uzaklığı `d`): `z_e − f(d)`.
- Ekseni dikey düzlemde olan eğik kenar (`d = 0`, eğim `γ`): `z = z_kenar(c) + f*(tan γ)` (yüz formülüyle aynı).
- `ρ_s` yarıçaplı küre (merkez orijin), XY uzaklığı `d`: torikte `d ≤ R_t` ise `z_CL = ρ_s`, değilse
  `z_CL = √((ρ_s + r_c)² − (d − R_t)²) − r_c` (temas üst yarıkürede). Konikte meridyen çizgisi küreye teğet:
  `z_CL = (ρ_s − d·cos θ)/sin θ`, teğet noktası koninin `[uç, kenar]` parçasındaysa; değilse uç (`√(ρ_s² − d²)`)
  veya kenar değeri.
- **Çakma yok + temas var:** her CL'de takım katısı ağa girmez (her `P` için `P_z ≤ z_CL + f(d) + TOL`) ve en az
  bir `P` eşitliği sağlar.

### Waterline (sabit Z kontur)
Seviye `z` için **girişim bölgesi** `I(z) = {c : z_CL(c) > z}` (floor yok; üçgen yoksa `−∞`). Takım ucu `z`'deyken
`c ∉ I(z)` ise takım ağa girmez. Waterline döngüleri `I(z)`'nin sınırıdır. `z_CL`, dik duvarlarda süreksizdir
(sıçrar); bu yüzden kontur `z_CL = z` denklemiyle değil, girişim aralıklarıyla bulunur.

1. **Lifler.** Ağın XY sınır kutusu `R + s_f` kadar büyütülür. Bu kutuda `s_f` aralıklı ortak ızgara:
   X lifleri `y = y_j` doğruları, Y lifleri `x = x_i` doğruları (`x_i = x_min + i·s_f`, `y_j` aynı kural).
2. **Girişim aralıkları (push-cutter).** Her (lif, aday üçgen) çifti için `{t : z_tri(p(t)) > z}` önermeye göre
   tek aralıktır. Uçları lif boyunca `≤ 1e-10` doğrulukla bulunur (kapalı form veya: önce aralık içinde
   `z_tri`'nin en büyüğü altın oranla, sonra iki yanda `z_tri > z` yüklemine ikiye bölme; yüklem dik duvardaki
   sıçramada da çalışır). Bir lifin aralıkları birleştirilir (örtüşen veya `TOL` içinde değenler); boyu `TOL`'dan kısa
   aralık atılır. Aralık uçları **kontur noktalarıdır** (CL noktası).
3. **Örgü (weave).** Düzlemsel çizge `G`: düğümler = kontur noktaları + bir X aralığıyla bir Y aralığının kesişimleri
   (kapalı aralıklar); kenarlar = aynı aralık üzerinde ardışık düğümler. Her kontur noktası bir yapraktır.
   Döngüler `G`'nin yarım-kenar yüzlerinden çıkar: bir düğümde sonraki kenar, gelinen kenardan saat yönü tersine
   ilk kenardır (yaprakta geri dönülür). Her yüz yürüyüşünde rastlanan kontur noktalarının döngüsel sırası bir
   **döngüdür**; kontur noktası olmayan yüzler (bölgenin içindeki hücreler) atılır. Her kontur noktası tam bir
   döngüde tam bir kez yer alır.
4. **Yön.** Tırmanma (`climb=True`, M3): `I(z)` (malzeme) hareket yönünün **sağındadır** → dış sınır saat yönünde
   (CW), iç sınır (cep, delik) saat yönü tersinde (CCW); SPEC 03 kuralı. `climb=False` hepsini ters çevirir.
5. **Uyarlamalı bölme.** Ardışık iki nokta `a, b` (boy `L`) için orta nokta `m` ve parçaya dik birim `n`
   (`I(z)`'den dışarı bakan). `m ∈ I(z)` ise `m + s·n`, değilse `m − s·n` boyunca `s ∈ (0, L]`'de yüklem
   değişimi aranır, ikiye bölmeyle sınır noktası `q` (`1e-10`) bulunur. `|q − m| > tol` ise `q` araya eklenir;
   `L/2 < ds_min` olunca durulur; `(0, L]`'de değişim yoksa parça olduğu gibi kalır. İki noktalı döngü (tek lifin
   kestiği ince bölge) bu adımla açılır.
6. **Başlangıç ve sıra.** Her döngü en küçük `x`'li noktasından başlar (eşitlikte en küçük `y`). Bir seviyedeki
   döngüler başlangıç noktalarının `(x, y)` sözlük sırasıyla gezilir; seviyeler yukarıdan aşağı.

Sınırlama (bilinçli): hiçbir lifin kesmediği girişim bileşenleri ve boşluklar görülmez; çözünürlük `s_f`'dir.

Analitik sonuçlar:
- **Prizma çıkıntı** (XY'de basit çokgen `Q`, `z ∈ [z_a, z_b]` arasında dik duvarlar, `z_a ≤ z` ve
  `z + f(R) ≤ z_b`): her takımda kontur `{c : dist(c, Q) = R}` (köşelerde `R` yarıçaplı yaylar). Her döngü noktası
  için `|dist(c, Q) − R| ≤ 1e-9`. Dışbükey `Q` → tek döngü, CW.
- **İçi boş prizma** (dış `Q₁`, iç delik `Q₂`; `Q₂`'nin iç teğet çember yarıçapı `> R`): iki döngü, iç döngü CCW.
- **İki ayrık çıkıntı** (aralarındaki boşluk `> 2R + 2s_f`): iki döngü.
- **Yarıküre** `ρ_s` (merkez orijin), `0 ≤ z < ρ_s`: kontur yarıçapı küresel `√((ρ_s + R)² − (z + R)²)`,
  torik `R_t + √((ρ_s + r_c)² − (z + r_c)²)`, düz `√(ρ_s² − z²) + R`, konik (teğet koni parçasındaysa)
  `(ρ_s − z sin θ)/cos θ`. Ağ kiriş hatası `ε` kadar tolerans.
- **Dik duvarda iz:** dik duvar boyunca `Δz` aralıklı seviyelerde duvardaki sırt yüksekliği küresel uçta
  `scallop_flat(R, Δz)`, torikte `scallop_flat(r_c, Δz)` (`Δz ≤ 2r_c`).

### İz yüksekliği ekleri (yatay düzlemde, yan paso `s`)
- Torik: `s ≤ 2R_t` → `h = 0`; değilse `h = r_c − √(r_c² − (s/2 − R_t)²)`; `s > 2R` → `CamError`.
- Konik: `h = (s/2)·cot θ`; `h > h_c` (yani `s > 2R`) → `CamError`.

## Dosyalar
- Yeni: `cam/cutter.py`, `cam/waterline.py`, `tests/cam/test_cutter.py`, `tests/cam/test_dropcutter_ek.py`,
  `tests/cam/test_waterline.py`, `durum/06b-cam-3d-ek.md`.
- Değişecek: `cam/dropcutter.py` (genel profil, torik ve konik), `cam/ops3d.py` (pay için `ofset`),
  `cam/scallop.py` (`scallop_torus`, `scallop_cone`).
- Değişecek test (test oturumu, bu SPEC onayıyla): `tests/cam/test_dropcutter.py` ve `tests/cam/test_ops3d.py`
  içindeki "köşe radyüslü düz → `CamError`" parametreleri artık geçerli değildir; test oturumu bunları kaldırır
  veya torik takımın kabul edildiğini doğrulayan teste çevirir. Diğer SPEC 06 testleri değişmeden geçmelidir.
- Kullanılır (değişmez): `cam/model.py` (`Tool`, `ToolKind`, `Move`, `Toolpath`, `CamError`), `cam/ops2d.py`.
- **Arayüz eki (ayrı PR, "CAM model arayüzü" sahibi):** `ToolKind.CONE = "konik"` ve
  `Tool.tip_angle: float | None = None` [derece, tam uç açısı]. `CONE` için zorunlu, `0 < tip_angle < 180`,
  `corner_r = 0`, `R·cot(tip_angle/2) ≤ flute_length`; `DRILL` için isteğe bağlı (SPEC 05 konik dip için kullanabilir);
  diğer türlerde verilirse `CamError`. `to_dict` / `from_dict` alanı taşır. Bu ek gelmeden konik takımın kodu ve
  testleri yazılamaz; torik ve waterline beklemez.
- Dokunulmayacak: tüm `*/model.py`, diğer paketler, ortak dosyalar.

## Arayüz

### `cam/cutter.py`
- `@dataclass(frozen=True) Cutter` — dışbükey profil; parçalar doğru ve yay. Kurucu: `f(0) = 0`, azalmayan,
  dışbükey, `R > 0` değilse `CamError`.
  - `Cutter.flat(R)`, `Cutter.ball(R)`, `Cutter.torus(R, r_c)` (`0 ≤ r_c ≤ R`), `Cutter.cone(R, theta)`
    (`0 < theta < 90°`, radyan değil derece verilir: `theta` yarı açı).
  - `Cutter.from_tool(tool: Tool) -> Cutter` — `BALL`, `FLAT` (her `corner_r`), `CONE`; `DRILL` → `CamError`.
  - `R: float` (dış yarıçap), `height: float` (`f(R)`).
  - `f(rho: array) -> array` — `rho > R` → `inf`; `rho < 0` → `CamError`.
  - `support(m: array) -> tuple[array, array]` — `(f*(m), ρ*(m))`; `m < 0` → `CamError`.
  - `offset(delta: float) -> Cutter` — `delta ≥ 0`; `delta = 0` aynı profil.

### `cam/dropcutter.py` (değişiklik)
- `drop(mesh, tool: Tool | Cutter, xy, floor=None)` ve `drop_one(...)`: `Tool` verilirse `Cutter.from_tool`.
  Torik ve konik desteklenir; `DRILL` → `CamError`. Düz ve küresel uçta sonuçlar SPEC 06 ile aynı.

### `cam/ops3d.py` (değişiklik)
- `finish` ve `rough` her `Cutter.from_tool` takımını kabul eder. `rough`'ta pay: `z_δ = drop(cutter.offset(δ)) + δ`.

### `cam/scallop.py` (ek)
- `scallop_torus(R, r_c, s) -> float`, `scallop_cone(R, theta, s) -> float` (`theta` yarı açı, derece). Hatalı girdi
  (`R ≤ 0`, `r_c ∉ [0, R]`, `theta ∉ (0, 90)`, `s < 0`, `s > 2R`) → `CamError`.

### `cam/waterline.py`
- `waterline_loops(mesh: TriMesh, tool: Tool | Cutter, z: float, fiber_step: float, tol: float, ds_min: float,
  climb: bool = True) -> list[np.ndarray]` — her döngü `(k, 2)` XY dizisi, kapanış noktası tekrar edilmez, sıra
  ve başlangıç yukarıdaki kural. `fiber_step > 0`, `0 < ds_min`, `tol > 0` değilse `CamError`. Girişim yoksa `[]`.
- `@dataclass Waterline(z_levels, fiber_step, tol, ds_min, feed, plunge_feed, rpm, z_safe, clearance=1.0,
  climb=True)` — `z_levels` boş olmayan, kesin azalan; diğer pozitiflik koşulları `Raster` gibi; aksi `CamError`.
- `waterline(mesh: TriMesh, tool: Tool, w: Waterline) -> Toolpath` — `z_safe < mesh.bbox()[1][2] + clearance`
  → `CamError`. Her döngü için: `G0` `(x_s, y_s, z_safe)`, `G0` `z + clearance`, `G1 plunge_feed` `z`,
  `G1 feed` döngü boyunca başlangıca dönüş, `G0` `z_safe`. Yol `z_safe`'te başlar ve biter, `validate()`'ten geçer,
  `rpm = w.rpm`.

## Kabul kriterleri
Geometrik değerlerde tolerans aksi yazılmadıkça mutlak `1e-9 mm`. Konik takım kriterleri (K3'ün konik kısmı,
K6, K11'in konik kısmı) arayüz eki birleşince yazılır.
- [ ] K1 `Cutter` profilleri: düz, küresel, torik, konik `f(ρ)` tablodaki formüllerle; `r_c = 0` ve `r_c = R` torik
  düz ve küresele eşit; `ρ > R` → `inf`; dışbükey olmayan / azalan profil, hatalı parametreler → `CamError` — `test_cutter.py`
- [ ] K2 `support`: dört takımda kapalı form `f*`, `ρ*`; kaba kuvvet (`ρ`'yu sık örnekleyerek) ile 1e-9 — `test_cutter.py`
- [ ] K3 `offset`: düz → torik (`R+δ`, `δ`), torik → torik, küresel → küresel; konik ofset profili, takım katısını
  `δ` küreyle büyütmenin kaba kuvvet alt zarfıyla 1e-6; `offset(0)` aynı — `test_cutter.py`
- [ ] K4 Torik drop-cutter: yatay düzlem, eğik düzlem (`β` = 10°, 30°, 60°) `R_t tan β + r_c(1/cos β − 1)`,
  tek köşe, yatay kenar, `d = 0` eğik kenar kapalı formları — `test_dropcutter_ek.py`
- [ ] K5 Torik uç küre ağında (kiriş hatası `ε`): `d ≤ R_t` ve `d > R_t` formülleri ± `ε` — `test_dropcutter_ek.py`
- [ ] K6 Konik drop-cutter: eğik düzlemde uç ve kenar dalları (`β` her iki tarafta), tek köşe, küre ağında teğet formül — `test_dropcutter_ek.py`
- [ ] K7 Çakma yok + temas var ve kaba kuvvet: rastgele dalgalı ağlarda torik (ve konik) uçta her CL'de
  `max_P (P_z − f(d)) − z_CL ∈ [−1e-9, 1e-9]` (ağı sık örnekleyen bağımsız hesap, örnekleme hatası içinde) — `test_dropcutter_ek.py`
- [ ] K8 SPEC 06 uyumu: düz ve küresel uçta yeni `drop` = SPEC 06 kapalı formları (SPEC 06 testleri yeşil) — mevcut testler
- [ ] K9 `rough` pay: torik ve düz uçta hiçbir CL'de takım katısı ağa `allowance − 1e-9`'dan yakın değil; yatay
  üst yüzeyde son yükseklik tam `z_üst + allowance`; eğik düzlemde düz uçta pay tam `δ` (kesin ofset) — `test_dropcutter_ek.py`
- [ ] K10 `finish` torik uçla yatay düzlemde: ölçülen iz (alt zarf) `scallop_torus(R, r_c, s)`; `s ≤ 2R_t`'de 0 — `test_dropcutter_ek.py`
- [ ] K11 `scallop_torus`, `scallop_cone`: formül, `r_c = 0`'da `s ≤ 2R` için 0, `r_c = R`'de `scallop_flat(R, s)`,
  hatalı girdiler → `CamError` — `tests/cam/test_scallop.py` eki veya `test_dropcutter_ek.py`
- [ ] K12 Waterline prizma: dışbükey ve içbükey çokgen çıkıntıda her döngü noktasında `|dist(c, Q) − R| ≤ 1e-9`
  (düz, küresel, torik); tek döngü; tırmanmada CW, `climb=False`'ta CCW — `test_waterline.py`
- [ ] K13 Waterline topoloji: iki ayrık çıkıntı → iki döngü; içi boş prizma → dış CW + iç CCW; girişim yok → `[]`;
  her lif aralığı ucu tam bir döngüde tam bir kez — `test_waterline.py`
- [ ] K14 Waterline yarıküre: dört takımda kontur yarıçapı formülü ± ağ `ε` — `test_waterline.py`
- [ ] K15 Waterline sınır doğruluğu: rastgele dalgalı ağda her döngü noktası `c` için döngü normali `n` ile
  `z_CL(c + η n) ≤ z` ve `z_CL(c − η n) > z` (`η = 1e-7`); `ds_min`'e takılmayan her parçanın orta noktasında
  dik doğrultudaki sınır uzaklığı `≤ tol` — `test_waterline.py`
- [ ] K16 Dik duvarda iz: `Δz` aralıklı seviyelerle duvardaki ölçülen sırt küresel `scallop_flat(R, Δz)`,
  torik `scallop_flat(r_c, Δz)` — `test_waterline.py`
- [ ] K17 `waterline` yolu: `z_safe`'te başlar/biter, `validate()` geçer, her döngü yukarıdaki hareket sırasında,
  seviyeler azalan, kesme `G1 feed`, dalma `G1 plunge_feed`, `rpm` doğru; dalma noktasında takım ağa girmez — `test_waterline.py`
- [ ] K18 Hatalı girdiler (`Waterline` alanları, azalmayan `z_levels`, yetersiz `z_safe`, `DRILL`) → `CamError` — `test_waterline.py`
- [ ] K19 (isteğe bağlı) OpenCAMLib kuruluysa torik `BatchDropCutter` (`BullCutter`) ve `Waterline` ile çapraz kontrol
  (drop 1e-6 mm; waterline noktalarının bizim konturumuza uzaklığı `≤ 1e-4 mm`); değilse atlanır — `tests/reference/test_ocl_dropcutter.py` eki
- [ ] `pytest` 0 failed, bu SPEC'in testlerinde 0 "uygulanmamış"; `ruff check .` ve `ruff format --check .` temiz;
  10 saniyeden uzun testler `@pytest.mark.slow`

## Kapsam dışı
- Dik / sığ bölge ayrımı (waterline'ı yalnız dik yerlerde, raster'ı sığ yerlerde kullanmak), birleşik ince işleme.
- Seviyeler arası köprüleme (aşağı inmeden döngüden döngüye geçiş), rampa / helis giriş, döngü sırası optimizasyonu (TSP).
- Lif aralığından dar bileşen ve boşlukların bulunması (uyarlamalı lif sıklaştırma), sabit iz yüksekliğine göre seviye seçimi.
- Konik küresel (tapered ball) ve kesik koni (pah frezesi) takımlar; `Cutter` bunları ifade edebilir ama `Tool`'da karşılıkları yok.
- Tutucu / sap çarpışması (05), talaş simülasyonu, G-code yazımı (04 `Toolpath` okur).
- 4/5 eksen, eğik takım ekseni; NURBS üzerinde doğrudan hesap.
