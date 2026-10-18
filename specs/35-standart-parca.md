# SPEC 35 — Standart parça kütüphanesi ve otomatik bağlantı önerisi (Dalga 5, H10)

## Amaç
ISO ölçü tablolarından üretilen parametrik standart parçalar (imbus vida, altıgen civata, somun, pul, pim,
rulman) ve SPEC 23 delik kayıtlarından (`Hole`) eş eksenli delik dizilerini bulup **hangi vidanın, hangi
boyda** takılacağını öneren, önerilen parçaları montaja eş eksen + yüzey kısıtlarıyla (SPEC 08) ekleyen
bir öneri katmanı.

## Teori

### Koordinat kuralı (bütün standart parçalar)
Eksen yerel Z'dir, parça eksene göre dönel simetriktir (altıgenler hariç; altıgenin iki karşılıklı düz
kenarı X eksenine diktir: x ∈ [−s/2, s/2], y ∈ [−s/√3, s/√3]).
- **Vida / civata:** baş altı (oturma yüzü) z = 0; baş z ∈ [0, k]; gövde z ∈ [−L, 0]. L baş altından uca
  ölçülür (ISO 4762 / 4017 tanımı). Gövdeye girme yönü yerel −Z'dir.
- **Somun, pul, pim, rulman:** bir alın yüzü z = 0, gövde z ∈ [0, h] (h: somunda m, pulda h, pimde L, rulmanda B).

### Basitleştirilmiş geometri (görsel / kütle amaçlı, hepsi el hesabıyla doğrulanır)
Diş helisi modellenmez (SPEC 23 kuralı): vida gövdesi ve somun deliği nominal çap `d` ile silindirdir.
Altıgen köşeleri keskindir (köşe çapı `e = 2s/√3`; standardın `e_min` değeri köşe yuvarlatmasından ötürü
biraz küçüktür, burada kullanılmaz). Pah, baş altı radyusu, lokma dibi konisi yoktur.
Düzgün altıgen alanı (anahtar ağzı s): `A_6 = (√3/2) s²`.

| Parça | Hacim |
|---|---|
| ISO 4762 imbus vida M d × L | `V = π d_k² k / 4 − A_6(s) t + π d² L / 4` (lokma: düz dipli altıgen, derinlik t) |
| ISO 4017 altıgen civata M d × L | `V = A_6(s) k + π d² L / 4` |
| ISO 4032 altıgen somun M d | `V = (A_6(s) − π d² / 4) m` |
| ISO 7089 pul (normal seri) | `V = π (d₂² − d₁²) h / 4` |
| ISO 2338 silindirik pim d × L | `V = π d² L / 4` |
| ISO 15 sabit bilyalı rulman (zarf) | `V = π (D² − d²) B / 4` (iç/dış bilezik + bilyeler tek dolu halka; zarf modeli) |

### Ölçü tabloları (mm; `geometry/standart/tablo.py`, saf Python)
Kaynak: ISO 4762:2004, ISO 4017:2014, ISO 4032:2012, ISO 7089:2000, ISO 2338:1997, ISO 15:2017,
ISO 273:1979; Machinery's Handbook, "Metric screws and nuts". Kaba hatve P: SPEC 23 `THREADS_COARSE`.

**ISO 4762** (d_k maks, k = d, s lokma anahtar ağzı, t min lokma derinliği, L aralığı):

| M | d_k | k | s | t | L aralığı |
|---|---|---|---|---|---|
| M3 | 5.5 | 3 | 2.5 | 1.3 | 5–30 |
| M4 | 7 | 4 | 3 | 2.0 | 6–40 |
| M5 | 8.5 | 5 | 4 | 2.5 | 8–50 |
| M6 | 10 | 6 | 5 | 3.0 | 10–60 |
| M8 | 13 | 8 | 6 | 4.0 | 12–80 |
| M10 | 16 | 10 | 8 | 5.0 | 16–100 |
| M12 | 18 | 12 | 10 | 6.0 | 20–120 |
| M14 | 21 | 14 | 12 | 7.0 | 25–140 |
| M16 | 24 | 16 | 14 | 8.0 | 25–160 |
| M20 | 30 | 20 | 17 | 10.0 | 30–200 |
| M24 | 36 | 24 | 19 | 12.0 | 40–200 |

