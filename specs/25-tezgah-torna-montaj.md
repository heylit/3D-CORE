# SPEC 25 — Tezgah: torna ekranı ve montaj ekranı

> **Durum: ONAYLANDI** (kullanıcı, 2026-10-18 10:24 UTC kart "Önerilerle onayla", 10:38 UTC yazılı onay: montajda CAD
> şekli, bağ yalnız torna işine, otomatik öneri dahil, DRO varsayılanı çap). Kod, SPEC 24 iskeleti `main`'e girdikten ve aşağıdaki
> "Bağımlılıklar" tablosundaki SPEC'ler (21, 22, 09) onaylanıp birleştikten sonra başlar.
> Prototip: https://claude.ai/artifact/2YA8RRJYuFSpRJyEFMEX8u ("Torna" ve "Montaj" sekmeleri; konsept, kabul ölçütü değil).
> SPEC 24'ün "Öneri: SPEC 25" bölümünün ayrıntılı halidir.

## Amaç
Tezgah'a (SPEC 24) iki çalışma alanı eklemek: **Torna** (kademeli mil işi: yol, çap programlı G-code, devir,
talaş simülasyonu, çene ve punta kontrolleri) ve **Montaj** (montaj ağacı, BOM, montaj sırası, parça başına
serbestlik, girişim). İkisi tek iplikle bağlıdır: montajdaki mil tornada işlenen parçanın kendisidir; girişim
çıkarsa düzeltme tornadaki parametreye yazılır ve torna işi yeniden hesaplanır. Bu adım bitince örnek
"yatak grubu" tarayıcıda uçtan uca çalışır: mil girişim yapar, öneri uygulanır, girişim sıfırlanır, torna
G-code'u ve çevrim süresi değişir.

## Temel ilke (SPEC 24'ten aynen)
Ön yüz hesap yapmaz. Torna yolu (20), torna G-code'u ve geri okuma (21), torna simülasyonu, süre ve çarpma (22),
montaj ağacı ve BOM (07), kısıt çözümü ve serbestlik (08), girişim (09) Python'dan gelir. Ön yüz gösterir,
ara değer verir (yalnızca görsel), sunucudan gelen iki sayının farkını gösterebilir ve girdiyi sunucuya iletir.

## Bağımlılıklar
| SPEC | Durum (2026-10-18) | Bu SPEC'in ondan kullandığı yetenek |
|---|---|---|
| 24 Tezgah | onaylı, kod yazılıyor | kabuk, köprü, `Is` şeması, ikili diziler, zaman şeridi, kanıt paneli, komut çubuğu |
| 20 Torna yolu | `main` | `cam.lathe_ops` işlemleri, `cam.model.LatheTool`, `CylinderStock` |
| 21 Torna G-code | yazılıyor | çap programlı yazıcı; okuyucu; çevrim satırlarının (`G71`/`G70`/`G76`) kanonik açılımı (satır → hareketler) |
| 22 Torna sim | yazılıyor | hareket başına kesit durumu (dış / iç yarıçap); `G96`/`G50` altında süre; çene ve punta çarpması; parçadan dönel profil çıkarma |
| 07 Montaj ağacı | `main` | `assy.tree` (`validate`, `walk`, `flatten`), `assy.bom` (`bom`, `total_mass`, `mass_center`) |
| 08 Kısıtlar | `main` | `assy.solver` (`solve`, `dof`), `assy.mates.jacobian` |
| 09 Girişim | yazılıyor | parça çifti için kesişim katısı ve hacmi; boşluk ölçümü; `common` |
| 02 Parça | `main` | `Part.volume`, `Part.mesh` / `geometry.mesh.tessellate`, `mesh_volume` |

21, 22 ve 09'un fonksiyon adları bu SPEC'te uydurulmaz: kod yazılırken onaylı SPEC metinlerinden alınır.
Tabloda adı geçen bir yetenek o SPEC'lerde yoksa `tezgah/` içinde yazılmaz; eksik, ilgili SPEC'e ek olarak
kullanıcıya sorulur (altın kural 3).

## Teori ve veri modeli

