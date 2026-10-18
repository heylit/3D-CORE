# SPEC 24 — Tezgah: web arayüzü (köprü, kabuk, freze akışı)

> **Durum: TASLAK, kullanıcı onayı bekliyor.** Onaylanmadan kod ya da test yazılmaz.
> Prototip: https://claude.ai/artifact/2YA8RRJYuFSpRJyEFMEX8u (konsept; bu SPEC'in kabul ölçütü değildir).
> Karar (kullanıcı, 2026-10-18 07:59 UTC, "Karma"): SPEC 15 pyvista geliştirici görüntüleyicisi olarak kalır;
> prototipteki arayüz ayrı bir SPEC olarak web ile yapılır. Bu SPEC o ayrı SPEC'tir.

## Amaç
Bir freze işini (stok, işlemler, takım yolları, G-code, talaş simülasyonu, kontroller) tarayıcıda
**zaman şeridi**, **G-code ↔ yol ↔ zaman canlı bağı** ve **kanıt paneli** ile gösteren, parametre
değişince her şeyi Python çekirdeğine yeniden hesaplatan bir web arayüzü. Bu adım bitince
`tezgah` komutu yerel bir sunucu açar ve örnek flanş plakası işi tarayıcıda uçtan uca çalışır.

## Temel ilke: arayüz hesap yapmaz
Prototipte takım yolu, simülasyon ve G-code tarayıcıda (JavaScript) hesaplandı. Üretimde **hiçbir
mühendislik sayısı ön yüzde hesaplanmaz.** Yol (SPEC 03), G-code ve geri okuma (SPEC 04), talaş
simülasyonu, süre, çakma ve çarpma (SPEC 05), kısıtlar (SPEC 08) Python'dan gelir. Ön yüz yalnızca
gösterir, ara değer (enterpolasyon) yapar ve kullanıcı girdisini sunucuya iletir. Böylece arayüzde
görülen her sayı, repoda testi olan bir fonksiyonun çıktısıdır ve kanıt panelindeki "SPEC NN" etiketi
gerçek bir teste işaret eder.

## Teori ve veri modeli

