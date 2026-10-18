# DURUM — SPEC 25 tezgah-torna-montaj

Dal: `claude/project-thread-udniip` · PR #48 · Oturum: bulut

## Sıradaki adım
Kod yazıldı. Torna yarısı (K1–K7, K15, e2e'nin torna kısmı) SPEC 22 (`cam.sim.simulate_lathe`, `part_rmap`) `main`'e
girmeden çalışamaz: SPEC 22 birleşince `main` bu dala merge edilir, torna testleri ve e2e koşulur, yeşilse PR birleşir.

## Test durumu
| Tarih | Geçen | Kalan | Not |
|---|---|---|---|
| 2026-10-18 | 179 (tests/tezgah) | 21 | Kalan 21'in hepsi `ImportError: cam.sim.part_rmap` (SPEC 22 henüz main'de değil). |

## Son oturum
**2026-10-18**
- Testler: `34964ef` (test oturumu, dal `claude/project-thread-gf1tz2`) ve bbox düzeltmesi `72c818f` cherry-pick edildi.
- Kod: `tezgah/torna.py` (SPEC 21 yazıcı/okuyucu + SPEC 22 sim köprüsü, K1–K7), `montaj.py` (K8–K14),
  `iplik.py` (K15–K16 parametre deposu, ikiye bölme önerisi), `ornekler_25.py` (`kademeli_mil`, `yatak_grubu`),
  `sunucu_25.py` (uçlar), ön yüz `arayuz/src/` (torna ve montaj ekranları).
- Test yazarının SPEC'in belirtmediği şema seçimleri, koordinatör kabul etti (11:30):
  1. K1: `plane`, `feed_mode`, `css`, `rpm` her `Is["islemler"][i]` içinde `Toolpath` alan adlarıyla, enum değeriyle.
  2. K3: `gcode[i]["dro"] = {"X": 2x, "Z": z}`, hareketsiz satırda `None`.
  3. K8: `kutle.merkez = mass_center(apply(agac, çözülmüş))`; `agac` tanımın `to_dict()`'i (çözülmemiş);
     `bom = dataclasses.asdict(BomLine)`.
  4. K9: alt montaj flatten'in başlangıç T'leriyle kurulur, `T_sonra` her adımda yerleşmiş tüm yolları taşır;
     K11: `T_once` yalnız adımın kendi bileşeni için verilir.
  5. K13: serbestlik kontrol kimlikleri `serbestlik` ile başlar; ayrıca `kisit_artigi`, `girisim`, `kutle`.
  6. K15: `sure_farki` = yeni − eski toplam süre.
  7. K18 e2e: `window.__tezgah`'a `ekran()`, `kesitAcik()`, `capModu()`, `seciliIslem()`, `montajU()`, `montajPoz(yol)`;
     data-testid'ler `sekme`, `montaj-seridi`, `girisim-karti`, `oner`, `uygula`, `sure-farki`, `tornada-goster`.
  8. K2: SPEC 21 çevrim yazmadığı için her hareket satırı tek grup.
- Kod tarafındaki tasarım kararları:
  - `torna.KALAN_ORAN = 1e-3`: kalan malzeme hacmi parça hacminin bu oranını aşarsa `kalan_malzeme` uyarı.
  - Vida ekseni (K10): sıfır uzayın dönme bileşeni ω için eksen yönü ω/|ω|, nokta `t + ω×Δt/|ω|²` (dünya),
    hatve `ω·Δt/|ω|²`; ötelemeler ve eksene hizalı dönmeler ayrı etiketlenir (`Tx`…, `Rx`…).
  - `kademeli_mil`: kaba / ince / kanal alın yüzü alınmış ham (zmax = 0) üzerinde; profil SPEC 28 `turn_profile`
    dış çizgisinden, ham yarıçapına (25) ulaşan uç segmentler atılarak. Ø44 üzerinde Ø50 omzuna dayalı 3 × 1 kanal.
  - Bilinmeyen iş/anahtar bağı → `CamError` (sunucuda 422); bilinmeyen montaj / parça / girişim indisi → 404.
  - Müfettiş: `POST /api/ekran/torna/is/{ad}/parametre {islem, anahtar, deger}` (SPEC 24 biçimi) → `{sema, is, sure_farki}`;
    değiştirilebilen kesme değerleri `ornekler_25.ISLEM_VARSAYILAN` (Vc, f, n_max / n, a_p). "paso 2" komutu bunu kullanır.
  - A3 (specs/24a) taşıması (koordinatör kabulü 12:08): uçlar `tezgah/ekranlar/torna.py` (`/api/ekran/torna/is/{ad}…`) ve
    `montaj.py` (`/api/ekran/montaj/…`), router'lar `sunucu_25.py`'de. Parametreler tek yerde (`sunucu_25.DEPO`, `iplik.Depo`):
    "torna_isleri" bölümünü torna ekranı dışa/içe aktarır (SPEC 37 tablosu: `{"sema", ad: {"parametreler",
    "islem_parametreleri"}}`, yama işaretçisi `/kademeli_mil/parametreler/L`); montaj bağı aynı depoya yazar, `bagimli=("torna_isleri",)`.
    "montajlar" bölümü yalnız adlar. Bilinmeyen torna işi / montaj / parça / girişim → 404 (router'da).
    Dinamik torna işleri (`is_kaydet`): `sunucu_25.kaydet` / `adlar`, `depo.kaydedici_ekle` kancasıyla (#105) kayıtlı;
    `/api/isler`'de freze işlerinden sonra, `/api/ekran/torna/is/{ad}` ile sunulur, `/api/sifirla` siler.
  - Ön yüz: `src/ekranlar/torna.ts`, `montaj.ts` (EkranModulu); türler `tipler_25.ts`. e2e kancaları `__tezgah.torna.*`,
    `__tezgah.montaj.*` altında (kabuk etkin ekrana yönlendirmiyor).
  - `Depo`, parametre değerleriyle anahtarlanmış önbellek tutar (tanım, Is, Montaj): aynı değerde yeniden hesap yok.

## Açık sorular
- Yok. (Profil çıkarma SPEC 28 `turn_profile` ile; SPEC 28 main'de.)