### Torna işi (`tur: "torna"`)
SPEC 24 `Is` şemasına tek alan eklenir: `tur: "freze" | "torna"` (yoksa `"freze"`; SPEC 24'ün kabul kriterleri
değişmez). Torna işinde:
- **Koordinatlar:** hareketler `cam.model` kuralıyla `(x, 0, z)`, `x` **yarıçap** (SPEC 20). G-code'da `X` **çaptır**
  (SPEC 21). DRO varsayılan olarak çap gösterir (`X = 2x`, G-code'daki sözcükle aynı sayı); `R` tuşu yarıçapa çevirir.
- **Kurulum:** `kurulum.stok = {tur: "silindir", D, d, zmin, zmax}` (`CylinderStock.to_dict`), ayna ve punta
  geometrisi SPEC 22'nin kurulumundan (gösterim ve çarpma kontrolü için).
- **Takım:** `LatheTool` alanları (uç numarası `T`, burun yarıçapı `r`, `κr`, `εr`, tür). Sahnede uç, hayali uç
  noktası ve burun dairesiyle çizilir; yol **hayali uç** yoludur (SPEC 20), takım çizimi burun merkezini
  `C = P − q_T` noktasına koyar (`q_T` köprüden gelir, ön yüz tablo tutmaz).
- **Devir:** her nokta için iş mili devri `n_k` köprüden gelir:
  `G96`'da `n = min(1000·Vc / (π·D), n_max)`, `D = 2x` [mm], `n_max` = `G50` sınırı; `G97`'de `n = rpm`.
  `x → 0`'da `n = n_max` (sonsuz devir yok, altın kural 5: `G96` altında `n_max` tanımsızsa `CamError`).
- **Süre:** SPEC 22'nin (ya da 21'in) süre fonksiyonundan. Analitik kontrol, sabit kesme hızında alın tornalama
  (`x₁ → x₀`, ilerleme `f` mm/dev, `Vc` m/dk, `x_c = 1000·Vc / (2π·n_max)`, `x₀ ≤ x_c ≤ x₁`):
  `t = 60 · [ π·(x₁² − x_c²) / (1000·Vc·f) + (x_c − x₀) / (f·n_max) ]` saniye.
- **İkili `noktalar`:** SPEC 24 biçimi + `float32[n]` devir `n_k` [dev/dk].
- **İkili `sim` (torna):** `z` ekseninde eşit aralıklı hücreler (`Δz`, hücre merkezi `z_c`); her hücre için
  `(nokta indeksi k, yeni r_dis, yeni r_ic, işlem)` olayları, hücreye göre sıralı + ofset dizisi. `k` anındaki kesit =
  her hücrede indeksi ≤ k olan son olay; olay yoksa ham malzeme (`D/2`, `d/2`). Hücre değerleri SPEC 22'nin
  hareket sonrası kesitinin `z_c`'deki örneğidir. Sahne bu kesiti eksen etrafında döndürür.
- **Hedef profil:** parçadan SPEC 22 ile çıkarılan profil, aynı hücrelerde örneklenmiş `float32` dizi olarak
  gönderilir (sapma katmanı ve kesit büyüteci için).

### Montaj (`Montaj` JSON)
```
Montaj = {
  sema: 1, ad,
  agac: Node.to_dict(),                       # SPEC 07
  parcalar: [{kimlik, ad, malzeme, rho, kaynak: {is, tur} | null, hacim}],
  bilesenler: [{yol, parca, T, sabit}],        # flatten(...) sırasıyla, T çözülmüş (4x4, satır öncelikli)
  bom: [BomLine], kutle: {toplam, merkez: [x,y,z]},
  sira: [Adim], girisimler: [Girisim], kontroller: [Kontrol], baglar: [Bag]
}
Adim = {i, yol, ad, yaklasma: [dx,dy,dz], mesafe, T_once, T_sonra, dof_toplam, serbestlik: {yol: Serbestlik}}
Serbestlik = {sayi, oteleme: [[ux,uy,uz]], vida: [{yon, nokta, hatve}], etiketler: ["Tz", "Rz", "vida"]}
Girisim = {a, b, hacim, bosluk, ag: "girisim/<i>"}
Bag = {parametre: {is, anahtar, deger, min, max}, parcalar: [kimlik]}
```

