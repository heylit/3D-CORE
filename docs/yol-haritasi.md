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
| **3** (başladı) | `17-kroki`, `21-torna-gcode`, `22-torna-sim`, `24-tezgah`, `26-tezgah-modelleme`, `03b-cep-kalan-malzeme`, `06b-cam-3d-ek`, `27-ozellik-tanima`, `28-torna-profili`, LinuxCNC rs274 kontrolünün CI'a alınması (SPEC değil, CI işi) | Her biri ayrı pakete ya da ayrı dosyaya yazar; dalga içi sıra: 22 → 21'i, 26 → 17 ve 24'ü bekler (aşağıda) |
| **4** (sıra yok, paralel kollar) | Aşağıdaki "Dalga 4 kolları" tablosu | Kollar birbirinin paketine yazmaz; her kol yalnızca kendi bağımlılığı `main`'e girince başlar |
| **5.0** (kısa, dosya sahibine göre paralel) | Arayüz PR'ları: CAM Ek 3 (`cam/model.py`: `ToolKind` TAP/SPOT/CHAMFER, `EntryMode`, `Fixture`, `MachineProfile` iş mili gücü/torku), montaj eklemleri ve tolerans (`assy/model.py`: `Joint`, `Tolerance`), kararlı referans (`geometry/part.py`: `FaceRef`, `Part.find`), Tezgah ekran kaydı (`tezgah/sunucu.py` → `tezgah/ekranlar/<ad>.py`, `src/ekranlar/<ad>.ts`) | Her biri farklı arayüz dosyasında, tek sahipli |
| **5** | `03c-giris`, `04b-cevrimler`, `19-adaptif-kaba`, `32-kesme-kuvveti`, `39-kalan-malzeme-3b`, `40-torna-ek`, `33-montaj-kinematigi`, `34-tolerans`, `10-montaj-cam`, `35-standart-parca`, `36-montaj-sirasi`, `18-ozellik-agaci`, `37-proje-kabuk`, `47-tezgah-ekranlari`, `38-is-foyu`, `45-modal`, `46-uctan-uca` | Her hat yalnız kendi yeni dosyalarına yazar; paylaşılan dosyalar yalnız 5.0 arayüz PR'larında değişir (kapsam "Tam", kullanıcı onayı 2026-10-18 10:51 UTC) |

### Dalga 3: dalga içi sıra
Aynı anda başlayanlar: 17, 21, 24, 03b, 06b, 27, 28, LinuxCNC CI. Sonra gelenler:
- `22-torna-sim` → 21 `main`'de (torna G-code'unu simüle eder).
- `26-tezgah-modelleme` → 17 ve 24 `main`'de. `geometry/extrude.py` ve `tezgah/ifade.py` kısmı (26 K1–K5)
  17'nin `sketch/model.py` arayüzü (PR #55) `main`'de olduğu için 24'ü beklemeden başlayabilir.

