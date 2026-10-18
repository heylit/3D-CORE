# SPEC 62 — Tezgah deneyimi: komut paleti, canlı fark, ölçü sürükleme, simülasyonu ileri-geri sarma

> **Durum: ONAYLI** (kullanıcı, 2026-10-18 16:06: "Dalga 7 taslakları 57, 58, 59, 61, 62, 63, 64 ve 72'yi önerileriyle onaylıyorum."; açık sorular önerilen yanıtlarla kapatıldı, bkz. Kararlar) (Dalga 7, hat A6; `yol-haritasi/dalga-6-ve-sonrasi.md` bölüm 4).
> Bağımlılık (kod): SPEC 24 (Tezgah, `main`'de), A3 ekran kaydı (`tezgah/ekranlar/`, `main`'de), SPEC 26 (model geçmişi
> `tezgah/modelleme.py`, güvenli ifade `tezgah/ifade.py`; `main`'de), SPEC 37 (proje dosyası ve kabuk, geri al),
> SPEC 29 (işlem planı, `cam/plan.py`; `main`'de) ve 57 (otomatik CAM 2; taslak), SPEC 05 (z-map / dexel simülasyonu,
> `cam/sim/`; `main`'de), 72 (çevrim süresi; taslak), 58 (süre/maliyet/teklif; başka thread'in taslağı) — maliyet farkı
> yalnız 58 birleşince gösterilir, o zamana kadar yalnız süre farkı.

## Amaç
Kullanıcının istediği "şaşırtıcı, profesyonel, alışılmadık" deneyimin dört parçası, hepsi doğrulanabilir saf fonksiyonların
üstünde:
1. **Komut paleti:** `Ctrl+K` ile açılan tek satır; "Ø10 delik, 20 derin, H7", "cep 40x20 derin 5", "pah 1x45" gibi
   doğal dile benzeyen komutlar **belirlenimci bir dilbilgisiyle** (yapay zekâ / dil modeli yok) model adımına çevrilir.
   Tanınmayan ya da iki anlamlı komut **tahmin edilmez**: hata ve öneri verir (altın kural 5).
2. **Canlı fark:** modelde değişen her şey (ölçü, yeni özellik) için CAM planı, çevrim süresi ve (58 varsa) maliyetin
   eski → yeni farkı; hangi işlemin eklendiği, kalktığı, değiştiği listelenir ve sahnede renklenir.
3. **Ölçüyü sürükleme:** sahnede bir ölçü tutamağı sürüklendikçe (gecikmeli, debounce) model, plan ve süre **artımlı**
   yeniden hesaplanır; artımlı sonuç tam yeniden hesapla birebir aynıdır.
4. **Zaman çizelgesinde sarma:** simülasyon ileri ve **geri** sarılır; geri sarma, her N harekette bir alınan stok
   anlık görüntüsünden (anahtar kare) ileri tekrar oynatılarak yapılır, sonuç düz simülasyonla bit düzeyinde aynıdır.

## Teori

### 1. Komut dilbilgisi
Girdi önce **normalleştirilir**: küçük harf (Türkçe kurallı: `I → ı`, `İ → i`), `ø`, `Ø`, `⌀` ve "çap" → `Ø`; ondalık
virgül nokta olur (`6,8 → 6.8`; virgülün ardından boşluk varsa ayraçtır); `×`, `*` ve `x` iki sayı arasında → `x`;
"derinlik", "derin", "d=" → `derin`; birden fazla boşluk teke iner. Sonra komut virgülle **parçalara** ayrılır ve her
parça bir kurala eşlenir. Dilbilgisi (EBNF, tüm sayılar mm, açılar derece):

```
komut     = eylem { "," nitelik } ;
eylem     = delik | cep | pah | fillet | kanal | dis ;
delik     = "Ø" sayı [ "delik" ] | "delik" "Ø" sayı | "m" sayı [ "x" sayı ] [ "dis" | "delik" ] ;
cep       = "cep" sayı "x" sayı [ "r" sayı ] ;               (en x boy, köşe radyüsü)
pah       = "pah" sayı [ "x" sayı ] ;                        (boy x açı; açı yoksa 45)
fillet    = ( "fillet" | "radyüs" | "r" ) sayı ;
kanal     = "kanal" sayı "x" sayı ;                          (genişlik x derinlik)
nitelik   = "derin" sayı | "boydan boya" | tolerans | "havşa" sayı [ "x" sayı ]
          | "lamba" "Ø" sayı "derin" sayı | "adet" tamsayı | "aralık" sayı | "yüz" yüzadı ;
tolerans  = harf tamsayı ;                                   (ISO 286 alan: H7, h6, g6, k6 …)
```
- Her eylemin **zorunlu nitelikleri** vardır: delikte `derin` ya da `boydan boya`; cepte `derin`; kanalda iki sayı.
  Eksik zorunlu nitelik → hata: "Delik derinliği eksik. Örnek: 'Ø10 delik, 20 derin' ya da 'Ø10 delik, boydan boya'".
- **İki anlamlılık kuralı:** bir parça birden fazla kurala eşleşirse (ör. "r 5" tek başına: fillet mi, cep köşesi mi?)
  ya da aynı nitelik iki kez verilirse (`derin 20, derin 25`) komut reddedilir; mesaj her iki okumayı listeler.
- **Öneri:** tanınmayan sözcük için en yakın anahtar sözcük Levenshtein uzaklığı ≤ 2 ile önerilir ("deilk" → "delik?").
  Öneri yalnız mesajdadır; komut **uygulanmaz**.
- Dilbilgisinin çıktısı **SPEC 26 model adımıdır** (`tur: "delik"`, `cesit`, `d`, `derinlik` …), yani yeni bir model
  yolu yoktur: palet yalnız `modelleme.insa`'nın zaten bildiği adımları üretir. Yerleşim (hangi yüz, hangi nokta)
  komutta yoksa sahnede o an seçili yüz / nokta kullanılır; seçim yoksa hata ("Önce bir yüz seçin").

### 2. Tolerans tablosu (ISO 286-1 / 286-2)
Sınır sapmaları `ES/EI` (delik) ve `es/ei` (mil) µm cinsinden tablodan okunur; dönüş mm. Çap aralığı "üstü … dahil":
Ø10 → 6–10 aralığı, Ø10.001 → 10–18. İlk sürüm 1–500 mm, alanlar H6–H11, h6–h11, g6, f7, js6, k6, m6, n6, p6.
Temel değerler (IT, µm): IT6 = 8 / 9 / 11 / 13, IT7 = 12 / 15 / 18 / 21, IT8 = 18 / 22 / 27 / 33 (sırasıyla 3–6, 6–10,
10–18, 18–30). Örnekler (test K4): Ø10 H7 = +0.015 / 0; Ø10 h7 = 0 / −0.015; Ø10 g6 = −0.005 / −0.014; Ø10 k6 = +0.010 /
+0.001; Ø20 H7 = +0.021 / 0; Ø6 H7 = +0.012 / 0. Toleranslı delik model adımına `tolerans: "H7"` niteliği ve
**işleme hedef çapı** `d_hedef = d + (ES + EI)/2` olarak yazılır; 29/57 bu bilgiyle raybalama veya ince işlem seçer
(seçim kuralı 57'nindir; bu SPEC yalnız bilgiyi taşır). Tablo kaynaklı ve sabittir; dışındaki alan → hata.

### 3. Canlı fark
Eski ve yeni durum `(model, plan, süre[, maliyet])`. İşlemler **özellik adresi + işlem türü** anahtarıyla eşleşir
(`PlannedOp.feature`, `kind`). Fark kümesi:
- `eklendi`: yalnız yenide olan anahtar; `kalktı`: yalnız eskide; `değişti`: iki tarafta, ama takım, devir, ilerleme,
  paso veya yol geometrisi (hareket listesinin özeti) farklı; `aynı`: geri kalanı.
- `Δt = t_yeni − t_eski` (72'nin toplamı; 72 birleşene kadar SPEC 05 `timing`), `Δmaliyet` (58 varsa). İşlem başına
  `Δt_i`. Toplamlar işlem farklarının toplamına eşittir (kalktı negatif, eklendi pozitif).
- Planlanamayan özelliklerin farkı (`Unplanned`) ayrıca listelenir: "yeni: Ø3 delik, kod `takim_yok`".
Sunucunun mevcut `/api/is/{ad}/parametre` ucu `sure_farki` döndürüyor; bu SPEC aynı fikri plan düzeyine taşır.

### 4. Artımlı yeniden hesap
`insa(model)` saf ve belirlenimcidir (SPEC 26). Önbellek: model adımı listesinin ön ekine göre katı ara sonuçları
(`k`. adıma kadar kurulmuş `Part`) ve özellik başına plan parçaları, anahtar = adımın ve bağımlı olduğu ön ekin
kanonik JSON özeti (SHA-256). Ölçü değişince yalnız o adımdan sonrası yeniden kurulur, yalnız özeti değişen özellikler
yeniden planlanır, sıra ve takım değişimi birleştirmesi her seferinde baştan yapılır (ucuz). **Değişmez:** artımlı sonuç
= önbelleksiz tam hesap (plan özeti, hareket listeleri ve süre bit düzeyinde). Sürükleme ön yüzde 150 ms debounce ile
istek gönderir; uçuştaki eski istek sonucu yenisi geldiyse atılır (istek sıra numarası).

### 5. Zaman çizelgesinde sarma
Simülasyon hareket adımları `k = 0 … n`. Her `N` adımda (varsayılan 200; bellek bütçesine göre seçilir) stok durumunun
**kopyası** saklanır: `K = {0, N, 2N, …}`. `k` adımına git: `j = max{K ≤ k}` karesinden başla, `j+1 … k` hareketlerini
SPEC 05 ile uygula. Geri sarma da aynı yoldur (önceki kareden ileri oynatma), dolayısıyla sonuç düz `0 … k` simülasyonuyla
**bit düzeyinde** aynıdır (aynı işlem sırası, aynı kayan nokta işlemleri). Bellek: z-map hücre sayısı × 8 bayt × kare
sayısı; bütçe aşılırsa `N` iki katına çıkar (kare seyrekleşir, sonuç değişmez, yalnız gecikme artar).
Ön yüzde mevcut `zaman.ts` (`idxAt`, `konumAt`) takım konumunu verir; stok görüntüsü sunucudan `k`'ya göre gelir.

## Dosyalar
- Yeni (Python, FastAPI'siz test edilir):
  - `tezgah/komut.py`: normalleştirme, dilbilgisi, `cozumle()`, öneri.
  - `tezgah/tolerans.py`: ISO 286 tablosu ve `sapma()`.
  - `tezgah/fark.py`: plan / süre / maliyet farkı.
  - `tezgah/artimli.py`: önbellekli `insa` + plan.
  - `tezgah/sarma.py`: anahtar kareli simülasyon.
  - `tezgah/ekranlar/komut.py`: A3 ekran modülü, uçlar `/api/ekran/komut/...`.
- Yeni (TypeScript):
  - `tezgah/arayuz/src/ekranlar/komut.ts`: palet ve fark paneli.
  - `tezgah/arayuz/src/surukle.ts`: ölçü tutamağı ve debounce.
  - `tezgah/arayuz/src/sarma.ts`: kaydırıcı ve önbellek.
- Testler:
  - `tests/tezgah/test_komut.py`, `test_tolerans.py`, `test_fark.py`, `test_artimli.py`, `test_sarma.py`.
  - `tezgah/arayuz/tests/komut.test.ts` (vitest), `tezgah/arayuz/tests/deneyim.e2e.spec.ts` (Playwright).
  - `durum/62-tezgah-deneyim.md`.
- Kullanılır (değişmez): `tezgah/modelleme.py`, `tezgah/ifade.py`, `tezgah/depo.py`, `tezgah/kopru.py`, `cam/plan.py`,
  `cam/sim/*`, `zaman.ts`, `kayit.ts`.
- Dokunulmayacak: tüm `*/model.py`, `tezgah/sunucu.py` ve kabuk dosyaları (`main.ts`, `paneller.ts`, `sahne.ts`). Paletin
  `Ctrl+K` kısayolu kabuğa aittir (`KABUK_KISAYOLLARI`): bkz. Açık soru 1.

## Arayüz
`tezgah.komut`:
- `@dataclass(frozen=True) Cozum(adim: dict, aciklama: str)`: `adim` SPEC 26 model adımı; `aciklama` insan okunur geri
  bildirim ("Ø10 H7 delik, 20 mm derin; hedef çap 10.0075").
- `class KomutError(ValueError)`: `.oneriler: tuple[str, ...]` ve `.okumalar: tuple[str, ...]` (iki anlamlılıkta).
- `normallestir(metin: str) -> str`.
- `cozumle(metin: str, secim: dict | None = None) -> Cozum`: hata → `KomutError`.
- `ornekler() -> list[tuple[str, dict]]`: paletin yardım listesi (K1 tablosuyla aynı kaynak).

`tezgah.tolerans`:
- `sapma(alan: str, d: float) -> tuple[float, float]`: (üst, alt) mm. Bilinmeyen alan, `d ≤ 0`, `d > 500` → `KomutError`.
- `hedef_cap(alan, d) -> float`: `d + (üst + alt)/2`.

`tezgah.fark`:
- `@dataclass(frozen=True) IslemFarki(anahtar, durum, dt, ayrinti)`: `durum ∈ {"eklendi", "kalkti", "degisti", "ayni"}`.
- `plan_farki(eski: MillPlan, yeni: MillPlan, sure_eski, sure_yeni, maliyet=None) -> dict`:
  `{"islemler": [...], "dt": float, "dmaliyet": float | None, "planlanamayan": {...}}`.

`tezgah.artimli`:
- `class Onbellek`: `insa_ve_planla(model: dict, stok, kutuphane, malzeme) -> tuple[Part, MillPlan, Rapor]`,
  `istatistik() -> dict` (isabet / kaçırma sayısı, testte kullanılır).

`tezgah.sarma`:
- `class Sarici(sim_girdisi, N=200, bellek_mb=256)`: `durum(k) -> ZMap/Dexel kopyası`, `n: int`, `kareler: list[int]`.

Uçlar (`/api/ekran/komut` altında, gövde ve yanıtlar `sema: 1`):
- `POST /cozumle {metin, secim}` → `{adim, aciklama}` | 422 `{detail, oneriler, okumalar}`.
- `POST /uygula {model_adi, adim}` → `{model, fark}`; geri al SPEC 37 kabuğunun yığınına yazılır.
- `POST /surukle {model_adi, adim, olcu, deger, sira}` → `{fark, sira}`; eski `sira` yanıtları ön yüzde atılır.
- `GET /sarma/{is}/{k}` → stok ikilisi (SPEC 24 `sim_ikili` biçimi).

## Kabul kriterleri
Testlerde uydurma geometri (SPEC 26 `ornek_model("flans")`); beklenen değerlerin kaynağı test yorumunda.
- [ ] K1 Dilbilgisi tablosu: aşağıdaki 15 girdi tam olarak verilen model adımına çevriliyor (sözlük eşitliği; sayılar
  `float` olarak). Örnekler: "Ø10 delik, 20 derin" → `{tur: "delik", cesit: "duz", d: 10, derinlik: 20}`;
  "ø10 delik, 20 derin, H7" → aynı + `tolerans: "H7"`, `d_hedef: 10.0075`; "delik ⌀6,8 boydan boya" → `derinlik: None`;
  "M8 dis, derin 16" → `cesit: "dis"`, `d` = M8 matkap çapı 6.8 (SPEC 23 tablosu); "M8x1 dis, derin 16" → ince diş,
  `d = 7.0`; "Ø6.6 delik, boydan boya, havşa 12x90" → `cesit: "havsa"`; "Ø9 delik, boydan boya, lamba Ø15 derin 9" →
  `cesit: "lamba"`; "cep 40x20 derin 5" → cep adımı, köşe `r = 0`; "cep 40 × 20, r 3, derin 5"; "pah 1x45";
  "pah 2" (açı 45); "fillet 3"; "kanal 8x4"; "Ø10 delik, 20 derin, adet 4, aralık 25"; "Ø10 DELİK, 20 DERİN"
  (Türkçe büyük harf) — `tests/tezgah/test_komut.py`
- [ ] K2 Hata ve öneri: "deilk Ø10 20 derin" → `KomutError`, `oneriler` içinde "delik"; "Ø10 delik" → derinlik eksik
  mesajı ve iki örnek; "r 5" tek başına → iki okuma (`fillet`, `cep köşesi`) ve ret; "derin 20, derin 25" → ret;
  boş girdi, yalnız sayı, negatif ya da sıfır ölçü → `KomutError`. Hiçbir hatada model değişmiyor — `test_komut.py`
- [ ] K3 Seçimsiz yerleşim: konumu olmayan komut ve `secim = None` → "Önce bir yüz seçin"; seçili yüz ve nokta verildiğinde
  adım `modelleme.insa` ile kuruluyor ve hacim farkı SPEC 26 hacim denetimiyle aynı (π d²/4 · derinlik) — `test_komut.py`
- [ ] K4 ISO 286: Ø10 H7 (+0.015, 0), Ø10 h7 (0, −0.015), Ø10 g6 (−0.005, −0.014), Ø10 k6 (+0.010, +0.001),
  Ø20 H7 (+0.021, 0), Ø6 H7 (+0.012, 0); aralık sınırı: Ø10 6–10'da, Ø10.001 10–18'de (H7 → +0.018); bilinmeyen alan
  "Z9", `d = 0`, `d = 600` → hata — `tests/tezgah/test_tolerans.py`
- [ ] K5 Fark: flanşta cep derinliği 5 → 8 değişince farkta cep işlemi `degisti`, diğerleri `ayni`; yeni Ø6 delik
  eklenince bir `eklendi` ve takım gerekiyorsa sıranın değiştiği görülüyor; `dt` işlem `dt`'lerinin toplamına eşit
  (1e-9 s); planlanamayan yeni özellik `planlanamayan.yeni` içinde — `tests/tezgah/test_fark.py`
- [ ] K6 Artımlı = tam: 50 rastgele (sabit tohum) ölçü değişikliği dizisinde her adımda `Onbellek` sonucu ile önbelleksiz
  `insa` + `plan_mill` sonucu birebir aynı (`summary()`, her `Toolpath.moves`, süre); son ölçüyü değiştiren adımda
  önceki adımların katısı önbellekten geliyor (`istatistik()` isabet sayısı > 0) — `tests/tezgah/test_artimli.py`
- [ ] K7 Sarma = düz simülasyon: flanş işinde `k ∈ {0, 1, N−1, N, N+1, n/2, n}` ve ileri-geri karışık 100 rastgele `k`
  dizisinde `Sarici.durum(k)` z-map dizisi, `0 … k` düz simülasyonuyla bit düzeyinde eşit (`np.array_equal`, `dtype`
  dahil); `bellek_mb` küçültülünce `N` büyüyor ve sonuç değişmiyor — `tests/tezgah/test_sarma.py`
- [ ] K8 Gecikme bütçesi (`@pytest.mark.slow`): flanşta tek ölçü değişikliğinin artımlı yeniden hesabı (model + plan +
  süre farkı) ≤ 300 ms, `Sarici.durum(k)` rastgele `k` için ≤ 100 ms (yerel makine, CI'da yalnız ölçülüp yazılır,
  eşik yerelde zorunlu) — `test_artimli.py`, `test_sarma.py`
- [ ] K9 Uçlar: `/api/ekran/komut/cozumle` K1'in iki girdisinde aynı adımı, K2'nin girdisinde 422 ve `oneriler`
  döndürüyor; `/surukle` eski `sira` ile gelen yanıtı ön yüz atıyor (vitest, saf fonksiyon); ekran A3 kaydında
  görünüyor ve `kisayolDogrula` kabuk kısayoluyla çakışmıyor — `tests/tezgah/test_komut.py`,
  `tezgah/arayuz/tests/komut.test.ts`
- [ ] K10 Uçtan uca (Playwright): paleti aç, "Ø10 delik, 20 derin, H7" yaz, seçili yüzde delik görünüyor, fark panelinde
  yeni işlem ve `Δt > 0`; geri al eski duruma döndürüyor; zaman kaydırıcısı sona ve başa gidip aynı stok görüntüsünü
  veriyor — `tezgah/arayuz/tests/deneyim.e2e.spec.ts`
- [ ] Tüm testler yeşil, `ruff check .` ve `ruff format --check .` temiz, ön yüz `npm test` ve tip denetimi temiz,
  0 "uygulanmamış"; 10 s'den uzun testler `slow`

## Kapsam dışı
- Serbest metin anlayan dil modeli, ses komutu, çok dilli komut (yalnız Türkçe anahtar sözcükler; İngilizce takma adlar
  Açık soru 3).
- Toleransa göre işlem seçimi (raybalama, ince bara): 57'nin kuralı; burada yalnız `tolerans` ve `d_hedef` taşınır.
- Maliyet hesabının kendisi (58), çevrim süresinin hesabı (72), geri al yığını (37).
- Sürüklemede kısıt çözücüyle eskiz yeniden çözümü (SPEC 17 zaten yapar; burada yalnız ölçü değeri değişir).
- Torna, montaj ve 5 eksen işlerinde sarma (ilk sürüm freze z-map / dexel; tri-dexel ve torna profili sonraki ek).
- Çok kullanıcılı canlı ortak çalışma.

## Kararlar (onayla kayda geçti, 2026-10-18 16:06; önerilen yanıtlar kabul edildi)
1. Palet her ekranda açılmalı, ama `Ctrl+K` kabuğun kısayolu ve kabuk dosyaları A3 sahibinindir. Paleti kabuğa kim bağlar?
   Karar: A3 sahibi thread'ine küçük bir kabuk PR'ı ("palet kancası": `Ctrl+K` → kayıtlı `komut` ekranının açılır
   katmanı). Bu SPEC yalnız ekran modülünü yazar; kanca yoksa palet "Komut" sekmesinde çalışır.
2. Komut doğrudan modele mi uygulansın, yoksa önce önizleme ve onay mı? Karar: `Enter` önizler (sahnede yarı saydam,
   farkla), ikinci `Enter` uygular; `Esc` vazgeçer. Geri al her uygulamayı tek adım sayar.
3. İngilizce takma adlar ("hole", "pocket", "chamfer", "deep") eklensin mi? Karar: ilk sürümde yalnız Türkçe; takma adlar
   aynı dilbilgisine tek tabloyla sonra eklenir.
4. Anahtar kare aralığı `N` ve bellek bütçesi: varsayılan `N = 200`, `bellek_mb = 256` mı? Karar: evet; Tezgah ayarlarında
   değiştirilebilir, sonuç `N`'den bağımsız olduğu için güvenli.
5. Ölçü sürüklemede adım (snap) olsun mu? Karar: 0.5 mm (Shift ile 0.1, Ctrl ile 1); sürükleme bırakılınca değer
   ifade olarak modele yazılır (SPEC 26 `ifade`), böylece parametreye bağlı ölçü bozulmaz: parametreye bağlı ölçü
   sürüklenirse parametrenin kendisi değişir ve fark panelinde bu açıkça yazılır.
