# SPEC 04b — Punta, havşa (pah) ve kılavuz çevrimleri (G82, G84)

> Durum: **taslak, kullanıcı onayı bekliyor.** Dalga 5, hat H2 (`yol-haritasi/dalga-5-onerisi.md`).
> Bağımlılıklar: arayüz eki A0 (`cam/model.py`, "CAM model arayüzü" thread'i), SPEC 30 (blok planı ve
> biçimleyici) ve SPEC 31 (Sinumerik / Heidenhain). Paylaşılan dosyalara gereken ekler bu SPEC'te
> **liste olarak** verilir ("Paylaşılan dosyalara ekler"); onları sahip thread'ler sırayla yapar.

## Amaç
SPEC 23'ün ürettiği delik kayıtlarındaki (`Hole`) **havşa** ve **diş** bilgisini, ve her deliğin
**punta** ile başlatılmasını CAM işlemine çevirmek. Bu adım bitince:
- `cam/cevrimler.py` bir delik listesinden punta, havşa ve kılavuz op'ları üretiyor; derinlik, ilerleme ve
  devir el hesabıyla doğrulanmış formüllerden geliyor, takım ile delik uyuşmuyorsa `CamError`.
- Op'lar Fanuc ve Haas'ta `G82` / `G84` çevrimi olarak, GRBL'de açılmış `G0/G1` + `G4` bekleme olarak
  yazılıyor; kılavuz desteklemeyen dilde (GRBL) **hiç metin üretilmeden** `CamError`.
- Okuyucu `G82`, `G84`, `M29` ve `G4`'ü okuyor; gidiş-dönüş SPEC 04 toleransında.
- SPEC 29'un `havsa_takimi_yok` ve `kilavuz_cevrimi_yok` gerekçeleri artık bu op'larla karşılanabilir
  (29'un kendisi bu SPEC'te değişmez).

## Teori

### Takım türleri (arayüz eki A0, aşağıda)
| Tür | Geometri | Kullanılan alanlar |
|---|---|---|
| `SPOT` (punta matkabı) | Sivri koni, tam uç açısı `σ` (90° veya 120° yaygın) | `D`, `tip_angle = σ` |
| `CHAMFER` (havşa / pah frezesi) | Koni, tam açı `α`, uçta düz kısım çapı `d_t` (`0 ≤ d_t < D`) | `D`, `tip_angle = α`, `tip_d = d_t` |
| `TAP` (kılavuz) | Nominal çap `d_n = D`, hatve `P`, giriş pahı `l` diş | `D`, `pitch = P`, `lead = l` |

### Punta derinliği
Sivri koninin, yüzeyde `d_s` çaplı iz bırakması için uç derinliği:
`h_s = (d_s / 2) · cot(σ / 2)`.
Örnek: `σ = 90°`, `d_s = 6` → `h_s = 3`; `σ = 120°`, `d_s = 6` → `h_s = √3 = 1.7320508...`
Koşul: `0 < d_s ≤ D` (iz takımın koni kısmından geniş olamaz), yoksa `CamError`.
Varsayılan `d_s` = deliğin matkap çapı `Hole.d` (matkabın dış köşeleri punta konisine oturur; yaygın uygulama).
Kaynak: Machinery's Handbook, "Drilling" / "Spotting and centering"; Smid, *CNC Programming Handbook*, Bölüm 22 (G82).

### Havşa (pah) derinliği
Havşa ağız çapı `D_h = Hole.csk_d`, havşa tepe açısı `α_h = Hole.csk_angle`. Takımın açısı havşanınkine
**eşit olmalı** (`|α − α_h| ≤ 1e-9°`), yoksa koni yanlış açıda olur → `CamError`. Uç derinliği:
`h_c = (D_h − d_t) / 2 · cot(α / 2)`.
Örnek: `α = 90°`, `D_h = 12`, `d_t = 2` → `h_c = 5`; `α = 82°`, aynı ölçüler → `h_c = 5·cot 41° = 5.751842036...`
Koşullar (`CamError`):
- `D_h ≤ D` (havşa takımın konisine sığmalı);
- `d_t < Hole.d` (düz uç deliğin içinde kalmalı; yoksa delik ağzında düz bir halka bırakır);
- kör delikte `h_c ≤ Hole.depth`.
Havşa, delik açıldıktan sonra yapılır; takım deliğin içine dalar, bu yüzden `center_cutting` denetlenmez
(`d_t < Hole.d` koşulu düz ucun malzemeye değmediğini zaten garanti eder).

