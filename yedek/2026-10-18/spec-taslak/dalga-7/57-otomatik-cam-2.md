# SPEC 57 — Otomatik CAM 2: stok ve bağlama seçimi, çok bağlamalı ve 3+2 yönelimli plan, takım değişimini azaltan sıralama

> **Durum: ONAYLI** (kullanıcı, 2026-10-18 16:06: "Dalga 7 taslakları 57, 58, 59, 61, 62, 63, 64 ve 72'yi önerileriyle onaylıyorum."; açık sorular önerilen yanıtlarla kapatıldı, bkz. Kararlar) (Dalga 7, hat A1; `yol-haritasi/dalga-6-ve-sonrasi.md` bölüm 4).
> Bağımlılık (kod): SPEC 29 (`cam/plan.py`: `plan_mill_features`, `MillPlan`, `MillOptions`, `Unplanned`; `cam/plan_turn.py`:
> `plan_turn`, `TurnPlan`; `cam/plan_verify.py`; `main`'de), SPEC 27 (`cam/features.py`: `recognize`, `Features`; `main`'de),
> SPEC 14 (`cam/setups.py`: `stock_from_bbox`, `bar_stock_from_bbox`, `check_setup`; `main`'de), SPEC 41 (`cam/multiaxis/indexed.py`:
> `from_normal`, `local_stock`, `local_mesh`; `Kinematics`, `RotaryAxis`; `main`'de), SPEC 40 (`cam/torna_ek.py`:
> `flip_profile`; `main`'de), SPEC 30 (`MachineProfile`; `main`'de), SPEC 10 (montaj-CAM ve bağlama kütüphanesi: `Fixture`
> gövdeleri; Dalga 5 H9, kodu henüz `main`'de değil — yalnız K9 için), SPEC 72 (süre; isteğe bağlı maliyet ağırlıkları).
> Hedef tezgâhlar: DMG MORI DMU 50 / 60 / 75 / 90 ve DMF 360 (3+2), NHC 5000 (yatay, B tablalı), NLX 2500 / 700 ve NTX 3000
> (torna, ters bağlama). Varsayılan kontrolörler: Sinumerik 840D sl, Heidenhain TNC 640; NTX / NLX'te MAPPS (Fanuc tabanlı).

## Amaç
SPEC 29 parçayı **yalnız üstten** ve en çok **iki bağlamayla** (ikincisi yalnız alt yüz alma) planlar; stok ve bağlamayı
kullanıcı verir; işlem sırası özellik sırasıdır, takım değişimi en azlanmaz. Yan yüzlerdeki ve alttaki özellikler
`ustten_erisilemez` / `alt_yuz` koduyla planlanmadan kalır. Bu SPEC, kuralları açık ve test edilebilir (kara kutu yok) şu
dört adımı ekler: (1) parça sınır kutusundan **stok** ve **bağlama** seçimi, (2) özellik erişimine göre **en az bağlama**
sayısıyla çok bağlamalı plan; döner eksenli tezgâhta (DMU, DMF, NHC) bir bağlamada birden çok **3+2 yönelim**, (3) öncelik
kısıtlarını koruyarak **takım değişimini en azlayan** sıralama, (4) tornada **ters bağlama** kararı. SPEC 50'nin Açık soru 1'i
(5 eksen kabada yönelim önerisi) burada cevaplanır: yönelim adayları düzlemsel yüz normallerinden ve delik eksenlerinden çıkar.

## Teori

### 1. Stok seçimi
Girdi: parça sınır kutusu `[b_min, b_max]`, boyut `(Lx, Ly, Lz)`; stok kataloğu (kullanıcı dosyası) satırları
`blok (a × b × c)` ya da `çubuk (Ø d, boy ≤ ℓ_max)`; yüz başına işleme payı `m` (varsayılan 1 mm), kavrama payı `g` (mengenede
çenenin tuttuğu yükseklik, varsayılan 5 mm; parça altına eklenir, son bağlamada alınır ya da kesilir), testere payı `s`.
Kural: blokta gereken iç ölçü `(Lx + 2m, Ly + 2m, Lz + m + g)`; katalogdaki her blok için parçanın **altı eksen
permütasyonu** denenir (parça stok içine döndürülebilir); uyanlardan **hacmi en küçük** olan seçilir, eşitlikte ilk katalog
satırı. Çubukta `d ≥ √(Lx'² + Ly'²) + 2m` (dairesel kesit tam kapsar; `Lx', Ly'` çubuk eksenine dik iki ölçü), boy
`Lz' + m + g + s`. Uyan stok yoksa `Unplanned("parca", "stok_yok", …)` ve plan durur (`strict` ise `CamError`).
Kullanıcı stok verirse seçim yapılmaz, yalnız kapsama denetimi (`stok_kucuk`).

### 2. Erişim yönü ve özelliğin dünya kimliği
Aday yönler `D`: altı ana yön `±X, ±Y, ±Z` ∪ düzlemsel yüzlerin dış normalleri ∪ delik eksenleri (`Part.planar_faces`,
`Part.holes`, `Part.cylindrical_faces`), açısal tolerans `0.5°` ile kümelenmiş. Her `d ∈ D` için çerçeve `F_d = from_normal(o, d,
x_hint)` (41) ve parça yerel çerçeveye taşınır (`Part.moved`); SPEC 27 `recognize` yerel çerçevede çalışır. Yerel çerçevede
**üstten erişilebilir** tanınan özellikler `S_d` kümesidir; SPEC 29'un `ustten_erisilemez` kuralı aynen geçerlidir (erişim
denetimi yeniden yazılmaz). Aynı özellik farklı çerçevelerde bulunabilir; kimliği dünya koordinatında anahtardır:
`(tür, ağırlık merkezi 1e-3'e yuvarlı, erişim yönü)`; delikte `(merkez, eksen, d)`. Hiçbir `S_d`'de bulunmayan yüz bölgesi
(27 tanımlayamadığı) `erisim_yok` olarak raporlanır.

