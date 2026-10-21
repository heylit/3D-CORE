# B0 — CAM Ek 4: torna-freze tezgâhı, silindir stokta frezeleme, 5 eksen yol bilgisi (`cam/model.py` arayüz PR'ı)

> **Durum: TASLAK** (Dalga 6, arayüz PR'ı B0; `yol-haritasi/dalga-6-ve-sonrasi.md` bölüm 3). Kullanıcı onayı bekliyor.
> Bu bir **arayüz metnidir**: yalnız `cam/model.py`'ye alan / sınıf ekler, algoritma yok. `cam/model.py`'nin sahibi
> "CAM model arayüzü" thread'idir; Ek 3 (A0, PR #107) birleşmeden B0'ın kodu başlamaz. Ayrı PR + ayrı test thread'i.
> Bu eki kullananlar: SPEC 49 (torna-freze), 50 (5 eksen kaba / yanak), 51 (5 eksen post), 52 (diş / helis simülasyonu).

## Amaç
`cam/model.py`'nin üç eksikliğini kapatmak, böylece 49–52 paralel yazılabilsin:
1. `MachineProfile` torna-freze tezgâhını (DMG MORI NTX 3000, NLX 2500/700 tipi: C ekseni, Y ekseni, canlı takımlı taret,
   NTX'te B eksenli freze kafası) ve 5 eksen postprosesör seçeneklerini (DMU / DMF serisi) taşıyamıyor.
2. `CylinderStock` üzerinde frezeleme yolu (C açısı, polar / silindirik enterpolasyon, taret istasyonu) ifade edilemiyor.
3. `Toolpath` yolun **ne olduğunu** (kaba / ince / yanak, bırakılan pay, eksen modu) taşımıyor; 50'nin kaba işlemesi,
   51'in TCP / döndürülmüş düzlem kararı ve 53'ün performans ölçümü bu bilgiye ihtiyaç duyuyor.

## Teori (yalnız sözleşmeler)

### Torna-freze koordinatları
Model kuralı değişmez: iş mili ekseni `Z`, torna yolları `y = 0` düzleminde ve `x` yarıçap (`cam/model.py` başlığı).
Torna-freze ekleri:
- **C ekseni** iş milinin açısal konumudur (derece, `+Z`'den bakınca saat yönü tersi pozitif). Parça çerçevesindeki bir
  nokta `p_parça`, C açısında tezgâh çerçevesine `p_tezgâh = R_z(C) · p_parça` ile geçer (41'in `rotation((0,0,1), C)`).
- **Y ekseni** freze takımının merkez yüksekliğini eksenden kaçırır (`y ≠ 0`); kursu `MachineProfile.y` ile verilir.
- **Taret istasyonu:** her istasyon sabit takım (torna) ya da canlı takım (freze/matkap) taşır; canlı takımın yönü
  **radyal** (takım ekseni `−X`) veya **eksenel** (takım ekseni `−Z`, alın tarafı). NTX'in B eksenli kafası
  41'in `Kinematics`'i ile (`B`, taşıyıcı `kafa`) ifade edilir; ayrı alan gerekmez.

### Koordinat modu (frezede)
Silindir stokta bir freze yolunun koordinatları üç biçimde olabilir; simülasyon ve post bunu `Toolpath.coord`'dan okur:
- `kartezyen`: `start/end` parça çerçevesinde `(x, y, z)` (C sabit veya `Move.c` ile indekslenmiş).
- `polar`: alın frezeleme; yol parça çerçevesinde `(x, y, z)` yazılır, kontrolör `r = √(x² + y²)`,
  `C = atan2(y, x)` dönüşümünü yapar (Fanuc `G12.1`, Sinumerik `TRANSMIT`). Dönüşümün kendisi SPEC 49'dadır.
- `silindirik`: silindir yüzeyinde kanal; `start/end = (s, z, r)` — `s` açılmış çevre boyu [mm], `s = r_ref · C[rad]`,
  `r_ref = Toolpath.cyl_r` (Fanuc `G7.1`, Sinumerik `TRACYL`).

### Yol bilgisi (`PathMeta`)
Bilgi alanıdır: yol geometrisini değiştirmez, yalnız taşınır ve doğrulanır. Gidiş-dönüşte (`to_dict` / `from_dict`) kaybolmaz.

## Dosyalar
- Değişecek: `cam/model.py` (yalnız bu ek), `tests/cam/test_model_ek4.py` (test thread'i yazar),
  `cam/gcode/writer.py` (yalnız `_yazilabilir`'e iki satırlık ret koruması: `Move.c` dolu veya `Toolpath.coord ≠ "kartezyen"` →
  `CamError`; PR #60'taki `frame` / `axis` korumasıyla aynı mantık, 3 eksen yazıcısı bu alanları sessizce yok saymasın).
- Dokunulmayacak: `cam/post/*`, `cam/gcode/*` (yukarıdaki koruma dışında), `cam/sim/*`, `cam/multiaxis/*` (49–51 kendi
  PR'larında kullanır), diğer `*/model.py`.

## Arayüz

### Yeni sınıflar
- `@dataclass(frozen=True) CAxis(continuous: bool = True, index_step: float = 0.001, rpm_max: float | None = None,
  m_on: str | None = None, m_off: str | None = None)` — C ekseni. `index_step` derece (> 0); `rpm_max` C modunda iş mili
  dönüş üst sınırı (polar enterpolasyonda açısal hız denetimi, SPEC 49); `m_on/m_off` C eksenini açan / kapatan M kodu
  metni (`"M45"` gibi, tezgâha özgü; `None` → yazılmaz). `continuous = False` → yalnız konumlama (`SPOS`), polar /
  silindirik enterpolasyon yok.
- `@dataclass(frozen=True) TurretStation(no: int, live: bool = False, direction: str = "radyal")` — `no ≥ 1`;
  `direction ∈ {"radyal", "eksenel"}`; `live = False` iken `direction` yok sayılmaz, torna takımının yönü olarak saklanır.
- `@dataclass(frozen=True) Turret(name: str, stations: tuple[TurretStation, ...], live_rpm_max: float | None = None)` —
  istasyon numaraları tekil; canlı istasyon varken `live_rpm_max > 0` zorunlu.
- `@dataclass(frozen=True) MultiAxisPost(tcp: str, swivel: str, vector: bool = False, swivel_data: str | None = None)` —
  `tcp ∈ {"traori", "m128", "tcpm", "g43.4", "g43.5", "yok"}`, `swivel ∈ {"cycle800", "plane_spatial", "g68.2", "yok"}`;
  `vector = True` → eş zamanlı yolda yön vektörü yazılır (Sinumerik `A3= B3= C3=`, Heidenhain `LN … TX TY TZ`,
  Fanuc `G43.5`); `swivel_data`: Sinumerik `CYCLE800` döndürme veri kaydı adı (`_TC`), diğerlerinde `None`.
  Dil uyumu (`controller` ile) `MachineProfile.validate`'te: Sinumerik `{traori, yok} × {cycle800, yok}`, Heidenhain
  `{m128, tcpm, yok} × {plane_spatial, yok}`, Fanuc / Haas `{g43.4, g43.5, yok} × {g68.2, yok}`; GRBL yalnız `yok`.
  `kind = "millturn"` profillerde aynı tablo geçerlidir, ancak torna-freze kontrolörlerinin `G43.5` / `G68.2` / `TRAORI`
  desteği freze kontrolörlerinden farklı olabilir (seçenek paketine bağlı); B0 yalnız dil uyumunu denetler, tezgâhın
  gerçek desteği kullanıcı profilinde doğrulanır (SPEC 48).
- `@dataclass(frozen=True) PathMeta(strategy: str, axis_mode: str = "3", allowance: float = 0.0, allowance_z: float | None = None,
  ap: float | None = None, ae: float | None = None)` — `strategy ∈ {"kaba", "yari_ince", "ince", "yanak", "delik", "dis",
  "kontur", "alin", "kanal"}`, `axis_mode ∈ {"3", "3+2", "5", "torna", "c_indeks", "polar", "silindirik"}`;
  `allowance ≥ 0` (yanal pay, mm), `allowance_z` (taban payı; `None` → `allowance`), `ap, ae > 0` verilirse.
  Eşdeğerlik kuralları (`Toolpath.validate`'te): `axis_mode = "torna"` ⇔ takım `LatheTool`; `axis_mode = "polar"` ⇔
  `Toolpath.coord = "polar"`; `axis_mode = "silindirik"` ⇔ `Toolpath.coord = "silindirik"`. Uyumsuzluk → `CamError`.

### Değişen sınıflar (geriye uyumlu: tüm yeni alanların varsayılanı eski davranış)
- `MachineProfile`:
  - `kind ∈ {"mill", "lathe", "millturn"}`. `"lathe"` doğrulaması `main`'deki kurallarla (A0 / SPEC 40 E1: yalnız `fanuc`,
    `y` / `kinematics` / `presets` / `tool_change_z` yasak) **aynen korunur**. `"millturn"` torna kurallarını miras almaz,
    kendi kuralları vardır: `controller ∈ {"fanuc", "sinumerik"}` (Heidenhain torna-freze Açık soru 3); `y` serbest
    (verilirse Y eksenli); `kinematics` serbest ama yalnız taşıyıcısı `kafa` olan bir `B` ekseni (NTX freze kafası);
    X kursu **çap** olarak (torna kuralı gibi `X_m = 2·x`), X ve Z kursları birlikte verilir (biri varken öteki zorunlu).
  - Yeni alanlar: `c_axis: CAxis | None = None`, `turrets: tuple[Turret, ...] = ()`, `multiaxis: MultiAxisPost | None = None`.
  - Kurallar: `millturn` → `c_axis` ve en az bir `Turret` zorunlu, en az bir canlı istasyon zorunlu; `y` verilirse
    Y eksenli sayılır. `mill` → `c_axis`, `turrets` boş olmalı. `multiaxis` yalnız `kinematics` varken (döner eksen ≥ 1)
    veya `millturn`'de verilir. `_PROFILE_KEYS`, `to_dict`, `from_dict` yeni anahtarları taşır; eski JSON profilleri
    (yeni anahtar yok) aynen okunur.
- `Move`: yeni alan `c: float | None = None` — C açısı [derece], sonlu; yalnız `Toolpath.coord = "kartezyen"` ve takım
  `Tool` (freze) iken geçerli (indeksleme). `polar` / `silindirik` yolda veya takım `LatheTool` iken `Move.c` verilirse
  `Toolpath.validate` → `CamError` (sessiz hata yok).
- `Toolpath`: yeni alanlar
  - `coord: str = "kartezyen"` (`{"kartezyen", "polar", "silindirik"}`),
  - `cyl_r: float | None = None` (`coord = "silindirik"` iken zorunlu, `> 0`; diğerlerinde `None`),
  - `station: int | None = None` (taret istasyonu, ≥ 1; doğrulaması profil bilindiğinde SPEC 49 / 30 `check_machine`'de),
  - `meta: PathMeta | None = None`.
  - `validate` kuralları: `polar` / `silindirik` → `plane = XY`, `frame = None`, takım `Tool` (freze), hiçbir `Move.axis`
    yok; `silindirik`'te yaylar yok (G2/G3 → `CamError`, açılmış düzlemde yay ileride); `Move.c` yalnız `kartezyen`'de.
    `meta.axis_mode = "5"` iken en az bir `Move.axis` dolu olmalı; `"3"` iken hiçbiri dolu olmamalı.
- `Setup`: değişmez. `CylinderStock` zaten kabul ediliyor; frezelemeyle birlikte kullanılabileceği bu ekle yazılı olur.

## Kabul kriterleri
Testler `tests/cam/test_model_ek4.py` (test thread'i, kodu görmeden yazar); uydurma tezgâh adları
(`ORNEK-NTX`, `ORNEK-DMU`), gerçek parametre yok.
- [ ] K1 Geriye uyum: `cam/post/profiles/*.json` profilleri ve mevcut `test_model*.py` değişmeden geçiyor; yeni alansız
  `Toolpath` / `Move` / `MachineProfile` `to_dict` çıktısı yeni anahtarları varsayılan değerle içeriyor ve geri okunuyor.
- [ ] K2 `CAxis`, `TurretStation`, `Turret`: geçerli örnekler kuruluyor; `index_step ≤ 0`, `no < 1`, tekrarlı istasyon no,
  bilinmeyen `direction`, canlı istasyon varken `live_rpm_max` yok → her biri `CamError`.
- [ ] K3 `millturn` profili: `c_axis` yok, taret yok, canlı istasyon yok → `CamError`; `controller` `fanuc` / `sinumerik` dışı,
  `kafa` dışı taşıyıcılı veya `B` dışı döner eksen, X kursu var ama Z yok (ya da tersi) → `CamError`; `mill` profilinde `c_axis`
  veya taret → `CamError`; `lathe` profilinin `main`'deki kuralları değişmeden geçiyor (mevcut testler); geçerli `ORNEK-NTX`
  (Sinumerik, C, Y, iki taret, B kafa `Kinematics`) `to_dict` → `from_dict` eşit.
- [ ] K4 `MultiAxisPost` dil uyumu tablosu: 5 dil × izinli / izinsiz her `tcp` ve `swivel` bileşimi (izinsiz → `CamError`);
  döner eksensiz `mill` profilde `multiaxis` → `CamError`.
- [ ] K5 `Toolpath.coord`: `polar` + `frame` / `Move.axis` / `ZX` düzlemi / `LatheTool` → `CamError`; `silindirik` + `cyl_r`
  yok veya ≤ 0, + G2 hareketi → `CamError`; `kartezyen` + `cyl_r` → `CamError`; `Move.c` sonsuz, `polar` / `silindirik` yolda
  veya `LatheTool` yolunda `Move.c` → `CamError`.
- [ ] K6 `PathMeta`: bilinmeyen `strategy` / `axis_mode`, negatif `allowance`, `ap ≤ 0` → `CamError`; `axis_mode = "5"` ama
  hiç `Move.axis` yok, `"3"` ama `Move.axis` var → `validate` `CamError`; `"torna"` ⇔ `LatheTool`, `"polar"` / `"silindirik"` ⇔
  aynı adlı `coord` eşdeğerlikleri iki yönde (uyumsuzluk → `CamError`); gidiş-dönüşte alanlar birebir.
- [ ] K8 Yazıcı koruması: `cam.gcode.writer` (3 eksen ISO yazıcı) `Move.c` dolu veya `coord ≠ "kartezyen"` olan yolu `CamError` ile
  reddediyor; mevcut yazıcı testleri değişmeden geçiyor.
- [ ] K7 Sonlu değer: tüm yeni sayısal alanlarda `nan` / `inf` → `CamError` (mevcut `_sonlu` kuralı).
- [ ] Tüm testler yeşil, `ruff check .` ve `ruff format --check .` temiz; 10 s'den uzun test yok.

## Kapsam dışı
- Algoritmalar: C indeksleme, `G12.1` / `TRANSMIT` dönüşümü, Y ekseni yolları (SPEC 49); 5 eksen kaba ve yanak (50);
  G-code yazımı (51, 49); simülasyon (49, 52).
- Alt iş mili (karşı iş mili), çift taretin eş zamanlı kesmesi, taret çarpışma geometrisi, punta / yatak.
- Takımın tarete bağlanma ölçüleri (taret ofsetleri): ileride ayrı ek; bu ekte yalnız istasyon numarası.
- `MachineProfile` için gerçek DMG MORI parametreleri: kullanıcı kendi profilini girer, `verified` yalnız kullanıcı
  işaretler (SPEC 30 kuralı).

## Açık sorular
1. NTX 3000 ve NLX'lerin kontrolörü (CELOS / Sinumerik 840D sl mi, MAPPS / Fanuc mu)? `m_on/m_off` ve `MultiAxisPost`
   örnekleri buna göre seçilecek. Öneri: kullanıcı profili girene kadar örnek profiller uydurma kalır.
   **Karar (koordinatör, 2026-10-18 14:59):** NTX 3000 / NLX kontrolörü MAPPS (Fanuc tabanlı) varsayılır; `millturn`
   örnekleri ve `MultiAxisPost` örnekleri Fanuc ailesiyle yazılır.
2. `PathMeta.strategy` listesi 57 (otomatik CAM 2) ile genişleyebilir; şimdilik kapalı liste (bilinmeyen → `CamError`).
3. Heidenhain torna-freze (TNC 640 freze-torna seçeneği) `millturn` dillerine girsin mi? Öneri: hayır; kullanıcının torna-freze
   tezgâhları (NTX, NLX) Sinumerik / Fanuc ailesinde, gerekirse sonra küçük ek.
