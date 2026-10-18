# Tezgâh doğrulama — üretilen G-code'u ilk kez çalıştırmadan önce

Bu liste 3D-CORE'un ürettiği bir programı (SPEC 04 yazıcısı, SPEC 14 kurulumu) gerçek tezgâhta **ilk kez**
çalıştırmadan önce operatörün yapacağı kontrolleri sıralar. Testi yoktur; tezgâhta insan uygular.
Bir madde tutmazsa program çalıştırılmaz, sebep bulunur.

## 1. Masa başında (tezgâhtan önce)
- [ ] Program `write(..., setup=...)` ile yazıldı: bağlama denetimi (`check_setup`) hatasız geçti.
- [ ] Takımlar `check_tools(kütüphane, op'lar)` ile denetlendi: programdaki her `T<n>` kütüphanedeki takım.
- [ ] Yol bir simülatörde / görüntüleyicide gözden geçirildi (SPEC 05, 15): hızlı hareket (`G0`) malzemeye
  veya bağlamaya girmiyor, son geri çekme güvenli Z'de.
- [ ] Program başı doğru: birim `G21` (mm), `G90` (mutlak), `G17`, iş sıfırı kodu (`G54`..`G59`) bağlamadaki
  ile aynı.
- [ ] Devir ve ilerleme kesme verisinden hesaplandı (`cam.cutting`); `S` tezgâhın en yüksek devrini aşmıyor.

## 2. İş sıfırı (WCS)
- [ ] Programdaki iş sıfırı kodu (ör. `G55`) kontrolde de aynı kayda girildi; başka bir kayıt değil.
- [ ] X ve Y kenar bulucu ile alındıysa çap payı hesaba katıldı (`edge_position`: yüzey = `m + yön·d/2`).
- [ ] Z sıfırı malzeme üstünde: referans takımla (GRBL) veya ölçü hattı yöntemiyle (Fanuc) alındı.
- [ ] İş sıfırı girildikten sonra takım parça köşesine yavaşça götürülüp ekrandaki iş koordinatı okundu.

## 3. Takım boyu
**Fanuc (`G43 H<n>`)**
- [ ] `fanuc_offset_table(kütüphane, takımlar)` tablosu ofset ekranına girildi: her `H<n>` = takımın ölçü boyu
  `L_n` (tutucu ölçü boyu + taşma).
- [ ] Her takım takıldıktan sonra taşma boyu cetvel / ön ayar cihazıyla ölçüldü; kütüphanedeki `stickout` ile
  aynı (fark > 0.05 mm ise kütüphane düzeltilir, program yeniden yazılır).
- [ ] Programdaki her `G43` satırında `H` numarası takım numarasıyla aynı.

**GRBL (`G43.1 Z<ΔL>`)**
- [ ] Z sıfırı programın **referans takımıyla** (genellikle ilk takım) alındı.
- [ ] `probe_program` ile ölçüm programı çalıştırıldı; her takım için GRBL'in bildirdiği `[PRB:x,y,z:1]`
  değerindeki `z` not edildi.
- [ ] `offsets_from_probe(okumalar, ref)` ile bulunan ofsetler `verify_offsets(ölçülen, length_offsets(...))`
  ile kütüphaneyle karşılaştırıldı; hata yok.
- [ ] Program, ölçülen ofsetlerle (`length_offsets=ölçülen`) yeniden yazıldı.
- [ ] Takım değişiminde (`T<n> M0`) program durunca **doğru takım** takıldı; devam edilince sıradaki satır
  `G43.1 Z…` ve ardından `S… M3`.

## 4. Kuru çalıştırma (havada)
- [ ] İş sıfırının Z'si geçici olarak +50 mm (veya malzeme boyundan fazla) yukarı kaydırıldı ya da tezgâhın
  kuru çalıştırma / Z kilidi özelliği açıldı.
- [ ] Hızlı hareket oranı %25 veya altında, ilerleme oranı %50 veya altında.
- [ ] Tek blok (single block) açık; ilk takımın ilk inişi satır satır izlendi.
- [ ] Program sonuna kadar havada çalıştı; takım değişimleri, geri çekmeler ve son konum beklendiği gibi.
- [ ] İş sıfırının Z'si geri alındı (kaydırma unutulmadı).

