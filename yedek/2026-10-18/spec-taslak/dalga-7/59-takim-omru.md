# SPEC 59 — Takım ömrü: Taylor, birikimli aşınma (Palmgren–Miner) ve planlı takım değişimi

> **Durum: ONAYLI** (kullanıcı, 2026-10-18 16:06: "Dalga 7 taslakları 57, 58, 59, 61, 62, 63, 64 ve 72'yi önerileriyle onaylıyorum."; açık sorular önerilen yanıtlarla kapatıldı, bkz. Kararlar) (Dalga 7, hat A3; `yol-haritasi/dalga-6-ve-sonrasi.md` bölüm 4).
> Bağımlılık (kod): **B2** (`malzeme/model.py`: `Malzeme.taylor`, `Taylor.omur`, `TAKIM_MALZEMELERI`; taslak),
> SPEC 66 (malzeme kütüphanesi; taslak), SPEC 05 (`SimResult.steps[*].duration`, `removed`; `main`'de), SPEC 22 / 40
> (torna simülasyonu ve süre, `cam/sim/lathe_time.py`; `main`'de), SPEC 32 (`cam/kuvvet.py` `Load.kind`; `main`'de),
> SPEC 14 (`cam/cutting.py` `effective_diameter`; `main`'de). Çıktıyı okuyanlar: SPEC 38 (iş föyü), SPEC 58 (süre, maliyet
> ve teklif; başka thread'in), SPEC 29 / 57 (plan).
> Hedef tezgâhlar: DMG MORI DMU 50 / 60 / 75 / 90, DMF 360, NHC 5000 (freze); NLX 2500 / 700, NTX 3000 (torna ve torna-freze).

## Amaç
Bir programın (bir veya birçok parça) her takımı ne kadar aşındırdığını hesaplamak ve kesici kenar ömrü dolmadan
**planlı takım değişimi** önermek. Hesap malzeme kaydındaki Taylor sabitlerinden gelir (`Vc · T^n = C`). Kesme hızı
hareket boyunca değişebildiği için (tornada G97 sabit devirde çap küçüldükçe, G96'da devir sınırına girince, frezede
etkin çap değişince) aşınma Palmgren–Miner kuralıyla toplanır. Sonuç iş föyüne (38) "T3: 4 parçada bir değiştir" satırı
olarak, maliyete (58) takım başına kenar sayısı olarak gider. Ölçülmemiş veri uydurulmaz: Taylor kaydı yoksa hesap
`ModelError` verir.

## Teori

### Taylor
Malzeme kaydı (B2) takım malzemesi başına `Taylor(C, n)` tutar: `Vc · T^n = C`, `Vc` m/dk, `T` dk.
```
T(Vc) = (C / Vc)^(1/n)          m = 1/n  (n ∈ (0, 1) → m > 1)
```
Örnek (testlerde): `C = 300`, `n = 0.25` → `T(150) = 16.0` dk, `T(200) = 5.0625` dk, `T(300) = 1.0` dk.

### Birikimli aşınma (Palmgren–Miner)
Kesme hızı zamanla değişiyorsa kenarın tükenen ömür oranı
```
D = ∫ dt / T(Vc(t)) = Σ_i ∫_adım i  (Vc(t) / C)^m dt
```
Sabit `Vc`'de `D = t / T`. `D = 1` kenar ömrünün bittiği andır. Yalnız **kesme** zamanı sayılır: SPEC 32 `Load.kind ==
"kesme"` olan adımlar (G0, hava kesmesi ve `"atlandi"` adımları 0 katkı verir). Takım değiştirme sınırı `D_lim`
(varsayılan **0.8**, güvenlik payı) ile karşılaştırılır.

İki hızlı örnek: `150 m/dk`'da 4 dk + `300 m/dk`'da 0.5 dk → `D = 4/16 + 0.5/1 = 0.75`.

### Freze: adım başına kesme hızı
`Vc = π · D_eff · n / 1000`. `D_eff`, SPEC 14 `effective_diameter(tool, ap)` (köşe radyüslü / küresel uçta kesme
derinliğine bağlı). `ap` SPEC 32 `Load.ap`'den gelir. Adımda `Vc` sabit sayılır: `D_i = duration_i / T(Vc_i)`.
`duration` SPEC 05 `SimStep.duration` [s] / 60 → dk.
Örnek: `D = 10` düz uç, `n = 4774.65` dev/dk → `Vc = 150`; 3 dk kesme → `D = 3/16 = 0.1875`.

### Torna: çapla değişen kesme hızı
Takım ucunun yarıçapı `r = |x|` (SPEC 21 yarıçap koordinatı). Devir:
- **G97 / G95 sabit devir `N`**: `Vc(r) = 2π r N / 1000`, `dt = ds / (f N)` (`f` mm/dev).
- **G96 sabit kesme hızı `Vc₀`, devir sınırı `N_max`**: `r ≥ r* = 1000 Vc₀ / (2π N_max)` iken `Vc = Vc₀`,
  `n(r) = 1000 Vc₀/(2π r)`; `r < r*` iken `n = N_max`, `Vc(r) = 2π r N_max / 1000`. SPEC 22 `lathe_time.py` ile aynı ayrım.

Alın tornalama (G97, `r: R₀ → 0`, `ds = dr`) kapalı form:
```
D = (2π N / (1000 C))^m · R₀^(m+1) / ((m + 1) · f · N)
```
Örnek: `N = 500`, `f = 0.2`, `R₀ = 50`, `C = 300`, `n = 0.25` → kesme süresi 0.5 dk, `D = 0.0075161336` (sayısal
integralle doğrulandı).
G96 alın tornalama (`Vc₀ = 150`, `N_max = 2000`, `f = 0.2`, `R₀ = 50`): `r* = 11.936621` mm;
```
D₁ = [2π (R₀² − r*²) / (2 · 1000 Vc₀ f)] / T(Vc₀) = 0.24687861 / 16 = 0.01542991
D₂ = (2π N_max / (1000 C))^m · r*^(m+1) / ((m + 1) f N_max) = 0.00037302
D  = 0.01580293
```
**Sayısal yöntem:** her doğrusal adım `r = r*` ve `x = 0` noktalarında bölünür, her parçada 8 noktalı Gauss–Legendre
ile `∫ (Vc/C)^m dt` alınır. Tam sayı `m`'de parçalar polinomdur ve sonuç kapalı formla kesindir (≤ 1e-12 göreli);
tam sayı olmayan `m`'de hata adım bölme ile `rtol` altına indirilir (varsayılan `1e-6`, gerekirse ikiye bölme). Yaylar
SPEC 22'deki gibi açı parametresiyle aynı noktalarda bölünür.

### Planlı takım değişimi ve kardeş takım
Program `parts` kez tekrarlanırsa (seri üretim) takım başına parça başı aşınma `D_parça`. Bir kenarla işlenebilecek
parça sayısı `k = floor(D_lim / D_parça)`. `k = 0` (tek parça bile `D_lim`'i aşıyor) ise program içinde, `D`'nin
`D_lim`'e ulaştığı **hareketten önceki ilk güvenli noktada** (işlem sınırı: aynı takımla iki op arası; yoksa o op'un
başı) takım değişimi önerilir. Öneri iki türdür:
- `"kenar"`: aynı takım, yeni kesici kenar (değiştirilebilir uçta uç çevirme); program değişmez, operatöre not.
- `"kardes"`: kütüphanede aynı geometri ve kesme verisine sahip başka takım (aynı `kind`, `D`, `corner_r`, `flutes`,
  `flute_length`; tornada `kind`, `nose_r`, `kappa_r`, `eps_r`); verilirse öneri bu takımın kimliğini taşır. Programa
  takım değişimi **yazılmaz**; bu SPEC yalnız öneri üretir (Açık soru 3).

Örnek: `D_parça = 0.1875`, `D_lim = 0.8` → `k = 4` parça/kenar; `D_parça = 0.75` → `k = 1`.

## Dosyalar
- Yeni: `cam/omur.py` (Taylor ve Miner hesabı, öneri), `tests/cam/test_omur.py`, `tests/cam/test_omur_torna.py`,
  `durum/59-takim-omru.md`.
- Kullanılır (değişmez): `cam/model.py`, `cam/cutting.py`, `cam/kuvvet.py`, `cam/sim/simulate.py`, `cam/sim/lathe.py`,
  `cam/sim/lathe_time.py`, `malzeme/model.py` (B2).
- Dokunulmayacak: tüm `*/model.py` (takım malzemesi alanı eksik, Açık soru 1), SPEC 32 / 05 / 22 dosyaları, SPEC 38 / 58
  dosyaları (onlar `cam.omur`'un çıktısını okur).

## Arayüz
`cam.omur`:
- `tool_life(taylor: Taylor, Vc: float) -> float` — dk; `Taylor.omur`'un ince sarmalayıcısı, `Vc ≤ 0` veya sonsuz → `ModelError`.
- `@dataclass(frozen=True) StepWear(k: int, op: int, tool_id: int, t: float, Vc_min: float, Vc_max: float, D: float)` —
  adım başına kesme süresi [dk], adımdaki hız aralığı [m/dk], katkı.
- `@dataclass(frozen=True) ToolWear(tool_id: int, tool_material: str, t_cut: float, D: float, Vc_max: float, steps:
  tuple[StepWear, ...])` — takım başına toplam.
- `@dataclass(frozen=True) ChangeAdvice(tool_id: int, kind: str, parts_per_edge: int | None, at_op: int | None,
  sister_id: int | None, D_part: float)` — `kind ∈ {"kenar", "kardes", "gerek_yok"}`; `parts_per_edge = None` iken
  program içi değişim (`at_op` dolu).
- `mill_wear(ops, result: SimResult, loads: list[Load], material: Malzeme, tool_materials: Mapping[int, str]) ->
  list[ToolWear]` — `len(loads) == len(result.steps)` değilse `CamError`; yalnız `kind == "kesme"` adımları.
- `turn_wear(ops, result, loads, material, tool_materials, rtol=1e-6) -> list[ToolWear]` — G96 / G97 ayrımı `Toolpath.css`
  ve `rpm`'den.
- `advise(wear: list[ToolWear], lib: ToolLibrary, parts: int = 1, D_lim: float = 0.8) -> list[ChangeAdvice]` —
  `0 < D_lim ≤ 1`, `parts ≥ 1` tam sayı, aksi `CamError`.
- `to_dict()` her sınıfta (38 ve 58 JSON olarak okur; Tezgah iş föyünde gösterir).

Hatalar (sessiz hata yok):
- Op'taki takım `tool_materials`'da yok → `ModelError("T3 için takım malzemesi verilmedi")`.
- Takım malzemesi `TAKIM_MALZEMELERI` dışında → `ModelError`.
- Malzeme kaydında o takım malzemesi için `taylor` yok → `ModelError("'C45' kaydında 'karbur' için Taylor yok")`.
- Kesme adımında `Vc` hesaplanamıyor (devir 0, tornada `css` ve `rpm` ikisi de yok) → `CamError`.

## Kabul kriterleri
Testlerde uydurma takım, uydurma malzeme kaydı (`C = 300`, `n = 0.25`) ve uydurma yol; beklenen değerin kaynağı test yorumunda.
- [ ] K1 Taylor: `tool_life` `Vc = 150, 200, 300` → `16.0`, `5.0625`, `1.0` dk (göreli 1e-12); `Vc = 0`, `−1`, `inf` →
  `ModelError` — `tests/cam/test_omur.py`
- [ ] K2 Sabit hız: tek takım, sabit `Vc = 150` (D = 10, `n = 4774.65`) ile 3 dk kesen uydurma freze yolu → `D = 0.1875`
  (1e-9); G0 ve hava adımları eklendiğinde `D` değişmiyor — `test_omur.py`
- [ ] K3 Miner iki hız: aynı takım 4 dk `150` ve 0.5 dk `300` m/dk → `D = 0.75` (1e-12); adım sırası değişince sonuç aynı — `test_omur.py`
- [ ] K4 Etkin çap: küresel uçta (`D = 10`) `ap = 1` iken `Vc`, SPEC 14 `effective_diameter` ile birebir; `ap` büyüdükçe `D` artıyor — `test_omur.py`
- [ ] K5 Torna G97 alın: `N = 500`, `f = 0.2`, `R₀ = 50 → 0` → kesme süresi 0.5 dk, `D = 0.0075161336` (kapalı form, 1e-9) —
  `tests/cam/test_omur_torna.py`
- [ ] K6 Torna G96 + devir sınırı: `Vc₀ = 150`, `N_max = 2000`, `f = 0.2`, `R₀ = 50 → 0` → `r* = 11.936621`, `D = 0.01580293`
  (kapalı form, 1e-9); boy tornalamada (`r` sabit) `D = t / T(Vc₀)` — `test_omur_torna.py`
- [ ] K7 Tam sayı olmayan üs: `n = 0.3` ile G97 alın tornalamada sayısal sonuç kapalı form `(2πN/1000C)^m R₀^(m+1)/((m+1) f N)`
  ile `rtol = 1e-6` içinde — `test_omur_torna.py`
- [ ] K8 Öneri: `D_parça = 0.1875`, `D_lim = 0.8` → `kind = "kenar"`, `parts_per_edge = 4`; `D_parça = 0.75` → `1`; tek programda
  `D = 1.2` → `at_op` `D`'nin 0.8'e ulaştığı op'un başı; kütüphanede aynı geometrili ikinci takım varken `kind = "kardes"` ve
  `sister_id` dolu, geometri farklıysa kardeş sayılmıyor — `test_omur.py`
- [ ] K9 Hatalar: takım malzemesi eşlemi eksik, kümede olmayan takım malzemesi, Taylor kaydı yok, `D_lim ∉ (0, 1]`, `parts = 0`,
  `loads` uzunluğu farklı, devirsiz kesme → ilgili `ModelError` / `CamError` ve anlaşılır mesaj — ilgili test dosyaları
- [ ] K10 JSON: `ToolWear` ve `ChangeAdvice` `to_dict` / `from_dict` gidiş-dönüşü birebir — `test_omur.py`
- [ ] Tüm testler yeşil, `ruff check .` ve `ruff format --check .` temiz, 0 "uygulanmamış"; 10 s'den uzun testler `slow`

## Kapsam dışı
- Genişletilmiş Taylor (`Vc · T^n · f^a · ap^b = C'`): Açık soru 2.
- Aşınma mekanizmaları (yan aşınma `VB` eğrisi, krater, kenar kırılması), sıcaklık modeli, soğutma etkisi.
- Takım ömrü için kesme hızı optimizasyonu (en düşük maliyetli `Vc`, Gilbert / Taylor ekonomik hız): SPEC 58 veya ayrı ek.
- Programa otomatik takım değişimi ya da kardeş takım çağrısı yazma (Sinumerik takım yönetimi, Fanuc `TLM`): Açık soru 3.
- Gerçek tezgâhtan ölçülen ömürle Taylor sabitlerini kalibre etme (kullanıcı ölçümünden `C`, `n` uydurma): ileride.
- Delme, kılavuz ve diş çevrimlerinde özel ömür modelleri: ilk sürümde aynı Taylor, `Vc` matkap dış çapından.

## Kararlar (onayla kayda geçti, 2026-10-18 16:06; önerilen yanıtlar kabul edildi)
1. `cam/model.py`'de `Tool` ve `LatheTool`'un takım malzemesi (karbur, HSS…) alanı yok. Bu SPEC eşlemi (`tool_materials`)
   dışarıdan mı alsın, yoksa önce arayüz PR'ı mı açılsın? Karar: bu SPEC eşlemle çalışsın (arayüz değişmez); ayrı küçük arayüz
   PR'ı `Tool.tool_material: str | None = None` eklesin, 59 onu varsayılan olarak kullansın.
2. Genişletilmiş Taylor (ilerleme ve derinlik üsleri) eklensin mi? Karar: hayır, ilk sürüm yalnız `Vc`; B2 kaydı yalnız `C, n`
   tutuyor ve kaynaklı `a, b` verisi az. Veri gelirse ek SPEC.
3. Öneri yalnız iş föyüne mi yazılsın, yoksa programa takım değişimi de eklensin mi? Karar: yalnız öneri ve iş föyü; programı
   değiştirmek 57 (otomatik CAM 2) ve kontrolör takım yönetimine (DMG MORI'de Sinumerik / MAPPS) bağlı ayrı bir iş.
4. `D_lim` varsayılanı 0.8 mi? Karar: 0.8 ve iş föyünde görünür; kullanıcı tezgâh/malzeme başına değiştirebilir.
