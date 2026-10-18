# SPEC 53 — Performans: bloklu numpy simülasyon, girişimde sınır kutusu ağacı, Tezgah'ta kademeli ağ (LOD)

> **Durum: ONAYLANDI** (kullanıcı, 2026-10-18: Dalga 6 CAM taslakları 14:53 UTC'de açık soruların önerilen cevaplarıyla
> onaya sunuldu; kullanıcının 11:14 UTC kuralı "2 dakikadan fazla geçerse öneriyi kabul et" ile kabul edildi). Dalga 6, hat G6;
> `yol-haritasi/dalga-6-ve-sonrasi.md` bölüm 3.
> Bağımlılık (kod): SPEC 05 (z-map / dexel simülasyonu; `main`'de), SPEC 09 (girişim, sort-and-sweep; `main`'de), SPEC 24
> (Tezgah web arayüzü; `main`'de), SPEC 43 (tri-dexel; metin onaylı, kod henüz `main`'de değil — yalnız K4 için).
> B0'a bağlı değildir; Dalga 6'nın arayüz PR'larını beklemeden başlayabilir.

## Amaç
Hesap sonucunu **hiç değiştirmeden** üç darboğazı hızlandırmak: (1) freze simülasyonu: **200 × 200 mm parçada 0.1 mm z-map
ile tam freze simülasyonu < 10 s**; (2) büyük montajda girişim adaylarını sınır kutusu ağacıyla (BVH) bulmak; (3) Tezgah'ta
büyük ağları kademeli ayrıntıyla (LOD) çizmek. Her hızlandırma eski sürümle **birebir aynı sonucu** verdiğini testle kanıtlar.

## Teori

### Ölçüt programları (benchmark)
Hız hedefi tanımsız bir "tam simülasyon" üzerinde ölçülemez; bu SPEC iki sabit programı tanımlar (uydurma geometri,
`tests/cam/data/bench/` altında betikle üretilir, dosya olarak saklanmaz):
- **B1 — 2.5D kaba:** stok 200 × 200 × 40 mm, `D = 16` düz takım, SPEC 03 zigzag cep tüm alan, `ae = 8`, `ap = 5`, 8 paso
  (yaklaşık 200 uzun doğrusal hareket + bağlantılar).
- **B2 — 3D ince:** aynı stokun üstünde uydurma yüzey `z = 30 + 5·sin(2πx/80)·cos(2πy/60)` (SPEC 06 ağ, kiriş 0.01 mm),
  `R = 5` küresel uç, SPEC 06 raster, yan adım 0.5 mm, nokta aralığı uyarlamalı (06 `tol = 0.005`) → yaklaşık 400 satır.
- Izgara: z-map hücre `0.1 mm` → `2000 × 2000 = 4·10⁶` hücre. Süre: `simulate(...)` çağrısının duvar saati, aynı süreçte
  ikinci çalıştırma (ısınma hariç), CI çalıştırıcısında (GitHub `ubuntu-latest`). Hedef: **B1 ve B2'nin her biri < 10 s**.
  Mevcut sürümün süresi bu SPEC'in ilk işi olarak ölçülür ve `durum/53-performans.md`'ye yazılır (başlangıç çizgisi).

### Bloklu z-map / dexel güncellemesi
SPEC 05 her hareketi (ve alt adımı) ayrı ayrı ızgara penceresine uygular. Hızlandırmanın üç adımı, sırasıyla:
1. **Hareket birleştirme:** aynı doğru üzerinde ardışık `G1` hareketleri (aynı `F`, sapma ≤ `1e-9` mm) tek hareket olarak
   süpürülür. Süpürme kümesi `takım ⊕ [p₀, p₂] = (takım ⊕ [p₀, p₁]) ∪ (takım ⊕ [p₁, p₂])` olduğundan z-map matematiksel olarak
   aynıdır (zarf farklı sırayla hesaplandığı için sayısal fark ≤ 1e-12 mm);
   yalnız adım kayıtları (`SimStep`) birleştirilmiş harekete göre değil, yine her hareket için yazılır (kaldırılan hacim
   hareketlere pencere farkıyla bölünür).
2. **Blok (karo) işleme:** ızgara `T × T` karolara (varsayılan `T = 256`) bölünür; her hareketin sınır kutusu hangi karolara
   değdiği önceden hesaplanır; bir karo için o karoya değen ardışık hareketlerin zarfları tek numpy dizisi üzerinde
   `np.minimum.reduce` ile birleştirilir (z-map: üst yüzey `min`; dexel: aralık farkı sırası korunarak). Hareket sırası
   karo içinde korunur, böylece çarpışma ve "o ana kadarki stok" gerektiren kayıtlar (05 `Collision`) değişmez.
