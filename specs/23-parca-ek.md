# SPEC 23 — Parça ek işlemleri: yuvarlatma (fillet), havşa, dişli delik, eğimli delik

## Amaç
SPEC 02'nin bıraktığı dört parça işlemini (yuvarlatma, havşalı delik, dişli delik, eğimli / açılı delik)
analitik değerle doğrulanmış şekilde eklemek ve her deliği CAM'in (delme çevrimi G81/G83, havşa, kılavuz)
doğrudan okuyabileceği bir **delik kaydı** (`Hole`) olarak parçaya iliştirmek.

## Teori
Çekirdek OCCT'dir (build123d üzerinden); fillet ve boolean işlemleri bizim değil. Bizim işimiz sade API,
CAM'e uygun delik bilgisi ve her sonucun **el hesabıyla** doğrulanması.
Koordinat kuralı SPEC 02 ile aynı: blok min köşesi orijinde, "üst yüz" = `zmax`, düz delikler üstten −Z.

### Yuvarlatma (fillet), yarıçap r
Bir dışbükey dik kenar yuvarlatılınca kesitten `r × r` karenin çeyrek daire dışında kalan parçası kalkar:
`A_f = (1 − π/4) r²`. Bu parçanın ağırlık merkezinin duvara uzaklığı
`x̄ = r (10 − 3π) / (3 (4 − π))` (kare r/2'de, çeyrek daire r − 4r/(3π)'de; farkın momenti).

- **Dikey kenarlar** (blok a × b × c, 4 dikey kenar): `ΔV = (4 − π) r² c`;
  yan yüzler her kenarda `2r` düzlem kaybeder, `πr/2` yay kazanır; üst ve alt yüz `(4 − π) r²` küçülür:
  `ΔS = −[(8 − 2π) r c + 2 (4 − π) r²]`
