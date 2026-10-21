# SPEC 48 — Gerçek tezgâh doğrulama programı

> Durum: **taslak** (kullanıcı onayı bekliyor). Dalga 6, hat G1 (`/mnt/project-files/yol-haritasi/dalga-6-ve-sonrasi.md`
> bölüm 3; "1.0'ın asıl kapısı"). Tezgâh sırası kararı 8a (kullanıcı, 2026-10-18 11:56).
> Dayanır: SPEC 30 (`MachineProfile.verified`, `post`), SPEC 31 (Sinumerik / Heidenhain), SPEC 38 (iş föyü,
> `docs/tezgah-dogrulama.md` bölüm 1–6).

## Amaç
Üretilen programların **kullanıcının kendi tezgâhlarında** güvenle çalıştığını adım adım göstermek ve bunun kaydını
tutmak. Bu SPEC iki ayrı parçadır:
- **A. Süreç (tezgâhta, kullanıcı yürütür):** her tezgâh için masa başı → havada (kuru) çalıştırma → mum / köpük
  parça → ilk metal parça → ölçüm basamakları ve tezgâh sırası. Testi yoktur; sonucu kullanıcının imzaladığı kayıttır.
- **B. Kod (bizde, testli):** kayıt biçimi, basamak sırasının denetimi, ölçüm sonucunun toleransla karşılaştırılması,
  iş föyüne ve programa bağlanma (özetle) ve bir profilin `verified: true` olmaya **hazır** olup olmadığının raporu.
  Kod `verified` alanını **hiçbir zaman yazmaz**; onu yalnız kullanıcı profil dosyasında elle `true` yapar.

## Neden
Bütün testlerimiz analitik ve kendi okuyucumuzla / rs274 ile çapraz kontrollü; ama hiçbir program gerçek bir
kontrolörde çalışmadı. Lehçeler belgelerden yazıldı, kinematik ve kurs değerleri genel bilgiden geldi. İlk gerçek
çalıştırmada yanlış bir işaret, yanlış bir döner eksen yönü ya da unutulmuş bir Z kaydırması tezgâha ve insana zarar
verebilir. Bu yüzden doğrulama basamaklıdır (her basamak bir öncekinin güvenini taşır) ve kayıtlıdır.

## A. Süreç

### A1. Basamaklar
Her basamak bir **doğrulama işi** (tezgâh profili + bir program + iş föyü) için yürütülür. Bir basamak "geçti"
olmadan sonraki başlamaz; "kaldı" ise neden bulunup düzeltilir ve iş **masa başından** yeniden başlar.

| # | Basamak (`adim`) | Ne yapılır | Geçme koşulu |
|---|---|---|---|
| 1 | `masa` | `docs/tezgah-dogrulama.md` bölüm 1 + iş föyü §1 maddeleri; simülasyonda (SPEC 05 / 43 / 44) çarpma yok | Tüm maddeler işaretli |
| 2 | `havada` | Bölüm 2–4: iş sıfırı, takım boyları, Z kaydırmalı kuru çalıştırma, hızlı %25, ilerleme %50, tek blok | Program sonuna kadar havada bitti; takım değişimleri ve döner eksen hareketleri beklenen yönde |
| 3 | `mum` | Aynı program, işlenebilir mum ya da sert köpük ham malzemede, ilerleme %50–100 | Parça çıktı, gözle hata yok; ölçüm listesinin kritik kalemleri ölçüldü (tolerans gevşek: mum için kullanıcı belirler) |
| 4 | `ilk_metal` | Aynı program, gerçek malzeme (önce alüminyum), bölüm 5 | Kesme normal (ses, titreşim, talaş); kırık takım / alarm yok |
| 5 | `olcum` | İş föyü ölçüm listesindeki **tüm** kalemler ölçülür ve girilir | Her kalem `alt ≤ ölçülen ≤ üst` (ISO 2768-1, SPEC 38 §6) |

