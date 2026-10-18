# SPEC 17 — Kısıtlı 2D eskiz (kroki) ve çözücü

> **Durum: TASLAK** (kullanıcı onayı bekliyor). Onaylanmadan kod, test ve arayüz PR'ı açılmaz.
> Karar (kullanıcı, 2026-10-18 09:28 UTC, "Eskiz ve modelleme ekle"): kısıtlı 2D eskiz çözücüsü ve Tezgah'ta
> eskiz → ekstrüzyon modelleme için SPEC'ler yazılır, Dalga 3'e girer. Bu SPEC çözücüdür; Tezgah tarafı SPEC 26.

## Amaç
Bir düzlem üzerinde nokta, çizgi, yay ve daireden oluşan bir eskizi; yatay, dik, teğet, eş, mesafe, açı gibi
kısıtları sağlayacak şekilde çözen, **her öğenin kalan serbestliğini ve yönünü** söyleyen, çelişkiyi
**hangi kısıtların çeliştiğiyle** birlikte bildiren, sürüklenen noktayı kısıtları bozmadan izleyen ve kapalı
döngülerden ekstrüzyona hazır bölgeler çıkaran saf numpy paketi (`sketch/`).

## Neden ayrı bir paket
Eskiz CAM'den, montajdan ve katı çekirdekten bağımsız bir matematik problemidir: bilinmeyenler düzlemdeki
nokta koordinatları ve daire yarıçaplarıdır. `sketch/` OCCT'siz, numpy ile test edilir (OCCT işareti yok).
SPEC 26 (Tezgah modelleme) ve ileride SPEC 18 (özellik ağacı) bunu `sketch/model.py` üzerinden kullanır.
Yöntem SPEC 08 ile aynıdır (Gauss–Newton, en küçük normlu adım, rank ile serbestlik sayımı), ama
paket kuralı gereği `assy/solver.py`'yi import etmez; kod kendi içinde yazılır. Bu bir öğrenme projesi:
iki çözücü yan yana okunabilir.

## Teori

### Bilinmeyenler
- Sabit olmayan her nokta için `(x, y)`; `Point.fixed = True` olan noktalar bilinmeyen değildir.
- Her daire için yarıçap `r`.
- Yayın yarıçapı ayrı bilinmeyen değildir: yay `merkez c`, `başlangıç s`, `bitiş e` noktalarıyla tanımlıdır
  (s'den e'ye saat yönünün tersine, CCW). Her yay çözücüye kendiliğinden bir satır ekler: `|s − c| − |e − c| = 0`.
  Yayın yarıçapı `r = |s − c|`.

Öğe başına serbestlik: nokta 2, çizgi 4 (iki nokta), daire 3 (merkez + r), yay 5 (üç nokta − 1).
Çizgiler ve yaylar nokta kimliklerine başvurur; iki çizginin aynı noktayı paylaşması kısıt gerektirmeden
uçlarını birleştirir.

### Kısıt artıkları
Gösterim: çizgi `ℓ = (p0, p1)`, `d = p1 − p0`, `|d| > 0`; `×` 2D çapraz çarpım `a × b = a_x b_y − a_y b_x`;
daire / yay için merkez `c`, yarıçap `r`. Değerler `Constraint.value` (mm veya derece).

