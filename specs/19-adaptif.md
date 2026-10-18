# SPEC 19 — Adaptif (sabit temas açılı) kaba işleme ve trokoidal kanal

> Onaylandı: kullanıcı, 2026-10-18 11:13 (proje sohbetinde Dalga 5 toplu yazılı onay, "önerilerle"):
> dar bölgeler kalan olarak raporlanır, giriş yerel basit helis, malzeme ızgarası, trokoidal düz kanal dahil.

## Amaç
Düz parmak frezeyle 2.5D cepleri (`cam.profile.Region`) takımın malzemeye **temas açısı** `φ` hiçbir adımda
hedef `φ_t`'yi aşmayacak biçimde boşaltan adaptif kaba işleme yolu ve düz bir kanalı aynı sınırla açan
trokoidal yol üretmek; temas açısının ölçüldüğü bir malzeme ızgarası ve kesilemeyen bölgenin (varsa)
sessizce değil, sonuçta raporlanması.

## Bağlam
- SPEC 03'ün kontur-paralel cebi yan pasoyu sabit tutar ama köşelerde ve halka geçişlerinde temas açısı 180°'ye
  kadar çıkar (tam kanal). Adaptif yolun amacı tersidir: `φ` sabit, böylece derin paso (`a_p` kesici boya kadar)
  ve yüksek ilerleme güvenle kullanılır. Ticari CAM'de "adaptive clearing", "dynamic milling", "VoluMill" adlarıyla
  standart özelliktir (Dalga 5 önerisi H3).
- Bağımlılıklar `main`'de: SPEC 03 (`Region`, `offset`, `Cut`, `depths`), SPEC 05 (çapraz kontrol için `simulate`).
  Arayüz (`cam/model.py`) değişmez; ortak dosyaya dokunulmaz.
