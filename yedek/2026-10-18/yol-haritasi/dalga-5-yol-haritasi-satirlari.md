# `docs/yol-haritasi.md` için Dalga 5 satırları (yapıştırmaya hazır)

> Sahibi: "Eskiz ve etkileşimli modelleme" thread'i (docs/yol-haritasi.md'nin sahibi). Kaynak:
> `yol-haritasi/dalga-5-onerisi.md`, kapsam "Tam" (kullanıcı, 2026-10-18 10:51 UTC).
> SPEC numaraları Dalga 5 thread'lerinin aldığı numaralardır.

## 1. "Paralel çalışma: dalgalar" tablosuna eklenecek satırlar

| Dalga | SPEC'ler (aynı anda) | Neden paralel olabilir |
|---|---|---|
| **5.0** (kısa, dosya sahibine göre paralel) | Arayüz PR'ları: CAM Ek 3 (`cam/model.py`: `ToolKind` TAP/SPOT/CHAMFER, `EntryMode`, `Fixture`, `MachineProfile` iş mili gücü/torku), montaj eklemleri ve tolerans (`assy/model.py`: `Joint`, `Tolerance`), kararlı referans (`geometry/part.py`: `FaceRef`, `Part.find`), Tezgah ekran kaydı (`tezgah/sunucu.py` → `tezgah/ekranlar/<ad>.py`, `src/ekranlar/<ad>.ts`) | Her biri farklı arayüz dosyasında, tek sahipli |
| **5** | `03c-giris`, `04b-cevrimler`, `19-adaptif-kaba`, `32-kesme-kuvveti`, `39-kalan-malzeme-3b`, `40-torna-ek`, `33-montaj-kinematigi`, `34-tolerans`, `10-montaj-cam`, `35-standart-parca`, `36-montaj-sirasi`, `18-ozellik-agaci`, `37-proje-kabuk`, `47-tezgah-ekranlari`, `38-is-foyu`, `45-modal`, `46-uctan-uca` | Her hat yalnız kendi yeni dosyalarına yazar; paylaşılan dosyalar yalnız 5.0 arayüz PR'larında değişir |

## 2. Bağımlılıklar listesine eklenecek satırlar

- `03c-giris` → 5.0 CAM Ek 3, 03b · `04b-cevrimler` → 5.0 CAM Ek 3, 30, 31 · `19-adaptif-kaba` → 03, 05
- `32-kesme-kuvveti` → 5.0 CAM Ek 3, 05, 14, 22, 30 · `39-kalan-malzeme-3b` → 05, 06b · `40-torna-ek` → 21, 22, 29, 30
- `33-montaj-kinematigi` → 5.0 montaj eklemleri, 08, 09 · `34-tolerans` → 5.0 montaj eklemleri, 08
- `10-montaj-cam` → 5.0 CAM Ek 3, 05, 07, 09, 14 · `35-standart-parca` → 07, 08, 23 · `36-montaj-sirasi` → 09
- `18-ozellik-agaci` → 5.0 kararlı referans, 17, 26 · `37-proje-kabuk` → 5.0 Tezgah ekran kaydı, 24, 25, 26
- `47-tezgah-ekranlari` → 5.0 Tezgah ekran kaydı + ekranın SPEC'i (29, 41–44, 12–13)
- `38-is-foyu` → 14, 16, 29 · `45-modal` → 12, 13 (kesme kuvvetinde sehim için 32) · `46-uctan-uca` → 24–29

## 3. Aşama tablolarına eklenecek satırlar

### Aşama 2 — CAM
| # | SPEC | Konu | Bitti sayılır |
|---|------|------|---------------|
| 03c | 03c-giris | Rampa ve helis giriş, merkezden kesmeyen takımda düz dalmanın reddi | Rampa açısı ve helis yarıçapı sınırları formülle; merkezden kesmeyen takımla düz dalma → hata |
| 04b | 04b-cevrimler | Kılavuz (G84), punta (G82), havşa / pah takımı çevrimleri | Diş adımı = ilerleme / devir birebir; havşa çapı derinlikten analitik; geri okunan yol aynı |
| 19 | 19-adaptif-kaba | Sabit temas açılı (trokoidal / adaptif) kaba işleme | Temas açısı her adımda sınır içinde; kalan malzeme simülasyonla doğru |
| 32 | 32-kesme-kuvveti | Kienzle kesme kuvveti, iş mili gücü denetimi, sabit talaş kalınlığı için ilerleme ayarı (freze ve torna) | `Fc = kc1.1·b·h^(1−mc)` ve `P = Fc·vc/60000` bilinen değerlerde birebir; güç sınırı aşımı → uyarı |
| 39 | 39-kalan-malzeme-3b | 05 son stoğundan 3B kalan malzeme işleme; simüle parçadan ağ ve CAD'e sapma haritası | Bilinen küre/cep parçasında kalan hacim analitik; sapma haritası bilinen kalınlığı veriyor |
| 40 | 40-torna-ek | Torna delme / punta, ters bağlama, profilli kanal, torna tezgâh profili | Delik hacmi ve ters bağlamada `z → −z` dönüşümü analitik; profil sınırı aşımı → hata |

