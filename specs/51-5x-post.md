# SPEC 51 — 5 eksen postprosesör: döndürülmüş iş düzlemi, takım ucu kontrolü (TCP), ters zaman ilerlemesi

> **Durum: ONAYLI** (Dalga 6, hat G4; kullanıcının 2 dakika kuralıyla 2026-10-18 14:56/14:57 onaylandı).
> Bağımlılık (kod): **B0** (`MachineProfile.multiaxis`, `PathMeta.axis_mode`), SPEC 30 (blok planı, `check_machine`; `main`'de),
> SPEC 31 (Sinumerik / Heidenhain biçimleyicileri; metin onaylı, kod henüz `main`'de değil), SPEC 41 (kinematik, `Frame`,
> `machine_toolpath`; `main`'de), SPEC 42 (`linearize`, `inverse_time`; metin onaylı, kod yok), SPEC 44 (eksen sınırı
> denetimi; metin onaylı, kod yok — yalnız K8 için). Dil sırası: **Sinumerik 840D sl → Heidenhain TNC 640 → Fanuc / MAPPS**.
> Hedef tezgâhlar: DMG MORI DMU 50 / 60 / 75 / 90 (masa-masa B/C ya da kafa-masa), DMF 360.

## Amaç
41–42'nin ürettiği 3+2 ve eş zamanlı 5 eksen yollarını gerçek kontrolör diline yazmak ve kendi okuyucumuzla geri okuyup
aynı uç yolunu ve takım eksenini elde etmek. Üç çıkış biçimi: (1) **döndürülmüş iş düzlemi** (3+2: `CYCLE800`,
`PLANE SPATIAL`, `G68.2`), (2) **TCP açık eş zamanlı** (`TRAORI`, `M128` / `FUNCTION TCPM`, `G43.4` / `G43.5`),
(3) **TCP kapalı eş zamanlı** (makine eksen değerleri + `G93` ters zaman ilerlemesi).

## Teori

### Hangi biçim ne zaman
Yolun `meta.axis_mode`'u (B0) ve profilin `multiaxis` alanı belirler:
| `axis_mode` | `multiaxis` | Çıkış |
|---|---|---|
| `3+2` (yol `frame`'li) | `swivel ≠ yok` | Döndürülmüş düzlem: yerel koordinatlarda 3 eksen blokları |
| `3+2` | `swivel = yok` | 41 `machine_toolpath`: makine koordinatı + sabit açılar (TCP kapalı) |
| `5` | `tcp ≠ yok` | TCP açık: uç konumu WCS'de + açılar (veya `vector = True` ise yön vektörü) |
| `5` | `tcp = yok` | 42 `linearize` + 41 `to_machine` → eklem değerleri, `G93` |
`meta` yoksa: `frame` varsa `3+2`, `Move.axis` varsa `5`, ikisi de yoksa SPEC 30/31 3 eksen yolu.

### Döndürülmüş iş düzlemi
41 `Frame` → açılar:
- **Sinumerik `CYCLE800`**: `_TC = swivel_data`; açılar eksenel modda (sabit X, Y, Z eksenleri etrafında sırayla dönüş)
  41 `xyz_angles(frame)` ile yazılır; döndürme öncesi geri çekme `_ST`, yön seçimi `_DIR` = önceki açıya en kısa (41 `prev`). Tam parametre dizilimi döngü sürümüne
  bağlıdır: biçimleyici bir şablon tablosu kullanır, tablo 840D sl 4.x "SINUMERIK Operate" kılavuzundaki dizilimle
  doğrulanır (Açık soru 1).
- **Heidenhain `PLANE SPATIAL SPA<a> SPB<b> SPC<c> TURN MB MAX FMAX SEQ±`**: `(a, b, c)` = `xyz_angles(frame)`; `SEQ` 41'in
  seçtiği çözüm dalından. Bitişte `PLANE RESET STAY`.
- **Fanuc `G68.2 X Y Z I J K`** (I, J, K = ZXZ Euler, 41 `zxz_angles(frame)`), ardından `G53.1` (döner eksenleri konumla);
  bitişte `G69`.
Yerel bloklar SPEC 30/31'in 3 eksen biçimiyle aynıdır (yaylar yerel XY'de korunur).

### TCP açık eş zamanlı
Uç konumu `p` (WCS) ve eksen `a` her harekette:
- Açı biçimi: `(θ₁, θ₂) = inverse_axes(kin, a, prev)` (41); Sinumerik `TRAORI` + `X Y Z B C`, Heidenhain `M128`
  (veya `FUNCTION TCPM F TCP AXIS POS PATHCTRL AXIS`) + `L X Y Z B C`, Fanuc `G43.4 H<n>` + `X Y Z B C`.
- Vektör biçimi (`vector = True`): Sinumerik `ORIWKS` + `A3= B3= C3=` (`a` bileşenleri), Heidenhain `LN X Y Z TX TY TZ`
  (yüzey normali yerine takım yönü: `TX TY TZ = a`, `M128` ile), Fanuc `G43.5 H<n>` + `I J K`.
- İlerleme uç yolunda mm/dk (`G94`); TCP kontrolörü eklemleri kendisi doğrusallaştırır. Bitiş: `TRAFOOF`, `M129` /
  `FUNCTION RESET TCPM`, `G49`.

### TCP kapalı eş zamanlı ve G93
42 `linearize(tp, kin, wcs, L, tol_p, tol_a)` (`L`: takım ölçü boyu, `Tool.stickout` + tutucu `gauge_length`) → 41
`to_machine` → eklem değerleri `(X, Y, Z, θ₁, θ₂)`; 42 `inverse_time` → `F_inv`. Her `G1`'de `F` zorunludur (`G93` modal
değildir: kontrolörler her blokta F ister). Program sonunda veya `G0`'dan önce `G94`. Sinumerik'te aynı `G93` kelimesi,
Heidenhain'de TCP kapalı eş zamanlı yol desteklenmez (`CamError`: TNC 640 için `M128` kullanılmalı).

