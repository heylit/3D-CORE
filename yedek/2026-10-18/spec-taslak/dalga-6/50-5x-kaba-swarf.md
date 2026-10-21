# SPEC 50 — 5 eksen kaba işleme, yanak (swarf) frezeleme, torik uçla serbest eğim, eksen düzgünleştirme

> **Durum: TASLAK** (Dalga 6, hat G3; `yol-haritasi/dalga-6-ve-sonrasi.md` bölüm 3). Kullanıcı onayı bekliyor.
> Bağımlılık (kod): **B0** (`PathMeta`), SPEC 41 (kinematik, `Frame`, `indexed`; `main`'de), SPEC 42 (eş zamanlı 5 eksen yol,
> `finish5`, `linearize`; metin onaylı, kod henüz `main`'de değil), SPEC 43 (tri-dexel; metin onaylı, kod yok), SPEC 44
> (tezgâh çarpışması; metin onaylı, kod yok), SPEC 06 (drop-cutter, katmanlı kaba; `main`'de), SPEC 06b (torik uç drop-cutter;
> taslak) — yalnız K6–K7 için. Hedef tezgâhlar: DMG MORI DMU 50 / 60 / 75 / 90, DMF 360 (masa-masa ve kafa-masa).

## Amaç
SPEC 42'nin bilerek kapsam dışı bıraktığı dört işi eklemek: (1) **5 eksen kaba**: birden çok yönelimde (3+2) stok bilinçli
katmanlı kaba işleme, hava kesmesini tri-dexel stokla atlayarak; (2) **yanak (swarf) frezeleme**: regle (cetvelli) yüzeyi
takımın yan yüzüyle tek pasoda işleme ve yanak hatasını formülle sınırlama; (3) **torik uçla serbest eğim** (42 yalnız
küresel uçtu); (4) **eksen düzgünleştirme**: çakmazlığı bozmadan yönelim dizisinin sarsıntısını azaltma.

## Teori

### 5 eksen kaba = yönelim kümesi + stok bilinci
Kullanıcı (veya otomatik öneri, Açık soru 1) yönelim listesi `F_1 … F_m` (41 `Frame`) verir. Her `F_i` için:
1. Parça ağı ve **o anki stok** yerel çerçeveye çevrilir (41 `local_mesh`; stok tri-dexel'den, aşağıda).
2. SPEC 06 katmanlı kaba yerel çerçevede çalışır (`ap`, `ae`, `allowance` → `PathMeta`).
3. **Hava kesmesi atlama:** her `G1` hareketi, o ana kadarki tri-dexel stokla ışın kesişimine bakar (43 `ray_tool`);
   kaldırdığı malzeme hacmi `< v_min` (varsayılan `0.01·ae·ap·L`) olan ardışık hareketler `G0`'a (güvenli yükseklikte
   bağlantı) çevrilir. Böylece ikinci yönelim ilkinin temizlediği yeri yeniden kesmez.
4. Yol 43 ile simüle edilir, stok güncellenir, sıradaki yönelime geçilir.
Sonuç `Toolpath` listesi, her biri `frame = F_i`, `meta.axis_mode = "3+2"`, `meta.strategy = "kaba"`.

### Yanak (swarf) frezeleme
Regle yüzey iki ray eğrisiyle: `S(u, v) = (1 − v)·C₀(u) + v·C₁(u)`, `u ∈ [0, 1]`, `v ∈ [0, 1]` (`C₀` alt, `C₁` üst ray; eş
parametreli çoklu doğrular). Cetvel doğrusu `ℓ(u)` yönü `g(u) = norm(C₁ − C₀)`.
- **Konumlama (orta nokta teğet):** silindirik kesen kısım (düz uç, yarıçap `R`) ekseni `a = g(u)`, eksen doğrusu
  cetvelin `n_m` yönünde `R` ötesinde (`n_m`: `v = ½`'deki yüzey normali, malzemeden dışarı). Uç noktası alt rayda,
  taban payı `allowance_z` kadar yukarıda: `p = C₀(u) + R·n_m + allowance_z·g(u)`.
- **Gelişebilir yüzeyde** (silindir, koni, teğet gelişebilir) yüzey normali cetvel boyunca sabittir: yanak hatası 0.
- **Gelişemez (bükülmüş) yüzeyde** normal cetvel boyunca döner; `Δφ(v) = angle(n(u, v), n_m)`. Kesit düzleminde (cetvele
  dik) takım dairesi ile yüzeyin teğet düzlemi arasındaki girme birinci mertebede `e(v) ≈ R·(1 − cos Δφ(v))`;
  bu SPEC'in **ölçtüğü** hata gerçek yüzeye girme (yoğun örneklemeyle), formül alt-mertebe sağlama içindir.
- **Hata denetimi:** `max_v e(v) > tol_swarf` → bölme yapılmaz, `CamError` (yüzey yanak frezelemeye uygun değil; nokta
  indeksi ve hata). Kaynak: Bedi / Menzel "two-point offset" yöntemleri hatayı küçültür; burada yalnız tek nokta + denetim
  (Kapsam dışı).
- Örnek: hiperbolik paraboloid `z = x·y / c`, cetveller `x = x₀`: `n ∝ (−y/c, −x₀/c, 1)`, `Δφ` kapalı formdur (test).

### Torik uçla serbest eğim
42'nin `finish5`'i küresel uç içindi. Torik (köşe radyüslü düz, `corner_r = r_c`, `R` dış yarıçap) takım eksen boyunca
drop'la konumlanır (06b torik drop, 42 `drop_along` kalıbıyla). Analitik kontrol: yatay düzleme `φ` eğik eksenle değen torik
takımda uç (eksen ucu) yüksekliği `z_uç − z₀ = r_c·(1 − cos φ) + (R − r_c)·sin φ`. Öne eğim (`lead`) torik uçta etkin kesme
yarıçapını büyütür; iz yüksekliği 06'nın scallop formülüyle, etkin yarıçap `R_eff = (R − r_c)/sin λ + r_c` (eksen ilerleme
yönünde `λ` eğik, düzlemde) kullanılarak hesaplanır.

### Eksen düzgünleştirme
42'nin yönelim dizisi `a_k` (birim). Düzgünleştirme: `a_k` dizisine sabit pencereli (genişlik `w`, tek) ağırlıklı ortalama
uygulanır ve birimlenir; her yeni `a_k` için 42 konumlama ve gövde denetimi yeniden yapılır; çakan / çarpan noktada eski
`a_k` korunur. Ölçüt: açısal ikinci fark `J = Σ_k angle₂(a_{k−1}, a_k, a_{k+1})` (ardışık açı farklarının farkı).
Düzgünleştirme `J`'yi artıramaz (artırıyorsa o adım reddedilir); 44 eksen sınırı ve 41 tekillik kuralı korunur.

## Dosyalar
- Yeni: `cam/multiaxis/rough5.py` (yönelim kümesiyle kaba, hava kesmesi atlama), `cam/multiaxis/swarf.py` (regle yüzey,
  konumlama, yanak hatası), `cam/multiaxis/smooth.py` (eksen düzgünleştirme), `tests/cam/test_rough5.py`,
  `tests/cam/test_swarf.py`, `tests/cam/test_smooth5.py`, `tests/cam/test_toric5.py`, `durum/50-5x-kaba-swarf.md`.
- Değişecek: `cam/multiaxis/toolpath5.py` (42'nin dosyası; yalnız `finish5`'e torik takım dalı) — 42 `main`'e girdikten
  sonra, 42 sahibi thread ile sıralı.
- Kullanılır (değişmez): `cam/model.py` (B0 ile), `cam/ops3d.py`, `cam/dropcutter.py`, `cam/multiaxis/indexed.py`,
  `cam/multiaxis/kinematics.py`, `cam/multiaxis/linearize.py` (42), `cam/sim/tridexel.py`, `cam/sim/simulate5.py` (43),
  44'ün çarpışma denetimi.
- Dokunulmayacak: tüm `*/model.py`, 06 / 41 / 43 / 44 dosyaları, ortak dosyalar.

## Arayüz
`cam.multiaxis.rough5`:
- `rough5(mesh: TriMesh, stock: Stock, tool: Tool, frames: list[Frame], cut: RoughCut, cell=1.0, v_min=None,
  machine: Machine | None = None) -> tuple[list[Toolpath], TriDexel]` — `RoughCut` 06'nın kaba parametreleri (`ap`, `ae`,
  `allowance`); boş `frames`, `BALL` dışı ve düz dışı takım, yönelimi +Z ile `max_tilt` üstü → `CamError`.