Mum / köpük basamağı (3) metalden önce gelir çünkü yanlış bir yol orada takımı ve tezgâhı kırmadan görünür.
Kullanıcı bir tezgâhta bu basamağı atlamak isterse kayda `atlandi` ve gerekçe yazılır; atlanan basamak "geçti" sayılmaz
ama sıraya engel olmaz (kodda bayrak, B2).

### A2. Tezgâh sırası (karar 8a)
Basitten karmaşığa; her tezgâh bir öncekinin doğrulanmış kısmını taşır. "Gerekenler" o tezgâhta gerçek bir program
yazabilmek için `main`'de olması gereken SPEC'lerdir.

| Sıra | Tezgâh | Kapsam (`kapsam`) | Önerilen uydurma doğrulama parçası | Gerekenler |
|---|---|---|---|---|
| 1 | NLX 2500 | `torna_2x` | Kademeli mil (alın, boy, pah, kanal); sonra diş | 20, 21, 22, 30 Ek A, 38b (torna föyü) |
| 2 | DMU 50 | `freze_3x`, sonra `freze_3arti2` | Prizmatik blok: yüz alma, cep, 4 delik (G83); sonra 3+2 ile 30° eğik yüz | 14, 29, 30, 31, 38, 41 |
| 3 | NHC 5000 | `freze_4x_indeks` | Aynı blokta 4 yüz, B ekseni 0/90/180/270 indeksleme | 41 (tek döner eksen), 31 |
| 4 | DMU 75 / 90 | `freze_5x` | Eş zamanlı 5 eksen: SPEC 42 örnek yüzeyi | 42, 43, 44, **51 (5 eksen post)** |
| 5 | DMF 360 | `freze_3arti2` (kafa-masa) | Uzun parça, kafa B ekseniyle eğik delik | 41 (kafa-masa), 44 (büyük strok) |
| 6 | NTX 3000 | `torna_freze` | Milde radyal delik ve kama (C/Y) | **49 (mill-turn)**, B0 |

Lehçe her tezgâhın kontrolörüne göre seçilir (Sinumerik önce, Heidenhain ikinci; karar 7). Kontrolör kullanıcı
tarafından tezgâh panelinden teyit edilir ve profil dosyasının `controller` alanına yazılır. MAPPS çıkarsa G12 hattı.
Kalın yazılı SPEC'ler henüz yok: o tezgâhın 4. basamaktan sonrası onlar `main`'e girene kadar bekler.

### A3. Sorumluluk
Program dosyaya yazılır (karar 3: DNC yok); kullanıcı dosyayı kendisi tezgâha taşır. Tezgâh başındaki her karar ve
`verified: true` işareti kullanıcınındır. Bu SPEC'in kodu yalnız kaydı tutar ve tutarsızlığı söyler.

## B. Kod

### B1. Kayıt biçimi
Bir basamak, bir JSON kaydıdır (kanonik JSON, SPEC 37 `kanonik`; `nan` yok):
```
DogrulamaKaydi = {
  sema: 1,
  profil:        { ad, ozet },                # MachineProfile.to_dict() kanonik özeti (sha256)
  program:       { ad, ozet, lehce },         # tezgâha taşınan G-code dosyasının baytlarının sha256'sı
  is_foyu:       { yol, ozet } | null,        # SPEC 38 is-foyu.html (göreli yol) ve baytlarının sha256'sı
  kapsam:        [str],                       # A2 sütunu; bilinen kümeden
  adim:          "masa" | "havada" | "mum" | "ilk_metal" | "olcum",
  sonuc:         "gecti" | "kaldi" | "atlandi",
  tarih:         "YYYY-AA-GG",                # kullanıcı girer; kod saat okumaz
  operator:      str,                         # boş olamaz
  maddeler:      [{ bolum: int, metin: str, isaret: bool }],   # bölüm 1–5 + iş föyü CheckItem'ları
  olcumler:      [{ no, metin, nominal, alt, ust, olculen }],  # yalnız "mum" ve "olcum"
  notlar:        str,
  gerekce:       str                          # "kaldi" ve "atlandi"da zorunlu
}
```
Dosya adı: `<profil ad>/<tarih>-<sıra 3 hane>-<adim>.json`, kullanıcının seçtiği bir `dogrulama/` klasöründe
(proje dosyasının yanında; `.3dc` içine almak 54 / B1 sonrasına bırakıldı).

