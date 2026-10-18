# SPEC 08 — Montaj kısıtları ve konum çözücü (Dalga 1)

## Amaç
`assy.model.Assembly` içindeki kısıtları (çakışık, eş eksen, mesafe, açı) sağlayan bileşen konumlarını
(`Component.T`) sayısal olarak bulan, kalan serbestlik derecesini sayan ve çelişkili kısıtı hata olarak
bildiren saf numpy çözücü.

## Teori

### Bilinmeyenler
Sabit olmayan (`fixed=False`) her bileşenin 6 serbestliği var: 3 öteleme + 3 dönme.
Dönme, o anki `R` üzerine **dünya ekseninde küçük dönme** olarak güncellenir (sol çarpım):
```
R' = exp([ω]×) R          t' = t + Δt          x = [Δt, ω]  (bileşen başına 6 sayı)
exp([ω]×) = I + sin θ [k]× + (1 − cos θ) [k]×²      θ = |ω|, k = ω/θ      (Rodrigues)
```
Böylece `R` hep ortonormal kalır (Euler açısı yok, gimbal kilidi yok).
Kaynak: Craig, *Introduction to Robotics*, Bölüm 2; Murray–Li–Sastry, *A Mathematical Introduction to
Robotic Manipulation*, Bölüm 2 (üstel koordinatlar).

### Referansların dünya değerleri ve türevleri
Yerel origin `p0`, yerel yön `d0` için (model: `Assembly.world`):
```
p = R p0 + t        d = R d0
δp = Δt + ω × (R p0) = Δt − [R p0]× ω
δd = ω × d          = −[d]× ω
```

### Kısıt artıkları
Her kısıt bir artık vektörü `r(x)` üretir; kısıt sağlanınca `r = 0`.
`a` ve `b` kısıtın iki referansı: `p_a, p_b` dünya origin'leri, `n` / `d` dünya birim yönleri.

| Kısıt | Referans çifti | Artık r | Kaldırdığı serbestlik |
|---|---|---|---|
| COINCIDENT | PLANE–PLANE | `n_a + n_b` (3) ; `(p_b − p_a)·n_a` (1) | 3 |
| COINCIDENT | POINT–POINT | `p_b − p_a` (3) | 3 |
| COINCIDENT | POINT–PLANE (her iki sıra) | `(p − q)·n` (1) | 1 |
| COINCIDENT | POINT–AXIS (her iki sıra) | `(p − q) × d` (3) | 2 |
| COINCIDENT | AXIS–AXIS | CONCENTRIC ile aynı | 4 |
| CONCENTRIC | AXIS–AXIS | `d_a × d_b` (3) ; `(p_b − p_a) × d_a` (3) | 4 |
| DISTANCE | PLANE–PLANE | `n_a + n_b` (3) ; `(p_b − p_a)·n_a − D` (1) | 3 |
| DISTANCE | POINT–PLANE (her iki sıra) | `(p − q)·n − D` (1) | 1 |
| DISTANCE | POINT–POINT | `|p_b − p_a| − D` (1), `D > 0` | 1 |
| DISTANCE | AXIS–AXIS | `d_a × d_b` (3) ; `|(p_b − p_a) × d_a| − D` (1), `D > 0` | 3 |
| ANGLE | PLANE/AXIS – PLANE/AXIS | `0 < θ < 180`: `d_a·d_b − cos θ` (1) | 1 |
| ANGLE | aynı, `θ = 0` | `d_a − d_b` (3) | 2 |
| ANGLE | aynı, `θ = 180` | `d_a + d_b` (3) | 2 |

Tabloda `p, q`: POINT ve PLANE/AXIS referanslarının origin'leri; `n`, `d`: PLANE normali / AXIS yönü.
`D` ve `θ`: `Mate.value` (mm / derece). ANGLE'da PLANE için yön = normal, AXIS için yön = eksen yönü.

**İşaret ve yön kuralları (taslak, onaya açık):**
- PLANE–PLANE çakışık ve mesafe kısıtında normaller **zıt** (yüz yüze temas, `n_b = −n_a`).
  Mesafe pozitif yönde: `b` düzlemi, `a` düzleminin normalinin gösterdiği tarafta `D` uzakta.
- POINT–PLANE mesafesi işaretli: nokta normalin gösterdiği tarafta `D` uzakta.
- AXIS yönleri eş eksende ve AXIS–AXIS mesafede serbest: `d_b = +d_a` de `−d_a` de kabul (çözücü başlangıca
  yakın olanı bulur).
- ANGLE `0` ve `180` için ayrı artık kullanılır, çünkü `d_a·d_b − cos θ` orada türevsizdir
  (Jacobian sıfır olur, serbestlik sayımı bozulur). Aynı nedenle uzaklık normlu artıklarda `D > 0` zorunludur;
  `D = 0` → `AssyError` ("COINCIDENT kullanın").

