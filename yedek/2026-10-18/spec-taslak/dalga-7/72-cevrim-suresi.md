# SPEC 72 — Çevrim süresi kestirimi 2: sarsıntı sınırlı hız profili, köşe yumuşatma, eksen başına ivme, takım değişimi ve bağlama süreleri

> **Durum: ONAYLI** (kullanıcı, 2026-10-18 16:06: "Dalga 7 taslakları 57, 58, 59, 61, 62, 63, 64 ve 72'yi önerileriyle onaylıyorum."; açık sorular önerilen yanıtlarla kapatıldı, bkz. Kararlar) (Dalga 7, yeni hat (CAM grubu önerisi); `yol-haritasi/dalga-6-ve-sonrasi.md` bölüm 4).
> Bağımlılık (kod): SPEC 05 (`cam/sim/timing.py`: `Machine`, `move_time`, `arc_geometry`; `main`'de), SPEC 22
> (`cam/sim/lathe_time.py`: `lathe_move_time`, G95/G96; `main`'de), SPEC 04 (`cam/gcode/cycles.py`: `DrillOp`, `hole_moves`;
> `main`'de), SPEC 30 (`MachineProfile`: `rapid`, `feed_max`, `rpm_max`, `tool_slots`; `main`'de), SPEC 41–42
> (`cam/multiaxis/indexed.py` `machine_toolpath`, `linearize.py`; `main`'de), SPEC 29 (`MillPlan`, `TurnPlan`; `main`'de).
> Kullanan: **SPEC 58** (süre, maliyet ve teklif; "Sonraki yol haritası (Dalga 5)" thread'inin hattı) bu SPEC'in `CycleTime`
> çıktısını okur. 58'in maliyet kuralları burada yoktur.
> Hedef tezgâhlar: DMG MORI DMU 50 / 60 / 75 / 90, DMF 360, NHC 5000, NLX 2500 / 700, NTX 3000. Varsayılan kontrolörler:
> Sinumerik 840D sl, Heidenhain TNC 640; NTX / NLX'te MAPPS (Fanuc tabanlı).

## Amaç
SPEC 05'in süre modeli her hareketi **tam duruşla** ve **sonsuz sarsıntıyla** (ivme anında açılır) hesaplar; köşelerde
yavaşlama, kontrolörün ileri bakışı (look-ahead), takım değişim süresi dışındaki bekleme süreleri ve döner eksenler yoktur.
Bu yüzden kısa segmentli 3B yollarda süre kısa çıkar (ivme yok sayılırsa) ya da çok uzun çıkar (her köşede tam duruş).
Teklif (58) bu sayıya para bağlayacağı için süre: (1) sarsıntı sınırlı (S eğrisi) hız profiliyle, (2) yol toleransıyla
köşe hızı ve ileri-geri hız planlamasıyla, (3) eksen başına hız / ivme sınırıyla, (4) takım değişimi, iş mili hızlanması,
bağlama ve palet süreleriyle, (5) torna (G95 / G96) ve 5 eksen döner eksen süreleriyle hesaplanır; kalem kalem dökülür ve
gerçek tezgâh ölçümüyle kalibre edilebilir.

## Teori

### 1. Sarsıntı sınırlı (S eğrisi) duruştan duruşa hareket
Sınırlar: hız `v` [mm/s], ivme `a` [mm/s²], sarsıntı `j` [mm/s³]. Simetrik yedi evreli profil, `0 → v` hızlanma:
- `v ≥ a²/j` (ivme sınırına ulaşılır): `t_h = v/a + a/j`, yol `s_h = v·t_h / 2 = v(v/a + a/j)/2`.
- `v < a²/j` (ivme sınırına ulaşılmaz): `t_h = 2√(v/j)`, yol `s_h = v·√(v/j)`.
Simetrik profilde `s_h = v·t_h/2` her iki durumda geçerlidir (sayısal integrasyonla doğrulandı, bkz. K1).
Hareket süresi, boy `L`:
- **Sabit hız evresi var** (`L ≥ 2·s_h`): `t = L/v + t_h`. İvme sınırına ulaşılan durumda `t = L/v + v/a + a/j`.
- **Sabit hız yok, ivme sınırına ulaşılıyor** (`2a³/j² ≤ L < 2·s_h`): tepe hızı `v_p` şu denklemi sağlar:
  `v_p²/a + v_p·a/j = L`, yani `v_p = (a/2)·(−a/j + √(a²/j² + 4L/a))`. Süre `t = 2(v_p/a + a/j)`.
- **Çok kısa** (`L < 2a³/j²`): `v_p = (j·L²/4)^(1/3)`, `t = 4·(L/(2j))^(1/3)`.
Sınır durumları: `j → ∞` iken ilk iki formül SPEC 05'in trapez (`L/v + v/a`) ve üçgen (`2√(L/a)`) formüllerine iner.
Örnek: `L = 500`, `v = 100`, `a = 1000`, `j = 10000` → `t = 5 + 0.1 + 0.1 = 5.2 s`. `L = 40`, `v = 1000`, aynı `a`, `j` →
`v_p = 156.155 mm/s`, `t = 0.51231 s`. `L = 10` → `t = 4·(5·10⁻⁴)^(1/3) = 0.31748 s`.

### 2. Giriş ve çıkış hızı sıfır olmayan segment
Köşe yumuşatma açıkken segment `v₀` hızla girer, `v₁` hızla çıkar (`v₀, v₁ ≤ v`). `Δv` hız değişimi için S eğrisi
süresi `τ(Δv) = Δv/a + a/j` (`Δv ≥ a²/j`) ya da `2√(Δv/j)` (`Δv < a²/j`); yol `(v_baş + v_son)·τ/2`. Sabit hız
evresi varsa süre doğrudan; yoksa tepe hızı `v_p ∈ [max(v₀, v₁), v]` boy denkleminden **ikiye bölmeyle** (mutlak
`1e-9 mm/s`) bulunur. `v₀ → v₁` boy içinde hiç ulaşılamıyorsa ileri-geri planlama (aşağıda) bunu zaten önler; yine de
oluşursa `CamError` (iç tutarlılık hatası, sessizce kısaltma yok).

### 3. Köşe hızı (yol toleransı ile)
Ardışık iki doğrusal segmentin birim yönleri `u₁`, `u₂`; yön değişimi `φ = arccos(u₁·u₂)` (`0` = düz devam). Kontrolör
köşeyi, köşe noktasından en çok `ε` (yol toleransı; Sinumerik `G64` / `CYCLE832`, Heidenhain `M120` / `CYCL DEF 32`
eşdeğeri) sapan teğet bir yayla yuvarlar. Yay yarıçapı:
`R = ε·cos(φ/2) / (1 − cos(φ/2))`, teğet boyu `R·tan(φ/2)` her iki segmentin yarısını aşamaz (aşarsa `R` buna göre kısılır).
Köşe hızı `v_k = min(F, √(a_yol·R))`; `φ = 0` → `v_k = F`, `φ = π` (geri dönüş) → `v_k = 0`. Bu, GRBL "junction deviation"
formülüyle aynıdır (`θ = π − φ`, `sin(θ/2) = cos(φ/2)`). Örnek: `ε = 0.01`, `φ = 90°`, `a = 1000` → `R = 0.024142`,
`v_k = 4.9135 mm/s = 294.81 mm/dk`. Yay segmentlerinde (G2/G3) merkezcil sınır `v ≤ √(a_yol·r)` (SPEC 05 ile aynı) ve
yay–doğru geçişinde teğet süreksizliği yoksa `φ = 0`.

### 4. İleri-geri hız planlaması (look-ahead)
Segment sınır hızları `v_i` (başlangıç ve son `0`). Geri geçiş: `v_i ≤ v_hız(v_{i+1}, L_i)`, ileri geçiş:
`v_i ≤ v_hız(v_{i−1}, L_{i−1})`; `v_hız(w, L)` = `w`'den başlayıp `L` boyda S eğrisiyle ulaşılabilen en büyük hız
(ikiye bölme). Ayrıca `v_i ≤ v_k,i`. İleri bakış ufku `N` segment (varsayılan sınırsız; kontrolörün blok tamponu,
Açık soru 3). G0 hareketleri ve takım değişimi, iş mili açma / kapama, `M0`/`M1`, `G4` tam duruştur (`v = 0`).

### 5. Eksen başına sınır
Yol yönü `u` için yol hızı ve ivmesi eksen sınırlarından: `v_yol = min_i v_i / |u_i|`, `a_yol = min_i a_i / |u_i|`,
`j_yol = min_i j_i / |u_i|` (SPEC 05'in `_axis_limit` kalıbı). `rapid` mm/dk ise `/60`. Kesmede `v = min(F/60, v_yol)`.
**Döner eksenli** (41 `machine_toolpath` ile makine eksenine çevrilmiş) harekette ek sınır: `t ≥ |Δq_r| / ω_r` her döner eksen
`r` için (`ω_r` derece/s); G0'da `t = max(t_doğrusal, max_r |Δq_r|/ω_r,hızlı)`. TCP'li (`G43.4` / `TRAORI` / `M128`)
G1'de `F` takım ucu hızıdır; döner eksen sınırı aşılırsa yol hızı düşürülür. Ters zaman (`G93`, 42 `inverse_time`) için
süre doğrudan `1/F` dakikadır.

### 6. Delik çevrimleri
`DrillOp` hareketleri `hole_moves` (SPEC 04) ile açılır; `G4 P` / `dwell` süresi `bekleme` kalemine eklenir. Gagalama
(G83) her geri çekilme G0 sayılır.

### 7. Torna
G95 ve G96 hareketlerinin "sınırsız ivme" süresi SPEC 22 `lathe_move_time` ile hesaplanır; eşdeğer hız
`v_eş = L / t_22` S eğrisi formülüne `v` olarak girer (22'deki `accel` kalıbının sarsıntılı hâli). G96'da devir değişimi
iş mili hızlanma süresini doğurmaz (sürekli izleme varsayımı, Kapsam dışı).

### 8. Hareket dışı süreler
- **Takım değişimi** `t_tc` (talaştan talaşa, s); torna tareti için `t_taret` (istasyon başına sabit).
- **İş mili hızlanması:** devir `n₀ → n₁` için `t = |n₁ − n₀| / ṅ` (`ṅ` dev/dk/s); `M3`/`M4` kalkış `n₀ = 0`, `M5` duruş.
  Takım değişimiyle örtüşen kısım bir kez sayılır: `max(t_tc, t_iş_mili)` (Açık soru 4).
- **Bağlama** `t_bağlama` her `Setup` için (kullanıcı girer, varsayılan 0); **palet** değişimi `t_palet` (NHC 5000).
- **Program başı / sonu** `t_sabit` (referansa gitme, kapı vb.).

### 9. Kalibrasyon
Kullanıcı tezgâhta ölçtüğü gerçek süreleri `(program, t_ölçülen)` olarak girer. Tezgâh başına düzeltme katsayısı en
küçük karelerle `k = Σ t_ölç·t_tah / Σ t_tah²` (orijinden geçen doğru). Raporda hem ham tahmin hem `k·t` gösterilir;
`k` yalnız kullanıcı ölçümünden gelir, uydurma varsayılan yoktur (`k = 1`). Ölçüm sayısı < 3 ise uyarı notu.

## Dosyalar
- Yeni: `cam/sim/sure.py` (S eğrisi, köşe hızı, ileri-geri planlama, eksen sınırları), `cam/sim/cevrim.py` (plan /
  işlem listesi → `CycleTime`, hareket dışı süreler, kalibrasyon), `cam/sim/zaman_profili.py` (tezgâh zaman bloğu JSON
  okuma / yazma), `cam/post/profiles/zaman/*.json` (örnek, uydurma değerli ve öyle işaretli profiller),
  `tests/cam/test_sure.py`, `tests/cam/test_cevrim.py`, `tests/cam/test_zaman_profili.py`, `durum/72-cevrim-suresi.md`.
- Kullanılır (değişmez): `cam/sim/timing.py`, `cam/sim/lathe_time.py`, `cam/gcode/cycles.py`, `cam/multiaxis/indexed.py`,
  `cam/multiaxis/linearize.py`, `cam/plan.py`, `cam/plan_turn.py`, `cam/post/machine.py`, `cam/model.py`.
- Dokunulmayacak: tüm `*/model.py` (`MachineProfile`'a alan eklemek ayrı arayüz PR'ıdır, Açık soru 1), SPEC 05'in
  `move_time`'ı (eski model aynen kalır; 05, 22, 32 onu kullanır).

## Arayüz
`cam.sim.sure`:
- `@dataclass(frozen=True) Dynamics(v_max: tuple[float, ...], a_max: tuple[float, ...], j_max: tuple[float, ...] | None,
  rot_v: tuple[float, ...] = (), rot_a: tuple[float, ...] = (), tol: float = 0.0, lookahead: int | None = None)` —
  eksen başına (X, Y, Z [+ döner]) hız mm/dk, ivme mm/s², sarsıntı mm/s³ (`None` → sonsuz); döner eksen hızı derece/dk,
  ivmesi derece/s²; `tol` = `ε` (0 → her köşede tam duruş). Pozitif olmayan / sonlu olmayan değer → `CamError`.
- `scurve_time(L: float, v: float, a: float, j: float | None, v0: float = 0.0, v1: float = 0.0) -> float`
- `junction_speed(u1, u2, F: float, a: float, tol: float, L1: float, L2: float) -> float` — mm/s
- `plan_speeds(segments, dyn: Dynamics) -> list[float]` — sınır hızları (ileri-geri geçiş)
- `toolpath_time(tp: Toolpath, dyn: Dynamics) -> PathTime` — `PathTime(cut, rapid, n_moves)` saniye
`cam.sim.cevrim`:
- `@dataclass(frozen=True) TimeProfile(machine: str, dynamics: Dynamics, tool_change: float, turret_index: float = 0.0,
  spindle_accel: float | None = None, pallet: float = 0.0, program_fixed: float = 0.0, k: float = 1.0, verified: bool = False)`
  — `machine` = `MachineProfile.name` ile eşleşir; `verified` yalnız kullanıcı tarafından `True` yapılır (30 kuralı).
- `@dataclass(frozen=True) OpTime(name: str, setup: int, tool_id: int, cut: float, rapid: float, tool_change: float,
  spindle: float, dwell: float)` — saniye; `total` özelliği toplam.
- `@dataclass(frozen=True) CycleTime(ops: tuple[OpTime, ...], setup: float, pallet: float, fixed: float, k: float)` —
  `total_raw`, `total` (`k·total_raw`), `by_kind() -> dict[str, float]` (`kesme`, `hizli`, `takim_degisimi`, `is_mili`,
  `bekleme`, `baglama`, `palet`, `sabit`). **58'in okuduğu tek sözleşme budur**; `to_dict()` JSON'a uygun.
- `cycle_time(plan: MillPlan | TurnPlan | list[Toolpath | DrillOp], prof: TimeProfile, setup_time: float = 0.0) -> CycleTime`
- `calibrate(pairs: list[tuple[float, float]]) -> tuple[float, float]` — `(k, göreli RMS hata)`; boş liste → `CamError`.
`cam.sim.zaman_profili`: `load_time_profile(path) -> TimeProfile`, `save_time_profile(p, path)`; bilinmeyen anahtar,
eksik alan, bozuk JSON → `CamError` (mesajda dosya yolu).

## Kabul kriterleri
Testlerde uydurma tezgâh değerleri; beklenen değerin kaynağı test yorumunda (bu belgedeki formüller, el hesabı).
- [ ] K1 S eğrisi, duruştan duruşa: `(L, v, a, j) = (500, 100, 1000, 10⁴) → 5.2`, `(40, 1000, 1000, 10⁴) → 0.5123105625617661`,
  `(10, 100, 1000, 10⁴) → 0.31748021039363994`, `(500, 50, 2000, 5000)` (`v < a²/j`) `→ 10 + 0.2 = 10.2` (göreli 1e-12);
  üç bölge sınırında (`L = 2·s_h`, `L = 2a³/j²`) süre sürekli (iki yandan 1e-9) — `tests/cam/test_sure.py`
- [ ] K2 Sayısal sağlama: K1'in dört durumunda sarsıntı profilinin sayısal integrali (adım 1e-6 s) boyu ve süreyi
  1e-4 içinde veriyor — `test_sure.py`
- [ ] K3 Eski modele iniş: `j = None` ve `tol = 0` iken `toolpath_time`, SPEC 05 `move_time` toplamıyla (aynı `rapid`, tek
  `accel`, eşit eksen ivmeleri) göreli 1e-12 eşit; uydurma dikdörtgen cep, kontur ve G2/G3 yaylı yol — `test_sure.py`
- [ ] K4 Köşe hızı: `ε = 0.01`, `φ = 90°`, `a = 1000`, `F` büyük → `294.80788362157386 mm/dk` (1e-9); `φ = 0` → `F`; `φ = 180°` → 0;
  çok kısa segmentte teğet boy sınırı devrede (`R·tan(φ/2) = min(L1, L2)/2`) — `test_sure.py`
- [ ] K5 Tekdüzelik: `ε` artınca, `a` veya `j` artınca, `F` artınca toplam süre artmıyor; segment bölmek (aynı doğruyu iki
  parçaya ayırmak, `φ = 0`) süreyi değiştirmiyor (1e-9) — `test_sure.py`
- [ ] K6 İleri-geri planlama: 1000 eşit kısa segmentli düz çizgi = tek segment süresi (1e-9); zigzag (`φ = 180°`) = segment
  başına duruştan duruşa toplamı — `test_sure.py`
- [ ] K7 Eksen başına sınır: X ivmesi Y'nin yarısı iken 45° doğruda `a_yol = a_X/cos45°`; yalnız Y hareketinde X sınırı etkisiz
  — `test_sure.py`
- [ ] K8 Döner eksen: B 90° dönüşü ve 1 mm doğrusal G0'da süre `max(t_doğrusal, 90/ω_B)`; TCP'li G1'de döner hız sınırı
  aşılınca süre `|Δq|/ω` — `test_sure.py`
- [ ] K9 Torna: G95 ve G96 yolunda `j = None`, `tol = 0` iken SPEC 22 `lathe_move_time` toplamına eşit; `j` sonlu iken büyük —
  `tests/cam/test_cevrim.py`
- [ ] K10 Hareket dışı: iki takımlı uydurma plan: `takim_degisimi = 2·t_tc` (ilk takım dahil, 29 `tool_changes()` ile aynı
  sayım), iş mili `|Δn|/ṅ` ile ve takım değişimiyle örtüşen kısım bir kez; `G4 P2` → `bekleme = 2`; iki bağlama →
  `baglama = 2·setup_time`; `by_kind()` toplamı `total_raw` (1e-12) — `test_cevrim.py`
- [ ] K11 Kalibrasyon: tahmin `(100, 200, 300)`, ölçüm `(110, 220, 330)` → `k = 1.1`, RMS hata 0; boş liste `CamError`;
  2 ölçümde uyarı notu — `test_cevrim.py`
- [ ] K12 Profil dosyası: gidiş-dönüş baytı aynı; bilinmeyen anahtar, negatif ivme, `MachineProfile.name` ile eşleşmeyen ad
  → `CamError` — `tests/cam/test_zaman_profili.py`
- [ ] K13 Hatalar: `L < 0`, `v ≤ 0`, `nan`, `G18` dışı torna düzlemi uyumsuzluğu, ulaşılamayan `v₀ → v₁` → `CamError`; hiçbir
  durumda `nan` veya negatif süre yok — ilgili test dosyaları
- [ ] Tüm testler yeşil, `ruff check .` ve `ruff format --check .` temiz, 0 "uygulanmamış"; 10 s'den uzun testler `slow`

## Kapsam dışı
- Kontrolörün gerçek yumuşatma algoritmaları (Sinumerik `COMPCAD` / `COMPSURF` spline, Heidenhain ADP), servo gecikmesi,
  hız ön beslemesi; bunlar kalibrasyon katsayısına bırakılır.
- Takım değişim zincirinin konuma bağlı süresi (cep numarasına göre), çip konveyörü, ölçüm probu çevrimleri.
- G96'da iş milinin devir değişimine yetişememesi; torna-freze C ekseni süreleri (49 birleşince ek).
- Maliyet, saat ücreti, teklif: SPEC 58.

## Kararlar (onayla kayda geçti, 2026-10-18 16:06; önerilen yanıtlar kabul edildi)
1. Zaman verileri (ivme, sarsıntı, takım değişimi, iş mili ivmesi, palet) nerede dursun? Seçenekler: (a) `MachineProfile`'a
   yeni alanlar (ayrı arayüz PR'ı + test thread'i), (b) 72'nin kendi `zaman` JSON dosyası, `MachineProfile.name` ile eşli.
   Karar: (b), arayüz değişmeden başlar; değerler oturunca ileride (a) ile birleştirilir.
2. DMG MORI tezgâhlarının gerçek ivme / sarsıntı değerleri bilinmiyor. Karar: örnek profiller açıkça "uydurma, ölçülmedi"
   işaretli; kullanıcı her tezgâhta 2–3 programın gerçek süresini girip `k`'yı kalibre eder; `verified` yalnız kullanıcı.
3. İleri bakış ufku: sınırsız mı, kontrolör tamponu kadar mı (ör. 840D sl'de yüzlerce blok)? Karar: varsayılan sınırsız,
   profil başına `lookahead` alanıyla kısıtlanabilir.
4. Takım değişimi ile iş mili hızlanması örtüşsün mü (`max`) yoksa toplansın mı? Karar: `max` (modern tezgâhlarda paralel);
   profil bayrağıyla `toplam` seçilebilir.
