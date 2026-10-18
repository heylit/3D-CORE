# SPEC 52 — 3B diş ve helis simülasyonu: torna dişi, kılavuz ve diş frezeleme

> **Durum: ONAYLANDI** (kullanıcı, 2026-10-18 14:53 UTC "Dalga 6 CAM taslakları" onay sorusu; kullanıcının 11:14 UTC kuralı
> gereği 2 dakika içinde itiraz gelmediği için açık soruların önerilen cevaplarıyla kabul). Metin kullanıcı onayı olmadan değişmez.
> Bağımlılık (kod): **B0** (`PathMeta.strategy = "dis"`), SPEC 20 (`thread`, `iso_thread_depth`; `main`'de), SPEC 22 (torna
> simülasyonu, `RadialMap`; `main`'de), SPEC 04b
> (kılavuz `G84`, `Tool.pitch`; yalnız K5 için; `ToolKind.TAP` `main`'de).

## Amaç
SPEC 22'nin dönel simetrik simülasyonunda diş bölgesi diş dibi çapında düz silindir görünür (22 Kapsam dışı: "senkron
kesimin helisel izi 3B simülasyon ister"). Bu SPEC dişi **gerçek helis olarak** simüle eder: torna diş çekme (`G32`
pasoları, SPEC 20 `thread`), frezede kılavuz (`G84`, SPEC 04b) ve diş frezeleme (helisel enterpolasyon); sonra simüle
edilen yüzeyden **hatve, büyük çap, böğür çapı ve diş dibi çapını ölçüp** ISO 68-1 formülleriyle karşılaştırır.

## Teori

### Silindirik yükseklik haritası (`PolarMap`)
Diş, bir eksen etrafında (tornada iş mili, frezede delik ekseni) açı `θ` ve eksen boyu `z` ile parametrelenir. Izgara
`n_θ × n_z` (açı adımı `Δθ = 360/n_θ`, boy adımı `Δz`); her hücrede malzemenin radyal aralığı `[r_iç(θ, z), r_dış(θ, z)]`
(dolu milde `r_iç = 0`, delikte `r_dış = r_stok`). Dış diş `r_dış`'ı, iç diş `r_iç`'i değiştirir. Tek aralık yeter:
diş ve helis kesimleri radyal yönde içbükey boşluk açmaz (alt kesik takımlar Kapsam dışı).
- Hacim: `V = Σ ½(r_dış² − r_iç²)·Δθ[rad]·Δz` (hücre ortası örneklemesi; `O(Δθ² + Δz)` yakınsama).
- Başlangıç: `CylinderStock`'tan, ya da 22 `RadialMap`'ten (dönel simetrik, her `θ` aynı) — torna sonrası diş.
- Frezede yerel harita: delik ekseni `Frame` (41) ile verilir; harita `r ≤ r_stok_yerel` silindir bölgesini kapsar.

### Senkron helis süpürmesi
Senkron kesimde (torna `G32` / `G95` ile `feed = P` mm/dev, kılavuz `G84`) parçanın açısı ile takımın eksenel konumu
bağlıdır: `θ(z) = θ₀ + 360°·(z − z₀)/P`. Takımın kesen profili, parçanın yerel `(r, z)` yarı düzleminde sabit bir kesittir
(torna diş kalemi: uç açısı `ε_r`, burun yarıçapı `r_ε`; kılavuz: ISO iç diş profili). Hücre `(θ, z)` için kesimin etkisi,
profilin `Δz = z − z_c(θ)` kayık değeriyle bulunur; `z_c(θ) = z₀ + P·(θ − θ₀)/360° + k·P` (en yakın `k`). Böylece bir
pasonun tüm etkisi tek vektör işlemiyle hesaplanır, adım adım hareket gerekmez:
- Dış diş: `r_dış(θ, z) ← min(r_dış, r_profil(z − z_c(θ)))`, iç diş: `r_iç(θ, z) ← max(r_iç, r_profil(…))`.
- Pasoların hepsi aynı `θ₀`'dan başlar (kontrolör senkronu: her paso iş milinin aynı açısında başlar). Çok ağızlı diş
  (`starts = n`): `θ₀ + j·360°/n`, `j = 0 … n − 1`.
- Giriş / çıkış boyları (hızlanma) bu SPEC'te ideal: profil `z_start`'tan `z_end`'e tam derinlikte (Kapsam dışı).

### Diş frezeleme (senkronsuz helis)
Freze takımı kendi ekseni etrafında hızla döndüğü için kesen kısmı dönel bir zarftır (tek profilli diş frezesi: çap `D`,
uç açısı 60°, burun yarıçapı `r_ε`; profil bu SPEC'te `ThreadMillForm` ile verilir). Takım ekseni delik eksenine paralel,
merkezi yarıçapı `ρ_h` olan helis üzerinde: `c(φ) = (ρ_h cos φ, ρ_h sin φ, z₀ + P·φ/2π)`. Hücre `(θ, z)` için malzemeye
etki, helis üzerindeki en yakın konumların (`φ ≈ θ`) zarfıyla hesaplanır: `φ` örnekleme adımı `Δφ ≤ Δθ/2`. Kesim dış
dişte `ρ_h = r_dış_diş + D/2 − h`, iç dişte `ρ_h = r_iç_diş − D/2 + h` (`h` diş derinliği). Helis açısı nedeniyle profil
hafifçe bozulur (iç dişte takım çapı delik çapına yaklaştıkça büyür); bu bozulma yoğun örneklemeli referansla ölçülür.

### ISO 68-1 temel profil (kabul formülleri)
Hatve `P`, temel üçgen yüksekliği `H = (√3/2)·P`:
- Böğür çapı `d₂ = d − (3√3/8)·P = d − 0.649519·P` (dış ve iç için aynı temel profil).
- Dış diş dibi (SPEC 20 kuralı, burun yarıçapı `H/6`): derinlik `h = 17/24·H`, `d₃ = d − 2h = d − 1.226869·P`.
- İç diş temel küçük çapı `D₁ = D − 2·(5/8)·H = D − 1.082532·P` (iç derinlik `5/8·H`, SPEC 20 `iso_thread_depth`).
- Kontrol: 60° V'ye teğet `r_ε = H/6` yarıçaplı burun, sivri tepeyi `H/6` yukarıda keser; böylece `h = 7H/8 − H/6 = 17H/24`.

### Ölçüm (simüle yüzeyden)
`thread_measure(map, side) -> ThreadMeasure(P, d, d2, d_root, lead_err)`:
- Hatve: sabit `θ`'da `r(z)` dizisinin öz-ilişkisinin (autocorrelation) ilk tepe noktası, parabol ile alt-hücre doğruluğunda.
- Büyük çap / diş dibi: `r(θ, z)`'nin bölgedeki en büyük / en küçük değeri × 2.
- Böğür çapı: diş genişliğinin boşluk genişliğine eşit olduğu yarıçap (her `θ` için `r = const` kesitinde dolu oranı ½),
  ikiye bölme (bisection) ile; tüm `θ`'ların ortalaması × 2.
- Helis tutarlılığı: `lead_err = max |r(θ, z) − r(0, z − P·θ/360°)|` (doğrusal ara değerle).

## Dosyalar
- Yeni: `cam/sim/polar.py` (`PolarMap`, hacim, başlangıç), `cam/sim/thread_sim.py` (senkron süpürme, diş frezeleme zarfı,
  sürücü `simulate_thread`), `cam/sim/thread_measure.py` (ölçüm), `cam/thread_mill.py` (helisel diş frezeleme yolu:
  `G2/G3` + Z, `meta.strategy = "dis"`), `tests/cam/test_thread_*.py`, `durum/52-dis-helis-sim.md`.
- Kullanılır (değişmez): `cam/model.py` (B0 ile), `cam/lathe_ops.py` (`thread`, `iso_thread_depth`), `cam/sim/radial.py`,
  `cam/sim/lathe.py`, `cam/model.py` `Frame`, 04b kılavuz op'u.
- Dokunulmayacak: tüm `*/model.py`, 22 / 43'ün mevcut dosyaları (simülatörleri değişmez; diş ayrı sürücüde), ortak dosyalar.

## Arayüz
- `@dataclass PolarMap(z0, dz, n_theta, n_z, r_in: np.ndarray, r_out: np.ndarray)`;
  `PolarMap.from_stock(stock: CylinderStock, dtheta_deg=1.0, dz=0.05, max_cells=20_000_000)`,
  `PolarMap.from_radial(rmap: RadialMap, dtheta_deg=1.0, dz=None)`, `volume() -> float`, `copy()`.
- `@dataclass ThreadMillForm(D: float, eps_deg: float = 60.0, nose_r: float = 0.0, flute_length: float = 20.0)` — `D > 0`,
  `0 < eps_deg < 180`, `nose_r ≥ 0`; aksi `CamError`.
- `thread_mill(hole_frame: Frame, d: float, P: float, length: float, form: ThreadMillForm, side: str = "ic",
  climb: bool = True, rpm: float = 3000.0, feed: float = 300.0) -> Toolpath` (`feed` mm/dk, `G94`).
- `simulate_thread(ops: list[Toolpath], initial: PolarMap, frame: Frame | None = None, starts: int = 1) -> PolarMap` —
  `G32`/`G95` torna pasoları (feed = P), `G84` kılavuz, `thread_mill` helisi kabul; başka yol → `CamError` ("diş yolu değil").
- `thread_measure(m: PolarMap, side: str, z_range: tuple[float, float]) -> ThreadMeasure`;
  `@dataclass ThreadMeasure(P: float, d: float, d2: float, d_root: float, lead_err: float)` (mm).

## Kabul kriterleri
Testlerde uydurma geometri; beklenen değerin kaynağı test yorumunda (ISO 68-1, SPEC 20 formülleri).
- [ ] K1 Harita: `from_stock` hacmi `CylinderStock.volume`'a `O(Δθ²)` yakın (rel ≤ `(Δθ[rad])²/6`); `from_radial` 22 `RadialMap`'in hacmini
  aynı ızgarada rel 1e-9 veriyor — `tests/cam/test_thread_map.py`
- [ ] K2 Torna dış diş M20×2.5: SPEC 20 `thread` (`h = 17/24·H`, `r_ε = H/6`, `ε_r = 60°`) simüle edilince `thread_measure`:
  `P = 2.5` (1e-3), `d₂ = 20 − 0.649519·2.5` (± `Δz`), `d_root = 20 − 1.226869·2.5` (± `Δz`), `lead_err ≤ Δz` — `tests/cam/test_thread_lathe.py`
- [ ] K3 Ince hatve ve sol diş: M12×1 ve sol dişte (`z_end < z_start`, ters dönüş) aynı ölçümler; çok ağızlı (`starts = 2`) dişte
  hatve `P`, hatve boyu (lead) `2P` — `test_thread_lathe.py`
- [ ] K4 Kaldırılan hacim: sivri profil (`r_ε = 0`), `n` tam tur diş için kaldırılan hacim, profil alanının `2π·r_c` ile çarpımına (Pappus,
  `r_c` boşluk alanının ağırlık merkezi yarıçapı) `O(Δθ² + Δz)` toleransta eşit — `test_thread_lathe.py`
- [ ] K5 Kılavuz (`G84`, 04b): M8×1.25 iç diş, ISO iç profil formu: `d₂ = 8 − 0.649519·1.25` (± `Δz`), küçük çap `8 − 1.082532·1.25` (± `Δz`);
  yerel çerçeve eğik delikte (41 `Frame`) sonuç aynı — `tests/cam/test_thread_tap.py`
- [ ] K6 Diş frezeleme (Ek 2): M16×1.5 iç diş, `D = 10`; simüle yüzey yoğun örneklemeli (açısal 0.05°) zarf referansıyla ≤ 1e-6; ölçülen `d₂`
  ISO değerine `0.03·P` içinde; tırmanma / geleneksel yönde aynı yüzey — `tests/cam/test_thread_mill.py`
- [ ] K7 Yol üretimi: `thread_mill` yolunda her tur `ΔZ = P` 1e-12, helis yarıçapı `ρ_h` formülü 1e-12, giriş yayı delik duvarına teğet —
  `test_thread_mill.py`
- [ ] K8 Çapraz kontrol (Ek 1): büyük `P`'li düz senkron kesimde (diş olmayan profil, kesit her θ'da stok z aralığının
  içinde) `PolarMap`'ten kalkan hacim kapalı form Pappus hacmine `V = Δφ·A·r̄` (A kalkan kesit alanı, r̄ ağırlık merkezi
  yarıçapı, Δφ taranan açı [rad]; tam turda `2π·A·r̄`) ızgara çözünürlüğüne uygun toleransta eşit — `tests/cam/test_thread_cross.py`
