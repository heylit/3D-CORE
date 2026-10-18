# SPEC 13 — Gerilme sonrası işlem (von Mises, düğüm gerilmesi) ve CalculiX çapraz kontrolü (Dalga 3)

## Amaç
3B çözümden mühendislik gerilmelerini çıkarmak (von Mises, asal gerilmeler, düğüme ortalanmış gerilme
tensörü), modeli CalculiX `.inp` olarak dışa aktarmak ve kendi çözücümüzü aynı ağda CalculiX C3D4 ile
karşılaştırmak. Bitince bir parçanın en yüksek von Mises gerilmesi güvenilir biçimde okunur (delikli plakada
Kt ≈ 3) ve sonuç bağımsız bir çözücüyle doğrulanmış olur.

## Teori

### Von Mises ve asal gerilmeler
Voigt düzeni SPEC 11 ile aynı: `σ = [σ_xx, σ_yy, σ_zz, τ_xy, τ_xz, τ_yz]`.
```
σ_vM = √( ½[(σ_xx − σ_yy)² + (σ_yy − σ_zz)² + (σ_zz − σ_xx)²] + 3(τ_xy² + τ_xz² + τ_yz²) )

        ┌ σ_xx  τ_xy  τ_xz ┐
    S = │ τ_xy  σ_yy  τ_yz │       asal gerilmeler σ1 ≥ σ2 ≥ σ3 = S'nin özdeğerleri
        └ τ_xz  τ_yz  σ_zz ┘
σ_vM = √( ½[(σ1 − σ2)² + (σ2 − σ3)² + (σ3 − σ1)²] )       σ1 + σ2 + σ3 = iz(S)
```
Değişmezlik: `S' = R S Rᵀ` için asal gerilmeler ve `σ_vM` aynıdır. Hidrostatik gerilmede `σ_vM = 0`,
tek eksende `σ_vM = |σ|`, saf kaymada `σ_vM = √3 |τ|`.

### Düğüm gerilmesi (gerilme düzleştirme)
tet4'te gerilme eleman içinde sabittir ve elemanlar arasında süreksizdir. Düğüm gerilmesi, düğümü içeren
katı elemanların gerilmelerinin **hacim ağırlıklı ortalamasıdır**:
```
σ_düğüm(i) = Σ_e∋i V_e σ_e / Σ_e∋i V_e
```
Düzgün gerilme alanında tam (her düğüm aynı `σ`). Sınırda gradyan dik olduğunda değeri alttan yaklaşır;
gerilme yığılması bölgesinde yerel inceltme (SPEC 12 `Refine`) gerekir. Bu basit ve öğretici yöntem seçildi;
SPR (Zienkiewicz–Zhu süper yakınsak düzeltme) kapsam dışıdır.

### Delikli plaka (Kirsch) ve sonlu genişlik
Sonsuz plakada çapı `d` olan delik, uzak alan çekmesi `σ` altında delik kenarında (`θ = 90°`) `σ_xx = 3σ`,
`θ = 0°`'da `σ_yy = −σ` verir. Genişliği `W` olan plakada brüt kesite göre (Heywood):
```
Kt_n = 2 + (1 − d/W)³          Kt_g = Kt_n / (1 − d/W)          d/W = 0.1  →  Kt_g = 3.032
```
Plaka kalınlığı boyunca Kt biraz değişir (orta düzlemde yüksek, yüzeyde düşük); ölçüt kalınlık boyunca
ortalamayı kullanır.

### CalculiX eşlemesi
| Bizde | CalculiX |
|---|---|
| `bar1d` (1B model) | `T3D2`, `*SOLID SECTION` alanı `A`; 1B modelde bütün düğümlerde `uy = uz = 0` |
| `tet4` (3B model) | `C3D4`, `*SOLID SECTION` (alan satırı yok); düğüm sırası pozitif hacimli (gerekirse 2. ve 3. düğüm yer değiştirir) |
| `Material(E, ν)` | `*MATERIAL`, `*ELASTIC` `E, ν` |
| `BC(node, dof, value)` | `*BOUNDARY` `node, k, k, value` (`k = 1, 2, 3`) |
| `Load(node, dof, value)` | `*CLOAD` `node, k, value` |
| Voigt `xx, yy, zz, xy, xz, yz` | `*EL PRINT S`: `sxx, syy, szz, sxy, sxz, syz` (aynı sıra) |