3. **Bellek düzeni:** `float64` z-map C-sıralı; zarf hesabında geçici diziler karo boyunca yeniden kullanılır.
- **Eşitlik şartı:** z-map değerleri eski sürümle **bit düzeyinde** aynı (aynı kayan nokta işlemleri, yalnız sıra ve gruplama
  değişir; `min` birleşmeli ve değişmeli olduğu için sonuç değişmez). Dexel aralıkları 1e-12 mm. `SimStep`, `Collision`
  listeleri ve süre birebir.

### Girişimde sınır kutusu ağacı (BVH)
SPEC 09 aday çiftleri x ekseninde sort-and-sweep ile bulur; parçalar x'te üst üste dizildiğinde (uzun mil üstünde çok
parça) `O(n²)`'ye düşer. BVH: yaprak kutuları (09 `world_aabb`) orta nokta bölmesiyle (en uzun eksende medyan) ikili ağaca
dizilir; iki ağaç düğümü aday olur ancak kutu boşluğu `g < eşik` ise (09'un aynı ölçütü: `g < clearance` veya `g ≤ tol_d`).
- Aday kümesi sort-and-sweep ile **aynı kümedir** (aynı ölçüt; ağaç yalnız aramayı budar). Sıralama 09 ile aynı (`sorted`).
- Ağaç kurulumu `O(n log n)`, sorgu tipik `O(n log n + k)`.

### Tezgah'ta kademeli ağ (LOD)
Büyük STEP / ağ parçalarında tarayıcıya giden üçgen sayısı sınırlanır:
- **Sadeleştirme:** quadric error metric (Garland–Heckbert 1997) ile kenar daraltma, saf numpy; seviyeler üçgen sayısının
  ~%50, %25, %12.5'i. Her seviyenin tek yönlü Hausdorff uzaklığı (sadeleşmiş → asıl, yüzey örneklemesiyle) ölçülür ve
  seviye ile birlikte saklanır.
- **Seçim:** ekran uzayı hatası `e_px = d_H · f / (z · s)` (odak `f`, uzaklık `z`, piksel boyu `s`) ≤ 1 piksel olan en kaba
  seviye. Seçim kuralı Python'da (test edilir); tarayıcı yalnız istenen seviyeyi ister.
- Sınır kenarları ve keskin kenarlar (dihedral açı > 30°) daraltılmaz; ağın topolojisi (kapalılık) korunur.

## Dosyalar
- Değişecek: `cam/sim/simulate.py`, `cam/sim/zmap.py`, `cam/sim/dexel.py` (SPEC 05'in dosyaları; **imzalar değişmez**,
  yalnız iç uygulama), `assy/girisim.py` (`_adaylar` yerine BVH; `check` imzası değişmez), `tezgah/kopru.py` ve ilgili
  ekran dosyası (LOD seviyesi isteği; 24 sahibi thread ile sıralı).
- Yeni: `cam/sim/blok.py` (hareket birleştirme, karo planı), `assy/bvh.py`, `viz/lod.py` (quadric sadeleştirme, Hausdorff,
  seviye seçimi; numpy, `core/` bağımlılığı yok), `tests/cam/test_perf_esitlik.py`, `tests/cam/test_perf_hiz.py` (`slow`),
  `tests/assy/test_bvh.py`, `tests/viz/test_lod.py`, `scripts/bench_sim.py` (ölçüt programlarını üretir ve süreyi yazar),
  `durum/53-performans.md`.
- Dokunulmayacak: tüm `*/model.py`, 05 / 09 testleri (değişmeden yeşil kalmalı), 43'ün dosyaları (tri-dexel hızlandırması
  43 `main`'e girdikten sonra bu SPEC'e ek).
- Yeni bağımlılık yok (numba, Cython, GPU kullanılmaz; gerekirse kullanıcıya sorulur).

## Arayüz
- `cam.sim.simulate(...)`: imza ve dönüş aynı; yeni isteğe bağlı parametreler `block: int | None = 256` ve `merge: bool = True`
  (`block = None, merge = False` → eski yol, eşitlik testleri için).
- `cam.sim.blok.merge_collinear(moves, tol=1e-9) -> list[tuple[int, int]]` — birleştirilen hareket aralıkları.
- `assy.bvh.Bvh.build(boxes) -> Bvh`, `Bvh.pairs(esik_c: float, tol_d: float) -> list[tuple[int, int]]`.
- `assy.girisim.check(...)`: imza aynı; yeni isteğe bağlı `broadphase: str = "bvh"` (`"sweep"` → eski yol).
- `viz.lod.simplify(V, T, target: int, keep_angle=30.0) -> (V, T)`, `viz.lod.hausdorff(V0, T0, V1, T1, n=…) -> float`,
  `viz.lod.levels(V, T, ratios=(0.5, 0.25, 0.125)) -> list[Level]`, `viz.lod.pick(levels, z, f, s, px=1.0) -> int`.

## Kabul kriterleri
- [ ] K1 Eşitlik, z-map: B1, B2 ve SPEC 05'in rastgele (sabit tohum) programlarında, hareket birleştirme kapalıyken `block = 256` ile
  `block = None` z-map'leri bit düzeyinde aynı (`np.array_equal`), birleştirme açıkken 1e-12 mm; `SimStep` hacimleri rel 1e-12, `Collision` listesi ve süre birebir — `tests/cam/test_perf_esitlik.py`