### Kılavuz: derinlik, ilerleme ve devir
**Derinlik.** Kılavuzun ilk `l` dişi giriş pahıdır, tam diş açmaz. Tam dişli boy `t_d = Hole.thread_depth`
için kılavuz ucu yüzeyden `h_t = t_d + l · P` iner. Kör delikte `h_t ≤ Hole.depth` olmalı; yoksa kılavuz
dibe vurur ve kırılır → `CamError` (mesajda `h_t`, `depth` ve "daha kısa giriş pahlı kılavuz veya daha derin
delik" önerisi). Boydan boya delikte `t_d = depth` ve kılavuz `l · P` kadar alttan çıkar (altta boşluk
gerekir; bağlama çarpışması SPEC 44'ün işi). Ayrıca `h_t ≤ flute_length`.
Kaynak: ISO 8830 (kılavuz giriş pahı biçimleri: C 2–3 diş, B 3.5–5.5 diş); Machinery's Handbook, "Tapping".

**İlerleme.** Rijit kılavuzda iş mili ile Z eşzamanlıdır; ilerleme hatveye tam eşit olmalıdır:
`F = S · P` [mm/dk, G94], `S = round(rpm)`. Yazılan `F` metni yuvarlanırsa kontrolör `F/S`'yi hatve
sayar ve diş bozulur. Bu yüzden **yuvarlama kabul edilmez**: `S · P`, dilin ilerleme basamağıyla
(`feed_decimals`, GRBL/Fanuc/Haas'ta 1) tam yazılabilmelidir, yani `S·P·10^fd` tam sayı olmalı
(`|S·P·10^fd − round(·)| ≤ 1e-9`), yoksa `CamError`.
Yardımcı: `tap_rpm(n, P, fd)` = `n`'yi aşmayan ve koşulu sağlayan en büyük tam sayı `S` (`S ≥ 1` yoksa `CamError`).
Örnek: `P = 1.25`, `fd = 1`: `S = 500` → `F = 625` geçer; `S = 333` → `416.25` yazılamaz → `CamError`;
`tap_rpm(333, 1.25, 1) = 332` (`F = 415`). ISO kaba hatvelerin hepsi (`P` en çok 2 ondalık, sonu 5) çift
`S` ile `fd = 1`'de tam yazılır.
Kaynak: Fanuc 0i-MF *Operator's Manual* (B-64604EN), "Rigid tapping"; Smid Bölüm 22 (G84).

**Rijit kılavuz modu.** Fanuc'ta `G84`'ten önce `M29 S<rpm>` rijit modu açar (parametre 5200#0 ile
kapatılabilir; Açık soru 2). Haas'ta rijit kılavuz seçeneği varsa `G84` doğrudan rijittir, `M29` yazılmaz.
GRBL 1.1'de eşzamanlı iş mili ve `G84` yoktur: kılavuz op'u → `CamError` ("bu kontrolör kılavuz çekemez").

### Kanonik açılımlar (SPEC 04 tanımlarıyla: başlangıç `z0`, R düzlemi `r`, dip `z`, dönüş `z_dön`)
- **G82** (punta, havşa): G81 ile aynı hareketler + dipte `w` saniye bekleme:
  `G0 (x, y, z_akım)` → `G0 (x, y, r)` → `G1 (x, y, z) F` → [bekle `w`] → `G0 (x, y, z_dön)`.
  Bekleme `Toolpath`'te temsil edilmez (yalnız süre; SPEC 05'in konusu); `to_toolpath()` G81 açılımının
  aynısını verir.
- **G84** (kılavuz): `G0 (x, y, z_akım)` → `G0 (x, y, r)` → `G1 (x, y, z) F` → [iş mili ters] →
  `G1 (x, y, r) F` → [iş mili ileri] → `G0 (x, y, z_dön)` (`G99`'da `z_dön = r`, son hareket sıfır boylu,
  yazılmaz). Çıkış da `F` ile yapılır (hızlı değil); bu SPEC 04 açılımından tek farktır.
- Boyu sıfır olan hareketler yazılmaz (SPEC 04 kuralı).

Analitik sonuçlar (tek delik, `G98`, `z_akım = z0`):
- G82: G1 sayısı 1, toplam G1 boyu `r − z`; toplam bekleme `n_delik · w`.
- G84: G1 sayısı 2, toplam G1 boyu `2 (r − z)`; G1'lerin süresi `2 (r − z) / F = 2 (r − z) / (S·P)` dk.

### Delik kaydından op'a
- Yalnız düşey delikler: `Hole.axis = (0, 0, −1)` (`1e-9` içinde); değilse `CamError` (eğimli delik 3+2
  ile SPEC 41'in işi). Deliğin üst yüzü `z_top = Hole.origin[2]`.
- R düzlemi `r = z_top + r_clear` (`r_clear` varsayılan 2 mm), dip `z = z_top − h` (`h` = `h_s`, `h_c` veya `h_t`).
- Bir op'taki delikler aynı `z` ve `r`'yi paylaşır (SPEC 04 `DrillOp` gibi): delikler giriş sırası
  korunarak `(z_top, h)` değerine göre gruplanır, her grup ayrı op olur (op adı `<ad>-<k>`, k 1 tabanlı).
- Gezi sırası optimizasyonu yok; sıra girdinin sırasıdır.

## Dosyalar
- Yeni: `cam/cevrimler.py`; `tests/cam/test_cevrimler.py` (hesap, op, açılım),
  `tests/cam/test_cevrimler_gcode.py` (yazma / okuma; SPEC 30 blok ekleri birleşince yeşile döner);
  `durum/04b-cevrimler.md`.
- Kullanılır (değişmez): `cam/model.py`, `cam/gcode/` (`Dialect`, `DrillOp` tanımları), `cam/post/`,
  `geometry/part.py` (`Hole`; `cam` → `geometry` yalnız `model.py` / `part.py` arayüzü üzerinden).
- Dokunulmayacak (sahipleri ekler, aşağıdaki listeye göre): `cam/model.py`, `cam/gcode/**`, `cam/post/**`,
  `tests/reference/**`, `pyproject.toml`, `.github/`, `CLAUDE.md`, `BASLANGIC.md`, `DURUM.md`,
  `docs/yol-haritasi.md`, `core/**`. Yeni bağımlılık yok.

### Arayüz eki A0 (ayrı PR, "CAM model arayüzü" sahibi)
`ToolKind`'a `SPOT = "punta"`, `CHAMFER = "havsa"`, `TAP = "kilavuz"`. `Tool`'a (PR #60'taki `tip_angle`
üstüne):
```python
tip_angle: float | None = None  # mevcut (06b); SPOT ve CHAMFER için de zorunlu, 0 < φ < 180
tip_d: float = 0.0  # mm, CHAMFER düz uç çapı, 0 ≤ tip_d < D; diğer türlerde 0 olmalı
pitch: float | None = None  # mm, TAP için zorunlu (> 0); diğer türlerde verilirse CamError
lead: float | None = None  # diş, TAP giriş pahı (> 0); TAP için zorunlu; diğerlerinde CamError
```
Ek doğrulama: `SPOT`, `CHAMFER`: `corner_r = 0`; koni yüksekliği `(D − d_t)/2 · cot(φ/2) ≤ flute_length`.
`TAP`: `corner_r = 0`, `lead · pitch < flute_length`. `to_dict` / `from_dict` yeni alanları taşır.
A0 birleşmeden bu SPEC'in kodu yazılamaz (iskelet `NotImplementedError` ile kurulabilir).

### Paylaşılan dosyalara ekler (koordinatör üzerinden sahiplere; bu SPEC'in PR'ı yapmaz)
SPEC 30 sahibi ("Postprosesörler ve tezgâh profilleri"), `cam/post/` ve `cam/gcode/`:
1. `Cycle` bloğu: `kind ∈ {G81, G82, G83, G84}`; yeni alan `p: float | None` (bekleme, saniye; yalnız G82).
2. Yeni blok `RigidTap(rpm)`: Fanuc `M29 S<rpm>`; Haas'ta satır yok (biçimleyici yok sayar).
3. Yeni blok `Dwell(seconds)` (açılmış G82 için): GRBL `G4 P<s>` (saniye, `fmt(s, 3)`); Sinumerik `G4 F<s>`;
   Heidenhain `CYCL DEF 9.0 DWELL TIME` + `CYCL DEF 9.1 DWELL<s>` (SPEC 31 sahibi; varsayım, doğrulanmalı).
4. `plan()`: bu SPEC'in `DwellDrillOp` ve `TapOp`'unu kabul eder. Op'lar `DrillOp` ile aynı alan adlarını
   taşır (`tool, rpm, start, holes, z, r, feed, retract`, artı `kind`, `dwell`); `canned_cycles` dilde
   `Cycle`, değilse açılım + `Dwell`. `TapOp` + çevrimsiz dil veya `rigid_tap = ""` dil → `CamError`
   (metin üretilmeden). Takım değişimi / güvenli Z / `stock_top` kuralları `DrillOp`'unkiyle aynı.
5. `Dialect`'e geriye uyumlu alan `rigid_tap: str` — `"m29"` (FANUC), `"g84"` (HAAS), `""` (GRBL ve 31'in dilleri).
6. Biçim: G82 satırında kelime sırası `G98 G82 X Y Z R P F`; Fanuc `P` tam sayı milisaniye (`P500` = 0.5 s),
   Haas `P` ondalıklı saniye (`P0.5`). G84 satırı `G98 G84 X Y Z R F` (Q yok).
   Varsayım (doğrulanmalı): Haas G82 `P`'yi ondalık noktalıyken saniye okur.
7. Okuyucu (`cam/gcode/reader.py`): `G82` (P zorunlu), `G84`, `M29 S`, `G4 P` kabul; çevrimler kanonik
   açılıma çevrilir. `G84` iş mili dönmüyorken (`M3` yok) veya `M4` ile → `CamError`; `G84` satırında `Q`
   → `CamError` (gagalı kılavuz kapsam dışı). Fanuc dilinde `G84`'ten önce aynı `S` ile `M29` yoksa → `CamError`.
8. `check_machine` (`cam/post/check.py`): kılavuz `F` de `feed_max`'e tabidir; açılım `DrillOp` gibi denetlenir.

SPEC 31 sahibi: madde 3'teki `Dwell` biçimi; `TapOp` için Açık soru 1'in kararı.

Test thread'i (bu SPEC'in testleriyle birlikte, `tests/reference/` sahibi izin verirse):
9. `tests/reference/gcode_ref.RefMachine`'e LinuxCNC tanımıyla `G82` (P saniye) ve `G84`; K12 için.

