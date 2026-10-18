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