### Montaj sırası
Montaj tanımı yaprak yollarının bir listesini (`sira`) taşır. Adım `i`'de ilk `i + 1` bileşen yerleşmiştir.
- Alt montaj `A_i`: yerleşmiş bileşenler ve **iki ucu da yerleşmiş** kısıtlar. İlk adımın bileşeni sabittir.
- `T_sonra` = `assy.solver.solve(A_i)` sonucu, `dof_toplam` = `assy.solver.dof(A_i)` (bilgi; kontrol sonra).
- Önceki bileşenlerin konumu sonraki adımlarda değişebilir (çözücü hepsini çözer); ön yüz her adımın kendi `T`'lerini kullanır.
- Geçersiz sıra → `AssyError` → 422: ilk adım sabit değil; yaprak olmayan / bilinmeyen / yinelenen yol;
  bir yaprağın sırada hiç olmaması.

### Parça serbestliği
Bileşen `c` için diğerleri sabit tutulur: `J_c = jacobian(A_i, c'ye dokunan kısıtlar, [c])` (6 sütun, `[Δt, ω]`,
dünya ekseni, SPEC 08). Serbestlik sayısı `6 − rank(J_c)` (SPEC 08'in rank toleransıyla); serbest hareketler
`J_c`'nin sıfır uzayı `N`.
- **Öteleme alt uzayı:** `{v ∈ N : ω = 0}`; ortonormal birim yönler `u`.
- **Vida eksenleri:** `N`'de öteleme alt uzayının dik tümleyeni; her taban vektörü `(Δt, ω)` için
  `yön = ω/|ω|`, eksen üstündeki nokta `p = ω × Δt / |ω|²`, hatve `h = ω·Δt / |ω|²` (Murray–Li–Sastry, Bölüm 2.4).
  Saf dönmede `h = 0` ve `p` dönme ekseni üstündedir (`Δt = p × ω`).
- **Etiket:** yön bir dünya eksenine paralelse (`1 − |yön·e| ≤ 1e-9`) `"Tx" … "Rz"`, değilse `"T"` / `"vida"`.
- Taban seçimi tekil değildir; testler alt uzayları karşılaştırır (asal açılar), tek boyutlularda ekseni doğrudan.

### Yaklaşma yönü ve patlatılmış görünüm
Adım `i`'nin bileşeni `c` önceden yerleşmiş bir bileşene bağlanırken şu yönden gelir:
1. `c`'nin yerleşmiş bir bileşenle `CONCENTRIC` kısıtı varsa: o eksenin yönü `a`;
2. yoksa `PLANE` içeren ilk kısıtın düzlem normali;
3. yoksa `+Z`.
İşaret: `c`'nin kütle merkezi ile karşı bileşenin kütle merkezi farkının `a` üstündeki izdüşümü ≥ 0 olacak şekilde
(sıfırsa `+a`). `mesafe` = `c`'nin sınır kutusu köşegeni. `T_once` = `T_sonra`'ya `mesafe·a` ötelemesi eklenmiş dönüşüm.
Zaman şeridinde `u ∈ [i, i+1]` aralığında ön yüz `T_once → T_sonra` arasında **yalnız ötelemeyi** yumuşatarak
ara değer verir; `u` tam sayıda dönüşüm sunucudan gelenle birebirdir. Şerit geri sürüklenince montaj patlar.

### Girişim
Son adımda (tam montaj) her bileşen çifti için SPEC 09: kesişim hacmi ve boşluk. Yalnız temas eden yüzler
(ör. rulman tabanı cep tabanında) hacim 0'dır (SPEC 09'un kuralı). Hacmi `> 0` olan çiftlerin kesişim katısı
üçgenlenip ikili ağ olarak gönderilir; sahnede kırmızı yarı saydam gösterilir.