### Okuyucu ve gidiş-dönüş
Okuyucu her biçimden `Toolpath` (WCS'de uç konumu + `Move.axis`) kurar:
- Döndürülmüş düzlem → `frame` geri kurulur (açılardan 41 `from_xyz` / `from_zxz`), yerel bloklar aynen.
- TCP açık açı biçimi → `a = forward` döner kısmı (41); vektör biçimi → doğrudan.
- TCP kapalı → `forward(kin, q, L, wcs)` (41) ile uç ve eksen; okuyucu `L`'yi takım kütüphanesinden alır, yoksa `CamError`.
Gidiş-dönüş toleransı yazılan ondalık sayısından türetilir (SPEC 04 kuralı): konum `0.5·10^−d·√3`, eksen açısı
`0.5·10^−d_açı` derece biçiminden yayılan hata.

### Dış yorumlayıcı (LinuxCNC)
CI'daki LinuxCNC `rs274` (PR #47) **TCP kapalı** çıkışı (ISO alt kümesi: `G93`, `A/B/C` sözcükleri, makine koordinatı)
yorumlar; kanonik `STRAIGHT_FEED` / `STRAIGHT_TRAVERSE` değerleri bizim eklem değerlerimizle karşılaştırılır, `G93`
F değerleri aynen. LinuxCNC `G43.4`, `TRAORI`, `M128` yorumlamaz; onlar yalnız kendi okuyucumuzla doğrulanır.

### Denetimler (yazmadan önce)
- 44 eksen sınırı denetimi (yoksa yalnız 41 `RotaryAxis.min/max`); sınır dışı → `CamError` (hareket indeksi, eksen).
- Açı sürekliliği: ardışık iki blokta döner eksen değişimi `> max_jump` (varsayılan 90°) → `CamError` (tekillik geçişi;
  41 kuralı). TCP kapalı yolda 42 `linearize` zorunlu (atlanırsa `CamError`).
- `multiaxis` ile dil uyumsuzluğu B0'da yakalanır; burada yalnız `kinematics` eksen adlarının (B/C, A/C) yazılan sözcüklerle
  aynı olduğu denetlenir.

## Dosyalar
- Yeni: `cam/post/multiaxis.py` (biçim seçimi, açı / vektör üretimi, blok planı ekleri), `cam/post/read_multiaxis.py`
  (okuyucu ekleri), `cam/post/profiles/ornek-sinumerik-5x.json`, `cam/post/profiles/ornek-heidenhain-5x.json`,
  `cam/post/profiles/ornek-fanuc-5x.json` (uydurma kinematik ve kurs, `verified: false`), `tests/cam/test_post5_*.py`,
  `durum/51-5x-post.md`.
- Paylaşılan dosyalara ekler (sahip thread'ler sırayla yapar): SPEC 30 `cam/post/blocks.py`'ye `Swivel(angles, kind)`,
  `SwivelReset`, `TcpOn(kind, vector)`, `TcpOff`, `FeedMode(G93/G94)`, `Rapid` / `Linear`'a isteğe bağlı döner eksen ve
  vektör alanları; SPEC 30 `format_iso.py` ve SPEC 31 biçimleyicilerine bu blokların satırları. Mevcut `test_gcode_multiaxis_reject.py`
  (çok eksenli yolu reddeden koruma) bu SPEC'le birlikte "yalnız `multiaxis` yoksa reddet" olarak güncellenir — test
  thread'i yapar.
- Kullanılır (değişmez): `cam/model.py` (B0 ile), `cam/multiaxis/kinematics.py`, `cam/multiaxis/indexed.py`,
  `cam/multiaxis/linearize.py` (42), 44 denetimi.
- Dokunulmayacak: `cam/gcode/*` (ISO 3 eksen yazıcı ve okuyucu), tüm `*/model.py`, ortak dosyalar.

## Arayüz
- `post5(ops: list[Toolpath], machine: MachineProfile, setup: Setup, tools: ToolLibrary, program_no=1,
  tol_p=1e-3, tol_a=0.05, max_jump=90.0) -> str` — SPEC 30 `post` ile aynı başlık / yorum kuralları; `kinematics`
  yok → `CamError`.
- `swivel_angles(frame: Frame, machine: MachineProfile, prev=None) -> tuple[float, ...]` — dile göre `CYCLE800` /
  `PLANE SPATIAL` / `G68.2` açıları.
- `read_program5(text: str, machine: MachineProfile, tools: ToolLibrary) -> list[Toolpath]` — desteklenmeyen sözcük
  (`TRAORI(2)`, `ORIAXES`/`ORIVECT` dışı yönelim modları, `CYCLE832`, Heidenhain `FN`, Fanuc `G43.4` ile vektör karışımı)
  → `CamError` (satır numarasıyla).

## Kabul kriterleri
Testlerde uydurma kinematikler: AC masa-masa, BC masa-masa (DMU tipi, B 45° eğik eksen dahil), BC kafa-masa; uydurma takım boyları.
- [ ] K1 Biçim seçimi: tablodaki dört satırın her biri beklenen biçimi seçiyor; `meta` yokken çıkarım kuralı; `kinematics` yok →
  `CamError` — `tests/cam/test_post5_select.py`
- [ ] K2 Döndürülmüş düzlem açıları: bilinen çerçeveler (`+Z`, X etrafında 30°, ZXZ (30°, 45°, 60°)) için `CYCLE800`,
  `PLANE SPATIAL`, `G68.2` açıları elle hesaplanan değerlerle 1e-9; `swivel_angles` → `from_xyz` / `from_zxz` → aynı çerçeve 1e-12 —
  `tests/cam/test_post5_swivel.py`
- [ ] K3 3+2 gidiş-dönüş: eğik yüzde cep (41 `Frame`'li yol) üç dilde yazılıp okununca `frame` ve yerel hareketler aynı (ondalık
  toleransı); yaylar yay olarak kalıyor — `test_post5_swivel.py`
- [ ] K4 TCP açık, açı biçimi: 42 tipi yarım küre yolunda (sabit tohumlu yönelimler) Sinumerik `TRAORI`, Heidenhain `M128`,
  Fanuc `G43.4` çıktısı okununca uç konumları ve `Move.axis` aynı (konum ve açı toleransı) — `tests/cam/test_post5_tcp.py`
- [ ] K5 TCP açık, vektör biçimi: aynı yol `A3= B3= C3=`, `LN … TX TY TZ`, `G43.5 I J K` ile; okunan eksen birim ve aynı — `test_post5_tcp.py`
- [ ] K6 TCP kapalı + G93: A masalı 4 eksen analitik durumu (42 K7: `r = 50`, `Δ = 30°`) → yazılan `F` değerleri 42 `inverse_time` ile
  rel 1e-9 (ondalık yuvarlaması içinde), her `G1` satırında `F` var, sonda `G94`; okununca uç yolu `tol_p` içinde — `tests/cam/test_post5_g93.py`
- [ ] K7 LinuxCNC çapraz kontrol: K6 programı ve AC masa-masa rastgele yol `rs274` ile yorumlanınca kanonik eksen değerleri bizim
  eklem değerlerimizle yazılan ondalık toleransında aynı (CI kapsayıcısında; yerelde `rs274` yoksa test atlanır, `skip` nedeni
  yazılı) — `tests/reference/test_post5_linuxcnc.py`
- [ ] K8 Denetimler: eksen sınırı dışı açı, tekillik geçişinde `max_jump` aşımı, TCP kapalı yolda `linearize` atlanmış, Heidenhain'de
  TCP kapalı eş zamanlı, eksen adı uyuşmazlığı → `CamError` (hareket / satır numarasıyla) — `tests/cam/test_post5_errors.py`
- [ ] K9 Okuyucu hataları: desteklenmeyen yönelim modları ve karışık sözcükler `CamError`, satır numarasıyla — `test_post5_errors.py`
- [ ] Tüm testler yeşil, `ruff check .` ve `ruff format --check .` temiz, 0 "uygulanmamış"; 10 s'den uzun testler `slow`

## Kapsam dışı
- Kontrolör yumuşatma / yüksek hız modları (`CYCLE832`, `COMPCAD`, Heidenhain `CYCL DEF 32`, Fanuc AICC `G05.1 Q1`), spline
  çıkışı (`BSPLINE`), `ORICURVE`.
- Tezgâh üreticisine özgü döngü sürümleri için kalibrasyon; kinematik kalibrasyon ölçümü; `TRAORI(2)` ikinci dönüşüm.
- Sinumerik / Heidenhain doğal delik çevrimlerinin döndürülmüş düzlemde kullanımı (31'de de kapsam dışı).
- Torna-freze B kafası çıkışı (NTX): 49 + bu SPEC'in eki, ayrıca.

## Kararlar
1. **Sinumerik `CYCLE800`**: güncel 840D sl (SINUMERIK Operate 4.x) parametre dizilimi varsayılır; kullanıcının DMU / DMF
   tezgâhlarındaki döngü sürümü ve `_TC` veri kaydı adları profil girilene kadar doğrulanmamıştır (örnek profil
   `verified: false`). Koordinatör kararı 2026-10-18 14:59.
2. **Heidenhain TCP**: TNC 640'ta `FUNCTION TCPM F TCP AXIS POS PATHCTRL AXIS` varsayılan; `M128` profilde seçenek
   (B0 `tcp = "tcpm" | "m128"`). Öneri kabul edildi (2 dakika kuralı).
3. **LinuxCNC çapraz kontrol** yalnız TCP kapalı çıkış için; `switchkins` ile TCP'li yorumlama ileride. Öneri kabul edildi.
4. **NTX / NLX denetimi** MAPPS (Fanuc tabanlı) varsayılır; Fanuc dili `G68.2`, `G43.4` / `G43.5`, `G93` ile yazılır.
   Torna-freze B kafası çıkışı kapsam dışı (SPEC 49 eki).
