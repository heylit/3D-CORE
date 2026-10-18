# SPEC 15 — Geliştirici görüntüleyicisi: parça, montaj ve takım yolu (pyvista)

## Amaç
Bir `Part`'ı, bir `Assembly`'yi ve bir `Toolpath`'i (ham malzemeyle birlikte) pyvista ile 3D gösterebilmek ve
ekransız (off-screen) ekran görüntüsü olarak PNG'ye kaydedebilmek. Bu bir **geliştirici aracıdır** (testlerde ve
hızlı bakışta kullanılır); kullanıcıya dönük "Tezgah" arayüzü ayrı bir SPEC'tir (web).

## Teori

### Katman kuralı
`viz/` başka paketleri yalnızca arayüzleri üzerinden kullanır: `geometry.part.Part` (özellikle `Part.mesh`),
`cam.model.Toolpath / Stock / MoveType`, `assy.model.Assembly`. Hiçbir paket `viz/`'e bağımlı olamaz.
İş iki katmana bölünür:
1. **Sahne verisi** (`viz/scene.py`): saf numpy. Çizilecek noktaları, çizgileri ve üçgenleri üretir.
   pyvista gerektirmez; doğruluk testlerinin çoğu burada analitik değerle yapılır.
2. **Çizim** (`viz/plot.py`): sahne verisini pyvista nesnelerine çevirir, `pv.Plotter` döndürür,
   ekran görüntüsü kaydeder. pyvista yalnızca bu dosyada import edilir.

### Montaj: bileşen ağını dünyaya taşıma
Bileşenin yerel ağı `V (n,3)`, konumu `T = [[R, t], [0, 1]]` (SPEC 00, `assy/model.py`):
`V' = V Rᵀ + t` (her satır için `p' = R p + t`). Üçgen sırası (dışa bakan yön) korunur çünkü `det R = +1`.
`Component.part` bir dizedir (dosya yolu veya kimlik); `Part` nesnesi çağırandan
`parts: dict[str, Part]` sözlüğüyle gelir, anahtar `Component.part`'tır. Aynı parça birden çok bileşende
kullanılabilir (ağ bir kez üretilir, her bileşen için ayrı taşınır).

### Takım yolu: yayı çokgene çevirme
G2/G3 yayı (merkez `c`, yarıçap `r`, süpürme `|Δθ|`, `cam.model` ile aynı tanım; başlangıç = bitiş → tam daire)
`n` eşit açılı parçaya bölünür. Kiriş sapması (sagitta) `s = r (1 − cos(φ/2))`, `φ = |Δθ| / n`.
`s ≤ tol` için `φ_max = 2 arccos(1 − tol/r)` (`tol ≥ r` ise `φ_max = π`), ve en az 90°'de bir nokta:

`n = max(1, ⌈|Δθ| / min(φ_max, π/2)⌉)`

Ara noktalar: `θ_k = θ₀ ± k φ` (G3 +, G2 −), `z_k = z₀ + (z₁ − z₀) k / n` (helis doğrusal), `k = 0..n`.
Son nokta hareketin `end`'idir (tam olarak, yuvarlama yok). Çokgen boyu `n·sqrt((2r sin(φ/2))² + (Δz/n)²)`,
`n → ∞` iken `Toolpath.length()`'deki `sqrt((r|Δθ|)² + Δz²)`'ye yaklaşır ve ondan büyük olamaz.
Göreli boy hatası ≈ `tol / (3r)` (kiriş/yay oranı `1 − φ²/24`, `s ≈ r φ²/8`).
Kaynak: kiriş–yay ilişkisi (sagitta), herhangi bir analitik geometri kitabı; CAM araştırma notları.

### Renk ve görünüm kuralı
- Hızlı (G0) hareketler ve kesme (G1/G2/G3) hareketleri ayrı çizgi kümeleridir; varsayılan renkler
  `RAPID_COLOR = "red"` (kesik değil, ince), `FEED_COLOR = "blue"`.
- Montajda her bileşene sabit paletten sırayla renk verilir (`PALETTE`, 8 renk, döngüsel). Aynı girdi → aynı renk.
- Ham malzeme (`Stock`) yarı saydam kutu veya tel kafes olarak çizilir.
- Ekran görüntüsü: arka plan beyaz, `window_size` piksel; kamera sahnenin sınır kutusuna oturtulur.
  `view="xy" | "xz" | "yz" | "iso"`; `parallel=True` → paralel (ortografik) izdüşüm.

