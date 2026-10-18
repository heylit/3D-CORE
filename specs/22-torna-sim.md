# SPEC 22 — Torna talaş simülasyonu, süre, ayna ve tutucu çarpışması

> **Durum: ONAYLANDI** (kullanıcı, 2026-10-18: 09:45 UTC kart "Önerilerle onayla": `LatheTool` arayüz eki ayrı PR,
> profil çıkarma ayrı SPEC; 10:38 UTC yazılı onay). SPEC 40 ek E4 (eksenel takım) 11:13 UTC yazılı onayla eklendi.
> Metin kullanıcı onayı olmadan değişmez.

## Amaç
Bir torna programını (SPEC 20 `Toolpath` listesi, `G18`, `G95`, `G96`) `CylinderStock` ham malzeme üzerinde
**radyal dexel** ile simüle eden saf numpy modülü: her hareketin kaldırdığı malzeme (Pappus hacmi), son parça
kesiti, işleme süresi (`G95` dev başına ilerleme, `G96` sabit kesme hızı ve devir sınırı), **hızlı harekette malzemeye
çarpma**, **kesici kenar boyu aşımı**, **takım tutucu** ve **ayna (bağlama elemanı)** çarpışması, **çakma**. Çıktı,
SPEC 05 ile aynı biçimde adım listesi, kümülatif süre ve SPEC 24 Tezgah'ın oynatacağı olay listesidir.
Bu adım bitince `simulate_lathe(ops, stock)` bilinen bir torna parçasının hacmini Pappus formülüyle ızgara adımına bağlı
tolerans içinde verir ve hatalı yollarda doğru hareketi işaret eden çarpışma kayıtları üretir.

## Teori

### Koordinatlar
- Her şey iş koordinatındadır; birim mm, mm/dev, m/dk, s. İş mili ekseni Z, X radyal ve **yarıçap** (SPEC 00 Ek 2, SPEC 20).
  Torna yolları `y = 0` düzlemindedir; hareket noktası takımın **hayali ucu** `P`'dir (SPEC 20).
- Burun merkezi `C = P − q_T` (`q_T = cam.lathe.tip_offset(tool.tip, tool.nose_r)`).
- Parça döndüğü için malzeme dönel simetriktir ve **yarı düzlemde** `(z, r)`, `r = √(x² + y²) ≥ 0` tam temsil edilir.
  Düzlemdeki bir takım noktası `(z, x)` malzemeyi `r = |x|` yarıçapında keser (eksenin öbür tarafına geçen alın pasosu dahil).

### Radyal dexel (z sütunları, r aralıkları)
Z ekseni `nz` hücreye bölünür; her hücre, **merkezindeki** `z = z_i` doğrusu üzerinde malzemenin `r` aralık listesini tutar:
`[(l_1, u_1), (l_2, u_2), …]`, `0 ≤ l_1 < u_1 < l_2 < …` (sıralı, ayrık, her aralığın boyu > 0). SPEC 05'teki Z yönlü
dexel'in aynısıdır; ışın düşey değil radyaldir. `r` yönünde ayrıklaştırma yoktur (aralık uçları kesin).
- Izgara: stok boyu tam bölünür: `n_s = ⌈(zmax − zmin)/Δ⌉`, `dz = (zmax − zmin)/n_s`. Izgara, bağlama elemanlarını
  (`fixtures`) da kapsasın diye stok aralığının altına ve üstüne aynı `dz` ile tam hücreler eklenir:
  `n_alt = ⌈(zmin − zf_min)/dz⌉⁺`, `n_üst = ⌈(zf_max − zmax)/dz⌉⁺` (`⌈·⌉⁺ = max(0, ⌈·⌉)`), `z0 = zmin − n_alt·dz`,
  `nz = n_alt + n_s + n_üst`, hücre merkezi `z_i = z0 + (i + ½)·dz`.
- Başlangıç: stok hücrelerinde tek aralık `[d/2, D/2]`, diğer hücreler boş.
- **Hacim (Pappus, hücre başına kesin):** `V = Σ_i Σ π·(u² − l²)·dz`. Başlangıçta tam olarak `CylinderStock.volume`
  (rel 1e-12), çünkü stok sınırları hücre sınırıdır.
- **Aralık farkı:** SPEC 05 dexel kuralı: `[l, u]`'dan `[a, b]` çıkarılınca sol parça `[l, min(u, a)]`, sağ parça
  `[max(l, b), u]` (boyu > 0 ise).
- Dış yarıçap `outer_i = max u` (aralık yoksa 0), iç yarıçap `inner_i = min l` (aralık yoksa 0).
Kaynak: CAM araştırma notları, "Dexel güncellemesi"; Abele vd. (2010). Dönel simetride 2D kesit yeterliliği: Pappus–Guldin.