### Tek iplik: parametre bağı ve öneri
Montaj tanımı her parçanın kaynağını bilir: tornadaki mil `kaynak = {is: "kademeli_mil", tur: "torna"}`. Mil
parçası işin parametrelerinden (ör. uç boyu `L`) kurulur; torna işi o parçadan SPEC 22 ile çıkarılan profilden
üretilir. Böylece bir parametre değişince **parça → torna işi (yol, G-code, sim, süre) → montaj (çözüm, girişim)**
birlikte yeniden hesaplanır.
- **Bağ:** `{parametre: {is, anahtar, deger, min, max}, parcalar: [...]}` — bu parametre bu parçaları değiştirir.
- **Öneri:** girişim kartında, girişime giren parçaya bağlı her parametre için `v(p)` = o çiftin kesişim hacmi.
  Mevcut değer `p₀`'da `v > 0` ve aralığın bir ucunda `v = 0` ise ikiye bölme (bisection) ile, `p₀`'a en yakın
  `v = 0` sınırı `|Δp| ≤ 1e-3` ile bulunur ve `v = 0` tarafındaki uç önerilir. Her iki uçta da `v > 0` ise ya da
  aralıkta `v` işaret değiştirmiyorsa **öneri yok** (sahte sayı yok, altın kural 5). En fazla 40 değerlendirme.
- Öneriyi uygulamak = o parametreyi ayarlamak; yanıt güncel montajı **ve** etkilenen torna işini
  (`sure_farki` ile) taşır.

### Sunucu durumu
Sunucu tek kullanıcı ve `127.0.0.1`'dedir (SPEC 24). İşlerin güncel parametreleri sunucu belleğinde tutulur;
montajdan yapılan değişiklik `GET /api/is/kademeli_mil`'de de görünür. `POST /api/sifirla` örnekleri başlangıç
değerlerine döndürür.

## Ekranlar

### Torna
- **Sahne:** mil ekseni yatay; ayna ve çeneler solda, punta (varsa) sağda; parça **270° kesit** görünümünde
  (bir çeyrek açık, iç çap ve kanal görünür, `S` tuşu tam / kesit), kesit yüzü işleme göre renkli. Yol çizgisi
  XZ düzleminde, kesit yüzeyinin üstünde. Hayalet takım: uç plakası, burun dairesi, hayali uç noktası.
- **Devir şeridi:** zaman şeridinin altında `n(t)` eğrisi; `n = n_max` olan bölgeler (`G50` sınırı) taralı;
  `G96` / `G97` geçişleri işaretli.
- **Kesit büyüteci:** imleç parçanın üstündeyken o `z`'deki güncel çap, hedef çap ve fark (iki sunucu değerinin farkı).
- **Kanıtlar:** çakma, kalan malzeme, hızlı harekette ham malzemeye çarpma, ayna / punta çarpması, G-code geri okuma,
  devir sınırı (her biri SPEC 21/22 fonksiyonundan, "SPEC NN" etiketiyle).
- **Müfettiş:** işlem parametreleri (`a_p`, `f`, `Vc`, `n_max`, burun yarıçapı, uç numarası); değişince sunucuya gider.

### Montaj
- **Sol:** montaj ağacı (SPEC 07 düğümleri, alt montajlar katlanır), her yaprağın yanında serbestlik çipi
  (6 kare, kilitli olan dolu; etiketler sunucudan); altında BOM (adet, birim ve toplam kütle) ve toplam kütle.
- **Sahne:** parçalar kendi koordinatlarında üçgen ağ olarak gelir, `T` ile yerleştirilir. Seçili parçada serbestlik
  glifleri: öteleme yönleri ok, vida eksenleri halka + eksen çizgisi. Kütle merkezi işareti. Girişim hacimleri kırmızı.
- **Zaman şeridi = montaj sırası:** her adım bir klip ("Rulman → cep"); oynatınca parçalar yaklaşma yönünden gelir,
  geri sürükleyince patlar. Saat "Adım i / N" gösterir.
- **Kanıtlar:** kısıt artığı (`max|r|`), serbestlik (aşağıdaki kural), girişim hacmi, kütle; "SPEC 07/08/09" etiketli.
- **İplik kartı:** girişim varsa çiftin adı, hacmi, kaynağı torna olan parçanın bağlı parametreleri, "Öner" ve
  "Uygula" düğmeleri; uygulanınca torna işinin süre farkı rozeti ve "Tornada göster" bağlantısı (değişen işlem seçili açılır).

### Kabuk
Üst çubukta **Freze / Torna / Montaj** sekmeleri (prototipteki gibi), `1`/`2`/`3` tuşları, adres `#/freze`, `#/torna`,
`#/montaj`. Komut çubuğu yeni komutları tanır: "torna", "montaj", "L 9.5", "paso 2", "patlat", "kesit".

