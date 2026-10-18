# SPEC 32 — Kesme kuvveti, iş mili gücü ve ilerleme optimizasyonu (Kienzle)

> **Durum: TASLAK** (kullanıcı onayı bekliyor). Açık sorular `durum/32-kuvvet.md`'de.

## Amaç
Simüle edilmiş bir freze (SPEC 05) veya torna (SPEC 22) programının her hareketi için Kienzle modeliyle
kesme kuvveti, kesme gücü ve iş mili torkunu hesaplayan; bunları tezgâhın iş mili sınırlarıyla (güç, tork)
denetleyen ve ilerlemeyi **talaş incelmesi** (sabit en büyük talaş kalınlığı) ile güç/tork sınırına göre
yeniden ayarlayan saf numpy modülü. Bu adım bitince `optimize_feed(ops, stock, malzeme, sinirlar)` geometrisi
birebir aynı, yalnız `F` değerleri değişmiş bir program, hareket başına değişiklik gerekçesi ve eski / yeni
işleme süresi verir; bilinen bir kanal ve yan frezelemede güç ve tork kapalı formla tutar.

## Teori
Birim sistemi: kuvvet N, uzunluk mm, gerilme ve özgül kesme kuvveti N/mm² (= MPa), güç kW, tork N·m,
ilerleme mm/dk (`F`), mm/diş (`fz`), mm/dev (`f`), kesme hızı m/dk (`Vc`), devir dev/dk (`n`).
Kaynak: Kienzle & Victor (1957); König & Klocke, *Fertigungsverfahren 1*, Bölüm 3 (Kienzle denklemi);
Sandvik Coromant, *Metal cutting technical guide* (frezede ortalama talaş kalınlığı, güç, talaş incelmesi);
Altintas, *Manufacturing Automation*, Bölüm 2 (frezede kavrama açısı ve anlık talaş kalınlığı).

### Kienzle denklemi
Talaş kesiti `A = b·h` (`b` talaş genişliği, `h` talaş kalınlığı) için asıl kesme kuvveti:

`Fc = K · kc1.1 · b · h^(1 − mc)`,  özgül kesme kuvveti `kc(h) = K · kc1.1 · h^(−mc)` (`h` mm, `h0 = 1 mm`)

`kc1.1` [N/mm²] `b = 1 mm`, `h = 1 mm` için özgül kesme kuvveti, `mc` [−] eğim (`0 ≤ mc < 1`), `K` [−] toplam
düzeltme katsayısı (talaş açısı, aşınma, kesme hızı; varsayılan 1). `h ≤ 0` → `CamError` (`h^(−mc)` tanımsız).

### Güç ve tork (ortak)
- Talaş debisi `Q` [mm³/s] ve kesit üzerinde ortalama özgül kesme kuvveti `kc` ile kesme gücü:
  `P = Q · kc / 10⁶` [kW]  (N/mm² · mm³/s = N·mm/s = 10⁻³ W).
  Tornada `Q = vc·ap·f` olduğundan bu, `P = Fc · Vc / 60000`'in aynısıdır.
- İş mili torku `M = 60000 · P / (2π · n)` [N·m]  (`P` kW, `n` dev/dk; `9549.30·P/n`).
- Motordan istenen güç ve tork iş mili verimiyle `η` (`0 < η ≤ 1`) büyür: `P_motor = P/η`, `M_motor = M/η`.
  Denetim: `P/η ≤ P_maks` ve `M/η ≤ M_maks` (verilen sınırlar için). Bu iki sınır birlikte tipik S1 eğrisini
  verir: `M_kull(n) = min(M_maks, 9549.30·P_maks/n)`.

### Torna
Ana kesici kenar yaklaşma açısı `κr` (`LatheTool.kappa_r`, derece). `h = f · sin κr`, `b = ap / sin κr`:
`Fc = K · kc1.1 · ap · f^(1 − mc) · (sin κr)^(−mc)`. `kc` için `h = f·sin κr`.
- Sayısal örnek (testlerde): `kc1.1 = 1500`, `mc = 0.25`, `ap = 2`, `f = 0.2`, `κr = 90°` → `Fc = 897.2093 N`;
  `Vc = 200` → `P = 2.99070 kW`; çap 50 mm'de `n = 1000·200/(π·50) = 1273.24` → `M = Fc·25/1000 = 22.4302 N·m`.

