# Yol haritası

**Asıl hedef: 3D CAM ve 3D montaj.** Katı modelleme bunlara hizmet eden altyapıdır ve hazır çekirdekle
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
| **2** | `05-cam-sim`, `06-cam-3d`, `07-montaj-agaci`, `11-tet4` | 02 (katı parça) ve 03/04 (takım yolu) `main`'de |
| **3** | `09-girisim`, `10-montaj-cam`, `12-gmsh`, `13-calculix` | Montaj ağacı, CAM simülasyonu ve tet4 `main`'de |

Bağımlılıklar (→ "şuna ihtiyaç duyar"):
- `03-cam-2d`, `04-gcode` → sadece `cam/model.py` (03 2D profillerle çalışır; parçadan özellik okuma 05/06'da)
- `08-kisitlar` → sadece `assy/model.py` (dönüşüm matrisleri üzerinde saf matematik)
- `05-cam-sim` → 02, 03, 04 · `06-cam-3d` → 02, 03 · `07-montaj-agaci` → 02
- `09-girisim` → 07 · `10-montaj-cam` → 05, 07 · `11-tet4` → 01 · `12-gmsh` → 02, 11 · `13-calculix` → 12

## Aşama 0 — FEM iskeleti (hazır olanı bitir)
| # | SPEC | Konu | Bitti sayılır |
|---|------|------|---------------|
| 1 | 01-bar | 1D çubuk + çözücü iskeleti | δ = FL/EA ve tüm benchmark'lar yeşil (testler hazır, sadece kod) |

## Aşama 1 — Katı altyapı (`geometry/`, CAM ve montaj için en az gereken)
| # | SPEC | Konu | Bitti sayılır |
|---|------|------|---------------|
| 2 | 02-parca | STEP/STL içe-dışa aktarma, kodla basit parça (blok, delik, cep, pah), hacim / alan / ağırlık merkezi, basit görüntüleme | Analitik değerle rel 1e-6; STEP geri okununca hacim aynı |

## Aşama 2 — CAM (`cam/`)
| # | SPEC | Konu | Bitti sayılır |
|---|------|------|---------------|
| 3 | 03-cam-2d | 2.5D takım yolu: yüz alma, kontur, cep (ofset), takım yarıçapı telafisi, paso derinlikleri (girdi: 2D profiller) | Dikdörtgen cep ve dairesel konturda yol geometrisi analitik ofsetle 1e-6 mm |
| 4 | 04-gcode | G-code çıkışı (GRBL / Fanuc post-işlemcisi) + kendi G-code okuyucumuz; delik delme çevrimleri (G81/G83) | Üretilen G-code geri okununca takım yolu birebir aynı |
| 5 | 05-cam-sim | Talaş kaldırma simülasyonu (dexel / voxel), işleme süresi tahmini | Simüle edilen son parça CAD hacmiyle tolerans içinde; çakma (gouge) ve hızlı harekette çarpma tespiti; parçadan işleme özelliklerini (düz yüz, cep, delik) okuma |
| 6 | 06-cam-3d | 3D yüzey işleme (küresel uçlu takım, drop-cutter), kaba + ince işleme | Küre / silindir yüzeyde iz yüksekliği (scallop) formülle tutuyor |

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

## İhtiyaç olursa (sıraya alınmadı)
- Özellik ağacı (eskiz → extrude / revolve / fillet) ve 2D eskiz kısıt çözücü
- Basit arayüz (PySide veya FastAPI + HTML)

## Bağımlılık notu
`cad` (build123d) zaten `pyproject.toml`'da isteğe bağlı. CAM için ofset kütüphanesi (ör. pyclipper / shapely)
veya simülasyon için ek paket gerekirse ilgili SPEC'te önerilir ve kullanıcı onayı alınır.
