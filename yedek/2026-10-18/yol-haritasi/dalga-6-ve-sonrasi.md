# Dalga 6 ve sonrası: amaç, hedef, sınırlar

> Durum: **kapsam onaylandı** (kullanıcı, 2026-10-18 10:57; bkz. bölüm 7). Önceki durum: öneri. Onaylanınca satırları `docs/yol-haritasi.md`'ye sahibi ("Eskiz ve etkileşimli
> modelleme" thread'i) taşır. Kod içermez. SPEC numaraları boştaki kimliklerdir, kesin değildir.
> Kaynaklar: `docs/yol-haritasi.md`, `DURUM.md` (main `eb70d49`), `specs/`, `specs-taslak/` (özellikle 29, 30, 41–44'ün
> "Kapsam dışı" bölümleri), `yol-haritasi/dalga-5-onerisi.md` (kullanıcı 10:51'de "Tam" kapsamı seçti), iki sert inceleme.

## 1. Kısa cevap

**Amaç:** tasarımdan tezgâha tek yerel mühendislik uygulaması. Bir parçayı modelle, montaja koy, girişimini ve
toleransını kontrol et, freze ve torna için işlem planını çıkar, simülasyonda çarpmadan işlendiğini gör,
kendi tezgâhının lehçesinde G-code al, operatöre iş föyünü ver. Hepsi tek proje dosyasında, tek ekranda
(Tezgah), internet gerekmeden.

**Hedef ("1.0" sayılır):** uydurma ama gerçekçi üç işte (prizmatik freze parçası, mil, ikisinin montajı)
uçtan uca zincirin **gerçek tezgâhta** ilk parçayı ölçüye uygun çıkarması ve her adımın analitik testle
doğrulanmış olması. Hız ve güzellik ikinci; **doğru ve güvenli** birinci.

**Nasıl ilerleyecek:** Dalga 5 (şimdi, 4 arayüz PR'ı + 15 hat) "parçaları birbirine bağlıyor". Sonra üç dalga:

| Dalga | Ana fikir | Bittiğinde elde ne olur |
|---|---|---|
| **6 — Atölyeye çıkış** | Gerçek tezgâhta doğrulama, mill-turn, 5 eksen tamamlama, sağlamlık ve hız | Kullanıcının kendi tezgâhında güvenle çalışan program; Windows'ta tek tık kurulum |
| **7 — Akıllı katman** | Otomasyon ve karar desteği: otomatik CAM'in olgunlaşması, süre/maliyet/teklif, takım ömrü, optimizasyon | "Parçayı ver, planı ve fiyatı al" deneyimi; FEM'in tasarımı yönlendirmesi |
| **8 — 1.0 olgunluk** | Dondurma: kararlı API, sürümleme, belge, örnek kütüphanesi, kabul senaryoları | Başkasına verilebilir, sürüm numaralı bir ürün |

## 2. Dalga 5 bittiğinde nerede olacağız

Freze (2.5B, 3B, rest, rampa/helis, adaptif kaba, delik çevrimleri), torna (yol, G-code, sim, profil çıkarma,
ekler), otomatik özellik tanıma ve işlem planı, Fanuc/Haas/GRBL/LinuxCNC/Sinumerik/Heidenhain lehçeleri,
3+2 ve eş zamanlı 5 eksen yolu + tri-dexel sim + tezgâh çarpışması, kesme kuvveti/güç, montaj ağacı + kısıt +
girişim + kinematik + tolerans + standart parça + montaj sırası, kroki + özellik ağacı, FEM (çubuk, tet4, gmsh,
von Mises, modal), tek proje dosyası ve kabuklu Tezgah, iş föyü, uçtan uca altın senaryo testi.

**Eksik kalan üç şey:** (1) hiçbir program gerçek tezgâhta denenmedi; (2) torna-freze (C/Y eksen) ve 5 eksen
kaba/yanak işleme yok; (3) büyük parçada hız, kurulum kolaylığı ve hata kurtarma denenmedi.

## 3. Dalga 6 — Atölyeye çıkış

Önce iki kısa arayüz PR'ı (kurala göre ayrı PR + ayrı test thread'i), sonra paralel hatlar.

| # | Arayüz PR'ı | Dosya | İçerik |
|---|---|---|---|
| B0 | CAM Ek 4 | `cam/model.py` | `MachineProfile`'a C ve Y eksenli torna (canlı takım, taret istasyonu), `CylinderStock` için freze işlemi; 5 eksen kaba için `Toolpath` meta alanları |
| B1 | Proje dosyası sürümü | `fileio/proje.py` (H13 sahibi) | `.3dc` şema sürümü + göç (migration) kuralı; eski projeler açılır ya da `ModelError` ile neden açılmadığı söylenir |
| B2 | Malzeme arayüzü | `malzeme/model.py` (yeni) + `assy/model.py` ("Dalga 2 arayüz ekleri") | Malzeme kaydı (E, ν, ρ, Rp0.2, Rm, S-N, k, cp, α, Kienzle, Taylor, Vc/fz, €/kg; N–mm–MPa birimiyle, ρ t/mm³) ve bileşene malzeme kimliği (kullanıcı kararı 2026-10-18 11:07; ayrıntı `sinirlar-malzeme-analiz.md`) |

| Hat | SPEC (öneri) | Ne yapar | Doğrulama | Bağımlılık |
|---|---|---|---|---|
| **G1** | 48 gerçek tezgâh doğrulama programı | `docs/tezgah-dogrulama.md`'deki listeyi adım adım yürütür: havada çalıştırma, mum/köpük parça, ilk metal parça, ölçüm. Sonuçlar profilde `verified: true` (yalnız kullanıcı işaretler) | Kullanıcının tezgâhında ölçülen ilk parça raporu | 30, 38 (iş föyü) |
| **G2** | 49 torna-freze (mill-turn) | C ekseni indeksleme ve polar enterpolasyon (G12.1), Y ekseni ile eksenden kaçık delik/kama, canlı takımla alın frezeleme; 22 + 43 simülasyonunun birleşimi | Kama ve radyal delik hacmi analitik; G12.1 dönüşümü kapalı formla | B0, 21, 22, 43 |
| **G3** | 50 5 eksen kaba ve yanak (swarf) | 42'nin kapsam dışı bıraktıkları: 5 eksen kaba, yanak frezeleme, torik uçla serbest eğim, eksen düzgünleştirme | Regle yüzeyde yanak hatası formülle; tri-dexel hacim | 42, 43, 44 |
| **G4** | 51 5 eksen postprosesör | 41–42'nin bıraktığı G-code yazımı: `G68.2`, `G43.4`, `CYCLE800`/`TRAORI`, `PLANE SPATIAL`/`M128`, `G93` | Kendi okuyucumuzla gidiş-dönüş + LinuxCNC (5 eksen yapılandırması) dış yorumlayıcı | 31, 41, 42 |
| **G5** | 52 3B diş ve helis simülasyonu | Torna dişi ve freze diş (G84/thread mill) için helis süpürmesi; diş profili kontrolü | Diş hatvesi ve kök çapı ISO formülüyle | 22, 43, 04b |
| **G6** | 53 performans | Simülasyonu ve büyük montajı hızlandırma: z-map/dexel'i bloklu numpy, girişimde sınır kutusu ağacı, Tezgah'ta kademeli ağ (LOD). Hedef: 200×200 mm parçada 0.1 mm z-map ile tam freze simülasyonu < 10 s | Hız testleri `@pytest.mark.slow`; sonuç eski sürümle birebir aynı | 05, 09, 43 |
| **G7** | 54 sağlamlık ve hata kurtarma | Bozuk STEP, OCCT boolean hatası, çözülemeyen kısıt: her biri anlaşılır mesajla (`ModelError`), Tezgah'ta geri al ile kurtarma; otomatik kayıt | Bilinen bozuk dosya koleksiyonu (uydurma) | 37 |
| **G8** | 55 Windows kurulumu | Tek tıkla kurulum ve başlatma (Python gömülü, `uv` ile); kısayol, güncelleme | Temiz Windows'ta kurulum betiği | Yeni bağımlılık olabilir → karar (bkz. 7) |
| **G9** | 56 ısıl analiz | Kararlı ısı iletimi (tet4 üzerinde), kesmede ısı kaynağı yaklaşık; FEM'in ikinci fiziği | Duvar ve silindirde kapalı form sıcaklık | 11, 12 |
| **G10** | 66 malzeme kütüphanesi | Kaynaklı tipik değerler + kullanıcı malzemesi; BOM kütlesi, FEM, kesme verisi, kuvvet, maliyet aynı kayıttan (kullanıcı kararı 2026-10-18 11:07; ayrıntı `sinirlar-malzeme-analiz.md`) | Fiziksel tutarlılık (0<ν<0.5, Rp0.2≤Rm, G=E/2(1+ν)); birim dönüşüm sabitleri | B2, 07, 14 |
| **G11** | 67 tet10 ve CAD yüzüne yük | İkinci mertebe tetrahedron; yük/mesnedi CAD yüzüne verme; hacim kuvveti (ağırlık, merkezkaç) ve ısıl yük; emniyet katsayısı `n = Rp0.2/σ_vM` (kullanıcı kararı 2026-10-18 11:07; ayrıntı `sinirlar-malzeme-analiz.md`) | Konsol kiriş yakınsaması tet4'ten hızlı; Kirsch; CalculiX C3D10 | A2, 11, 12, 13, G10 |

Sıra: B0, B1 ve B2 hemen; G1, G6, G7, G9, G10, G11 bağımlılıkları Dalga 5'te bitince başlar; G2–G5 B0'dan sonra. G1 kod
değil, kullanıcının tezgâhında yürür; ama **1.0'ın asıl kapısıdır**.

## 4. Dalga 7 — Akıllı katman

| Hat | SPEC (öneri) | Ne yapar |
|---|---|---|
| **A1** | 57 otomatik CAM 2 | 27 + 29'un kural tabanlı planını genişletir: stok/bağlama seçimi, çok bağlamalı plan (ters çevirme), takım kütüphanesinden en az takım değişimi. Kurallar açık ve test edilir; "kara kutu" yapay zekâ yok |
| **A2** | 58 süre, maliyet ve teklif | Simüle edilen süre + takım aşınması + saat ücreti + malzeme → parça başı maliyet ve teklif sayfası. Atölyenin en çok sorduğu soru |
| **A3** | 59 takım ömrü | Taylor (`v·T^n = C`) ve kesme kuvvetinden takım değişim önerisi; iş föyüne yazılır |
| **A4** | 60 FEM ile parametre optimizasyonu | Özellik ağacı parametresi (et kalınlığı, fillet) → von Mises / sehim / öz frekans sınırı altında kütleyi azalt (scipy.optimize) |
| **A5** | 61 tasarım için imalat (DFM) denetimi | Modelde işlenemeyecek yeri anında göster: takımın giremediği iç köşe, derin dar cep, erişilemeyen yüz, ince duvar titreşim riski |
| **A6** | 62 Tezgah "şaşırtıcı" deneyim | Komut paletinden doğal dil benzeri komutlar ("Ø10 delik, 20 derin, H7"), canlı fark gösterimi, ölçüyü sürükleyince CAM ve maliyetin anında değişmesi, zaman çizelgesinde simülasyonu ileri-geri sarma |
| **A7** | 63 DNC / tezgâha gönderme | Programı ağ veya seri hat üzerinden tezgâha gönderme. Dış dünyaya etki ettiği için yalnız kullanıcı onayıyla ve önce simülasyon zorunlu (karar gerekir) |
| **A8** | 64 MES bağlantısı | Kullanıcının kendi MES'i (yerel, TypeScript + PostgreSQL). Kabul edilen yol (11:16): Tezgah'ın FastAPI'si yerel bir REST API açar (iş emri al; program, takım listesi, süre, iş föyü ver), OpenAPI şeması otomatik çıkar, MES tarafı TypeScript tiplerini bu şemadan üretir. Tezgah MES veritabanına doğrudan yazmaz (yeni bağımlılık yok, şemanın sahibi MES kalır) (kullanıcı kararı 2026-10-18 11:00: Dalga 7; bilgi 11:09) |
| **A9** | 65 serbest yüzey ve gerçekçi görünüm (basit) | Loft, sweep, B-spline yüzey (OCCT); Tezgah'ta tarayıcıda PBR malzeme görünümü. Işın izleme ve class-A yüzey yok (kullanıcı kararı 2026-10-18 11:00: Dalga 7'de basit) |
| **A10** | 68 ek analizler | Doğrusal burkulma, geçici ısıl, termo-mekanik, harmonik tepki, yüksek çevrim yorulma (S-N, Goodman) (kullanıcı kararı 2026-10-18 11:07; ayrıntı `sinirlar-malzeme-analiz.md`) |
| **A11** | 69 mekanizma dinamiği | Kinematikten (33) eklem kuvvetleri, motor torku, hız/ivme (Newton-Euler) (kullanıcı kararı 2026-10-18 11:07; ayrıntı `sinirlar-malzeme-analiz.md`) |
| **A12** | 70 CalculiX köprüsü | Temas, plastisite, büyük şekil değişimi CalculiX'te çözülür, sonuç Tezgah'ta gösterilir (kullanıcı kararı 2026-10-18 11:07; ayrıntı `sinirlar-malzeme-analiz.md`) |
| **A13** | 71 chatter lobu | Kullanıcının çekiç testi FRF ölçümüyle kararlılık lobu (Altintas sıfırıncı mertebe); ölçüm yoksa `ModelError` (kullanıcı kararı 2026-10-18 11:07; ayrıntı `sinirlar-malzeme-analiz.md`) |