### Kesici bölge (takım kesiti)
Takım `y = 0` düzleminde, kalınlığı ihmal edilen bir uçtur (uç ekseni merkez yüksekliğinde). **Dış çerçevede**
(dış tornalama, `T = 3` yönü) `C`'ye göre birim kenar yönleri, `−Z`'den `+X`'e doğru ölçülen açılarla (SPEC 20'deki `φ` kuralı):
`e(α) = (−cos α, sin α)` (bileşenler `(z, x)`); ana kenar `e₁ = e(κr)`, arka kenar `e₂ = e(κr + εr)`.
`l = edge_len` (kesici kenar boyu, burun teğet noktasından ölçülür).
- `TURN`, `BORE`, `THREAD`: çekirdek üçgen `Q = üçgen(C, C + l·e₁, C + l·e₂)`, kesici bölge `K = Q ⊕ D(r)`
  (`D(r)` burun yarıçaplı disk, `⊕` Minkowski toplamı). `K`'nin iki kenarı burun dairesine teğet, `e₁`/`e₂`'ye paralel,
  teğet noktasından `l` boyundadır; uzak köşeler `r` ile yuvarlanır (kesime katılmayan bölge; fark ihmal).
- `GROOVE` (genişlik `w`, iki köşede `r`): `C_L` sol köşe burun merkezi (`T = 3`: `C_L = C`; `T = 4`: `C_L = C − (w − 2r, 0)`),
  `Q = dikdörtgen([C_L,z, C_L,z + w − 2r] × [C_L,x, C_L,x + l])`, `K = Q ⊕ D(r)`. `l` dalma derinliği kapasitesidir.