### B2. Kurallar (hepsi `CamError`, mesajda kayıt dosyası adı)
- Şema: bilinmeyen alan, eksik alan, bilinmeyen `adim` / `sonuc` / `kapsam`, boş `operator`, `kaldi` / `atlandi` için
  boş `gerekce`, `olcum` basamağında boş `olcumler`.
- **Sıra:** aynı `(profil.ozet, program.ozet)` için bir basamak, ancak önceki basamakların her biri en son kaydında
  `gecti` ya da `atlandi` ise kaydedilebilir (`masa` hariç). `kaldi` sonrası yalnız `masa` kaydedilebilir (zincir sıfırlanır).
  `masa` ve `olcum` atlanamaz.
- **Bağ:** `is_foyu` verildiyse dosyası var ve özeti tutuyor; `program.ozet` verilen G-code dosyasının özetiyle aynı.
  Profil değiştiyse (`profil.ozet` farklı) eski kayıtlar **o profil için** geçersizdir (rapor bunu söyler).
- **Ölçüm:** her kalemde `alt ≤ ust`; `sonuc = gecti` iken herhangi bir kalem `olculen ∉ [alt, ust]` → `CamError`
  ("<no> <metin>: ölçülen X, sınır [alt, üst]"). `olculen` boş olamaz. Kalemler iş föyünden geliyorsa (`olcum_listesi`)
  no, metin ve sınırlar föydekiyle aynı olmalı.

### B3. Hazırlık raporu
`hazirlik(profil, kayitlar) -> Rapor`: her `kapsam` için en son geçerli zincir (aynı profil özeti) `masa … olcum`
tamamsa `hazir`, değilse eksik ilk basamak. Profil dosyasında `verified: true` ama hiçbir kapsam `hazir` değilse
rapora **uyarı**: `"<ad>: verified=true ama geçen doğrulama kaydı yok"`. Rapor `verified`'ı değiştirmez; kullanıcıya
"bu profil şu kapsamlarda doğrulanmaya hazır; `verified` alanını kendiniz `true` yapın" der.

### B4. Kod `verified`'ı yazmaz
`atolye/dogrulama.py` profil dosyasına yazmaz, `MachineProfile`'ı değiştirmez. Depoda `verified` alanını `True` yapan
kod yolu yoktur; yalnız örnek profil JSON'larında `false` bulunur (K7 AST + metin taraması).

## Dosyalar
- Yeni: `atolye/dogrulama.py`, `tests/atolye/test_dogrulama.py`, `durum/48-tezgah-dogrulama.md`.
- Değişecek: `docs/tezgah-dogrulama.md`, yalnız iki bölüm **eklenir**: `## 7. Doğrulama programı` (A1 basamakları,
  mum / köpük adımı, kayıt nasıl tutulur) ve `## 8. Tezgâh sırası` (A2 tablosu). Bölüm 1–6 başlıkları ve numaraları
  aynen kalır (SPEC 38 K9).
- Dokunulmayacak: `cam/model.py` (`MachineProfile`), `cam/post/` profilleri, `atolye/is_foyu.py` (yalnız dışa açılan
  `JobSheet`, `InspectionItem`, `CheckItem` okunur), `pyproject.toml`, `DURUM.md`. Yeni bağımlılık yok.

