# SPEC 03 — 2.5D takım yolu: profil, ofset, yüz alma, kontur, cep

## Amaç
Düzlemsel 2D profillerden (doğru + yay parçaları, adalı bölgeler) düz parmak freze için doğrulanmış
2.5D takım yolları (`cam.model.Toolpath`) üretmek: yüz alma, dış/iç kontur ve kontur-paralel (ofset) cep;
takım yarıçapı telafisi CAM tarafında (ofsetlenmiş merkez yolu), Z'de eşit paso derinlikleri.

## Teori

### Profil ve yön
- Profil, uç uca bağlı **doğru** ve **yay** parçalarından oluşan zincirdir. Kapalı profilde son parçanın
  bitişi ilk parçanın başlangıcıdır (tolerans `LINK_TOL = 1e-7 mm`). Başlangıcı ve bitişi aynı olan tek yay tam dairedir.
- **Bölge (Region)** = bir dış halka + sıfır veya daha fazla iç halka (ada / delik). İç kural:
  **bölgenin içi her halkanın solundadır** → dış halka saat yönü tersi (CCW), iç halkalar saat yönü (CW).
  Kullanıcının verdiği yön ne olursa olsun bu kurala çevrilir.
- Yönlü alan (doğru + yay için kapalı form, Green teoremi):
  `A = Σ ½ (x₀y₁ − x₁y₀)  +  Σ_yaylar ± ½ R² (Δθ − sin Δθ)`
  (+ CCW yay, − CW yay; `Δθ ∈ (0, 2π]` süpürme açısı). Tam dairede `A = ± π R²`.
  Kaynak: O'Rourke, *Computational Geometry in C*, Bölüm 1 (shoelace); yay terimi daire parçası alanıdır.
- Noktanın bölgede olması: sarım sayısı (winding number), yaylar dahil.

### Ofset (takım yarıçapı telafisi)
Bölge Ω'nın `d > 0` iç ofseti, takım merkezinin sınıra `d`'den yakın olmadan gezebildiği küme
`Ω ⊖ B_d = { p ∈ Ω : dist(p, ∂Ω) ≥ d }` sınırıdır (Minkowski farkı); `d < 0` dış ofsettir (`Ω ⊕ B_|d|`).
Doğrunun ofseti normal yönde `d` kaydırılmış doğru, yayın ofseti aynı merkezli `R ∓ d` yarıçaplı yaydır;
bu yüzden **ofsette yaylar korunur** (G2/G3 olarak çıkar). Kaynak: Held, *On the Computational Geometry
of Pocket Machining*, Bölüm 2–3; CAM araştırma notları (proje belgesi).

Yöntem: **ham ofset + budama** (pairwise):
1. Her halkayı soluna doğru `d` kadar kaydır. Ofset yarıçapı ≤ 0 olan yay düşer.
2. Köşelerde (gelen ve giden teğet `t₁, t₂`, `k = t₁ × t₂`):
   ofset tarafında **boşluk** açılıyorsa köşe noktası `V` merkezli `|d|` yarıçaplı yay eklenir
   (dışbükey köşe → takım köşeyi yay çizerek döner); **örtüşme** varsa `q → V → p` iki doğru eklenir
   (bunlar 4. adımda budanır, köşe keskin kalır). Teğet köşede (`|k| ≈ 0`, aynı yön) ek yok.
3. Tüm ham parçaların ikili kesişimleri (doğru–doğru, doğru–yay, yay–yay) bulunur, parçalar bu
   noktalardan bölünür.
4. Her alt parçanın orta noktası `m` için `dist(m, ∂Ω) ≥ |d| − TOL` ve doğru tarafta
   (`d > 0` → `m ∈ Ω`, `d < 0` → `m ∉ Ω`) değilse parça atılır.
5. Kalan parçalar uç uca bağlanarak kapalı halkalar kurulur (yön kuralı korunur: içi solda).

Bu yöntem adaları, dar boğazda ikiye bölünmeyi ve dış ofsette adaların küçülmesini aynı adımlarla çözer.
Analitik sonuçlar (testler bunlara dayanır):
- `a×b` dikdörtgenin `r` iç ofseti: `(a−2r)×(b−2r)` dikdörtgen, **keskin** köşeler; `2r ≥ min(a,b)` → boş.
- `a×b` dikdörtgenin `r` dış ofseti: 4 doğru + 4 çeyrek yay, alan `ab + 2r(a+b) + πr²`, çevre `2(a+b) + 2πr`.
- `R` yarıçaplı dairenin ofseti: `R − d` yarıçaplı tek yay; `d ≥ R` → boş.
- İç ofsetlerin birleşme özelliği: `(Ω ⊖ B_d₁) ⊖ B_d₂ = Ω ⊖ B_(d₁+d₂)`.