`cam.multiaxis.swarf`:
- `@dataclass RuledSurface(C0: np.ndarray (n, 3), C1: np.ndarray (n, 3))` — eş sayıda nokta, sıfır boy cetvel → `CamError`.
- `swarf(surface, tool: Tool, side: int = +1, allowance=0.0, allowance_z=0.0, tol_swarf=0.01, n_check=21) -> Toolpath` —
  `side` malzemenin hangi yanda olduğu (normal yönü); `FLAT` dışı takım, cetvel boyu > `flute_length` → `CamError`;
  `meta.strategy = "yanak"`, `axis_mode = "5"`, her `Move.axis = g(u)`.
- `swarf_error(surface, tool, u, side=+1, n_check=101) -> float` — gerçek yüzeye en büyük girme [mm].
`cam.multiaxis.smooth`:
- `smooth_axes(tp: Toolpath, mesh, tool, w=5, avoid=None, kin=None) -> tuple[Toolpath, float, float]` — yeni yol, `J_eski`, `J_yeni`.
`cam.multiaxis.toolpath5.finish5`: `tool.kind = FLAT` ve `corner_r > 0` (torik) kabul edilir; `corner_r = 0` düz uç → `CamError`.

## Kabul kriterleri
Testlerde uydurma geometri; beklenen değerin kaynağı test yorumunda.
- [ ] K1 Kaba, tek yönelim: `F = +Z` iken `rough5` 06 katmanlı kaba ile aynı yolu (hava atlama kapalıyken) üretiyor; kaldırılan
  hacim 43 ile `stok − parça − pay` (ızgara toleransı) — `tests/cam/test_rough5.py`