### Ekransız çizim
CI ve bulut oturumunda ekran yoktur; VTK OSMesa ile çizer (`VTK_DEFAULT_OPENGL_WINDOW=vtkOSOpenGLRenderWindow`,
`libosmesa6`; PR #18). Windows / masaüstünde ek ayar gerekmez. Testler her zaman `off_screen=True` kullanır.

## Dosyalar
- Yeni: `viz/scene.py`, `viz/plot.py`, `viz/__main__.py` (komut satırı), `tests/viz/__init__.py`,
  `tests/viz/test_scene.py`, `tests/viz/test_plot.py`, `tests/viz/test_cli.py`, `durum/15-goruntuleyici.md`
- Değişecek: `viz/__init__.py` (yalnızca docstring / dışa açılan adlar)
- Dokunulmayacak: `*/model.py`, `geometry/part.py`, `pyproject.toml`, `.github/`, diğer paketler.
  Yeni bağımlılık yok (pyvista `viz` ekstrasında, PR #18 CI'a kurar).

Test işaretleri: pyvista gerektiren test dosyaları `pytest.importorskip("pyvista")` kullanır;
`Part` gerektiren testler ayrıca `@pytest.mark.occt`. `viz/scene.py`'nin takım yolu testleri ne pyvista
ne OCCT ister. Hatalı girdi → `viz.scene.VizError(ValueError)`; girdi modelinin kendi hatası
(`CamError`, `AssyError`, `GeometryError`) olduğu gibi yükselir. Sessiz hata yok: boş çizim döndürülmez.

## Arayüz

### `viz/scene.py` (saf numpy)
- `class VizError(ValueError)`
- `PALETTE: tuple[str, ...]` — 8 renk adı
- `toolpath_polyline(tp: Toolpath, tol: float = 0.01) -> tuple[np.ndarray, np.ndarray]`
  — noktalar `P (k+1, 3)` (ilk nokta `tp.start`) ve her parçanın hareket tipi `kinds (k,)` (`MoveType` değerleri,
  dtype object). Önce `tp.validate()` çağrılır. Hareketi olmayan yol veya `tol <= 0` → `VizError`.
- `split_rapid_feed(P, kinds) -> tuple[list[np.ndarray], list[np.ndarray]]` — art arda gelen aynı türden
  parçaları birleştirip hızlı ve kesme çoklu çizgilerini (her biri `(m, 3)`) ayrı listelerde döndürür.
- `assembly_meshes(assy: Assembly, parts: dict[str, Part], tol: float = 0.01) -> list[ComponentMesh]`
  — `@dataclass(frozen=True) ComponentMesh(name: str, V: np.ndarray, T: np.ndarray, color: str)`; `V` dünya
  koordinatında. Önce `assy.validate()`. `parts`'ta olmayan `Component.part` → `VizError` (bileşen adıyla).
  Bileşeni olmayan montaj → `VizError`.
- `stock_box(stock: Stock) -> tuple[np.ndarray, np.ndarray]` — kutunun 8 köşesi ve 12 kenarı (`(12, 2)` indeks).

### `viz/plot.py` (pyvista)
- `plot_part(part, *, plotter=None, color="lightsteelblue", tol=0.01, off_screen=False) -> pv.Plotter`
- `plot_assembly(assy, parts, *, plotter=None, tol=0.01, off_screen=False) -> pv.Plotter`
- `plot_toolpath(tp, *, stock=None, plotter=None, tol=0.01, rapid_color=RAPID_COLOR,
  feed_color=FEED_COLOR, off_screen=False) -> pv.Plotter`
- Hepsi `plotter` verilirse ona ekler (parça + takım yolu aynı sahnede), verilmezse yenisini kurar.
  Eklenen her aktörün adı sabittir: parça `part:<ad>`, bileşen `comp:<ad>`, `toolpath:rapid`,
  `toolpath:feed`, `stock` (testler aktörü adıyla bulur).
- `screenshot(plotter, path=None, *, window_size=(800, 600), view="iso", parallel=False) -> np.ndarray`
  — kamerayı sahneye oturtur, `(h, w, 3)` uint8 görüntü döndürür, `path` verilirse PNG yazar.
  Geçersiz `view` veya boş sahne → `VizError`.

### `viz/__main__.py` (hızlı bakış)
`python -m viz DOSYA [--png CIKTI.png] [--view iso|xy|xz|yz]`
- `.step/.stp` → `Part.from_step`; `.json` → `Toolpath.from_dict`. STL açılmaz: STL okuma
  `geometry.mesh.read_stl`'dir, `geometry`'nin iç dosyasıdır ve `viz/` onu import edemez.
- `--png` verilirse ekransız çizip dosyaya yazar ve çıkar; verilmezse pencere açar.
- Bilinmeyen uzantı / okunamayan dosya → çıkış kodu ≠ 0 ve Türkçe hata iletisi.

## Kabul kriterleri
- [ ] K1 `toolpath_polyline`: yalnızca G0/G1 yolunda noktalar `tp.points()` ile birebir; `kinds` hareket tipleriyle aynı — `tests/viz/test_scene.py`
- [ ] K2 Yay çokgeni: G2 ve G3 çeyrek, yarım ve tam dairede (r = 10, tol = 0.01) her ara nokta merkeze `r` uzaklıkta (1e-9), parça sayısı `n` formülle aynı, en büyük sagitta ≤ tol, son nokta `end` ile tam aynı, dönüş yönü doğru (G3'te ara noktaların açısı artıyor) — `test_scene.py`
- [ ] K3 Helis: z ara noktalarda açıyla doğrusal; çokgen boyu ≤ `tp.length()` ve tol 1e-5'te göreli fark < 1e-6 — `test_scene.py`
- [ ] K4 Takım yolu sınır kutusu: çokgenin sınır kutusu `tp.bbox()` içinde ve her eksende en çok `tol` kadar içeride — `test_scene.py`
- [ ] K5 Hatalar: hareketsiz yol, `tol <= 0` → `VizError`; yarıçapları tutmayan yay → `CamError` — `test_scene.py`
- [ ] K6 `split_rapid_feed`: G0–G1–G1–G0–G2 dizisinde 2 hızlı ve 2 kesme çizgisi, uç noktalar paylaşılıyor, toplam nokta sayısı tutuyor — `test_scene.py`
- [ ] K7 `assembly_meshes` (occt): 90° döndürülüp ötelenmiş blok bileşeninin dünya ağının sınır kutusu el hesabıyla 1e-9; ağ hacmi (`mesh_volume`'un formülü, testte yeniden yazılır) dönüşümle değişmiyor (rel 1e-9); aynı parça iki bileşende iki ayrı ağ; renkler `PALETTE` sırasında — `test_scene.py`
- [ ] K8 `assembly_meshes` hataları: `parts`'ta olmayan parça ve boş montaj → `VizError`; bilinmeyen bileşenli kısıt → `AssyError` — `test_scene.py`
- [ ] K9 `stock_box`: 8 köşe kutunun köşeleri, 12 kenarın her biri eksenlerden birine paralel ve boyu `Stock.size`'ın bir bileşeni — `test_scene.py`
- [ ] K10 `plot_part` / `plot_assembly` (occt, pyvista): aktör adları kurala uygun; aktör sınırları parça / bileşen sınır kutusuyla 1e-6 — `tests/viz/test_plot.py`
- [ ] K11 `plot_toolpath`: `toolpath:rapid` ve `toolpath:feed` aktörleri var; sınırları K4 ile tutarlı; `stock` verilince `stock` aktörünün sınırları ham malzemeyle 1e-9 — `test_plot.py`
- [ ] K12 Piksel kontrolü (occt, pyvista): 100×60×20 blok, `view="xy"`, `parallel=True`, 400×300 pencere: arka plandan farklı piksellerin sınır kutusunun en/boy oranı 100/60 ± %3; `screenshot` boyutu `(300, 400, 3)` — `test_plot.py`
- [ ] K13 Piksel kontrolü renk: sol yarısı tek G0, sağ yarısı tek G1 olan düz bir takım yolu, `view="xy"`, `parallel=True`: kırmızı baskın piksellerin tamamı görüntünün sol yarısında, mavi baskınların tamamı sağ yarısında ve ikisi de var — `test_plot.py`
- [ ] K14 Aynı sahne: bir `Plotter`'a parça + takım yolu eklenince ikisinin aktörü de var; `path` verilince PNG yazılıyor ve tekrar okununca boyutu tutuyor; geçersiz `view` ve boş sahne `VizError` — `test_plot.py`
- [ ] K15 Komut satırı: takım yolu JSON'u ve (occt) STEP için `--png` ile çıkış kodu 0 ve PNG var; bilinmeyen uzantı ve olmayan dosya çıkış kodu ≠ 0 — `tests/viz/test_cli.py`
- [ ] Tüm testler yeşil (`pytest` 0 failed, bu SPEC'te 0 "uygulanmamış"), `ruff check .` ve `ruff format --check .` temiz; CI'da `tests/viz` atlanmadan çalışıyor

## Kapsam dışı
- Kullanıcıya dönük arayüz, menüler, seçme / tıklama ile düzenleme ("Tezgah" web SPEC'i)
- Talaş kaldırma animasyonu ve takımın yol boyunca hareketi (SPEC 05 simülasyonu kullanır)
- Takım tutucu ve takım gövdesi çizimi; tornalama yolları (SPEC 20)
- FEM sonuç çizimi (gerilme renk haritası) — ileride, `core/post.py` sonrası
- STL'yi komut satırından açma (geometry iç dosyası; gerekirse `Part` arayüzüne eklenince)
- Görüntü karşılaştırmalı (referans PNG'ye piksel piksel) regresyon testi: sürücüye bağlı, kırılgan