## 5. İlk parça
- [ ] İlk kesmeye kadar tek blok; takım malzemeye girerken ilerleme oranı %25–50.
- [ ] Her yeni takımın ilk inişinde durulup kalan mesafe (ekrandaki "kalan") ile takım–malzeme arası gözle
  karşılaştırıldı.
- [ ] Soğutma, talaş tahliyesi ve ses normal; anormal ses veya titreşimde ilerleme tutma / acil durdurma.
- [ ] İlk parça tezgâhtan çıkmadan ölçüldü (kritik ölçüler, derinlikler); sapma varsa takım boyu / çap ofseti
  ve iş sıfırı yeniden kontrol edildi.
- [ ] Ölçüm sonuçları ve yapılan düzeltmeler kayda geçti; düzeltme kütüphaneye işlendi.

## 6. İş föyü
İş föyü (SPEC 38, `atolye/`) bu listenin **yanında** kullanılır, yerine geçmez: genel maddeler (1–5) her programda
aynıdır, föy ise bu işe özel değerleri (kayıt kodu, ofsetler, kaydırma boyu, ölçüm kalemleri) verir.

Föy şöyle üretilir:
```python
from atolye import build_job_sheet, write_job_sheet  # SPEC 29 planından: atolye.from_mill_plan

job = build_job_sheet("Parça adı", [setup], [ops], kutuphane, "al", dialect=GRBL, machine=makine, n_max=12000)
write_job_sheet(job, "cikti/is-foyu")  # is-foyu.html + baglama-<i>.svg; tarayıcıda açıp "Yazdır" → PDF
```
Föy güvensiz program için üretilmez: `check_tools` ve `check_setup` hatası föy yerine hata verir.

| Föydeki yer | Bu listedeki bölüm |
|---|---|
| Özet: kontrol, program no; doğrulama maddesi "En yüksek devir S… ≤ tezgâh sınırı …" | 1. Masa başında |
| Bağlama bölümü: WCS tablosu (kayıt, makine koordinatı, X0 / Y0 / Z0 tarifi) ve bağlama resmi | 2. İş sıfırı |
| Takım tablosu: `L`, Fanuc `H` veya GRBL `G43.1 ΔL` (referans takım), gerekli kesici boy | 3. Takım boyu |
| Doğrulama maddesi "Kuru çalıştırma: G5x Z'si +h mm kaydırıldı"; işlem tablosu ve süreler | 4. Kuru çalıştırma |
| İlk parça ölçüm listesi (ISO 2768-1 genel tolerans, "Ölçülen" sütunu boş) | 5. İlk parça |

Föydeki her doğrulama maddesi `data-bolum` ile yukarıdaki bölüm numarasına bağlıdır; bu yüzden bölüm 1–5'in
başlık numaraları değiştirilmez. Süreler SPEC 05 modeline göre tahmindir (yazıcının eklediği güvenli Z geri
çekmeleri ve bağlama değişimi hariç); tezgâhtaki gerçek süre kayda geçirilir.

## 7. Doğrulama programı
Bir tezgâh profili (`cam/post/profiles/*.json`) ve bir program ancak bu basamaklardan sırayla geçince güvenilir
sayılır (SPEC 48). Her basamak bir **doğrulama kaydıdır**; kodu `atolye/dogrulama.py`.

| # | Basamak | Ne yapılır | Geçme koşulu |
|---|---|---|---|
| 1 | `masa` | Bölüm 1 ve iş föyündeki bölüm 1 maddeleri; simülasyonda çarpma yok | Tüm maddeler işaretli |
| 2 | `havada` | Bölüm 2–4: iş sıfırı, takım boyları, Z'si kaydırılmış kuru çalıştırma (hızlı %25, ilerleme %50, tek blok) | Program havada sonuna kadar bitti; takım değişimi ve döner eksen yönleri beklendiği gibi |
| 3 | `mum` | Aynı program işlenebilir mum ya da sert köpükte, ilerleme %50–100 | Parça çıktı, gözle hata yok; kritik ölçüler alındı (gevşek tolerans) |
| 4 | `ilk_metal` | Aynı program gerçek malzemede (önce alüminyum), bölüm 5 | Ses, titreşim, talaş normal; kırık takım veya alarm yok |
| 5 | `olcum` | İş föyü ölçüm listesindeki **tüm** kalemler ölçülüp girilir | Her kalem `alt ≤ ölçülen ≤ üst` (ISO 2768-1) |

