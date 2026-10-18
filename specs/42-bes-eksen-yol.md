# SPEC 42 — Eş zamanlı 5 eksen takım yolu: takım ekseni yönelimi, doğrusallaştırma, ters zaman ilerlemesi

> **Durum: ONAYLANDI** (kullanıcı, 2026-10-18 10:38 UTC, proje sohbetinde yazılı onay: "SPEC … 41–44 metinlerini onaylıyorum"). Metin kullanıcı onayı olmadan değişmez. Bağımlılık: SPEC 41 (kinematik, `Frame`), SPEC 06 (drop-cutter),
> SPEC 05 (`body_steps`). Arayüz: `Move.axis` (41 ile aynı arayüz PR'ı).

## Amaç
Üçgen ağı yüzey üzerinde küresel uçlu takımla, takım ekseni her noktada bir **yönelim stratejisiyle**
(sabit, yüzey normali + öne / yana eğim, noktaya doğru / noktadan uzak) belirlenen, **çakmasız ve sap / tutucu
çarpışmasız** eş zamanlı 5 eksen ince işleme yolu üretmek; yolu tezgâh kinematiğiyle (41) eklem değerlerine
çevirirken **eklem uzayı doğrusallaştırma hatasını** sınırlamak ve `G93` ters zaman ilerlemesini hesaplamak.

## Teori

### Eksen boyunca drop-cutter (06'nın yeniden kullanımı)
Birim yön `a` boyunca drop: `F = from_normal(0, a, x_hint)` (41) çerçevesine ağ çevrilir (`local_mesh`),
SPEC 06 `drop` yerel `(x, y)`'de çalışır, sonuç geri çevrilir. Yerel `+z = a` olduğundan bu, takımı `−a`
yönünde yüzeye değene kadar indirmektir; 06'nın çakmazlık güvencesi aynen geçerlidir. `x_hint`: ilerleme
yönü, ona paralelse `+X`, o da paralelse `+Y`.

### Normal tahmini (ofset yüzeyden)
Küresel uçta düşey drop ile merkez yüzeyi `z_c(x, y) = drop(x, y) + R`, gerçek yüzeyin `R` ofsetidir; ofset
yüzeyin normali temas noktasındaki yüzey normaline eşittir. Merkezi fark (adım `h_n`, varsayılan `R/10`):
`n ∝ (−∂z_c/∂x, −∂z_c/∂y, 1)`, `∂z_c/∂x ≈ (z_c(x + h_n, y) − z_c(x − h_n, y)) / (2h_n)`. Düzlemde kesin;
eğri yüzeyde hata `O(h_n²)` artı ağın kiriş hatası.

### Yönelim stratejileri
Sürüş noktası `(x, y)` (06 `Raster` ile aynı sıra / nokta kuralı), merkez `c₀ = (x, y, z_c)`, normal `n`,
ilerleme yönü `f` (komşu sürüş noktalarından, `n`'e dik bileşeni birimlenmiş), yan yön `b = n × f`.
- `fixed(a)`: her noktada `a` (eğik sabit eksen; 3+2'nin eş zamanlı yolu).
- `normal(lead, tilt)`: önce öne eğim `a₁ = n·cos λ + f·sin λ` (eksen ilerleme yönüne doğru `λ` kadar),
  sonra `f` etrafında yana eğim `a = R_f(τ)·a₁` (41 `rotation`). `λ = τ = 0` → `a = n`.
- `toward(P)` / `away(P)`: `a = norm(P − c₀)` / `norm(c₀ − P)` (eksen `P` noktasından geçer / uzaklaşır).
- `max_tilt` (varsayılan 90°): `angle(a, +Z) > max_tilt` → `CamError`.

### Konumlama
Seçilen `a` ile küresel takım `c₀`'dan geçen `a` doğrultulu çizgi üzerinde eksen boyunca drop'la konumlanır:
uç `p = c − R·a`. Düzgün yüzeyde ve kesin normalde `c = c₀` (teğet konumdan `a·n > 0` yönünde aşağı inmek
çakma olurdu), yani strateji temas noktasını değiştirmez. Sonuç her zaman eksen boyunca drop olduğu için
çakmasızdır.

### Gövde çarpışması ve kaçınma
Takım çerçevesinde (`+z = a`) sap / tutucu basamakları `(ρ_j, H_j)` (SPEC 05 `body_steps`) için: düz uç drop
(SPEC 06, yarıçap `ρ_j`) `z_j = drop_flat(ρ_j)` gövdenin oturabileceği en alçak yüksekliktir. Çarpışma:
`z_j > z_uç + H_j + tol`. Çarpışma varsa yana eğim `τ_k = τ + k·Δτ` (`k = ±1, ±2, …`, mutlak değerce artan,
pozitif önce, `|τ_k − τ| ≤ tilt_max_avoid`) sırayla denenir, ilk çarpışmasız alınır; hiçbiri yoksa `CamError`
(nokta indeksi ve basamak).

### Yönelim sürekliliği
Ardışık iki noktada eksenler arası açı `> max_dangle` (varsayılan 5°) ise araya sürüş noktası eklenir
(06 uyarlamalı bölme gibi, `ds_min`'e kadar); `ds_min`'de hâlâ aşıyorsa `CamError`. Nokta eklenmesi aynı
uyarlamalı Z ölçütüyle (06: `tol`) de yapılır.

### Eklem uzayında doğrusallaştırma (TCP kapalı çıkış)
Kontrolör takım ucu kontrolü (TCP / RTCP) olmadan eklem değerlerini doğrusal enterpole eder:
`q(t) = q₀ + t(q₁ − q₀)`; ucun iş parçasındaki yolu `tip_w(t) = forward(q(t))` doğru değildir.
- Hata: konum `e_p(t) = dist(tip_w(t), [p₀, p₁])`, yönelim `e_a(t) = angle(a(t), slerp(a₀, a₁, t))`.
- `linearize(tp, kin, wcs, L, tol_p, tol_a)`: her hareket için `t ∈ {¼, ½, ¾}`'te hata ölçülür; aşan
  hareket orta noktada (`p` doğrusal, `a` slerp) ikiye bölünür, yinelenir (`max_depth`, varsayılan 12,
  aşılırsa `CamError`).
- Analitik kontrol (testler): A masalı 4 eksende, A eksenine uzaklığı `r` olan, aralarında `Δ` açısı bulunan
  iki uç noktası ve radyal eksen → makinede uç aynı yerde, yalnız A döner; uç iş parçasında yarıçapı `r` olan
  yayı izler, kirişten en büyük sapma orta noktada `r(1 − cos(Δ/2))`. `2^m` parçaya bölününce
  `r(1 − cos(Δ/2^{m+1}))`; gereken en küçük `m` kapalı formdur.

### Ters zaman ilerlemesi (G93)
Uç yolu boyu `L_k = |p₁ − p₀|`, istenen uç ilerlemesi `F` [mm/dk]: süre `t_k = L_k / F` [dk], `G93` değeri
`F_inv = 1 / t_k = F / L_k` [1/dk]. Yalnız yönelim değişen harekette (`L_k < 1e-9`) açısal ilerleme
`F_rot` [°/dk]: `t_k = max_i |Δθ_i| / F_rot`. `F_inv` üst sınırı `inv_max` (varsayılan 99999) aşılırsa `CamError`.

## Dosyalar
- Yeni: `cam/multiaxis/toolpath5.py` (yönelim, konumlama, gövde kaçınma, `finish5`),
  `cam/multiaxis/linearize.py` (`linearize`, `inverse_time`), `tests/cam/test_toolpath5.py`,
  `tests/cam/test_linearize.py`, `durum/42-bes-eksen-yol.md`.
- Kullanılır (değişmez): `cam/model.py`, `cam/dropcutter.py`, `cam/ops3d.py` (`Raster`), `cam/sim` (`body_steps`),
  `cam/multiaxis/kinematics.py`, `cam/multiaxis/indexed.py`.
- Dokunulmayacak: tüm `*/model.py`, 05 / 06 / 41 dosyaları, ortak dosyalar.

## Arayüz
`cam.multiaxis.toolpath5`:
- `drop_along(mesh: TriMesh, tool: Tool, point, a, x_hint=None) -> np.ndarray (3,)` — `point`'ten geçen `a`
  doğrultulu çizgi üzerinde eksen boyunca drop; takım ucu (WCS). Ağla örtüşme yoksa `CamError`.
- `surface_normal(mesh, tool, x, y, h_n=None) -> np.ndarray (3,)` — ofset yüzeyden birim normal.
- `@dataclass Orientation(kind: str, a=None, lead=0.0, tilt=0.0, point=None, max_tilt=90.0)` —
  `kind ∈ {"sabit", "normal", "noktaya", "noktadan"}`; eksik / fazla alan → `CamError`.
- `@dataclass Avoid(dtilt=2.0, tilt_max=30.0, tol=1e-6)`.
- `finish5(mesh, tool, raster: Raster, orient: Orientation, avoid: Avoid | None = None,
  max_dangle=5.0, floor=None) -> Toolpath` — `BALL` dışı takım → `CamError`; her `Move.axis` dolu, `frame = None`.
`cam.multiaxis.linearize`:
- `joint_path(tp, kin, wcs, L, prev=None) -> np.ndarray (n+1, 3 + k)` (41 `to_machine` ile aynı, `Move.axis` kullanır).
- `deviation(kin, wcs, L, q0, q1, p0, p1, a0, a1, t) -> (e_p, e_a)`.
- `linearize(tp, kin, wcs, L, tol_p=1e-3, tol_a=0.05, max_depth=12) -> Toolpath`.
- `inverse_time(tp, q: np.ndarray, F_rot: float | None = None, inv_max=99999.0) -> np.ndarray (n,)`.

## Kabul kriterleri
- [ ] K1 Eksen boyunca drop: yatay düzlem `z = z₀` üstünde, düşeyle `φ` açısı yapan `a` ile merkez `z₀ + R`'de ve
  uç `c − R·a` → uç Z'si `z₀ + R(1 − cos φ)` 1e-9; `a = +Z`'de 06 `drop` ile birebir — `tests/cam/test_toolpath5.py`
- [ ] K2 Normal tahmini: `β = 0°, 20°, 45°` eğik düzlemde `n = (−sin β, 0, cos β)` 1e-9; `ρ` yarıçaplı küre ağında
  açı hatası ≤ ağ kiriş açısı + `O(h_n²)` sınırı — `test_toolpath5.py`
- [ ] K3 Stratejiler: `normal(0, 0)` → `a = n`; `normal(λ, 0)` → `a·n = cos λ`, `a·b = 0`; `normal(0, τ)` → `a·f = 0`,
  `a·n = cos τ`; `noktaya(P)` → `P` eksen doğrusu üstünde 1e-9; `max_tilt` aşımı `CamError` — `test_toolpath5.py`
- [ ] K4 Konum: eğik düzlemde ve küre ağında her strateji için merkez `c₀`'da (düzlemde 1e-9, kürede kiriş hatası),
  uç `c₀ − R·a`; çakma yok: her uçta küre merkezinin ağa uzaklığı `≥ R − 1e-9` — `test_toolpath5.py`
- [ ] K5 Gövde: dik bir duvarın dibinde `normal(0, 0)` yolunda sap duvara çarpıyor (`z_j > z_uç + H_j`); `Avoid` ile
  seçilen eğim çarpışmasız en küçük `|τ_k|` (elle hesaplanan duvar açısıyla); kaçınılamayan durumda `CamError` — `test_toolpath5.py`
- [ ] K6 Süreklilik: ardışık eksen açısı ≤ `max_dangle` (her çift); yarım küre ağında `noktadan(merkez)` yolu — `test_toolpath5.py`
- [ ] K7 Doğrusallaştırma analitik: A masalı 4 eksende `r = 50`, `Δ = 30°` → orta nokta sapması `r(1 − cos 15°)` 1e-9;
  `tol_p = 1e-3` için bölüm sayısı kapalı formdaki `2^m`; bölünmüş yolda her `t ∈ {¼, ½, ¾}` sapması ≤ `tol_p` — `tests/cam/test_linearize.py`
- [ ] K8 Doğrusallaştırma genel: AC masa-masada rastgele (sabit tohum) 5 eksen yolu; `linearize` sonrası yoğun
  örneklemeyle (her harekette 101 nokta) konum sapması ≤ `tol_p`, yönelim ≤ `tol_a` (örneklenen noktalarda);
  döner eksen yokken (3 eksen) yol değişmiyor — `test_linearize.py`
- [ ] K9 Ters zaman: `F_inv = F / L` rel 1e-12; yalnız döner hareket `F_rot` ile; `L = 0` ve `F_rot = None` →
  `CamError`; `inv_max` aşımı `CamError` — `test_linearize.py`
- [ ] K10 Hatalar: `BALL` dışı takım, sıfır `a`, geçersiz `Orientation` / `Avoid`, `max_depth` aşımı → `CamError` — `test_toolpath5.py`
- [ ] Tüm testler yeşil, `ruff check .` ve `ruff format --check .` temiz, 0 "uygulanmamış"; 10 s'den uzun testler `slow`

## Kapsam dışı
- Yanak (swarf / flank) frezeleme, 5 eksen kaba işleme, düz ve torik uçla serbest eğim (torik uç 06b'den sonra
  ayrı ek), yay (G2/G3) içeren 5 eksen hareketler (yaylar kirişe bölünür, 41).
- Otomatik "en iyi" yönelim / eksen düzgünleştirme (B-spline), tekillik çevresinde yol yeniden planlama
  (yalnız 41'in tekillik kuralı ve `max_dangle` uygulanır).
- G-code yazımı (`G93`, `G43.4`, `TRAORI`, `M128`): postprosesör SPEC'i. Malzeme simülasyonu: 43. Tezgâh çarpışması: 44.

## Ek A — Eksen doğrusu başka geometriye takılınca (onaylandı: kullanıcının 2 dakika kuralı, koordinatör önerisi 2026-10-18 13:39 UTC, itiraz yok)
- Sorun: eksen boyunca drop, eksen doğrusu üstündeki her geometriyi hesaba katar. Takım yüksek bir duvara doğru
  eğilince doğru duvarı deler ve takım duvarın üstüne ya da arkasına oturur; sonuç çakmasızdır ama istenen
  temas noktasında değildir ve sap / tutucu basamak denetimi bunu her zaman yakalamaz.
- Kural: eksen boyunca drop'la bulunan merkez `c` ile sürüş noktası merkezi `c₀` arasında `|c − c₀| > tol`
  ise bu konum **çarpışma** sayılır (`tol` = `Avoid.tol`; `Avoid` yoksa 1e-6 mm). Düzgün yüzeyde ve kesin
  normalde `c = c₀` olduğundan (Teori, Konumlama) iyi noktalar etkilenmez.
- Sonuç gövde çarpışmasıyla aynıdır: `Avoid` varsa yana eğim adayları aynı sırayla denenir, aday da bu
  ölçütle ve basamak ölçütüyle sınanır; hiçbiri geçmezse ya da `Avoid` yoksa `CamError` (nokta indeksi,
  `|c − c₀|`).
- `floor` ile ağa değmeyen eksen drop'unda `c = c₀` alınır (ölçüt tetiklenmez).
- Kabul: K5'e ek: duvara doğru eğik sabit eksen (`sabit`, duvara 10°) ile duvar dibinde `Avoid` yokken
  `CamError`; `Avoid` ile seçilen eksen `|c − c₀| ≤ tol` sağlar. K4 yolları değişmez.