**ISO 4017 / ISO 4032 / ISO 7089** (altıgen anahtar ağzı s civata ve somunda aynı; civata baş yüksekliği k,
somun yüksekliği m; pul iç çapı d₁, dış çapı d₂, kalınlığı h; civata L aralığı):

| M | s | k (4017) | L aralığı (4017) | m (4032) | d₁ | d₂ | h |
|---|---|---|---|---|---|---|---|
| M3 | 5.5 | 2.0 | 6–30 | 2.4 | 3.2 | 7 | 0.5 |
| M4 | 7 | 2.8 | 8–40 | 3.2 | 4.3 | 9 | 0.8 |
| M5 | 8 | 3.5 | 10–50 | 4.7 | 5.3 | 10 | 1.0 |
| M6 | 10 | 4.0 | 12–60 | 5.2 | 6.4 | 12 | 1.6 |
| M8 | 13 | 5.3 | 16–80 | 6.8 | 8.4 | 16 | 1.6 |
| M10 | 16 | 6.4 | 20–100 | 8.4 | 10.5 | 20 | 2.0 |
| M12 | 18 | 7.5 | 25–120 | 10.8 | 13 | 24 | 2.5 |
| M14 | 21 | 8.8 | 30–140 | 12.8 | 15 | 28 | 2.5 |
| M16 | 24 | 10.0 | 30–200 | 14.8 | 17 | 30 | 3.0 |
| M20 | 30 | 12.5 | 40–200 | 18.0 | 21 | 37 | 3.0 |
| M24 | 36 | 15.0 | 50–200 | 21.5 | 25 | 44 | 4.0 |

**Vida / civata boy serisi** (ISO 4762 ve 4017 ortak tercihli boylar; L bu seride VE aralıkta olmalı):
5, 6, 8, 10, 12, 16, 20, 25, 30, 35, 40, 45, 50, 55, 60, 65, 70, 80, 90, 100, 110, 120, 130, 140, 150, 160, 180, 200.

**ISO 273 geçiş delikleri** (ince / orta / kaba seri):

| M | ince | orta | kaba |
|---|---|---|---|
| M3 | 3.2 | 3.4 | 3.6 |
| M4 | 4.3 | 4.5 | 4.8 |
| M5 | 5.3 | 5.5 | 5.8 |
| M6 | 6.4 | 6.6 | 7.0 |
| M8 | 8.4 | 9.0 | 10.0 |
| M10 | 10.5 | 11.0 | 12.0 |
| M12 | 13.0 | 13.5 | 14.5 |
| M14 | 15.0 | 15.5 | 16.5 |
| M16 | 17.0 | 17.5 | 18.5 |
| M20 | 21.0 | 22.0 | 24.0 |
| M24 | 25.0 | 26.0 | 28.0 |

Bir delik çapı d, `ince(M) − 1e-6 ≤ d ≤ kaba(M) + 1e-6` olan tek M'nin geçiş deliğidir (aralıklar çakışmaz:
her satırda `kaba(M_i) < ince(M_{i+1})`). Orta seri SPEC 23 `CBORE_ISO4762` tablosunun `d` sütunuyla aynıdır.

**ISO 2338 silindirik pim** (d → L aralığı; L serisi: 4, 5, 6, 8, 10, 12, 14, 16, 18, 20, 22, 24, 26, 28, 30,
32, 35, 40, 45, 50, 55, 60, 65, 70, 75, 80, 85, 90, 95, 100, 120, 140, 160, 180, 200):
d2: 6–20, d2.5: 6–24, d3: 8–30, d4: 8–40, d5: 10–50, d6: 12–60, d8: 14–80, d10: 18–95, d12: 22–140,
d16: 26–180, d20: 35–200.

**ISO 15 sabit bilyalı rulman** (d iç, D dış, B genişlik):

