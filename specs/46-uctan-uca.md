# SPEC 46 — Uçtan uca altın senaryo: flanş + mil, modelden G-code'a ve montaja

> **Durum: ONAYLANDI** (kullanıcı, 2026-10-18 11:14 UTC proje sohbeti: "beni bekleyen bir şey varsa 2 dk'dan fazla
> geçerse öneriyi kabul et"; koordinatörün 11:16 onay sorusu yanıtsız kaldı → önerilen varsayılanlarla onaylı).
> Açık soruların yanıtı (öneriler): gelecek halkaların testleri SPEC birleşince yazılır; mil düz Ø20 + pah;
> 31 ve 41–44 zincir dışı (ek SPEC 46b).
> Testler yazılırken düzeltilen iki tutarsızlık (SPEC 14 / 20 ile uyum, kapsam değişmedi): K3 delme dibi `z = 0`
> (SPEC 14 stok altına inmeyi yasaklar); K7 hayali uç yerine burun merkezi ölçütü (alında hayali uç eksenin
> `−r` ötesine iner, pahta `x < 9` olur; doğru ölçü burun dairesinin parçaya girmemesidir).
> Dalga 5, hat H17 (`/mnt/project-files/yol-haritasi/dalga-5-onerisi.md`). Kullanıcı Dalga 5'i 2026-10-18 10:51 UTC'de
> tam kapsamla seçti.

## Amaç
"Tasarımdan tezgâha" iddiasını tek bir test zinciriyle sınamak: uydurma bir **flanş** ve **mil** modellenir, ham
malzemeye bağlanır, takım yolları kurulur, talaş simülasyonuyla doğrulanır, G-code'a yazılır, G-code bağımsız bir
yorumlayıcıda (ve kuruluysa LinuxCNC `rs274`'te) yeniden yürütülür, iki parça montajda birleştirilir ve girişimi
denetlenir. Zincir **yeni uygulama kodu içermez**: yalnız `main`'deki genel (herkese açık) işlevleri zincirler.
Her SPEC `main`'e birleştikçe zincire bir **halka** eklenir; tüm halkalar `main`'de yeşil olunca Dalga 5 biter.

## Bağımlılıklar
Zincir mevcut SPEC'lerin genel işlevlerini kullanır; hiçbirinin imzasını değiştirmez. Halka tablosu (Teori §2)
hangi halkanın hangi SPEC'e bağlı olduğunu ve bugün `main`'de olup olmadığını verir.
- **Arayüz değişikliği gerekmez.** `*/model.py`, `pyproject.toml`, ortak dosyalar değişmez.
- Zincirde bir SPEC'in hatası bulunursa bu SPEC'in testi düzeltilmez ve uygulama kodu bu SPEC'te düzeltilmez:
  bulgu (başarısız test + beklenen / bulunan değer) koordinatöre bildirilir, düzeltme ilgili SPEC'in sahibine gider.
  Bekleyen düzeltme süresince ilgili test `pytest.mark.xfail(strict=True, reason="SPEC NN hata: …")` ile işaretlenir
  (düzeltme birleşince strict xfail kırmızıya döner ve işaret kaldırılır; tests/reference K1–K3 düzeni).

## Teori

### 1. Senaryo (uydurma geometri, N–mm–MPa)
**Malzeme:** `"Al"` (uydurma kesme verisi; gerçek katalog değeri değildir).

**Flanş** (freze, SPEC 02 / 23 işlevleriyle):
`flans = block(80, 80, 12)` → `hole(flans, 40, 40, 20)` (merkez delik Ø20, boydan) → dört köşe deliği
`hole(flans, x, y, 6.6)`, `(x, y) ∈ {(12, 12), (68, 12), (12, 68), (68, 68)}` (boydan).
Hacim `V_f = 80·80·12 − π·10²·12 − 4·π·3.3²·12`.

**Mil** (torna): `mil = chamfer_top(cylinder(10, 60), 1)` → Ø20 × 60, üst ucu 1 × 45° pah.
Hacim `V_m = π·10²·60 − V_pah`, `V_pah = π·c²·(r − c/3)`, `r = 10`, `c = 1` (dik kenarları `c` olan üçgen
kesitin dönmesi, Pappus: alan `c²/2`, ağırlık merkezi yarıçapı `r − c/3`).

**Ham malzemeler:**
- Flanş: `Stock` `x ∈ [0, 80]`, `y ∈ [0, 80]`, `z ∈ [0, 15]` (üstten 3 mm alın payı).
- Mil: `CylinderStock(D = 24, zmin = −5, zmax = 61)` (`z < 0` ayna içinde, alın payı 1 mm).

**Takım kütüphanesi** (`ToolLibrary`, test içinde kurulur, `Al` kesme verisiyle):
| id | Tür | Ölçü | Kullanım |
|---|---|---|---|
| 1 | `FLAT` | D 16, kesici boy 30 | alın |
| 2 | `FLAT` | D 10, kesici boy 25 | merkez delik (dairesel cep, boydan) |
| 3 | `DRILL` | D 6.6, kesici boy 30 | köşe delikleri (`DrillOp`, dip `z = 0`: SPEC 14 stok altına inilmez) |
| 11 | dış torna kalemi (`LatheTool`) | uç radyusu 0.4 | alın, kaba, finiş |

**Elle işlem listesi** (SPEC 29 yokken zincirin kaynağı): flanş için `ops2d.face` (T1, `z 15 → 12`),
`ops2d.pocket` (T2, Ø20 daire bölge, `z 12 → 0`), `DrillOp` (T3, dört delik, dip `z = 0`); mil için
`lathe_ops.face` (`z 61 → 60`), `lathe_ops.rough` (pay 0.2) + `lathe_ops.finish` alından sonraki çubukta
(`zmax = 60`; SPEC 20: profil ön yüzden başlar), profil `(z, x)`: `(60, 9) → (59, 10) → (0, 10) → (0, 12)`, dış.
Devir ve ilerleme `cam.cutting.milling` / `cam.cutting.css` ile kütüphaneden alınır (sabit sayı yazılmaz).

**Montaj:** kök düğüm altında `flans` (sabit) ve `mil`. Kısıtlar: `CONCENTRIC` (flanş merkez delik ekseni
`(40, 40, 0)`, `+Z` ↔ mil ekseni `(0, 0, 0)`, `+Z`) ve `COINCIDENT` (flanş alt düzlemi `z = 0` ↔ mil alt düzlemi
`z = 0`). Mil keyfi bir başlangıç konumundan (öteleme + küçük dönme) başlatılır.
Beklenen: mil dünyada `(40, 40, 0)`'a oturur; serbestlik derecesi 1 (eksen etrafında dönme).

### 2. Halkalar
Her halka bir test dosyasıdır (`tests/uctan_uca/test_hNN_*.py`) ve önceki halkaların **fikstürlerini** kullanır
(`tests/uctan_uca/conftest.py`). Halkalar zincir sırasına göre numaralı, ama bağımsız çalışır: bir halkanın
SPEC'i `main`'de değilse yalnız o halka (ve ona bağlı halkalar) atlanır.

| Halka | Ne zincirlenir | SPEC | Bugün `main`'de |
|---|---|---|---|
| H1 Model | flanş ve mil, hacim / sınır kutusu / `Part.holes` | 02, 23 | evet |
| H2 Kurulum ve takım | `Setup`, `check_setup`, kütüphane JSON gidiş-dönüşü, `milling` / `css` | 14 | evet |
| H3 Freze yolları | elle işlem listesi (flanş) | 03, 04 (`DrillOp`) | evet |
| H4 Freze simülasyonu | z-map simülasyonu, çakma / çarpışma, kaldırılan hacim | 05 | evet |
| H5 Freze G-code | GRBL + Fanuc yazımı, okuma, bağımsız yorumlayıcı, güvenlik, `rs274` | 04, `tests/reference` | evet |
| H6 Montaj | ağaç, kısıtlar, çözüm, dünya konumu | 07, 08 | evet |
| H7 Torna yolları | elle işlem listesi (mil) | 20 | evet |
| H8 Girişim | flanş–mil temas, kaydırılmış milde girişim hacmi | 09 | hayır |
| H9 Torna G-code | Fanuc torna yazımı / okuma gidiş-dönüşü | 21 | hayır |
| H10 Torna simülasyonu | dönel harita, kaldırılan hacim (Pappus), ayna çarpışması yok | 22 | hayır |
| H11 Eskizden model | flanşı eskiz + ekstrüzyonla kurmak, H1 ile eşdeğerlik | 17, 26 | hayır |
| H12 Özellik tanıma | flanştan alın / delik özellikleri | 27 | hayır |
| H13 Torna profili | `turn_profile(mil)` = H7'nin elle profili | 28 | hayır |
| H14 Otomatik plan | `plan_mill(flans, …)`, `plan_turn(…)`, `verify_*`; plan çıktısı H4 / H5 / H9 / H10 denetimlerinden geçer | 29 | hayır |
| H15 Tezgâh profili | `post(ops, machine, setup)`; kurs dışı program `CamError` | 30 | hayır |

Kapsam dışı halkalar (bu SPEC'te yok): 31 (Sinumerik / Heidenhain), 41–44 (çok eksen), Tezgah ekranları (24–26'nın
web kısmı). Bunlar ayrı bir ek SPEC'le (46b) eklenebilir.

### 3. Atlama kuralı (SPEC `main`'e girene kadar)
- Halka testleri, bağlı olduğu SPEC `main`'e **birleştikten sonra** yazılır (koordinatör birleşmeyi bildirir);
  onaylanmamış / birleşmemiş imzalara karşı önceden test yazılmaz.
- Buna rağmen her halka dosyası, bağımlılığını modül düzeyinde ister:
  `conftest.halka(spec, modul, *adlar)` → `pytest.importorskip(modul, reason=f"SPEC {spec} main'de değil")` ve
  her ad için `hasattr`; eksikse aynı gerekçeyle `pytest.skip(..., allow_module_level=True)`. Böylece zincir,
  halkalar ters sırayla birleşse de (ör. 21, 29'dan önce) ya da eski bir dalda koşturulsa da kırılmaz.
- Atlama **yalnız** "modül / ad yok" durumunda olur. Modül var ama işlev `NotImplementedError` fırlatıyorsa test
  atlanmaz: yerelde "uygulanmamış", CI'da (`--uygulanmamis-hata`) kırmızıdır.
- OCCT gerektiren halkalar `@pytest.mark.occt` taşır (H1, H4, H6'nın parça kısmı, H8, H11, H12, H13, H14 freze);
  OCCT'siz halkalar (H3'ün yol kısmı, H7, H9, H10) OCCT olmadan da koşar.
- Kaynak seçimi: H4 / H5, SPEC 29 yokken H3'ün elle işlemlerini, varken **ikisini de** (elle + plan) denetler.
  Elle zincir H14'ten sonra da kalır (regresyon tabanı).
- 10 saniyeden uzun halka testleri `@pytest.mark.slow` ile işaretlenir.

### 4. Doğrulama ölçüleri
- **Kaldırılan hacim (freze, z-map).** Beklenen `ΔV₀ = V_stok − V_f`. Hücre adımı `h` olan z-haritasında yalnız
  dikey duvarları kesen hücreler hatalıdır; sınır `|ΔV − ΔV₀| ≤ 2·h·Σ(çevre_i · yükseklik_i)`
  (duvarlar: Ø20 delik, dört Ø6.6 delik, yükseklik 12; dış kenar stok kenarıyla çakışık olduğu için duvar değil).
- **Kaldırılan hacim (torna).** İşlenen bölge `z ∈ [0, 61]`: `ΔV₀ = π·12²·61 − V_m` (`z < 0` aynada, işlenmez);
  dönel haritada sınır SPEC 22'nin kendi hücre ölçütüyle (SPEC 22 Teori) verilir.
- **Girişim hacmi** (H8, mil `x` yönünde `e = 1` kaydırılmış): mil diski ile delik diski (eşit `r = 10`)
  arasındaki fark alanı `A = π r² − (2r²·acos(e / 2r) − (e/2)·√(4r² − e²))`, hacim `A · 12`.
- **G-code eşdeğerliği:** `tests/reference/gcode_ref` ile yürütülen hareketler = model hareketleri
  (`gcode_check.compare` boş), `gcode_check.safety` boş; `read(write(ops))` simülasyonu doğrudan simülasyonla aynı
  z-haritasını verir (`|Δz| ≤ 10^(−decimals)`).

## Dosyalar
- Yeni: `tests/uctan_uca/__init__.py`, `tests/uctan_uca/conftest.py` (senaryo fikstürleri, `halka()`),
  `tests/uctan_uca/test_h01_model.py` … `test_h15_post.py` (halka başına bir dosya, birleşmeler oldukça).
- Yeni: `durum/46-uctan-uca.md`.
- Okunur (değişmez): `tests/reference/gcode_ref.py`, `tests/reference/gcode_check.py`.
- Dokunulmayacak: tüm uygulama kodu (`geometry/`, `cam/`, `assy/`, `sketch/`, `core/`, `tezgah/`, `fileio/`, `viz/`),
  `*/model.py`, `pyproject.toml`, `DURUM.md`, `docs/yol-haritasi.md`, başka SPEC'lerin testleri.

## Arayüz
Yeni genel işlev yok. Test yardımcıları (yalnız `tests/uctan_uca/conftest.py` içinde):
```python
def halka(spec: str, modul: str, *adlar: str) -> ModuleType: ...  # yoksa modül düzeyinde skip

# fikstürler (scope="session")
flans() -> Part; mil() -> Part
flans_stok() -> Stock; mil_stok() -> CylinderStock
kutuphane() -> ToolLibrary
freze_ops() -> list[Toolpath | DrillOp]      # H3 elle
torna_ops() -> list[Toolpath]                # H7 elle
montaj() -> Node                             # H6 çözülmüş ağaç
```

## Kabul kriterleri
Bugün `main`'de olan halkalar (bu PR'da yazılır, yeşil olmalı):
- [ ] **K1 Model (H1):** `flans.volume`, `mil.volume` Teori §1 formülleriyle `rel 1e-6`; sınır kutuları
  `[0,80]×[0,80]×[0,12]` ve `[−10,10]²×[0,60]`; `flans.holes` beş kayıt (Ø20 + 4 × Ø6.6, hepsi `through`).
  (`tests/uctan_uca/test_h01_model.py`)
- [ ] **K2 Kurulum (H2):** kütüphane `save_library` / `load_library` sonrası eşit; `check_tools(lib, ops)` ve
  `check_setup(setup, freze_ops)` hata vermez; işlemlerin devri ve ilerlemesi `milling(tool, "Al")` ile aynı.
  (`test_h02_kurulum.py`)
- [ ] **K3 Freze yolları (H3):** alın yolunun kesme hareketleri `z = 12`'ye iner, altına inmez; cep yolu Ø20 dairenin
  `r − D/2 = 5` içinde kalır, en derin kesme `z = 0`; dört delik `DrillOp` ile delik merkezlerinde, dip `z = 0`.
  (`test_h03_freze_yol.py`)
- [ ] **K4 Freze simülasyonu (H4):** `simulate(freze_ops, stok, cell = 0.5, part_z = part_zmap(flans, …))`:
  `collisions == []` (çarpışma ve çakma yok), kaldırılan hacim §4 sınırı içinde. (`test_h04_freze_sim.py`)
- [ ] **K5 Freze G-code (H5):** GRBL ve Fanuc için `compare(expected(ops), gcode_ref(write(ops, d))) == []` ve
  `safety(...) == []`; `read(write(ops, d))` ile simülasyon K4'le aynı z-haritası; `rs274` kuruluysa aynı
  karşılaştırma onunla da (yoksa atlanır; CI kapsayıcısında kuruludur, PR #47). (`test_h05_freze_gcode.py`)
- [ ] **K6 Montaj (H6):** `flatten` + `solve` yakınsar (artık `≤ 1e-10`), `dof == 1`; `world(kök, "mil")`
  ötelemesi `(40, 40, 0)` `abs 1e-9`, mil ekseni `+Z`; `apply` sonrası ağaç `validate`'ten geçer.
  (`test_h06_montaj.py`)
- [ ] **K7 Torna yolları (H7):** alın yolu `z = 60`'a iner; finiş yolunun Ø20 bölümünde hayali uç `x = 10`
  (`abs 1e-6`); alın, kaba ve finiş kesme hareketlerinde burun merkezinin (`C = P − q_T`) parça yarı kesitine
  uzaklığı `≥ r + δ` (kaba `δ = 0.2`, diğerleri `0`), finişte en küçük uzaklık tam `r` (profile değer).
  (`test_h07_torna_yol.py`)

Bağlı SPEC birleşince yazılacak halkalar (o zamana dek §3 kuralıyla atlanır):
- [ ] **K8 Girişim (H8, SPEC 09):** `check(montaj, parts)` → yalnız `flans`–`mil` için `TEMAS`, `GIRISIM` yok;
  mil `e = 1` kaydırılınca tek `GIRISIM`, hacim §4 formülüyle `rel 1e-3`.
- [ ] **K9 Torna G-code (H9, SPEC 21):** `read_lathe(write_lathe(torna_ops, "M3", (50, 50)), tools)` hareketleri
  `torna_ops`'la yazılan basamakta eşit.
- [ ] **K10 Torna simülasyonu (H10, SPEC 22):** `simulate_lathe(torna_ops, mil_stok)`: çarpışma yok, kaldırılan
  hacim §4 (Pappus) sınırında; `read_lathe(write_lathe(…))` ile aynı sonuç.
- [ ] **K11 Eskizden model (H11, SPEC 17 + 26):** flanş eskiz (80 × 80 kare, Ø20 ve 4 × Ø6.6 daire, kısıtlı) +
  ekstrüzyonla kurulur; hacim ve sınır kutusu H1 flanşıyla `rel 1e-6`, simetrik farkın hacmi `≤ 1e-6·V_f`.
- [ ] **K12 Özellik tanıma (H12, SPEC 27):** `recognize(flans, …)` bir alın özelliği (`z = 12`) ve Ø20 + 4 × Ø6.6
  delik / cep özelliği verir; tanınmayan özellik yok.
- [ ] **K13 Torna profili (H13, SPEC 28):** `turn_profile(mil).outer` H7'deki elle profile `tol` içinde eşit
  (iki doğru: pah 45° ve Ø20 silindir).
- [ ] **K14 Otomatik plan (H14, SPEC 29):** `plan_mill(flans, flans_stok, kutuphane, "Al")` ve
  `plan_turn(...)`: `unplanned == []`; `verify_mill` / `verify_turn` geçer; plan işlemleri K4, K5, K9, K10'un
  aynı denetimlerinden geçer.
- [ ] **K15 Tezgâh profili (H15, SPEC 30):** `post(freze_ops, profil, setup)` hata vermez ve K5 karşılaştırmasından
  geçer; stok tezgâh kursunun dışına taşınınca `CamError`.

Genel:
- [ ] **K16 Kod yok:** bu SPEC'in PR'ları yalnız `tests/uctan_uca/`, `specs/46-uctan-uca.md`,
  `durum/46-uctan-uca.md` değiştirir (bağımsızlık kapısı ve `git diff --stat` ile görülür).
- [ ] **K17 Atlama dürüstlüğü:** `pytest tests/uctan_uca -rs` çıktısında her atlama gerekçesi "SPEC NN main'de
  değil" veya "OCCT yok" / "rs274 kurulu değil"dir; başka atlama yoktur.
- [ ] **K18 Bitiş:** H1–H15'in hepsi `main`'de etkin ve yeşil → Dalga 5 biter (DURUM sahibi thread'e bildirilir).

## Kapsam dışı
- Yeni uygulama kodu, uygulama hatası düzeltme (bulgu koordinatöre gider).
- Gerçek şirket parçası veya kesme verisi; senaryo uydurmadır.
- 31, 41–44, Tezgah web ekranları (bkz. §2), FEM analizi (12 / 13) bu zincirde yok.
- Performans ölçümü (süre yalnız `slow` işareti için).
