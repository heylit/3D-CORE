# SPEC 12 — Parçadan tetrahedron ağı (gmsh) ve sınır yükleri (Dalga 3)

## Amaç
Bir katı parçayı (`geometry.part.Part`) gmsh ile dört düğümlü tetrahedron ağına çevirip doğrudan çözülebilir
bir `core.model.Model` (SPEC 11 `tet4`) üretmek; ağın sınır yüzeyinden düzlem / silindir seçerek mesnet,
yüzey çekmesi ve basınç yükü eklemek. Bitince "parça → ağ → mesnet + yük → `solve`" zinciri uçtan uca çalışır.

## Teori

### Ağ üretimi
- Parça STEP olarak geçici bir dosyaya yazılır (`Part.to_step`), gmsh'in OpenCascade çekirdeğine okunur
  (`gmsh.model.occ.importShapes`). Böylece gmsh aynı B-rep'i görür; geometri ikinci kez kurulmaz.
- Hedef eleman boyu `h` [mm] (`Mesh.MeshSizeMax`). Yerel inceltme küreleri (`Refine`) gmsh `Ball` alanlarıyla,
  birden fazlası `Min` alanıyla birleştirilir: kürenin içinde boy `h_local`, kürenin dışında bir yarıçap
  kalınlığında `h`'ye doğrusal geçiş. Eğrilikten boy türetme kapalıdır (`Mesh.MeshSizeFromCurvature = 0`):
  boyu sadece `h` ve `Refine` belirler, sonuç öngörülebilir olur.
- Tekrarlanabilirlik: `General.NumThreads = 1`, sabit 3B algoritma (`Mesh.Algorithm3D = 1`, Delaunay).
  Aynı parça, aynı gmsh sürümü ve aynı argümanlar → aynı ağ (düğüm sırası dahil).
- gmsh sınır düğümlerini CAD yüzeyinin üstüne koyar: düzlemsel yüzlü parçada ağ hacmi ve sınır alanı tam
  (yuvarlama düzeyinde) parçanınkine eşittir; eğri yüzlerde ağ, yüzeye içten çizilmiş bir çokyüzlüdür,
  hacim hatası `O(h²)` ile azalır (silindirde kiriş hatası: `1 − sin(2π/n)·n/(2π)`, `n ≈ 2πR/h`).

### Dönüşüm (gmsh → `Model`)
- Sadece 4 düğümlü tetrahedronlar (gmsh eleman tipi 4) alınır; tetrahedronlarda kullanılmayan düğümler
  (ör. sadece eğri üstünde kalan) atılır.