## Örnek işler (uydurma geometri)
- **`kademeli_mil` (torna):** C45, ham Ø50 × 101. Profil (ön uçtan arkaya): Ø24 × `L` (varsayılan `L = 20`),
  omuz, Ø35 × 30, Ø44 × 30, Ø50 kalan. İşlemler: alın, kaba boyuna, ince profil, kanal (SPEC 20).
  Parça SPEC 02/09 fonksiyonlarıyla eş eksenli silindirlerden kurulur; profil parçadan SPEC 22 ile çıkarılır.
- **`yatak_grubu` (montaj):** plaka 120 × 80 × 30 (üst yüz `z = 0`, merkezde Ø40,02 × 10 cep, dört Ø8,02 × 20 kör delik),
  rulman (uydurma halka, iç Ø24,02, dış Ø40, genişlik 10), `kademeli_mil`, dört pim Ø8 × 24.
  Kısıtlar: rulman → cep (`CONCENTRIC` + taban `COINCIDENT`), mil → rulman (`CONCENTRIC` + omuz rulman üst yüzüne
  `COINCIDENT`), pim → delik (`CONCENTRIC` + pim tabanı delik tabanına `COINCIDENT`). Sıra: plaka (sabit), rulman, mil, pimler.
  Mil ucu `z = −L`'ye iner, cep tabanı `z = −10`: `L > 10` ise girişim hacmi `V = π·12²·(L − 10)` mm³.
  Bağ: `{is: "kademeli_mil", anahtar: "L", min: 5, max: 30}` → mil. Öneri `L* = 10` (ε = 1e-3).

## Mimari
```
tezgah/
  torna.py           Torna köprüsü: Toolpath + SPEC 21/22 çıktıları → Is (tur: torna) + ikili noktalar/sim. Saf.
  montaj.py          Montaj köprüsü: ağaç, BOM, sıra, serbestlik, yaklaşma, girişim → Montaj JSON + ikili ağlar. Saf.
  iplik.py           Parametre bağları, yeniden hesaplama zinciri, ikiye bölme önerisi. Saf.
  ornekler_25.py     kademeli_mil ve yatak_grubu örnekleri (parametre → Part → iş / montaj)
  sunucu.py          (SPEC 24 dosyası) yeni uçlar ve parametre deposu eklenir
  arayuz/src/
    torna.ts         çap / yarıçap biçimi, devir şeridi örnekleme, kesit olaylarından kesit (saf, test edilir)
    sira.ts          adım ↔ u eşlemesi, T_once → T_sonra ara değeri, serbestlik çipi (saf, test edilir)
    sahne_torna.ts   dönel kesit ağı, ayna/punta, uç plakası
    sahne_montaj.ts  parça ağları, glifler, girişim, patlatma
tests/tezgah/        test_torna.py, test_montaj.py, test_iplik.py, test_sunucu_25.py
tezgah/arayuz/tests/ torna.test.ts, sira.test.ts, e2e_25.spec.ts
```
Bağımlılık yönü SPEC 24 ile aynı (K9 kuralı): `tezgah` → `cam`, `assy`, `geometry` herkese açık fonksiyonları;
hiçbir paket `tezgah`'ı import etmez. Bu SPEC başka paketlere dosya eklemez veya değiştirmez.

### REST uçları (SPEC 24'e ek)
| Uç | Yanıt |
|---|---|
| `GET /api/is/kademeli_mil` | `Is` (`tur: "torna"`), `/noktalar`, `/sim` SPEC 24 uçlarıyla aynı yol |
| `GET /api/montajlar` | montaj listesi |
| `GET /api/montaj/{ad}` | `Montaj` JSON |
| `GET /api/montaj/{ad}/ag/{parca}` | ikili parça ağı: `float32[nv·3]` köşe (parçanın kendi koordinatı), `uint32[nt·3]` üçgen |
| `GET /api/montaj/{ad}/ag/girisim/{i}` | ikili kesişim ağı (dünya koordinatı) |
| `POST /api/montaj/{ad}/parametre` | `{is, anahtar, deger}` → `{montaj, is, sure_farki}` |
| `GET /api/montaj/{ad}/oneri?is=&anahtar=&cift=` | `{deger, hacim}` ya da `{deger: null, neden}` |
| `POST /api/sifirla` | örnekleri başlangıç değerlerine döndürür |