Mum / köpük basamağı metalden önce gelir: yanlış bir yol orada takımı ve tezgâhı kırmadan görünür. Bir tezgâhta
`havada`, `mum` ya da `ilk_metal` atlanacaksa kayda `atlandi` ve gerekçe yazılır; `masa` ve `olcum` atlanamaz.
Bir basamak `kaldi` ise neden bulunup düzeltilir ve iş `masa` basamağından yeniden başlar.

Kayıt nasıl tutulur:
1. Proje dosyasının yanında bir `dogrulama/` klasörü seçin. Kayıtlar
   `dogrulama/<profil adı>/<tarih>-<sıra>-<basamak>.json` dosyalarıdır.
2. `bos_kayit(profil, program, föy, basamak, kapsam, tarih, operatör)` doldurulacak kaydı verir: bu belgenin bölüm
   1–5 maddeleri ve iş föyünün maddeleri işaretsiz, ölçüm kalemleri (yalnız `olcum`) boş.
3. Tezgâh başında maddeleri işaretleyin, ölçülenleri girin, sonucu (`gecti` / `kaldi` / `atlandi`) ve gerekiyorsa
   gerekçeyi yazın; `kaydet(kayıt, "dogrulama", program=..., job=...)` sırayı, ölçümleri ve dosya özetlerini
   denetleyip kaydı yazar. Kural ihlali kaydı yazmaz, dosya adıyla başlayan bir hata verir.
4. `hazirlik(profil, oku("dogrulama"))` her kapsam için "hazir" ya da eksik ilk basamağı söyler; `rapor_html`
   aynı bilgiyi yazdırılabilir rapor olarak verir. Profil dosyası değişirse (kurs, kinematik…) eski kayıtlar o profil
   için sayılmaz ve rapor bunu söyler.
5. `verified: true` işaretini profil dosyasına **yalnız siz** koyarsınız; kod bu alanı hiçbir zaman yazmaz.

## 8. Tezgâh sırası
Basitten karmaşığa; her tezgâh bir öncekinin doğrulanmış kısmını taşır. "Gerekenler" o tezgâhta gerçek bir program
yazabilmek için `main`'de olması gereken SPEC'lerdir; kalın yazılanlar henüz yoktur ve o tezgâhın 4. basamaktan
sonrası onları bekler.

| Sıra | Tezgâh | Kapsam | Uydurma doğrulama parçası | Gerekenler |
|---|---|---|---|---|
| 1 | NLX 2500 | `torna_2x` | Kademeli mil (alın, boy, pah, kanal); sonra diş | 20, 21, 22, 30 Ek A, 38b |
| 2 | DMU 50 | `freze_3x`, sonra `freze_3arti2` | Prizmatik blok: yüz alma, cep, 4 delik (G83); sonra 3+2 ile 30° eğik yüz | 14, 29, 30, 31, 38, 41 |
| 3 | NHC 5000 | `freze_4x_indeks` | Aynı blokta 4 yüz, B ekseni 0/90/180/270 indeksleme | 31, 41 |
| 4 | DMU 75 / 90 | `freze_5x` | Eş zamanlı 5 eksen: SPEC 42 örnek yüzeyi | 42, 43, 44, **51** |
| 5 | DMF 360 | `freze_3arti2` (kafa-masa) | Uzun parça, kafa B ekseniyle eğik delik | 41, 44 |
| 6 | NTX 3000 | `torna_freze` | Milde radyal delik ve kama (C/Y) | **49**, B0 |

Lehçe tezgâhın kontrolörüne göre seçilir (önce Sinumerik, sonra Heidenhain); kontrolör tezgâh panelinden teyit edilip
profilin `controller` alanına yazılır. Dalga 6'nın bitmesi için ilk iki tezgâhın kayıtları şarttır.