### Kontur-paralel cep ve kalan malzeme
Halkalar `d_k = r + k·s` (`r = D/2`, `s` yan paso) ofsetleriyle, ofset boşalana kadar üretilir. Halkalar
bir ağaç kurar (bir halka dar boğazda ikiye bölünebilir). Her **yaprak** halka `L` için içinde kalan
malzeme: `L`'nin iç yarıçapı `t*` (L'nin `t` iç ofsetinin boşaldığı en küçük `t`, ikiye bölme ile `1e-9·D`
hassasiyetle) `r`'den büyükse `L`'nin `t* − r` (+ `LINK_TOL` pay) iç ofseti ek halka olarak eklenir (ortada ada kalmasın).

Açısı `θ` olan bir köşede ardışık iki keskin halka arasında kesilmemiş ada kalmaması koşulu
(açıortay boyunca `min(t, (s−t)/sin(θ/2))` mesafesinin en büyüğü ≤ r):
`s ≤ r (1 + sin(θ/2))` → 90° köşede `s ≤ 1,707 r`. `s ≤ r` her köşede güvenlidir.
Bölgenin kendi içbükey olmayan köşelerinde takımın erişemediği `r² − πr²/4` alanlı köşe kalanı kaçınılmazdır
(sonraki küçük takımla temizlenir; bu SPEC'in işi değil).

### Kesme yönü
Varsayım: iş mili saat yönünde döner (M3). **Tırmanma frezeleme** (varsayılan) = malzeme takımın
ilerleme yönüne göre **sağında**:
- cep halkaları (dış duvar ve adalar) kendi doğal yönünde gezilir (içi solda → malzeme sağda),
- dış kontur saat yönünde (CW), iç kontur saat yönü tersinde (CCW).
`climb=False` (geleneksel frezeleme) tüm halkaları ters çevirir. Kaynak: Sandvik Coromant,
*Metal Cutting Technical Guide*, frezeleme (tırmanma/geleneksel).

### Paso derinlikleri
Toplam derinlik `H = z_top − z_bottom`, en fazla `a_p` olan eşit pasolara bölünür:
`n = ⌈H / a_p⌉`, `z_i = z_top − i·H/n`, `i = 1..n`. Son paso tam olarak `z_bottom`'dadır.

## Dosyalar
- Yeni: `cam/profile.py`, `cam/geom2d.py`, `cam/offset.py`, `cam/ops2d.py`,
  `tests/cam/test_profile.py`, `tests/cam/test_offset.py`, `tests/cam/test_ops2d.py`, `durum/03-cam-2d.md`
- Dokunulmayacak: `cam/model.py` (arayüz sabit), diğer tüm paketler ve ortak dosyalar.
- Not (depo kazanır): koordinatör önerisindeki modül adları (`offset`, `cep`, ...) depodaki İngilizce dosya
  adı düzenine (`core/assembly.py`, `cam/model.py`) uyduruldu. 2D profil tipi henüz `cam/model.py`'de yok;
  bu SPEC onu `cam/profile.py`'de tanımlar. 04/05/06 bunu kullanmak isterse `cam/model.py`'ye taşınması
  ayrı bir arayüz PR'ıdır. Hata tipi `cam.model.CamError` (CAM'de `ModelError`'ın karşılığı).

## Arayüz

### `cam/profile.py`
- `@dataclass(frozen=True) Line(p0: tuple[float, float], p1: tuple[float, float])` — boy < `TOL` → `CamError`
- `@dataclass(frozen=True) Arc(p0, p1, c: tuple[float, float], ccw: bool)` — `|p0−c|`, `|p1−c|` farkı > `ARC_TOL` veya
  `R < R_MIN` → `CamError`; `p0 == p1` tam daire. Özellikler: `R`, `sweep` (`(0, 2π]`).
- Her parça: `length`, `point(t)` (`t ∈ [0,1]`), `reversed()`, `split(t) -> (parça, parça)`.
- `@dataclass Profile(segments: list[Line | Arc], closed: bool = True)` — parçalar uç uca değilse (`LINK_TOL`)
  veya kapalı profil kapanmıyorsa → `CamError`. `area` (yönlü), `length`, `reversed()`, `bbox()`.
- Kurucular: `Profile.polygon(points)`, `Profile.rectangle(x0, y0, a, b)` (CCW), `Profile.circle(c, R, ccw=True)`.
- `@dataclass Region(outer: Profile, holes: list[Profile] = [])` — açık halka → `CamError`; kurulurken yön
  kuralına çevrilir (dış CCW, delikler CW). `area` = dış alan − delik alanları. `contains(p) -> bool`.

### `cam/geom2d.py`
- `TOL = 1e-9`, `LINK_TOL = 1e-7` [mm]
- `intersect(a, b) -> list[tuple[float, float]]` — iki parça arasındaki kesişimlerin parametreleri `(t_a, t_b)`
- `distance(p, seg) -> float`, `distance_to_region(p, region) -> float`
- `winding(p, profile) -> int`

### `cam/offset.py`
- `offset(region: Region, d: float) -> list[Region]` — `d > 0` iç, `d < 0` dış ofset. Sonuç boş olabilir (`[]`).
  Dar boğazda birden çok bölge döner; adalar ilgili bölgenin `holes` listesindedir. `d == 0` → `CamError`.
- `offset_profile(profile: Profile, d: float) -> list[Region]` — kısayol, `Region(profile)` için.

### `cam/ops2d.py`
- `@dataclass Cut(z_top, z_bottom, a_p, feed, plunge_feed, rpm, z_safe, clearance=1.0, stepover=None)`
  - `z_top > z_bottom`, `a_p > 0`, `feed > 0`, `plunge_feed > 0`, `rpm > 0`, `z_safe > z_top`, `clearance ≥ 0`;
    `stepover` cep ve yüz almada zorunlu, `0 < s ≤ D`. Aksi `CamError`.
- `depths(z_top, z_bottom, a_p) -> list[float]` — yukarıdaki eşit paso kuralı.
- `face(stock: Stock, tool: Tool, cut: Cut) -> Toolpath` — ham malzemenin üst yüzünü `z_bottom`'a indirir.
  X'e paralel zigzag sıralar; sıra sayısı `m = ⌈(y_max − y_min)/s⌉ + 1`, sıralar `y_min`'den `y_max`'a eşit aralıklı
  (ilk ve son sıra kenarda); her sıra `x_min − r − clearance`'tan `x_max + r + clearance`'a. Sıralar arası G1.
- `contour(profile: Profile, tool: Tool, cut: Cut, side: str, climb=True) -> Toolpath`
  - `side`: `"dis"` (takım dışarıda, `−r` ofset), `"ic"` (içeride, `+r`), `"uzerinde"` (ofsetsiz; açık profile izin verilen tek seçenek).
  - İç ofset boşsa (takım sığmıyor) → `CamError`.
- `pocket(region: Region, tool: Tool, cut: Cut, climb=True) -> Toolpath` — kontur-paralel cep, içten dışa.
- Hareket kuralları (hepsi için):
  - Yol `z_safe`'te başlar ve biter. Bir halkaya giriş: `G0` XY (`z_safe`'te) → `G0` `z_prev + clearance`'a →
    `G1` `plunge_feed` ile paso derinliğine. Çıkış: `G0` `z_safe`'e.
  - Cepte iç halkadan onu çevreleyen dış halkaya, halkaların arasındaki düz çizgi o derinlikteki geçerli
    merkez kümesinden (`Ω ⊖ B_d`) çıkmıyorsa **inmeden** `G1` ile geçilir; dış halka bu çizginin bittiği
    en yakın noktadan başlatılır. Aksi halde çıkış + giriş.
  - Yaylar `G2`/`G3`, merkez mutlak XY (`cam/model.py` kuralı). Kesme hareketleri `feed` ile.
  - Dönen yol `validate()`'ten geçer.