### Köprü: `*/model.py` → JSON
Saf fonksiyonlar, yan etkisiz, web bağımlılığı yok (FastAPI'siz test edilir). Birim mm, mm/dk, s
(altın kural 4: dönüşüm yok). Her yanıtta `"sema": 1` sürüm alanı.

```
Is = {
  sema: 1, ad, kurulum: {stok: {x0,x1,y0,y1,z0,z1}, wcs: "G54", malzeme},
  islemler: [{i, anahtar, ad, takim: {T, ad, R, tur}, t0, t1, k0, k1, parametreler}],
  hareketler: [{g: 0|1|2|3, a: [x,y,z], b: [x,y,z], c?: [x,y], F, satir, islem}],
  gcode: [{metin, islem}],          # SPEC 04 yazıcısının çıktısı, satır satır
  satir_hareket: [[ilk, son] | null], # satır → hareket aralığı (canlı bağ bunun üstüne kurulur)
  sure: {toplam, kumulatif_url},    # kümülatif süre ayrı ikili dizi olarak (aşağıda)
  kontroller: [Kontrol]
}
Kontrol = {kimlik, baslik, deger, birim, durum: "tamam"|"uyari"|"hata", aciklama, spec: "SPEC 05"}
```

### İkili diziler (büyük veri)
Nokta dizileri ve simülasyon JSON'a gömülmez; `application/octet-stream`, little-endian:
- `noktalar`: `float32[n·3]` konum, `float64[n]` kümülatif süre, `int32[n]` satır, `int16[n]` işlem,
  `uint8[n]` hızlı hareket bayrağı, `float32[n]` normalize takım yükü (0–1).
- `sim`: SPEC 05'in z-haritası (ya da dexel) için **olay listesi**: her hücre için `(nokta indeksi, yeni z, işlem)`
  kayıtları, hücreye göre sıralı + ofset dizisi. `t` anındaki yüzey = her hücrede indeksi ≤ k olan son olay.
  Bu biçim prototipte denendi: geri sarma ve ileri sarma aynı maliyette, ön yüz sim hesaplamaz.

### Zaman → indeks
`k(t) = max{k : t_k ≤ t}` ikili arama ile; takım konumu `k` ile `k+1` arasında doğrusal ara değer.
Ara değer yalnızca görsel; DRO'da gösterilen koordinat `k` ve `k+1` uçlarından türetildiği için
yolun dışına çıkmaz.

## Mimari

```
tezgah/                 Yeni Python paketi (web arayüzü). Hiçbir paket tezgah/'a bağımlı olamaz (viz/ gibi).
  kopru.py              model.py nesneleri → Is sözlüğü + ikili diziler. Saf, FastAPI'siz.
  isler.py              Örnek işler (uydurma flanş plakası) ve parametre → iş üretimi (cam/ fonksiyonlarını çağırır)
  sunucu.py             FastAPI uygulaması: REST uçları + statik dosya servisi
  __main__.py           `python -m tezgah` / `tezgah` komutu: sunucuyu açar, tarayıcıyı başlatır
  arayuz/               Ön yüz (TypeScript + three.js, Vite ile derlenir)
    src/zaman.ts        zaman → indeks, şerit ölçeği, kıvılcım grafiği örnekleme (saf, test edilir)
    src/gcode.ts        satır vurgusu, satır ↔ hareket eşlemesi (saf, test edilir)
    src/sahne.ts        three.js sahnesi, yörünge kamera, z-haritası ağı, takım ve hayalet
    src/paneller.ts     iş yığını, müfettiş, G-code, kanıtlar, komut çubuğu
    dist/               Derlenmiş çıktı (repoya girmez; paket kurulurken ya da `npm run build` ile üretilir)
tests/tezgah/           Python testleri (köprü, uçlar, bağımlılık kuralı)
tezgah/arayuz/tests/    Ön yüz birim testleri (vitest) ve uçtan uca (Playwright)
```

Bağımlılık yönü: `tezgah` → `cam`, `assy`, `geometry` (yalnızca `model.py` arayüzleri ve paketlerin
herkese açık fonksiyonları). `core/` FEM'e bu SPEC'te dokunulmaz.

### REST uçları
| Uç | Yanıt |
|---|---|
| `GET /api/isler` | Örnek işlerin listesi |
| `GET /api/is/{ad}` | `Is` JSON |
| `GET /api/is/{ad}/noktalar` | ikili nokta dizisi |
| `GET /api/is/{ad}/sim` | ikili olay listesi |
| `POST /api/is/{ad}/parametre` | `{islem, anahtar, deger}` → yeni `Is` + `sure_farki` (s) |

Geçersiz parametre (ör. takım çapı ≤ 0, cep takımdan dar) çekirdekte `ModelError` / `CamError` fırlatır;
sunucu bunu **422** ve hata metniyle döner, ön yüz müfettişte gösterir. Sessiz düzeltme yok (altın kural 5).

## Yeni bağımlılıklar (kullanıcı onayı gerekir; `pyproject.toml` ayrı PR)
| Bağımlılık | Nerede | Neden |
|---|---|---|
| `fastapi`, `uvicorn` | yeni isteğe bağlı grup `[web]` | REST + statik servis |
| `httpx` | `[dev]` | FastAPI `TestClient` için |
| Node 20+, `three`, `vite`, `typescript`, `vitest` | `tezgah/arayuz/package.json` | ön yüz derleme ve birim testi |
| `@playwright/test` | `tezgah/arayuz` dev | uçtan uca test (bulutta Chromium hazır kurulu) |

Python çekirdeği (`.[dev]`, `.[cad]`) bu bağımlılıklar olmadan kurulmaya ve test edilmeye devam eder;
`[web]` kurulu değilse `tests/tezgah/` atlanır (`pytest.importorskip("fastapi")`).

## Yol haritası yeri
- **Numara:** 24 (`24-tezgah`). 14–23 yol haritası PR'ında (#8) kullanılıyor.
- **Bağımlılık:** 24 → 02, 03, 04, 05, 08. (15'e bağlı değil; pyvista görüntüleyicisi ayrı yürür.)
- **Dalga:** 3 (05 talaş simülasyonu Dalga 2'de `main`'e girince başlar). Köprünün 03/04'e dayanan kısmı
  (K1–K3) isterseniz Dalga 2'de 05'ten bağımsız başlayabilir; sim katmanları (K6) 05'i bekler.
- **Devamı (bu SPEC değil):** `25-tezgah-torna-montaj`: torna akışı (→ 20, 21, 22) ve montaj sırası,
  serbestlik göstergesi, girişim düzeltmesi (→ 07, 09). Dalga 5.
- `docs/yol-haritasi.md` bu PR'da değişmez; onaydan sonra yol haritası sahibi thread ekler.

## Kabul kriterleri
- [ ] **K1 Köprü geri dönüşü:** `kopru.is_json()` çıktısı JSON'a yazılıp okununca hareket uç noktaları,
  merkezler ve F değerleri `cam.model.Toolpath` ile **birebir** aynı (float JSON'da kayıpsız).
  (`tests/tezgah/test_kopru.py::test_toolpath_round_trip`)
- [ ] **K2 Canlı bağ doğruluğu:** her G-code hareket satırı için `satir_hareket` aralığının son hareketinin
  `b` noktası, SPEC 04 okuyucusunun aynı satır için verdiği uç noktadan koordinat başına en fazla
  ε = 5·10⁻⁴ mm uzakta; delik çevrimi satırları kanonik açılımın son noktasına eşlenir.
  (`test_kopru.py::test_line_move_map_matches_reader`)
- [ ] **K3 Süre:** köprüdeki toplam ve işlem başına süre SPEC 05 süre tahmini ile aynı (rel 1e-12);
  tek doğru G1 için `L/F·60` analitik. (`test_kopru.py::test_times_match_cam_sim`)
- [ ] **K4 Parametre ucu:** `POST /parametre` sonrası dönen `sure_farki`, iki işin ayrı ayrı hesaplanan
  sürelerinin farkı; geçersiz değer 422 ve çekirdeğin hata metni. (`tests/tezgah/test_sunucu.py`)
- [ ] **K5 Kanıtlar gerçek:** kontroller SPEC 04/05 fonksiyonlarından gelir. Bilerek çakma yapan
  (yol CAD'in altına inen) uydurma işte `cakma` kontrolü `hata`; hızlı hareketi malzemeden geçen işte
  `hizli_carpma` `hata`; temiz örnek işte hepsi `tamam`. (`test_sunucu.py::test_checks_*`)
- [ ] **K6 Sim ikili dizisi:** olay listesinden herhangi bir `k` için kurulan yüzey, SPEC 05'in aynı `k`'daki
  z-haritasıyla `float32` olarak birebir. (`test_kopru.py::test_sim_events_reconstruct`)
- [ ] **K7 Ön yüz saf fonksiyonları (vitest):** `idxAt` sınır durumları (t < t₀, t > t_son, eşit süreli
  noktalar); şerit ölçeği ve onay işareti adımı; satır ↔ hareket eşlemesinin tersi.
  (`tezgah/arayuz/tests/zaman.test.ts`, `gcode.test.ts`)
- [ ] **K8 Uçtan uca (Playwright):** örnek iş açılır; konsolda hata yok; bir G-code satırının üstüne
  gelinince hayalet takımın konumu o satırın uç noktası (`window.__tezgah` test kancası ile okunur, ε içinde);
  zaman şeridi sürüklenince DRO değişir ve şerit sonundaki yüzey K6'daki son yüzeyle aynı;
  takım çapı kaydırıcısı değişince G-code satır sayısı ve süre sunucu yanıtıyla aynı. 400 px ve 1440 px
  genişlikte ekran görüntüsü alınır, yatay kaydırma yok. `@slow`. (`tezgah/arayuz/tests/e2e.spec.ts`)
- [ ] **K9 Bağımlılık kuralı:** `cam`, `assy`, `geometry`, `core`, `viz` içinden hiçbir modül `tezgah`'ı
  import etmez; `tezgah` başka paketlerin iç dosyalarını değil yalnızca `model.py` ve herkese açık
  fonksiyonlarını import eder. (`tests/tezgah/test_bagimlilik.py`, AST taraması)
- [ ] **K10 Klavye:** Boşluk oynat/duraklat, Ctrl K komut çubuğu, ←/→ adım, Esc kapat; her etkileşimli
  öğenin görünür odak durumu var. (K8 içinde)

## Test yaklaşımı
- CLAUDE.md "Test bağımsızlığı" aynen geçerli: önce `dogrulayici` oturumu bu SPEC'ten testleri yazar
  (Python ve TS), sonra ayrı bir `yazici` oturumu kodu yazar.
- Python testleri mevcut `pytest` akışında; `[web]` yoksa atlanır.
- Ön yüz testleri `npm test` (vitest) ve `npm run e2e` (Playwright). Yerelde pre-push hook'una eklenmesi
  ve CI'da çalışıp çalışmayacağı aşağıdaki açık sorudadır.
- Görsel tasarım (renk, yerleşim) kabul ölçütü değildir; prototip yön gösterir. Ölçütler sayılar ve davranıştır.

## Açık sorular (kullanıcıya)
1. Yeni bağımlılıklar (`fastapi`, `uvicorn`, `httpx`, Node araç zinciri) kabul mü?
2. Ön yüz testleri CI'da çalışsın mı? Çalışırsa `.github/workflows/test.yml`'e bir Node adımı eklenir
   (dakika maliyeti artar). Öneri: CI'da yalnızca Python testleri, ön yüz testleri yerelde pre-push'ta.
3. Derlenmiş `dist/` repoya girmesin, kurulumda üretilsin (öneri) mi; yoksa kullanıcı Node kurmadan
   açabilsin diye derlenmiş hali repoya mı girsin?

## Kapsam dışı
- Torna akışı ve montaj ekranı (SPEC 25 önerisi).
- Arayüzde parça modelleme, eskiz, özellik ağacı (SPEC 17/18 sonrası).
- Çok kullanıcılı sunucu, kimlik doğrulama, uzak dağıtım: sunucu yalnızca `127.0.0.1`'de dinler.
- pyvista görüntüleyicisi (SPEC 15) ile ortak kod.
- Gerçek şirket parçaları (gizlilik kuralı): örnek işler uydurma geometridir.