### Dalga 4 kolları (paralel, öncelik sırası yok)
| Kol | SPEC'ler | Başlamak için `main`'de olmalı |
|---|---|---|
| Tezgâh profilleri ve postprosesörler | `30-tezgah-profili` (GRBL, Fanuc, Haas; sınır denetimi) → `31-sinumerik-heidenhain` | 30: 04, 14, 21 · 31: 30 |
| Özellik tanımaya dayalı otomatik CAM | `29-islem-plani` | 27, 14, 05, 21, 22 (+ 28 torna profili) |
| 4 ve 5 eksen | `41-kinematik-3arti2` → (`42-bes-eksen-yol`, `43-tri-dexel`) → `44-tezgah-carpisma` | 41: 03, 06 · 42: 41, 06 · 43: 05 · 44: 41, 43 |
| Montaj girişim kontrolü | `09-girisim` | 07, 08 (+ `geometry/part.py` arayüz PR'ı) |
| FEM ağ ve gerilme analizi | `12-gmsh` → `13-calculix` (13, 12'yi bekler) | 02, 11 |
| Tezgah torna ve montaj ekranı | `25-tezgah-torna-montaj` | 24, 21, 22, 09 |

Not: `09`, `10`, `12`, `13` daha önce Dalga 3'teydi; 2026-10-18'de Dalga 3 CAM, torna ve Tezgah'a ayrıldığı
için Dalga 4'e taşındı. `10`, `18` ve `19` Dalga 5'e alındı (2026-10-18 10:51).

Bağımlılıklar (→ "şuna ihtiyaç duyar"):
- `03-cam-2d`, `04-gcode` → sadece `cam/model.py` (03 2D profillerle çalışır; parçadan özellik okuma 05/06'da)
- `08-kisitlar` → sadece `assy/model.py` (dönüşüm matrisleri üzerinde saf matematik)
- `05-cam-sim` → 02, 03, 04 · `06-cam-3d` → 02, 03 · `07-montaj-agaci` → 02
- `09-girisim` → 07, 08 · `11-tet4` → 01 · `12-gmsh` → 02, 11 · `13-calculix` → 12
- `14-cam-kurulum` → 03, 04 · `15-goruntuleyici` → 02, 03 · `16-teknik-resim` → 02 · `17-kroki` → `sketch/model.py` arayüz PR'ı (yöntem 08 ile aynı, kod bağımlılığı yok) · `18-ozellik-agaci` → 5.0 kararlı referans, 17, 26 · `19-adaptif-kaba` → 03, 05
- `20-torna-yol` → 03 · `21-torna-gcode` → 04, 20 · `22-torna-sim` → 02, 21 · `23-parca-ek` → 02
- `24-tezgah` → 02, 03, 04, 05, 08 · `25-tezgah-torna-montaj` → 24, 21, 22, 07, 09 · `26-tezgah-modelleme` → 02, 03, 04, 17, 23, 24
- `03b-cep-kalan-malzeme` → 03 · `06b-cam-3d-ek` → 06 · `27-ozellik-tanima` → 02, 03, 20, 23 · `28-torna-profili` → 02, 20
- `29-islem-plani` → 27, 14, 05, 21, 22 (torna tarafı için 28) · `30-tezgah-profili` → 04, 14, 21 · `31-sinumerik-heidenhain` → 30
- `41-kinematik-3arti2` → 03, 06 · `42-bes-eksen-yol` → 41, 06 · `43-tri-dexel` → 05 · `44-tezgah-carpisma` → 41, 43
- `03c-giris` → 5.0 CAM Ek 3, 03b · `04b-cevrimler` → 5.0 CAM Ek 3, 30, 31
- `32-kesme-kuvveti` → 5.0 CAM Ek 3, 05, 14, 22, 30 · `39-kalan-malzeme-3b` → 05, 06b · `40-torna-ek` → 21, 22, 29, 30
- `33-montaj-kinematigi` → 5.0 montaj eklemleri, 08, 09 · `34-tolerans` → 5.0 montaj eklemleri, 08
- `10-montaj-cam` → 5.0 CAM Ek 3, 05, 07, 09, 14 · `35-standart-parca` → 07, 08, 23 · `36-montaj-sirasi` → 09
- `37-proje-kabuk` → 5.0 Tezgah ekran kaydı, 24, 25, 26 · `47-tezgah-ekranlari` → 5.0 Tezgah ekran kaydı + ekranın SPEC'i (29, 41–44, 12–13)
- `38-is-foyu` → 14, 16, 29 · `45-modal` → 12, 13 (kesme kuvvetinde sehim için 32) · `46-uctan-uca` → 24–29

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
| 03b | 03b-cep-kalan-malzeme | Kalan malzeme denetimli cep: D/2 < s ≤ D yan paso, her halka seviyesinde kesin (ofset aritmetiğiyle) kalan malzeme denetimi, gerekirse ara halka | Hiçbir durumda ada kalmıyor; ara halka sayısı ve yan paso analitik |
| 03c | 03c-giris | Rampa ve helis giriş, merkezden kesmeyen takımda düz dalmanın reddi | Rampa açısı ve helis yarıçapı sınırları formülle; merkezden kesmeyen takımla düz dalma → hata |
| 4 | 04-gcode | G-code çıkışı (GRBL / Fanuc post-işlemcisi) + kendi G-code okuyucumuz; delik delme çevrimleri (G81/G83) | Üretilen G-code geri okununca takım yolu birebir aynı |
| 04b | 04b-cevrimler | Kılavuz (G84), punta (G82), havşa / pah takımı çevrimleri | Diş adımı = ilerleme / devir birebir; havşa çapı derinlikten analitik; geri okunan yol aynı |
| 5 | 05-cam-sim | Talaş kaldırma simülasyonu (dexel / voxel), işleme süresi tahmini | Simüle edilen son parça CAD hacmiyle tolerans içinde; çakma (gouge), hızlı harekette çarpma ve takım tutucu / sap çarpışması tespiti; parçadan işleme özelliklerini (düz yüz, cep, delik) okuma |
| 6 | 06-cam-3d | 3D yüzey işleme (küresel uçlu takım, drop-cutter), kaba + ince işleme | Küre / silindir yüzeyde iz yüksekliği (scallop) formülle tutuyor |
| 06b | 06b-cam-3d-ek | Torik ve konik takımla drop-cutter (tek dışbükey takım profili), waterline (sabit Z kontur) ince işleme | Analitik yüzeylerde CL noktaları formülle; rastgele ağda çakma yok ve temas var; waterline döngüleri sınırda |
| 14 | 14-cam-kurulum | İş sıfırı (WCS), stok, bağlama; freze ve torna takımları için JSON takım kütüphanesi; kesme verisinden devir ve ilerleme: n = 1000·Vc / (π·D), F = n·z·fz | Bilinen Vc, fz, D, z için S ve F birebir; G-code'da WCS (G54) doğru; takım boyu: Fanuc'ta G43 H, GRBL'de prob (G38.2) ile ölçüm + G43.1 dinamik ofset (GRBL'de G43 yok) |
| 19 | 19-adaptif-kaba | Sabit temas açılı (trokoidal / adaptif) kaba işleme | Temas açısı her adımda sınır içinde; kalan malzeme simülasyonla doğru |
| 20 | 20-torna-yol | Torna takım yolu, XZ düzleminde 2D (girdi: dönel parçanın yarı kesit profili): alın ve boy tornalama, kaba çevrim (paso derinliği), ince profil, kanal açma, diş çekme; takım burun yarıçapı telafisi | Silindir / koni / yay profilinde paso sayısı ve ofset analitik 1e-6 mm; burun yarıçapı telafisi koni ve yayda formülle tutuyor; diş paso derinlikleri formülle |
| 21 | 21-torna-gcode | Torna post-işlemcisi (Fanuc torna) + okuyucu: çap programlama, G96/G97 sabit kesme hızı, G50 devir sınırı, G71/G70 kaba-ince çevrim, G76 diş çevrimi | Üretilen G-code geri okununca takım yolu birebir aynı; G96'da n = 1000·Vc / (π·D) ve G50 sınırı doğru |
| 22 | 22-torna-sim | Torna talaş simülasyonu (radyal dexel), süre (G95, G96 ve devir sınırı), hızlı harekette çarpma, ayna ve tutucu çarpışması, çakma | Son parça hacmi Pappus formülüyle tutuyor; süre analitik; ayna / tutucu çarpması tespit ediliyor |
| 27 | 27-ozellik-tanima | İşleme özelliği tanıma: parçadan yüz alma, cep, açık bölge, delik (3 eksen, üstten); torna profilinden kaba zarf ve kanal | Bilinen parçalarda özellik sayısı, bölgeler ve derinlikler analitik; desteklenmeyen yüz (eğik, alttan erişim) → hata |
| 28 | 28-torna-profili | Katı parçadan torna profili: eksenden geçen yarı düzlem kesiti, doğru + yay uydurma | Kademeli milde profil analitik; dönel olmayan parça → hata |
| 29 | 29-islem-plani | Otomatik işlem planı: özelliklerden (27) freze ve torna işlemlerine, takım ve kesme verisi seçimi (14), sıra, bağlama, simülasyonla doğrulama (05 / 22) | Bilinen özelliklerde takım, kesme verisi, sıra ve delik çevrimi beklenen değerde; kalan malzemede ek takım; uygun takım yoksa açık gerekçeli hata |
| 30 | 30-tezgah-profili | Tezgâh profilleri (JSON), tezgâh sınır denetimi, dilden bağımsız blok planı ve postprosesör katmanı (GRBL, Fanuc, Haas) | SPEC 04 altın metinleri bayt bayt aynı; kurs, devir, ilerleme ve takım numarası aşımı → hata (sessiz kırpma yok) |
| 31 | 31-sinumerik-heidenhain | Siemens Sinumerik 840D / 828D ve Heidenhain Klartext postprosesörleri ve okuyucuları | Geri okunan yol aynı; desteklenmeyen kod (ör. Siemens G58/G59) → hata |
| 32 | 32-kesme-kuvveti | Kienzle kesme kuvveti, iş mili gücü denetimi, sabit talaş kalınlığı için ilerleme ayarı (freze ve torna) | `Fc = kc1.1·b·h^(1−mc)` ve `P = Fc·vc/60000` bilinen değerlerde birebir; güç sınırı aşımı → uyarı |
| 39 | 39-kalan-malzeme-3b | 05 son stoğundan 3B kalan malzeme işleme; simüle parçadan ağ ve CAD'e sapma haritası | Bilinen küre/cep parçasında kalan hacim analitik; sapma haritası bilinen kalınlığı veriyor |
| 40 | 40-torna-ek | Torna delme / punta, ters bağlama, profilli kanal, torna tezgâh profili | Delik hacmi ve ters bağlamada `z → −z` dönüşümü analitik; profil sınırı aşımı → hata |
| 41 | 41-kinematik-3arti2 | Tezgâh kinematiği (ileri / ters; masa-masa, kafa-kafa, kafa-masa) ve 3+2 indeksli işleme | Dönme ve Euler gidiş-dönüş 1e-9; ileri ve ters kinematik kapalı formla (AC, BC, AB, nutasyonlu B); ulaşılamaz yön → hata |
| 42 | 42-bes-eksen-yol | Eş zamanlı 5 eksen takım yolu: takım ekseni yönelimi, eklem uzayı doğrusallaştırma, G93 ters zaman ilerlemesi | Analitik yüzeyde çakma ve sap çarpması yok; doğrusallaştırma hatası sınırda; G93 değeri formülle |
| 43 | 43-tri-dexel | Tri-dexel talaş simülasyonu: her yönde takım ekseni (3+2 ve 5 eksen) | Eğik takımla kaldırılan hacim analitik; alttan / yandan boşluk, sap / tutucu çarpması tespit ediliyor |
| 44 | 44-tezgah-carpisma | Tezgâh kinematiğiyle gövde–gövde çarpışması, en az boşluk ve eksen sınırları | İlk temas anı analitik; eksen sınırı aşımı hareketin içindeki ilk anıyla bulunuyor |

## Aşama 3 — Montaj (`assy/`)
| # | SPEC | Konu | Bitti sayılır |
|---|------|------|---------------|
| 7 | 07-montaj-agaci | Parça + konum (Location) ağacı, alt montajlar, malzeme listesi (BOM), montaj STEP içe-dışa aktarma | STEP geri okununca parça sayısı ve konumlar aynı; BOM adet ve kütle doğru |
| 8 | 08-kisitlar | Montaj kısıtları (çakışık, eş eksen, mesafe, açı) → konum çözücü (Newton-Raphson / en küçük kareler) | Bilinen kapalı form konumlar 1e-9 mm içinde; serbestlik derecesi sayımı doğru; çelişkili kısıt → hata |
| 9 | 09-girisim | Genel boolean API (`cut` / `fuse` / `common`), rijit taşıma, en küçük uzaklık; montajda girişim, temas ve dar boşluk raporu | Bilerek çakıştırılan parçalarda kesişim hacmi analitik (pim–delik sıkı geçme dahil); temiz montajda 0 |
| 10 | 10-montaj-cam | Bağlama kütüphanesi (mengene, ayna, pabuç), montajdan bağlamasıyla CAM'e gönderme, şekilli fikstür çarpması | Fikstüre çarpma tespit ediliyor; temiz bağlamada 0 olay |
| 33 | 33-montaj-kinematigi | Eklemler, Grübler serbestlik sayımı, sürükleyerek hareket, hareket boyunca çarpışma | Dört çubuk mekanizmasında konum kapalı formla 1e-9; ilk temas anı analitik |
| 34 | 34-tolerans | Tolerans yığılımı: en kötü durum, RSS, Monte Carlo; 3B için 08 Jacobian'ı | 1B zincirde WC ve RSS kapalı formla birebir; Monte Carlo RSS'e istatistik sınırda yakınsıyor |
| 35 | 35-standart-parca | ISO civata, somun, pul, pim, rulman; delik kaydından civata önerisi ve eş eksen mate | Hacimler standart ölçüden analitik; önerilen civata delik çapına uyuyor |
| 36 | 36-montaj-sirasi | Girişimsiz sökme yönlerinden montaj sırası ve demontaj yolu | Bilinen yığında sıra tek ve doğru; kilitli montajda → hata |

## Aşama 4 — Analiz (FEM, `core/` + `mesh/`)
| # | SPEC | Konu | Bitti sayılır |
|---|------|------|---------------|
| 11 | 11-tet4 | 3D tetrahedron eleman | Patch test + konsol kiriş yakınsaması |
| 12 | 12-gmsh | Parçadan tetrahedron ağı (gmsh) → `core.model.Model` (tet4); sınır yüzeyinden düzlem / silindir seçip mesnet, yüzey çekmesi ve basınç yükü | Aynı girdiyle aynı ağ; yük bileşkeleri analitik; parça → ağ → yük → `solve` zinciri çalışıyor |
| 13 | 13-calculix | Gerilme sonrası işlem (von Mises, asal gerilmeler, düğüm gerilme tensörü), CalculiX `.inp` dışa aktarma ve C3D4 çapraz kontrolü | Delikli plakada Kt ≈ 3 (Peterson Kt_g = 3.032 civarı); aynı ağda CalculiX ile fark < %1 |
| 45 | 45-modal | Öz frekans analizi, kesme kuvvetinde ince duvar sehimi | Konsol kirişte ilk öz frekans Euler-Bernoulli formülüyle; sehim kapalı formla |

## Aşama 5 — Parametrik model, görüntüleme, tek uygulama ve atölye
| # | SPEC | Konu | Bitti sayılır |
|---|------|------|---------------|
| 23 | 23-parca-ek | 02'den sonraya kalan parça işlemleri: yuvarlatma (fillet), havşa, dişli delik, eğimli / açılı delik | Fillet sonrası hacim ve alan analitik (çeyrek daire kesit) rel 1e-6; havşa ve delik hacmi formülle |
| 15 | 15-goruntuleyici | `viz/` içinde pyvista ile parça, montaj ve takım yolunu 3D gösterme, ekran görüntüsü kaydetme | Bilinen sahnede sınır kutusu / piksel kontrolü; ekransız (off-screen) test çalışıyor |
| 16 | 16-teknik-resim | OCCT gizli çizgi kaldırma ile ön / üst / yan görünüş ve kesit, temel ölçüler, DXF ve SVG çıkışı | Blok + delikte görünüş kenar uzunlukları analitik; DXF geri okununca aynı |
| 17 | 17-kroki | Kısıtlı 2D eskiz (`sketch/`, saf numpy): nokta, çizgi, yay, daire + yatay, dik, paralel, teğet, eş, mesafe, açı, simetri; Gauss–Newton çözücü (08 ile aynı yöntem); öğe başına serbestlik ve yönü, çelişen kısıt kümesi, sürükleme, kapalı döngülerden bölgeler | Kapalı formlu üçgen / dörtgen / kanal 1e-9; DOF ve öğe serbestliği doğru; çelişki kümesi tam çelişen kısıtlar; sürükleme kapalı formda; bölge alanı analitik |
| 18 | 18-ozellik-agaci | Özellik ağacı (26'nın doğrusal geçmişinin yerine), kararlı yüz referansı, revolve, pah / fillet adımı, desen, ayna | Parametre değişince hacim analitik; bağlı özellik doğru yüze kalıyor |
| 24 | 24-tezgah | Tezgah web arayüzü (FastAPI 127.0.0.1 + three.js): freze işi, zaman şeridi, G-code ↔ yol ↔ zaman bağı, kanıt paneli | `specs/24-tezgah.md` K1–K10 |
| 26 | 26-tezgah-modelleme | Tezgah'ta etkileşimli modelleme: eskiz çiz, ölçü ve kısıtla sabitle (17), ekstrüzyon ekle / kes, delik, ifadeli parametreler, geçmiş şeridi; tasarım niyetini (kesim → cep, delik → delme) freze işine gönderme | Ekstrüzyon / kesim hacmi analitik rel 1e-6; parametre değişince hacim analitik; gönderilen işte cep bölgesi eskizdekiyle 1e-9 ve SPEC 24 kontrolleri `tamam` |
| 25 | 25-tezgah-torna-montaj | Tezgah'ta torna ekranı (yol, çap programlı G-code, simülasyon, ayna / punta kontrolleri) ve montaj ekranı (ağaç, BOM, sıra, serbestlik, girişim); girişim düzeltmesi tornadaki parametreye yazılır | Ekran uçları kütüphane sonucunu birebir döndürüyor; e2e yerelde |
| 37 | 37-proje-kabuk | Tek `.3dc` proje dosyası, geri al / yinele, komut paleti, ekranlar arası tek iplik | Proje kaydedilip açılınca model, montaj, plan ve profil birebir aynı |
| 47 | 47-tezgah-ekranlari | Tezgah'ta otomatik CAM (29), çok eksen (41–44) ve analiz (12–13) ekranları | Ekran uçları kütüphane sonucunu birebir döndürüyor (Python testleri); e2e yerelde |
| 38 | 38-is-foyu | İş föyü (takım listesi, bağlama resmi, WCS, süre, ilk parça ölçüm listesi), `docs/tezgah-dogrulama.md` | Föydeki takım boyu, süre ve WCS kaynak plandakiyle birebir |
| 46 | 46-uctan-uca | Altın senaryo: model → plan → sim → G-code → LinuxCNC rs274 → montaj girişimi | Zincir tek testte yeşil; rs274'ün geri verdiği yol plandakiyle aynı |

Not: 14 ve 20 (`cam/model.py`: torna takımı / uç geometrisi, silindirik stok, XZ hareketleri) ile 17 (yeni `sketch/model.py`: `Plane`, eskiz öğeleri, kısıtlar, `SketchRegion`) ortak arayüz değişikliği gerektirir; kurala göre önce ayrı küçük arayüz PR'ı açılır.

## Gerçek tezgâh doğrulaması (belge, SPEC değil)
`docs/tezgah-dogrulama.md`: üretilen G-code'u tezgâhta ilk kez çalıştırmadan önceki kontrol listesi (simülasyonda gözden geçirme, havada / kuru çalıştırma, Z ofsetini ve takım boyunu doğrulama, düşük ilerleme oranıyla ilk parça, ilk parça ölçümü). Dalga 2'de 04 ve 14 ile birlikte yazılır; testleri yoktur, tezgâhta kullanıcı uygular.

## İhtiyaç olursa (sıraya alınmadı)
3+2 ve 5 eksen (41–44), montajda hareket ve kinematik (33), modal analiz (45) ve kullanıcı arayüzü (24–26, 37, 47)
artık planlı. Burada kalanlar:
- C ve Y eksenli torna-freze (mill-turn)
- Isıl analiz
- FEM'i özellik ağacı parametreleriyle döngüye sokan optimizasyon

## Bağımlılık notu
`cad` (build123d) zaten `pyproject.toml`'da isteğe bağlı. CAM için ofset kütüphanesi (ör. pyclipper / shapely)
veya simülasyon için ek paket gerekirse ilgili SPEC'te önerilir ve kullanıcı onayı alınır.
`pyvista` (SPEC 15, görüntüleyici) kullanıcı tarafından onaylandı (2026-10-18); `pyproject.toml`'a eklenmesi ayrı küçük PR olarak yapılır.
