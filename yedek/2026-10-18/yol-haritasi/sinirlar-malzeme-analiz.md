# Sınırlar, malzeme ve analizler: gözden geçirme

> Durum: **onaylandı, hepsi** (kullanıcı, 2026-10-18 11:07); satırlar `dalga-6-ve-sonrasi.md`'ye işlendi. `dalga-6-ve-sonrasi.md`'nin eki. Onaylanan satırlar o belgeye işlenir.
> Bakılanlar: `main` (`eb70d49`) içinde `core/`, `assy/bom.py`, `cam/model.py`; `specs/00-arayuzler.md`;
> `specs-taslak/11`, `12`, `13`'ün "Kapsam dışı" bölümleri; iki sert inceleme.

## 1. Kısa cevap

- **Malzeme seçilebilecek mi?** Evet, ama bugün malzeme üç ayrı yerde, birbirinden habersiz duruyor. FEM
  `core.model.Material(E, nu, rho)` kullanıyor. BOM `assy/bom.py` içinde yoğunluğu parça başına elle alıyor.
  CAM'de `Tool.cutting` sözlüğü malzeme **adına** göre kesme verisi tutuyor. Parçanın kendisi malzeme bilmiyor.
  Önerim tek bir malzeme kütüphanesi ve "parçaya malzeme ata" adımı. Bunu bir kez seçince kütle, FEM,
  kesme verisi, kesme kuvveti, takım ömrü ve maliyet aynı kayıttan beslenir.
- **Analiz ve fizik:** Kendi çözücümüzle parça ölçeğinde (yüz binlerce serbestlik derecesi) bugünkü
  yapıya iki eleman tipi eklemek yetiyor. Bununla doğrusal statik, modal, burkulma, ısıl, termo-mekanik,
  yorulma ve kesme kuvvetinde sehim yapılabiliyor. Temas ve plastisite gibi doğrusal olmayan işler için kendi
  çözücümüzü büyütmek yerine zaten kullandığımız **CalculiX'e köprü** kurmak daha akıllıca. CFD ve talaş oluşumu
  fiziği bizim yapımızın dışında.
- **İki düzeltme:** önceki cevaplarımda chatter lobunu "yapamayız" demiştim. Kullanıcı ölçülmüş FRF verisini
  girerse yapabiliriz; ölçüm olmadan yapamayız. "Doğrusal olmayan FEM yok" da yalnız kendi çözücümüz için
  doğru; CalculiX köprüsüyle yapılabilir.

## 2. Malzeme kütüphanesi (öneri)

| Konu | Öneri |
|---|---|
| Arayüz | Yeni `malzeme/model.py` (saf Python + numpy), ayrı arayüz PR'ı + ayrı test thread'i. Paketler malzemeyi yalnız buradan okur |
| Kayıt alanları | Ad ve standart (ör. EN 1.0503 / C45, EN AW-6061-T6, 1.4404, POM-C); E, ν, ρ; Rp0.2, Rm, uzama, sertlik; yorulma sınırı veya S-N eğrisi; ısıl iletkenlik k, özgül ısı cp, genleşme α; işlenebilirlik: Kienzle `kc1.1`, `mc`, Taylor `C`, `n`, takım malzemesine göre önerilen Vc ve fz; €/kg |
| Kim kullanır | BOM kütlesi (07), FEM (11–13 ve sonrası), kesme verisi (14, 29), kesme kuvveti ve güç (32), takım ömrü (59), maliyet ve teklif (58), ısıl analiz (56), DFM (61) |
| Parçaya atama | Montajda bileşene malzeme kimliği. Bu `assy/model.py`'ye bir alan eklemek demek, yani ayrı arayüz PR'ı. Proje dosyası (37) atamayı saklar |
| Veri | Kitaplardaki tipik değerler, kaynak satırıyla ve "tipik değer" işaretiyle. Kullanıcı kendi malzemesini ve kendi ölçtüğü değerleri ekleyebilir. Uydurma veri girmez |
| Birim tuzağı | Proje N–mm–MPa sisteminde ve kodda dönüşüm yok, o yüzden kütüphane bu sistemde saklar: ρ t/mm³ (çelik 7.85e-9), k W/(m·K) ile sayıca aynı, cp mJ/(t·K) (çelik 460 J/(kg·K) = 4.6e8). Testler bu dönüşümleri bir kez sabitler; yanlış birim sessizce 10⁶ kat hata verir |
| Doğrulama | Fiziksel tutarlılık testleri: 0 < ν < 0.5, E > 0, Rp0.2 ≤ Rm, G = E / (2(1+ν)). Eksik alan istenirse `ModelError` |

