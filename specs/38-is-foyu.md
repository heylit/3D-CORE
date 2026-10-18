# SPEC 38 — İş föyü (setup sheet) ve tezgâh doğrulama belgesi

## Amaç
Bir freze programını (bağlamalar + takım yolları + takım kütüphanesi; ya da doğrudan SPEC 29 `MillPlan`) operatörün
tezgâh başında okuduğu **iş föyüne** çevirmek: takım listesi ve boyları (Fanuc `H` / GRBL `G43.1` ofsetleri),
bağlama resmi (SPEC 16 pafta altyapısıyla SVG), iş sıfırı (WCS) tarifi, işlem sırası ve süre (SPEC 05 süre modeli),
ilk parça ölçüm listesi (ISO 2768-1 genel toleransıyla) ve bu işe özel doldurulmuş tezgâh doğrulama listesi.
Çıktı tek bir HTML dosyası + bağlama başına bir SVG'dir; yeni bağımlılık yoktur, PDF tarayıcının "Yazdır"ıyla alınır.
`docs/tezgah-dogrulama.md` (SPEC 14'te yazılan genel liste) iş föyüyle eşlenecek şekilde genişletilir.

Hedefe yeri: "tasarımdan tezgâha" akışında G-code'dan sonraki son kâğıt. Tezgah (SPEC 24 / 25) "İş föyü" düğmesiyle
bu SPEC'in `write_job_sheet` çıktısını açar (Tezgah işi; bu SPEC'te uç yok).

## Bağımlılıklar ve kod sırası
- Kullanılır (hepsi `main`'de): SPEC 14 (`cam/setups.py`: `check_setup`, `clearance_height`; `cam/library.py`:
  `check_tools`; `cam/tool_length.py`: `length_offsets`, `fanuc_offset_table`), SPEC 05 (`cam.sim`: `Machine`,
  `move_time`; çapraz kontrol için `simulate`), SPEC 04 (`cam.gcode`: `GRBL`, `FANUC`, `Dialect`, `DrillOp`),
  SPEC 16 (`geometry.drawing`: `View`, `Sheet`, `Line2D`, `Arc2D`, `Text2D`, `layout`, `hatch`, `write_svg`,
  `format_value`, `make_drawing`, `Dimension`).
- SPEC 29 (`cam/plan.py`, `MillPlan`) yalnız `from_mill_plan` uyarlayıcısı için gerekir. Çekirdek (`build_job_sheet`)
  29'a bağlı değildir; K10 testi `pytest.importorskip("cam.plan")` ile 29 birleşene kadar atlanır.
- **Arayüz değişikliği gerekmez.** `cam/model.py`, `geometry/part.py` ve diğer `*/model.py` değişmez.
- Yeni üst düzey paket `atolye/`: paketin kurulabilmesi için `pyproject.toml` `[tool.setuptools.packages.find]`
  `include` listesine `"atolye*"` eklenmelidir. Bu satır bu SPEC'in PR'ında **değişmez**; "Durum tablosu ve kurulum
  belgeleri" sahibi ayrı PR'da ekler. Testler `pythonpath = ["."]` sayesinde o PR'dan önce de çalışır.

## Teori

### 1. Girdi ve iş föyünün kapsamı
Bir iş, sıralı bağlamalardan oluşur: bağlama `i` için `Setup` (SPEC 14: WCS, kutu ham malzeme, bağlama elemanları) ve
o bağlamada çalışan op listesi (`Toolpath` veya `DrillOp`, yalnız freze takımı, G17, G94). İş föyü programı
**değiştirmez**, yalnız okur. Güvensiz bir program için föy üretilmez (sessiz hata yok): her bağlamada
`check_tools(lib, ops)` ve `check_setup(setup, ops)` çağrılır, hata aynen (`CamError`) yükselir.

### 2. İş sıfırı (WCS) tarifi
Op koordinatları iş koordinatıdır, yani iş sıfırı `(0, 0, 0)`'dır. Operatöre sıfırın ham malzemenin neresinde
olduğu söylenir. Kutu ham malzeme `[xmin, xmax] × [ymin, ymax] × [zmin, zmax]` için eksen başına metin
(`ε = 1e-9` mm):

