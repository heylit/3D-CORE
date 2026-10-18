# Yol haritası

**Asıl hedef: 3D CAM (freze ve torna) ve 3D montaj.** Katı modelleme bunlara hizmet eden altyapıdır ve hazır çekirdekle
yapılır: **OpenCascade (OCCT), build123d üzerinden**. B-rep'i sıfırdan yazmıyoruz. Kendi FEM çözücümüz
analiz modülü olarak kalır ve en sona gelir.

Her adımın sonunda çalışan ve DOĞRULANMIŞ bir şey olur. Doğrulamadan sonraki adıma geçilmez.
SPEC dosya adı `specs/NN-ad.md`. Numara bir kimliktir, sıra değildir: **sırayı aşağıdaki dalgalar belirler.**

## Paralel çalışma: dalgalar

Aynı dalgadaki SPEC'ler birbirine bağlı değildir; her biri ayrı thread / ayrı dal / ayrı PR olarak
(bulutta ya da yerelde) **aynı anda** yürür. Bir dalga, önceki dalgadaki bağımlılıkları `main`'e girince başlar.

| Dalga | SPEC'ler (aynı anda) | Neden paralel olabilir |
|---|---|---|
| **0** (tek iş, kısa) | `00-arayuzler`: `geometry/part.py`, `cam/model.py`, `assy/model.py` veri modelleri + testleri; bulut ve yerel için aynı kurulum (bulut başlangıç betiği, `occt` test işareti); hook'ların paralel dallara uyarlanması (`main` hep yeşil, TDD'nin kırmızı test commit'i engellenmeden) | Diğer her şey bu arayüzlere bağlı; önce bunlar sabitlenir |
| **1** | `01-bar`, `02-parca`, `03-cam-2d`, `04-gcode`, `08-kisitlar` | Her biri sadece kendi paketine yazar; CAM ve montaj çözücüsü saf numpy ile, OCCT'siz test edilir |
| **2** | `05-cam-sim`, `06-cam-3d`, `07-montaj-agaci`, `11-tet4`, `14-cam-kurulum`, `15-goruntuleyici`, `16-teknik-resim`, `20-torna-yol`, `23-parca-ek` | 02 (katı parça) ve 03/04 (takım yolu) `main`'de |
| **3** (başladı) | `17-kroki`, `21-torna-gcode`, `22-torna-sim`, `24-tezgah`, `26-tezgah-modelleme`, `03b-kalan-malzeme-cep`, işleme özelliği tanıma (numara bekleniyor), `06b` torik takım + waterline, LinuxCNC rs274 kontrolünün CI'a alınması (SPEC değil, CI işi) | Her biri ayrı pakete ya da ayrı dosyaya yazar; dalga içi sıra: 22 → 21'i, 26 → 17 ve 24'ü bekler (aşağıda) |
| **4** (sıra yok, paralel kollar) | Aşağıdaki "Dalga 4 kolları" tablosu | Kollar birbirinin paketine yazmaz; her kol yalnızca kendi bağımlılığı `main`'e girince başlar |

### Dalga 3: dalga içi sıra
Aynı anda başlayanlar: 17, 21, 24, 03b, özellik tanıma, 06b, LinuxCNC CI. Sonra gelenler:
- `22-torna-sim` → 21 `main`'de (torna G-code'unu simüle eder).
- `26-tezgah-modelleme` → 17 ve 24 `main`'de. `geometry/extrude.py` ve `tezgah/ifade.py` kısmı (26 K1–K5)
  17'nin `sketch/model.py` arayüz PR'ı birleşince 24'ü beklemeden başlayabilir.
- 17 kodundan önce `sketch/model.py` arayüz PR'ı (ayrı, kullanıcı onayıyla).

### Dalga 4 kolları (paralel, öncelik sırası yok)
SPEC'lerin çoğu ayrı thread'lerde yazılıyor; numaralar kesinleştikçe bu tabloya işlenir.