## 3. Düzeltilmesi gerekenler (sınırlar ve yol haritası)

| # | Sorun | Neden önemli | Öneri |
|---|---|---|---|
| D1 | Malzeme üç yerde dağınık | Aynı parçada FEM ile CAM farklı malzeme kullanabilir | Bölüm 2; Dalga 6'ya **B2 arayüz + G10** |
| D2 | Tek 3B eleman tet4 | Doğrusal tetrahedron eğilmede çok sert kalır, gerilme düşük çıkar; ancak çok ince ağla doğru sonuç verir | **tet10** (ikinci mertebe) ekle; aynı ağda hassasiyeti kat kat artırır. Dalga 6, G11 |
| D3 | Yük ve mesnet geometrik tahminle seçiliyor (12 kapsam dışı: CAD yüz kimliği) | Kullanıcı "bu delik yüzüne kuvvet" diyemiyor | Kararlı yüz referansı (A2) ile gmsh yüz etiketini eşle. G11'in parçası |
| D4 | Montaj analizi yok (11/12 kapsam dışı: çok gövde, temas) | Gerçek parçalar tek başına değil, montajda yüklenir | Önce yapıştırılmış (bonded) montaj; temas CalculiX köprüsüyle (bkz. 4) |
| D5 | Hacim kuvveti ve ısıl yük yok (11 kapsam dışı) | Dönen parçada merkezkaç, ağırlık ve ısıl gerilme hesaplanamıyor | Yük türlerini ekle; malzeme kütüphanesine bağlı |
| D6 | Kesme verisi kaynağı belli değil | Yanlış Vc/fz takım kırar | Malzeme kütüphanesinde kaynaklı değer; 30'un tezgâh güç sınırıyla denetim (32) |
| D7 | Analiz sonucu "emniyetli mi?" demiyor | Sayı tek başına karar vermiyor | Emniyet katsayısı `n = Rp0.2 / σ_vM`, yorulmada Goodman; Tezgah'ta renkli harita |
| D8 | "Yapamayacaklar"daki iki yanlış | Chatter ve doğrusal olmayan FEM aslında kısmen mümkün | Bölüm 1'deki düzeltme; ana belgede güncellenecek |
| D9 | Gerçek tezgâh doğrulaması ve onay darboğazı | İncelemelerin en büyük iki riski | Değişmedi: G1 ve dalga başına tek toplu onay |

## 4. Hangi analiz ve fizik simülasyonları?

**Seviye 1: kendi çözücümüzle, bugünkü yapıyla.** numpy + scipy yetiyor; tet10 ve malzeme kütüphanesi ekleniyor.

| Analiz | Ne verir | Doğrulama (analitik) | Not |
|---|---|---|---|
| Doğrusal statik + von Mises + emniyet katsayısı | Gerilme, sehim, "kırılır mı" | Konsol kiriş, Kirsch delikli plaka (13), CalculiX | 11–13 var, tet10 ile güçlenir |
| Modal (öz frekans) | Titreşim frekansları ve biçimleri | Konsol kiriş frekansı `β²√(EI/ρA)/L²` | Dalga 5 H16 |
| Doğrusal burkulma | İnce çubuk/levhada kritik yük | Euler `π²EI/(KL)²` | Geometrik rijitlik matrisi + özdeğer; yeni |
| Kararlı ve geçici ısıl | Sıcaklık alanı, ısınma süresi | Duvar, silindir, yarı sonsuz cisim | G9 kararlı; geçici zaman adımlı, yeni |
| Termo-mekanik | Isıl genleşme gerilmesi ve çarpılması | Tutulu çubukta `σ = −EαΔT` | Isıl + statik zinciri, yeni |
| Harmonik tepki | Belirli frekansta zorlanınca genlik | Tek serbestlik dereceli sistem rezonansı | Modal süperpozisyon, yeni |
| Yorulma (yüksek çevrim) | Ömür, Goodman emniyeti | S-N eğrisi, Goodman doğrusu | Statik sonuçtan sonra işlem, yeni |
| Kesme kuvvetinde parça/fikstür/takım sehimi | İnce duvarda ölçü hatası, takım eğilmesi | Konsol kiriş `FL³/(3EI)` | H4 + H16, Dalga 5 |
| Mekanizma dinamiği (katı cisim) | Eklem kuvvetleri, motor torku, hız/ivme | Krank-biyel kapalı form | Kinematik (33) + Newton-Euler, yeni |
| Kütle, atalet, denge | Ağırlık merkezi, atalet tensörü, balans | Silindir ve blok formülleri | 02/07 kısmen var |
| Tolerans yığılımı | En kötü durum, RSS, Monte Carlo | Kapalı form | Dalga 5 H8 |
| Talaş kaldırma, çarpışma, kuvvet, güç | İşlenmiş parça, çakma, iş mili gücü | Hacim, Kienzle | Var veya Dalga 5'te |
| Chatter lobu (FRF girdisiyle) | Titreşimsiz devir ve paso derinliği | Altintas sıfırıncı mertebe çözümü | Kullanıcı çekiç testi FRF'sini girer; girmezse hesap `ModelError` |
| Takım ömrü, talaş sıcaklığı (analitik) | Takım değişimi, kesme sıcaklığı | Taylor; Loewen–Shaw | Dalga 7 A3 |

