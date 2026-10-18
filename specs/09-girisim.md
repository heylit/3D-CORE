# SPEC 09 — Boolean API, montajda girişim ve boşluk kontrolü (Dalga 4)

## Amaç
Parçalar üzerinde genel boolean işlemleri (`cut` / `fuse` / `common`), rijit taşıma ve en küçük uzaklık;
bunların üstünde bir montaj ağacındaki (SPEC 07) parçalar arasında **girişimi** (hacim kesişimi),
**temas**ı ve **dar boşluğu** ayıran, alt montajları ve paylaşımlı tanımları doğru yollarla raporlayan,
büyük montajda gereksiz OCCT çağrısı yapmayan bir kontrol.

## Teori

### Sınıflandırma
İki katı A ve B (dünya koordinatında) için:
- **Kesişim hacmi** `V∩ = hacim(A ∩ B)` (OCCT boolean *common*).
- **Yüzey uzaklığı** `d = min ‖p − q‖`, `p ∈ ∂A`, `q ∈ ∂B` (OCCT `BRepExtrema_DistShapeShape`).

Dikkat: `d` sınırlar arasıdır. B tamamen A'nın içindeyse `d > 0` ama `V∩ = hacim(B)`. Bu yüzden önce
hacme, sonra uzaklığa bakılır:

| Durum | Koşul | Rapor |
|---|---|---|
| Girişim (`GIRISIM`) | `V∩ > tol_v` | `volume = V∩`, `distance = 0`, `center` = kesişimin ağırlık merkezi |
| Temas (`TEMAS`) | `V∩ ≤ tol_v` ve `d ≤ tol_d` | `volume = 0`, `distance = d`, `points = (p, q)` |
| Dar boşluk (`DAR`) | `tol_d < d < clearance` | `volume = 0`, `distance = d`, `points = (p, q)` |
| Serbest | `d ≥ clearance` (ve `d > tol_d`) | raporlanmaz |

Varsayılanlar: `tol_v = 1e-6 mm³`, `tol_d = 1e-6 mm`, `clearance = 0` (dar boşluk aranmaz).
Yüz yüze değen iki blokta OCCT `V∩ = 0` ve `d = 0` verir (ön deneme), yani temas girişimden temiz ayrılır.

### Rijit taşıma
Parça yerel koordinatta, montajdaki dünya dönüşümü `T = [[R, t], [0, 1]]` (SPEC 07 `walk`). Taşınan
parçada her nokta `p' = R p + t`; hacim değişmez, ağırlık merkezi `c' = R c + t`. Delik kayıtları da
taşınır: `origin' = R origin + t`, `axis' = R axis` (Craig, *Introduction to Robotics*, Bölüm 2).

### Kaba eleme (broad phase)
Her yaprak için dünya eksen hizalı kutusu (AABB): yerel `bbox`'ın 8 köşesi `T` ile taşınır, min / max
alınır. Bu kutu gerçek şekli her zaman içerir (dönmüş parçada daha büyük olabilir). İki kutu arasındaki
boşluk `g = ‖max(0, lo_B − hi_A, lo_A − hi_B)‖` ise `d ≥ g`'dir; `g ≥ clearance` ve `g > tol_d` olan
çift kesin olarak serbesttir ve OCCT'ye gönderilmez. Adaylar x eksenine göre sıralanıp süpürülür
(sort and sweep; Ericson, *Real-Time Collision Detection*, Bölüm 7.5).

### Analitik doğrulama değerleri
- Eksen hizalı iki blok: `V∩ = Π_k max(0, min(hi_k) − max(lo_k))`.
- Kenarı `2h` olan iki küp, aynı merkezli, biri Z'de 45° dönmüş: kesit düzgün sekizgen,
  `V∩ = 16 h³ (√2 − 1)` (ön deneme h = 5: 828.427124746, rel 3e-16).
- İki küre `r₁`, `r₂`, merkezler arası `D` (`|r₁ − r₂| < D < r₁ + r₂`), mercek hacmi:
  `V∩ = π (r₁ + r₂ − D)² (D² + 2D r₁ − 3r₁² + 2D r₂ + 6 r₁ r₂ − 3 r₂²) / (12 D)`;
  boşluk `d = D − r₁ − r₂` (`D > r₁ + r₂`). Ön deneme r₁ = 10, r₂ = 6, D = 12: 167.55160815, rel 2e-9.
- Pim (yarıçap `r`) delikte (yarıçap `R`), eş eksenli, iç içe boy `L`: `r < R` → `DAR`, `d = R − r`;
  `r = R` → `TEMAS`; `r > R` → `GIRISIM`, `V∩ = π (r² − R²) L` (sıkı geçme; ön deneme rel 2e-15).

### OCCT ön deneme bulgusu
build123d 0.13'te iki kürenin `a & b` / `a.intersect(b)` sonucu yanlış (küçük kürenin tamamı: 904.78
yerine 167.55 olmalı); doğrudan `BRepAlgoAPI_Common` doğru. Bu yüzden `geometry/boolean.py` OCCT
`BRepAlgoAPI_Cut / Fuse / Common`'ı doğrudan kullanır ve sonucun geçerliliğini (`BRepCheck_Analyzer`)
denetler; küre benchmark'ı bu hatayı yakalamak için kabul kriterindedir.

