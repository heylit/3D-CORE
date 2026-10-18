# SPEC 00 — Arayüzler ve ortak kurulum (Dalga 0)

## Amaç
Dalga 1'deki SPEC'lerin (01-bar, 02-parca, 03-cam-2d, 04-gcode, 08-kisitlar) birbirini beklemeden,
bulutta ve yerelde aynı anda geliştirilebilmesi için paketler arası arayüzleri ve ortak kurulumu sabitlemek.
Bu SPEC hesap yapmaz (takım yolu, kısıt çözme yok); sadece veri modellerini, doğrulamalarını ve araç düzenini kurar.

## Teori
- Konum / yönelim: 4x4 homojen dönüşüm `T = [[R, t], [0, 1]]`, `R` ortonormal ve `det(R) = +1`.
  Nokta dönüşümü `p' = R p + t`, yön dönüşümü `d' = R d`. Kaynak: Craig, *Introduction to Robotics*, Bölüm 2.
- Takım yolu hareketleri G-code anlamıyla aynıdır (ISO 6983): `G0` hızlı, `G1` doğrusal, `G2` saat yönü yay,
  `G3` saat yönü tersi yay. Yaylar XY düzleminde (G17); Z değişirse helis. Merkez mutlak koordinatta verilir.
  Yay boyu: `s = sqrt((r·|Δθ|)² + Δz²)`; başlangıç ve bitiş XY'de aynıysa tam daire (`|Δθ| = 2π`).
  Kaynak: Smid, *CNC Programming Handbook*, Bölüm 29 (dairesel enterpolasyon).
- Birimler: mm, mm/dk (ilerleme), dev/dk (devir), derece (açı girdisi), radyan (iç hesap).

## Dosyalar
- Yeni: `geometry/part.py`, `cam/__init__.py`, `cam/model.py`, `assy/__init__.py`, `assy/model.py`,
  `conftest.py` (kök), `tests/geometry/`, `tests/cam/`, `tests/assy/`, `.claude/settings.json`,
  `scripts/bulut_kurulum.sh`, `durum/00-arayuzler.md`
- Değişecek: `pyproject.toml` (paketler, `occt` işareti), `.github/workflows/test.yml` (sadece kurulum satırı),
  `ci.ps1` (uygulanmamış test sayısı)
- Dokunulmayacak: `core/**`, `tests/unit/**`, `tests/benchmarks/**`

## Arayüz

### `geometry/part.py` (OCCT gerektirir; build123d sadece bu dosyanın içinde import edilir)
- `class GeometryError(ValueError)`
- `class Part(shape, name="parca")` — `shape` bir build123d `Shape` (Solid / Compound). Boş veya hacmi ≤ 0 ise `GeometryError`.
  - `volume -> float` [mm³], `area -> float` [mm²], `center_of_mass -> np.ndarray (3,)` [mm]
  - `bbox -> tuple[np.ndarray, np.ndarray]` (min köşe, max köşe)
  - `to_step(path)`, `Part.from_step(path, name=None) -> Part` (dosya yoksa `GeometryError`)
  - `to_stl(path, tolerance=0.01)`

### `cam/model.py` (saf Python + numpy)
- `class CamError(ValueError)`
- `class ToolKind(str, Enum)`: `FLAT="duz"`, `BALL="kuresel"`, `DRILL="matkap"`
- `@dataclass Tool(id: int, name: str, kind: ToolKind, D: float, flute_length: float, corner_r: float = 0.0)`
  - `D > 0`, `flute_length > 0`, `0 <= corner_r <= D/2`; `BALL` için `corner_r` otomatik `D/2` olur. Aksi `CamError`.
- `@dataclass Stock(xmin, ymin, zmin, xmax, ymax, zmax)` — her eksende max > min, aksi `CamError`; `size -> np.ndarray (3,)`, `volume -> float`
- `class MoveType(str, Enum)`: `RAPID="G0"`, `LINEAR="G1"`, `ARC_CW="G2"`, `ARC_CCW="G3"`
- `@dataclass Move(type: MoveType, end: tuple[float, float, float], feed: float | None = None, center: tuple[float, float] | None = None)`
  - `center` sadece yaylarda, XY mutlak koordinat.