| Tür | Referanslar | Artık `r` | Satır |
|---|---|---|---|
| COINCIDENT | nokta, nokta | `q − p` | 2 |
| POINT_ON_LINE | nokta, çizgi | `d × (q − p0) / |d|` (sonsuz doğru) | 1 |
| POINT_ON_CIRCLE | nokta, daire/yay | `|q − c| − r` | 1 |
| MIDPOINT | nokta, çizgi | `q − (p0 + p1)/2` | 2 |
| HORIZONTAL | çizgi | `d_y` | 1 |
| HORIZONTAL | nokta, nokta | `q_y − p_y` | 1 |
| VERTICAL | çizgi / nokta, nokta | `d_x` / `q_x − p_x` | 1 |
| PARALLEL | çizgi, çizgi | `L · (d_a × d_b) / (|d_a||d_b|)` | 1 |
| PERPENDICULAR | çizgi, çizgi | `L · (d_a · d_b) / (|d_a||d_b|)` | 1 |
| ANGLE | çizgi, çizgi, θ | `L · wrap(atan2(d_a × d_b, d_a · d_b) − θ)` | 1 |
| EQUAL | çizgi, çizgi | `|d_a| − |d_b|` | 1 |
| EQUAL | daire/yay, daire/yay | `r_a − r_b` | 1 |
| LENGTH | çizgi, `L₀ > 0` | `|d| − L₀` | 1 |
| DISTANCE | nokta, nokta, `D > 0` | `|q − p| − D` | 1 |
| DISTANCE | nokta, çizgi, `D` (işaretli) | `d × (q − p0) / |d| − D` | 1 |
| HDISTANCE | nokta, nokta, `D` (işaretli) | `(q − p)_x − D` | 1 |
| VDISTANCE | nokta, nokta, `D` (işaretli) | `(q − p)_y − D` | 1 |
| RADIUS | daire/yay, `R > 0` | `r − R` | 1 |
| DIAMETER | daire/yay, `D > 0` | `2r − D` | 1 |
| TANGENT | çizgi, daire/yay | `d × (c − p0) / |d| − σ r` | 1 |
| TANGENT | daire/yay, daire/yay, dış | `|c_b − c_a| − (r_a + r_b)` | 1 |
| TANGENT | daire/yay, daire/yay, iç | `|c_b − c_a| − σ (r_a − r_b)` | 1 |
| SYMMETRIC | nokta p, nokta q, çizgi | `d × (m − p0)/|d|` ; `(q − p) · d / |d|`, `m = (p + q)/2` | 2 |

**İşaret ve dal kuralları (taslak, onaya açık):**
- `wrap(φ)` açıyı `(−π, π]` aralığına indirger. ANGLE `θ` işaretlidir: `a` çizgisinden `b`'ye CCW pozitif.
  `atan2` biçimi her açıda türevlidir; bu yüzden SPEC 08'deki gibi `θ = 0` / `180` için ayrı artık gerekmez.
- PARALLEL `sin φ = 0`, PERPENDICULAR `cos φ = 0` kullanır: ikisi de kökte türevlidir ve yönü serbest bırakır
  (paralelde aynı ya da zıt yön, dikte ±90°).
- DISTANCE nokta–nokta `|q − p|` sıfırda türevsizdir: `D > 0` zorunlu, `D = 0` → `SketchError` ("COINCIDENT kullanın").
  Nokta–çizgi mesafesi işaretli ve her yerde türevli: pozitif = çizgi yönünün solu, `D = 0` serbest.
- TANGENT'te `σ ∈ {+1, −1}` dalı seçer ve kısıtın `side` alanında **saklanır**. `side = 0` ile eklenen kısıtta
  çözücü `σ`'yı ilk konumdan belirler (çizgi–daire: merkezin çizginin hangi yanında olduğu; iç teğet:
  `sign(r_a − r_b)`; sıfırsa +1) ve sonuçta döndürür. Böylece sürükleme sırasında çözüm dal değiştirmez.
  İç teğette başlangıçta `|c_b − c_a| < 1e-9` ise → `SketchError` (dal belirsiz).
- Teğet nokta yayın açıklığında olmak zorunda değildir (sonsuz doğru, tam çember). Uçta teğet geçiş
  istenirse ayrıca COINCIDENT yazılır; bu CAD'deki alışılmış kullanımdır.

### Satır ölçeği
Yön satırları (PARALLEL, PERPENDICULAR, ANGLE) birimsizdir; uzunluk satırlarıyla aynı toleransa girsin diye
`L` ile çarpılır: `L = max(ilk konumdaki noktaların sınır kutusu köşegeni, 1 mm)`, çözüm boyunca sabit.
SPEC 08'in ölçekli artıkları (PR #15) ile aynı yaklaşım. `tol` bu yüzden her satırda mm'dir.

### Çözüm
Tüm satırlar tek `r(x)` vektöründe, `J = ∂r/∂x` analitik. SPEC 08 ile aynı:
```
δx = −J⁺ r            (np.linalg.lstsq, en küçük normlu adım)
x ← x + α δx          (α = 1, ½, ¼ ... |r| azalana kadar, en az 2⁻¹⁰)
```
Durma: `max|r| ≤ tol` (varsayılan `1e-10` mm). `max_iter` (50) dolarsa ya da `‖Jᵀ r‖ ≤ 1e-14·L` ve
`max|r| > tol` ise (durağan nokta) → çelişki. En küçük normlu adım eksik tanımlı eskizi **ilk çizimden en az
hareketle** düzeltir: kullanıcının çizdiği şekil, kısıtların izin verdiği ölçüde yerinde kalır.

