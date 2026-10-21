# SPEC 54 — Sağlamlık: anlaşılır hata mesajları, hatadan geri al ile kurtarma, otomatik kayıt

> Durum: **taslak** (kullanıcı onayı bekliyor). Dalga 6, hat G7 (`/mnt/project-files/yol-haritasi/dalga-6-ve-sonrasi.md`
> bölüm 3). Dayanır: SPEC 37 (`.3dc`, tek geri al yığını, hata olunca yayılımın bütünüyle geri çevrilmesi; Karar 3:
> "otomatik kurtarma dosyası Dalga 6") ve B1 (şema sürümü, göç). SPEC 37 PR #70 ile henüz açık.

## Amaç
Kullanıcı bozuk bir dosya açtığında, OCCT bir işlemi yapamadığında ya da bir kısıt çözülemediğinde program **çökmez,
yanlış sayı göstermez ve işini kaybettirmez**. Bu adım bitince:
1. Bilinen her hata durumu, ne olduğunu, **hangi nesnede** olduğunu ve **ne yapılabileceğini** söyleyen tek biçimli bir
   mesajla ilgili çekirdek hata sınıfından (`ModelError`, `GeometryError`, `CamError`, `AssyError`, `SketchError`,
   `ProjeError`) gelir; Tezgah bunu bir hata kartında gösterir.
2. Hata veren bir değişiklik projeyi değiştirmez (SPEC 37 K11); kart "Son değişikliği geri al" seçeneği sunar ve geri al
   her zaman son **başarılı** duruma döner.
3. Kaydedilmemiş iş, belirli aralıklarla bir kurtarma dosyasına yazılır; program beklenmedik kapanırsa bir sonraki
   açılışta kullanıcıya kurtarma önerilir. Asıl proje dosyası hiçbir zaman kendiliğinden ezilmez.