C3D4 tek integrasyon noktalı doğrusal tetrahedrondur, SPEC 11 `tet4` ile matematiksel olarak aynıdır: aynı ağda
yer değiştirme, tepki ve eleman gerilmesi `.dat` dosyasının yazdırma hassasiyeti (7 anlamlı basamak) içinde
eşit çıkmalıdır. Tepki tanım farkı: CalculiX `RF = K u`, bizde `R = K u − F` (tests/reference/README.md).
Sayı biçimi: CalculiX bir sayı alanını en çok 20 karakter okur (`repr(-7.850462293417722e-16)` 22 karakterdir ve
ccx onu reddeder; ön hesapta görüldü). Bu yüzden her gerçel sayı `format(x, ".12e")` ile yazılır (13 anlamlı basamak,
en çok 20 karakter); geri okunan değerin göreli hatası `≤ 5e-13`.

Kaynaklar: CalculiX CrunchiX User's Manual 2.21 (C3D4, T3D2, *SOLID SECTION, *EL PRINT); Pilkey–Pilkey,
*Peterson's Stress Concentration Factors*, 3. baskı, Bölüm 4 (sonlu genişlikte delik); Heywood, *Designing
Against Fatigue* (1962); Zienkiewicz–Taylor–Zhu, Bölüm 14 (gerilme düzleştirme).

## Dosyalar
- Yeni: `fileio/calculix.py`, `tests/unit/test_post_gerilme.py`, `tests/fileio/test_calculix_yazici.py`,
  `tests/benchmarks/test_kirsch.py`, `tests/reference/test_calculix_tet4.py`, `durum/13-calculix.md`
- Değişecek: `core/post.py` (yeni fonksiyonlar, mevcutlar aynı), `core/elements/__init__.py` (sözleşme metni:
  katı elemanlar `volume` da sağlar), `tests/reference/calculix.py` (testlerin kendi C3D4 yazıcısı ve gerilme
  okuması; test oturumu yazar), `tests/reference/README.md` (tablo satırı)
- Dokunulmayacak: `core/model.py` (`Result` aynı), `core/solver.py`, `core/elements/tet4.py`, `mesh/`, ortak dosyalar

## Arayüz

### `core/post.py`
- `von_mises(sigma) -> float | np.ndarray` — `sigma` `(6,)` → `float`; `(n, 6)` → `(n,)`.
- `principal_stresses(sigma) -> np.ndarray` — `(6,)` → `(3,)`, `(n, 6)` → `(n, 3)`; azalan sırada `σ1 ≥ σ2 ≥ σ3`.
- `nodal_stress_tensors(model, u) -> dict[int, np.ndarray]` — düğüm id → `(6,)` [MPa], hacim ağırlıklı
  ortalama; sadece `stress` sağlayan elemanlar (hacim: eleman modülünün `volume` fonksiyonu). Hiçbir katı
  elemana ait olmayan düğüm sözlükte yer almaz (çubuk modelinde sözlük boş).
- Hatalar (`ModelError`): son ekseni 6 olmayan dizi veya 1–2 boyut dışı şekil; sonlu olmayan değer.
- `Result` değişmez: `r = solve(m)`, `post.nodal_stress_tensors(m, r.u)`, `post.von_mises(...)`.

### `fileio/calculix.py`
- `to_inp(model) -> str` — Teori'deki eşleme; çıktı istekleri `*NODE PRINT` (`U, RF`), `*EL PRINT` (`S`),
  ayrıca CalculiX görüntüleyicisi için `*NODE FILE` (`U`) ve `*EL FILE` (`S`).
- `write_inp(model, path) -> None`
- Hatalar (`ModelError`): `model.validate()` hatası; desteklenmeyen eleman tipi; 1B dışında `bar1d`, 3B dışında
  `tet4`; tek modelde iki eleman tipi; `bar1d` elemanının kesiti yok.

## Kabul kriterleri
Ön hesap (gmsh 4.15.2 ve ccx, karalama, repoya girmedi) eşiklerin yanında verilmiştir.

- [ ] **K1** `von_mises`: tek eksen `|σ|`, saf kayma (`τ_xy`, `τ_xz`, `τ_yz` ayrı ayrı) `√3|τ|`, hidrostatik
  `≤ 1e-12 p`, iki boyutlu çekme–basma; rastgele `R` ile döndürülmüş tensörde aynı (rel 1e-12); `(n, 6)`
  girdide satır satır aynı sonuç — `tests/unit/test_post_gerilme.py`
- [ ] **K2** `principal_stresses`: köşegen tensörde sıralanmış köşegen; rastgele simetrik tensörde `numpy.linalg.eigvalsh`
  ile aynı (rel 1e-12) ve azalan; `Σ σ_i = iz`; asal gerilmelerden von Mises = `von_mises` (rel 1e-12) — unit