- `@dataclass Toolpath(name: str, tool: Tool, start: tuple[float, float, float], moves: list[Move], rpm: float)`
  - `validate()` → `CamError` şu durumlarda: `rpm <= 0`; G1/G2/G3 için `feed` yok veya `<= 0`; yayda `center` yok;
    yayda `|start_xy - c|` ile `|end_xy - c|` farkı > 1e-6 mm; yay yarıçapı < 1e-9.
  - `points() -> np.ndarray (n+1, 3)` — başlangıç + her hareketin bitişi
  - `length(types: set[MoveType] | None = None) -> float` — yaylar gerçek yay boyuyla (helis dahil); `types` verilirse sadece o hareketler
  - `bbox() -> tuple[np.ndarray, np.ndarray]` — yayların XY uç noktalarını da (eksen kesişimleri) içerir
  - `to_dict()`, `Toolpath.from_dict(d)` — JSON uyumlu, gidiş-dönüş birebir

### `assy/model.py` (saf Python + numpy)
- `class AssyError(ValueError)`
- `transform(R=None, t=None) -> np.ndarray (4,4)`; `rot_x(deg)`, `rot_y(deg)`, `rot_z(deg)` → 3x3
- `is_rigid(T, tol=1e-9) -> bool` — `R^T R = I` ve `det R = +1` ve son satır `[0,0,0,1]`
- `class RefKind(str, Enum)`: `PLANE="duzlem"`, `AXIS="eksen"`, `POINT="nokta"`
- `@dataclass Ref(component: str, kind: RefKind, origin: tuple[float,float,float], direction: tuple[float,float,float] = (0,0,1))`
  - Parçanın kendi (yerel) koordinatında. `PLANE` için `direction` = normal, `AXIS` için eksen yönü; sıfır vektör → `AssyError`; birim vektöre normalize edilir.
- `class MateKind(str, Enum)`: `COINCIDENT="cakisik"`, `CONCENTRIC="es_eksen"`, `DISTANCE="mesafe"`, `ANGLE="aci"`
- `@dataclass Component(name: str, part: str, T: np.ndarray = I4, fixed: bool = False)` — `T` rijit değilse `AssyError`
- `@dataclass Mate(kind: MateKind, a: Ref, b: Ref, value: float = 0.0)` — `DISTANCE` için value ≥ 0, `ANGLE` için 0–180 derece
- `@dataclass Assembly(name: str, components: list[Component], mates: list[Mate] = [])`
  - `component(name) -> Component` (yoksa `AssyError`)
  - `validate()` → yinelenen bileşen adı, bilinmeyen bileşene giden kısıt, bir kısıtın iki ucunun aynı bileşen olması → `AssyError`
  - `world(ref) -> tuple[np.ndarray, np.ndarray]` — referansın dünya koordinatında origin ve birim yönü (`T` ile)
  - `to_dict()`, `Assembly.from_dict(d)` — JSON uyumlu, gidiş-dönüş birebir

### Ek — arayüz PR'ı 2026-10-18 (inceleme Y4, Y5, O3)
Dalga 2'nin (CAM 05/06, montaj 07, tet ağları 11–12) ihtiyacı için eklenenler. Geriye uyumludur: eski çağrılar ve
JSON'lar aynen çalışır.
- `core/model.py`
  - `Model.node / node_index / material / section` O(1): id → indeks sözlüğü, listeye dışarıdan ekleme / değiştirme
    sonrası kendini onarır (bulunan kaydın anahtarı tutmazsa veya anahtar yoksa bir kez yeniden kurulur).
    Sözlük dataclass alanı değildir; `to_dict` ve eşitliğe girmez.
  - `Material` (E, nu, rho), `Section` (A), `Node` (x, y, z), `BC.value`, `Load.value`: `nan` / `inf` → `ModelError`.
  - `Model.from_dict`: eksik / fazla / yanlış tipte alan → `ModelError` (eskiden `TypeError`).