## Neden
Altın kural 5 (sessiz hata yok) çekirdekte büyük ölçüde uygulanıyor (ör. `geometry/boolean.py` geçersiz sonucu ve
`IsDone()`'u denetliyor). Ama (a) mesajlar biçim olarak tutarsız: bazıları dosya ya da parça adı vermiyor, bazıları OCCT
istisna metnini olduğu gibi aktarıyor; (b) bozuk girdilerle sistematik bir deneme yok, hangi yolların hâlâ yakalanmamış
`Exception` ya da `nan` ürettiği bilinmiyor; (c) Tezgah'ta bir ekranda çıkan beklenmedik hata sunucuda 500 olarak kalıyor;
(d) kaydedilmemiş iş bir çökmede kayboluyor.

## Teori

### 1. Mesaj biçimi
Her kullanıcıya görünen hata metni üç parçadır, ` — ` ile ayrılır:
```
<nesne>: <ne oldu> — <ne yapılabilir>
```
- `<nesne>`: dosya adı (yol değil, ad), parça / özellik / kısıt / takım / bölüm adı. Birden çok düzey `/` ile:
  `"yatak.step / gövde"`, `"Montaj yatak_grubu / kısıt eş_eksen_2"`.
- `<ne oldu>`: kullanıcı dilinde, sayıları birimleriyle (`r = 12 mm`, `ΔV = 0 mm³`). OCCT ya da Python istisna metni
  burada **yer almaz**; o, istisnanın `__cause__`'unda ve teknik ayrıntıda kalır.
- `<ne yapılabilir>`: en az bir somut öneri (`"yarıçapı 6 mm'nin altına indirin"`, `"dosyayı CAD programınızda STEP AP214
  olarak yeniden dışa aktarın"`, `"kısıtlardan birini kaldırın: eş_eksen_2 ile mesafe_1 çelişiyor"`).
Bir hata sınıfının kendisi değişmez; biçim **metin** kuralıdır. Mevcut mesajlar bu SPEC'te bu biçime getirilir (bkz. §4).

### 2. Hata kartı (Tezgah)
Sunucu, çekirdek hata sınıflarından birini yakalayınca (SPEC 37 kabuğu ve ekran uçları) 422 ile şunu döndürür:
`{hata: {sinif, nesne, ne_oldu, oneri, teknik}}` (`teknik` = istisna zinciri, son 20 satır). Çekirdek hata **dışındaki**
istisna (programlama hatası) 500 kalır ama aynı biçimde: `{sinif: "IcHata", nesne: <uç>, ne_oldu: "beklenmeyen hata",
oneri: "son değişikliği geri alın; hata kaydı <dosya> içinde", teknik}` ve istisna bir hata günlüğüne yazılır
(`~/3D-CORE projeleri/.gunluk/hatalar.log`, en fazla 5 MiB, döner). Her iki durumda proje değişmez (SPEC 37 K11).
Ön yüz kartı: başlık `ne_oldu`, alt satır `nesne`, `oneri`, "Ayrıntı" açılırı (`teknik`) ve "Son değişikliği geri al"
düğmesi (geçmiş boşsa yok).

### 3. Geri al ile kurtarma
SPEC 37 bir değişiklik hata verirse geçmişe kayıt eklemez. Ek kural: hata kartındaki "geri al", **son başarılı kaydı**
geri alır (yani hata verenden önceki değişikliği); hatalı denemenin kendisi geri alınacak bir şey bırakmaz. Ardışık
`k` hata ve sonra `geri_al` = hiç hata olmamış gibi `geri_al`.

### 4. Bozuk girdi koleksiyonu
`tests/saglamlik/bozuk/` altında **uydurma** (gizlilik kuralı) dosyalar ve testte kurulan girdiler. Her durum için
beklenen sınıf ve mesajın `<nesne>` parçası tabloda; mesajın üç parçası olduğu ve `<ne yapılabilir>`'in boş olmadığı denetlenir.

| # | Durum | Nasıl üretilir | Beklenen |
|---|---|---|---|
| 1 | Boş STEP | 0 bayt | `GeometryError`, nesne `bos.step` |
| 2 | Yarıda kesilmiş STEP | geçerli bir blok STEP'inin ilk %60'ı | `GeometryError`, `kesik.step` |
| 3 | Sözdizimi bozuk STEP | `ENDSEC;` silinmiş | `GeometryError` |
| 4 | Katısız STEP | yalnız bir yüz (`SHELL`) | `GeometryError`, öneri "katı" kelimesini içerir |
| 5 | Kapalı olmayan STL | blok STL'inden bir üçgen silinmiş | `GeometryError` |
| 6 | Bozuk montaj STEP | SPEC 07 montajında bir bileşenin şekli silinmiş | `GeometryError`, bileşen adı |
| 7 | Fillet çok büyük | 10 mm kalınlıkta blokta `r = 8` dikey fillet | `GeometryError`, nesne parça adı, öneri sınır içerir |
| 8 | Boş boolean sonucu | `cut(a, a)` | `GeometryError` (boş sonuç), `nan` hacim yok |
| 9 | Çelişkili kısıtlar | eş eksen + paralel olmayan eksenler arası açı 30° | `AssyError`, iki kısıt adı da mesajda |
| 10 | Aşırı kısıtlı kroki | üçgende üç kenar + üç açı | `SketchError`, fazla kısıtın adı |
| 11 | Sıfır boy hareket / takım | `D = 0` takım, sıfır boy yay | `CamError` |
| 12 | `nan` parametre | Tezgah ucuna `"L": "NaN"` | 422, `nan` hiçbir bölüme yazılmaz |
| 13 | Tekil FEM | mesnetsiz çubuk | `ModelError`, öneri "mesnet" içerir |
| 14 | Bozuk `.3dc` | özet tutmuyor / kesik zip / `sema` yeni | `ProjeError` (SPEC 37 K4, B1 K3), dosya ve bölüm adı |
| 15 | Kurtarma dosyası bozuk | §5 dosyasının yarısı | açılışta uyarı, asıl dosya yine açılır |

Bir durum beklenen sınıf yerine başka bir istisna (`Exception`, `IndexError`, OCCT `StdFail_*` …) ya da `nan` üretirse bu
SPEC'in işi o yolu düzeltmektir (§Dosyalar: hangi dosyaya dokunulacağı).

### 5. Otomatik kayıt (kurtarma dosyası)
- **Ne zaman:** proje kirliyse (son kayıttan sonra değişiklik var) ve son kurtarma yazımından beri `T = 60 s` geçtiyse
  ya da `K = 10` yeni geçmiş kaydı eklendiyse. `T`, `K` ayarlanabilir; `T ≥ 10 s`.
- **Nereye:** proje dosyası `P = <klasör>/<ad>.3dc` için `<klasör>/.<ad>.3dc.kurtarma`; hiç kaydedilmemiş proje için
  `~/3D-CORE projeleri/.kurtarma/<ad>-<ilk açılış özeti 8>.3dc.kurtarma`.
- **Ne:** SPEC 37 `kaydet` ile **aynı biçimde** tam bir `.3dc` (geçmiş dahil, önbellek hariç), atomik yazım. Bildirime
  `kurtarma: {kaynak_ozet}` eklenmez; bunun yerine yanına `.kurtarma.json` = `{kaynak: ad, kaynak_ozet: <P'nin baytlarının
  sha256'sı ya da null>, sayac}` yazılır (B1'e dokunmadan).
- **Arka planda:** yazım `Proje` nesnesinin (değişmez, SPEC 37) anlık görüntüsüyle ayrı bir iş parçacığında yapılır;
  kullanıcı işlemi beklemez. Yazım hatası (disk dolu, izin) kullanıcıya bir kez `uyari` olur, uygulama sürer.
- **Temizlik:** kullanıcı `P`'ye başarıyla kaydettiğinde ya da projeyi kaydetmeden kapatmayı onayladığında kurtarma
  dosyası silinir.
- **Açılış:** `P` açılırken kurtarma dosyası varsa ve (a) okunabiliyorsa, (b) `kaynak_ozet` `P`'nin şimdiki baytlarına
  eşitse (ya da `P` yoksa) ve (c) içeriği `P`'den kanonik olarak farklıysa, kullanıcıya üç seçenek: **Kurtar** (kurtarma
  dosyası açılır, kirli işaretli, `P` değişmez), **Yok say** (kurtarma dosyası `.kurtarma.eski`'ye taşınır), **İkisini de
  aç** (kurtarma `<ad> (kurtarılan).3dc` olarak ayrı kaydedilir). `kaynak_ozet` tutmuyorsa (dosya başka yerde değişmiş)
  uyarı metniyle yine sorulur, varsayılan "İkisini de aç". Bozuksa uyarı verilir ve `P` normal açılır (durum 15).
- **Asla:** kurtarma mekanizması `P`'yi yazmaz, silmez, taşımaz.

## Dosyalar
- Yeni: `fileio/kurtarma.py` (§5 kitaplık kısmı: zamanlama kararı, yaz, bul, karşılaştır, temizle; yalnız stdlib +
  `fileio.proje`), `tests/fileio/test_kurtarma.py`, `tests/saglamlik/` (§4 koleksiyonu ve üreticileri,
  `test_bozuk_girdiler.py`, `test_mesaj_bicimi.py`), `durum/54-saglamlik.md`.
- Değişecek (sahipleriyle eşgüdüm gerekir, açık soru 1): §4'te beklenen sınıfı vermeyen yolların bulunduğu dosyalar
  ve mesajı §1 biçiminde olmayan `raise` satırları; şimdiden bilinenler `geometry/boolean.py`, `geometry/fillet.py`,
  `geometry/mesh.py`, `fileio/step_montaj.py`, `assy/solver.py`, `sketch/solver.py`. Yalnız mesaj metni ve eksik
  yakalama eklenir; davranış ve imza değişmez. `tezgah/ekranlar/kabuk.py` (SPEC 37): §2 hata yanıtı ve §5 zamanlayıcı;
  `tezgah/arayuz/src/ekranlar/kabuk.ts`: hata kartı ve kurtarma iletişim kutusu.
- Dokunulmayacak: tüm `*/model.py` ve `geometry/part.py` (hata sınıfları ve imzalar aynen; `Part.from_step` mesajı
  yetersizse sarmalayan çağrı yerinde düzeltilir, gerekirse ayrı arayüz PR'ı), `pyproject.toml`, `DURUM.md`.
  Yeni bağımlılık yok.

## Arayüz
```python
# fileio/kurtarma.py
@dataclass(frozen=True)
class KurtarmaAyari:
    T: float = 60.0          # s, ≥ 10
    K: int = 10              # kayıt, ≥ 1

def kurtarma_yolu(proje_yolu: Path | None, ad: str, ilk_ozet: str) -> Path
def yazmali_mi(simdi: float, son_yazim: float | None, yeni_kayit: int, kirli: bool, a: KurtarmaAyari) -> bool  # saf
def kurtarma_yaz(p: Proje, yol: Path, kaynak_ozet: str | None, sayac: int) -> None   # atomik, .kurtarma.json ile
def kurtarma_bul(proje_yolu: Path) -> dict | None
    # {"yol", "kaynak_tutuyor": bool, "farkli": bool, "okunur": bool, "neden": str | None}
def kurtarma_temizle(proje_yolu: Path) -> None
def kurtarma_eskit(proje_yolu: Path) -> Path          # "Yok say": .kurtarma.eski'ye taşır

# çekirdek hata → kart (tezgah tarafında, saf)
def hata_karti(e: BaseException) -> dict              # {sinif, nesne, ne_oldu, oneri, teknik}; §1'i ayrıştırır
```
Saat ve iş parçacığı yalnız `tezgah/ekranlar/kabuk.py`'de; `fileio/kurtarma.py` zamanı parametre alır (test edilebilir).

## Kabul kriterleri
- [ ] K1 **Bozuk girdi koleksiyonu:** §4 tablosundaki her durum beklenen sınıfla düşüyor; hiçbiri başka istisna, `nan`
  ya da yarım sonuç üretmiyor; mesajda beklenen `<nesne>` var. OCCT gerektirenler `@pytest.mark.occt`.
  (`tests/saglamlik/test_bozuk_girdiler.py`)
- [ ] K2 **Mesaj biçimi:** K1'deki her mesaj `^[^:]+: .+ — .+$` kalıbına uyuyor; `<ne yapılabilir>` en az 3 kelime;
  mesajda OCCT sınıf adı (`Standard_`, `StdFail_`, `BRep`) ve Python izi yok; aynı hata zinciri `__cause__`'da
  korunuyor. (`test_mesaj_bicimi.py`)
- [ ] K3 **Hata kartı:** `hata_karti` K1 hatalarından alanları doğru ayırıyor; çekirdek dışı istisna `IcHata` ve günlüğe
  bir satır; günlük 5 MiB'da dönüyor. Sahte ekranlı kabukta (SPEC 37 K11 düzeni) 422 gövdesi bu biçimde.
  (`tests/tezgah/test_hata_karti.py`, `fastapi` yoksa atlanır)
- [ ] K4 **Geri al ile kurtarma:** değişiklik A (başarılı), B (hata), C (hata) → `geri_al` sonrası proje A'dan önceki
  hale kanonik olarak eşit; geçmiş uzunluğu A'dan sonra 1, hatalardan sonra yine 1. (`test_hata_karti.py::test_undo_after_error`)
- [ ] K5 **Zamanlama (saf):** `yazmali_mi` tablosu: kirli değilse hiçbir zaman; `T` dolunca ya da `K` kayıt olunca evet;
  `T < 10` ayarı `ProjeError`. (`tests/fileio/test_kurtarma.py::test_schedule`)
- [ ] K6 **Kurtarma gidiş-dönüşü:** kurtarma dosyası SPEC 37 `ac` ile açılıyor, bölümler ve geçmiş kirli projeyle aynı;
  `.kurtarma.json` `kaynak_ozet`'i `P`'nin özeti; önbellek yok. (`::test_round_trip`)
- [ ] K7 **Asıl dosya korunur:** her `kurtarma_*` işleminden önce ve sonra `P`'nin baytları aynı (her test denetler);
  `kurtarma_yaz` yarıda kesilince (`monkeypatch`) eski kurtarma dosyası aynı, `.tmp` kalmıyor. (`::test_never_touches_project`)
- [ ] K8 **Açılış kararı:** dört durum (kurtarma yok; var ve aynı içerik; var, farklı, kaynak tutuyor; var, farklı, kaynak
  tutmuyor) ve bozuk kurtarma için `kurtarma_bul` alanları doğru; bozuk olanda `P` yine açılıyor. (`::test_find_*`)
- [ ] K9 **Çökme benzetimi:** alt süreçte kabuk başlatılır, 3 değişiklik yapılır, `T` kısaltılmış ayarla kurtarma yazılınca
  süreç `kill` ile öldürülür; yeni süreçte `kurtarma_bul` `farkli = True`, "Kurtar" sonrası 3 değişiklik ve geçmişleri
  geri geliyor. `@slow`. (`tests/tezgah/test_kurtarma_cokme.py`)
- [ ] K10 **Arka plan:** kurtarma yazımı sürerken (yazıcı testte yavaşlatılır) kabuk uçları yanıt vermeye devam ediyor;
  disk hatası bir kez `uyari` veriyor, uygulama sürüyor. (`test_kurtarma_cokme.py::test_background`)
- [ ] K11 **Ön yüz (vitest + Playwright, yalnız yerelde):** hata kartı `ne_oldu`, `nesne`, `oneri` gösteriyor, "Ayrıntı"
  kapalı başlıyor, "geri al" düğmesi geçmiş boşken yok; kurtarma iletişim kutusunda üç seçenek ve klavyeyle erişim.
  (`tezgah/arayuz/tests/saglamlik.*`)
- [ ] K12 **Bağımlılık:** `fileio/kurtarma.py` yalnız stdlib ve `fileio.proje`; SPEC 37 K17 aynen geçiyor.
- [ ] Tüm testler yeşil (SPEC 37 ve B1 testleri dahil, değişmeden), `ruff check .` ve `ruff format --check .` temiz.

## Bağımlılıklar
- SPEC 37 (`fileio/proje.py`, kabuk) ve B1 `main`'de olmalı. K1'in alt kümeleri ilgili SPEC'lerin (02, 07, 08, 17, 23,
  04, 01) `main`'de olmasına bağlı; hepsi şu an `main`'de.
- Arayüz değişikliği yok. §Dosyalar'daki "Değişecek" listesi başka SPEC'lerin dosyalarıdır: kural 3 gereği bu bir
  istisnadır ve kullanıcı onayı ister (açık soru 1).

## Kapsam dışı
- Dallanan geçmiş, adlı sürümler, geçmişte arama (SPEC 37 kapsam dışı aynen).
- Bulut yedekleme, sürüm kontrolüne otomatik işleme.
- OCCT'nin yapamadığı işlemi başka yoldan yapmak (ör. büyük fillet'i parçalara bölmek): yalnız açıkça raporlanır
  (Dalga 6 bölüm 6: "OCCT'nin sınırı bizim de sınırımız").
- Çökme raporunu bir yere göndermek: günlük yereldir, internete çıkmaz.

## Açık sorular
1. Mesaj biçimini başka SPEC'lerin dosyalarında (`geometry/`, `assy/`, `sketch/`, `fileio/step_montaj.py`) bu SPEC mi
   düzeltsin, yoksa her sahibe ayrı küçük iş mi açılsın? Öneri: bu SPEC düzeltsin, yalnız `raise` metni ve eksik
   yakalama; imza ve davranış değişmez, her dosyanın mevcut testleri değişmeden geçer.
2. `T = 60 s`, `K = 10` varsayılanları uygun mu? Öneri: evet.
