# SPEC 07 — Montaj ağacı, malzeme listesi (BOM), montaj STEP'i (Dalga 2)

## Amaç
Parçaları ve alt montajları konumlarıyla (4x4 dönüşüm) tutan bir **montaj ağacı**; ağaçtan dünya
konumları, SPEC 08 çözücüsüne giden düz `Assembly` ve geri dönüş; adet ve kütleleri doğru bir **malzeme
listesi**; ve ağacı ürün / oluşum yapısıyla koruyan **montaj STEP** yazma-okuma.

## Teori

### Ağaç ve dönüşüm zinciri
Ağacın her düğümü bir **oluşumdur** (occurrence, STEP: `NEXT_ASSEMBLY_USAGE_OCCURRENCE`): bir ad, ebeveyne
göre bir dönüşüm `T` ve ya bir **parça** (yaprak) ya da **çocuklar** (alt montaj). Aynı parça veya aynı alt
montaj ağaçta birden çok kez kullanılabilir; tekrar kullanılan şey **tanımdır** (STEP: `PRODUCT`),
her kullanım ayrı bir oluşumdur.

Kökten bir düğüme giden yol `n₀ (kök), n₁, …, n_k` ise düğümün dünya dönüşümü
```
T_dünya(n_k) = T(n₀) · T(n₁) · … · T(n_k)
```
Yerel noktası `p` olan bir nokta dünyada `p' = R p + t` (Craig, *Introduction to Robotics*, Bölüm 2.3
"bileşik dönüşümler"). Düz montajdan ağaca dönüşte yaprak `n_k` için
```
T(n_k) = T_dünya(n_{k−1})⁻¹ · T_dünya,yeni(n_k)       T⁻¹ = [[Rᵀ, −Rᵀ t], [0, 1]]
```

### Malzeme listesi ve kütle
- Düz BOM: ağacın tüm yaprakları parça kimliğine göre toplanır. Adet `q_p` = o parçanın yaprak sayısı;
  toplam kütle `M_p = q_p · m_p`. Montaj kütlesi `M = Σ_p q_p m_p`.
- Üst seviye BOM: sadece kökün doğrudan çocukları, tanıma göre toplanır. Alt montaj satırının birim kütlesi
  kendi içindeki yaprakların kütle toplamıdır.
- Parça kütlesi `m = ρ V` (SPEC 02; `V = Part.volume`). Birimler N – mm – MPa: ρ [t/mm³], m [t].
- Montaj ağırlık merkezi (Beer & Johnston, *Statics*, Bölüm 5): yaprak `i`'nin kütlesi `m_i`, yerel ağırlık
  merkezi `c_i` (`Part.center_of_mass`), dünya dönüşümü `(R_i, t_i)` ise
  ```
  x̄ = Σ m_i (R_i c_i + t_i) / Σ m_i
  ```

### Montaj STEP'i
STEP AP214 montaj yapısı (ISO 10303-214; OCCT XCAF belgesi `STEPCAFControl_Writer/Reader`):
- Her parça kimliği ve her alt montaj tanımı **bir** `PRODUCT` olur (ad = kimlik / tanım adı); kökün
  tanımı da bir `PRODUCT`'tır.
- Her ağaç düğümü bir `NEXT_ASSEMBLY_USAGE_OCCURRENCE` olur (ad = düğüm adı), konumu ebeveyne göre `T`.
- Aynı parça 9 kez kullanılsa da şekli dosyada bir kez yazılır.
- OCCT gerçel sayıları 13 anlamlı basamakla yazar (ön deneme: `1.234567890123456 → 1.234567890123`);
  |t| ≤ 1000 mm için konum hatası ≤ 1e-9 mm.

