# SPEC 28 — Katı parçadan torna profili: eksenden geçen yarı düzlem kesiti, doğru + yay uydurma

## Amaç
Dönel simetrik bir katı parçadan (`geometry.part.Part`) torna için yarı kesit profilini çıkarmak: parça, dönme
ekseninden geçen yarı düzlemle (`y = 0`, `x ≥ 0`) kesilir, kesit tam doğru ve yay parçalarına çevrilir (serbest
eğriler tolerans içinde doğru + yaya uydurulur) ve sonuç SPEC 20'nin `cam.profile.Profile` biçiminde döner: kapalı kesit
bölgesi, dış profil (`side="dis"`) ve varsa iç profil (`side="ic"`). Dönel olmayan parça sessizce kesilmez, hata verir.

Bu SPEC iki SPEC'in ortak girdisini üretir: SPEC 22 torna simülasyonu (kapalı bölge → `profile_rmap`) ve SPEC 27 özellik
tanıma (`turn_features(profile)`). İkisi de profili hazır alır; profil çıkarma yalnız burada yapılır.

## Teori

### Koordinatlar
- Parça kendi koordinatında verilir. Dönme ekseni `origin + s · axis` (`axis` birim). Varsayılan eksen parçanın `Z`
  eksenidir: `origin = (0, 0, 0)`, `axis = (0, 0, 1)` (tornada iş mili ekseni Z, SPEC 00 Ek 2 / SPEC 20).
- Kesit yarı düzlemi, eksen ve `xdir` birim vektörünün gerdiği `x ≥ 0` yarısıdır. `xdir`, global `X`'in eksene dik
  bileşeninin birimi; `|axis × X| < 1e-6` ise global `Y`'nin dik bileşeni. Varsayılan eksende `xdir = (1, 0, 0)`, yani
  yarı düzlem tam olarak `y = 0`, `x ≥ 0`'dır.
