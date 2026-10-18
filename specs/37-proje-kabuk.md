# SPEC 37 — Tek proje dosyası (`.3dc`) ve uygulama kabuğu: geri al, komut paleti, ekranlar arası iplik

> **Durum: TASLAK** (kullanıcı onayı bekliyor). Onaylanmadan kod, test ve arayüz PR'ı açılmaz.
> Dalga 5, hat H13 (`/mnt/project-files/yol-haritasi/dalga-5-onerisi.md`; kullanıcı 2026-10-18 10:51 UTC Dalga 5'i
> tam kapsamla seçti). Tezgah kabuğu, köprü kuralları, `Kontrol` biçimi ve ön yüz araç zinciri SPEC 24'ten; torna /
> montaj ipliği SPEC 25'ten; model geçmişi SPEC 26'dan gelir, burada tekrar edilmez.
> Prototip yönü: https://claude.ai/artifact/2YA8RRJYuFSpRJyEFMEX8u (konsept; kabul ölçütü değildir).

## Amaç
Tezgah'taki bütün işi (model, freze ve torna işleri, montaj, işlem planı, tezgâh profili, simülasyon önbelleği)
**tek bir `.3dc` dosyasında** kaydedip açmak; bütün ekranlarda **tek bir geri al / yinele** geçmişi; her komutu
bulan bir **komut paleti**; ve bir ekranda yapılan değişikliğin diğer ekranlara **tek iplikle** yayılıp farkının
gösterilmesi. Bu adım bitince örnek "yatak grubu" projesi açılır, palette `L 9.5` yazılınca Enter'a basmadan
torna süresi ve montaj girişimindeki değişim görünür, uygulanır, `Ctrl Z` ile her şey birebir eski haline döner,
`Ctrl S` ile kaydedilen dosya yeniden açılınca aynı durum ve aynı geri al geçmişi gelir.

## Temel ilke (SPEC 24'ten)
**Arayüz mühendislik sayısı hesaplamaz.** Etki kartındaki her sayı ekranların sunucu tarafı `ozet()` çıktısıdır;
ön yüz yalnız sunucudan gelen iki sayının farkını gösterebilir. Kabuk da hesap yapmaz: hangi bölümün kimden
etkilendiğini bilir, yeniden hesabı sırayla ilgili ekrana yaptırır ve önce / sonra özetlerini karşılaştırır.

## Kullanıcı deneyimi: alışılmışın dışında olanlar
Görsel tasarım kabul ölçütü değildir; aşağıdaki **davranışlar** ölçüttür (K14–K16).
1. **Enter'dan önce sonuç.** Palette parametreli bir komut (`L 9.5`, `paso 2`, `genislik 110`) yazılırken sunucu
   değişikliği **önizler** (uygular, ölçer, geri alır) ve palette bir etki kartı belirir: "Torna süresi −4.2 s,
   G-code 212 → 208 satır, mil–yatak girişimi 31.4 → 0 mm³". Kullanıcı değişikliğin bedelini yapmadan görür.
2. **Dalga rozeti.** Bir değişiklik uygulanınca etkilenen her ekranın sekmesinde fark rozeti çıkar (`Torna −4.2 s`,
   `Montaj ✓ girişim yok`); rozete tıklayınca o ekran, değişen öğe seçili açılır. Rozetler bir sonraki
   değişikliğe ya da sekme ziyaretine kadar kalır. Kullanıcı modelde bir ölçüyü değiştirdiğinde işlemenin ve
   montajın ne kadar etkilendiğini sekme çubuğundan okur.
3. **Geri al ekranlar arasıdır.** `Ctrl Z` hangi ekranda olursa olsun projedeki son değişikliği geri alır;
   değişiklik başka bir ekrandaysa kısa bir bildirim "Torna: L 9.5 → 9.0 geri alındı" der ve tıklanınca oraya
   gider. Geri alınan değişikliğin etki kartı ters işaretle gösterilir.
4. **Geri al anında.** Simülasyon gibi pahalı sonuçlar girdilerinin özetiyle (SHA-256) önbelleğe alınır; geri
   alınıp eski bir duruma dönülünce sonuç yeniden hesaplanmaz, önbellekten gelir.
5. **Tek dosya, dürüst dosya.** `.3dc` sıradan bir zip'tir; içindeki JSON'lar bir metin düzenleyicide okunur.
   Aynı proje her kaydedildiğinde bayt bayt aynı dosya çıkar (sürüm kontrolüne uygun). Bozuk bir dosya hiçbir
   zaman yarım açılmaz: hangi girdinin bozuk olduğu söylenir.

## Teori ve veri modeli

### Proje: bölümler, önbellek, geçmiş
Proje, adlı **bölümlerden** oluşan bir JSON belgesidir; her bölümün sahibi bir ekrandır (A3 kaydı, aşağıda).
`fileio/proje.py` bölümlerin içeriğini yorumlamaz; yalnız kanonik JSON olduklarını ve `sema` alanlarını denetler.