### Çözüm: Gauss–Newton, en küçük normlu adım
Tüm artıklar tek vektörde: `r(x)`, Jacobian `J = ∂r/∂x` (analitik, yukarıdaki türevlerle).
Her adımda:
```
δx = −J⁺ r          (J⁺: sözde ters, np.linalg.lstsq — en küçük normlu çözüm)
x ← x + α δx        (α = 1, ½, ¼, ... : |r| azalana kadar geri izleme, en az 2⁻¹⁰)
```
En küçük normlu adım, eksik kısıtlı bir bileşeni **başlangıç konumundan en az hareketle** taşır; böylece
çözüm başlangıca en yakın konumdur ve serbest kalan yönlerde bileşen yerinde durur.
Durma: `max|r| ≤ tol` (varsayılan `1e-10`). `max_iter` (varsayılan 50) içinde inmezse veya adım küçüldüğü halde
`|r|` artık azalmıyorsa (`‖Jᵀ r‖ ≈ 0`, `|r| > tol`) önce durağan noktadan kaçış denenir (aşağıda);
yine azalmıyorsa → **çelişkili kısıt**: `AssyError`; mesaj en büyük artığa
sahip kısıtın sırasını ve türünü yazar.
Kaynak: Nocedal–Wright, *Numerical Optimization*, Bölüm 10 (Gauss–Newton, doğrusal en küçük kareler).

### Serbestlik derecesi sayımı
Sayısal rank ile: `DOF = 6·n_serbest − rank(J)`; `rank` = `J`'nin tekil değerlerinden
`σ_i > 1e-8 · σ_max` olanların sayısı (`J` boşsa rank 0). Gruebler sayımı (kısıt başına sabit sayı çıkarmak)
fazla tanımlı ama tutarlı kısıtlarda yanlış sonuç verir (aynı kısıt iki kez → 2 kez sayılır); rank bunu doğru sayar.
Sayım çözülmüş konumda yapılır.

### Kenar durumlar
- Hiç sabit bileşen yok → `AssyError` (montaj dünyaya bağlı değil).
- Kısıtsız bileşen → hareket etmez, 6 serbestlik sayılır.
- İki ucu da sabit bileşende olan kısıt → bilinmeyeni yok; sağlanmıyorsa çelişki → `AssyError`.
- Desteklenmeyen kısıt/referans çifti (ör. CONCENTRIC PLANE–POINT) → `AssyError`.
- Başlangıç tam yanlış daldaysa (ör. çakışık düzlemlerin normalleri zıt değil tam aynı yönde) `n_a + n_b`
  artığının gradyeni sıfırdır (durağan nokta, `‖Jᵀ r‖ ≈ 0`, `r ≠ 0`). Çözücü serbest bileşenleri küçük sabit
  bir dönmeyle (|ω| = 1e-3 rad) iter ve devam eder (en fazla 3 kez); montaj CAD'deki gibi doğru dalda kapanır.
  Gerçek çelişkide itme işe yaramaz → `AssyError` ("yerel minimum / çelişki"). (Kullanıcı kararı, 2026-10-18.)
- Önce `assembly.validate()` çağrılır (bilinmeyen bileşen vb. → `AssyError`).