| Kod | d | D | B | Kod | d | D | B |
|---|---|---|---|---|---|---|---|
| 6000 | 10 | 26 | 8 | 6200 | 10 | 30 | 9 |
| 6001 | 12 | 28 | 8 | 6201 | 12 | 32 | 10 |
| 6002 | 15 | 32 | 9 | 6202 | 15 | 35 | 11 |
| 6003 | 17 | 35 | 10 | 6203 | 17 | 40 | 12 |
| 6004 | 20 | 42 | 12 | 6204 | 20 | 47 | 14 |
| 6005 | 25 | 47 | 12 | 6205 | 25 | 52 | 15 |
| 6006 | 30 | 55 | 13 | 6206 | 30 | 62 | 16 |
| 6007 | 35 | 62 | 14 | 6207 | 35 | 72 | 17 |
| 6008 | 40 | 68 | 15 | 6208 | 40 | 80 | 18 |

Tablo tutarlılığı (testle denetlenir, her M için): `d_k > d`, `k = d`, `t < k`, lokma köşesi `2s/√3 < d_k`
(4762); `ince > d`, `ince < orta < kaba`, `kaba(M_i) < ince(M_{i+1})` (273); `d₁ > d`, `d₂ > s` (7089);
`s` > d ve 4762 lambası `CBORE_ISO4762[M]` için `D > d_k`, `d = orta(M)` (SPEC 23 ile çapraz).
Rulmanda `d < D`, `B > 0`; pimde aralık uçları L serisinde.

### Eş eksenli delik dizisi
Bileşen `c`'nin dönüşümü `T_c = [[R, t], [0, 1]]`, parçasının delik kaydı `(o, a, depth)` (yerel). Dünyada
`o' = R o + t`, `a' = R a` (SPEC 07 / 08 kuralı). İki delik **eş eksenlidir**:
`|a'_i × a'_j| ≤ tol_aci` ve eksenler arası uzaklık `|(o'_j − o'_i) × a'_i| ≤ tol` (varsayılan `tol = 1e-3`
mm, `tol_aci = 1e-6`). Eş eksenlilik geçişli kabul edilir: grup = eş eksen ilişkisinin bağlı bileşenleri.

**Dizi yönü** `a`: grupta dişli veya lambalı delik varsa onun `a'`'sı (birden çok ve çelişiyorsa →
eşleşmeme `yon`). Yalnız düz boydan boya geçiş delikleri ters yönlü olabilir: böyle bir delik
`o ← o + depth·a`, `a ← −a` ile çevrilir (aynı silindir). Hepsi düz geçiş ise yön, `assembly.components`
sırasında ilk gelen bileşenin deliğinin yönüdür. Delikler `s = (o' − o'_0)·a` ile sıralanır.

