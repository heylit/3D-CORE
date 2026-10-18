# SPEC 26 — Tezgah'ta etkileşimli modelleme: eskiz → ekstrüzyon → işleme

> **Durum: ONAYLANDI** (kullanıcı, 2026-10-18 10:38 UTC: "SPEC 09, 12, 13, 17, 22, 25, 26, ... metinlerini onaylıyorum").
> Karar (kullanıcı, 2026-10-18 09:28 UTC, "Eskiz ve modelleme ekle"): kısıtlı 2D eskiz çözücüsü (SPEC 17) ve
> Tezgah'ta eskiz → ekstrüzyon modelleme için SPEC'ler yazılır, Dalga 3'e girer. Bu SPEC Tezgah tarafıdır.
> Tezgah kabuğu, köprü kuralları ve ön yüz araç zinciri SPEC 24'ten gelir; burada tekrar edilmez.
> Prototip yönü: https://claude.ai/artifact/2YA8RRJYuFSpRJyEFMEX8u (konsept; kabul ölçütü değildir).

## Amaç
Tezgah'ta fareyle eskiz çizip ölçü ve kısıtla sabitlemek, eskizi ekstrüzyonla gövdeye çevirmek ya da parçadan
kesmek, delik açmak, ölçüleri parametreye bağlayıp modeli yeniden kurmak ve bitmiş parçayı **tasarım niyetiyle
birlikte** freze akışına (SPEC 24) göndermek. Bu adım bitince örnek bir flanş plakası tarayıcıda sıfırdan
modellenir, tek tuşla işleme ekranına geçer ve oradan G-code çıkar.

## Temel ilke (SPEC 24'ten)
**Arayüz mühendislik sayısı hesaplamaz.** Ön yüz imlecin eskiz düzlemindeki konumunu, önerilen kısıtı ve
kullanıcının yazdığı ölçüyü gönderir. Eskiz çözümü, serbestlik, çelişki, bölgeler (SPEC 17), katı işlemler,
hacim, alan (SPEC 02, bu SPEC'in `geometry/extrude.py`'si) ve CAM işlemleri (SPEC 03, 04) Python'dan gelir.
Ön yüzde yalnızca görsel önizleme yapılır (ör. ekstrüzyon tutamacı sürüklenirken bölge ağının yarı saydam
prizması); bırakınca sunucu hesaplar ve kanıt panelinde gerçek hacim görünür.

## Kullanıcı deneyimi: alışılmışın dışında olanlar
Görsel tasarım kabul ölçütü değildir; aşağıdaki **davranışlar** ölçüttür (K10, K11).
1. **Serbestlik haritası.** Her öğe kalan serbestliğine göre renklenir (tam tanımlı / eksik / fazla tanımlı),
   tek serbestlikli noktada hareket edebileceği yönü gösteren bir ok çıkar, köşede toplam DOF sayacı durur.
   Hepsi SPEC 17'nin `freedom`, `directions`, `redundant` çıktısıdır. Kullanıcı "neyi daha ölçmem lazım"
   sorusunun cevabını eskize bakarak görür.
2. **Çelişkinin açıklaması.** Çelişen bir ölçü eklenince "çözülemedi" demek yerine SPEC 17'nin çelişki kümesi
   vurgulanır ve yan kartta listelenir; birine tıklayınca o kısıt kaldırılıp eskiz yeniden çözülür. Yeni ölçü
   ancak kullanıcı seçince eklenir; eskiz hiçbir zaman sessizce bozulmaz.
3. **Sürükleyerek keşif.** Eksik tanımlı nokta sürüklenince eskiz kısıtları bozmadan izler (SPEC 17 `drag`);
   kullanıcı serbestliği eliyle hisseder. Sürükleme istekleri çerçeve başına en fazla bir tane gider.
4. **Ölçü bir ifadedir.** Ölçü kutusuna `40`, `=genislik/2` ya da `=2*r+3` yazılabilir. Parametre tablosundaki
   bir değer değişince model geçmişi baştan kurulur ve kanıt panelinde hacim farkı görünür.
5. **Geçmiş şeridi.** SPEC 24'ün zaman şeridi bileşeni burada model geçmişini gösterir: her adım bir dilimdir,
   şerit sürüklenince model o adımdaki haline döner, bir dilime çift tıklayınca adım düzenlenir. Geri al / yinele
   şeritte konum değiştirmektir.