| Bölüm | Sahibi (ekran) | İçerik |
|---|---|---|
| `model` | SPEC 26 modelleme | `Model` JSON (SPEC 26) |
| `isler` | SPEC 24 freze | `{ad: {parametreler, kaynak?}}`; freze işlerinin güncel parametreleri |
| `torna_isleri` | SPEC 25 torna | `{ad: {parametreler}}`; torna işlerinin güncel parametreleri |
| `montajlar` | SPEC 25 montaj (`bagimli`: `isler`, `torna_isleri`) | montaj tanımları (ağaç, sıra, bağlar); çözülmüş `Montaj` JSON değil |
| `plan` | SPEC 29 / 47 (varsa) | işlem planı girdileri |
| `tezgah` | SPEC 30 (varsa) | `MachineProfile.to_dict()` |
| `kabuk` | bu SPEC | `{sema: 1, aktif_ekran}` |

Bölümler **girdilerdir**; türetilmiş her şey (yol, G-code, sim, çözülmüş montaj) ya yeniden hesaplanır ya da
önbellektedir. Önbellek kaybı veri kaybı değildir.

### Kanonik JSON ve özet
`kanonik(b) = json.dumps(b, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8")`.
`nan` / `inf` → `ProjeError` (altın kural 5; yazılmaz). Python `float` gösterimi gidiş-dönüş kayıpsızdır.
`ozet(b) = sha256(kanonik(b)).hexdigest()`. İki belge **eşittir** ⇔ kanonik baytları eşittir; geri al / yinele ve
önbellek geçerliliği bu tanımı kullanır.

### Önbellek
`Onbellek = {anahtar: str, girdi_ozeti: str, veri: bytes}`. `anahtar` ekranın verdiği addır (`torna_isleri.kademeli_mil.sim`);
`girdi_ozeti` kabuk tarafından hesaplanır: ekranın sahip olduğu ve girdi aldığı bölümlerin
`ozet({b: belge_b for b in (bolum,) + bagimli})` değeri. Ekran yalnız `{anahtar: veri}` verir. Kabuk `ice_aktar`
çağırırken o ekrana yalnız `girdi_ozeti` güncel girdilerin özetine eşit kayıtları geçirir; ekran bunları kullanır
ya da yok sayıp yeniden hesaplar. Eşleşmeyen kayıt hiçbir zaman ekrana verilmez.
Bellekte en fazla 256 MiB tutulur (en eski kullanılan atılır); dosyaya **yalnız güncel duruma ait** kayıtlar yazılır.

### Geçmiş (geri al / yinele)
```
Kayit   = { etiket: str, ekran: str, bolumler: {ad: [once | null, sonra | null]} }   # null: bölüm yok
Gecmis  = { kayitlar: [Kayit], konum: int }     # 0 ≤ konum ≤ len(kayitlar); geri alınabilecek kayıt sayısı
```
- `uygula(p, etiket, ekran, yeni: {ad: belge | None}) -> Proje`: yalnız kanonik olarak değişen bölümleri kaydeder;
  hiçbiri değişmediyse kayıt **eklenmez**. `konum`'dan sonraki kayıtlar (yinelenebilecekler) silinir, yeni kayıt
  eklenir, `konum` bir artar. En fazla `N = 200` kayıt; aşılınca en eski kayıt atılır.
- `geri_al(p)`: `konum == 0` → `ProjeError("geri alınacak değişiklik yok")`. Aksi halde `kayitlar[konum−1]`'in her
  bölümü `once`'a döner, `konum` bir azalır. `yinele(p)` simetrik (`sonra`'ya); `konum == len` → `ProjeError`.
- Kayıt bölümün tamamını saklar (fark değil): belgeler küçüktür ve tam kopya, geri alma hatasını imkânsız kılar.
- Değişmezler: herhangi bir değişiklik dizisinden sonra `k` kez geri al ve `k` kez yinele, kanonik olarak aynı
  projeyi verir; tüm kayıtlar geri alınınca proje ilk duruma kanonik olarak eşittir.

### `.3dc` dosya biçimi
Standart zip (`zipfile`, yeni bağımlılık yok). Girdi adları **yalnız** şu kalıplara uyar:
```
proje.json                 bildirim (manifest)
bolumler/<ad>.json         kanonik JSON, ad ∈ [a-z0-9_]{1,40}
onbellek/<anahtar>.bin     ikili, anahtar ∈ [a-z0-9_.]{1,80}
gecmis.json                Gecmis, kanonik JSON
```
```
proje.json = { sema: 1, uygulama: "3D-CORE", ad,
               bolumler: {ad: {sema, ozet}},
               onbellek: {anahtar: {girdi_ozeti, boyut, ozet}},
               gecmis: {ozet, konum, sayi} }
```
- **Belirlenimci yazım:** girdiler ada göre sıralı, her girdinin zamanı `1980-01-01 00:00:00`, `ZIP_DEFLATED`
  düzey 6, sabit `external_attr`; bildirimde saat yok. Aynı proje → bayt bayt aynı dosya.
- **Atomik kayıt:** önce aynı klasörde `<ad>.3dc.tmp`'ye yazılır, `fsync`, sonra `os.replace`. Yazım herhangi bir
  aşamada hata verirse eski dosya değişmez ve `.tmp` silinir.
