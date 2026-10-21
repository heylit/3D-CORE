# SPEC 64 — MES bağlantısı (yerel REST API)

> **Durum: ONAYLANDI** (kullanıcı, 2026-10-18 16:06 UTC, proje sohbetinde yazılı: "Dalga 7 taslakları 57, 58, 59, 61, 62,
> 63, 64 ve 72'yi önerileriyle onaylıyorum."). Açık sorular önerilen cevaplarla kapandı (dosya sonu "Kararlar").
> Önceki durum: taslak. Dalga 7, hat A8 (`/mnt/project-files/yol-haritasi/dalga-6-ve-sonrasi.md`
> bölüm 4).
> **Kararlar (kullanıcı, 2026-10-18 11:00 / 11:09 / 11:16):** MES kullanıcının kendi uygulamasıdır (TypeScript +
> PostgreSQL, yerel). Bağlantı Tezgah'ın FastAPI'sinin açtığı **yerel REST API** ile kurulur. OpenAPI şeması otomatik
> çıkar, MES tarafı TypeScript tiplerini bu şemadan üretir. **Tezgah MES veritabanına yazmaz**; şemanın sahibi MES'tir.
> Yeni bağımlılık yok.
> Dayanır: SPEC 24 / 24a (Tezgah sunucusu, A3 ekran kaydı, hata → 422 kuralı), SPEC 55 Karar 4
> (`GET /api/openapi.json` → `info.title == "Tezgah"`), SPEC 38 (iş föyü), SPEC 58 (süre, maliyet), SPEC 63 (DNC
> denetimi ve gönderim kaydı), SPEC 37 / B1 (`.3dc` proje).

## Amaç
MES'in Tezgah'a **iş emri** verebilmesi ve Tezgah'tan o iş emrinin **imalat çıktılarını** alabilmesi:
- MES → Tezgah: iş emri oluştur / güncelle / iptal et (parça, revizyon, adet, malzeme, tezgâh, termin).
- Tezgah → MES (MES çeker): iş emrinin durumu, NC programı, takım listesi, parça başı süre, iş föyü, maliyet,
  gönderim kayıtları.

Yön **tek taraflı çekmedir**: Tezgah hiçbir zaman MES'e istek göndermez, MES veritabanına bağlanmaz. Bütün bilgi akışı
MES'in Tezgah'a yaptığı HTTP istekleriyle olur. Böylece MES'in şeması, yetkisi ve işlem (transaction) kuralları
tamamen MES'te kalır; Tezgah'ın PostgreSQL sürücüsüne ya da MES şemasına bağımlılığı olmaz.

## Neden
Atölyede iş emri MES'te doğar; program, takım listesi ve süre ise CAM'de. Bugün bu bilgiler elle taşınıyor (MES'e süre
elle giriliyor, takım listesi föyden okunuyor). Sürümlenmiş, şeması otomatik çıkan bir yerel API iki uygulamayı
birbirinin içine girmeden bağlar ve MES'in TypeScript tipleri şemadan üretildiği için alan adı uyuşmazlığı derleme
anında yakalanır.

## Teori

### 1. Kapsam ve sürüm
- Tüm uçlar `/api/mes/v1/` altındadır. `v1` içinde yalnız **ekleme** yapılır (yeni uç, isteğe bağlı yeni alan).
  Alan silme, ad ya da tür değiştirme `v2` demektir ve ayrı SPEC ister.
- Şema anlık görüntüsü `docs/mes-openapi-v1.json` repodadır. Test, çalışan uygulamanın `/api/openapi.json`'ındaki
  `/api/mes/v1/` yollarını ve bunların başvurduğu bileşen şemalarını bu dosyayla karşılaştırır: **kaldırılan ya da
  değişen** bir şey varsa kırmızı, yalnız eklenen varsa sarı (test geçer ama "anlık görüntüyü güncelle" uyarısı).
- Alan adları ASCII Türkçe ve `snake_case`'tir (MES'te TypeScript'e olduğu gibi geçer).

### 2. İş emri ve durum makinesi
```
IsEmri = { mes_id: str, revizyon: int ≥ 1, parca_no: str, parca_rev: str, adet: int ≥ 1,
           malzeme_id: str | null, tezgah: str | null,      # MachineProfile.name
           termin: "YYYY-AA-GG" | null, notlar: str,
           proje: str | null }                              # .3dc yolu (Tezgah'ın gördüğü yerel yol) ya da null
```
Durumlar ve geçişler (Tezgah tarafından yürütülür; MES yalnız `iptal` isteyebilir):

    alindi → baglandi → hazir → gonderildi
       ↘        ↘         ↘
                 iptal (her durumdan; gonderildi'den de, kayıt silinmez)

- `alindi`: MES iş emrini verdi.
- `baglandi`: kullanıcı Tezgah'ta bu iş emrine bir CAM işi (depo adı) bağladı, ya da `proje` verildi ve açıldı.
- `hazir`: bağlı işin programı SPEC 63 ön koşullarından (Ö1–Ö5) geçti. Program, takım listesi, süre, föy bu andaki
  hâliyle **dondurulur** (özetleri kaydedilir). Bağlı iş sonradan değişirse durum `baglandi`'ya döner ve `hazir`
  çıktıları geçersiz olur (bayat çıktı verilmez, 409).
- `gonderildi`: SPEC 63 `gonder` bu iş emrinin programını yazdı (gönderim kaydındaki `mes_id` ile eşleşir).

Aynı `mes_id` ile yeni `revizyon` gelirse eski revizyon `iptal` olur ve yeni kayıt `alindi`'dan başlar. Aynı
`(mes_id, revizyon)` ikinci kez aynı içerikle gelirse yanıt aynıdır (eş-etkili, idempotent); farklı içerikle gelirse
409.

### 3. Uçlar
| Yöntem ve yol | Gövde / yanıt | Not |
|---|---|---|
| `GET /api/mes/v1/saglik` | `{ api: "v1", tezgah_surum, sema_ozeti }` | `sema_ozeti`: anlık görüntünün sha256'sı; MES uyuşmazlığı buradan görür |
| `PUT /api/mes/v1/is-emirleri/{mes_id}` | `IsEmri` → `IsEmriDurumu` | oluşturur ya da yeni revizyon; eş-etkili |
| `GET /api/mes/v1/is-emirleri?durum=&sonra=` | `[IsEmriDurumu]` | `sonra`: değişiklik sırası numarası (§4) |
| `GET /api/mes/v1/is-emirleri/{mes_id}` | `IsEmriDurumu` | 404 bilinmeyen |
| `POST /api/mes/v1/is-emirleri/{mes_id}/iptal` | `{ gerekce }` → `IsEmriDurumu` | gerekçe boş olamaz |
| `GET …/{mes_id}/program` | `text/plain`, başlık `X-Sha256` | yalnız `hazir` / `gonderildi`; değilse 409 |
| `GET …/{mes_id}/takimlar` | `[{ t_no, ad, tur, D, boy, tutucu, sure_s }]` | SPEC 38 `ToolRow`'dan |
| `GET …/{mes_id}/sure` | `{ t_isleme_s, t_yukle_s, t_hazirlik_s, t_parca_s }` | SPEC 58 §1, `n = adet` |
| `GET …/{mes_id}/maliyet` | SPEC 58 `Maliyet` | ücret dosyası yoksa 422 (58'in mesajı) |
| `GET …/{mes_id}/is-foyu.html` | `text/html` | SPEC 38 çıktısı |
| `GET /api/mes/v1/gonderimler?sonra=` | `[GonderimKaydi]` | SPEC 63 kayıtları, `mes_id` alanlı |

`IsEmriDurumu = { is_emri: IsEmri, durum, is_adi: str | null, ciktilar: { program_ozeti, foy_ozeti } | null,
degisiklik: int, uyarilar: [str] }`.

Hatalar SPEC 24'ün tek kuralıyla döner: çekirdek hata türleri → 422, gövde `{ "detail": str }`. Durum çakışması → 409,
bilinmeyen kayıt → 404, şema dışı gövde → 422 (FastAPI/pydantic doğrulaması). Hiçbir uç 500 ile çekirdek hatası
sızdırmaz.

### 4. Değişiklik sırası (yoklama için)
MES değişiklikleri **yoklayarak** (polling) öğrenir: her durum değişikliği tekdüze artan bir `degisiklik` numarası alır.
`GET …?sonra=N` yalnız `degisiklik > N` kayıtları verir. Tezgah'tan MES'e bildirim (webhook) yoktur (tek yön kuralı).

### 5. Saklama
İş emirleri müşteri verisidir: `yerel_parcalar/mes/is-emirleri.json` (kanonik JSON, atomik yazım, SPEC 63 §4 ile aynı
yöntem). Dosya bozuksa Tezgah açılır ama MES uçları 503 ve mesaj verir (SPEC 24a kullanılamaz ekran kuralı); dosya
sessizce sıfırlanmaz.

### 6. Erişim
Tezgah yalnız `127.0.0.1`'e bağlanır (SPEC 24). MES aynı bilgisayarda çalışıyorsa ek ayar gerekmez. MES başka bir
makinedeyse bu SPEC'te **desteklenmez** (açık soru 1). CORS: MES'in tarayıcı ön yüzü doğrudan çağıracaksa yalnız
`yerel_parcalar/mes/ayar.json`'daki `izinli_kokenler` listesi; varsayılan boş (sunucudan sunucuya çağrı CORS
gerektirmez).

## Dosyalar
- **Yeni:** `tezgah/mes/__init__.py`, `tezgah/mes/sema.py` (pydantic modelleri), `tezgah/mes/uclar.py` (router),
  `tezgah/mes/depo.py` (iş emri saklama, durum makinesi), `docs/mes-openapi-v1.json`, `docs/mes-baglantisi.md`
  (MES tarafı için kısa kılavuz: tip üretimi `npx openapi-typescript http://127.0.0.1:8724/api/openapi.json`, yoklama
  örneği), `tests/tezgah/mes/test_*.py`, `durum/64-mes-baglantisi.md`.
- **Değişecek:** `tezgah/sunucu.py`'ye router bağlama satırı. Sahibi "Tezgah uygulaması" thread'idir; değişiklik ona
  dosya olarak gönderilir (ya da A3 kaydıyla `mes` "ekranı" olarak kendiliğinden bağlanır, açık soru 3).
- **Dokunulmayacak:** `cam/`, `atolye/` (yalnız dışa açılanlar çağrılır), `*/model.py`, `pyproject.toml`. MES'in deposu
  bu repoda değildir; TypeScript kodu yazılmaz.

## Arayüz
```python
# tezgah/mes/sema.py  (pydantic; OpenAPI şemasının kaynağı)
class IsEmri(BaseModel): ...            # §2
class IsEmriDurumu(BaseModel): ...      # §3
class Takim(BaseModel): ...
class Sure(BaseModel): ...
class GonderimKaydi(BaseModel): ...     # SPEC 63 §5 + mes_id

# tezgah/mes/depo.py
DURUMLAR = ("alindi", "baglandi", "hazir", "gonderildi", "iptal")
def yukle(yol: Path) -> MesDepo
def koy(d: MesDepo, e: IsEmri) -> IsEmriDurumu                 # eş-etkili; çakışmada MesCakisma
def bagla(d: MesDepo, mes_id: str, is_adi: str) -> IsEmriDurumu
def hazirla(d: MesDepo, mes_id: str) -> IsEmriDurumu            # SPEC 63 denetle; çıktıları dondurur
def iptal(d: MesDepo, mes_id: str, gerekce: str) -> IsEmriDurumu
def degisenler(d: MesDepo, sonra: int) -> list[IsEmriDurumu]

# tezgah/mes/uclar.py
router = APIRouter(prefix="/api/mes/v1")
```

## Kabul kriterleri
`TestClient` ile, `tmp_path` altında uydurma `yerel_parcalar/` ve SPEC 31 örnek işi.
- [ ] **K1 Şema anlık görüntüsü:** `/api/openapi.json`'dan çıkarılan `/api/mes/v1/` alt şeması
  `docs/mes-openapi-v1.json` ile aynı; bir alanı silen ya da türünü değiştiren yama (test içinde) karşılaştırmayı
  kırmızı yapıyor, yeni isteğe bağlı alan sarı uyarıyla geçiyor; `info.title == "Tezgah"`. (`test_sema.py`)
- [ ] **K2 Oluşturma ve eş-etkililik:** `PUT` iki kez aynı gövde → aynı yanıt, `degisiklik` artmıyor; aynı revizyon
  farklı gövde → 409; yeni revizyon → eskisi `iptal`, yenisi `alindi`. (`test_is_emri.py::test_put`)
- [ ] **K3 Durum makinesi:** `alindi → baglandi → hazir → gonderildi` yolu; `alindi`'da `program` → 409; bağlı iş
  parametresi değişince `hazir → baglandi` ve `program` 409; `iptal` gerekçesiz → 422; `gonderildi`'den `iptal`
  kayıt silmeden. (`::test_durum`)
- [ ] **K4 Çıktılar:** `hazir` iş emrinde `program` gövdesi SPEC 31 `post` çıktısıyla bayt bayt aynı ve `X-Sha256`
  tutuyor; `takimlar` föydeki `ToolRow`'larla aynı sırada; `sure.t_parca_s` SPEC 58 `maliyet(n=adet).t_parca_s` ile
  aynı (58 yoksa `skip`); `is-foyu.html` SPEC 38 çıktısıyla aynı. (`test_ciktilar.py`)
- [ ] **K5 Yoklama:** üç değişiklikten sonra `?sonra=1` yalnız son iki kaydı verir, sıra `degisiklik` artan.
  (`::test_yoklama`)
- [ ] **K6 Gönderimler:** SPEC 63 `gonder` bu iş emri için çağrılınca durum `gonderildi`, `gonderimler` listesinde
  `mes_id`'li kayıt (63 yoksa `skip`). (`::test_gonderim`)
- [ ] **K7 Tek yön ve DB yok:** AST taraması: `tezgah/mes/` ve tüm repo (`tests/` hariç) `psycopg`, `psycopg2`,
  `asyncpg`, `sqlalchemy`, `pg8000` içe aktarmıyor; `tezgah/mes/` `httpx`, `requests`, `urllib.request`, `socket`
  içe aktarmıyor (MES'e istek yok). (`test_tek_yon.py`)
- [ ] **K8 Saklama:** depo dosyası atomik yazılıyor (yazım ortasında hata → eski dosya sağlam); bozuk JSON → MES uçları
  503 ve mesaj, dosya değişmemiş; `yerel_parcalar/` repoda yok. (`test_depo.py`)
- [ ] **K9 Hata kuralı:** bilinmeyen alan, `adet = 0`, geçersiz `termin` → 422; bilinmeyen `mes_id` → 404; hiçbir
  senaryoda 500 yok (tüm K testleri boyunca `TestClient(raise_server_exceptions=True)`). (`::test_hatalar`)
- [ ] **K10 Belge:** `docs/mes-baglantisi.md` uç listesi `docs/mes-openapi-v1.json`'daki yollarla aynı küme
  (metin taraması). (`test_belge.py`)
- [ ] Tüm testler yeşil, `ruff check .` ve `ruff format --check .` temiz.

## Bağımlılıklar
SPEC 24 / 24a, 38 `main`'de. SPEC 55 Karar 4 (`info.title`). SPEC 58 ve 63 aynı dalgada: K4 ve K6'nın ilgili alt
koşulları onlar yokken `skip` olur; `sure` ve `maliyet` uçları 58 yokken 503 döner. B1 / 37 (`.3dc` açma) `proje`
alanı için; yoksa yalnız `bagla` ile depo adı bağlanır. Arayüz (`*/model.py`) değişikliği yok.

## Kapsam dışı
- MES'in kendisi, MES veritabanı şeması, TypeScript kodu, MES ön yüzü.
- Tezgah'tan MES'e bildirim (webhook), kuyruk sistemleri (MQTT, Kafka).
- Kimlik doğrulama ve çok kullanıcı: Tezgah yerel ve tek kullanıcılıdır (yol haritası bölüm 6).
- Tezgâh durumu (OEE, makine sinyalleri, MTConnect / OPC UA): ayrı iş.
- Malzeme fiyatı ve stok yönetimi MES'tedir; Tezgah yalnız 58 için yerel fiyat dosyasını okur.

## Kararlar (açık sorular; önerilen cevaplarla kapandı, kullanıcı 2026-10-18 16:06 UTC)
Her maddedeki **Öneri** artık karardır.
1. MES başka bir bilgisayarda (sunucuda) mı çalışıyor? **Öneri:** ilk sürüm yalnız aynı bilgisayar (`127.0.0.1`).
   Sunucudaysa ayrı küçük SPEC: Tezgah'ı yerel ağa açmak + paylaşılan anahtar başlığı (`X-Tezgah-Anahtar`,
   `yerel_parcalar/mes/ayar.json`) + izinli IP listesi. Ağa açmak güvenlik kararıdır, kullanıcı ayrıca onaylar.
2. Değişiklikleri MES yoklayarak mı öğrensin, yoksa Tezgah MES'e bildirsin mi? **Öneri:** yoklama (tek yön kararı; MES
   `?sonra=` ile birkaç saniyede bir sorar). Bildirim istenirse Tezgah'ın MES'e istek atması gerekir, bu da karar ister.
3. MES uçları A3 ekran kaydıyla mı bağlansın? **Öneri:** evet, `mes` başlığı olan, ön yüz sayfası olmayan bir "ekran"
   olarak; böylece `sunucu.py` değişmez ve depo dosyası bozukken 503 kuralı A3'ten gelir. A3 sayfasız ekrana izin
   vermiyorsa küçük A3 eki gerekir (Tezgah sahibi thread'ine sorulur).
4. Programın içine MES iş emri numarası yorum olarak yazılsın mı (`; MES 12345 rev 2`)? **Öneri:** evet, post'un
   mevcut yorum satırı mekanizmasıyla, ASCII ve kontrolörün yorum sözdizimiyle. Program özeti buna göre değişir, bu
   istenen bir şeydir (iş emri başına ayrı program).
