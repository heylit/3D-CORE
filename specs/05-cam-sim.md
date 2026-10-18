# SPEC 05 — Talaş kaldırma simülasyonu, süre tahmini, çakma ve çarpışma

> **Durum: ONAYLANDI** (kullanıcı, 2026-10-18: 08:55 UTC kapsam kararı "Dexel de ekle", parçadan özellik okuma ayrı
> SPEC; 09:23 UTC dexel eki "Eki onayla"). Metin kullanıcı onayı olmadan değişmez.

## Amaç
Bir freze programını (`Toolpath` / `DrillOp` listesi) kutu ham malzeme üzerinde **z-haritası** ya da
**tek yönlü (Z) dexel** ile simüle eden saf numpy modülü: her hareketin kaldırdığı malzeme, son parça hacmi, işleme süresi (ilerleme ve
ivmeli trapez profil), **çakma** (takımın CAD parçasına girmesi), **hızlı harekette malzemeye çarpma**,
**sap (kesici boy aşımı)** ve **takım tutucu** çarpışması. Çıktı, SPEC 24 Tezgah'ın okuyacağı olay listesi
ve kümülatif süre dizisidir. Bu adım bitince `simulate(ops, stock)` bilinen bir cebin hacmini ızgara
adımına bağlı tolerans içinde verir ve hatalı yollarda doğru hareketi işaret eden çarpışma kayıtları üretir.

## Teori

