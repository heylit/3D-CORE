# MES bağlantısı (SPEC 64) — MES tarafı için kısa kılavuz

Tezgah, MES'in aynı bilgisayardan çağırdığı yerel bir REST API açar (`http://127.0.0.1:8724`, uçlar `/api/mes/v1` altında).
Yön tek taraflıdır: MES Tezgah'a istek atar, Tezgah MES'e hiçbir zaman istek atmaz ve MES veritabanına bağlanmaz.

## Tip üretimi
MES (TypeScript) tipleri çalışan Tezgah'ın şemasından üretilir:

```sh
npx openapi-typescript http://127.0.0.1:8724/api/openapi.json -o src/tezgah-api.d.ts
```

Şemanın MES uçlarına ait kısmının anlık görüntüsü repodadır: `docs/mes-openapi-v1.json`. `GET /api/mes/v1/saglik`
yanıtındaki `sema_ozeti` bu dosyanın sha256'sıdır; MES kendi ürettiği tiplerin hangi şemadan geldiğini buradan
denetler. `v1` içinde yalnız ekleme yapılır (yeni uç, isteğe bağlı yeni alan).

## Uçlar
| Yöntem | Yol | Açıklama |
|---|---|---|
| GET | `/api/mes/v1/saglik` | `{api, tezgah_surum, sema_ozeti}` |
| GET | `/api/mes/v1/is-emirleri` | `?durum=&sonra=`; `degisiklik > sonra` olan iş emirleri, artan sırada |
| PUT | `/api/mes/v1/is-emirleri/{mes_id}` | iş emri oluştur / yeni revizyon (eş-etkili; aynı revizyon farklı gövde → 409) |
| GET | `/api/mes/v1/is-emirleri/{mes_id}` | iş emri durumu (bilinmeyen → 404) |
| POST | `/api/mes/v1/is-emirleri/{mes_id}/iptal` | `{gerekce}` (boş → 422) |
| GET | `/api/mes/v1/is-emirleri/{mes_id}/program` | NC programı, `text/plain`, başlık `X-Sha256` (yalnız `hazir` / `gonderildi`, değilse 409) |
| GET | `/api/mes/v1/is-emirleri/{mes_id}/takimlar` | takım listesi (iş föyünden) |
| GET | `/api/mes/v1/is-emirleri/{mes_id}/sure` | parça başı süre (SPEC 58 yokken 503) |
| GET | `/api/mes/v1/is-emirleri/{mes_id}/maliyet` | maliyet dökümü (SPEC 58 yokken 503) |
| GET | `/api/mes/v1/is-emirleri/{mes_id}/is-foyu.html` | iş föyü, `text/html` |
| GET | `/api/mes/v1/gonderimler` | `?sonra=`; tezgâha gönderim kayıtları, eşleşen `mes_id` ile |

Hatalar: gövde `{"detail": ...}`; şema dışı gövde ve çekirdek hataları 422, bilinmeyen kayıt 404, durum çakışması
409, Tezgah tarafındaki iş emri dosyası bozuksa 503.

## Durumlar
`alindi → baglandi → hazir → gonderildi`, her durumdan `iptal`. Bağlama ve hazırlama Tezgah'ta yapılır. Bağlı iş
sonradan değişirse `hazir` iş emri `baglandi`'ya döner; bayat program verilmez. Programın POST yorumunun hemen
ardında `MES <mes_id> REV <revizyon>` yorum satırı vardır.

## Yoklama örneği
```ts
let sonra = 0;
setInterval(async () => {
  const r = await fetch(`http://127.0.0.1:8724/api/mes/v1/is-emirleri?sonra=${sonra}`);
  const degisenler = await r.json();
  for (const k of degisenler) {
    sonra = Math.max(sonra, k.degisiklik);
    // k.is_emri.mes_id, k.durum, k.ciktilar ...
  }
}, 5000);
```

## Erişim
Tezgah yalnız `127.0.0.1`'e bağlanır. MES'in tarayıcı ön yüzü doğrudan çağıracaksa izinli kökenler
`yerel_parcalar/mes/ayar.json` dosyasına yazılır: `{"izinli_kokenler": ["http://127.0.0.1:3000"]}` (varsayılan boş).
İş emirleri `yerel_parcalar/mes/is-emirleri.json` dosyasında durur; bu klasör repoya girmez.
