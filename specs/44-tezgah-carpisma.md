# SPEC 44 — Tezgâh kinematiğiyle çarpışma ve eksen sınırları

> **Durum: ONAYLANDI** (kullanıcı, 2026-10-18 10:38 UTC, proje sohbetinde yazılı onay: "SPEC … 41–44 metinlerini onaylıyorum"). Metin kullanıcı onayı olmadan değişmez. Bağımlılık: SPEC 41 (kinematik), SPEC 43 (malzemeyle çarpışma onda).
> Tezgâh profili SPEC 30 ile ortak: doğrusal sınırlar `MachineProfile.x/y/z`, kinematik `MachineProfile.kinematics`.

## Amaç
Bir çok eksenli programı, tezgâhın hareketli gövdeleriyle (iş mili kafası, döner masa / beşik, kolon, fikstür,
ham malzeme kutusu, tutucu) birlikte zaman boyunca konumlandırıp **gövde–gövde çarpışmasını**, **en az boşluk**
ihlalini ve **eksen sınırı aşımını** hareketin içindeki ilk anıyla bulmak. Takım ve tutucunun kalan malzemeyle
teması 43'te kalır; 44 tezgâhın kendi parçalarına bakar.

## Teori

### Tezgâh modeli
- Halkalar (link): `taban` (sabit), doğrusal eksenler `X, Y, Z`, döner eksenler (41 `RotaryAxis`), `is_mili`, `is_parcasi`.
  Her doğrusal eksenin taşıyıcısı `masa` ya da `kafa`: masa zinciri `taban → (masa doğrusalları) → t1 → t2 → is_parcasi`,
  kafa zinciri `taban → (kafa doğrusalları) → h1 → h2 → is_mili`. Masa doğrusalı `+X` hareketini masayı `−X` yönünde
  götürerek verir (göreli hareket 41 ile aynı kalır: uç–iş parçası ilişkisi değişmez).
- Gövdeler bir halkaya bağlı ilkel şekillerdir, sıfır konumunda makine koordinatında verilir:
  - `Box(center, half, R)`: yönlendirilmiş kutu (OBB), `half > 0`, `R` ortonormal.
  - `Capsule(p, q, r)`: küre süpürülmüş doğru parçası (silindir gövdeler için güvenli taraf yaklaşımı).
- `is_parcasi` halkasına `Setup.stock` ve `Setup.fixtures` kutuları (`Wcs.origin` ile makineye), `is_mili`
  halkasına tutucu ve takım (tutucu basamakları ve sap kapsül olarak, 05 `body_steps`) otomatik eklenir.
