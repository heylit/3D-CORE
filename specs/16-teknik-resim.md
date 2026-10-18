# SPEC 16 — Teknik resim: görünüşler, kesit, ölçülendirme, DXF ve SVG

## Amaç
Bir `Part`'tan atölyede okunabilecek 2D teknik resim üretmek: OCCT gizli çizgi kaldırma (HLR) ile ön / üst /
yan görünüş, düzlemsel kesit ve taraması, temel ölçüler; bunları ISO birinci açı yerleşimiyle bir pafta
üzerinde toplayıp kendi yazdığımız DXF (R12) ve SVG yazıcısıyla dışa aktarmak. Her uzunluk ve alan analitik
değerle doğrulanır; DXF geri okunduğunda aynı resim çıkar.

## Teori

### Görünüş düzlemleri (dik izdüşüm)
Her görünüş, parçayı bir bakış yönü `d` boyunca görünüş düzlemine dik izdüşürür. Görünüş koordinatları
`(u, v)` dünya koordinatlarından şöyle gelir (sağ el kuralı: `u × v = −d`, yani `u, v` bakan göze göre sağ ve yukarı):

| Görünüş | Göz | Bakış yönü `d` | `u` | `v` |
|---|---|---|---|---|
| `on` (ön) | −Y'de | +Y | `x` | `z` |
| `ust` (üst) | +Z'de | −Z | `x` | `y` |
| `sol` (soldan görünüş) | −X'te | +X | `−y` | `z` |
| `sag` (sağdan görünüş) | +X'te | −X | `y` | `z` |

Görünüş koordinatları ötelenmez: blok `block(a, b, c)` ön görünüşte `u ∈ [0, a]`, `v ∈ [0, c]`; soldan
görünüşte `u ∈ [−b, 0]`, `v ∈ [0, c]`. Paftaya yerleşimde öteleme yapılır (aşağıda).

### Gizli çizgi kaldırma ve temizleme
OCCT HLR (`HLRBRep_Algo`, build123d `Shape.project_to_viewport`) her kenarı görünen ve gizli parçalara
ayırır. Ham çıktı teknik resme uygun değildir: üst yüz ile alt yüzün kenarları üst görünüşte üst üste düşer,
izdüşen daireler B-spline doğru olarak gelir.

Sadece **keskin kenarlar** ve **silüetler** (dış hat) çizilir. Teğet (G1 sürekli, "yumuşak") kenarlar
çizilmez: cep köşe yarıçapının düz duvara geçtiği çizgi gibi (ISO 128 alışkanlığı). OCCT karşılığı:
`HLRBRep_HLRToShape`'in `VCompound` / `OutLineVCompound` (görünen) ve `HCompound` / `OutLineHCompound`
(gizli) çıktıları; `Rg1LineVCompound`, `RgNLineVCompound` ve gizli karşılıkları kullanılmaz (build123d
`project_to_viewport` bunları da döndürdüğü için doğrudan kullanılmaz).

Bu SPEC'in yazdığı temizleme (`clean_edges`) şunları yapar:

1. **Sınıflama.** Her kenar `tol_s = 1e-6 mm` ile örneklenir: tüm örnekler bir doğru üzerindeyse `Line2D`;
   bir çember üzerindeyse `Arc2D` (tam çember: tarama açısı 360°); değilse kiriş sapması `tol` olan `Polyline2D`.
2. **Birleştirme.** Aynı doğru üzerindeki (yön ve doğruya uzaklık `tol_s` içinde) doğru parçaları o doğru
   üzerinde 1D aralıklar olarak birleştirilir: `[s₀, s₁] ∪ [s₂, s₃]`, aralıklar örtüşüyor veya değiyorsa tek aralık.
   Aynı merkez ve yarıçaplı yaylar açı aralığında aynı şekilde birleştirilir.
3. **Öncelik.** Görünen çizgi gizli çizgiyi örter: gizli aralıklardan, aynı doğru / çember üzerindeki görünen
   aralıklar çıkarılır (`H ← H ∖ V`). Boyu `tol_s`'den kısa kalan parça atılır.

Temizleme sonrası özellik: hiçbir iki çıktı parçası pozitif uzunlukta örtüşmez; gizli ile görünen de örtüşmez.