- Profil koordinatları **`(u, v) = (z, x)`** (SPEC 20 kuralı): bir 3B nokta `p` için `z = (p − origin) · axis`,
  `x = (p − origin) · xdir ≥ 0` (yarıçap). `z` parçanın kendi koordinatındaki eksen konumudur; ön yüzü `z = 0`'a
  kaydırma yapılmaz (iş sıfırı SPEC 14'ün işidir). Böylece profil, SPEC 22'nin parça ağından kestiği `y = 0` kesitiyle ve
  SPEC 27'nin parça koordinatlı örnekleriyle aynı çerçevededir.
- **Ön uç** büyük `z` tarafıdır (ayna `−axis` tarafında, SPEC 20). Parçayı öbür ucundan bağlamak için ekseni ters verin
  (`axis = (0, 0, −1)`): profil `z → −z` aynalanmış olarak döner.

### Dönel simetri kontrolü
Bir katı, ancak her yüzü aynı eksen etrafında bir dönel yüzeyse bu eksene göre dönel simetriktir. Yüzler OCCT yüzey
türüne göre sınıflanır (`d_tol = 1e-7` mm uzaklık, `a_tol = 1e-9` rad açı):

| Yüzey | Eksene göre dönel sayılır, eğer |
|---|---|
| Düzlem | normal ∥ `axis` (eksene dik alın / omuz yüzü) |
| Silindir, koni | yüzey ekseni ile dönme ekseni çakışık (yön ∥, eksen doğruları arası uzaklık ≤ `d_tol`) |
| Küre | merkez eksen doğrusu üzerinde |
| Torus | torus ekseni dönme ekseniyle çakışık |
| Dönel yüzey (`SurfaceOfRevolution`) | dönme ekseni çakışık |
| Diğer (B-spline, Bezier, ofset, ekstrüzyon yüzeyi) | **bilinmiyor**: aşağıdaki Pappus kontrolüne bırakılır |

Sınıflamada "dönel değil" çıkan tek bir yüz varsa parça reddedilir (düzlük, kama yuvası, çapraz delik, altıgen, eksen dışı
delik bu yolla yakalanır) ve hata mesajı yüz numaralarını (`PlanarFace.index` ile aynı OCCT yüz sırası) listeler.

Sınıflama geçse de (bilinmeyen yüz varken ya da yüzler bölünmüşken) kesit iki bağımsız Pappus–Guldin denetiminden geçer:

- Hacim: `V_P = 2π · ∬ x dA`. Yön CCW iken Green teoremiyle `∬ x dA = −½ ∮ x² dz`.
- Yüzey alanı: `S_P = 2π · Σ ∫ x ds`, eksen üzerindeki (`x = 0`) kenarlar hariç tüm kesit kenarları üzerinden.

Kabul: `|V_P − V| ≤ ε_V`, `|S_P − S| ≤ ε_S` (`V = part.volume`, `S = part.area`), burada
`ε_V = 1e-6 · V + 2π · x_max · tol · L_u` ve `ε_S = 1e-6 · S + 2π · (x_max + L_u) · tol`; `L_u` uydurulmuş (serbest
eğriden gelen) kenarların toplam boyu, `x_max` kesitin en büyük yarıçapı. Sadece doğru ve yaydan oluşan kesitte
`L_u = 0`. Tutmazsa `CamError` (mesajda `V`, `V_P`, `S`, `S_P`).
Kaynak: Pappus–Guldin teoremleri; Stewart, *Calculus*, "Volumes of revolution" ve "Areas of surfaces of revolution".

### Eksen seçimi
- `axis` verilirse aynen kullanılır (birime çevrilir; sıfır ya da sonlu olmayan vektör → `CamError`).
- `axis="auto"`: dönel yüzlerin (silindir, koni, torus, dönel yüzey) eksenleri toplanır. Hepsi `d_tol` / `a_tol` içinde
  tek bir doğruysa o eksen kullanılır; kürelerin merkezi de bu doğru üzerinde olmalıdır. Yön işareti, mutlak değerce en
  büyük bileşeni pozitif olacak şekilde seçilir; `origin`, global orijinin eksen doğrusuna izdüşümüdür. Eksen bulunamazsa
  (hiç eksenli yüz yok, örn. yalnız küre) ya da birden fazla eksen varsa → `CamError` (bulunan eksenler mesajda);
  ekseni açık verin.

### Kesit
1. Yarı düzlem, parçanın sınır kutusunu her yönde `10 · tol + 1` mm aşan bir dikdörtgen yüz olarak kurulur
   (`z` aralığı × `[0, x_üst]`) ve katıyla ortak kısmı (`BRepAlgoAPI_Common`) alınır.
2. Sonuç tek bir yüz olmalıdır. Boş → `CamError` ("eksen parçayı kesmiyor"); birden fazla yüz (ayrık halkalar, birden fazla
   katı) → `CamError`; yüzün iç halkası (kesitte delik = parçada kapalı toroidal boşluk, tornayla işlenemez) → `CamError`.
3. Kenarlar `(z, x)` düzlemine taşınır:
   - OCCT doğrusu → `Line` (uçlar OCCT köşelerinden, tam).
   - OCCT çemberi → `Arc` (merkez, yarıçap ve yön OCCT eğrisinden, tam). Dönel parçada çemberler küre ve torustan gelir.
   - Diğer eğriler (elips, B-spline, Bezier) → kiriş sapması `≤ tol / 4` olan çokgen (uçları köşelere tam oturur), sonra
     aşağıdaki uydurma.
4. Uç uca bağlama: komşu kenar uçları `LINK_TOL = 1e-7` mm içinde aynı noktaya oturtulur (ortak köşe tek koordinat);
   `|x| ≤ LINK_TOL` olan uçlar `x = 0`'a çekilir. Halka CCW yönlendirilir (`(z, x)` düzleminde işaretli alan > 0, SPEC 03
   bölge kuralı).
5. Birleştirme: art arda iki doğru aynı doğru üzerindeyse (yön farkı `≤ a_tol`, ortak uç) birleşir; art arda iki yay aynı
   merkez (`≤ LINK_TOL`), aynı yarıçap (`≤ ARC_TOL`) ve aynı yöndeyse birleşir. Bölünmüş yüzlerden (dikiş, ayrılmış
   silindir) gelen parçalı kenarlar böylece tek parça olur.

