# SPEC 14 — CAM kurulumu: takım kütüphanesi, kesme verisi, iş sıfırı, takım boyu

## Amaç
Bir CAM programının tezgâha çıkmadan önceki "kurulum" bilgisini hesaplanabilir ve denetlenebilir yapmak:
JSON takım kütüphanesi (freze + torna), malzemeye göre kesme verisinden devir ve ilerleme, ham malzeme ve
iş sıfırı (WCS), bağlama denetimi ve takım boyu akışı (Fanuc `G43 H`, GRBL `G38.2` prob + `G43.1`).
Bu adım bitince `write(..., setup=..., length_offsets=...)` programı doğru iş sıfırıyla (G54..G59),
güvenli Z'yi ham malzemeden alarak ve her takım için doğru boy telafisiyle yazıyor.

Veri tipleri `cam/model.py`'de hazır (SPEC 00 Ek 2: `CuttingData`, `ToolHolder`, `Tool`, `LatheTool`,
`ToolLibrary`, `Stock`, `CylinderStock`, `Wcs`, `Setup`, `Tool.gauge_length`). Bu SPEC onları **kullanan
işlevleri** tanımlar; `cam/model.py` değişmez.

## Teori

### Kesme verisinden devir ve ilerleme (freze)
Kaynak: Sandvik Coromant, *Metal cutting technical guide* (Frezeleme formülleri); Smid, *CNC Programming
Handbook*, Bölüm 9.
- Devir `n = 1000·Vc / (π·D)` [dev/dk]; `Vc` m/dk, `D` mm.
- Program `S` tam sayıdır. **`n` önce tam sayıya yuvarlanır** (`round`, Python bankacı yuvarlaması değil:
  `floor(x + 0.5)`), sonra tezgâh üst sınırı varsa `n = min(n, n_max)`.
- İlerleme yuvarlanmış devirden: `F = n·z·fz` [mm/dk]. Böylece programdaki `S` ve `F` tutarlıdır (diş başı
  ilerleme korunur; devir sınıra takılırsa ilerleme de orantılı düşer).
- Gerçek kesme hızı `Vc_gercek = π·D·n / 1000`.
- Etkin çap (küresel ve köşe radyüslü uç, kesme derinliği `ap < r`):
  `D_eff = D − 2r + 2·sqrt(r² − (r − ap)²)`; `r = corner_r`. `ap ≥ r` veya `r = 0` → `D_eff = D`.
  Küresel uçta (`r = D/2`): `D_eff = 2·sqrt(ap·(D − ap))`. `ap` verilirse devir `D_eff` ile hesaplanır.
- Talaş debisi `Q = ap·ae·F / 1000` [cm³/dk].

Sayısal örnek (testlerde): `Vc = 200`, `D = 10`, `z = 3`, `fz = 0.05` → `n = 6366.197… → 6366`,
`F = 954.9`. `n_max = 6000` → `n = 6000`, `F = 900`, `Vc_gercek = 188.4956…`.
Küresel `D = 10`, `ap = 1` → `D_eff = 6`.

### Torna
- Sabit devir: `n = round(1000·Vc / (π·D))`, `D` işlenen çap (= 2·yarıçap; modelde X yarıçaptır),
  sonra `min(n, n_max)`; `F = n·fn` [mm/dk] (G94 eşdeğeri), `fn` [mm/dev] (G95 programı için).
- Sabit kesme hızı (G96): `css = Vc`, devir üst sınırı `n_max` **zorunlu** (G50). Verilmezse `CamError`:
  küçük çapta devir sınırsız artar (sessiz tehlike).
- Talaş debisi `Q = Vc·ap·fn` [cm³/dk].
Örnek: `Vc = 180`, `D = 50`, `fn = 0.2` → `n = 1145.9… → 1146`, `F = 229.2`; `ap = 2` → `Q = 72`.

