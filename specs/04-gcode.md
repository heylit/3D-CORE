# SPEC 04 — G-code çıkışı (son işlemci) ve G-code okuyucu

## Amaç
`cam/model.py`'deki takım yollarını (`Toolpath`) GRBL ve Fanuc kontrolörleri için G-code'a çeviren
bir son işlemci, delik delme çevrimleri (G81 / G83) ve kendi G-code okuyucumuz. Bu adım bitince
`read(write(yollar))` aynı hareket listesini, yazılan ondalık basamak sayısının izin verdiği
tolerans içinde geri veriyor.

## Teori

### G-code modaldır (durum makinesi)
G0/G1/G2/G3, G90/G91, G17, G21, F ve S bir kez yazılır, değişene kadar geçerlidir. Yazıcı ve
okuyucu **aynı durum makinesini** (`ModalState`) kullanır:
- Yazıcı: bir kelime (ör. `G1`, `F300.`, `Y10.`) durumdaki değerle aynıysa yazılmaz.
- Okuyucu: satırda olmayan kelime önceki durumdan doldurulur.

Bir satırdaki kelime sırası (yazıcı): `N G X Y Z I J R Q F S T M`. Koordinatlar her zaman mutlak (G90)
yazılır; böylece yuvarlama hatası satırdan satıra birikmez.
Kaynak: Smid, *CNC Programming Handbook*, Bölüm 4–6 (program yapısı, modal kelimeler);
LinuxCNC G-code referansı ("Modal Groups").

### Sayı biçimi ve tolerans
Koordinatlar `d` ondalık basamakla, her zaman ondalık noktalı yazılır (`10.`, `-2.5`, `0.`):
Fanuc'ta noktasız `X10` makine birimi (µm) olarak okunabilir, nokta bunu önler. `-0.` yazılmaz, `0.` yazılır.

Yuvarlama hatası koordinat başına en fazla `ε = 0.5·10^-d` mm'dir (d = 3 için 5e-4 mm).
Yol haritasındaki "birebir aynı" kriteri buna göre netleşir: **okunan değer, yazılan değerden
koordinat başına en fazla ε uzakta.** (Araştırma belgesi önerisi; 1e-6 mm, 3 basamakla imkânsız.)

