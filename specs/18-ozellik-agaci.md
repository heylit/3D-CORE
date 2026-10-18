# SPEC 18 — Özellik ağacı: kararlı yüz referansı, döndürme, pah / yuvarlatma adımı, desen, ayna

> **Durum: TASLAK** (kullanıcı onayı bekliyor). Onaylanmadan kod, test ve arayüz PR'ı açılmaz.
> Yer: Dalga 5, hat H12 (`/mnt/project-files/yol-haritasi/dalga-5-onerisi.md`; kullanıcı 2026-10-18 10:51 tam kapsam).
> Bağımlılık: arayüz A2 (`geometry/part.py`: `FaceRef`, `Part.names`, `Part.find`), SPEC 17 (`sketch.model`),
> SPEC 26 (`geometry/extrude.py`). `geometry/revolve.py` SPEC 28'indir (`Part.axial_section`); bu SPEC ona dokunmaz.

## Amaç
SPEC 26'nın doğrusal, "her seferinde sayısal düzlemle" kurulan model geçmişini, adımları birbirine **kalıcı adla**
bağlanan bir özellik ağacına çevirmek. Bu adım bitince: bir özellik (eskiz düzlemi, pah kenarı, ayna düzlemi) önceki
bir özelliğin yüzünü OCCT yüz sırasıyla değil `FaceRef("cep1", "son")` gibi bir adla gösterir; bir ölçü değişince ya
da araya özellik girince referans aynı geometrik yüze çözülür; döndürme, pah, yuvarlatma, doğrusal / dairesel desen
ve ayna analitik hacimle doğrulanmış özellikler olarak ağaçta yer alır. Bulunamayan referans sessizce başka yüze
kaymaz: o özellik ve ona bağlı özellikler adla raporlanır.

## Teori

### Topolojik adlandırma (neden ve nasıl)
OCCT her boolean'dan sonra yüzleri yeniden sıralar; SPEC 26'da `index` ile tutulan bir yüz, öncesine bir delik
eklenince başka bir yüzü gösterir. Çözüm iki parçadır:
1. **Doğuşta ad.** Her özellik ürettiği yüzlere **yapısından** gelen yerel bir ad verir (aşağıdaki tablo). Yeni
   kurulmuş takım gövdesinde (ekstrüzyon prizması, döndürme gövdesi) yüzler kesit kenarlarıyla bire bir eşlenir;
   eşleme geometriktir (düzlem normali + uzaklığı, silindir / koni / torus ekseni + yarıçapı, 1e-9) ve bu anda
   belirsizlik yoktur.
2. **Geçmişle taşıma.** Adlar sonraki her işlemden **OCCT geçmişiyle** geçer: `BRepAlgoAPI_Cut / Fuse` için
   `Modified` / `IsDeleted`, `BRepFilletAPI_MakeFillet` / `MakeChamfer` için `Modified` / `Generated`,
   `BRepBuilderAPI_Transform` (desen, ayna) için `Modified`, `ShapeUpgrade_UnifySameDomain` için `History()`.
   - Bölünen yüz (ör. boydan boya kanal üst yüzü ikiye ayırır) adını her parçaya taşır: `find` iki index döner.
   - Birleşen yüzler (eş düzlemli füzyon) bütün adları taşır: her iki ad da aynı tek yüze çözülür.
   - Silinen yüzün adı düşer. Geometrik "en yakın yüzü bul" geri dönüşü **yoktur** (sessiz kayma yasak).

Bir yüzün adı = üreten özelliğin kimliği + yerel ad. Kenar ayrıca adlandırılmaz: `EdgeRef(a, b)` iki adlı yüzün
**ortak kenarlarıdır** (pah ve yuvarlatmanın girdisi). Ortak kenar yoksa → `GeometryError`.

### Yerel ad tablosu
`<src>` kesit kenarının eskizdeki öğe kimliğidir (`SegLine.src` / `SegArc.src`, bkz. Açık soru S2).