### Serbest eğri uydurma (doğru + yay)
Çokgen `q_0 … q_n` (eğri üzerinde, uçlar köşelerde) açgözlü yöntemle kapsanır: `i` başlangıcından en büyük `j` aranır,
öyle ki `q_i → q_j` arasındaki aday parça şunu sağlar:
- Aday: doğru `q_i q_j`, ya da `q_i`, `q_m` (`m = ⌊(i + j)/2⌋`) ve `q_j`'den geçen yay (yön, `q_m`'nin hangi yanda olduğundan).
- Koşul: `q_i … q_j` noktalarının ve ardışık noktaların orta noktalarının adaya uzaklığı `≤ tol / 2`; yayda ayrıca
  noktalar yay üzerinde `q_i`'den `q_j`'ye açısal olarak sıralıdır ve yarıçap `≤ R_düz = 1e6` mm'dir (daha büyük
  yarıçaplı yay doğru sayılır).
- Aynı `j`'ye doğru da yay da ulaşıyorsa doğru seçilir; yoksa daha uzağa ulaşan seçilir. Sonra `i ← j`.
Toplam sapma sınırı: örnekleme `tol / 4` + uydurma `tol / 2` < `tol`. Uydurulan parçalar uçlarda sürekli (G0) ama teğet
sürekliliği (G1) garanti edilmez. Uydurma sonrası 5. adımdaki birleştirme tekrar uygulanır.
Kaynak: Meek & Walton, "Approximating smooth planar curves by arc splines", *J. Comput. Appl. Math.* 59 (1995);
SPEC 27 §4 (çokgen halkadan yay geri kurma) aynı tolerans mantığını freze kesitinde kullanır.

### Kapalı kesitten dış ve iç profil
Kesit halkası CCW iken (iç yukarıda, eksen altta) eksen üzerindeki kenarlar arka→ön (`+z`), dış kontur ön→arka (`−z`)
gezilir. Tanımlar:
- `P_ön`: halkanın en büyük `z`'li noktası; eşitlikte en küçük `x`'li olan (ön yüzün eksene ya da deliğe yakın ucu).
- `P_arka`: en küçük `z`'li nokta; eşitlikte en büyük `x`'li olan (arka yüzün dış ucu).
- **Dış profil** `outer`: halkanın CCW yönde `P_ön`'den `P_arka`'ya giden alt zinciri. Ön yüzle başlar (alın, `t = (0, +1)`),
  dış konturu ön→arka izler, arka yüzü **içermez**. `Profile(closed=False)`, SPEC 20'de `side="dis"`.
- **İç profil** `inner`: CCW yönde `P_arka`'dan `P_ön`'e giden alt zincirden (a) baştaki arka yüz parçaları (`z = z_min`
  doğruları) ve (b) eksen üzerindeki (`x ≤ LINK_TOL` her iki uçta) son kenara kadar her şey atılır; kalan ters çevrilir
  (ön→arka). Boş kalırsa `None`. Sonuç: boydan boya delikte delik duvarı, kör delikte duvar + dip (matkap ucu konisi eksene
  iner). `side="ic"`.
- Arka taraftan açılmış delik iç profile girmez (ikinci bağlama işidir): parçayı ters eksenle ayrıca çıkarın.

## Dosyalar
- Yeni: `cam/turn_profile.py` (`TurnProfile`, `profile_from_section`, `turn_profile`, uydurma ve bölme yardımcıları)
- Yeni: `geometry/revolve.py` (kesit, yüz sınıflama, otomatik eksen: `Part.axial_section`'ın gövdesi; build123d / OCP
  sadece burada)
