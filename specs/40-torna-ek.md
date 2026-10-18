# SPEC 40 — Torna ekleri: eksenel delme ve punta, ters bağlama, profilli kanal, torna tezgâh profili

> Durum: **onaylandı** (kullanıcı, 2026-10-18 11:13, proje sohbetinde yazılı toplu onay; önerilerle, E1–E4 ekleri dahil). Dalga 5, hat H6.
> Düzeltme: K6 gidiş-dönüş toleransı SPEC 21'le aynı yapıldı (kullanıcı, 2026-10-18 13:59, 2 dakika kuralıyla onaylı öneri).
> Bağımlılık (kod): SPEC 20 (`main`'de), SPEC 21 (PR #42), SPEC 22 (PR #41), SPEC 29 (PR #58), SPEC 30, `cam/model.py`
> Ek 2 dalga 2 arayüzü (PR #60: `ToolKind.CONE`, `Tool.tip_angle`). Kod iskeleti birleşmemiş bağımlılık dallarının üstüne kurulabilir.

## Amaç
SPEC 20–22 ve 29'un bilerek dışarıda bıraktığı dört torna işini eklemek. Bu adım bitince:
- Tornada **eksenel delme** (gagalı / talaş kırmalı) ve **punta (merkez) delme** yolları üretiliyor; derinlikler uç açısından
  kapalı formla hesaplanıyor.
- Parça **ters bağlanabiliyor** (`z → z_ref − z`): profil, ham malzeme, bağlama ve SPEC 22 radyal haritası ikinci bağlamaya
  taşınıyor; ikinci bağlamanın simülasyonu birincinin son durumundan devam ediyor.
- SPEC 27'nin `Recess`'i (V kanal, yay tabanlı kanal, kademeli girinti) kanal ucuyla **profilli kanal** olarak işleniyor:
  dalarak kaba + yanal ince paso, çakmasız, kalan malzeme kapalı formla ölçülüyor.
- SPEC 30'un ertelenen **torna tezgâh profili** (`kind = "lathe"`) tanımlı: çap cinsinden X kursu, taret istasyonu, devir ve
  ilerleme denetimi, `post_lathe`.

## Neden
- SPEC 29 torna planı bugün delik isteyen iç profili `on_delik_yok`, her `Recess`'i `genel_girinti` olarak "planlanamadı"
  listesine atıyor; dolu çubuktan burç gibi en sıradan torna parçası planlanamıyor.
- İki yüzü işlenen her torna parçası (flanş, burç, mil) ters bağlama ister; SPEC 22 `initial` parametresini bunun için
  bıraktı ama haritayı ters çeviren işlev yok.
- SPEC 30 tezgâh denetimi yalnız frezede çalışıyor; torna programı tezgâha denetlenmeden gidiyor.

## Teori

### Koordinatlar ve ortak kurallar
SPEC 20'deki gibi: iş mili ekseni Z, X **yarıçap**, ön uç büyük `z`, yollar `y = 0` düzleminde, `Plane.ZX`, `FeedMode.PER_REV`,
nokta `(x, 0, z)`, yay merkezi `(x, z)`. Profil `(u, v) = (z, x)`, ön→arka (`cam.lathe.orient`). İç işlemler dış işlemlerin
aynasıdır (SPEC 20 kuralı: `x → −x`, uç numarası `mirror_tip`). Geometrik tolerans `TOL = cam.geom2d.TOL`.
Hiçbir değer sessizce kırpılmaz; geçersiz girdi, `nan`/`inf` → `CamError`.

### A. Eksenel delme ve punta
Matkap, iş mili ekseninde (`x = 0`) duran bir **freze takımıdır** (`cam.model.Tool`, `kind ∈ {DRILL, CONE}`); iş parçası döner.
Takım ekseni iş mili eksenidir, bu yüzden programlanan nokta **matkap ucudur** ve telafi yoktur.
- **Uç boyu**: tam uç açısı `φ` (`Tool.tip_angle`), çap `D`: `L_uç = (D/2) / tan(φ/2)`.
  Örnek: `D = 10`, `φ = 118°` → `L_uç = 3,0043030951…`. Tam çap derinliğinden uç derinliğine: `z_uç = z_tam − L_uç`.
  `tip_angle = None` iken `L_uç` gerekiyorsa `CamError` (varsayılan 118° kabul edilmez).
- **Punta / havşa derinliği**: uç açısı `φ` olan sivri konik takımla (`CONE` veya `DRILL`) yüzeyde `d_c` çaplı ağız açmak
  için uç derinliği `t = (d_c/2) / tan(φ/2)`. Örnek: `φ = 90°`, `d_c = 6` → `t = 3`; `φ = 60°`, `d_c = 6` → `t = 5,196152…`.
  Koşul `0 < d_c ≤ D` (aksi `CamError`). Kaynak: DIN 333 (merkez matkapları, A tipi 60° havşa); Smid, *CNC Programming
  Handbook*, delme bölümü.
- **Paso bölmesi** (SPEC 03 `depths` kuralı): delme boyu `H = z_top − z_uç`, paso `q` verilirse `n = ⌈H/q⌉` (`1e-9`
  toleransla), paso uçları `z_k = z_top − k·H/n`, `k = 1..n`, son `z_n = z_uç` tam. `q = None` → tek paso (`n = 1`).
- **Hareketler** (hepsi `x = 0`): başlangıç ve bitiş `R = (0, 0, z_top + cl)`.
  - `mode = "tam"` (derin delik, Fanuc `G83` mantığı): `k = 1` için `G1 → z_1`; her sonraki paso: `G0 → z_top + cl`
    (talaş tahliyesi), `G0 → z_{k−1} + e` (`e = retract`), `G1 → z_k`. Sonunda `G0 → z_top + cl`.
  - `mode = "kirma"` (talaş kırma, Fanuc `G73`/`G74` mantığı): her sonraki paso: `G0 → z_{k−1} + e`, `G1 → z_k`.
    Sonunda `G0 → z_top + cl`.
  - İlk `G1` başlangıcı `R`'dir (`z_top + cl`'den ilerlemeyle girilir, `e` kullanılmaz).
  Kontrolör çevrimi (`G74`/`G83`) yazılmaz; SPEC 21 kuralı (çevrim yok, her hareket açık) korunur.
- **İş mili**: delme sabit devirle (`G97`) yapılır: `x = 0`'da `G96` devri `n_max`'a kilitlenir, anlamsızdır →
  `css` verilirse `CamError`. İlerleme `feed` mm/dev (`G95`).
- **Ham malzeme**: `z_top ≤ stock.zmax + TOL`; `z_uç ≥ stock.zmin` (ayna tarafına delip geçme kapsam dışı, aksi `CamError`);
  borude `D ≤ stock.d` → `CamError` (hava delme; `D > d` delik büyütme olarak kabul).
- Kesici boy: `H > flute_length` → `CamError` (talaş kanalı gömülür).

### B. Ters bağlama
Parça Z'ye dik bir düzlem etrafında çevrilip yeniden bağlanır. Dönüşüm `z' = z_ref − z`, `x' = x` (yarıçap değişmez).
- Varsayılan `z_ref = stock.zmin + stock.zmax`: ham malzeme kendine gider (SPEC 29 frezedeki "stok merkezinden 180°" kuralının
  torna karşılığı). Kullanıcı yeni ön yüzü iş sıfırına almak isterse kendi `z_ref`'ini verir.
- **Profil**: her noktaya dönüşüm uygulanır; yansıma yönü ters çevirdiği için yayların `ccw`'si değişir; açık profil sonra
  `orient` ile yeniden ön→arka yapılır (kapalı profil kapalı kalır, yönü korunmaz).
- **Ham malzeme**: `CylinderStock(D, z_ref − zmax, z_ref − zmin, d)`.
- **Bağlama**: yeni `Setup(name, wcs, stock', fixtures')`; bağlama elemanları (ayna, punta) ikinci bağlamada yeniden
  verilir, birinciden dönüştürülmez (ayna çoğunlukla işlenmiş çaptan tutar; kullanıcının bilgisi). `wcs` varsayılan `G55`.
- **Radyal harita** (SPEC 22 `RadialMap`): sütun `i`'nin merkezi `z_i` → `z_ref − z_i`. Hedef ızgara, ikinci bağlamanın
  `RadialMap.from_stock(stock', cell, fixtures')` ızgarasıdır; stok hücreleri ters sırayla kopyalanır, stok dışındaki
  (bağlama elemanı) hücreler boş kalır. `dz` aynı olmalı ve sütun merkezleri `1e-9·dz` içinde örtüşmeli; aksi `CamError`.
  Stok sınırları hücre sınırı olduğundan (SPEC 22) varsayılan `z_ref` ve `z_ref − (zmin + zmax)`'in `dz`'nin tam katı
  olduğu her `z_ref` bu koşulu sağlar. Hacim korunur (rel 1e-12).

### C. Profilli kanal (`Recess`)
Girdi SPEC 27'nin `Recess`'idir: açık alt profil (ön→arka), `z_right` = ilk noktanın `z`'si (ön), `z_left` = son noktanın
`z`'si (arka), `x_top`. Takım kanal ucu (`GROOVE`), genişlik `w`, iki köşede burun yarıçapı `r`, `a = w − 2r` düz taban boyu.
Hesap dış çerçevede yapılır; iç tarafta SPEC 20 aynası.
- **Ön koşullar** (aksi `CamError`): profil her yerde `t_z ≤ TOL` (taban `z`'nin tek değerli fonksiyonu `x_b(z)`;
  arka kesim / alttan oyuk yok, dik duvar serbest); ilk ve son nokta `x = x_top` (± `TOL`); bütün noktalar
  `x ≤ x_top + TOL` ve dışta `x ≥ 0`; `W = z_right − z_left ≥ w + 2δ − TOL`.
- **Takımın alt sınırı**: sol köşe burun merkezi `C_L = (z_L, h)`, sağ `C_R = C_L + (a, 0)`. Takımın malzemeye dönük sınırı
  `S(z_L, h) = [C_L, C_R] ⊕ D(ρ)` (düz taban + iki burun), `ρ = r + δ` (`δ` talaş payı, ince pasoda 0).
- **Düşürme zarfı** (SPEC 06 drop-cutter'ın 2B karşılığı): `g(z)` = profilin `ρ` burun merkezi yolu
  (`cam.lathe.nose_path(profile, ρ, strict=False)`, budamalı; tek değerli profilde bu, yarıçapı `ρ` olan diskin profile
  düşürüldüğü yüksekliktir). Takımın inebileceği en alçak yükseklik
  `h_ρ(z_L) = max_{s ∈ [0, a]} g(z_L + s)` (kayan pencerede en büyük değer). `h_ρ` parçalı doğru + yaydır: `g`'nin parçaları,
  `a` kadar kaydırılmışları ve `g`'nin yerel tepelerinde yatay doğrular; kesin hesaplanır (örnekleme yok).
  Çanak biçimli profilde (`x_b` önce artmayan, sonra azalmayan) `h_ρ(z_L) = max(g(z_L), g(z_L + a))`.
- **Erişim aralığı**: takım kanal ağzının dışına taşmaz (komşu yüzeyler bilinmez, kanal ağzı iki yanda dik sanal duvar sayılır):
  `z_L ∈ [z_left + ρ, z_right − ρ − a]`. Aralık boşsa (`W < w + 2δ`) `CamError`.
- **Kaba (dalarak)**: SPEC 20 kanal kuralı: aralık boyu `span = z_right − z_left − 2ρ − a`; `span ≤ TOL` → tek dalış
  (`z_L` aralığın ortası), aksi `m = ⌈span / a⌉ + 1` dalış (`a ≤ TOL` iken `span > TOL` → `CamError`, tam yarıçaplı uçla çok
  dalış tanımsız), `z_L,j = z_left + ρ + j·span/(m − 1)`, `j = 0..m−1`, arkadan öne. Dalış: `G0` `C_x = x_top + cl + r` →
  `G1` `C_x = h_ρ(z_L,j)` → `G0` `x_top + cl + r`. Kaba her yerde en az `δ` pay bırakır; dalışlar arasındaki sırtlar
  ince pasoya kalır.
- **İnce (yanal, tek paso, önden arkaya)**: `ρ = r`. `G0` ile `z_L = z_right − r − a`, `C_x = x_top + cl + r` → `G1` aşağı
  `h_r(z_L)`'ye → `h_r` zarfı boyunca `G1`/`G2`/`G3` ile `z_L = z_left + r`'ye → `G1` `C_x = x_top + cl + r`'ye → `G0`
  güvenli noktaya. Zarf parçaları burun merkezi yolları olduğundan hareketler kesin doğru ve yaydır.
- **Programlanan nokta**: takımın `tip` numarası SPEC 20 kanal kuralıyla: `T = 3` → `P = C_L + (−r, −r)` (sol kenar, taban);
  `T = 4` → `P = C_R + (+r, −r)` (sağ kenar). İçte `T = 2` / `T = 1` (aynalı).
- **Çakma yok**: kaba ve incede her konumda `S(z_L, h)`'nin içi profilin altındaki malzemeyle kesişmez (yapı gereği; test
  edilir).
- **Kalan malzeme**: profil noktası `p`'nin kalan kalınlığı, ince paso boyunca süpürülen takım bölgesinin `p`'den
  düşey uzaklığı (`p`'nin üstündeki ilk takım sınırına kadar). İki tür bölge **ölçüm dışıdır** (kaçınılmaz):
  (1) SPEC 20 kuralıyla keskin içbükey köşenin `r / tan(θ/2)` komşuluğu, (2) kanal ağzı: `x > x_top − r` olan noktalar
  (sanal duvar yüzünden takım ağız köşesinin etrafından dönemez; ağız pahı / kırılması dış profil işlemidir).
  `e_max` = ölçülen bölgede en büyük kalan kalınlık.
  - Örnek (kapalı form): yarıçapı `R` olan yarım daire taban, `a > 0`: düz taban iki burunun arasında köprü kurar;
    `e_max = (R − r) − √((R − r)² − (a/2)²)`. `R = 3`, `w = 4`, `r = 0,4` → `e_max = 2,6 − √4,2 = 0,5506098…`.
    Tam yarıçaplı uç (`a = 0`, `r ≤ R`) → `e_max = 0` ve ince yol yarıçapı `R − r` olan tek yay.
  - `finish` `e_max > rest_max + 1e-9` iken `CamError` verir (mesajda `e_max`); varsayılan `rest_max = 0`.
    Sessizce malzeme bırakılmaz.
- Kaynak: Sandvik Coromant, *Metal Cutting Technology*, "Parting and grooving" (çok yönlü kanal ucuyla yanal profil tornalama);
  CAM araştırma notları, "Drop-cutter".

### D. Torna tezgâh profili (SPEC 30'un ertelenen bölümü)
SPEC 30'un "Torna yazıcısıyla ilişki" bölümündeki taslak burada kesinleşir. Uygulayan: "Postprosesörler ve tezgâh
profilleri" thread'i (`cam/post/` sahibi), `cam/model.py` doğrulama eki "CAM model arayüzü" thread'i (bkz. Dosyalar).
- `MachineProfile(kind = "lathe")` kuralları (aksi `CamError`): `controller = "fanuc"` (ileride başka torna dili);
  `y`, `tool_change_z`, `kinematics`, `presets` `None`; `x` ve `z` kursu ikisi birlikte verilir ya da ikisi de `None`.
  `x` kursu **çap** cinsindendir (kontrolörün gösterdiği `X`, SPEC 21 sistem A).
  **Dikkat:** `cam/model.py`'de torna takım yolunun `x`'i **yarıçaptır** (SPEC 00 Ek 2); profil sınırıyla karşılaştıran
  her kod yoldaki değeri `2·x`'e çevirir (aşağıdaki `X_m`). Yarıçapı doğrudan çap kursuyla karşılaştırmak kursu iki kat geniş gösterir.
- **Kurs**: makine koordinatı `X_m = 2·(x + o_x)`, `Z_m = z + o_z` (`Wcs.origin = (o_x, 0, o_z)`, yarıçap cinsinden; tornada
  genellikle `o_x = 0`). Her hareket ucu ve yayın süpürdüğü eksen yönü noktaları (SPEC 30 yay kuralı, `G18`'de `(x, z)`
  düzleminde) denetlenir; `G0` dahil. Takım değiştirme noktası `tool_change = (x_tc, z_tc)` aynı dönüşümle kurs içinde olmalı.
  Kurs varken `setup` zorunlu (SPEC 30 kuralı).
- **Devir**: sabit devirde `S = round(rpm)`, `G96`'da `G50` sınırı `S = round(rpm)`; ikisinde de `rpm_min ≤ S ≤ rpm_max`.
- **İlerleme**: torna ilerlemesi mm/dev'dir; tezgâh sınırı mm/dk. Muhafazakâr denetim: her kesme hareketinde
  `feed · S ≤ feed_max` (`S` yolun devir sınırı; `G96`'da gerçek devir `≤ S` olduğundan güvenli taraf).
- **Taret**: `tool_slots` verilmişse `1 ≤ T ≤ tool_slots` (`T` = takım `id`, SPEC 21 `T0101`).
- **Yol türü**: freze yolu (`plane = XY` veya `feed_mode = PER_MIN`) ve `kind = "mill"` profile torna yolu → `CamError`
  (SPEC 30'daki kuralın tersi). Eksenel delme yolu (A) torna yoludur.
- `post_lathe(ops, machine, setup, spindle, tool_change, program_no=1) -> str` = `check_machine` + `write_lathe(…,
  dialect_for(machine))` + SPEC 30'daki iki yorum satırı (`(POST <name> <controller>)`, doğrulanmamış profil uyarısı),
  `FANUC_TORNA` başlığından sonra.
- Örnek profil `cam/post/profiles/ornek-fanuc-torna.json`: `name = "ORNEK-FANUC-TORNA"`, `X` çap `[0, 400]`, `Z` `[-600, 0]`,
  `rpm_max = 4000`, `feed_max = 5000`, `tool_slots = 12`, `verified = false`.

## Dosyalar
- Yeni: `cam/torna_ek.py` (A, B, C), `tests/cam/test_torna_delme.py`, `tests/cam/test_torna_ters.py`,
  `tests/cam/test_torna_kanal.py`, `durum/40-torna-ek.md`.
- Kullanılır (değişmez): `cam/model.py`, `cam/profile.py`, `cam/geom2d.py`, `cam/lathe.py` (`nose_path`, `orient`, `mirror`,
  `tip_offset`), `cam/lathe_ops.py` (`TurnCut`), `cam/sim` (SPEC 22: `RadialMap`, `simulate_lathe`, `profile_rmap`),
  `cam/turn_features.py` (SPEC 27: `Recess`, yalnız testlerde).
- Dokunulmayacak: `cam/model.py`, `cam/gcode/`, `cam/post/`, `cam/sim/`, `cam/plan*.py`, `pyproject.toml`, `DURUM.md`,
  `docs/yol-haritasi.md`, diğer paketler.

### Başka sahiplere ek listesi (bu SPEC'in PR'ı yapmaz; koordinatör sırayla dağıtır)
| # | Sahip | Dosya | Ek |
|---|---|---|---|
| E1 | "CAM model arayüzü" | `cam/model.py` | `MachineProfile.validate()`: `kind = "lathe"` kabul, D bölümündeki kurallar (yeni alan yok) |
| E2 | "Postprosesörler ve tezgâh profilleri" | `cam/post/` | D bölümü: torna kursu (çap), devir, `feed·S`, taret, `post_lathe`, örnek torna profili; testleri `tests/cam/test_post_lathe.py` (bu SPEC'in K14–K16'sı) |
| E3 | SPEC 21 sahibi | `cam/gcode/lathe.py` | `write_lathe`/`read_lathe` eksenel delme yolunu kabul eder: takım `Tool` (`DRILL`/`CONE`), bütün noktalar `x = 0`, yay yok, `css = None`; `G97 S M3/M4`, `G0`/`G1 Z` satırları; okuyucu `tools` sözlüğünde `Tool`'u kabul eder |
| E4 | SPEC 22 sahibi | `cam/sim/lathe_shape.py` | `cutter_shape` eksenel takımı kabul eder: `x = 0`'da `Tool` `DRILL`/`CONE`, kesici bölge `(z, x)` düzleminde uç konisi + `flute_length` boyunda `[−D/2, D/2]` dikdörtgen (`r = 0`), taraf kuralı uygulanmaz (`x` aralığı `to_radial` ile `[0, D/2]`); gövde = sap (`shank`) |

E3 ve E4 olmadan A bölümünün yolları üretilir ve test edilir (K1–K5), yalnız G-code ve simülasyon çapraz kontrolü (K6) bekler.

## Arayüz
Hepsi `cam/torna_ek.py`'de. Hatalar `cam.model.CamError`.

### A. Delme
- `@dataclass DrillCut(feed: float, rpm: float, peck: float | None = None, mode: str = "tam", retract: float = 0.5, clearance: float = 1.0)`
  — `feed` mm/dev, `rpm` dev/dk, `peck` = `q`; `feed, rpm, retract, clearance > 0`, `peck` `None` veya `> 0`,
  `mode ∈ {"tam", "kirma"}`; aksi `CamError`.
- `tip_length(tool: Tool) -> float` — `L_uç`; `kind ∉ {DRILL, CONE}` veya `tip_angle = None` → `CamError`.
- `center_depth(tool: Tool, d_c: float) -> float` — `t = (d_c/2)/tan(φ/2)`; `d_c ≤ 0`, `d_c > D` → `CamError`.
- `lathe_drill(stock: CylinderStock, tool: Tool, cut: DrillCut, z_top: float, z_bottom: float, full_diameter: bool = False, name: str = "delme") -> Toolpath`
  — `full_diameter=True` ise `z_bottom` tam çap derinliğidir, uç `z_bottom − L_uç`'ye iner. Takım `DRILL`.
- `lathe_center(stock: CylinderStock, tool: Tool, cut: DrillCut, z_top: float, d_c: float, name: str = "punta") -> Toolpath`
  — tek paso, uç `z_top − center_depth(tool, d_c)`'ye; `peck`, `mode` yok sayılmaz: `peck` verilmişse `CamError`.
  Takım `CONE` veya `DRILL`.
- Dönen yol: `Toolpath(name, tool, start=(0, 0, z_top + cl), plane=ZX, feed_mode=PER_REV, rpm=cut.rpm, css=None)`,
  bütün noktalar `x = y = 0`, son hareket `start`'ta biter, kesme hareketlerinde `feed = cut.feed`, `G0`'da `None`,
  `validate()`'ten geçer, sıfır boylu hareket yok.

### B. Ters bağlama
- `flip_profile(profile: Profile, z_ref: float) -> Profile`
- `flip_stock(stock: CylinderStock, z_ref: float | None = None) -> CylinderStock` — `None` → `zmin + zmax`.
- `flip_setup(setup: Setup, fixtures: Sequence[CylinderStock], z_ref: float | None = None, wcs: Wcs | None = None, name: str | None = None) -> Setup`
  — stok `flip_stock`, `wcs` varsayılan `Wcs("G55")`, `name` varsayılan `setup.name + "-ters"`; `setup.stock` `CylinderStock`
  değilse `CamError`.
- `flip_rmap(rmap: RadialMap, setup: Setup, cell: float, z_ref: float | None = None) -> RadialMap` — `setup` ikinci bağlama
  (`flip_setup` çıktısı); `z_ref` `None` → ikinci bağlamanın stoğundan `zmin + zmax`. Izgara uyuşmazlığı → `CamError`.
  Girdi haritası değişmez. Sonuç doğrudan `simulate_lathe(..., initial=...)`'a verilir.

### C. Profilli kanal
- `recess_envelope(profile: Profile, tool: LatheTool, allowance: float = 0.0, side: str = "dis") -> list[Segment]`
  — `C_L` yolu (`h_ρ`), erişim aralığında, arkadan öne; dış çerçevede değil `side`'ın kendi çerçevesinde.
- `recess_rest(profile: Profile, tool: LatheTool, side: str = "dis") -> float` — `e_max`.
- `recess_rough(profile: Profile, x_top: float, stock: CylinderStock, tool: LatheTool, cut: TurnCut, allowance: float = 0.0, side: str = "dis", name: str = "girinti_kaba") -> Toolpath`
- `recess_finish(profile: Profile, x_top: float, stock: CylinderStock, tool: LatheTool, cut: TurnCut, rest_max: float = 0.0, side: str = "dis", name: str = "girinti_ince") -> Toolpath`
- Takım `GROOVE`; dışta `tip ∈ {3, 4}`, içte `{2, 1}`; `allowance ≥ 0`, `rest_max ≥ 0`. Dönen yollar SPEC 20 K16 genel
  kurallarına uyar (`start = P_A` SPEC 20 güvenli noktası, son hareket `P_A`'da, çapraz `G0` yok).
- `cut.a_p` kullanılmaz (dalış derinliği zarfla belirlenir; kenar boyu aşımını SPEC 22 `kenar_asimi` denetler).

## Kabul kriterleri
Geometrik değerlerde tolerans aksi yazılmadıkça mutlak `1e-9 mm`. Test geometrileri uydurmadır.

| # | Durum | Beklenen (kapalı form) |
|---|---|---|
| T1 | `D = 10`, `φ = 118°` | `L_uç = 5/tan 59° = 3,0043030951…` |
| T2 | `φ = 90°` / `60°`, `d_c = 6` | `t = 3` / `3·√3 = 5,1961524…` |
| T3 | `H = 25`, `q = 6` | `n = 5`, paso uçları `z_top − 5k` |
| T4 | stok `[0, 60]`, `z_ref = 60`, nokta `(40, 12)` | `(20, 12)`; `ccw` yay → `cw` |
| T5 | yarım daire taban `R = 3`, merkez `(30, 17)`, `x_top = 20`; `w = 4`, `r = 2` | ince yol tek yay, merkez `(30, 17)`, yarıçap `1`, `e_max = 0` |
| T6 | aynı taban, `w = 4`, `r = 0,4` | `e_max = 2,6 − √4,2 = 0,55060984…` |
| T7 | yamuk kanal `(35,20)→(32,17)→(28,17)→(25,20)`, `w = 3`, `r = 0,2` | ön yanakta `C_R` doğrusu `x − z = −15 + r√2`; tabanda `C_x = 17,2`, `C_R,z ∈ [30,68284…, 31,91716…]`; `e_max = 0` |

- [ ] K1 `DrillCut` doğrulamaları; `tip_length` (T1) ve `center_depth` (T2), `tip_angle = None`, yanlış tür, `d_c > D` →
  `CamError` — `tests/cam/test_torna_delme.py`
- [ ] K2 `lathe_drill` paso bölmesi (T3): paso sayısı, uçlar, son paso tam `z_uç`; `full_diameter=True` ucu `L_uç` kadar
  derine indiriyor; `peck = None` tek `G1` — `test_torna_delme.py`
- [ ] K3 Hareket dizisi: `"tam"`'da her paso arasında `z_top + cl`'ye `G0` ve `z_{k−1} + e`'ye `G0`; `"kirma"`da yalnız
  `z_{k−1} + e`; bütün noktalar `x = y = 0`; `G0`'larda `feed = None`, `G1`'lerde `feed = cut.feed`; `start` ve bitiş
  `(0, 0, z_top + cl)`; `validate()` geçiyor; `plane = ZX`, `feed_mode = PER_REV`, `css = None` — `test_torna_delme.py`
- [ ] K4 `lathe_center`: tek paso, uç `z_top − t` (T2); `peck` verilmişse `CamError` — `test_torna_delme.py`
- [ ] K5 Delme hataları: `z_uç < stock.zmin`, `z_top > stock.zmax`, borude `D ≤ d`, `H > flute_length`, `LatheTool` ya da
  `FLAT` takım → `CamError` — `test_torna_delme.py`
- [ ] K6 (E3 ve E4 birleşince) Çapraz kontrol: `write_lathe → read_lathe` gidiş-dönüşü delme yolunu SPEC 21
  toleranslarıyla (`x` yarıçapta `≤ 0,25·10⁻³`, `z` `≤ 0,5·10⁻³` mm: 3 basamaklı çıktının yarım basamağı) geri
  veriyor ve `G96` içermiyor; `simulate_lathe` dolu çubukta delinen hacim
  `π/4·D²·(H − L_uç) + π/3·(D/2)²·L_uç`'ye ızgara toleransıyla (`≤ π·(D/2)²·dz`) eşit, çarpışma yok —
  `test_torna_delme.py` (bağımlılık birleşmeden `NotImplementedError`)
- [ ] K7 `flip_profile` (T4): noktalar dönüşüyor, yay yönü değişiyor, açık profil ön→arka; iki kez uygulanınca aynı profil;
  `flip_stock` varsayılanı stoğu kendine götürüyor — `tests/cam/test_torna_ters.py`
- [ ] K8 `flip_setup`: stok, `wcs` (`G55`), ad varsayılanları, verilen bağlama elemanları aynen; kutu stok → `CamError` —
  `test_torna_ters.py`
- [ ] K9 `flip_rmap`: sütunlar ters sırada, aralıklar aynen; hacim rel 1e-12; ikinci bağlamada alttan / üstten taşan bağlama
  elemanı hücreleri boş; `dz` farklı veya sütun kayması `dz`'nin tam katı değil → `CamError`; girdi harita değişmiyor —
  `test_torna_ters.py`
- [ ] K10 İki bağlamalı senaryo: bağlama 1'de SPEC 20 `face` + `turn` (ön yarı), `flip_rmap`, bağlama 2'de `face` + `turn`
  (arka yarı) `initial` ile; toplam kaldırılan hacim analitik (rel 1e-9; kesitler hücre sınırına denk seçilir) ve son
  harita iki yüzü işlenmiş parçanın `profile_rmap`'ine eşit — `test_torna_ters.py`
- [ ] K11 Zarf: T5'te tek yay; T7'de yanak doğruları, taban seviyesi ve geçiş noktaları kapalı formla; zarf üzerindeki
  örnek noktalarda takım sınırı `S` profilin altına girmiyor (`dist ≥ ρ − 1e-9`) ve her örnekte en az bir temas var
  (`= ρ ± 1e-9`) — `tests/cam/test_torna_kanal.py`
- [ ] K12 Kaba: dalış sayısı `m` ve `z_L,j`; dalış tabanı `h_ρ(z_L,j)`; `allowance = δ` iken bütün örnek konumlarda
  profilden uzaklık `≥ r + δ − 1e-9`; `W < w + 2δ`, `a = 0` ve `span > 0` → `CamError` — `test_torna_kanal.py`
- [ ] K13 İnce: hareketler zarfla birebir (T5, T7), giriş ön sanal duvarda, çıkış arka sanal duvarda; `recess_rest` T5'te 0,
  T6'da kapalı form (rel 1e-12); `rest_max = 0`'da T6 → `CamError`, `rest_max = 0,56`'da geçiyor; arka kesimli profil,
  `x_top`'a dönmeyen profil, yanlış takım / uç → `CamError`; iç taraf (aynalı T7) dış sonucun aynası; programlanan nokta
  `T = 3` ve `T = 4` için SPEC 20 kanal kuralıyla — `test_torna_kanal.py`
- [ ] K14 (E1, E2) Torna profili doğrulaması: D bölümündeki her kural ayrı ayrı `CamError`; örnek profil yükleniyor,
  `save → load` eşit — `tests/cam/test_post_lathe.py`
- [ ] K15 (E2) Torna denetimi: `X` çap kursu `[0, 400]`, `o_x = 0`: `x = 200` geçer, `200,001` → `CamError` (mesajda op ve
  hareket sırası); `G0` ve yay çeyrek noktası yakalanıyor; `tool_change` kurs dışı → `CamError`; `rpm_max = 4000`:
  `G96` yolunda `rpm = 4000,4` geçer, `4000,5` → `CamError`; `feed = 0,3`, `S = 4000`, `feed_max = 1000` → `CamError`
  (`1200 > 1000`), `feed_max = 1200` geçer; `T13` (12 istasyon) → `CamError`; freze yolu torna profiline → `CamError` —
  `test_post_lathe.py`
- [ ] K16 (E2, E3) `post_lathe` çıktısı `write_lathe` çıktısına yalnız iki yorum satırı eklenmiş hâliyle eşit; eksenel
  delme yolu içeren program denetimden geçiyor — `test_post_lathe.py`
- [ ] `pytest` 0 failed, bu SPEC'in testlerinde 0 "uygulanmamış"; `ruff check .` ve `ruff format --check .` temiz

## Kapsam dışı
- Kontrolör çevrimleri (`G74`, `G75`, `G83`, `G84`), kılavuz çekme (SPEC 04b), tornada eksen dışı delme (C/Y eksenli,
  canlı takım), ayna tarafına delip geçme, delik dibinde bekleme.
- SPEC 29 planına bağlama: `on_delik_yok` → delme + `BORE`, `genel_girinti` → profilli kanal, ikinci bağlama planı.
  29 sahibinin sonraki eki (bu SPEC'in işlevlerini çağırır).
- Ters bağlamada otomatik bağlama elemanı yerleşimi, ayna sıkma boyu / taşma denetimi (SPEC 22 `ayna_carpma` dışında),
  karşı iş mili (alt iş mili) devri, punta ile destekleme hesabı.
- Alın kanalı (eksenel kanal), kanal ağzında pah, kanalda talaş kırma; kanal ucunun yanal kesmede eğilmesi.
- Kanal profilinin `Recess` dışındaki kaynakları (alttan oyuk / arka kesimli girinti: `t_z > TOL`).
- Torna profilinde `G28` / referans dönüşü, çok taretli tezgâh, Y ekseni; Siemens / Heidenhain torna dilleri.