**Bitişiklik**: sıralı dizide i'nci delik boydan boya olmalı (son hariç); çıkışı `x_i = o'_i + depth_i·a`
ile sonraki girişi arasında `|(o'_{i+1} − x_i)·a| ≤ tol` olmalı (parçalar birbirine yaslı).

### Vida seçimi
**Ölçü**: son delik dişliyse `M` = diş (`thread_d`, kaba hatve; ince hatve → eşleşmeme `ince_hatve`).
Değilse ilk deliğin çapından ISO 273 ile. Dizideki diğer bütün geçiş delikleri aynı M'nin ISO 273
aralığında olmalı.

**Oturma noktası** `p_s`: ilk delik lambalıysa `o'_0 + cbore_depth·a` (lamba tabanı), değilse `o'_0`
(üst yüz). Lambada baş sığmalı: `cbore_d > d_k(M)` (değilse `bas_sigmiyor`). Havşalı ilk delik →
`havsa` (havşa başlı vida bu SPEC'te yok).

**(a) Dişli deliğe imbus vida (ISO 4762)** — son delik dişli. Sıkıştırma boyu `g = (o'_son − p_s)·a`,
diş kavrama katsayısı `κ` (varsayılan 1.0: çelik / dökme çelik; alüminyumda kullanıcı 2.0 verir):
```
L_min = g + κ d          L_maks = g + thread_depth_son
L = seri ∩ aralık(4762, M) içinde L ≥ L_min olan en küçük;   L > L_maks ise → dis_yetersiz
```
Kaynak: VDI 2230 "Mindesteinschraubtiefe" (çelikte ≈ 1·d, AlSi dökümde ≈ 2·d); Machinery's Handbook,
"Length of engagement".

**(b) Boydan boya geçişe civata + 2 pul + somun (ISO 4017 + 7089 + 4032)** — son delik dişsiz boydan boya,
ilk delik düz (lambalı ilk delik → `lamba_somun`). Sıkıştırma boyu `g = (x_son − o'_0)·a`, pul kalınlığı h,
somun yüksekliği m, uçta en az 2 hatve taşma:
```
L_min = g + 2h + m + 2P
L = seri ∩ aralık(4017, M) içinde L ≥ L_min olan en küçük
```
Hiçbir seri boyu uymuyorsa (`L_min > aralık üstü`) → `uzunluk_yok`.

### Yerleşim ve kısıtlar
`R(u → v)`: u birim vektörünü v'ye çeviren en küçük dönme (Rodrigues; `u = −v` iken `rot_x(180)`).
| Parça | R | t | Kısıtlar (SPEC 08) |
|---|---|---|---|
| (a) vida | `R(−Z → a)` | `p_s` | CONCENTRIC (vida ekseni, ilk delik ekseni) + COINCIDENT PLANE (baş altı, oturma düzlemi) |
| (b) baş altı pulu | `R(+Z → −a)` | `o'_0` | CONCENTRIC (pul, ilk delik) + COINCIDENT PLANE (pul alt yüzü, ilk deliğin giriş düzlemi) |
| (b) civata | `R(−Z → a)` | `o'_0 − h a` | CONCENTRIC (civata, ilk delik) + COINCIDENT PLANE (baş altı, pul üst yüzü) |
| (b) somun altı pulu | `R(+Z → a)` | `x_son` | CONCENTRIC (pul, son delik) + COINCIDENT PLANE (pul alt yüzü, son deliğin çıkış düzlemi) |
| (b) somun | `R(+Z → a)` | `x_son + h a` | CONCENTRIC (somun, son delik) + COINCIDENT PLANE (somun alt yüzü, pul üst yüzü) |

Referanslar (hepsi bileşenin yerel çerçevesinde; dünya karşılıkları yukarıdaki T ile):
- Standart parça ekseni `Ref(AXIS, (0,0,0), (0,0,1))`.
- Vida / civata baş altı `Ref(PLANE, (0,0,0), (0,0,−1))`; pul / somun alt yüzü `Ref(PLANE, (0,0,0), (0,0,−1))`;
  pul üst yüzü `Ref(PLANE, (0,0,h), (0,0,1))`.
- Delikli parçada delik ekseni `Ref(AXIS, o, a)`; oturma düzlemi `Ref(PLANE, p_s yerel, −a)`; giriş düzlemi
  `Ref(PLANE, o, −a)`; çıkış düzlemi `Ref(PLANE, o + depth·a, a)`. Normaller malzemeden dışa bakar,
  böylece SPEC 08'in "yüz yüze, normaller zıt" kuralı sağlanır. Delik kaydı ters çevrildiyse çevrilmiş
  `o, a` kullanılır.

Her eklenen parça eksen etrafında serbest döner: CONCENTRIC (4) + düzlem (3) birlikte 5 serbestlik kaldırır
(SPEC 08 K5), parça başına `dof = 1` kalır. Yerleşim kısıtları zaten sağlar (artık ≤ 1e-9).

## Dosyalar
- Yeni: `geometry/standart/__init__.py`, `geometry/standart/tablo.py` (yukarıdaki tablolar + tanım
  ayrıştırma; **saf Python, OCCT yok**), `geometry/standart/parcalar.py` (OCCT ile parça üretimi),
  `assy/oneri.py` (saf Python + numpy), `tests/geometry/test_standart.py`, `tests/assy/test_oneri.py`,
  `durum/35-standart-parca.md`
- Dokunulmayacak: `geometry/part.py`, `assy/model.py`, `geometry/holes.py` (sadece okunur: `THREADS_COARSE`,
  `CBORE_ISO4762`), `assy/solver.py`, `assy/mates.py`, `pyproject.toml`, `DURUM.md`, `docs/`. Yeni bağımlılık yok.
- Arayüz eki gerekmiyor: `Hole` (SPEC 23) ve `Ref` / `Mate` / `Component` / `Assembly` (SPEC 00 / 08) yeterli.
  Kararlı yüz referansı (A2) kullanılmaz; kısıtlar delik kaydının koordinatlarından kurulur.
- Paket sınırı: `assy/oneri.py` yalnız `assy.model`, `assy.solver` (yalnız testte), `geometry.part.Hole` ve
  OCCT'siz `geometry.standart.tablo` modülünü import eder. `geometry.standart.tablo` bu SPEC ile geometry'nin
  OCCT'siz ikinci arayüz dosyası olur (açık soru 1).

`parcalar.py` testleri `@pytest.mark.occt` işaretli; tablo ve öneri testleri OCCT'siz koşar (delikli parça
yerine `.holes` özniteliği olan basit nesne kullanılır; `assy/bom.py` ile aynı yaklaşım).

## Arayüz

### `geometry/standart/tablo.py` (saf Python)
- Sabitler: `ISO4762`, `ISO4017`, `ISO4032`, `ISO7089`, `ISO273`, `ISO2338`, `ISO15` (`dict`, anahtar `"M8"`,
  pimde `float` d, rulmanda `"6204"`), `L_SERI_VIDA`, `L_SERI_PIM` (artan `tuple[float, ...]`).
  Satır biçimleri: `ISO4762["M8"] = (d_k, k, s, t, L_min, L_maks)`, `ISO4017["M8"] = (s, k, L_min, L_maks)`,
  `ISO4032["M8"] = (s, m)`, `ISO7089["M8"] = (d1, d2, h)`, `ISO273["M8"] = (ince, orta, kaba)`,
  `ISO2338[6.0] = (L_min, L_maks)`, `ISO15["6204"] = (d, D, B)`.
- `boyut(M: str) -> float` — `"M8"` → 8.0; tabloda yoksa `GeometryError`.
- `gecis_olcusu(d: float) -> str | None` — ISO 273 aralığına giren M; yoksa `None`.
- `vida_boyu(M: str, L_min: float, seri: str = "4762") -> float | None` — `seri ∈ {"4762", "4017"}`;
  seri ∩ aralıkta `L ≥ L_min − 1e-9` olan en küçük boy, yoksa `None`.
- `ayristir(tanim: str) -> tuple[str, dict]` — kanonik yazım (tek boşluk, büyük harf):
  `"ISO 4762 M8x25"`, `"ISO 4017 M8x40"`, `"ISO 4032 M8"`, `"ISO 7089 M8"`, `"ISO 2338 6x30"`,
  `"ISO 15 6204"` → `("4762", {"M": "M8", "L": 25.0})` vb. Bozuk yazım, bilinmeyen standart / ölçü,
  seride veya aralıkta olmayan L → `GeometryError`.
- `tanim(std: str, **olcu) -> str` — `ayristir`'ın tersi (`tanim("4762", M="M8", L=25)` → `"ISO 4762 M8x25"`;
  L tamsayıysa ondalıksız yazılır).

