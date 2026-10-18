# SPEC 29 — Otomatik işlem planı: özelliklerden freze ve torna işlemlerine, takım seçimi, sıra, bağlama, doğrulama

## Amaç
Kullanıcı parçayı, ham malzemeyi, takım kütüphanesini ve malzeme adını verir; sistem elle profil çizmeden ve elle
takım seçmeden **işlem planını** kurar: SPEC 27 özelliklerinden (freze: yüz alma, açık bölge, cep, delik; torna:
alın, kaba zarf, kanal) SPEC 03 / 04 / 20 işlemlerine geçer, takımı ve kesme verisini SPEC 14 kütüphanesinden seçer,
işlemleri sıralar, bağlamayı (`Setup`) kurar, gerekirse ikinci bağlamayı (alt yüz) ekler, planı SPEC 05 / 22
simülasyonuyla doğrular ve G-code'u SPEC 04 / 14 / 21 yazıcılarıyla verir. Planlanamayan her özellik **gerekçe
koduyla** listelenir; hiçbir özellik sessizce atlanmaz.

Hedefe yeri: tasarımdan tezgâha tek yerel uygulamada (Tezgah, SPEC 24 / 25) "Parçayı aç → Plan → Simüle et →
G-code" akışının "Plan" adımı. Bu SPEC hesap katmanıdır; arayüz yalnız `MillPlan` / `TurnPlan` sonuçlarını gösterir.

## Bağımlılıklar ve kod sırası
- Kullanılır: SPEC 27 (`cam/features.py`, `cam/turn_features.py`), SPEC 14 (`cam/cutting.py`, `cam/library.py`,
  `cam/setups.py`), SPEC 03 (`cam/ops2d.py`, `cam/offset.py`), SPEC 04 (`cam/gcode`), SPEC 20 (`cam/lathe_ops.py`,
  `cam/lathe.py`), SPEC 05 (`cam/sim`), SPEC 21 (`cam/gcode/lathe.py`), SPEC 22 (`cam.sim.simulate_lathe`).
- Kod bu bağımlılıkların hepsi `main`'e birleşmeden yazılmaz. Torna tarafı (21, 22) gecikirse koordinatör torna
  bölümünü (K11–K14) ayrı bir eke (29b) ayırabilir; freze bölümü tek başına anlamlıdır.
- SPEC 28 (katı parçadan torna profili) zorunlu değildir: `plan_turn` profili girdi alır. SPEC 28 birleşince
  `turn_profile(part).outer` / `.inner` doğrudan `plan_turn`'e verilir (Tezgah işi; bu SPEC'te ayrı işlev yok).
- 3B yüzey işleme (SPEC 06 / 06b) bu SPEC'in otomatik planında yoktur: SPEC 27 eğik / serbest yüzeyi 2.5D dışı
  sayar (`CamError`). Bkz. Kapsam dışı.
- **Arayüz değişikliği gerekmez.** `cam/model.py`, `geometry/part.py` ve diğer `*/model.py` değişmez.

## Teori

### 1. Plan modeli
Plan, işlem kayıtlarının sıralı listesidir. Her kayıt (`PlannedOp`) tam olarak bir SPEC 03 / 04 / 20 çıktısı
(`Toolpath` veya `DrillOp`) taşır ve hangi özellikten, hangi takımla, hangi kesme verisiyle kurulduğunu söyler.
Planlanamayan özellik `Unplanned(feature, code, detail)`, plan sırasında bilinen ama işlemle giderilemeyen durum
`PlanNote(feature, code, value, detail)` olur. Plan saf işlevdir: aynı girdi → aynı plan (bayt bayt aynı özet ve
`Toolpath.to_dict()`); girdiler (kütüphane, stok, özellikler) değiştirilmez.

Özellik adresi metindir: `"faces[0]"`, `"opens[i]"`, `"pockets[i]"`, `"holes[i]"`, `"alt_yuz"`; torna:
`"alin"`, `"dis"`, `"ic"`, `"grooves[i]"`, `"recesses[i]"`. `i`, SPEC 27 sonucundaki sıradır.

Gerekçe kodları (sabit küme; testler kodla denetler):
| Kod | Anlam |
|---|---|
| `kesme_verisi_yok` | Bu türde, bu malzeme için gerekli kesme verisi olan takım yok |
| `takim_yok` | Uygun tür / çap / genişlikte takım yok |
| `takim_sigmiyor` | Aday takımların hiçbiri bölgeye sığmıyor |
| `kesici_boy_yetmez` | Sığan takımların kesici boyu derinliğe yetmiyor |
| `ustten_erisilemez` | Delik ekseni `−Z` değil (`HoleFeature.top_access` yanlış) |
| `havsa_takimi_yok` | Havşa: `ToolKind`'da havşa takımı yok (delik matkapla açılır, havşa açılmaz) |
| `kilavuz_cevrimi_yok` | Dişli delik: SPEC 04'te kılavuz çevrimi (`G84`) yok (kılavuz matkabı deliği açılır) |
| `baglama_carpismasi` | İşlem SPEC 14 `check_setup`'tan geçmiyor (mesaj `detail`'de) |
| `on_delik_yok` | Torna iç profili var ama ham malzeme dolu (`d = 0`); tornada delme kapsam dışı |
| `genel_girinti` | Torna `Recess`: profilli kanal işlemi SPEC 20'de yok |