## Kabul kriterleri
Geometrik değerlerde tolerans aksi yazılmadıkça mutlak `1e-9 mm` (alan için göreli `1e-9`).
- [ ] K1 Profil/Region doğrulamaları: kopuk parça, kapanmayan profil, sıfır boy, tutarsız yay → `CamError`;
  yön kuralı (dış CCW, delik CW) uygulanıyor — `tests/cam/test_profile.py`
- [ ] K2 Yönlü alan ve boy: dikdörtgen `ab`, daire `πR²`, yarım daire + çap `πR²/2`, CW profilde işaret ters;
  adalı bölge alanı; `contains` sınırın içi/dışı/adanın içi — `tests/cam/test_profile.py`
- [ ] K3 Kesişimler: doğru–doğru, doğru–yay (0/1/2 nokta, teğet), yay–yay (iki daire), yay süpürme aralığı dışındaki
  çözümler atılıyor — `tests/cam/test_profile.py`
- [ ] K4 Dikdörtgen iç ofset `(a−2r)×(b−2r)`, keskin köşe noktaları tam; `2r ≥ min(a,b)` → boş — `tests/cam/test_offset.py`
- [ ] K5 Dikdörtgen dış ofset: alan `ab + 2r(a+b) + πr²`, çevre `2(a+b) + 2πr`, 4 çeyrek yay merkezleri köşelerde — `tests/cam/test_offset.py`
- [ ] K6 Daire ofseti `R ∓ d` tek yay; `d ≥ R` → boş — `tests/cam/test_offset.py`
- [ ] K7 Dar boğaz (iki kare + `w` genişlikli köprü): `d < w/2` tek bölge, `d > w/2` iki bölge — `tests/cam/test_offset.py`
- [ ] K8 Adalı bölge: dairesel adanın iç ofsette `R + d`'ye büyümesi; ada ile dış duvar ofsetlerinin birleştiği `d`'de
  halka sayısının değişmesi — `tests/cam/test_offset.py`