| Eksen | `0 = min` | `0 = max` | `0 = (min + max)/2` | Diğer |
|---|---|---|---|---|
| X | `"sol kenar"` | `"sağ kenar"` | `"X ortası"` | `"sol kenardan " + f(−xmin) + " mm"` |
| Y | `"ön kenar"` | `"arka kenar"` | `"Y ortası"` | `"ön kenardan " + f(−ymin) + " mm"` |
| Z | `"alt yüz"` | `"üst yüz"` | `"Z ortası"` | `"üst yüzden " + f(zmax) + " mm aşağıda"` (`zmax > 0`) / `" mm yukarıda"` (`zmax < 0`, değer `f(−zmax)`) |

`f` = SPEC 16 `format_value` (0,01'e yuvarlanmış, ondalık virgül). Sıra: önce `min`, sonra `max`, sonra orta
(eşitlik ancak dejenere kutuda olur; `Stock` buna izin vermez). Ayrıca `Wcs.origin` (makine koordinatı) föyde
`dialect.decimals` basamakla (virgüllü) yazılır: operatör bunu `G5x` kaydına girer.

### 3. Takım listesi ve boyları
Bağlama başına, takımlar **ilk kullanım sırasıyla** listelenir. Takım `T` için:
- Kütüphane verisi: `id, name, kind, D, corner_r, flute_length, stickout, holder.name, L = gauge_length`
  (SPEC 14: `L = holder.gauge_length + stickout`; biri yoksa `None`).
- **Gerekli kesici boy** `need_T = z_üst − min z` : `z_üst` ham malzeme üstü (`stock.zmax`), `min z` takımın bu
  bağlamadaki kesme hareketlerinin (G1/G2/G3; `DrillOp`'ta delik dibi `z`) en alçak Z'si. SPEC 14 `check_setup`
  `flute_length ≥ need_T`'yi zaten denetler; föy sayıyı operatöre gösterir.
- **Boy ofseti** (`dialect.tool_length_comp`):
  - Fanuc tipi (`True`): `offset_T = L_T` (`fanuc_offset_table`); operatör `H<T>` kaydına girer.
  - GRBL tipi (`False`): `offset_T = ΔL_T = L_T − L_ref` (`length_offsets`), `ref` = bağlamanın ilk takımı
    (`ref_id` verilirse o; listede yoksa `CamError`). Z sıfırı referans takımla alınır.
  - Bağlamadaki takımlardan herhangi birinin `L`'si `None` ise o bağlamada **hiçbir** ofset hesaplanmaz (`None`) ve
    uyarı eklenir: `"T<n> ölçü boyu bilinmiyor: tezgâhta ölçülecek"` (eksik her takım için, id sırasıyla).
- `rpm_max_T` = takımın op'larındaki en büyük `rpm`; `ops_T` = op adları (sırayla); `time_T` = op sürelerinin toplamı.

### 4. Süre (SPEC 05 modeli)
Süre, SPEC 05 `simulate`'in `op_times` kuralıyla **birebir** hesaplanır ama ızgara kurulmaz (yalnız `move_time`):
- `DrillOp` → `op.to_toolpath(dialect)` (kanonik açılım).
- Bağlama içinde konum ilk op'un `start`'ıyla başlar. Sonraki op'un `start`'ı mevcut konumdan farklıysa aradaki
  bağlantı `G0` (düz doğru) o op'a sayılır. Takım bir öncekinden farklıysa `machine.tool_change` o op'a eklenir
  (bağlamanın ilk takımına eklenmez). Her hareket `move_time(p0, p1, move, G17, machine)`.
- Bağlama süresi `t_i = Σ op süreleri`; iş toplamı `Σ t_i` (bağlama değişimi süresi kapsam dışı).
- `OpRow.t_end` bağlama içinde birikimli süredir.
- Takım değişim sayısı (bağlama başına): bağlamanın ilk takımı + ardışık farklı takım geçişleri
  (SPEC 29 `MillPlan.tool_changes` ile aynı tanım).
Not: Yazıcının (SPEC 04) eklediği güvenli Z geri çekmeleri bu modelde yoktur; föyde süre "tahmin (SPEC 05)" diye
etiketlenir.

**Elle hesap (Ek A):** T1 op'u: `G1` 16 mm, `F100` → 9,6 s; `G1` 10 mm, `F300` → 2 s; toplam 11,6 s. T2 op'u:
bağlantı `G0 (15, 5, −1) → (20, 20, 15)`, Z ekseni sınırlar: `16 mm / 3000 mm/dk = 0,32 s`; takım değişimi 10 s;
`G1` 20 mm, `F150` → 8 s; toplam 18,32 s. Bağlama 29,92 s, takım değişimi sayısı 2.

### 5. Bağlama resmi
Her bağlama için SPEC 16 paftası (`Sheet`) kurulur; iki görünüş, iş koordinatında (öteleme yok):
- `"on"` (u = x, v = z) ve `"ust"` (u = x, v = y); `layout([on, ust], scale, gap)` ile birinci açı yerleşimi
  (üst görünüş önün altında).
- Ham malzeme dış çizgisi → `EKSEN` katmanı (noktalı-kesikli; ISO 128'de komşu / ham parça çizgisi alışkanlığı):
  kutu görünüşte dikdörtgen.
- Bağlama elemanı → `GORUNUR` sınır + `TARAMA` (SPEC 16 `hatch`, `s = 3 / scale`, `θ = 45°`). Kutu: dikdörtgen;
  `CylinderStock`: üstte tam çember (`Arc2D`, merkez `(0, 0)`, yarıçap `D/2`), önde dikdörtgen `[−D/2, D/2] × [zmin, zmax]`;
  silindirin taraması çemberin içi (bölge, 1e-3 mm kiriş toleranslı çokgen).
- Parça verilirse (`part`, OCCT): SPEC 16 `project(part, "on")` / `project(part, "ust")` kenarları aynen eklenir.
- İş sıfırı simgesi → `OLCU` katmanı: orijinden `+u` ve `+v` yönünde `A = 15 / scale` mm iki ok (gövde `Line2D` +
  iki kanat, SPEC 16 ok biçimi), uçlarında eksen harfleri (`"X"`, `"Z"` önde; `"X"`, `"Y"` üstte) ve orijin yanında
  `wcs.code` metni (ör. `"G55"`).

### 6. İlk parça ölçüm listesi ve ISO 2768-1 genel tolerans
Ölçüm kalemleri iki kaynaktan gelir, bu sırayla:
1. **Resim ölçüleri:** verilen SPEC 16 `Dimension`'ları (parça varsa `make_drawing` temel ölçüleri), verildiği sırayla.
   Metin `dim.text`, nominal `dim.value`.
2. **Derinlikler:** her bağlamada her `Toolpath` op'unun kesme hareketlerinin en alçak Z'si için
   `derinlik = stock.zmax − z_min` (> 0 olanlar). `DrillOp` derinliği alınmaz (delik dibi uç payı ve taşma içerir,
   parça ölçüsü değildir). Aynı bağlamada `1e-6` mm içinde eşit derinlikler tek kalem; artan sırayla. Metin
   `"derinlik " + f(derinlik)` (bağlama adıyla: `"<setup.name>: derinlik 4"`).

Her kaleme ISO 2768-1 doğrusal ölçü toleransı `±t` (sınıf varsayılan `"m"`):

| Nominal (mm) | 0,5–3 | >3–6 | >6–30 | >30–120 | >120–400 | >400–1000 | >1000–2000 | >2000–4000 |
|---|---|---|---|---|---|---|---|---|
| f | 0,05 | 0,05 | 0,1 | 0,15 | 0,2 | 0,3 | 0,5 | — |
| m | 0,1 | 0,1 | 0,2 | 0,3 | 0,5 | 0,8 | 1,2 | 2 |
| c | 0,2 | 0,3 | 0,5 | 0,8 | 1,2 | 2 | 3 | 4 |
| v | — | 0,5 | 1 | 1,5 | 2,5 | 4 | 6 | 8 |

Aralık sınırı alt aralığa aittir (3 → "0,5–3", 3,0001 → ">3–6"). Nominal `< 0,5` veya `> 4000`, tabloda "—" olan
hücre ya da bilinmeyen sınıf → `CamError` (genel tolerans tanımsız: resimde ayrıca belirtilmeli). Alt / üst sınır
`nominal ∓ t`. Ölçülen değer sütunu boş bırakılır (operatör doldurur).
Kaynak: ISO 2768-1:1989, Tablo 1.

### 7. Doğrulama listesi (işe özel)
`docs/tezgah-dogrulama.md` genel listedir (bölüm 1–5). Föy, aynı bölüm numaralarına bağlı işe özel maddeler üretir
(`CheckItem(section, text)`), bu sırayla:
- §1, `n_max` verildiyse: `"En yüksek devir S<rpm_max> ≤ tezgâh sınırı <n_max>"`; `rpm_max > n_max` → `CamError`.
- §2, her bağlama: `"<code> kaydına X<ox> Y<oy> Z<oz> girildi"` (origin, `dialect.decimals`, virgüllü) ve
  `"Sıfır: X0 <x metni>, Y0 <y metni>, Z0 <z metni>"` (§2 tablosu).
- §3, her bağlama, her takım (ilk kullanım sırası): Fanuc tipi `"T<n>: H<n> = <L>"`; GRBL tipi
  `"T<n>: G43.1 Z<ΔL> (referans T<ref>)"`; ofset yoksa `"T<n>: ölçü boyu tezgâhta ölçülecek"`.
- §4, her bağlama: `"Kuru çalıştırma: <code> Z'si +<h> mm kaydırıldı"`, `h = max(50, ⌈z_tepe − stock.zmin⌉ + 10)`,
  `z_tepe` = ham malzeme ve bağlama elemanlarının en üst Z'si.
- §5: `"İlk parça ölçüm listesindeki <k> kalem ölçüldü ve kaydedildi"` (`k` = kalem sayısı; `k = 0` ise madde yok).

`docs/tezgah-dogrulama.md`'ye "## 6. İş föyü" bölümü eklenir: föyün hangi tablosunun hangi bölüme karşılık geldiği,
föyün nasıl üretildiği (`write_job_sheet`) ve föydeki maddelerin genel listenin yerine değil **yanında** kullanıldığı.
Bölüm 1–5'in başlık numaraları değişmez (föy maddeleri bunlara bağlanır; K9 denetler).

### 8. HTML çıktısı
Tek dosya, UTF-8, `<!DOCTYPE html>`, `lang="tr"`; dış kaynak yok (`http://`, `https://`, `<script>` yok); yazdırma
için `@page { size: A4; margin: 12mm }` ve tablo satırlarının sayfa arasında bölünmemesi (`break-inside: avoid`).
Bölümler ve `id`'ler (testler HTML'i stdlib `html.parser` ile bu `id`'lerden okur):

| Öğe | `id` / sınıf | İçerik |
|---|---|---|
| Başlık | `<h1>` | `title` |
| Özet tablosu | `table#ozet` | satırlar: Parça, Malzeme, Program no, Kontrol (`dialect.name`), Bağlama sayısı, Toplam süre, Tarih (verildiyse) |
| Bağlama bölümü | `section#baglama-<i>` (`i` 1'den) | `<img src="baglama-<i>.svg">`, `table.wcs`, `table.takimlar`, `table.islemler` |
| Ölçüm listesi | `table#olcum` | No, Ölçü, Nominal, Alt, Üst, Ölçülen (boş) |
| Doğrulama | `ul#dogrulama` | her madde `<li data-bolum="<section>">☐ <text></li>` |
| Uyarılar | `ul#uyarilar` | uyarı metinleri (yoksa öğe yok) |

Sayılar: uzunluklar `format_value`; ofset ve WCS değerleri `dialect.decimals` basamak, virgül; süre `d:ss`
(`⌊t + 0,5⌋` saniyeye yuvarlanır; ≥ 1 saat ise `s:dd:ss`); devir tam sayı. Metin `html.escape` ile kaçırılır.
Aynı `JobSheet` → bayt bayt aynı HTML (tarih yalnız parametreden; saat / rastgelelik yok).

## Dosyalar
- Yeni paket `atolye/`:
  - `atolye/__init__.py` — dışa açılan adlar
  - `atolye/is_foyu.py` — veri tipleri, `build_job_sheet`, `wcs_text`, süre ve takım tablosu (§1–4, §7)
  - `atolye/olcum.py` — ISO 2768-1, ölçüm kalemleri (§6)
  - `atolye/baglama.py` — bağlama resmi (§5)
  - `atolye/html.py` — `render_html`, `write_job_sheet` (§8)
  - `atolye/plan.py` — `from_mill_plan` (SPEC 29 uyarlayıcısı)
- Yeni testler `tests/atolye/`: `test_is_foyu.py`, `test_olcum.py`, `test_baglama.py`, `test_html.py`,
  `test_dogrulama_belgesi.py`, `test_plan.py` (`importorskip("cam.plan")`), `test_bagimlilik.py`.
- Değişecek: `docs/tezgah-dogrulama.md` (yalnız "## 6. İş föyü" bölümü eklenir; 1–5 aynen kalır).
- Yeni: `durum/38-is-foyu.md`.
- Dokunulmayacak: tüm `*/model.py`, `geometry/part.py`, SPEC 04 / 05 / 14 / 16 / 29 dosyaları, `pyproject.toml`
  (`"atolye*"` satırı ayrı PR), `DURUM.md`, `docs/yol-haritasi.md`, `.github/`. Yeni bağımlılık yok.

Bağımlılık yönü: `atolye` → `cam`, `geometry` (yalnız `model.py` arayüzleri ve paketlerin `__init__`'ten dışa açılan
/ SPEC'lerde "Arayüz" başlığı altında tanımlı herkese açık işlevleri). Hiçbir paket `atolye`'yi import etmez.
OCCT gerektiren testler `@pytest.mark.occt`; çekirdek OCCT'sizdir (parça yalnız `part=` verilince kullanılır).

## Arayüz
Hatalar `cam.model.CamError` (SPEC 16 işlevlerinden gelen `GeometryError` aynen geçer).

```python
# atolye/is_foyu.py
@dataclass(frozen=True)
class ToolRow:
    T: int
    name: str
    kind: str  # ToolKind değeri
    D: float
    corner_r: float
    flute_length: float
    stickout: float | None
    holder: str | None
    L: float | None  # gauge_length
    offset: float | None  # Fanuc: L; GRBL: ΔL; bilinmiyorsa None
    need: float  # gerekli kesici boy (§3)
    rpm_max: int
    ops: tuple[str, ...]
    time: float  # s


@dataclass(frozen=True)
class OpRow:
    no: int  # bağlama içinde 1'den
    name: str
    T: int
    rpm: int
    F: float  # kesme hareketlerinin en büyük ilerlemesi (DrillOp: feed); kesme yoksa 0
    z_min: float  # kesme hareketlerinin en alçak Z'si (DrillOp: z)
    time: float  # s, §4
    t_end: float  # s, bağlama içinde birikimli


@dataclass(frozen=True)
class SetupSheet:
    index: int  # 1'den
    setup: Setup
    wcs: tuple[str, str, str]  # wcs_text(setup.stock)
    ref_id: int | None  # GRBL referans takımı; Fanuc'ta None
    tools: tuple[ToolRow, ...]
    ops: tuple[OpRow, ...]
    time: float
    tool_changes: int
    drawing: Sheet  # §5


@dataclass(frozen=True)
class InspectionItem:
    no: int  # 1'den
    text: str
    nominal: float
    tol: float  # ±t
    lower: float
    upper: float


@dataclass(frozen=True)
class CheckItem:
    section: int  # docs/tezgah-dogrulama.md bölümü (1..5)
    text: str


@dataclass(frozen=True)
class JobSheet:
    title: str
    material: str
    dialect: Dialect
    program_no: int
    setups: tuple[SetupSheet, ...]
    inspection: tuple[InspectionItem, ...]
    checks: tuple[CheckItem, ...]
    warnings: tuple[str, ...]
    total_time: float
    date: str | None = None


def wcs_text(stock: Stock) -> tuple[str, str, str]: ...  # §2


def build_job_sheet(
    title: str,
    setups: Sequence[Setup],
    ops: Sequence[Sequence[Toolpath | DrillOp]],  # setups ile aynı uzunluk
    lib: ToolLibrary,
    material: str,
    dialect: Dialect = GRBL,
    machine: Machine | None = None,  # None → Machine()
    n_max: float | None = None,
    ref_id: int | None = None,
    program_no: int = 1,
    names: Sequence[Sequence[str]] | None = None,  # op adları; None → op.name
    dims: Sequence[Dimension] = (),
    tol_class: str = "m",
    warnings: Sequence[str] = (),
    part: Part | None = None,  # yalnız bağlama resmi için (OCCT)
    scale: float = 1.0,
    date: str | None = None,
) -> JobSheet: ...


# atolye/olcum.py
def tolerance_2768(nominal: float, cls: str = "m") -> float: ...
def inspection_items(
    dims: Sequence[Dimension],
    setups: Sequence[Setup],
    ops: Sequence[Sequence[Toolpath | DrillOp]],
    cls: str = "m",
) -> list[InspectionItem]: ...


# atolye/baglama.py
def setup_drawing(setup: Setup, part: Part | None = None, scale: float = 1.0, gap: float = 20.0) -> Sheet: ...


# atolye/html.py
def render_html(job: JobSheet) -> str: ...
def write_job_sheet(job: JobSheet, folder: str | Path) -> Path: ...


# folder yoksa kurulur; "is-foyu.html" ve her bağlama için "baglama-<i>.svg" (SPEC 16 write_svg) yazılır,
# aynı adlı dosyaların üstüne yazılır; dönüş: HTML dosyasının yolu.


# atolye/plan.py
def from_mill_plan(
    plan: MillPlan,
    lib: ToolLibrary,
    title: str,
    dialect: Dialect = GRBL,
    machine: Machine | None = None,
    n_max: float | None = None,
    part: Part | None = None,  # verilirse dims = make_drawing(part) temel ölçüleri ve bağlama resminde parça
    date: str | None = None,
) -> JobSheet: ...


# = build_job_sheet(title, plan.setups, [plan.ops_for(i) ...], lib, plan.material, ...,
#   names = PlannedOp.name'ler, warnings = unplanned ("<feature>: <code> — <detail>") + notes
#   ("<feature>: <code> = <f(value)> — <detail>"), SPEC 29'daki sırayla)
```

Geçersiz girdi → `CamError`: `title` veya `material` boş / `str` değil; `setups` boş; `ops` uzunluğu `setups`'tan
farklı; bir bağlamada op listesi boş; `names` şekli `ops`'la uyuşmuyor; op'ta torna takımı, `Plane ≠ XY` veya
`FeedMode ≠ PER_MIN`; `CylinderStock` ham malzeme (torna föyü kapsam dışı); `n_max`, `scale`, `gap` pozitif sonlu
değil; `program_no < 1`; `ref_id` bağlamanın takımları arasında yok; `check_tools` / `check_setup` hatası;
`rpm_max > n_max`; §6 tolerans tanımsızlığı.

## Kabul kriterleri
Takımlar ve bağlama uydurmadır (Ek A). Süreler rel `1e-12`, uzunluklar `1e-9` mm.
- [ ] K1 **WCS tarifi**: Ek A stoğu → `("sol kenar", "ön kenar", "üst yüz")`; `Stock(−25, −20, −20, 25, 20, 0)` →
  `("X ortası", "Y ortası", "üst yüz")`; `Stock(−2, −3, −20, 48, 37, 2)` → `("sol kenardan 2 mm", "ön kenardan 3 mm",
  "üst yüzden 2 mm aşağıda")`; `zmax = −1,5` → `"üst yüzden 1,5 mm yukarıda"`. (`test_is_foyu.py::test_wcs_text`)
- [ ] K2 **Takım tablosu**: Ek A, GRBL → satırlar T1, T2 (ilk kullanım sırası), `L = 90, 105`, `offset = 0, 15`,
  `ref_id = 1`, `need = 1, 5`, `rpm_max = 10000, 3000`; `ref_id = 2` → `offset = −15, 0`; FANUC → `offset = 90, 105`,
  `ref_id = None`; T2'nin tutucusu yok → iki ofset `None`, uyarı `"T2 ölçü boyu bilinmiyor: tezgâhta ölçülecek"`;
  `ref_id = 7` → hata. (`::test_takim_tablosu`)
- [ ] K3 **Süre**: Ek A, `Machine(rapid = (6000, 6000, 3000), tool_change = 10)` → op süreleri `11,6` ve `18,32` s,
  `t_end = 11,6, 29,92`, bağlama `29,92` s, `tool_changes = 2`; aynı program T1–T2–T1 ile → `tool_changes = 3`;
  K12 programında op süreleri `simulate(ops, stock, cell = 2, machine).op_times` ile rel 1e-12 aynı (`DrillOp`
  G83 dahil). (`::test_sure`)
- [ ] K4 **İşlem tablosu**: `OpRow` `no, name, T, rpm, F, z_min` Ek A'dan (`F = 300, 150`; `z_min = −1, −5`);
  `names` verilince adlar onlar. (`::test_islem_tablosu`)
- [ ] K5 **Güvenlik denetimi**: bağlama elemanına giren op → `check_setup` mesajıyla `CamError`; kütüphanede
  olmayan takım → `CamError`; `n_max = 5000` ve `rpm = 10000` → `CamError`; `n_max = 12000` → §1 maddesi
  `"En yüksek devir S10000 ≤ tezgâh sınırı 12000"`. (`::test_guvenlik`)
- [ ] K6 **ISO 2768-1**: `m`'de `3 → 0,1`, `6 → 0,1`, `6,01 → 0,2`, `30 → 0,2`, `120 → 0,3`, `4000 → 2`; `f`'de
  `6 → 0,05`, `6,01 → 0,1`; `c`'de `0,5 → 0,2`; `0,4`, `4001`, `v` sınıfında `2` ve sınıf `"x"` → hata. Ölçüm
  kalemleri: verilen `Dimension`'lar sırayla, ardından Ek A'nın derinliği (`"on-yuz: derinlik 1"`, T1 op'u; T2
  `DrillOp` derinliği yok), eşit derinlik tek kalem; `lower/upper = nominal ∓ t`. (`test_olcum.py`)
- [ ] K7 **Bağlama resmi** (OCCT'siz): Ek A → `Sheet`'te `"on"` ve `"ust"` görünüşü; `ust`'te `EKSEN` toplam boyu
  `2(50 + 40)`, `on`'da `2(50 + 20)`; bağlama elemanı `GORUNUR` dikdörtgeni ve tüm `TARAMA` parçalarının orta noktası
  eleman içinde; `OLCU`'da orijinden çıkan `+u`, `+v` okları (boy `15 / scale`) ve `"G55"` metni; `scale = 2`'de
  pafta boyları iki katı; `CylinderStock` bağlama elemanında üst görünüşte merkez `(0, 0)`, yarıçap `D/2` tam çember;
  SPEC 16 `write_svg` dosyayı hatasız yazıyor. `@occt`: `part` verilince `project(part, "ust")`'ün `GORUNUR` boyu
  resimde de var. (`test_baglama.py`)
- [ ] K8 **HTML**: `html.parser` ile ayrışıyor; `table#ozet` satırları §8'deki sırayla; `section#baglama-1` içinde
  `img[src="baglama-1.svg"]`, takım ve işlem tablolarının satır sayısı `ToolRow` / `OpRow` sayısı, hücre metinleri
  §8 biçiminde (ör. Ek A GRBL ofset `"15,000"`, süre `"0:30"`, `L` `"105"`); `ul#dogrulama` madde sayısı `checks`
  sayısı ve `data-bolum` değerleri; `http`, `<script>` yok; `"<&>"` içeren başlık kaçırılmış; aynı `JobSheet` iki
  kez → bayt bayt aynı. `write_job_sheet(job, tmp/"yeni")` klasörü kurup `is-foyu.html` ve `baglama-1.svg` yazıyor,
  SVG `xml.etree` ile ayrışıyor. (`test_html.py`)
- [ ] K9 **Doğrulama listesi ve belge**: Ek A GRBL `checks` metinleri ve sırası Teori §7 ile birebir (ör.
  `"G55 kaydına X-250,000 Y-190,000 Z-80,000 girildi"`, `"T2: G43.1 Z15,000 (referans T1)"`,
  `"Kuru çalıştırma: G55 Z'si +50 mm kaydırıldı"`); bağlama elemanı olmayan `Stock(0, 0, −100, 50, 40, 0)` bağlamasında `h = 110`; `docs/tezgah-dogrulama.md`'de
  `## 1.` … `## 6.` başlıkları var, her `CheckItem.section` için o başlık var, `## 6.` bölümü `write_job_sheet`'i
  anıyor. (`test_dogrulama_belgesi.py`)
- [ ] K10 **SPEC 29 uyarlayıcısı** (`importorskip("cam.plan")`): SPEC 29 K8 planından `from_mill_plan` → bağlama ve
  op sayıları plandakiyle aynı, op adları `PlannedOp.name`, uyarılar `unplanned` + `notes` sırasıyla ve biçimiyle,
  `tool_changes` = `plan.tool_changes()` (tek bağlamada). (`test_plan.py`)
- [ ] K11 **Bağımlılık kuralı**: `core`, `cam`, `geometry`, `assy`, `sketch`, `mesh`, `fileio`, `viz` içinden hiçbir
  modül `atolye`'yi import etmiyor (AST taraması). (`test_bagimlilik.py`)
- [ ] K12 **Uçtan uca** (OCCT'siz): iki bağlamalı uydurma iş (bağlama 1: Ek A + G83 `DrillOp` 4 delik; bağlama 2:
  `G56`, tek yüz alma) → `build_job_sheet` + `write_job_sheet`; HTML'de iki `section`, iki SVG, toplam süre iki
  bağlamanın toplamı, takım değişimi sayıları elle sayılan değer; hatalar §Arayüz sonundaki listeyle `CamError`.
  (`test_is_foyu.py::test_uctan_uca`, `::test_hatalar`)
- [ ] Tüm testler yeşil, `ruff check .` ve `ruff format --check .` temiz, bu SPEC'in testlerinde 0 "uygulanmamış"

## Kapsam dışı
- Torna iş föyü (SPEC 20 / 21 / 22, `TurnPlan`): SPEC 05 süre modeli yalnız G17; torna süresi SPEC 22'de. Ayrı ek (38b).
- PDF üretimi (tarayıcıdan yazdırılır), antet / logo, çok dilli föy.
- Bağlama değişim süresi, takım ömrü, maliyet hesabı, talaş debisi tablosu.
- Ölçüm sonuçlarını geri okuma ve ofset düzeltmesi (`verify_offsets` akışı ayrı iş), SPC / ölçüm kaydı saklama.
- ISO 2768-2 (geometrik genel tolerans), açısal ölçü toleransı, resimde belirtilmiş özel toleranslar.
- Tezgah'ta "İş föyü" düğmesi (SPEC 24 / 25 tarafı).
- `pyproject.toml` `include` satırı (ayrı PR).

## Ek A — Uydurma iş (SPEC 14 Ek A ile aynı takımlar)
- Tutucu `H = ToolHolder("BT30-ER", 60, ((0, 15), (40, 20)))`.
- `T1 = Tool(1, "freze6", FLAT, D = 6, flute_length = 20, flutes = 3, stickout = 30, holder = H)` → `L = 90`.
- `T2 = Tool(2, "matkap5", DRILL, D = 5, flute_length = 40, flutes = 2, stickout = 45, holder = H)` → `L = 105`.
- `lib = ToolLibrary([T2, T1])` (sıra bilerek ters: föy ilk kullanım sırasını izler).
- `setup = Setup("on-yuz", Wcs("G55", (−250, −190, −80)), Stock(0, 0, −20, 50, 40, 0),
  fixtures = [Stock(−15, 0, −20, −5, 40, 10)])`.
- `tp1 = Toolpath("cep", T1, start = (5, 5, 15), rpm = 10000)`, hareketler `G1 (5, 5, −1) F100`, `G1 (15, 5, −1) F300`.
- `tp2 = Toolpath("delik", T2, start = (20, 20, 15), rpm = 3000)`, hareket `G1 (20, 20, −5) F150`.
- `material = "al"`, `Machine(rapid = (6000, 6000, 3000), accel = None, tool_change = 10)`.