### 3. Bağlama ve ulaşılabilen yönler
Bir **bağlama** = parçanın bağlandığı yüz yönü `c` (yüzü fikstüre dayalı, normali `−z_tabla`) + fikstür. Tezgâh türüne göre
o bağlamada ulaşılabilen yönler `R(c)`:
- **3 eksen** (`kinematics = None`): `R(c) = {−c}` (yalnız tablanın tersi, yani yukarısı).
- **Masa-masa / kafa-masa 5 eksen** (DMU, DMF; 41 `Kinematics`): `R(c) = {d : ∠(d, −c) ≤ θ_max, d ≠ c}`, `θ_max` devrilir eksenin
  sınırından (`RotaryAxis.min/max`) ve 44'ün eksen sınırı denetiminden; döner tabla (C) sınırsız varsayılır, sınırlıysa `R`
  daralır.
- **Yatay, tek döner tabla** (NHC 5000, B ekseni tablanın normaline paralel): `R(c) = {d : d ⊥ c}` (iş mili yataydır, tabla
  dönünce `c`'ye dik yönlerin hepsi; açı aralığı `B` sınırıyla kısılır).
- **Fikstür engeli:** mengene çene üstü `z_c`; yerel çerçevede tabanı `z_c + clearance` altında kalan yan özellik bu bağlamada
  ulaşılamaz (`cene_engeli`). Ayna (torna) bölüm 6'da.

### 4. En az bağlama: tam küme örtüsü
Özellik kümesi `U`, bağlama adayları `c ∈ C` (aday yönlerin tersleri), örtülen `K(c) = ⋃_{d ∈ R(c)} S_d` (çene engeli
düşülmüş). İstenen: `|B|` en küçük `B ⊆ C`, `⋃_{c∈B} K(c) = U`. Aday sayısı küçük (tipik ≤ 14) olduğundan **tam arama**:
boyut 1, 2, … alt kümeler sırayla denenir, ilk örten alt küme seçilir. Eşitlikte sırasıyla: toplam yönelim sayısı az,
ana yönler (`±X, ±Y, ±Z`) eğik yönlerden önce, yönler sözlük sırasıyla. `|C| > 16` ise `CamError` (aday sınırı, Açık soru 2).
Her özellik **ilk** örten bağlamaya ve orada **ilk** örten yönelime atanır (aynı özellik iki kez işlenmez). `U`'yu örtmeyen
özellikler `erisim_yok` (hiçbir bağlamada) ile raporlanır; sessizce atlanan özellik yoktur.
Örnekler (uydurma blok, her yüzde bir cep): 6 yüz → 3 eksende 6 bağlama; `θ_max ≥ 90°` masa-masa 5 eksende 2 (alt yüz ikinci
bağlamada); yatay B tablada 2 (`c = −Z`: dört yan; `c = −X`: üst ve alt). 5 yüz (alt boş) → 3 eksende 5, 5 eksende 1, yatayda 2.

### 5. Takım değişimini azaltan sıralama
Bir bağlamadaki işlemler `o_1 … o_n`, her birinin takımı `T(o)` ve yönelimi `F(o)`. Öncelik ilişkisi (DAG) SPEC 29'un
kurallarından gelir ve **açıkça kurulur**: yüz alma → aynı yöndeki her şey; kaba → aynı özelliğin finişi; punta → matkap →
kılavuz / havşa (aynı delik); cep → içindeki delik (29 sırası); yönelim içi z sırası 29'daki gibi. Maliyet:
`J = c_tc·N_tc + c_rot·N_rot`, `N_tc` = ardışık farklı takım geçişi + ilk takım (29 `tool_changes()` ile aynı sayım), `N_rot` =
ardışık farklı yönelim geçişi. Varsayılan `c_tc = 1, c_rot = 0.1` (bir döndürme takım değişiminden ucuz); 72 profili verilirse
`c_tc = t_tc`, `c_rot` = ortalama yönelim değişim süresi.
- **Alt sınır:** `N_tc ≥` farklı takım sayısı.
- **Tam çözüm** (`n ≤ 12`): alt kümeler üzerinde dinamik programlama, durum `(yapılmış işlemler kümesi, son takım, son yönelim)`;
  yalnız öncelikleri karşılanmış işlemler eklenir.
- **Sezgisel** (`n > 12`): "aynı takımla devam et; yoksa en çok hazır işlemi olan takıma geç; eşitlikte 29 sırası". Sonuç 29'un
  özgün sırasından kötüyse özgün sıra kullanılır (asla kötüleşmez). Sonuç DAG'ı ihlal etmez (her işlem öncüllerinden sonra).

### 6. Torna: ters bağlama kararı
Aynanın kavrama boyu `g_t`, kavrama çapı. Bağlama 1'de ayna stoğun bir ucunu `g_t` boyunca tutar; aynaya `g_t + clearance`'tan
yakın profil bölümü işlenemez. Kural: profilde boyu `≥ g_t` olan silindirik bölümlerden **çapı en büyük** olanı ikinci
bağlamanın kavrama yüzü seçilir (yumuşak çene, işlenmiş çap); birinci bağlama o bölümü ve aynadan uzak tarafı işler, parça
`flip_profile(profile, z_ref)` (40) ile ters çevrilir, kalan taraf ikinci bağlamada `plan_turn` ile planlanır. Uygun silindirik
bölüm yoksa `kavrama_yuzeyi_yok`. Tek bağlamada bütün profil işlenebiliyorsa (çubuktan, parça boyu `+ g_t` kadar uzun stok ve
kesme kanalı) ters bağlama yapılmaz. NTX 3000'de karşı iş mili devri (bağlamayı elle sökmeden) Açık soru 4.

### 7. Doğrulama
Her bağlama 29 `plan_verify` (`verify_mill` / `verify_turn`) ile simüle edilir; bağlama `k`'nın başlangıç stoğu bağlama
`k − 1`'in sonuç stoğudur (yerel çerçeveye dönüştürülmüş; 5 eksende 43 tri-dexel, 3 eksende 05 z-map sınırlı: Açık soru 3).

## Dosyalar
- Yeni: `cam/plan2/__init__.py`, `cam/plan2/stok.py` (katalog, stok seçimi), `cam/plan2/erisim.py` (aday yönler, `S_d`, `R(c)`),
  `cam/plan2/ortu.py` (tam küme örtüsü), `cam/plan2/sira.py` (öncelik DAG'ı, DP ve sezgisel sıralama), `cam/plan2/plan.py`
  (`plan_auto`, `plan_auto_turn`, `AutoPlan`), `tests/cam/plan2/test_stok.py`, `test_erisim.py`, `test_ortu.py`, `test_sira.py`,
  `test_plan_auto.py`, `test_plan_auto_turn.py`, `durum/57-otomatik-cam-2.md`.
- Kullanılır (değişmez): `cam/plan.py`, `cam/plan_turn.py`, `cam/plan_verify.py`, `cam/features.py`, `cam/setups.py`,
  `cam/multiaxis/indexed.py`, `cam/torna_ek.py`, `cam/post/machine.py`, `geometry/part.py` (`Part` arayüzü).
- Dokunulmayacak: tüm `*/model.py` (yeni `Unplanned` kodları düz metindir, arayüz değişmez), 29'un dosyaları.

## Arayüz
`cam.plan2.stok`:
- `@dataclass(frozen=True) StockSize(kind: str, a: float, b: float = 0.0, c: float = 0.0, max_len: float | None = None,
  name: str = "")` — `kind ∈ {"blok", "cubuk"}`; çubukta `a = d`. `load_catalog(path) -> tuple[StockSize, ...]` (JSON).
- `select_stock(bbox, catalog, m=1.0, g=5.0, saw=3.0) -> tuple[Stock | CylinderStock, np.ndarray]` — stok ve parçanın stok
  içindeki dönüşümü (4×4); uyan yoksa `CamError("stok_yok: …")`.
`cam.plan2.erisim`:
- `candidate_directions(part, ang_tol=0.5) -> tuple[np.ndarray, ...]`
- `accessible(part, d, stock, tol=1e-3, hole_d_max=20.0) -> Features` — yerel çerçevede tanınan, üstten erişilebilir özellikler.
- `reachable(c, profile: MachineProfile) -> Callable[[np.ndarray], bool]`
`cam.plan2.ortu`: `min_cover(universe: set, cover: dict[key, set]) -> tuple[key, ...]` — tam arama; örtülemeyen eleman varsa
örtülebilenlerin en küçük örtüsü ve kalan küme döner.
`cam.plan2.sira`:
- `precedence(ops: list[PlannedOp]) -> dict[int, set[int]]`
- `order_ops(ops, prec, c_tc=1.0, c_rot=0.1, exact_max=12) -> tuple[list[int], int, int]` — sıra, `N_tc`, `N_rot`; döngülü DAG
  → `CamError`.
`cam.plan2.plan`:
- `@dataclass(frozen=True) AutoOptions(mill: MillOptions = DEFAULT_OPTIONS, m=1.0, g=5.0, clearance=1.0, c_tc=1.0, c_rot=0.1,
  ang_tol=0.5, max_candidates=16, verify=True)`
- `@dataclass(frozen=True) AutoPlan(stock, clamps: tuple[Setup, ...], frames: tuple[tuple[Frame, ...], ...], plans:
  tuple[MillPlan, ...], order: tuple[tuple[str, ...], ...], tool_changes: int, rotations: int, unplanned:
  tuple[Unplanned, ...], checks: tuple[PlanCheck, ...])` — `summary()` ve `gcode(lib, dialect)` 29 ile aynı biçimde.
- `plan_auto(part, lib, material, machine: MachineProfile, catalog=None, stock=None, fixtures=(), options=AutoOptions())
  -> AutoPlan`
- `plan_auto_turn(outer, lib, material, options: TurnOptions, catalog=None, stock=None, grip=20.0, inner=None) ->
  tuple[TurnPlan, ...]` — bir ya da iki bağlama.
Yeni `Unplanned` kodları: `stok_yok`, `stok_kucuk`, `erisim_yok`, `cene_engeli`, `kavrama_yuzeyi_yok`, `aday_siniri`.

## Kabul kriterleri
Testlerde uydurma geometri ve uydurma katalog; beklenen değerin kaynağı test yorumunda (el hesabı, bu belgedeki kurallar).
- [ ] K1 Stok seçimi: `80 × 50 × 30` parça, katalog `{100×60×40, 90×60×40, 60×90×45}`, `m = 1, g = 5` → gereken `82 × 52 × 36`;
  seçilen `90×60×40` (hacim en küçük uyan); permütasyon testi: katalog yalnız `60×90×45` iken döndürülmüş yerleşim seçiliyor;
  uyan yok → `stok_yok` — `tests/cam/plan2/test_stok.py`
- [ ] K2 Çubuk: `40 × 30` kesitli parça → `d ≥ 50 + 2m = 52` (√(40² + 30²) = 50); katalogda Ø50, Ø55, Ø60 → Ø55 — `test_stok.py`
- [ ] K3 Aday yönler: altı yüzlü blok + 30° eğik pah yüzü + eğik delik → ana yönler, eğik yüz normali ve delik ekseni, kümeleme
  `0.5°` (0.3° farklı iki yüz tek aday) — `tests/cam/plan2/test_erisim.py`
- [ ] K4 En az bağlama (her yüzünde bir cep olan blok): 6 yüz → 3 eksen 6, masa-masa `θ_max = 110°` 2, yatay B tabla 2;
  5 yüz (alt boş) → 3 eksen 5, masa-masa 1, yatay B tabla 2; tam aramanın sonucu kaba kuvvetle (bütün alt kümeler) aynı boyutta —
  `tests/cam/plan2/test_ortu.py`
- [ ] K5 Çene engeli: yan yüzünde çene üstünün 2 mm altında tabanı olan cep o bağlamada atanmıyor, başka bağlamada atanıyor;
  hiçbir bağlamada ulaşılamıyorsa `cene_engeli` — `test_ortu.py`
- [ ] K6 Hiçbir özellik kaybolmuyor: rastgele (sabit tohum) 20 uydurma parçada her özellik ya tam bir `PlannedOp`'ta ya bir
  `Unplanned`'da; iki kez işlenen özellik yok (dünya kimliğine göre) — `tests/cam/plan2/test_plan_auto.py`
- [ ] K7 Sıralama, bilinen en iyi: (a) `A(T1)→B(T2)`, `C(T1)→D(T2)`: 29 sırası `A,B,C,D` `N_tc = 4`, sonuç `A,C,B,D` `N_tc = 2`
  (alt sınır); (b) `A(T1)→B(T2)→C(T1)`: `N_tc = 3` (zorunlu); (c) üç delik `punta(T3)→matkap(T4)→kılavuz(T5)`: 29 sırası 9, sonuç
  3; (d) iki yönelimde aynı takım: `N_tc = 1`, `N_rot = 1` — `tests/cam/plan2/test_sira.py`
- [ ] K8 Sıralama doğruluğu: rastgele DAG'larda (`n ≤ 10`) DP sonucu bütün topolojik sıraların kaba kuvvet en iyisine eşit;
  sezgisel sonuç her zaman ≤ 29 sırası ve DAG'ı ihlal etmiyor; döngülü DAG `CamError` — `test_sira.py`
- [ ] K9 Uçtan uca freze: üstte cep, iki yanda delik, altta yüz alma olan uydurma parça, DMU benzeri uydurma profil → 2 bağlama,
  ilkinde 3 yönelim; her bağlama `verify_mill` ile çakmasız ve `check_setup` temiz; G-code her bağlama için ayrı program;
  3 eksen profiliyle aynı parça 4 bağlama — `test_plan_auto.py`
- [ ] K10 Torna ters bağlama: iki ucunda farklı çap kademesi olan mil, `g_t = 20`: en büyük çaplı ≥ 20 mm silindir ikinci kavrama
  yüzü; iki `TurnPlan`, ikincisi `flip_profile` ile; `verify_turn` ikisinde de temiz; uygun silindir yoksa `kavrama_yuzeyi_yok`;
  yeterince uzun çubukta tek bağlama — `tests/cam/plan2/test_plan_auto_turn.py`
- [ ] K11 Determinizm ve hatalar: aynı girdi aynı plan (baytı aynı G-code); `|C| > max_candidates` → `aday_siniri`; `strict`'te
  her `Unplanned` `CamError`; kullanıcı stoğu parçayı kapsamıyor → `stok_kucuk` — ilgili test dosyaları
- [ ] Tüm testler yeşil, `ruff check .` ve `ruff format --check .` temiz, 0 "uygulanmamış"; OCCT gerektirenler `occt`,
  10 s'den uzun testler `slow`

## Kapsam dışı
- Eş zamanlı 5 eksen ve 3B yüzey işleme planı (06 / 06b / 50 strateji seçimi), serbest yüzeyli parçada bölge ayırma.
- Fikstürün otomatik tasarımı ve yerleşimi (yalnız katalogdaki mengene / ayna seçilir); sıkma kuvveti ve parça sehimi (67 / 32).
- Takım kütüphanesine yeni takım önerme (eksik takım `takim_yok` kalır), takım ömrüne göre bölme (59).
- Makine seçimi (parkta hangi tezgâh): ayrı iş; burada tezgâh profili girdidir. Süre ve maliyet: 72, 58.

## Kararlar (onayla kayda geçti, 2026-10-18 16:06; önerilen yanıtlar kabul edildi)
1. Bağlama sayısını en azlarken ikinci ölçüt yönelim sayısı mı, süre mi olsun? Karar: sırayla bağlama, yönelim, `J`; 72 birleşince
   süre ölçütü isteğe bağlı.
2. Aday yön sınırı 16 yeterli mi? Karar: 16; daha fazlası olağan dışı karmaşık parça demektir, `aday_siniri` ile kullanıcıya
   yönelim listesini kendisinin vermesi önerilir.
3. Bağlama 2 ve sonrasının başlangıç stoğu 3 eksende z-map ile tam temsil edilemez (yan yüzler). Karar: döner eksenli ya da çok
   yönlü planda 43 tri-dexel zorunlu; 43 yoksa her bağlama ham stokla doğrulanır ve not düşülür.
4. NTX 3000'de karşı iş miliyle parça devri ayrı bağlama mı sayılsın? `MachineProfile`'da karşı iş mili bilgisi yok (arayüz PR'ı
   gerekir). Karar: şimdilik iki bağlama sayılır ve plan notu "karşı iş mili devri uygun" düşer; alan ayrı arayüz PR'ında.