### Serbestlik derecesi ve öğe başına serbestlik
`DOF = n_bilinmeyen − rank(J)`, rank SPEC 08'deki gibi `σ_i > 1e-8 σ_max` (J boşsa 0). Sayım çözülmüş konumda.

Öğe başına: `N`, `J`'nin sıfır uzayının birimdik tabanı (SVD'den, `σ ≤` eşik sütunları; `J` boşsa birim matris).
Bir nokta için `S_p`, `x`'ten o noktanın iki koordinatını seçen matris olsun.
- Noktanın serbestliği `k_p = rank(S_p N)` ∈ {0, 1, 2} (eşik `1e-8`, `N` birimdik olduğu için mutlak).
  `k_p = 1` ise noktanın hareket edebildiği **birim yön** `S_p N`'nin ilk sol tekil vektörüdür (işareti
  `x` bileşeni ≥ 0 olacak şekilde sabitlenir).
- Çizgi / yay: uç noktalarının (ve yayda merkezin) satırları üst üste konarak aynı rank.
- Daire: merkez + yarıçap satırı.
Bu, SPEC 26'da her öğenin "tam tanımlı / eksik / fazla" rengini ve tek serbestlikli noktada hareket okunu
verir; arayüz bunu kendisi hesaplamaz.

### Çelişki teşhisi
Çözüm durağan bir noktada takılırsa `Jᵀ r = 0`, yani artık `r`, `J`'nin **sol sıfır uzayındadır**: hiçbir
küçük hareket onu azaltamaz. Artığı sıfırdan farklı kalan satırlar, birbirini bağlayan ve birlikte
sağlanamayan kısıtlardır; bağımsız (sağlanabilen) kısıtların artığı en küçük kareler çözümünde sıfıra iner.
Bu yüzden:
```
çelişki kümesi = { k : max_{j ∈ k'nın satırları} |r_j| > max(tol, 1e-6 · max|r|) }
```
`SketchError` bu kümeyi kısıt sırası ve türüyle taşır (`err.constraints: tuple[int, ...]`).
Örnek: aynı nokta çiftine `D = 5` ve `D = 7` → en küçük kareler `|q − p| = 6`, iki artık `+1` ve `−1`, küme `{0, 1}`.

### Fazla tanımlı ama tutarlı kısıtlar
Kısıtlar sırayla eklenirken `rank(J_1..k) = rank(J_1..k−1)` ise k. kısıt **gereksizdir** (ör. dikdörtgenin
dört kenarına yatay/dikey yazıldıktan sonra karşılıklı kenarlara PARALLEL). Çözücü bunlarla çalışır ve
listeyi döndürür; SPEC 26 bunları sarıyla gösterir. Sayım çözülmüş konumda yapılır.