| Özellik | Yerel adlar |
|---|---|
| `Blok` | `xmin`, `xmax`, `ymin`, `ymax`, `zmin`, `zmax` |
| `Silindir` | `alt`, `ust`, `yan` |
| `Ekstruzyon` | `bas` (kesit düzleminin, ekstrüzyon yönünde başlangıç kapağı), `son` (bitiş kapağı), `yan:<src>` |
| `Dondurme` | `yan:<src>` (kenarın döndürülmesiyle oluşan yüzey); açı < 360° ise `bas`, `son` kapakları |
| `Delik` | `<n>/duvar`, `<n>/dip` (kör), `<n>/havsa`, `<n>/lamba_duvar`, `<n>/lamba_dip`; `<n>` = noktanın sırası (0'dan) |
| `Pah`, `Yuvarlatma` | `<i>` = `kenarlar` listesindeki i. `EdgeRef`'ten doğan yüz (0'dan); bir EdgeRef birden çok kenara çözülürse `<i>.<j>` |
| `DogrusalDesen`, `DaireselDesen` | `<k>/<kaynak>/<ad>`: k. kopya (1'den; 0 = asıl, kendi adlarını korur), kaynak özelliğin yerel adı |
| `Ayna` | `<kaynak>/<ad>` (özellik aynası) ya da `govde/<özellik>/<ad>` (gövde aynası: aynalanan yarıdaki her adlı yüz) |

Kesimde (`islem="kes"`) takımın adları sonuca aynı yerel adla geçer: kör cebin tabanı `son`, duvarları `yan:<src>`;
parçanın dışında kalan `bas` kapağı silinir.

### Döndürme (Pappus–Guldinus)
Kesit bölgesi (alan A, ağırlık merkezinin eksene uzaklığı ρ̄) eksen etrafında θ radyan döner:
`V = θ · ρ̄ · A`. Yan yüzey: her kenar (boy L_k, ağırlık merkezi eksenden ρ_k) `S_k = θ · ρ_k · L_k`; θ < 2π ise iki
kapak `2A` eklenir. Eksen kesit düzlemindedir (uv'de nokta + yön). Bölge ekseni **kesmez**; eksene değen kenar
(ρ = 0) serbesttir ve yüzey üretmez. Örnekler (K3): dikdörtgen w × h, iç kenarı eksenden R'de, 360° →
`V = π((R+w)² − R²) h`; yarım disk r (çapı eksende) → `4πr³/3`; daire r, merkezi eksenden R'de → `2π² R r²`;
dik üçgen (dik kenarları eksende h ve radyal R) → `πR²h/3`.

### Pah ve yuvarlatma (SPEC 23 ile aynı formüller)
Dışbükey, 90° düz kenar, boy L; kenar uçları kenara dik düzlemlerde biter:
- Eşit pah d: `ΔV = d² L / 2`; iki uzaklıklı pah d₁ (a yüzü üzerinde), d₂ (b yüzü üzerinde): `ΔV = d₁ d₂ L / 2`.
- Yuvarlatma r: `ΔV = (1 − π/4) r² L`.
- Delik ağzı (boydan boya delik yarıçapı r_h, ağız kenarı yuvarlatma r): `ΔV = 2π (r_h + x̄)(1 − π/4) r²`,
  `x̄ = r (10 − 3π) / (3 (4 − π))` (SPEC 23 Pappus satırı).
OCCT ön deneme (blok 100 × 60 × 20, kenar y = 0, z = 20): r = 4 yuvarlatma rel 3e-15; pah 2 → 200, pah 2 / 3 → 300
(tam); r_h = 5 deliğin ağzı r = 1 → rel 5e-13.

### Desen ve ayna
Desen ve ayna **özellik** üzerinedir: kaynak özelliğin takım gövdesi (ekstrüzyon / döndürme gövdesi, delik kesicisi)
dönüştürülür ve kaynakla aynı işlemle (`ekle` / `kes`) uygulanır. Kopyalar birbirine değmiyorsa ve parçanın içinde
kalıyorsa `ΔV = n · ΔV₁`. Delik kaynağında her kopya kendi `Hole` kaydını taşır: `origin' = T(origin)`,
`axis' = R(axis)` (T dönüşüm, R onun dönme kısmı; aynada R yansımadır, `axis` yine birimdir).
- Doğrusal: `p_ij = p + i·s₁·e₁ + j·s₂·e₂`, i < n₁, j < n₂ (e birim). Dairesel: eksen etrafında
  `φ_k = k · aci / n` (aci = 360° ise kapalı tam tur), aci < 360° ise `φ_k = k · aci / (n − 1)`.
- Ayna düzlemi (nokta q, birim normal m): `p' = p − 2((p − q)·m) m`. Gövde aynası: `parça ∪ ayna(parça)`;
  tek katı olmalı (parça ayna düzlemine bir yüzle değmeli), değilse `GeometryError("ayrık katı")`.
  Ayna düzlemine yüzle değen blokta `V' = 2V`.

### Ağaç ve yeniden kurulum
Ağaç = sıralı özellik listesi + bağımlılık grafiği. Kenar `B → A`: B, A'nın kimliğini (`profil`, `ozellikler`) ya da
A'nın ürettiği bir `FaceRef`'i kullanıyor. Kurulum liste sırasıyla yürür (her özellik bir öncekinin parçasına
uygulanır); grafik geri alma, bastırma, taşıma ve hata yayılımı içindir.
- **Doğrulama (kurulumdan önce):** kimlikler tekil, boş değil, `:` ve `/` içermez; her referans **daha önceki** bir
  özelliğe (ileri referans yasak); bilinmeyen özellik türü yok → değilse `GeometryError`.
- **Hata yalıtımı (bkz. Açık soru S1):** bir özellik başarısız olursa (referans çözülemedi, malzeme kaldırmayan kesim,
  ayrık katı, OCCT hatası) parçaya uygulanmaz, `durum="hata"` ve çekirdeğin mesajıyla raporlanır; ona (doğrudan ya da
  dolaylı) bağlı özellikler `durum="atlandi"` ve `neden=<hatalı kimlik>` alır; bağımsız özellikler uygulanmaya devam
  eder. `Sonuc.basarili = False`. Hiçbir özellik sessizce atlanmaz.
- **Bastırma:** `bastir=True` özellik uygulanmaz (`durum="bastirildi"`); bağımlıları "atlandi" olur.
- **Eskiz düzlemi yüze bağlıysa:** düzlem her kurulumda `FaceRef`'ten yeniden hesaplanır: normal = yüzün dışa bakan
  normali; `origin` = saklanan ilk origin'in yeni yüz düzlemine izdüşümü; `xdir` = saklanan xdir'in izdüşümü (normlu).
  Böylece yüz ötelenince eskiz onunla gider, düzlem içinde kaymaz. Yüz düzlemsel değilse ya da birden çok parçaya
  bölünüp eş düzlemli değilse → o özellik hata. SPEC 26'nın `eskiz_duzlemi_kopuk` durumu ağaçta oluşmaz.
- **Önbellek:** `insa(agac, onbellek)` ilk değişen özelliğe kadar (tanımı ve sırası aynı önek) önceki sonucu yeniden
  kullanır, sonrasını yeniden kurar. Sonuç önbelleksiz kurulumla birebir aynıdır (hacim, adlar, `Part.holes`).
- **Belirlenimcilik:** aynı ağaç iki kez kurulunca hacim, yüz sayısı ve her adın çözüldüğü yüzlerin geometrisi aynı.

## Dosyalar
- Yeni: `geometry/agac.py` (özellik kayıtları, `EdgeRef`, doğrulama, `insa`, ad taşıma, JSON), `geometry/dondur.py`
  (döndürme takım gövdesi ve adları), `geometry/desen.py` (doğrusal / dairesel desen, ayna dönüşümü, `Hole` dönüşümü)
- Yeni: `tests/geometry/test_dondur.py`, `test_desen.py`, `test_agac.py`, `test_agac_ad.py` (hepsi `@pytest.mark.occt`),
  `durum/18-ozellik-agaci.md`
- Kullanılır (değişmez): `geometry/part.py` (A2 sonrası), `geometry/extrude.py` (SPEC 26 takım gövdesi), `geometry/features.py`,
  `geometry/holes.py`, `geometry/fillet.py`, `sketch/model.py`
- Dokunulmayacak: `geometry/revolve.py` (SPEC 28), `geometry/part.py` (A2 sahibi), `sketch/`, `tezgah/`, `*/model.py`,
  `pyproject.toml`, `DURUM.md`, `docs/yol-haritasi.md`
- Bağımlılık kuralı: `geometry/agac.py` `sketch`'ten yalnız `sketch.model`'i import eder; eskiz çözümü dışarıdan
  verilen `coz` fonksiyonuyla gelir (`geometry` → `sketch.solver` bağımlılığı yok).

## Arayüz

### A2 (`geometry/part.py`, ayrı arayüz PR'ı, sahibi "Dalga 2 arayüz ekleri")
```python
@dataclass(frozen=True)
class FaceRef:
    """Kararlı yüz referansı: yüzü üreten özelliğin kimliği + o özelliğin yerel adı (SPEC 18)."""

    feature: str  # boş değil; ':' ve '/' içermez
    name: str  # boş değil; '/' içerebilir (desen / ayna adları)

    def __str__(self) -> str: ...  # "cep1:son"

    # ilk ':'ten böler; biçim dışı → GeometryError
    @classmethod
    def parse(cls, s: str) -> FaceRef: ...


class Part:
    def __init__(self, shape, name="parca", holes=(), names=None) -> None: ...

    # salt okunur; index'ler artan, tekrarsız, boş değil
    @property
    def names(self) -> Mapping[FaceRef, tuple[int, ...]]: ...

    # adda yoksa → GeometryError("referans bulunamadı: cep1:son")
    def find(self, ref: FaceRef) -> tuple[int, ...]: ...

    # ters arama (Tezgah'ta yüze tıkla → ad); bilinmeyen index → GeometryError
    def face_refs(self, index: int) -> tuple[FaceRef, ...]: ...
```
- `names` index'leri `PlanarFace.index` / `CylindricalFace.index` ile aynı OCCT yüz sırasıdır. Kurulumda index aralık
  dışı ya da boş tuple → `GeometryError`. `names=None` → boş eşleme.
- Adlar `Hole` kayıtları gibi STEP / STL gidiş-dönüşünde taşınmaz. SPEC 02 / 23 / 26 fonksiyonları adsız `Part`
  döndürmeye devam eder; adları yalnız `geometry.agac` üretir ve taşır. Var olan testler değişmez.

### `geometry/agac.py`
Tüm özellikler `frozen` dataclass; ortak alanlar `kimlik: str`, `bastir: bool = False`. Sayılar sonlu olmalı.
```python
EdgeRef(a: FaceRef, b: FaceRef)
DuzlemRef = sketch.model.Plane | FaceRef   # FaceRef → yukarıdaki "yüze bağlı eskiz düzlemi" kuralı

Blok(kimlik, a, b, c)                      # SPEC 02 block
Silindir(kimlik, r, h)                     # SPEC 02 cylinder
Profil(kimlik, duzlem: DuzlemRef, bolgeler: tuple[SketchRegion, ...] = (), eskiz: Sketch | None = None)
Ekstruzyon(kimlik, profil: str, mesafe: float, islem="yeni"|"ekle"|"kes", yon="ileri"|"geri"|"simetrik",
           bitis="mesafe"|"boydan_boya", bolge_sec: tuple[int, ...] | None = None)
Dondurme(kimlik, profil: str, eksen_p: (u, v), eksen_y: (du, dv), aci: float = 360.0, islem="yeni"|"ekle"|"kes")
Delik(kimlik, duzlem: DuzlemRef, noktalar: tuple[(u, v), ...], cesit="duz"|"havsa"|"lamba"|"dis",
      d, derinlik: float | None, ...)      # çeşide göre SPEC 02 / 23 parametreleri; SPEC 26 "Delik adımı" kuralı
Pah(kimlik, kenarlar: tuple[EdgeRef, ...], d, d2: float | None = None)
Yuvarlatma(kimlik, kenarlar: tuple[EdgeRef, ...], r)
DogrusalDesen(kimlik, ozellikler: tuple[str, ...], e1, s1, n1, e2=None, s2=0.0, n2=1)
DaireselDesen(kimlik, ozellikler: tuple[str, ...], eksen_p, eksen_y, n, aci=360.0)
Ayna(kimlik, duzlem: DuzlemRef, ozellikler: tuple[str, ...] | None)   # None → gövde aynası

Agac(ozellikler: tuple[Ozellik, ...])
insa(agac, onbellek: Onbellek | None = None, kadar: str | None = None,
     coz: Callable[[Sketch, Plane], Sequence[SketchRegion]] | None = None) -> Sonuc
Sonuc: part: Part | None, rapor: tuple[OzellikRaporu, ...], basarili: bool
OzellikRaporu: kimlik, durum="tamam"|"hata"|"atlandi"|"bastirildi", mesaj: str, neden: str | None,
               dV: float | None, adlar: tuple[FaceRef, ...] (bu özelliğin ürettiği ve sonuçta yaşayan adlar)
bagimlilar(agac, kimlik) -> tuple[str, ...]   # doğrudan ve dolaylı, liste sırasıyla
tasi(agac, kimlik, yeni_sira) -> Agac          # bağımlılığı bozan taşıma → GeometryError (adlarla)
sil(agac, kimlik, zincir=False) -> Agac        # bağımlısı varken zincir=False → GeometryError; True → bağımlılarla siler
to_dict(agac) -> dict  ·  from_dict(d) -> Agac # {"sema": 1, "ozellikler": [...]}; bilinmeyen tür / sema → GeometryError
```
- `Profil`: `eskiz` verilirse bölgeler `coz(eskiz, duzlem)` ile kurulumda hesaplanır (`coz` yoksa → hata); verilmezse
  `bolgeler` kullanılır. `Ekstruzyon` takımını `geometry.extrude.extrude` kurar, boolean'ı ağaç geçmiş izli yapar.
- `islem="yeni"` yalnız ağacın ilk katı üreten özelliğinde; sonrasında → hata (çok gövde kapsam dışı).
- `kadar=kimlik`: o özellik dahil oraya kadar kurar (SPEC 26 geçmiş şeridi). Bilinmeyen kimlik → `GeometryError`.
- Pah / yuvarlatmada her `EdgeRef` en az bir kenara çözülmeli; aksi hata. Desen kaynağı yalnız `Ekstruzyon` / `Dondurme`
  (`ekle` / `kes`) ve `Delik` olabilir; `Pah`, `Yuvarlatma`, `Blok`, `"yeni"` kaynak → `GeometryError`.
- Desen / ayna kopyalarından biri malzeme kaldırmıyorsa (`kes`, ΔV ≤ 1e-9 mm³) ya da parçaya değmiyorsa (`ekle`) → hata.

### `geometry/dondur.py`
`revolve(regions, plane, eksen_p, eksen_y, aci=360.0, name="dondurme") -> Part` (adlı takım gövdesi).
Hatalar: bölge ekseni kesiyor, `aci ∉ (0, 360]`, `|eksen_y| = 0`, boş bölge → `GeometryError`.

### `geometry/desen.py`
`dogrusal(n1, s1, e1, n2=1, s2=0, e2=None) -> list[Donusum]`, `dairesel(eksen_p, eksen_y, n, aci) -> list[Donusum]`,
`ayna(q, m) -> Donusum`, `donustur_hole(hole, T) -> Hole`. `Donusum` 4 × 4 homojen matris (numpy). `n < 1`,
sıfır yön, sıfır adım (n > 1 iken) → `GeometryError`.

## Kabul kriterleri
Hacim ve alan `rel 1e-6`, konum `1e-9` mm, aksi yazmadıkça. Blok kısaltması: `B = Blok("blok", 100, 60, 20)`.
"Cep" = blok üst yüzüne (`FaceRef("blok","zmax")`) bağlı `Profil`; 40 × 30 dikdörtgen, merkez (50, 30); `Ekstruzyon("cep", kes, 8)`.

### Analitik test tablosu
| # | Ağaç | Beklenen |
|---|---|---|
| T1 | B, cep | `V = 120000 − 9600 = 110400`; `find(cep:son)` tek düzlemsel yüz, z = 12, alan 1200; dört `cep:yan:<src>` alanı 320 / 240 |
| T2 | T1, sonra B'de c = 20 → 30 | `V = 180000 − 9600 = 170400`; `cep:son` z = 22 (eskiz yüzle gitti) |
| T3 | B, `Delik` (üst yüz, (20, 30), d = 10, boydan boya), sonra `Yuvarlatma(EdgeRef(blok:zmax, blok:ymin), 4)` | `V = 120000 − 500π − (1 − π/4)·16·100`; yuvarlanan kenar y = 0, z = 20 kenarıdır |
| T4 | T3'te delik bastırılır | `V = 120000 − (1 − π/4)·16·100`; yuvarlatma yine aynı kenarda (delik index'leri kaydırsa da) |
| T5 | B, `Pah(EdgeRef(blok:zmax, blok:ymin), 2)` / `d2 = 3` | `ΔV = 200` / `ΔV = 300`; d₁ zmax yüzünde, d₂ ymin yüzünde ölçülür |
| T6 | B, delik d = 10 boydan boya, `Yuvarlatma(EdgeRef(blok:zmax, delik:0/duvar), 1)` | `ΔV = 2π(5 + x̄)(1 − π/4)` |
| T7 | `Dondurme` XZ düzleminde dikdörtgen u ∈ [30, 40], v ∈ [0, 20], eksen Z, 360° / 90° | `V = 14000π` / `3500π`; alan 360°: `2π(40 + 30)·20 + 2π(1600 − 900)`; 90°'de çeyrek + `2·200` kapak |
| T8 | Döndürme: yarım disk r = 10; daire r = 5, R = 20; dik üçgen R = 10, h = 30 | `4000π/3`; `1000π²`; `1000π` |
| T9 | `Silindir(r=20, h=50)`, XZ'de u ∈ [16, 25], v ∈ [20, 30] dikdörtgen `Dondurme(kes)` (oluk) | `ΔV = π(20² − 16²)·10 = 1440π`; `oluk:yan:<iç kenar>` r = 16 silindirik yüz |
| T10 | B, delik d = 6 (10, 30) boydan boya, `DogrusalDesen(delik, e1 = X, s1 = 20, n1 = 4)` | `ΔV = 4·π·9·20 = 720π`; 4 `Hole`, origin x = 10, 30, 50, 70; `desen:3/delik/0/duvar` x = 70 eksenli r = 3 yüz |
| T11 | B 2B desen: n₁ = 3 (X, 25), n₂ = 2 (Y, 30), delik d = 6 (25, 15) | 6 delik, `ΔV = 6·180π`; `Hole` origin'leri ızgara |
| T12 | B, delik d = 8 (80, 30), `DaireselDesen(delik, eksen (50, 30), Z, n = 6)` | `ΔV = 6·π·16·20 = 1920π`; origin'ler `(50 + 30 cos 60k, 30 + 30 sin 60k)` |
| T13 | B, x ∈ [10, 30], y ∈ [15, 45] cep (8 derin), `Ayna(Plane x = 50, (cep,))` | `ΔV = 2·4800 = 9600`; aynalı cep x ∈ [70, 90]; `ayna:cep/son` z = 12 |
| T14 | `Blok(50, 60, 20)`, `Ayna(FaceRef(blok, xmax), None)` | Tek katı, `V = 120000`, sınır kutusu 100 × 60 × 20; `ayna:govde/blok/xmin` x = 100 düzlemi |
| T15 | B, `Ayna` deliği (30, 30) → x = 70 | `Hole.axis` (0, 0, −1) kalır, origin (70, 30, 20) |

### Kriterler
- [ ] **K1 Kararlı referans (T1–T4):** referanslar ölçü değişimi, araya giren özellik ve bastırmadan sonra aynı geometrik
  yüze çözülür; testlerden en az biri aynı ad için iki kurulumda **farklı OCCT index'i** görüp yine doğru yüzü bulduğunu
  gösterir — `tests/geometry/test_agac_ad.py`
- [ ] **K2 Bölünen ve birleşen yüz:** boydan boya kanal (Y yönünde, genişlik 10) `blok:zmax`'ı ikiye böler → `find` iki
  index, ikisi z = 20, alan toplamı `6000 − 10·60`; bloğa yan yana aynı yükseklikte `Ekstruzyon(ekle)` → `blok:zmax` ve
  `ek:son` aynı tek yüz; silinen yüzün adı `names`'te yok ve `find` → `GeometryError` — `test_agac_ad.py`
- [ ] **K3 Döndürme (T7–T9):** hacim ve alan Pappus; ekseni kesen bölge, `aci = 0`, `aci > 360`, sıfır eksen yönü →
  `GeometryError`; `yan:<src>` adları kenarlarla bire bir — `tests/geometry/test_dondur.py`
- [ ] **K4 Pah / yuvarlatma (T3, T5, T6):** analitik ΔV; çözülmeyen `EdgeRef` (ortak kenarsız iki yüz) → özellik "hata";
  doğan yüzler `pah:0`, `yuvarlatma:0` adını alır — `test_agac.py`
- [ ] **K5 Desen (T10–T12):** ΔV, `Hole` kayıtları (origin 1e-9, axis birim), kopya adları; parçadan taşan kopya (malzeme
  kaldırmayan) → özellik "hata"; `Pah` kaynağı → `GeometryError` — `tests/geometry/test_desen.py`
- [ ] **K6 Ayna (T13–T15):** özellik ve gövde aynası; ayrık gövde aynası → "hata" (`ayrık katı`); `donustur_hole` yansıtma
  ile `axis` birim kalır — `test_desen.py`
- [ ] **K7 Hata yalıtımı:** ortadaki özellik hata verince bağımlıları `atlandi` (neden = hatalı kimlik), bağımsız sonraki
  özellik uygulanır ve hacim ona göre analitik; `basarili = False`; bastırılan özelliğin bağımlıları `atlandi` — `test_agac.py`
- [ ] **K8 Doğrulama ve düzenleme:** tekrar eden / biçim dışı kimlik, ileri referans, bilinmeyen tür → `GeometryError`;
  `bagimlilar` doğru küme; bağımlılığı bozan `tasi` ve bağımlısı olan `sil` → `GeometryError` (adlarla); `sil(zincir=True)`
  bağımlılarla birlikte siler — `test_agac.py`
- [ ] **K9 Önbellek ve belirlenimcilik:** son özellik değişince yalnız o yeniden kurulur (rapor sayacı), sonuç önbelleksiz
  kurulumla aynı (hacim, `names` anahtarları, her adın yüz merkezleri, `holes`); aynı ağaç iki kez kurulunca aynı;
  `kadar` ara parçayı verir — `test_agac.py`
- [ ] **K10 JSON:** `from_dict(to_dict(a)) == a` (her özellik türü); `sema ≠ 1`, bilinmeyen tür → `GeometryError` — `test_agac.py`
- [ ] **K11 Delik ve eskiz uyumu:** ağaçtaki `Delik` özelliği hacim ve `Hole` kayıtlarında SPEC 02 / 23 fonksiyonlarının
  doğrudan çağrısıyla birebir; `Profil(eskiz=…)` `coz` ile çözülür, `coz` yoksa özellik "hata" — `test_agac.py`
- [ ] **K12 Bağımlılık kuralı:** `geometry` paketi `sketch`'ten yalnız `sketch.model`'i, `tezgah`'ı hiç import etmez
- [ ] Tüm testler yeşil: `pytest` 0 failed, bu SPEC'te 0 "uygulanmamış"; `ruff check .` ve `ruff format --check .`
  temiz; SPEC 02, 17, 23, 26, 28 testleri değişmeden geçiyor

## Test yaklaşımı
CLAUDE.md "Test bağımsızlığı" aynen geçerli: kod oturumu `NotImplementedError` iskeleti push eder, ayrı test oturumu
bu SPEC'ten (kodu görmeden) testleri yazar, kod ayrı commit'te gelir. OCCT gerektiren testler `@pytest.mark.occt`;
10 s'den uzun olanlar `@pytest.mark.slow`. Testler eskiz çözücüsüne bağlanmamak için bölgeleri (`SketchRegion`)
doğrudan verir; K11'in `coz` testi sahte bir `coz` fonksiyonuyla yapılır.

## Yol haritası yeri
- **Numara:** 18 (`18-ozellik-agaci`), Dalga 5 hat H12.
- **Bağımlılık:** 18 → A2, 17, 26 (`geometry/extrude.py`), 02, 23. `geometry/dondur.py` ve `geometry/desen.py` (K3, K5,
  K6'nın takım gövdesi ve dönüşüm kısmı) A2'den önce başlayabilir; adlar A2'yi bekler.
- **Devamı:** Tezgah'ta ağaç paneli ve SPEC 26 doğrusal geçmişinin ağaca dönüştürülmesi (Açık soru S3); sweep / loft / kabuk.

## Açık sorular (onayda karar)
- **S1 Hata sonrası:** (a) bağımsız özellikler devam eder, hatalı ve bağımlıları raporlanır **[öneri]**;
  (b) SPEC 26 gibi ilk hatada durulur.
- **S2 Yan yüz adı kaynağı:** (a) `sketch/model.py`'de `SegLine` / `SegArc`'a `src: str = ""` alanı (bölge kenarının
  eskiz öğe kimliği; ayrı küçük arayüz PR'ı, sahibi eskiz thread'i) **[öneri]**; (b) arayüz değişmez, ad
  `yan:<bölge>.<halka>.<kenar>` sıra numarası olur (ölçü değişince sıra kayabilir, referans kırılgan).
- **S3 Tezgah bağlantısı:** (a) bu SPEC yalnız `geometry` kütüphanesi + JSON; Tezgah'ta ağaç paneli ve 26 geçmişinin
  dönüştürülmesi A3 / H13 sonrasında küçük bir ek SPEC **[öneri]**; (b) bu SPEC'e dahil (tezgah/ dosyalarına dokunur).
- **S4 Parametre / ifade:** (a) ağaç sayısal değer tutar, ifade ve parametre tablosu Tezgah'ta (SPEC 26 `ifade.py`) kalır
  **[öneri]**; (b) ağaç ifadeleri kendisi değerlendirir.
- **S5 Ayna:** (a) hem özellik hem gövde aynası **[öneri]**; (b) yalnız özellik aynası.

## Kapsam dışı
- Sweep, loft, kabuk (shell), eğim (draft), değişken yarıçaplı yuvarlatma, yüz yuvarlatma, pah / yuvarlatma deseni
- Çok gövdeli parça, montaj içi (parçalar arası) referans, düzlemsel olmayan yüze eskiz
- Doğrudan kenar / köşe adı (kenar yalnız iki yüzün ortak kenarı olarak gösterilir)
- Adların STEP / STL ile taşınması, içe alınmış (STEP) parçada ad üretimi, özellik tanıma (SPEC 27)
- Tezgah ekranı, parametre / ifade dili (S3, S4)
- Gerçek şirket parçaları (gizlilik kuralı): bütün örnekler uydurma geometridir