### Koordinatlar ve takım noktası
- Her şey **iş koordinatındadır** (WCS); `Stock` da iş koordinatında. Birim mm, mm/dk, s. Dönüşüm yok.
- Takım ekseni +Z'ye paraleldir (3 eksen). Hareket noktası (`Toolpath.start`, `Move.end`) takımın
  **uç noktasıdır**: takım ekseninin takımın en alt noktasıyla kesiştiği yer (SPEC 03 ile aynı:
  cep tabanı `z_bottom` = uç noktasının Z'si). Küresel uçta küre merkezi `z + R`'dedir.

### Z-haritası (yükseklik haritası)
Stok XY dikdörtgeni `nx × ny` hücreye bölünür; her hücre, **merkezindeki** düşey doğru üzerinde kalan
malzemenin üst Z'sini tutar.
- `nx = ⌈(xmax − xmin)/Δ⌉`, `dx = (xmax − xmin)/nx` (gerçek adım ≤ Δ; stok tam örtülür), `ny`, `dy` aynı şekilde.
  Hücre merkezi `x_i = xmin + (i + ½)·dx`, `y_j = ymin + (j + ½)·dy`. Dizi `z[j, i]`, şekil `(ny, nx)`.
- Başlangıç: her hücrede `z = zmax`. Alt sınır `zmin` (stok tabanı): hiçbir hücre `zmin`'in altına inmez
  (stok tabanından taşan kesim hücreyi `zmin`'e indirir, yani o sütunda malzeme kalmaz).
- Hacim: `V = Σ (z_ij − zmin)·dx·dy`. Başlangıçta tam olarak `Stock.volume` (yuvarlama hatası kadar).

**Neden z-haritası yeterli?** Takım ekseni düşey ve takım (kesici + sap + tutucu) yukarı doğru
genişleyen bir dönel cisim olduğu için 3 eksende kaldırılan bölge her zaman "bir yükseklik fonksiyonunun
üstü"dür; kalan malzeme yükseklik haritasıyla **tam** temsil edilir (hata yalnız ızgara örneklemesinden).
Z-haritasının yetmediği iki 3 eksen durumu için tek yönlü dexel (aşağıda) vardır: kesici boyunu aşan kesimde
kesicinin üstünde kalan malzeme ve ikinci bağlamada (parça ters çevrilince) alttan açılmış boşluklar.
Kaynak: CAM araştırma notları, "Simülasyon ve doğrulama"; Choi & Jerard, *Sculptured Surface Machining*, Z-map.

### Tek yönlü dexel (Z yönü)
Aynı XY ızgarasında her hücre merkezinden geçen düşey ışın üzerinde malzeme **aralık listesi** tutulur:
`[(l_1, u_1), (l_2, u_2), …]`, `l_1 < u_1 < l_2 < u_2 < …` (sıralı, ayrık, her aralığın boyu > 0).
Kaynak: CAM araştırma notları, "Dexel güncellemesi"; Abele vd., dexel tabanlı talaş kaldırma simülasyonu (2010).
- Başlangıç (kutu stok): her hücrede tek aralık `[zmin, zmax]`.
- **Kaldırma aralığı:** takımın **kesen** kısmı uçtan `L_f` (`flute_length`) yüksekliğe kadardır. Bir doğrusal hareketin
  ışında kestiği küme tek aralıktır: `[e(q), e_üst(q)]`, `e(q)` z-haritasındaki zarf, `e_üst(q) = L_f + max{ z(t) : d(t) ≤ R }`
  (her `t` için kesilen `[z(t) + h(d(t)), z(t) + L_f]` aralığı `t` ile sürekli değişir, birleşimleri bağlantılıdır).
  Kesicinin üstünde kalan malzeme kaldırılmaz; ona gövde dokunur ve sap / tutucu çarpışması olarak raporlanır.
- **Aralık farkı:** her `[l, u]`'dan `[a, b]` çıkarılır: sol parça `[l, min(u, a)]` (boyu > 0 ise), sağ parça
  `[max(l, b), u]` (boyu > 0 ise). Bir aralık ikiye bölünebilir, tamamen silinebilir ya da değişmeyebilir.
- Hacim `V = Σ_hücre Σ (u − l)·dx·dy`. Üst yüzey `top = max u` (aralık yoksa `zmin`).
- **Ters çevirme (ikinci bağlama):** stok merkezinden geçen X eksenine paralel doğru etrafında 180°:
  `y → ymin + ymax − y`, `z → zmin + zmax − z`. Izgara simetrik olduğundan hücre `j` hücre `ny − 1 − j`'ye,
  `(l, u)` aralığı `(zmin + zmax − u, zmin + zmax − l)`'ye gider; iki kez çevirmek birebir aynı haritayı verir.
  İkinci bağlamanın yolları çevrilmiş koordinatlarda yazılır.
- **Z-haritasıyla ilişki (çapraz kontrol):** kutu stokta ve gövde çarpışması olmayan programda dexel her hücrede
  tek aralık `[zmin, z]` tutar (malzeme kalmayan hücrede aralık yok) ve `top` z-haritasıyla **birebir** aynıdır.
- Gövde denetimi ve olay listesi dexel'de üst yüzey (`top`) ile yapılır; adımın kaldırdığı hacim `ΔV_k` dexel
  hacim farkıdır (üst yüzey değişmeden kaldırılan malzeme de sayılır).

### Takım alt yüzeyi h(d)
Takım ucunun eksenden `d` uzaklıktaki alt yüzey yüksekliği, uç noktasına göre (`R = D/2`, `r_c = corner_r`):
- Düz (`FLAT`, `r_c = 0`): `h(d) = 0`, `0 ≤ d ≤ R`.
- Küresel (`BALL`, `r_c = R`): `h(d) = R − √(R² − d²)`.
- Köşe radyüslü (`FLAT`, `0 < r_c < R`): `d ≤ R − r_c` → `h = 0`; aksi `h = r_c − √(r_c² − (d − R + r_c)²)`.
- Matkap (`DRILL`): modelde uç açısı alanı yok; **düz** kabul edilir (konik dip hacmi `πR³/(3·tan(φ/2))`
  kadar fazla kaldırılır; uç açısı ileride arayüz PR'ı ile eklenebilir).
`d > R` için takım o hücreye dokunmaz (`h = +∞`).

### Doğrusal hareketin süpürme zarfı
Uç `P(t) = P0 + t·(P1 − P0)`, `t ∈ [0, 1]`. Hücre merkezi `q = (x, y)` için yatay uzaklık
`d(t) = |q − (P0xy + t·Δxy)|` ve uç yüksekliği `z(t) = z0 + t·Δz`. Hareketin hücrede bıraktığı yükseklik:

`e(q) = min { z(t) + h(d(t)) : t ∈ [0, 1], d(t) ≤ R }`   (küme boşsa `+∞`)

ve hücre güncellemesi `z ← max(zmin, min(z, e(q)))`. Hücre sırası önemsizdir (min işlemi).
- `d(t)² = a t² + b t + c` ikinci derece: `d(t) ≤ R` aralığı `[t_a, t_b]` kapalı formdur.
- **Düz takım:** `h = 0` → `z(t)` doğrusal; en küçük değer aralık ucunda: `Δz ≥ 0` ise `z(t_a)`, değilse `z(t_b)`. Kesin.
- **Küresel ve köşe radyüslü:** `h` artan ve dışbükey, `d(t)` dışbükey → `h(d(t))` dışbükey; `z(t)` doğrusal
  olduğundan `g(t) = z(t) + h(d(t))` `[t_a, t_b]`'de **dışbükeydir** ve tek minimumu vardır. Küresel uç için
  kapalı form (düşey ışın–kapsül kesişimi) ya da altın oran araması kullanılabilir; şart: `e(q)` hatası ≤ 1e-6 mm.
- Yatay harekette (`Δz = 0`) minimum, hücrenin harekete en yakın noktasındadır: `e(q) = z0 + h(d_min)`.

### Yaylar (G2 / G3, G17)
Yay (helis dahil) kirişlere bölünür; kiriş sayısı `n = ⌈|Δθ| / (2·acos(1 − ε_yay / r))⌉`, `ε_yay` (varsayılan
1e-3 mm) kiriş sapmasıdır; Z kirişler boyunca doğrusal paylaştırılır. Simülasyonda yay **tek hareket**
olarak kalır (bir `k` indeksi, bir süre); kirişler yalnız malzeme ve çarpışma hesabı içindir.
`G18` yaylı yol veya `LatheTool` → `CamError` (torna simülasyonu SPEC 22).

### Program, adımlar ve bağlantılar
- Girdi sırasıyla işlenir. `DrillOp` önce `to_toolpath(dialect)` ile kanonik açılıma çevrilir (SPEC 04).
- **Global adım indeksi `k`:** nokta 0 = ilk yolun `start`'ı; her hareket bir adım, `k = 1, 2, …`; nokta `k`
  = adım `k`'nin bitişi. İki ardışık yol arasında önceki yolun son noktası ile sonrakinin `start`'ı farklıysa
  araya **bağlantı adımı** eklenir: doğrusal `G0`, `bag = True`, `op` = sonraki yolun sırası. (SPEC 04
  yazıcısı geçişte önce güvenli Z'ye çeker; `read(write(...))` çıktısında bu geri çekme zaten yolda `G0`
  olarak bulunur. Elle verilen yolda bağlantı malzemeden geçiyorsa hızlı çarpma olarak raporlanır.)
- Her adım `alt adımlara` bölünür: alt adım boyu ≤ `min(R, L_f)/2` (`L_f` = `flute_length`). Malzeme sonucu
  alt adımlardan bağımsızdır (min); alt adımlar çarpışma denetiminin hareket içindeki ilerlemeyi görmesi içindir.

### Çarpışma ve çakma denetimleri
Her kayıt: `kind`, `k`, `op`, en derin noktanın `(x, y, z)`'si (hücre merkezi ve orada takım yüzeyinin, çakma ve
hızlı çarpmada kesimin ulaştığı Z'si) ve `depth` [mm] (en büyük batma). Aynı
`(kind, k)` için **tek** kayıt (en büyük `depth`). Eşik `tol` (varsayılan 1e-6 mm): `depth > tol` ise kayıt.

1. **Hızlı harekette çarpma (`hizli_carpma`):** bir `G0` adımı (bağlantılar dahil) herhangi bir hücrede `tol`'dan
   uzun malzeme kaldırıyorsa. `depth` = adım boyunca hücre başına kaldırılan en büyük boy (z-haritasında alçalma). Malzeme yine kaldırılır
   (simülasyon gerçekte olanı gösterir).
2. **Gövde (sap ve tutucu):** takımın kesmeyen gövdesinin alt yüzeyi, uca göre, eksenden uzaklığın
   azalmayan basamak fonksiyonudur `h_B(d)`:
   - Sap: `d ≤ R_s` için `L_f` (`R_s = shank/2`). Sap `L_f`'den `stickout`'a kadar uzanır; `stickout` yoksa sonsuza.
   - Tutucu (`holder` ve `stickout` verilmişse): profilin her kesik konisi, yüksekliği ≤ 1 mm'lik silindirlere
     bölünür; her silindirin yarıçapı koninin o dilimdeki **büyük** ucu, alt yüzeyi `stickout + ζ_alt`
     (tutucu şişirilir → güvenli taraf). Profilin üstünde gövde son yarıçapla sonsuza sürer (iş mili yaklaşımı).
   - Gövde, yarı sonsuz silindirlerin (basamakların) birleşimidir; daha alçak ve daha geniş bir basamağın
     gölgesinde kalan basamak atılır, kalan basamaklar `ρ` ve `H`'de kesin artandır.
   - `h_B(d)` basamaklı olduğundan, basamak `j` (`d ≤ ρ_j` için yükseklik `H_j`) için
     `e_B(q) = min_j [ H_j + min{ z(t) : d(t) ≤ ρ_j } ]` kesindir; iç minimum düz takım zarfının aynısıdır.
   - Çarpışma: alt adımdan **önceki** yüksekliklerle `z_önce(q) − e_B(q) > tol`. Batan basamak sapa aitse
     `sap_carpma`, tutucuya aitse `tutucu_carpma`. (Kesici `L_f` boyunca keser; onun üstünde kalan malzemeye
     gövde dokunur. Sap çapı ≤ D iken sap boyunca dalma, kesici boyu aşsa da çarpma değildir: kesici yolu açar.)
   - Bilinen sınır: alt adım içindeki kesim ilerlemesi görülmez; rampada gövde, uç önündeki hücreyi en çok
     `alt adım · tan(α)` kadar erken "görür" (yanlış alarm olabilir, kaçırma olmaz).
3. **Çakma (`cakma`):** parça z-haritası `z_P` verilmişse (aşağıda), bir adım bir hücrede en alçak kaldırdığı nokta
   `z_k < z_P − gouge_tol` ise (varsayılan `gouge_tol` = 1e-3 mm). `depth = z_P − z_k`. Z-haritasında `z_k = z_sonra`.
   (Takım yukarıdan geldiği için parçanın üst yüzeyinin altında kesmek her iki modelde de çakmadır.)
   Yalnız o adımda alçalan hücreler denetlenir; kayıt hücreyi ilk kez çakan adıma aittir.

### Parça z-haritası
CAD parçası `Part.mesh(tol)` üçgen ağıyla (SPEC 02) aynı ızgaraya işlenir: her hücre merkezinden geçen düşey
doğrunun parçayı kestiği **en yüksek** Z (`z_P`); doğru parçaya değmiyorsa `−∞`. Hesap: her üçgen için XY
izdüşümündeki hücre merkezlerinde ağırlık (barisentrik) koordinatla yükseklik, hücre başına en büyük. Kenar
üstündeki merkezler `1e-12` toleransla kapsanır (ortak kenarda delik kalmaz). Düşey üçgenler katkı vermez.
- **Kalan malzeme:** `V_kalan = Σ max(z − max(z_P, zmin), 0)·dx·dy`; **çakma hacmi**: `Σ max(z_P − z, 0)·dx·dy`
  (`z_P > zmin` hücrelerde).
- Doğru bir ince işlemeden sonra simüle hacim, parçanın stok içindeki hacmine (z-haritası örneklemesiyle)
  eşittir; hata ızgara adımıyla `O(Δ)` azalır.

### Süre tahmini
Makine parametreleri `Machine(rapid=(5000, 5000, 3000), accel=None, tool_change=0.0)`:
`rapid` eksen başına hızlı ilerleme [mm/dk], `accel` yol ivmesi [mm/s²] (`None` → sonsuz), `tool_change` [s].
- Hareket boyu `L` (`Toolpath.length` ile aynı formül; yayda `√((rΔθ)² + Δz²)`), birim yön `u`.
- Hız sınırı `v` [mm/s]: kesme hareketinde `v = F/60`; `G0`'da `v = min_i (rapid_i / |u_i|) / 60`
  (eksen hızlarını aşmayan doğrusal hızlı hareket). Doğrusal kesme hareketinde de `v ≤ min_i (rapid_i/|u_i|)/60`;
  yayda `v ≤ min(rapid_x, rapid_y)/60`.
  Yayda merkezcil ivme sınırı: `v ≤ √(accel · r)` (accel verilmişse).
- `accel = None`: `t = L / v` (G1 için `t = 60·L/F`, SPEC 24 K3).
- `accel = a`: her hareket durarak başlar ve durarak biter (tam duruş, G61; ileriye bakışlı planlayıcı kapsam dışı):
  `L ≥ v²/a` → trapez `t = L/v + v/a`; değilse üçgen `t = 2·√(L/a)`.
- Yol değişiminde takım farklıysa (`tool.id`) `tool_change` saniyesi, o yolun ilk adımından (bağlantı dahil)
  önce eklenir ve o yolun süresine sayılır.
- `L = 0` olan adım (ör. tam duruş) süre 0.
Kaynak: CAM araştırma notları, "İşleme süresi tahmini"; GRBL planlayıcısı (trapez profil).

### Takım yükü
Her adımın kaldırdığı hacim `ΔV_k = Σ (z_önce − z_sonra)·dx·dy` [mm³] ve `MRR_k = ΔV_k / t_k` [mm³/s]
(`t_k = 0` ise 0). SPEC 24 normalize takım yükünü bundan üretir.

### Olay listesi (SPEC 24 `sim` ikili dizisi)
Bir adım bir hücreyi alçaltırsa (`z_sonra < z_önce`) olay `(hücre, k, z_sonra)` yazılır; hücre indeksi
`c = j·nx + i`. Olaylar `(c, k)` sırasıyla dizilir ve CSR ofsetleri `offsets` (uzunluk `nx·ny + 1`) verilir.
`k` anındaki yüzey: her hücrede `k' ≤ k` olan son olayın `z`'si, olay yoksa başlangıç üst yüzeyi (kutu stokta `zmax`). Bu yüzey, aynı programın ilk
`k` adımı simüle edildiğinde çıkan z-haritasıyla **birebir** aynıdır. Olayın `op`'u `moves[k].op`'tan okunur.

## Dosyalar
- Yeni: `cam/sim/__init__.py`, `cam/sim/zmap.py` (ızgara, hacim), `cam/sim/dexel.py` (aralık listesi), `cam/sim/sweep.py` (`h(d)`, zarf, gövde
  basamakları), `cam/sim/part.py` (ağdan parça z-haritası), `cam/sim/timing.py` (`Machine`, süre),
  `cam/sim/simulate.py` (sürücü, çarpışma, olaylar); `tests/cam/test_sim_*.py`; `durum/05-cam-sim.md`
- Dokunulmayacak: `cam/model.py` ve tüm `*/model.py`, `geometry/part.py`, SPEC 03 / 04 dosyaları,
  `pyproject.toml`, `.github/`, `CLAUDE.md`, `BASLANGIC.md`, `DURUM.md`, `core/**`
- Bağımlılık: numpy. `cam/sim` → `cam.model`, `cam.gcode` (DrillOp açılımı), `geometry.part.Part` (yalnız
  `part_zmap`, OCCT testleri `@pytest.mark.occt`). Yeni bağımlılık yok.

## Arayüz
Hepsi `cam.sim`'den dışa açılır. Hatalar `cam.model.CamError`.

- `@dataclass ZMap(x0, y0, dx, dy, nx, ny, zmin, zmax, z: np.ndarray)`
  - `ZMap.from_stock(stock: Stock, cell: float, max_cells: int = 20_000_000) -> ZMap` — `cell ≤ 0` veya sonsuz,
    `nx·ny > max_cells` → `CamError`.
  - `centers() -> (X, Y)` (her biri `(ny, nx)`), `volume() -> float`, `copy() -> ZMap`
- `@dataclass DexelMap` — `ZMap` ile aynı ızgara alanları (`x0, y0, dx, dy, nx, ny, zmin, zmax`); iç saklama serbest.
  - `DexelMap.from_stock(stock, cell, max_cells=20_000_000)` (hatalar `ZMap` ile aynı)
  - `intervals(i: int, j: int) -> list[tuple[float, float]]` — hücre (sütun i, satır j) aralıkları, sıralı ve ayrık
  - `subtract(i, j, a, b)` — tek hücreden `[a, b]` çıkarır (`a ≥ b` → `CamError`); test ve açıklama için
  - `top() -> np.ndarray` `(ny, nx)`, `volume() -> float`, `flipped() -> DexelMap`, `copy()`, `centers()`
- `sweep_top(tool: Tool, p0, p1, X, Y) -> np.ndarray` — `e_üst(q) = L_f + max{z(t) : d(t) ≤ R}` (dokunmayan `-inf`).
- `tool_height(tool: Tool, d: np.ndarray) -> np.ndarray` — `h(d)`; `d > R` → `inf`.
- `sweep_envelope(tool: Tool, p0, p1, X, Y) -> np.ndarray` — doğrusal hareketin `e(q)`'su (dokunmayan hücre `inf`).
- `body_steps(tool: Tool, dz: float = 1.0) -> list[tuple[float, float, str]]` — `(ρ_j, H_j, "sap" | "tutucu")`,
  `ρ` ve `H` kesin artan (gölgede kalanlar atılmış); tutucu dilimleri yüksekliği ≤ `dz`, yarıçapı dilimdeki büyük uç.
- `mesh_zmap(V: np.ndarray, T: np.ndarray, grid: ZMap) -> np.ndarray` — `(ny, nx)` `z_P`, değmeyen `-inf`.
- `part_zmap(part: Part, grid: ZMap, tol: float = 0.01) -> np.ndarray` — `part.mesh(tol)` + `mesh_zmap`.
- `@dataclass Machine(rapid: tuple[float, float, float] = (5000.0, 5000.0, 3000.0), accel: float | None = None,
  tool_change: float = 0.0)` — `rapid > 0`, `accel > 0` veya `None`, `tool_change ≥ 0`, aksi `CamError`.
- `move_time(p0, p1, move: Move, plane: Plane, machine: Machine) -> float` — tek hareketin süresi [s].
- `@dataclass Collision(kind: str, k: int, op: int, at: tuple[float, float, float], depth: float)`
  — `kind ∈ {"hizli_carpma", "sap_carpma", "tutucu_carpma", "cakma"}`.
- `@dataclass SimStep(k: int, op: int, type: MoveType, start, end, center, feed, link: bool, t0: float,
  duration: float, removed: float, mrr: float)` — `t0` adım başlangıç zamanı (takım değişimi dahil).
- `@dataclass SimResult`:
  - `zmap: ZMap` (son üst yüzey; dexel modelinde `top()`), `dexel: DexelMap | None` (dexel modelinde son durum), `steps: list[SimStep]` (`steps[k-1]` adım `k`), `start: tuple` (nokta 0)
  - `points() -> np.ndarray` `(n+1, 3)`, `cumulative_time() -> np.ndarray` `(n+1,)` (nokta 0'da 0; ilk yol için takım değişimi süresi yok), `total_time: float`, `op_times: list[float]`
  - `event_cell: np.ndarray[int32]`, `event_k: np.ndarray[int32]`, `event_z: np.ndarray[float64]`, `offsets: np.ndarray[int64]`
  - `zmap_at(k: int) -> np.ndarray` — olaylardan yüzey; `0 ≤ k ≤ n`, aksi `CamError`
  - `collisions: list[Collision]` (`k` sırasıyla), `removed_volume: float`
  - `part_z: np.ndarray | None`, `rest_volume() -> float`, `gouge_volume() -> float` (parça yoksa `CamError`)
- `simulate(ops: list[Toolpath | DrillOp], stock: Stock, cell: float = 1.0, machine: Machine | None = None,
  part_z: np.ndarray | None = None, arc_tol: float = 1e-3, tol: float = 1e-6, gouge_tol: float = 1e-3,
  dialect=GRBL, max_cells: int = 20_000_000, model: str = "zmap", initial: ZMap | DexelMap | None = None) -> SimResult`
  - `model ∈ {"zmap", "dexel"}`. `initial` verilirse simülasyon o haritadan başlar (ör. ikinci bağlama:
    `onceki.dexel.flipped()`); türü `model` ile ve ızgarası (`x0, y0, dx, dy, nx, ny, zmin, zmax`) `stock` ve `cell`'den
    kurulan ızgarayla aynı olmalı. `initial` kopyalanır, değiştirilmez. `zmap_at(0)` başlangıç üst yüzeyidir.
  - Her yol önce `validate()`'ten geçer. `CamError`: boş `ops`; `Stock` olmayan stok (`CylinderStock`);
    `LatheTool`, `plane != XY`, `feed_mode != PER_MIN`; `part_z` şekli ızgarayla uyuşmuyor; `arc_tol`, `tol`,
    `gouge_tol ≤ 0`; bilinmeyen `model`; `initial` türü veya ızgarası uyuşmuyor. `machine=None` → `Machine()`.

## Kabul kriterleri
Testlerde uydurma geometri; beklenen değerin kaynağı test yorumunda.
- [ ] K1 Izgara: `from_stock` `nx, ny, dx, dy` tanımı; başlangıç hacmi `Stock.volume` rel 1e-12; `cell ≤ 0`,
  `nan`, `max_cells` aşımı `CamError` — `tests/cam/test_sim_zmap.py`
- [ ] K2 `h(d)`: düz, küresel, köşe radyüslü ve matkap profilleri formülle 1e-12; `d > R` → `inf` — `tests/cam/test_sim_sweep.py`
- [ ] K3 Düz takım, yatay G1: hücre merkezi stadyumun (segment + `R` disk) içindeyse `z = z0`, dışındaysa
  değişmemiş; birebir (sınıflandırma merkez uzaklığına göre) — `test_sim_sweep.py`
- [ ] K4 Küresel takım, yatay G1: hücre `z = z0 + R − √(R² − d²)` 1e-9; köşe radyüslü takımda profil formülü 1e-9 — `test_sim_sweep.py`
- [ ] K5 Eğik hareketler (rampa, dalma, uzay doğrusu): düz takımda kapalı form 1e-12; küresel ve köşe radyüslüde
  yoğun örneklemeli (≥ 10⁵ t) kaba kuvvet referansıyla ≤ 1e-6 mm (referans en az örneklem kadar iyi) — `test_sim_sweep.py`
- [ ] K6 Yay: düz takımla tam daire kanal (G2 ve G3, helis dahil) halka bölgesi; sınırdan `arc_tol + 1e-9`'dan uzak
  hücreler doğru sınıflanıyor; helis sonunda dip `z` doğru — `test_sim_sweep.py`
- [ ] K7 Hacim: `a×b` stokta düz takımla eksenlere hizalı dikdörtgen cep (ofsetli zigzag + kontur, elle kurulmuş yol,
  köşe yarıçapı `R`) → kaldırılan hacim `(ab − (4 − π)R²)·H`; hata ≤ `P·Δ·H` (`P` cep çevresi), ızgaraya hizasız
  cepte Δ = 1, 0.5 ve 0.25 mm için ayrı ayrı — `tests/cam/test_sim_volume.py`
- [ ] K8 Delme: G81 `DrillOp` (3 delik, düz kabul edilen matkap) → kaldırılan hacim `3·πR²·H` (ızgara toleransıyla);
  G83 açılımıyla aynı son yüzey — `test_sim_volume.py`
- [ ] K9 Süre: G1 `t = 60·L/F` rel 1e-12; G0 eksen sınırı (`rapid = (6000, 6000, 1200)`, XY köşegen ve Z dahil
  uzay doğrusu) formülle; `accel` ile trapez ve üçgen dalları kapalı formla rel 1e-12 (sınırda `L = v²/a` iki dal eşit);
  yayda `√(a·r)` sınırı; takım değişimi süresi doğru yola ekleniyor; `cumulative_time` azalmayan, son değer
  `total_time`, `op_times` toplamı `total_time` — `tests/cam/test_sim_time.py`
- [ ] K10 Hızlı çarpma: stoktan geçen G0 → tek `hizli_carpma`, doğru `k` ve `depth` (geçilen malzeme kalınlığı, 1e-9);
  stok üstünden (z = zmax) geçen G0 → kayıt yok; yollar arası bağlantı malzemeden geçiyorsa `link = True` adımda kayıt —
  `tests/cam/test_sim_collision.py`
- [ ] K11 Sap: `L_f = 10`, düz takımla 15 mm derin yatay kanal → `sap_carpma`, `depth = 5` (1e-9); 8 mm derin kanal →
  kayıt yok; sap ≤ D ile 15 mm dalma → kayıt yok; `shank_d > D` ile tek paso sığ kanal ama sapın değdiği yüksek
  komşu duvar → `sap_carpma` — `test_sim_collision.py`
- [ ] K12 Tutucu: kısa `stickout` ve geniş tutucuyla yüksek bir duvarın yanında kontur → `tutucu_carpma`, `depth`
  bilinen değer (silindir tutucuda 1e-9); tutucusuz aynı yol → kayıt yok; `body_steps` yukarı genişleyen konik
  profilde ardışık `H` farkı ≤ `dz` ve yarıçap dilimin büyük ucu; daralan bölümün basamakları atılmış — `test_sim_collision.py`
- [ ] K13 Parça z-haritası: elle kurulmuş kutu ağı (12 üçgen) ve basamaklı blok ağı için `mesh_zmap` hücre başına
  beklenen değer; ortak kenar ve köşe üstündeki merkezlerde delik yok; ağ dışında `-inf` — `tests/cam/test_sim_part.py`
- [ ] K14 Çakma: blok parçanın üst yüzünden 0.2 mm aşağı inen yol → `cakma`, `depth = 0.2` (1e-9), doğru `k`;
  yüzeyi tam teğet işleyen yol → kayıt yok; doğru ince işlemeden sonra `rest_volume` ve `gouge_volume` beklenen
  (ızgara toleransıyla) — `test_sim_part.py`
- [ ] K15 OCCT uçtan uca (`@pytest.mark.occt`): SPEC 02 ile kurulan cepli blok `Part`'ı, `part_zmap` ve SPEC 03
  `pocket()` yolu → çakma yok, son simüle hacim `Part.volume` ile `P·Δ·H` toleransında — `test_sim_part.py`
- [ ] K16 Olay listesi: rastgele (sabit tohum) 50 hareketlik program için her `k`'da `zmap_at(k)` ilk `k` adımın
  ayrıca simülasyonuyla birebir (`array_equal`) ve `float32`'ye çevrilince de aynı; `offsets` CSR tutarlı;
  `ΔV_k` toplamı `removed_volume` ve `stok − son hacim` rel 1e-9 — `tests/cam/test_sim_events.py`
- [ ] K17 Hatalar: boş program, `CylinderStock`, `LatheTool`, `G18`, `G95`, geçersiz `Toolpath`, yanlış `part_z` şekli,
  `tol/arc_tol/gouge_tol ≤ 0`, geçersiz `Machine`, `zmap_at` aralık dışı → `CamError` — `tests/cam/test_sim_errors.py`
- [ ] K18 Dexel aralıkları: `from_stock` tek aralık; `subtract` ile ortadan bölme, alttan / üstten kırpma, tamamen
  silme, değmeyen aralık, sınıra değen (`a = u`) aralık; sonuç sıralı, ayrık, boyları > 0; `volume` ve `top` formülle;
  `flipped` aralık ve hücre eşlemesi formülle, iki kez çevirmek birebir aynı — `tests/cam/test_sim_dexel.py`
- [ ] K19 Çapraz kontrol: K16'daki rastgele program (kesici boyu yeterli, gövde çarpışması yok) iki modelde:
  her hücrede dexel aralıkları `[(zmin, z)]` (malzemesiz hücrede boş), `top()` z-haritasıyla birebir, hacimler rel 1e-12,
  olay listeleri, çarpışma kayıtları ve süreler aynı; düz, küresel ve köşe radyüslü takımla — `test_sim_dexel.py`
- [ ] K20 Kesici boyu: `L_f = 10`, düz takımla stok dışında 15 mm derine inip yandan giren yatay kanal dexel'de:
  kanal hücrelerinde aralıklar
  `[(zmin, zmax − 15), (zmax − 5, zmax)]` (1e-12), `sap_carpma` iki modelde aynı `k` ve `depth = 5`, hacim farkı
  `5 · (kanal hücre sayısı)·dx·dy`; `sweep_top` eğik harekette kapalı formla 1e-12 — `test_sim_dexel.py`
- [ ] K21 İki bağlama: üstten `a×b×H1` cep, `flipped()`, çevrilmiş koordinatlarda `c×d×H2` cep (ayak izleri kesişen):
  iki cebin içindeki hücrelerde tek aralık, boyu `(zmax − zmin) − H1 − H2` (1e-12); son hacim `stok − V1 − V2`
  (ızgara toleransıyla, K7'deki gibi); z-haritası bu sonucu temsil edemez (`top` yalnız üst cebi gösterir) —
  `test_sim_dexel.py`
- [ ] K22 `initial`: z-haritası modelinde `initial` ile iki parça halinde simüle edilen program, tek seferde simüle
  edilenle aynı son haritayı verir; `initial` değişmiyor; tür veya ızgara uyuşmazlığı ve bilinmeyen `model` `CamError` —
  `test_sim_dexel.py`
- [ ] Tüm testler yeşil, `ruff check .` ve `ruff format --check .` temiz, bu SPEC'in testlerinde 0 "uygulanmamış";
  10 s'den uzun testler `@pytest.mark.slow`

## Kapsam dışı
- **Tri-dexel / voksel** stok, X ve Y yönlü dexel ışınları, dexel'den yüzey ağı çıkarma; alt kesik takımlar (T kanal),
  4–5 eksen; ters çevirme dışında bağlama dönüşümleri (90° yan bağlama); parça ağından dexel stok kurma
  (dökme / önceden işlenmiş stok).
- Dexel'de parçanın tam aralık listesiyle kalan malzeme: `rest_volume` / `gouge_volume` iki modelde de parça üst
  yüzeyi `z_P` ile hesaplanır.
- **Parçadan işleme özelliği tanıma** (düz yüz, cep, delik): yol haritasında 05'in satırındaydı; araştırma
  önerisiyle kendi başına büyük bir konu (feature recognition), ayrı SPEC önerilir.
- Fikstür (bağlama) çarpışması: SPEC 10 (`Setup.fixtures`). Torna simülasyonu: SPEC 22. `CylinderStock` frezede.
- İleriye bakışlı (look-ahead) hız planlayıcısı, köşe geçiş hızları, eksen başına ivme, iş mili hızlanma süresi.
- Kesme kuvveti / güç, takım sehimi, yüzey pürüzlülüğü, kalan malzemeden otomatik yeniden işleme.
- Yayın kesin tor süpürmesi (kirişlerle yaklaşılır), matkap uç konisi (arayüzde alan yok).
- Görselleştirme (SPEC 15 / 24), ikili dosya biçimi (SPEC 24 köprüsü).
- `cam/model.py` değişikliği: gerekirse ayrı arayüz PR'ı ("CAM model arayüzü" thread'i).