6. **Yüze tıkla, çiz.** 3D'de düzlemsel bir yüze tıklanınca kamera o düzleme dik döner, yüzün kenarları eskize
   sabit referans çizgileri olarak gelir (ölçü onlara bağlanabilir).
7. **Tasarım niyeti işlemeye taşınır.** Modelin geçmişi "şu bölge, şu derinlikte kesildi" bilgisini zaten taşır.
   "Tezgah'a gönder" bunu özellik tanıma yapmadan CAM işlemine çevirir: kör kesim → cep, boydan boya iç bölge →
   iç kontur, delik adımı → delme çevrimi. Kullanıcı modelden çıkıp G-code'a gelene kadar hiçbir şeyi yeniden çizmez.

## Teori ve veri modeli

### Model geçmişi (`tezgah/modelleme.py`)
Doğrusal bir adım listesi; her değişiklikte **baştan** yeniden kurulur (saf, deterministik).
```
Model = { sema: 1, ad, parametreler: {ad: ifade}, adimlar: [Adim] }
Adim  = { kimlik, tur: "eskiz",      duzlem: Duzlem, eskiz: Sketch.to_dict(), olculer: {kisit_sirasi: ifade} }
      | { kimlik, tur: "ekstruzyon", eskiz: kimlik, bolgeler: [i] | "hepsi", mesafe: ifade,
          yon: "ileri" | "geri" | "simetrik", islem: "yeni" | "ekle" | "kes", bitis: "mesafe" | "boydan_boya" }
      | { kimlik, tur: "delik",      eskiz: kimlik, noktalar: [nokta kimliği], cesit: "duz" | "havsa" | "lamba" | "dis",
          d: ifade, derinlik: ifade | null, ... (çeşide göre SPEC 02/23 parametreleri) }
Duzlem = { tur: "XY" | "XZ" | "YZ", ofset: ifade } | { tur: "yuz", adim: kimlik, yuz: index, plane: Plane }
```
`insa(model, k=None) -> (Part | None, Rapor)`: parametreleri değerlendirir, her eskizin ölçülerine yazar,
SPEC 17 ile çözer, bölgeleri çıkarır ve katı işlemleri sırayla uygular; `k` verilirse ilk `k` adımda durur.
`Rapor` adım başına eskiz sonucu (DOF, çelişki), bölge alanları ve `Kontrol` listesi (SPEC 24 biçimi) taşır.

**Yüz düzlemi sınırı:** yüze bağlı eskizin düzlemi oluşturulduğu anda sayısal olarak saklanır (`plane`).
Yeniden kurulumda yüz kimliğiyle yeniden aranmaz (kararlı yüz referansı = topolojik adlandırma, SPEC 18'in
konusu). Bunun yerine her kurulumda saklanan düzlemin, önceki adımın parçasında aynı normalli (1e-9) ve
düzlem uzaklığı ≤ 1e-6 mm olan bir düzlemsel yüzle hâlâ çakıştığı denetlenir; çakışmıyorsa adım çalışır ama
`Kontrol(durum="uyari", kimlik="eskiz_duzlemi_kopuk")` döner. Sessiz kayma yok.

### İfadeler (`tezgah/ifade.py`)
Güvenli, küçük bir dil; Python `eval` kullanılmaz, `ast` ağacı beyaz listeyle yürünür:
sayılar, `+ − * / **`, parantez, tekli eksi, parametre adları, `pi`, `sqrt`, `sin`, `cos`, `tan` (derece),
`abs`, `min`, `max`. Başka her düğüm (öznitelik, indeks, lambda, karşılaştırma, atama, başka çağrı)
→ `IfadeError`. Bilinmeyen ad, sıfıra bölme, sonsuz / nan sonuç, parametreler arası döngü (`a = b`, `b = a`)
→ `IfadeError` (adlarla). Değerlendirme sırası parametre bağımlılık grafiğinin topolojik sırasıdır.