### İş sıfırı (WCS)
- `Wcs.origin`: iş sıfırının makine koordinatı. Dokunma ile bulunur: takım / kenar bulucu makinede `m`
  noktasında, bu nokta iş koordinatında `w` ise `origin = m − w`.
- Kenar bulucu (çapı `d`) bir yan yüze `yon` (+1 / −1, eksen boyunca yaklaşma yönü) ile dokunduğunda yüzeyin
  makine koordinatı `m + yon·d/2`.

### Ham malzeme
- Freze: parçanın sınır kutusundan (`Part.bbox()` veya herhangi bir `(bmin, bmax)`) eksen başına pay ile kutu.
- Torna: parça Z eksenli **dönel** kabul edilir (`x = y = 0` ekseni). Gerekli çap
  `D = 2·max(|xmin|, |xmax|, |ymin|, |ymax|) + 2·pay_r`; standart çubuk çapları verilirse en küçük `≥ D` olan.
  Uygun standart yoksa `CamError`.

### Güvenli yükseklik ve bağlama denetimi
- Güvenli Z = ham malzemenin ve bağlama elemanlarının en üst Z'si + `clearance` (varsayılan 5 mm).
  (Kutu: `zmax`; silindir: `zmax`.)
- Torna güvenli yarıçapı = ham malzeme ve silindir bağlama elemanlarının en büyük yarıçapı + `clearance`
  (varsayılan 2 mm); kutu bağlama elemanında köşelerin `hypot(x, y)` en büyüğü.
- Bağlama denetimi takım **ucu** noktasıyla yapılır, takım yarıçapı kadar şişirilmiş engelle (Minkowski
  toplamının tutucu tarafı: köşeler kare alınır, yani temkinli):
  - Kutu bağlama elemanı: `[xmin − ρ, xmax + ρ] × [ymin − ρ, ymax + ρ] × [−∞, zmax + h/2]` içine giren uç
    noktası çarpışmadır (takım uçtan yukarı uzanır, elemanın altından geçemez).
  - Silindir bağlama elemanı (Z ekseni): `hypot(x, y) ≤ D/2 + ρ` ve `zmin − ρ ≤ z ≤ zmax + ρ`.
  - `ρ = R + h/2`: freze `R = D/2`, torna `R = nose_r`; `h = 0.25 mm` örnekleme adımı (doğrular `h`'den
    kısa parçalara, yaylar açısal olarak kiriş boyu `≤ h` olacak şekilde bölünür; `h/2` şişirme örnekler
    arasında kaçan noktayı kapatır).
  - Ham malzemenin altına (kutu: `z < zmin`) inen her nokta → `CamError` (tablaya dalış).
  - Kesme derinliği: kesme hareketlerinin (G1/G2/G3 ve delik dibi) en alçak Z'si ile ham malzeme üstü
    arasındaki fark freze takımının `flute_length`'inden büyükse → `CamError` (sap malzemeye sürtünür).
  Tutucu çarpışması, talaş kaldırma ve gerçek takım gövdesi SPEC 05'tir.

### Takım boyu
Program koordinatları takım **ucunun** iş koordinatıdır. Takım boyu farkı telafi edilmezse uzun takım
malzemeye dalar.
- `L_n = Tool.gauge_length` = tutucu ölçü boyu + taşma (iş mili ölçü hattından uca).
- **Fanuc (`G43 H<n>`):** "ölçü hattı" yöntemi: H<n> kaydına `L_n` girilir, iş sıfırının Z'si ölçü
  hattına göre ayarlanır. Yazıcı zaten `G0 G43 X Y Z H<n>` yazıyor (SPEC 04 Ek B). Bu SPEC operatöre
  tezgâha girilecek ofset tablosunu verir: `{n: L_n}`.