- [ ] K2 Kaba, iki yönelim: üst yüzünde dikdörtgen cep, 45° eğik yüzünde dik cep olan uydurma blok; `F_1 = +Z`, `F_2` eğik yüz
  normali → her iki cebin kaldırılan hacmi analitik (`a·b·h`), kalan malzeme payı `allowance` ± ızgara toleransı — `test_rough5.py`
- [ ] K3 Hava kesmesi: K2'de ikinci yönelimde `G1` olarak kalan hareketlerin her biri ≥ `v_min` malzeme kaldırıyor; ilk yönelimin
  temizlediği bölgede `G1` yok; `v_min = 0` iken atlama kapalı (yol 06 ile aynı) — `test_rough5.py`
- [ ] K4 Yanak, gelişebilir: dik silindir duvar (`ρ = 40`) ve koni (yarı açı 15°) üzerinde `swarf_error ≤ 1e-9`; uç noktası
  `C₀ + R·n_m + allowance_z·g` 1e-9 — `tests/cam/test_swarf.py`
- [ ] K5 Yanak, bükülmüş: hiperbolik paraboloid `z = xy/c` (`c = 200`, `x₀ ∈ [−20, 20]`, cetvel boyu 30): `swarf_error` yoğun örnekleme
  referansıyla 1e-6; küçük bükümde birinci mertebe `R(1 − cos Δφ_max)` ile %10 içinde (`Δφ` kapalı form); `tol_swarf` aşımı
  `CamError` ve nokta indeksi — `test_swarf.py`
- [ ] K6 Torik eğik konum: yatay düzlem, `R = 5`, `r_c = 1`, `φ = 0°, 10°, 30°, 60°` → uç yüksekliği `r_c(1 − cos φ) + (R − r_c) sin φ`
  1e-9; `φ = 0` 06 düz/torik drop ile birebir — `tests/cam/test_toric5.py`
- [ ] K7 Torik çakmazlık: eğik düzlem ve küre ağında torik `finish5` yolunun her noktasında tor yüzeyinin ağa uzaklığı ≥ `−1e-9`;
  `corner_r = 0` → `CamError` — `test_toric5.py`
- [ ] K8 Düzgünleştirme: gürültülü (sabit tohum) yönelim dizisi verilen yarım küre yolunda `J_yeni < J_eski`; her nokta çakmasız ve
  gövde çarpışmasız (42 denetimi); zaten düzgün dizide yol değişmiyor (1e-12) — `tests/cam/test_smooth5.py`
- [ ] K9 Hatalar: boş yönelim listesi, uyumsuz ray nokta sayısı, sıfır cetvel, cetvel boyu > kesici boy, düz uçla `finish5`,
  `w` çift → `CamError` — ilgili test dosyaları
- [ ] Tüm testler yeşil, `ruff check .` ve `ruff format --check .` temiz, 0 "uygulanmamış"; 10 s'den uzun testler `slow`

## Kapsam dışı
- Gerçek eş zamanlı 5 eksen kaba (sürekli değişen eksenle adaptif / trokoidal): 19 (adaptif) + 42 sonrası ayrı SPEC.
- Yanak hatasını küçülten iki nokta / çok nokta konumlama ve konik takımla yanak; yanak yolunda tabanla birlikte köşe işleme.
- Otomatik yönelim seçimi (görünürlük konisi, erişilebilirlik): Açık soru 1; 57 (otomatik CAM 2) ile ilişkili.
- Eksen düzgünleştirmenin B-spline / eniyileme sürümü, kontrolör tarafı yumuşatma (`COMPCAD`, `CYCLE832`): post / ileride.
- G-code yazımı: SPEC 51.

## Açık sorular
1. 5 eksen kabada yönelim listesi kullanıcıdan mı gelsin, yoksa parçanın düzlemsel yüz normallerinden otomatik mi önerilsin?
   Öneri: bu SPEC'te kullanıcıdan (veya 27 özellik tanımanın yüz normallerinden), otomatik seçim 57'de.
2. `tol_swarf` varsayılanı 0.01 mm mi? Atölye toleransına göre kullanıcı belirlesin; öneri 0.01.