- `geometry/part.py` (OCCT uygulaması `geometry/query.py`'de; diğer paketler onu değil `Part`'ı kullanır)
  - `@dataclass Region(outer: (k,2) CCW, holes: tuple[(k,2) CW, ...])` — kapalı çokgen, son nokta tekrarsız
  - `@dataclass PlanarFace(index, origin (3,), normal (3,) dışa bakan birim, area)`
  - `@dataclass CylindricalFace(index, origin (3,), axis (3,) birim, radius, length, angle [derece], concave, area)`
    — eksen `origin + s·axis, s ∈ [0, length]`; `concave=True` → delik / cep köşesi; `angle = 360` → tam silindir
  - `Part.section_z(z, tol=0.01) -> list[Region]` — z düzlemindeki malzeme; kiriş sapması ≤ tol; kesmiyorsa `[]`
  - `Part.planar_faces() -> list[PlanarFace]`, `Part.cylindrical_faces() -> list[CylindricalFace]`
    (`index` ortak yüz numarası, aynı parçada kararlı)
  - `Part.mesh(tol=0.01) -> (V, T)` — `geometry.mesh.tessellate` ile aynı
- `assy/model.py`
  - `Mate(..., flip: bool = False)` — yönlü referansın yönü ters alınır (b'nin; b NOKTA ise a'nın):
    PLANE–PLANE zıt → aynı yön; POINT–PLANE DISTANCE öbür taraf; ANGLE θ → 180° − θ.
    Etkisiz olduğu kısıtlarda (eksen–eksen, nokta–nokta, nokta–eksen, nokta–düzlem çakışık) `flip=True` → `AssyError`.
    JSON'da `"flip"` alanı; yoksa `False`.
  - `Mate.value`, `Ref.origin`, `Ref.direction`: `nan` / `inf` → `AssyError`.
- `cam/model.py`
  - `Tool` (D, flute_length, corner_r), `Stock` sınırları, `Move` (end, center, feed), `Toolpath.start`:
    `nan` / `inf` → `CamError`. `Toolpath.validate()` aynı kontrolleri (ve `rpm`) yerinde değişikliğe karşı tekrarlar.

### Ek 2 — Dalga 2 CAM arayüzü 2026-10-18 (SPEC 14 kurulum, 20 torna yolu, 05 tutucu çarpışması)
Geriye uyumludur: yukarıdaki bütün çağrılar, alanlar ve eski JSON'lar aynen çalışır; yeni alanların hepsinin varsayılanı var.
Sadece veri tipleri ve doğrulamaları; hesap (devir / ilerleme, telafi, çarpışma) ilgili SPEC'tedir.

**Birimler ve yönler**
- Kesme hızı `Vc` m/dk; diş başı ilerleme `fz` mm/diş (freze); devir başı ilerleme `fn` mm/dev (torna); açılar derece.
- Torna: iş mili ekseni Z, X radyal. Modelde X **yarıçaptır** (çap programlama G-code işidir, SPEC 21). Torna yolları
  `y = 0` düzleminde, XZ'dedir.
- `G18` (ZX düzlemi) yaylarında yön +Y'den bakınca tanımlanır (ISO 6983, sağ el kuralı +Y ekseni etrafında):
  `G3` = Z'den X'e doğru dönüş. `G17`'de olduğu gibi yay düzleme dik eksende (burada Y) ilerlerse helistir.
  Yay boyu formülü aynı: `s = sqrt((r·|Δθ|)² + Δ⊥²)`.