### `geometry/standart/parcalar.py` (OCCT)
- `socket_screw(M, L) -> Part`, `hex_bolt(M, L) -> Part`, `hex_nut(M) -> Part`, `washer(M) -> Part`,
  `dowel_pin(d, L) -> Part`, `bearing(kod) -> Part` — Teori'deki koordinat kuralı ve basit geometri;
  `Part.name` = kanonik tanım; `holes = ()`.
- `parca(tanim: str) -> Part` — `ayristir` + ilgili üretici. Aynı tanım her çağrıda aynı hacmi verir.
- Hatalar: tablo dışı ölçü, seri / aralık dışı L → `GeometryError` (sessiz yuvarlama yok).

### `assy/oneri.py` (saf Python + numpy)
```python
@dataclass(frozen=True)
class DelikRef:
    component: str
    index: int  # Part.holes içindeki sıra


@dataclass
class Oneri:
    kind: str  # "vida" (a) | "civata_somun" (b)
    M: str  # "M8"
    L: float  # mm, seçilen standart boy
    grip: float  # mm, sıkıştırma boyu g
    stack: tuple[DelikRef, ...]  # dizi yönünde sıralı
    components: list[Component]  # eklenecekler; part = kanonik tanım ("ISO 4762 M8x12")
    mates: list[Mate]


@dataclass
class Eslesmeme:
    stack: tuple[DelikRef, ...]
    neden: str  # aşağıdaki kodlardan biri
```
- `eksen_gruplari(assembly, parts, tol=1e-3, tol_aci=1e-6) -> list[tuple[DelikRef, ...]]` — `parts`:
  `Mapping[str, nesne]` (anahtar `Component.part`, nesnenin `.holes`'u okunur). En az iki farklı bileşenden
  delik içeren eş eksen grupları, dizi yönünde sıralı; grupların sırası ilk deliğin
  (`assembly.components` sırası, delik sırası) sırasıdır. Tek delikli gruplar dönmez.
- `oner(assembly, parts, kappa=1.0, tol=1e-3, tol_aci=1e-6) -> tuple[list[Oneri], list[Eslesmeme]]` —
  her grup ya bir `Oneri` ya bir `Eslesmeme` üretir. `neden` kodları:
  `ayni_bilesen` (grupta aynı bileşenden iki delik), `yon`, `bosluk` (bitişiklik bozuk), `kor_ara`
  (son olmayan delik kör), `olcu_uyusmuyor` (geçiş deliği ISO 273 aralığında değil veya diş ile uyuşmuyor),
  `ince_hatve`, `havsa`, `bas_sigmiyor`, `lamba_somun`, `dis_yetersiz`, `uzunluk_yok`, `ortada_dis`
  (dişli delik dizinin son deliği değil).
- `uygula(assembly, oneriler) -> Assembly` — girdiyi değiştirmeden yeni montaj: bileşenler ve kısıtlar
  eklenmiş. Ad kuralı: `vida_1`, `civata_1`, `pul_1`, `pul_2`, `somun_1`… (tür başına sayaç, montajdaki
  mevcut adlarla çakışırsa sayaç ilerler). Eklenen bileşenler `fixed=False`.
- Hatalar (`AssyError`): `parts`'ta olmayan parça kimliği, `kappa ≤ 0`, `tol ≤ 0`, bilinmeyen bileşen.

## Kabul kriterleri
- [ ] K1 Tablolar: Teori'deki tutarlılık koşullarının hepsi her satırda; örnek değerler birebir (M8: 4762
  `(13, 8, 6, 4, 12, 80)`, 4017 `(13, 5.3, 16, 80)`, 4032 `(13, 6.8)`, 7089 `(8.4, 16, 1.6)`, 273 `(8.4, 9, 10)`;
  `ISO15["6204"] = (20, 47, 14)`); 273 orta = `CBORE_ISO4762[M][0]` ve `CBORE_ISO4762[M][1] > d_k` —
  `tests/geometry/test_standart.py`
