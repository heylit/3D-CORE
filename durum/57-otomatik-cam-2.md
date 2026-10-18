# DURUM — SPEC 57 otomatik-cam-2

Dal: `claude/project-thread-ysr96h` · Oturum: bulut

## Sıradaki adım
Kod yazıldı, 125/125 SPEC 57 testi yeşil; PR #132 CI'da. Açık iş: 3+2 döndürme komutunun son işlemcide yazılması.

## Test durumu
| Tarih | Geçen | Kalan | Not |
|---|---|---|---|
| 2026-10-18 | 0 | – | iskelet, testler henüz yok |
X

## Son oturum
**2026-10-18**
- SPEC metni onaylı (kullanıcı 16:06, "Dalga 7 taslakları 57, … onaylıyorum") `specs/57-otomatik-cam-2.md`'ye kopyalandı.
- `cam/plan2/` altında `NotImplementedError` gövdeli arayüz: `stok`, `erisim`, `ortu`, `sira`, `plan`.
- K9 bağlama gövdeleri SPEC 10 (#79) birleşince; o zamana kadar ilgili test xfail kalabilir (koordinatör notu).

## Arayüz netleştirmeleri (test yazarının soruları, 2026-10-18 16:35; SPEC metni değişmez)
1. **Yönelim:** `order_ops` yönelimi `PlannedOp.setup`'tan okur; `AutoPlan.plans[k]` bağlama `k`'nın `MillPlan`'ıdır ve
   içindeki `PlannedOp.setup`, `AutoPlan.frames[k]` içindeki yönelim indeksidir (K7d: iki yönelim = setup 0 ve 1).
   `N_rot` = ardışık iki işlemde `setup` farklı olan geçiş sayısı.
2. **İşlem türleri ve öncelik** (`precedence`): `kind` dizeleri SPEC 29'dakiler (`yuz_alma`, `acik_bolge`, `cep`,
   `cep_kalan`, `delik`, `lamba`) artı `punta`, `kilavuz`, `havsa`. Aynı `setup` içinde: `yuz_alma` → diğer her işlem;
   `{acik_bolge, cep, cep_kalan}` → `{punta, delik, kilavuz, havsa, lamba}`; aynı özellik adresinde `cep` → `cep_kalan`.
   Delik adresleri `holes[i,j,…]`; indeks kümeleri kesişen işlemler aynı delik sayılır: `punta` → `delik` →
   `{kilavuz, havsa, lamba}`. Farklı `setup`'lar arasında öncelik yoktur. Öncül sözlüğü: indeks → öncüllerin kümesi
   (öncülü olmayan indeks boş kümeyle bulunur).
3. **`min_cover` dönüşü:** yalnız `tuple[key, ...]` (imza esastır). Örtülemeyen elemanlar dönmez; çağıran
   `universe − ⋃ cover[k]` ile bulur. Anahtar sırası: boyut, sonra `cover` sözlüğündeki ekleme sırası (ilk örten alt küme).
   `cover` dışındaki eleman taşıyan küme (universe'te olmayan) görmezden gelinir.
4. **`select_stock` / `load_catalog`:** `bbox = (b_min, b_max)`, her biri 3 elemanlı dizi (2×3 dizi de kabul).
   Katalog JSON'u `StockSize` alanlarıyla nesne listesidir: `[{"kind": "blok", "a": 100, "b": 60, "c": 40, "name": "…"},
   {"kind": "cubuk", "a": 55, "max_len": 1000}]`; bilinmeyen anahtar, eksik `kind`/`a` ya da pozitif olmayan ölçü →
   `CamError`. Dönen 4×4 matris parçanın dünya koordinatından stok koordinatına dönüşümdür.
5. **Çene engeli:** `fixtures` = `Stock` kutuları dizisi, **bağlama yerel çerçevesinde**: `z = 0` parçanın o bağlamadaki
   en alt noktası (bağlanan yüz), `z` yukarı. Aynı fikstür her bağlamaya uygulanır. Çene üstü `z_c = max(f.zmax)`;
   `fixtures` boşsa çene engeli yoktur. Yukarı (`−c`) dışındaki bir yönden (yan ya da eğik) erişilen özellik, yerel
   tabanı (en düşük noktası) `z_c + clearance` altındaysa o bağlamada `cene_engeli` sayılır.
6. **Kavrama payı bağlaması:** stok parçanın altında fazla bırakıyorsa (`stock.zmin < parça zmin`) ilk bağlama bu
   paydan tutar (`c = −Z`); en az bağlama araması bu bağlamayı içeren alt kümelerle yapılır, alt yüz alma sonraki
   bağlamadadır (§1 "kavrama payı … son bağlamada alınır"; K9).

## Uygulama notları (kod oturumu)
- **Erişim:** parça sınır kutusu − parça = bağlı bölgeler (Part.cut + katılar). Bölge `d`'den erişilebilir ⇔ yerel ayak
  izinin üstündeki sütunda parça yok ve bölge tek başına bir kutudan çıkarıldığında SPEC 27 `recognize` tanıyor.
  Delikler `Part.holes` kayıtlarından (aday = −eksen); yalnız kayıtlı delikten oluşan bölge ayrıca sayılmaz. Stok
  fazlası ana yönlerde yüz alma. Kutu katısı için `cam/plan2/erisim.py` build123d'yi geç içe aktarır (Part arayüzünde
  kutu kurucu yok); OCCT gerektiren testler zaten `occt`.
- **Özellik kimliği:** bölge indeksi, delik kaydı indeksi, stok yüzü; aynı özellik iki yönden görünse de tek eleman.
- **Katalog (freze):** `plan_auto` yalnız blok satırlarını kullanır; çubuk satırları `plan_auto_turn` içindir.
- **Doğrulama (§7):** çarpışma ve hacimler 43 tri-dexel ile, bağlamalar boyunca taşınan stokla (Karar 3). Çakma
  yönelim başına 05 dexel ile (29 `verify_mill`, yerel ham stok): tri-dexel'in yan ışınları parça ağının kiriş
  hatasını yay duvarlarında çakma sayıyor (K9'da 0.015 mm, 1.8 mm³), düşey ışın saymıyor.
- **G-code:** bağlama başına bir program; çok yönelimli bağlamada her yönelim ayrı bölüm ve iş düzlemi notu.
  Döndürme komutu (CYCLE800 / PLANE SPATIAL) yazıcıda yok (`write` frame'i reddediyor): son işlemci işi, açık iş.
- **Fikstür ve `check_setup`:** fikstür kutuları yalnız çene kuralında kullanılır; yönelim planlarına verilmez
  (bağlama çerçevesindeki kutu yan yönelimde tabla gibi davranıp her hızlı hareketi engelliyor); K9 fikstür testi
  (çeneler parçadan uzakta, z_c = 5) yönelim setup'larında `check_setup` temiz.
- **Torna:** tek bağlama ⇔ profil `stock.zmin + grip + clearance`'tan önde; değilse kavrama silindiri (boy ≥ grip,
  en büyük çap) seçilir, bağlama 1 önden o silindirin sonuna, bağlama 2 `flip_profile` (z_ref = zmin + zmax) ile kalan
  uç; iç profil bağlama 1'de. B ekseni açı sınırı (yatay tabla) şimdilik uygulanmıyor.

## Açık sorular
_(yok)_
