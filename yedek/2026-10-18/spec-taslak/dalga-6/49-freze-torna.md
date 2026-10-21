# SPEC 49 — Torna-freze (mill-turn): C ekseni indeksleme, polar enterpolasyon, Y ekseni, canlı takım

> **Durum: TASLAK** (Dalga 6, hat G2; `yol-haritasi/dalga-6-ve-sonrasi.md` bölüm 3). Kullanıcı onayı bekliyor.
> Bağımlılık (kod): **B0** (`CAxis`, `Turret`, `Move.c`, `Toolpath.coord/cyl_r/station`; "CAM model arayüzü" thread'i, A0 / PR #107'den
> sonra), SPEC 21 (torna G-code, `main`'de), SPEC 22 (torna simülasyonu, `RadialMap`, `main`'de), SPEC 43 (tri-dexel; SPEC metni
> onaylı, kod henüz `main`'de değil), SPEC 30 (blok planı, `main`'de), SPEC 31 (Sinumerik; kod henüz `main`'de değil).
> Hedef tezgâhlar: DMG MORI NTX 3000, NLX 2500 / 700 (canlı takımlı, Y eksenli). Dil sırası: Sinumerik 840D sl → Fanuc / MAPPS.

## Amaç
Torna tezgâhında, iş milini **C ekseni** olarak kullanıp canlı takımla frezeleme ve delme yollarını üretmek, simüle etmek
ve G-code'a yazmak: alında ve çevrede C indeksli delikler, **Y ekseniyle** eksenden kaçık delik ve kama kanalı, alında
**polar enterpolasyonla** (G12.1 / `TRANSMIT`) kontur ve cep, silindir yüzeyinde **silindirik enterpolasyonla**
(G7.1 / `TRACYL`) kanal. Torna işlemleri (SPEC 20–22) ile aynı programda, aynı simülasyonda.

## Teori

### Çerçeveler
Parça çerçevesi: iş mili ekseni `Z`, `C = 0`'da parça `X` ekseni tezgâh `+X`'e (taret tarafına) bakar. C açısında
parçanın bir noktası tezgâhta `p_t = R_z(C)·p_p` (B0). Canlı takım radyal istasyonda takım ekseni tezgâhta `−X`, eksenel
istasyonda `−Z` (alına bakar). Yollar **parça çerçevesinde** üretilir; makine değerleri post ve simülasyonda hesaplanır.

### C indeksleme
Parça çerçevesinde ekseni `d` olan bir özellik (radyal delik: `d = (cos θ, sin θ, 0)`; alında eksenel delik: `d = −Z`,
konum açısı `θ = atan2(y, x)`):
- Radyal istasyon için gereken C: `R_z(C)·d = +X` → `C = −θ (mod 360)`; eksenel istasyonda delik merkezi tezgâh
  `+X` yarıçapına getirilir: `C = −θ`, `X = r = √(x² + y²)` (Y eksenli tezgâhta Y ile de yapılabilir; varsayılan C).
- Açı seçimi: önceki C'ye **en kısa yol** (`ΔC ∈ (−180°, 180°]`); `CAxis.continuous = False` ise yazılacak açı
  `index_step`'e yuvarlanır, yuvarlama hatası `r·|ΔC_yuv|·π/180 > tol` → `CamError` (konum hatası mm cinsinden).

### Polar enterpolasyon (alın frezeleme; Fanuc `G12.1`, Sinumerik `TRANSMIT`)
Parça çerçevesinde `(x, y)` yolu kontrolörde `r = √(x² + y²)`, `C = atan2(y, x)` olur. Kontrolör dönüşümü kendisi yapar;
bizim işimiz (a) yolu kontrol etmek, (b) simülasyonda aynı dönüşümü uygulamak:
- **Merkez tekilliği:** takım merkezinin yolu eksenden `h` kadar geçen bir doğruda, teğet ilerleme `F` [mm/dk] iken
  açısal hız `ω = F·h / r²` en çok `r = h`'de `ω_max = F / h` [rad/dk]. `ω_max > 2π·CAxis.rpm_max` → `CamError`
  (öneri: yolu kısalt ya da ilerlemeyi düşür; otomatik ilerleme düşürme bu SPEC'te yok). Merkezden geçen hareket
  (`h < 1e-9`) → `CamError` (kontrolörlerin çoğu reddeder; Açık soru 2).
- Yaylar polar modda XY yayıdır (G2 / G3 parça çerçevesinde); kontrolöre aynen yazılır.

### Silindirik enterpolasyon (Fanuc `G7.1`, Sinumerik `TRACYL`)
Yol `(s, z, r)` açılmış koordinatta (B0): `C = s / r_ref` [rad], takım ucu tezgâhta `X = r` (radyal istasyon). Kanal
tabanı `r = r_ref − t`. Simülasyon her hareketi `s` boyunca `Δs ≤ arc_tol`-uyumlu alt adımlara böler (yay ölçütü:
çevrede `r_ref·Δφ`).

### Y ekseni: eksenden kaçık delik ve kama
Radyal istasyonda takım ekseni `−X`, merkezi `y = e`'de (Y kursu `MachineProfile.y`). Kaçık delik: ekseni parça `X`'ine
paralel, `y = e` doğrusunda. Kama kanalı: `C` sabit, takım `−X` yönünde `x = R − t`'ye kadar dalar, sonra `Z` boyunca `L`
kadar ilerler (genişlik = takım çapı `b`, uçlar yarım daire).

### Hacim formülleri (kabul testleri için)
Dolu mil yarıçapı `R`, üst yüzeyden derinlik `t` (taban düzlemi `x = R − t`):
- Kama kesiti (genişlik `b`, `b/2 < R`): `A = ∫_{−b/2}^{b/2} (√(R² − y²) − (R − t)) dy
  = (b/2)·√(R² − b²/4) + R²·asin(b / 2R) − b·(R − t)`.
- Kama uçları (iki yarım daire = bir tam disk, yarıçap `b/2`): `V_uç = ∫_{−b/2}^{b/2} 2√(b²/4 − y²)·(√(R² − y²) − (R − t)) dy`.
  Toplam `V = A·L + V_uç` (`L` iki uç merkezi arası boy).
- Kaçık düz tabanlı delik (yarıçap `ρ`, kaçıklık `e`, taban `x = x_b`, delik tamamen malzemede):
  `V = ∫_{−ρ}^{ρ} 2√(ρ² − y²)·(√(R² − (y + e)²) − x_b) dy`. `e = 0` radyal deliktir.
- Tek katlı integraller `scipy.integrate.quad` ile `1e-10` göreli doğrulukta referanstır (test yorumunda yazılır).

### Simülasyon: 22 + 43
Sıralı iki aşama:
1. Torna işlemleri SPEC 22 `RadialMap` üzerinde (değişmez).
2. İlk freze işleminden önce `RadialMap` → `TriDexel` dönüşümü: kutu `[−R, R]² × [zmin, zmax]`, her ışın dönel bölgeyle
   kesilir (Z ışını: `r = √(x² + y²)` sabit; X ve Y ışınları: `r(t)` boyunca dilim dilim). Freze hareketleri parça
   çerçevesinde simüle edilir: tezgâh konumundaki takım `R_z(−C)` ile parçaya çevrilir, sonra 43 `simulate5` kuralları.
   Polar ve silindirik yollar önce parça çerçevesinde kartezyen kirişlere açılır.
- Frezeden **sonra** torna işlemi → `CamError` (ters dönüşüm bu SPEC'te yok; Kapsam dışı).
- Çarpışma: 43'ün `hizli_carpma`, `sap_carpma`; ayna (22 `ayna_carpma`) aynen.

### G-code
Blok planı SPEC 30 kuralıyla; yeni bloklar "Paylaşılan dosyalara ekler" listesindedir.
| İşlev | Sinumerik 840D sl | Fanuc / MAPPS |
|---|---|---|
| C eksenini aç / kapat | `SPOS=<C>` (konumlama), `CAxis.m_on/m_off` varsa yazılır | `CAxis.m_on` (ör. `M45`), `M46` |
| C indeks | `SPOS=DC(<C>)` veya `C=DC(<C>)` | `G0 C<C>` |
| Canlı takım devri | `SETMS(2)` … `M2=3 S2=<n>`, sonra `SETMS` | `M13 S<n>` / tezgâha özgü (profil) |
| Polar | `TRANSMIT` … `TRAFOOF` | `G12.1` … `G13.1` (X çap, C sanal eksen [mm]) |
| Silindirik | `TRACYL(<2·r_ref>)` … `TRAFOOF` | `G7.1 C<r_ref>` … `G7.1 C0` |
Okuyucu bu blokları geri okur; gidiş-dönüşte yol parça çerçevesinde aynı (SPEC 04 toleransı, yazılan ondalık sayısıyla).

## Dosyalar
- Yeni: `cam/millturn/__init__.py`, `cam/millturn/indeks.py` (C açısı, en kısa yol, yuvarlama),
  `cam/millturn/polar.py` (polar / silindirik dönüşüm ve denetim), `cam/millturn/ops.py` (radyal / eksenel delik, kaçık delik,
  kama, alın konturu ve cebi — 03'ün 2D ofset ve cebini çağırır), `cam/sim/millturn.py` (`RadialMap` → `TriDexel`, C dönüşümü,
  sürücü `simulate_mt`), `cam/post/millturn.py` (blok biçimleri), `tests/cam/test_mt_*.py`, `durum/49-freze-torna.md`.
- Kullanılır (değişmez): `cam/model.py` (B0 ile), `cam/ops2d.py`, `cam/offset.py`, `cam/sim/radial.py`, `cam/sim/lathe.py`,
  `cam/sim/tridexel.py` (43), `cam/multiaxis/kinematics.py` (`rotation`), `cam/gcode/lathe.py` (21).
- Paylaşılan dosyalara ekler (sahip thread'ler sırayla yapar, bu SPEC'in PR'ı yapmaz): SPEC 30 `cam/post/blocks.py`'ye
  `CIndex`, `LiveSpindle`, `TransformOn(kind)`, `TransformOff`; `cam/post/check.py`'ye istasyon ve C denetimi; SPEC 31
  biçimleyicisine Sinumerik satırları.
- Dokunulmayacak: tüm `*/model.py`, 22 ve 43'ün mevcut dosyaları (yalnız yeni sürücü), ortak dosyalar.

## Arayüz
- `c_for(feature_axis, station: str, prev: float | None = None) -> float` — derece; `station ∈ {"radyal", "eksenel"}`.
- `polar_check(tp: Toolpath, c_axis: CAxis) -> float` — en büyük açısal hız [dev/dk]; aşım / merkezden geçiş → `CamError`.
- `to_polar(p) -> (r, C)`, `from_cyl(s, z, r, r_ref) -> np.ndarray (3,)` (parça çerçevesi).
- `radial_hole(stock, tool, theta, z, depth, e=0.0, station=…) -> Toolpath`, `axial_hole(stock, tool, r, theta, depth) -> Toolpath`,
  `keyway(stock, tool, theta, z0, z1, t, ap) -> Toolpath`, `face_contour(region, tool, cut, z) -> Toolpath` (`coord = "polar"`),
  `cyl_slot(path_sz, tool, r_ref, t) -> Toolpath` (`coord = "silindirik"`). Takım `LatheTool` / istasyon canlı değil / Y kursu
  dışında `e` → `CamError`.
- `simulate_mt(ops, stock: CylinderStock, machine: MachineProfile, cell=0.5, part=None, …) -> SimResult5` (43 sonuç tipi).
- `post_mt(ops, machine, setup, …) -> str` (30 `post` imzasıyla; `kind = "millturn"` olmayan profil → `CamError`).

## Kabul kriterleri
Testlerde uydurma geometri ve uydurma `ORNEK-NTX` profili; beklenen değerin kaynağı test yorumunda.
- [ ] K1 C indeksleme: 6 radyal delik `θ = 0, 60, …, 300°` → `C = −θ (mod 360)` 1e-12; en kısa yol sırası (`350° → 10°` = +20°);
  `continuous = False`, `index_step = 5°` iken `θ = 12°` → konum hatası `r·2°·π/180` > `tol` → `CamError` — `tests/cam/test_mt_indeks.py`
- [ ] K2 Polar dönüşüm: rastgele (sabit tohum) 1000 nokta `to_polar` → geri 1e-12; doğru `y = h` boyunca `F = 1000`: `polar_check`
  `ω_max = F/h` (rad/dk → dev/dk) rel 1e-9; merkezden geçen doğru ve `ω_max` aşımı `CamError` — `tests/cam/test_mt_polar.py`
- [ ] K3 Silindirik: `s = π·r_ref` → `C = 180°`; çevresel düz kanal yolu açılınca yarıçap `r_ref − t` olan yay üzerinde kirişler,
  kiriş hatası ≤ `arc_tol` — `test_mt_polar.py`
- [ ] K4 Kama hacmi: `R = 20`, `b = 6`, `t = 3.5`, `L = 30` → simüle edilen kaldırılan hacim `A·L + V_uç` (formül + `quad`), tri-dexel
  `Δ = 0.5, 0.25` mm'de `P·Δ·L` mertebesi toleransta, `Δ` yarıya inince hata azalıyor — `tests/cam/test_mt_hacim.py`
- [ ] K5 Delik hacmi: radyal (`e = 0`) ve kaçık (`e = 8`) düz tabanlı delik; eksenel alın deliği `πρ²·depth`; aynı tolerans kuralı;
  Y kursu dışında `e` → `CamError` — `test_mt_hacim.py`
- [ ] K6 22 + 43 birleşimi: önce tornalanmış kademeli mil (22), sonra kama: toplam kaldırılan hacim = torna hacmi (22 formülü) + kama
  hacmi; `RadialMap` → `TriDexel` dönüşümünde hacim 22 hacmine `O(Δ)` eşit; frezeden sonra torna → `CamError` — `tests/cam/test_mt_sim.py`
- [ ] K7 Çarpışma: C indeksli radyal delikte stoktan geçen `G0` → `hizli_carpma`, doğru `k` ve `depth`; ayna bölgesine giren kama
  → `ayna_carpma` — `test_mt_sim.py`
- [ ] K8 Post Sinumerik: polar alın cebi ve C indeksli delik programı beklenen blok dizisini içeriyor (`TRANSMIT`, `TRAFOOF`, `SPOS`,
  `SETMS(2)`); okuyucuyla geri okunan yol aynı (yazılan ondalığa göre tolerans) — `tests/cam/test_mt_post.py`
- [ ] K9 Post Fanuc / MAPPS: aynı programlar `G12.1` / `G13.1`, `G7.1`, `CAxis.m_on/m_off` ile; gidiş-dönüş aynı — `test_mt_post.py`
- [ ] K10 Hatalar: `mill` profili, canlı olmayan istasyon, `LatheTool` ile freze işlemi, bilinmeyen istasyon no, `coord` / takım
  uyumsuzluğu → `CamError` — `tests/cam/test_mt_errors.py`
- [ ] Tüm testler yeşil, `ruff check .` ve `ruff format --check .` temiz, 0 "uygulanmamış"; 10 s'den uzun testler `slow`

## Kapsam dışı
- B eksenli freze kafasıyla eğik işleme (NTX'in 5 eksen modu): 41–42–51 zinciri, `Kinematics` ile; bu SPEC'te kafa yalnız
  radyal / eksenel konumda.
- Alt iş mili ve parça aktarma, çift taretle eş zamanlı kesme, taret / kafa çarpışma geometrisi (44 ailesi).
- Frezeden sonra tornalama (tri-dexel → dönel harita), dönel olmayan parçadan torna profili.
- Kontrolör çevrimleri (Sinumerik `CYCLE83` C eksenli, ShopTurn, Fanuc `G83` yan delme çevrimleri): açılmış `G0/G1` yazılır.
- Diş: SPEC 52. Otomatik ilerleme düşürme (polar merkez yakını), takım ofsetleri / taret ölçüleri.

## Açık sorular
1. NTX 3000 ve NLX'lerin kontrolörü ve C ekseni / canlı takım M kodları? Öneri: örnek profiller uydurma kalır, kullanıcı
   kendi profilini girer; tabloda Fanuc tarafı MAPPS kılavuzundan doğrulanmadan "taslak" sayılır.
   **Karar (koordinatör, 2026-10-18 14:59):** NTX 3000 / NLX kontrolörü MAPPS (Fanuc tabanlı) varsayılır; tablonun
   Fanuc/MAPPS sütunu bu tezgâhlar için geçerlidir.
2. Polar modda merkezden geçen hareket: kontrolör izin veriyorsa `CamError` yerine uyarı mı olsun? Öneri: şimdilik `CamError`.
3. Fanuc `G12.1`'de X'in çap mı yarıçap mı yazıldığı tezgâh parametresine bağlı (ör. Fanuc parametre 5101 ailesi); profilde
   alan gerekebilir (B0'a küçük ek). Öneri: varsayılan çap, kullanıcının tezgâhında kuru çalıştırmayla doğrulanır (SPEC 48).