- [ ] K9 Hatalar: diş olmayan yol, `P ≤ 0`, `starts < 1`, haritayı aşan yol, `ThreadMillForm` geçersiz değerleri, `max_cells` aşımı →
  `CamError` — `tests/cam/test_thread_errors.py`
- [ ] Tüm testler yeşil, `ruff check .` ve `ruff format --check .` temiz, 0 "uygulanmamış"; 10 s'den uzun testler `slow`

## Kapsam dışı
- Diş giriş / çıkış (hızlanma) boyları, senkron gecikme, `G76` kontrolör açılımı (21 Kapsam dışı), diş toleransı sınıfları
  (6g / 6H) ile otomatik kabul / ret (ölçüm değerleri verilir, sınıf kararı ileride).
- Konik dişler (NPT, BSPT), trapez / testere dişi profilleri, diş ovalama (talaşsız şekillendirme).
- Alt kesik takımlar ve radyal yönde iki aralıklı malzeme; görselleştirme (24 / 25 köprüsü ayrı iş).
- `ToolKind`'e diş frezesi türü eklemek: ileride `cam/model.py` eki (Açık soru 1); bu SPEC profili `ThreadMillForm` ile alır.

## Kararlar (eski açık sorular, önerilen cevaplarla onaylandı)
1. Diş frezesi takımı kütüphaneye şimdi girmez: 52 bitince küçük bir `cam/model.py` eki (`ToolKind.THREAD_MILL` + profil
   alanları) ayrı arayüz PR'ı olur; bu SPEC'te `ThreadMillForm` yalnız simülasyon ve yol üretimi parametresidir.