- Yeni: `tests/cam/test_turn_profile.py` (OCCT'siz: elle kurulan `AxialSection` ile bölme, birleştirme, uydurma),
  `tests/cam/test_turn_profile_occt.py` (`@pytest.mark.occt`: gerçek parçalar)
- Yeni: `durum/28-torna-profili.md`
- Ön koşul (ayrı arayüz PR'ı, kullanıcı onayı, `geometry/part.py` sahibi thread yapar): aşağıdaki `SectionEdge`,
  `SectionFace`, `AxialSection` kayıtları ve `Part.axial_section` imzası (`geometry/revolve.py`'ye devreder).
- Dokunulmayacak: `cam/model.py`, `cam/profile.py`, `cam/lathe.py`, `geometry/part.py` (arayüz PR'ı dışında), SPEC 20 / 22 /
  27 dosyaları.
- Bağımlılık: `cam.turn_profile` → `geometry.part` (yalnız `Part` ve kesit kayıtları), `cam.profile`, `cam.model`
  (`CamError`, `ARC_TOL`), `cam.geom2d` (`TOL`, `LINK_TOL`). Yeni üçüncü taraf bağımlılık yok.

## Arayüz

### Arayüz PR'ı: `geometry/part.py` eki
```python
@dataclass(frozen=True)
class SectionEdge:
    """Eksenden geçen yarı düzlem kesitinde bir kenar; koordinatlar (z, x) [mm]."""

    kind: str  # "line" | "arc" | "curve"
    points: np.ndarray  # line, arc: (2, 2) [p0, p1]; curve: (k, 2), k ≥ 2, kiriş sapması ≤ tol/4
    center: np.ndarray | None = None  # arc: (2,)
    ccw: bool = True  # arc: (z, x) düzleminde saat yönü tersi


@dataclass(frozen=True)
class SectionFace:
    """Kesitte bir malzeme yüzü: dış halka CCW, iç halkalar CW; her halka uç uca sıralı kenarlar."""

    outer: tuple[SectionEdge, ...]
    holes: tuple[tuple[SectionEdge, ...], ...] = ()


@dataclass(frozen=True)
class AxialSection:
    origin: np.ndarray  # (3,) eksen noktası, parça koordinatı
    axis: np.ndarray  # (3,) birim, +z (ön) yönü
    xdir: np.ndarray  # (3,) birim, axis'e dik, kesit yarı düzleminin +x yönü
    faces: tuple[SectionFace, ...]
    off_axis_faces: tuple[int, ...]  # bu eksene göre dönel OLMAYAN yüzler (OCCT yüz sırası)
    unknown_faces: tuple[int, ...]  # türü sınıflanamayan yüzler (B-spline vb.)


class Part:
    def axial_section(self, origin=(0.0, 0.0, 0.0), axis=(0.0, 0.0, 1.0), tol: float = 1e-3) -> AxialSection:
        """Eksenden geçen x ≥ 0 yarı düzlem kesiti. axis="auto" → dönel yüzlerden eksen bulunur.
        Sınıflama ve kesit; doğrulama ve uydurma yapmaz. Geçersiz eksen / bulunamayan eksen → GeometryError."""
```

### `cam/turn_profile.py`
```python
@dataclass(frozen=True)
class TurnProfile:
    section: Profile  # kapalı, CCW, (z, x), her noktada x ≥ 0
    outer: Profile  # açık, ön→arka, SPEC 20 side="dis"
    inner: Profile | None  # açık, ön→arka, SPEC 20 side="ic"; delik yoksa None
    origin: np.ndarray  # (3,)
    axis: np.ndarray  # (3,) birim
    xdir: np.ndarray  # (3,) birim
    fitted_length: float  # L_u: serbest eğriden uydurulan kenarların toplam boyu [mm]; tam kesitte 0


def profile_from_section(sec: AxialSection, tol: float = 1e-3) -> TurnProfile:
    """OCCT'siz: kenarları Line/Arc'a çevirir, bağlar, birleştirir, uydurur, dış/iç profili böler.
    off_axis_faces doluysa, yüz sayısı 1 değilse ya da yüzde iç halka varsa → CamError."""


def turn_profile(part: Part, axis=(0.0, 0.0, 1.0), origin=(0.0, 0.0, 0.0), tol: float = 1e-3) -> TurnProfile:
    """part.axial_section + profile_from_section + Pappus hacim ve alan denetimi.
    axis="auto" desteklenir. Tüm hatalar CamError (GeometryError da CamError'a çevrilir, mesaj korunur)."""
```
Geçersiz girdi → `CamError`: `tol ≤ 0` ya da sonlu değil, `Part` olmayan `part`, sıfır / sonlu olmayan `axis` ya da
`origin`, `axis` ne vektör ne `"auto"`.

## Kabul kriterleri
Uzunluk ve koordinat toleransı, aksi yazmadıkça `1e-9` mm (OCCT tam eğrileri); hacim ve alan `rel 1e-9`.

- [ ] K1 **Basamaklı mil** (Ø40×40, `z ∈ [0, 40]` + Ø20×20, `z ∈ [40, 60]`, varsayılan Z ekseni): `outer` tam olarak
  `(60, 0)→(60, 10)→(40, 10)→(40, 20)→(0, 20)` (4 doğru), `inner is None`; `section` 6 doğru, alan `40·20 + 20·10`;
  `fitted_length == 0`; `V_P = π(20²·40 + 10²·20)`. (`test_turn_profile_occt.py::test_basamakli_mil`)
- [ ] K2 **Koni, torus radyüsü ve küre uç**: `revolve` ile kurulmuş parça (koni yarım açısı 30°, omuzda `R = 3` iç radyüs,
  önde `R = 10` yarım küre): koni doğru, radyüs merkezi `(z_c, x_c)` ve `R = 3`, `ccw = False` (içbükey); küre yayı merkezi
  eksende, `R = 10`, `ccw = True`; `V_P` kapalı form (silindir + koni gövdesi + yarım küre − radyüs dolgusu, Pappus).
  (`::test_koni_radyus_kure`)
- [ ] K3 **Boydan delikli burç** (`Ø50/Ø30 × 40`): `outer` `(40, 15)→(40, 25)→(0, 25)`; `inner` ön→arka tek doğru
  `(40, 15)→(0, 15)`; `section` alanı `10·40`; `V_P = π(25² − 15²)·40`. (`::test_delikli_burc`)
- [ ] K4 **Kör delik, 118° matkap ucu** (Ø40×50 mil, önden Ø10, 30 derin, koni dip): `inner` = delik duvarı
  `(50, 5)→(20, 5)` + koni `(20, 5)→(20 − 5/tan 59°, 0)`, eksende biter; `outer` ön yüzle `(50, 5)`'ten başlar.
  (`::test_kor_delik`)
- [ ] K5 **Ters eksen**: K1 milinde `axis = (0, 0, −1)` → `outer` `(0, 0)→(0, 20)→(−40, 20)→(−40, 10)→(−60, 10)`
  (arka uç artık ön). (`::test_ters_eksen`)
- [ ] K6 **Eksen X'te modellenmiş parça**: K1 mili `Y` ekseni etrafında 90° döndürülmüş (`axis = (1, 0, 0)`) ve ayrıca
  `axis="auto"` ile: profil K1 ile `1e-9` içinde aynı; `auto` ekseni `(1, 0, 0)` bulur. (`::test_eksen_x`, `::test_auto_eksen`)
- [ ] K7 **Otomatik eksen hataları**: yalnız küre → `CamError`; iki farklı eksenli silindir (eksen dışı delik) → `CamError`,
  mesajda iki eksen. (`::test_auto_eksen_hata`)
- [ ] K8 **Dönel olmayan parça reddi**: K1 milinde (a) `z ∈ [5, 25]` boyunca 2 mm düzlük, (b) Ø6 çapraz delik, (c) altıgen
  baş (SW 30) → `CamError`, mesaj dönel olmayan yüzlerin numaralarını içerir ve bu numaralar `part.planar_faces()` /
  `part.cylindrical_faces()` ile aynı yüzleri gösterir. (`::test_donel_olmayan`)
- [ ] K9 **Serbest eğri uydurma, elips uç**: Ø40 silindir (`z ∈ [0, 40]`) önüne yarı eksenleri `a = 20` (radyal),
  `b = 30` (eksenel), merkezi `(z, x) = (40, 0)` olan yarım sferoid (elips yayının `revolve`'u; OCCT yüzü dönel yüzey,
  kesit kenarı elips verir). `tol ∈ {1e-2, 1e-3}` için: profil yalnız
  `Line`/`Arc`; uydurulmuş her parçanın elipse yoğun örneklemde (parça başına 200 nokta) en büyük uzaklığı `≤ tol`, elipsin
  her noktasının profile uzaklığı `≤ tol` (iki yönlü Hausdorff); parçalar uç uca (`LINK_TOL`); uçlar elips uçlarına tam
  oturur; `fitted_length` elips yay boyuyla `rel 1e-3` içinde; `|V_P − V| ≤ ε_V`. (`::test_elips_uydurma`)
- [ ] K10 **Pappus denetimi**: K1–K4 ve K9 parçalarında `|S_P − part.area| ≤ ε_S` ve `|V_P − part.volume| ≤ ε_V`. OCCT'siz:
  `profile_from_section`'a eksende olmayan, alanı bilinen bir kesit verilip `V_P` kapalı formla `1e-12` göreli.
  (`test_turn_profile.py::test_pappus`, `test_turn_profile_occt.py::test_pappus_parca`)
- [ ] K11 **Birleştirme ve bağlama (OCCT'siz)**: elle kurulan `AxialSection`: aynı doğru üzerinde üç parçalı silindir kenarı
  → tek `Line`; aynı merkezli iki yay → tek `Arc`; uçları `5e-8` mm kayık kenarlar → tek koordinatta birleşik köşe;
  `x = 3e-8` uç → `x = 0`. (`test_turn_profile.py::test_birlestirme`, `::test_baglama`)
- [ ] K12 **Bölme kuralları (OCCT'siz)**: elle kurulan kesitlerle `P_ön` / `P_arka` eşitlik kuralları (ön yüz deliğe kadar,
  arka yüz hariç), ön ucu eksende biten kubbe (`inner is None`, `outer` `x = 0`'dan başlar), arkadan delik (`inner`'a girmez).
  (`::test_bolme`)
- [ ] K13 **Geçersiz kesit (OCCT'siz)**: iki yüz → `CamError`; iç halkalı yüz → `CamError`; boş kesit → `CamError`;
  `off_axis_faces` dolu → `CamError` (numaralar mesajda). Geçersiz girdiler (`tol ≤ 0`, `nan`, sıfır eksen, `Part` olmayan
  girdi) → `CamError`. (`::test_gecersiz`)
- [ ] K14 **SPEC 20 ve SPEC 27 uyumu**: K1 ve K2 `outer`'ı `cam.lathe.orient` sonrası değişmez, K1 için
  `cam.lathe.is_monotone(outer) is True`; K1 `outer` + uygun silindir stokla SPEC 20 `rough` ve `finish` hatasız çalışır;
  K3 `inner` ile `side="ic"` `finish` hatasız çalışır. (`test_turn_profile_occt.py::test_spec20_uyum`)
- [ ] K15 **STEP gidiş-dönüş**: K2 parçası `to_step` / `from_step` sonrası aynı profil (`1e-6` mm). (`::test_step`)

## Kapsam dışı
- **Dönel olmayan parçanın torna zarfı** (düzlüklü / kamalı / çapraz delikli milden "önce tornada işlenecek dönel gövde"):
  bu SPEC reddeder; zarf ayrı bir SPEC'tir. Freze özellikleri SPEC 27'nin işidir.
- Diş helisi: helisel yüz dönel sayılmaz → reddedilir. Dişli parçalar modelde diş dibi / diş üstü silindiriyle verilmelidir.
- Arka taraftan açılmış delik ve ikinci bağlama planı (iki bağlamanın profillerini birleştirme).
- Kesitte iç boşluk (kapalı toroidal boşluk) ve birden fazla katı.
- Uydurulan parçalarda teğet sürekliliği (G1) ve en az sayıda yay garantisi (biark uydurma).
- İş sıfırı / WCS kaydırması (SPEC 14), stok seçimi, takım yolu (SPEC 20), simülasyon (SPEC 22), özellik tanıma (SPEC 27).
