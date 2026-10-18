# SPEC 27 — İşleme özelliği tanıma: parçadan yüz alma, cep, açık bölge, delik; torna profilinden kaba zarf ve kanal

## Amaç
Katı parçadan (`geometry.part.Part`) 3 eksen, üstten (`−Z` takım yönü) işlenecek **işleme özelliklerini** okumak ve
her birini doğrudan bir CAM işleminin girdisi olarak vermek: yüz alma derinliği, cep bölgesi (`cam.profile.Region`,
yaylar tam yarıçapla) ve derinlik aralığı, açık bölge (basamak / dış kontur), delik kaydı (`Hole`). Tornada, dönel
parçanın yarı kesit profilinden (`cam.profile.Profile`) alın, `G71` tip I için monoton **kaba zarf**, kanal ve genel
girinti çıkarmak. Sonuç: kullanıcı parçayı verir, SPEC 03 / 04 / 20 işlemleri elle profil çizmeden beslenir.

Bu SPEC **tasarım ağacı** değildir (o SPEC 18, `18-ozellik-agaci`): burada özellik, parçanın son geometrisinden
geriye doğru okunur.

## Teori

### Neden kesit tabanlı (2.5D) tanıma
Prizmatik parçada (yan duvarlar dik, tabanlar yatay) malzeme yalnızca `z` seviyeleri arasında değişir. Yatay yüz
seviyeleri `h_0 < h_1 < … < h_m` arasında kalan her **dilimde** `z = sabit` kesiti aynıdır; dolayısıyla her dilim tek bir
kesitle (`Part.section_z`) tam tanımlanır. Cep = kesitte bir iç halka (malzemedeki boşluk); açık bölge = zarf
dikdörtgeni ile kesitin dış halkaları arasındaki boşluk; delik = eksenli silindir. Kesit çokgendir (`tol_kesit`
kiriş sapmalı); yaylar, aynı seviyedeki dik silindirik yüzlerin (`Part.cylindrical_faces`) **tam** merkez ve yarıçapıyla
geri kurulur, böylece çıkan geometri analitik olarak doğrudur. Kaynak: Gao & Shah, "Automatic recognition of
interacting machining features based on minimal condition subgraph" (CAD, 1998) — 2.5D hacim ayrıştırma fikri;
Vandenbrande & Requicha, "Spatial reasoning for the automatic recognition of machinable features" (IEEE PAMI, 1993).

Kullanılan parça sorguları yalnızca `geometry/part.py` arayüzündekilerdir: `bbox`, `area`, `holes`, `planar_faces()`,
`cylindrical_faces()`, `section_z()`. **Arayüz değişikliği gerekmez.**

### Toleranslar
- `tol` (varsayılan `1e-3` mm): eşleme toleransı (seviye birleştirme, köşenin daire üstünde olması, halka eşitliği).
- `tol_kesit = 0.01` mm: `section_z` kiriş sapması.
- `ANG = 1e-6`: yön toleransı (`|n_z| ≥ 1 − ANG` yatay, `|n_z| ≤ ANG` dik; eksen için aynı).
- Alan dengesi bağıl toleransı `1e-6`.

### 1. Ön koşullar (2.5D denetimi) — sağlanmazsa `CamError`, sessizce kısmi sonuç yok
1. `stock` verildiyse parça kutusu stok kutusunun içinde (`tol` payla); değilse `CamError`.
2. Her düzlemsel yüz yatay (`|n_z| ≥ 1 − ANG`) veya dik (`|n_z| ≤ ANG`). Eğik düzlem (örn. `chamfer_top` pahı) → hata.
3. Her silindirik yüzün ekseni `Z`'ye paralel (`|a_z| ≥ 1 − ANG`). İstisna: bir delik kaydıyla eşleşen silindir
   (ekseni kaydın `axis`'ine paralel, eksen doğrusunun kaydın `origin`'ine uzaklığı ≤ `tol`, yarıçapı `d/2` veya
   `cbore_d/2` ile `tol` içinde) — eğimli delikler bu yolla geçer.
4. Normali `−Z` olan düzlemsel yüzlerin hepsi `z = zmin` (parça tabanı) seviyesinde. Daha yukarıdaki `−Z` yüz =
   alttan erişilen bölge (undercut, T-kanal) → hata.