- CAM algoritmaları bizimdir; pyclipper / OpenCAMLib gerekirse yalnız testte çapraz kontrol olur (bu SPEC'te gerekmiyor).

## Teori

### Temas açısı (engagement angle)
`r = D/2`, takım merkezi `a`'dan `b`'ye doğrusal bir adım atıyor; `M` adımdan **önceki** malzeme kümesi (XY, bu
paso derinliğinde). Takım çevresi `q(α) = b + r·(cos α, sin α)`. Adımın temas açısı:

  `φ(a, b) = ölçü{ α ∈ [0, 2π) : q(α) ∈ M  ve  dist(q(α), [a, b]) ≥ r }`

İkinci koşul, çevrenin bu adımın önceki konumlarınca zaten süpürülmüş arka kısmını dışarıda bırakır
(`a = b` ise koşul her `α` için sağlanır: malzemede duran takımda `φ = 360°`). Bu tanım küçük adımda standart
"temas yayı" tanımına iner. Kaynak: Sandvik Coromant, *Metal Cutting Technical Guide*, frezeleme (radyal kesme
derinliği ve temas açısı); Altintas, *Manufacturing Automation*, Bölüm 2 (frezeleme geometrisi).

Analitik sonuçlar (bu oturumda 2·10⁴ noktalı örneklemeyle sayısal olarak doğrulandı, sapma < 0,02°):
1. **Düz duvar**, radyal kesme derinliği `a_e`: `φ = arccos(1 − a_e/r)`. `a_e = r` → 90°, `a_e = D` (tam kanal) → 180°.
   Ters bağıntı `a_e = r(1 − cos φ)`.
2. **İçbükey daire** (takım merkezi `ρ` yarıçaplı çemberde, önceki tur `R_p` yarıçaplı daireyi boşaltmış, dışı malzeme):
   `cos φ = (R_p² − ρ² − r²) / (2ρr)`. Sabit `φ` için turlar arası radyal aralık (spiral adımı)
   `Δ(ρ) = ρ + r − √(ρ² + r² + 2ρr·cos φ)`; `ρ → ∞` için `Δ → r(1 − cos φ)` (düz duvar). Dairesel cepte sabit temaslı
   yol, aralığı `Δ(ρ)` olan bir spiraldir.
3. **Trokoid döngüsü** (döngü yarıçapı `ρ`, döngü merkezleri `p` aralıklı; önceki döngü `ρ + r` yarıçaplı daireyi
   boşaltmış; takım döngünün ön noktasında, merkezden uzaklığı `d = ρ + p`):
   `cos φ_max = ((ρ + r)² − d² − r²) / (2 d r)`. Hedef `φ_t` için en büyük aralık
   `p(ρ, φ_t) = −r·cos φ_t + √((ρ + r)² − r²·sin² φ_t) − ρ` (her `ρ > 0`, `0 < φ_t < 180°` için `p > 0`;
   `ρ = 0`, yani kanal genişliği tam `D` ise `φ ≥ 90°`: genişliği `D` olan kanal 90°'nin altında açılamaz).
4. Duvar dalgası: trokoidal kanalın duvarı yarıçapı `R = w/2` olan dairelerin birleşimidir; iki döngü arasında kalan
   tepe yüksekliği `e = R − √(R² − p²/4)` (ör. `w = 15`, `p = 1` → `e = 0,017 mm`). Bu SPEC duvarı perdahlamaz.

### Malzeme ızgarası
Temas açısı ve kalan malzeme, hücre boyu `h` olan bir XY ızgarasında tutulur (`h` varsayılan `D/100`):
- Hücre, merkezi bölgenin içindeyse (`Region.contains`) başlangıçta malzemedir.
- Bir doğrusal adım `[a, b]` merkezi `[a, b]`'ye uzaklığı `≤ r` olan hücreleri boşaltır. Yaylar (helis dahil),
  kiriş sapması `≤ h/4` olan kirişlerle adımlanır (kiriş sayısı `n = ⌈Δθ / (2·arccos(1 − (h/4)/R))⌉`, SPEC 05 kuralı).
- `φ`, çevre üzerinde eşit aralıklı `n_α` noktada (varsayılan 1440) yukarıdaki tanım uygulanarak sayılır:
  `φ ≈ (360°/n_α) · #{k : q_k'nın düştüğü hücre malzeme ve dist(q_k, [a, b]) ≥ r(1 − 1e-12)}`.
- Hata sınırı: malzeme sınırını kesen her çevre noktası en fazla yarım hücre kayar; bu yüzden
  `|φ_ızgara − φ| ≤ tol(φ) = (180/π)·h / (r·sin φ) + 360°/n_α` (`15° ≤ φ ≤ 165°`); `φ = 180°` (kanal) için
  `(180/π)·h/r + 360°/n_α`. Bu oturumdaki deneyde (`h = D/100`, `n_α = 1440`, 200 rastgele ızgara kayması) gözlenen
  en büyük sapma sınırın altında kaldı (ör. `φ = 60°`: 0,75° ≤ 1,57°).

### Adaptif cep yöntemi (başvuru; kabul kriterleri özellikleri sınar, ayrıntı uygulayıcıya kalır)
Bir paso derinliğinde:
1. Geçerli merkez kümesi `C = Ω ⊖ B_(r + leave)` (SPEC 03 `offset`). Boşsa `CamError` (takım sığmıyor).
   Ulaşılabilir hedef `T = C ⊕ B_r`; `Ω ⊖ B_leave`'in `T` dışındaki kısmı (içbükey köşe kalanı) zaten kesilemez.
2. **Giriş:** `C` içinde sınıra en uzak noktada (ızgara üzerinde yaklaşık) yarıçapı `ρ_h = min(helix_radius, o noktanın
   ∂C'ye uzaklığı)` olan helis; eğim açısı `ramp_angle`, ardından aynı derinlikte bir tam tur (taban düzlenir).
   Helisin temas açısı `φ_t` sınırına tabi değildir (Z yönünde kesme ayrı rejimdir).
3. **Cephe izleme:** takım boşaltılmış bölgenin sınırını, malzeme sağında (tırmanma) kalacak biçimde, boyu ≤ `step` olan
   adımlarla izler; her adımda yön, `φ(a, b) ≤ φ_t` ve `b ∈ C` olacak, `φ`'yi `φ_t`'ye olabildiğince yaklaştıracak
   biçimde seçilir (ör. açı üzerinde ikiye bölme). Böyle bir yön kalmazsa geçiş biter.
4. **Bağlantı:** sonraki geçişin başlangıcı boşaltılmış bölgede, `φ = 0` olan ve yakınında malzeme kalan bir noktadır.
   Düz çizgi `C`'den çıkmıyor ve hiç malzeme kesmiyorsa takım inmeden `G1` ile geçer; aksi halde SPEC 03 çıkış + giriş
   kuralı (`G0 z_safe` → `G0` XY → `G0 z_önceki + clearance` → `G1` aşağı; iniş boşaltılmış bölgeye olur).
5. `T` içinde malzeme kalmayınca ya da hiçbir başlangıç noktasından `0 < φ ≤ φ_t` olan adım bulunamayınca durur. Kalan
   malzeme sonuçta raporlanır; **hiçbir adım `φ_t`'yi aşarak kesmez** (dar boğaz, `D`'ye çok yakın genişlikte kanal).
Yol XY'de her paso derinliğinde aynıdır (duvarlar düşey); pasolar `depths(z_top, z_bottom, a_p)`.

### Trokoidal kanal
`P0 → P1` doğrusu boyunca genişliği `w` olan kanal, `ρ = (w − D)/2`, birim yön `t`, boy `L = |P1 − P0|`:
- `p = p(ρ, φ_t)` (yukarıdaki formül 3), döngü sayısı `N = ⌈L/p⌉`, gerçek aralık `p' = L/N ≤ p`,
  döngü merkezleri `c_k = P0 + k·p'·t`, `k = 0..N`.
- Her pasoda: `c_0 − ρt` noktasına giriş, `c_0` merkezli `ρ` yarıçaplı helis (eğim ≤ `ramp_angle`, tur sayısı
  `n_h = ⌈ΔZ / (2πρ·tan(ramp_angle))⌉`, `ΔZ = (z_önceki + clearance) − z_i`), tabanda bir tam tur; sonra her `k = 1..N` için
  arka noktalar arasında `G1` (`c_(k−1) − ρt → c_k − ρt`, bu çizgi önceki döngünün boşalttığı dairenin içindedir, `φ = 0`)
  ve `c_k` merkezli tam tur. Tırmanma: turlar `G3` (CCW), `climb=False` → `G2`.
- Bir döngünün en büyük temas açısı `φ(ρ, p')` (formül 3) `≤ φ_t`; `L/p` tam sayıysa tam olarak `φ_t`.
- Kesilen bölge `c_k` merkezli `w/2` yarıçaplı dairelerin birleşimidir (duvar dalgası formül 4).

## Dosyalar
- Yeni: `cam/adaptive.py`, `tests/cam/test_adaptive_grid.py`, `tests/cam/test_adaptive_pocket.py`,
  `tests/cam/test_trochoid.py`, `durum/19-adaptif.md`
- Dokunulmayacak: `cam/model.py` (arayüz sabit), `cam/ops2d.py`, `cam/offset.py`, `cam/gcode/`, `cam/sim/`
  (yalnız okunur / çağrılır), diğer paketler ve ortak dosyalar (`pyproject.toml`, `DURUM.md`, `docs/`).
- Not (depo kazanır): yol haritasındaki `cam/adaptif.py` adı, `cam/` içindeki İngilizce dosya adı düzenine
  (`ops2d.py`, `dropcutter.py`, `scallop.py`) uyduruldu; SPEC 03'teki emsal.

## Arayüz (`cam/adaptive.py`)

### Analitik yardımcılar (açılar derece, `cam/model.py` birim kuralı)
- `ae_to_engagement(ae: float, D: float) -> float` — `arccos(1 − 2ae/D)`; `0 < ae ≤ D` dışında `CamError`.
- `engagement_to_ae(phi: float, D: float) -> float` — `(D/2)(1 − cos φ)`; `0 < φ ≤ 180` dışında `CamError`.
- `spiral_spacing(rho: float, r: float, phi: float) -> float` — formül 2'deki `Δ(ρ)`; `rho > 0`, `r > 0`.
- `trochoid_pitch(rho: float, r: float, phi: float) -> float` — formül 3'teki `p(ρ, φ)`; `rho > 0`, `0 < φ < 180`.

### `MaterialGrid`
- `@dataclass MaterialGrid(x0: float, y0: float, h: float, nx: int, ny: int, m: np.ndarray)` — `m` `(ny, nx)` bool,
  `True` = malzeme; hücre `(i, j)` merkezi `(x0 + (j + ½)h, y0 + (i + ½)h)`.
- `MaterialGrid.from_region(region: Region, h: float, pad: float = 0.0) -> MaterialGrid` — bölgenin sınır kutusu
  (her yönde `pad` genişletilmiş) üzerinde; merkezi bölgede olan hücreler malzeme. `h ≤ 0` → `CamError`.
- `cut_segment(a, b, r: float) -> float` — merkezi `[a, b]`'ye uzaklığı `≤ r` olan hücreleri boşaltır; boşaltılan alanı
  [mm²] döndürür (`a = b` → disk).
- `cut_arc(p0, p1, center, ccw: bool, r: float) -> float` — yukarıdaki kiriş kuralıyla `cut_segment` dizisi
  (`p0 = p1` tam tur).
- `engagement(a, b, r: float, n: int = 1440) -> float` — yukarıdaki tanımla `φ(a, b)` [derece], ızgarayı değiştirmez.
  Çevre noktası ızgara dışında kalırsa malzeme değildir.
- `area() -> float` — kalan malzeme alanı `h² · Σ m`.

### Adaptif cep
- `adaptive_pocket(region: Region, tool: Tool, cut: Cut, engagement: float, *, leave: float = 0.0,
  step: float | None = None, cell: float | None = None, helix_radius: float | None = None,
  ramp_angle: float = 2.0, climb: bool = True, samples: int = 1440) -> AdaptiveResult`
  - `engagement` = `φ_t` [derece], `0 < φ_t < 180`. `step` varsayılan `D/20`, `0 < step ≤ r/2`.
    `cell` (= `h`) varsayılan `D/100`, `0 < h ≤ D/20`. `helix_radius` varsayılan `r/2`, `≥ 0` (0 → düz dalma).
    `0 < ramp_angle ≤ 15`. `leave ≥ 0`. `samples ≥ 360`.
  - `cut.stepover` verilmişse `CamError` (adaptifte yan paso yerine `engagement`).
  - Takım `ToolKind.FLAT` değilse, `center_cutting=False` ise (rampa/helis 03c'ye kadar) veya `cut.a_p > tool.flute_length`
    ise `CamError`.
- `@dataclass AdaptiveResult(toolpath: Toolpath, material: MaterialGrid, uncut_area: float, max_engagement: float)`
  - `material`: bir paso derinliğinin son ızgarası (`from_region(region, h)`, tüm pasolarda XY aynı).
  - `uncut_area`: `material`'da `T`'nin "iç" hücrelerinde (merkezi `C`'ye uzaklığı `≤ r − h`) kalan malzeme alanı [mm²].
  - `max_engagement`: helis dışındaki kesme adımlarının üretim sırasında ölçülen en büyük `φ`'si.
  - `toolpath.validate()` geçer; hareket kuralları SPEC 03 ile aynı (`z_safe`'te başlar/biter, `G0` kesme derinliğinin
    altına inmez, yaylar `G2`/`G3` mutlak merkezle); cephe izleme adımları `G1`.

### Trokoidal kanal
- `trochoidal_slot(p0, p1, width: float, tool: Tool, cut: Cut, engagement: float, *, ramp_angle: float = 2.0,
  climb: bool = True) -> Toolpath`
  - `width ≤ D` (+`TOL`), `L < TOL`, `engagement ∉ (0, 180)`, `cut.stepover` verilmiş, takım FLAT değil,
    `center_cutting=False`, `a_p > flute_length` → `CamError`.
  - Yol yukarıdaki "Trokoidal kanal" kuralıyla; `validate()` geçer.

## Kabul kriterleri
Geometride tolerans aksi yazılmadıkça mutlak `1e-9 mm`; açıda `tol(φ)` (Teori, malzeme ızgarası). Testlerdeki
"yeniden oynatma": `MaterialGrid.from_region(Ω, h)` üzerinde bir paso derinliğinin hareketleri sırayla
`cut_segment` / `cut_arc` ile uygulanır; helis ve tabandaki ilk tam tur hariç her kesme hareketi boyu `≤ step` olan
parçalara bölünür ve her parçanın `engagement`'ı kesimden önce ölçülür.

Malzeme ızgarası — `tests/cam/test_adaptive_grid.py`
- [ ] K1 Yardımcılar: `ae_to_engagement` / `engagement_to_ae` ters fonksiyon (gidiş-dönüş 1e-12); `a_e = r` → 90°,
  `a_e = D` → 180°; `spiral_spacing(ρ→∞)` → `r(1 − cos φ)` (ρ = 1e6, göreli 1e-6); `trochoid_pitch` formül 3'ü sağlar
  (geri koyunca `φ_max = φ_t`, 1e-9°); aralık dışı girdiler → `CamError`.
- [ ] K2 `from_region` alanı: dikdörtgen, daire, adalı bölge için `|area − A| ≤ çevre·h`; `cut_segment` boşalttığı alan
  kapsül alanı `2rL + πr²` (`± (2L + 2πr)·h`); `cut_arc` tam turda halka `π((ρ+r)² − (ρ−r)²)` (`ρ > r`, aynı tolerans).
- [ ] K3 `engagement` analitik (her biri `h ∈ {D/100, D/200}`, rastgele ızgara kayması, tolerans `tol(φ)`):
  düz duvar `a_e ∈ {0,1D; 0,25D; 0,5D; 0,75D}` → `arccos(1 − a_e/r)`; tam kanal → 180°; içbükey daire
  (formül 2, en az üç `(ρ, R_p)`); trokoid ön noktası (formül 3, en az üç `(ρ, p)`); boşaltılmış bölge içinde → 0;
  malzemede duran takım (`a = b`) → 360°; `engagement` ızgarayı değiştirmez.

Adaptif cep — `tests/cam/test_adaptive_pocket.py` (D = 10 mm, aksi yazılmadıkça)
- [ ] K4 Hareket kuralları: `validate()` geçer; yol `z_safe`'te başlar ve biter; `G0` hareketleri hiçbir zaman
  `z_önceki + clearance`'ın altında değil; paso derinlikleri `depths(z_top, z_bottom, a_p)` ile aynı.
- [ ] K5 Çakma yok: bütün kesme hareketleri (helis dahil) üzerindeki örnek noktalarda `p ∈ Ω` ve
  `dist(p, ∂Ω) ≥ r + leave − 1e-6` (`leave ∈ {0, 0,5}`, adalar dahil).
- [ ] K6 Temas sınırı: yeniden oynatmada her parçanın `φ ≤ φ_t + tol(φ_t)`; `result.max_engagement ≤ φ_t + tol(φ_t)`
  (`φ_t ∈ {45°, 90°}`; daire R = 50, dikdörtgen 100×80, L cep 50×45 kollar 20 / D = 6, dairesel adalı dikdörtgen).
- [ ] K7 Dalmasız iniş: helis dışındaki her aşağı (`ΔZ < 0`) hareketin noktasında yeniden oynatmada
  `cut_segment(p, p, r)` = 0 (takım boşaltılmış bölgeye iner).
- [ ] K8 Tam boşaltma: K6'daki şekillerde ve genişliği `1,6D` olan kanalla bağlı iki karede yeniden oynatmadan sonra
  `T`'nin iç hücrelerinde malzeme yok ve `result.uncut_area == 0`.
- [ ] K9 Sessiz hata yok: genişliği `D + 0,1 mm` kanalla bağlı iki karede (`φ_t = 60°`) K6 geçer ve
  `|result.uncut_area − yeniden oynatmada T'nin iç hücrelerinde kalan alan| ≤ h · çevre(T)`; `result.material` ile yeniden
  oynatma ızgarasının farklı hücre sayısı `≤ nx + ny`.
- [ ] K10 Sabit temas (verim): yeniden oynatmada `φ > 0` olan parçaların toplam boyunun daire R = 50 için en az %70'i,
  dikdörtgen 100×80 için en az %50'si `φ ≥ φ_t − 5°` (`φ_t = 60°`).
- [ ] K11 SPEC 05 çapraz kontrolü: dikdörtgen cep `simulate(...)` (z-haritası, hücre 0,5) kaldırılan hacmi
  `alan(T) · H`'ye göre (`a×b` dikdörtgende `alan(T) = ab − (4 − π)r²`) `≤ çevre · H · 0,5` farkla; çarpışma kaydı yok.
- [ ] K12 Hatalı girdiler → `CamError`: `stepover` verilmiş, `φ_t ∈ {0, 180, −10}`, `leave < 0`, `step ∈ {0, 0,6r}`,
  `cell ∈ {0, D/10}`, `ramp_angle ∈ {0, 20}`, küresel takım, `center_cutting=False`, `a_p > flute_length`,
  sığmayan takım (`C` boş).

Trokoidal kanal — `tests/cam/test_trochoid.py`
- [ ] K13 Geometri: döngü sayısı `N + 1 = ⌈L/p⌉ + 1`, merkezler `c_k = P0 + k·(L/N)·t`, döngü yarıçapı `ρ = (w − D)/2`,
  arka noktalar arası `G1` boyu `L/N`; tırmanmada turlar `G3`, `climb=False` → `G2`; helis tur sayısı `n_h` ve eğimi
  `≤ ramp_angle`.
- [ ] K14 Temas: yeniden oynatmada helis dışındaki en büyük `φ`, `φ(ρ, L/N)` (formül 3) ile `tol` içinde aynı; `L/p` tam
  sayı olan durumda `φ_t` ile aynı.
- [ ] K15 Kesilen bölge: `c_k` merkezli `w/2` dairelerinin içindeki her hücre (sınırdan `h` içeride) boşalmış;
  `[P0, P1]`'e uzaklığı `w/2 + h`'den büyük hiçbir hücre kesilmemiş (taşma yok).
- [ ] K16 Kesme boyu kapalı form (her paso): `n_h·√((2πρ)² + (ΔZ/n_h)²) + (N + 1)·2πρ + L` (helis + tabandaki tur +
  `N` döngü + `N` bağlantı) 1e-6 göreli.
- [ ] K17 Hatalı girdiler (`width ≤ D`, `L = 0`, `φ_t` aralık dışı, `stepover` verilmiş, küresel takım,
  `center_cutting=False`, `a_p > flute_length`) → `CamError`.
- [ ] `pytest` 0 failed, bu SPEC'in testlerinde 0 "uygulanmamış"; `ruff check .` temiz; 10 s'den uzun testler `slow`.

## Kapsam dışı
- İlerleme hızını temas açısına göre ayarlama (talaş inceltme `h_ex = f_z·sin φ`, sabit talaş kalınlığı): SPEC 32.
- Rampa / helis girişin genel hâli, merkezden kesmeyen takım, açık cebe dışarıdan giriş: SPEC 03c (bu SPEC basit helis
  kullanır ve `center_cutting=False` takımı reddeder).
- 3B adaptif (serbest yüzeyde Z seviyeli kaba), çok eksenli adaptif, stoğun önceki işlemden kalan hâlinden başlama
  (05 sonucundan kalan malzeme): SPEC 39 / Dalga 6.
- Yay uydurma (G1 dizisini G2/G3'e çevirme), yol yumuşatma, boş hareket sırası optimizasyonu.
- Trokoidal kanalda yay veya çok parçalı merkez yolu, duvar perdah geçişi.
- Kesin (ızgarasız) temas açısı hesabı: ızgara ve `tol(φ)` yeterli kabul edildi.

## Ek A — Trokoid döngüsü boyunca temas sınırı (onaylandı: kullanıcı, 2026-10-18; koordinatör sorusu 11:56, 2 dakika kuralıyla kabul, kural mesajı 11:14)
Test oturumu, "Trokoidal kanal" kuralının `φ_t`'yi aştığını buldu: formül 3 yalnız döngünün **ön noktasındaki** açıyı verir;
takım ön noktayı geçmeden önce, döngünün alt yarısında (tırmanmada CCW turun ilerleme yönünün sağında kalan, `−n` yarısı)
taze malzemeye dönerken açı büyür. Bu oturumda örneklemeyle (`n_α = 7200`, döngü 0,5° adımlı) ölçülen değerler, `p = p(ρ, φ_t)` ile:

| `ρ` | `φ_t` | ön nokta | döngü boyunca en büyük | konum |
|---|---|---|---|---|
| 2,5 | 60° | 60,0° | 67,9° | ≈ 310° |
| 2,5 | 90° | 90,0° | 118,2° | 270° |
| 5 | 45° | 45,0° | 46,7° | ≈ 333° |
| 1 | 30° | 30,0° | 31,6° | ≈ 331° |

(`r = 5`; konum döngü merkezinden ilerleme yönüne göre CCW açı, ön nokta 0°.)

**A1 — Döngü temas açısı.** Döngü merkezi orijinde, önceki döngünün merkezi `(−p, 0)`, takım döngüye arka noktadan (`α = π`)
girip CCW döner. Takım merkezi `α`'da (`ρ·(cos α, sin α)`) iken malzeme: önceki döngünün boşalttığı `ρ + r` yarıçaplı dairenin
**dışı**, ve bu döngüde `π`'den `α`'ya kadar süpürülmüş bölgenin (merkezleri o yay üzerindeki `r` yarıçaplı disklerin birleşimi)
**dışı**. `φ(α)` bu malzemeye düşen takım çevresinin açısı; `φ_loop(ρ, r, p) = max_{α ∈ (π, 3π]} φ(α)`.
Yalnız bir önceki döngü hesaba katılır: daha eski döngüler malzemeyi yalnız azaltır, bu yüzden `φ_loop` bir üst sınırdır ve ilk
döngüde (`k = 1`, önceki = helis dairesi) tam değerdir. Ön noktada (`α = 2π`) formül 3'e eşittir. Sayısal hesap: çevrede
7200 nokta, `α`'da en az 720 adım ve en büyüğün çevresinde ikiye bölme; hassasiyet 0,1°.

**A2 — Adım seçimi.** Trokoidal kanalın döngü aralığı `p* = max{ p ∈ (0, p(ρ, φ_t)] : φ_loop(ρ, r, p) ≤ φ_t }`
(ikiye bölme, `φ_loop` `p`'de artandır; göreli hassasiyet 1e-9). "Trokoidal kanal" bölümündeki `p = p(ρ, φ_t)` yerine `p*` kullanılır:
`N = ⌈L/p*⌉`, `p' = L/N ≤ p*`. Bedeli biraz daha küçük adım, yani biraz daha uzun süre.

**A3 — Arayüz eki (`cam/adaptive.py`).**
- `trochoid_loop_engagement(rho: float, r: float, p: float) -> float` — `φ_loop` [derece]; `rho > 0`, `r > 0`, `p > 0` dışında `CamError`.
- `trochoid_loop_pitch(rho: float, r: float, phi: float) -> float` — `p*`; `rho > 0`, `0 < phi < 180` dışında `CamError`.
- `trochoid_pitch` (formül 3, ön nokta) aynen kalır.

Ek A ile değişen kabul kriterleri (eski metindeki karşılıklarının yerine geçer):
- [ ] K1a `trochoid_loop_engagement(ρ, r, p(ρ, φ))` ≥ `φ − 0,1°` (ön nokta alt sınırdır) ve yukarıdaki tabloyla 0,2° içinde;
  `trochoid_loop_pitch(ρ, r, φ) ≤ trochoid_pitch(ρ, r, φ)` ve geri konunca `trochoid_loop_engagement = φ` (0,2°) — `tests/cam/test_adaptive_grid.py`
- [ ] K13 (yerine) Döngü sayısı `N + 1 = ⌈L/p*⌉ + 1`, `p* = trochoid_loop_pitch(ρ, r, φ_t)`; diğer maddeler aynı — `tests/cam/test_trochoid.py`
- [ ] K14 (yerine) Yeniden oynatmada helis dışındaki her parçanın `φ ≤ φ_t + tol(φ_t)`; en büyük `φ`, `trochoid_loop_engagement(ρ, r, L/N)`
  ile `tol + 0,2°` içinde aynı ve bu değer `≤ φ_t + 0,2°` — `tests/cam/test_trochoid.py`