- **Okuma denetimleri** (hepsi `ProjeError`, mesajda girdi adı): zip değil; `proje.json` yok; `sema > 1`; kalıba
  uymayan ya da `..` / mutlak yol içeren girdi adı; bildirimde olup zipte olmayan bölüm; bölüm özeti tutmuyor;
  bölüm kanonik JSON değil; toplam açılmış boyut > 1 GiB ya da bir girdinin sıkıştırma oranı > 200 (zip bombası).
- **Hoşgörülü olanlar** (yükleme sürer, `uyarilar` listesine `Kontrol(durum="uyari")` eklenir): özeti tutmayan
  önbellek girdisi (atılır, yeniden hesaplanır); bildirimde olmayan fazladan girdi (okunmaz, yeniden yazılmaz);
  tanınmayan bölüm (hiçbir ekranın sahiplenmediği; olduğu gibi korunur ve geri yazılır).

### Kabuk: bağımlılık sırası, yayılım, etki
Her ekran (A3 kaydı) sahip olduğu bölümü ve **girdi aldığı** bölümleri bildirir (`bagimli`). Bunlar bölümler
üzerinde yönlü bir grafiktir.
- `sira(ekranlar) -> list[str]`: topolojik sıra; eşit durumda bölüm adına göre alfabetik (belirlenimci). Döngü →
  `ProjeError` (döngüdeki bölümler sırayla mesajda); bilinmeyen bölüme bağımlılık → `ProjeError`.
- **Yayılım:** bölüm kümesi `D` değişince, `D`'nin aşağı akış kapanışı `A` (D'ye doğrudan ya da dolaylı bağlı
  bölümler) topolojik sırayla dolaşılır; `A`'daki her bölüm için sahibi ekranın `ice_aktar(belge, onbellek)`
  çağrısı türetilmiş durumunu yeniden kurar (her biri **bir kez**). Değişiklik kabuktan geldiyse (`degistir`,
  `geri_al`, `yinele`, `ac`) `D`'nin sahipleri de önce aynı sırayla `ice_aktar` alır; ekranın kendi ucundan
  geldiyse (yakalama, aşağıda) ekran durumunu zaten kurmuştur ve yalnız `A` dolaşılır. `D ∪ A` dışındaki
  ekranlara dokunulmaz.
- **Etki:** `Etki = [{bolum, ekran, once: Ozet, sonra: Ozet, fark: {anahtar: sonra − once}}]`, `D ∪ A` sırasıyla.
  `Ozet = {anahtar: float | str}` ekranın `ozet()` çıktısıdır; `fark` yalnız iki tarafta da sayı olan anahtarlar
  için hesaplanır (sunucuda), metin anahtarlar `once` / `sonra` olarak gösterilir.
- **Hata:** yayılım sırasında bir `ice_aktar` çekirdek hatası (`CamError`, `ModelError`, `AssyError`,
  `GeometryError`, `SketchError`, `ProjeError`) fırlatırsa değişiklik **bütünüyle** geri çevrilir: tüm bölümler ve
  ekran durumları değişiklikten önceki haline döner, geçmişe kayıt eklenmez, yanıt 422 ve hata metni + hatayı veren
  bölüm. Yarım yayılmış proje yok.
- **Önizleme:** aynı yol `onizle=True` ile yürür, `Etki` hesaplanır, ardından durum geri çevrilir. Önizleme
  sonrası her bölüm ve geçmiş kanonik olarak öncekinin aynısıdır.

### Değişikliklerin yakalanması
Ekranların mevcut uçları (SPEC 24 `/parametre`, SPEC 25 `/montaj/.../parametre`, SPEC 26 `PUT /api/model` …)
değişmez. Kabuk, A3'ün sağladığı istek sonrası kancasıyla (`kur(app)`) her başarılı (2xx), `GET` olmayan,
`/api/proje` dışındaki `/api/` isteğinden sonra kayıtlı ekranların `disa_aktar()` çıktısını son bilinen proje ile
karşılaştırır; değişen bölümler için yayılımı yürütür ve bir `Kayit` ekler. Etiket istek başlığı
`X-Tezgah-Etiket`'ten (yoksa `"<METOT> <yol>"`), ekran adı isteği karşılayan ekranın kaydından gelir. Hata yanıtı
(4xx / 5xx) kayıt üretmez. Bu sayede ekranlar geri al için hiçbir şey yazmaz.

### Komut paleti eşleştirmesi (ön yüz, saf)
`katla(s)`: Türkçe küçük harf (`toLocaleLowerCase("tr")`), ardından `ı→i, ş→s, ğ→g, ü→u, ö→o, ç→c, â→a, î→i, û→u`.
`eslestir(sorgu, komutlar, son: string[]) -> Komut[]`: sorgu ve aday metinleri (`baslik` + `anahtar_kelimeler`)
katlanır; sorgunun harfleri aday içinde **sırayla** bulunmalıdır (alt dizi), bulunmazsa aday elenir. Puan, yüksek
önce: (1) başlık sorguyla başlar, (2) sorgu bir kelime başında başlıyor, (3) sorgu bitişik geçiyor, (4) alt dizi;
eşitlikte daha kısa toplam boşluk, sonra `son` listesindeki sıra (yakın kullanılan önce), sonra başlık alfabetik.
Boş sorgu: önce `son` (en fazla 8), sonra kalanlar alfabetik.
**Parametreli komut:** komut bir `desen` (`"L <sayı>"` biçiminde, tek sayı yeri) taşıyabilir. Sorgu katlanmış
desen önekine uyar ve ardından bir sayı gelirse komut ilk sıraya çıkar; sayı `.` ya da `,` ondalık ayırıcıyla
okunur (`9,5` = `9.5`), `nan`, `inf`, boş ya da fazladan metin → komut geçersiz gösterilir, önizleme gitmez.