Çekirdek hataları (`CamError`, `AssyError`, `GeometryError`, `ModelError`) 422 + hata metni (SPEC 24 kuralı).

### Serbestlik kontrolü
Sabit olmayan her bileşen için: serbestlik 0 → `tamam`; yalnız saf dönmeler (`h = 0`) ve parça o eksen etrafında
dönel simetrikse → `tamam` ("simetri serbestliği"); aksi → `uyari` ("eksik kısıt: <etiketler>").
Dönel simetri: parça eksen etrafında 37° döndürülünce `common(parça, döndürülmüş)` hacmi parça hacmine
rel 1e-6 ile eşit (SPEC 09).

## Kabul kriterleri
Konum toleransı `1e-9` mm (aksi yazmadıkça). Örnek geometriler uydurmadır.

**Torna**
- [ ] **K1 Torna köprüsü geri dönüşü:** `torna.is_json()` JSON'a yazılıp okununca hareket uç noktaları, yay merkezleri,
  `feed`, `plane = ZX`, `feed_mode = PER_REV`, `css`, `rpm` SPEC 20 `Toolpath` ile birebir; `tur == "torna"`;
  `tur`suz eski `Is` freze sayılır. (`tests/tezgah/test_torna.py::test_round_trip`)
- [ ] **K2 Canlı bağ (çap programı):** her hareket satırı için `satir_hareket` aralığının son hareketinin `b` noktası,
  SPEC 21 okuyucusunun o satır için verdiği uç noktadan (çap → yarıçap) koordinat başına ≤ 5·10⁻⁴ mm;
  `G71`/`G70`/`G76` satırları kanonik açılımlarının son noktasına eşlenir ve aralık açılımın tamamını kapsar.
  (`test_torna.py::test_line_move_map`)
- [ ] **K3 DRO çap:** her satır için köprünün verdiği DRO `X` değeri `2·x`'tir ve satırdaki `X` sözcüğünün sayısıyla
  ≤ 5·10⁻⁴ mm aynı. (`test_torna.py::test_dro_diameter`)
- [ ] **K4 Devir:** her nokta için `n_k`: `G96`'da `min(1000·Vc/(π·2x), n_max)` (rel 1e-12), `x = 0`'da `n_max`,
  `G97`'de `rpm`; `G96`'da `n_max` yoksa `CamError`. (`test_torna.py::test_spindle_speed`)
- [ ] **K5 Süre:** toplam ve işlem başına süre SPEC 21/22 süre fonksiyonuyla aynı (rel 1e-12); sabit kesme hızında
  alın tornalama Teori'deki kapalı formla rel 1e-9 (`x_c` aralığın içinde, dışında ve tam ucunda üç durum).
  (`test_torna.py::test_times`)
- [ ] **K6 Torna sim olayları:** her `k` için olay listesinden kurulan `(r_dis, r_ic)` dizileri SPEC 22'nin `k`
  sonrası kesitinin hücre merkezlerindeki örneğiyle `float32` olarak birebir; son kesit SPEC 22'nin son durumu.
  (`test_torna.py::test_sim_events_reconstruct`)
- [ ] **K7 Torna kanıtları gerçek:** profilin altına inen uydurma işte `cakma` `hata`; hızlı hareketi ham malzemeden
  geçen işte `hizli_carpma` `hata`; takımı çene bölgesine giren işte `ayna_carpma` `hata`; temiz `kademeli_mil`'de
  hepsi `tamam`; değerler SPEC 21/22 fonksiyonlarının çıktısı. (`test_sunucu_25.py::test_lathe_checks_*`)

**Montaj**
- [ ] **K8 Ağaç, BOM, kütle:** `agac == Node.to_dict()`; `bom` satırları `assy.bom.bom()` ile aynı sırada ve değerde;
  `kutle.toplam == total_mass` ve `kutle.merkez == mass_center` (1e-12); `bilesenler` `flatten` sırasıyla ve `T`'ler
  `solve` sonucuyla birebir. (`tests/tezgah/test_montaj.py::test_tree_bom_mass`)