## Dosyalar
- Yeni: `geometry/boolean.py` (OCCT boolean, taşıma, uzaklık), `assy/girisim.py` (montaj girişim kontrolü;
  saf Python + numpy), `tests/geometry/test_boolean.py`, `tests/assy/test_girisim.py`,
  `durum/09-girisim.md`
- Ön koşul (ayrı arayüz PR'ı, bu SPEC'ten önce, `geometry/part.py` sahibi): `Part`'a aşağıdaki beş metot.
  Gövdeleri `section_z` gibi `geometry.boolean`'a yönlendirir; `geometry/boolean.py` iskeleti bu SPEC'in
  dalında gelir.
- Dokunulmayacak: `assy/model.py` (değişiklik gerekmez), `assy/tree.py`, `assy/bom.py`, `cam/`, `core/`,
  `pyproject.toml`. Yeni bağımlılık yok.

`assy/girisim.py` OCCT import etmez: parçayı sadece `Part` arayüzünden (`bbox`, `moved`, `common`,
`distance`, `volume`, `center_of_mass`) kullanır; böylece kutu biçimli sahte parçalarla OCCT'siz test
edilir. Gerçek `Part` kullanan testler `@pytest.mark.occt` işaretli.
Yapı / girdi hatası → `assy.model.AssyError`; şekil / boolean hatası → `geometry.part.GeometryError`.
Hiçbir fonksiyon girdisini değiştirmez.

## Arayüz

### Ön koşul: `geometry/part.py` → `Part` metotları (arayüz PR'ı)
```python
def moved(self, T: np.ndarray) -> Part:
    """Rijit T (4x4) ile taşınmış yeni parça; ad aynı, delik kayıtları da taşınır. Rijit değilse GeometryError."""


def common(self, other: Part, tol_v: float = 1e-6) -> Part | None:
    """Kesişim (A ∩ B). Hacmi ≤ tol_v ise None (temas veya ayrık)."""


def cut(self, other: Part) -> Part:
    """Fark (A − B). Delik kayıtları korunur. Sonuç boşsa GeometryError."""


def fuse(self, other: Part) -> Part:
    """Birleşim (A ∪ B), tek parça; delik kayıtları A, B sırasıyla."""


def distance(self, other: Part) -> tuple[float, np.ndarray, np.ndarray]:
    """Sınırlar arası en küçük uzaklık d ve en yakın noktalar (p ∈ ∂A, q ∈ ∂B), mm."""
```
Boolean sonucu geçersiz şekilse veya OCCT işlemi başarısızsa `GeometryError`. `tol_v < 0` → `GeometryError`.

### `geometry/boolean.py`
Yukarıdaki beş işlemin gövdeleri: `moved(part, T)`, `common(a, b, tol_v)`, `cut(a, b)`, `fuse(a, b)`,
`distance(a, b)`. Ad sonucu: `cut` / `common` → `a.name`; `fuse` → `a.name`.

### `assy/girisim.py`
```python
class ClashKind(StrEnum):
    GIRISIM = "girisim"
    TEMAS = "temas"
    DAR = "dar"


@dataclass(frozen=True)
class Clash:
    a: str  # yaprak yolu (SPEC 07 walk biçimi), walk sırasında önce gelen
    b: str
    kind: ClashKind
    volume: float  # mm³; GIRISIM dışında 0
    distance: float  # mm; GIRISIM'de 0
    center: np.ndarray | None  # GIRISIM: kesişimin ağırlık merkezi (dünya); diğerleri None
    points: tuple[np.ndarray, np.ndarray] | None  # TEMAS / DAR: en yakın noktalar (dünya, a'da, b'de)
```
- `check(root: Node, parts: Mapping[str, Part], clearance: float = 0.0, tol_v: float = 1e-6,
  tol_d: float = 1e-6, scope: str = "", across: bool = False, ignore: Iterable[tuple[str, str]] = ())
  -> list[Clash]`
  - `validate(root)` çağrılır. Her yaprak `parts[yaprak.part].moved(world(root, yol))` ile dünyaya taşınır.
  - Sadece `scope` yolundaki düğümün altındaki yapraklar (`""` = kök, tüm montaj) karşılaştırılır.
  - `across=True`: sadece `scope`'un **farklı doğrudan çocuklarının** altındaki yaprak çiftleri (alt montajlar
    arası kontrol; bir alt montajın kendi içi atlanır).
  - `ignore`: bu yaprak yolu çiftleri (sırasız) atlanır (ör. bilerek sıkı geçme, dişli bağlantı).
  - Kaba eleme Teori'deki gibi; elenen çift için `common` / `distance` çağrılmaz.
  - Sıra: `a`'nın `walk` sırası, sonra `b`'nin. Her sırasız çift en çok bir kez.
  - Paylaşımlı alt montaj tanımının iç girişimi her oluşumda ayrı satırdır (yollar farklı).
  - Hatalar (`AssyError`): ağaçtaki parça kimliği `parts`'ta yok; bilinmeyen `scope` veya `scope` bir
    yaprak; `across=True` ve `scope`'un tek çocuğu var; `ignore`'da yaprak olmayan yol; `clearance`,
    `tol_v`, `tol_d` negatif veya sonlu değil.