## 5. Dalga 8 — 1.0 olgunluk

- **Kararlı API:** `*/model.py` arayüzleri dondurulur, sürüm numarası (semver) ve değişiklik günlüğü.
- **Kabul senaryoları:** üç altın senaryonun (prizmatik, mil, montaj) gerçek tezgâh ölçümleriyle kaydı.
- **Belge:** kullanıcı kılavuzu (Türkçe), her algoritmanın "nasıl çalışır" sayfası (öğrenme projesi olduğu için).
- **Örnek kütüphanesi:** uydurma parça ve montaj seti, her biri işlem planı ve G-code'u ile.
- **Teknik borç turu:** sert incelemelerdeki açık maddeler (O ve D seviyeleri) kapatılır.

## 6. Sistem neleri yapabilecek, neleri yapamayacak

### Yapabilecekleri (Dalga 8 sonunda)

- **Modelleme:** kroki + kısıtlar, extrude/revolve/cep/delik/pah/fillet, desen, ayna, özellik ağacı ve
  parametreyle yeniden hesap; STEP/STL içe-dışa; teknik resim (DXF/SVG).
- **Montaj:** ağaç, BOM, kısıtlar, eklem ve hareket, hareket boyunca çarpışma, girişim, tolerans yığılımı
  (en kötü durum, RSS, Monte Carlo), standart parçalar, montaj sırası.