## Dosyalar
- Yeni: `assy/tree.py` (ağaç gezinme, doğrulama, düzleştirme ve geri dönüş), `assy/bom.py` (BOM, kütle,
  ağırlık merkezi), `fileio/step_montaj.py` (montaj STEP yazma / okuma), `tests/assy/test_agac.py`,
  `tests/assy/test_bom.py`, `tests/fileio/__init__.py`, `tests/fileio/test_step_montaj.py`,
  `durum/07-montaj-agaci.md`
- Ön koşul (ayrı arayüz PR'ı, bu SPEC'ten önce): `assy/model.py`'ye `Node` sınıfı (aşağıda).
- Dokunulmayacak: `assy/model.py` (bu PR'da), `geometry/`, `assy/mates.py`, `assy/solver.py`,
  `pyproject.toml`. Yeni bağımlılık yok.

OCCT sadece `fileio/step_montaj.py` içinde kullanılır (`fileio/` dosya biçimleri paketidir; `assy/`
OCCT'siz kalır). `tests/fileio/test_step_montaj.py` ve gerçek `Part` kullanan testler `@pytest.mark.occt`
işaretli. `assy/tree.py` ve `assy/bom.py` saf Python + numpy'dir: parçayı sadece `.volume` ve
`.center_of_mass` özniteliklerinden okur, böylece OCCT'siz test edilir.

Hiçbir fonksiyon verilen ağacı değiştirmez; değişiklik gerektiren işlemler yeni ağaç döndürür.
Yapı hatası → `assy.model.AssyError`; dosya / şekil hatası → `geometry.part.GeometryError`.

## Arayüz

### Ön koşul: `assy/model.py` → `Node` (arayüz PR'ı)
```python
@dataclass
class Node:
    """Montaj ağacında bir oluşum. Yaprak: part dolu, children boş. Alt montaj: part None, children dolu."""

    name: str  # kardeşler arasında tekil, boş değil, '/' içermez
    T: np.ndarray = field(default_factory=lambda: np.eye(4))  # ebeveyne göre, rijit
    part: str | None = None  # yaprak: parça kimliği
    children: list[Node] = field(default_factory=list)
    ref: str | None = None  # alt montaj tanım adı; None → name

    @property
    def definition(self) -> str: ...  # yaprak: part; alt montaj: ref veya name
    def to_dict(self) -> dict: ...  # özyinelemeli; T liste olarak
    @classmethod
    def from_dict(cls, d: dict) -> Node: ...
```
`__post_init__`: `T` rijit değilse, `name` boşsa veya '/' içeriyorsa, yaprakta çocuk ya da `ref` varsa
`AssyError`. Ağaç bütünlüğü (kardeş adları, boş alt montaj, tanım tutarlılığı) `assy.tree.validate`'tedir,
çünkü ağaç adım adım kurulabilmeli.

### `assy/tree.py`
- `validate(root: Node) -> None` — `AssyError` durumları:
  kardeşler arasında yinelenen ad; çocuksuz alt montaj (kök dahil); aynı `Node` nesnesinin ağaçta iki kez
  bulunması (paylaşım nesneyle değil `ref` ile yapılır); aynı tanım adına sahip iki alt montajın içeriğinin
  farklı olması (adlar, parça kimlikleri, tanımlar, `T` atol 1e-9); bir adın hem parça kimliği hem alt montaj
  tanımı (ya da kök tanımı) olarak kullanılması.
- `walk(root) -> Iterator[tuple[str, Node, np.ndarray]]` — derinlik öncelikli, çocuk sırasıyla her düğüm
  için `(yol, düğüm, T_dünya)`. Yol kökten sonraki adların `/` ile birleşimidir (kök için `""`);
  ör. `"alt_a/vida_1"`. Kökün kendi `T`'si zincire dahildir.
- `world(root, path) -> np.ndarray` — yoldaki düğümün dünya dönüşümü. Bilinmeyen yol → `AssyError`.
- `flatten(root, fixed=()) -> Assembly` — her yaprak bir `Component(name=yol, part=parça kimliği,
  T=T_dünya, fixed=yol ∈ fixed)`, `walk` sırasıyla; `mates` boş, `name` = kök adı. `fixed` içinde bir
  yaprağa karşılık gelmeyen yol → `AssyError`.
- `apply(root, assy) -> Node` — yaprakların dünya dönüşümü `assy`'deki aynı adlı bileşenin `T`'si olacak
  şekilde yaprakların yerel `T`'si yeniden hesaplanmış **yeni** ağaç; alt montaj düğümlerinin `T`'si
  değişmez. `assy` bileşen adları yaprak yollarıyla birebir aynı değilse veya sonuçta aynı tanımlı iki alt
  montajın içeriği ayrışıyorsa (`validate` kuralı) → `AssyError`.

### `assy/bom.py`
```python
@dataclass(frozen=True)
class BomLine:
    item: str  # parça kimliği veya alt montaj tanımı
    kind: str  # "parca" | "montaj"
    qty: int
    unit_mass: float | None  # t; kütle verilmediyse None
    total_mass: float | None  # qty · unit_mass
```
- `unit_masses(parts: Mapping[str, Part], rho: float | Mapping[str, float]) -> dict[str, float]` —
  `m = ρ · part.volume`. `rho` sözlükse her parça kimliği için olmalı; eksik kimlik, `ρ ≤ 0` veya sonlu
  olmayan `ρ` → `AssyError`.
- `bom(root, unit_mass=None, flat=True) -> list[BomLine]` — `flat=True`: tüm yapraklar parça kimliğine
  göre (`kind="parca"`); `flat=False`: kökün doğrudan çocukları tanıma göre. Satırlar `walk` sırasında ilk
  görülme sırasıyla. `unit_mass` verilmişse ağaçtaki her parça kimliği için sonlu ve `> 0` olmalı, yoksa
  `AssyError`. `validate(root)` çağrılır.
- `total_mass(root, unit_mass) -> float` — `Σ q_p m_p`.
- `mass_center(root, parts, unit_mass) -> np.ndarray` — `x̄` (3,), dünya koordinatında. Ağaçtaki bir
  parça kimliği `parts`'ta yoksa `AssyError`.

### `fileio/step_montaj.py`
- `write_step(path, root: Node, parts: Mapping[str, Part]) -> None` — Teori'deki ürün / oluşum yapısıyla
  yazar. Kökün `T`'si birim değilse kökün doğrudan çocuklarına katlanır (`T(kök) · T(çocuk)`); dünya
  konumları korunur. `validate(root)` çağrılır; ağaçtaki bir parça kimliği `parts`'ta yoksa `AssyError`;
  `parts`'taki kullanılmayan parçalar yok sayılır. Yazma başarısızsa `GeometryError`.
- `read_step(path) -> tuple[Node, dict[str, Part]]` — kök tanımı kök düğüm (`T` = birim, `name` = kök
  ürün adı), alt montaj tanımları `ref`, parça ürün adları parça kimliği olur; `parts[kimlik]` o ürünün
  kendi koordinatındaki şeklidir (`Part.name` = kimlik).
  - Montaj olmayan tek gövdeli STEP (ör. `Part.to_step`): kök adı dosya adı (uzantısız), tek yaprak çocuk
    (ad = kimlik = ürün adı, `T` = birim). Birden çok serbest şekil: aynı kökün çocukları.
  - Oluşum adı boşsa tanım adı kullanılır; kardeşler arasında ad yinelenirse ikinciden başlayarak
    `"<ad>#2"`, `"<ad>#3"`… (dosya sırasıyla).
  - Dosya yok / okunamıyor → `GeometryError`; rijit olmayan konum (ölçek, ayna) → `AssyError`.

## Kabul kriterleri
- [ ] K1 `validate`: geçerli 3 seviyeli ağaç geçer; Arayüz'deki her hata durumu ayrı ayrı `AssyError` —
  `tests/assy/test_agac.py`
- [ ] K2 `walk` / `world`: 3 seviyeli, dönmeli ağaçta dünya dönüşümleri el hesabıyla (ör. Z ekseninde 90°
  + öteleme zinciri, kapalı formda nokta konumu) atol 1e-12; yol biçimi ve sırası; kökün `T`'si zincirde;
  bilinmeyen yol hata — `test_agac.py`
- [ ] K3 `flatten` / `apply`: bileşen adları = yaprak yolları, `T` = dünya dönüşümü; `apply(root,
  flatten(root))` ağacı değiştirmiyor (atol 1e-12); yaprağın dünya konumu değiştirilip `apply` edilince
  `world` yeni konumu veriyor ve kardeş / ebeveyn `T`'leri aynı kalıyor; SPEC 08 `solve` ile uçtan uca:
  kısıtlı düz montaj çözülüp `apply` edilince yaprak dünya konumları çözümle 1e-9 mm; ayrışan paylaşımlı
  tanım ve ad uyuşmazlığı hata — `test_agac.py`
- [ ] K4 Düz BOM: 2 alt montaj × (4 vida + 1 plaka) + 1 gövde → vida 8, plaka 2, gövde 1; ilk görülme
  sırası; `total_mass` = Σ q m (rel 1e-12); kütlesiz BOM'da kütleler `None` — `tests/assy/test_bom.py`
- [ ] K5 Üst seviye BOM: alt montaj satırı `qty = 2`, `kind = "montaj"`, birim kütlesi = 4 m_vida + m_plaka;
  kökteki parça satırı `kind = "parca"` — `test_bom.py`
- [ ] K6 `unit_masses` ve `mass_center`: blok `a×b×c`, ρ ile `m = ρabc` rel 1e-6 (`@pytest.mark.occt`,
  gerçek `Part`); sahte parça nesneleriyle (`volume`, `center_of_mass` öznitelikli) OCCT'siz: iki kütleli
  dönmüş montajda `x̄` el hesabıyla atol 1e-12; eksik kütle / ρ, `ρ ≤ 0`, eksik parça hata — `test_bom.py`
- [ ] K7 STEP gidiş-dönüş (`@pytest.mark.occt`): paylaşımlı alt montajlı, dönmeli 3 seviyeli ağaç
  `write_step → read_step` sonrası: yollar, düğüm adları, parça kimlikleri ve alt montaj tanımları aynı;
  her düğümün dünya dönüşümü atol 1e-9; parça hacimleri rel 1e-6; düz ve üst seviye BOM aynı; dosyadaki
  `PRODUCT` sayısı = farklı parça + farklı alt montaj tanımı + 1 (kök) — `tests/fileio/test_step_montaj.py`
- [ ] K8 STEP kenar durumları (`@pytest.mark.occt`): kökün `T`'si birim değilken dünya konumları korunuyor;
  `Part.to_step` ile yazılmış tek parça tek yapraklı kök olarak okunuyor; ağaçtaki parça `parts`'ta yoksa
  `AssyError`; olmayan dosya `GeometryError` — `test_step_montaj.py`
- [ ] Tüm testler yeşil (`pytest` 0 failed, bu SPEC'te 0 "uygulanmamış"), `ruff check .` ve
  `ruff format --check .` temiz

## Kapsam dışı
- Alt montajı kısıt çözümünde tek rijit cisim olarak tutmak (bu SPEC'te düzleştirme yapraklara kadar;
  ayrışan paylaşımlı tanım hata verir)
- Kısıtların (`Mate`) ağaçta saklanması ve STEP'e yazılması; STEP'te renk, katman, malzeme, PMI
- Girişim / çakışma — SPEC 09; montajdan CAM'e — SPEC 10
- Montajı ekrana çizme (`viz/`) — SPEC 15
- Başka CAD araçlarının dosyalarında birim dönüşümü (STEP'in mm olduğu varsayılır; OCCT okurken mm'ye çevirir)