- `gap(root, parts, a: str, b: str) -> tuple[float, np.ndarray, np.ndarray]` — iki yaprak arasında
  (kaba eleme olmadan) dünya koordinatında `distance`; bilinmeyen / yaprak olmayan yol veya `a == b` →
  `AssyError`.
- `world_aabb(part, T) -> tuple[np.ndarray, np.ndarray]` — Teori'deki taşınmış kutu (kaba elemenin
  kendisi; ayrı test edilir).

## Kabul kriterleri
- [ ] K1 `moved`: dönmüş + ötelenmiş blokta hacim rel 1e-9 aynı, ağırlık merkezi `R c + t` atol 1e-9,
  `bbox` el hesabıyla; delik kaydının `origin` / `axis`'i taşınmış; rijit olmayan `T` → `GeometryError`
  (`@pytest.mark.occt`) — `tests/geometry/test_boolean.py`
- [ ] K2 `common` / `cut` / `fuse` analitik: eksen hizalı bloklar (`V∩` formülü, `V_A − V∩`,
  `V_A + V_B − V∩` rel 1e-9); 45° dönmüş küpler `16h³(√2 − 1)` rel 1e-9; iki küre mercek hacmi en az iki
  `D` değerinde rel 1e-6; yüz yüze değen bloklarda `common` → `None`; tamamen içerdeki küçük blokta
  `common` hacmi = küçük bloğun hacmi; `cut` sonucu boş → `GeometryError` (`occt`) — `test_boolean.py`
- [ ] K3 `distance`: aralıklı bloklar `d` el hesabıyla atol 1e-9; iki ayrık küre `D − r₁ − r₂` atol 1e-9 ve
  en yakın noktalar merkez doğrusunda; temas eden bloklarda `d = 0` (`occt`) — `test_boolean.py`
- [ ] K4 `check` sınıflandırma (gerçek parçalar, `occt`): pim–delik üç durumu (`DAR` + `d = R − r`,
  `TEMAS`, `GIRISIM` + `π(r² − R²)L` rel 1e-6); `clearance = 0` iken dar boşluk raporlanmıyor; içerdeki
  parça `GIRISIM`; temiz (aralıklı) montajda boş liste — `tests/assy/test_girisim.py`
- [ ] K5 Alt montajlar (sahte kutu parçalarla, OCCT'siz): paylaşımlı tanımın iki oluşumunda iç girişim iki ayrı
  satır, doğru yollarla; dönmüş alt montajda girişim hacmi ve merkezi dünya koordinatında el hesabıyla;
  `scope` ile sadece alt ağaç; `across=True` ile alt montaj içi çiftler yok, aralarındakiler var; `ignore`
  çifti atlıyor; satır sırası ve `a`/`b` sırası Arayüz'deki gibi — `test_girisim.py`
- [ ] K6 Kaba eleme (sahte parçalar, çağrı sayan): `world_aabb` 45° dönmüş kutuda el hesabıyla;
  10 × 10 ızgarada 1 mm aralıklı 100 blok, `clearance = 0.5` → 0 `common` / `distance` çağrısı ve boş
  sonuç; `clearance = 1.2` → sadece kenar komşusu çiftler (180) çağrılıyor ve hepsi `DAR` (köşe komşuları √2 mm uzakta, elenir); elemenin hiçbir
  gerçek girişimi kaçırmadığı rastgele dönmüş 30 kutuda (sabit tohum) kaba elemesiz tam taramayla aynı
  sonuç — `test_girisim.py`
- [ ] K7 Hatalar: Arayüz'deki her `AssyError` durumu ayrı ayrı; `gap` bilinmeyen yol, `a == b` —
  `test_girisim.py`
- [ ] Tüm testler yeşil (`pytest` 0 failed, bu SPEC'te 0 "uygulanmamış"), `ruff check .` ve
  `ruff format --check .` temiz

## Kapsam dışı
- Dinamik (hareket boyunca) çarpışma, tezgâh / takım / fikstür çarpışması (SPEC 10 montaj-CAM ve Dalga 4 5 eksen)
- Diş geometrisine göre girişim ayrımı: dişli delikteki civata nominal çapla modellenirse `GIRISIM` verir;
  bilinçli olanlar `ignore` ile atlanır (otomatik "dişi yok say" ileride)
- Nüfuz derinliği (penetration depth) ve ayırma yönü; sadece kesişim hacmi ve merkezi verilir
- Kısıtlardan (`Mate`) beklenen temasları otomatik tanıma
- Sonuçları ekranda gösterme (`viz/`, Tezgah) ve montaj STEP'ine yazma
- Ağ (mesh) tabanlı hızlı yaklaşık kontrol; kontrol kesin B-rep üzerindendir
