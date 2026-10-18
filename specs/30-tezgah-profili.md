# SPEC 30 — Tezgâh profilleri, tezgâh sınır denetimi ve postprosesör katmanı (GRBL, Fanuc, Haas)

> Durum: **taslak, kullanıcı onayı bekliyor.** Kod, `cam/gcode/writer.py`'ye dokunan açık PR'lar
> (CAM güvenlik düzeltmesi #33, SPEC 14 #27, SPEC 21) `main`'e girdikten sonra başlar.
> Devamı: SPEC 31 (Siemens Sinumerik ve Heidenhain Klartext), bu SPEC'in blok katmanını kullanır.

## Amaç
Bir CAM programını **belirli bir tezgâha** göndermeden önce o tezgâhın sınırlarına göre denetlemek ve
o tezgâhın kontrolörünün diliyle yazmak. Bu adım bitince:
- Bir tezgâh profili (JSON) eksen kurslarını, devir ve ilerleme sınırlarını, takım magazinini, program
  numarası aralığını ve kontrolör dilini taşıyor.
- `post(ops, machine, setup)` önce programı tezgâha karşı denetliyor (kurs dışı, devir / ilerleme
  sınırı, takım numarası, program numarası → `CamError`; **hiçbir değer sessizce kırpılmıyor**), sonra
  GRBL, Fanuc veya Haas dilinde yazıyor.
- Yazıcı iki aşamaya ayrılıyor: dilden bağımsız **blok planı** (bütün güvenlik mantığı burada, tek yerde)
  ve dile özel **biçimleyici**. GRBL ve Fanuc çıktısı bugünküyle **bayt bayt aynı** kalıyor; SPEC 31 aynı
  planı Siemens ve Heidenhain diline biçimliyor.

## Neden
Bugünkü `cam.gcode.write` tezgâhı tanımıyor: 30 000 dev/dk'lık bir yol 8 000 dev/dk'lık tezgâha da
yazılıyor. GRBL `$30`'dan yüksek `S`'yi **sessizce kırpar**, ilerleme `F = n·z·fz` ile hesaplandığı için
diş başı talaş katlanır ve takım kırılır. Kurs dışı bir nokta tezgâhta "soft limit" alarmıyla durur ama
program yarıda kalır (en iyi ihtimalle); limit tanımlı değilse eksen dayanağa vurur. Bu SPEC bu
hataları program tezgâha gitmeden yakalar.

## Teori

### Tezgâh koordinatı ve takım boyu
`cam/model.py` sözleşmesi (SPEC 00 Ek 2, SPEC 14):
- Program koordinatı takım **ucunun** iş koordinatıdır.
- `Wcs.origin` iş sıfırının makine koordinatıdır: uç makinede `p_m = p + origin` noktasında.
- Tezgâhın eksen kursu **iş mili ölçü hattı** (gauge line) için tanımlıdır; kontrolörün telafisiz
  gösterdiği Z budur. Takım ucu ölçü hattının `L = Tool.gauge_length` altındadır:
  `z_ölçü = z + origin_z + L`.
  Kaynak: Smid, *CNC Programming Handbook*, Bölüm 13 (takım boyu ofseti), Bölüm 11 (iş koordinatları).

Kurs denetimi her nokta için: `xmin ≤ x + ox ≤ xmax`, `ymin ≤ y + oy ≤ ymax`,
`zmin ≤ z + oz + L ≤ zmax`. `L` bilinmiyorsa (`gauge_length is None`) ve profilde Z kursu varsa
**`CamError`**: uzun takım tablaya, kısa takım Z üst sınırına çarpabilir; varsayılan boy kabul edilmez.

### Yayların kursu
Yay için yalnız uç noktaları denetlemek yetmez: çeyrek daire noktaları kursu aşabilir. Merkez `c`,
yarıçap `r`; süpürülen açı aralığında kalan her eksen yönü `θ ∈ {0, π/2, π, 3π/2}` için `c + r·(cos θ, sin θ)`
noktası da denetlenir. Helisin Z'si uçlar arasında doğrusal olduğundan Z için uçlar yeter.
Tam daire dört noktanın hepsini içerir. Delik op'ları kanonik açılımıyla (`DrillOp.to_toolpath`) denetlenir.
G0 hızlı hareketler de denetlenir (kursun dışına hızlı gitmek de çarpmadır).

### Devir ve ilerleme sınırı
Programdaki `S = round(rpm)` (SPEC 04). Denetim: `n_min ≤ S ≤ n_max`. Sınırın dışında **kırpma yok**:
`CamError` (mesajda op adı, istenen ve izin verilen değer, ve "kesme verisini SPEC 14 `milling(...,
n_max=...)` ile tezgâh sınırında yeniden hesaplayın" önerisi; bu ilerlemeyi de orantılı düşürür).
Kesme ilerlemesi (G1/G2/G3 ve delik ilerlemesi) `F ≤ feed_max`; `F > feed_max` → `CamError`.
G0 ilerlemesi tezgâhındır (`rapid`), denetlenmez; `rapid` alanı yalnız süre tahmini (SPEC 05) içindir.

### Takım ve program numarası
- `tool_slots` verilmişse `1 ≤ T ≤ tool_slots` (magazin cebi). Verilmemişse tezgâh elle takım değiştirir
  (GRBL); o zaman `T ≥ 1` yeter ve dil `M0` ile operatöre bırakır (SPEC 04).
- Program numarası profilin aralığında olmalı: Fanuc `O0001–O9999` (4 hane; 8000–9999 çoğu tezgâhta
  korumalıdır, örnek profil `1–7999` verir), Haas `O00001–O99999` (5 hane).
  Kaynak: Fanuc 0i-MF *Operator's Manual* (B-64604EN), program numarası; Haas *Mill Operator's Manual*,
  "Program numbers".

### Takım değişim konumu
Magazinli tezgâhta takım değişimi Z ekseni makine takım değişim yüksekliğindeyken yapılır. Profilde
`tool_change_z` (makine koordinatı, ölçü hattı) verilirse, her takım değişiminden önce güvenli Z'ye geri
çekmeden (SPEC 04 Ek B) **sonra** ayrıca `G53 G0 Z<tool_change_z>` yazılır (`G53` tek satırlık makine
koordinatı; Fanuc, Haas ve GRBL 1.1'de var). `tool_change_z` Z kursu içinde olmalı. Bu satırdan sonra
iş koordinatında Z konumu bilinmiyor sayılır; yazıcı zaten op başını üç eksenli `G0 X Y Z` ile yazar.
Kaynak: Fanuc 0i-MF, G53; GRBL 1.1 wiki "G-code commands" (G53).

### Yazıcının iki aşaması: blok planı ve biçimleyici
SPEC 04, 14 ve 04 Ek B/C'deki bütün sıralama ve güvenlik kararları (geri çekme, M5'ten sonra takım
değişimi, güvenli Z, `stock_top`, kısa yayın G1'e çevrilmesi, takım boyu telafisi, iş sıfırı, op başında
üç eksenli G0) **dilden bağımsızdır** ve tek yerde kalmalıdır. Bu SPEC yazıcıyı ikiye ayırır:

1. `plan(ops, decimals, ...) -> list[Block]` — modal durum makinesi (`ModalState`) ve güvenlik mantığı.
   Bloklar yuvarlanmış değerleri taşır (yazılacak sayının ta kendisi). Modal bastırma da burada kalır:
   blok, durumdan farklı olan eksenleri `None` dışı verir.
2. `format(blocks, dialect) -> str` — her blok tipini bir veya birkaç satıra çevirir; satır numarası,
   baş / son, sayı biçimi dile özgüdür. Biçimleyici karar vermez, yalnız yazar.

Bloklar (`cam/post/blocks.py`, `frozen` dataclass'lar): `Start(program_no, wcs)`, `ToolChange(tool, first)`,
`ToolLength(tool, delta)` (GRBL `G43.1`, Fanuc/Haas `G43 H` op başı satırının parçası olarak),
`Spindle(rpm)` (`None` → dur), `MachineZ(z)` (G53), `Rapid(x, y, z, g43_h)`, `Linear(x, y, z, F)`,
`Arc(x, y, z, i, j, ccw, F)`, `Cycle(kind, retract, x, y, z, r, q, F, first)`, `CycleEnd()`, `End()`.
Eksen alanı `None` ise "değişmedi, yazma" demektir. Torna yazıcısı (SPEC 21 `write_lathe`) bu ayrıma
bu SPEC'te katılmaz; aşağıdaki "Torna yazıcısıyla ilişki" bölümüne bakınız.

## Dosyalar
- Yeni: `cam/post/__init__.py`, `cam/post/blocks.py`, `cam/post/machine.py`, `cam/post/check.py`,
  `cam/post/format_iso.py` (GRBL / Fanuc / Haas biçimleyici), `cam/post/profiles/` (örnek profiller:
  `ornek-grbl-router.json`, `ornek-fanuc-dik.json`, `ornek-haas-dik.json`; **uydurma kurs ve sınırlar**,
  `verified: false`), `tests/cam/test_post_*.py`, `durum/30-tezgah-profili.md`.
- Değişecek: `cam/gcode/writer.py` (`write` = `format(plan(...))`; imza ve çıktı aynı),
  `cam/gcode/dialect.py` (`HAAS` örneği; `Dialect`'e geriye uyumlu, varsayılanlı alanlar),
  `cam/gcode/reader.py` (`G53 G0 Z` ve Haas başı okuma).
- Dokunulmayacak: `cam/model.py` ve tüm `*/model.py` (aşağıdaki arayüz önerisi ayrı PR), SPEC 04 / 14 /
  04 Ek C testleri (hepsi değişmeden geçer), `pyproject.toml`, `.github/`, `CLAUDE.md`, `BASLANGIC.md`,
  `DURUM.md`, `core/**`. Yeni bağımlılık yok.

### Arayüz önerisi (ayrı küçük PR, sahibi "CAM model arayüzü")
`MachineProfile` başka SPEC'lerin de verisidir: SPEC 05 (süre tahmini: `rapid`, `feed_max`), 4–5 eksen
SPEC'i (döner eksenler ve kinematik bu profile eklenir), SPEC 24 Tezgah (tezgâh seçimi). Bu yüzden
`cam/model.py`'de durmalıdır (saf Python, numpy yok):
```python
@dataclass(frozen=True)
class AxisLimits:  # makine koordinatı, mm; Z ölçü hattı için
    min: float
    max: float


@dataclass(frozen=True)
class MachineProfile:
    name: str  # ASCII [A-Z0-9 _-], programa yorum olarak yazılır
    controller: str  # "grbl" | "fanuc" | "haas" (SPEC 31: "sinumerik" | "heidenhain")
    kind: str = "mill"  # "mill" | "lathe" (torna profili SPEC 21'den sonra)
    x: AxisLimits | None = None  # None → o eksen denetlenmez (bilinçli seçim, profil yorumunda yazar)
    y: AxisLimits | None = None
    z: AxisLimits | None = None
    rpm_min: float = 0.0
    rpm_max: float = ...  # zorunlu, > 0
    feed_max: float = ...  # zorunlu, mm/dk, kesme ilerlemesi üst sınırı
    rapid: tuple[float, float, float] | None = None  # mm/dk, eksen başına (SPEC 05)
    tool_slots: int | None = None  # None → elle takım değişimi
    tool_change_z: float | None = None
    program_no_range: tuple[int, int] = (1, 9999)
    decimals: int = 3
    verified: bool = False  # kullanıcı bu profili gerçek tezgâhta kuru çalıştırmayla doğruladı mı

    def validate(self) -> None: ...
    def to_dict(self) -> dict: ...
    @classmethod
    def from_dict(cls, d: dict) -> MachineProfile: ...  # bilinmeyen anahtar → CamError
```
Arayüz PR'ı kabul edilmezse aynı sınıf `cam/post/machine.py`'de tanımlanır; bu SPEC'in testleri
`cam.post`'tan içe aktardığı için ikisinde de değişmez (`cam.post` yeniden dışa açar).

## Arayüz
Hepsi `cam.post`'tan dışa açılır. Hatalar `cam.model.CamError`; `nan` / `inf` → `CamError`.

### Profil
- `load_machine(path) -> MachineProfile` — UTF-8 JSON. Dosya yok, bozuk JSON, bilinmeyen / eksik anahtar,
  geçersiz değer → `CamError` (mesajda dosya yolu ve alan).
- `save_machine(m, path) -> None` — `json.dumps(m.to_dict(), ensure_ascii=False, indent=2) + "\n"`;
  `load(save(m)) == m`, iki kayıt aynı bayt.
- `builtin_machines() -> dict[str, MachineProfile]` — `cam/post/profiles/*.json`, ada göre.
- `MachineProfile.validate()` kuralları: `name` ASCII `[A-Z0-9 _-]` 1–32 karakter (Fanuc yorumunda
  Türkçe karakter ve küçük harf sorun çıkarır); `controller` bilinen dillerden; `min < max`;
  `0 ≤ rpm_min < rpm_max`; `feed_max > 0`; `rapid` bileşenleri `> 0`; `tool_slots ≥ 1`;
  `tool_change_z` Z kursu içinde (Z kursu yoksa `CamError`: konumu denetlenemeyen G53 yazılmaz);
  `1 ≤ program_no_range[0] ≤ program_no_range[1]` ve dilin hane sınırı içinde (Fanuc 9999, Haas 99999);
  `decimals ∈ {3, 4}`; `kind = "lathe"` şimdilik → `CamError` ("SPEC 21'den sonra").

### Denetim
- `check_machine(machine, ops, setup=None, program_no=1) -> None` — ilk ihlalde `CamError`.
  Mesaj: op adı, hareket sırası (1 tabanlı), ihlal türü, değer ve sınır.
  - Op'lar önce kendi `validate()`'inden geçer.
  - Torna takımlı / G18 / G95 / G96 op ve `kind = "mill"` → `CamError`.
  - Kurs: Teori'deki kurallar; `setup` verilmezse `origin = (0, 0, 0)` **kabul edilmez**: profilde en
    az bir eksen kursu varsa ve `setup` yoksa `CamError` ("iş sıfırı bilinmeden kurs denetlenemez").
  - Devir, ilerleme, takım numarası, program numarası, `tool_change_z`.
- `machine_extents(machine, ops, setup) -> dict[str, tuple[float, float]]` — op'ların makine
  koordinatında kapladığı aralık (`"x"`, `"y"`, `"z_ölçü"`); kullanıcıya "ne kadar pay kaldı" göstermek
  ve testler için.

### Yazma ve okuma
- `post(ops, machine, setup=None, program_no=1, safe_z=None, stock_top=None, length_offsets=None) -> str`
  1. `check_machine(machine, ops, setup, program_no)`.
  2. `plan(...)` (SPEC 04 / 14 / Ek C parametreleriyle aynı anlam; `setup` iş sıfırını ve güvenli Z'yi verir).
  3. `format(blocks, dialect_for(machine))`. `machine.decimals` koordinat basamağıdır.
  4. Programın ilk satırları (dilin baş satırlarından sonra, ilk hareketten önce) bir yorum:
     `(POST <name> <controller>)`; `verified` `False` ise ikinci yorum
     `(DOGRULANMAMIS PROFIL - ILK PARCADA KURU CALISTIRIN)`. Yorumlar ASCII ve büyük harftir.
- `dialect_for(machine) -> Dialect` — `grbl → GRBL`, `fanuc → FANUC`, `haas → HAAS`; `program_no`
  hane sayısı dilden.
- `read_program(text, machine, tools, arc_tol=0.005) -> list[Toolpath]` — dile göre okuyucu
  (`cam.gcode.read`); yorum satırları ve `G53 G0 Z` yola yansımaz.
- `cam.gcode.write(...)` imzası ve çıktısı değişmez; `write = format(plan(...), dialect)`.

### Haas dili (`HAAS`)
Fanuc ailesindendir; farklar (Haas *Mill Operator's Manual*, "G-codes", "M-codes"):
| | Fanuc (`FANUC`) | Haas (`HAAS`) |
|---|---|---|
| Program numarası | `O0001` (4 hane) | `O00001` (5 hane) |
| Satır numarası | `N10`, 10'ar | yok (Haas zorunlu tutmaz; okunurluk için kapalı) |
| Takım değişimi | `T1 M6` | `T1 M06` |
| Baş | `G21 G90 G17 G94 G40 G49 G80 G54` | aynı |
| Takım boyu | `G43 ... H1` | `G43 ... H01` (iki hane) |
| Çevrim | `G98 G81/G83 ... G80` | aynı |
Varsayım (doğrulanmalı): Haas NGC `M6` ve `M06`'yı, `H1` ve `H01`'i eşdeğer okur; iki haneli yazım Haas
belgelerindeki örneklere uymak içindir. Okuyucu her iki yazımı kabul eder.

### Torna yazıcısıyla ilişki (SPEC 21)
SPEC 21 torna dilini (`LatheDialect`, `FANUC_TORNA`, `cam/gcode/lathe.py`) ve `write_lathe(ops, spindle,
tool_change, ...)`'i tanımlar; bu SPEC bunları **yeniden tanımlamaz**. İş mili yönü (`M3`/`M4`) takımın
tarete bağlanışına göre op'tan op'a değişebilir ve takım değiştirme noktası iş koordinatındadır; ikisi
de tezgâh profilinin değil kurulumun bilgisidir. Bu yüzden ikisi `write_lathe`'in zorunlu parametresi
kalır, profil onlara **varsayılan vermez**.
Torna eki (`kind = "lathe"`, SPEC 21 birleşince bu SPEC'e Ek A olarak) profilden şunları besler:
- `dialect_for(machine)` → `FANUC_TORNA` (ileride başka `LatheDialect`);
- denetim: X kursu **çap** olarak (`x_çap = 2·x`, SPEC 21 sistem A), Z kursu; `Toolpath.rpm` (G50 devir
  üst sınırı) `≤ rpm_max`, sabit devirde `S ≤ rpm_max`; `G96` op'unda `rpm` yoksa SPEC 14 / 21 zaten `CamError`;
  taret istasyonu `1 ≤ T ≤ tool_slots`; takım değiştirme noktası (`tool_change`, iş koordinatı) iş sıfırıyla
  makineye çevrilip kurs içinde olmalı;
- `post_lathe(ops, machine, setup, spindle, tool_change, ...)` = `check_machine` + `write_lathe(...)`.
Freze tarafında `post()` aynı profil alanlarını `plan()`'a (`decimals`, `tool_change_z`) ve
`dialect_for()`'a besler; `cam.gcode.write`'ın kendi parametreleri (`safe_z`, `stock_top`, `setup`,
`length_offsets`) olduğu gibi geçirilir.

## Kabul kriterleri
- [ ] K1 Bayt bayt uyum: `write(...)` SPEC 04 Ek A/B altın metinlerini, SPEC 14 ve 04 Ek C örneklerini
  aynen üretiyor; mevcut `tests/cam/test_gcode_*.py` ve SPEC 14 testleri değişmeden yeşil —
  `tests/cam/test_post_compat.py` (ek olarak 50 rastgele op listesinde eski yazıcının bu dalın başındaki
  kopyasıyla metin eşitliği)
- [ ] K2 Plan / biçim ayrımı: Ek A yolunun `plan()` çıktısı elle yazılmış blok listesine eşit (bloklarda
  yuvarlanmış değerler, değişmeyen eksen `None`) — `tests/cam/test_post_blocks.py`
- [ ] K3 Profil dosyası: üç örnek profil yükleniyor; `save → load` eşit, iki kayıt aynı bayt; dosya yok /
  bozuk JSON / bilinmeyen anahtar / eksik `rpm_max` → `CamError` (mesajda yol ve alan) —
  `tests/cam/test_post_machine.py`
- [ ] K4 Profil doğrulama: `validate()`'in her kuralı (ASCII ad, `min ≥ max`, `rpm_min ≥ rpm_max`,
  `feed_max ≤ 0`, `tool_change_z` kurs dışı / Z kursu yok, program aralığı hane dışı, `decimals = 2`,
  `kind = "lathe"`, `nan`) ayrı ayrı `CamError` — `test_post_machine.py`
- [ ] K5 Kurs, doğrusal: X kursu `[0, 500]`, `origin = (100, 0, 0)`: `x = 400` geçer, `x = 400.001` →
  `CamError`, mesajda op adı ve hareket sırası; G0 hareketi de yakalanıyor — `tests/cam/test_post_check.py`
- [ ] K6 Kurs, yay: uçları kursun içinde, çeyrek noktası dışında kalan G2 ve G3 yayı (`c = (490, 0)`,
  `r = 20`, X kursu `[0, 500]`, 0° noktası süpürülüyor) → `CamError`; aynı yayın tersi (0° süpürülmüyor)
  geçer; tam daire dört noktayı da denetliyor — `test_post_check.py`
- [ ] K7 Kurs, Z ve takım boyu: Z kursu `[-400, 0]`, `origin_z = -350`, `gauge_length = 100`:
  `z = 250` geçer (`z_ölçü = 0`), `z = 250.001` → `CamError`; `z = -150` geçer (`-400`), `-150.001` →
  `CamError`; `gauge_length = None` → `CamError`; `setup` yokken kurslu profil → `CamError` —
  `test_post_check.py`
- [ ] K8 Devir ve ilerleme: `rpm_max = 8000`: `rpm = 8000.4` (S = 8000) geçer, `8000.5` (S = 8001) →
  `CamError`, metin hiç üretilmiyor (kırpma yok); `rpm_min = 100`, `rpm = 50` → `CamError`;
  `feed_max = 5000`: G1, G2 ve `DrillOp` ilerlemesi `5000.01` → `CamError`, G0 denetlenmiyor —
  `test_post_check.py`
- [ ] K9 Takım ve program numarası: `tool_slots = 20`, `T21` → `CamError`, `T20` geçer;
  `tool_slots = None` → her `T ≥ 1`; Fanuc profilinde `program_no = 8000` (aralık 1–7999) → `CamError`;
  Haas `program_no = 12345` → `O12345` — `test_post_check.py`
- [ ] K10 `machine_extents`: bilinen kare + yarım daire yolunda (Ek A) X, Y, `z_ölçü` aralıkları analitik
  (yarım dairenin tepe noktası dahil) 1e-12 — `test_post_check.py`
- [ ] K11 Takım değişim konumu: `tool_change_z = 0` iki takımlı programda her takım değişiminden önce
  sırayla `G0 Z<safe_z>`, `M5`, `G53 G0 Z0.`, `T2 M6` satırları; okuyucu `G53 G0 Z` satırını kabul ediyor,
  yol aynı (≤ ε) — `tests/cam/test_post_iso.py`
- [ ] K12 Haas altın metin: Ek A yolu `ornek-haas-dik` profiliyle satır satır beklenen metne eşit (aşağıda)
  — `test_post_iso.py`
- [ ] K13 Yorumlar: `verified = False` profilde iki yorum satırı, `True`'da yalnız `(POST ...)`; okuyucu
  yorumları yok sayıyor — `test_post_iso.py`
- [ ] K14 Gidiş-dönüş: SPEC 04 K4'teki rastgele yollar (sabit tohum, `safe_z` verilerek) üç dilin örnek
  profilleriyle `post → read_program`: hareket tipleri aynı, uçlar ≤ `0.5·10⁻³` mm, merkez ≤ 1e-2 mm —
  `tests/cam/test_post_roundtrip.py`
- [ ] K15 Bağımsız çapraz kontrol: üç dilin çıktısı `tests/reference/gcode_ref.RefMachine` ile yürütülüp
  `gcode_check.compare(expected(ops), trace)` boş ve `safety(...)` boş; LinuxCNC `rs274` CI'da varsa
  (`@pytest.mark.rs274`, yoksa atlanır) aynı karşılaştırma onunla da — `tests/reference/test_post_crosscheck.py`
- [ ] K16 Tüm testler yeşil, `ruff check .` ve `ruff format --check .` temiz, 0 "uygulanmamış"

### Haas altın metni (K12)
SPEC 04 Ek A yolu, `safe_z = 5`, profil `ORNEK-HAAS-DIK` (`verified: false`), `setup` iş sıfırı G54:
```
%
O00001
G21 G90 G17 G94 G40 G49 G80 G54
(POST ORNEK-HAAS-DIK HAAS)
(DOGRULANMAMIS PROFIL - ILK PARCADA KURU CALISTIRIN)
T1 M06
S10000 M3
G0 G43 X0. Y0. Z5. H01
G1 Z-1. F100.
X10. F300.
Y10.
G3 X0. I-5. J0.
G1 Y0.
G0 Z5.
M5
M30
%
```
(Örnek profilde `tool_change_z` var ama tek takımlı programda ilk takımdan önce iş mili zaten makine
sıfırındadır varsayımı **yapılmaz**: ilk takım değişiminden önce de `G53 G0 Z<tool_change_z>` yazılır.
Bu yüzden altın metin, `tool_change_z = None` olan profil kopyasıyla üretilir; K11 G53'ü ayrıca sınar.)

## Kapsam dışı
- Siemens Sinumerik ve Heidenhain Klartext: SPEC 31.
- Torna tezgâhı profilleri ve denetimi: SPEC 21 birleştikten sonra bu SPEC'e ek (aşağıdaki bölüm).
- Döner eksenler (A/B/C), 3+2 ve 5 eksen kinematiği: 4–5 eksen SPEC'i `MachineProfile`'a ekler.
- İşleme süresi tahmini, ivme / sarsıntı (jerk) modeli: SPEC 05 (`rapid` ve `feed_max` alanlarını kullanır).
- Soğutma sıvısı (M7/M8), yüksek hız modu (Fanuc `G05.1`, Haas `G187`), alt programlar, makrolar.
- Program boyutu / bellek sınırı, DNC ile gönderme.
- Gerçek tezgâhta doğrulama: kullanıcı yapar (`docs/tezgah-dogrulama.md`); profil `verified: true`
  yalnız kullanıcı tarafından işaretlenir.

## Teknik kararlar (koordinatör, 2026-10-18)
1. `MachineProfile` ve `AxisLimits` `cam/model.py`'ye girer; ayrı arayüz PR'ı ("CAM model arayüzü" thread'i).
   Bu SPEC'in PR'ı `cam/model.py`'ye dokunmaz.
2. `Wcs.origin` sözleşmesi SPEC 14'ün `wcs_from_touch` tanımına uyar; SPEC 14 birleşince Teori'deki
   `z_ölçü` formülü ona göre netleştirilir.
3. Profilde eksen kursu varken `setup` zorunludur (yoksa `CamError`).
