# SPEC 61 — Tasarım için imalat (DFM) denetimi

> **Durum: ONAYLANDI** (kullanıcı, 2026-10-18 16:06 UTC, proje sohbetinde yazılı: "Dalga 7 taslakları 57, 58, 59, 61, 62,
> 63, 64 ve 72'yi önerileriyle onaylıyorum."). Açık sorular önerilen cevaplarla kapandı (dosya sonu "Kararlar").
> Önceki durum: taslak. Dalga 7, hat A5 (`/mnt/project-files/yol-haritasi/dalga-6-ve-sonrasi.md`
> bölüm 4).
> Dayanır: SPEC 27 (`cam.features.recognize`: cep, açık bölge, delik, `r_corner`), SPEC 28 / 20 (torna profili),
> SPEC 14 / 41 (bağlama yönleri, 3+2), SPEC 43 (`cam/sim/raymesh.py` ışın aralıkları), SPEC 26 (Tezgah modelleme,
> `/api/ekran/model/yuz/{index}`), B2 + SPEC 66 (malzeme grubu), takım kütüphanesi (`cam.model.ToolLibrary`).

## Amaç
Modelde **işlenemeyecek ya da zor işlenecek** yeri, tasarımcı modeli değiştirdiği anda göstermek. Denetim CAM yolu
üretmez; yalnız geometriye, takım kütüphanesine ve izin verilen bağlama yönlerine bakar. Her bulgu bir yüze ya da noktaya
bağlıdır, ölçülen değeri ve sınırı sayıyla söyler ve bir düzeltme önerir ("iç köşe R2 → en az R3: kütüphanedeki en küçük
uygun freze Ø6, boy 25").

Denetlenenler (ilk sürüm):
1. **İç köşe**: cep / açık bölge iç köşe yarıçapı, cebin derinliğine yetecek boyu olan en küçük frezenin yarıçapından küçük.
2. **Derin dar cep**: gereken takım boy/çap oranı (`L/D`) sınırı aşıyor.
3. **Delik**: derinlik/çap oranı sınırı aşıyor; çap kütüphanedeki matkaplarla açılamıyor; kör delik dibi düz (matkap ucu
   açısı yok).
4. **Erişilemeyen yüz**: izin verilen hiçbir takım yönünden görünmeyen yüz (alttan kesik, undercut).
5. **İnce duvar**: duvar kalınlığı malzeme grubuna göre sınırın altında, ya da yükseklik/kalınlık oranı titreşim riski
   sınırının üstünde.
6. **Torna** (dönel parça): kanal genişliği kütüphanedeki en dar kanal ucundan dar; iç çap derinliği / çap oranı
   delik çubuğu sınırını aşıyor.

## Neden
Bugün işlenemeyen bir köşe ancak CAM aşamasında (SPEC 29 planı hata verince) ya da daha kötüsü tezgâhta fark ediliyor.
Tasarım anında gösterilirse düzeltme bir ölçü değişikliğidir. Ticari CAD'lerin DFM araçları kara kutu kural setleridir;
bizimki açık kurallı, sayılı ve testlidir. Kurallar atölyenin kendi takım kütüphanesine bakar: "piyasada R1 freze var"
değil, "**sizin** kütüphanenizde var mı" sorusunu cevaplar.

## Teori

### 1. İç köşe
Cep `P` (SPEC 27 `PocketFeature`) için derinlik `h = z_top − z_bottom`. Uygun frezeler: `kind ∈ {FLAT, BULL}` ve
`flute_length ≥ h` (SPEC 29'daki uygunluk kuralıyla aynı). `R_min = min(D/2)`. Kural:
- `r_corner = 0` (keskin iç köşe) → **hata**: "keskin iç köşe frezeyle işlenemez (EDM ya da R ≥ R_min)".
- `0 < r_corner < R_min` → **hata**, öneri `R ≥ R_min`.
- `R_min ≤ r_corner < 1.1·R_min` → **uyarı**: takım köşede tam sarılır, titreşim; öneri `r_corner ≥ 1.1·R_min`
  (köşe yarıçapı takım yarıçapından biraz büyük olmalı; oran kural dosyasında).
- Uygun freze yoksa → **hata**: "derinlik h için kütüphanede boyu yeten freze yok".

### 2. Derin dar cep
Cebin dar genişliği `w` (bölgenin içine sığan en büyük dairenin çapı; `cam.offset` ile ofset boşalana kadar ikiye bölme,
tolerans 0.01 mm). Gereken takım çapı `D ≤ w`; gereken boy `h`. `λ = h / D_max(w, h)`; `D_max` kütüphanede `D ≤ w` ve
`flute_length ≥ h` olan en büyük çap. `λ > λ_uyari` (varsayılan 4) uyarı, `λ > λ_hata` (varsayılan 8) ya da uygun takım yok
hata.

### 3. Delik
Delik `d`, derinlik `h` (SPEC 27 `HoleFeature.hole`). `h/d > 10` uyarı ("derin delik: gagalama ya da tabancalı matkap"),
`h/d > 20` hata. Kütüphanede `|D − d| ≤ 0.01` matkap yoksa ve delik toleranslı değilse **bilgi** ("frezeyle helisel
açılır"); `d` kütüphanedeki en küçük frezeden de küçükse hata. Kör delik dibi düzse (konik dip yok) bilgi: düz dipli
matkap ya da freze gerekir.

### 4. Erişilemeyen yüz
İzin verilen yön kümesi `Y`: 3 eksende bağlama başına takım ekseni (SPEC 14 `Setup`), 3+2'de profilin döner eksen
sınırlarından örneklenen yönler (SPEC 41; adım 5°). Yüz `f` üzerinde `N` örnek nokta (üçgen ağından alan ağırlıklı,
sabit tohum). Nokta `p`, `d ∈ Y` yönünden **erişilebilir** ⇔ `p + ε·n` noktasından `+d` yönüne giden ışın parçayı kesmez
(`raymesh.part_intervals`) ve `n·d ≥ 0` (yüz takıma dönük ya da yan). Yüzün erişilebilir oranı `ρ_f`. `ρ_f = 0` hata,
`ρ_f < 0.95` uyarı ("yüzün %X'i hiçbir yönden görünmüyor"). Takımın çapı burada hesaba katılmaz (ilk sürüm): ince bir
yarığın dibi ışınla görünür ama takım giremeyebilir; bunu §2 yakalar.

### 5. İnce duvar
Düzlemsel yüz `f` (alan > `A_min`) üzerindeki örnek noktalarda içe doğru `−n` ışınıyla parçanın içinden çıkış mesafesi
`t(p)` (kalınlık). `t_f = min t(p)`; karşıt yüz düzleme yakın paralel olmalı (`|n_f · n_karsi| > cos 10°`), değilse
nokta sayılmaz (kama biçimli bölgede yanlış alarm olmasın). Sınırlar malzeme grubuna göre (B2 `GRUPLAR`):
- `t_f < t_min(grup)` hata. Varsayılan `t_min`: alüminyum 0.8, çelik 0.5, plastik 1.5 mm.
- Duvar yüksekliği `H` (yüzün takım ekseni boyunca uzunluğu) için `H / t_f > 15` uyarı (titreşim riski).
Bu bir **sezgisel kuraldır**, FEM ya da chatter hesabı değildir (o SPEC 71'dedir); mesaj bunu söyler.

### 6. Torna
Dönel parça (SPEC 28 profil çıkarımı başarılıysa): profildeki kanal genişliği `w_k` < kütüphanedeki en dar kanal ucu
genişliği → hata; iç çap boyu / delik çapı `> 4` uyarı (delik çubuğu sarkması), `> 7` hata (karbür çubuk için yaygın
sınır; kural dosyasında). Profildeki iç keskin köşe → uç burun yarıçapından küçükse hata (SPEC 20 kuralı).

### 7. Kural dosyası
Tüm eşikler `atolye/dfm_kurallari.json`'dadır (repoda, uydurma değil: kaynaklı genel değerler; her eşiğin `kaynak`
alanı vardır). Kullanıcı `yerel_parcalar/dfm-kurallari.json` ile ezebilir; ezilen anahtar raporda "yerel" diye işaretlenir.

### 8. Hız
Denetim modelin her değişikliğinde çalışır. Hedef: SPEC 53'ün referans parçasında (≤ 2000 üçgen) **1 s altı**
(`@pytest.mark.slow` olmayan test). Erişilebilirlik ve kalınlık örnek sayısı `N` buna göre seçilir (varsayılan 64 / yüz).
Süre aşılırsa denetim yarıda kesilmez; sonuç `tamam: false` ve "kısmi" uyarısıyla döner, Tezgah arka planda tamamlar.

## Dosyalar
- **Yeni:** `atolye/dfm.py`, `atolye/dfm_kurallari.json`, `tests/atolye/test_dfm.py`, `tests/atolye/test_dfm_hiz.py`,
  `durum/61-dfm-denetimi.md`.
- **Tezgah:** `tezgah/ekranlar/model.py`'ye **tek uç eklenir**: `GET /api/ekran/model/dfm` (bulgular JSON). Model ekranında
  bulguya tıklanınca ilgili yüz vurgulanır (mevcut `yuz/{index}` ucu). Sahibi "Tezgah uygulaması" thread'idir; bu SPEC'in
  thread'i değişikliği ona dosya olarak gönderir (CLAUDE.md: ortak dosya).
- **Dokunulmayacak:** `cam/model.py`, `cam/features.py` (yalnız `recognize` çağrılır), `geometry/part.py`,
  `pyproject.toml`. Yeni bağımlılık yok.

## Arayüz
```python
# atolye/dfm.py
DERECELER = ("hata", "uyari", "bilgi")
TURLER = ("ic_kose", "derin_cep", "delik", "erisilemez", "ince_duvar", "torna_kanal", "torna_ic_cap", "torna_kose")

@dataclass(frozen=True)
class Bulgu:
    tur: str
    derece: str
    yuzler: tuple[int, ...]           # Part yüz indisleri (Tezgah vurgusu); boş olabilir
    nokta: tuple[float, float, float] | None
    olculen: float
    sinir: float
    mesaj: str                        # Türkçe, sayılı
    oneri: str                        # Türkçe, sayılı; yoksa ""
    kural: str                        # kural dosyasındaki anahtar

@dataclass(frozen=True)
class Rapor:
    bulgular: tuple[Bulgu, ...]       # derece (hata → bilgi), sonra tur, sonra ilk yüz indisi
    tamam: bool
    sure_s: float

def kurallari_oku(yerel: str | Path | None = "yerel_parcalar/dfm-kurallari.json") -> dict
def denetle(part: Part, lib: ToolLibrary, yonler: Sequence[tuple[float, float, float]] = ((0, 0, 1),),
            malzeme_grubu: str | None = None, kurallar: dict | None = None,
            butce_s: float | None = 1.0) -> Rapor
```

## Kabul kriterleri
Uydurma parçalar `tests/atolye/test_dfm.py` içinde build123d ile kurulur (`@pytest.mark.occt`).
- [ ] **K1 İç köşe:** 40×30×10 cep, köşe R2; kütüphane {Ø6 boy 25, Ø10 boy 30} → hata, `olculen = 2`, `sinir = 3`,
  öneri "R ≥ 3"; köşe R3.2 → uyarı (`< 1.1·3`); R4 → bulgu yok; keskin köşe → hata ("EDM"). (`::test_ic_kose`)
- [ ] **K2 Boy yetmez:** aynı cep 30 derin, kütüphane yalnız Ø6 boy 25 → "boyu yeten freze yok" hatası. (`::test_boy`)
- [ ] **K3 Derin dar cep:** 8 genişlik, 40 derinlik yarık; kütüphane Ø8 boy 45 → `λ = 5` uyarı; 70 derinlik ve
  Ø8 boy 75 → `λ = 8.75` hata. (`::test_derin_cep`)
- [ ] **K4 Delik:** Ø5×60 → uyarı (`h/d = 12`); Ø5×110 → hata; Ø5.3 ve kütüphanede yalnız Ø5 matkap → bilgi. (`::test_delik`)
- [ ] **K5 Erişilemeyen yüz:** T-oluk (alttan kesik) parçada `yonler = ((0,0,1),)` → oluk alt yüzleri `erisilemez` hata;
  `(0,0,1)` ve `(0,0,-1)` ile oluk tavanı erişilebilir olur ve o bulgu düşer. Düz blokta bulgu yok. (`::test_erisim`)
- [ ] **K6 İnce duvar:** alüminyum, 0.6 mm duvar → hata (`sinir 0.8`); 2 mm duvar 40 yüksek → uyarı (`H/t = 20`);
  kama biçimli yüzde yanlış alarm yok. (`::test_ince_duvar`)
- [ ] **K7 Torna:** Ø40 milde 2 mm kanal, kütüphanede en dar kanal ucu 3 mm → hata. (`::test_torna`)
- [ ] **K8 Kural ezme:** yerel dosyada `ince_duvar.aluminyum = 0.5` → K6'daki 0.6 duvar bulgusu düşer, rapordaki kural
  "yerel" işaretli; bilinmeyen anahtar `CamError`. (`::test_kural_ezme`)
- [ ] **K9 Belirlenimci:** aynı girdi iki kez → aynı `bulgular` (sıra dahil; örnekleme sabit tohumlu). (`::test_belirlenimci`)
- [ ] **K10 Hız:** SPEC 53 referans parçası (≤ 2000 üçgen) `denetle` < 1 s; `butce_s = 1e-6` ile `tamam = False` ve
  "kısmi" uyarısı, istisna yok. (`test_dfm_hiz.py`)
- [ ] **K11 Tezgah ucu:** `GET /api/ekran/model/dfm` → bulgular JSON, her bulguda `yuzler`; model kurulamazsa 422.
  (`tests/tezgah/test_dfm_ucu.py`; Tezgah sahibi thread uygular)
- [ ] **K12 Bağımlılık:** `atolye/dfm.py` `cam.model`, `cam.features`, `cam.offset`, `cam/sim/raymesh`, `geometry.part`,
  `malzeme.model` (geç import) dışında 3D-CORE paketi içe aktarmıyor. (`test_bagimlilik.py`)
- [ ] Tüm testler yeşil, `ruff check .` ve `ruff format --check .` temiz.

## Bağımlılıklar
SPEC 27, 28, 41, 43 `main`'de. B2 (malzeme grubu; yoksa `malzeme_grubu=None` ve ince duvar için en sıkı sınır kullanılır).
SPEC 53 referans parçası K10 için gerekir (yoksa K10 kendi 2000 üçgenlik uydurma parçasını kurar). Arayüz değişikliği yok.

## Kapsam dışı
- Otomatik düzeltme (köşe yarıçapını modelde değiştirme): bulgu yalnız öneri verir.
- Sac, döküm, kalıp, enjeksiyon DFM'i (sac kapsam dışı; döküm / kalıp ayrı ürün).
- Toleransın işlenebilirliği (IT sınıfı → işlem seçimi): SPEC 34 tolerans zinciriyle ayrı iş.
- Takım çapını hesaba katan tam erişilebilirlik (takım gövdesi süpürmesi): SPEC 44 çarpışma denetimi CAM sonrası yapar.
- Titreşim kararlılığı (chatter lobu): SPEC 71.

## Kararlar (açık sorular; önerilen cevaplarla kapandı, kullanıcı 2026-10-18 16:06 UTC)
Her maddedeki **Öneri** artık karardır.
1. Bulgular modelleme sırasında **canlı** mı gösterilsin, yoksa düğmeyle mi? **Öneri:** canlı; 1 s bütçe aşılırsa arka
   planda tamamlanır ve ekranda "denetleniyor" görünür.
2. Hangi takım kütüphanesi esas alınsın? **Öneri:** Tezgah'ta seçili kütüphane (SPEC 24 / 47); seçili yoksa repodaki
   örnek kütüphane ve rapora "örnek kütüphaneyle denetlendi" uyarısı.
3. "Hata" derecesi modeli kaydetmeyi ya da CAM'e göndermeyi engellesin mi? **Öneri:** hayır; yalnız `tezgaha-gonder`
   yanıtının `kontroller` listesine eklenir (kullanıcı bilerek EDM'ye gönderebilir).
4. Eşiklerin varsayılanları (λ 4 / 8, delik 10 / 20, duvar 0.8 / 0.5 / 1.5, `H/t` 15): **Öneri:** bu değerlerle başla,
   kaynak satırları kural dosyasında; atölye kendi değerlerini yerel dosyayla ezer.