- **GRBL 1.1 (`G43.1 Z<ΔL>`):** GRBL'de `G43` ve takım tablosu yok; yalnız dinamik ofset `G43.1` var.
  Z sıfırı **referans takımla** (ilk takım veya seçilen) alınır. Diğer takımlar için `ΔL_n = L_n − L_ref`
  (uzun takımda pozitif: iş mili yukarıda kalır). İki kaynak:
  1. **Ön ayardan:** kütüphanedeki `gauge_length` farkları.
  2. **Prob ile ölçüm:** sabit bir takım boyu ölçerde (tool setter) her takım `G38.2` ile ölçülür; GRBL
     tetiklenme noktasını `[PRB:x,y,z:1]` olarak makine koordinatında bildirir. `ΔL_n = z_n − z_ref`
     (uzun takım daha yukarıda tetiklenir). GRBL'de değişken yok; ölçüm programı ayrı yazılır, okunan
     `z` değerleri bu SPEC'in işlevine verilir.
  Ölçülen ve ön ayardan gelen fark `tol`'dan (varsayılan 0.05 mm) büyükse → `CamError`: yanlış takım
  takılmış ya da taşma boyu kütüphaneyle uyuşmuyor.
- **Ölçüm programı (GRBL):** her takım için: `M0` ile takım değişimi, makine koordinatında (`G53`) güvenli
  Z'ye çık, ölçerin üstüne git, artımsal (`G91`) hızlı prob `G38.2 Z−travel F<hızlı>`, `backoff` kadar geri
  çekil, yavaş prob `G38.2 Z−1.5·backoff F<yavaş>`, `G90`, güvenli Z'ye dön. Başta `M5` ve `G49`
  (ölçüm telafisiz yapılır). `G38.2` temas olmazsa GRBL alarm verir (güvenli davranış).
  Kaynak: GRBL 1.1 wiki "G-code commands" (`G38.2`, `G43.1`, `G49`, `G53`), LinuxCNC G38 / G43.1 belgeleri.

## Dosyalar
- Yeni: `cam/cutting.py`, `cam/library.py`, `cam/setups.py`, `cam/tool_length.py`;
  `tests/cam/test_cutting.py`, `tests/cam/test_library.py`, `tests/cam/test_setups.py`,
  `tests/cam/test_tool_length.py`, `tests/cam/test_gcode_setup.py`;
  `examples/takim_kutuphanesi.json` (uydurma takımlar); `docs/tezgah-dogrulama.md`; `durum/14-cam-kurulum.md`.
- Değişecek (geriye uyumlu, yeni parametrelerin varsayılanında çıktı **bayt bayt aynı**):
  `cam/gcode/writer.py` (`setup`, `length_offsets` parametreleri), `cam/gcode/reader.py` (`G43.1`, `G49`,
  `G55`..`G59` okuma), `cam/gcode/dialect.py` (gerekirse yalnız iş sıfırı yer tutucusu).
  SPEC 04'ün mevcut testleri değişmeden geçer.
- Dokunulmayacak: `cam/model.py` ve tüm `*/model.py`, SPEC 03 dosyaları (`cam/ops2d.py`, `offset.py`, ...),
  `tests/cam/test_gcode_*.py` (SPEC 04 testleri), `pyproject.toml`, `.github/`, `CLAUDE.md`, `BASLANGIC.md`,
  `DURUM.md`, `core/**`. Yeni bağımlılık yok.

## Arayüz
Hatalar `cam.model.CamError`. `nan` / `inf` girdi → `CamError`.

### `cam/cutting.py`
- `@dataclass(frozen=True) SpindleFeed(n: int, F: float, Vc: float, f: float)` —
  `n` devir [dev/dk], `F` ilerleme [mm/dk], `Vc` gerçek kesme hızı [m/dk], `f` diş/devir başı ilerleme
  (freze `fz`, torna `fn`).