### Yay (G2 / G3), I-J ve R biçimi
G17 (XY) düzleminde G2 saat yönü, G3 saat yönü tersi (+Z'den bakınca). Z kelimesi varsa helis.
- **I, J** (yazıcının tek biçimi): başlangıç noktasına göre bağıl merkez ofseti, `I = cx − x0`, `J = cy − y0`.
  Yazıcı I, J'yi **yuvarlanmış** merkez ile **yuvarlanmış** başlangıç farkından hesaplar
  (`I = round(cx) − round(x0)`); böylece okuyucunun bulduğu merkez yuvarlanmış merkezin tam kendisidir.
- **R** (sadece okuyucu): kiriş `L = |p1 − p0|`, orta nokta `m`, kirişe dik birim vektör `n`.
  `h = sqrt(R² − (L/2)²)`, merkez `c = m ± h·n`. G2 ve `R > 0` (≤ 180°) için merkez kirişin sağında,
  G3 ve `R > 0` için solunda; `R < 0` (> 180° yay) tarafı tersine çevirir. `|R| < L/2 − arc_tol` → `CamError`.
  R ile tam daire tanımsızdır → `CamError`. Yarım daireye yakın yaylarda R biçimi kötü koşulludur;
  bu yüzden yazıcı I, J kullanır. Kaynak: Smid Bölüm 29; LinuxCNC G2/G3 ("Radius format arc").

**Okuyucuda yay doğrulama ve merkez düzeltme.** Başlangıç ve bitişin merkeze uzaklıkları `r0`, `r1`:
- `|r0 − r1| > arc_tol` → `CamError` (sessiz hata yok).
- Aksi halde merkez, kirişin orta dikmesine izdüşürülür: `c' = m + ((c − m)·u) u`
  (`u` orta dikme yönünde birim vektör). Böylece `r0 = r1` olur ve okunan yol `Toolpath.validate()`'ten
  (ARC_TOL = 1e-6 mm) geçer. Tam dairede (p0 = p1) düzeltme yapılmaz.
- `arc_tol` varsayılanı 0.005 mm: d basamakta uç ve merkez hataları en kötü durumda
  `|r0 − r1| ≤ 4·(√2/2)·10^-d ≈ 2.83·10^-d` verir; 0.005 mm, d ≥ 3 için bunu kapsar.

### Delik çevrimleri (G81, G83)
Tanımlar: başlangıç yüksekliği `z0` (çevrim başlarken takımın Z'si), R düzlemi `r`, dip `z`
(`z < r ≤ z0`), gagalama derinliği `q`, geri çekilme payı `c` (dialect alanı `peck_clearance`).
Çevrim sonundaki dönüş düzlemi: `G98` → `z0`, `G99` → `r`. Kaynak: Smid Bölüm 21–22; LinuxCNC G81/G83.

Her delik için **kanonik açılım** (yazıcı GRBL'de bunu yazar, okuyucu her iki dilde bunu üretir):
- **G81:** `G0` (x, y, z_akım) → `G0` (x, y, r) → `G1` (x, y, z) F → `G0` (x, y, z_dön).
- **G83:** `G0` (x, y, z_akım) → `G0` (x, y, r) → k = 1..n için: (k > 1 ise `G0` (x, y, d_{k−1} + c)) →
  `G1` (x, y, d_k) F → `G0` (x, y, r); sonra `G0` (x, y, z_dön).
  Derinlikler `d_k = max(r − k·q, z)`, `n = ⌈(r − z)/q⌉`.
- Boyu sıfır olan hareketler yazılmaz (ör. G99'da ikinci delikte z_akım = r).

Analitik sonuçlar (G83, tek delik): G1 sayısı `n`; toplam G1 boyu `(r − z) + (n − 1)·c`.

### Kontrolör farkları (`Dialect`)
| | GRBL 1.1 | Fanuc (0i/31i tipi) |
|---|---|---|
| Ondalık basamak (koordinat / F) | 3 / 1 | 3 / 1 |
| Satır numarası | yok | `N10`, 10'ar artar |
| Program başı | `G21 G90 G17 G94` | `%`, `O0001`, `G21 G90 G17 G94 G40 G49 G80` |
| Program sonu | `M5`, `M30` | `M5`, `M30`, `%` |
| Takım değişimi | `T1` (+ ilk takım değilse `M0` duraklat) | `T1 M6` |
| Delik çevrimi | yok: kanonik açılım G0/G1 olarak yazılır | `G98 G81 X Y Z R F` / `G83 ... Q`, sonra `G80` |
| `peck_clearance` c | 0.5 mm | 0.5 mm |

Varsayım (doğrulanmalı): GRBL 1.1 `T` kelimesini kabul edip yok sayar, `M6` ve G8x çevrimlerini desteklemez;
takım değişimi `M0` ile operatöre bırakılır.

## Mimari ve depo ile uyum
Koordinatörün önerdiği boru hattı (takım yolu `cam/model.py` veri sınıflarıyla gelir, makineye özel
son işlemci G-code üretir, yan etkisiz saf fonksiyonlar) aynen alındı. İki noktada **depo kazanır**:
- **Yer:** öneride `post/` ayrı bir klasördü; `CLAUDE.md` mimarisi G-code'u `cam/` altına koyuyor.
  Kod `cam/gcode/` alt paketinde.
- **Hareket listesi:** araştırma belgesi `Drill`, `ToolChange`, `Spindle` hareket tiplerini önermişti;
  `cam/model.py`'de sadece `G0/G1/G2/G3` (`MoveType`) var ve SPEC PR'ı arayüzü değiştiremez. Bu yüzden:
  takım değişimi ve devir `Toolpath.tool` / `Toolpath.rpm`'den çıkarılır; delik çevrimi bu SPEC'e ait
  ayrı bir veri sınıfı `DrillOp`'tur ve kanonik açılımla `Toolpath`'e çevrilebilir.
  `cam/model.py`'ye ileride çevrim tipi eklemek ayrı bir arayüz PR'ı konusudur.

## Dosyalar
- Yeni: `cam/gcode/__init__.py`, `cam/gcode/modal.py`, `cam/gcode/dialect.py`, `cam/gcode/cycles.py`,
  `cam/gcode/writer.py`, `cam/gcode/reader.py`; `tests/cam/test_gcode_*.py`; `durum/04-gcode.md`
- Dokunulmayacak: `cam/model.py` ve tüm `*/model.py`, `cam/` altındaki SPEC 03 dosyaları,
  `pyproject.toml`, `.github/`, `CLAUDE.md`, `BASLANGIC.md`, `DURUM.md`, `core/**`
- Yeni bağımlılık yok (saf Python + numpy).

## Arayüz
Hepsi `cam.gcode`'dan dışa açılır. Hatalar `cam.model.CamError`.

- `@dataclass(frozen=True) Dialect(name, decimals, feed_decimals, line_numbers: bool, line_step: int,
  header: tuple[str, ...], footer: tuple[str, ...], tool_change: str, canned_cycles: bool,
  peck_clearance: float)`; hazır örnekler `GRBL`, `FANUC`.
- `@dataclass DrillOp(name: str, tool: Tool, rpm: float, start: tuple[float, float, float],
  holes: list[tuple[float, float]], z: float, r: float, feed: float, kind: str = "G81",
  q: float | None = None, retract: str = "G98")`
  - `validate()` → `CamError`: `rpm ≤ 0`, `feed ≤ 0`, delik yok, `z ≥ r`, `r > start[2]`,
    `kind` G81/G83 dışı, G83'te `q` yok veya `≤ 0`, `retract` G98/G99 dışı.
  - `to_toolpath(dialect) -> Toolpath` — kanonik açılım (`peck_clearance` dialect'ten; G83'te `c < q` değilse `CamError`).
- `class ModalState` — `motion`, `distance` (G90/G91), `plane`, `units`, `feed`, `rpm`, `tool`,
  `pos: tuple | None`, çevrim parametreleri. Yazıcı ve okuyucunun ortak durumu.
- `fmt(v: float, decimals: int) -> str` — `10.`, `-2.5`, `0.` biçimi.
- `write(ops: list[Toolpath | DrillOp], dialect=GRBL, program_no: int = 1) -> str`
  - Önce her op'u doğrular (`Toolpath.validate()` / `DrillOp.validate()`).
  - Her op başında: takım farklıysa takım değişimi, takım veya devir farklıysa `S<rpm> M3`
    (devir tam sayıya yuvarlanır), sonra op'un başlangıcına üç ekseni de içeren `G0 X Y Z`.
- `read(text: str, tools: dict[int, Tool], dialect=GRBL, arc_tol: float = 0.005) -> list[Toolpath]`
  - Her `T` kelimesinde veya `S` değişiminde yeni bir `Toolpath` başlar; ondan sonraki ilk hareket
    `G0` olmalı ve onun bitişi yolun `start`'ıdır. Aynı takım ve devirle art arda gelen op'lar
    tek yol olarak okunur (aradaki `G0` sıradan bir harekettir). Yol adı `T<n>-<sıra>`.
  - Desteklenen: `G0 G1 G2 G3 G17 G21 G40 G49 G54 G80 G81 G83 G90 G91 G94 G98 G99`,
    `M0 M1 M2 M3 M5 M6 M7 M8 M9 M30`, `X Y Z I J R Q F S T N`, `O`, `%`, `( )` ve `;` yorumları,
    büyük/küçük harf, boşluksuz yazım (`G1X10Y5`).
  - `CamError` (satır numarasıyla): bilinmeyen G/M kodu; `G20` (inç; birim dönüşümü yok); `G18`/`G19`;
    `M4`; `K` kelimesi; `tools`'ta olmayan takım; konumu bilinmeyen eksen (programın ilk hareketi üç
    ekseni vermiyorsa); `T`/`S` sonrası ilk hareket G0 değil; ilerlemesi olmayan G1/G2/G3; tutmayan yay;
    `G91` altında çevrim.
  - `G91` okunur (artımsal X Y Z); I, J her zaman başlangıca göre bağıldır (G91.1 varsayılanı).
  - Çevrimler kanonik açılıma çevrilir (`peck_clearance` verilen dialect'ten).
  - Çıkan her yol `Toolpath.validate()`'ten geçer.

## Kabul kriterleri
- [ ] K1 `fmt`: `10 → "10."`, `-2.5 → "-2.5"`, `-0.0001 (d=3) → "0."`, `1.23456 → "1.235"` — `tests/cam/test_gcode_format.py`
- [ ] K2 Altın metin: kare + yarım daire konturlu bilinen bir yol için GRBL ve Fanuc çıktısı satır satır
  beklenen metne eşit (modal bastırma, I/J, satır numarası, baş/son dahil) — `tests/cam/test_gcode_writer.py`
- [ ] K3 Modal bastırma: aynı F ve aynı hareket tipindeki ardışık satırlarda `F` ve `G1` bir kez yazılıyor;
  değişmeyen eksen yazılmıyor — `test_gcode_writer.py`
- [ ] K4 Gidiş-dönüş: sabit tohumlu rastgele 200 hareketlik yol (G0/G1/G2/G3, helis, tam daire dahil;
  yaylarda kiriş ≥ r/2 veya tam daire) GRBL ve Fanuc ile yazılıp okununca: hareket tipleri aynı,
  uç noktalar koordinat başına ≤ 0.5·10⁻³ mm, ilerleme ≤ 0.05 mm/dk, yay merkezi ≤ 1e-2 mm,
  devir tam — `tests/cam/test_gcode_roundtrip.py`
- [ ] K5 Çok takımlı program: iki takım, üç op (ikisi aynı takım) → okununca iki yol; aynı takımlı op'lar
  birleşik hareket listesi — `test_gcode_roundtrip.py`
- [ ] K6 R biçimi: çeyrek yay (`R > 0`) ve 270° yay (`R < 0`) için G2 ve G3'te merkez bilinen noktada
  (1e-9 mm); `|R| < L/2` ve R ile tam daire `CamError` — `tests/cam/test_gcode_reader.py`
- [ ] K7 Yay doğrulama: `|r0 − r1| > arc_tol` → `CamError`; tolerans içindeki yayda merkez orta dikmeye
  düzeltilip `validate()` geçiyor — `test_gcode_reader.py`
- [ ] K8 Okuyucu hataları: K-listesindeki her `CamError` durumu (G20, G18, M4, bilinmeyen kod, bilinmeyen
  takım, ilerlemesiz G1, eksik başlangıç ekseni, T sonrası G1, G91'de çevrim) ve mesajda satır numarası — `test_gcode_reader.py`
- [ ] K9 Okuyucu ayrıntıları: yorumlar, `N`, `%`, `O`, küçük harf, boşluksuz kelimeler, `G91` artımsal
  hareketler bilinen mutlak noktalara gidiyor — `test_gcode_reader.py`
- [ ] K10 G81 açılımı: 3 delik, G98 ve G99 için hareket listesi elle yazılmış beklenenle aynı;
  sıfır boylu hareket yok — `tests/cam/test_gcode_cycles.py`
- [ ] K11 G83 analitik: `r = 2, z = −10, q = 3, c = 0.5` → `n = 4`, G1 sayısı 4, toplam G1 boyu
  `12 + 3·0.5 = 13.5` mm (rel 1e-12); son derinlik tam `z` — `test_gcode_cycles.py`
- [ ] K12 Dil bağımsızlığı: aynı `DrillOp` Fanuc'ta `G81/G83 ... G80` olarak, GRBL'de açılmış G0/G1 olarak
  yazılıyor; ikisi okununca aynı yol (≤ ε) ve `DrillOp.to_toolpath()` ile aynı — `test_gcode_cycles.py`
- [ ] K13 `DrillOp.validate()` her hata durumunu yakalıyor; G83'te `c ≥ q` → `CamError` — `test_gcode_cycles.py`
- [ ] K14 `write` geçersiz `Toolpath`'i (ör. ilerlemesiz G1) reddediyor (`CamError`) — `test_gcode_writer.py`
- [ ] Tüm testler yeşil, `ruff check .` temiz, bu SPEC'in testlerinde 0 "uygulanmamış"

## Kapsam dışı
- G41/G42 takım yarıçap telafisi çıktısı (araştırmada isteğe bağlıydı; takım yolu zaten merkez yolu
  olarak 03'ten geliyor). Okuyucu G41/G42'yi `CamError` ile reddeder; `G40` iptal olarak kabul edilir.
- G18/G19 düzlemleri, inç (G20), G91.1/G90.1, `M4` ters devir, G73/G82/G84+ çevrimleri, G4 bekleme,
  alt programlar (M98/M99), makro değişkenleri (#), takım boyu telafisi değerleri (G43 H).
- Delik gezi sırası optimizasyonu (TSP; 03 veya ayrı SPEC), işleme süresi tahmini (05).
- Soğutma sıvısı bilgisi: okuyucu M7/M8/M9'u kabul eder ama yola yansıtmaz (modelde alan yok).
- Gerçek makinede deneme; LinuxCNC, Heidenhain gibi başka diller (yeni `Dialect` örneği ile ileride).
- `cam/model.py` arayüz değişikliği (çevrim veya takım değişimi hareket tipi): ayrı arayüz PR'ı.

## Ek A — Yazım ayrıntıları (onaydan sonra eklenen netleştirmeler; kapsam değişmedi)
Testleri yazan (`dogrulayici`) ve kodu yazan (`yazici`) aynı metni üretsin diye:
- Satırlar `\n` ile ayrılır, metin `\n` ile biter. Bir satırdaki kelimeler tek boşlukla ayrılır.
- Baş satırlar (`G21 G90 G17 G94 ...`) yazıcının durumunu kurar: G90/G17/G21/G94 sonra tekrar yazılmaz.
  Başlangıçta hareket tipi, ilerleme, devir, takım ve konum bilinmiyor.
- Fanuc satır numarası `%` ve `O0001` dışındaki her satıra (son satırlar dahil) `N10`, `N20`... olarak verilir.
  Program numarası `O{program_no:04d}`.
- Takım değişimi satırı: Fanuc `T<n> M6`; GRBL ilk takımda `T<n>`, sonrakilerde `T<n> M0`.
  Ardından her zaman `S<rpm> M3` (rpm tam sayıya yuvarlanır, `S10000`). Devir tek başına değişirse sadece `S<rpm> M3`.
- Op başlangıç satırı: `G0` kelimesi ve üç eksen her zaman yazılır (`G0 X0. Y0. Z5.`).
- Bastırma yuvarlanmış metin üzerinden yapılır: `fmt(yeni) == fmt(durum)` ise eksen / `F` yazılmaz.
  G0'da `F` yazılmaz. Yayda `I` ve `J` her zaman (0 olsa da) yazılır; `X`, `Y`, `Z` sadece değiştiyse.
- Fanuc çevrimi: op başlangıcına `G0 X Y Z` yazıldıktan sonra ilk delik `G98 G81 X Y Z R F`
  (G83'te `R` ile `F` arasında `Q`), sonraki delikler sadece değişen `X`/`Y`, en sonda `G80`.
  `G80` sonrası hareket tipi bilinmiyor sayılır (sonraki hareket G kelimesini yazar); konum son deliğin
  (x, y, z_dön) noktasıdır. Okuyucuda çevrim `G80` ile veya bir G0/G1/G2/G3 ile biter; G98'deki `z0`
  çevrimin ilk satırındaki Z konumudur (çevrim boyunca sabit).
- Okuyucu hata mesajı `satır <n>` içerir (n: metindeki 1 tabanlı satır sırası).
- Okuyucu yol adı `T<n>-<k>`, k çıktı listesindeki 1 tabanlı sıra.

### Altın örnek (K2)
Takım `Tool(1, "freze6", FLAT, D=6, flute_length=20)`, `rpm = 10000`, `start = (0, 0, 5)`, hareketler:
`G1 (0,0,−1) F100`, `G1 (10,0,−1) F300`, `G1 (10,10,−1) F300`, `G3 (0,10,−1) merkez (5,10) F300`,
`G1 (0,0,−1) F300`, `G0 (0,0,5)`.

GRBL:
```
G21 G90 G17 G94
T1
S10000 M3
G0 X0. Y0. Z5.
G1 Z-1. F100.
X10. F300.
Y10.
G3 X0. I-5. J0.
G1 Y0.
G0 Z5.
M5
M30
```
Fanuc:
```
%
O0001
N10 G21 G90 G17 G94 G40 G49 G80
N20 T1 M6
N30 S10000 M3
N40 G0 X0. Y0. Z5.
N50 G1 Z-1. F100.
N60 X10. F300.
N70 Y10.
N80 G3 X0. I-5. J0.
N90 G1 Y0.
N100 G0 Z5.
N110 M5
N120 M30
%
```