- [ ] K2 Eşitlik, dexel: aynı programlar `model = "dexel"` ile; aralık uçları 1e-12 mm, hacim rel 1e-12 — `test_perf_esitlik.py`
- [ ] K3 Hareket birleştirme: aynı doğru üzerindeki 1000 kısa hareket tek harekete iniyor, kırık doğruda (sapma 1e-6) birleşme yok;
  birleşmiş ve birleşmemiş z-map aynı — `test_perf_esitlik.py`
- [ ] K4 Hız: B1 ve B2, 0.1 mm z-map, CI çalıştırıcısında her biri < 10 s; ölçülen süre ve başlangıç çizgisi test çıktısına yazılıyor
  (`@pytest.mark.slow`) — `tests/cam/test_perf_hiz.py`
- [ ] K5 BVH eşitliği: rastgele (sabit tohum) 10, 100, 1000 kutuda ve "uzun mil üstünde 500 halka" senaryosunda `Bvh.pairs` sort-and-sweep
  ile aynı liste; 09'un tüm testleri `broadphase = "bvh"` ile değişmeden yeşil — `tests/assy/test_bvh.py`
- [ ] K6 BVH hızı: "uzun mil üstünde 2000 halka" senaryosunda aday bulma sort-and-sweep'ten en az 10 kat hızlı (aynı makinede, `slow`) — `test_bvh.py`
- [ ] K7 LOD sadeleştirme: küp (12 üçgen) daraltılmıyor (keskin kenarlar); yoğun ağlı küre (`ρ = 50`, 80 000 üçgen) %12.5 seviyesinde
  Hausdorff `d_H ≤ ρ − √(ρ² − c²/3) + δ + ε₀` (`c` seviyenin en uzun kenarı, `δ` sadeleşmiş köşelerin küreden en büyük sapması,
  `ε₀` asıl ağın kiriş hatası; karar 3), ağ kapalı kalıyor — `tests/viz/test_lod.py`
- [ ] K8 LOD seçimi: `pick` uzaklık iki katına çıkınca bir kademe kabalaşıyor (hata formülüyle elle hesaplanan eşiklerde); `px` sınırı
  her seçilen seviyede sağlanıyor — `test_lod.py`
- [ ] K9 Hatalar: `block ≤ 0`, `target < 4` veya `target ≥` mevcut üçgen sayısı, kapalı olmayan ağda `keep` ihlali → `CamError` /
  `ModelError` (paketin hata tipi) — ilgili test dosyaları
- [ ] Tüm testler yeşil, `ruff check .` ve `ruff format --check .` temiz, 0 "uygulanmamış"; 10 s'den uzun testler `slow`

## Kapsam dışı
- Tri-dexel (43) ve torna (22) simülasyonunun hızlandırılması: 43 / 22 kararlı olunca bu SPEC'e ek.
- Çok çekirdek / süreç havuzu, numba / Cython / GPU, C uzantısı (yeni bağımlılık; kullanıcı kararı gerekir).
- Drop-cutter (06) ve tri-dexel ışın sorgularında BVH: ayrı ek; bu SPEC'in BVH'si yalnız montaj girişimi için.
- Tarayıcı tarafında (JS) sadeleştirme ve görünüm dışı nesne ayıklama (frustum culling): 24 sahibinin işi.

## Kararlar (açık soruların önerilen cevapları, onaylı)
1. Hedef makine: < 10 s **CI çalıştırıcısında** (GitHub `ubuntu-latest`) ölçülür (tekrarlanabilir); kullanıcının makinesinde
   de `scripts/bench_sim.py` ile ölçülüp `durum/53-performans.md`'ye yazılır.
2. Önce bu SPEC'in saf numpy yolu uygulanıp ölçülür; hedef tutmazsa numba (yeni bağımlılık) kararı ölçümden sonra
   kullanıcıya sorulur. Bu SPEC kendiliğinden yeni bağımlılık eklemez.
3. K7 ölçütü (errata, kullanıcı onayı 2026-10-18 15:59 UTC, 11:14 kuralıyla otomatik kabul): ilk metindeki `d_H ≤ ρ(1 − cos(θ/2))` (θ ortalama kenar açısı)
   ideal ikosferde bile tutmuyor (gerçek / formül ≈ 1.6), çünkü üçgenin içi kenar kirişinden daha derindedir.
   Kenarı en çok `c` olan bir üçgenin çevrel çember yarıçapı ≤ `c/√3`; kürede bu üçgenin en derin noktası
   `ρ − √(ρ² − c²/3)` kadar içeridedir. Köşeler küre üzerinde değilse sapmaları `δ`, asıl ağın kendi kiriş hatası `ε₀`
   eklenir: `d_H ≤ ρ − √(ρ² − c²/3) + δ + ε₀`.
