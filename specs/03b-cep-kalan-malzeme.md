# SPEC 03b — Kalan malzeme denetimli cep: D/2 < s ≤ D yan paso

> Onaylandı: kullanıcı, 2026-10-18 10:24 (proje sohbeti kartı "Onayla") ve 10:38 (yazılı onay).

## Amaç
Kontur-paralel cebin (`cam.ops2d.pocket`) `r < s ≤ D` yan pasoyu yeniden kabul etmesi; her halka seviyesinde
kesilmemiş malzeme kalıp kalmadığının **kesin** (ofset aritmetiğiyle, örneklemesiz) denetlenmesi ve kalıyorsa
o seviyede yan pasonun kanıtlanmış biçimde küçültülmesi (ara halka). Hiçbir durumda sessizce ada kalmaz.

## Bağlam
- SPEC 03 Ek A1 (PR #33, kullanıcı onayı 2026-10-18 09:24 "En fazla D/2") cepte `s > r` → `CamError` yaptı,
  çünkü `r < s` için kanıt yoktu ve L biçimli cepte (50×45, kollar 20, D = 6, `s = 0,6D`) kolların ortasında
  ≈ 27 mm² malzeme sessizce kalıyordu. Ek A1 bu durumu "ayrı SPEC" olarak bıraktı: bu SPEC.
- Bu SPEC birleşince Ek A1'in "`s > r` → `CamError`" kuralı kalkar; cepte sınır yine `0 < s ≤ D` olur.
  Ek A1'in `s ≤ r` kanıtı aynen kullanılır (aşağıda Önerme 1).
- Ön koşul: PR #33 (Ek A) `main`'de. Kod o birleşmeden önce yazılmaz.

## Teori

### Gösterim
- `Ω` cep bölgesi, `r = D/2`, `s` istenen yan paso, `ε = COVER_TOL = 1e-7 mm`.
- `R ⊖ B_d` iç ofset (`offset(R, d)`), `X ⊕ B_d` dış ofset (`offset_union(X, −d)`), `δ_R(p) = dist(p, ∂R)`.
- Halka ağacı: kökler `R₀ = Ω ⊖ B_r` bileşenleri. Bir düğüm `R`'nin çocukları `R ⊖ B_σ` bileşenleridir; `σ`
  o düğümün **adımıdır** (SPEC 03'te her düğümde `σ = s`). Takım merkezi her düğümün sınırı `∂R`'yi gezer ve
  `∂R ⊕ B_r` şeridini keser.

### Seviye koşulu
Düğüm `R`, adım `σ`, çocuk kümesi `X = R ⊖ B_σ` için:

  `A = R ⊖ B_r`,  `Y = X ⊕ B_(r+ε)`,  **koşul: `A ⊆ Y`**  (X boşsa `Y = ∅`, koşul `A = ∅` olur).

**Önerme 1 (Ek A1).** `σ ≤ r` ise koşul her `R` için sağlanır. Kanıt: `p ∈ A` ise `δ_R(p) ≥ r ≥ σ`, yani `p ∈ X ⊆ Y`.

**Önerme 2 (yeterlilik).** Ağaçtaki her düğüm seviye koşulunu sağlıyorsa, erişilebilir kümenin
(`R₀ ⊕ B_r`) her noktası bir halkaya `≤ r + ε` uzaklıktadır. Kanıt: `p ∈ R₀ ⊕ B_r`. `p ∉ R₀` ise `p`, `R₀`'a
(yani `∂R₀`'a) `≤ r` uzaklıktadır. Aksi halde `p`'yi içeren en derin düğüm `R` olsun (`p ∈ R`, `p ∉ X`).
`δ_R(p) ≤ r` ise `p` halka `∂R`'ye `≤ r` uzaktır. Değilse `p ∈ A ⊆ Y`: `dist(p, X) ≤ r + ε`; `p ∉ X` olduğundan
en yakın nokta `∂X` üzerindedir, `∂X` çocuk halkalardır. ∎
Z pasoları XY'yi değiştirmez; önerme her paso derinliği için geçerlidir.

**Önerme 3 (gereklilik, yorum).** Koşul bozuksa `A \ Y` boş olmayan açık bir kümedir; bu kümenin noktaları
`∂R`'ye `> r`, `∂X`'e `> r + ε` uzaktır; daha derin halkalar `X`'in içindedir, üst halkalar `R`'ye `≥ σ_üst > r`
uzaktır. Yani denetim yalnız gerçekten kesilmeyen malzeme varken başarısız olur (`ε` payı dışında).

**Önerme 4 (tekdüzelik).** `σ₁ < σ₂` ⇒ `R ⊖ B_σ₂ ⊆ R ⊖ B_σ₁` ⇒ `Y(σ₂) ⊆ Y(σ₁)`. Koşul `σ₂`'de sağlanıyorsa
`σ₁`'de de sağlanır. Bu yüzden en büyük geçerli adım ikiye bölmeyle aranabilir.

**Analitik sonuç (köşe).** `R`'nin iç açısı `θ` olan keskin dışbükey köşesinde `A`'nın köşesi ile `X`'in köşesi
açıortay üzerinde `(σ − r)/sin(θ/2)` uzaklıktadır; köşede koşul `σ ≤ r (1 + sin(θ/2))` olur (SPEC 03'teki köşe
formülüyle aynı). Kenar boyunca koşul `σ ≤ 2r` ile her zaman sağlanır. Dolayısıyla `a×b` dikdörtgen `R` için
(`X` boş değilken) koşul ⇔ `σ ≤ r(1 + sin 45°) = 1,7071 r`; eşkenar üçgen için ⇔ `σ ≤ 1,5 r`.
`ρ` yarıçaplı daire `R` için: `σ < ρ` ise koşul her zaman sağlanır (`A`, `Y`'nin içindeki eş merkezli daire);
`σ ≥ ρ` (yaprak) ise koşul ⇔ `ρ ≤ r`.

### Kesin denetim (`covered`)
`A` ve `Y` doğru + yay sınırlı bölgelerdir (SPEC 03 ofseti yayları korur). `A ⊆ Y` şu iki koşula denktir
(`A`'nın her bileşeni bağlantılı olduğundan):
1. `∂A`'nın, `∂Y` ile kesişim noktalarından bölünmüş her alt parçasının orta noktası `Y` içinde,
2. `∂Y`'nin, `∂A` ile kesişim noktalarından bölünmüş hiçbir alt parçasının orta noktası `A` içinde değil
   (bu, `A`'nın ortasında kalan "ada" durumunu yakalar: `Y`'nin bir deliği `A`'nın içinde).
Boyu `≤ LINK_TOL` olan alt parçalar atlanır. `ε` payı, koşulun tam sınırda olduğu (kesilmemiş kalınlık 0)
durumlarda `∂A` ile `∂Y`'nin üst üste binmesini önler: sınır `ε` kadar ayrılır, karar kararlı olur.
Kesilmemiş kalınlığı `ε`'dan küçük malzeme kabul edilir (fiziksel olarak anlamsız; K-ölçütlerinde tolerans).

### Halka ağacı (adım seçimi)
Her düğüm `R` için (kökler dahil):
1. `X = R ⊖ B_s`.
2. `s ≤ r` (+ `TOL`) → adım `s` (Önerme 1, denetim yok; SPEC 03 Ek A ile aynı yol).
3. `X` boş (yaprak): SPEC 03 kuralı aynen: `t*` iç yarıçap; `t* − r > TOL` ise `t* − r + LINK_TOL` adımlı ek
   halka(lar) eklenir ve onlar işlenmez (iç yarıçapları `r + LINK_TOL`, yani `A` ≈ boş). Bu adım `< r`'dir
   (`t* < s ≤ 2r`), Önerme 1 ile güvenlidir.
4. `covered(R, s, r)` → adım `s`.
5. Aksi halde ikiye bölme: `lo = r` (Önerme 1 ile geçerli), `hi = s`; `BISECT_N = 8` kez
   `m = (lo + hi)/2`, `covered(R, m, r)` ise `lo = m` değilse `hi = m`. Adım `σ = lo`, çocuklar `R ⊖ B_σ`.
   Sonuç: `σ ≥ σ_max − (s − r)/2⁸`, burada `σ_max` en büyük geçerli adım (Önerme 4).
6. Çocuklara aynı kural uygulanır (özyineleme; istenen adım her düğümde yeniden `s`'dir).
`pocket`'in hareket kuralları (halka sırası, inmeden geçiş, giriş/çıkış) SPEC 03'teki gibidir; değişen yalnız
ağacın kurulmasıdır.

## Dosyalar
- Yeni: `cam/rest.py`, `tests/cam/test_rest.py`, `durum/03b-cep-kalan-malzeme.md`
- Değişecek: `cam/offset.py` (`offset_union` eklenir, `offset` ona yönlenir; davranış aynı),
  `cam/ops2d.py` (`pocket` ağacı `cam.rest.ring_tree` ile kurar; cepte `s > r` hatası kalkar),
  `tests/cam/test_ops2d.py` (yalnız Ek A K17'nin `s > r` → `CamError` beklentisi `s > D`'ye döner; test oturumu yapar)
- Dokunulmayacak: `cam/model.py` (arayüz değişikliği yok), `face`, `contour`, diğer paketler, ortak dosyalar.

## Arayüz

### `cam/offset.py`
- `offset_union(regions: list[Region], d: float) -> list[Region]` — ayrık bölgelerin birleşiminin `d` ofseti
  (SPEC 03 algoritması, tüm halkaların ham ofsetleri birlikte budanır: `dist(m, ∪∂R_i) ≥ |d| − KEEP_TOL`,
  `m ∈ ∪R_i ⇔ d > 0`). `d < 0`'da bileşenler birleşebilir. `regions == []` → `[]`. `d == 0` → `CamError`.
- `offset(region, d)` = `offset_union([region], d)` (sonuç SPEC 03 ile aynı).

### `cam/rest.py`
- `COVER_TOL = 1e-7` [mm], `BISECT_N = 8`
- `covered(region: Region, sigma: float, r: float) -> bool` — yukarıdaki seviye koşulu `A ⊆ Y`.
  `sigma ≤ 0` veya `r ≤ 0` → `CamError`.
- `residue(region: Region, sigma: float, r: float) -> list[Region]` — `A \ Y` bölgeleri (aynı bölme +
  sınıflandırma; `∂A`'nın `Y` dışındaki parçaları + `∂Y`'nin `A` içindeki parçaları ters yönde, zincirlenir).
  `covered(...) ⇔ residue(...) == []`. Tanı ve test içindir; `pocket` bunu çağırmak zorunda değildir.
- `@dataclass RingNode(region: Region, step: float, children: list[RingNode])` — `step`: düğümü üstünden
  ayıran ofset (kökte `r`).
- `ring_tree(region: Region, r: float, s: float) -> list[RingNode]` — kökler (`Ω ⊖ B_r` bileşenleri) ve
  yukarıdaki adım seçimi. `0 < s ≤ 2r` değilse → `CamError`. Takım sığmıyorsa `[]`.

### `cam/ops2d.py`
- `pocket(region, tool, cut, climb=True)` — imza aynı. Cepte `0 < s ≤ D` kabul edilir (`s > D` → `CamError`,
  mesaj aynı). Halka ağacı `ring_tree(region, r, s)`.

## Kabul kriterleri
Tolerans aksi yazılmadıkça mutlak `1e-9 mm`; "kalan malzeme yok" ölçütünde `r + COVER_TOL + 1e-9`.
- [ ] K1 `offset_union`: tek bölgede `offset` ile aynı halkalar; iki ayrık `a×a` kare (aralık `g`) dış ofsette
  `|d| < g/2` → 2 bölge, `|d| > g/2` → 1 bölge; sonuç sınırındaki örnek noktaların `∪∂R_i`'ye uzaklığı `|d|`;
  iç ofsette sonuç her bölgenin `offset`'lerinin birleşimi; `d = 0` → `CamError` — `tests/cam/test_rest.py`
- [ ] K2 `covered` analitik eşikleri: `a×b` dikdörtgen `R` için `σ = 1,7071 r − 1e-6` → `True`,
  `σ = 1,7071 r + 1e-6` → `False` (eşik `r(1 + sin 45°)`); herhangi bir üçgende (iç ofseti benzer üçgendir,
  kenar kaybolmaz; iç yarıçap `> σ` iken) eşik `r(1 + sin(θ_min/2))`: eşkenar `1,5 r`, dik ikizkenar `1,3827 r`;
  `ρ` yarıçaplı dairede `σ < ρ` (`σ ≤ 2r`) → her zaman `True`, `σ ≥ ρ` → `True` ⇔ `ρ ≤ r`;
  `σ ≤ r` → her bölgede `True` (Önerme 1, rastgele çokgenler) — `tests/cam/test_rest.py`
- [ ] K3 `residue`: `covered` ile tutarlı (boş ⇔ `True`); dikdörtgende `σ > 1,7071 r` iken 4 köşe bölgesi;
  L cep (50×45, kollar 20, D = 6, `s = 0,6D`) ağacında bozuk seviyenin `residue` alanı > 0 ve SPEC 03
  ağacıyla kesilmeyen örnek noktaları içeriyor — `tests/cam/test_rest.py`
- [ ] K4 `ring_tree` adımları: `s ≤ r` iken her adım `s` (SPEC 03 Ek A ile aynı ağaç); 60×40, D = 10:
  `s = 0,8D` → dikdörtgen düğümlerde adım `s` (eşik `8,536` altında, küçültme yok; yaprakta SPEC 03 ek halkası); `s = D` → kök adımı
  `σ ∈ [1,7071 r − (s − r)/256, 1,7071 r]`, çocuk dikdörtgen `(50 − 2σ)×(30 − 2σ)`; her düğüm `covered` —
  `tests/cam/test_rest.py`
- [ ] K5 `pocket` kalan malzeme yok (`r < s ≤ D`): dikdörtgen (`0,8D`, `D`), daire (`0,95D`), L cep
  (`0,6D`, `0,7D`, `D`), adalı cep (`0,7D`, `D`), rastgele dışbükey/içbükey çokgenler (`0,6D`, `0,8D`, `D`):
  erişilebilir kümedeki (`(Ω ⊖ B_r) ⊕ B_r`) her örnek nokta bir kesme hareketine `≤ r + COVER_TOL + 1e-9` —
  `tests/cam/test_ops2d.py`
- [ ] K6 `pocket` çakma yok ve hareket kuralları (SPEC 03 K13, K15) `r < s ≤ D` için de geçer — `tests/cam/test_ops2d.py`
- [ ] K7 Hatalı girdiler: `pocket` `s > D` → `CamError`; `ring_tree` `s > 2r` veya `s ≤ 0` → `CamError`;
  `covered` `σ ≤ 0`, `r ≤ 0` → `CamError` — `tests/cam/test_rest.py`, `tests/cam/test_ops2d.py`
- [ ] K8 Ek A K17'deki `s = r + 1e-6`, `0,8D`, `D` → `CamError` beklentisi kaldırılır; bu değerler artık K5'e göre
  kabul edilir (`s > D` → `CamError` kalır)
- [ ] `pytest` 0 failed, bu SPEC'in testlerinde 0 "uygulanmamış"; `ruff check .` temiz; 10 s'den uzun testler `slow`

## Kapsam dışı
- Rampa / helis giriş ve giriş-çıkış yayları: SPEC 03 ve Ek A2 bunları "03b" diye anıyordu; bu SPEC'ten ayrı
  tutulur; adı 03c (koordinatör kararı, 2026-10-18). Merkezden kesmeyen takımla cep Ek A2'deki gibi `CamError` kalır.
- Seviye içinde yerel ek halka / temizleme pasosu (yalnız kalan bölgeyi kesen kısa yollar): adım küçültme
  kanıtlı ve hareket kurallarını değiştirmediği için seçildi; yerel temizleme ileride ayrı SPEC olabilir.
- Önceki takımdan kalan malzeme (rest machining, küçük takımla köşe temizliği), zigzag / trokoidal cep (19).
- Örneklemeyle kalan malzeme denetimi: kanıtsız olduğu için kullanılmaz (testlerde bağımsız doğrulama olarak kalır).
- pyclipper / OpenCAMLib bağımlılığı: yalnız testlerde çapraz kontrol olarak, ayrı kararla.