- `spindle_speed(Vc: float, D: float) -> float` — `1000·Vc/(π·D)`, yuvarlanmamış. `Vc ≤ 0`, `D ≤ 0` → hata.
- `cutting_speed(n: float, D: float) -> float` — `π·D·n/1000`.
- `effective_diameter(tool: Tool, ap: float) -> float` — yukarıdaki formül; `ap ≤ 0` → hata.
- `cutting_for(tool: Tool | LatheTool, material: str) -> CuttingData` — yoksa `CamError` (mesajda takım
  adı ve malzeme).
- `milling(tool: Tool, material: str, n_max: float | None = None, ap: float | None = None) -> SpindleFeed`
  — `tool.flutes` yoksa `CamError`; `ap` verilirse `D_eff`.
- `turning(tool: LatheTool, material: str, D: float, n_max: float | None = None) -> SpindleFeed`
- `css(tool: LatheTool, material: str, n_max: float) -> tuple[float, int]` — `(Vc, n_max)`; `n_max`
  `None` / `≤ 0` → `CamError`. (`Toolpath.css` ve `Toolpath.rpm` alanlarına verilecek değerler.)
- `mrr_milling(ap: float, ae: float, F: float) -> float`, `mrr_turning(Vc: float, ap: float, fn: float) -> float`
  [cm³/dk].
- `n_max` verilirse `> 0` olmalı.

### `cam/library.py`
- `load_library(path) -> ToolLibrary` — UTF-8 JSON; dosya yok, bozuk JSON veya geçersiz takım →
  `CamError` (mesajda dosya yolu).
- `save_library(lib: ToolLibrary, path) -> None` — önce `lib.validate()`; metin
  `json.dumps(lib.to_dict(), ensure_ascii=False, indent=2) + "\n"`, takımlar `id` sırasına dizilmiş.
  Aynı kütüphane iki kez kaydedilince aynı bayt; `load(save(lib))` → `to_dict()` birebir aynı.
- `find_tools(lib, kind=None, D=None, material=None) -> list[Tool | LatheTool]` — `kind` `ToolKind` veya
  `LatheToolKind` değeri; `D` (yalnız freze) `|D − t.D| ≤ 1e-9`; `material` için `cutting`'de kaydı olanlar.
  `id` sırasıyla.
- `remove_tool(lib, id: int) -> None` — yoksa `CamError`.
- `materials(lib) -> list[str]` — kütüphanede geçen malzemeler, sıralı.
- `check_tools(lib, ops) -> None` — her op'un (`Toolpath`, `DrillOp`) takımı kütüphanede aynı `id` ile ve
  **aynı tanımla** (`to_dict()` eşit) olmalı; aksi `CamError` (`T<n>` numarası yanlış takımı çağırmasın).

### `cam/setups.py`
- `CLEARANCE = 5.0` (mm, freze güvenli Z payı), `CLEARANCE_R = 2.0` (mm, torna güvenli yarıçap payı),
  `SAMPLE_STEP = 0.25` (mm, bağlama denetimi örnekleme adımı `h`).
- `stock_from_bbox(bmin, bmax, margin=(0.0, 0.0, 0.0)) -> Stock` — `margin` tek sayı veya 3'lü, `≥ 0`.
- `bar_stock_from_bbox(bmin, bmax, margin_r=0.0, margin_z=0.0, standard: Sequence[float] | None = None) -> CylinderStock`
- `wcs_from_touch(code: str, machine_point, work_point) -> Wcs` — `origin = m − w`.
- `edge_position(machine_coord: float, probe_d: float, direction: int) -> float` — `m + yon·d/2`;
  `direction` ±1 değilse veya `probe_d < 0` → `CamError`.
- `clearance_height(setup: Setup, clearance: float = CLEARANCE) -> float`
- `safe_radius(setup: Setup, clearance: float = CLEARANCE_R) -> float`
- `check_setup(setup: Setup, ops: list[Toolpath | DrillOp]) -> None` — Teori'deki bağlama denetimi;
  ilk ihlalde `CamError` (mesajda op adı, ihlal türü ve nokta). `DrillOp` kanonik açılımıyla denetlenir
  (`to_toolpath(GRBL)`).