### Aşama 3 — Montaj
| # | SPEC | Konu | Bitti sayılır |
|---|------|------|---------------|
| 33 | 33-montaj-kinematigi | Eklemler, Grübler serbestlik sayımı, sürükleyerek hareket, hareket boyunca çarpışma | Dört çubuk mekanizmasında konum kapalı formla 1e-9; ilk temas anı analitik |
| 34 | 34-tolerans | Tolerans yığılımı: en kötü durum, RSS, Monte Carlo; 3B için 08 Jacobian'ı | 1B zincirde WC ve RSS kapalı formla birebir; Monte Carlo RSS'e istatistik sınırda yakınsıyor |
| 10 | 10-montaj-cam | Bağlama kütüphanesi (mengene, ayna, pabuç), montajdan bağlamasıyla CAM'e gönderme, şekilli fikstür çarpması | Fikstüre çarpma tespit ediliyor; temiz bağlamada 0 olay |
| 35 | 35-standart-parca | ISO civata, somun, pul, pim, rulman; delik kaydından civata önerisi ve eş eksen mate | Hacimler standart ölçüden analitik; önerilen civata delik çapına uyuyor |
| 36 | 36-montaj-sirasi | Girişimsiz sökme yönlerinden montaj sırası ve demontaj yolu | Bilinen yığında sıra tek ve doğru; kilitli montajda → hata |

### Aşama 5 — Parametrik model, tek uygulama ve atölye
| # | SPEC | Konu | Bitti sayılır |
|---|------|------|---------------|
| 18 | 18-ozellik-agaci | Özellik ağacı, kararlı yüz referansı, revolve, pah / fillet adımı, desen, ayna | Parametre değişince hacim analitik; bağlı özellik doğru yüze kalıyor |
| 37 | 37-proje-kabuk | Tek `.3dc` proje dosyası, geri al / yinele, komut paleti, ekranlar arası tek iplik | Proje kaydedilip açılınca model, montaj, plan ve profil birebir aynı |
| 47 | 47-tezgah-ekranlari | Tezgah'ta otomatik CAM (29), çok eksen (41–44) ve analiz (12–13) ekranları | Ekran uçları kütüphane sonucunu birebir döndürüyor (Python testleri); e2e yerelde |
| 38 | 38-is-foyu | İş föyü (takım listesi, bağlama resmi, WCS, süre, ilk parça ölçüm listesi), `docs/tezgah-dogrulama.md` | Föydeki takım boyu, süre ve WCS kaynak plandakiyle birebir |
| 46 | 46-uctan-uca | Altın senaryo: model → plan → sim → G-code → LinuxCNC rs274 → montaj girişimi | Zincir tek testte yeşil; rs274'ün geri verdiği yol plandakiyle aynı |

### Aşama 4 — Analiz
| # | SPEC | Konu | Bitti sayılır |
|---|------|------|---------------|
| 45 | 45-modal | Öz frekans analizi, kesme kuvvetinde ince duvar sehimi | Konsol kirişte ilk öz frekans Euler-Bernoulli formülüyle; sehim kapalı formla |

## 4. "İhtiyaç olursa" bölümünden çıkarılacaklar

"3+2 ve 5 eksen" (41–44 ile planlandı), "Montajda hareket ve kinematik" (33), "Modal" (45) ve "Kullanıcı arayüzü"
(24–26, 37, 47) satırları artık planlı; bu bölümde yalnız ısıl analiz, C/Y eksenli torna-freze ve FEM ile
optimizasyon kalır (ayrıntı: `yol-haritasi/dalga-6-ve-sonrasi.md`).