## Dosyalar
- Yeni: `assy/mates.py` (kısıt artıkları ve Jacobian'ları), `assy/solver.py` (çözücü, DOF sayımı),
  `tests/assy/test_mates.py`, `tests/assy/test_solver.py`, `durum/08-kisitlar.md`
- Dokunulmayacak: `assy/model.py` (arayüz sabit), diğer paketler, ortak dosyalar

## Arayüz

### `assy/mates.py`
- `rodrigues(omega: np.ndarray) -> np.ndarray (3,3)` — `exp([ω]×)`; `|ω| < 1e-12` → birim
- `skew(v) -> np.ndarray (3,3)` — `[v]×`, `skew(a) @ b == np.cross(a, b)`
- `residual(assembly: Assembly, mate: Mate) -> np.ndarray` — tablodaki artık (boyut kısıt türüne göre 1 veya 3/4/6);
  desteklenmeyen çift veya `D = 0` normlu mesafe → `AssyError`
- `jacobian(assembly, mate, unknowns: list[str]) -> np.ndarray (m, 6·len(unknowns))` —
  sütun düzeni: `unknowns[i]` için `[Δt (3), ω (3)]`; listede olmayan (sabit) bileşenin sütunu yok

### `assy/solver.py`
- `@dataclass SolveResult`:
  - `T: dict[str, np.ndarray]` — her bileşenin çözülmüş 4x4 dönüşümü (sabitler dahil, değişmeden)
  - `iterations: int`, `residual: float` (son `max|r|`), `dof: int`
  - `apply(assembly) -> None` — `T`'leri bileşenlere yazar
- `residuals(assembly) -> np.ndarray` — tüm kısıtların artıkları ard arda (mevcut `T`'lerle)
- `solve(assembly, tol=1e-10, max_iter=50) -> SolveResult` — **girdiyi değiştirmez** (kopya üzerinde çalışır)
- `dof(assembly) -> int` — mevcut konumda kalan serbestlik (çözmez)

## Kabul kriterleri
Konum toleransı `1e-9` mm, yön toleransı `1e-9` (birimsiz), aksi yazmadıkça.
- [ ] K1 `rodrigues`: `ω=0` → I; `ω = (0,0,π/2)` → `rot_z(90)` (1e-12); her `ω` için `is_rigid` — `tests/assy/test_mates.py`
- [ ] K2 Her tablo satırı için: elle kurulmuş sağlanan konumda `r = 0` (1e-12), bilinen bozulmada bilinen değer
  (ör. düzlem 5 mm kaçık → `r = 5`) — `test_mates.py::test_residual_*`
- [ ] K3 Analitik Jacobian = merkezi fark Jacobian'ı (h = 1e-6, mutlak 1e-6), her tablo satırı için, rastgele konumlarda — `test_jacobian_matches_fd`
- [ ] K4 Blok üstüne blok: 3 dik düzlem çifti çakışık, `B` keyfi başlangıçtan (≈20° dönük, ≈10 mm kaçık)
  kapalı form `T`'ye (1e-9 mm) iner; `dof = 0` — `test_solver.py`
- [ ] K5 Mil–delik: CONCENTRIC + PLANE–PLANE COINCIDENT → milin ekseni deliğin ekseninde, omuzu yüzeyde; `dof = 1` (eksen etrafında dönme)
- [ ] K6 Mesafe: PLANE–PLANE `D = 7.5` → yüzler arası 7.5 mm; POINT–PLANE ve POINT–POINT ve AXIS–AXIS mesafeleri tutuyor
- [ ] K7 Açı: menteşe (CONCENTRIC + düzlem) + ANGLE 30° → kanatlar arası açı 30° (1e-9 rad), menteşe ekseni üstündeki nokta yerinde; `θ = 0` ve `180` dalları
- [ ] K8 Zincir: A sabit, B → A, C → B; C'nin konumu kapalı formda (1e-9 mm)
- [ ] K9 DOF sayımı: kısıtsız 6; PLANE çakışık 3; CONCENTRIC 2; CONCENTRIC + düzlem 1; 3 düzlem çifti 0;
  aynı kısıt iki kez yazılınca sayı değişmez (rank); iki serbest bileşen toplamı
- [ ] K10 Çelişki → `AssyError`: aynı düzlem çiftine `D = 5` ve `D = 7`; iki sabit bileşen arasında sağlanmayan kısıt.
  Tam yanlış dal (normaller aynı yönde) çelişki değildir: çözülür, normaller zıt olur
- [ ] K11 Hata durumları → `AssyError`: sabit bileşen yok; desteklenmeyen çift; normlu mesafede `D = 0`; `validate` hataları
- [ ] K12 `solve` girdiyi değiştirmez; sonuç `T`'leri rijit (`is_rigid`); zaten sağlanmış montajda 0 iterasyon ve `T` aynen (1e-12); `apply` yazıyor
- [ ] K13 Değişmezlik: tüm montaj (sabit bileşen dahil) keyfi rijit `G` ile taşınınca çözüm `G·T` olur (1e-9)
- [ ] Tüm testler yeşil: `pytest` → 0 failed, bu SPEC'te 0 "uygulanmamış"; `ruff check .` temiz

## Kapsam dışı
- ~~Çakışık/zıt yön seçimi için kullanıcı bayrağı (`flip`)~~ → `Mate.flip` arayüz PR'ıyla eklendi (SPEC 00, Ek)
- Dişli, kam, teğet, yuva (slot), sınır (min/max) kısıtları; simetri kısıtı
- Sürükleme / kinematik simülasyon (serbest kalan serbestlikte hareket ettirme), çarpışma, girişim (SPEC 09)
- Montaj ağacı, alt montajlar, STEP montajı (SPEC 07); parça geometrisinden referans çıkarma (yüz seçme)
- Kısıtları gruplara bölme / sembolik ayrıştırma (büyük montaj hızı); en fazla birkaç düzine bileşen hedefleniyor
- Birden çok çözüm dalını listelemek: sadece başlangıca en yakın çözüm bulunur