- [ ] **K9 Montaj sırası:** her adımda `T_sonra` yalnız yerleşmiş bileşenler ve iki ucu yerleşmiş kısıtlardan kurulan
  alt montajın `solve` sonucuyla birebir, `dof_toplam == dof(A_i)`; geçersiz sıralar (ilk adım sabit değil, bilinmeyen,
  yinelenen, eksik yol) → `AssyError` ve uçta 422. (`test_montaj.py::test_sequence*`)
- [ ] **K10 Parça serbestliği:** diğerleri sabitken: sabit 0; kısıtsız 6 (3 öteleme `Tx Ty Tz`, 3 vida `h = 0`);
  `CONCENTRIC` 2 (eksen boyunca öteleme + eksen üstünde `h = 0` vida); `CONCENTRIC` + düzlem 1 (eksen üstünde saf
  dönme: `|yön × a| ≤ 1e-9`, `p` eksene ≤ 1e-9 mm, `h = 0`); 3 düzlem çifti 0. Çok boyutlu durumlarda sıfır uzayı
  analitik uzayla asal açı ≤ 1e-9. Örnekte: rulman 1, mil 1, pim 1. (`test_montaj.py::test_part_freedom*`)
- [ ] **K11 Yaklaşma ve patlatma:** örnekte rulman ve mil `+Z`'den (`a = (0,0,1)`), mesafe sınır kutusu köşegeni;
  `T_once = T_sonra` + `mesafe·a` ötelemesi (1e-12); `CONCENTRIC`'siz bileşende düzlem normali, hiç kısıtı yoksa `+Z`;
  işaret kuralı karşı tarafa yerleştirilmiş bir parçada `−a` verir. (`test_montaj.py::test_approach*`)
- [ ] **K12 Girişim:** `L = 20`'de tek girişim çifti (mil, plaka), hacim `π·144·10` (rel 1e-6), SPEC 09 değeriyle aynı;
  temas eden rulman tabanı ve omuz girişim sayılmaz; `L = 10`'da liste boş. Kesişim ağının kapalı hacmi
  (`mesh_volume`) girişim hacmiyle rel 1e-2. (`test_montaj.py::test_interference*`)
- [ ] **K13 Serbestlik kontrolü:** örnekte rulman ve mil (dönel simetrik) `tamam`; pimin düzlem kısıtı silinince `uyari`
  ("eksik kısıt: Tz"); dönel simetrik olmayan bir blok tek `CONCENTRIC` + düzlemle bağlanınca `uyari`.
  (`test_montaj.py::test_freedom_check*`)