- **Üst kenarlar** (blok, `zmax`'taki 4 kenar, dikey kenarlar keskin kalır): her kenar `A_f · L` kaldırır;
  köşede iki kenarın kaldırdığı bölgeler `[0, r]³` içinde örtüşür. z derinliğinde her kenarın kaldırdığı
  genişlik `g = r − √(r² − s²)` (s = r − z'); örtüşme `∫₀^r g² ds = r³ (5/3 − π/2)`. 4 köşe için
  `ΔV = (1 − π/4) r² · 2(a + b) − 4 r³ (5/3 − π/2)`
  (OCCT ön deneme: a=100, b=60, c=20, r=4 → 1074.21860 mm³, formülle rel 3e-11)
- **Tüm kenarlar** (blok, 12 kenar; köşeler küre sekizde biri olur). `a' = a − 2r` vb.:
  `V = a'b'c' + 2r (a'b' + b'c' + c'a') + π r² (a' + b' + c') + (4/3) π r³`
  `S = 2 (a'b' + b'c' + c'a') + 2π r (a' + b' + c') + 4π r²`
- **Dairesel kenar** (Pappus): kaldırılan kesit `A_f`, eksenden `ρ` uzaklıkta döner: `ΔV = 2π ρ A_f`.
  Silindir (yarıçap R) üst kenarı: `ρ = R − x̄`. Boydan boya delik (yarıçap r_h) ağzı: `ρ = r_h + x̄`.

### Havşalı delik (countersink)
Delik çapı d, havşa ağız çapı D (> d), tepe açısı α (ör. 90°), delik derinliği t (üst yüzden, düz dip).
Koni yüksekliği `h = (D − d) / (2 tan(α/2))`, `t > h` olmalı. Kaldırılan hacim (kesik koni + silindir):
`ΔV = (π h / 3)(R² + R r + r²) + π r² (t − h)`, `R = D/2`, `r = d/2`. Boydan boyada `t = c`.

### Lambalı delik (counterbore, düz havşa)
Geçiş deliği çapı d, lamba çapı D (> d), lamba derinliği t_c, delik derinliği t (> t_c, üst yüzden, düz dip).
İki eş eksenli silindir: `ΔV = π (D² − d²) t_c / 4 + π d² t / 4`. Boydan boyada `t = c`.
Civata adıyla çağrılınca varsayılanlar ISO 4762 imbus civata (baş çapı d_k, baş boyu k = d_n) içindir:
geçiş deliği ISO 273 orta seri, lamba çapı ve derinliği DIN 974-1 (pulsuz) satırı:

| Civata | d (geçiş) | D (lamba) | t_c (lamba derinliği) | ISO 4762 d_k / k |
|---|---|---|---|---|
| M3 | 3.4 | 6.5 | 3.4 | 5.5 / 3 |
| M4 | 4.5 | 8.0 | 4.4 | 7 / 4 |
| M5 | 5.5 | 10.0 | 5.4 | 8.5 / 5 |
| M6 | 6.6 | 11.0 | 6.4 | 10 / 6 |
| M8 | 9.0 | 15.0 | 8.6 | 13 / 8 |
| M10 | 11.0 | 18.0 | 10.6 | 16 / 10 |
| M12 | 13.5 | 20.0 | 12.6 | 18 / 12 |
| M14 | 15.5 | 24.0 | 14.6 | 21 / 14 |
| M16 | 17.5 | 26.0 | 16.6 | 24 / 16 |
| M20 | 22.0 | 33.0 | 20.6 | 30 / 20 |
| M24 | 26.0 | 40.0 | 24.8 | 36 / 24 |

Tablo tutarlılığı (testle denetlenir): her satırda `D > d_k`, `t_c > k`, `d > d_n`.
OCCT ön deneme (blok c = 20; M8 boydan boya, M8 kör t = 14, M6 boydan boya): rel ≤ 1.2e-14.

### Dişli delik (tapped hole)
Diş **görsel / kozmetiktir**: geometride sadece kılavuz matkabı deliği vardır, diş bilgisi `Hole` kaydında
durur (helis modellenmez; CAM ve teknik resim diş bilgisini kayıttan okur).
ISO metrik (ISO 261 / ISO 724): kılavuz matkabı `d_m = d_n − P`.
Kaba hatve tablosu: M3 0.5, M4 0.7, M5 0.8, M6 1.0, M8 1.25, M10 1.5, M12 1.75, M14 2.0, M16 2.0,
M20 2.5, M24 3.0. İnce hatve `"M8x1"` biçiminde yazılır (`d_n = 8`, `P = 1`).
`ΔV = π d_m² t / 4`; diş derinliği `t_d ≤ t`.

### Eğimli / açılı delik
Giriş noktası p parça yüzeyinde, birim delme yönü n malzemeye doğru, çap d.
- Boydan boya, iki paralel düzlem arasında (blok kalınlığı c, n ile −Z arası açı θ):
  Cavalieri: yatay kesit `π r² / cos θ` elips → `ΔV = π r² c / cos θ`; eksen boyu `L = c / cos θ`.
- Kör, düz dip (dip n'ye dik), eksen boyunca derinlik t: eğik üst kesim eksene göre simetrik olduğundan
  `ΔV = π r² t` (`t > r tan θ` iken, yani ağız tümüyle üst düzlemde).
- OCCT ön deneme (c = 20, θ = 30°, r = 4): boydan boya rel 4e-13, kör t = 12 rel 2e-10.

Kaynaklar: build123d / OCCT belgeleri (BRepFilletAPI_MakeFillet); ISO 261, ISO 724 (metrik diş, kılavuz
matkabı); ISO 4762 (imbus civata), ISO 273 (geçiş delikleri), DIN 974-1 (lamba ölçüleri); Pappus–Guldin teoremi; Cavalieri ilkesi; Machinery's Handbook, "Countersinks" ve "Tap drill sizes".

## Delik kaydı (`Hole`) — CAM için
Her delik işlemi dönen parçaya bir `Hole` ekler. CAM (SPEC 04 G81/G83, ileride havşa ve G84 kılavuz)
geometriyi yeniden tanımadan bu kayıttan delme çevrimi kurar.

```python
@dataclass(frozen=True)
class Hole:
    origin: np.ndarray  # (3,) mm, giriş noktası: delik ekseninin parça yüzeyini deldiği yer
    axis: np.ndarray  # (3,) birim, delme yönü (malzemeye doğru); takım ekseni = −axis
    d: float  # mm, matkap çapı (dişli delikte kılavuz matkabı d_m)
    depth: float  # mm, eksen boyunca giriş noktasından düz dibe; boydan boyada çıkışa kadar
    through: bool
    csk_d: float = 0.0  # mm, havşa ağız çapı; 0 → havşa yok
    csk_angle: float = 0.0  # derece, havşa tepe açısı; havşa yoksa 0
    cbore_d: float = 0.0  # mm, lamba çapı; 0 → lamba yok
    cbore_depth: float = 0.0  # mm, lamba derinliği (giriş noktasından eksen boyunca)
    thread: str = ""  # "M8", "M8x1"; "" → dişsiz
    thread_d: float = 0.0  # mm, nominal diş çapı d_n
    pitch: float = 0.0  # mm, hatve P
    thread_depth: float = 0.0  # mm, diş derinliği t_d
```

Doğrulama (`__post_init__`, hepsi `GeometryError`): değerler sonlu; `axis` birim (|n| − 1 ≤ 1e-9);
`d > 0`, `depth > 0`; havşa varsa `csk_d > d` ve `0 < csk_angle < 180`;
lamba varsa `cbore_d > d` ve `0 < cbore_depth < depth`; havşa ve lamba aynı delikte olamaz; diş varsa `thread_d > d`,
`pitch > 0`, `0 < thread_depth ≤ depth`.

Kayıt **tasarım niyetidir**: parçanın sonraki işlemleri (pah, cep, fillet, yeni delik) kayıtları korur ama
geometriye göre yeniden doğrulamaz. STEP / STL gidiş-dönüşünde kayıt kaybolur (STEP sadece geometri taşır).

## Dosyalar
- **Önce ayrı arayüz PR'ı** (bu SPEC'in PR'ı değil): `geometry/part.py`'ye `Hole` dataclass'ı,
  `Part(shape, name="parca", holes=())` parametresi ve `Part.holes -> tuple[Hole, ...]` özelliği.
  Mevcut `Part(shape, name)` çağrıları aynen çalışır (varsayılan boş).
- Yeni: `geometry/holes.py` (havşalı, lambalı, dişli, eğimli delik; diş ve lamba tabloları), `geometry/fillet.py`,
  `tests/geometry/test_holes.py`, `tests/geometry/test_fillet.py`, `durum/23-parca-ek.md`
- Değişecek: `geometry/features.py` — SPEC 02 işlemleri (`hole`, `pocket`, `chamfer_top`) girdi parçanın
  `holes` kayıtlarını yeni parçaya taşır; `hole` kendi kaydını ekler
  (`origin = (x, y, zmax)`, `axis = (0, 0, −1)`). Hacim / alan davranışı değişmez, SPEC 02 testleri değişmez.
  `geometry/__init__.py` (sadece dışa açılan adlar).
- Dokunulmayacak: `pyproject.toml`, `cam/`, `assy/`, diğer paketler. Yeni bağımlılık yok.

Tüm testler `@pytest.mark.occt` işaretli. Hiçbir işlem verilen `Part`'ı değiştirmez; her zaman yeni `Part`.
Geçersiz girdi ve OCCT başarısızlığı → `geometry.part.GeometryError` (sessiz hata yok).
Malzeme kaldırmayan işlem (ΔV ≤ 1e-9 mm³) → `GeometryError` (SPEC 02 ile aynı kural).

## Arayüz

### `geometry/fillet.py`
- `fillet_vertical(part, r) -> Part` — Z eksenine paralel tüm dışbükey (dış) doğrusal kenarlar;
  silindirik yüzlerin dikiş (seam) kenarları ve içbükey kenarlar (cep köşesi) seçilmez.
- `fillet_top(part, r) -> Part` — üst yüzün (`zmax`, +Z normalli düzlemsel yüzler) tüm kenarları
  (delik ağızları dahil; `chamfer_top` ile aynı seçim).
- `fillet_all(part, r) -> Part` — parçanın tüm kenarları.
- Ortak hatalar: `r <= 0`, seçilecek kenar yok, OCCT fillet'i kuramıyor (ör. r kenar boyundan / yüz
  genişliğinden büyük) → `GeometryError`. Fillet `holes` kayıtlarını korur.

### `geometry/holes.py`
- `THREADS_COARSE: dict[str, float]` — yukarıdaki kaba hatve tablosu (`"M8": 1.25`, ...).
- `parse_thread(spec) -> tuple[float, float]` — `"M8"` → `(8.0, 1.25)`, `"M8x1"` → `(8.0, 1.0)`.
  Tabloda olmayan kaba diş, bozuk yazım, `P >= d_n` → `GeometryError`.
- `countersink_hole(part, x, y, d, csk_d, csk_angle=90.0, depth=None) -> Part` — üstten −Z, eksen (x, y).
  `depth=None` → boydan boya. `csk_d <= d`, açı (0, 180) dışında, `depth <= h` (havşa konisi dibe
  ulaşıyor), `depth > yükseklik` → `GeometryError`. Kayıt: `csk_d`, `csk_angle` dolu.
- `CBORE_ISO4762: dict[str, tuple[float, float, float]]` — yukarıdaki lamba tablosu,
  `"M8": (9.0, 15.0, 8.6)` = (d, D, t_c).
- `counterbore_hole(part, x, y, screw=None, d=None, cbore_d=None, cbore_depth=None, depth=None) -> Part` —
  üstten −Z, eksen (x, y). `screw="M8"` verilirse eksik ölçüler tablodan gelir, açıkça verilen ölçü tablonun
  önüne geçer; `screw=None` iken `d`, `cbore_d`, `cbore_depth` üçü de zorunlu. `depth=None` → boydan boya.
  Tabloda olmayan civata, eksik ölçü, `cbore_d <= d`, `cbore_depth >= depth` (veya boydan boyada ≥ yükseklik),
  `depth > yükseklik` → `GeometryError`. Kayıt: `cbore_d`, `cbore_depth` dolu.
- `tapped_hole(part, x, y, thread, depth=None, thread_depth=None) -> Part` — üstten −Z, kılavuz matkabı
  `d_m = d_n − P` ile delik. `thread_depth=None` → `depth` (boydan boyada parça yüksekliği).
  `thread_depth > depth` → `GeometryError`. Kayıt: `thread`, `thread_d`, `pitch`, `thread_depth` dolu.
- `inclined_hole(part, p, n, d, depth=None) -> Part` — giriş noktası p (3,) parça yüzeyinde
  (uzaklık ≤ 1e-6 mm), yön n (3,) normalize edilir, eksen boyunca derinlik `depth`; `None` → boydan boya.
  p yüzeyde değil, `|n| = 0`, n malzemeye girmiyor (p + 1e-3·n parça dışında), boydan boyada eksen
  parçadan çıkmıyor → `GeometryError`. Boydan boyada kaydın `depth`'i eksenin parça içindeki boyudur
  (giriş ile çıkış noktası arası). Kesici gövde girişte p'nin, boydan boyada çıkışta da
  çıkış noktasının PAY + r·tanθ ötesine uzanır (θ: eksen ile o yüzeyin normali arası açı); θ > ~87°
  (cos θ < 0.05) → `GeometryError`.

## Kabul kriterleri
- [x] K1 `fillet_vertical`: blokta ΔV = (4 − π) r² c ve ΔS formülle rel 1e-6; sınır kutusu değişmez — `tests/geometry/test_fillet.py`
- [x] K2 `fillet_top`: blokta ΔV = (1 − π/4) r²·2(a+b) − 4r³(5/3 − π/2) rel 1e-6; silindirde ve boydan boya delik ağzında Pappus ΔV rel 1e-6 — `test_fillet.py`
- [x] K3 `fillet_all`: blokta V ve S kapalı formla rel 1e-6; ağırlık merkezi blok merkezinde 1e-6 mm — `test_fillet.py`
- [x] K4 Fillet hataları: r ≤ 0, kenar boyundan büyük r → `GeometryError`; girdi parça değişmiyor — `test_fillet.py`
- [x] K5 `countersink_hole`: kör ve boydan boyada ΔV = kesik koni + silindir rel 1e-6 (α = 90° ve 82° dahil); `Hole` kaydı (origin, axis, d, depth, csk_d, csk_angle) doğru; geçersiz girdiler hata — `tests/geometry/test_holes.py`
- [x] K5b `counterbore_hole`: tablo değerleriyle (M6, M8) ve açık ölçülerle kör / boydan boya ΔV = π(D² − d²)t_c/4 + π d² t/4 rel 1e-6; tablo tutarlılığı (D > d_k, t_c > k, d > d_n); açık ölçü tabloyu eziyor; kayıtta cbore_d, cbore_depth; geçersiz girdiler hata — `test_holes.py`
- [x] K6 `parse_thread` ve `tapped_hole`: tablo değerleri ve ince hatve; ΔV = π (d_n − P)² t / 4 rel 1e-6; kayıtta diş bilgisi; bozuk yazım, tabloda olmayan diş, thread_depth > depth hata — `test_holes.py`
- [x] K7 `inclined_hole`: θ = 0°, 30°, 45°'de boydan boya ΔV = π r² c / cos θ ve kayıt depth = c / cos θ rel 1e-6; kör ΔV = π r² t rel 1e-6; yüzey dışı p, malzemeye girmeyen n, sıfır n hata — `test_holes.py`
- [x] K8 Kayıt zinciri: blok → `hole` → `countersink_hole` → `counterbore_hole` → `tapped_hole` → `inclined_hole` → `chamfer_top` → `fillet_vertical` sonunda `part.holes` 5 kaydı sırayla taşıyor; girdi parçaların kayıtları değişmiyor — `test_holes.py`
- [x] Tüm testler yeşil (`pytest` 0 failed, bu SPEC'te 0 "uygulanmamış"), `ruff check .` ve `ruff format --check .` temiz; SPEC 02 testleri değişmeden geçiyor

## Kapsam dışı
- Helisel (gerçek) diş geometrisi; inç / UNC / boru dişi; sol diş
- Pullu lamba ölçüleri, ISO 4762 dışındaki civata başları (DIN 7984 alçak baş vb.); havşa + lamba aynı delikte
- Matkap ucu konisi (118°) ile kör delik dibi; delikler SPEC 02 gibi düz diplidir
- Değişken yarıçaplı fillet, pah + fillet karışık köşeler, seçili tek kenarın kullanıcıca işaretlenmesi
  (kararlı kenar referansı SPEC 18 özellik ağacının konusu)
- Kayıtların geometriden yeniden çıkarılması (parçadan delik tanıma — SPEC 05) ve STEP'e yazılması
- CAM tarafı: kayıttan G81/G83/G84 üretimi ve havşa takımı (SPEC 14 / ileride); bu SPEC sadece kaydı verir
- Genel boolean API — SPEC 09