## Mimari ve dosyalar
```
fileio/proje.py                     Proje, Gecmis, kanonik / ozet, kaydet / ac, uygula / geri_al / yinele (yalnız stdlib)
tezgah/ekranlar/kabuk.py            Kabuk ekranı: sira, yayılım, Etki, değişiklik yakalama, /api/proje uçları (A3 kaydı)
tezgah/ornekler_37.py               Örnek proje: SPEC 25 "yatak grubu" + SPEC 24 flanş işi tek .3dc'de (uydurma geometri)
tezgah/arayuz/src/ekranlar/kabuk.ts Proje çubuğu, komut paleti, etki kartı, sekme rozetleri, genel kısayollar (A3 kaydı)
tezgah/arayuz/src/ekranlar/kabuk_ara.ts  katla, eslestir, desen ayrıştırma (saf, vitest)
tests/fileio/test_proje.py          (fileio; FastAPI'siz, OCCT'siz)
tests/tezgah/test_kabuk.py          (sahte ekranlarla; FastAPI TestClient)
tests/tezgah/test_kabuk_iplik.py    (gerçek 24/25 ekranlarıyla; @pytest.mark.slow, @pytest.mark.occt)
tezgah/arayuz/tests/kabuk.test.ts, kabuk.e2e.spec.ts
durum/37-proje-kabuk.md
```
- `fileio/proje.py` → yalnız standart kitaplık (`json`, `zipfile`, `hashlib`, `os`, `pathlib`, `re`, `dataclasses`).
  `cam`, `assy`, `geometry`, `tezgah` import etmez. Hata sınıfı `ProjeError(ValueError)` bu dosyadadır.
- `tezgah/ekranlar/kabuk.py` → `fileio.proje` ve A3 kayıt arayüzü; başka ekranların iç dosyalarını import etmez
  (SPEC 24 K9 kuralı). Çekirdek hata sınıfları yalnız `*/model.py`'lerden.
- **Dokunulmayacak:** `tezgah/sunucu.py`, `tezgah/arayuz/src/` altındaki mevcut dosyalar, `*/model.py`,
  `pyproject.toml`, `DURUM.md`, `docs/yol-haritasi.md`, diğer SPEC'lerin dosyaları. Kabuk kendini yalnız A3 kaydıyla
  ekler. A3'te eksik bir kanca çıkarsa burada yazılmaz; A3 sahibine ek olarak iletilir.
- Yeni bağımlılık yok.

## A3'ten beklenen kayıt arayüzü
Bu SPEC A3'ün (Tezgah ekran kaydı, sahibi "Tezgah uygulaması" thread'i; metin `/mnt/project-files/yol-haritasi/a3-ekran-kaydi.md` sürüm 2) şu arayüzü sunmasına dayanır. Bir bölümün tek sahibi vardır (A3 doğrular). Adlar A3
PR'ında farklı çıkarsa A3'ünkiler geçerlidir; anlam aynı kalmalıdır.