## Arayüz
Hepsi `cam.cevrimler`'den dışa açılır. Hatalar `cam.model.CamError`; `nan` / `inf` → `CamError`.

### Hesap
- `spot_depth(tool, d_s) -> float` — `h_s`; `tool.kind` `SPOT` değilse, `d_s ≤ 0` veya `d_s > D` → `CamError`.
- `chamfer_depth(tool, csk_d, csk_angle, d) -> float` — `h_c`; tür `CHAMFER` değil, açı uyuşmuyor,
  `csk_d > D`, `tip_d ≥ d`, `csk_d ≤ d` → `CamError`.
- `tap_depth(tool, thread_depth) -> float` — `h_t = t_d + lead · pitch`; tür `TAP` değil veya `t_d ≤ 0` → `CamError`.
- `tap_feed(rpm, pitch, feed_decimals=1) -> float` — `S · P` (`S = round(rpm)`); tam yazılamıyorsa `CamError`.
- `tap_rpm(n, pitch, feed_decimals=1) -> int` — Teori'deki tanım.

### Op'lar
- `@dataclass DwellDrillOp(name, tool, rpm, start, holes, z, r, feed, dwell, retract="G98")`, `kind = "G82"`.
  `validate()` → `CamError`: `DrillOp` kuralları (rpm, feed, delik, `z < r ≤ start_z`, retract) ve
  `dwell > 0`; `tool.kind ∉ {SPOT, CHAMFER, DRILL}`; `dwell` 1 ms'nin katı değil (`|1000·w − round| > 1e-9`).
  `to_toolpath(dialect=GRBL) -> Toolpath` — kanonik açılım (G81'inkiyle aynı hareketler).
- `@dataclass TapOp(name, tool, rpm, start, holes, z, r, retract="G98", feed_decimals=1)`, `kind = "G84"`.
  `feed` özelliği `tap_feed(rpm, tool.pitch, feed_decimals)`. `validate()` → `CamError`: `DrillOp` kuralları,
  `tool.kind ≠ TAP`, `tap_feed` hatası. `to_toolpath(dialect=GRBL)` — G84 kanonik açılımı (dil yalnız
  arayüz uyumu için; açılım dile bağlı değil).

### Delik kaydından
Ortak parametreler: `holes: list[Hole]`, `tool`, `rpm`, `start: tuple[float, float, float]`,
`name`, `r_clear=2.0`, `retract="G98"`. Dönüş: `list[...Op]` (Teori'deki gruplama). Boş liste → `CamError`.
- `spot_ops(holes, tool, rpm, feed, start, d_s=None, dwell=0.2, ...) -> list[DwellDrillOp]` —
  `d_s=None` → her delik için `Hole.d`.
- `chamfer_ops(holes, tool, rpm, feed, start, dwell=0.2, ...) -> list[DwellDrillOp]` — havşasız delik
  (`csk_d = 0`) → `CamError` (seçimi çağıran yapar; SPEC 29 süzer).
- `tap_ops(holes, tool, rpm, start, feed_decimals=1, ...) -> list[TapOp]` — dişsiz delik, `tool.D ≠ thread_d`
  veya `tool.pitch ≠ Hole.pitch` (`1e-9`) → `CamError`; kör delikte `h_t > depth` → `CamError`.
- Hepsinde düşey olmayan delik → `CamError` (mesajda delik sırası).

## Kabul kriterleri
- [ ] K1 `spot_depth`: `σ = 90°, d_s = 6 → 3`; `σ = 120°, d_s = 6 → √3` (rel 1e-12); `d_s > D`, `d_s ≤ 0`,
  SPOT olmayan takım → `CamError` — `tests/cam/test_cevrimler.py`
- [ ] K2 `chamfer_depth`: `α = 90°, D_h = 12, d_t = 2 → 5`; `α = 82° → 5·cot 41°` (rel 1e-12); `d_t = 0`
  sivri uç; açı farkı, `D_h > D`, `d_t ≥ d`, `D_h ≤ d` → `CamError` — `test_cevrimler.py`
- [ ] K3 Kılavuz ilerlemesi: `P = 1.25`: `S = 500 → F = 625`; `S = 333` → `CamError`; `tap_rpm(333, 1.25, 1) = 332`;
  ISO kaba hatve tablosunun (SPEC 23 `THREADS_COARSE`) her girişi için `tap_rpm(1000, P, 1)` sonucu koşulu
  sağlıyor ve `F/S = P` (rel 1e-12) — `test_cevrimler.py`
- [ ] K4 Kılavuz derinliği: M8 (`P = 1.25`, `lead = 3`), `t_d = 12` → `h_t = 15.75`; kör `depth = 16` geçer,
  `depth = 15.7` → `CamError`; boydan boya delikte `h_t = depth + 3.75` — `test_cevrimler.py`
- [ ] K5 Delik kaydından op: SPEC 23 `tapped_hole` + `countersink_hole` ile üretilmiş (uydurma) blokta
  `spot_ops`, `chamfer_ops`, `tap_ops` beklenen `z`, `r`, delik XY'leri ve gruplamayı veriyor (iki farklı
  üst yüz yüksekliği → iki op, sıra korunmuş); eğimli delik, havşasız delikte `chamfer_ops`, dişsiz delikte
  `tap_ops`, çap / hatve uyuşmazlığı → `CamError` — `test_cevrimler.py` (`@pytest.mark.occt`; OCCT'siz
  sürümü elle kurulmuş `Hole` kayıtlarıyla)
- [ ] K6 Açılım analitik: G82 tek delik G1 sayısı 1, boy `r − z`; G84 G1 sayısı 2, boy `2 (r − z)`, ikinci G1
  yukarı ve aynı `F`; G99'da sıfır boylu hareket yok; 3 delikli G98 ve G99 açılımı elle yazılmış listeye
  eşit — `test_cevrimler.py`
- [ ] K7 `validate()`: her hata durumu ayrı ayrı (`dwell ≤ 0`, ms katı olmayan `dwell`, yanlış takım türü,
  `z ≥ r`, `r > start_z`, yazılamayan kılavuz `F`) `CamError` — `test_cevrimler.py`
- [ ] K8 Fanuc altın metni (punta, aşağıda Örnek A) ve kılavuz (Örnek B), `M29` dahil, satır satır eşit —
  `tests/cam/test_cevrimler_gcode.py`
- [ ] K9 Haas: Örnek B `HAAS` dilinde `M29`'suz, `T5 M06`, `H05`; Örnek A'da `P0.5` — `test_cevrimler_gcode.py`
- [ ] K10 GRBL: Örnek A açılmış `G0/G1` + `G4 P0.5` olarak (aşağıda) satır satır eşit; `TapOp` içeren
  op listesi → `CamError`, hiç metin dönmüyor — `test_cevrimler_gcode.py`
- [ ] K11 Gidiş-dönüş: Örnek A ve B (ve 3 delikli G99 sürümleri) Fanuc ve Haas ile yazılıp okununca yol
  `to_toolpath()` ile aynı (uçlar ≤ `0.5·10⁻³` mm, `F` tam); okuyucu `G84` öncesi `M29`'suz Fanuc metni,
  `M3`'süz `G84`, `G84 ... Q` → `CamError` (mesajda satır numarası) — `test_cevrimler_gcode.py`
- [ ] K12 Bağımsız çapraz kontrol: Örnek A ve B'nin Fanuc çıktısı `tests/reference/gcode_ref.RefMachine`
  (LinuxCNC G82/G84 tanımı) ile yürütülünce iz `to_toolpath()` ile aynı — `tests/reference/test_cevrimler_crosscheck.py`
- [ ] K13 Tezgâh denetimi: `feed_max = 600` profilde Örnek B (`F = 625`) → `post()` `CamError` — `test_cevrimler_gcode.py`
- [ ] K14 Tüm testler yeşil, `ruff check .` ve `ruff format --check .` temiz, bu SPEC'in testlerinde 0 "uygulanmamış"

### Örnek A — punta (G82)
Takım `Tool(3, "punta10", SPOT, D=10, flute_length=20, tip_angle=90)`, `rpm = 2000`, `feed = 200`,
`dwell = 0.5`, `start = (0, 0, 5)`, delikler `(10, 10)` ve `(30, 10)`, `z_top = 0`, `d_s = 6` → `z = −3`, `r = 2`, `G98`.

Fanuc (`write(..., FANUC)`, SPEC 04 Ek B başı ve `G43`):
```
%
O0001
N10 G21 G90 G17 G94 G40 G49 G80 G54
N20 T3 M6
N30 S2000 M3
N40 G0 G43 X0. Y0. Z5. H3
N50 G98 G82 X10. Y10. Z-3. R2. P500 F200.
N60 X30.
N70 G80
N80 M5
N90 M30
%
```
GRBL:
```
G21 G90 G17 G94
T3
S2000 M3
G0 X0. Y0. Z5.
X10. Y10.
Z2.
G1 Z-3. F200.
G4 P0.5
G0 Z5.
X30.
Z2.
G1 Z-3.
G4 P0.5
G0 Z5.
M5
M30
```

### Örnek B — kılavuz (G84)
Takım `Tool(5, "M8", TAP, D=8, flute_length=25, pitch=1.25, lead=3)`, `rpm = 500` (`F = 625`),
`start = (0, 0, 5)`, delik `(10, 10)`, `z_top = 0`, `t_d = 12` → `z = −15.75`, `r = 2`, `G98`.

Fanuc:
```
%
O0001
N10 G21 G90 G17 G94 G40 G49 G80 G54
N20 T5 M6
N30 S500 M3
N40 G0 G43 X0. Y0. Z5. H5
N50 M29 S500
N60 G98 G84 X10. Y10. Z-15.75 R2. F625.
N70 G80
N80 M5
N90 M30
%
```
Haas (`HAAS`, SPEC 30 K12 biçimi; `post()` yorumları olmadan `write` ile):
```
%
O00001
G21 G90 G17 G94 G40 G49 G80 G54
T5 M06
S500 M3
G0 G43 X0. Y0. Z5. H05
G98 G84 X10. Y10. Z-15.75 R2. F625.
G80
M5
M30
%
```

## Kapsam dışı
- Gagalı kılavuz (`G84 Q`), sol diş (`G74`), yüzer (rijit olmayan) kılavuz tutucu ile `M4` dönüşü,
  G95 (mm/dev) ile kılavuz ilerlemesi.
- Diş frezeleme (helisel `G2/G3` ile diş): ayrı SPEC.
- Lamba (counterbore) işleme: SPEC 29'da dairesel cep olarak zaten var.
- Eğimli delikler (3+2): SPEC 41. Tornada punta / kılavuz: SPEC 21'in eki.
- Delik gezi sırası optimizasyonu (TSP), işlem sırası (punta → delme → havşa → kılavuz): SPEC 29.
- Kılavuz ve konik takımın simülasyonu (SPEC 05 talaş modeli), bekleme süresinin süre tahmini.
- `cam/model.py`, `cam/gcode/`, `cam/post/` değişiklikleri: yukarıdaki listeyle sahip thread'lerde.

## Açık sorular (onay için)
1. **Sinumerik ve Heidenhain'de kılavuz.** SPEC 31 çevrimleri açar (G0/G1), ama kılavuz G0/G1 ile
   açılamaz (iş mili eşzamanı gerekir). Öneri: **şimdilik `CamError`** ("bu dilde kılavuz için doğal
   çevrim ekini bekleyin"); alternatif: doğal `CYCLE84` / `CYCL DEF 207` bu SPEC'e girer (söz dizimi
   kılavuzlardan, tezgâhta doğrulanmadan).
2. **Fanuc `M29`.** Öneri: **her `G84`'ten önce `M29 S<rpm>` yaz** (parametre 5200#0 kapalı tezgâhta da
   güvenli); alternatif: yazma, rijit mod parametreye kalsın.

Önerilen varsayılanlar (koordinatör kararı yeterli): `r_clear = 2 mm`; punta ve havşa `dwell = 0.2 s`;
punta çapı `d_s = Hole.d`; `lead` takımda zorunlu (varsayılan diş sayısı uydurulmaz).