2. Ölçüm toleransları sayısal doğruluktur (ızgara adımı `Δz`); ISO 965 tolerans sınıfı (6g / 6H) kararı atölye
   ihtiyacına göre sonra.
3. Taslaktaki boş varsayılanlar (koordinatör kararı, küçük teknik ayrıntı): `ThreadMillForm.flute_length = 20.0` mm,
   `thread_mill(rpm=3000.0, feed=300.0)` (`feed` mm/dk).
4. **Ek 1 — K8 düzeltmesi** (kullanıcı yazılı onayı, 2026-10-18 16:27 UTC): taslaktaki K8 aynı kesimi 43 tri-dexel ile
   karşılaştırıyordu; ama tri-dexel (`simulate5`) yalnız freze takımı ve kutu stok kabul eder, torna / kılavuz profiliyle aynı
   geometri iki simülatörde kesilemez. Yeni K8, aynı hacmi bağımsız kapalı form (Pappus) ile denetler; 43 bağımlılığı kalkar.
5. **Ek 2 — K6 düzeltmesi** (kullanıcı yazılı onayı, 2026-10-18 16:27 UTC): bağımsız zarf referansında takımın helis sapması
   `d₂`'yi geometrik olarak `+0.023·P` kaydırıyor (`D = 8`'de de `+0.0134·P`), `0.01·P` toleransı tutamaz; `D = 10` kalır,
   tolerans `0.03·P`. Test, takım burnunu `nose_r = H/8` seçer (K7 `ρ_h` formülü bu yarıçapla ISO tepe noktasına oturur).
