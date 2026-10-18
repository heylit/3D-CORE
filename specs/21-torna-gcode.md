# SPEC 21 — Torna G-code: Fanuc torna son işlemcisi ve okuyucusu

## Amaç
SPEC 20'nin torna takım yollarını (`Toolpath`, `G18`, `G95`, `css`) Fanuc torna kontrolörü için G-code'a çeviren
bir son işlemci (çap programlama, `G96`/`G97`/`G50` iş mili, `G32` diş, takım değiştirme noktası) ve bunu geri okuyan
okuyucu. Bu adım bitince `read_lathe(write_lathe(yollar))` aynı hareket listesini, yazılan ondalık basamakların izin
verdiği tolerans içinde geri veriyor ve `G96`'da devir `n = 1000·Vc / (π·D)`, `G50` sınırıyla, doğru hesaplanıyor.

## Teori

### Fanuc torna G-code sistemi A
Fanuc tornalarda üç G-code sistemi vardır; en yaygını ve varsayılanı **A**'dır. Freze dilinden farkları tezgâhta kırılmaya
yol açabilecek kadar büyüktür:

| Anlam | Freze (SPEC 04) | Torna, sistem A (bu SPEC) |
|---|---|---|
| İlerleme mm/dev | `G95` | `G99` |
| İlerleme mm/dk | `G94` | `G98` |
| Mutlak / artımsal | `G90` / `G91` | adres harfi: `X Z` mutlak, `U W` artımsal |
| `G90`, `G92`, `G94` | mutlak, koordinat, mm/dk | **dış çap çevrimi, diş çevrimi, alın çevrimi** |
| Devir üst sınırı | — | `G50 S<n>` (`G50 X Z` ise koordinat sistemi kurar) |
| Takım | `T1 M6` | `T0101` (ilk iki hane taret istasyonu, son iki hane ofset no.) |

Bu yüzden torna yazıcısı **asla** `G90 G91 G92 G94 G95 G98` yazmaz ve okuyucu bunları reddeder. Freze başlığı
(`G21 G90 G17 G94`) bir tornaya gönderilirse `G90` ve `G94` çevrim olarak çalışır; freze yazıcısının torna yolunu
reddetmesi (`_yazilabilir`) bu yüzden kalıcıdır.
Kaynak: Fanuc Series 0i-TF Operatör El Kitabı (B-64604EN), "G code list" (sistem A/B/C), "Spindle speed function",
"Thread cutting (G32)", "Circular interpolation"; Smid, *CNC Programming Handbook*, torna bölümleri.

### Çap programlama
Modelde `x` yarıçaptır (SPEC 00 Ek 2). Tornada `X` kelimesi **çaptır**: `X = 2·x`. Yay merkezinin `I` bileşeni Fanuc'ta
çap modunda da **yarıçap** cinsinden ve başlangıca göre bağıldır: `I = c_x − x0`, `K = c_z − z0`.
- Ondalık: `X` ve `Z` 3 basamak (`ε = 0,5·10⁻³` mm). Çapta yuvarlama hatası yarıçapta yarıya iner: `|x_okunan − x| ≤ 0,25·10⁻³`.
- Yazıcının bildiği yarıçap `x̂ = snap(2x)/2`, `ẑ = snap(z)` (`snap` SPEC 04). `I = fmt(c_x − x̂0)`, `K = fmt(snap(c_z) − ẑ0)`.
  Okuyucu merkezi `(x̂0 + I, ẑ0 + K)` bulur ve SPEC 04'teki gibi orta dikmeye izdüşürür.
  En kötü durumda `|r0 − r1| ≤ 2·√(0,25² + 0,5²)·10⁻³ + 2·√2·0,5·10⁻³ ≈ 2,5·10⁻³ mm < arc_tol = 0,005`.
- Negatif `X` geçerlidir: alın tornalamada `T = 3` hayali uç `x = −r`'ye iner (burun merkezi eksende, SPEC 20).

### İş mili
- Sabit devir: `G97 S<n> M3|M4` (`n = round(rpm)`).
- Sabit kesme hızı: önce `G50 S<n_max>` (`n_max = round(rpm)`, model kuralı: `css` varken `rpm` devir sınırıdır),
  sonra `G96 S<Vc> M3|M4` (`Vc = round(css)` m/dk). `G50` olmadan `G96` yazılmaz ve okunmaz (SPEC 14 kuralı).