- **Freze CAM:** 2.5B ve 3B, kalan malzeme, adaptif kaba, rampa/helis giriş, delik/kılavuz/havşa çevrimleri,
  3+2 ve eş zamanlı 5 eksen, kesme kuvveti ve güç denetimi, ilerleme optimizasyonu.
- **Torna CAM:** kaba/ince/kanal/diş, delme/punta, ters bağlama, C/Y eksenli torna-freze.
- **Simülasyon ve güvenlik:** talaş kaldırma (z-map, dexel, tri-dexel, torna profili), çakma, hızlı hareket
  çarpması, sap/tutucu, fikstür ve tezgâh gövdesi çarpışması, eksen sınırları.
- **Çıktı:** Fanuc, Haas, GRBL, LinuxCNC, Sinumerik, Heidenhain; iş föyü; süre ve maliyet.
- **Analiz:** statik (çubuk, tet4), von Mises, modal, ısıl, kesme kuvvetinde sehim, basit optimizasyon;
  CalculiX çapraz kontrolü.
- **Uygulama:** tek proje dosyası, geri al, otomatik kayıt, Windows'ta yerel çalışma, internetsiz.

### Yapamayacakları (bilerek kapsam dışı)

| Alan | Neden |
|---|---|
| Sac metal | Kullanıcı kararı (2026-10-18) |
| Class-A yüzey (kaporta/kalıp kalitesinde süreklilik), fotogerçekçi ışın izleme (ray tracing) render | Basit serbest yüzey ve PBR görünüm Dalga 7'de (A9); bunun ötesi ayrı bir ürün kadar iş |
| Kendi katı çekirdeğimiz | OCCT kullanıyoruz; onun fillet ve boolean hataları bizim de sınırımız. Hata olursa açıkça raporlarız, gizlemeyiz |
| Tezgâh kontrolörü / firmware, gerçek zamanlı eksen kontrolü | Biz programı üretiriz; tezgâhı kontrolör sürer |
| "Sertifikalı" postprosesör, tezgâh üreticisi onayı | Lehçeler belgelerden yazılır; gerçek tezgâhta **ilk parça doğrulamasını kullanıcı yapar** ve sorumluluk onundur |
| Ölçümsüz chatter lobu | FRF ölçümü olmadan doğru sayı veremeyiz; ölçümle Dalga 7'de (A13) |
| Talaş oluşumunun fizik simülasyonu, CFD, kalıp akışı, açık dinamik (çarpma), elektromanyetik | Ölçek ve doğrulama maliyeti. Doğrusal olmayan FEM (temas, plastisite) kendi çözücümüzde yok, CalculiX köprüsüyle Dalga 7'de (A12) |
| Tel erozyon, lazer, su jeti, eklemeli imalat (3B yazıcı), robotla işleme | Hedef freze ve torna |
| Çok kullanıcılı bulut, PDM/PLM, ERP bağlantısı (MES bağlantısı ise Dalga 7'de, A8) | Uygulama yerel ve tek kullanıcılı |
| Ölçülen nokta bulutundan tersine mühendislik | Kapsam dışı; ileride ayrıca değerlendirilir |
| Ticari CAM'in (ör. Mastercam, NX, hyperMILL) tüm stratejileri | Her stratejiyi kendimiz yazıp test ettiğimiz için seçici gideriz; en sık kullanılanlar önce |

## 7. Riskler ve karar bekleyen sorular

**Riskler (incelemelerden):** (1) Darboğaz kod değil onay; dalga başına tek toplu yazılı onay sürmeli.
(2) Gerçek tezgâh doğrulaması hiç yapılmadı; G1 bitmeden "atölyede kullanılır" denmemeli. (3) Dış G-code
yorumlayıcısı (rs274) CI'da her lehçe için yok; 5 eksen için de eklenmeli. (4) Büyük parçada hız ölçülmedi (G6).

**Kararlar (kullanıcı, proje sohbeti kartları, 2026-10-18 10:57):**
1. **Dalga 6 kapsamı: Tam.** B0–B1 arayüz PR'ları + G1–G9. SPEC'ler Dalga 5 ilerleyince başlar.
2. **Windows kurulumu (G8): önce `uv` betiği.** Yeni bağımlılık yok; yetmezse paketleyici için ayrıca sorulur.
3. **DNC (A7): şimdilik yalnız dosyaya yazma.** Tezgâha doğrudan gönderme Dalga 7 sonunda ayrıca karara bağlanır.

4. **MES bağlantısı (A8): Dalga 7** (11:00).
5. **Serbest yüzey + görünüm (A9): Dalga 7'de basit** (11:00).
6. **Malzeme ve analiz eklemeleri: hepsi** (11:07): Dalga 6'ya B2, G10, G11; Dalga 7'ye A10–A13.

**Kullanıcı bilgisi (11:09):** tezgâhlar **DMG MORI**; MES kendi tasarımı, yerelde TypeScript + PostgreSQL.
DMG MORI'de kontrolör genelde Siemens Sinumerik 840D sl veya Heidenhain TNC 640 (CELOS altında), bazı torna ve eski
modellerde Mitsubishi/Fanuc tabanlı MAPPS. Sinumerik ve Heidenhain SPEC 31'de var. 5 eksen (DMU) ve torna-freze
(CTX/NTX) yaygın olduğundan G2 (mill-turn), G3–G4 (5 eksen) ve G1 (gerçek tezgâh doğrulaması) bu tezgâhlara göre önceliklenir.

7. **G1 doğrulama sırası (varsayılan, 11:16):** önce Siemens Sinumerik 840D sl profili, ikinci Heidenhain TNC 640.
   Kullanıcı kuralı (11:14): kendisini bekleyen öneri 2 dakikada cevapsız kalırsa kabul edilir. Tezgâh modeli yazılırsa sıra güncellenir.
8. **MES bağlantı yolu (A8): yerel REST API** (11:16, aynı kuralla kabul). Tezgah MES veritabanına yazmaz.

**Tezgâh parkı (kullanıcı, 11:56):** DMG MORI DMU 50, 60, 75, 90; DMF 360; NTX 3000; NHC 5000; NLX 2500/700.

| Tezgâh | Tür | Bizim için anlamı (kinematik genel bilgi; kontrolör tezgâh başında doğrulanacak) |
|---|---|---|
| DMU 50 / 60 / 75 / 90 | 5 eksen dik işleme merkezi, döner-devrilir tabla (B + C) | SPEC 41 masa-masa kinematiği, 42–44; 3+2 ve eş zamanlı 5 eksen |
| DMF 360 | Hareketli kolonlu, devrilir kafa (B) + tabla, uzun parça | Kafa-masa kinematiği (41'de var); 44'te büyük strok sınırları |
| NHC 5000 | Yatay işleme merkezi, döner tabla (B), palet | 4 eksen (indeksli B): 41'in tek döner eksen hâli; palet değiştirme 30'a ek |
| NLX 2500 / 700 | Torna (taretli, canlı takım, isteğe bağlı Y) | SPEC 20–22 ve G2 (C/Y ekseni) |
| NTX 3000 | Torna-freze, B eksenli freze mili + alt taret, iki ayna | En karmaşığı: G2 + 5 eksen + iki ayna senkronu; G2'ye ek bölüm |

8a. **G1 doğrulama sırası (varsayılan, 11:56):** basitten karmaşığa, her adım bir öncekinin güvenini taşır:
   1) NLX 2500 (2 eksen torna) → 2) DMU 50 (3 eksen, sonra 3+2) → 3) NHC 5000 (4 eksen) → 4) DMU 75/90 eş zamanlı 5 eksen
   → 5) DMF 360 → 6) NTX 3000. Lehçe her tezgâhın kontrolörüne göre seçilir (Sinumerik önce, Heidenhain ikinci; 11:16).
8b. **Olası yeni hat G12, MAPPS lehçesi (varsayılan):** NLX, NHC ve NTX'te sık görülen Mitsubishi/Fanuc tabanlı DMG MORI
   MAPPS kontrolörü çıkarsa Fanuc lehçesinin bir alt lehçesi olarak eklenir; kontrolörü kullanıcı tezgâh panelinden (CELOS / MAPPS
   ekranı, Siemens / Heidenhain / Mitsubishi logosu) teyit eder.
