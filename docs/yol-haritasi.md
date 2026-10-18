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
| **2** | `05-cam-sim`, `06-cam-3d`, `07-montaj-agaci`, `11-tet4`, `14-cam-kurulum`, `15-goruntuleyici`, `16-teknik-resim`, `20-torna-yol` | 02 (katı parça) ve 03/04 (takım yolu) `main`'de |
| **3** | `09-girisim`, `10-montaj-cam`, `12-gmsh`, `13-calculix`, `17-kroki`, `21-torna-gcode` | Montaj ağacı, CAM simülasyonu, tet4, kısıt çözücü (08) ve torna takım yolu (20) `main`'de |
| **4** | `18-ozellik-agaci`, `19-adaptif-kaba`, `22-torna-sim` | Kroki (17), talaş simülasyonu (05) ve torna G-code'u (21) `main`'de |

Bağımlılıklar (→ "şuna ihtiyaç duyar"):
- `03-cam-2d`, `04-gcode` → sadece `cam/model.py` (03 2D profillerle çalışır; parçadan özellik okuma 05/06'da)
- `08-kisitlar` → sadece `assy/model.py` (dönüşüm matrisleri üzerinde saf matematik)
- `05-cam-sim` → 02, 03, 04 · `06-cam-3d` → 02, 03 · `07-montaj-agaci` → 02
- `09-girisim` → 07 · `10-montaj-cam` → 05, 07 · `11-tet4` → 01 · `12-gmsh` → 02, 11 · `13-calculix` → 12
- `14-cam-kurulum` → 03, 04 · `15-goruntuleyici` → 02, 03 · `16-teknik-resim` → 02 · `17-kroki` → 08 · `18-ozellik-agaci` → 02, 17 · `19-adaptif-kaba` → 03, 05
- `20-torna-yol` → 03 · `21-torna-gcode` → 04, 20 · `22-torna-sim` → 02, 21

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
| 5 | 05-cam-sim | Talaş kaldırma simülasyonu (dexel / voxel), işleme süresi tahmini | Simüle edilen son parça CAD hacmiyle tolerans içinde; çakma (gouge) ve hızlı harekette çarpma tespiti; parçadan işleme özelliklerini (düz yüz, cep, delik) okuma |
| 6 | 06-cam-3d | 3D yüzey işleme (küresel uçlu takım, drop-cutter), kaba + ince işleme | Küre / silindir yüzeyde iz yüksekliği (scallop) formülle tutuyor |
| 14 | 14-cam-kurulum | İş sıfırı (WCS), stok, bağlama; freze ve torna takımları için JSON takım kütüphanesi; kesme verisinden devir ve ilerleme: n = 1000·Vc / (π·D), F = n·z·fz | Bilinen Vc, fz, D, z için S ve F birebir; G-code'da WCS (G54) doğru |
| 19 | 19-adaptif-kaba | Sabit takım temas açılı (trokoidal / adaptif) kaba işleme | Temas açısı her adımda sınır içinde; kalan malzeme simülasyonla doğru |
| 20 | 20-torna-yol | Torna takım yolu, XZ düzleminde 2D (girdi: dönel parçanın yarı kesit profili): alın ve boy tornalama, kaba çevrim (paso derinliği), ince profil, kanal açma, diş çekme; takım burun yarıçapı telafisi | Silindir / koni / yay profilinde paso sayısı ve ofset analitik 1e-6 mm; burun yarıçapı telafisi koni ve yayda formülle tutuyor; diş paso derinlikleri formülle |
| 21 | 21-torna-gcode | Torna post-işlemcisi (Fanuc torna) + okuyucu: çap programlama, G96/G97 sabit kesme hızı, G50 devir sınırı, G71/G70 kaba-ince çevrim, G76 diş çevrimi | Üretilen G-code geri okununca takım yolu birebir aynı; G96'da n = 1000·Vc / (π·D) ve G50 sınırı doğru |
| 22 | 22-torna-sim | Torna talaş simülasyonu (dönel simetri: 2D profil kesişimi) ve katı parçadan dönel profil çıkarma | Son parça hacmi Pappus formülüyle tutuyor; profil CAD profiliyle tolerans içinde; çene / punta çarpması tespit ediliyor |

## Aşama 3 — Montaj (`assy/`)
| # | SPEC | Konu | Bitti sayılır |
|---|------|------|---------------|
| 7 | 07-montaj-agaci | Parça + konum (Location) ağacı, alt montajlar, malzeme listesi (BOM), montaj STEP içe-dışa aktarma | STEP geri okununca parça sayısı ve konumlar aynı; BOM adet ve kütle doğru |
| 8 | 08-kisitlar | Montaj kısıtları (çakışık, eş eksen, mesafe, açı) → konum çözücü (Newton-Raphson / en küçük kareler) | Bilinen kapalı form konumlar 1e-9 mm içinde; serbestlik derecesi sayımı doğru; çelişkili kısıt → hata |
| 9 | 09-girisim | Girişim / çakışma kontrolü ve boşluk ölçümü | Bilerek çakıştırılan parçalarda kesişim hacmi analitik değeri tutuyor; temiz montajda 0 |
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
| 15 | 15-goruntuleyici | `viz/` içinde pyvista ile parça, montaj ve takım yolunu 3D gösterme, ekran görüntüsü kaydetme | Bilinen sahnede sınır kutusu / piksel kontrolü; ekransız (off-screen) test çalışıyor |
| 16 | 16-teknik-resim | OCCT gizli çizgi kaldırma ile ön / üst / yan görünüş ve kesit, temel ölçüler, DXF ve SVG çıkışı | Blok + delikte görünüş kenar uzunlukları analitik; DXF geri okununca aynı |
| 17 | 17-kroki | 2D kroki (çizgi, yay, daire) + kısıtlar (yatay, dik, teğet, eş, mesafe, açı) ve çözücü; 08 ile aynı matematik (Newton, serbestlik derecesi sayımı) | Kapalı formlu üçgen / dörtgenler 1e-9; DOF sayımı doğru; çelişkili kısıt → hata |
| 18 | 18-ozellik-agaci | Kroki → extrude / revolve / cep / delik / pah; parametre değişince yeniden hesap; yüzlere kararlı referans (topolojik adlandırma sorunu) | Parametre değişince hacim analitik; bağlı özellik doğru yüze kalıyor |

Not: 14 ve 20 (`cam/model.py`: torna takımı / uç geometrisi, silindirik stok, XZ hareketleri) ile 17 (yeni `sketch/model.py`) ortak arayüz değişikliği gerektirir; kurala göre önce ayrı küçük arayüz PR'ı açılır.

## İhtiyaç olursa (sıraya alınmadı)
- 3+2 ve 5 eksen işleme, makine kinematiği (post-işlemcide döner eksenler)
- C ve Y eksenli torna-freze (mill-turn)
- Montajda hareket ve kinematik
- Modal ve ısıl analiz
- FEM'i özellik ağacı parametreleriyle döngüye sokan optimizasyon
- Kullanıcı arayüzü (PySide veya FastAPI + HTML), 15'teki görüntüleyicinin üstüne

## Bağımlılık notu
`cad` (build123d) zaten `pyproject.toml`'da isteğe bağlı. CAM için ofset kütüphanesi (ör. pyclipper / shapely)
veya simülasyon için ek paket gerekirse ilgili SPEC'te önerilir ve kullanıcı onayı alınır.
`pyvista` (SPEC 15, görüntüleyici) kullanıcı tarafından onaylandı (2026-10-18); `pyproject.toml`'a eklenmesi ayrı küçük PR olarak yapılır.