| Kol | İçerik | Başlamak için `main`'de olmalı |
|---|---|---|
| Postprosesörler ve tezgâh profilleri | Fanuc / GRBL dışındaki kontrol üniteleri; tezgâh profili (eksen sınırları, devir / ilerleme sınırı, takım değiştirme) | 04, 14, 21 |
| Özellik tanımaya dayalı otomatik CAM | Tanınan cep / delik / düz yüzden işlem ve takım seçimi | işleme özelliği tanıma SPEC'i (Dalga 3) onaylanıp `main`'e girince; 03, 03b, 14 |
| 4 ve 5 eksen | 3+2 konumlama, tri-dexel simülasyon, kinematik çarpışma, döner eksenli post | 05, 06, 06b, 14 |
| Montaj girişim kontrolü | `09-girisim`: boolean API, girişim ve boşluk; ardından `10-montaj-cam` (fikstürle simülasyon) | 07, 08 (10 için ayrıca 05) |
| FEM ağ ve gerilme analizi | `12-gmsh` → `13-calculix` (13, 12'yi bekler) | 02, 11 |
| Tezgah torna ve montaj ekranı | `25-tezgah-torna-montaj` | 24, 21, 22, 07 (girişim düzeltmesi için 09) |
| Özellik ağacı | `18-ozellik-agaci`: 26'nın doğrusal geçmişi → kararlı yüz referanslı ağaç, revolve / pah / fillet | 17, 26 |
| Adaptif kaba işleme | `19-adaptif-kaba` | 03, 05 |

Not: `09`, `10`, `12`, `13` daha önce Dalga 3'teydi; 2026-10-18'de Dalga 3 CAM, torna ve Tezgah'a ayrıldığı
için Dalga 4 kollarına taşındı (bağımlılıkları değişmedi). `18` ve `19` kullanıcının listesinde adı geçmeyen
mevcut SPEC'lerdir; bağımlılıklarına göre Dalga 4'e kol olarak eklendi.

Bağımlılıklar (→ "şuna ihtiyaç duyar"):
- `03-cam-2d`, `04-gcode` → sadece `cam/model.py` (03 2D profillerle çalışır; parçadan özellik okuma 05/06'da)
- `08-kisitlar` → sadece `assy/model.py` (dönüşüm matrisleri üzerinde saf matematik)
- `05-cam-sim` → 02, 03, 04 · `06-cam-3d` → 02, 03 · `07-montaj-agaci` → 02
- `09-girisim` → 07 · `10-montaj-cam` → 05, 07 · `11-tet4` → 01 · `12-gmsh` → 02, 11 · `13-calculix` → 12
- `14-cam-kurulum` → 03, 04 · `15-goruntuleyici` → 02, 03 · `16-teknik-resim` → 02 · `17-kroki` → `sketch/model.py` arayüz PR'ı (yöntem 08 ile aynı, kod bağımlılığı yok) · `18-ozellik-agaci` → 02, 17, 26 · `19-adaptif-kaba` → 03, 05
- `20-torna-yol` → 03 · `21-torna-gcode` → 04, 20 · `22-torna-sim` → 02, 21 · `23-parca-ek` → 02
- `24-tezgah` → 02, 03, 04, 05, 08 · `25-tezgah-torna-montaj` → 24, 21, 22, 07, 09 · `26-tezgah-modelleme` → 02, 03, 04, 17, 23, 24

## Aşama 0 — FEM iskeleti (hazır olanı bitir)
| # | SPEC | Konu | Bitti sayılır |
|---|------|------|---------------|
| 1 | 01-bar | 1D çubuk + çözücü iskeleti | δ = FL/EA ve tüm benchmark'lar yeşil (testler hazır, sadece kod) |

## Aşama 1 — Katı altyapı (`geometry/`, CAM ve montaj için en az gereken)
| # | SPEC | Konu | Bitti sayılır |
|---|------|------|---------------|
| 2 | 02-parca | STEP/STL içe-dışa aktarma, kodla basit parça (blok, delik, cep, pah), hacim / alan / ağırlık merkezi, basit görüntüleme | Analitik değerle rel 1e-6; STEP geri okununca hacim aynı |

## Aşama 2 — CAM (`cam/`, freze ve torna)
| # | SPEC | Konu | Bitti sayılır |
|---|------|------|---------------|
| 3 | 03-cam-2d | 2.5D takım yolu: yüz alma, kontur, cep (ofset), takım yarıçapı telafisi, paso derinlikleri (girdi: 2D profiller) | Dikdörtgen cep ve dairesel konturda yol geometrisi analitik ofsetle 1e-6 mm |
| 4 | 04-gcode | G-code çıkışı (GRBL / Fanuc post-işlemcisi) + kendi G-code okuyucumuz; delik delme çevrimleri (G81/G83) | Üretilen G-code geri okununca takım yolu birebir aynı |
| 5 | 05-cam-sim | Talaş kaldırma simülasyonu (dexel / voxel), işleme süresi tahmini | Simüle edilen son parça CAD hacmiyle tolerans içinde; çakma (gouge), hızlı harekette çarpma ve takım tutucu / sap çarpışması tespiti; parçadan işleme özelliklerini (düz yüz, cep, delik) okuma |
| 6 | 06-cam-3d | 3D yüzey işleme (küresel uçlu takım, drop-cutter), kaba + ince işleme | Küre / silindir yüzeyde iz yüksekliği (scallop) formülle tutuyor |
| 14 | 14-cam-kurulum | İş sıfırı (WCS), stok, bağlama; freze ve torna takımları için JSON takım kütüphanesi; kesme verisinden devir ve ilerleme: n = 1000·Vc / (π·D), F = n·z·fz | Bilinen Vc, fz, D, z için S ve F birebir; G-code'da WCS (G54) doğru; takım boyu: Fanuc'ta G43 H, GRBL'de prob (G38.2) ile ölçüm + G43.1 dinamik ofset (GRBL'de G43 yok) |
| 19 | 19-adaptif-kaba | Sabit takım temas açılı (trokoidal / adaptif) kaba işleme | Temas açısı her adımda sınır içinde; kalan malzeme simülasyonla doğru |
| 20 | 20-torna-yol | Torna takım yolu, XZ düzleminde 2D (girdi: dönel parçanın yarı kesit profili): alın ve boy tornalama, kaba çevrim (paso derinliği), ince profil, kanal açma, diş çekme; takım burun yarıçapı telafisi | Silindir / koni / yay profilinde paso sayısı ve ofset analitik 1e-6 mm; burun yarıçapı telafisi koni ve yayda formülle tutuyor; diş paso derinlikleri formülle |
| 21 | 21-torna-gcode | Torna post-işlemcisi (Fanuc torna) + okuyucu: çap programlama, G96/G97 sabit kesme hızı, G50 devir sınırı, G71/G70 kaba-ince çevrim, G76 diş çevrimi | Üretilen G-code geri okununca takım yolu birebir aynı; G96'da n = 1000·Vc / (π·D) ve G50 sınırı doğru |
| 22 | 22-torna-sim | Torna talaş simülasyonu (dönel simetri: 2D profil kesişimi) ve katı parçadan dönel profil çıkarma | Son parça hacmi Pappus formülüyle tutuyor; profil CAD profiliyle tolerans içinde; çene / punta çarpması tespit ediliyor |

## Aşama 3 — Montaj (`assy/`)
| # | SPEC | Konu | Bitti sayılır |
|---|------|------|---------------|
| 7 | 07-montaj-agaci | Parça + konum (Location) ağacı, alt montajlar, malzeme listesi (BOM), montaj STEP içe-dışa aktarma | STEP geri okununca parça sayısı ve konumlar aynı; BOM adet ve kütle doğru |
| 8 | 08-kisitlar | Montaj kısıtları (çakışık, eş eksen, mesafe, açı) → konum çözücü (Newton-Raphson / en küçük kareler) | Bilinen kapalı form konumlar 1e-9 mm içinde; serbestlik derecesi sayımı doğru; çelişkili kısıt → hata |
| 9 | 09-girisim | Genel boolean API (`cut` / `fuse` / `common`), girişim / çakışma kontrolü ve boşluk ölçümü | Bilerek çakıştırılan parçalarda kesişim hacmi analitik değeri tutuyor; temiz montajda 0 |
| 10 | 10-montaj-cam | Montajdan parça seçip CAM'e gönderme; bağlama (fikstür) ile birlikte simülasyon | Fikstüre çarpma tespit ediliyor |

## Aşama 4 — Analiz (FEM, `core/` + `mesh/`)
| # | SPEC | Konu | Bitti sayılır |
|---|------|------|---------------|
| 11 | 11-tet4 | 3D tetrahedron eleman | Patch test + konsol kiriş yakınsaması |
| 12 | 12-gmsh | Katı parçayı gmsh ile mesh'le → `core.model.Model` | Delikli plakada Kt ≈ 3 (Kirsch) |
| 13 | 13-calculix | Von Mises + CalculiX çapraz kontrolü | Braket analizi fark < %1 |

## Aşama 5 — Parametrik model ve görüntüleme
| # | SPEC | Konu | Bitti sayılır |
|---|------|------|---------------|
| 23 | 23-parca-ek | 02'den sonraya kalan parça işlemleri: yuvarlatma (fillet), havşa, dişli delik, eğimli / açılı delik | Fillet sonrası hacim ve alan analitik (çeyrek daire kesit) rel 1e-6; havşa ve delik hacmi formülle |
| 15 | 15-goruntuleyici | `viz/` içinde pyvista ile parça, montaj ve takım yolunu 3D gösterme, ekran görüntüsü kaydetme | Bilinen sahnede sınır kutusu / piksel kontrolü; ekransız (off-screen) test çalışıyor |
| 16 | 16-teknik-resim | OCCT gizli çizgi kaldırma ile ön / üst / yan görünüş ve kesit, temel ölçüler, DXF ve SVG çıkışı | Blok + delikte görünüş kenar uzunlukları analitik; DXF geri okununca aynı |
| 17 | 17-kroki | Kısıtlı 2D eskiz (`sketch/`, saf numpy): nokta, çizgi, yay, daire + yatay, dik, paralel, teğet, eş, mesafe, açı, simetri; Gauss–Newton çözücü (08 ile aynı yöntem); öğe başına serbestlik ve yönü, çelişen kısıt kümesi, sürükleme, kapalı döngülerden bölgeler | Kapalı formlu üçgen / dörtgen / kanal 1e-9; DOF ve öğe serbestliği doğru; çelişki kümesi tam çelişen kısıtlar; sürükleme kapalı formda; bölge alanı analitik |
| 18 | 18-ozellik-agaci | Kroki → extrude / revolve / cep / delik / pah; parametre değişince yeniden hesap; yüzlere kararlı referans (topolojik adlandırma sorunu) | Parametre değişince hacim analitik; bağlı özellik doğru yüze kalıyor |
| 24 | 24-tezgah | Tezgah web arayüzü (FastAPI 127.0.0.1 + three.js): freze işi, zaman şeridi, G-code ↔ yol ↔ zaman bağı, kanıt paneli | `specs/24-tezgah.md` K1–K10 |
| 26 | 26-tezgah-modelleme | Tezgah'ta etkileşimli modelleme: eskiz çiz, ölçü ve kısıtla sabitle (17), ekstrüzyon ekle / kes, delik, ifadeli parametreler, geçmiş şeridi; tasarım niyetini (kesim → cep, delik → delme) freze işine gönderme | Ekstrüzyon / kesim hacmi analitik rel 1e-6; parametre değişince hacim analitik; gönderilen işte cep bölgesi eskizdekiyle 1e-9 ve SPEC 24 kontrolleri `tamam` |

Not: 14 ve 20 (`cam/model.py`: torna takımı / uç geometrisi, silindirik stok, XZ hareketleri) ile 17 (yeni `sketch/model.py`: `Plane`, eskiz öğeleri, kısıtlar, `SketchRegion`) ortak arayüz değişikliği gerektirir; kurala göre önce ayrı küçük arayüz PR'ı açılır.

## Gerçek tezgâh doğrulaması (belge, SPEC değil)
`docs/tezgah-dogrulama.md`: üretilen G-code'u tezgâhta ilk kez çalıştırmadan önceki kontrol listesi (simülasyonda gözden geçirme, havada / kuru çalıştırma, Z ofsetini ve takım boyunu doğrulama, düşük ilerleme oranıyla ilk parça, ilk parça ölçümü). Dalga 2'de 04 ve 14 ile birlikte yazılır; testleri yoktur, tezgâhta kullanıcı uygular.

## İhtiyaç olursa (sıraya alınmadı)
- 3+2 ve 5 eksen işleme, makine kinematiği (post-işlemcide döner eksenler)
- C ve Y eksenli torna-freze (mill-turn)
- Montajda hareket ve kinematik
- Modal ve ısıl analiz
- FEM'i özellik ağacı parametreleriyle döngüye sokan optimizasyon

## Bağımlılık notu
`cad` (build123d) zaten `pyproject.toml`'da isteğe bağlı. CAM için ofset kütüphanesi (ör. pyclipper / shapely)
veya simülasyon için ek paket gerekirse ilgili SPEC'te önerilir ve kullanıcı onayı alınır.
`pyvista` (SPEC 15, görüntüleyici) kullanıcı tarafından onaylandı (2026-10-18); `pyproject.toml`'a eklenmesi ayrı küçük PR olarak yapılır.