### Katı işlemler (`geometry/extrude.py`)
Bölgeler SPEC 17'nin `SketchRegion`'ıdır (uv, yaylar tam yay olarak). Düzlem `sketch.model.Plane`:
dünya noktası `P = origin + u·xdir + v·ydir`. Yay ve daireler OCCT'ye gerçek daire kenarı olarak verilir
(çokgen yaklaşımı yok), bu yüzden hacimler kapalı formla tutar.
- Ekstrüzyon hacmi `V = A · |mesafe|` (A: SPEC 17 `area`); simetrikte gövde düzlemin iki yanında `mesafe/2`.
- Boydan boya kesim: kesici gövde düzlemden `+PAY` yukarıda başlar, `−normal` yönünde parça sınır kutusu
  köşegeni + `PAY` kadar uzanır (SPEC 02'deki `PAY` ile aynı).
- Yüz düzlemi: `origin` = yüzün ağırlık merkezi (`PlanarFace.origin`), `normal` = dışa bakan normal,
  `xdir` = dünya X'in düzleme izdüşümü (normlu); `|izdüşüm| < 1e-6` ise dünya Y'ninki.

## Mimari ve dosyalar
```
geometry/extrude.py        Bölge + düzlem → OCCT yüz; extrude / extrude_add / extrude_cut; face_plane / face_outline
tezgah/ifade.py            İfade değerlendirici (saf)
tezgah/modelleme.py        Model geçmişi, insa(), Kontroller (saf, FastAPI'siz test edilir)
tezgah/model_kopru.py      Model / SolveResult / Part ağı → JSON + ikili dizi; "Tezgah'a gönder" → SPEC 24 Is
tezgah/sunucu.py           (SPEC 24 dosyası) yeni /api/model uçları eklenir
tezgah/arayuz/src/eskiz.ts       İmleç → düzlem uv, yakalama önerileri (saf, test edilir)
tezgah/arayuz/src/modelleme.ts   Eskiz katmanı, serbestlik haritası, çelişki kartı, ekstrüzyon tutamacı
tests/geometry/test_extrude.py   (@pytest.mark.occt)
tests/tezgah/test_ifade.py, test_modelleme.py, test_model_kopru.py, test_model_sunucu.py
tezgah/arayuz/tests/eskiz.test.ts, model.e2e.spec.ts
durum/26-tezgah-modelleme.md
```
- `geometry/extrude.py` → `geometry.part`, `sketch.model` (yalnızca arayüz). `sketch/` `geometry`'yi import etmez.
- `tezgah` → `sketch`, `geometry`, `cam` (model.py ve herkese açık fonksiyonlar; SPEC 24 K9 kuralı).
- Dokunulmayacak: `sketch/` (SPEC 17), `*/model.py` arayüzleri, `geometry/part.py`, `cam/`, ortak dosyalar.
  `geometry.part.Part` arayüzü değişmez; ekstrüzyon yeni `Part` döndüren bir fonksiyondur.

## Arayüz

### `geometry/extrude.py`
- `extrude(regions, plane, distance, symmetric=False, name="govde") -> Part` — `distance` işaretli (normal yönünde +)
- `extrude_add(part, regions, plane, distance, symmetric=False) -> Part` — birleşim tek katı olmalı;
  yeni gövde parçaya değmiyorsa → `GeometryError` ("ayrık katı")
- `extrude_cut(part, regions, plane, depth: float | None) -> Part` — `None` = boydan boya, `−normal` yönünde;
  hiç malzeme kaldırmıyorsa (ΔV ≤ 1e-9 mm³) → `GeometryError`
- `face_plane(part, index) -> Plane` — düzlemsel olmayan yüz / bilinmeyen index → `GeometryError`
- `face_outline(part, index) -> list[tuple[Seg, ...]]` — yüzün kenar döngüleri düzlemin uv'sinde
  (`SegLine` / `SegArc`; tam daire tek `SegArc`); doğru ve daire dışı kenar → `GeometryError` (sessiz yaklaşım yok)
- Ortak hatalar: boş bölge listesi, `distance = 0`, sonsuz değer → `GeometryError`. Girdi parça değişmez.
- `Part.holes` kayıtları ekstrüzyon ve kesimden geçer (SPEC 23 kayıt zinciri gibi); kesim delik kaydı üretmez.

### Delik adımı
Mevcut fonksiyonlar çağrılır, kayıtlar (`Part.holes`) onlardan gelir: normali +Z olan düzlemde nokta (x, y)
için `hole`, `countersink_hole`, `counterbore_hole`, `tapped_hole`; başka normalde yalnızca `cesit = "duz"`
ile `inclined_hole(p, −normal, d, depth)`. Başka normalde havşa / lamba / diş → `IfadeError` değil
`GeometryError` ("bu yüzde yalnız düz delik"), arayüz bunu müfettişte gösterir.

### `tezgah/modelleme.py`
- `insa(model: dict, k: int | None = None) -> tuple[Part | None, Rapor]`
- `Rapor`: `adimlar: list[AdimRaporu]` (eskiz: `dof`, `freedom`, çelişki kümesi; ekstrüzyon: alan, ΔV),
  `kontroller: list[Kontrol]`
- Bir adım başarısızsa (çelişki, bölge hatası, `GeometryError`) kurulum o adımda durur; hata adım kimliği ve
  çekirdeğin hata metniyle `Rapor`'a yazılır, önceki adımların parçası döner. Sessiz atlama yok.

### REST uçları (SPEC 24 sunucusuna eklenir)
| Uç | Yanıt |
|---|---|
| `POST /api/model/eskiz/coz` | `{eskiz}` → `SolveResult` JSON (konumlar, `dof`, `freedom`, `directions`, `redundant`, `sides`) |
| `POST /api/model/eskiz/surukle` | `{eskiz, nokta, hedef}` → `SolveResult` JSON |
| `GET /api/model` · `PUT /api/model` | `Model` JSON; `PUT` sonrası `Rapor` |
| `GET /api/model/ag?k=` | `k`. adımdaki parçanın üçgen ağı, ikili (`float32` köşe, `int32` üçgen, `int32` yüz index) |
| `GET /api/model/yuz/{index}` | `{plane, outline}` (`face_plane`, `face_outline`) |
| `POST /api/model/tezgaha-gonder` | SPEC 24 `Is` JSON |

Çelişki **422** ve gövdede `{hata, kisitlar: [sıra]}`; diğer çekirdek hataları 422 ve hata metni (SPEC 24 kuralı).

### "Tezgah'a gönder" (`tezgah/model_kopru.py`)
- Stok: parçanın sınır kutusu + pay (XY'de 2 mm, üstte 1 mm; altta 0), `cam.model.Stock`.
- İşlemler sırayla: yüz alma (SPEC 03 `face`); her `islem = "kes"` + `bitis = "mesafe"` adımı, normali +Z ise
  bölgesi XY'ye taşınmış bir **cep** (SPEC 03 `pocket`, derinlik = adımın mesafesi); boydan boya kesimin iç
  bölgeleri **iç kontur**; parçanın en alt kesitinin (`section_z`) dış sınırı **dış kontur**; düşey
  `Part.holes` kayıtları **delme** (SPEC 04 G81 / G83, derinliğe göre). Takımlar örnek iş takım listesinden.
- +Z dışı yüzlerden gelen kesim ve delikler bu SPEC'te işlenmez; atlandıkları `Kontrol(durum="uyari")` ile
  listelenir (3+2 eksen kapsam dışı).

## Yeni bağımlılık
Yok. FastAPI, uvicorn, three.js ve Node araç zinciri SPEC 24'te onaylandı.

## Kabul kriterleri
Hacim ve alan `rel 1e-6` (SPEC 02 ile aynı), konum `1e-9` mm, aksi yazmadıkça.
- [ ] **K1 Ekstrüzyon:** 40×30 dikdörtgen `d = 10` → 12000 mm³; dikdörtgen + r = 5 delik → `(1200 − 25π)·10`;
  kanal (SPEC 17 K6) → `(2ra + πr²)·d`; normali `(0, 1, 1)/√2` düzlemde hacim aynı, sınır kutusu analitik;
  `symmetric` gövdeyi düzleme göre ortalar; `distance < 0` ters yöne çıkar; hata durumları — `tests/geometry/test_extrude.py`
- [ ] **K2 Ekle / kes:** 100×60×20 blok üst yüzünden 40×30 bölge 8 mm kesim → `V − 9600`; r = 5 daire boydan boya
  → `V − 25π·20`; üst yüze boss ekleme → `V + A·h`; ayrık ekleme ve malzemesiz kesim → `GeometryError`;
  girdi parça değişmez; `Part.holes` kayıtları korunur; sonuç STEP'e yazılıp okununca hacim aynı
- [ ] **K3 Yüz düzlemi ve kenarlar:** bloğun üst yüzünde `face_plane` normali +Z, origin ağırlık merkezi;
  `face_outline` dikdörtgen döngü (uv, 1e-9) ve delikli yüzde daire; kenarlardan kurulan eskiz ekstrüde edilince
  alan yüz alanına eşit; silindirik yüze `face_plane` → `GeometryError`
- [ ] **K4 Delik adımı:** üst yüzdeki eskiz noktalarına düz / havşa / lamba / dişli delik → `Part.holes` kayıtları ve
  hacim, aynı fonksiyonların doğrudan çağrısıyla birebir; yan yüzde düz delik `inclined_hole` kaydıyla aynı;
  yan yüzde havşa → `GeometryError`
- [ ] **K5 İfade:** tablo testi (öncelik, tekli eksi, `**`, derece trigonometri, `min` / `max`); yasak düğümler
  (`__import__`, öznitelik, lambda, karşılaştırma, liste) → `IfadeError`; bilinmeyen ad, sıfıra bölme, döngü
  → `IfadeError` ve mesajda adlar — `tests/tezgah/test_ifade.py`
- [ ] **K6 Yeniden kurulum:** `genislik` 40 → 50 değişince hacim analitik değere iner; `insa(model, k)` ilk `k`
  adımın parçası; aynı model iki kez kurulunca hacim ve yüz sayısı aynı; yüze bağlı eskizin yüzü parametreyle
  kayınca `eskiz_duzlemi_kopuk` uyarısı; ortadaki adım hata verince önceki adımın parçası ve adım kimlikli hata
  — `test_modelleme.py`
- [ ] **K7 Eskiz uçları:** `/eskiz/coz` ve `/eskiz/surukle` yanıtları `sketch.solver.solve` / `drag` ile birebir
  (JSON float kayıpsız); çelişkide 422 ve `kisitlar` SPEC 17 çelişki kümesi; sabit noktayı sürüklemek 422
  — `test_model_sunucu.py`
- [ ] **K8 Tasarım niyeti → CAM:** örnek flanş modeli (dış dikdörtgen, ortada 8 mm kör cep, 4 boydan boya delik)
  "Tezgah'a gönder" ile `Is` olur: stok sınır kutusu + pay; işlemler yüz alma, cep (bölge eskizdekiyle 1e-9,
  derinlik 8), dış kontur, 4 delme; SPEC 24 K2 (G-code ↔ okuyucu) ve K5 (kontroller hepsi `tamam`) bu iş için de
  geçer; yan yüz kesimi `uyari` olarak listelenir — `test_model_kopru.py`
- [ ] **K9 Kanıtlar:** her ekstrüzyon adımı için `Kontrol`: "yeni" işlemde geometri hacmi = `area · |d|`
  (rel 1e-6, `tamam`), eskiz DOF (0 → `tamam`, > 0 → `uyari`), STEP gidiş-dönüş hacmi; her kontrolün `spec`
  alanı gerçek bir teste işaret eder ("SPEC 17", "SPEC 26")
- [ ] **K10 Ön yüz saf fonksiyonları (vitest):** imleç ışını ile düzlem kesişimi → uv (eğik düzlem dahil, ışın
  düzleme paralel → `null`); yakalama önerileri: yatay / dikey (açı eşiği), uç noktaya çakışık (piksel eşiği),
  öneri yoksa boş — `tezgah/arayuz/tests/eskiz.test.ts`
- [ ] **K11 Uçtan uca (Playwright, `@slow`):** XY'de dikdörtgen çizilir, DOF sayacı sunucu yanıtıyla aynı ve ölçüler
  eklendikçe 0'a iner, tam tanımlı öğeler renk değiştirir; çelişen ölçü eklenince kart SPEC 17 çelişki kümesini
  listeler, biri kaldırılınca DOF tutarlı; eksik tanımlı nokta sürüklenince `window.__tezgah` ile okunan konum
  `/surukle` yanıtıyla aynı; ekstrüzyon 10 → kanıt panelinde hacim; parametre değişince hacim güncellenir ve
  geçmiş şeridi `k`. adıma sürüklenince ağ `GET /ag?k=` ile aynı; "Tezgah'a gönder" freze ekranını cep işlemiyle
  açar; konsolda hata yok; 400 px ve 1440 px'te yatay kaydırma yok — `tezgah/arayuz/tests/model.e2e.spec.ts`
- [ ] **K12 Klavye:** `L` çizgi, `C` daire, `A` yay, `D` ölçü, `E` ekstrüzyon, `H` delik, `Esc` aracı bırak,
  `Ctrl Z` / `Ctrl Shift Z` geri al / yinele (geçmiş şeridinde konum), `Ctrl K` komut çubuğu; her etkileşimli
  öğenin görünür odak durumu var (K11 içinde)
- [ ] **K13 Bağımlılık kuralı:** `sketch` `geometry`'yi, hiçbir paket `tezgah`'ı import etmez; `geometry/extrude.py`
  `sketch`'ten yalnızca `sketch.model`'i import eder (SPEC 24 `test_bagimlilik.py` genişletilir)
- [ ] Tüm testler yeşil: `pytest` 0 failed, bu SPEC'te 0 "uygulanmamış"; `ruff check .` ve `ruff format --check .`
  temiz; SPEC 02, 17, 23, 24 testleri değişmeden geçiyor

## Test yaklaşımı
CLAUDE.md "Test bağımsızlığı" aynen geçerli. Python testleri CI'da; vitest ve Playwright SPEC 24 kararıyla
yalnızca yerelde pre-push'ta. OCCT gerektiren testler `@pytest.mark.occt`.

## Yol haritası yeri
- **Numara:** 26 (`26-tezgah-modelleme`). 25 Tezgah torna / montaj önerisine ayrıldı.
- **Bağımlılık:** 26 → 02, 03, 04, 17, 23, 24.
- **Dalga:** 3, dalganın ikinci yarısı: 17 ve 24 `main`'e girince başlar. `geometry/extrude.py` (K1–K4) ve
  `tezgah/ifade.py` (K5) 17'nin arayüz PR'ı birleşince 24'ü beklemeden başlayabilir.
- **Devamı:** SPEC 18 (özellik ağacı) bu SPEC'in doğrusal geçmişini kararlı yüz referanslı, revolve / pah /
  fillet içeren bir özellik ağacına çevirir.

## Ek A — Uçlar ekran kaydında (A3)
> Karar (kullanıcı, 2026-10-18 11:36; 11:14 kuralı "beni bekleyen bir şey varsa 2 dk'dan fazla geçerse öneriyi
> kabul et" ile önerilen seçenek): SPEC 26 uçları A3 ekran kaydına (`specs/24a-ekran-kaydi.md`) uyar.

- Uçlar `tezgah/ekranlar/model.py` içindeki `EKRAN = Ekran(ad="model", baslik="Model", tus="7", bolum="model", …)`
  router'ındadır; kabuk `/api/ekran/model` önekiyle bağlar. `tezgah/sunucu.py` değişmez.
- Eşleme birebir: `GET`/`PUT /api/ekran/model/` (Model; `PUT` → `{sema, rapor}`), `POST /api/ekran/model/eskiz/coz`,
  `POST /api/ekran/model/eskiz/surukle`, `GET /api/ekran/model/ag?k=`, `GET /api/ekran/model/yuz/{index}`,
  `POST /api/ekran/model/tezgaha-gonder`. Gövdeler ve 422 kuralı yukarıdaki tablodaki gibidir; ekran hazır
  değilse 503 (A3).
- "model" bölümünün sahibi bu ekrandır: `disa_aktar()` Model JSON'u, `ice_aktar()` atomik yükleme (A3 K5).
- Ön yüz `tezgah/arayuz/src/ekranlar/model.ts` (A3 `EkranModulu`); "Mimari ve dosyalar"daki `modelleme.ts`
  bunun yerine geçer. Saf fonksiyonlar `src/eskiz.ts`'te kalır (K10).

## Kapsam dışı
- Revolve, sweep, loft, kabuk, pah / fillet adımı, desen ve ayna (SPEC 18 ve sonrası)
- Kararlı yüz / kenar referansı (topolojik adlandırma, SPEC 18); yüze bağlı eskiz sayısal düzlemde kalır
- Montaj ekranında modelleme, parçalar arası referans (SPEC 25 önerisi)
- +Z dışı yüzlerden işleme (3+2 eksen), özellik tanıma ile işleme (ayrı gelecek SPEC)
- Teknik resim ekranı (SPEC 16 çıktısı Tezgah'ta gösterilmez)
- Çok kullanıcılı düzenleme, dosya yönetimi ekranı: model tek JSON dosyasıdır, sunucu yalnızca `127.0.0.1`'de
- Gerçek şirket parçaları (gizlilik kuralı): örnek model uydurma geometridir
