# SPEC 36 — Montaj sırası ve demontaj yolu (Dalga 5, hat H11)

## Amaç
Bir montaj ağacından (SPEC 07) **girişimsiz sökme yönlerini** bulup, her parçanın (veya alt montajın) tek bir
doğrusal ötelemeyle söküldüğü bir **demontaj sırası** ve onun tersi olan **montaj sırasını** çıkarmak; her adım
için yönü, yol boyunu ve başlangıç / bitiş konumunu vermek. SPEC 25 bugün sırayı elle alıyor; bu SPEC'ten sonra
sıra ve yaklaşma yönü geometriden önerilebilir.

## Teori

### Sökerek montaj (assembly by disassembly)
Bir montaj sırası, demontaj sırasının tersidir: tam montajdan başlayıp her adımda **bir birim** (parça ya da alt
montaj) bir yön `d` boyunca sonsuza ötelenerek, kalan hiçbir birime girmeden çıkarılır; geriye **taban** kalır.
Montajda birimler ters sırayla gelir ve her biri `−d` yönünde ilerleyerek yerine oturur (Homem de Mello &
Sanderson, "A correct and complete algorithm for the generation of mechanical assembly sequences", IEEE T-RA
7(2), 1991; Wilson & Latombe, "Geometric reasoning about mechanical assembly", *Artificial Intelligence* 71,
1994).

Bu SPEC'in plan sınıfı: **sıralı** (her adımda tek birim hareket eder), **monoton** (bir birim yerine bir kez
gelir, ara konum yok), **tek öteleme** (her birim tek doğrusal yolla, dönmeden). Aday yönler sonlu bir listedir.

### Yönlü engelleme grafiği
Yön `d` (birim vektör) için birim `i`'nin `j` tarafından engellenmesi:
```
j, i'yi d yönünde engeller  ⇔  ∃ s > 0 :  V( (i + s d) ∩ j ) > tol_v
```
`i + s d`, `i`'nin `s d` kadar ötelenmiş hâlidir. Yönlü engelleme grafiği (DBG, Wilson & Latombe) `G_d`: düğümler
birimler, `i → j` kenarı "j, i'yi d yönünde engeller". `S` kalan birim kümesiyse `i`, `d` yönünde
**sökülebilir** ⇔ `G_d`'de `i`'den `S ∖ {i}` içine giden kenar yok.

Dikkat:
- Yalnız yüz yüze değen iki parça birbirine doğru ötelenince kesişim hacmi `≈ ε · A > tol_v` olur (engeller);
  yüzey boyunca kayınca hacim 0 kalır (engellemez). Bu SPEC 09'un temas / girişim ayrımının aynısıdır.