5. **Alan dengesi**: `A_parça − ΣA_düzlem − ΣA_silindir − ΣA_havşa ≤ 1e-6 · A_parça`. `A_havşa`, havşalı her delik
   kaydının koni yan alanıdır: `R = csk_d/2`, `r = d/2`, `θ = csk_angle`; `A_havşa = π (R + r)(R − r) / sin(θ/2)`.
   Fazlalık başka tip yüz (koni, küre, tor, serbest yüzey; örn. yuvarlatma) demektir → hata. (Ön deneme: 100×60×20
   blok, cep 40×30 r5 derinlik 8, iç cep 16×12 derinlik 12, Ø8 boydan delik, Ø6.6 / Ø12 × 90° havşa: fark
   `111.5608 mm²`, formül `π·9.3·2.7/sin 45° = 111.5608`.)

### 2. Delikler
- **Silindir birleştirme**: aynı eksenli (`xy` farkı ≤ `tol`, eksen `Z`'ye paralel), aynı yarıçaplı ve aynı `z` aralıklı
  (hepsi `tol` içinde) silindirik yüzler tek silindir sayılır, açıları toplanır; toplam `≥ 360° − ANG` → tam silindir.
  (Ön deneme: STEP'e yazılıp okunan Ø30 kör delik `270° + 90°` iki yüze bölünüyor.) §4 de silindirleri böyle gruplar.
- **Kayıtlı delikler**: `part.holes`'daki her kayıt olduğu gibi `HoleFeature(hole, source="kayit")` olur (kayıt
  geometriye göre yeniden doğrulanmaz; SPEC 23 kuralı).
- **Tanınan delikler** (kayıt dışı, örn. STEP'ten okunan parça): içbükey (`concave`), birleştirilmiş açısı tam (`360°`), ekseni `Z`'ye
  paralel ve `2R ≤ hole_d_max` olan, hiçbir kayıtla eşleşmeyen silindir. Silindirin `z` aralığı `[z_b, z_e]`
  (`origin_z` ve `origin_z + axis_z · length`'in küçüğü / büyüğü):
  `Hole(origin=(x, y, z_e), axis=(0, 0, −1), d=2R, depth=z_e − z_b, through=(z_b ≤ zmin + tol))`, `source="tanima"`.
- **Lamba**: aynı eksende (`xy` farkı ≤ `tol`) iki tanınan silindir uç uca değiyorsa (üsttekinin `z_b` = alttakinin
  `z_e`, `tol` içinde) ve üstteki daha genişse tek delik: `d = 2R_alt`, `cbore_d = 2R_üst`, `cbore_depth = L_üst`,
  `depth = L_üst + L_alt`, `through` alttakinin tabanına göre. Üç veya daha fazla kademe → `CamError`
  (kademeli delik kapsam dışı).
- `2R > hole_d_max` olan içbükey 360° silindir delik sayılmaz; kesitte iç halka olarak kalır ve **dairesel cep** olur.
- Delik halkası: bir kesit halkasının her köşesinin, bir delik özelliğinin eksen doğrusuna 3B uzaklığı `ρ(z)` ile
  `tol` içindeyse halka o deliğindir ve cep / ada sayılmaz. `ρ(z)`: girişten eksen boyunca `t` derinlikte
  lamba bölgesinde (`t < cbore_depth`) `cbore_d/2`; havşa bölgesinde (`t < (csk_d − d) / (2 tan(θ/2))`)
  `csk_d/2 − t · tan(θ/2)`; diğer yerde `d/2`.
- Sıra: önce kayıtlılar (kayıt sırasıyla), sonra tanınanlar (`z_e` azalan, sonra `x`, sonra `y` artan).

### 3. Seviyeler ve dilimler
- Seviyeler: normali `+Z` olan düzlemsel yüzlerin `origin_z` değerleri ve `zmin`; `tol` içinde birleştirilip sıralanır:
  `h_0 = zmin < h_1 < … < h_m = zmax`.
- Dilim `k`: `[h_k, h_{k+1}]`, kesit `z_k = (h_k + h_{k+1}) / 2` yüksekliğinde `section_z(z_k, tol_kesit)`.

### 4. Çokgen halkadan profile (yay geri kurma)
Dilimdeki dik silindirler: ekseni `Z`'ye paralel ve `z` aralığı `z_k`'yı içeren tüm silindirik yüzler (içbükey ve
dışbükey), merkez `c` (eksenin `xy`'si), yarıçap `R`.
1. Ardışık iki köşe `v_i, v_{i+1}` aynı silindire aittir ⇔ ikisi de `| |v − c| − R | ≤ tol` **ve** orta noktaları
   `| |(v_i + v_{i+1})/2 − c| − R | ≤ tol_kesit + tol` (gerçek kiriş, örn. D biçimli düzlük, bu yüzden yay sayılmaz).
2. Aynı silindire ait en uzun ardışık köşe dizisi tek `Arc` olur: uçlar daireye izdüşürülür
   (`p = c + R (v − c)/|v − c|`), yön `(v_i − c) × (v_{i+1} − c) > 0` ise `ccw=True`. Dizi halkanın tamamıysa tam daire
   (`p0 = p1`).
3. Kalan köşeler doğru parçalarıyla bağlanır; komşu yayın izdüşürülmüş ucu kullanılır. Ortadaki köşesi, komşularından
   geçen doğruya `≤ tol` uzak olan ardışık doğrular birleştirilir.
4. Sonuç kapalı `Profile`; `Region` kurulurken yönü SPEC 03 kuralına çevrilir (dış CCW, adalar CW).

İki halka **eşittir** ⇔ parça sayıları eşit ve bir döngüsel kaydırmayla her parçanın tipi, iki ucu ve (yayda)
merkezi ve yönü `tol` içinde eşleşir.

### 5. Kapalı cepler
Dilim `k`'daki her bölgenin her iç halkası `L` (delik halkası değilse) bir **boşluk imzası** verir:
`(L, adalar)`; adalar = aynı dilimde dış halkası `L`'nin içinde kalan bölgelerin dış halkaları (en içteki kapsayan halka
`L` olanlar; içerme: adanın ilk köşesi `L` çokgeninin içinde). Ardışık dilimlerde imzası eşit olan boşluklar
birleşir; her **en uzun ardışık dilim dizisi** bir `PocketFeature` olur: `z_bottom = h_alt`, `z_top = h_üst`,
`region = Region(outer=L, holes=adalar)`. Örnekler:
- Cep içinde daha derin cep: üst dilimde büyük halka, alt dilimde küçük halka → iki cep; büyük cep `[h_orta, zmax]`,
  küçük cep `[h_taban, h_orta]`. (CAM büyük cebi kendi tabanına kadar, küçüğü oradan aşağı işler.)
- Cep içinde cep tabanından alçak ada: adanın üstünden yukarıda ada yok → imza değişir → iki cep: üstte adasız,
  altta adalı. Böylece ada yüksekliğinin üstündeki malzeme de işlenir.

### 6. Açık bölgeler (basamak, dış kontur)
Zarf dikdörtgeni `E`: `stock` verildiyse stokun `xy` dikdörtgeni, yoksa parça kutusunun `xy` dikdörtgeni.
Dilim `k`'nın imzası: dilimdeki tüm bölgelerin dış halkaları kümesi (yayları geri kurulmuş). Tek bölge varsa ve dış
halkası `E`'ye eşitse dilimde açık bölge yoktur. Aksi hâlde imzası eşit en uzun ardışık dilim dizisi bir
`OpenFeature(boundary=E, islands=dış halkalar, z_top, z_bottom)` olur. Boşluk = `E ∖ ∪ islands`; adalar `E`'ye
değebilir (basamakta değer). Bu SPEC boşluğu çokgen farkıyla hesaplamaz; veri tam ve kesindir, işlemi seçmek
(dış kontur, açık cep) CAM'in işidir.

### 7. Yüz alma
`stock` verildi ve `stock.zmax − zmax_parça > tol` ise `FaceFeature(z=zmax_parça, depth=stock.zmax − zmax_parça,
boundary=E)`. Değilse yüz alma yok.

### 8. Köşe yarıçapı sınırı (takım seçimi)
Bölgenin içinden bakınca **dışbükey** köşeler takımın tam giremediği yerlerdir: `ccw=True` her yay (dış halka CCW,
ada halkası CW kuralıyla) ve keskin sola dönüşlü her köşe (gelen ve giden teğet için `t₁ × t₂ > tol`).
`r_corner = min(yay yarıçapları, keskin köşelerde 0)`; hiç yoksa `inf`. `max_tool_d = 2 · r_corner`.
`r_corner = 0` → her takım köşede malzeme bırakır (SPEC 03'ün köşe artığı); CAM uyarmalıdır.

### 9. Torna: profilden alın, kaba zarf, kanal, girinti
Girdi: SPEC 20 kuralındaki yarı kesit profili (`(u, v) = (z, x)`, açık, `side = "dis" | "ic"`). Hesap SPEC 20 gibi
dış çerçevede yapılır (`cam.lathe.prepare`: ön→arka yönlendirme, içte `x → −x` aynası) ve çıktılar geri aynalanır.
1. **Ön koşul**: profilde `t_z > ANG` olan nokta (öne dönen, arka kesim) → `CamError`. `stock` verildiyse dışta
   `max x ≤ D/2`, içte `min x ≥ d/2` (`tol` ile), değilse `CamError`.
2. **Bölme**: yaylar `x` uç değerlerinde (`t_x` işaret değiştirdiği noktada) bölünür.
3. **Zarf**: ön→arka gezide `X(z)` yürüyen en büyük değeri `M(s) = max_{s' ≤ s} x(s')`. Profilin `x < M − tol` olduğu her
   aralık, `x = M` sabit doğrusuyla köprülenir: köprü, profilin `M`'den aşağı indiği noktada başlar ve profilin
   tekrar `x = M`'ye ulaştığı ilk noktada (doğru veya yayla kesişim) biter. Profil bir daha `M`'ye çıkmazsa köprü
   profilin son `z`'sine kadar gider. Köprülenmiş profil `rough` = **kaba zarf**: SPEC 20 `is_monotone(rough, side)`
   doğrudur ve SPEC 20 `rough()` bunu kabul eder.
4. **Girinti**: her köprünün altında kalan alt profil bir girintidir, `x_top = M`.
   - Alt profil tam olarak *dik iniş → sabit x tabanı → dik çıkış* (üç doğru, iniş `t = (0, −1)`, taban
     `t = (−1, 0)`, çıkış `t = (0, +1)`) ise `Groove(z_left, z_right, x_top, x_bottom)`: `z_right` iniş duvarının `z`'si
     (ön), `z_left` çıkış duvarınınki (arka), `x_bottom` taban. Parametreler doğrudan SPEC 20 `groove()`'a gider.
   - Diğer her şekil (V kanal, yaylı tabanlı kanal, kademeli girinti) `Recess(profile, z_left, z_right, x_top)`:
     alt profil, ön→arka, `Profile(closed=False)`.
5. **Alın**: dışta, profil ilk parçası `x = 0`'dan başlayan sabit `z` doğrusuysa `z_face` = o `z`; `stock` verildiyse
   `face_depth = stock.zmax − z_face` (`≤ tol` ise alın yok). İç tarafta alın yok.
6. `finish` = girdi profilinin kendisi (yönlendirilmiş, aynalanmamış hâli).

## Dosyalar
- Yeni: `cam/features.py` (freze tanıma, §1–8), `cam/turn_features.py` (torna, §9)
- Yeni: `tests/cam/test_features.py` (`@pytest.mark.occt`), `tests/cam/test_turn_features.py` (OCCT'siz)
- Yeni: `durum/27-ozellik-tanima.md`
- Kullanılır (değişmez): `geometry/part.py` (`Part`, `Hole`), `cam/model.py` (`Stock`, `CylinderStock`, `CamError`),
  `cam/profile.py`, `cam/lathe.py`
- Dokunulmayacak: tüm `*/model.py`, `geometry/part.py`, `docs/yol-haritasi.md`, `DURUM.md`

## Arayüz
```python
# cam/features.py
@dataclass(frozen=True)
class FaceFeature:
    z: float  # yüz alma son seviyesi (parça üstü)
    depth: float  # stock.zmax − z
    boundary: Profile  # zarf dikdörtgeni E (CCW)


@dataclass(frozen=True)
class PocketFeature:
    region: Region  # dış = cep halkası, holes = adalar
    z_top: float
    z_bottom: float
    r_corner: float  # §8; keskin köşe → 0.0, köşe yok → inf

    @property
    def max_tool_d(self) -> float: ...  # 2 · r_corner


@dataclass(frozen=True)
class OpenFeature:
    boundary: Profile  # E
    islands: tuple[Profile, ...]
    z_top: float
    z_bottom: float


@dataclass(frozen=True)
class HoleFeature:
    hole: Hole
    source: str  # "kayit" | "tanima"

    @property
    def top_access(self) -> bool: ...  # axis == (0, 0, −1) (ANG içinde): üstten delinebilir


@dataclass(frozen=True)
class Features:
    faces: tuple[FaceFeature, ...]  # 0 veya 1 eleman
    pockets: tuple[
        PocketFeature, ...
    ]  # z_top azalan, sonra z_bottom azalan, sonra dış halkanın ilk köşesi (x, y) artan
    opens: tuple[OpenFeature, ...]  # z_top azalan
    holes: tuple[HoleFeature, ...]  # §2 sırası


def recognize(
    part: Part, stock: Stock | None = None, tol: float = 1e-3, hole_d_max: float = 20.0
) -> Features: ...


# cam/turn_features.py
@dataclass(frozen=True)
class Groove:
    z_left: float
    z_right: float
    x_top: float
    x_bottom: float


@dataclass(frozen=True)
class Recess:
    profile: Profile
    z_left: float
    z_right: float
    x_top: float


@dataclass(frozen=True)
class TurnFeatures:
    side: str
    z_face: float | None
    face_depth: float | None
    rough: Profile  # monoton kaba zarf (açık)
    finish: Profile  # girdi profili, ön→arka
    grooves: tuple[Groove, ...]  # ön→arka (z_right azalan)
    recesses: tuple[Recess, ...]  # ön→arka


def turn_features(
    profile: Profile, stock: CylinderStock | None = None, side: str = "dis", tol: float = 1e-3
) -> TurnFeatures: ...
```
Geçersiz girdi (`tol ≤ 0`, `hole_d_max ≤ 0`, sonlu olmayan değer, `side` hatalı, `Part` / `Profile` olmayan girdi) → `CamError`.

## Kabul kriterleri
Parçalar `geometry.features` / `geometry.holes` ile ya da testte doğrudan build123d ile kurulur (uydurma geometri).
Analitik değerler `1e-6` mm (alan `1e-6` bağıl) içinde.
- [ ] K1 **Yüz alma**: 100×60×20 blok, stok `[−2, 102]×[−2, 62]×[0, 22]` → bir `FaceFeature`, `z = 20`, `depth = 2`,
  `boundary` stok dikdörtgeni; stok üstü `20` iken yüz yok. (`test_features.py::test_yuz_alma`)
- [ ] K2 **Yuvarlak köşeli cep**: blok + `pocket(30, 30, 40, 30, 8, r=5)` → tek cep, `z_top = 20`, `z_bottom = 12`;
  dış halka 4 doğru + 4 `ccw` yay, yay merkezleri `(15, 20)`, `(45, 20)`, `(45, 40)`, `(15, 40)`, `R = 5`;
  alan `1200 − (4 − π)·25`; `r_corner = 5`, `max_tool_d = 10`. (`::test_yuvarlak_koseli_cep`)
- [ ] K3 **İç içe cep**: K2 + `pocket(30, 30, 16, 12, 12)` → iki cep, sırasıyla `[12, 20]` (40×30 halka) ve `[8, 12]`
  (16×12, alan 192, `r_corner = 0`). (`::test_ic_ice_cep`)
- [ ] K4 **Adalı cep, ada cepten alçak**: 60×40 cep derinlik 15 içinde Ø20, yükseklik 10 silindir ada → iki cep:
  `[zmax − 5, zmax]` adasız, `[zmax − 15, zmax − 5]` tek adalı (ada tam daire, `R = 10`, merkez tam). (`::test_adali_cep`)
- [ ] K5 **Kayıtlı delikler**: düz, havşalı, lambalı, dişli ve eğimli delik (SPEC 23) → her kayıt `source="kayit"` ile
  aynen; delik halkaları cep üretmez; havşa koni alanı alan dengesini bozmaz; `top_access` eğimlide `False`.
  (`::test_kayitli_delikler`)
- [ ] K6 **Tanınan delikler**: düz Ø8 boydan, lambalı (M6), dişli (M8, derinlik 12) ve Ø30 × 10 kör delikli blok STEP'e
  yazılıp okunur (kayıtlar düşer) → ilk üçü `source="tanima"` ile `d`, `depth`, `through`, `origin`, `cbore_d`,
  `cbore_depth` analitik (dişli delik diş bilgisi olmadan Ø6.75 kör delik); `hole_d_max`'tan büyük Ø30 kör silindir
  (STEP'te iki yüze bölünmüş) dairesel cep olur: `[10, 20]`, tam daire yay, `R = 15`. (`::test_taninan_delikler`)
- [ ] K7 **Açık bölge**: üst kenarı boyunca 10 mm genişlik, 5 mm derinlik basamaklı blok → bir `OpenFeature`,
  `[15, 20]`, adalar tek dikdörtgen halka (tam köşeler); stok `xy`'de parçadan büyükse en alt dilime kadar dış kontur
  açık bölgesi de çıkar. (`::test_acik_bolge`)
- [ ] K8 **2.5D değil** → `CamError`: `chamfer_top` pahı (eğik düzlem), üst kenar yuvarlatma (alan dengesi), alttan
  erişilen T-kanal (`−Z` yüz), stoktan taşan parça, üç kademeli delik. (`::test_25d_degil`)
- [ ] K9 **CAM'e girdi**: K2 cebi `cam.ops2d.pocket(f.region, Ø8 takım, Cut(z_top=f.z_top, z_bottom=f.z_bottom, …))`
  hatasız takım yolu verir; `f.max_tool_d`'den büyük takımla cep köşesinde artık kalacağı `r_corner` ile görünür;
  `top_access` delik SPEC 04 `hole_moves` ile `(x, y)` = `origin[:2]`, dip `origin_z − depth` olarak açılır.
  (`::test_cam_girdisi`)
- [ ] K10 **Torna zarfı ve kanal**: profil — alın `(60, 0)→(60, 10)`, Ø20 boy `→(40, 10)`, kanal (iniş
  `→(40, 8)`, taban `→(34, 8)`, çıkış `→(34, 10)`), Ø20 `→(20, 10)`, omuz `→(20, 15)`, Ø30 `→(0, 15)` →
  `rough` = aynı profil kanal yerine `(40, 10)→(34, 10)` köprüsüyle, `is_monotone` doğru; tek `Groove(34, 40, 10, 8)`;
  stok `zmax = 62` ile `z_face = 60`, `face_depth = 2`. (`test_turn_features.py::test_zarf_ve_kanal`)
- [ ] K11 **Genel girinti**: V kanal (`45°` iki eğik doğru) ve yay tabanlı kanal `Recess` olur, alt profiller tam;
  köprü yayla kesişimde yayın doğru noktasında biter (yarım küre bitişli profil: `x = M` doğrusu ile yay kesişimi
  analitik). (`::test_girinti`)
- [ ] K12 **İç taraf ve hatalar**: aynı kanal iç profilde (`side="ic"`) aynalanmış sonuç; arka kesimli profil
  (`t_z > 0`), stoktan taşan profil, hatalı `side` → `CamError`. (`::test_ic_taraf_ve_hatalar`)

## Kapsam dışı
- Katı parçadan dönel yarı kesit profili çıkarmak: ayrı SPEC ("Katı parçadan torna profili"). Bu SPEC profili `Profile` olarak girdi alır.
- Çok bağlamalı (alttan / yandan) işleme, 4–5 eksen; eğik düzlem, pah, yuvarlatma, serbest yüzey özellikleri
  (3B yüzey işleme SPEC 06'nın girdisi olan ağdır, özellik değildir).
- Açık bölgede çokgen farkı ve açık cep takım yolu; özelliklerden otomatik işlem / takım seçimi (işlem planlama).
- En dar boğaz (iki duvar arası en kısa mesafe) ölçümü; matkap ucu konili delik tabanı; üç ve daha fazla kademeli delik.
- Dış diş (milde diş kaydı yok); kayıt geometriye göre doğrulanmaz.