**Seviye 2: CalculiX köprüsüyle.** 13'teki `.inp` yazıcısı genişletilir. CalculiX aynı ağda çözer, sonucu biz okur
ve Tezgah'ta gösteririz. Kendi çözücümüz bunlar için büyütülmez.

- Temas: montaj parçaları arası, civata ön yükü, sıkma.
- Plastisite: kalıcı eğilme, akma sonrası davranış.
- Büyük şekil değişimi.
- Doğrusal olmayan ısıl.
- Kaynaklı veya preslenmiş geçme gerilmesi.

Bunların doğrulaması CalculiX'in kendi örnekleri ve kapalı formlu durumlarla (ör. sıkı geçmede Lamé) yapılır.

**Seviye 3: bu yapıda yapmayız.**

- CFD: soğutma sıvısı, hava akışı. OpenFOAM gibi ayrı bir dünya gerektirir.
- Talaş oluşumunun FEM simülasyonu.
- Çarpma ve patlama gibi açık (explicit) dinamik.
- Kalıp dolum ve döküm.
- Elektromanyetik.
- Kompozit katman analizi.

## 5. Mevcut yapıyla ne kadar ileri gidebiliriz?

| Sınır | Bugünkü yapı | Pratik tavan | Aşmak için |
|---|---|---|---|
| FEM boyutu | scipy seyrek doğrudan çözücü, Python'da eleman döngüsü | Dizüstünde ~200–500 bin serbestlik derecesi (orta karmaşık bir parça, tet10 ile) | Yinelemeli çözücü (CG + ön koşullayıcı) scipy ile birkaç milyon; daha fazlası için yeni bağımlılık (karar) ya da CalculiX |
| Analiz türü | Doğrusal | Seviye 1'in tamamı | Seviye 2 için CalculiX köprüsü |
| Talaş simülasyonu | z-map, dexel, tri-dexel (numpy) | 200×200 mm parça, 0.05 mm çözünürlük (~16 milyon hücre) | G6 performans; ince ayrıntıda yerel çözünürlük |
| Katı model | OCCT | Yüzlerce parçalık montaj | Ağır parçada sadeleştirilmiş görünüm (LOD) |
| Uygulama | Yerel, tek kullanıcı, tarayıcı | Bir mühendisin masası ve atölye | Çok kullanıcı kapsam dışı; MES bağlantısı Dalga 7 (A8) |

Özet: **parça ve küçük montaj ölçeğinde** tasarım, imalat ve doğrusal mühendislik analizinin hepsi bu yapıda
yapılabiliyor. Doğrusal olmayan analiz CalculiX'le mümkün. Araç ölçeğinde büyük montaj analizi ve akışkan
bizim hedefimizin dışında.

## 6. Yol haritasına eklenecekler (karar bekliyor)

| Nereye | Kod | Ne |
|---|---|---|
| Dalga 6 | B2 | `malzeme/model.py` arayüzü + `assy/model.py`'de bileşene malzeme kimliği |
| Dalga 6 | G10 | Malzeme kütüphanesi (kaynaklı tipik değerler, kullanıcı malzemesi), BOM/FEM/CAM'e bağlama |
| Dalga 6 | G11 | tet10 + CAD yüzüne yük/mesnet + hacim kuvveti ve ısıl yük + emniyet katsayısı |
| Dalga 7 | A10 | Burkulma, geçici ısıl, termo-mekanik, harmonik, yorulma |
| Dalga 7 | A11 | Mekanizma dinamiği (eklem kuvveti, motor torku) |
| Dalga 7 | A12 | CalculiX köprüsü: temas, plastisite, büyük şekil değişimi; sonuç Tezgah'ta |
| Dalga 7 | A13 | Chatter lobu (kullanıcının FRF ölçümüyle) |