## Arayüz
```python
# atolye/dogrulama.py
ADIMLAR = ("masa", "havada", "mum", "ilk_metal", "olcum")
KAPSAMLAR = ("torna_2x", "freze_3x", "freze_3arti2", "freze_4x_indeks", "freze_5x", "torna_freze")

@dataclass(frozen=True)
class Olcum: no: int; metin: str; nominal: float; alt: float; ust: float; olculen: float

@dataclass(frozen=True)
class DogrulamaKaydi: ...                       # B1 alanları

def profil_ozeti(m: MachineProfile) -> str
def dosya_ozeti(yol: str | Path) -> str         # sha256(bytes)
def bos_kayit(m: MachineProfile, program: Path, job: JobSheet | None, adim: str, kapsam: Sequence[str],
              tarih: str, operator: str) -> DogrulamaKaydi
    # maddeler: docs bölüm 1–5'in "- [ ]" satırları + job.checks (işaretsiz); olcumler: job.inspection (olculen boş)
def denetle(k: DogrulamaKaydi, onceki: Sequence[DogrulamaKaydi]) -> None
def kaydet(k: DogrulamaKaydi, klasor: str | Path) -> Path    # denetle + atomik yazım
def oku(klasor: str | Path) -> list[DogrulamaKaydi]          # tarih, sıra düzeninde
def hazirlik(m: MachineProfile, kayitlar: Sequence[DogrulamaKaydi]) -> dict
    # {"profil": ad, "kapsam": {k: "hazir" | "<eksik adim>"}, "uyarilar": [str]}
def rapor_html(m: MachineProfile, kayitlar: Sequence[DogrulamaKaydi]) -> str
    # tek dosya, dış kaynaksız; SPEC 38 §8 kuralları (id'ler: table#zincir, table#olcum, ul#uyarilar)
```

## Kabul kriterleri
### Kod (test edilir; uydurma profil, program ve iş föyü: SPEC 38 Ek A + SPEC 30 örnek profili)
- [ ] K1 **Kayıt gidiş-dönüşü:** `bos_kayit` → doldur → `kaydet` → `oku` kanonik olarak aynı; aynı kayıt iki kez →
  bayt bayt aynı dosya; maddeler docs bölüm 1–5 satırları + `job.checks` sırasıyla, ölçümler `job.inspection`'la aynı.
  (`test_dogrulama.py::test_round_trip`)
- [ ] K2 **Şema hataları:** B2 şema listesindeki her durum `CamError`, mesajda dosya adı ve alan adı. (`::test_schema_*`)
- [ ] K3 **Sıra:** `masa` geçmeden `havada` → hata; `masa, havada, mum(atlandi), ilk_metal, olcum` kabul; `havada kaldi`
  sonrası `mum` → hata, `masa` kabul ve zincir sıfırlanır; `masa` veya `olcum` `atlandi` → hata; farklı program özetiyle
  kayıt eski zinciri ilerletmez. (`::test_order`)
- [ ] K4 **Ölçüm:** nominal 20, `m` sınıfı → sınır `[19,8; 20,2]`; `olculen = 20,2` geçer, `20,21` `gecti` ile hata
  (mesajda kalem no, metin, değer, sınırlar), aynı kalem `kaldi` ile kabul; föyden farklı sınırlı kalem hata. (`::test_measurement`)
- [ ] K5 **Bağ:** iş föyü dosyası bir bayt değişince hata; G-code özeti tutmayınca hata; profil kursu değişince eski
  kayıtlar `hazirlik`'ta sayılmaz ve rapor bunu söyler. (`::test_links`)
- [ ] K6 **Hazırlık:** tam zincirli `freze_3x` → `hazir`, `freze_3arti2` → `"masa"`; `verified=true` ve kayıt yok →
  uyarı metni birebir; `hazirlik` profil nesnesini ve dosyasını değiştirmez. (`::test_readiness`)