- [ ] K9 Ofset özellikleri (rastgele dışbükey/içbükey çokgenler): her sonuç parçası üzerindeki örnek noktaların
  `∂Ω`'ya uzaklığı `|d|` (± 1e-9); birleşme `offset(offset(Ω,d₁),d₂) ≈ offset(Ω,d₁+d₂)` (alan rel 1e-9) — `tests/cam/test_offset.py`
- [ ] K10 `depths`: `H/a_p` tam bölünen ve bölünmeyen durumlar, son derinlik tam `z_bottom` — `tests/cam/test_ops2d.py`
- [ ] K11 `face`: sıra sayısı, sıra aralığı ≤ s, toplam kesme boyu kapalı form, kesilen her noktanın üst yüzeyi
  kapsaması (örnek ızgara) — `tests/cam/test_ops2d.py`
- [ ] K12 `contour`: dairesel konturda yol `R ± r` yarıçaplı yay (merkez ve yarıçap 1e-9); dikdörtgen dış konturda
  yol boyu `2(a+b) + 2πr` her pasoda; tırmanma yönü (dış CW, iç CCW), `climb=False` ters — `tests/cam/test_ops2d.py`
- [ ] K13 `pocket` çakma yok: tüm kesme hareketleri üzerindeki örnek noktalar için `dist(p, ∂Ω) ≥ r − 1e-9` ve
  `p ∈ Ω` (adalar dahil) — `tests/cam/test_ops2d.py`
- [ ] K14 `pocket` kalan malzeme yok: dikdörtgen cepte (`s = 0,5D` ve `s = 0,8D`), dairesel cepte (`s = 0,95D`) ve adalı cepte
  bölgedeki her örnek nokta (erişilemeyen köşe kalanları hariç) bir kesme hareketine `≤ r + 1e-9` uzaklıkta — `tests/cam/test_ops2d.py`
- [ ] K15 Hareket kuralları: yol `z_safe`'te başlar/biter, `validate()` geçer, hızlı hareketler (G0) hiçbir zaman kesme
  derinliğinin altında değil, her paso `depths` ile aynı — `tests/cam/test_ops2d.py`
- [ ] K16 Hatalı girdiler (`Cut` alanları, `stepover > D`, sığmayan takım, açık profilde `"dis"`/`"ic"`) → `CamError` — `tests/cam/test_ops2d.py`
- [ ] `pytest` 0 failed, bu SPEC'in testlerinde 0 "uygulanmamış"; `ruff check .` temiz

## Kapsam dışı
- Rampa / helis giriş, giriş-çıkış (lead-in/out) yayları: bu SPEC düz dalma kullanır (merkezden kesen takım varsayılır). Ayrı küçük SPEC (03b).
- Zigzag / spiral cep, trokoidal / adaptif cep, kalan malzeme (rest machining), köşe kalanı temizliği.
- Delik delme çevrimleri ve G41/G42 makine tarafı telafi (04-gcode), G-code yazımı (04).
- Halka sırası / boş hareket optimizasyonu (TSP); sadece yukarıdaki basit kural.
- Spline / NURBS kenarlar (sadece doğru + yay), 3D yüzeyler (06), parçadan profil çıkarma (05/06).
- Küresel / köşe radyüslü takım: bu SPEC sadece `ToolKind.FLAT` kabul eder, diğerleri `CamError`.
- pyclipper ile çapraz kontrol: testler analitik çözümlerle yeterli; gerekirse ayrı karar (test bağımlılığı).
- Sayısal sağlamlık için tam sayı (Clipper tarzı) aritmetik; `TOL` ile kayan nokta yeterli kabul edildi.
