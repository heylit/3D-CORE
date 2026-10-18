# SPEC 31 — Siemens Sinumerik ve Heidenhain Klartext postprosesörleri

> Durum: **taslak, kullanıcı onayı bekliyor.** SPEC 30'a bağlıdır (blok planı `cam.post.plan`,
> `MachineProfile`, `check_machine`). SPEC 30 `main`'e girince başlar.

## Amaç
SPEC 30'un dilden bağımsız blok planını iki ISO dışı kontrolör diline biçimlemek ve okumak:
- **Siemens Sinumerik 840D sl / 828D**, kendi (Siemens) dili;
- **Heidenhain TNC 640 / 620 / 530**, Klartext (konuşmalı dil, `.h`).

Bu adım bitince `read_program(post(ops, machine), machine, tools)` her iki dilde aynı hareket listesini,
yazılan ondalığın izin verdiği tolerans içinde geri veriyor ve bütün güvenlik kuralları (SPEC 04 Ek B/C,
SPEC 30) bu dillerde de geçerli, çünkü kararlar tek yerde (`plan`) veriliyor.

## Neden ISO modu değil
İki kontrolör de ISO (Fanuc benzeri) G-code okuyabilir (Sinumerik "ISO dialect", Heidenhain DIN/ISO).
Ama tezgâh başındaki operatör ve tezgâhın kendi döngüleri, takım yönetimi ve simülasyonu doğal dili
kullanır; ISO modu tezgâhta ayrı bir seçenek ve ayar gerektirir. Bu SPEC doğal dilleri yazar.
(Onayda alternatif: yalnız ISO modu; o zaman bu SPEC'e gerek kalmaz, Fanuc çıktısı yeter, ama
tezgâhta ISO modunun açık olması operatöre kalır.)

## Teori

