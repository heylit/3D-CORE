# B1 — `.3dc` proje dosyası şema sürümü ve göç (migration) kuralı

> Durum: **taslak** (kullanıcı onayı bekliyor). Dalga 6, arayüz PR'ı B1 (`/mnt/project-files/yol-haritasi/dalga-6-ve-sonrasi.md`
> bölüm 3). Bu bir **SPEC 37 eki**dir: `fileio/proje.py`'nin sahibi H13 ("SPEC 37" thread'i). SPEC 37 (PR #70) henüz
> `main`'de değil; bu metin PR #70'teki SPEC 37 metnine (`SEMA = 1`, `ProjeError`, `ac` / `kaydet`, okuma denetimleri,
> hoşgörü kuralları) dayanır ve onun birleşmesinden sonra uygulanır.

## Amaç
Eski bir `.3dc` dosyası yeni sürümle **her zaman ya açılır ya da neden açılmadığı söylenir**. Bu adım bitince:
- Dosyanın ve her bölümün şema sürümü (`sema`) okunur; eski sürüm sırayla kayıtlı göç adımlarından geçirilip
  güncel sürüme getirilir, kullanıcıya hangi göçün yapıldığı `uyari` olarak bildirilir.
- Daha yeni bir sürümle yazılmış dosya ya da göç adımı eksik bir bölüm `ProjeError` ile, **hangi bölümün hangi
  sürümden hangi sürüme** getirilemediği yazılarak reddedilir. Hiçbir bölüm sessizce düşürülmez ya da kırpılmaz.
- Göç edilmiş bir proje ilk kez kaydedilirken özgün dosyanın bir yedeği bırakılır; kullanıcı eski sürüme dönebilir.

## Neden
SPEC 37 bugün yalnız `sema: 1` dosyayı okuyor ve `sema > 1`'i reddediyor; bölüm içeriklerinin sürüm yükseltmesini
"bölüm sahibinin işi" diye kapsam dışı bırakıyor. Ama bölüm sahipleri (24, 25, 26, 29, 30 …) göçlerini nereye
yazacağını, sırasını ve geçmiş (geri al) kayıtlarının ne olacağını bilmiyor. Ortak bir kural olmazsa ilk bölüm
değişikliğinde kullanıcının eski projeleri açılmaz ya da daha kötüsü yarım açılır.

## Teori

### 1. İki düzey sürüm
- **Dosya şeması** `proje.json.sema` (`D`): zip düzeni, bildirim alanları, `gecmis.json` biçimi. Sahibi `fileio/proje.py`.
- **Bölüm şeması** `bolumler/<ad>.json.sema` (`S_b`): bölüm içeriğinin biçimi. Sahibi o bölümün ekranı (A3 kaydı).
- Güncel sürümler: `D_g = SEMA` (bu ekte **1 kalır**; ilk gerçek değişiklik bu kuralla yapılır) ve bölüm başına
  `S_g(b)` = o bölüm için kayıtlı göçlerin en büyük hedefi (göç yoksa 1).

### 2. Göç adımı
Bir göç adımı `g = (bolum, kaynak k, uygula, aciklama)` bir belgeyi `k` sürümünden `k + 1`'e taşır. `bolum = ""`
dosya düzeyidir (bildirim + geçmiş biçimi). Kurallar:
- **Saf:** `uygula(belge)` girdiyi değiştirmez, yeni belge döndürür; aynı girdi → kanonik olarak aynı çıktı.
- **Tek adım:** çıktının `sema` alanı tam olarak `k + 1`; değilse `ProjeError`.
- **Kanonik:** çıktı `kanonik()`'ten geçer (`nan` / `inf` → `ProjeError`).
- **Zincir:** `k → S_g` için `k, k+1, …, S_g − 1` adımlarının **hepsi** kayıtlı olmalı; boşluk → `ProjeError`.
  Aynı `(bolum, k)` iki kez kaydedilemez.
- **Geri yön yok:** göç yalnız ileri gider. `S_b > S_g(b)` (daha yeni sürümle yazılmış) → `ProjeError`.

### 3. `ac` sırası
1. SPEC 37 okuma denetimleri (zip, girdi adları, özetler, boyut ve oran sınırları) **göçten önce**, dosyadaki
   baytlar üzerinde. Özet tutmuyorsa göç denenmez.
2. `D > D_g` → `ProjeError("dosya şeması D: bu 3D-CORE en çok D_g okuyabilir; programı güncelleyin")`.
   `D < D_g` → dosya düzeyi zinciri bildirime ve `gecmis`'e uygulanır.
3. Her bölüm `b` için (ada göre sıralı): `b` hiçbir ekranca sahiplenilmiyorsa SPEC 37 hoşgörüsü aynen (olduğu gibi
   korunur, `uyari`). Sahipleniliyorsa `S_b > S_g(b)` → `ProjeError`; `S_b < S_g(b)` → zincir uygulanır.
4. **Geçmiş de göç eder:** her `Kayit`'ın `bolumler[b] = [once, sonra]` belgelerinin `null` olmayanları aynı
   bölüm zincirinden geçirilir. Böylece göçten sonra `geri_al` güncel şemada bir belge geri yükler. Geçmişteki bir
   belgenin göçü hata verirse `ac` başarısız olur (yarım geçmiş yok).
5. **Önbellek düşer:** göç olan bölümlerin girdi özeti değişir; SPEC 37 kuralıyla ilgili önbellek kayıtları zaten
   eşleşmez ve ekrana verilmez. Ek bir kural gerekmez.
6. Her uygulanan zincir için bir `uyari`: `Kontrol(durum="uyari", mesaj="<bolum>: sema k → S_g (<aciklama>; …)")`
   (`bolum = ""` için `"dosya"`). `Proje.goc` alanına `{bolum: (k, S_g)}` yazılır (dosyaya yazılmaz).

Hata mesajı biçimi (bütün `ProjeError`'larda): `"<dosya adı>: <bolum|dosya>: <ne oldu> (sema <bulunan>, beklenen ≤ <güncel>)"`.

### 4. Yedek
`kaydet(p, yol)` çağrısında `p.goc` boş değilse ve `yol`'da var olan dosya `p`'nin açıldığı dosyaysa (aynı yol), üstüne
yazmadan önce özgün baytlar `<ad>.sema<eski D>-<eski bölüm sürümleri özeti>.3dc.yedek` adıyla aynı klasöre kopyalanır
(atomik: `.tmp` + `os.replace`). Yedek zaten varsa ve baytları aynıysa yeniden yazılmaz; farklıysa adına `-2`, `-3` …
eklenir. Yedek yazılamazsa kayıt **yapılmaz** (`ProjeError`); kullanıcının eski dosyası hiçbir durumda yedeksiz ezilmez.
Bir kez kaydedilen projede `goc` boşalır (sonraki kayıtlar yedek üretmez).

### 5. Bölüm sahiplerinin yükümlülüğü
Bir ekran bölüm biçimini değiştiren her PR'da: `S_g(b)`'yi bir artıran göç adımını kaydeder, `tests/fileio/goc/`
altına eski sürümde yazılmış bir uydurma örnek `.3dc` ekler ve onun açılıp güncel sürüme geldiğini test eder (K8).
Bu kural `CLAUDE.md`'ye değil, `fileio/proje.py` docstring'ine ve bu SPEC'e yazılır.

## Dosyalar
- Değişecek: `fileio/proje.py` (göç kaydı, `ac` sırası, yedek), `tests/fileio/test_proje.py` (yalnız yeni testler
  eklenir; SPEC 37 testleri değişmez), `durum/37-proje-kabuk.md` (B1 satırı).
- Yeni: `tests/fileio/test_proje_goc.py`, `tests/fileio/goc/` (uydurma eski sürüm dosyaları, testte üretilir ya da
  küçük ikili örnek olarak eklenir).
- Dokunulmayacak: `tezgah/` (ekranların göç kaydı kendi PR'larında), tüm `*/model.py`, `pyproject.toml`, `DURUM.md`.
  Yeni bağımlılık yok (yalnız standart kitaplık; SPEC 37 K17 aynen geçerli).

## Arayüz
```python
# fileio/proje.py (SPEC 37'ye ek)
@dataclass(frozen=True)
class Goc:
    bolum: str                     # "" = dosya düzeyi
    kaynak: int                    # k → k + 1, k ≥ 1
    uygula: Callable[[dict], dict]
    aciklama: str                  # kullanıcıya gösterilir, boş olamaz

class GocKaydi:
    def kaydet(self, g: Goc) -> None: ...              # çift (bolum, kaynak) → ProjeError
    def guncel(self, bolum: str) -> int: ...           # S_g; kayıt yoksa 1 ("" için SEMA)
    def zincir(self, bolum: str, k: int) -> list[Goc]: ...  # k → guncel; boşluk / k > guncel → ProjeError

GOCLER: GocKaydi                                       # varsayılan, ekranlar içe aktarılırken doldurur

@dataclass(frozen=True)
class Proje:                                           # SPEC 37 alanlarına ek
    ...
    goc: Mapping[str, tuple[int, int]] = {}            # {bolum: (eski, yeni)}; dosyaya yazılmaz
    kaynak_yol: str | None = None                      # ac'ın açtığı dosya; yedek kuralı için

def ac(yol: str | Path, gocler: GocKaydi = GOCLER) -> Proje
def kaydet(p: Proje, yol: str | Path) -> None          # §4 yedek kuralı eklenir
def incele(yol: str | Path, gocler: GocKaydi = GOCLER) -> dict
    # dosyayı açmadan raporlar: {"dosya": (D, D_g), "bolumler": {b: (S_b, S_g)}, "acilir": bool, "neden": str | None}
```

## Kabul kriterleri
Testler sahte göç kayıtlarıyla (`GocKaydi()` testte kurulur) çalışır; gerçek ekran göçü gerekmez.
- [ ] K1 **Güncel dosya değişmez:** göç olmayan bir proje için `ac` → `kaydet` baytları SPEC 37 K2 ile bayt bayt aynı;
  `goc` boş, yedek dosyası oluşmuyor. (`test_proje_goc.py::test_no_migration_no_change`)
- [ ] K2 **Zincir:** `a` bölümü için `1→2`, `2→3` kayıtlı; `sema 1` belge `ac` sonrası `sema 3`, içerik iki adımın
  sırayla uygulanmış hali; `uyari` metni `"a: sema 1 → 3 (…; …)"`; `goc == {"a": (1, 3)}`. (`::test_chain`)
- [ ] K3 **Reddedilenler:** `sema 4 > 3` bölüm; dosya `sema 2 > SEMA`; `1→2` var ama `2→3` yok iken `sema 1`;
  çift kayıt; çıktısı `sema` atlayan (`1 → 3`) adım; girdiyi değiştiren adım (test `deepcopy` ile karşılaştırır);
  `nan` üreten adım → her biri `ProjeError`, mesajda dosya adı, bölüm adı ve iki sürüm numarası.
  (`::test_rejects_*`)
- [ ] K4 **Denetim önce:** özeti tutmayan eski sürüm bölüm → SPEC 37'nin özet hatası (göç fonksiyonu hiç çağrılmaz;
  sayaçla denetlenir). (`::test_checks_before_migration`)
- [ ] K5 **Geçmiş göç eder:** 3 kayıtlı geçmişi olan `sema 1` dosya açılınca her `once` / `sonra` göç etmiş; `geri_al`
  üç kez → her adımda bölüm `sema 3` ve içerik, aynı geçmişin önce `sema 3`'te kurulmuş haliyle kanonik olarak aynı;
  geçmişteki bir belgenin göçü hata verince `ac` başarısız. (`::test_history_migrates`)
- [ ] K6 **Tanınmayan bölüm:** sahipsiz bölüm göçe sokulmaz, SPEC 37 K5 gibi korunur. (`::test_unknown_section_untouched`)
- [ ] K7 **Yedek:** göç edilmiş proje aynı yola kaydedilince klasörde özgün baytlarla birebir aynı bir `.yedek`
  dosyası ve yeni dosya var; ikinci kayıt yeni yedek üretmez; yedek yazımı `monkeypatch` ile hata verince kayıt
  yapılmaz, özgün dosya baytları aynı, `.tmp` kalmaz; farklı yola kaydetmek yedek üretmez.
  (`::test_backup_*`)
- [ ] K8 **Örnek dosyalar:** `tests/fileio/goc/` altındaki her örnek, dosya adındaki sürümden güncele açılıyor
  (bu ekte örnek: sahte `deneme` bölümü, `sema 1`). Bölüm sahipleri kendi PR'larında buraya örnek ekler.
  (`::test_sample_files`)
- [ ] K9 **İnceleme:** `incele` K2, K3 dosyaları için `acilir` ve `neden` doğru; dosyayı değiştirmiyor ve göç
  fonksiyonu çağırmıyor. (`::test_inspect`)
- [ ] Tüm testler yeşil (SPEC 37 testleri dahil, değişmeden), `ruff check .` ve `ruff format --check .` temiz.

## Bağımlılıklar
- SPEC 37 (`fileio/proje.py`, PR #70) `main`'de olmalı. Başka hiçbir şeye bağlı değil.
- Arayüz eki olduğu için kural gereği **ayrı küçük PR + ayrı test oturumu** (CLAUDE.md "Test bağımsızlığı").
- Bunu kullananlar: bölüm biçimini değiştiren her ekran SPEC'i; 54 (kurtarma dosyası aynı `ac` yolundan açılır).

## Kapsam dışı
- Gerçek bir bölüm göçü (ilk göç, biçimi değişen ilk ekranın PR'ında gelir).
- Eski sürüme geri yazma (downgrade), iki sürüm arasında fark gösterme, dallanan geçmiş.
- Uygulama (paket) sürümünü dosyaya yazmak: belirlenimci bayt kuralını (SPEC 37 K2) sürümden sürüme bozar; gerekirse
  Dalga 8'de (semver) ayrıca karar.

## Açık soru
1. Yedek dosya adı biçimi (`<ad>.sema1-<özet8>.3dc.yedek`) uygun mu? Öneri: evet; kısa özet aynı adlı iki farklı
   eski sürümü ayırır.
