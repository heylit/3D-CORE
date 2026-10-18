# SPEC 41 — Tezgâh kinematiği ve 3+2 indeksli işleme

> **Durum: ONAYLANDI** (kullanıcı, 2026-10-18 10:38 UTC, proje sohbetinde yazılı onay: "SPEC … 41–44 metinlerini onaylıyorum"). Metin kullanıcı onayı olmadan değişmez. Çok eksen dizisinin ilk adımı: 41 → (42, 43) → 44.
> Arayüz PR'ına bağlı: `cam/model.py`'ye `Frame`, `Toolpath.frame`, `Move.axis`, `RotaryAxis`, `Kinematics`
> ("CAM model arayüzü" thread'i, ayrı PR). Bu SPEC arayüzü değiştirmez, kullanır.

## Amaç
En çok iki döner eksenli (masa-masa, kafa-kafa, kafa-masa; tek döner eksenle 4 eksen) bir tezgâhın
kinematiğini **ileri ve ters** çözen saf numpy modülü, ve bunun üstünde **3+2 indeksli işleme**: bir iş
düzlemi (`Frame`) tanımlanır, mevcut 3 eksen işlemleri (SPEC 03, 06) o düzlemde değişmeden çalışır, sonuç
WCS'ye ve makine eksen değerlerine (X, Y, Z, döner açılar) çevrilir. Postprosesörün kullanacağı Euler
açıları (ZXZ: Fanuc `G68.2`; sabit eksen XYZ: Heidenhain `PLANE SPATIAL`) da burada hesaplanır.

## Teori

### Dönme ve iş düzlemi
- Birim eksen `u` etrafında `θ` dönme (Rodrigues): `R_u(θ) = I + sin θ·K + (1 − cos θ)·K²`, `K = [u]×`.
  Pozitif `θ` sağ el kuralıyla `u` etrafındadır. Pivot `c`'den geçen eksen etrafında nokta dönmesi:
  `x ↦ c + R_u(θ)(x − c)`. Açılar arayüzde **derece**, içeride radyan.
- **İş düzlemi** `Frame(origin o, R)`: `R`'nin sütunları yerel `x, y, z` eksenlerinin WCS'deki birim
  vektörleridir. `‖RᵀR − I‖_max ≤ 1e-9` ve `det R > 0` olmalı. Nokta: `p_w = o + R·p_l`, `p_l = Rᵀ(p_w − o)`;
  vektörde `o` yok. 3+2'de takım ekseni yerel `+z`'dir: `a_w = R[:, 2]`.
- Kurucular:
  - `from_normal(o, n, x_hint)`: `z = n/|n|`, `x = norm(x_hint − (x_hint·z)z)`, `y = z × x`.
    `|n| = 0` veya `|x_hint × z| < 1e-9·|x_hint|` → `CamError`.
  - `from_zxz(o, α, β, γ)`: `R = R_z(α)·R_x(β)·R_z(γ)` (Fanuc `G68.2 I J K` sırası).
  - `from_xyz(o, a, b, c)`: `R = R_z(c)·R_y(b)·R_x(a)` (sabit eksenler etrafında önce X, sonra Y, sonra Z;
    Heidenhain `SPA SPB SPC`).
- Ters açılar (birebir gidip dönme testlenir):
  - ZXZ: `β = acos(R₃₃) ∈ [0°, 180°]`; `sin β > 1e-9` ise `α = atan2(R₁₃, −R₂₃)`, `γ = atan2(R₃₁, R₃₂)`.
    Tekil (`β ≈ 0°` veya `180°`): `γ = 0`, `α = atan2(R₂₁, R₁₁)`.
  - XYZ: `b = −asin(R₃₁) ∈ [−90°, 90°]`; `cos b > 1e-9` ise `a = atan2(R₃₂, R₃₃)`, `c = atan2(R₂₁, R₁₁)`.
    Tekil: `c = 0`, `a = atan2(−R₂₃, R₂₂)`.
  Kontrol: `α = 90°, β = 90°, γ = 0` → yerel `z` WCS'de `(1, 0, 0)`.

### Kinematik zincir (çarpımlar-üstel / product of exponentials)
Tüm eksenler **sıfır konumunda** (tüm eksenler 0) makine koordinatında tanımlanır:
- `RotaryAxis(name, carrier, u, pivot, min, max)`: `carrier ∈ {"masa", "kafa"}`; `u` birim, `pivot` eksen
  üstünde bir nokta; `min/max` derece (`None, None` → sürekli eksen, ör. C).
- Zincir sırası her taşıyıcıda **tabandan uca**: masa ekseni `t1` tabana yakın, iş parçası son masa ekseninin
  üstünde; kafa ekseni `h1` tabana yakın, iş mili son kafa ekseninin ucunda.
- `s` iş mili ekseni (uçtan iş miline doğru, varsayılan `+Z`), `g` sıfır konumunda iş mili ölçü noktası
  (varsayılan orijin). Takım ucu sıfır konumunda `tip₀ = g − L·s`; `L` takım ölçü boyu (`Tool.gauge_length`
  ya da açıkça verilen).
- Masa dönüşümü `W(θ) = Rot(t1) ∘ Rot(t2)`, kafa dönüşümü `H(q) = Trans(X, Y, Z) ∘ Rot(h1) ∘ Rot(h2)`
  (her `Rot` kendi pivotu etrafında, sıfır konumundaki eksenle; yoksa birim). İş parçası noktası `w` (WCS)
  sıfır konumunda makinede `w + o_wcs`'dedir (`Wcs.origin`; WCS eksenleri sıfırda makine eksenlerine paralel).

**İleri kinematik** `q = (X, Y, Z, θ₁[, θ₂])` →
`tip_w = W⁻¹(H(tip₀)) − o_wcs`, `a_w = R_Wᵀ·R_H·s` (`R_W`, `R_H` dönüşümlerin dönme kısımları).

**Ters kinematik — yönelim.** `a_w` verilince döner açılar. İki eksende her durum
**Paden–Kahan alt problem 2** biçimine iner: `exp(ω₁φ₁)·exp(ω₂φ₂)·p = q`:

| Yapı | `ω₁, φ₁` | `ω₂, φ₂` | `p` | `q` |
|---|---|---|---|---|
| masa-masa | `u_t2, −θ_t2` | `u_t1, −θ_t1` | `s` | `a_w` |
| kafa-kafa | `u_h1, θ_h1` | `u_h2, θ_h2` | `s` | `a_w` |
| kafa-masa | `u_t, −θ_t` | `u_h, θ_h` | `s` | `a_w` |

Alt problem 2 (`c = ω₁·ω₂`, `|c| < 1`):
`α = (c(ω₂·p) − ω₁·q)/(c² − 1)`, `β = (c(ω₁·q) − ω₂·p)/(c² − 1)`,
`γ² = (|p|² − α² − β² − 2αβc) / |ω₁ × ω₂|²`, `z = αω₁ + βω₂ ± γ(ω₁ × ω₂)`;
`γ² < −1e-12` → ulaşılamaz yön → `CamError`; `γ² ∈ [−1e-12, 0)` → `γ = 0` (tek çözüm).
Her `z` için **alt problem 1** (`exp(ωφ)x = y`: `x' = x − ω(ω·x)`, `y' = y − ω(ω·y)`,
`φ = atan2(ω·(x' × y'), x'·y')`): `φ₂` = `p → z` (`ω₂`), `φ₁` = `−(q → z)` (`ω₁`).
Örnek (kontrol): masa-masa AC, `u_A = +X`, `u_C = +Z`, `s = +Z` → `a_w = (sin A sin C, sin A cos C, cos A)`;
çözümler `(A, C)` ve `(−A, C + 180°)`.

- Tek döner eksen (4 eksen): yalnız alt problem 1; `|ω·p − ω·q| > 1e-9` → ulaşılamaz → `CamError`.
  Döner eksen yok: `a_w ≠ s` (1e-9) → `CamError`.
- **Tekillik:** `|ω₁ × q| < 1e-9` ise `φ₁` serbesttir (ör. AC'de eksen düşey, C belirsiz): `θ` önceki
  değerinde tutulur (önceki yoksa 0), diğeri alt problem 1 ile. `|ω₂ × p| < 1e-9` için simetrik.
- **Çözüm seçimi:** her çözüm açısı `θ + 360°k` adaylarıyla açılır. Sınırlı eksende `[min, max]` içindekiler,
  sürekli eksende önceki değere en yakın olan alınır (sarma çözülür: önceki 350°, hedef 10° → 370°). Geçerli
  adaylardan `Σ|θᵢ − θᵢ_önceki|` en küçük olan seçilir (önceki yoksa önceki = 0); eşitlikte birinci eksen
  açısı küçük olan. Geçerli aday yok → `CamError` (hangi eksen, hangi sınır).

**Ters kinematik — konum.** Açılar bilinince `H(tip₀) = W(p_w + o_wcs)` doğrusal eksenleri verir:
`(X, Y, Z) = W(p_w + o_wcs) − (Rot(h1) ∘ Rot(h2))(tip₀)` (kapalı form).

### 3+2 akışı
1. Kullanıcı `Frame` seçer (ör. eğik yüzün normalinden). Ham malzeme yerel çerçevede eksenlere hizalı değildir:
   `local_stock(stock, frame)` köşelerin yerel sınır kutusunu verir (03/06 girdisi için, güvenli taraf).
   Parça ağı `local_mesh(mesh, frame)` ile yerele çevrilir (SPEC 06 `TriMesh`).
2. 03 / 06 işlemleri yerel çerçevede değişmeden çalışır; sonuç `Toolpath`'ın `frame`'i atanır.
3. `to_world(tp)`: noktalar WCS'ye, her harekete `axis = R[:, 2]`; yaylar WCS'de G17 olmadığından
   `ε_yay` (varsayılan 1e-3 mm) kiriş sapmasıyla `G1`'lere bölünür (kiriş sayısı SPEC 05 formülü).
4. `to_machine(tp, kin, wcs, L, prev=None)`: her nokta için `q` (eklem değerleri) dizisi `(n+1, 3 + k)`.
5. `machine_toolpath(tp, kin, wcs, L, prev=None)`: tüm döner eksenler masadaysa ve yön sabitse, makine
   koordinatında `G17` `Toolpath` (döner eksen döndürmeli TWP'siz kontrolörler, ör. 4. eksenli GRBL): masa
   döndürmesi yerel `z`'yi `s`'ye taşıyan katı harekettir, yerel XY yayları makine XY'sinde yay kalır, merkez
   aynı dönüşümle taşınır. Kafada döner eksen varsa yaylı yolda `CamError` (eğik düzlem; postprosesör TWP kullanır).

## Dosyalar
- Yeni: `cam/multiaxis/__init__.py` (boş; modüller kendi yolundan import edilir), `cam/multiaxis/kinematics.py`
  (dönme, ileri / ters kinematik), `cam/multiaxis/indexed.py` (`Frame` kurucuları ve açıları, 3+2 akışı),
  `tests/cam/test_kinematics.py`, `tests/cam/test_indexed.py`, `durum/41-kinematik-3arti2.md`.
- Kullanılır: `cam/model.py` (arayüz PR'ından sonra `Frame`, `RotaryAxis`, `Kinematics`, `Move.axis`,
  `Toolpath.frame`), `cam/dropcutter.py` (`TriMesh`), `cam/ops2d.py` ve `cam/ops3d.py` yalnız testlerde.
- Dokunulmayacak: tüm `*/model.py`, SPEC 03 / 04 / 05 / 06 dosyaları, ortak dosyalar.

## Arayüz
`cam.multiaxis.kinematics`:
- `rotation(u, theta_deg) -> np.ndarray (3, 3)`; `rotate_about(x, u, pivot, theta_deg) -> np.ndarray` (`x` `(3,)` veya `(n, 3)`).
- `forward(kin: Kinematics, q, L: float, wcs: Wcs) -> (tip_w (3,), a_w (3,))`.
- `inverse_axes(kin, a_w, prev: tuple[float, ...] | None = None) -> tuple[float, ...]` — seçilmiş açılar (derece).
- `all_solutions(kin, a_w) -> list[tuple[float, ...]]` — sınırdan bağımsız temel çözümler (`(−180°, 180°]`).
- `inverse(kin, p_w, a_w, L, wcs, prev=None) -> np.ndarray (3 + k,)` — `(X, Y, Z, θ…)`.
`cam.multiaxis.indexed`:
- `from_normal(o, n, x_hint) -> Frame`, `from_zxz(o, α, β, γ) -> Frame`, `from_xyz(o, a, b, c) -> Frame`.
- `zxz_angles(frame) -> (α, β, γ)`, `xyz_angles(frame) -> (a, b, c)` (derece).
- `local_stock(stock: Stock, frame) -> Stock`, `local_mesh(mesh: TriMesh, frame) -> TriMesh`.
- `to_world(tp: Toolpath, arc_tol=1e-3) -> Toolpath` (`frame = None`, her `Move.axis` dolu).
- `to_machine(tp, kin, wcs, L, prev=None) -> np.ndarray (n+1, 3 + k)`.
- `machine_toolpath(tp, kin, wcs, L, prev=None) -> (Toolpath, tuple[float, ...])` — makine koordinatlı yol ve sabit açılar.

## Kabul kriterleri
- [ ] K1 Dönme: `rotation` bilinen açılarda (90°, 180°, rastgele) formülle 1e-12, ortonormal, `det = 1`;
  `rotate_about` pivot noktasını sabit bırakır — `tests/cam/test_kinematics.py`
- [ ] K2 `Frame`: `from_normal` (eğik düzlem, `x_hint` izdüşümü), `to_world ∘ to_local = I` 1e-12; ortonormal olmayan,
  `det < 0`, `n = 0`, `x_hint ∥ n` → `CamError` — `tests/cam/test_indexed.py`
- [ ] K3 Euler: `from_zxz`/`zxz_angles` ve `from_xyz`/`xyz_angles` gidip dönüş 1e-9 (tekil olmayan rastgele 100 açı);
  tekil durum kuralı (`γ = 0` / `c = 0`) ve matris eşitliği; `α = 90°, β = 90°, γ = 0` örneği — `test_indexed.py`
- [ ] K4 İleri kinematik, AC masa-masa: `a_w = (sin A sin C, sin A cos C, cos A)` 1e-12; pivot ofsetli masada
  `A = 90°`'de elle hesaplanmış uç noktası 1e-9 — `test_kinematics.py`
- [ ] K5 Ters kinematik: AC ve BC masa-masa, AB kafa-kafa, B kafa + C masa, 45° eğik (nutasyonlu) B eksenli masa
  için rastgele ulaşılabilir `(p_w, a_w)`: `forward(inverse(…)) = (p_w, a_w)` 1e-9; `all_solutions` iki çözümü
  `(A, C)` ve `(−A, C + 180°)` veriyor; 45° nutasyonlu yapıda 90°'den fazla eğim ulaşılamaz → `CamError` — `test_kinematics.py`
- [ ] K6 Seçim: sınır dışı çözüm eleniyor; önceki konuma en yakın çözüm seçiliyor; sürekli C'de sarma
  (önceki 350°, hedef 10° → 370°); geçerli aday yok → `CamError` — `test_kinematics.py`
- [ ] K7 Tekillik: AC'de `a_w = +Z` → C önceki değerinde kalıyor, A = 0; 4 eksen (tek A) ve 3 eksen (döner eksen yok)
  durumları; ulaşılamaz yön → `CamError` — `test_kinematics.py`
- [ ] K8 3+2 uçtan uca: 30° eğik yüzlü kama üstünde yerel çerçevede elle kurulmuş dikdörtgen cep yolu (yaylı köşeler)
  → `to_world` noktaları eğik düzlemde 1e-9, kiriş sapması ≤ `arc_tol`; AC masada `machine_toolpath` cep tabanının
  tüm noktalarını aynı makine Z'sinde verir (1e-9), yay yarıçapları korunuyor (1e-9) — `test_indexed.py`
- [ ] K9 4 eksen indeksleme: yatay A eksenli masada silindir çevresinde 0°, 90°, 180°, 270° iş düzlemlerinde aynı
  yerel delik yolu → makine yolları birebir aynı, açılar beklenen — `test_indexed.py`
- [ ] K10 `local_stock` köşeleri kapsıyor (her köşe kutunun içinde, en az bir köşe her yüzde); `local_mesh` geri
  çevrilince 1e-12 — `test_indexed.py`
- [ ] Tüm testler yeşil, `ruff check .` ve `ruff format --check .` temiz, 0 "uygulanmamış"; 10 s'den uzun testler `slow`

## Kapsam dışı
- Eş zamanlı 5 eksen yol üretimi, doğrusallaştırma, ters zaman ilerlemesi: SPEC 42. Simülasyon: SPEC 43.
  Tezgâh gövdesi çarpışması ve eksen sınırı denetimi hareket boyunca: SPEC 44.
- G-code yazımı (`G68.2`, `CYCLE800`, `PLANE SPATIAL`, `G43.4`/`TRAORI`/`M128`): postprosesör SPEC'i.
  Bu SPEC yalnız açıları ve makine değerlerini verir.
- Üç ve daha çok döner eksen, kinematik kalibrasyon, eksen hatası telafisi; doğrusal eksenlerin hangi gövdeyi
  taşıdığı (44); parçanın düzlemsel yüzünden otomatik çerçeve seçimi (özellik tanıma SPEC'i).
