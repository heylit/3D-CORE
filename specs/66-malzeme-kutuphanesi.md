# SPEC 66 — Malzeme kütüphanesi ve bağlantıları (BOM, FEM, kesme verisi, maliyet) (Dalga 6, G10)

> Onaylandı: kullanıcı, 2026-10-18 14:52 UTC (Dalga 6 ilk 8 taslak; 2 dakikada itiraz yok, otomatik kabul kuralı 11:14). Bağımlılık: B2 (malzeme arayüzü), SPEC 07 (BOM), SPEC 14 (CAM kurulumu ve kesme verisi).
> Kaynak: `yol-haritasi/dalga-6-ve-sonrasi.md` G10, `yol-haritasi/sinirlar-malzeme-analiz.md` bölüm 2.

## Amaç
Atölyede en çok işlenen malzemeler için **kaynaklı** bir yerleşik kütüphane kurmak, kullanıcının kendi malzemesini
eklemesine izin vermek ve tek malzeme kaydını kullanan yerlere bağlamak:

| Kullanan | Ne alır | Bu SPEC'te |
|---|---|---|
| BOM, kütle, ağırlık merkezi (07) | `rho` | `yogunluk_haritasi`, `kutle_tablosu` |
| FEM (11, 13, 45, 56, 67) | `E`, `ν`, `rho`, `k`, `alpha`, `Rp02` | `fem_malzemeleri` |
| Kesme verisi (14, 29) | takım malzemesine göre `Vc`, `fz` / `fn` | `kesme_tablosu` |
| Kesme kuvveti (32), takım ömrü (59), DFM (61) | `kc11`, `mc`, `taylor`, `iso513` | yalnız `Kutuphane.get` (hesap kendi SPEC'lerinde) |
| Maliyet (58) | `fiyat` | `malzeme_maliyeti` |

Bitince bir montajda her bileşenin malzemesi seçilir (`Component.material`, B2). BOM kütleyi, FEM elastik sabitleri ve
CAM kesme verisini aynı kayıttan okur. Elle sayı yazmak gerekmez.

## Teori

### Veri ilkeleri (uydurma veri yok)
1. Her kayıtta bir `kaynak` satırı bulunur. Kaynak bir standart (ör. EN 10083-2 tablo 7), bir üretici kataloğu ya da bir el
   kitabıdır (yazar, baskı, tablo). Her alan için ayrı kaynak gerekirse satır `;` ile bölünür.
2. Standardın verdiği alt sınır (ör. `Rp0.2 min`) olduğu gibi girilir ve `tipik = False` olur. Aralığın orta noktası
   girildiyse `tipik = True` olur. Tasarım hesabında (67 güvenlik katsayısı) alt sınır kullanılmalıdır. Kayıt hangisinin
   girildiğini söyler; kod seçim yapmaz.
3. Kaynağı bulunamayan alan boş bırakılır (`None`). Tahmin yazılmaz. B2 gereği eksik alan istenince `ModelError` verir.
4. Kesme verisi önerisi (`Vc`, `fz` / `fn`) bir takım üreticisi kataloğunun **başlangıç değeridir**. Tezgâh ve bağlama
   rijitliğine göre kullanıcı düzeltir. Kütüphane bunu "öneri" olarak etiketler.

### Yerleşik malzeme listesi (ilk sürüm, 14 kayıt)
Atölye profiline göre seçildi (DMG MORI freze ve torna, çelik, paslanmaz ve alüminyum ağırlıklı):

| id | name | Standart | grup | iso513 |
|---|---|---|---|---|
| `1.0038` | S235JR | EN 10025-2 | celik | P |
| `1.0577` | S355J2 | EN 10025-2 | celik | P |
| `1.0503` | C45 (+N) | EN 10083-2 | celik | P |
| `1.7225` | 42CrMo4 (+QT) | EN 10083-3 | celik | P |
| `1.2312` | 40CrMnMoS8-6 (P20+S) | EN ISO 4957 | celik | P |
| `1.4301` | X5CrNi18-10 (304) | EN 10088-3 | paslanmaz | M |
| `1.4404` | X2CrNiMo17-12-2 (316L) | EN 10088-3 | paslanmaz | M |
| `EN-GJL-250` | GG25 | EN 1561 | dokme_demir | K |
| `EN-AW-6061-T6` | AlMg1SiCu T6 | EN 573-3, EN 755-2 | aluminyum | N |
| `EN-AW-6082-T6` | AlSi1MgMn T6 | EN 573-3, EN 755-2 | aluminyum | N |
| `EN-AW-7075-T6` | AlZn5,5MgCu T6 | EN 573-3, EN 755-2 | aluminyum | N |
| `CW614N` | CuZn39Pb3 | EN 12164 | bakir | N |
| `Ti-6Al-4V` | Ti Grade 5 | ASTM B348 | titanyum | S |
| `POM-C` | Polioksimetilen kopolimer | üretici veri sayfası | plastik | None |

Liste kullanıcı onayıyla değişir (veri SPEC metni değildir, ama listenin kendisi kapsamdır). Sayısal değerler kod
PR'ında kaynağıyla birlikte girilir; SPEC sayı içermez. Testler değerleri değil, fiziksel olarak makul aralıkları ve
tutarlılığı denetler (K3).

### Kütle ve maliyet
Bileşenin kütlesi `m = ρ · V`'dir. `V` mm³ cinsinden `Part.volume`, `ρ` t/mm³ cinsindendir, sonuç ton olur.
Kilogram için `m_kg = 1000 · m`. Bu, raporlama sınırında yapılan tek gösterim dönüşümüdür ve CLAUDE.md'nin "kodda birim
dönüşümü yok" kuralına istisna değildir: fiyat €/kg biriminde girildiği için maliyet `fiyat · 1000 · m` olarak yazılır ve
fonksiyon adı birimi söyler.

Ham malzeme maliyeti `ham_kutle · fiyat`'tır. Ham kütle bitmiş parçadan değil, stok (`cam.model.Stock`) hacminden
hesaplanır. Bu SPEC yalnız `kütle → €` çevirisini sağlar; kesim payı ve fire SPEC 58'dedir.

## Dosyalar
- **Yeni:**
  - `malzeme/kutuphane.py`, `malzeme/baglanti.py`, `malzeme/yerlesik.json`
  - `tests/malzeme/test_kutuphane.py`, `tests/malzeme/test_baglanti.py`, `tests/malzeme/test_yerlesik_veri.py`
  - `examples/66_montaj_malzemeli.json`
  - `specs/66-malzeme-kutuphanesi.md`, `durum/66-malzeme-kutuphanesi.md`
- **Değişecek:** `malzeme/__init__.py` (yeni adların dışa açılması; B2 paketi).
- **Ortak dosya, ayrı küçük PR:** `pyproject.toml`'a `malzeme/yerlesik.json` için `package-data` satırı. Sahibi
  "Durum tablosu ve kurulum belgeleri" thread'idir; B2'nin `packages.find` satırıyla aynı PR'da olabilir. Testler
  kaynak ağacından okuduğu için o PR olmadan da çalışır.
- **Dokunulmayacak:**
  - `malzeme/model.py` (B2 arayüzü)
  - `assy/bom.py`: `unit_masses(parts, rho: Mapping)` olduğu gibi kullanılır; köprü sözlüğü üretir.
  - `cam/model.py`: `Tool.cutting` sözlüğü köprüden doldurulur, anahtar `Malzeme.id`'dir.
  - `core/`, `mesh/`, `geometry/`, `tezgah/`: malzeme seçici ekranı SPEC 47 ekidir.

Bağımlılık yönü: `malzeme/baglanti.py` → `malzeme.model`, `assy.model`, `assy.bom`, `cam.model`, `core.model`. Bunların
hepsi açık arayüzlerdir. `assy/bom.py`, `model.py` değildir ama SPEC 07'nin yayımlanmış işlevidir; içeri dosya importu
sayılmaz. İnceleme bunu reddederse `bom` yerine yalnız sözlük döndürülür ve çağıran bağlar. `malzeme` paketini hiçbir
paket import etmez, yalnız `analiz` ve `tezgah` gibi üst katmanlar eder.

## Arayüz

### `malzeme/kutuphane.py`
```python
class Kutuphane:
    """Değişmez malzeme kümesi: id → Malzeme. ekle() yeni bir Kutuphane döndürür."""

    def __init__(self, kayitlar: Iterable[Malzeme]): ...  # yinelenen id → ModelError
    def get(self, id: str) -> Malzeme: ...  # bilinmeyen id → ModelError (yakın eşleşmeler mesajda)
    def __contains__(self, id: str) -> bool: ...
    def __iter__(self) -> Iterator[Malzeme]: ...  # id sırasıyla
    def __len__(self) -> int: ...
    def ara(self, metin: str) -> list[Malzeme]: ...  # id, name, standart içinde büyük/küçük harf duyarsız
    def grup(self, grup: str) -> list[Malzeme]: ...  # B2 GRUPLAR dışı → ModelError
    def ekle(self, m: Malzeme) -> "Kutuphane": ...  # m.kullanici True olmalı; id çakışması → ModelError
    def kullanici_kayitlari(self) -> list[Malzeme]: ...


def yerlesik() -> Kutuphane: ...  # malzeme/yerlesik.json (importlib.resources), önbellekli
def kullanici_oku(yol: str | Path) -> list[Malzeme]: ...
def kullanici_yaz(yol: str | Path, kayitlar: Iterable[Malzeme]) -> None: ...  # yalnız kullanici=True kayıtlar
def kutuphane(kullanici_dosyasi: str | Path | None = None) -> Kutuphane: ...  # yerleşik + kullanıcı
```
JSON biçimi: `{"surum": 1, "malzemeler": [Malzeme.to_dict(), ...]}`. Bilinmeyen `surum` → `ModelError`.
`kullanici_oku` `kullanici=False` kayıt bulursa `ModelError` verir (kullanıcı yerleşik kaydı gölgeleyemez).
Yerleşik bir değeri değiştirmek isteyen kullanıcı yeni id ile kopyalar (ör. `1.0503-atolye`).

### `malzeme/baglanti.py`
```python
def bilesen_malzemeleri(assembly: Assembly, kut: Kutuphane) -> dict[str, Malzeme]:
    ...
    # Component.name → Malzeme; malzemesi None olan bileşen → ModelError (adı listelenir)


def yogunluk_haritasi(assembly: Assembly, kut: Kutuphane) -> dict[str, float]:
    ...
    # Component.part → rho (assy.bom.unit_masses'in beklediği anahtar);
    # aynı parça iki bileşende farklı malzemeyle → ModelError; rho yok → ModelError


def kutle_tablosu(assembly: Assembly, parts: Mapping[str, Part], kut: Kutuphane) -> dict[str, float]:
    ...
    # parça kimliği → birim kütle [t]; assy.bom.unit_masses(parts, yogunluk_haritasi(...)) ile aynı sonuç


def fem_malzemeleri(kut: Kutuphane, ids: Iterable[str]) -> list[core.model.Material]: ...
def kesme_tablosu(
    kut: Kutuphane, takim: str, ap: float, ae: float | None = None, ids: Iterable[str] | None = None
) -> dict[str, CuttingData]:
    ...
    # Malzeme.id → CuttingData; bu takım malzemesi için önerisi olmayan kayıt ATLANMAZ, ids verilmişse ModelError,
    # verilmemişse (tüm kütüphane) yalnız önerisi olanlar döner


def malzeme_maliyeti_eur(
    m: Malzeme, kutle_t: float
) -> float: ...  # fiyat · 1000 · kutle_t; kutle_t < 0 → ModelError
```

## Kabul kriterleri
- [ ] **K1** Yerleşik kütüphane yüklenir:
  - 14 kayıt, liste tablosundaki id'ler birebir.
  - Her kayıt B2 tutarlılık kurallarından geçer (yükleme zaten kurar).
  - `kaynak` boş değil.
  - `kullanici = False`.
- [ ] **K2** Zorunlu alanlar: plastik dışındaki her kayıtta `E, nu, rho, Rp02, Rm, k, cp, alpha` dolu. Yerleşik kayıtlarda `fiyat` boştur (D7). Plastik dışı her
  kayıtta `iso513` dolu. `celik`, `paslanmaz`, `dokme_demir`, `aluminyum` grubunun her kaydında `kc11` ve `mc` dolu, en az
  `"karbur"` için bir `kesme` önerisi var.
- [ ] **K3** Makul aralık. Her biri bir test parametresidir; yazım hatası ve birim karışıklığı yakalanır:
  - çelik ve paslanmaz:
    - `E ∈ [190000, 215000]`
    - `rho ∈ [7.7e-9, 8.1e-9]`
    - `k ∈ [12, 60]`
    - `alpha ∈ [1.0e-5, 1.8e-5]`
    - `cp ∈ [4.2e8, 5.2e8]`
  - alüminyum:
    - `E ∈ [68000, 73000]`
    - `rho ∈ [2.6e-9, 2.85e-9]`
    - `k ∈ [110, 210]`
    - `alpha ∈ [2.1e-5, 2.5e-5]`
  - titanyum: `E ∈ [105000, 120000]`, `rho ∈ [4.3e-9, 4.5e-9]`
  - dökme demir: `E ∈ [80000, 140000]`
  - plastik: `E ∈ [1000, 4000]`, `rho ∈ [1.1e-9, 1.5e-9]`
  - hepsi: `kc11 ∈ [300, 3500]`, `mc ∈ [0.1, 0.45]`, kesme önerisinde `Vc ∈ [20, 2000]` m/dk
- [ ] **K4** Arama ve hata:
  - `get("1.0503").name` `"C45"` ile başlar.
  - `ara("6061")` tam bir kayıt döndürür.
  - `ara("c45")` büyük/küçük harf duyarsızdır.
  - `get("1.0505")` `ModelError` verir ve mesajda `1.0503` geçer (yakın eşleşme: `difflib`, standart kütüphane).
  - `grup("tahta")` `ModelError` verir.
- [ ] **K5** Kullanıcı malzemesi (`tmp_path`):
  - `ekle` yeni bir kütüphane döndürür; eskisi değişmez (`len` aynı).
  - `kullanici_yaz` ve sonra `kullanici_oku` gidiş-dönüşü eşittir.
  - `kutuphane(yol)` 15 kayıt verir.
  - Yerleşik id'yle çakışan kullanıcı kaydı `ModelError` verir.
  - `kullanici = False` içeren kullanıcı dosyası `ModelError` verir.
  - `surum = 2` dosyası `ModelError` verir.
- [ ] **K6** BOM bağlantısı: uydurma bir montaj kurulur. Bileşenler:
  - `govde` (`1.0503`, 100×50×20 mm kutu)
  - `kapak` (`EN-AW-6061-T6`, 100×50×5)
  - aynı parçadan ikinci bir `kapak` kopyası

  Beklenen sonuçlar:
  - `kutle_tablosu` `govde` için `rho_C45 · 100000`, `kapak` için `rho_6061 · 25000` verir (göreli 1e-12).
  - Sonuç `assy.bom.unit_masses` ile birebir aynıdır.
  - `total_mass` iki kapak ve bir gövdeyi toplar.
  - Malzemesiz bileşen `ModelError` verir.
  - Aynı parçaya iki farklı malzeme `ModelError` verir.
- [ ] **K7** FEM bağlantısı: `fem_malzemeleri(kut, ["1.0503"])[0]` bir `core.model.Material` döndürür. `name = "1.0503"`;
  `E`, `nu`, `rho` kayıtla aynıdır. SPEC 11 K10 konsol kirişi bu malzemeyle çözülür ve `E = 210000` ile çözülen kirişle
  `δ` oranı `210000 / E_C45`'e eşittir (göreli 1e-9).
- [ ] **K8** Kesme bağlantısı:
  - `kesme_tablosu(kut, "karbur", ap=2, ae=5, ids=["1.0503", "EN-AW-6061-T6"])` iki `CuttingData` döndürür. Anahtarlar id,
    değerler kayıttaki öneri ile `ap` ve `ae`'dir.
  - Sonuç `cam.model.Tool(..., cutting=...)` içine konur ve `Tool.to_dict` / `from_dict` gidiş-dönüşünden geçer.
  - `ids` içinde `"karbur"` önerisi olmayan `POM-C` varsa `ModelError` verir.
  - Takım `"elmas"` ise `ModelError` verir.
- [ ] **K9** Maliyet: `fiyat = 1.5` €/kg ve 0.002 t (2 kg) için `3.0` € (göreli 1e-12). `kutle_t = −1` `ModelError` verir.
  `fiyat` yoksa `ModelError` verir.
- [ ] **K10** Örnek dosya: `examples/66_montaj_malzemeli.json` bir `Assembly.from_dict` girdisidir. Bileşenlerin hepsinde
  `material` vardır ve hepsi yerleşik kütüphanede bulunur.
- [ ] **K11** Bağımlılık yönü: `core`, `cam`, `assy`, `geometry`, `mesh` kaynaklarında `import malzeme` geçmez. OCCT gerekmez,
  çünkü K6 hacmi `Part` yerine `volume` özelliği olan bir test ikamesi ya da `@pytest.mark.occt` ile gerçek kutu kullanır.
  `ruff` temiz.

## Bağımlılık
- **B2:** zorunlu, arayüz PR'ı önce birleşir.
- **SPEC 07** (BOM) ve **SPEC 14** (`CuttingData`, `Tool.cutting`): ikisi de birleşti.
- **SPEC 37** (proje dosyası): `Component.material`'ı taşıması B2'nin işidir. 66 yalnız okur.
- Bu SPEC'i kullananlar:
  - 29: otomatik kesme verisi; `Tool.cutting` anahtarı artık `Malzeme.id`. 29 sahibine not gider.
  - 32, 56, 58, 59, 61, 67.
  - 47: malzeme seçici ekranı.

## Kapsam dışı
- Malzeme seçici ve düzenleyici arayüzü (Tezgah): SPEC 47 eki.
- Fiyatın tarih ve tedarikçiye göre güncellenmesi, döviz: SPEC 58 / Dalga 7 MES bağlantısı.
- Sıcaklığa bağlı özellikler, S-N eğrisi, sertleştirme ve ısıl işlem durumlarının ayrı kayıtları (her durum ayrı id ile
  girilebilir, ama otomatik türetme yok).
- Kesme verisinin tezgâh rijitliğine ve bağlamaya göre düzeltilmesi: SPEC 29 / 32.
- Gerçek şirket verisi: CLAUDE.md gizlilik kuralı. Atölyeye özel fiyat ve kesme değerleri kullanıcı dosyasında kalır.
  Kullanıcı dosyası varsayılan olarak `yerel_parcalar/` altındadır ve repoya girmez.

## Kararlar (onayla kayda geçti)
Taslakta ayrı "açık sorular" bölümü yoktu. Metnin kendi seçtiği yollar geçerlidir:
- **D1** `malzeme/baglanti.py` `assy.bom.unit_masses`'ı doğrudan çağırır (SPEC 07'nin yayımlanmış işlevi). İnceleme
  reddederse yalnız sözlük döndürülür.