**Yeni sabitler**
- `class Plane(str, Enum)`: `XY="G17"`, `ZX="G18"`
- `class FeedMode(str, Enum)`: `PER_MIN="G94"` (mm/dk), `PER_REV="G95"` (mm/dev)
- `class LatheToolKind(str, Enum)`: `TURN="tornalama"`, `BORE="ic_tornalama"`, `GROOVE="kanal"`, `THREAD="dis"`
  (değerler `ToolKind` değerleriyle çakışmaz; JSON'da takım türü `kind` değerinden anlaşılır)

**Kesme verisi**
- `@dataclass CuttingData(Vc: float, fz: float | None = None, fn: float | None = None, ap: float | None = None, ae: float | None = None)`
  - `Vc > 0`; `fz` ve `fn`'den **tam olarak biri** verilir ve `> 0`; `ap`, `ae` verilirse `> 0`; `nan` / `inf` → `CamError`.
  - `to_dict()`, `CuttingData.from_dict(d)`

**Takım tutucu (05 çarpışma, 14 takım boyu)**
- `@dataclass ToolHolder(name: str, gauge_length: float, profile: tuple[tuple[float, float], ...])`
  - `gauge_length`: iş mili ölçü hattından tutucu ağzına boy, `> 0`.
  - `profile`: tutucunun dönel kesiti, `(z, r)` noktaları; `z` tutucu ağzından yukarı (ağız `z = 0`), ilk nokta `z = 0`,
    `z` azalmayan, `0 <= z <= gauge_length`, `r > 0`, en az 2 nokta. Ardışık iki nokta arası kesik koni.
    Aksi `CamError`.
  - `to_dict()`, `ToolHolder.from_dict(d)`

**Freze takımı — `Tool`'a eklenen alanlar** (hepsi isteğe bağlı)
- `flutes: int | None = None` — diş sayısı `z`, verilirse `>= 1`
- `shank_d: float | None = None` — sap çapı, verilirse `> 0`; `None` → `D` kabul edilir (`shank` özelliği)
- `stickout: float | None = None` — tutucu ağzından takım ucuna boy, verilirse `>= flute_length`
- `holder: ToolHolder | None = None`
- `cutting: dict[str, CuttingData] = {}` — malzeme adı → kesme verisi; freze için her kayıtta `fz` zorunlu (`fn` → `CamError`)
- `gauge_length -> float | None` (özellik) — `holder.gauge_length + stickout`; ikisinden biri yoksa `None`.
  Fanuc `G43 H` ve GRBL prob ölçümünün (`G38.2` + `G43.1`) karşılaştırılacağı değer (SPEC 14).
- `to_dict()`, `Tool.from_dict(d)` — eksik yeni alanlar varsayılan alır

**Torna takımı**
- `@dataclass LatheTool(id: int, name: str, kind: LatheToolKind, nose_r: float, tip: int, kappa_r: float, eps_r: float, width: float = 0.0, cutting: dict[str, CuttingData] = {})`
  - `nose_r` burun yarıçapı `>= 0` (`TURN`, `BORE` için `> 0`).
  - `tip`: Fanuc hayali uç numarası 0..9 (burun yarıçapı telafisinin yönü; 0 ve 9 burun merkezi).
  - `kappa_r`: yaklaşma açısı (ana kesici kenar ile ilerleme yönü arası), `eps_r`: uç açısı (ISO: C 80°, D 55°, V 35°,
    T 60°, diş 60°). `0 < kappa_r < 180`, `0 < eps_r < 180`, `kappa_r + eps_r <= 180` (arka kenarda boşluk).
  - `GROOVE` için `width > 0` ve `nose_r <= width / 2`; diğerlerinde `width = 0`.
  - `cutting` kayıtlarında `fn` zorunlu (`fz` → `CamError`).
  - `nan` / `inf` → `CamError`. `to_dict()`, `LatheTool.from_dict(d)`
- `tool_from_dict(d) -> Tool | LatheTool` — `kind` değerine göre

**Takım kütüphanesi**
- `@dataclass ToolLibrary(tools: list[Tool | LatheTool] = [])`
  - `validate()` → yinelenen `id` → `CamError`; `get(id)` → yoksa `CamError`; `add(tool)` → yinelenen `id` → `CamError`
  - `to_dict()`, `ToolLibrary.from_dict(d)` — JSON gidiş-dönüş birebir (SPEC 14 dosyaya yazar / okur)

**Ham malzeme ve kurulum**
- `Stock`: `to_dict()`, `Stock.from_dict(d)` eklendi.
- `@dataclass CylinderStock(D: float, zmin: float, zmax: float, d: float = 0.0)` — Z eksenli silindir (torna çubuğu, boru),
  ekseni `x = y = 0`; `D > 0`, `zmax > zmin`, `0 <= d < D`, aksi `CamError`.
  - `length -> float`, `volume -> float` = `π/4·(D² − d²)·(zmax − zmin)`, `bbox() -> (min, max)`; `to_dict` / `from_dict`
- `@dataclass Wcs(code: str = "G54", origin: tuple[float, float, float] = (0, 0, 0))`
  - `code` `G54`..`G59`; `origin` iş sıfırının makine koordinatı. `to_machine(p) = p + origin`, `to_work(p) = p − origin`.
  - `to_dict` / `from_dict`
- `@dataclass Setup(name: str, wcs: Wcs, stock: Stock | CylinderStock, fixtures: list[Stock | CylinderStock] = [])`
  - Bağlama elemanları (mengene çenesi, pabuç, torna aynası) iş koordinatında kutu veya silindir; 05 ve 22 çarpışma için okur.
  - `to_dict()`, `Setup.from_dict(d)`

**`Toolpath`'e eklenenler**
- `tool: Tool | LatheTool`
- `plane: Plane = Plane.XY` — yaylar bu düzlemde. `center` iki sayıdır: `XY` → `(x, y)`, `ZX` → `(x, z)` (I, K sırası).
- `feed_mode: FeedMode = FeedMode.PER_MIN` — `feed` birimi
- `css: float | None = None` — `G96` sabit kesme hızı `Vc` [m/dk]; verilirse `> 0` ve `rpm` devir üst sınırıdır (`G50`).
- `validate()` ek olarak: `css <= 0`; takım `LatheTool` ise `plane` `ZX` değil veya başlangıçta / herhangi bir bitişte `y != 0`
  → `CamError`. Yay yarıçapı denetimi, `length()` ve `bbox()` yayın düzleminde yapılır.
- `to_dict` / `from_dict`: `plane`, `feed_mode`, `css` alanları; yoksa varsayılan (eski JSON çalışır).

**G-code yazıcısı koruması (`cam/gcode/writer.py`, geçici)**
- Yazıcı (SPEC 04) şimdilik yalnız G17 / G94 / sabit devirli freze yollarını yazar; `plane != XY`, `feed_mode != PER_MIN`,
  `css is not None` veya takım `LatheTool` ise `CamError` (sessizce G17 yayı yazmasın). SPEC 21 torna yazıcısıyla bu korumayı kaldırır.

### Ek — eskiz bölge kenarı kaynağı 2026-10-18 (SPEC 18 S2)
- `sketch/model.py`: `SegLine` ve `SegArc`'a son alan olarak `src: str = ""` eklendi: bölge kenarının geldiği eskiz
  öğesinin kimliği (`""` → bilinmiyor; metin değilse `SketchError`). Özellik ağacı yan yüzleri `yan:<src>` diye adlandırır.
  Varsayılan boş olduğundan mevcut çağrılar değişmez; eskiz çözücüsü (SPEC 17) bölge çıkarırken doldurur.

### Ortak kurulum
- `pyproject.toml`: paket listesine `cam*`, `assy*`; pytest işareti `occt: build123d / OpenCascade gerektirir`.
- Kök `conftest.py`:
  - build123d kurulu değilse `occt` işaretli testler atlanır (sebep yazılı).
  - **Uygulanmamış kod kuralı:** bir test sadece `NotImplementedError` yüzünden düşerse `xfail` ("uygulanmamış") sayılır.
    Böylece TDD'de kırmızı testler commit'i ve paralel dalları engellemez; gerçek hatalar (yanlış sayı, yanlış hata) yine kırmızıdır.
    Bir SPEC'in bitti sayılması için kendi testlerinde 0 "uygulanmamış" olmalı.
- `.github/workflows/test.yml`: kurulum `pip install -e ".[dev,cad]"`; tetikleyici, sürüm, işletim sistemi değişmez.
- Bulut oturumları: `.claude/settings.json` içinde SessionStart hook'u → `scripts/bulut_kurulum.sh`
  (sadece bulutta: `.venv` yoksa kurar, `pip install -e ".[dev,cad]"`, `git config core.hooksPath .githooks`).

## Kabul kriterleri
- [ ] K1 `Tool`, `Stock` doğrulamaları ve `BALL → corner_r = D/2` — `tests/cam/test_model.py`
- [ ] K2 `Toolpath.validate` her hata durumunu yakalıyor — `tests/cam/test_model.py`
- [ ] K3 `Toolpath.length`: doğrusal, çeyrek yay (πr/2), tam daire (2πr), helis (`sqrt((2πr)² + h²)`) rel 1e-12; G0 filtresi — `tests/cam/test_model.py`
- [ ] K4 `Toolpath.bbox` yarım dairede yayın tepe noktasını içeriyor; `to_dict/from_dict` gidiş-dönüş — `tests/cam/test_model.py`
- [ ] K5 `transform`, `rot_*`, `is_rigid`: 90° dönüşler tam değer, yansıma (det = −1) rijit değil — `tests/assy/test_model.py`
- [ ] K6 `Ref` normalize ediliyor, sıfır vektör hata; `Component` rijit olmayan T'yi reddediyor — `tests/assy/test_model.py`
- [ ] K7 `Assembly.validate` hataları, `world(ref)` bilinen dönüşümle doğru, JSON gidiş-dönüş — `tests/assy/test_model.py`
- [ ] K8 `Part`: 10×20×30 kutuda hacim 6000, alan 2200, ağırlık merkezi ve sınır kutusu tam; STEP gidiş-dönüş hacmi koruyor; eksik dosya hata (`occt`) — `tests/geometry/test_part.py`
- [ ] K9 `NotImplementedError` → xfail kuralı; mevcut SPEC 01 testleri "uygulanmamış" görünüyor, `pytest` 0 failed
- [ ] K10 `ruff check .` temiz; bulut kurulum betiği temiz bir klonda `pytest` çalıştırabiliyor
- [ ] K11 (Ek 2) `CuttingData`, `ToolHolder`, `Tool` yeni alanları, `LatheTool` doğrulamaları; `gauge_length` = tutucu + taşma — `tests/cam/test_model_dalga2.py`
- [ ] K12 (Ek 2) `ToolLibrary` yinelenen id / bilinmeyen id hata; freze + torna takımlı kütüphane JSON gidiş-dönüş birebir — `tests/cam/test_model_dalga2.py`
- [ ] K13 (Ek 2) `CylinderStock` hacmi `π/4·(D² − d²)·L` rel 1e-12; `Wcs` `to_machine` / `to_work`; `Setup` JSON gidiş-dönüş — `tests/cam/test_model_dalga2.py`
- [ ] K14 (Ek 2) `G18` yayları: çeyrek yay boyu `πr/2`, helis (Y'de ilerleme), yön kuralı (G3 = Z'den X'e) `bbox` ile; torna yolunda `y != 0` ve `XY` düzlemi hata — `tests/cam/test_model_dalga2.py`
- [ ] K15 (Ek 2) Eski JSON (yeni alanlar yok) okunuyor; Dalga 1 testleri (`tests/cam/`) değişmeden geçiyor
- [ ] K16 (Ek 2) G-code yazıcısı (04) henüz desteklemediği yolları reddediyor: `plane != XY`, `feed_mode != PER_MIN`, `css` verilmiş veya takım `LatheTool` → `CamError` (SPEC 21 bu korumayı kaldırır) — `tests/cam/test_gcode_dalga2_koruma.py`

## Kapsam dışı
- Takım yolu üretimi (03), G-code yazma/okuma (04), kısıt çözme (08), STEP montaj (07), parça modelleme işlemleri (02)
- Alt montajlar (07'de), takım ömrü bilgisi (takım tutucu Ek 2 ile eklendi)
- `core/` FEM'de herhangi bir değişiklik