### `cam/tool_length.py`
- `@dataclass ToolSetter(x: float, y: float, z_start: float, z_safe: float, travel: float,
  feed_fast: float = 200.0, feed_slow: float = 20.0, backoff: float = 2.0)` — makine koordinatı;
  `z_safe ≥ z_start`, `travel`, beslemeler ve `backoff` `> 0`, `1.5·backoff < travel`; aksi `CamError`.
- `length_offsets(lib: ToolLibrary, ids: Sequence[int], ref_id: int) -> dict[int, float]` —
  `ΔL_n = L_n − L_ref`; `gauge_length` `None` olan takım veya `ref_id ∉ ids` → `CamError`.
- `offsets_from_probe(readings: dict[int, float], ref_id: int) -> dict[int, float]` — `ΔL_n = z_n − z_ref`.
- `verify_offsets(measured: dict[int, float], expected: dict[int, float], tol: float = 0.05) -> None` —
  anahtarlar aynı olmalı; `|m − e| > tol` olan her takım mesajda (`T<n>: ölçülen …, beklenen …`).
- `fanuc_offset_table(lib: ToolLibrary, ids: Sequence[int]) -> dict[int, float]` — `{n: L_n}`.
- `probe_program(ids: Sequence[int], setter: ToolSetter, decimals: int = 3) -> str` — GRBL ölçüm programı
  (Ek A altın metin). Okuyucu (`read`) bu programı okumaz (`G38.2`, `G53` yol değildir).

### `cam/gcode` değişiklikleri
- `write(ops, dialect=GRBL, program_no=1, safe_z=None, setup: Setup | None = None,
  length_offsets: dict[int, float] | None = None) -> str`
  - `setup` verilirse: önce `check_setup(setup, ops)`. İş sıfırı kodu programa yazılır: Fanuc baş
    satırındaki `G54` yerine `setup.wcs.code`; GRBL baş satırının sonuna ` <code>` eklenir
    (`G21 G90 G17 G94 G55`). `safe_z` verilmezse `max(clearance_height(setup), op başlarının en yükseği)`;
    verilmiş `safe_z < clearance_height(setup) − CLEARANCE` (yani malzeme / bağlama üstünden alçak) → `CamError`.
  - `length_offsets` yalnız `tool_length_comp = False` dillerde (GRBL) geçerli; Fanuc'ta verilirse `CamError`
    (Fanuc `H` kullanır). Programdaki her takımın anahtarı olmalı, aksi `CamError`. Her takım değişimi
    satırından hemen sonra `G43.1 Z<ΔL>` (ΔL koordinat basamağıyla, ilk takım dahil; `ΔL = 0` → `Z0.`).
  - İkisi de `None` → çıktı bugünküyle bayt bayt aynı.
- `read(...)`: `G43.1 Z<v>` kabul edilir (satırda başka hareket / eksen kelimesi olamaz, `Z` burada
  ofsettir, hareket değildir; yola yansımaz); `G49` kabul edilir; `G55`..`G59` kabul edilir (yola yansımaz).
  `G38.2`, `G53` `CamError` olarak kalır.

## Kabul kriterleri
- [ ] K1 Freze devir / ilerleme: Teori örneği (`n = 6366`, `F = 954.9`; `n_max = 6000` → `6000`, `900`,
  `Vc = 188.4955592…` rel 1e-12); yuvarlama `x.5` yukarı; `flutes` yok, malzeme yok, `Vc/D/n_max ≤ 0`,
  `nan` → `CamError` — `tests/cam/test_cutting.py`
- [ ] K2 Etkin çap: küresel `D = 10, ap = 1` → 6; köşe radyüslü `D = 10, r = 2, ap = 1` →
  `6 + 2·sqrt(3)`; `ap ≥ r` → `D`; düz uç → `D`; `milling(..., ap=1)` devri `D_eff` ile — `test_cutting.py`