- [ ] K2 `gecis_olcusu` (6.6 → M6, 9.0 → M8, 10.0 → M8, 8.0 → None, aralık uçları), `vida_boyu` (M8, L_min 9.4 →
  12; 28 → 30; 81 → None; 4017 M8 37.5 → 40), `ayristir` / `tanim` gidiş-dönüş ve hatalı yazımlar
  (`"ISO 4762 M8x27"`, `"ISO 4762 M7x20"`, `"iso 4762 M8x25"`, `"ISO 15 6309"`) → `GeometryError` — `test_standart.py`
- [ ] K3 `socket_screw` (M3×10, M8×25, M24×100): V formülle rel 1e-6; bbox `x,y ∈ ±d_k/2`, `z ∈ [−L, k]`
  (1e-6 mm); ağırlık merkezi eksende (|x|, |y| ≤ 1e-6) — `@pytest.mark.occt`
- [ ] K4 `hex_bolt`, `hex_nut`, `washer` (M6, M8, M20): V rel 1e-6; altıgen bbox `x ∈ ±s/2`, `y ∈ ±s/√3`;
  somun ve pul `z ∈ [0, h]` — `@pytest.mark.occt`
- [ ] K5 `dowel_pin` (6×30, 10×18) ve `bearing` (6000, 6204, 6208): V rel 1e-6; `parca(tanim).name == tanim`
  ve `parca` ile doğrudan üretici aynı hacmi veriyor — `@pytest.mark.occt`
- [ ] K6 Üretici hataları: seride olmayan L, aralık dışı L (M8×10, M8×90), tablo dışı M ve rulman kodu, pim
  aralık dışı → `GeometryError` — `test_standart.py`