**Python** (`tezgah/ekranlar/__init__.py` ya da A3'ün seçtiği kayıt modülü):
```python
@dataclass(frozen=True)
class Ekran:
    ad: str                                  # "freze", "torna", "montaj", "model", "kabuk"
    baslik: str
    router: APIRouter | None
    bolum: str | None = None                 # sahip olduğu proje bölümü; None = durumsuz ekran
    bagimli: tuple[str, ...] = ()            # girdi aldığı bölümler
    disa_aktar: Callable[[], dict] | None = None      # bölümün güncel belgesi (sema alanlı, kanonik JSON'a uygun)
    ice_aktar: Callable[[dict, Mapping[str, bytes]], None] | None = None
                                             # belge + geçerli önbellek kayıtları → türetilmiş durumu kur; hata → durum değişmez
    ozet: Callable[[], dict[str, float | str]] | None = None   # etki kartı ölçüleri
    onbellek: Callable[[], dict[str, bytes]] | None = None     # pahalı sonuçlar {anahtar: veri} (isteğe bağlı)
    kur: Callable[[FastAPI], None] | None = None      # uygulama kurulurken bir kez (kabuk ara katmanı için)

def ekranlar() -> list[Ekran]
```
Beklenen davranışlar: (a) `ice_aktar` atomiktir: hata fırlatırsa ekranın durumu çağrıdan önceki gibidir;
(b) `ice_aktar(disa_aktar(), {})` durumu değiştirmez ve `disa_aktar()` aynı kanonik belgeyi yeniden verir;
(c) bağımlı bir ekran (ör. montaj) girdisini (ör. `torna_isleri`) kendi belleğinden değil, `ice_aktar` sırasında
paylaşılan duruma bakarak okur. Bunun için A3'ün ekranlara verdiği bir `paylasilan_bolum(ad) -> dict` okuyucusu
yeterlidir; SPEC 25'in "montajdan yapılan değişiklik `GET /api/is/...`'te de görünür" kuralı bu yolla korunur.

**TypeScript** (`src/ekranlar/kayit.ts` ya da A3'ün seçtiği modül):
```ts
interface Ekran {
  ad: string; baslik: string; kisayol?: string;           // sekme ve "1"/"2"/"3" tuşları
  yukle(kap: HTMLElement): void | Promise<void>;
  tazele?(): Promise<void>;                               // sunucu durumu dışarıdan değişti (geri al, aç)
  komutlar?(): Komut[];
  sec?(oge: string): void;                                // rozet / bildirim tıklanınca ilgili öğeyi seç
}
interface Komut {
  kimlik: string; baslik: string; anahtar_kelimeler?: string[]; ekran?: string; kisayol?: string;
  desen?: string;                                         // "L <sayı>"
  calistir(sayi?: number): Promise<void>;
  yama?(sayi: number): { bolum: string; isaretci: string; deger: unknown }[];  // önizleme için (JSON Pointer)
}
```
Ayrıca: `api.ts`'te değiştiren her isteğe `X-Tezgah-Etiket` başlığı eklenebilmesi ve değişiklik sonrası abonelik
(`degisiklikSonrasi(cb)`); sekme rozeti (`rozet(ekran, metin | null)`); `Ctrl K`, `Ctrl Z`, `Ctrl Shift Z`, `Ctrl Y`,
`Ctrl S`, `Ctrl Shift S`, `Ctrl O` tuşlarının yalnız kabuğa ait olması (SPEC 24'ün komut çubuğu ve SPEC 26'nın geri
alı bu SPEC'te kabuğun paletine ve geçmişine devredilir; davranışları korunur, bkz. Açık soru 1).

## Arayüz

### `fileio/proje.py`
```python
SEMA = 1
UZANTI = ".3dc"
GECMIS_SINIRI = 200

class ProjeError(ValueError): ...

@dataclass(frozen=True)
class Onbellek:
    girdi_ozeti: str
    veri: bytes

@dataclass(frozen=True)
class Gecmis:
    kayitlar: tuple[dict, ...] = ()
    konum: int = 0

@dataclass(frozen=True)
class Proje:
    ad: str
    bolumler: Mapping[str, dict]                 # her belge "sema" alanı taşır (int ≥ 1)
    onbellek: Mapping[str, Onbellek] = {}
    gecmis: Gecmis = Gecmis()
    uyarilar: tuple[dict, ...] = ()              # SPEC 24 Kontrol biçimi; dosyaya yazılmaz

def kanonik(belge: dict) -> bytes
def ozet(belge: dict) -> str
def bos_proje(ad: str) -> Proje                  # yalnız "kabuk" bölümü
def uygula(p: Proje, etiket: str, ekran: str, yeni: Mapping[str, dict | None]) -> Proje
def geri_al(p: Proje) -> Proje
def yinele(p: Proje) -> Proje
def kaydet(p: Proje, yol: str | Path) -> None    # uzantı .3dc değilse ProjeError
def ac(yol: str | Path) -> Proje
```
`Proje` değişmez; işlemler yeni nesne döndürür, girdi nesnesi değişmez. Bölüm adı ya da önbellek anahtarı kalıba
uymuyor, `sema` yok ya da tam sayı değil, `ad` boş → `ProjeError`.

### `tezgah/ekranlar/kabuk.py`
- `sira(ekranlar: Sequence[Ekran]) -> list[str]`
- `kapanis(ekranlar, degisen: set[str]) -> list[str]` — aşağı akış, topolojik sırayla (değişenler hariç)
- `class Kabuk` — tek kullanıcılı durum: güncel `Proje`, dosya yolu, `kirli`, son `Etki`; iş parçacığı kilidi.
  `degistir(yamalar, etiket, onizle=False) -> Etki`, `geri_al() -> Etki`, `yinele() -> Etki`, `ac(yol)`,
  `kaydet(yol=None)`, `yakala(etiket, ekran) -> Etki | None` (ara katmanın çağırdığı).
- `ekran() -> Ekran` — A3 kaydı: `ad="kabuk"`, `bolum="kabuk"`, router ve `kur`.

### REST uçları (`/api/proje`, kabuk router'ı)
| Uç | Yanıt |
|---|---|
| `GET /api/proje` | `{sema, ad, yol, kirli, geri_al: etiket \| null, yinele: etiket \| null, bolumler: [ad], uyarilar, son_etki}` |
| `GET /api/proje/gecmis` | `{konum, kayitlar: [{etiket, ekran, bolumler: [ad]}]}` (belgeler gönderilmez) |
| `POST /api/proje/yeni` | `{ad}` → boş proje; örnekler başlangıç durumuna |
| `POST /api/proje/ac` | `{yol}` → proje yüklenir, bütün ekranlara `sira` ile `ice_aktar` |
| `POST /api/proje/kaydet` | `{yol?}` → atomik kayıt; yol yoksa son yol; ikisi de yoksa 422 |
| `GET /api/proje/indir` | `.3dc` baytları (`application/zip`, `Content-Disposition` ile) |
| `POST /api/proje/yukle` | gövde `.3dc` baytları → `ac` ile aynı |
| `POST /api/proje/degistir` | `{etiket, yamalar: [{bolum, isaretci, deger}], onizle}` → `{etki, proje}` |
| `POST /api/proje/geri-al` · `POST /api/proje/yinele` | `{etki, proje}`; yığın boşsa 409 |
| `GET /api/proje/ornekler` · `POST /api/proje/ornek/{ad}` | örnek projeler; seçilen açılır |

`isaretci` RFC 6901 JSON Pointer'dır (`/kademeli_mil/parametreler/L`); yolu olmayan işaretçi, var olmayan bölüm →
422. Çekirdek hatası → 422 ve hata metni (SPEC 24 kuralı). `ProjeError` → 422. Sunucu yalnız `127.0.0.1`'de;
`ac` / `kaydet` yolları `.3dc` uzantılı olmalı, başka bir dosyanın üzerine yazmak için uzantı denetimi yeter (yerel tek kullanıcı).

### Ön yüz (`kabuk.ts`)
- **Proje çubuğu:** proje adı, kaydedilmemiş değişiklik işareti (`•`), geri al / yinele düğmeleri (etiketleri ipucunda),
  son kayıt yolu. Sayfa başlığı `ad • — Tezgah` (kirliyse). Kirliyken sekme kapatılırsa tarayıcı uyarısı.
- **Komut paleti** (`Ctrl K`): kabuk komutları (Yeni, Aç, Kaydet, Farklı kaydet, Dosyayı indir, Dosya yükle,
  Geri al, Yinele, her ekrana geçiş, her örnek proje) + ekranların `komutlar()`'ı. `↑/↓` gezinir, `Enter`
  çalıştırır, `Esc` kapatır. Parametreli komutta yazım durduktan 250 ms sonra `onizle=True` gider; aynı anda en
  fazla bir önizleme isteği, yenisi gelince eskisinin yanıtı yok sayılır. Etki kartı yanıt geldikçe güncellenir.
- **Etki kartı ve rozetler:** `son_etki` her değişiklikten sonra kart olarak görünür; `bolum`'ün ekranı sekmesinde
  rozet (en önemli `fark`; ekranın `ozet` sırasındaki ilk sayısal anahtar).
- **Kısayollar:** `Ctrl Z` / `Ctrl Shift Z` / `Ctrl Y` / `Ctrl S` / `Ctrl Shift S` / `Ctrl O`. Odak bir metin
  kutusundaysa (`input`, `textarea`, `contenteditable`) `Ctrl Z` / `Ctrl Y` tarayıcının kendi geri alına bırakılır.
- Test kancası: `window.__tezgah.kabuk = {proje(), etki(), palet(): string[]}` (SPEC 24 kanca biçimi).

## Örnek proje (uydurma geometri)
`tezgah/ornekler_37.py`: `yatak_grubu.3dc` bellekte kurulur: SPEC 25'in `kademeli_mil` torna işi ve `yatak_grubu`
montajı (başlangıçta `L = 20`, girişim var), SPEC 24'ün flanş freze işi; SPEC 26 birleşmişse `model` bölümü
(flanş modeli) de eklenir. Gerçek şirket parçası yok.

## Kabul kriterleri
- [ ] **K1 Dosya gidiş-dönüşü:** bölümleri, önbelleği ve 5 kayıtlı geçmişi (konum 3) olan bir proje `kaydet` → `ac`
  sonrası her bölüm kanonik olarak aynı, önbellek baytları aynı, `gecmis` aynı; `float` değerler (ör. `0.1 + 0.2`,
  `1e-300`, `-0.0`) birebir. (`tests/fileio/test_proje.py::test_round_trip`)
- [ ] **K2 Belirlenimci dosya:** aynı proje iki kez (ve bölüm sözlüğü farklı anahtar sırasıyla kurulup) kaydedilince
  dosyalar bayt bayt aynı; zip girdileri sıralı ve tarihleri 1980-01-01. (`test_proje.py::test_deterministic_bytes`)
- [ ] **K3 Biçim:** standart `zipfile` ile açılır; girdi listesi tam olarak bildirimdekiler; `proje.json`'daki her
  `ozet` girdinin SHA-256'sı; bölüm dosyaları kanonik JSON. (`test_proje.py::test_layout`)
- [ ] **K4 Bozuk dosya:** zip değil; `proje.json` yok; `sema: 2`; bölüm özeti tutmuyor; bölüm geçersiz JSON;
  `../x.json` ve `/x.json` girdileri; 1 GiB sınırını aşan bildirilen boyut; oranı 200'ü aşan girdi → her biri
  `ProjeError`, mesajda girdi adı. Bölüme `nan` konmuş proje `kaydet`'te `ProjeError` ve diske hiçbir şey yazılmaz.
  (`test_proje.py::test_corrupt_*`)
- [ ] **K5 Hoşgörü:** özeti tutmayan önbellek girdisi atılır ve bir `uyari` döner, bölümler yüklenir; fazladan girdi
  ve tanınmayan bölüm `uyari` ile; tanınmayan bölüm yeniden kaydedilince bayt bayt korunur.
  (`test_proje.py::test_lenient_*`)
- [ ] **K6 Atomik kayıt:** var olan dosyanın üstüne kayıt sırasında yazım hatası (yazıcı `monkeypatch` ile yarıda
  kesilir) → eski dosyanın baytları aynı, klasörde `.tmp` kalmaz. (`test_proje.py::test_atomic_save`)
- [ ] **K7 Geri al cebiri:** tohumlu rastgele 300 işlemlik dizi (değiştir / geri al / yinele) için her adımda
  bağımsız bir başvuru modeliyle (durum listesi + işaretçi) aynı sonuç; değişmeyen yeni değer kayıt eklemez;
  geri aldıktan sonra yeni değişiklik yinele dalını siler; 201. kayıtta en eski atılır ve `konum` 200; boş yığında
  `geri_al` / `yinele` `ProjeError`; girdi `Proje` nesnesi hiç değişmez. (`test_proje.py::test_undo_algebra`)
- [ ] **K8 Geçmiş dosyada yaşar:** 3 değişiklik + 1 geri al sonrası kaydet → aç → `geri_al` ve `yinele` kaydetmeden
  önceki projeyle aynı sonuçları verir. (`test_proje.py::test_history_persists`)
- [ ] **K9 Sıra:** sahte ekranlarla `a → b → c`, `a → d`: `sira` = `[a, b, c, d]` (eşitlikte alfabetik);
  `kapanis({a})` = `[b, c, d]`, `kapanis({b})` = `[c]`; `a ↔ b` döngüsü ve bilinmeyen bölüme bağımlılık `ProjeError`.
  (`tests/tezgah/test_kabuk.py::test_order`)
- [ ] **K10 Yayılım ve etki:** sahte ekranlar (her biri `ice_aktar` çağrılarını sayar, `ozet` belgeden belirlenimci
  türetilir): `a` değişince `b`, `c`, `d` tam bir kez, topolojik sırayla `ice_aktar` alır; bağımsız `e` hiç almaz;
  `Etki`'deki her `fark` = `sonra − once` (tam eşit); metin anahtarlar `fark`'ta yok. Önbellek: `b` `onbellek()` ile
  bir kayıt verir; değiştir → geri al sonrası `b`'nin `ice_aktar`'ı o kaydı alır, girdisi farklı bir durumda hiç
  almaz. (`test_kabuk.py::test_propagation`, `test_cache_by_input_digest`)
- [ ] **K11 Hata geri çevrilir:** `c`'nin `ice_aktar`'ı `CamError` fırlatınca bütün sahte ekranların `disa_aktar`'ı
  ve proje kanonik olarak değişiklik öncesiyle aynı, geçmiş uzunluğu değişmez, uç 422 ve gövdede hata metni ile
  `c`. (`test_kabuk.py::test_rollback_on_error`)
- [ ] **K12 Önizleme iz bırakmaz:** `onizle=True` yanıtının `etki`'si aynı yamanın gerçek uygulamasınınkine eşit;
  önizleme sonrası bütün bölümler, ekran durumları ve geçmiş öncekiyle kanonik olarak aynı, `kirli` değişmez.
  (`test_kabuk.py::test_preview_is_pure`)
- [ ] **K13 Yakalama:** sahte ekranın `POST` ucu durumunu değiştirince geçmişe `X-Tezgah-Etiket` etiketli bir kayıt
  eklenir; başlıksız istek `"POST /api/..."` etiketi alır; `GET` ve 4xx yanıtı kayıt eklemez; `geri-al` sahte ekranın
  `ice_aktar`'ını eski belgeyle çağırır ve ardından `disa_aktar` eski belgeyi verir; boş yığında 409.
  (`test_kabuk.py::test_capture_*`)
- [ ] **K14 Gerçek iplik (yatak grubu):** örnek proje açılır; `degistir` ile `torna_isleri/kademeli_mil/parametreler/L` =
  9.5 → etkide `torna_isleri` süre farkı, SPEC 25 `POST /api/montaj/yatak_grubu/parametre` ile aynı değişikliğin
  `sure_farki`'na eşit (rel 1e-12); `montajlar` girişim hacmi önce > 0, sonra 0. `geri-al` sonrası
  `GET /api/is/kademeli_mil` ve `GET /api/montaj/yatak_grubu` yanıtları değişiklik öncesiyle JSON olarak aynı;
  `yinele` sonrası değişiklik sonrasıyla aynı. Kaydet → yeni sunucu → aç → aynı iki yanıt.
  `@slow`, `@occt`. (`tests/tezgah/test_kabuk_iplik.py::test_bearing_thread`)
- [ ] **K15 Palet eşleştirmesi (vitest):** `katla` tablosu (`"İŞLEM" → "islem"`, `"ışık" → "isik"`, `"Çap" → "cap"`);
  `sifirla` sorgusu `Sıfırla`'yı bulur; dört puan basamağının her biri için sıralama örneği; eşitlikte `son` sırası;
  boş sorgu; desen: `"l 9,5"` ve `"L 9.5"` → 9.5, `"L abc"`, `"L 9.5x"`, `"L nan"`, `"L"` geçersiz.
  (`tezgah/arayuz/tests/kabuk.test.ts`)
- [ ] **K16 Uçtan uca (Playwright, `@slow`):** örnek proje açılır, konsolda hata yok; `Ctrl K`, `L 9.5` yazılır →
  palet etki kartındaki süre farkı `POST /api/proje/degistir` önizleme yanıtıyla aynı ve sunucuda geçmiş uzunluğu
  değişmemiş; `Enter` → Torna ve Montaj sekmelerinde rozet, başlıkta `•`; `Ctrl Z` → `window.__tezgah` torna işi
  ilk haliyle aynı, rozetler ters işaretli; bir metin kutusundayken `Ctrl Z` projeyi geri almaz; `Ctrl S` sonrası
  `•` kalkar; sayfa yenilenip proje yeniden açılınca geçmişte aynı etiketler. 400 px ve 1440 px'te palet ve etki
  kartı yatay kaydırmasız; her etkileşimli öğenin görünür odak durumu var. (`tezgah/arayuz/tests/kabuk.e2e.spec.ts`)
- [ ] **K17 Bağımlılık kuralı:** `fileio/proje.py` yalnız standart kitaplık import eder; `tezgah/ekranlar/kabuk.py`
  başka ekranların modüllerini (`tezgah.kopru`, `tezgah.sunucu*`, `tezgah.montaj` …) import etmez, yalnız A3 kaydı,
  `fileio.proje` ve `*/model.py` hata sınıfları; hiçbir paket `tezgah`'ı import etmez. (`test_kabuk.py::test_imports`, AST)

## Test yaklaşımı
- CLAUDE.md "Test bağımsızlığı" aynen geçerli: önce bu SPEC'ten bağımsız testler (Python + TS) ayrı oturumda,
  sonra kod ayrı oturumda.
- K1–K8 `fileio` testleridir: FastAPI, OCCT, Node gerektirmez, CI'da her zaman çalışır.
- K9–K13 sahte ekranlarla (test içinde kurulan `Ekran` kayıtları) çalışır; gerçek 24/25/26 ekranlarına bağlı değildir.
  `fastapi` yoksa atlanır (`pytest.importorskip`).
- K14 gerçek ekranlara bağlıdır; A3, 24 ve 25 `main`'e girene kadar `@slow` ile işaretli ve atlanır.
- K15–K16 SPEC 24 kararıyla yalnız yerelde (pre-push), CI'da değil.

## Yol haritası yeri
- **Numara:** 37 (`37-proje-kabuk`), Dalga 5 hat H13.
- **Bağımlılık (kod):** A3 (ekran kaydı), 24, 25; 26 birleşmişse `model` bölümü örnek projeye eklenir (yoksa K14
  yine geçer). `fileio/proje.py` (K1–K8) hiçbir şeye bağlı değildir ve onaydan hemen sonra yazılabilir.
- **Devamı:** SPEC 47 (H14) ekranları kayda girerken `bolum`, `bagimli`, `ozet` bildirir ve kendiliğinden projeye,
  geri ala ve palete katılır. Kurtarma dosyası ve dallanan geçmiş Dalga 6'ya bırakılır (Açık soru 3).

## Kapsam dışı
- Dallanan (ağaç) geçmiş, geçmişte arama, adlı sürümler; geçmiş doğrusaldır.
- Çok kullanıcılı düzenleme, birleştirme (merge), kilitleme; sunucu tek kullanıcı ve `127.0.0.1`.
- Bölüm içeriklerinin anlamı ve sürüm yükseltmesi (`sema` 1 → 2 göçü): her bölümün sahibi SPEC'in işidir.
- STEP / CalculiX gibi dış biçimler (`fileio/` diğer dosyaları); `.3dc` içine STEP gömmek.
- Parçalar arası referans, SPEC 26 modelinin özellik ağacına dönüşmesi (SPEC 18).
- Gerçek şirket parçaları (gizlilik kuralı): örnek proje uydurma geometridir.

## Açık sorular (onayda karara bağlanır)
1. **Tek geri al yığını.** SPEC 26 `Ctrl Z`'yi modelin geçmiş şeridinde konum değiştirmek olarak tanımlıyor, SPEC 24
   `Ctrl K`'yı kendi komut çubuğu olarak. **Önerilen:** iki tuş da kabuğa geçer; model ekranındaki değişiklik projenin
   geri alındığı yığına girer (geri alınca şerit yine bir adım geri gider, SPEC 26 K12'nin gözlenen davranışı aynı),
   SPEC 24'ün komutları palete `komutlar()` ile taşınır. Alternatif: ekran başına ayrı yığın.
2. **Dosya açma / kaydetme yolu.** **Önerilen:** sunucu tarafı yol (`~/3D-CORE projeleri/` varsayılan klasör + son
   açılanlar listesi) ve yedek olarak tarayıcıdan indir / yükle. Alternatif: yalnız tarayıcı indir / yükle.
3. **Otomatik kurtarma dosyası** (her değişiklikte `<ad>.3dc.kurtarma`, temiz kayıtta silinir). **Önerilen:** Dalga 6;
   bu SPEC'te yok. Alternatif: bu SPEC'e K18 olarak eklemek.
4. **Geçmiş sınırı 200 kayıt, önbellek belleği 256 MiB, dosyada yalnız güncel durumun önbelleği.** **Önerilen:** bu
   değerler. Alternatif: geçmiş dosyaya yazılmaz (yalnız oturum boyunca).
