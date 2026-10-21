# Dalga 5 önerisi: tasarımdan tezgâha tek akış

> Durum: **kapsam onaylandı: Tam** (kullanıcı, 2026-10-18 10:51 UTC, proje sohbeti kartı). Hatların SPEC metinleri ayrıca onaylanır.
> İlk hâli öneri (2026-10-18). Onaylanınca satırları `docs/yol-haritasi.md`'ye sahibi ("Eskiz ve etkileşimli
> modelleme" thread'i) taşır. Bu belge kod içermez.
> Kaynaklar: `docs/yol-haritasi.md` ve `DURUM.md` (main, `6eb07ec`), `specs/`, `/mnt/project-files/specs-taslak/`,
> iki sert inceleme (`/mnt/project-files/inceleme/`), önceki öneri (claude.ai artifact c20eb184), SPEC'lerin "Kapsam dışı" bölümleri.

## 1. Kısa cevap

Dalga 3–4 bitince elimizde freze ve torna yolları, G-code, iki simülasyon, otomatik işlem planı (29),
tezgâh profilleri (30–31), 3+2 / 5 eksen (41–44), montaj ağacı + kısıt + girişim ve üç Tezgah ekranı olacak.
Eksik olan şey **parçaların birbirine bağlanması** ve **atölyenin gerçekten kullanacağı katman**:

1. **Tek uygulama yok.** Modelleme (26), freze (24), torna/montaj (25) ayrı ekranlar; ortak proje dosyası,
   geri al, ekranlar arası tek iplik yok. Her yeni ekran aynı `tezgah/sunucu.py` dosyasına yazıyor (çakışma noktası).
2. **CAM'de güvenlik ve verim katmanı eksik:** rampa/helis giriş (03c), kılavuz/punta/havşa çevrimleri,
   adaptif kaba (19), 3B kalan malzeme, kesme kuvveti / iş mili gücü, ilerleme optimizasyonu.
3. **Montaj durağan:** hareket (eklem, sürükleme, dinamik çarpışma), tolerans yığılımı, bağlama/fikstür ile
   CAM bağlantısı (10), standart parça yok.
4. **Modelleme doğrusal:** özellik ağacı ve kararlı yüz referansı (18), revolve, desen, ayna yok.
5. **Uçtan uca kanıt yok:** "model → plan → simülasyon → G-code → dış yorumlayıcı → montaj" zincirini
   tek testte koşan bir altın senaryo yok.

Öneri: **Dalga 5 = 4 kısa arayüz PR'ı + 17 paralel hat (H1–H17).** Hatların her biri kendi yeni dosyalarına yazar;
paylaşılan dosyalar yalnız arayüz PR'larında ve tek sahipli olarak değişir. Hiçbir hat yeni bağımlılık istemiyor.

## 2. Hedefe göre boşluk tablosu