- Başlangıçta girişen (`V∩ > tol_v`, ör. sıkı geçme) iki birim **her yönde** birbirini engeller. Bilinçli
  girişimler `ignore` ile engellemeden çıkarılır (SPEC 09'daki gibi).
- Kenar kümesi yalnız `i` ile `j`'nin geometrisine bağlıdır; `S` küçüldükçe kenarlar yalnız azalır.

### Açgözlü sıra tam ve deterministiktir
`S`'den sökülebilir bir birim çıkarmak, kalanlar için hiçbir engeli artırmaz. Bu yüzden bu plan sınıfında bir
sökme sırası varsa, **her adımda herhangi** bir sökülebilir birimi çıkaran açgözlü algoritma da bir sıra bulur;
hiçbir birim sökülemiyorsa (ve tabandan başka birim kaldıysa) bu sınıfta sıra yoktur (Wilson & Latombe, Bölüm 4:
monoton, iki elli, tek ötelemeli planlarda her sökülebilir alt kümenin çıkarılması tamlığı bozmaz). Seçim kuralı:
1. Kalan, sökülebilir, taban olmayan birimlerden **`walk` sırasında en sonda** olanı söküle.
2. Yönü: `directions` listesinde o birimi serbest bırakan **ilk** yön.

Sonuç: ağacın `walk` sırası (taban başta) zaten geçerli bir montaj sırasıysa, bulunan montaj sırası `walk`
sırasının aynısıdır (tümevarım: son birim yalnız kendinden öncekilerce engellenebilir; onlara göre yerine
girebildiyse onlardan sökülebilir).

### Örnekleme ve kaba eleme
`∃ s > 0` koşulu, kesişim sorgusunun (`Part.common`, SPEC 09) sonlu sayıda `s` değerinde çağrılmasıyla sınanır.
Birimin dünya eksen hizalı kutusu (AABB) yapraklarının SPEC 09 `world_aabb` kutularının birleşimidir. `i`'nin
kutusu `[lo_i, hi_i]`, `j`'ninki `[lo_j, hi_j]` ise, `i + s d`'nin kutusu `j`'ninkiyle her eksende **kesin**
(pozitif uzunlukta) örtüştüğü `s` aralığı, eksenler üstünden kesişimdir:
```
d_k > 0 :  s ∈ ( (lo_j,k − hi_i,k) / d_k ,  (hi_j,k − lo_i,k) / d_k )
d_k < 0 :  s ∈ ( (hi_j,k − lo_i,k) / d_k ,  (lo_j,k − hi_i,k) / d_k )
d_k = 0 :  lo_i,k < hi_j,k  ve  hi_i,k > lo_j,k  ise tüm s, değilse boş
```
Bu aralık `(0, ∞)` ile kesişince `(a, b)` elde edilir. `b ≤ a` ise kutular yol boyunca hiç örtüşmez, `j` `i`'yi
`d` yönünde engellemez ve **`common` çağrılmaz**. Değilse sınanan noktalar
```
P = sıralı( ({ε} ∪ {k δ : k = 1, 2, …} ∪ {(a + b)/2}) ∩ (a, b) )
```
ve küçükten büyüğe ilk engelleyen noktada durulur. `ε` (varsayılan 0.01 mm) değen yüzlerdeki yerel engeli,
`δ` (örnekleme adımı) uzaktaki engeli yakalar; orta nokta kutular örtüştüğü sürece en az bir sorgu yapılmasını
sağlar. Bir noktada yalnız kutuları o `s`'de kesin örtüşen yaprak çiftleri için `common` çağrılır. Aynı
`(i, j, d)` için sınama en çok bir kez yapılır (sonuç önbelleğe alınır).

Örnekleme sınırı: yol boyunca `i`'nin ve `j`'nin `d` doğrultusundaki kalınlıkları toplamı `δ`'dan küçük olan bir
geçişi atlayabilir. Varsayılan `δ`, kapsamdaki yaprakların yerel `bbox` kenarlarının en küçüğüdür; daha ince
özellikleri olan parçalar için `step` küçük verilir.

### Demontaj yolu boyu
Birim `i`, `d` yönünde sökülürken kalan birimlerin (`S ∖ {i}`) kutularının birleşimi `[L, H]` ise, `i`'nin kutusu
bu kutudan bir eksende `pay` kadar ayrıldığında yol biter (bir eksende ayrılan kutu `d` boyunca hep ayrık kalır):
```
d_k > 0 :  s_k = (H_k + pay − lo_i,k) / d_k
d_k < 0 :  s_k = (L_k − pay − hi_i,k) / d_k
s_çık = max(0, min_{k : d_k ≠ 0} s_k)
```
Adımın başlangıcı birimin yerindeki dünya dönüşümü `T`, ucu `T_out = Tr(s_çık d) · T` (`Tr(v)` saf öteleme).
Montajda birim `T_out`'tan `T`'ye, `−d` yönünde gelir (SPEC 25'teki `T_once → T_sonra` ile aynı biçim).

### Taban
Taban sökülmez ve montaj sırasının ilk adımıdır (`direction = None`, `distance = 0`, `T_out = T`). Verilmezse
toplam yaprak hacmi en büyük birim seçilir; hacimler eşitse (rel 1e-9) `walk` sırasında önce gelen.

## Dosyalar
- Yeni: `assy/sira.py`, `tests/assy/test_sira.py`, `durum/36-montaj-sirasi.md`
- Dokunulmayacak: `assy/model.py`, `assy/tree.py`, `assy/girisim.py`, `geometry/`, `pyproject.toml`.
  Arayüz değişikliği gerekmez; yeni bağımlılık yok.
- Kod bağımlılığı: SPEC 09 (`Part.moved`, `Part.common` arayüz PR'ı ve `assy.girisim.world_aabb`). İskelet
  birleşmemiş SPEC 09 dalının üstüne kurulabilir.

`assy/sira.py` saf Python + numpy'dir, OCCT import etmez: parçayı yalnız `Part` arayüzünden (`bbox`, `moved`,
`common`, `volume`) kullanır; kutu biçimli sahte parçalarla OCCT'siz test edilir. Gerçek `Part` kullanan testler
`@pytest.mark.occt` işaretli. Yapı / girdi hatası → `assy.model.AssyError`. Hiçbir fonksiyon girdisini değiştirmez.

## Arayüz

### `assy/sira.py`
```python
DIRECTIONS: tuple[np.ndarray, ...]  # +Z, −Z, +X, −X, +Y, −Y (bu sırayla)


@dataclass(frozen=True)
class Step:
    path: str  # birim yolu (SPEC 07 walk biçimi): yaprak yolu ya da scope'un çocuğunun yolu
    leaves: tuple[str, ...]  # birimdeki yaprak yolları, walk sırasıyla (yaprak birimde tek eleman)
    direction: np.ndarray | None  # sökme yönü d (birim, dünya); montajda birim −d yönünde gelir. Taban: None
    distance: float  # s_çık, mm; taban: 0
    T: np.ndarray  # birimin yerindeki dünya dönüşümü (world(root, path))
    T_out: np.ndarray  # Tr(distance · d) · T; taban: T
```

- `sequence(root: Node, parts: Mapping[str, Part], base: str | None = None,
  directions: Sequence = DIRECTIONS, *, scope: str = "", units: str = "yaprak",
  ignore: Iterable[tuple[str, str]] = (), step: float | None = None, eps: float = 0.01,
  tol_v: float = 1e-6, pay: float = 5.0) -> list[Step]`
  - **Montaj sırası** döner: ilk eleman taban, sonrakiler sırayla yerine gelen birimler. Demontaj sırası
    `reversed(...)`'ın tabandan önceki kısmıdır.
  - `validate(root)` çağrılır. Birimler `scope` düğümünün altındadır (`""` = kök):
    `units="yaprak"` → altındaki her yaprak; `units="cocuk"` → `scope`'un her doğrudan çocuğu (alt montaj tek
    rijit birim; yaprak çocuk kendisi). Birim sırası `walk` sırasıdır.
  - `base`: birim yolu; `None` → Teori'deki hacim kuralı.
  - `directions`: her biri birime normlanır; birbirinin aynısı olanlar (`1 − d·d' ≤ 1e-9`) ilk geçen tutularak
    atılır. Sıra önceliktir.
  - `ignore`: kapsamdaki yaprak yolu çiftleri (sırasız); bu yaprak çifti engelleme sınamasında yok sayılır.
  - `step`: `δ`; `None` → Teori'deki varsayılan.
  - Teori'deki açgözlü kural ve yol boyu. Bir birimin yaprakları birbirine karşı sınanmaz.
  - Sökülemez montaj → `AssyError`; mesaj kalan (taban dışı) birimlerin yollarını `walk` sırasıyla içerir.
- `blocking(root, parts, directions=DIRECTIONS, *, scope="", units="yaprak", ignore=(), step=None,
  eps=0.01, tol_v=1e-6) -> list[tuple[np.ndarray, set[tuple[str, str]]]]` — tanı için: tekilleştirilmiş her
  yön için `(d, {(i, j) : j, i'yi d yönünde engeller})`, birim yollarıyla; tüm birim çiftleri için.
- `mate_directions(assy: Assembly) -> list[np.ndarray]` — kısıtlardan aday yönler (dünya): her
  `CONCENTRIC` kısıtın `a` referansının ekseni ve her iki ucu `PLANE` olan `COINCIDENT` / `DISTANCE` kısıtın
  `a` normali, kısıt sırasıyla, her biri önce `+`, sonra `−`; tekilleştirme `directions` ile aynı kural. Diğer
  kısıtlar yön vermez. Dönüşler `assy`'deki bileşen `T`'leriyle (SPEC 08 çözümü sonrası). Kullanım:
  `sequence(..., directions=mate_directions(a) + list(DIRECTIONS))`.
- Hatalar (`AssyError`): ağaçtaki parça kimliği `parts`'ta yok; bilinmeyen `scope` ya da `scope` bir yaprak;
  `units` `"yaprak"` / `"cocuk"` dışında; kapsamda tek birim (sökülecek bir şey yok); `base` birim değil;
  `ignore`'da kapsamdaki bir yaprak olmayan yol ya da `a == b`; `directions` boş, sıfır ya da sonlu olmayan
  vektör; `step` veya `eps` sonlu ve `> 0` değil; `tol_v` veya `pay` sonlu ve `≥ 0` değil; sökülemez montaj.

## Kabul kriterleri

> Onay: kullanıcı, 2026-10-18 11:13 UTC (Dalga 5 toplu yazılı onay, önerilen varsayılanlarla).
- [ ] K1 Yön listesi: normlama; yinelenenin atılması (ör. `(0,0,2)` ile `+Z`); `mate_directions`: Z'de 90°
  dönmüş bileşendeki `CONCENTRIC` ekseni dünyada `±` sırasıyla, düzlem–düzlem `COINCIDENT` normali, nokta–nokta
  kısıtı yön vermiyor, ortak yönler bir kez — `tests/assy/test_sira.py`
- [ ] K2 Engelleme, analitik (sahte kutu parçalar, OCCT'siz): `blocking` kenarları el hesabıyla birebir
  (Ek A sahnesinde ve ayrı küçük sahnelerde): üst üste değen kutular (`ε` ile yerel engel; yüzey boyunca kayan yönler serbest), 20 mm boşluktan sonra
  gelen engel (`+X`), `δ = 1` ile 0.5 mm kalınlığında duvar yakalanıyor, köşegen yön `(1,1,0)/√2` ile hem engelli
  hem kutusu ıskalayan durum; başlangıçta girişen çift her yönde engelli, `ignore` ile engelsiz — `test_sira.py`
- [ ] K3 Örnekleme ve kaba eleme (çağrı sayan sahte parçalar): kutuları yol boyunca örtüşmeyen çiftte 0 `common`
  çağrısı; çağrılan `s` değerleri Teori'deki `P` kümesiyle sırasıyla birebir (ilk engelde duruyor); aynı
  `(i, j, d)` ikinci kez sorulduğunda yeni çağrı yok; birimin kendi yaprakları arasında çağrı yok — `test_sira.py`
- [ ] K4 Montaj sırası (Ek A, OCCT'siz): sıra 1 ve sıra 2 için tablodaki yollar, yönler ve yol boyları
  (atol 1e-12); `T_out = Tr(s d) · T`; taban adımı `direction None`, `distance 0`, `T_out = T`; `walk` sırası
  geçerliyken sonuç `walk` sırası — `test_sira.py`
- [ ] K5 Kilit ve `ignore` (Ek A + pim): `ignore` olmadan `AssyError`, mesajda `dayama` ve `pim` var, `blok_1`
  yok; `ignore` ile tablodaki sıra — `test_sira.py`
- [ ] K6 Alt montaj birimi (`units="cocuk"`, Ek A gruplu): taban hacim kuralıyla `alt`; `base="taban"` verilince
  tablodaki sıra; `Step.leaves` ve `T` doğru; `scope` ile yalnız alt ağaç — `test_sira.py`
- [ ] K7 Gerçek parçalar (`@pytest.mark.occt`): 40×40×10 plaka, Ø10 delik, Ø9.8 pim. Boydan boya delikte pim
  `±Z` serbest, `±X`, `±Y` engelli; 6 mm derin kör delikte yalnız `+Z` serbest; kör delik montajında sıra
  plaka, pim (`+Z`, `distance = 11` atol 1e-9) — `test_sira.py`
- [ ] K8 Hatalar: Arayüz'deki her `AssyError` durumu ayrı ayrı — `test_sira.py`
- [ ] Tüm testler yeşil (`pytest` 0 failed, bu SPEC'te 0 "uygulanmamış"), `ruff check .` ve
  `ruff format --check .` temiz

## Kapsam dışı
- Çok parçalı yollar (önce yukarı sonra yana), dönerek sökme, vidalama hareketi; birden çok birimin aynı anda
  hareketi (alt montaj dışında); monoton olmayan planlar (parçayı ara konuma bırakma)
- Kararlılık ve yerçekimi: bulunan sırada bir parça yalnız havada durabilir (Ek A sıra 2'de kapak); fikstür /
  tutucu gereksinimi; el / takım erişimi ve takım çarpışması
- Sıra kalitesi için en iyileme (en az yön değiştirme, en az tutucu); bu SPEC deterministik bir geçerli sıra verir
- Alt montajların kendi içlerinin özyinelemeli planı (çağıran her alt montaj için `scope` ile ayrıca çağırır)
- Kesin süpürülmüş hacim; sınama `δ` adımlı örneklemedir (Teori'deki sınır)
- Tezgah ekranına bağlama (SPEC 25 sırayı elle almaya devam eder; öneri düğmesi sonraki bir ekran SPEC'i)

## Ek A — Uydurma test sahnesi (sahte kutu parçalar)

Tüm parçalar eksen hizalı kutu, yerel koordinatları dünya ile aynı (`T` birim), mm:

| Yaprak | x | y | z | Hacim |
|---|---|---|---|---|
| `taban` | 0 … 100 | 0 … 60 | −10 … 0 | 60000 |
| `blok_1` | 10 … 40 | 10 … 50 | 0 … 30 | 36000 |
| `blok_2` | 60 … 90 | 10 … 50 | 0 … 30 | 36000 |
| `dayama` | 40 … 60 | 20 … 40 | 0 … 20 | 8000 |
| `kapak` | 5 … 95 | 5 … 55 | 30 … 38 | 36000 |
| `pim` (yalnız K5) | 48 … 52 | 28 … 32 | −5 … 25 | 480 |

`dayama`, `blok_1` ve `blok_2`'ye yan yüzlerinden değer; `kapak` iki bloğun üstüne oturur. Varsayılanlar:
`directions = DIRECTIONS`, `eps = 0.01`, `pay = 5`, `step = None` (pimsiz `δ = 8`, pimli `δ = 4`).

**Sıra 1** — kökün çocukları `taban, blok_1, blok_2, dayama, kapak` (geçerli `walk` sırası):

| Montaj adımı | Birim | Sökme yönü `d` | `distance` |
|---|---|---|---|
| 0 | `taban` | — | 0 |
| 1 | `blok_1` | +Z | 5 |
| 2 | `blok_2` | +Z | 35 |
| 3 | `dayama` | +Z | 35 |
| 4 | `kapak` | +Z | 5 |

**Sıra 2** — çocuklar `taban, kapak, blok_1, dayama, blok_2` (kapak bloklardan önce; açgözlü kural blokları yandan
çıkarır, kapak havada kalır):

| Montaj adımı | Birim | Sökme yönü `d` | `distance` |
|---|---|---|---|
| 0 | `taban` | — | 0 |
| 1 | `kapak` | +Z | 0 |
| 2 | `blok_1` | +X | 95 |
| 3 | `dayama` | +X | 65 |
| 4 | `blok_2` | +X | 45 |

**Pimli** — çocuklar `taban, blok_1, blok_2, dayama, kapak, pim`; pim `taban` (80 mm³) ve `dayama` (320 mm³) ile
girişir. `ignore` yok → `AssyError` (kalan `dayama`, `pim`). `ignore = {(pim, taban), (pim, dayama)}` → Sıra 1'in
adımları, ardından adım 5 `pim`, `d = −Z`, `distance = 40` (`+Z`'de kapak engeller).

**Gruplu** (K6) — kökün çocukları `taban`, `alt` (alt montaj, `T` birim: `blok_1, blok_2, dayama`), `kapak`;
`units = "cocuk"`. `base = None` → taban `alt` (80000 > 60000): `alt`; `taban` (`−Z`, 5); `kapak` (`+Z`, 5).
`base = "taban"` → `taban`; `alt` (`+Z`, 5); `kapak` (`+Z`, 5).