- Kontrolörün `G96`'daki devri, programlanan noktanın (hayali uç) çapında: `n = min(1000·Vc / (π·D), n_max)`, `D = 2·|x|`;
  `x = 0`'da `n = n_max`. Bu fonksiyon (`spindle_rpm`) simülasyon ve süre hesabı (SPEC 22) içindir.
- **Dönüş yönü** (`M3`/`M4`) takımın tarete bağlanışına ve taretin ön/arka konumuna bağlıdır; modelde yoktur ve
  varsayılamaz. `write_lathe(..., spindle=)` **zorunlu** parametredir, varsayılanı yoktur (`"M3"` veya `"M4"`, aksi `CamError`).
- Diş (`G32`) sabit devir ister: `THREAD` takımlı yolda `css` verilmişse `CamError` (SPEC 20 de reddeder).

### Takım değiştirme noktası ve hızlı hareketler
Fanuc'ta `G0` doğrusal olmayabilir (parametreye bağlı olarak eksenler bağımsız gider, yol "köpek bacağı" olur). Bu yüzden:
- Bir torna yolunda **çapraz `G0`** (aynı satırda hem `X` hem `Z` değişen hızlı hareket, `|Δx|, |Δz| > 1e-9`) → `CamError`.
  SPEC 20'nin bütün işlemleri bu kurala uyar (çapraz `G0` üretmez).
- **Takım değiştirme noktası** `tc = (x_tc, z_tc)` (yarıçap, iş koordinatında) `write_lathe`'e **zorunlu** verilir. Taret
  sadece bu noktada döner. Koşul: `z_tc ≥` bütün yolların bütün noktalarının (`bbox`) en büyük `z`'si ve
  `x_tc ≥` en büyük `x`'i; aksi `CamError`.
