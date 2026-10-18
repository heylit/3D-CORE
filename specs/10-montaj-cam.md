# SPEC 10 — Montaj-CAM bağlantısı ve bağlama (fikstür) kütüphanesi (Dalga 5, H9)

> **Durum: ONAYLANDI** (kullanıcı, 2026-10-18 11:13 UTC, Dalga 5 toplu yazılı onay, önerilerle; A0 `Fixture.params` dahil).
> Metin kullanıcı onayı olmadan değişmez.

## Amaç
Parametrik **mengene**, **torna aynası** ve **pabuç** (bağlama pabucu) kütüphanesi; montajdaki bir parçayı
bağlama elemanlarıyla birlikte iş koordinatına (WCS) taşıyıp CAM kurulumuna (`Setup` + `Fixture` listesi)
çeviren köprü ve geri dönüşü; SPEC 05 freze simülasyonunda takımın (kesici, sap, tutucu) **şekilli bağlama
elemanına çarpmasını** bulan denetim. Bu adım bitince bir montajdan "bu parçayı bu mengeneyle işle" denince
ham malzeme, bağlama konumları ve simülasyondaki fikstür çarpışmaları el hesabıyla doğrulanmış olarak çıkıyor.

## Teori

### Çerçeveler
- Montajda (SPEC 07) her yaprağın dünya dönüşümü `T_w = T(n₀)·…·T(n_k)` (4x4, rijit).
- İş koordinatı (WCS) dünyada bir rijit poz `W` ile verilir (ya bir montaj düğümünün dünya dönüşümü ya da açık
  `Frame`). Bir yaprağın WCS'deki konumu `T_wcs = W⁻¹ · T_w`, `W⁻¹ = [[Rᵀ, −Rᵀt], [0, 1]]` (Craig, Bölüm 2.3).
  3 eksen frezede takım ekseni WCS +Z'dir; dönüşüm kısıtsızdır, ama ham malzeme WCS eksenlerine hizalı kutudur.