### Freze: kavrama ve talaş kalınlığı
Düz parmak freze, çap `D`, diş sayısı `z` (`Tool.flutes`; `None` → `CamError`), yanal kavrama `ae` (`0 < ae ≤ D`),
eksenel derinlik `ap`. Takım bir yandan kavrar (yan frezeleme; `ae = D` kanal):
- Kavrama açısı `φe = arccos(1 − 2·ae/D)` [rad], `φe ∈ (0, π]`.
- Anlık talaş kalınlığı `h(φ) = fz · sin φ · sin κ`; freze için `κ = 90°` (`sin κ = 1`; küresel ve köşe radyüslü
  uçta da bu varsayım, kapsam dışına bakın).
- Ortalama talaş kalınlığı `hm = fz · (1 − cos φe) / φe = fz · (2·ae/D) / φe`. Kanal ve yarım kavrama: `hm = 2·fz/π`.
- En büyük talaş kalınlığı `hex = fz · sin(min(φe, π/2))`; `ae ≥ D/2` → `hex = fz`, değilse `hex = 2·fz·√(a(1 − a))`, `a = ae/D`.
- `fz = F / (n · z)`, `n = Toolpath.rpm`. Diş başına en büyük teğetsel kuvvet `Ft_maks = K·kc1.1·ap·hex^(1 − mc)`.
- Freze gücü ortalama talaş kalınlığıyla: `P = Q · kc(hm) / 10⁶` (Sandvik yöntemi; `h^(1−mc)`'nin kavrama
  ortalaması yerine `hm`, fark `mc = 0.25`'te < %2 — bilinçli seçim, kaynakla aynı).
- Sayısal örnek: `D = 10`, `z = 3`, `fz = 0.1`, `n = 3000` (`F = 900`), `ap = 3`, `kc1.1 = 1500`, `mc = 0.25`:
  | `ae` | `hm` | `Q` [mm³/s] | `P` [kW] | `M` [N·m] | `hex` |
  |---|---|---|---|---|---|
  | 10 (kanal) | 0.0636620 | 450 | 1.343797 | 4.277439 | 0.1 |
  | 5 | 0.0636620 | 225 | 0.671899 | 2.138720 | 0.1 |
  | 1 | 0.0310800 | 45 | 0.160762 | 0.511722 | 0.06 |

### Simülasyondan hareket başına yük
Simülasyon çıktısı yalnız **okunur**; SPEC 05 / 22 imzaları değişmez.
- Hareket `k`'nin kaldırdığı hacim `ΔV_k = steps[k−1].removed`. Süre `t⁰_k` ivmesiz (`accel = None`, aynı `rapid`)
  hareket süresidir (`cam.sim.move_time` / `lathe_move_time`); freze G1'de `t⁰ = 60·L/F`. `Q_k = ΔV_k / t⁰_k`
  (`t⁰_k = 0` → `Q = 0`). İvmeli süre kullanılmaz: ivme gücü düşürmez, yalnız süreyi uzatır.
- **Freze:** `ap_k = max_hücre (zmap_at(k−1) − zmap_at(k))` (hareketin en derin kesimi), eşdeğer kavrama
  `ae_k = min(D, Q_k · 60 / (ap_k · F))`. Dikdörtgen kesitli kesimde (düz takım, kanal ya da düz duvar yanında
  paso) bu, gerçek `ae`'dir; diğerlerinde aynı `Q`'yu veren eşdeğer dikdörtgendir. `SimResult.dexel is not None`
  (dexel modeli) → `CamError` (üst yüzey farkı alttaki malzemeyi görmez).
- **Torna:** `f = F` (`G95`) veya `F / n_e` (`G94`). Kesim yarıçapı `r_k` = adımın kaldırdığı aralıkların
  (`section_at(k−1)` eksi `section_at(k)`) en büyük dış yarıçapı. `n_e = rpm` (sabit devir) veya
  `min(1000·Vc / (2π·r_k), rpm)` (`G96`). `h = f · sin κr`, `M = 60000·P/(2π·n_e)`. Bilgi için `ap_k = Q_k·60 / (1000·vc_k·f)`,
  `vc_k = 2π·r_k·n_e/1000`.
- **Hava:** `ΔV_k ≤ v_tol` (varsayılan 1e-6 mm³) veya `G0` → yük sıfır (`P = M = 0`, `h = None`). Bağlantı adımları
  (`link = True`) ve `DrillOp` açılımı yük listesinde yer alır ama değerlendirilmez (`kind = "atlandi"`);
  delme kuvveti kapsam dışı ve bu, sonuçta `skipped` olarak **görünür** (sessiz atlama yok).

### Analiz bölütleri
Bir hareket malzemeye yolunun ortasında girebilir; ortalama `ΔV` girişteki tam kavramayı gizler. Bu yüzden analiz
programı hareketleri bölütlere ayırır: `split_moves(ops, seg)` her kesme hareketini (G1 eşit boylu, G2/G3 eşit açılı;
helis Z'si doğrusal paylaştırılır) boyu ≤ `seg` olan `m = ⌈L/seg⌉` parçaya böler, `G0`'ı bölmez, `F` ve diğer
alanları kopyalar; her yeni hareketin özgün `(op, j)` indeksini verir. Varsayılan `seg = D/2` (freze) ve
`seg = 2·nose_r`'den büyük olanı ile 1 mm (torna). Bölünmüş program aynı malzemeyi kaldırır (doğrular için birebir
aynı süpürme; yaylarda kiriş farkı ≤ `arc_tol`). Yükler bölünmüş programın simülasyonundan hesaplanır; bir özgün
hareketin yükü bölütlerinin **en kötüsüdür** (en büyük `P`, `M`, `ae`).

### İlerleme ayarı
Her kesme hareketi (veya `split=True` ise her bölüt) için yeni ilerleme `F' = F · c`:
1. **Talaş incelmesi (yalnız freze):** hedef en büyük talaş kalınlığı `hex* = target_hex` (verilmezse
   programlanan `fz`; kesme verisindeki `fz`'in `ae ≥ D/2` için önerildiği kabulü). `c_ince = hex* / hex(ae)`;
   `ae ≥ D/2` → 1 (programlanan `fz` korunur). Örnek: `ae/D = 0.1` → `c_ince = 1/0.6 = 1.6667`.
   Tornada `h = f·sin κr` kavramadan bağımsızdır: `c_ince = 1` (torna ilerlemesi yüzey ve talaş kırma ile sınırlıdır,
   yalnız düşürülür).
2. **Güç ve tork sınırı:** sabit devirde `Q ∝ f` ve `kc ∝ f^(−mc)` → `P ∝ c^(1 − mc)`, `M ∝ c^(1 − mc)`. Kapalı form:
   `c_P = (η·P_maks / P)^(1/(1 − mc))`, `c_M = (η·M_maks / M)^(1/(1 − mc))` (sınır yoksa veya `P = 0` → `+∞`).
   (Freze talaş incelmesinde `hm` de `c` ile orantılı büyür; aynı üs geçerlidir.)
3. `c = min(c_ince, c_P, c_M, max_factor)`, sonra `F' = min(F·c, feed_max)` (`feed_max` verilirse, ör.
   `MachineProfile.feed_max`). `c < min_factor` ise `F' = F·min_factor` ve hareket **aşırı yük** olarak kalır
   (sonuçta `overloads_after`'da görünür).
4. `F'` aşağı yuvarlanır: `F' = ⌊F'/resolution⌋·resolution` (varsayılan 0.1 mm/dk; sınırı aşmamak için aşağı).
   `F' ≤ 0` → `CamError`.
5. **Hava:** yük sıfır olan kesme hareketleri `air_feed` verilmişse `min(air_feed, feed_max)` ilerleme alır,
   verilmemişse değişmez.
- Gerekçe (hareket başına, en küçük terime göre): `"inceltme" | "guc" | "tork" | "en_cok" | "ilerleme_siniri" |
  "en_az" | "hava" | "degismedi"` (`c = 1` ve `F' = F`).
- `split=False`: özgün hareketin `c`'si bölütlerinin en küçüğüdür; program hareket sayısı değişmez.
  `split=True`: bölütler kendi `F'`'ini alır; aynı özgün harekete ait ardışık ve aynı `F'`'li G1 bölütleri yeniden birleştirilir.
- Geometri değişmez: yeni program aynı uç noktaları, yay merkezlerini, takımları, `rpm`/`css`'i taşır. Yeni
  programın simülasyonu aynı son z-haritasını (veya radyal haritayı) verir (`split=False`'da birebir).
- Doğrulama: `optimize_feed` yeni programı yeniden simüle eder ve yükleri yeniden hesaplar (`loads_after`);
  `F' ≤ F·c` ve aşağı yuvarlama nedeniyle sınırı aşan hareket yalnız `min_factor` ile kalanlardır.

### Süre kazancı
`t_before`, `t_after`: eski ve yeni programın verilen `Machine` (ivme dahil) ile toplam simülasyon süresi
(`SimResult.total_time` / `LatheSimResult.total_time`).

## Dosyalar
- Yeni: `cam/kuvvet.py` (Kienzle, kavrama, güç/tork, simülasyondan yük, iş mili denetimi),
  `cam/ilerleme_opt.py` (bölütleme, ilerleme ayarı, `optimize_feed`); `tests/cam/test_kuvvet*.py`,
  `tests/cam/test_ilerleme_opt*.py`; `durum/32-kuvvet.md`; `examples/kienzle_malzemeler.json` (örnek veri, kaynaklı).
- Dokunulmayacak: `cam/model.py` ve tüm `*/model.py` (aşağıdaki arayüz eki ayrı PR), `cam/sim/**` (yalnız okunur,
  imzalar değişmez), `cam/gcode/**`, SPEC 14 ve 30 dosyaları, `pyproject.toml`, `.github/`, `CLAUDE.md`,
  `BASLANGIC.md`, `DURUM.md`, `docs/yol-haritasi.md`, `core/**`.
- Bağımlılık: numpy. `cam.kuvvet` → `cam.model`, `cam.sim` (yalnız herkese açık işlevler). Yeni bağımlılık yok.

### Beklenen arayüz eki (A0, sahibi "CAM model arayüzü")
`MachineProfile`'a (SPEC 30) iki isteğe bağlı alan: `spindle_power_kw: float | None = None` (S1 sürekli güç, kW),
`spindle_torque_nm: float | None = None` (S1 sürekli tork, N·m); `None` → o sınır denetlenmez; verilirse `> 0`
ve sonlu, aksi `CamError`; `to_dict` / `from_dict`'te. A0 birleşmeden bu SPEC'in kodu `SpindleLimits`'i elle
kurarak çalışır; yalnız `SpindleLimits.from_profile` A0'ı bekler.

## Arayüz
Hepsi `cam.kuvvet` ve `cam.ilerleme_opt`'tan dışa açılır. Hatalar `cam.model.CamError`; `nan` / `inf` → `CamError`.

`cam/kuvvet.py`:
- `@dataclass(frozen=True) KienzleMaterial(name: str, kc11: float, mc: float)` — `kc11 > 0`, `0 ≤ mc < 1`.
  `to_dict` / `from_dict` (bilinmeyen anahtar → `CamError`).
- `load_materials(path) -> dict[str, KienzleMaterial]` — UTF-8 JSON `{"malzemeler": [{name, kc11, mc, kaynak}]}`;
  `kaynak` (metin) zorunlu; dosya yok, bozuk JSON, yinelenen ad → `CamError`.
- `specific_force(mat, h, K=1.0) -> float` — `K·kc11·h^(−mc)`; `h ≤ 0`, `K ≤ 0` → `CamError`. numpy dizisi de kabul eder.
- `kienzle_force(mat, b, h, K=1.0) -> float` — `K·kc11·b·h^(1−mc)`; `b ≤ 0` → `CamError`.
- `turning_force(mat, ap, f, kappa_r=90.0, K=1.0) -> float` — `0 < κr ≤ 90`.
- `engagement_angle(ae, D) -> float`, `mean_chip_thickness(fz, ae, D) -> float`, `max_chip_thickness(fz, ae, D) -> float`
  — `0 < ae ≤ D`, aksi `CamError`.
- `cutting_power(Q, kc) -> float` [kW], `spindle_torque(P, n) -> float` [N·m] — `n ≤ 0` → `CamError`.
- `@dataclass(frozen=True) SpindleLimits(P_max: float | None = None, M_max: float | None = None, eta: float = 0.8)`
  — sınırlar `> 0` veya `None`, `0 < eta ≤ 1`. `from_profile(profile: MachineProfile, eta=0.8)` (A0 alanları).
- `@dataclass Load(k: int, op: int, move: int | None, kind: str, ap: float, ae: float | None, h: float | None,
  kc: float | None, Q: float, P: float, M: float, F_t: float | None)` — `kind ∈ {"kesme", "hava", "atlandi"}`;
  `move` özgün `ops[op].moves` indeksi (`link` ve `DrillOp` → `None`); `h` frezede `hm`, tornada `f·sin κr`;
  `F_t` frezede `Ft_maks`, tornada `Fc`.
- `milling_loads(ops, result: SimResult, material, K=1.0, v_tol=1e-6) -> list[Load]` — `len == len(result.steps)`,
  `k` sırasıyla. `CamError`: dexel sonucu, `flutes is None`, `ops` ile `result` uyuşmuyor (adım ve hareket sayısı).
- `lathe_loads(ops, result: LatheSimResult, material, K=1.0, v_tol=1e-6) -> list[Load]` — aynı kurallar.
- `@dataclass Overload(k: int, op: int, move: int | None, kind: str, value: float, limit: float)` — `kind ∈ {"guc", "tork"}`;
  `value` `P/η` veya `M/η`, `limit` `P_max` veya `M_max`.
- `check_spindle(loads, limits: SpindleLimits, tol=1e-9) -> list[Overload]` — `value > limit·(1 + tol)` olan her
  `(k, kind)` için bir kayıt, `k` sırasıyla.

`cam/ilerleme_opt.py`:
- `split_moves(ops, seg: float | None = None) -> tuple[list[Toolpath | DrillOp], list[tuple[int, int | None]]]` —
  bölünmüş program ve her yeni `(op, yeni hareket)` için özgün hareket indeksi (`DrillOp` olduğu gibi kalır); `seg ≤ 0` → `CamError`.
- `@dataclass FeedChange(op: int, move: int, F_old: float, F_new: float, reason: str)`.
- `@dataclass FeedPlan(ops: list, changes: list[FeedChange], loads_before: list[Load], loads_after: list[Load],
  overloads_before: list[Overload], overloads_after: list[Overload], skipped: list[int], t_before: float, t_after: float)`
  — `loads_*` özgün hareketlere indirgenmiş (bölütlerin en kötüsü), `skipped` değerlendirilmeyen op indeksleri.
- `optimize_feed(ops, stock, material: KienzleMaterial, limits: SpindleLimits, *, feed_max: float | None = None,
  seg: float | None = None, split: bool = False, air_feed: float | None = None, max_factor: float = 2.0,
  min_factor: float = 0.1, target_hex: float | None = None, resolution: float = 0.1, K: float = 1.0,
  cell: float | None = None, machine: Machine | None = None) -> FeedPlan`
  - Freze (`Tool`) → `simulate` (z-haritası, `cell` varsayılanı 0.5); torna (`LatheTool`) → `simulate_lathe`
    (`cell` varsayılanı 0.25). Karışık takım türleri → `CamError`. Girdi `ops` değiştirilmez (kopya).
  - `CamError`: `max_factor < 1`, `0 < min_factor ≤ 1` değil, `resolution ≤ 0`, `feed_max`, `air_feed`,
    `target_hex ≤ 0`; simülasyon hataları olduğu gibi geçer.

## Kabul kriterleri
Testlerde uydurma malzeme verisi (`kc1.1 = 1500`, `mc = 0.25` gibi) ve uydurma geometri; beklenen değerin kaynağı test yorumunda.
- [ ] K1 Kienzle: `specific_force`, `kienzle_force`, `turning_force` Teori'deki sayısal örnekle rel 1e-12; `mc = 0` →
  `Fc = kc1.1·b·h`; `κr = 45°` için `b` ve `h` dönüşümü kapalı formla; `K = 1.2` çarpanı doğrusal — `tests/cam/test_kuvvet.py`
- [ ] K2 Kavrama: `engagement_angle` `ae = D` → `π`, `ae = D/2` → `π/2`; `hm` ve `hex` Teori tablosuyla rel 1e-12;
  `hm` yoğun sayısal ortalamayla (`∫ h dφ / φe`, ≥ 10⁵ nokta) rel 1e-9 — `test_kuvvet.py`
- [ ] K3 Güç ve tork: `cutting_power`, `spindle_torque` Teori tablosuyla rel 1e-6; tornada `Q·kc/10⁶ = Fc·Vc/60000`
  rel 1e-12 — `test_kuvvet.py`
- [ ] K4 Freze kanalı simülasyondan: kutu stokta düz takım (`D = 10`, `z = 3`) ile önce giriş hareketi, sonra
  kararlı bölgede `L = 40` mm `ap = 3` kanal hareketi → o hareketin `ap = 3` (1e-9), `ae` = 10 ve `P`, `M` Teori
  tablosundaki kanal satırıyla ızgara toleransında (`Δ = 0.5` mm'de rel ≤ `2Δ/D`); `G0` ve stok üstü hareketler `kind = "hava"`, `P = 0` —
  `tests/cam/test_kuvvet_sim.py`
- [ ] K5 Yan frezeleme: kanalın yanında `ae = 5` ve `ae = 1` paso → `ae`, `hm`, `P` tabloyla aynı tolerans — `test_kuvvet_sim.py`
- [ ] K6 Torna simülasyondan: SPEC 22 ile `CylinderStock D = 50`, `G95` sabit devir `n = 1273.24`, `ap = 2`, `f = 0.2`,
  `κr = 90°` boyuna paso → `P`, `M` Teori torna örneğiyle ızgara toleransında; aynı paso `G96 Vc = 200` → `n_e` ve `M`
  kapalı formla; `G94` → `f = F/n_e` — `test_kuvvet_sim.py`
- [ ] K7 İş mili denetimi: `P_max = 1.0 kW`, `η = 1` ile K4 kanalı → bir `guc` kaydı (`value = 1.343797`, `limit = 1.0`);
  K5 `ae = 5` pasosu → kayıt yok; `M_max` ile `tork` kaydı; `η = 0.8` değeri `P/0.8` yapar; `None` sınırlar denetlenmez;
  `from_profile` A0 alanlarını okur (`@pytest.mark` yok; A0 yoksa test `uygulanmamış`) — `test_kuvvet.py`
- [ ] K8 Talaş incelmesi: K5'in `ae = 1` pasosu, sınırsız güç → `F' ≈ 900/0.6 = 1500` (simülasyonun ölçtüğü `ae` ile
  kapalı form `F·hex*/hex(ae)` aşağı yuvarlanmış, 1e-9; `ae` K5 toleransında), gerekçe `inceltme`;
  `ae = 5` ve kanal → `degismedi`; `max_factor = 1.5` → `F' = 1350`, `en_cok`; `feed_max = 1200` → `ilerleme_siniri` —
  `tests/cam/test_ilerleme_opt.py`
- [ ] K9 Güç sınırı: K4 kanalı `P_max = 1.0`, `η = 1` → `c_P = (1/1.343797)^(4/3)`, `F'` buna göre aşağı yuvarlanmış,
  gerekçe `guc`; `loads_after`'da o hareketin `P ≤ 1.0` ve `P ≥ 1.0·(1 − 10⁻³)`; `overloads_after` boş; aynı sınırla
  tornada K6 pasosu için de kapalı form; `min_factor`'un altına düşen sınır → `en_az` ve `overloads_after`'da kayıt — `test_ilerleme_opt.py`
- [ ] K10 Geometri değişmez: rastgele (sabit tohum) 30 hareketlik freze programı `split=False` → yeni programın uç
  noktaları, merkezleri, `rpm`'i birebir aynı, yalnız `feed` farklı; son z-haritası `array_equal`; `t_after ≤ t_before`
  yalnız tüm `c ≥ 1` iken; girdi `ops` değişmemiş — `test_ilerleme_opt.py`
- [ ] K11 Bölütleme: `split_moves` G1 ve G2/G3 (helis dahil) için bölüt boyu ≤ `seg`, uçlar ve yay merkezleri doğru
  (1e-12), toplam boy aynı (rel 1e-12), eşleme doğru; bölünmüş programın son hacmi özgünle rel 1e-9 (yaylar `arc_tol`
  toleransında); hareketin yarısı havada başlayan kanalda `split=False` girişteki tam kavramayı kullanır (`c` kanal
  değeri), `split=True` hava bölütlerini değiştirmez ve tam kavramalıları ayrı ayarlar, ardışık eşit bölütler birleşmiş — `test_ilerleme_opt.py`
- [ ] K12 Hava ilerlemesi: `air_feed = 3000`, `feed_max = 2500` → yük sıfır kesme hareketleri `F' = 2500`, gerekçe
  `hava`; `air_feed = None` → değişmez; `G0` hiçbir zaman değişmez — `test_ilerleme_opt.py`
- [ ] K13 Görünür atlama: `DrillOp` içeren programda delme adımları `kind = "atlandi"`, `skipped` o op'u içerir,
  `DrillOp` değişmeden çıkar — `test_ilerleme_opt.py`
- [ ] K14 Malzeme dosyası: `load_materials` örnek dosyayı okur; `kaynak` eksik, `mc ≥ 1`, `kc11 ≤ 0`, yinelenen ad,
  bilinmeyen anahtar, bozuk JSON → `CamError`; `to_dict`/`from_dict` gidiş-dönüş — `test_kuvvet.py`
- [ ] K15 Hatalar: `h ≤ 0`, `ae > D`, `ae ≤ 0`, `n ≤ 0`, `κr ∉ (0, 90]`, `flutes = None`, dexel sonucu, `ops`–sonuç
  uyuşmazlığı, karışık freze + torna, geçersiz `max_factor` / `min_factor` / `resolution` / `feed_max` / `air_feed`,
  `nan` girdiler → `CamError` — `tests/cam/test_kuvvet_hatalar.py`
- [ ] Tüm testler yeşil, `ruff check .` ve `ruff format --check .` temiz, bu SPEC'in testlerinde 0 "uygulanmamış";
  10 s'den uzun testler `@pytest.mark.slow`

## Kapsam dışı
- Kesme kuvvetinin yönleri (ilerleme kuvveti `Ff`, pasif kuvvet `Fp`), anlık kuvvet zaman serisi, titreşim / tırlama
  (stabilite lobları), takım ve parça sehimi (sehim SPEC 45: H4 kuvvetiyle FEM).
- Küresel ve köşe radyüslü uçta değişken `κ` ile kesin talaş kesiti (burada `κ = 90°` ve eşdeğer dikdörtgen).
- Delme ve kılavuz kuvveti / torku (`DrillOp` görünür biçimde atlanır), diş çekme (`G32`/`G76`) kuvveti.
- Yay hareketinde takım kenarı ilerlemesinin merkez ilerlemesinden farkı (iç yaylarda `F·(R_yol − R)/R_yol` düzeltmesi).
- Talaş açısı, aşınma, kesme hızı için ayrı Kienzle düzeltme tabloları (tek `K` çarpanı var), takım ömrü (Taylor).
- İvme / sarsıntı sınırlı ilerleme planlaması, ileriye bakışlı hız; iş mili hızlanması, güç–devir eğrisinin S6 bölgesi.
- Devir (`S`) optimizasyonu: yalnız `F` değişir. Dexel modelli freze sonucu. 4–5 eksen.
- G-code'a doğrudan yazma: yeni program SPEC 04 / 21 / 30 yazıcılarıyla yazılır.
- `cam/model.py`, `cam/sim/` değişikliği.