- **D2** Standart alt sınırı girilirse `tipik = False`; kod alt sınır / tipik arasında seçim yapmaz.
- **D3** Kaynağı bulunamayan alan `None` kalır; tahmin yazılmaz.
- **D4** `kesme_tablosu`: `ids` verilmişse önerisi olmayan kayıt `ModelError`; verilmemişse yalnız önerisi olanlar döner.
- **D5** Kullanıcı dosyası yerleşik kaydı gölgeleyemez; değiştirmek için yeni id ile kopyalanır.
- **D6** `pyproject.toml` `package-data` satırı ayrı küçük PR'dır ("Durum tablosu ve kurulum belgeleri" thread'i).
- **D7** (kullanıcı, 2026-10-18 15:20 UTC, otomatik kabul): yerleşik kayıtlarda `fiyat` boş kalır, çünkü kaynaklı,
  tarihli ve açık bir çubuk malzeme fiyatı yoktur. Atölye fiyatları `yerel_parcalar/` altındaki kullanıcı dosyasına girilir.
  `fiyat` yoksa `malzeme_maliyeti_eur` `ModelError` verir. K2'nin zorunlu alan listesinden `fiyat` çıkarıldı.
- **D8** Kaynak notları: 1.2312 için `Rp02` ve `Rm` Uddeholm Holdax föyünün (ed. 6, 11.2017) alt sınırlarıdır. CW614N için
  `ν = 0.31`, eşdeğer UNS C38500'ün veri tabanı değeridir. C45, 42CrMo4 ve P20 için `ν = 0.3` EN 1993-1-1'den benzetmeyle
  alınmıştır. EN-GJL-250 için `Rp02` alanına EN 1561'in Rp0.1 alt sınırı girilmiştir. Her biri `kaynak` satırında yazar.