- [ ] **K14 Parça ağları:** her parça için ikili ağın kapalı hacmi `Part.volume` ile rel 1e-2; köşeler parçanın kendi
  koordinatında (ön yüz `T`'yi uygular); bayt uzunlukları başlıktaki `nv`, `nt` ile tutarlı. (`test_montaj.py::test_meshes`)

**Tek iplik**
- [ ] **K15 Parametre bağı:** `POST /api/montaj/yatak_grubu/parametre {is: "kademeli_mil", anahtar: "L", deger: 9.5}`
  sonrası: dönen montajda girişim yok; dönen `is` ile ardından gelen `GET /api/is/kademeli_mil` aynı; `sure_farki`
  iki işin ayrı hesaplanan sürelerinin farkı; geçersiz değer (`L ≤ 0`, aralık dışı) 422 ve çekirdeğin metni;
  `POST /api/sifirla` sonrası `L = 20`. (`test_sunucu_25.py::test_param_link`)
- [ ] **K16 Öneri:** `L = 20`'de öneri `|L_öneri − 10| ≤ 1e-3` ve `L_öneri`'de SPEC 09 hacmi 0; değerlendirme sayısı ≤ 40;
  aralık `[12, 30]` verilince (her yerde girişim) `deger: null` ve neden metni; girişimsiz durumda öneri istenirse
  `deger: null`. (`tests/tezgah/test_iplik.py`)

**Ön yüz**
- [ ] **K17 Saf fonksiyonlar (vitest):** çap / yarıçap biçimi (G-code ile aynı ondalık), devir şeridinde `n_max`
  bölgelerinin bulunması; `sira.ts`'de `u` tam sayıda pozun sunucu `T`'siyle birebir, aradaki pozda dönme kısmının
  `T_sonra`'nınkiyle aynı, ötelemenin `T_once`–`T_sonra` doğrusu üstünde olması; serbestlik çipi eşlemesi; kesit
  olaylarından `k` anındaki kesit (K6 verisiyle). (`tezgah/arayuz/tests/torna.test.ts`, `sira.test.ts`)
- [ ] **K18 Uçtan uca (Playwright, `@slow`):** `2` ile torna açılır, konsolda hata yok; bir G-code satırının üstüne
  gelinince hayalet takımın hayali ucu satırın uç noktasında (ε içinde) ve DRO `X` satırdaki sayı; `S` kesiti açıp
  kapatır. `3` ile montaj açılır; şerit başında bütün bileşenler `T_once`'da, sonunda `T_sonra`'da (`window.__tezgah`
  kancası); girişim kartı görünür; "Öner" + "Uygula" sonrası kart "temiz" olur, torna işinin G-code'u ve süresi
  sunucu yanıtıyla aynı, "Tornada göster" torna ekranını değişen işlem seçili açar. 400 px ve 1440 px'te ekran
  görüntüsü, yatay kaydırma yok. (`tezgah/arayuz/tests/e2e_25.spec.ts`)
- [ ] **K19 Klavye ve erişilebilirlik:** `1`/`2`/`3` sekmeler, `S` kesit, `R` çap/yarıçap, `E` patlat/topla, mevcut
  SPEC 24 tuşları; her etkileşimli öğede görünür odak; glif ve renklerin yanında metin karşılığı (çip etiketi, kart metni). (K18 içinde)
- [ ] **K20 Bağımlılık kuralı:** SPEC 24 K9 testi yeni modülleri de kapsar; `tezgah` dışında dosya değişmez.
  (`tests/tezgah/test_bagimlilik.py`)
- [ ] `pytest` 0 failed, bu SPEC'in testlerinde 0 "uygulanmamış"; `ruff check .` ve `ruff format --check .` temiz

## Test yaklaşımı
- CLAUDE.md "Test bağımsızlığı" aynen: testleri ayrı bir `dogrulayici` oturumu bu SPEC'ten yazar (Python ve TS),
  kodu ayrı bir `yazici` oturumu ayrı commit'te yazar.
- Python testleri `[web]` ve `[cad]` yoksa atlanır (`importorskip`; OCCT gerektirenler `@pytest.mark.occt`);
  ön yüz testleri SPEC 24'teki gibi yalnız yerelde (pre-push). CI'a yeni adım eklenmez.
- Görsel tasarım kabul ölçütü değildir; ölçütler sayılar ve davranıştır.

## Yol haritası yeri
- **Numara:** 25 (`25-tezgah-torna-montaj`).
- **Bağımlılık:** 25 → 24, 20, 21, 22, 07, 08, 09.
- **Dalga:** SPEC metni Dalga 4'te; kod 24 iskeleti, 21, 22 ve 09 `main`'e girince. Torna ekranı (K1–K7) ile montaj
  ekranı (K8–K14) birbirini beklemez; tek iplik (K15–K16) ikisini de bekler.
- `docs/yol-haritasi.md` bu PR'da değişmez; onaydan sonra yol haritası sahibi thread ekler.

## Kapsam dışı
- Montajda **işlenmiş** şekil (talaş simülasyonundan katı): parçalar CAD şekliyle girer.
- Freze işine parametre bağı (plaka ↔ SPEC 24 freze işi): sonraki adım; bu SPEC'te yalnız torna bağı.
- Kısıt ekleme / düzenleme, sürükleyerek serbestlikte hareket ettirme (kinematik), yerleştirme yolunda çarpışma kontrolü.
- Montaj sırasının otomatik bulunması (sıra montaj tanımında verilir).
- Çok eksenli torna (C/Y, mill-turn), arka iş mili, alın kanalı; diş çekmenin senkron gösterimi.
- Montaj STEP içe aktarma ekranı (SPEC 07 `read_step` var; dosya seçici bu SPEC'te yok).
- Çok kullanıcılı sunucu, kalıcı proje dosyası: parametre deposu bellektedir.
- Gerçek şirket parçaları (gizlilik kuralı).
