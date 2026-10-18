# SPEC 65a — Serbest yüzey özellikleri: loft, sweep, B-spline yüzey (Dalga 7, A9)

> Durum: **onaylı** (kullanıcı, 2026-10-18 16:19, önerilen cevaplarla; mesaj cmsg_01DTo5iWYb5RBUWgjk6xu1sGJGTUdh2rjZ3topbRjRQuit). Kullanıcı kararı (2026-10-18 11:00): serbest yüzey Dalga 7'de **basit** kapsamda olacak;
> class-A yüzey yok. Bağımlılık: SPEC 18 özellik ağacı (`geometry/agac.py`, #73), SPEC 17/26 eskiz, A2 `FaceRef`.

## Amaç
Bugünkü özellik ağacında yalnız prizmatik ve dönel unsurlar var: blok, silindir, ekstrüzyon, döndürme, delik, pah,
yuvarlatma, desen ve ayna. Atölyede sık görülen şu parçalar bu unsurlarla modellenemiyor:
- değişken kesitli kol (loft)
- boru, kanal ve yay yolu boyunca profil (sweep)
- tutamak ya da kalıp yüzeyi gibi nokta ağından geçen yüzey (B-spline)

Bu SPEC üç unsuru ağaca ekler: **Loft**, **Sweep** ve **BSplineYuzey**. Üçü de OCCT'nin hazır algoritmalarıyla yapılır:
- `BRepOffsetAPI_ThruSections`
- `BRepOffsetAPI_MakePipeShell`
- `GeomAPI_PointsToBSplineSurface`

Kendi yüzey matematiğimizi yazmayız. Ortaya çıkan katı, bugünkü zincirin tamamına girer: CAM 06 yüzey işleme, 27 unsur
tanıma ve 12 ağ.

## Teori

### Loft (kesitler arası katı)
`n ≥ 2` kapalı profil `P_1..P_n` paralel olmayan düzlemlerde de olabilir.

- `ruled = True`: ardışık kesitler doğrusal (regle) yüzeylerle birleşir. Hacim kapalı formludur:
  - aynı kesit → prizma `V = A h`
  - benzer kare kesitler (kesik piramit) → `V = h/3 (A1 + A2 + √(A1 A2))`
  - daireler → kesik koni `V = π h/3 (r1² + r1 r2 + r2²)`
- `ruled = False`: kesitlerden geçen tek bir B-spline yüzey üretilir. Kesitler arasında yüz dikişi oluşmaz; yan yüz tek
  yüzdür ve G1 süreklidir.

Profillerin kenar sayısı eşit değilse OCCT kenarları kendisi eşler. Eşleme başarısızsa unsur hata verir (S1: hatalı unsur
uygulanmaz, bağımlıları "atlandi" olur).

### Sweep (yol boyunca profil)
Kapalı profil `P`, `C` yolu boyunca süpürülür. Yol çizgi, yay ve 3B spline parçalarından oluşan teğet sürekli bir zincirdir.
Profil yolun başında yola diktir. Yönlendirme seçenekleri:
- `"frenet"`: helis için doğru seçimdir
- `"sabit"`: profil dönmez
- `"yardimci"`: bir yön vektörü verilir

Pappus–Guldinus teoremine göre profil merkezi yol üzerindeyse ve yol kendini kesmiyorsa `V = A · s` olur (`s` yol boyu).
- düz yol: `V = A L`
- `R` yarıçaplı çeyrek yay: `V = A · π R/2`
- helis: `s = √((2π R)² + p²) · tur`

### B-spline yüzey
Kullanıcı `m × n` nokta ağı verir (`m, n ≥ 4`). `GeomAPI_PointsToBSplineSurface` ile derece 3 olan, `tol` içinde noktalardan
geçen bir yüzey kurulur. Yüzey tek başına katı değildir, katıya iki yoldan girer:
- **Kalınlaştır** (`t`, yön ±): `BRepOffsetAPI_MakeThickSolid`. Küçük eğrilikte hacim yaklaşık `A_yüzey · t` olur.
  Kalınlık, eğrilik yarıçapından büyükse OCCT hata verir ve unsur uygulanmaz.
- **Yüzeyle kes**: parçanın yüzeyin bir tarafında kalan kısmı atılır (`BRepAlgoAPI_Splitter` + taraf seçimi). Kalıp
  maçası ve tutamak üstü bu yolla yapılır.

### Yüz adları (A2 `FaceRef`)
- Loft: `bas`, `son`, `yan` (ruled'da `yan_1..yan_k`, kesit aralığı başına).
- Sweep: `bas`, `son`, `yan_i` (profil kenarı başına).
- B-spline kalınlaştırma: `ust`, `alt`, `kenar_i`.
- Yüzeyle kesme: kesik yüz `kesit`.

Adlar SPEC 18'in geçmiş taşıma mekanizmasıyla sonraki unsurlara aktarılır.

## Dosyalar
- **Değişecek:**
  - `geometry/agac.py`: yeni unsur dataclass'ları ve uygulayıcılar. Dosya SPEC 18'indir; sahibi "18" thread'idir, 65a
    18 birleştikten sonra başlar.
  - `geometry/__init__.py`
- **Yeni:**
  - `geometry/serbest.py`: OCCT çağrıları; `agac.py` yalnız bu modülü çağırır
  - `tests/geometry/test_loft.py`, `tests/geometry/test_sweep.py`, `tests/geometry/test_bspline_yuzey.py`
  - `examples/65_tutamak.json`
  - `specs/65a-serbest-yuzey.md`, `durum/65a-serbest-yuzey.md`
- **Dokunulmayacak:** `geometry/part.py` (arayüz), `sketch/`, `cam/`.
- **Tezgah tarafı ayrı iştir:** modelleme ekranında Loft, Sweep ve Yüzey komutları SPEC 26/47 ekidir.

## Arayüz
```python
@dataclass(frozen=True)
class Loft:
    kimlik: str
    profiller: tuple[str, ...]  # Profil kimlikleri, ≥ 2, sırayla
    ruled: bool = False
    islem: Literal["ekle", "cikar", "yeni"] = "ekle"


@dataclass(frozen=True)
class Yol:
    parcalar: tuple[
        YolParcasi, ...
    ]  # Cizgi(p0, p1) | Yay(p0, p1, p2) | Spline(noktalar, teget0=None, teget1=None)


@dataclass(frozen=True)
class Sweep:
    kimlik: str
    profil: str
    yol: Yol
    yonlendirme: Literal["frenet", "sabit", "yardimci"] = "frenet"
    yardimci: tuple[float, float, float] | None = None
    islem: Literal["ekle", "cikar", "yeni"] = "ekle"


@dataclass(frozen=True)
class BSplineYuzey:
    kimlik: str
    noktalar: tuple[tuple[tuple[float, float, float], ...], ...]  # m × n
    tol: float = 0.01
    kullanim: Literal["kalinlastir", "kes"] = "kalinlastir"
    kalinlik: float = 1.0  # kalinlastir: ± yön işaretiyle
    sakla: Literal["ust", "alt"] = "alt"  # kes: yüzeyin hangi tarafı kalır (yüzey normaline göre)
```
`Agac` JSON gidiş-dönüşü yeni tipleri taşır (SPEC 18 `to_dict` deseni).

Hatalar (`ModelError` ya da S1 "atlandi"):
- profil kapalı değil
- profil sayısı `< 2`
- sweep yolu teğet sürekli değil (köşe açısı > 1e-6 rad) ya da kendini kesiyor
- nokta ağı düzensiz (satır uzunlukları farklı) ya da `m` veya `n` 4'ten küçük
- `tol ≤ 0`
- kalınlaştırma OCCT'de başarısız

## Kabul kriterleri
Hepsi `@pytest.mark.occt`.

- [ ] **K1** Ruled loft hacimleri (göreli 1e-6):
  - r=10'luk iki daire, aralık 50 → `15707.963`
  - 20×20 kare ile 10×10 kare, aralık 30 → `7000.0`
  - r=10 daire ile r=5 daire, aralık 30 → `5497.787`
- [ ] **K2** Pürüzsüz loft:
  - r=10, 15 ve 10 yarıçaplı üç daire, z = 0, 25, 50 düzlemlerinde.
  - Yan yüz **tek** yüzdür.
  - Hacim, aynı kesitlerin ruled loftundan büyüktür (dışbükey şişkinlik).
  - z = 25 düzleminde kesit yarıçapı 15 olur (abs 1e-3).
- [ ] **K3** Sweep hacimleri (göreli 1e-6):
  - r=5 daire, düz 100 mm yol → `7853.982`
  - r=5 daire, R=50 çeyrek yay → `6168.503` (Pappus)
- [ ] **K4** Helis sweep: r=2 daire, R=20, adım 10, 3 tur, `"frenet"`. Hacim `A·s`'ye göreli 1e-3 içinde. Profil her
  yerde yola diktir: rastgele 10 noktada yan yüz normali yol teğetine dik (açı farkı ≤ 1e-3 rad).
- [ ] **K5** B-spline yüzey ağı:
  - `z = (x² + y²)/200` paraboloidinden 7×7 nokta, `x, y ∈ [−30, 30]`.
  - Yüzey her noktadan `tol = 0.01` içinde geçer.
  - Hücre ortalarında paraboloide sapma ≤ 0.05 mm.
  - `kalinlik = 3` ile kalınlaştırılan katının hacmi `A_yüzey · 3`'e göreli 5e-2 içinde (eğrilik yarıçapı ~100 mm'de
    Steiner farkı ~%3; düzeltme 4).
- [ ] **K6** Yüzeyle kesme: 60×60×40 blok (yüzeyle aynı x, y aralığı) K5 yüzeyiyle kesilir ve `"alt"` saklanır.
  Yüzey uzatılmaz; yüzeyin baştan başa kesmediği gövde hata verir (düzeltme 4).
  - Kalan hacim `∫∫ (z_yüzey − z_taban) dA`'nın sayısal değerine göreli 1e-3 içinde.
  - Kesik yüz `FaceRef("…", "kesit")` ile bulunur.
- [ ] **K7** Ağaç davranışı:
  - Loft profili silinince loft ve bağımlıları "atlandi" olur; bağımsız unsurlar devam eder.
  - Profil boyutu değişince loft yeniden hesaplanır, `bas` ve `son` adları korunur.
  - JSON gidiş-dönüşünden sonra aynı hacim çıkar.
- [ ] **K8** Hatalar:
  - açık profil
  - tek profil
  - köşeli sweep yolu (iki çizgi 90°)
  - kendini kesen helis (adım < 2r)
  - 3×5 nokta ağı
  - `tol = 0`
  - eğrilik yarıçapından kalın kalınlaştırma

  Her biri `ModelError` verir ya da "atlandi" olur, hiçbiri sessiz geçmez.
- [ ] **K9** Zincir:
  - K2 loftu STEP'e yazılıp okununca hacim göreli 1e-6 içinde aynı kalır.
  - SPEC 12 `tet_mesh` hatasız ağlar.
  - SPEC 06 paralel finiş takım yolu K5 yüzeyinde yüzeye `≤ tol + 1e-3` mesafede kalır (06'nın kendi kabul ölçütüyle
    aynı).
- [ ] **K10** `ruff` temiz; 10 s'yi aşan testler `slow` ile işaretlenir.

## Bağımlılık
- SPEC 18 (#73) birleşmiş olmalı (ağaç, `FaceRef` geçmişi).
- SPEC 17/26 (`Profil`).
- SPEC 06 (K9).
- Kullananlar: 65b (görünüm), 27 (unsur tanıma serbest yüzeyi "serbest" sınıfına koyar), 06/50 (yüzey işleme).

## Kararlar (kullanıcı onayı 2026-10-18 16:19; önerilen cevaplar kabul edildi)
1. **Yüzey sürekliliği G2 ve eğrilik analizi (zebra) gerekli mi?** Karar: hayır. Class-A kapsam dışıdır (kullanıcı
   kararı). Yalnız G1 garanti edilir.
2. **Yüzey kenarından yuvarlatma (değişken yarıçap)?** Karar: hayır. Sabit yarıçaplı yuvarlatma SPEC 18'de var, değişken
   yarıçap sonraya kalır.
3. **Nokta ağı STEP / IGES'ten yüzey olarak alınsın mı?** Karar: evet, ama ayrı küçük bir ek olarak: `Part.from_step`
   zaten katı okuyor, yalnız yüzey içeren STEP ayrı bir yol ister.

4. **K5 / K6 ölçüt düzeltmesi** (kullanıcı onayı 2026-10-18 16:47, mesaj cmsg_01DTo5iWYb5RBUWgjk6xu1sGGabJ6sK4RC64XZsWuWP9nf):
   K5 kalınlaştırma hacmi toleransı 1e-2 → 5e-2 (OCCT ölçümü −%2,8 / +%2,9); K6 bloğu 80×80×40 → 60×60×40,
   yüzey uzatılmaz, yüzeyi aşan gövde hata verir, beklenen hacim paraboloid integraliyle göreli 1e-3.

## Kapsam dışı
- Class-A süreklilik (G2/G3), yüzey düzeltme (sculpt), alt bölümlü yüzeyler (SubD).
- Kabuk (shell) ve sac metal: sac kullanıcı kararıyla kapsam dışıdır.
- Yüzey dikme (sewing) ile dış kaynaklı yüzey modelleri onarma.