- [ ] K7 `eksen_gruplari`: üç bileşenli montajda (biri Z etrafında 90° dönük, biri ötelenmiş) dünya
  koordinatında eş eksen grupları doğru ve sıralı; 2e-3 mm kaçık eksen gruplanmıyor, 0.5e-3 mm gruplanıyor;
  ters yönlü düz geçiş deliği çevrilip gruba giriyor; tek delikli eksen dönmüyor — `tests/assy/test_oneri.py`
- [ ] K8 (a) vida: plaka 10 mm, M8 lambalı boydan boya (`cbore_depth` 8.6) + taban M8 dişli (`thread_depth` 20)
  → `g = 1.4`, `L_min = 9.4`, `L = 12`, tanım `"ISO 4762 M8x12"`; düz Ø9 geçişli 20 mm plaka → `g = 20`, `L = 30`;
  `κ = 2` ile 20 mm plaka → `L_min = 36`, `L = 40`; vidanın T'si tablodaki kurala eşit (1e-12);
  `assy.solver.residuals` ≤ 1e-9; `dof` tam 1 artıyor — `test_oneri.py`
- [ ] K9 (b) civata + somun: 10 + 15 mm iki plaka, Ø9 geçiş → `g = 25`, `L_min = 25 + 3.2 + 6.8 + 2.5 = 37.5`,
  `L = 40`; 4 bileşen (civata, 2 pul, somun) tablodaki T'lerle; artık ≤ 1e-9; `dof` tam 4 artıyor — `test_oneri.py`
- [ ] K10 Eşleşmeme kodları: her kod için en az bir senaryo doğru kodu veriyor (`ayni_bilesen`, `yon`, `bosluk`
  0.5 mm aralık, `kor_ara`, `olcu_uyusmuyor` M6 geçiş + M8 diş, `ince_hatve` M8x1, `havsa`, `bas_sigmiyor`,
  `lamba_somun`, `dis_yetersiz` thread_depth 5, `uzunluk_yok` 300 mm paket, `ortada_dis`) — `test_oneri.py`
- [ ] K11 `uygula`: girdi montaj değişmiyor; yeni adlar tekil ve kurala uygun (mevcut `vida_1` varken
  `vida_2`); `Assembly.validate` geçiyor; `assy.solver.solve` 0 iterasyonla dönüyor; `to_dict` / `from_dict`
  gidiş-dönüşü eşit; eklenen her `Component.part` için `parca(...)` kuruluyor (`@pytest.mark.occt` kısmı) — `test_oneri.py`
- [ ] K12 Değişmezlik: bütün montaj keyfi rijit G ile taşınınca aynı M, L, kod ve eklenen T'ler `G·T` (1e-9) — `test_oneri.py`
- [ ] K13 Hatalar: `parts`'ta olmayan kimlik, `kappa ≤ 0`, `tol ≤ 0` → `AssyError` — `test_oneri.py`
- [ ] Tüm testler yeşil (`pytest` 0 failed, bu SPEC'te 0 "uygulanmamış"), `ruff check .` ve
  `ruff format --check .` temiz

## Kapsam dışı
- Gerçek diş helisi, pah, köşe yuvarlatması, lokma dibi konisi; rulmanın iç bilezik / bilye / kafes ayrıntısı
- Havşa başlı vida (ISO 10642), alçak başlı vida (DIN 7984), saplama, ince hatveli vida, inç ölçüler
- Pim ve rulman için otomatik öneri (yalnız kütüphane); yataklama toleransları (H7/k6), sıkı geçme hesabı
- Ön yükleme / sıkma torku / VDI 2230 mukavemet hesabı; κ dışında malzemeye göre kavrama tablosu
- Önerilen parçaların mevcut parçalarla girişim kontrolü (SPEC 09 ile ayrıca yapılabilir)
- Parça geometrisinden delik tanıma (kayıtsız delikler; SPEC 27), STEP'ten gelen parçalara öneri
- Tezgah ekranında kütüphane / öneri paneli (ileride ekran SPEC'i)
- Standart parçaların BOM'da "standart" olarak ayrı listelenmesi (SPEC 07 BOM'u tanımı adla zaten toplar)