- [ ] K3 Torna: `Vc = 180, D = 50, fn = 0.2` → `n = 1146`, `F = 229.2`; `css` `n_max`'sız → `CamError`;
  `Q` freze `ap = 2, ae = 5, F = 954.9` → `9.549`, torna `72` — `test_cutting.py`
- [ ] K4 Kütüphane dosyası: freze + torna takımlı kütüphane `save → load` birebir; iki kayıt aynı bayt;
  `examples/takim_kutuphanesi.json` okunuyor; yok dosya / bozuk JSON / yinelenen id → `CamError` (mesajda
  yol) — `tests/cam/test_library.py`
- [ ] K5 Kütüphane işlemleri: `find_tools` (tür, çap, malzeme), `remove_tool`, `materials`; `check_tools`
  yanlış tanımlı / eksik takımı yakalıyor — `test_library.py`
- [ ] K6 Ham malzeme ve iş sıfırı: `stock_from_bbox` pay; `bar_stock_from_bbox` standart çapa yuvarlama,
  uygun çap yoksa `CamError`; `wcs_from_touch` ve `edge_position` bilinen değerler — `tests/cam/test_setups.py`
- [ ] K7 Güvenli yükseklik: `clearance_height` en yüksek bağlama elemanı + pay; `safe_radius` silindir ve
  kutu bağlama elemanı — `test_setups.py`
- [ ] K8 Bağlama denetimi: mengene çenesinin `R`'den yakınından geçen yol, yayla çeneyi sıyıran yol,
  stok altına inen yol, `flute_length`'ten derin kesim ve torna aynasına giren torna yolu `CamError`;
  çeneden `R + 0.2 mm` uzaktan geçen yol geçiyor — `test_setups.py`
- [ ] K9 Takım boyu: `length_offsets` ön ayar farkları; `offsets_from_probe`; `verify_offsets` `tol`
  aşımında mesajda takım numarası; `gauge_length` yok → `CamError`; `fanuc_offset_table` — `tests/cam/test_tool_length.py`
- [ ] K10 Ölçüm programı: Ek A'daki GRBL altın metin birebir; geçersiz `ToolSetter` → `CamError` — `test_tool_length.py`
- [ ] K11 Yazıcı + kurulum: Ek A'daki iki takımlı GRBL (`G55`, `G43.1`) ve Fanuc (`G55`, `G43 H`) altın
  metinleri birebir; `setup`'tan güvenli Z; Fanuc'ta `length_offsets` ve eksik takım ofseti `CamError`;
  bağlamaya çarpan op `write`'ta `CamError` — `tests/cam/test_gcode_setup.py`
- [ ] K12 Okuyucu: K11 metinleri okununca yollar `setup`'sız yazılanla aynı (≤ ε); `G43.1` hareket
  sayılmıyor; `G43.1` ile aynı satırda `X` → `CamError`; `G38.2` → `CamError` — `test_gcode_setup.py`
- [ ] K13 Geriye uyum: `setup` ve `length_offsets` verilmeden çıktı değişmedi (SPEC 04 altın metinleri ve
  `tests/cam/test_gcode_*.py` değişmeden yeşil)
- [ ] `docs/tezgah-dogrulama.md` yazıldı (testsiz; kuru çalıştırma kontrol listesi)
- [ ] Tüm testler yeşil, `ruff check .` ve `ruff format --check .` temiz, bu SPEC'in testlerinde 0 "uygulanmamış"

## Kapsam dışı
- Torna G-code'u ve torna takım ofsetleri (`T0101`, X/Z geometri ofseti, burun yarıçapı telafisi): SPEC 21.
- Tutucu çarpışması, gerçek takım gövdesi, talaş kaldırma: SPEC 05 / 22.
- Fanuc'ta prob ile otomatik ölçüm (`G31` makroları), `G10 L10/L11` ile ofset yükleme (bellek tipine göre
  değişir; operatör tabloyu elle girer, `docs/tezgah-dogrulama.md`).