### Analitik görünüş uzunlukları (testlerin dayanağı)
Görünen toplam boy `L_g = Σ |görünen parça|`, gizli toplam boy `L_h`. `block(a, b, c)` için:
- Ön: `L_g = 2(a + c)`, üst: `L_g = 2(a + b)`, sol / sağ: `L_g = 2(b + c)`; tümünde `L_h = 0`.

Boydan boya delik (çap `d`, eksen `(x, y)`, blok yüksekliği `c`), delik bloğun içinde:
- Üst: `L_g = 2(a + b) + π d` (merkezi `(x, y)`, yarıçapı `d/2` tam çember), `L_h = 0`.
- Ön: `L_g = 2(a + c)`, `L_h = 2c` (u = x ± d/2'de iki dikey gizli çizgi, delik ağzı ve dibi dış kenarla örtüşür).
- Sol: `L_g = 2(b + c)`, `L_h = 2c` (u = −y ± d/2).

Kör delik (derinlik `t < c`), düz dipli (SPEC 02):
- Ön: `L_h = 2t + d` (iki yan çizgi + `v = c − t`'deki dip çizgisi; ağız `v = c`'de görünen üst kenarla örtüşür).

Köşe yarıçaplı dikdörtgen cep (merkez `(x, y)`, X boyu `w`, Y boyu `l`, köşe `r`, derinlik `t`):
- Ön: `L_h = 2t + w`; sol: `L_h = 2t + l` (köşe silindirlerinin silüeti yan duvarla, dip yaylarının
  izdüşümü dip çizgisiyle örtüşür; `r`'den bağımsız).
- Üst: `L_g = 2(a + b) + P`, `P = 2(w + l) − (8 − 2π) r`, `L_h = 0` (cep ağzı ve cep dibi aynı çevreye
  izdüşer; birleştirmede tek sayılır).

### Kesit
Kesit düzlemi bir görünüşün düzlemine paraleldir: `on` için `y = y₀`, `ust` için `z = z₀`, `sol` / `sag` için
`x = x₀`. Gözle düzlem arasındaki malzeme kaldırılır (`on` kesitinde `y < y₀` kısmı), kalan parça aynı
bakış yönüyle izdüşürülür. Kesit görünüşünde **gizli çizgi çizilmez** (ISO 128-50 alışkanlığı).

Kesit yüzeyi (malzemenin düzlemle arakesiti) görünüş koordinatlarında `Region` listesi olarak verilir
(`geometry.part.Region`: dış sınır CCW, delikler CW) ve taranır.

Boydan boya delikli blokta, delik ekseninden (`y₀ = y`) `on` kesiti:
- Kesit alanı `A = c(a − d)`, iki bölge: `[0, x − d/2] × [0, c]` ve `[x + d/2, a] × [0, c]`.
- Görünen boy `L_g = 2a + 4c`: dış dikdörtgen `2(a + c)` + deliğin arka yarısının iki silüeti `2c`
  (delik ağız / dip çizgileri `v = 0` ve `v = c`'de dış kenarın boşluğunu kapatır).

### Tarama (hatch)
Tarama, açısı `θ` (varsayılan 45°) ve aralığı `s` (varsayılan 3 mm, kağıt üzerinde; ölçekle bölünür) olan paralel
doğruların bölge ile kesişimidir. Doğrular `n·p = (k + ½)·s` (`p` konum, `n = (−sin θ, cos θ)` normal, `k`
tam sayı) ailesindendir. Her doğru için bölgenin tüm kenarlarıyla kesişim parametreleri sıralanır, çift-tek
kuralıyla içteki aralıklar alınır (tarama satırı / scanline algoritması; Foley vd., *Computer Graphics*, 3.6).

Eksen-paralel dikdörtgende (`W × H`, `θ = 0`) doğru sayısı `N = round(H / s)` (H, s'nin tam katıysa tam
olarak `H/s`), her biri `W` boyunda: toplam boy `W·H/s = A/s`. Genel bölgede orta nokta kuralı:
`s · Σ Lᵢ → A`, `s → 0`.

### Ölçülendirme (ISO 129-1 esası, sadeleştirilmiş)
"Temel ölçüler": her ölçü pafta üzerinde **bir kez** yazılır.
- Ön görünüşte toplam genişlik (`a`, yatay) ve yükseklik (`c`, dikey).
- Üst görünüşte toplam derinlik (`b`, dikey).
- Üst görünüşte görünen her tam çember (delik) için: çap ölçüsü `Ø d` ve merkezin sınır kutusunun sol-alt
  köşesine göre konumu (yatay `x − u_min`, dikey `y − v_min`). Aynı merkez konumu birden çok delikte tekrar
  ediyorsa tek yazılır.

Ölçü metni: değer 0.01 mm'ye yuvarlanır, sondaki sıfırlar atılır, ondalık ayırıcı virgüldür
(`12.50 → "12,5"`, `10.0 → "10"`); çap ölçüsünde `"Ø"` öneki. Ölçü değeri her zaman geometriden
(ölçeksiz, mm) gelir; pafta ölçeği metni değiştirmez.

### Pafta yerleşimi (ISO 5456-2, birinci açı, "E" yöntemi)
Ön görünüş referanstır. Üst görünüş önün **altına**, soldan görünüş önün **sağına**, sağdan görünüş önün
**soluna** yerleşir; aralarında kağıt üzerinde `g` (varsayılan 20 mm) boşluk. Yatay hizada `v`, dikeyde `u`
eksenleri ortaktır (ön ve üst aynı `u = x` değerini aynı pafta X'inde gösterir). Ölçek `k`: pafta koordinatı
`= k · görünüş koordinatı + öteleme`. Kesit görünüşü ait olduğu yönün yerine geçer ve kesit çizgisi
(`A–A`) onu kesen görünüşe çizilir (ör. `on` kesiti için üst görünüşte `v = y₀` doğrusu).

### Çizgi tipleri ve katmanlar (ISO 128-20)
| Katman | Ne | Çizgi | Kalınlık (mm) |
|---|---|---|---|
| `GORUNUR` | görünen kenar, kesit sınırı | sürekli | 0.5 |
| `GIZLI` | gizli kenar | kesikli (`HIDDEN`) | 0.25 |
| `EKSEN` | delik eksen / merkez çizgisi, kesit çizgisi | noktalı-kesikli (`CENTER`) | 0.25 |
| `TARAMA` | tarama | sürekli | 0.18 |
| `OLCU` | ölçü ve yardımcı çizgi, ok, metin | sürekli | 0.18 |

Delik eksenleri: üst görünüşte her tam çemberin merkezinden geçen yatay ve dikey merkez çizgisi (çemberden
2 mm taşar); yan görünüşlerde gizli delik çizgilerinin ortasında, delik boyunca 2 mm taşan eksen çizgisi.

### DXF (R12, ASCII) ve SVG
DXF'yi kendimiz yazarız: R12 (`$ACADVER = AC1009`) ASCII, grup kodu / değer çiftleri. Bölümler: `HEADER`,
`TABLES` (`LTYPE`: `CONTINUOUS`, `HIDDEN`, `CENTER`; `LAYER`: yukarıdaki beş katman), `ENTITIES`. Varlıklar:
`LINE`, `CIRCLE`, `ARC` (açılar derece, CCW), `TEXT`. Çoklu çizgi ve tarama `LINE` dizisi olarak yazılır.
Sayılar en az 12 anlamlı basamakla yazılır (geri okumada 1e-9 mm). Kaynak: Autodesk, *DXF Reference (R12)*.

SVG 1.1: `viewBox` paftanın sınır kutusu + kenar payı; SVG'de y aşağı baktığı için `y_svg = y_maks − y`.
Gizli çizgi `stroke-dasharray`, eksen noktalı-kesikli; çizgi kalınlıkları yukarıdaki tablodan. Her katman bir
`<g id="KATMAN">`.

Kaynaklar: ISO 128-20/-50, ISO 129-1, ISO 5456-2; Autodesk *DXF Reference R12*; W3C *SVG 1.1*;
OCCT belgeleri (HLRBRep); Foley, van Dam vd., *Computer Graphics: Principles and Practice*, 3.6 (tarama satırı).

## Dosyalar
- Yeni paket `geometry/drawing/` (üst düzey yeni paket `pyproject.toml` değişikliği gerektirdiği için
  `geometry/` altında):
  - `geometry/drawing/__init__.py` — dışa açılan adlar
  - `geometry/drawing/types.py` — 2D çizim veri tipleri (saf numpy)
  - `geometry/drawing/cleanup.py` — kenar sınıflama, birleştirme, gizli/görünen önceliği (saf numpy)
  - `geometry/drawing/hatch.py` — tarama (saf numpy)
  - `geometry/drawing/views.py` — HLR ile görünüş ve kesit (OCCT)
  - `geometry/drawing/dimensions.py` — temel ölçüler, metin biçimi, eksen çizgileri
  - `geometry/drawing/sheet.py` — pafta yerleşimi
  - `geometry/drawing/dxf.py` — DXF R12 yazıcı ve okuyucu (saf Python)
  - `geometry/drawing/svg.py` — SVG yazıcı (saf Python)
- Yeni testler: `tests/geometry/drawing/` (`test_cleanup.py`, `test_hatch.py`, `test_views.py`,
  `test_section.py`, `test_dimensions.py`, `test_sheet.py`, `test_dxf.py`, `test_svg.py`)
- Yeni: `durum/16-teknik-resim.md`
- Dokunulmayacak: `geometry/part.py` ve diğer `*/model.py` arayüzleri, `pyproject.toml`, `.github/`, diğer paketler.
  `views.py` parçanın OCCT şekline `Part.shape` üzerinden erişir (aynı paket); `Part` arayüzü değişmez.

**Yeni bağımlılık yok.** DXF ve SVG'yi kendimiz yazıp okuruz. `ezdxf` build123d ile birlikte kurulu geldiği
için testlerde **yalnızca çapraz kontrol** olarak kullanılır (`pytest.importorskip("ezdxf")`); kodda kullanılmaz.

OCCT gerektiren testler `@pytest.mark.occt`. `cleanup`, `hatch`, `dxf`, `svg`, `dimensions` metin biçimi
testleri OCCT'siz çalışır. Geçersiz girdi → `geometry.part.GeometryError` (sessiz hata yok).

## Arayüz

### `geometry/drawing/types.py`
```python
Layer = Literal["GORUNUR", "GIZLI", "EKSEN", "TARAMA", "OLCU"]


@dataclass(frozen=True)
class Line2D:
    p0: np.ndarray  # (2,) mm
    p1: np.ndarray  # (2,) mm
    layer: Layer


@dataclass(frozen=True)
class Arc2D:
    c: np.ndarray  # (2,) merkez, mm
    r: float  # mm
    a0: float  # derece, CCW; a0 < a1 <= a0 + 360
    a1: float  # a1 - a0 = 360 -> tam çember
    layer: Layer


@dataclass(frozen=True)
class Polyline2D:
    P: np.ndarray  # (k, 2), açık
    layer: Layer


@dataclass(frozen=True)
class Text2D:
    p: np.ndarray  # (2,) sol-alt köşe
    text: str
    h: float  # yazı boyu, mm
    angle: float  # derece
    layer: Layer


Entity = Line2D | Arc2D | Polyline2D | Text2D


@dataclass(frozen=True)
class Dimension:
    kind: Literal["yatay", "dikey", "cap"]
    p1: np.ndarray  # ölçülen 1. nokta (cap: çember merkezi)
    p2: np.ndarray  # ölçülen 2. nokta (cap: çember üstünde bir nokta)
    offset: float  # ölçü çizgisinin p1-p2'ye uzaklığı (mm, görünüş koordinatı)
    value: float  # mm, geometriden
    text: str  # format_value ile


@dataclass(frozen=True)
class View:
    name: str  # "on", "ust", "sol", "sag" veya "A-A"
    direction: str  # bakış yönü: "on", "ust", "sol", "sag"
    edges: tuple[Entity, ...]  # temizlenmiş görünen + gizli + eksen çizgileri (görünüş koordinatı)
    regions: tuple[Region, ...] = ()  # sadece kesitte: kesit yüzeyi
    hatch: tuple[Line2D, ...] = ()  # sadece kesitte
    dims: tuple[Dimension, ...] = ()

    def bbox(self) -> tuple[np.ndarray, np.ndarray]: ...  # edges'in (u, v) sınır kutusu


@dataclass(frozen=True)
class PlacedView:
    view: View
    offset: np.ndarray  # pafta = scale * görünüş + offset
    scale: float


@dataclass(frozen=True)
class Sheet:
    views: tuple[PlacedView, ...]
    extras: tuple[Entity, ...] = ()  # kesit çizgisi, etiketler (pafta koordinatı)

    def entities(self) -> list[Entity]: ...  # pafta koordinatında tüm çizim; ölçüler çizgi + metne açılmış

    def bbox(self) -> tuple[np.ndarray, np.ndarray]: ...
```

### `geometry/drawing/cleanup.py`
- `clean_edges(visible, hidden, tol_s=1e-6) -> list[Entity]` — girdi: ham 2D kenarlar (`Line2D`, `Arc2D`,
  `Polyline2D`); çıktı: Teori'deki 3 adımdan geçmiş liste (`GORUNUR` ve `GIZLI` katmanlı).
- `classify(P, tol_s=1e-6) -> Line2D | Arc2D | Polyline2D` — örnek noktalardan (k, 2) sınıflama.
- `total_length(edges, layer) -> float` — katmandaki toplam boy (yay boyu `r·Δθ`).

### `geometry/drawing/hatch.py`
- `hatch(regions, s=3.0, theta=45.0) -> list[Line2D]` — `TARAMA` katmanlı doğru parçaları. `s <= 0` veya
  boş bölge → `GeometryError`.

### `geometry/drawing/views.py`
- `project(part, direction, tol=0.01, axes=True) -> View` — `direction ∈ {"on","ust","sol","sag"}`;
  aksi `GeometryError`. `axes=True` delik eksen çizgilerini ekler.
- `section(part, direction, offset, name="A-A", s=3.0, theta=45.0, tol=0.01) -> View` — Teori'deki
  düzlem (`on`: `y = offset` ...). Düzlem parçayı kesmiyorsa `GeometryError`.

### `geometry/drawing/dimensions.py`
- `format_value(value, diameter=False) -> str` — Teori'deki kural.
- `basic_dimensions(part, views) -> dict[str, tuple[Dimension, ...]]` — görünüş adı → ölçüler; Teori'deki
  "temel ölçüler" kümesi, her ölçü bir kez.

### `geometry/drawing/sheet.py`
- `layout(views, scale=1.0, gap=20.0) -> Sheet` — birinci açı yerleşimi; `on` yoksa `GeometryError`;
  `scale <= 0` veya `gap < 0` → `GeometryError`.
- `make_drawing(part, views=("on", "ust", "sol"), section=None, scale=1.0, dims=True) -> Sheet` —
  `section=("on", y₀)` gibi verilirse o görünüş kesitle değişir ve kesit çizgisi eklenir.

### `geometry/drawing/dxf.py`
- `write_dxf(sheet_or_entities, path) -> None`
- `read_dxf(path) -> list[Entity]` — sadece bizim yazdığımız alt küme (`LINE`, `CIRCLE`, `ARC`, `TEXT`).
  Dosya yok, bozuk grup kodu, desteklenmeyen sürüm → `GeometryError`.

### `geometry/drawing/svg.py`
- `write_svg(sheet, path, margin=10.0) -> None`

## Kabul kriterleri
- [ ] K1 `classify`: doğru, çember, yay ve dejenere (doğrusal) B-spline örnekleri doğru sınıflanıyor; `clean_edges`
  örtüşen / değen doğru parçalarını birleştiriyor, gizliden görüneni çıkarıyor; çıktıda pozitif boylu örtüşme
  yok — `tests/geometry/drawing/test_cleanup.py` (OCCT'siz)
- [ ] K2 `project` bloğu: dört görünüşte `L_g` Teori'deki formülle rel 1e-9, `L_h = 0`, sınır kutusu
  (`on`: `[0,a]×[0,c]`, `sol`: `[−b,0]×[0,c]` ...) 1e-9 mm; geçersiz yön hata — `test_views.py`
- [ ] K3 Delikler: boydan boya delikte üst görünüşte merkez `(x, y)` ve yarıçap `d/2` olan tam çember (1e-6 mm),
  ön ve sol görünüşte `L_h = 2c`; kör delikte ön `L_h = 2t + d`; rel 1e-6 — `test_views.py`
- [ ] K4 Cep (r = 0 ve r > 0; teğet kenar çizilmiyor): ön `L_h = 2t + w`, sol `L_h = 2t + l`, üst `L_g = 2(a + b) + P` rel 1e-6 — `test_views.py`
- [ ] K5 Eksen çizgileri: üst görünüşte her deliğin merkezinden geçen iki `EKSEN` çizgisi çemberden 2 mm taşıyor;
  ön görünüşte delik ekseni `u = x`'te — `test_views.py`
- [ ] K6 `hatch`: `θ = 0` eksen-paralel dikdörtgende doğru sayısı `H/s` ve toplam boy `A/s` rel 1e-9; `θ = 45°`'de
  her parçanın uçları bölge sınırında (1e-9 mm), orta noktası içeride, delikli bölgede delik içinde tarama yok;
  `s = 0.1` ile `s·ΣL` alanla rel 1e-2; geçersiz `s` hata — `test_hatch.py` (OCCT'siz)
- [ ] K7 `section`: delik ekseninden `on` kesitinde iki bölge, toplam alan `c(a − d)` rel 1e-6, `L_g = 2a + 4c`
  rel 1e-6, gizli çizgi yok, tarama yalnızca bölgelerin içinde; parçayı kesmeyen düzlem hata — `test_section.py`
- [ ] K8 Ölçüler: `format_value` örnekleri (`12.5 → "12,5"`, `10.0 → "10"`, `3.14159 → "3,14"`, çap `"Ø10"`);
  delikli blokta `basic_dimensions` tam olarak {a, c (ön), b, Ø d, x, y (üst)} değerlerini veriyor, tekrar yok — `test_dimensions.py`
- [ ] K9 `layout`: birinci açı — üst görünüş önün altında, sol görünüş önün sağında, aralar `g·`(ölçekli) 1e-9 mm;
  ön ve üst aynı `x`'i aynı pafta X'inde gösteriyor; ölçek `k`'da pafta boyları `k` katı; `on` yok veya
  `scale <= 0` hata — `test_sheet.py`
- [ ] K10 DXF gidiş-dönüş: `write_dxf → read_dxf` aynı varlıkları (tür, katman, sayı) veriyor, koordinatlar 1e-9 mm;
  başlıkta `AC1009`, `LTYPE` ve `LAYER` tabloları var; bozuk dosya / eksik dosya hata — `test_dxf.py` (OCCT'siz)
- [ ] K11 DXF çapraz kontrol: `ezdxf.readfile` dosyayı açıyor, `audit()` hatasız, varlık sayıları ve katmanlar
  bizim okuyucuyla aynı (`importorskip("ezdxf")`) — `test_dxf.py`
- [ ] K12 SVG: `xml.etree` ile ayrışıyor; `viewBox` = pafta sınır kutusu + kenar payı 1e-9; her katman bir `<g>`;
  gizli çizgilerde `stroke-dasharray` var; y ekseni çevrilmiş (pafta `y_maks` → SVG `0`); eleman sayısı
  `Sheet.entities()` ile aynı — `test_svg.py` (OCCT'siz)
- [ ] K13 Uçtan uca: delikli + cepli blokta `make_drawing(..., section=("on", y))` DXF ve SVG'ye yazılıyor; DXF geri
  okununca `GORUNUR` / `GIZLI` toplam boyları `Sheet`'tekiyle rel 1e-9 aynı — `test_sheet.py`
- [ ] Tüm testler yeşil (`pytest` 0 failed, bu SPEC'te 0 "uygulanmamış"), `ruff check .` ve `ruff format --check .` temiz

## Kapsam dışı
- İzometrik / perspektif görünüş, yardımcı (eğik) görünüş, detay görünüşü, kırık / yarım kesit, kademeli kesit
- Eğik düzlemli kesit (sadece görünüş düzlemine paralel kesitler)
- Tam ISO ölçülendirme: delik derinliği, cep ölçüleri, pah ve yarıçap ölçüleri, tolerans, yüzey işareti, geometrik
  tolerans (GD&T), ölçü çakışmasını otomatik çözme
- Antet (başlık bloğu), pafta çerçevesi ve standart kağıt boyları (A4/A3)
- DXF'de `DIMENSION`, `HATCH`, `LWPOLYLINE`, blok ve R12 sonrası sürümler; DXF'den 3D okuma
- Montaj resmi, parça listesi, balon — SPEC 07 sonrası
- PDF çıkışı, ekrana çizim (`viz/`)
- Diş gösterimi (SPEC 23'te dişli delik geldiğinde)