### Siemens Sinumerik (doğal dil)
Kaynak: Siemens, *SINUMERIK 840D sl / 828D Fundamentals Programming Manual* (6FC5398-1BP40), bölümler
"Units of measurement", "Tool change", "Circular interpolation", "Comments".
| Konu | Fanuc (SPEC 04) | Sinumerik |
|---|---|---|
| Metrik | `G21` | `G71` |
| Sayı | `10.` (nokta zorunlu) | `10` (noktasız sayı mm'dir; nokta gereksiz) |
| Yorum | `( ... )` | `; ...` |
| Takım değişimi | `T1 M6` + `G43 ... H1` | `T1 M6`, sonra `D1` (D1 boy ve yarıçap ofsetini açar; `G43` yok) |
| Yay | `G2/G3 X Y I J` (I, J başlangıca göre) | aynı; I, J varsayılanı başlangıca göre bağıl |
| Program başı / sonu | `%`, `O0001` … `M30`, `%` | dosya adı kontrolörde (`.MPF`); başta yorum, sonda `M30` |
| İş sıfırı | `G54`..`G59` | `G54`..`G57` (G505+ kapsam dışı); `G58`/`G59` Siemens'te **eksen ofsetidir**, iş sıfırı değil → `CamError` |
Sayı biçimi: `fmt` gibi, ama sonda nokta yok: `10`, `-2.5`, `0`. Satır numarası kapalı.

### Heidenhain Klartext
Kaynak: HEIDENHAIN, *TNC 640 Klartext Programming User's Manual* (ID 892903), bölümler "Path
contours – Cartesian coordinates" (L, CC, C), "Path contours – polar coordinates" (CP, helis),
"Tool call", "Miscellaneous functions".
- Her satır 0'dan başlayıp birer artan blok numarasıyla başlar. İlk satır `0 BEGIN PGM <ad> MM`,
  son satır `<n> END PGM <ad> MM`.
- Doğru: `L X+10 Y-2.5 Z+0 R0 F300`. Koordinat işaretle yazılır (`+0`), sondaki sıfırlar atılır, tam sayıda
  nokta yok. `R0` yarıçap telafisi yok (her `L`'de yazılır). Yalnız değişen eksenler yazılır.
- Hızlı hareket `FMAX`: **yalnız o blokta** geçerlidir, kesme ilerlemesi modaldır. Bu yüzden FMAX'tan sonra
  gelen ilk kesme bloğu `F`'yi tekrar yazmaz; ama FMAX blokları her seferinde `FMAX` yazar.
  (Okuyucu da böyle okur: FMAX bloğu modal `F`'yi değiştirmez.)
- Yay: önce merkez `CC X+5 Y+10` (CC modaldır ama her yayda yazılır: okunurluk ve güvenlik), sonra
  `C X+0 Y+10 DR+ R0 F300`. `DR+` saat yönü tersi (G3), `DR-` saat yönü (G2). `C`'de X ve Y her zaman yazılır.
  Tam daire: `C`'nin bitişi başlangıca eşit.
- Helis (Z değişen yay) kartezyen `C` ile yazılamaz; kutupsal yayla yazılır:
  `CC X Y`, sonra `CP IPA±<açı> IZ±<dz> DR± R0 F`. `IPA` derece cinsinden artımsal açı (helisin toplam
  süpürmesi, `DR+` için pozitif), `IZ` artımsal Z. Açı 4 ondalıkla yazılır: uçtaki hata
  `r·0.5·10⁻⁴·π/180 ≤ 8.8·10⁻⁷·r` mm (r ≤ 500 mm için ≤ 4.4·10⁻⁴ < ε).
- Takım: `TOOL CALL <n> Z S<rpm>` (Z: iş mili ekseni). Takım boyu tezgâhın takım tablosundan gelir
  (`G43` karşılığı yok). İş mili `M3` ilk hareket bloğuna eklenir (`L X+0 Y+0 Z+5 R0 FMAX M3`); `M5` geri
  çekme bloğuna eklenir.
- İş sıfırı: tezgâhın ön ayar (preset) tablosu. `G54`..`G59` → profildeki `presets` eşlemesi
  (`{"G54": 1, ...}`) ile `CYCL DEF 247 DATUM SETTING ~ Q339=+<n>`. Eşleme yoksa → `CamError`
  (yanlış ön ayar satırı parçayı başka yere koyar; varsayılan eşleme yapılmaz).
- Makine koordinatı (SPEC 30 `tool_change_z`): `L Z+<v> R0 FMAX M91` (M91: makine koordinatı, tek blok).
- Program sonu: `L Z+<safe_z> R0 FMAX M30` (M30 iş milini de durdurur), sonra `END PGM`.
- Yorum: `; ...` kendi blok numarasıyla.

### Delik çevrimleri
Sinumerik `CYCLE81/83` ve Heidenhain `CYCL DEF 200/203`, gagalamada yeniden yaklaşma mesafesini
kontrolörün içinde hesaplar (Sinumerik CYCLE83 "anticipation distance", Heidenhain Q256 / dahili değer);
bu, SPEC 04'teki `c = peck_clearance` ile aynı değildir ve bizim simülasyonumuz (SPEC 05) tezgâhın gerçek
yolunu bilemez. Sessiz fark olmaması için bu SPEC'te iki dilde de **delik op'ları kanonik açılımla**
(G0/G1 ve `L ... FMAX` / `L ... F`) yazılır (`Dialect.canned_cycles = False`, GRBL gibi).
Doğal çevrimler ayrı bir ek konusudur.

## Dosyalar
- Yeni: `cam/post/format_sinumerik.py`, `cam/post/format_heidenhain.py`, `cam/post/read_sinumerik.py`,
  `cam/post/read_heidenhain.py`, `cam/post/profiles/ornek-sinumerik-dik.json`,
  `cam/post/profiles/ornek-heidenhain-dik.json` (uydurma kurs ve sınırlar, `verified: false`),
  `tests/cam/test_post_sinumerik.py`, `tests/cam/test_post_heidenhain.py`, `durum/31-sinumerik-heidenhain.md`.
- Değişecek: `cam/post/__init__.py` (`dialect_for`, `read_program` dağıtımı), `cam/post/machine.py`
  veya arayüz PR'ı ile `MachineProfile` (`controller` için `"sinumerik"`, `"heidenhain"`; `presets`
  alanı — `cam/model.py`'deyse ayrı arayüz PR'ı).
- Dokunulmayacak: `cam/gcode/*` (ISO yazıcı ve okuyucu), `cam/post/blocks.py` ve `plan()` (bu SPEC
  karar vermez, yalnız biçimler; yeni blok gerekirse SPEC 30'a ek), tüm `*/model.py`, ortak dosyalar.
  Yeni bağımlılık yok.

## Arayüz
- `MachineProfile.controller ∈ {..., "sinumerik", "heidenhain"}`; `presets: dict[str, int] | None`
  (yalnız Heidenhain, `1 ≤ n`; diğer dillerde verilirse `CamError`).
- `post(ops, machine, ...)` SPEC 30'daki gibi; dile göre biçimleyici. Sinumerik'te `setup.wcs.code`
  `G58`/`G59` → `CamError`; `length_offsets` (GRBL'e özgü) → `CamError`.
- `read_program(text, machine, tools, arc_tol=0.005) -> list[Toolpath]`:
  - Sinumerik okuyucu: `G0 G1 G2 G3 G17 G40 G54..G57 G71 G90 G94`, `M0 M3 M5 M6 M30`, `T`, `D`, `S`, `F`,
    `; yorum`. `D` takım değişiminden sonra ve ilk harekete kadar gelmeli; `D0` veya `D`'siz hareket →
    `CamError` (telafisiz takım boyu). `G70` (inç), `G91`, `CR=`, `AC/IC`, çevrimler, değişkenler → `CamError`.
  - Heidenhain okuyucu: `BEGIN PGM`, `END PGM`, `TOOL CALL n Z S`, `L`, `CC`, `C`, `CP IPA IZ`, `FMAX`,
    `F`, `R0`, `DR±`, `M3 M5 M30 M91`, `CYCL DEF 247 ... Q339`, `; yorum`. Blok numaraları 0'dan ardışık
    olmalı (değilse `CamError`: eksik blok). `RL`/`RR`, `I`'li artımsal koordinat (`IX`), `LP`,
    `CT`, `RND`, `CHF`, diğer çevrimler, `FN`/`Q` parametreleri → `CamError`.
  - Hatalar satır numarası ile (`satır <n>`); çıkan her yol `Toolpath.validate()`'ten geçer.

## Kabul kriterleri
- [ ] K1 Sinumerik altın metin: SPEC 04 Ek A yolu `ORNEK-SINUMERIK-DIK` ile satır satır aşağıdaki metin —
  `tests/cam/test_post_sinumerik.py`
- [ ] K2 Heidenhain altın metin: aynı yol `ORNEK-HEIDENHAIN-DIK` (`presets = {"G54": 1}`) ile satır satır
  aşağıdaki metin — `tests/cam/test_post_heidenhain.py`
- [ ] K3 Heidenhain helis: `r = 5`, 2 tam tur, `Δz = −2` helis → `CP IPA+720 IZ-2 DR+`; geri okununca uç
  ≤ 0.5·10⁻³ mm, merkez aynı; 90°'lik helis `IPA+90` — `test_post_heidenhain.py`
- [ ] K4 FMAX modal değil: `G1 F300 → G0 → G1 F300` yolunda Heidenhain çıktısı ikinci kesmede `F`'yi
  yazmıyor ve okuyucu ikinci kesmeyi `F300` okuyor; `G0`'dan sonra `F` değişirse yazılıyor — `test_post_heidenhain.py`
- [ ] K5 Gidiş-dönüş: SPEC 04 K4 rastgele yolları (sabit tohum, `safe_z` verilerek; tam daire ve helis
  dahil) iki dilde `post → read_program`: hareket tipleri aynı, uçlar ≤ 0.5·10⁻³ mm, merkez ≤ 1e-2 mm,
  devir tam — `test_post_sinumerik.py`, `test_post_heidenhain.py`
- [ ] K6 Delik: aynı `DrillOp` (G81 ve G83, G98 ve G99) iki dilde kanonik açılımla yazılıyor ve okununca
  `DrillOp.to_toolpath()` ile aynı (≤ ε); çıktıda `CYCLE` / `CYCL DEF 20x` yok — her iki test dosyası
- [ ] K7 Güvenlik dilden bağımsız: SPEC 04 Ek B/C ve SPEC 30'un `CamError` durumları (alçak `safe_z`,
  `stock_top` altında XY hızlı, kurs dışı, devir sınırı) iki dilde de aynı mesajla yakalanıyor; iki takımlı
  programda takım değişiminden önce geri çekme ve `M5` var (Heidenhain: `L Z+.. R0 FMAX M5` bloğu) —
  her iki test dosyası
- [ ] K8 İş sıfırı: Sinumerik `G55` başta yazılıyor, `G58` → `CamError`; Heidenhain `presets`'te olmayan
  `G55` → `CamError`, olan `G55` → `CYCL DEF 247` ile `Q339=+2` — her iki test dosyası
- [ ] K9 Okuyucu hataları: Sinumerik (`G70`, `D0`, `D`'siz hareket, `CR=`, `G91`, bilinmeyen kod) ve
  Heidenhain (atlanan blok numarası, `RL`, `IX`, `RND`, `FN`, `END PGM` yok) her biri `CamError` ve
  mesajda satır numarası — her iki test dosyası
- [ ] K10 Tüm testler yeşil, `ruff check .` ve `ruff format --check .` temiz, 0 "uygulanmamış"

### Sinumerik altın metni (K1)
SPEC 04 Ek A yolu, `safe_z = 5`, iş sıfırı G54:
```
; POST ORNEK-SINUMERIK-DIK SINUMERIK
; DOGRULANMAMIS PROFIL - ILK PARCADA KURU CALISTIRIN
G71 G90 G17 G94 G40 G54
T1 M6
D1
S10000 M3
G0 X0 Y0 Z5
G1 Z-1 F100
X10 F300
Y10
G3 X0 I-5 J0
G1 Y0
G0 Z5
M5
M30
```

### Heidenhain altın metni (K2)
Aynı yol; program adı `1` (`program_no`):
```
0 BEGIN PGM 1 MM
1 ; POST ORNEK-HEIDENHAIN-DIK HEIDENHAIN
2 ; DOGRULANMAMIS PROFIL - ILK PARCADA KURU CALISTIRIN
3 CYCL DEF 247 DATUM SETTING ~ Q339=+1
4 TOOL CALL 1 Z S10000
5 L X+0 Y+0 Z+5 R0 FMAX M3
6 L Z-1 R0 F100
7 L X+10 R0 F300
8 L Y+10 R0
9 CC X+5 Y+10
10 C X+0 Y+10 DR+ R0
11 L Y+0 R0
12 L Z+5 R0 FMAX M30
13 END PGM 1 MM
```

## Varsayımlar (doğrulanmalı; tezgâh kılavuzu ve kuru çalıştırma)
Bu iki dilin bağımsız, özgür bir yorumlayıcısı yok; LinuxCNC `rs274` yalnız ISO dilini okur. Doğrulama:
(1) kılavuzlardaki örneklerden elle yazılmış altın metinler, (2) kendi okuyucumuzla gidiş-dönüş,
(3) kullanıcının tezgâhında simülasyon ekranı ve kuru çalıştırma. Profiller bu yüzden `verified: false`
gelir ve programın başında uyarı yorumu yazılır. Doğrulanması gerekenler:
- Sinumerik: `T1 M6` + ayrı satırda `D1` (takım yönetimi açık tezgâhta `T="AD"` gerekebilir); `G71`'in
  tezgâhta varsayılan olması; noktasız sayı.
- Heidenhain: `CYCL DEF 247` satırının tek satır yazımı (`~` ile devam), `M3`'ün ilk `L` bloğunda,
  `M30`'un son geri çekme bloğunda olması; her `L`'de `R0`; `CP IPA` ile helis.

## Kapsam dışı
- Doğal delik çevrimleri (`CYCLE81/83`, `CYCL DEF 200/203`), cep / kontur çevrimleri.
- Sinumerik takım yönetimi (`T="ad"`), `TRANS`/`ROT` çerçeveleri, `G505+`, `CR=` ile yay yazımı.
- Heidenhain `BLK FORM` (ham malzeme grafiği), `RL/RR`, `FK` serbest kontur, Q parametreleri, `TOOL DEF`.
- Torna dilleri (Sinumerik ShopTurn, Heidenhain MANUALplus): SPEC 21 ailesi.
- Döner eksenler, `TRAORI`, `PLANE SPATIAL`, `M128`: 4–5 eksen SPEC'i.