- [ ] **K3** Hatalar `ModelError`: `(5,)`, `(2, 3, 6)` şekli, `nan` içeren tensör — unit
- [ ] **K4** `nodal_stress_tensors`: tek elemanda dört düğüm = eleman gerilmesi; düğüm paylaşan iki elemanda
  `(V1σ1 + V2σ2)/(V1 + V2)` (rel 1e-12); düzgün çekme ağında (SPEC 11 yapılandırılmış ağ) her düğüm `σ`
  (rel 1e-9); `bar1d` modelinde boş sözlük — unit
- [ ] **K5** Delikli plaka (Kirsch): 1/8 model, plaka `200 × 100 × 2` (model `[0,100] × [0,50] × [0,1]`), delik
  `d = 10` merkezde, `x = 0`, `y = 0`, `z = 0` simetri, `x = 100` yüzünde `t = (1, 0, 0)` MPa; ağ
  `tet_mesh(h = 5, refine = [Refine((0, 0, 0.5), 8, 0.25)])`. `Kt` = delik kenarındaki `x = 0` düğümlerinin
  (`y = 5`) düğüm `σ_xx` ortalaması / `σ`:
  - `|Kt / 3.032 − 1| ≤ %3` (ön hesap: 3.031)
  - `y = 0` kenarındaki delik düğümlerinde (`x = 5`) ortalama düğüm `σ_yy / σ` `[−1.10, −0.90]` aralığında (ön hesap: −1.03)
  - En büyük düğüm von Mises'i delik kenarında, `x = 0` düzlemine `1` mm'den yakın bir düğümde
  - `@pytest.mark.slow` (ön hesap ~9 s) — `tests/benchmarks/test_kirsch.py`
- [ ] **K6** CalculiX C3D4 çapraz kontrolü (`ccx` yoksa atlanır): uydurma bir L braket (taban `60 × 40 × 8`,
  dikme `8 × 40 × 50`, dikmede `Ø10` delik), `tet_mesh(h = 4)`, taban alt yüzü ankastre, dikme üst yüzüne yanal
  `add_traction`. Aynı ağ ccx'te: düğüm yer değiştirmeleri `≤ 1e-5 · max|u|`, eleman gerilmeleri
  `≤ 1e-5 · max|σ|`, mesnet tepkileri `≤ 1e-5 · max|R|` (ön hesap, bu braket: 5.2e-8 ve 5.9e-8) —
  `tests/reference/test_calculix_tet4.py`
- [ ] **K7** `fileio.calculix.to_inp` çıktısı ccx'te çözülünce sonuç bizim çözücümüzle K6 toleransında aynı: K6
  braketi (C3D4) ve SPEC 01 örnek çubukları (T3D2) — `test_calculix_tet4.py`
- [ ] **K8** Yazıcı biçimi: `*NODE` satır sayısı = düğüm sayısı; her sayı alanı `≤ 20` karakter ve geri okununca göreli
  hata `≤ 5e-13` (`1e-16`, `−7.85e-16`, `1e+100` gibi değerler dahil);
  `*ELEMENT, TYPE=C3D4` satırlarının hepsi pozitif hacimli (girdide negatif sıralı elemanlar dahil); her
  malzeme bir `*MATERIAL`; Arayüz'deki hata listesinin her durumu `ModelError` — `tests/fileio/test_calculix_yazici.py`
- [ ] **K9** Mevcut `post` fonksiyonları ve `Result` değişmedi (mevcut testler yeşil)
- [ ] Tüm testler yeşil: `pytest --uygulanmamis-hata` → 0 failed, `ruff check .` ve `ruff format --check .` temiz

## Bağımlılık
K5–K7 SPEC 12'nin (`mesh.tet_mesh`, seçim ve yük yardımcıları) `main`'de olmasını ister. K1–K4 ve K8 SPEC 12'den
bağımsızdır; kod SPEC 12 birleşmeden yazılabilir, benchmark'lar ondan sonra yeşile döner.

## Kapsam dışı
- SPR veya başka süper yakınsak gerilme düzeltmesi, hata tahmincisi, uyarlamalı ağ
- `Result`'a gerilme alanı (`core/model.py`); gerekirse ayrı arayüz PR'ı
- CalculiX sonuç dosyası (`.frd` / `.dat`) okuyucusu ve ccx'i ürün içinden çalıştırma (Tezgah tarafında, sonraki SPEC)
- C3D10 / ikinci mertebe eleman, temas, doğrusal olmayan malzeme, akma ve yorulma değerlendirmesi
- Görselleştirme (gerilme renk haritası `viz/` içinde, ayrı iş)
