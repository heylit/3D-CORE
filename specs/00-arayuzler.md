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

## Kapsam dışı
- Takım yolu üretimi (03), G-code yazma/okuma (04), kısıt çözme (08), STEP montaj (07), parça modelleme işlemleri (02)
- Alt montajlar (07'de), takım tutucu ve takım ömrü bilgisi
- `core/` FEM'de herhangi bir değişiklik