| Hedef alanı | Dalga 4 sonunda var | Boşluk (Dalga 5) |
|---|---|---|
| Freze CAM | 03, 03b, 04, 05, 06, 06b, 14, 27, 29, 30, 31 | 03c rampa/helis; G84/punta/havşa; 19 adaptif kaba; 3B kalan malzeme; kesme kuvveti, güç, ilerleme optimizasyonu |
| Torna CAM | 20, 21, 22, 28, 29 (torna kısmı) | Torna delme/punta, ters bağlama, torna tezgâh profili (30'un ertelenmiş eki), profilli kanal |
| Çok eksen | 41–44 | Tezgah ekranı (şimdilik yok) |
| Montaj | 07, 08, 09, 25 | Eklem ve hareket, dinamik çarpışma, tolerans yığılımı, montaj sırası, standart parça, 10 montaj-CAM / fikstür |
| Katı modelleme | 02, 16, 17, 23, 26 | 18 özellik ağacı + kararlı referans, revolve, desen/ayna, pah/fillet adımı |
| Tek uygulama / UX | 24, 25, 26 (ayrı ekranlar) | Proje dosyası, kabuk + ekran kaydı, geri al, komut paleti, 29 / 41–44 / analiz ekranları |
| Atölye çıktısı | G-code, teknik resim (16) | İş föyü (takım listesi, bağlama resmi, WCS, süre), `docs/tezgah-dogrulama.md` (inceleme M6'da hâlâ yok) |
| Analiz | 01, 11, 12, 13 | Modal (öz frekans), kesme kuvveti altında parça/fikstür sehimi (CAM ↔ FEM köprüsü) |
| Kanıt | Birim + benchmark, LinuxCNC rs274, CalculiX | Uçtan uca altın senaryo |

## 3. Dalga 5.0 — önce arayüz PR'ları (kısa, dosya sahibine göre paralel)

Kurala göre arayüz değişikliği ayrı PR + ayrı test thread'i ister. Dört PR **aynı anda** yürür çünkü her biri
farklı dosyadadır; hatların SPEC metinleri bu sırada yazılır.

| # | Arayüz PR'ı | Dosya (sahip thread) | İçerik | Kim kullanır |
|---|---|---|---|---|
| A0 | CAM Ek 3 | `cam/model.py` ("CAM model arayüzü") | `ToolKind`: `TAP`, `SPOT`, `CHAMFER`; `EntryMode` (dalma / rampa / helis, açı, yarıçap); `Fixture` (şekilli bağlama gövdesi: `Part` referansı + konum); `MachineProfile.spindle_power_kw`, `spindle_torque_nm` | H1, H2, H4, H9 |
| A1 | Montaj eklemleri | `assy/model.py` ("Dalga 2 arayüz ekleri") | `Joint` (döner, kayar, silindirik, küresel, sabit; sınırlar), `Tolerance` (nominal, alt, üst, dağılım) | H7, H8 |
| A2 | Kararlı referans | `geometry/part.py` ("Dalga 2 arayüz ekleri", A1'den sonra aynı thread) | Yüz/kenar için kalıcı ad (`FaceRef`: üreten özellik + yerel ad), `Part.find(ref)` | H12 |
| A3 | Tezgah kabuğu | `tezgah/sunucu.py`, `tezgah/arayuz/src/` ("Tezgah uygulaması") | Ekran kaydı: her ekran kendi `tezgah/ekranlar/<ad>.py` (FastAPI `APIRouter`) ve `src/ekranlar/<ad>.ts` dosyasında; sunucu ve ön yüz listeden yükler. 24, 25, 26 birleştikten sonra | H13, H14 |

A3 en önemli paralellik açıcısıdır: bundan sonra yeni ekranlar `sunucu.py`'ye, `paneller.ts`'e dokunmaz.

## 4. Paralel hatlar

Her hat = bir SPEC = bir dal = bir PR (+ ayrı test thread'i). "Başlar" sütunu: SPEC metni **hemen** yazılabilir;
kod, listelenen PR'lar `main`'e girince başlar. Numaralar boştaki kimliklerdir; sıra değildir.

### CAM (freze ve torna)

| Hat | SPEC | Gerekçe | Bağımlılık (kod) | Dokunduğu dosyalar |
|---|---|---|---|---|
| **H1** | 03c rampa / helis giriş | Merkezden kesmeyen takımla cepte düz dalma hâlâ tek seçenek (inceleme H6); 29 helisi kapsam dışı bırakıyor | A0, 03b | `cam/giris.py` (yeni), `tests/cam/test_giris.py` |
| **H2** | 04b kılavuz, punta, havşa çevrimleri (G84, G82, pah takımı) | 23 dişli delik ve havşa üretiyor ama hiçbir şey onları işlemiyor; 29 bunları "planlanamadı" listesine atıyor | A0, 30, 31 | `cam/cevrimler.py` (yeni), 30'un lehçe dosyalarına yalnız yeni blok tipleri (30 sahibiyle sıralı) |
| **H3** | 19 adaptif / trokoidal kaba | Sabit temas açısı = takım ömrü ve hız; ticari CAM'in standart özelliği | 03, 05 (main'de) | `cam/adaptif.py` (yeni) |
| **H4** | 32 kesme kuvveti, güç, ilerleme optimizasyonu | Kienzle `Fc = kc1.1·b·h^(1−mc)`, `P = Fc·vc/60000`; 05/22'nin hareket başına kaldırılan hacminden iş mili gücü denetimi ve sabit talaş kalınlığı için ilerleme ayarı. Analitik test edilir; atölyede doğrudan süre kazancı | A0, 05, 14, 22, 30 | `cam/kuvvet.py`, `cam/ilerleme_opt.py` (yeni) |
| **H5** | 39 kalan malzeme ve işlenmiş parça | 05'in son stoğundan 3B kalan malzeme bölgesi → 06/06b ile kalan malzeme işleme; simüle edilen parçadan ağ (STL) ve CAD'e sapma haritası (25'in kapsam dışı "işlenmiş şekil"i) | 05, 06b | `cam/kalan3d.py`, `cam/sim/ikiz.py` (yeni) |
| **H6** | 40 torna ekleri | Torna delme/punta, ters bağlama (`z → −z`), profilli kanal, torna tezgâh profili (30'un ertelenmiş bölümü) | 21, 22, 29, 30 | `cam/torna_ek.py` (yeni), `cam/machine/` içinde yalnız torna profili dosyası (30 sahibiyle sıralı) |

### Montaj

| Hat | SPEC | Gerekçe | Bağımlılık (kod) | Dokunduğu dosyalar |
|---|---|---|---|---|
| **H7** | 33 montaj kinematiği | Eklemler, Grübler serbestlik sayımı, sürükleyerek hareket (08 çözücüsü + 17'deki sürükleme mantığı), hareket boyunca çarpışma (09 ile süpürme) | A1, 08, 09 | `assy/kinematik.py` (yeni) |
| **H8** | 34 tolerans yığılımı | 1B zincir en kötü durum ve RSS, Monte Carlo; 3B için 08'in Jacobian'ı. Kapalı formla doğrulanır; ticari CAD'de ayrı ücretli modül | A1, 08 | `assy/tolerans.py` (yeni) |
| **H9** | 10 montaj-CAM ve bağlama kütüphanesi | Parametrik mengene, ayna, pabuç; montajdaki parçayı bağlamasıyla CAM'e gönderme; 05 simülasyonunda şekilli fikstür çarpması | A0, 05, 07, 09, 14 | `cam/baglama.py`, `geometry/baglama_parca.py` (yeni) |
| **H10** | 35 standart parça ve otomatik eşleme | ISO civata, somun, pul, pim, rulman (parametrik, uydurma değil standart ölçü); 23'ün delik kaydından civata önerisi ve eş eksen mate | 07, 08, 23 | `geometry/standart/` (yeni alt paket), `assy/oneri.py` (yeni) |
| **H11** | 36 montaj sırası ve demontaj yolu | 25 sırayı elle alıyor; girişimsiz sökme yönlerinden sıra çıkarma | 09 | `assy/sira.py` (yeni) |

### Modelleme ve tek uygulama

| Hat | SPEC | Gerekçe | Bağımlılık (kod) | Dokunduğu dosyalar |
|---|---|---|---|---|
| **H12** | 18 özellik ağacı | 26'nın doğrusal geçmişini ağaca çevirir; kararlı yüz referansı, revolve, pah/fillet adımı, desen, ayna | A2, 17, 26 | `geometry/agac.py` ve hat thread'inin aldığı ek dosya (yeni); `geometry/revolve.py` SPEC 28'in iskeletidir, dokunulmaz |
| **H13** | 37 proje dosyası ve kabuk | Tek `.3dc` proje (zip içinde JSON + ikili): model ağacı, montaj, CAM planı, tezgâh profili, sim önbelleği; geri al / yinele; komut paleti; ekranlar arası tek iplik (modelde değişen ölçü → CAM ve montaj yeniden hesap, farkı gösterir) | A3, 24, 25, 26 | `fileio/proje.py` (yeni), `tezgah/ekranlar/kabuk.py`, `src/ekranlar/kabuk.ts` |
| **H14** | 47 Tezgah ekranları: otomatik CAM, çok eksen, analiz | 29, 41–44, 12–13 kütüphane olarak bitiyor ama ekranı yok. Üç ekran ayrı dosyada olduğu için üç alt PR paralel | A3 + ilgili SPEC | `tezgah/ekranlar/{plan,cok_eksen,analiz}.py`, `src/ekranlar/{plan,cok_eksen,analiz}.ts` |

### Atölye, analiz, kanıt

| Hat | SPEC | Gerekçe | Bağımlılık (kod) | Dokunduğu dosyalar |
|---|---|---|---|---|
| **H15** | 38 iş föyü ve tezgâh doğrulama belgesi | Operatörün tezgâh başında okuduğu sayfa: takım listesi ve boyları, bağlama resmi (16), WCS, süre, ilk parça ölçüm listesi; HTML/SVG çıktı (yeni bağımlılık yok, tarayıcıdan PDF). `docs/tezgah-dogrulama.md` burada yazılır | 14, 16, 29 | `atolye/` (yeni paket), `docs/tezgah-dogrulama.md` (yeni) |
| **H16** | 45 modal analiz ve kesme kuvvetinde sehim | Öz frekans (Lanczos, scipy) ve H4 kuvvetiyle ince duvarlı parçada sehim: CAM ↔ FEM'in ilk gerçek bağı | 12, 13 (H4 sonra) | `core/modal.py`, `mesh/` değil; `analiz/` (yeni köprü paketi) |
| **H17** | 46 uçtan uca altın senaryo | Uydurma flanş + mil + montaj: 26 ile modelle → 29 plan → 05/22 sim → 04/21/30 G-code → LinuxCNC rs274 → 09 girişim. "Tasarımdan tezgâha" iddiasının tek testi | 24–29 | `tests/uctan_uca/` (yeni klasör, kod yok) |

Sıralama notu: H17 kod yazmaz, yalnız mevcut herkese açık fonksiyonları zincirler; test bağımsızlığı kuralına
doğal olarak uyar ve diğer hatların birleşmesini bekleyerek kademeli büyür.

## 5. Çakışma haritası (paralellik kanıtı)

| Paylaşılan nokta | Risk | Çözüm |
|---|---|---|
| `cam/model.py`, `assy/model.py`, `geometry/part.py` | Birden fazla hattın alan eklemesi | Yalnız A0–A2'de, tek sahipli; hatlar bu dosyalara dokunmaz |
| `tezgah/sunucu.py`, `paneller.ts`, `sahne.ts` | 24, 25, 26 ve her yeni ekran | A3 ekran kaydı; sonra her ekran kendi dosyasında |
| `cam/gcode/` ve 30'un lehçe dosyaları | H2 ve H6 yeni blok ister | 30/31 sahibi thread'e sıralı küçük ekler; H2 ve H6 hesaplarını kendi dosyalarında yapar |
| `pyproject.toml` | Yeni paketler (`atolye`, `analiz`) paket listesine girer | Tek bir ortak PR ("Durum tablosu ve kurulum belgeleri" sahibi) iki paketi birlikte ekler |
| `DURUM.md`, `docs/yol-haritasi.md` | Her birleşme | Mevcut sahipler; hatlar yalnız `durum/NN-*.md` yazar |
| `cam/sim/` (05) | H4 ve H5 sim çıktısını okur | Yalnız okur; 05'in imzaları değişmez (43'teki kural) |

Aynı anda **17 hat + 4 arayüz PR'ı** = en çok 21 SPEC thread'i ve 21 test thread'i. Hatların hiçbiri başka
bir hattın dosyasına yazmaz; bağımlılıklar yalnız "kod ne zaman başlar"ı belirler.

## 6. Önerilen başlatma sırası (en hızlı yol)

1. **Hemen (Dalga 4 sürerken):** 17 hattın SPEC metinleri ve A0–A2 arayüz PR'ları. Bağımlılığı tamamen `main`'de olan
   H3 (adaptif kaba: 03, 05) ve H10 (standart parça: 07, 08, 23) SPEC onaylanınca koda geçer.
2. **A1 birleşince:** H8 (tolerans). **A1 ve 09 birleşince:** H7 (kinematik). **09 birleşince:** H11 (montaj sırası).
3. **06b birleşince:** H5 (3B kalan malzeme). **A2, 17 ve 26 birleşince:** H12 (özellik ağacı).
4. **12 ve 13 birleşince:** H16 (modal; sehim kısmı H4'ten sonra).
5. **24, 25, 26 birleşince:** A3, ardından H13 ve H14'ün üç ekranı.
6. **A0 ile birlikte 27, 29, 30, 31 (ve hattın kendi listesindeki diğerleri) birleşince:** H1, H2, H4, H6, H9, H15.
7. **Sürekli:** H17 altın senaryo her birleşmede bir halka büyür; bittiğinde Dalga 5 biter.

Onay darboğazı (ikinci inceleme, "Sistem hakkında" 1): kullanıcı her hat için ayrı kart yerine **dalga başına tek
toplu yazılı onay** verirse (09:46'da denendi, işe yaradı) 17 SPEC metni tek mesajla açılır.

## 7. Dalga 6'ya bırakılanlar

C / Y eksenli torna-freze (mill-turn), 5 eksen kaba işleme, ısıl analiz, FEM ile parametre optimizasyonu,
çok kullanıcılı çalışma, DNC ile tezgâha gönderme, 3B diş (helis) simülasyonu.

## 8. Karar (verildi)

Kullanıcı 2026-10-18 10:51 UTC'de proje sohbetindeki kartta **Tam** kapsamı seçti: 4 arayüz PR'ı + 17 hat birlikte
başlar. Hatların SPEC metinleri 10:53'te açılan ayrı thread'lerde yazılıyor; her metin yine kullanıcı onayı ister.
`docs/yol-haritasi.md` için satırlar: `yol-haritasi/dalga-5-yol-haritasi-satirlari.md`.