- Denetlenen çiftler: kafa zinciri gövdeleri × (masa zinciri + taban) gövdeleri; `ignore` listesindeki çiftler
  hariç. Takım kesen kısmı ve sap × ham malzeme çifti **hariç** (43'ün işi); takım ve tutucu × fikstür dahil.

### Uzaklık
- Kapsül–kapsül: iki doğru parçası arası en kısa uzaklık (kapalı form, paralel durum dahil) eksi yarıçaplar.
- Kapsül–kutu: parça noktası `x(t)`'nin kutuya uzaklığı (kutu çerçevesinde kenetleme ile kapalı form) `t`'de
  dışbükeydir; altın oran araması 1e-9 mm'ye kadar; eksi `r`.
- Kutu–kutu: ayırıcı eksen teoremi (15 eksen). Boşluk denetimi için kutular `clearance/2` büyütülür
  (köşede güvenli taraf). Kesişim varsa uzaklık 0 sayılır, ayırıcı eksen bulunursa o eksendeki boşluk raporlanır
  (gerçek uzaklığın alt sınırı).
- Olay: `distance < clearance` (varsayılan 0 → yalnız temas / girişim).

### Hareket boyunca örnekleme
- İki mod: `tcp=False` → eklemler doğrusal enterpole (`q(t) = q₀ + t·Δq`); `tcp=True` → uç doğrusal, eksen slerp,
  her örnekte 41 `inverse` (önceki örnekten devam).
- Örnek sayısı: hiçbir gövde noktası iki örnek arasında `σ`'dan fazla yer değiştirmez:
  `n = ⌈(|ΔX, ΔY, ΔZ| + Σ_i |Δθ_i|·ρ_i) / σ⌉`, `ρ_i` o eksenin taşıdığı gövdelerin eksene en uzak noktası
  (gövde ve kapsül uç noktalarından), `σ` varsayılan 1 mm. Bir çarpışma `σ`'dan ince değilse kaçırılmaz
  (gövde `σ/2` kalınlığından ince değilse); rapor edilen `t` gerçek ilk temastan en çok bir örnek aralığı sonradır.
- İlk temastan sonra `t` ikiye bölmeyle (bisection) `1e-6` mm hassasiyete indirilir.

### Eksen sınırları
- Doğrusal (`MachineProfile.x/y/z`, `None` → denetlenmez) ve döner (`RotaryAxis.min/max`) sınırlar her örnekte; `tcp=False`'ta eklem
  hareketi doğrusal olduğundan uç noktalar yeterlidir, `tcp=True`'da örneklerde.
- Olay `eksen_siniri`: ekseni, değeri, sınırı ve `t`'si ile.

## Dosyalar
- Yeni: `cam/multiaxis/machine.py` (`Box`, `Capsule`, `Body`, `MachineModel`, JSON), `cam/multiaxis/collision.py`
  (uzaklıklar, örnekleme, `check`), `tests/cam/test_machine_*.py`, `examples/tezgah_ac_besik.json` (uydurma beşik tezgâh),
  `durum/44-tezgah-carpisma.md`.
- Kullanılır (değişmez): `cam/model.py` (`Kinematics`, `MachineProfile`, `Setup`, `Toolpath`), `cam/multiaxis/kinematics.py`,
  `cam/sim` (`body_steps`).
- Dokunulmayacak: tüm `*/model.py`, 05 / 41 / 43 dosyaları, ortak dosyalar.

## Arayüz
`cam.multiaxis.machine`:
- `@dataclass Box(center, half, R=I)`, `@dataclass Capsule(p, q, r)` — geçersiz değer → `CamError`.
- `@dataclass Body(name: str, link: str, shape: Box | Capsule)`.
- `@dataclass MachineModel(profile: MachineProfile, linear_carrier: dict[str, str], bodies: list[Body],
  ignore: list[tuple[str, str]] = [])` — `profile.kinematics` kullanılır (`None` → 3 eksen); bilinmeyen halka / eksen, yinelenen ad → `CamError`; `to_dict` / `from_dict`.
- `poses(model, q, setup: Setup, tool: Tool) -> dict[str, (R (3,3), t (3,))]` — her halkanın makinedeki dönüşümü.
`cam.multiaxis.collision`:
- `dist_capsule_capsule(a, b) -> float`, `dist_capsule_box(c, b) -> float`, `boxes_overlap(a, b, margin=0.0) -> bool`.
- `@dataclass MachineEvent(kind: str, k: int, t: float, a: str, b: str, distance: float, detail: str)` —
  `kind ∈ {"tezgah_carpma", "eksen_siniri"}`; çarpışmada `a, b` gövde adları, sınırda `a` eksen adı.
- `check(model, setup, ops: list[Toolpath], L: float | None = None, tcp: bool = True, sigma=1.0,
  clearance=0.0, prev=None) -> list[MachineEvent]` — `(kind, k, a, b)` başına ilk `t`; `k` 05 adım indeksi kuralıyla.

## Kabul kriterleri
- [ ] K1 Uzaklık: kapsül–kapsül (kesişen, paralel, çapraz, uç–uç) kapalı formla 1e-12; kapsül–kutu (yüz, kenar, köşe
  bölgeleri, 45° döndürülmüş kutu) elle hesapla 1e-9; kutu–kutu SAT (ayrık, değen, iç içe, kenar-kenar 45°) — `tests/cam/test_machine_dist.py`
- [ ] K2 Model: JSON gidip dönüş birebir; bilinmeyen halka, paralel döner eksen, yinelenen gövde adı → `CamError`;
  `poses` sıfır konumunda birim dönüşüm, A = 90°'de beşik gövdesi elle hesapla 1e-12 — `tests/cam/test_machine_model.py`
- [ ] K3 Düşey temas: kafa kutusu alt yüzü `z_h`, masa üst yüzü `z_m`; Z ekseni aşağı inen `G1` → `tezgah_carpma`,
  temas anındaki Z değeri `z_h − z_m` farkından 1e-6; boşluk `clearance = 2` ile temas 2 mm önce — `tests/cam/test_machine_check.py`
- [ ] K4 Dönen fikstür: beşikte yüksek fikstür, A 0°'dan 90°'ye dönerken kolona çarpıyor; temas açısı kapalı form
  (fikstür köşesinin A eksenine uzaklığı `ρ`, başlangıç açısı `φ₀`, kolon yüzüne eksenden uzaklık `w` → `θ* = asin(w/ρ) − φ₀`) `σ/ρ` toleransında ve ikiye bölmeyle 1e-6 mm'de — `test_machine_check.py`
- [ ] K5 TCP modu: aynı uç doğrusu `tcp=True` ve `tcp=False` ile farklı gövde yolu izliyor; birinde çarpışma var,
  diğerinde yok (elle kurulmuş durum) — `test_machine_check.py`
- [ ] K6 Eksen sınırı: A sınırının 1° ötesine giden hareket → `eksen_siniri` doğru `k` ve `t`; doğrusal eksen aşımı;
  sınır içinde kayıt yok — `test_machine_check.py`
- [ ] K7 Temiz program: `examples/tezgah_ac_besik.json` üstünde 3+2 cep (41 K8 yolu) → olay yok; tutucu × fikstür
  temasını bilerek yapan yol → tek kayıt — `test_machine_check.py`
- [ ] Tüm testler yeşil, `ruff check .` ve `ruff format --check .` temiz, 0 "uygulanmamış"; 10 s'den uzun testler `slow`

## Kapsam dışı
- Gerçek tezgâh CAD'inden (STEP) gövde modeli, ağ–ağ çarpışması; esnek kablo / talaş koruma.
- Çarpışmadan kaçınan otomatik yol düzeltmesi (42 yalnız takım gövdesi × parça için yana eğer).
- Postprosesörün kontrolör tarafı (TCP komutları, tekillik kontrolörde nasıl çözülür).
- Montaj (SPEC 07 / 09) ile entegrasyon: fikstürlerin montajdan gelmesi SPEC 10'un işi.