- `Frame` (SPEC 41 arayüzü, PR #60): `p_wcs = origin + R·p_yerel`. 4x4 ile ilişki `T = [[R, origin], [0, 1]]`.
- `cam/baglama.py` OCCT'siz kalır ve `assy` paketinin iç dosyalarını import etmez (CLAUDE.md bağımlılık kuralı):
  ağacı yalnız `assy.model.Node` üzerinden gezer (yol biçimi SPEC 07 `walk` ile aynı: kökten sonraki adlar `/` ile).

### İlkel cisimler ve kütüphane elemanları
Kütüphanedeki her eleman, **kendi yerel çerçevesinde** ilkel cisimlerin birleşimidir:
- Kutu: `Stock(xmin, ymin, zmin, xmax, ymax, zmax)` (yerel eksenlere hizalı).
- Silindir: `CylinderStock(D, zmin, zmax, d=0)` (yerel Z ekseni, `x = y = 0`).
- Her ilkelin yerel çerçeveye göre bir `Frame`'i vardır (`Primitive(shape, frame)`); elemanın kendisi `Fixture.frame`
  ile WCS'ye konur. Aynı ilkel listesi (1) `geometry/baglama_parca.py`'de OCCT katısına (birleşim), (2) analitik
  üst yüzey haritasına, (3) SPEC 14 / 22'nin anladığı zarf kutularına ve halkalarına çevrilir.

**Mengene** (`Vise`). Yerel çerçeve: orijin iki çenenin arasındaki açıklığın ortası, kızak (yatak) üst yüzeyinde;
çeneler yerel Y'ye dik (sıkma yönü Y). Ölçüler: çene genişliği `b`, çene kalınlığı `t`, çene yüksekliği `h_j`,
açıklık `w`, yatak yüksekliği `h_b`, yatak uzantısı `s` (hareketli çene arkası), paralel yüksekliği `p`, paralel
genişliği `w_p`.
| İlkel | x | y | z |
|---|---|---|---|
| Sabit çene | `[−b/2, b/2]` | `[−w/2 − t, −w/2]` | `[0, h_j]` |
| Hareketli çene | `[−b/2, b/2]` | `[w/2, w/2 + t]` | `[0, h_j]` |
| Yatak | `[−b/2, b/2]` | `[−w/2 − t, w/2 + t + s]` | `[−h_b, 0]` |
| Paraleller (`p > 0` ise iki adet) | `[−b/2, b/2]` | `[−w/2, −w/2 + w_p]` ve `[w/2 − w_p, w/2]` | `[0, p]` |

İlkeller yalnız yüzeyden değer; hacim `V = 2·b·t·h_j + b·(w + 2t + s)·h_b + 2·b·w_p·p` (paralel varsa).

`vise_for(stock, grip, axis)`: tutma yüksekliği `g` (çenenin stoğu tuttuğu boy). `axis="x"`: sıkma yönü WCS Y,
`w = ymax − ymin`, `R = I`; `axis="y"`: sıkma yönü WCS X, `w = xmax − xmin`, `R = R_z(90°)`. Paralel
`p = h_j − g` (stok tabanı `z = zmin` paralel üstünde, çene üstü `zmin + g`); `origin = (x_c, y_c, zmin − p)`,
`x_c, y_c` stok merkezinin. `p < 0` (çene yetmiyor) veya `g ≥ zmax − zmin` (çene stoğun üstüne çıkar, üst yüz
işlenemez) → `CamError`.

Sayısal örnek (testlerde): `Stock(0, 0, 0, 80, 50, 30)`, `g = 10`, `b = 100`, `t = 20`, `h_j = 15`, `h_b = 40`,
`s = 60`, `w_p = 6` → `p = 5`, `origin = (40, 25, −5)`; sabit çene WCS'de `[−10, 90] × [−20, 0] × [−5, 10]`,
hareketli çene `y ∈ [50, 70]`, yatak `y ∈ [−20, 130]`, `z ∈ [−45, −5]`; paraleller `y ∈ [0, 6]` ve `[44, 50]`,
`z ∈ [−5, 0]`; `V = 60000 + 600000 + 6000 = 666000 mm³`.

**Torna aynası** (`Chuck3`, üç çeneli). Yerel çerçeve: orijin iş mili ekseninde ayna alnında, +Z stoğa doğru.
Ölçüler: gövde çapı `D_b`, gövde boyu `L_b`, tutulan çap `d`, çene radyal yüksekliği `h`, çene boyu `L_j`, çene
genişliği `w_j`. Gövde: silindir `D_b`, `z ∈ [−L_b, 0]`. Çene `i` (`θ_i = 90°, 210°, 330°`): çene yerel
kutusu `x ∈ [d/2, d/2 + h]`, `y ∈ [−w_j/2, w_j/2]`, `z ∈ [0, L_j]`, `R_z(θ_i)` ile döndürülmüş.
Çeneler örtüşmesin diye `w_j < √3·d` (çene, 60° yarım açılı dilimin içinde kalır). Hacim
`V = π (D_b/2)² L_b + 3·h·w_j·L_j`.
- **Dönen zarf (SPEC 22 `Setup.fixtures` biçimi):** iş mili döndüğü için çeneler halka süpürür. Çene köşesinin en
  büyük yarıçapı `r_o = √((d/2 + h)² + (w_j/2)²)` (köşe, `d/2 + h`'den uzaktadır). Halkalar:
  `CylinderStock(D = 2 r_o, d = d, zmin = z_f, zmax = z_f + L_j)` ve gövde `CylinderStock(D_b, z_f − L_b, z_f)`;
  `z_f` alnın WCS Z'si.
- `chuck_for(stock: CylinderStock, grip)`: `d = stock.D`, `L_j = grip`, `origin = (0, 0, stock.zmin)`, `R = I`.
  `grip ≥ stock.length` → `CamError`.
- Örnek: `CylinderStock(40, −60, 0)`, `grip = 20`, `D_b = 160`, `L_b = 80`, `h = 25`, `w_j = 20` →
  `r_o = √2125 = 46.0977…`, çene halkası `D = 92.195…`, `d = 40`, `z ∈ [−60, −40]`; gövde `z ∈ [−140, −60]`.

**Pabuç** (`Clamp`, kol + cıvata + topuk). Yerel çerçeve: orijin kolun stoğa basan ucunun (burun) alt kenarında,
kol −X yönünde uzanır. Ölçüler: kol boyu `L_a`, genişliği `w_a`, kalınlığı `t_a`; cıvata çapı `d_b`, kol üstündeki
taşması `h_c`; topuk genişliği `w_h`, destek yüksekliği `H_s`.
| İlkel | x | y | z |
|---|---|---|---|
| Kol | `[−L_a, 0]` | `[−w_a/2, w_a/2]` | `[0, t_a]` |
| Topuk | `[−L_a, −L_a + w_h]` | `[−w_a/2, w_a/2]` | `[−H_s, 0]` |
| Cıvata (silindir, eksen `x = −L_a/2`) | yarıçap `d_b/2` | | `[−H_s, t_a + h_c]` |

Cıvata kolun içinden geçer: hacim `V = L_a w_a t_a + w_h w_a H_s + π (d_b/2)² (H_s + h_c)` (kolun içindeki
cıvata boyu `t_a` bir kez sayılır). `w_a ≥ d_b` ve `w_h + d_b/2 < L_a/2` olmalı.
`clamp_for(stock, side, at, overlap)`: burun stok üstünde (`z = zmax`), kenardan `o = overlap` içeride;
`H_s = zmax − zmin` (topuk ve cıvata tablaya, `z = zmin`'e iner).
| `side` | `R` | burun `origin` |
|---|---|---|
| `"x-"` | `I` | `(xmin + o, at, zmax)` |
| `"x+"` | `R_z(180°)` | `(xmax − o, at, zmax)` |
| `"y-"` | `R_z(90°)` | `(at, ymin + o, zmax)` |
| `"y+"` | `R_z(−90°)` | `(at, ymax − o, zmax)` |
`0 < o`, `o < L_a/2 − d_b/2` (cıvata stok dışında kalır), `o` stok boyunu aşmaz ve `at` kenarın içinde
(`w_a/2` payla) olmalı; aksi `CamError`.
Örnek: `Stock(0, 0, 0, 80, 50, 30)`, `side="y-"`, `at = 40`, `o = 8`, `L_a = 80`, `w_a = 20`, `t_a = 12`,
`d_b = 12`, `h_c = 15`, `w_h = 15` → kol WCS'de `[30, 50] × [−72, 8] × [30, 42]`, cıvata ekseni `(40, −32)`,
`z ∈ [0, 57]`, topuk `y ∈ [−72, −57]`, `z ∈ [0, 30]`; `V = 19200 + 9000 + 36π·45`.

### Bağlama denetimi (sıkma)
Bağlama elemanı stoğa değebilir (çene yan yüze, pabuç üst yüze, paralel alta) ama içine giremez:
- Kütüphane elemanında analitik: her ilkel ile stok kutusunun **iç kısımları** kesişiyorsa `CamError`.
  Kutu–kutu (her ilkel `R`'si `R_z(k·90°)` olan kutu, eksenlere hizalı): üç eksende de açık aralıklar örtüşür
  (örtüşme > `tol_l`, varsayılan 1e-9 mm). Z eksenli silindir–kutu: Z aralıkları açık örtüşür ve disk merkezinin
  dikdörtgene uzaklığı `< r − tol_l`. Döndürülmüş (90°'nin katı olmayan) kutu: kesişim 2B ayırma ekseni testiyle
  (dört kenar normali) aynı kuralla.
- Kütüphane dışı (`kind = "ozel"`) eleman: `Part.common` (SPEC 09 arayüzü) ile WCS'de kesişim hacmi `> tol_v` ise
  `CamError` (`@pytest.mark.occt`).

### Bağlama üst yüzey haritası (temkinli)
Takım (3 eksen) ekseni düşey ve yukarı doğru sonsuza uzanan bir dönel cisimdir: bir hücre sütununda takım
`[e(q), +∞)` aralığını kaplar. Bağlamanın o sütundaki herhangi bir parçası `[l, u]` takıma ancak `u > e(q)` ise
değer; yani **yalnız bağlamanın üst yüzeyi** `z_F(q) = max u` önemlidir (pabuç kolunun altındaki boşluk takımı
kurtarmaz: takım oraya ancak kolu delerek girer). Bu yüzden 3 eksende yükseklik haritası kesindir; hata yalnız
ızgaradan gelir. Hiçbir çarpışmayı kaçırmamak için iki taraf da temkinli alınır (SPEC 14'teki `h/2` şişirmesinin
benzeri):
- **Hücre değeri:** `z_F(c) = max{ z_üst(p) : p ∈ hücre c'nin kapalı dikdörtgeni }` (bağlama hücreye değmiyorsa `−∞`).
  - Kutu (yerel Z'si WCS Z'ye paralel, `R = R_z(φ)`): ayak izi döndürülmüş dikdörtgen, üstü düz `z_max`; hücre
    dikdörtgeniyle kapalı kesişim varsa (2B ayırma ekseni testi) `z_max`.
  - Z eksenli silindir: ayak izi disk; hücre dikdörtgeninin disk merkezine uzaklığı `≤ r` ise `z_max`.
  - Yerel Z'si WCS Z'ye paralel olmayan ilkel → `CamError` (ağ yolunu kullan).
  - Üçgen ağ (`kind = "ozel"`, `Part.mesh`): her üçgen, XY izdüşümündeki en uzun kenarı `≤ Δ_min = min(dx, dy)`
    olana dek orta noktalardan dörde bölünür; her alt üçgenin XY sınır kutusunun değdiği hücrelere alt üçgenin en
    büyük Z'si yazılır, hücre başına en büyük. Sonuç her hücrede kesin değerden büyük ya da eşittir; fazlalık,
    hücreyi XY'de en çok `√2·Δ_min` şişirmekle sınırlıdır. Eksenlere hizalı kutu ağında, hiçbir yüz bir hücre
    sınırına 1e-6 mm'den yakın değilse sonuç ilkel haritasıyla birebir aynıdır.
- **Takım tarafı:** hücre merkezleri arası en büyük uzaklık `δ = √(dx² + dy²)/2`. Takımın kesici profili
  `h_δ(d) = h(max(0, d − δ))` (`d ≤ R + δ`) ve gövde basamakları `ρ_j + δ` ile şişirilir (`h`, `body_steps`:
  SPEC 05). Gerçek takımın bir noktası `(x, y, z)`'de bağlamanın altındaysa, o noktanın hücresinin merkezinde
  şişirilmiş takım `≤ z`'dedir ve hücre değeri `≥ z_F(x, y)`'dir; çarpışma kaçmaz.
- **Bilinen sınır (yanlış alarm bandı):** bağlamadan yatay uzaklığı `≤ R + 2δ` olan yol çarpışma verebilir
  (`2δ = √2·Δ` ızgara adımında). `> R + 2δ` uzaktan geçen yol kesin kayıtsızdır; `< R` (gerçek çarpışma) kesin
  kayıtlıdır.

### Fikstür çarpışması (SPEC 05 sonucuna ek denetim)
SPEC 05 simülasyonu değişmez; bu SPEC onun `SimResult.steps` adımlarını (bağlantı adımları dahil, aynı `k`) okur ve
her bağlama elemanının kendi ızgarasında ayrı denetim yapar:
- Izgara: elemanın WCS XY sınır kutusu, `ZMap` ile aynı kural (`nx = ⌈(xmax − xmin)/Δ⌉`, `dx = (xmax − xmin)/nx`).
- Her adım (yaylar SPEC 05 ile aynı kiriş kuralıyla, `n = ⌈|Δθ| / (2·acos(1 − ε_yay/r))⌉`) için takımın en alçak
  yüzeyi `e(q) = min( e_kesici(q), min_j [H_j + e_düz(q; ρ_j + δ)] )`; `e_kesici` şişirilmiş profille SPEC 05
  süpürme zarfı, `e_düz` düz takım zarfı. Bağlama durağandır ve kaldırılmaz; adım içinde ilerleme önemsizdir
  (alt adım yok), sonuç kesindir.
- Kayıt: `z_F(q) − e(q) > tol` olan hücre varsa; `depth` en büyük fark, `at = (x_c, y_c, e)` o hücrenin merkezi ve
  takımın oradaki yüksekliği. `part`: o hücrede `e`'yi veren bölüm (`"kesici"`, `"sap"`, `"tutucu"`; eşitlikte
  kesici önce). Aynı `(fixture, k)` için tek kayıt (en büyük `depth`). `G0` dahil her adım denetlenir.

### Montajdan CAM'e
`from_assembly(root, parts, workpiece, wcs, fixtures)`:
1. Yaprak yollarının dünya dönüşümleri `T_w` (`Node` zinciri). `W` = `wcs` bir yol ise o düğümün dünya
   dönüşümü (yaprak olabilir), `Frame` ise doğrudan.
2. İş parçası WCS'de: `T_p = W⁻¹ T_w(workpiece)`. Ham malzeme: parçanın yerel `bbox`'ının 8 köşesi `T_p` ile
   taşınır, eksen başına min / max, her eksende `margin` eklenir (SPEC 09 `world_aabb` ile aynı kural; dönmüş
   parçada temkinli).
3. Her bağlama yaprağı `f` → `Fixture(name = yol, part_ref = yaprak.part, frame = Frame(W⁻¹ T_w(f)), kind = "ozel")`.
   Yaprak kütüphaneden geldiyse (`parts[part]`'ı bilinmez) kullanıcı `kinds={yol: Fixture}` ile kütüphane
   tanımını verebilir; o zaman `kind` ve `params` o tanımdan, `frame` montajdan alınır.
4. `Setup(name, Wcs(code, origin), stock, fixtures = zarf kutuları)`; zarf, her bağlamanın WCS sınır kutusudur
   (kütüphanede ilkel başına), böylece SPEC 14 `clearance_height` / `check_setup` bugünkü haliyle çalışır.
Geri dönüş `to_assembly(job)`: kök (`T = I`, dünya = WCS) altında `is_parcasi` yaprağı (`T_p`) ve her bağlama
için yaprak (`Fixture.frame`); `from_assembly(to_assembly(job), …)` aynı dönüşümleri verir (atol 1e-12).

## Dosyalar
- Yeni: `cam/baglama.py` (kütüphane, yerleştirme, sıkma denetimi, üst yüzey haritası, fikstür çarpışması,
  montaj köprüsü; saf Python + numpy), `geometry/baglama_parca.py` (ilkel listesinden OCCT katısı),
  `tests/cam/test_baglama_*.py`, `tests/geometry/test_baglama_parca.py`, `durum/10-montaj-cam.md`.
- Ön koşul arayüzler (bu SPEC'ten önce, kendi PR'larında): `cam/model.py` → `Fixture` (A0, "CAM model arayüzü";
  beklenen biçim aşağıda), `Frame` (PR #60); `geometry/part.py` → `Part.moved`, `Part.common` (PR #53).
- Kullanılan (değişmeden): `cam.sim` (SPEC 05: `SimResult`, `sweep_envelope`, `tool_height`, `body_steps`),
  `cam.setups` (SPEC 14, PR #27: yalnız K12 testinde), `assy.model.Node` (SPEC 07), `Part.mesh` / `bbox` (SPEC 02).
- Dokunulmayacak: tüm `*/model.py`, `cam/sim/**`, `cam/setups.py`, `assy/**`, `geometry/part.py`, `pyproject.toml`,
  `.github/`, `CLAUDE.md`, `BASLANGIC.md`, `DURUM.md`, `docs/yol-haritasi.md`. Yeni bağımlılık yok.

`geometry/baglama_parca.py` `cam`'i import etmez: ilkelleri düz sözlük olarak alır (`Primitive.to_dict()` biçimi).
OCCT gerektiren testler `@pytest.mark.occt`. Hatalar: `cam/baglama.py` → `cam.model.CamError` (ağaç yapısı
hataları dahil, `AssyError` değil: köprü CAM tarafındadır); `geometry/baglama_parca.py` → `GeometryError`.
Hiçbir fonksiyon girdisini değiştirmez.

## Arayüz

### Ön koşul: `cam/model.py` → `Fixture` (A0 önerisine ek istek)
```python
@dataclass(frozen=True)
class Fixture:
    name: str  # [A-Za-z0-9 _/-]{1,64}; montaj yolu ad olabilsin diye '/' ve 64 karakter
    part_ref: str  # şekil anahtarı (Part sözlüğü kimliği), boş olamaz
    frame: Frame = Frame((0, 0, 0), ((1, 0, 0), (0, 1, 0), (0, 0, 1)))  # yerel → WCS
    kind: str = "ozel"  # "mengene" | "ayna" | "pabuc" | "ozel"
    params: tuple[tuple[str, float], ...] = ()  # kütüphane ölçüleri (ad, değer), ada göre sıralı; sonlu

    # to_dict: {"name", "part_ref", "frame": Frame.to_dict(), "kind", "params": {ad: değer}}
    def to_dict(self) -> dict: ...
    @classmethod
    def from_dict(cls, d: dict) -> Fixture: ...  # "frame", "kind", "params" isteğe bağlı
```
`params` için anahtar doğrulaması arayüzde yok (10'un `from_fixture`'ı yapar); arayüz yalnız sonluluğu ve tekil adı
denetler. `Setup`'a alan eklenmez (A0 ile aynı); fonksiyonlar `fixtures: list[Fixture]` parametresi alır.

### `cam/baglama.py`
```python
@dataclass(frozen=True)
class Primitive:
    shape: Stock | CylinderStock  # yerel çerçevede
    frame: Frame = <birim>
    def to_dict(self) -> dict: ...  # {"shape": shape.to_dict(), "frame": frame.to_dict()}
    @property
    def volume(self) -> float: ...

@dataclass(frozen=True)
class Vise:  # tüm ölçüler mm, > 0 (parallel ≥ 0); w_p < w/2
    jaw_width: float; jaw_thickness: float; jaw_height: float; opening: float
    bed_height: float = 40.0; bed_extra: float = 60.0; parallel: float = 0.0; parallel_width: float = 6.0
    def primitives(self) -> list[Primitive]: ...  # Teori tablosu sırasıyla (sabit, hareketli, yatak, paraleller)

@dataclass(frozen=True)
class Chuck3:
    grip_d: float; jaw_length: float; body_d: float = 160.0; body_length: float = 80.0
    jaw_height: float = 25.0; jaw_width: float = 20.0
    def primitives(self) -> list[Primitive]: ...  # gövde, çene 90°, 210°, 330°
    def rings(self, frame: Frame) -> list[CylinderStock]: ...  # [çene halkası, gövde]; frame R = I olmalı

@dataclass(frozen=True)
class Clamp:
    support_height: float; arm_length: float = 80.0; arm_width: float = 20.0; arm_thickness: float = 12.0
    bolt_d: float = 12.0; bolt_above: float = 15.0; heel_width: float = 15.0
    def primitives(self) -> list[Primitive]: ...  # kol, topuk, cıvata
```
Her sınıfta `params() -> dict[str, float]` ve `from_params(d)`; ölçü kuralı bozuksa `CamError`.
- `vise_for(stock: Stock, grip: float, axis: str = "x", **olculer) -> tuple[Vise, Frame]`
- `chuck_for(stock: CylinderStock, grip: float, **olculer) -> tuple[Chuck3, Frame]`
- `clamp_for(stock: Stock, side: str, at: float, overlap: float, **olculer) -> tuple[Clamp, Frame]`
- `make_fixture(name: str, item: Vise | Chuck3 | Clamp, frame: Frame) -> Fixture` — `kind` sınıftan, `params`
  `item.params()`'tan, `part_ref = name`.
- `from_fixture(fx: Fixture) -> Vise | Chuck3 | Clamp` — `kind = "ozel"`, eksik / fazla / geçersiz ölçü → `CamError`.
- `primitives_wcs(fx: Fixture) -> list[Primitive]` — ilkeller, çerçeveleri `fx.frame ∘ ilkel.frame` (WCS'de).
- `envelope(fx: Fixture, parts: Mapping[str, Part] | None = None) -> list[Stock]` — WCS sınır kutuları:
  kütüphanede ilkel başına, `"ozel"`de `parts[fx.part_ref].bbox()` köşeleri `frame` ile taşınarak tek kutu.
- `check_clamping(stock: Stock | CylinderStock, fixtures: Sequence[Fixture], parts=None, tol_l: float = 1e-9,
  tol_v: float = 1e-6) -> None` — Teori'deki sıkma denetimi; ilk ihlalde `CamError` (mesajda bağlama adı ve ilkel).
  `CylinderStock` ile yalnız `Chuck3`: çene iç yüzü `d/2`'de stoğa değer, `grip_d ≠ stock.D` (1e-9) → `CamError`.
- `fixture_top(fixtures, parts=None) -> float` — tüm bağlamaların en büyük WCS Z'si.
- `@dataclass FixtureMap(fixture: str, x0, y0, dx, dy, nx, ny, top: np.ndarray)` — `top` şekli `(ny, nx)`,
  değmeyen hücre `-inf`; `centers()`.
- `primitive_topmap(prims: Sequence[Primitive], grid: FixtureMap) -> np.ndarray` (WCS ilkelleri)
- `mesh_topmap(V: np.ndarray, F: np.ndarray, frame: Frame, grid: FixtureMap) -> np.ndarray` (yerel ağ + çerçeve)
- `fixture_map(fx: Fixture, cell: float, parts=None, mesh_tol: float = 0.01, max_cells: int = 4_000_000) -> FixtureMap`
  — `cell ≤ 0` / sonsuz, `nx·ny > max_cells`, `"ozel"` ve `parts` yok / kimlik yok → `CamError`.
- `@dataclass(frozen=True) FixtureCollision(fixture: str, k: int, op: int, part: str, at: tuple[float, float, float],
  depth: float)` — `part ∈ {"kesici", "sap", "tutucu"}`.
- `fixture_collisions(ops: list[Toolpath | DrillOp], result: SimResult, maps: Sequence[FixtureMap],
  arc_tol: float = 1e-3, tol: float = 1e-6) -> list[FixtureCollision]` — `(k, fixture)` sırasıyla.
  `result.steps[i].op` `ops` dizinine uymuyorsa → `CamError`.
- `@dataclass SetupSim(sim: SimResult, fixture_collisions: list[FixtureCollision], maps: list[FixtureMap])`
- `simulate_setup(ops, stock: Stock, fixtures: Sequence[Fixture], parts=None, cell: float = 1.0,
  fixture_cell: float | None = None, **sim_kwargs) -> SetupSim` — `simulate(ops, stock, cell, **sim_kwargs)`
  (SPEC 05, değişmeden), sonra `fixture_map` (`fixture_cell` yoksa `cell`) ve `fixture_collisions`
  (`arc_tol`, `tol` aynı değerlerle). Fikstür adları tekil olmalı.
- `@dataclass AssemblySetup(setup: Setup, workpiece: str, part: str, T_part: np.ndarray, fixtures: list[Fixture])`
- `from_assembly(root: Node, parts: Mapping[str, Part], workpiece: str, wcs: str | Frame,
  fixtures: Sequence[str], name: str = "baglama", code: str = "G54", origin=(0.0, 0.0, 0.0),
  margin: float | tuple[float, float, float] = 0.0, kinds: Mapping[str, Fixture] | None = None) -> AssemblySetup`
  — `CamError`: bilinmeyen yol; `workpiece` veya bir bağlama yolu yaprak değil; `workpiece` bağlama listesinde;
  yinelenen yol; `parts`'ta olmayan parça kimliği; `margin < 0`; `kinds` anahtarı bağlama listesinde değil.
- `to_assembly(job: AssemblySetup, name: str = "baglama") -> Node` — Teori'deki gibi; yaprak adları `/` içermesin
  diye yoldaki `/` → `__`.

### `geometry/baglama_parca.py`
- `primitives_part(prims: Sequence[dict], name: str) -> Part` — her sözlük `Primitive.to_dict()` biçiminde
  (`shape.type ∈ {"kutu", "silindir"}`); katılar `frame` ile konup birleştirilir (`fuse`), `Part.name = name`.
  Boş liste, bilinmeyen tür, eksik alan, rijit olmayan `R` → `GeometryError`. Sonuç geçersiz katıysa `GeometryError`.

## Kabul kriterleri
Testlerde uydurma geometri; beklenen değerin kaynağı test yorumunda. Tolerans aksi yazılmadıkça mutlak 1e-9 mm.
- [ ] K1 Ölçü doğrulama ve gidiş-dönüş: üç sınıfta her ölçü kuralı (`≤ 0`, `nan`, `w_j ≥ √3·d`, `w_a < d_b`,
  `w_h + d_b/2 ≥ L_a/2`, `w_p ≥ w/2`) `CamError`; `from_params(params())` eşit; `make_fixture` → `from_fixture`
  aynı eleman; `Fixture.to_dict` → `from_dict` → `from_fixture` aynı; `"ozel"` → `CamError` — `tests/cam/test_baglama_kutuphane.py`
- [ ] K2 Mengene: Teori örneğinde `vise_for` ilkelleri WCS'de tablo değerleri; `axis="y"` aynı stokta X/Y yer
  değiştirmiş değerler; hacim `666000` (rel 1e-12, ilkel hacimleri toplamı); `p < 0` ve `g ≥ H` → `CamError` —
  `test_baglama_kutuphane.py`
- [ ] K3 Ayna: Teori örneğinde `rings` halkaları (`D = 2√2125`, `d = 40`, z aralıkları); çene kutularının WCS
  ağırlık merkezleri `R_z(θ_i)·(d/2 + h/2, 0, L_j/2) + origin`; hacim formülü; `grip ≥ L` → `CamError` —
  `test_baglama_kutuphane.py`
- [ ] K4 Pabuç: Teori örneğinde dört `side` için burun, kol, cıvata ekseni, topuk WCS değerleri; hacim formülü;
  `o ≤ 0`, cıvatayı stoğa sokan `o`, kenar dışı `at` → `CamError` — `test_baglama_kutuphane.py`
- [ ] K5 Sıkma denetimi: K2–K4 yerleşimleri (değen yüzler) geçer; mengene çerçevesi 1 mm içeri kaydırılınca,
  pabuç `origin` z'si 1 mm aşağı inince, cıvata stoğa girecek şekilde elle konunca → `CamError` (mesajda bağlama
  adı); `CylinderStock` + `Chuck3` `grip_d` uyuşmazlığı → `CamError` — `tests/cam/test_baglama_sikma.py`
- [ ] K6 İlkel haritası: eksenlere hizalı kutu kapalı kesişim kuralı (sınıra tam değen hücre dahil, 1e-9 dışarıdaki
  hariç); `R_z(30°)` kutu ve Z silindiri için her hücre, testte bağımsız yazılmış ayırma ekseni / disk–dikdörtgen
  uzaklığı hesabıyla birebir; eğik ilkel → `CamError` — `tests/cam/test_baglama_harita.py`
- [ ] K7 Ağ haritası: elle kurulmuş 12 üçgenli kutu ağı (yüzler hücre sınırlarından > 1e-6 uzak) ilkel haritasıyla
  `array_equal`; eğik kama ağında her hücre kesin hücre-en-büyük değerinden `≥` ve `√2·Δ` şişirilmiş hücrenin kesin
  en büyüğünden `≤` (kesin değerler testte düzlem denkleminden) — `test_baglama_harita.py`
- [ ] K8 Kesici çarpışması (Teori mengenesi, düz `D = 10`, `Δ = 0.5`): sabit çene üstünden (`y = −10`) `z = 5`'te
  geçen G1 → tek kayıt, `part = "kesici"`, `depth = 5`, doğru `k` ve `fixture`; `z = 10.5`'te → kayıt yok; çene
  yüzüne paralel, takım merkezi çeneden `R + √2·Δ + 0.01` uzakta → yok, `R − 0.5` uzakta → kayıt — `tests/cam/test_baglama_carpisma.py`
- [ ] K9 Gövde: `L_f = 10`, `shank_d = 16` takım çene yanından kesici dışarıda (`R + √2·Δ + 0.01`), sap içeride,
  `z + L_f < 10` → `part = "sap"`, `depth = 10 − (z + L_f)`; silindir tutuculu (`stickout = s`) takımda tutucu
  çeneye biniyor → `part = "tutucu"`, `depth = 10 − (z + s)`; tutucusuz aynı yol → kayıt yok — `test_baglama_carpisma.py`
- [ ] K10 Pabuç ve bağlantılar: Teori pabucunda burnun altından `z = zmax − 1`'de geçen yüz alma pasosu →
  `depth = t_a + 1`; burna `R + √2·Δ + 1` kala duran paso → yok; SPEC 05'in eklediği bağlantı `G0`'ı cıvatadan
  geçiyor → kayıt o bağlantı adımının `k`'sıyla; cıvata çevresinde tam daire G2 (yarıçap `r_y`):
  `r_y − R > d_b/2 + √2·Δ + ε_yay` → yok, `r_y − R < d_b/2 − 0.5` → kayıt — `test_baglama_carpisma.py`
- [ ] K11 `simulate_setup`: `sim` alanı aynı girdili `simulate` sonucuyla aynı (son harita `array_equal`, süreler,
  çarpışmalar); iki bağlamalı kurulumda kayıtlar `(k, fixture)` sırasıyla; yinelenen fikstür adı, uyuşmayan
  `ops` → `CamError` — `test_baglama_carpisma.py`
- [ ] K12 SPEC 14 ve 22 uyumu: `envelope` kutuları ilkel sınır kutuları; `Setup(fixtures = zarf)` ile
  `clearance_height` = en yüksek bağlama + 5; çene zarfına giren yol `check_setup`'ta `CamError`; `rings`
  SPEC 22 alan biçiminde (`CylinderStock`, `d` = tutulan çap) — `tests/cam/test_baglama_kurulum.py`
- [ ] K13 Montaj köprüsü (sahte parçalar, OCCT'siz: `bbox` ve `name` öznitelikli): iki seviyeli ağaçta iş parçası,
  mengene ve iki pabuç; alt montaj `R_z(90°)` + öteleme; `wcs` düğüm yolu ve `Frame` ile: her `Fixture.frame`
  `W⁻¹ T_w` (1e-12), ham malzeme döndürülmüş köşe kutusu + `margin`; `kinds` ile mengene `kind`/`params`'ı;
  `to_assembly` → `from_assembly` gidiş-dönüş 1e-12; Arayüz'deki her `CamError` durumu — `tests/cam/test_baglama_montaj.py`
- [ ] K14 OCCT (`@pytest.mark.occt`): `primitives_part` hacmi mengene `666000`, ayna ve pabuç formülleri rel 1e-9,
  `bbox` ilkel kutularının birleşimi; mengene `Part.mesh` ağı + `mesh_topmap` hücre sınırlarına hizasız ızgarada
  ilkel haritasıyla birebir; `"ozel"` fikstür olarak mengene parçası: `check_clamping` `Part.common` ile değen
  stokta geçer, 1 mm içeri kaydırılınca `CamError`; geçersiz sözlükler `GeometryError` — `tests/geometry/test_baglama_parca.py`
- [ ] K15 Hatalar: `fixture_map` (`cell`, `max_cells`, eksik `parts`), `fixture_collisions` (`arc_tol`, `tol ≤ 0`),
  `vise_for` `axis`, `clamp_for` `side` bilinmeyen → `CamError` — `test_baglama_harita.py`, `test_baglama_carpisma.py`
- [ ] Tüm testler yeşil (`pytest` 0 failed, bu SPEC'te 0 "uygulanmamış"), `ruff check .` ve `ruff format --check .`
  temiz; 10 s'den uzun testler `@pytest.mark.slow`

## Kapsam dışı
- Bağlama kuvveti, çene sıkma momenti, kesme kuvvetinde parçanın kayması / sehimi (H5 / analiz modülü).
- 4–5 eksende fikstür ve tezgâh gövdesi çarpışması: SPEC 44 (fikstürleri bu SPEC'in `envelope` / `Fixture`'ından alır).
- Torna simülasyonunun kendisi (SPEC 22); burada yalnız aynanın parametrik şekli ve `rings` zarfı.
- Dört çeneli ayna, punta, yumuşak (işlenmiş) çene, vakum tabla, modüler fikstür sistemleri, T kanallı tabla.
- Bağlamayı otomatik seçme / yerleştirme (hangi kenara pabuç?): SPEC 29'un sonraki eki; burada yerleşim elle verilir.
- Montaj ağacında bağlamaların kısıtla (`Mate`) konması; burada dönüşümler ağaçtan okunur.
- Tezgah ekranında gösterme (SPEC 24 / 47); STEP'e yazma SPEC 07 `write_step` ile `to_assembly` sonucundan yapılabilir.