Not kodları: `kose_artigi` (`value` = beklenen artık hacmi, mm³), `yan_paso_kisildi` (`value` = kullanılan `s`),
`delik_tasma_kisildi` (`value` = kullanılan taşma `b`), `ikinci_baglama` (`value` = alt yüzden alınacak kalınlık).

### 2. Ortak kesme verisi kuralları (SPEC 14 üzerinden)
- Freze adayı: `kind = FLAT`, `cutting[material]` var **ve** `ap`, `ae` dolu. Matkap adayı: `kind = DRILL`,
  `cutting[material]` var. Torna adayı: türü uygun `LatheTool`, `cutting[material]` var; kaba işlemde `ap` dolu.
  Kesme verisi eksik takım aday değildir (sessiz varsayılan yok).
- Devir ve ilerleme: freze / matkap `cam.cutting.milling(tool, material, n_max)` → `SpindleFeed(n, F, …)`;
  `Toolpath.rpm = n`, kesme ilerlemesi `F`. Torna `cam.cutting.css(tool, material, n_max)` → `TurnCut(css = Vc,
  rpm = n_max, feed = fn)` (G96 + G50; SPEC 14: `n_max` torna planında zorunlu).
- Paso derinliği `a_p = min(cd.ap, tool.flute_length)`. Yan paso `s = min(cd.ae, s_max)`, `s_max = D/2`
  (SPEC 03 Ek A). `cd.ae > s_max` ise `s = s_max` ve not `yan_paso_kisildi`. (SPEC 03b birleşince `s_max` ayrı ekle
  `D` olur; bu SPEC'in testleri `ae ≤ D/2` ile kurulur, K7 hariç.)
- Dalma ilerlemesi `plunge_feed = plunge_ratio · F` (varsayılan `0.3`).
- Güvenli Z `z_safe = cam.setups.clearance_height(setup)`; `Cut.clearance = clearance` (varsayılan `1.0`).
- **Kesici boy koşulu** (SPEC 14 `check_setup` ile aynı ölçü): freze takımı ancak
  `flute_length ≥ z_stok_üst − z_alt` ise derinliği `z_alt` olan işlemi yapabilir (`z_stok_üst` = bağlamanın stok
  üstü). Matkapta `z_alt` delme dibidir (§5).

### 3. Alan işlemleri: yüz alma, açık bölge, cep
**Bölge.** Cep: `PocketFeature.region`. Açık bölge: zarf `E` dışa büyütülür, adalar aynen kalır:
`Ω = Region(outer = offset(Region(E), −(r_T + m)).outer, holes = islands)`; `r_T` aday takımın yarıçapı,
`m = open_margin` (varsayılan `1.0`). Büyütme takıma bağlıdır; her aday için yeniden kurulur. Böylece takım
stoğun dışından gelir ve basamak / dış kontur, SPEC 03 cebiyle tam işlenir (`E`'ye değen adalar büyütmeden sonra
`E`'den `r_T + m` uzaktadır).

**Sığma.** Takım `T` bölgeye sığar ⇔ `cam.offset.offset(Ω, D_T/2) ≠ []` (SPEC 03 cebinin kendi koşulu).

**Takım seçimi (bir alan işlemi, derinlik `[z_b, z_t]`).** Adaylar `D` azalan, eşitlikte `id` artan sırada.
1. `S` = sığan **ve** kesici boy koşulunu sağlayan adaylar. Aday yok → `kesme_verisi_yok` / `takim_sigmiyor` /
   `kesici_boy_yetmez` (ilk boşalan süzgece göre, bu sırayla).
2. `T₁ = S`'nin ilki (en büyük çap).
3. Köşe sınırı: cepte `d_max = PocketFeature.max_tool_d`; açık bölgede `d_max = 2·r_corner(Ω)` (SPEC 27 §8
   kuralı büyütülmüş `Ω`'ya uygulanır). Yüz almada köşe yok.
4. `T₁.D ≤ d_max` ise tek işlem.
5. Değilse ve `rest = True` ise kalan malzeme takımı `T₂`: `S` içinde `D ≤ d_max` olanların en büyüğü; yoksa
   `D < T₁.D` olanların en küçüğü (artığı küçültür). `T₂` yoksa tek işlem. `rest = False` ise `T₂` varsa tek
   işlem `T₂` ile yapılır (yavaş ama tek takım).

**Kalan malzeme işlemi ve kanıtı.** `r₁ = T₁.D/2`, `r₂ = T₂.D/2`. SPEC 03 cebi (Ek A1, `s ≤ r`) `Ω`'nın
açılımını `O_r(Ω) = (Ω ⊖ B_r) ⊕ B_r` tam keser. `T₂` ile `Ω`'nın her halkası boyunca kontur (dış halka
`side="ic"`, adalar `side="dis"`) `∂(Ω ⊖ B_{r₂}) ⊕ B_{r₂}` şeridini keser; kesmediği yer `Ω ⊖ B_{2r₂}`'dir.
- **Önerme.** `2r₂ ≥ r₁` (yani `D₂ ≥ D₁/2`) ise `T₁` cebi + `T₂` konturu, `T₂` cebinin keseceği her yeri keser:
  `Ω ⊖ B_{2r₂} ⊆ Ω ⊖ B_{r₁} ⊆ O_{r₁}(Ω)`, dolayısıyla `O_{r₂}(Ω) ⊆ O_{r₁}(Ω) ∪ (O_{r₂}(Ω) ∖ (Ω ⊖ B_{2r₂}))`. ∎
- Bu yüzden: `D₂ ≥ D₁/2` → kalan işlem `T₂` konturu (`kind = "cep_kalan"`); değilse `T₂` ile **tam cep**
  (`kind = "cep_kalan"`, aynı adres). İkisinde de sonuç `T₂`'nin tek başına bırakacağı artıkla aynıdır.

**Köşe artığı notu.** Bölgenin içinden bakınca dışbükey her köşe için (SPEC 27 §8), son işlemi yapan takımın
yarıçapı `r` köşe yarıçapı `R_c`'den büyükse beklenen artık alanı:
`A = (r² − R_c²) · (tan(φ/2) − φ/2)`; `φ` köşedeki dönüş açısı (yayda yay süpürme açısı, keskin köşede teğetler
arası açı), `R_c = 0` keskin köşede. Doğrulama: `φ = 90°` → `(r² − R_c²)(1 − π/4)` (dikdörtgen köşe artığı).
Formül, köşeye teğet giren iki komşu parçanın en az `r·tan(φ/2)` uzun olduğu durumda tamdır (yakın köşeler
etkileşirse plan yine `A`'yı yazar, simülasyon gerçeği gösterir). Alanların toplamı `·(z_t − z_b)` →
`PlanNote("kose_artigi", value = V)`. Takım köşeye sığıyorsa (`r ≤ R_c` her köşede) not yok.

**İşlem kurulumu.**
- Yüz alma: `ops2d.face(stock, T, Cut(z_top = stock.zmax, z_bottom = f.z, a_p, feed, plunge_feed, rpm, z_safe,
  clearance, stepover = s))`.
- Cep / açık bölge: `ops2d.pocket(Ω, T, Cut(z_top = f.z_top, z_bottom = f.z_bottom, …, stepover = s))`.
- Kalan kontur: her halka için `ops2d.contour(halka, T₂, Cut(…, stepover = None), side)`, aynı `[z_b, z_t]`.

### 4. Delikler
Yalnız `top_access` delikler; diğerleri `ustten_erisilemez`. Delik girişi `z_e = origin_z`.
- **Matkap seçimi**: `|D − hole.d| ≤ drill_tol` (varsayılan `0.01`) olan matkap adayları; delme dibi `z_dip` için
  kesici boy koşulu; uyanlar içinde en kısa `flute_length` (rijitlik), eşitlikte `id`. Yoksa `takim_yok` /
  `kesme_verisi_yok` / `kesici_boy_yetmez`.
- **Delme dibi**: kör delik `z_dip = z_e − depth` (matkap ucu; konik dip kapsam dışı, SPEC 27). Boydan delik:
  `b = min(breakthrough, z_e − depth − z_stok_alt)` (varsayılan `breakthrough = 1.0`); `z_dip = z_e − depth − b`.
  `b < breakthrough` ise not `delik_tasma_kisildi` (SPEC 14: stok altına inilmez). `b < 0` olamaz (SPEC 27 ön koşulu).
- **Çevrim**: `depth / D > peck_limit` (varsayılan `3.0`) → `G83`, `q = peck_q · D` (varsayılan `peck_q = 1.0`);
  değilse `G81`. `r = z_e + clearance`. Dönüş `G98`.
- **Gruplama**: aynı (matkap, `z_e`, `z_dip`, çevrim, `q`) delikler tek `DrillOp`. Grup içinde sıra en yakın
  komşu: ilk delik `(x, y)` sözlük sırasında en küçük; sonra kalanların en yakını (eşit uzaklıkta sözlük sırası).
  Gruplar: matkap `D` azalan, sonra `z_e` azalan, sonra ilk deliğin `(x, y)`'si.
- **Lamba** (`cbore_d > 0`): delmeden sonra dairesel cep: `Ω = Region(tam daire, R = cbore_d/2, merkez
  origin[:2])`, `[z_e − cbore_depth, z_e]`; takım seçimi §3 (tek işlem, `rest` yok), `kind = "lamba"`.
- **Havşa** (`csk_d > 0`): delik açılır, havşa `havsa_takimi_yok`. **Diş** (`thread ≠ ""`): `d` (kılavuz matkabı)
  deliği açılır, diş `kilavuz_cevrimi_yok`. İkisi de `Unplanned` (adres aynı delik).

### 5. Sıra ve bağlama (freze)
- **Bağlama 1 (üst)**: `Setup(name = "baglama-1", wcs, stock, fixtures)`; `wcs` verilmezse `Wcs("G54")`. Parça
  koordinatı = iş koordinatı.
- **Sıra, bağlama 1**: (a) alan işlemleri `z_t` azalan; eşitlikte yüz alma, açık bölge, cep; eşitlikte SPEC 27
  sırası; her alan işleminin kalan malzeme işlemi hemen arkasında. Kural: bir alan işleminin `z_t`'sinin üstünde
  kalan malzeme, kendisinden önceki işlemlerce alınmıştır (SPEC 27'de her dilim kendi üstündeki dilimlerin
  özelliklerinin altındadır). (b) delik grupları (§4 sırası); her grubun lambaları grubun hemen arkasında.
- **Bağlama 2 (alt yüz)**: `stock.zmin < zmin_parça − tol` ise. Ters çevirme SPEC 05 kuralıyla (stok merkezinden
  geçen X'e paralel eksen etrafında 180°): `y' = 2y_c − y`, `z' = 2z_c − z`; `(y_c, z_c)` stok merkezi.
  Bağlama 2 stoğu, bağlama 1'in stoğunun aynı kutusudur (ters çevirme kutuyu kendine götürür); iş koordinatı ters
  çevrilmiş çerçevedir. Tek işlem: yüz alma `z_top = stock.zmax`, `z_bottom = z' (zmin_parça) = 2z_c −
  zmin_parça`, takım §3 yüz alma kuralı. `wcs2` (varsayılan `Wcs("G55")`), `fixtures2` (varsayılan bağlama 1'in
  elemanları). Not `ikinci_baglama`, `value = zmin_parça − stock.zmin`.
- **Bağlama denetimi**: her işlem kurulduktan sonra kendi bağlamasıyla `cam.setups.check_setup(setup, [op])`.
  `CamError` → işlem plandan çıkar, `Unplanned(adres, "baglama_carpismasi", mesaj)`. (Bir sonraki takımı denemez:
  çarpışma çoğunlukla bağlama yerleşiminden gelir; kullanıcı düzeltir.)
- `strict = True` ise `unplanned` boş değilse `CamError` (mesajda tüm adres ve kodlar).

### 6. Torna planı
Girdi: dış profil (SPEC 20 kuralı, açık, `side="dis"`), isteğe bağlı iç profil, `CylinderStock`, kütüphane,
malzeme, `rpm_max`. Özellikler `turn_features(outer, stock, "dis")` ve varsa `turn_features(inner, stock, "ic")`.
- **Takım seçimi** (deneme ile, deterministik): aday sırası tablodaki gibidir; ilk adayla SPEC 20 işlevi çağrılır,
  `CamError` verirse sıradaki denenir; hiçbiri olmazsa `Unplanned(adres, "takim_yok", son hata mesajı)`.

| İşlem (`kind`) | Adres | SPEC 20 çağrısı | Aday türü ve sırası |
|---|---|---|---|
| `alin` | `"alin"` | `face(stock, T, cut, z_face)` | `TURN`, `nose_r` azalan |
| `dis_kaba` | `"dis"` | `rough(tf.rough, stock, T, cut, allowance = δ, side="dis")` | `TURN`, `nose_r` azalan, `ap` dolu |
| `ic_kaba` | `"ic"` | `rough(tf_ic.rough, …, side="ic")` | `BORE`, `nose_r` azalan, `ap` dolu |
| `ic_finis` | `"ic"` | `finish(tf_ic.rough, …, side="ic")` | `BORE`, `nose_r` artan |
| `dis_finis` | `"dis"` | `finish(tf.rough, stock, T, cut, side="dis")` | `TURN`, `nose_r` artan |
| `kanal` | `"grooves[i]"` | `groove(stock, T, cut, z_left, z_right, x_top, x_bottom, side)` | `GROOVE`, `width ≤ z_right − z_left`, `width` azalan |

  Eşitlikte `id` artan. Sıra tablodaki satır sırasıdır (alın → dış kaba → iç kaba → iç finiş → dış finiş →
  kanallar ön→arka; kanal en son: ince boyunlu kesitte rijitlik). İç işlem yalnız `stock.d > 0` iken; değilse
  `Unplanned("ic", "on_delik_yok")`.
- **Finiş profili** `tf.rough`'tur (kanallar köprülenmiş monoton zarf): kanallar kanal takımıyla, `Recess`'ler
  `genel_girinti` olarak ayrılır; finiş takımı girintiye dalmaz. Girinti yoksa `tf.rough = tf.finish`.
- **Pay**: finiş işlemi planlanacaksa kaba `allowance = δ_t` (varsayılan `0.2`), değilse `0`.
- **Kesme**: `TurnCut(feed = fn, rpm = rpm_max, css = Vc, a_p = cd.ap, clearance = clearance)`.
- **Bağlama**: `Setup("torna-1", wcs, stock, fixtures)` (`fixtures`: ayna, `CylinderStock` olarak, kullanıcıdan).
  Tek bağlama; ters bağlama kapsam dışı.

### 7. Doğrulama (simülasyon)
- **Freze** (`verify_mill`): bağlama 1 `simulate(ops_1, stock, cell, machine, part_z = part_zmap(part, grid),
  model = "dexel")`. Bağlama 2 varsa `initial = r1.dexel.flipped()` ve parça haritası ters çevrilmiş ağdan:
  `V' = (x, 2y_c − y, 2z_c − z)`, `mesh_zmap(V', T, grid)` (`V, T = part.mesh(tol)`; üçgen yönü önemsizdir).
- **Torna** (`verify_turn`): `simulate_lathe(ops, setup, cell, machine, part = profile_rmap(kesit, grid))`;
  kesit, dış profilin (varsa iç profille) eksenle kapatılmış kapalı `Profile`'ıdır: ön uçta ve arka uçta profil
  ucundan eksene (içte iç profile) dik doğrular.
- `PlanCheck.ok ⇔` hiç çarpışma / çakma kaydı yok (SPEC 05 / 22 `collisions == []`). `rest_volume`,
  `gouge_volume`, `removed_volume`, `total_time` raporlanır; `expected_rest = Σ kose_artigi` (freze).
- Izgara hata sınırı (SPEC 05 K): kaldırılan / kalan hacimde `≤ P·Δ·H` (`P` işlenen sınırların çevresi, `Δ`
  hücre, `H` derinlik); testler bu sınırla karşılaştırır.

### 8. G-code
- Freze: her bağlama için `cam.gcode.write(ops_i, dialect, program_no = program_no + i, setup = setup_i,
  length_offsets = …)` (SPEC 14). GRBL'de `length_offsets` verilmezse `cam.tool_length.length_offsets(lib, ids,
  ref_id = ilk takım)`; Fanuc'ta `None`. Sonuç bağlama başına bir program.
- Torna: `write_lathe(ops, spindle, tool_change, dialect, program_no)` (SPEC 21); `spindle`, `tool_change`
  kurulum bilgisidir ve zorunludur (SPEC 30 kuralı).

## Dosyalar
- Yeni: `cam/plan.py` (§1–5, §8 freze), `cam/plan_turn.py` (§6, §8 torna), `cam/plan_verify.py` (§7)
- Yeni: `tests/cam/test_plan.py` (OCCT'siz: elle kurulmuş `Features`), `tests/cam/test_plan_part.py`
  (`@pytest.mark.occt`, parça + simülasyon), `tests/cam/test_plan_turn.py` (OCCT'siz)
- Yeni: `durum/29-islem-plani.md`
- Kullanılır (değişmez): bağımlılıklardaki tüm modüller, `cam/model.py`, `geometry/part.py`
- Dokunulmayacak: tüm `*/model.py`, `geometry/part.py`, SPEC 03 / 04 / 05 / 14 / 20 / 21 / 22 / 27 dosyaları,
  `docs/yol-haritasi.md`, `DURUM.md`, `pyproject.toml`. Yeni bağımlılık yok.

## Arayüz
```python
# cam/plan.py
@dataclass(frozen=True)
class PlannedOp:
    name: str  # f"{sıra:02d}-{kind}-T{tool_id}", sıra 1'den, bağlamalar boyunca sürer
    kind: str  # "yuz_alma" | "acik_bolge" | "cep" | "cep_kalan" | "delik" | "lamba"  (torna: §6 tablosu)
    setup: int  # 0 → setups[0], 1 → setups[1]
    feature: str  # özellik adresi (§1); delik grubunda "holes[i,j,...]"
    tool_id: int
    op: Toolpath | DrillOp
    spindle: SpindleFeed  # SPEC 14; tornada n = rpm_max, Vc = css, f = fn
    a_p: float | None
    stepover: float | None


@dataclass(frozen=True)
class Unplanned:
    feature: str
    code: str  # §1 tablosu
    detail: str


@dataclass(frozen=True)
class PlanNote:
    feature: str
    code: str
    value: float
    detail: str


@dataclass(frozen=True)
class MillOptions:
    n_max: float | None = None
    rest: bool = True
    plunge_ratio: float = 0.3  # 0 < · ≤ 1
    clearance: float = 1.0
    open_margin: float = 1.0
    drill_tol: float = 0.01
    breakthrough: float = 1.0
    peck_limit: float = 3.0
    peck_q: float = 1.0
    hole_d_max: float = 20.0  # SPEC 27 recognize'a geçer
    tol: float = 1e-3  # SPEC 27 recognize'a geçer
    strict: bool = False


@dataclass(frozen=True)
class MillPlan:
    material: str
    features: Features
    setups: tuple[Setup, ...]  # 1 veya 2
    ops: tuple[PlannedOp, ...]
    unplanned: tuple[Unplanned, ...]  # adres, sonra kod sırasıyla
    notes: tuple[PlanNote, ...]  # adres, sonra kod sırasıyla

    def ops_for(self, setup: int) -> list[Toolpath | DrillOp]: ...
    def tool_changes(
        self,
    ) -> int: ...  # bağlama içinde ardışık farklı takım geçişleri + her bağlamanın ilk takımı
    def summary(
        self,
    ) -> list[dict]: ...  # op başına {name, kind, setup, feature, tool_id, n, F, a_p, stepover}
    def gcode(self, lib: ToolLibrary, dialect: Dialect = GRBL, program_no: int = 1) -> list[str]: ...


def plan_mill_features(
    features: Features,
    part_zmin: float,
    stock: Stock,
    lib: ToolLibrary,
    material: str,
    wcs: Wcs | None = None,
    fixtures: Sequence[Stock | CylinderStock] = (),
    wcs2: Wcs | None = None,
    fixtures2: Sequence[Stock | CylinderStock] | None = None,
    options: MillOptions = MillOptions(),
) -> MillPlan: ...  # OCCT'siz çekirdek


def plan_mill(part: Part, stock: Stock, lib: ToolLibrary, material: str, **kw) -> MillPlan: ...


# = plan_mill_features(recognize(part, stock, tol, hole_d_max), part.bbox()[0][2], stock, lib, material, **kw)


# cam/plan_turn.py
@dataclass(frozen=True)
class TurnOptions:
    rpm_max: float  # zorunlu (G50)
    finish_allowance: float = 0.2
    clearance: float = 1.0
    strict: bool = False


@dataclass(frozen=True)
class TurnPlan:
    material: str
    outer: TurnFeatures
    inner: TurnFeatures | None
    setup: Setup
    ops: tuple[PlannedOp, ...]  # setup = 0
    unplanned: tuple[Unplanned, ...]
    notes: tuple[PlanNote, ...]

    def summary(self) -> list[dict]: ...
    def gcode(self, spindle: str, tool_change: tuple[float, float], program_no: int = 1) -> str: ...


def plan_turn(
    outer: Profile,
    stock: CylinderStock,
    lib: ToolLibrary,
    material: str,
    options: TurnOptions,
    inner: Profile | None = None,
    wcs: Wcs | None = None,
    fixtures: Sequence[CylinderStock] = (),
) -> TurnPlan: ...


# cam/plan_verify.py
@dataclass(frozen=True)
class PlanCheck:
    ok: bool
    collisions: tuple[Collision, ...]
    removed_volume: float
    rest_volume: float
    gouge_volume: float
    expected_rest: float  # freze: Σ kose_artigi; torna: 0
    total_time: float  # s, bağlamaların toplamı


def verify_mill(
    plan: MillPlan, part: Part, cell: float = 0.5, machine: Machine | None = None
) -> PlanCheck: ...
def verify_turn(plan: TurnPlan, cell: float = 0.25, machine: Machine | None = None) -> PlanCheck: ...
```
Geçersiz girdi → `CamError`: `material` boş ya da `str` değil; `lib` `ToolLibrary` değil ya da `validate()`'ten
geçmiyor; `stock` türü yanlış (`plan_mill`'de `Stock`, `plan_turn`'de `CylinderStock`); seçeneklerde sonlu olmayan
ya da aralık dışı değer (`n_max ≤ 0`, `rpm_max ≤ 0`, `plunge_ratio ∉ (0, 1]`, `clearance < 0`, `open_margin < 0`,
`drill_tol < 0`, `breakthrough < 0`, `peck_limit ≤ 0`, `peck_q ≤ 0`, `finish_allowance < 0`); `part_zmin` stok
dışında; `strict` ve `unplanned ≠ ()`.

## Kabul kriterleri
Takımlar ve parçalar uydurmadır (Ek A). Sayısal değerler `1e-9` (bağıl) içinde, hacimler `§7` ızgara sınırıyla.
Freze: kütüphane `LIB` (Ek A), malzeme `"al"`.
- [ ] K1 **Yüz alma ve kesme verisi**: `Features(faces=(FaceFeature(z=20, depth=2, E),))`, stok
  `[−2, 102]×[−2, 62]×[0, 22]` → tek op `yuz_alma`, takım T1 (Ø16, en büyük), `Cut.z_top = 22`, `z_bottom = 20`,
  `rpm`/`F` = `cam.cutting.milling(T1, "al")` ile birebir, `stepover = min(ae, 8)`, `plunge_feed = 0.3·F`;
  `n_max = 5000` → `rpm = 5000`. (`test_plan.py::test_yuz_alma`)
- [ ] K2 **Cep, kalan malzeme**: 40×30 cep, `r_corner = 5`, `[12, 20]` → `rest=True`: `cep` T1 (Ø16) +
  `cep_kalan` T2 (Ø10, `D₂ ≥ D₁/2` → kontur, dış halka `side="ic"`); `rest=False`: tek `cep` T2; not yok.
  (`::test_cep_kalan_malzeme`)
- [ ] K3 **Keskin köşe artığı**: 16×12 keskin köşeli cep `[8, 12]` → `cep` T2 (Ø10, en büyük sığan: T1 sığmaz),
  `cep_kalan` T3 (Ø6: köşeye sığan yok, `D < 10` olanların kesici boyu yetenlerin en küçüğü; T4'ün 12 mm kesici
  boyu `22 − 8 = 14`'e yetmez; `D₃ ≥ D₂/2` → kontur), not `kose_artigi`, `value = 4·3²·(1 − π/4)·4`. Aynı cep
  stok üstü `z = 20` iken (`20 − 8 = 12 ≤ 12`) `cep_kalan` T4 (Ø4, `D₄ < D₂/2` → tam cep), `value = 4·2²·(1 − π/4)·4`.
  (`::test_keskin_kose`)
- [ ] K4 **Süzgeçler ve gerekçe**: `ap`/`ae`'siz takım aday değil; hiç aday yoksa `kesme_verisi_yok`; 3 mm
  genişlik cepte `takim_sigmiyor`; derin (stok üstünden 40 mm) cepte `kesici_boy_yetmez`; `strict=True` →
  `CamError`, mesajda adres ve kod. (`::test_suzgecler`)
- [ ] K5 **Açık bölge**: basamak `OpenFeature` (zarf 100×60, ada `[0, 100]×[10, 60]`, `[15, 20]`) → `acik_bolge`
  `pocket(Ω)`, `Ω.outer` = zarfın `r_T + 1` dışa ofseti (yuvarlak köşeli dikdörtgen, köşe yarıçapı `r_T + 1`),
  ada aynen. (`::test_acik_bolge`)
- [ ] K6 **Delikler**: kayıtlı Ø8 boydan (`depth = 20`, stok altı `−3` → `b = 1`, `G81`), Ø4 × 15 kör (`15/4 > 3`
  → `G83`, `q = 4`), stok altı `0` iken boydan Ø8 → `b = 0`, not `delik_tasma_kisildi`; lambalı Ø6.6 / Ø11 × 6.4
  → `delik` + `lamba` (dairesel cep, `[z_e − 6.4, z_e]`); havşalı → `delik` + `havsa_takimi_yok`; M8 dişli →
  Ø6.8 `delik` + `kilavuz_cevrimi_yok`; eğimli → `ustten_erisilemez`; Ø5 (kütüphanede yok) → `takim_yok`.
  Aynı gruptaki 4 delik en yakın komşu sırasıyla (elle hesaplanmış sıra). (`::test_delikler`)
- [ ] K7 **Yan paso kısma**: `ae = 0.7·D` → `s = D/2`, not `yan_paso_kisildi`. (`::test_yan_paso`)
- [ ] K8 **Sıra**: yüz alma + cep `[12, 20]` + iç cep `[8, 12]` + açık bölge `[15, 20]` + delikler → sıra
  `yuz_alma, acik_bolge, cep, cep_kalan, cep, cep_kalan, delik…, lamba`; her alan op'unun `z_t`'si bir öncekininkinden
  büyük değil; `tool_changes()` elle sayılan değer; `name` biçimi. (`::test_sira`)
- [ ] K9 **İkinci bağlama**: stok `zmin = −3`, parça `zmin = 0`, stok `[−2, 102]×[−2, 62]×[−3, 22]` →
  `setups[1]` var (`G55`), tek op `yuz_alma`, `z_bottom = 2·9.5 − 0 = 19`, `z_top = 22`; not `ikinci_baglama`,
  `value = 3`. (`::test_ikinci_baglama`)
- [ ] K10 **Bağlama çarpışması**: stok kenarına bitişik, üstü `z = 15` mengene çenesi + `[15, 20]` dış kontur açık
  bölgesi → `baglama_carpismasi` (op plandan çıkmış, `detail` SPEC 14 mesajı); çene `z = 14`'te → planlanır.
  (`::test_baglama_carpismasi`)
- [ ] K11 **G-code ve determinizm**: `plan.gcode(LIB, GRBL)` = `write(plan.ops_for(0), GRBL, setup = setups[0],
  length_offsets = length_offsets(LIB, ids, ref_id = ilk))` birebir; Fanuc'ta `length_offsets = None`; iki bağlamada
  iki program (`program_no` 1, 2). Aynı girdiyle iki plan → `summary()` ve her `op.to_dict()` aynı; kütüphane takım
  sırası karıştırılınca plan aynı; girdiler değişmemiş. (`::test_gcode_ve_determinizm`)
- [ ] K12 **Uçtan uca freze** (`@occt`, gerekirse `@slow`): 100×60×20 blok + K2 cebi (`r = 5`) + iç cep 16×12 × 4 +
  2 adet Ø8 boydan, stok `[−2, 102]×[−2, 62]×[−3, 22]`, bağlama elemanı yok → `plan_mill` → `verify_mill(cell =
  0.25)`: `ok`, `gouge_volume = 0`, `|rest_volume − expected_rest| ≤ P·Δ·H`; `removed_volume =
  V_stok − V_parça − expected_rest` (`≤ P·Δ·H` farkla, `P` tüm işlenen sınırların çevresi).
  (`test_plan_part.py::test_uctan_uca`)
- [ ] K13 **Torna planı**: SPEC 27 K10 profili, `CylinderStock(D = 32, zmin = −10, zmax = 62)`, torna kütüphanesi
  (Ek A), `rpm_max = 3000` → sıra `alin` (T21, `z_face = 60`), `dis_kaba` (T21, `nose_r = 0.8`, `allowance = 0.2`,
  profil `tf.rough`), `dis_finis` (T22, `nose_r = 0.4`, profil `tf.rough`), `kanal` (T23, `width = 3 ≤ 6`,
  `Groove(34, 40, 10, 8)`); hepsinde `css = Vc`, `rpm = 3000`, `feed = fn`. İç profil + dolu stok → `on_delik_yok`;
  boru stok (`d = 10`) → `ic_kaba`, `ic_finis` (T24 `BORE`); V kanallı profil → `genel_girinti`; kanal 2 mm
  (takım 3 mm) → `takim_yok`. `gcode(spindle="M3", tool_change=(50, 80))` = `write_lathe(...)` birebir.
  (`test_plan_turn.py::test_torna_plani`)
- [ ] K14 **Torna doğrulaması**: K13 planı → `verify_turn(cell = 0.1)`: `ok`, `gouge_volume = 0`, `rest_volume`
  ≤ burun artıklarının üst sınırı (son takımın her iç köşesinde Pappus: `2π·(x_k + r)·r²(1 − π/4)`, `x_k` köşenin
  yarıçapı, `r` burun yarıçapı) + SPEC 22 ızgara sınırı. (`test_plan_turn.py::test_torna_dogrulama`)
- [ ] K15 **Hatalar**: §Arayüz sonundaki her geçersiz girdi → `CamError`. (`test_plan.py::test_hatalar`,
  `test_plan_turn.py::test_hatalar`)
- [ ] Tüm testler yeşil, `ruff check .` ve `ruff format --check .` temiz, bu SPEC'in testlerinde 0 "uygulanmamış"

## Kapsam dışı
- 3B yüzey işleme planı (SPEC 06 / 06b `rough`/`finish`/`waterline` seçimi, 3B kalan malzeme): SPEC 27 eğik ve
  serbest yüzeyi tanımaz; ayrı SPEC (ör. "3B işlem planı": ağdan bölge, takım ve yön seçimi).
- Kılavuz çekme (`G84`), havşa / pah takımı, punta (merkez) matkabı, helisel / rampalı dalma (SPEC 03c): `ToolKind`
  ve SPEC 04 genişleyince ek. `ToolKind` eki arayüz PR'ı ister.
- Yan / alt yüzlerden erişilen özellikler, 3+2 ve çok eksen (SPEC 41–44); bağlama 2'de alt yüz alma dışında işlem.
- Takım değişimini azaltmak için öncelik koruyan yeniden sıralama; takım yolu süresine göre en iyileme; takım ömrü,
  kesme kuvveti / güç, tezgâh kursu (SPEC 30 `check_machine` Tezgah'ta ayrıca çağrılır).
- Tornada delme / punta, ters bağlama, diş (profilde dış diş kaydı yok), `Recess` için profilli kanal.
- Otomatik bağlama elemanı (mengene, ayna) yerleşimi: kullanıcı verir.
- Bağlama 2'de iş sıfırının tezgâhta bulunması (SPEC 14 `wcs_from_touch` kullanıcı akışı).

## Ek A — Uydurma test takımları
Freze (`material = "al"`; `CuttingData(Vc, fz, ap, ae)`):
| id | ad | tür | D | flute_length | flutes | kesme verisi "al" |
|---|---|---|---|---|---|---|
| 1 | `freze16` | FLAT | 16 | 30 | 3 | `Vc=300, fz=0.08, ap=4, ae=6` |
| 2 | `freze10` | FLAT | 10 | 25 | 3 | `Vc=250, fz=0.05, ap=3, ae=4` |
| 3 | `freze6` | FLAT | 6 | 18 | 3 | `Vc=200, fz=0.04, ap=2, ae=2.5` |
| 4 | `freze4` | FLAT | 4 | 12 | 2 | `Vc=150, fz=0.03, ap=1, ae=1.5` |
| 5 | `freze3-veri-yok` | FLAT | 3 | 8 | 2 | `Vc=120, fz=0.02` (`ap`, `ae` yok → aday değil) |
| 11 | `matkap8` | DRILL | 8 | 40 | 2 | `Vc=80, fz=0.1` |
| 12 | `matkap6.6` | DRILL | 6.6 | 35 | 2 | `Vc=80, fz=0.08` |
| 13 | `matkap6.8` | DRILL | 6.8 | 35 | 2 | `Vc=80, fz=0.08` |
| 14 | `matkap4` | DRILL | 4 | 25 | 2 | `Vc=70, fz=0.05` |

Torna (`material = "al"`; `CuttingData(Vc, fn, ap)`):
| id | ad | tür | nose_r | tip | κr / εr | width | kesme verisi "al" |
|---|---|---|---|---|---|---|---|
| 21 | `dis-kaba` | TURN | 0.8 | 3 | 93 / 80 | — | `Vc=250, fn=0.25, ap=2` |
| 22 | `dis-finis` | TURN | 0.4 | 3 | 93 / 55 | — | `Vc=300, fn=0.1` |
| 23 | `kanal3` | GROOVE | 0.2 | 3 | 90 / 90 | 3 | `Vc=150, fn=0.05` |
| 24 | `ic-kaba` | BORE | 0.4 | 2 | 95 / 80 | — | `Vc=200, fn=0.15, ap=1` |

Uç numaraları ve açılar SPEC 20 / 22 doğrulamasından geçmezse testi yazan oturum değerleri SPEC 20 kurallarına
uygun en yakın değerle değiştirir ve durum dosyasına yazar (beklenen sonuçlar takım kimliğine bağlıdır, açıya değil).
