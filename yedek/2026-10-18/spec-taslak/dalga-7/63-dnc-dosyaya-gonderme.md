# SPEC 63 — DNC: programı tezgâha göndermek (dosya yoluyla)

> **Durum: ONAYLANDI** (kullanıcı, 2026-10-18 16:06 UTC, proje sohbetinde yazılı: "Dalga 7 taslakları 57, 58, 59, 61, 62,
> 63, 64 ve 72'yi önerileriyle onaylıyorum."). Açık sorular önerilen cevaplarla kapandı (dosya sonu "Kararlar").
> Önceki durum: taslak. Dalga 7, hat A7 (`/mnt/project-files/yol-haritasi/dalga-6-ve-sonrasi.md`
> bölüm 4).
> **Karar 3 (kullanıcı, 2026-10-18 10:57): DNC şimdilik yalnız dosyaya yazmadır.** Ağdan / seri hattan doğrudan
> gönderme bu SPEC'te **yoktur**; Dalga 7 sonunda ayrıca karara bağlanır (açık soru 1).
> Dayanır: SPEC 30 / 31 / 40 / 51 (`cam.post.post`, `read_program`, lehçeler, `MachineProfile.verified`, `UYARI`),
> SPEC 05 / 22 / 43 / 44 (simülasyon ve tezgâh çarpışma denetimi), SPEC 38 (iş föyü), SPEC 48 (doğrulama kaydı),
> SPEC 24 / 47 (Tezgah).

## Amaç
Tezgah'tan bir programı **tezgâhın okuyacağı klasöre** güvenle yazmak. "Güvenle" şu demektir:
- Program yazılmadan önce **denetimden geçmiş** olmalı: simülasyon ve tezgâh denetimi hatasız, program kendi
  okuyucumuzla gidiş-dönüşte aynı yolu veriyor.
- Dosya adı, uzantı, satır sonu, karakter kümesi ve program numarası **o kontrolörün kurallarına** uyuyor.
- Var olan bir dosya **asla sessizce ezilmiyor**.
- Her gönderim bir **kayda** yazılıyor: hangi program (özet), hangi tezgâha, hangi denetim sonucuyla, kim, ne zaman.

Hedef klasör kullanıcının seçtiği yerel bir yoldur: USB bellek, kontrolörün paylaştığı ağ sürücüsü (Sinumerik
"Logical drive", Heidenhain TNC paylaşımı, MAPPS bellek kartı klasörü) ya da atölyenin DNC sunucusunun izlediği klasör.
Tezgah bu klasöre yalnız **dosya yazar**; ağ protokolü, seri hat ve tezgâhla el sıkışma yoktur.

## Neden
Bugün program Tezgah'tan indiriliyor ve kullanıcı elle doğru adla doğru yere kopyalıyor. Bu adımda yapılan hatalar
gerçek ve pahalıdır: yanlış program numarası tezgâhtaki başka bir programı ezer, eski sürüm gönderilir, Windows satır
sonu ya da Türkçe karakter kontrolörde okuma hatası verir, doğrulanmamış profille üretilmiş program fark edilmeden
tezgâha gider. Dosya yoluyla göndermek bu hataların hepsini **tezgâhla bağlantı kurmadan** kapatır; doğrudan DNC'nin
riskini (yanlış tezgâha canlı gönderim, yarıda kalan aktarım) almadan kazancın çoğunu verir.

## Teori

### 1. Ön koşullar (hepsi sağlanmadan dosya yazılmaz)
| # | Denetim | Kaynak | Başarısızsa |
|---|---|---|---|
| Ö1 | Simülasyon çarpışmasız, `check` sonuçlarında `hata` derecesinde kontrol yok | SPEC 05 / 22 / 43 / 44, Tezgah `kontroller` | `CamError`, ilk hata metni |
| Ö2 | Gidiş-dönüş: `read_program(metin, lehçe)` → hareketler üretilen yolla aynı (SPEC 31 toleransı) | SPEC 31 / 40 / 51 okuyucu | `CamError`, ilk farklı satır |
| Ö3 | Program numarası profilin `program_no_range` aralığında | SPEC 30 `check_machine` | `CamError` |
| Ö4 | Metin yalnız izinli karakterlerden (§2), satır uzunluğu sınırın altında | bu SPEC | `CamError`, satır no |
| Ö5 | Profil `verified: false` ise programın başında `UYARI` yorumu **var** | SPEC 30 | `CamError` (uyarısız doğrulanmamış program gönderilmez) |

Ö5 doğrulanmamış profille gönderimi **engellemez**; doğrulama basamakları (SPEC 48) zaten doğrulanmamış profille
yapılır. Yalnız uyarının programda olduğunu garanti eder ve kayda `dogrulanmis: false` yazar.

### 2. Kontrolör dosya kuralları
Kural tablosu `atolye/dnc_kurallari.json`'dadır (repoda; her satırın `kaynak` alanı kontrolör kılavuzunun adıdır):

| Kontrolör | Dosya adı | Uzantı | Satır sonu | Karakter | Not |
|---|---|---|---|---|---|
| `sinumerik` | `[A-Z][A-Z0-9_]{1,23}` (ilk iki karakter harf) | `.MPF` (ana), `.SPF` (alt) | LF | ASCII | Ad programın içindeki adla aynı |
| `heidenhain` | `[A-Za-z0-9_]{1,24}` | `.H` | CRLF | ASCII | `BEGIN PGM <ad> MM` / `END PGM <ad> MM` adla aynı |
| `fanuc` (MAPPS dahil) | `O` + 4 hane (`O0001`) | yok ya da `.NC` (profilde) | CRLF | ASCII | `%` ile başlar ve biter; `O` numarası program numarasıyla aynı |
| `haas` | `O` + 5 hane | `.NC` | CRLF | ASCII | `%` sınırlayıcı |
| `grbl` | serbest `[A-Za-z0-9_-]{1,64}` | `.nc` | LF | ASCII | — |

ASCII dışı karakter (ör. Türkçe yorum `ş`) bulunursa denetim **hata** verir ve yeri söyler; kod karakteri sessizce
değiştirmez. (Post zaten ASCII yazmalı; bu denetim son kapıdır.) Satır sonu dönüşümü yazımda yapılır ve yalnız
`\n` → `\r\n`'dir.

### 3. Ezme koruması
Hedefte aynı adda dosya varsa:
- İçeriği bayt bayt aynıysa: yazılmaz, kayda `ayni` yazılır, başarılı döner.
- Farklıysa: `ezme=False` (varsayılan) → `CamError`: "<yol> var ve farklı (sha256 …). Üzerine yazmak için onay
  gerekir." `ezme=True` yalnız boş olmayan bir `gerekce` ile kabul edilir; eski dosya önce
  `<hedef>/.3dcore-yedek/<ad>.<eski sha256'nın ilk 12 hanesi>` olarak kopyalanır, sonra yeni dosya yazılır.

### 4. Atomik yazım
Dosya önce aynı klasöre geçici adla (`.<ad>.yaziliyor`) yazılır, `fsync` edilir, sonra `os.replace` ile asıl adına
taşınır. Yazım yarıda kalırsa hedefte yarım program kalmaz; geçici dosya silinir. Ağ sürücüsünde `os.replace`
desteklenmezse (hata) kod geçici dosyayı siler ve `CamError` verir; asla yarım dosya bırakmaz.

### 5. Gönderim kaydı
Her başarılı gönderim (ve `ayni`) kullanıcı klasöründeki `gonderim-kaydi.jsonl` dosyasına bir satır ekler (kanonik
JSON, satır başına bir kayıt):
```
{ "sema": 1, "zaman": "YYYY-AA-GGTSS:DD:SSZ", "operator": str, "profil": {ad, ozet}, "program": {ad, ozet, lehce,
  program_no}, "hedef": str, "sonuc": "yazildi" | "ayni" | "ezildi", "gerekce": str, "dogrulanmis": bool,
  "denetim": {"sim": "temiz", "gidis_donus": "ayni", "uyarilar": [str]}, "is_foyu": {yol, ozet} | null }
```
Zaman kodun içinde saatten okunmaz; çağıran verir (testler sabit zamanla çalışır, SPEC 48 ile aynı ilke). Kayıt
dosyası yalnız eklenir; kod onu kısaltmaz ya da düzeltmez. `profil.ozet` ve `program.ozet` SPEC 48'in
`profil_ozeti` / `dosya_ozeti` fonksiyonlarıyla aynı hesaptır, böylece doğrulama kaydı ile gönderim kaydı eşleşir.

## Dosyalar
- **Yeni:** `atolye/dnc.py`, `atolye/dnc_kurallari.json`, `tests/atolye/test_dnc.py`, `durum/63-dnc-dosyaya-gonderme.md`.
- **Tezgah:** yeni ekran ucu `POST /api/ekran/freze/{is}/gonder` ve torna karşılığı (gövde: `hedef`, `operator`,
  `ezme`, `gerekce`). Sahibi "Tezgah uygulaması" thread'i; bu SPEC değişikliği ona dosya olarak gönderir. Tezgâh
  başına hedef klasör `yerel_parcalar/dnc-hedefleri.json`'da durur (yol atölyeye özeldir, repoya girmez).
- **Dokunulmayacak:** `cam/model.py`, `cam/post/` (yalnız `post`, `read_program`, `dialect_for` çağrılır),
  `pyproject.toml`. Yeni bağımlılık yok.

## Arayüz
```python
# atolye/dnc.py
@dataclass(frozen=True)
class DosyaKurali:
    kontrolor: str
    ad_deseni: str              # regex
    uzanti: str
    satir_sonu: str             # "\n" | "\r\n"
    satir_uzunlugu: int
    sinirlayici: str | None     # "%" ya da None

@dataclass(frozen=True)
class Gonderim:
    yol: Path
    sonuc: str                  # "yazildi" | "ayni" | "ezildi"
    kayit: dict                 # §5 satırı

def dosya_kurali(m: MachineProfile) -> DosyaKurali
def dosya_adi(m: MachineProfile, program_no: int, ad: str | None = None) -> str
def denetle(metin: str, m: MachineProfile, yollar: Sequence[Toolpath], kontroller: Sequence[dict]) -> list[str]
    # Ö1–Ö5; hata varsa CamError, yoksa uyarı listesi
def gonder(metin: str, m: MachineProfile, yollar: Sequence[Toolpath], kontroller: Sequence[dict],
           hedef: str | Path, operator: str, zaman: str, program_no: int, ad: str | None = None,
           ezme: bool = False, gerekce: str = "", is_foyu: Path | None = None,
           kayit_dosyasi: str | Path = "yerel_parcalar/gonderim-kaydi.jsonl") -> Gonderim
def kayitlari_oku(kayit_dosyasi: str | Path) -> list[dict]
```

## Kabul kriterleri
Uydurma iş: SPEC 31 örnek cep işi, SPEC 30 örnek profilleri (sinumerik, heidenhain, fanuc). Hedef `tmp_path`.
- [ ] **K1 Dosya adı:** sinumerik `program_no=12, ad="CEP_1"` → `CEP_1.MPF`; heidenhain → `CEP_1.H`; fanuc → `O0012`
  (profilde uzantı varsa `O0012.NC`); kurala uymayan ad (`"1CEP"`, `"çep"`, 25 karakter) `CamError`. (`test_dnc.py::test_ad`)
- [ ] **K2 İçerik biçimi:** yazılan dosyanın satır sonları tablodaki gibi (heidenhain ve fanuc'ta her satır `\r\n`,
  sinumerik'te `\r` yok); fanuc dosyası `%` ile başlar ve biter; heidenhain `BEGIN PGM` / `END PGM` adları dosya
  adıyla aynı; dosya ASCII çözülüyor. (`::test_bicim`)
- [ ] **K3 Ön koşullar:** Ö1 `hata` dereceli kontrol → `CamError`, dosya yok; Ö2 bir satırı elle bozulmuş program →
  `CamError`, mesajda satır no; Ö3 aralık dışı numara; Ö4 `ş` içeren yorum → `CamError`, satır no ve karakter;
  Ö5 `verified=false` profil, `UYARI` satırı silinmiş program → `CamError`. Her durumda hedef klasör değişmemiş
  (dosya listesi aynı). (`::test_on_kosul`)
- [ ] **K4 Ezme:** aynı içerik ikinci kez → `ayni`, dosya zamanı değişmez; farklı içerik `ezme=False` → `CamError`;
  `ezme=True, gerekce=""` → `CamError`; `ezme=True, gerekce="rev B"` → eski dosya `.3dcore-yedek/` altında,
  yenisi yerinde, kayıt `ezildi`. (`::test_ezme`)
- [ ] **K5 Atomik:** `os.replace` hata verecek biçimde yamalanınca (`monkeypatch`) hedefte ne asıl ne geçici dosya
  kalır, `CamError`. (`::test_atomik`)
- [ ] **K6 Kayıt:** iki gönderim → `gonderim-kaydi.jsonl` iki satır, kanonik, `program.ozet` yazılan dosyanın
  sha256'sı, `profil.ozet` SPEC 48 `profil_ozeti` ile aynı (48 yoksa bu alt koşul `skip`); `zaman` çağıranın
  verdiği. (`::test_kayit`)
- [ ] **K7 Ağ yok:** AST taraması: `atolye/dnc.py` `socket`, `serial`, `http`, `urllib`, `ftplib`, `requests`
  içe aktarmıyor ve hiçbir alt süreç (`subprocess`) başlatmıyor. (`::test_ag_yok`)
- [ ] **K8 Tezgah ucu:** `POST /api/ekran/freze/{is}/gonder` başarılı → 200 ve `Gonderim` JSON; ön koşul hatası →
  422 ve metin; hedef tanımsız tezgâh → 422 "dnc-hedefleri.json'da <ad> yok". (`tests/tezgah/test_gonder_ucu.py`)
- [ ] **K9 Bağımlılık:** `atolye/dnc.py` yalnız stdlib, `cam.model`, `cam.post` dışa açılanları ve (varsa)
  `atolye.dogrulama` özet fonksiyonlarını içe aktarır. (`test_bagimlilik.py`)
- [ ] Tüm testler yeşil, `ruff check .` ve `ruff format --check .` temiz.

## Bağımlılıklar
SPEC 30, 31, 38, 44 `main`'de. SPEC 48 (özet fonksiyonları) isteğe bağlı: yoksa aynı hesap `dnc.py`'de yazılır ve 48
birleşince ona bağlanır. SPEC 51 (5 eksen post) birleşince Ö2 5 eksen programlarını da kapsar. Arayüz değişikliği yok.

## Kapsam dışı (karar 3)
- Ağ (FTP, SMB istemcisi, OPC UA), seri hat (RS-232, DNC1), Heidenhain LSV2, Sinumerik "Execution from External",
  MTConnect. Tezgâhtan durum ya da ofset okuma.
- Uzun programların parça parça besleme (drip feed).
- Tezgâhtaki program listesini okuma ve eşleme.

## Kararlar (açık sorular; önerilen cevaplarla kapandı, kullanıcı 2026-10-18 16:06 UTC)
Her maddedeki **Öneri** artık karardır.
1. Doğrudan (ağ / seri) gönderme ne zaman konuşulsun? **Öneri:** Dalga 7 sonunda, SPEC 48'de en az iki tezgâh
   (NLX 2500, DMU 50) doğrulandıktan sonra ayrı bir SPEC; o zamana kadar yalnız dosya.
2. Doğrulanmamış profille gönderim engellensin mi? **Öneri:** hayır (doğrulama basamakları bu yolla yapılır), ama
   Ö5 uyarıyı zorunlu kılar ve Tezgah onay penceresinde "DOĞRULANMAMIŞ PROFİL" kırmızı yazar.
3. Fanuc / MAPPS'te dosya uzantısı: **Öneri:** profilde `dnc_uzanti` olmadığı için kural dosyasında kontrolör başına
   varsayılan (`""`); tezgâh başına fark gerekirse `dnc-hedefleri.json`'da `uzanti` alanı. `MachineProfile`'a alan
   eklenmez (arayüz değişikliği olurdu).
4. Gönderim kaydı nerede? **Öneri:** `yerel_parcalar/gonderim-kaydi.jsonl` (atölye verisi); MES (SPEC 64) bu kaydı
   REST'ten okuyabilir.