- [ ] K7 **`verified` yazılmaz:** AST taraması: depoda (`tests/` hariç) `verified` adına `True` atayan / `"verified": true`
  yazan kod yok; `atolye/dogrulama.py` hiçbir `cam/post/profiles/*.json` yolunu yazma kipinde açmıyor. (`::test_never_sets_verified`)
- [ ] K8 **Rapor:** `rapor_html` `html.parser` ile ayrışıyor, `http` / `<script>` yok, `table#zincir` satır sayısı kayıt
  sayısı, aynı girdi → bayt bayt aynı. (`::test_report_html`)
- [ ] K9 **Belge:** `docs/tezgah-dogrulama.md`'de `## 1.` … `## 8.` var; `## 7.` beş basamağın adını, `## 8.` altı tezgâhı
  A2 sırasıyla anıyor; SPEC 38 K9 testi değişmeden geçiyor. (`::test_document`)
- [ ] K10 **Bağımlılık:** `atolye/dogrulama.py` yalnız stdlib, `cam.model`, `cam.post` (profil okuma) ve `atolye.is_foyu`
  dışa açılanlarını içe aktarıyor; hiçbir paket `atolye`'yi içe aktarmıyor. (`test_bagimlilik.py`)
- [ ] Tüm testler yeşil, `ruff check .` ve `ruff format --check .` temiz.

### Süreç (test değil; kullanıcı kabulü, Dalga 6 G1 kapısı)
- [ ] S1 NLX 2500 `torna_2x`: beş basamak `gecti`, ölçüm raporu (`rapor_html`) kayıtlı.
- [ ] S2 DMU 50 `freze_3x` ve `freze_3arti2`: aynı.
- [ ] S3–S6 NHC 5000, DMU 75/90, DMF 360, NTX 3000: gerekli SPEC'ler (A2) `main`'e girdikçe aynı.
- Her tezgâhta `verified: true` işaretini kullanıcı koyar; Dalga 6 bitti sayılması için en az S1 ve S2 gerekir
  (öneri, açık soru 2).

## Bağımlılıklar
- Kod (B): SPEC 30 ve 38 `main`'de (var). SPEC 37 gerekmez (kayıt ayrı JSON). Arayüz değişikliği yok.
- Süreç (A): tezgâh başına A2 "Gerekenler" sütunu. 38b (torna iş föyü) yoksa NLX 2500 için föysüz kayıt
  (`is_foyu: null`) kabul edilir, ölçüm kalemleri elle girilir.

## Kapsam dışı
- Programı tezgâha gönderme (DNC, karar 3), tezgâhtan veri okuma (OPC UA, MTConnect), CELOS entegrasyonu.
- Ölçümden ofset düzeltmesi önerme ve kütüphaneye geri yazma (SPEC 38'de de kapsam dışı), SPC.
- Tezgah'ta doğrulama ekranı (ayrı Tezgah işi; bu SPEC yalnız kitaplık + HTML rapor).
- `MachineProfile`'a kapsam bazlı doğrulama alanı eklemek (ör. `verified_scopes`): gerekirse ayrı arayüz PR'ı.

## Açık sorular
1. Kayıtlar proje dosyasının yanında ayrı `dogrulama/` klasöründe mi tutulsun (öneri), yoksa `.3dc` içinde bölüm mü?
   Öneri: ayrı klasör; doğrulama bir tezgâha aittir, projeye değil.
2. Dalga 6'nın "bitti" sayılması için hangi tezgâhlar şart? Öneri: NLX 2500 ve DMU 50 (S1, S2); diğerleri SPEC'leri
   geldikçe Dalga 7'ye taşabilir.
3. `verified` tek bir bayrak kaldığı için bir DMU 50 profili 3 eksende doğrulanınca 5 eksen için de "doğrulandı" görünür.
   Öneri: şimdilik `hazirlik` raporu kapsamı ayrı söyler; kapsam bazlı alan için ayrı arayüz PR'ı (B0 ile birlikte) açılsın.