- **Gövde uzantısı** (SPEC 05'teki sapın karşılığı): kesici kenarların ötesi kesmez. `TURN/BORE/THREAD`'de
  `Q_B = {C + s·e₁ + t·e₂ : s, t ≥ 0, s + t ≥ l}`, `GROOVE`'da `Q`'nun `x ≥ C_L,x + l` yukarı uzantısı (aynı genişlik);
  gövde `B = Q_B ⊕ D(r)`. Sonsuz bölge, hesapta `l + 2·(nz·dz + D)` boyunda kesilir (ızgaradaki her malzemeyi aşar).
- **İç çerçeve:** `BORE`, iç `GROOVE` (`T ∈ {1, 2}`) ve iç `THREAD` için bütün şekil `x → −x` ile aynalanır
  (`C` etrafında, `C`'nin kendisi değişmez).
- **Tutucu** (verilmişse): `C`'ye göre dış çerçevede tanımlı dışbükey çokgen `H`, `y` yönünde yarı kalınlık `b`;
  iç çerçevede aynalanır. Tutucu `K`'nin içine girmemeli (kesişim alanı > 1e-9 mm² → `CamError`).

**Taraf** her yol için başlangıç noktasından belirlenir (SPEC 20 güvenli noktası `A` stoğun dışında / deliğin içindedir):
`start.x ≥ D/2` → dış, `d > 0` ve `start.x ≤ d/2` → iç, aksi `CamError`. `TURN` yalnız dış, `BORE` yalnız iç; `GROOVE`
dışta `T ∈ {3, 4}`, içte `T ∈ {1, 2}`; uyumsuzluk → `CamError`.

### Eksenel takım (SPEC 40 ek E4: matkap, punta matkabı)
İş mili ekseninde (`x = 0`) duran freze takımı (`cam.model.Tool`, `kind ∈ {DRILL, CONE}`) ile delme. Takım ekseni iş mili
eksenidir, programlanan nokta **takım ucudur** (`C = P`, telafi yok), takım `−Z` yönünde ilerler.
- Kesici bölge `(z, x)` düzleminde, uca göre (`r = 0`): uç konisi + kesici boyda dikdörtgen,
  `L_uç = (D/2) / tan(φ/2)` (`φ = Tool.tip_angle`; `tip_angle = None` → `L_uç = 0`, düz uç, SPEC 05 kuralı),
  `L_f = flute_length`; `core` = beşgen `(0, 0), (L_uç, D/2), (L_f, D/2), (L_f, −D/2), (L_uç, −D/2)` (`(z, x)` sırasında;
  `L_uç = 0` iken dikdörtgen). `L_uç ≥ L_f` → `CamError`.
- Gövde = sap: `[L_f, ∞) × [−d_s/2, d_s/2]` (`d_s = Tool.shank`), sonsuz uç gövde uzantısı gibi kesilir; çakışması `kenar_asimi`.
  `Tool.holder` bu SPEC'te kullanılmaz.
- Taraf kuralı uygulanmaz; takım eksene göre simetrik olduğundan `to_radial` aralığı `[0, D/2]` verir (3B'de de kesin).
- Yolun **bütün noktaları** (`start` ve her hareketin `end`'i) `|x| ≤ 1e-9` olmalı, yay olmamalı; aksi `CamError`.
  `FLAT`, `BALL` freze takımı → `CamError`.

### Doğrusal hareketin süpürmesi
Bir dışbükey şeklin doğru boyunca süpürmesi iki ucundaki kopyalarının dışbükey zarfıdır:
`S = conv(Q(P0) ∪ Q(P1)) ⊕ D(r)` (çokgen ⊕ disk; `Q(P)` şeklin `P`'deki kopyası). Gövde ve tutucu için de aynı
(`Q_B`, `H`; tutucuda disk yok). Hücre doğrusu `z = z_i` ile kesişim tek aralıktır `[a, b]` (x cinsinden; dışbükey).
- **Kesin hesap:** `conv` çokgeninin köşeleri bulunur; `z = z_i` doğrusu üzerinde çokgene uzaklığı `≤ r` olan noktaların
  `x` aralığı, çokgenin kendi kesişimi ile her kenarın "kapsül"ünün (`kenar ⊕ D(r)`) kesişimlerinin birleşimidir
  (dışbükey olduğundan `[min, max]`). Kapalı form; şart: aralık uçları 1e-12 mm.
- **x → r:** aralık `[a, b]` ⇒ `a ≥ 0` → `[a, b]`; `b ≤ 0` → `[−b, −a]`; aksi `[0, max(−a, b)]`.
- **Tutucu kalınlığı:** tutucu `y ∈ [−b, b]` boyunca uzandığından `x` aralığı `[a, b_x]` (`a ≥ 0` hali)
  `r ∈ [a, √(b_x² + b²)]` olur (`b ≤ 0` ve eksen geçişi aynı mantıkla). Uç ve gövde uzantısı kalınlıksız.
- Yaylar (`G2/G3`, `G18`) SPEC 05 kuralıyla kirişlere bölünür (`n = ⌈|Δθ| / (2·acos(1 − ε_yay/R))⌉`, `ε_yay` = `arc_tol`);
  yay simülasyonda tek adımdır.

### Program, adımlar, bağlantılar
SPEC 05 ile birebir: global adım indeksi `k`, nokta 0 = ilk yolun `start`'ı, yollar arası farklı noktada `G0` bağlantı adımı
(`link = True`). Her adım, boyu `≤ min(l, 2r, 1 mm)/2`'yi aşmayan alt adımlara bölünür (`r = 0` ise `min(l, 1 mm)/2`).
Malzeme sonucu alt adımlardan bağımsızdır; alt adımlar çarpışma denetiminin hareket içindeki ilerlemeyi görmesi içindir.

Her alt adımda sıra: (1) gövde, tutucu ve ayna denetimleri **alt adımdan önceki** malzemeyle, (2) kesici süpürmenin
aralığı her hücreden çıkarılır, (3) çıkarılan parçalar hızlı çarpma ve çakma için kaydedilir.

### Çarpışma ve çakma denetimleri
Kayıt SPEC 05'teki `Collision`: `kind`, `k`, `op`, `at = (x, 0, z)` (en derin hücrenin `z`'si, orada çakışan aralığın
dış ucu `r`, `x = r`), `depth` [mm]. Aynı `(kind, k)` için tek kayıt (en büyük `depth`). Eşik `tol` (varsayılan 1e-6 mm).
Hücre başına çakışma derinliği: iki aralık listesinin kesişiminin en uzun parçasının boyu (r yönünde).
1. **Hızlı çarpma (`hizli_carpma`):** bir `G0` adımı (bağlantılar dahil) bir hücrede `tol`'dan uzun malzeme kaldırıyorsa;
   `depth` = hücre başına kaldırılan en uzun parça. Malzeme yine kaldırılır.
2. **Kenar boyu aşımı (`kenar_asimi`):** gövde uzantısı `B`'nin süpürmesi malzemeyle çakışıyorsa (örn. `a_p > l` kaba paso,
   kanal derinliği `> l`). SPEC 05 `sap_carpma`'nın karşılığı.
3. **Tutucu (`tutucu_carpma`):** tutucu `H` (kalınlıkla) süpürmesi malzemeyle çakışıyorsa.
4. **Ayna / bağlama elemanı (`ayna_carpma`):** `Setup.fixtures`'taki her `CylinderStock` dönen bağlama elemanının zarfıdır
   (ayna çeneleri: `d` = tutulan çap, `D` = çene dış çapı; punta gövdesi: dolu silindir). Kesici bölge, gövde uzantısı
   veya tutucu süpürmesi bir elemanın `[d/2, D/2]` aralığıyla (hücre merkezi elemanın `[zmin, zmax]`'ında) çakışıyorsa.
   Bağlama elemanı malzeme değildir, kaldırılmaz.
5. **Çakma (`cakma`):** parça haritası verilmişse, bir adımın kaldırdığı parçalar parça aralıklarıyla `gouge_tol`'dan
   (varsayılan 1e-3 mm) uzun çakışıyorsa. Kayıt hücreyi ilk kez çakan adıma aittir.
- Bilinen sınır (SPEC 05 ile aynı): denetim alt adımdan önceki malzemeyle yapıldığından, alt adım içinde kesilecek
  malzemeye gövde/tutucu en çok bir alt adım boyu kadar erken "dokunabilir" (yanlış alarm olabilir, kaçırma olmaz).

### Parça haritası
Parça yarı kesiti aynı ızgarada aralık listesi olarak verilir (`RadialMap`).
- `profile_rmap(region, grid)`: `(u, v) = (z, x)` düzleminde kapalı bölge (`cam.profile.Region` / kapalı `Profile`,
  `x ≥ 0`); her `z = z_i` doğrusunun bölge sınırını kestiği noktalar sıralanır, içte kalan aralıklar alınır (çift–tek kuralı).
  Teğet dokunma ve köşeden geçişte boyu 0 aralık yazılmaz.
- `mesh_rmap(V, T, grid)`: dönel simetrik parçanın üçgen ağı `y = 0`, `x ≥ 0` yarı düzlemiyle kesilir; kesit doğru
  parçalarından `profile_rmap` ile aynı kural. `part_rmap(part, grid, tol)` = `part.mesh(tol)` + `mesh_rmap`
  (`@pytest.mark.occt`). Parçanın dönel simetrik olduğu varsayılır (denetlenmez; kapsam dışı).
- **Kalan malzeme:** `V_kalan = Σ π(u² − l²)·dz` (malzeme aralıkları − parça aralıkları); **çakma hacmi**: parça aralıklarının
  malzemede olmayan kısmı (stok içinde kalan parça bölümüyle sınırlı).

### Süre tahmini
SPEC 05 `Machine(rapid, accel, tool_change)` kullanılır; `rapid` eksen başına (X yarıçap ekseni, Z), `rapid[1]` (Y) kullanılmaz.
- `G0`: SPEC 05 ile aynı (`v = min_i(rapid_i/|u_i|)/60`, `accel` ile trapez/üçgen).
- **`G95`, sabit devir** (`css = None`): `n = rpm`, hız `v = F·n/60` [mm/s] (`F` mm/dev) → `t = 60·L/(F·n)`.
- **`G96`, sabit kesme hızı** (`css = Vc`, `rpm` devir sınırı, `G50`): `n(x) = min(1000·Vc / (2π·|x|), rpm)`, `x = 0` → `rpm`.
  `|x|` hayali ucun yarıçapıdır (kontrolün kullandığı program koordinatı). `t = ∫ 60 ds / (F·n(x(s)))`:
  sınırsız bölgede integrand `60·2π|x| / (1000·Vc·F)`, sınırlı bölgede `60/(F·rpm)`. Bölge geçişi `|x| = x* = 1000·Vc/(2π·rpm)`.
  Doğruda `∫|x| ds` parça parça kapalı form (eksen geçişi ve `x*` geçişinde bölünür); yayda `x(θ)` için aynı (geçiş açıları kapalı form).
- Kesme hareketinde ayrıca `v ≤ min_i(rapid_i/|u_i|)/60` (sabit devirde); `G96`'da bu sınır yok sayılır (kapsam dışı).
- `accel` verilmişse sabit hızlı hareketlerde SPEC 05 trapez/üçgen; `G96` hareketinde eşdeğer sabit hız
  `v_eş = L / t_G96` ile aynı formül.
- Takım değişimi (`tool.id` değişince `tool_change`), sıfır boylu adım, `cumulative_time`, `op_times`: SPEC 05 ile aynı.
- İş mili hızlanma süresi, `G96`'da devir değişim gecikmesi kapsam dışı.
Kaynak: Fanuc 0i-TF, `G96`/`G50`; Smid, *CNC Programming Handbook*, sabit yüzey hızı.

### Takım yükü
`ΔV_k = Σ π(u² − l²)·dz` (adımın kaldırdığı parçalar), `MRR_k = ΔV_k / t_k` (`t_k = 0` → 0).

### Olay listesi (SPEC 24)
Bir adım bir hücrenin aralık listesini değiştirirse olay `(hücre i, k, yeni aralık listesi)` yazılır. Olaylar `(i, k)`
sırasıyla; `offsets` (uzunluk `nz + 1`) CSR; her olayın aralıkları düz dizide: `event_iv` `(M, 2)`, `event_iv_off`
(olay sayısı + 1). `k` anındaki kesit: her hücrede `k' ≤ k` olan son olayın listesi, yoksa başlangıç listesi; aynı programın
ilk `k` adımı ayrıca simüle edildiğinde çıkan haritayla **birebir** aynıdır. Tezgah, kesiti Z ekseni etrafında döndürerek çizer.

## Dosyalar
- Yeni: `cam/sim/radial.py` (`RadialMap`, aralık işlemleri, `profile_rmap`, `mesh_rmap`, `part_rmap`),
  `cam/sim/lathe_shape.py` (kesici bölge, gövde, tutucu, süpürme aralıkları), `cam/sim/lathe_time.py` (`G95`/`G96` süre),
  `cam/sim/lathe.py` (`simulate_lathe`, `LatheSimResult`); `tests/cam/test_lsim_*.py`; `durum/22-torna-sim.md`
- Değişecek: `cam/sim/__init__.py` (yalnız yeni adların dışa açılması; SPEC 05 birleştikten sonra).
- Dokunulmayacak: `cam/model.py` ve tüm `*/model.py` (gerekirse ayrı arayüz PR'ı, aşağıda), SPEC 05'in diğer dosyaları,
  SPEC 20 dosyaları, `geometry/part.py`, ortak dosyalar.
- Bağımlılık: numpy. `cam.sim.lathe` → `cam.model`, `cam.lathe` (`tip_offset`), `cam.profile`, `cam.sim` (SPEC 05:
  `Machine`, `Collision`, `SimStep`, `move_time`), `geometry.part.Part` (yalnız `part_rmap`). E4 için `cam.model` `ToolKind.CONE` ve `Tool.tip_angle` (PR #60,
  arayüz eki). Yeni bağımlılık yok.

### Gerekli arayüz eki (ayrı PR, "CAM model arayüzü" thread'i)
`LatheTool`'da kesici kenar boyu ve tutucu yok; simülasyon bunlarsız kesici bölgeyi ve tutucu çarpışmasını tanımlayamaz.
Önerilen ek (`cam/model.py`):
- `LatheTool.edge_len: float | None = None` — mm, kesici kenar boyu (burun teğet noktasından); kanal ucunda dalma
  derinliği kapasitesi. `> 0` ve sonlu.
- `@dataclass LatheHolder(name: str, polygon: tuple[tuple[float, float], ...], half_width: float)` — burun merkezine göre
  dış çerçevede `(z, x)` dışbükey çokgen (≥ 3 nokta, saat yönü tersi), `half_width > 0` (`y` yarı kalınlığı).
- `LatheTool.holder: LatheHolder | None = None`; `to_dict` / `from_dict` alanları.
`simulate_lathe` `edge_len = None` olan takımda `CamError` verir (kesici bölge tanımsız; sessiz varsayım yok).

## Arayüz
Hepsi `cam.sim`'den dışa açılır. Hatalar `cam.model.CamError`.
- `@dataclass RadialMap(z0: float, dz: float, nz: int, r_max: float)` — iç saklama serbest.
  - `RadialMap.from_stock(stock: CylinderStock, cell: float, fixtures: list[CylinderStock] = (), max_cells: int = 1_000_000)`
    — `cell ≤ 0`, sonsuz / `nan`, `nz > max_cells` → `CamError`. `r_max = max(D/2, fixtures D/2)`.
  - `RadialMap.empty_like(grid)`; `centers() -> np.ndarray` `(nz,)`; `intervals(i) -> list[tuple[float, float]]`;
    `subtract(i, a, b)` (`a ≥ b` → `CamError`); `add(i, a, b)` (birleştirerek; parça haritası kurmak için);
    `outer() -> np.ndarray`, `inner() -> np.ndarray`, `volume() -> float`, `copy()`.
- `cutter_shape(tool: LatheTool | Tool, side: str | None) -> LatheShape` — `LatheShape(core: np.ndarray (m, 2), r: float,
  body: np.ndarray (p, 2), holder: np.ndarray | None, half_width: float)`; hepsi `C`'ye göre `(z, x)`. Eksenel takımda
  (`Tool`, `DRILL`/`CONE`) `side` yok sayılır (`None` verilebilir); `LatheTool`'da `side` `"dis"` veya `"ic"`.
- `sweep_interval(poly: np.ndarray, r: float, p0, p1, z: np.ndarray) -> tuple[np.ndarray, np.ndarray]` —
  `conv(poly + p0, poly + p1) ⊕ D(r)`'nin `z` doğrularıyla kesişimi `(a, b)` (x cinsinden; kesişmeyen `a = +inf, b = −inf`).
  `p0`, `p1` `(z, x)` sırasında.
- `to_radial(a, b, half_width: float = 0.0) -> tuple[np.ndarray, np.ndarray]` — x aralığından r aralığı.
- `profile_rmap(region: Region | Profile, grid: RadialMap) -> RadialMap`, `mesh_rmap(V, T, grid) -> RadialMap`,
  `part_rmap(part: Part, grid: RadialMap, tol: float = 0.01) -> RadialMap`.
- `lathe_move_time(p0, p1, move: Move, path: Toolpath, machine: Machine) -> float` — tek hareketin süresi [s]
  (`path.feed_mode`, `css`, `rpm` buradan).
- `@dataclass LatheSimResult`:
  - `rmap: RadialMap` (son durum), `steps: list[SimStep]`, `start: tuple`, `points()`, `cumulative_time()`, `total_time`,
    `op_times` (SPEC 05 `SimResult` ile aynı anlam)
  - `event_cell: int32`, `event_k: int32`, `event_iv_off: int64`, `event_iv: float64 (M, 2)`, `offsets: int64`
  - `section_at(k: int) -> list[list[tuple[float, float]]]` — `0 ≤ k ≤ n`, aksi `CamError`
  - `collisions: list[Collision]` (`k` sırasıyla; `kind ∈ {"hizli_carpma", "kenar_asimi", "tutucu_carpma", "ayna_carpma", "cakma"}`),
    `removed_volume: float`
  - `part: RadialMap | None`, `rest_volume()`, `gouge_volume()` (parça yoksa `CamError`)
- `simulate_lathe(ops: list[Toolpath], stock: CylinderStock | Setup, cell: float = 0.5, machine: Machine | None = None,
  part: RadialMap | None = None, arc_tol: float = 1e-3, tol: float = 1e-6, gouge_tol: float = 1e-3,
  max_cells: int = 1_000_000, initial: RadialMap | None = None) -> LatheSimResult`
  - `Setup` verilirse `stock` ve `fixtures` ondan; `CylinderStock` verilirse bağlama elemanı yok.
  - `initial` verilirse (ör. parça ters bağlanmadan önceki durumun devamı) o haritadan başlar; ızgarası
    `(z0, dz, nz)` kurulan ızgarayla aynı olmalı; kopyalanır, değiştirilmez.
  - Her yol `validate()`'ten geçer. `CamError`: boş `ops`; `Stock` (kutu) ham malzeme; `DRILL`/`CONE` dışı `Tool`;
    eksenel takımla `x ≠ 0` nokta veya yay; `plane != ZX`; `edge_len = None`; taraf belirlenemiyor veya takım türüyle uyuşmuyor; tutucu `K`'ye giriyor; `part`
    veya `initial` ızgarası uyuşmuyor; `arc_tol`, `tol`, `gouge_tol ≤ 0`. `feed_mode = PER_MIN` (`G94`) kabul edilir
    (SPEC 05 süre kuralı). `machine=None` → `Machine()`.

## Kabul kriterleri
Testlerde uydurma geometri; beklenen değerin kaynağı test yorumunda. Tolerans aksi yazılmadıkça mutlak 1e-9 mm.
- [ ] K1 Izgara: `from_stock` `nz`, `dz`, `z0` tanımı (bağlama elemanı alttan / üstten taşınca ek hücreler, stok sınırları
  hücre sınırı); başlangıç hacmi `CylinderStock.volume` rel 1e-12 (dolu ve boru); hatalı `cell`, `max_cells` → `CamError` —
  `tests/cam/test_lsim_radial.py`
- [ ] K2 Aralıklar: `subtract` ortadan bölme, iç / dış kırpma, tamamen silme, değmeyen ve sınıra değen aralık; `add` birleştirme;
  sıralı, ayrık, boylar > 0; `outer`, `inner`, `volume` (Pappus) formülle — `test_lsim_radial.py`
- [ ] K3 Kesici şekil: `T = 3`, `κr = 93°`, `εr = 80°` için çekirdek üçgen köşeleri `C`, `C + l·e₁`, `C + l·e₂` kapalı formla
  1e-12; `BORE` aynası; kanal dikdörtgeni `T = 3` ve `T = 4` için; gövde uzantısı kenarları; tutucu `K`'ye girerse
  `CamError` — `tests/cam/test_lsim_shape.py`
- [ ] K4 Süpürme aralığı: hareketsiz (`p0 = p1`) daire / yuvarlatılmış üçgen için kapalı form; yatay, düşey ve eğik
  hareketlerde yoğun örneklemeli (≥ 10⁵ nokta) kaba kuvvet referansıyla ≤ 1e-6, kapalı formun bilindiği hallerde 1e-12;
  `to_radial` eksen geçişi ve tutucu kalınlığı `√(x² + b²)` — `test_lsim_shape.py`
- [ ] K5 Alın tornalama: SPEC 20 `face` ile `H` mm alın → kaldırılan hacim `π/4·(D² − d²)·H`, hata ≤ `π/4·D²·dz`;
  dolu çubukta alın düzleminin önündeki hücrelerde hiç aralık kalmıyor (eksene kadar temiz) — `tests/cam/test_lsim_volume.py`
- [ ] K6 Boy tornalama: SPEC 20 `turn(x_final, z_end)` → son haritada `[zend, zmax]` hücrelerinde dış yarıçap `x_final`
  (burun yarıçapı köşesi hariç hücreler, 1e-9); kaldırılan hacim `π(R² − x_final²)·(zmax − z_end)` + köşe dolgusu
  hacmi (kapalı form, Pappus) ≤ `π·R²·dz` toleransla — `test_lsim_volume.py`
- [ ] K7 Pappus: SPEC 20 `rough` + `finish` ile koni + silindir + dışbükey yay + omuz profili → son hacim, profilin dönel
  hacmi `2π·A·r̄` (kapalı form, bölge alanı ve ağırlık merkezi) ile hata ≤ `P_k·dz·2π·R` (`P_k` profil uzunluğu);
  Δ = 1, 0.5, 0.25 mm için ayrı ayrı; `rest_volume` yalnız keskin içbükey köşelerde (`r` dolgusu) kalan kadar —
  `test_lsim_volume.py`
- [ ] K8 Kanal ve diş: `groove` (`W > w`, çok dalış) → kanal hücrelerinde dış yarıçap `x_bottom` (köşe `r` dolgusu hariç);
  `thread` (radyal dalma, `T = 8`) → uçlardan `l`'den uzak diş hücrelerinde dış yarıçap `x0 − h`, `kenar_asimi` yok — `test_lsim_volume.py`
- [ ] K9 İç tornalama: borude SPEC 20 iç `rough` / `finish` → iç yarıçap profili, hacim Pappus formülüyle (K7 toleransı) —
  `test_lsim_volume.py`
- [ ] K10 Süre: `G95` sabit devir `t = 60·L/(F·n)` rel 1e-12; `G96` doğru (alın pasosu, `x` 0'a inerken `x*`'de devir
  sınırına geçen) ve yay için parça parça kapalı form rel 1e-12; `x*` sınırında iki dal eşit; `G0` ve `accel` SPEC 05
  formülleriyle; takım değişimi; `cumulative_time` azalmayan, son değer `total_time`, `op_times` toplamı — `tests/cam/test_lsim_time.py`
- [ ] K11 Hızlı çarpma: stoğun içinden geçen `G0` → tek `hizli_carpma`, doğru `k` ve `depth` (geçilen radyal kalınlık);
  stok dışından geçen `G0` → kayıt yok; malzemeden geçen bağlantı adımında `link = True` kayıt — `tests/cam/test_lsim_collision.py`
- [ ] K12 Kenar boyu: `l = 4` ile `a_p = 6` boyuna paso → `kenar_asimi`, `depth` kapalı formla; `a_p = 3` → kayıt yok —
  `test_lsim_collision.py`
- [ ] K13 Tutucu: dikdörtgen tutucu ve yüksek omuz (tutucu omuza değiyor) → `tutucu_carpma`, `depth` kapalı form;
  tutucusuz aynı yol → kayıt yok; `half_width` ile delik içinde bor barı: düzlemde değmeyen ama `√(x² + b²)` ile değen
  durum kayıt veriyor — `test_lsim_collision.py`
- [ ] K14 Ayna: `Setup.fixtures`'ta ayna çenesi halkası; `z_end` çene yüzüne `cl`'den yakın boy pasosu → `ayna_carpma`,
  doğru `k` ve `depth`; güvenli `z_end` → kayıt yok; `G0` geri dönüşü çeneden geçiyorsa kayıt; ayna malzemesi
  hacimden düşülmüyor — `test_lsim_collision.py`
- [ ] K15 Parça haritası ve çakma: `profile_rmap` kapalı formla (basamaklı mil, delikli burç, yay); köşe ve teğet
  geçişte sıfır boylu aralık yok; parçaya 0.2 mm giren `G1` → `cakma`, `depth = 0.2`, doğru `k`; doğru ince paso → kayıt yok;
  `rest_volume`, `gouge_volume` beklenen — `tests/cam/test_lsim_part.py`
- [ ] K16 OCCT (`@pytest.mark.occt`): SPEC 02 ile döndürülerek kurulan basamaklı mil `Part`'ı, `part_rmap` ile
  `profile_rmap` aynı profilden ağ toleransı içinde aynı; SPEC 20 yollarıyla simülasyon → çakma yok, son hacim
  `Part.volume` ile K7 toleransında — `test_lsim_part.py`
- [ ] K17 Olay listesi: sabit tohumlu rastgele 40 hareketlik torna programında her `k` için `section_at(k)` ilk `k` adımın ayrı
  simülasyonuyla birebir; `offsets` ve `event_iv_off` CSR tutarlı; `ΔV_k` toplamı `removed_volume` ve `stok − son hacim`
  rel 1e-9; `initial` ile iki parçada simüle edilen program tek seferdekiyle aynı — `tests/cam/test_lsim_events.py`
- [ ] K18 Hatalar: boş program, kutu `Stock`, freze `Tool`, `G17` yol, `edge_len = None`, taraf belirsiz, `TURN` içte,
  `BORE` dışta, tutucu `K`'ye giriyor, `part` / `initial` ızgarası uyuşmuyor, `tol/arc_tol/gouge_tol ≤ 0`, `section_at`
  aralık dışı → `CamError` — `tests/cam/test_lsim_errors.py`
- [ ] K19 Eksenel takım (E4): `cutter_shape` matkapta beşgen köşeleri kapalı formla 1e-12 (`φ = 118°`, `CONE` `φ = 90°`,
  `tip_angle = None` dikdörtgen); dolu çubuğa `H` derin delik → kaldırılan hacim `π(D/2)²·(H − L_uç) + π(D/2)²·L_uç/3`,
  hata ≤ `π(D/2)²·dz`; delik hücrelerinde iç yarıçap `D/2` (koni bölgesi hariç); boruda (`d > 0`) delme hacmi farkla;
  `H > L_f` (sap malzemeye giriyor) → `kenar_asimi`; `FLAT` takım, `x ≠ 0` nokta, yaylı yol → `CamError` —
  `tests/cam/test_lsim_drill.py`
- [ ] Tüm testler yeşil, `ruff check .` ve `ruff format --check .` temiz, bu SPEC'in testlerinde 0 "uygulanmamış";
  10 s'den uzun testler `@pytest.mark.slow`

## Kapsam dışı
- **Katı parçadan dönel profil çıkarma** (doğru + yay `Profile` olarak, SPEC 20 girdisi): ayrı SPEC ("Katı parçadan torna
  profili" thread'i). Bu SPEC parçayı yalnız simülasyon haritası olarak okur: o SPEC'in ürettiği SPEC 20 `Profile`'ı
  (kapalı bölge olarak) `profile_rmap` ile ya da ağdan `part_rmap` ile. Dönel simetrik olmayan parçalar.
- Uç kalınlığı, uç talaş açısı, merkez yüksekliği hatası; uçun `y ≠ 0` konumları (Y eksenli torna), C ekseni, canlı takım.
- Punta ucu konisi, gezer / sabit yatak, parçanın bağlamada sehimi; bağlama elemanları yalnız `CylinderStock` halkaları.
- Ters bağlamada otomatik dönüşüm (`z → −z`): `initial` ile elle verilen haritayla yapılabilir; dönüşüm fonksiyonu ayrı iş.
- `G96`'da eksen hız sınırları, iş mili hızlanması, diş çekmede senkron gecikme (`G32` giriş/çıkış boyları).
- **Diş helisi:** dönel simetrik simülasyonda diş bölgesi diş dibi yarıçapında silindir olarak görünür (diş profili
  yok; senkron kesimin helisel izi 3B simülasyon ister).
- Kesme kuvveti, talaş kırma, yüzey pürüzlülüğü (`Ra ≈ f²/(32 r)`), takım aşınması.
- G-code'dan okuma: simülasyon `Toolpath` alır; SPEC 21 okuyucusu `Toolpath` ürettiğinde aynı yol kullanılır.
- Görselleştirme (SPEC 15 / 24), ikili dosya biçimi (SPEC 24 köprüsü).