- Tezgâh eksen sınırları (makine stroku), takım ömrü, kesme kuvveti / güç, talaş incelmesi düzeltmesi.
- GRBL'de `G10 L20` ile iş sıfırını prob sonrası otomatik ayarlama.
- `cam/model.py` değişikliği (gerekirse ayrı arayüz PR'ı).

## Ek A — Altın metinler

### Yazıcı örneği (K11, K12)
- `T1 = Tool(1, "freze6", FLAT, D=6, flute_length=20, flutes=3, stickout=30, holder=ToolHolder("BT30-ER", 60, ((0, 15), (40, 20))))` → `L = 90`
- `T2 = Tool(2, "matkap5", DRILL, D=5, flute_length=40, flutes=2, stickout=45, holder=<aynı tutucu>)` → `L = 105`
- `setup = Setup("on-yuz", Wcs("G55", (-250, -190, -80)), Stock(0, 0, -20, 50, 40, 0), fixtures=[Stock(-15, 0, -20, -5, 40, 10)])`
  → `clearance_height = 10 + 5 = 15`.
- `tp1 = Toolpath("cep", T1, start=(5, 5, 15), rpm=10000)`, hareketler `G1 (5, 5, −1) F100`, `G1 (15, 5, −1) F300`.
- `tp2 = Toolpath("delik", T2, start=(20, 20, 15), rpm=3000)`, hareket `G1 (20, 20, −5) F150`.
- GRBL: `length_offsets = length_offsets(lib, [1, 2], ref_id=1)` → `{1: 0, 2: 15}`.

GRBL (`write([tp1, tp2], GRBL, setup=setup, length_offsets={1: 0.0, 2: 15.0})`):
```
G21 G90 G17 G94 G55
T1
G43.1 Z0.
S10000 M3
G0 X5. Y5. Z15.
G1 Z-1. F100.
X15. F300.
G0 Z15.
M5
T2 M0
G43.1 Z15.
S3000 M3
G0 X20. Y20. Z15.
G1 Z-5. F150.
G0 Z15.
M5
M30
```
Fanuc (`write([tp1, tp2], FANUC, setup=setup)`):
```
%
O0001
N10 G21 G90 G17 G94 G40 G49 G80 G55
N20 T1 M6
N30 S10000 M3
N40 G0 G43 X5. Y5. Z15. H1
N50 G1 Z-1. F100.
N60 X15. F300.
N70 G0 Z15.
N80 M5
N90 T2 M6
N100 S3000 M3
N110 G0 G43 X20. Y20. Z15. H2
N120 G1 Z-5. F150.
N130 G0 Z15.
N140 M5
N150 M30
%
```
`fanuc_offset_table(lib, [1, 2])` → `{1: 90.0, 2: 105.0}`.

### Ölçüm programı (K10)
`ToolSetter(x=-10, y=-20, z_start=-70, z_safe=-1, travel=50)` (beslemeler 200 / 20, `backoff = 2`),
`probe_program([1, 2], setter)`:
```
G21 G90 G17 G94
M5
G49
T1
G53 G0 Z-1.
G53 G0 X-10. Y-20.
G53 G0 Z-70.
G91
G38.2 Z-50. F200.
G0 Z2.
G38.2 Z-3. F20.
G90
G53 G0 Z-1.
T2 M0
G53 G0 Z-1.
G53 G0 X-10. Y-20.
G53 G0 Z-70.
G91
G38.2 Z-50. F200.
G0 Z2.
G38.2 Z-3. F20.
G90
G53 G0 Z-1.
M30
```
Satırlar `\n` ile ayrılır, metin `\n` ile biter. F değerleri 1 basamak (`fmt(v, 1)`), koordinatlar `decimals`.