### Sürükleme
Kullanıcı bir noktayı `hedef`e sürükler. Kısıtlar tam sağlanırken nokta hedefe yerel olarak en yakın konuma
gelir. Her adımda (çözülmüş `x`'ten):
```
δx = N (S_p N)⁺ (hedef − S_p x)          sıfır uzayında, noktayı hedefe en çok yaklaştıran adım
x ← x + δx, ardından Gauss–Newton ile r(x) = 0'a geri dönüş
```
`|δx| ≤ 1e-12 · L` ya da `max_iter` ile durur. Sabit noktayı sürüklemek → `SketchError`. Diğer noktalar en küçük
normlu adım sayesinde gereğinden fazla oynamaz. Girdi eskiz değişmez; sonuç yeni konumları döndürür.

### Bölgeler (ekstrüzyona hazır profiller)
Profil öğeleri: `construction = False` olan çizgiler, yaylar ve daireler. Çözülmüş eskizde:
1. Uç noktalar **nokta kimliğiyle** bağlanır: aynı kimlik ya da COINCIDENT kısıtıyla birleştirilmiş kimlikler
   (birleşim-bul). Geometrik olarak çakışık ama kısıtla bağlanmamış uçlar bağlı sayılmaz (sessiz yapıştırma yok).
2. Her düğümün derecesi 2 olmalı: derece 1 → açık zincir, derece ≥ 3 → dallanma → `SketchError` (öğe kimlikleriyle).
3. Döngüler birbirini ya da kendini kesmemeli (paylaşılan uçlar dışında) → yoksa `SketchError`.
4. İç içelik derinliği çift olan döngü dış sınır, tek olan hemen içinde bulunduğu dış sınırın deliğidir
   (delik içindeki ada ayrı bölgedir). Yönler normalize edilir: dış CCW, delik CW (`geometry.part.Region` ve
   SPEC 03 profil kuralıyla aynı: malzeme her halkanın solunda).
5. Tam daire tek başına bir döngüdür.

İşaretli alan, yaylı döngüde kapalı formdur:
```
A = ½ Σ_i (u_i v_{i+1} − u_{i+1} v_i)  +  Σ_yaylar ½ r² (α − sin α)
```
ilk toplam köşeler (yay uçları dahil) üzerinden, `α` döngü yönünde işaretli yay açısı. Kaynak: Green teoremi;
dairesel kesit (segment) alanı ½ r² (α − sin α).

## Arayüz

### `sketch/model.py` (ayrı arayüz PR'ı, bu SPEC'ten önce)
Saf Python + numpy. `SketchError(ValueError)`.
- `@dataclass(frozen=True) Plane(origin, normal, xdir)` — `(3,)`; `|normal| = |xdir| = 1`, `normal · xdir = 0`
  (1e-9) yoksa `SketchError`. `ydir = normal × xdir`. `to_world(uv) -> (3,)`, `to_local(p) -> (2,)` (düzleme dik
  bileşen atılır; düzlemden uzaklık > 1e-9 mm → `SketchError`). Hazır düzlemler: `Plane.XY()`, `XZ()`, `YZ()`.
- `@dataclass Point(x, y, fixed=False)`
- `@dataclass Line(p0, p1, construction=False)` — nokta kimlikleri; `p0 != p1`
- `@dataclass Circle(center, r, construction=False)` — `r > 0`
- `@dataclass Arc(center, start, end, construction=False)` — CCW, üç kimlik farklı
- `class ConstraintType(Enum)` — tablodaki türler
- `@dataclass Constraint(type, refs: tuple[str, ...], value: float | None = None, side: int = 0)`
- `@dataclass Sketch(plane, points: dict[str, Point], entities: dict[str, Line | Circle | Arc], constraints: list[Constraint])`
  - `validate()` — kimlikler var, referans türleri tablodaki bir satıra uyuyor, değerler sonlu, `L₀, R, D > 0`
    olması gerekenler pozitif, `side ∈ {−1, 0, 1}`; değilse `SketchError` (kısıt sırası mesajda)
  - `to_dict() -> dict` / `Sketch.from_dict(d)` — `"sema": 1`; JSON'a yazılıp okununca kayıpsız (SPEC 26 köprüsü)
- Çıktı tipleri: `@dataclass(frozen=True) SegLine(p0, p1)`, `SegArc(center, r, start, end, ccw: bool)` (uv, mm),
  `@dataclass(frozen=True) SketchRegion(outer: tuple[Seg, ...], holes: tuple[tuple[Seg, ...], ...])`

### `sketch/constraints.py`
- `residual(sketch, k, x_map) -> np.ndarray` ve `jacobian(sketch, k, unknowns) -> np.ndarray` — tablodaki satırlar
  (ölçek dahil); desteklenmeyen tür/referans çifti → `SketchError`

### `sketch/solver.py`
- `@dataclass SolveResult`:
  - `points: dict[str, np.ndarray]`, `radii: dict[str, float]` (daireler), `sides: dict[int, int]` (TANGENT dalları)
  - `iterations: int`, `residual: float`, `dof: int`
  - `freedom: dict[str, int]` (öğe ve nokta kimliği → kalan serbestlik), `directions: dict[str, np.ndarray]`
    (tek serbestlikli noktalar için birim yön), `redundant: tuple[int, ...]`
  - `apply(sketch) -> None` — konumları, yarıçapları ve `side` değerlerini eskize yazar
- `solve(sketch, tol=1e-10, max_iter=50) -> SolveResult` — **girdiyi değiştirmez**; çelişki → `SketchError`
  (`constraints` alanı dolu)
- `drag(sketch, point, target, tol=1e-10, max_iter=50) -> SolveResult` — girdiyi değiştirmez
- `dof(sketch) -> int` — mevcut konumda (çözmez)

### `sketch/regions.py`
- `regions(sketch) -> list[SketchRegion]` — çözülmüş (sağlanmış) eskizden; kısıtlar sağlanmıyorsa
  (`max|r| > 1e-9`) → `SketchError` ("önce çöz")
- `area(region) -> float` — yaylı kapalı form, delikler düşülmüş (mm²)

## Dosyalar
- Arayüz PR'ı (önce, ayrı, kullanıcı onayıyla): `sketch/__init__.py`, `sketch/model.py`, `tests/sketch/test_model.py`
- Bu SPEC: `sketch/constraints.py`, `sketch/solver.py`, `sketch/regions.py`, `tests/sketch/test_constraints.py`,
  `tests/sketch/test_solver.py`, `tests/sketch/test_regions.py`, `durum/17-kroki.md`
- Dokunulmayacak: `sketch/model.py` (SPEC PR'ında), `assy/`, `cam/`, `geometry/`, ortak dosyalar
- `CLAUDE.md` mimari listesine `sketch/` satırı, sahibi olan thread tarafından eklenir (bu SPEC PR'ında değil)

## Yeni bağımlılık
Yok (numpy).

## Kabul kriterleri
Konum toleransı `1e-9` mm, açı `1e-9` rad, aksi yazmadıkça. Testler `tests/sketch/`.
- [ ] **K1 Artıklar:** her tablo satırı için elle kurulmuş sağlanan konumda `r = 0` (1e-12) ve bilinen bozulmada
  bilinen değer (ör. 2 mm kaçık nokta → POINT_ON_LINE `r = 2`; 30° açı yerine 31° → `r = L·π/180`)
  — `test_constraints.py::test_residual_*`
- [ ] **K2 Jacobian:** analitik = merkezi fark (h = 1e-6, mutlak 1e-6), her tablo satırı ve yay iç satırı için,
  rastgele (tohumlu) konumlarda — `test_jacobian_matches_fd`
- [ ] **K3 Üçgen:** 3-4-5 kenarlı üçgen (bir köşe sabit, bir kenar HORIZONTAL, üç DISTANCE/LENGTH) bozuk
  başlangıçtan kapalı forma iner; dik açı 90° (1e-9 rad); `dof = 0`. Eşkenar üçgen (EQUAL ×2 + LENGTH) iç açılar 60°
- [ ] **K4 Dikdörtgen:** paylaşılan 4 nokta, 4 çizgi; H, V, H, V → `dof = 4`; + LENGTH ×2 → 2; + sabit köşe → 0;
  köşeler kapalı formda. Karşılıklı kenarlara PARALLEL eklemek `dof`'u değiştirmez ve `redundant` bu kısıtları listeler
- [ ] **K5 Teğet:** sabit daire (r = 10, merkez orijinde) ve HORIZONTAL çizgiye TANGENT → çizgi `y = ±10`,
  dal başlangıç tarafından seçilir ve `sides`'ta döner; iki daire dış teğet → merkezler arası `r_a + r_b`, iç teğet →
  `|r_a − r_b|`; iç teğette çakışık merkezle başlangıç → `SketchError`
- [ ] **K6 Kanal (obround):** iki yay + iki çizgi, uçlar paylaşılan noktalar, her çizgi iki yaya TANGENT,
  merkezler arası DISTANCE `a`, bir yaya RADIUS `r`, yaylar EQUAL → `area = 2 r a + π r²` (1e-9 mm²),
  `dof = 3` (düzlemde rijit hareket)
- [ ] **K7 Serbestlik sayımı:** boş nokta 2, çizgi 4, daire 3, yay 5; sabit merkezli ve RADIUS'lu daire üzerinde
  POINT_ON_CIRCLE noktası 1 ve yönü teğet yön (1e-9); tam tanımlı eskizde her öğe 0; aynı kısıt iki kez
  yazılınca sayı değişmez
- [ ] **K8 Çelişki teşhisi:** aynı çifte `D = 5` ve `D = 7` → `SketchError`, `constraints == (i, j)` tam o ikisi;
  3-4-5 üçgene dik köşede ANGLE 60° eklenince küme dört kısıtı içerir ve üçgene bağlı olmayan ayrı bir dairenin
  RADIUS kısıtını içermez
- [ ] **K9 Sürükleme, kapalı formlar:** sabit merkezli r = 10 daire üzerindeki nokta (10, 0)'dan (30, 40)'a
  sürüklenince (6, 8); p0 sabit, LENGTH 10 çizginin p1'i hedefe sürüklenince `p0 + 10·birim(hedef − p0)`;
  HORIZONTAL çizgi üstündeki (POINT_ON_LINE) nokta (5, 7)'ye sürüklenince `(5, y₀)`; her durumda `max|r| ≤ 1e-10`;
  sabit noktayı sürüklemek → `SketchError`; girdi eskiz değişmez
- [ ] **K10 Bölgeler:** 40×30 dikdörtgen + içinde r = 5 daire → tek bölge, bir delik, `area = 1200 − 25π`;
  dış CCW, delik CW; deliğin içindeki ada ayrı bölge; iki ayrık dikdörtgen iki bölge;
  construction çizgileri bölgeye girmez
- [ ] **K11 Bölge hataları → `SketchError`:** açık zincir, dallanma (T bağlantı), kendini kesen döngü (papyon),
  kesişen iki döngü, kısıtı sağlanmamış eskiz; mesajda ilgili öğe kimlikleri var
- [ ] **K12 Değişmezlik:** sabit noktası olmayan eskiz keyfi rijit hareket (dönme + öteleme) ile taşınınca çözüm
  aynı hareketle taşınır (1e-9); `solve` girdiyi değiştirmez; zaten sağlanmış eskizde 0 iterasyon ve konumlar aynı
  (1e-12); `apply` yazıyor
- [ ] **K13 Model:** `validate` hataları (bilinmeyen kimlik, yanlış referans türü, `D = 0` nokta–nokta mesafesi,
  `r ≤ 0`, sonsuz değer); `to_dict` → JSON → `from_dict` kayıpsız; `Plane.to_world(to_local(p)) = p` (1e-12),
  ortonormal olmayan düzlem hata — `test_model.py` (arayüz PR'ı)
- [ ] **K14 Ölçek:** 12 delikli flanş profili (dış daire, 12 delik daire, 12 construction çizgi, ~110 bilinmeyen)
  bozuk başlangıçtan 20 iterasyon içinde çözülür ve tek çözüm 0.5 s'nin altında sürer (SPEC 26'da sürükleme akıcı olsun)
- [ ] Tüm testler yeşil: `pytest` 0 failed, bu SPEC'te 0 "uygulanmamış"; `ruff check .` ve `ruff format --check .` temiz

## Test yaklaşımı
CLAUDE.md "Test bağımsızlığı" aynen geçerli: arayüz PR'ı birleşince `dogrulayici` oturumu bu SPEC'ten testleri
yazar, ayrı bir `yazici` oturumu kodu yazar. Kapalı formlar elle türetilir; FreeCAD / SolveSpace gibi dış
çözücülerle çapraz kontrol bu SPEC'te yok (bağımlılık eklenmez).

## Kapsam dışı
- Spline, elips, ofset eğrisi, desen (doğrusal / dairesel çoğaltma), ayna komutu (SYMMETRIC kısıtı var, ayna aracı yok)
- 3D eskiz; eskizin katı parçadan kenar yansıtması (SPEC 26 bunu sabit referans geometri olarak verir)
- Teğet noktanın yay açıklığında tutulması, eşitsizlik kısıtları (min / max mesafe)
- Büyük eskizler için kısıtları gruplara ayırma / sembolik ayrıştırma (birkaç yüz bilinmeyene kadar hedefleniyor)
- Birden çok çözüm dalını listeleme: başlangıca en yakın çözüm bulunur
- Ölçülere ifade / parametre yazma (SPEC 26), ekstrüzyon (SPEC 26), özellik ağacı (SPEC 18)