- Op geçişi ve program sonu (hepsi eksen eksen):
  1. Geri çekme: takım `z_tc`'de değilse `G0 Z<z_tc>` (ham malzemenin önüne, `+Z` yönünde).
  2. Takım değişiyorsa: `G0 X<2·x_tc>` → iş mili dönüyorsa `M5` → `T<id:02d><id:02d>` → iş mili satırları.
     Takım aynı, iş mili farklıysa: sadece iş mili satırları (taret dönmez, `X` noktasına gidilmez).
  3. `G0 X<2·x_A>` (`z_tc`'de), sonra `G0 Z<z_A>` (`P_A = Toolpath.start`).
  Program sonunda 1, sonra `G0 X<2·x_tc>`, `M5`, `M30`.
- Program başı: başlıktan sonra ilk hareket `G0 X<2·x_tc> Z<z_tc>`. **Varsayım** (programın başında belgelenir, operatör
  sorumluluğu): taret programa `tc` noktasında veya ondan uzakta (`x ≥ x_tc`, `z ≥ z_tc`) başlar; böylece köpek bacağı
  yol da `tc`'nin ötesinde kalır.
- `G28` (referansa dönüş) yazılmaz; okuyucu reddeder (konumu bilinmez).

### Burun yarıçapı telafisi
SPEC 20 yolları **hayali uç** yoludur, telafi CAM tarafında yapılmıştır. Program `G40` ile başlar ve `G41`/`G42` yazılmaz;
okuyucu `G41`/`G42`'yi reddeder (çift telafi takımı malzemeye sokar). Tezgâhta takımın `X`/`Z` geometri ofseti hayali uç
noktasına göre ölçülür (Fanuc standart uygulaması); ofset sayfasındaki `R`/`T` değerleri `G40`'ta kullanılmaz.

### Diş: `G32`
`THREAD` takımlı yolda her `G1` `Z`'ye paralel olmalıdır (`|Δx| ≤ 1e-9`); `G32 Z<z> F<hatve>` olarak yazılır. `F` hatvedir
(mm/dev), **4** ondalıkla (inç hatveleri `25,4/n` için; diğer ilerlemeler 3 ondalık). `X` değişen `G1` (konik diş) veya yay → `CamError`.
`G32`'de ilerleme ayarı ve besleme durdurma kontrolörce devre dışıdır; giriş/çıkış hızlanma boyları (`δ1`, `δ2`) burada denetlenmez.
Okuyucu `G32`'yi `Move(LINEAR, feed = F)` olarak okur; yolun takımı `THREAD` değilse `G32` → `CamError`.

### Çok kısa yay
SPEC 04 Ek B1'in torna karşılığı: yuvarlanmış uçları (`X` metni ve `Z` metni) aynı olan yay, süpürmesi `< π` ise `G1`
olarak yazılır; `≥ π` ise `CamError` (tornada tam daire anlamsızdır, okunsa eksenin altına iner). Okuyucuda başlangıcı ve
bitişi aynı yay → `CamError`.

### Program yapısı (`FANUC_TORNA`)
Kelime sırası: `N G X Z U W I K R F S T M`; satırlar `\n`, metin `\n` ile biter. Bastırma SPEC 04 gibi yuvarlanmış metin
üzerinden (`X` için `fmt(2x)`); `G0`'da `F` yazılmaz; yayda `I` ve `K` her zaman yazılır.
```
%
O0001
N10 G21 G18 G40 G99 G54
...
N.. M5
N.. M30
%
```
Satır numarası `%` ve `O....` dışındaki her satıra `N10`, `N20`, ...

### Okuyucu
- Yeni `Toolpath`: her `T` kelimesinde ve her iş mili değişiminde (`G50`/`G96`/`G97` değeri veya modu). Ondan sonraki
  ilk hareket `G0` olmalı; bitişi yolun `start`'ıdır. İlk `T`'den önceki hareketler sadece `G0` olabilir, konumu kurar,
  hiçbir yola girmez. Yol adı `T<n>-<k>`.
- `T<ss><oo>`: `ss` `tools` sözlüğünde olmalı, `oo == ss` olmalı (`T0100` ofset iptali ve farklı ofset no. → `CamError`).
- Kabul edilenler: `G0 G1 G2 G3 G32 G18 G21 G40 G50 G54 G96 G97 G99`, `M0 M1 M3 M4 M5 M8 M9 M30`,
  `X Z U W I K R F S T N`, `O`, `%`, `( )` ve `;` yorumları, küçük harf, boşluksuz yazım. `U`/`W` artımsal (`U` çaptır).
  `R` biçimli yay SPEC 04'teki formülle (`R` yarıçap; uzaklıklar yarıçap koordinatında).
- `CamError` (mesajda `satır <n>`): `G90 G91 G92 G94 G95` (sistem B/C veya çevrim), `G98` (mm/dk), `G20`, `G17 G19`,
  `G41 G42`, `G28`, `G70 G71 G72 G73 G74 G75 G76`, `X`/`Z` ile `G50`, `G50` olmadan `G96`, `Y J` kelimeleri, aynı satırda
  `X` ve `U` (veya `Z` ve `W`), bilinmeyen takım, ofset uyuşmazlığı, `spindle` verilmişken diğer yön, `T`/iş mili sonrası ilk
  hareket `G0` değil, ilerlemesiz `G1 G2 G3 G32`, konumu bilinmeyen eksen, tutmayan yay, tam daire, `THREAD` olmayan
  takımla `G32`.
- Çıkan her yol: `plane = ZX`, `feed_mode = PER_REV`, `css` / `rpm` iş milinden, noktalar `(x, 0, z)`, `validate()` geçer.

## Dosyalar
- Yeni: `cam/gcode/lathe.py`, `tests/cam/test_gcode_lathe_writer.py`, `tests/cam/test_gcode_lathe_reader.py`,
  `tests/cam/test_gcode_lathe_roundtrip.py`, `durum/21-torna-gcode.md`
- Değişecek (küçük): `cam/gcode/__init__.py` (dışa açılanlar); `cam/gcode/writer.py` sadece `_yazilabilir` docstring'i ve
  torna takımı hata mesajı (koruma **kalır**; mesaj `write_lathe`'i gösterir).
- Kullanılır (değişmez): `cam/model.py`, `cam/gcode/modal.py` (`fmt`, `snap`), `cam/lathe_ops.py` (testlerde).
- Dokunulmayacak: `cam/model.py` (arayüz değişikliği gerekmiyor), `cam/gcode/reader.py`, `dialect.py`, `cycles.py`,
  SPEC 04 testleri, diğer paketler ve ortak dosyalar.

## Arayüz
Hepsi `cam/gcode/lathe.py`'de, `cam.gcode`'dan da dışa açılır. Hatalar `cam.model.CamError`.

- `@dataclass(frozen=True) LatheDialect(name: str, decimals: int, feed_decimals: int, lead_decimals: int,
  line_numbers: bool, line_step: int, header: tuple[str, ...], footer: tuple[str, ...])`;
  hazır örnek `FANUC_TORNA = LatheDialect("Fanuc torna", 3, 3, 4, True, 10, ("%", "O{program_no:04d}",
  "G21 G18 G40 G99 G54"), ("M5", "M30", "%"))`.
- `spindle_rpm(css: float, x: float, rpm_max: float) -> float` — `min(1000·css / (π·2|x|), rpm_max)`, `x = 0` → `rpm_max`;
  `css ≤ 0`, `rpm_max ≤ 0` veya sonlu olmayan girdi → `CamError`.
- `write_lathe(ops: list[Toolpath], spindle: str, tool_change: tuple[float, float], dialect: LatheDialect = FANUC_TORNA,
  program_no: int = 1) -> str`
  - `tool_change = (x_tc, z_tc)`, yarıçap. `spindle ∈ {"M3", "M4"}`.
  - Önce her yol `validate()`; sonra: takım `LatheTool` değil, `plane ≠ ZX`, `feed_mode ≠ PER_REV`, takım `id ∉ 1..99`,
    çapraz `G0`, `tc` koşulu, `THREAD` kuralları, `≥ π` çok kısa yay → `CamError`. Boş liste → `CamError`.
- `read_lathe(text: str, tools: dict[int, LatheTool], spindle: str | None = None, arc_tol: float = 0.005) -> list[Toolpath]`
  - `spindle` verilirse programdaki her `M3`/`M4` ona eşit olmalı; `None` ise ikisi de kabul.

### Altın örnek (K1)
Takım `LatheTool(1, "dis-kaba", TURN, nose_r=0.8, tip=3, kappa_r=93, eps_r=55)`; yol `rpm = 2500`, `css = 180`,
`start = (21, 0, 1)`; hareketler `G0 (12, 0, 1)`, `G1 (12, 0, −10) F0.2`, `G2 (15, 0, −13)` merkez `(15, −10)` `F0.2`,
`G1 (21, 0, −13) F0.2`, `G0 (21, 0, 1)`. `write_lathe([yol], spindle="M3", tool_change=(50, 50))`:
```
%
O0001
N10 G21 G18 G40 G99 G54
N20 G0 X100. Z50.
N30 T0101
N40 G50 S2500
N50 G96 S180 M3
N60 G0 X42.
N70 Z1.
N80 X24.
N90 G1 Z-10. F0.2
N100 G2 X30. Z-13. I3. K0.
N110 G1 X42.
N120 G0 Z1.
N130 Z50.
N140 X100.
N150 M5
N160 M30
%
```
`read_lathe` bunu tek yol olarak okur: `start = (21, 0, 50)`, hareketler `G0 (21, 0, 1)` + yukarıdaki beş hareket +
`G0 (21, 0, 50)`, `G0 (50, 0, 50)`; `css = 180`, `rpm = 2500`.

## Kabul kriterleri
Toleranslar: yarıçap `x` `0,25·10⁻³`, `z` `0,5·10⁻³` mm; ilerleme `0,5·10⁻³`, hatve `0,5·10⁻⁴` mm/dev; yay merkezi `1e-2` mm;
`rpm` ve `css` tam sayıya yuvarlanmış değer. Test yolları uydurma geometridir.
- [ ] K1 Altın metin: yukarıdaki program satır satır aynı; `spindle="M4"` ile tek fark `M4` — `tests/cam/test_gcode_lathe_writer.py`
- [ ] K2 Çap programlama ve bastırma: `X = 2x` (`x = 12,3456` → `X24.691`), negatif `x` (`X-1.6`), `I` yarıçap ve bağıl,
  değişmeyen eksen / aynı `F` / aynı `G` yazılmıyor, `G0`'da `F` yok — `test_gcode_lathe_writer.py`
- [ ] K3 İş mili: `css = None` → `G97 S<n> M3`; `css` → `G50 S<n_max>` + `G96 S<Vc> M3`; yuvarlama (`rpm = 1499,6` → `S1500`);
  sadece iş mili değişince taret dönmüyor, sadece iş mili satırları; `spindle` eksik / `"M6"` → `CamError` — `test_gcode_lathe_writer.py`
- [ ] K4 Takım değişimi ve hızlı hareketler: iki takımlı programda sıra `G0 Z<z_tc>`, `G0 X<2x_tc>`, `M5`, `T0202`, iş mili,
  `G0 X<2x_A>`, `G0 Z<z_A>`; aynı takımlı ikinci op `T` yazmıyor; `T` biçimi (`id = 7` → `T0707`); `id = 0` / `100` → `CamError`;
  `z_tc` veya `x_tc` bir yolun `bbox`'ının altında → `CamError`; çapraz `G0` → `CamError` — `test_gcode_lathe_writer.py`
- [ ] K5 Diş: `THREAD` yolunda her kesme `G32 Z F<hatve>` (`P = 1,8143` → `F1.8143`); `G97`; `css` verilmiş, konik `G1`
  veya yay → `CamError`; freze yazıcısı `write()` torna yolunu hâlâ reddediyor ve mesajda `write_lathe` geçiyor — `test_gcode_lathe_writer.py`
- [ ] K6 Diğer yazıcı hataları: freze takımlı yol, `PER_MIN`, boş liste, `≥ π` çok kısa yay → `CamError`; `< π` çok kısa yay
  `G1` yazılıyor ve okununca boyu `≤ 1e-3` mm — `test_gcode_lathe_writer.py`
- [ ] K7 `spindle_rpm`: `Vc = 180`, `x = 25` (`D = 50`) → `1145,9156`, yani `180000/(50π)` (rel 1e-12); sınır `1000` → `1000`; `x = 0` → sınır;
  hatalı girdiler → `CamError` — `test_gcode_lathe_writer.py`
- [ ] K8 Okuyucu ayrıntıları: `U`/`W` artımsal bilinen mutlak noktalara gidiyor; `R` biçimli `G2`/`G3` merkezi bilinen noktada
  (1e-9); yorumlar, `N`, `%`, `O`, küçük harf, boşluksuz kelimeler; ilk `T`'den önceki `G0` yola girmiyor; `G96`'lı yolda
  `css`, `rpm` doğru — `tests/cam/test_gcode_lathe_reader.py`
- [ ] K9 Okuyucu hataları: "Okuyucu" bölümündeki her `CamError` durumu ve mesajda satır numarası — `test_gcode_lathe_reader.py`
- [ ] K10 Gidiş-dönüş, SPEC 20 işlemleri: `face`, `turn`, `rough`, `finish`, `groove`, `thread` (dış ve iç, `"yanak"` dahil)
  tek programda yazılıp okununca her yol: hareket tipleri aynı, uç noktalar ve merkezler toleransta, araya sadece yukarıdaki
  kuralla eklenen `G0`'lar giriyor; `css`, `rpm`, `feed`, hatve toleransta — `tests/cam/test_gcode_lathe_roundtrip.py`
- [ ] K11 Gidiş-dönüş, rastgele: sabit tohumlu 200 hareketlik ZX yolu (`G0` eksen eksen, `G1`, `G2`/`G3` süpürme `< 2π`,
  `x ∈ [0, 40]`) yazılıp okununca K10 toleransları — `test_gcode_lathe_roundtrip.py`
- [ ] `pytest` 0 failed (SPEC 04 testleri değişmeden yeşil), bu SPEC'in testlerinde 0 "uygulanmamış"; `ruff check .` ve
  `ruff format --check .` temiz

## Kapsam dışı
- Kontrolör çevrimleri `G71`/`G70`/`G72`/`G73` (kaba/ince), `G76`/`G92` (diş), `G74`/`G75` (gagalama): kontrolör bunları
  kendi açar ve bu açılım SPEC 20'nin doğrulanmış yolundan farklıdır (eksenel `U`/`W` payı, kendi geri çekmeleri, telafi).
  İleride ayrı SPEC (okuyucu açılımı SPEC 20 ile karşılaştırarak).
- Makine tarafı burun telafisi (`G41`/`G42`), takım aşınma ofsetleri, `G28`/`G30` referans dönüşleri.
- Soğutma sıvısı (`M8`/`M9` okunur, yazılmaz; modelde alan yok), `M19` iş mili konumlama, C/Y ekseni, punta / yatak komutları.
- Ayna, punta ve taret çarpışması; `G0`'ların kalan malzemeye girmemesi; diş hızlanma boyları: SPEC 22 (simülasyon).
- Sistem B/C, Siemens, LinuxCNC torna (`G7`) dilleri: yeni `LatheDialect` ile ileride.
- `cam/model.py`'ye iş mili yönü veya takım değiştirme noktası eklemek (bu SPEC'te `write_lathe` parametresi; SPEC 14'ün
  `Setup`'ı ileride taşıyabilir: ayrı arayüz PR'ı).