- Düğümler gmsh sırasıyla `1..n`, elemanlar `1..m` olarak yeniden numaralanır.
- Her eleman **sağ el** sırasına getirilir: `det C > 0` (SPEC 11'deki `C`); değilse 2. ve 3. düğüm yer
  değiştirir. SPEC 11 iki sırayı da kabul eder, ama CalculiX C3D4 (SPEC 13) pozitif hacim ister.

### Sınır yüzeyi
Pozitif yönlü bir tet `(a, b, c, d)` için dışa bakan yüzler `(a, c, b)`, `(a, b, d)`, `(a, d, c)`, `(b, c, d)`.
Ağda tek bir elemana ait yüz sınırdadır. Üçgen `(i, j, k)`'nin alanı ve dış normali:
```
A = ½ |(x_j − x_i) × (x_k − x_i)|        n = (x_j − x_i) × (x_k − x_i) / (2A)
```
Kapalı, dışa yönlü yüzeyde: her kenar tam iki üçgende ve ters yönde geçer; `Σ n A = 0`;
diverjans teoremi `V = ⅓ Σ (c · n) A` (`c` = üçgen ağırlık merkezi).

### Sınır yükleri (tutarlı düğüm yükü)
Doğrusal üçgende düzgün yüzey yükünün tutarlı düğüm yükü her köşeye eşit pay verir:
- Yüzey çekmesi `t = (t_x, t_y, t_z)` [MPa]: her köşeye `F = t A / 3`.
- Basınç `p` [MPa] (pozitif `p` yüzeye doğru, cisme bastırır): her köşeye `F = −p n A / 3`.
Toplam kuvvet `Σ F = t Σ A` ve moment `Σ x × F = Σ_üçgen A c × t` tam olarak korunur (üç köşenin ortalaması
ağırlık merkezidir). Basınç kapalı bir yüzeyin tamamına uygulanırsa `Σ F = 0` ve `Σ x × F = 0`.

### Mesnet
`fix` seçilen düğümlerin istenen DOF'larına `BC` ekler (varsayılan ankastre: üç öteleme 0).
Simetri düzlemi mesnedi: düzleme dik DOF tutulur (ör. `x = 0` düzleminde sadece `ux`).

Kaynaklar: gmsh başvuru kılavuzu (Python API, `Mesh.*` seçenekleri, `Ball` / `Min` alanları);
Zienkiewicz–Taylor–Zhu, *The Finite Element Method: Its Basis and Fundamentals*, Bölüm 6 (tutarlı yük);
Timoshenko–Goodier, *Theory of Elasticity*, §33 (kalın cidarlı silindir, Lamé).

## Dosyalar
- Yeni: `mesh/gmsh_ag.py` (`tet_mesh`, `Refine`), `mesh/secim.py` (sınır, seçim), `mesh/yukler.py` (`fix`,
  `add_traction`, `add_pressure`), `tests/mesh/__init__.py`, `tests/mesh/test_ag.py`, `tests/mesh/test_secim.py`,
  `tests/mesh/test_yukler.py`, `tests/benchmarks/test_gmsh.py`, `durum/12-gmsh.md`
- Değişecek: `mesh/__init__.py` (aşağıdaki adları dışa açar)
- Dokunulmayacak: `core/` (model, elemanlar, çözücü), `geometry/part.py`, `pyproject.toml` (gmsh zaten `mesh`
  ekstrasında), mevcut testler, ortak dosyalar
- Ayrı PR (CI sahibi thread): `.github/workflows/test.yml`'de `pip install -e ".[mesh]"` ve gmsh'in sistem
  kütüphaneleri (`libglu1-mesa libxcursor1 libxinerama1 libxft2`); bulut kurulum betiğinde aynısı. Bu PR
  birleşmeden SPEC 12 testleri CI'da atlanır, SPEC 12 PR'ı birleşmez.

## Arayüz
`mesh` paketi dışarıya sadece `mesh/__init__.py`'deki adları verir; çıktı her zaman `core.model.Model`'dir,
yeni bir veri modeli yoktur.

### `mesh/gmsh_ag.py`
- `Refine(center: tuple[float, float, float], radius: float, h: float)` — dondurulmuş dataclass, yerel
  inceltme küresi [mm]. `radius ≤ 0`, `h ≤ 0` veya sonlu olmayan değer → `ModelError`.
- `tet_mesh(part: Part, h: float, material: Material, *, refine: Sequence[Refine] = (), max_nodes: int = 200_000) -> Model`
  - `Model(dim=3, name=part.name, materials=[material])`, elemanlar `Element(id, "tet4", [4 düğüm], material.name)`,
    `bcs` ve `loads` boş, `model.validate()` geçer.
  - Hatalar (`ModelError`): `part` bir `Part` değil; `h` pozitif ve sonlu değil; parça tek katı değil
    (gmsh'te 3B varlık sayısı ≠ 1); gmsh ağ üretemedi (gmsh hatası mesajla birlikte); ağdaki düğüm sayısı
    `> max_nodes`; hiç tetrahedron çıkmadı.
  - gmsh kurulu değilse `ModelError("gmsh kurulu değil: pip install -e .[mesh]")`. gmsh her çağrıda
    `initialize` / `finalize` edilir (çağrılar arasında durum taşınmaz, hata olsa da `finalize` çalışır).

### `mesh/secim.py` (gmsh ve OCCT gerektirmez; her tet4 `Model` ile çalışır)
- `boundary_triangles(model) -> np.ndarray (m, 3) int` — sınır üçgenleri, düğüm id'leri, dışa bakan sırada
  (Teori). Eleman sırası pozitif ya da negatif olabilir; ikisinde de dış normal döner. Sıra: elemanlar ve
  yüzler sırasıyla, tekrarlanabilir.
- Tahmin fonksiyonları (vektörel: `(n, 3)` nokta dizisi → `(n,)` bool):
  - `on_plane(point, normal, tol=1e-6)` — `|(x − point) · n̂| ≤ tol`
  - `on_cylinder(point, axis, radius, tol=1e-6)` — eksenden uzaklık `| d − radius | ≤ tol`
  - `normal` / `axis` sıfır vektör, `radius ≤ 0`, `tol ≤ 0` → `ModelError`
- `select_nodes(model, pred) -> list[int]` — `pred` doğru olan düğüm id'leri, artan sırada
- `select_triangles(model, pred) -> np.ndarray (k, 3)` — üç köşesi de `pred`'i sağlayan sınır üçgenleri
  (`boundary_triangles` sırasında)
- `triangle_areas(model, tris) -> np.ndarray (k,)`, `triangle_normals(model, tris) -> np.ndarray (k, 3)` (birim)

### `mesh/yukler.py`
- `fix(model, node_ids, dofs=("ux", "uy", "uz"), value=0.0) -> None` — her (düğüm, dof) için `BC` ekler.
  Aynı (düğüm, dof) zaten aynı değerle tutuluysa tekrar eklemez; farklı değerle tutuluysa `ModelError`.
- `add_traction(model, tris, t) -> None` — `t` (3,) [MPa]; köşe başına `t A / 3`.
- `add_pressure(model, tris, p) -> None` — `p` [MPa]; köşe başına `−p n A / 3`.
- İki yük fonksiyonu da çağrı başına (düğüm, dof) için toplanmış **tek** `Load` ekler, düğüm id'si sonra
  `ux, uy, uz` sırasıyla; tam sıfır bileşen eklenmez. Boş `tris` → hiçbir şey eklemez. Sonlu olmayan `t` / `p`
  veya bilinmeyen düğüm → `ModelError`.

Kullanım:
```python
m = mesh.tet_mesh(parca, h=2.0, material=Material("St", 210000.0, 0.3))
mesh.fix(m, mesh.select_nodes(m, mesh.on_plane((0, 0, 0), (1, 0, 0))))
mesh.add_traction(m, mesh.select_triangles(m, mesh.on_plane((100, 0, 0), (1, 0, 0))), (50.0, 0, 0))
r = solve(m)
```

## Kabul kriterleri
gmsh gerektiren testler `pytest.importorskip("gmsh")` ve `@pytest.mark.occt` ile işaretlenir. Ön hesap
(gmsh 4.15.2, karalama, repoya girmedi) eşiklerin yanında verilmiştir; eşikler sürüm farkı için paylıdır.

- [ ] **K1** Kutu `30 × 20 × 10`, `h = 4`: bütün elemanlar `tet4`, düğüm id'leri `1..n` ve eleman id'leri `1..m`
  ardışık, her düğüm en az bir elemanda, her elemanda `det C > 0`; `Σ V = 6000` (rel 1e-9); `dim = 3`,
  `materials == [material]`, `bcs` ve `loads` boş, `validate()` geçer — `tests/mesh/test_ag.py`
- [ ] **K2** Aynı kutunun `boundary_triangles`'ı: `Σ A = part.area` (rel 1e-9); her kenar tam iki üçgende ters
  yönde; `|Σ n A| ≤ 1e-9 Σ A`; `⅓ Σ (c · n) A = V` (rel 1e-9) — `test_secim.py`
- [ ] **K3** Silindir `R = 10, L = 20`: sınır üçgenlerinde uç düzlemlerinde olmayan her düğüm `|r − R| ≤ 1e-6 R`;
  hacim hatası `1 − V_ağ/(πR²L)` `h = 5 → 2.5 → 1.25`'te azalır, `h = 2.5`'te `≤ %1`, `h = 1.25`'te `≤ %0.5`
  (ön hesap: %1.35, %0.72, %0.19) — `test_ag.py`
- [ ] **K4** Tekrarlanabilirlik: aynı argümanlarla iki çağrı `==` olan iki `Model` verir — `test_ag.py`
- [ ] **K5** İnceltme: `100 × 50 × 10` blok, `h = 5`, merkezde `Refine(r = 8, h = 1)`: iki ucu kürenin içinde olan
  kenarların ortalama boyu `≤ 1.5 · 1`; bütün kenarların ortalaması `≤ 1.5 h` (inceltmesiz); eleman sayısı
  inceltmesizden fazla (ön hesap: 1.33, 1.21 h; 13205 > 2341) — `test_ag.py`
- [ ] **K6** Hatalar `ModelError`: `h ∈ {0, −1, nan, inf}`; `Refine` yarıçapı / boyu `≤ 0`; `max_nodes` aşımı;
  `Part` olmayan girdi; iki ayrık katılı parça — `test_ag.py`
- [ ] **K7** Seçim (gmsh'siz, SPEC 11 yapılandırılmış ağıyla ve gmsh kutusuyla): `on_plane` ile `x = L` yüzünün
  üçgen alanları toplamı `b · h` (rel 1e-12), seçilen düğüm sayısı ızgaradaki sayı; `on_cylinder` seçimindeki her
  düğüm yüzeyde, üç köşesi yüzeyde olan her sınır üçgeni seçilmiş; tahminler `(n, 3)` dizide vektörel;
  sıfır normal / eksen, `radius ≤ 0`, `tol ≤ 0` → `ModelError` — `test_secim.py`
- [ ] **K8** `add_traction`: `Σ F = t Σ A` (rel 1e-12); `Σ x × F = Σ A c × t` (rel 1e-12); (düğüm, dof) başına tek
  `Load`, sıfır bileşen yok, sıra kurala uygun — `test_yukler.py`
- [ ] **K9** `add_pressure`: tüm kapalı sınıra uygulanınca `|Σ F| ≤ 1e-9 p Σ A` ve `|Σ x × F| ≤ 1e-9 p Σ A ℓ`
  (`ℓ` = sınır kutusu köşegeni); tek bir düzlem yüzüne `Σ F = −p n̂ A_yüz` (rel 1e-12) — `test_yukler.py`
- [ ] **K10** `fix`: düğüm × dof kadar `BC`; aynı değerle tekrar çağrı değişiklik yapmaz; farklı değer → `ModelError`
  — `test_yukler.py`
- [ ] **K11** Parçadan çekme (uçtan uca): blok `100 × 20 × 10`, `h = 5` düzensiz ağ, `x = 0` / `y = 0` / `z = 0`
  düzlemlerinde simetri mesnedi, `x = 100` yüzünde `t = (100, 0, 0)` MPa, `E = 210000`, `ν = 0.3`. tet4 doğrusal
  alanı tam ürettiği için ağdan bağımsız tam sonuç: her elemanda `σ = (100, 0, 0, 0, 0, 0)` (abs 1e-9 · 100),
  her düğümde `u = (σx/E, −νσy/E, −νσz/E)` (abs 1e-9 · σL/E); global kuvvet ve moment dengesi (SPEC 11 K9) —
  `tests/benchmarks/test_gmsh.py::test_cekme_*`
- [ ] **K12** Kalın cidarlı silindir (Lamé, düzlem şekil değiştirme): çeyrek halka `a = 10, b = 20`, boy `5`,
  `x = 0` ve `y = 0` simetri, iki uçta `uz = 0`, iç yüzeye `add_pressure(p = 100)`. Analitik:
  `u_r(r) = (1+ν) a² p / (E (b² − a²)) · ((1 − 2ν) r + b²/r)`,
  `σ_θ(r) = p a² / (b² − a²) · (1 + b²/r²)`.
  - İç yüzey düğümlerinin ortalama radyal yer değiştirmesinin hatası `e_h = 1 − ū_r/u_r(a)`: `h = 4, 2, 1`'de
    azalır, `e_2 ≤ %3`, `e_1 ≤ %1.5`, hepsi `> 0` (uyumlu eleman: yer değiştirme alttan) (ön hesap: %6.1, %1.9, %0.64)
  - Eleman ağırlık merkezinde `σ_θ` (eleman gerilmesinin teğet bileşeni) ile analitik `σ_θ(r_c)` arasındaki göreli
    hatanın karekök ortalaması: `h = 1`'de `≤ %8` ve `≤ 0.7 ×` (`h = 2` değeri) (ön hesap: %9.6 → %5.3)
  - Global denge — `test_lame_*`
- [ ] Tüm testler yeşil: `pytest --uygulanmamis-hata` → 0 failed, `ruff check .` ve `ruff format --check .` temiz;
  CI günlüğünde SPEC 12 testleri atlanmamış (gmsh CI PR'ı birleşmiş)

## Kapsam dışı
- Gerilme düzleştirme (düğüm gerilmesi), von Mises, asal gerilmeler, delikli plaka Kt (Kirsch) — SPEC 13
- CalculiX `.inp` yazıcısı ve C3D4 çapraz kontrolü — SPEC 13
- tet10 / hex8, ikinci mertebe ağ, ağ kalitesi iyileştirme (optimize) seçenekleri
- CAD yüz kimliğiyle seçim (gmsh yüz etiketi ↔ `Part.planar_faces`); seçim şimdilik geometrik tahminle
- Montajdan ağ (çok gövdeli, temas), hacim kuvveti, ısıl yük
- Performans: eleman döngüsü Python'da kalabilir; 10 s'yi geçen test `@pytest.mark.slow`
