# DURUM — SPEC 64 MES bağlantısı (yerel REST API)

Dal: `claude/project-thread-nkn98y` · Oturum: bulut

## Sıradaki adım
CI yeşilse birleştirme. SPEC 58 birleşince `sure` / `maliyet` uçlarının bağlanması (şimdi 503).

## Test durumu
| Tarih | Geçen | Kalan | Not |
|---|---|---|---|
| 2026-10-18 | — | — | iskelet; gövdeler `NotImplementedError`, test yok |
| 2026-10-18 | 48 | 0 | testler ayrı oturumda (`2087edf` + düzeltme `65e6eac`, cherry-pick); kod commit'i testlere dokunmadı |

## Son oturum
**2026-10-18 — kod**
- `depo.py`: dosya her işlemde okunur ve atomik yazılır (geçici dosya + fsync + `os.replace`); bir PUT bir
  `degisiklik`. Yeni revizyonda eskisi aynı numarayla `iptal`. Program = `post(..., program_no=1)` + POST yorumunun
  ardına `MES <id> REV <rev>` (Heidenhain'de satırlar yeniden numaralanır). Föy:
  `render_html(build_job_sheet("<parca_no> rev <parca_rev>", [kurulum], [ops], ToolLibrary(ops'un takımları), malzeme,
  dialect_for(profil), program_no=1, names=...))`. `tazele` bağlı işin programını / föyünü yeniden üretip özetle karşılaştırır.
- `uclar.py`: her istekte `yukle` → `esitle` (SPEC 63 kaydı) → `tazele`; MES hataları `tezgah/ekranlar/mes.py`'nin
  `kur`'unda 404 / 409 / 503'e eşlenir. `sure` / `maliyet` SPEC 58 bağlanana kadar 503.
- `docs/mes-openapi-v1.json` `sema.alt_sema(openapi)` çıktısı (kanonik JSON); `docs/mes-baglantisi.md` kılavuz.

**2026-10-18 — iskelet**
- `specs/64-mes-baglantisi.md`: onaylı metin (kullanıcı 16:06 UTC) olduğu gibi.
- `tezgah/mes/sema.py` pydantic modelleri tam (OpenAPI şeması bunlardan çıkar); `depo.py` ve `uclar.py`
  gövdeleri `NotImplementedError`.
- Karar 3: A3 sayfasız ekrana zaten izin veriyor. `tezgah/ekranlar/mes.py` `router` ve `tus` olmadan kaydolur
  (sekme olmaz, `/api/ekranlar`'da görünmez); `/api/mes/v1` uçları `kur` kancasıyla bağlanır. `sunucu.py`
  ve A3 değişmedi. A3'ün `hazir` → 503 bağımlılığı yalnız `/api/ekran/<ad>` router'ına uygulandığı için bozuk
  depo 503'ü MES uçlarının kendi bağımlılığından gelir.
- Varsayılanlar (küçük belirsizlikler):
  - Yollar çalışma klasörüne göre: `yerel_parcalar/mes/is-emirleri.json`, `yerel_parcalar/mes/ayar.json`,
    SPEC 63 kaydı `yerel_parcalar/gonderim-kaydi.jsonl`.
  - `mes_id` deseni `[A-Za-z0-9_.-]{1,40}` (yorum satırı ASCII kalsın); dışı 422. Yoldaki `mes_id` gövdedekiyle
    aynı olmalı, değilse 422.
  - Karar 4 ile K4 "bayt bayt aynı": program = SPEC 31 `post` çıktısı + POST yorumunun hemen ardına tek satır
    `MES <mes_id> REV <revizyon>` yorumu (kontrolörün yorum sözdizimiyle). K4 karşılaştırması bu satır
    çıkarılınca `post` çıktısıyla bayt bayt aynılıktır (Heidenhain'de satır numaraları sonraki satırlarda bir kayar).
  - `gonderildi` geçişi: SPEC 63 kaydındaki `program.ozet` iş emrinin dondurulmuş `program_ozeti` (programın
    UTF-8 sha256'sı = `X-Sha256`) ile eşleşirse. `GonderimKaydi.mes_id` bu eşleşmeden doldurulur.
  - `tezgah` alanı `builtin_machines()` içinden adla çözülür; boşsa işin lehçesindeki varsayılan profil.
  - SPEC 58 / 63 yokken: `sure`, `maliyet` 503; `hazirla` 63'ün `denetle`'si yoksa yalnız `post` (CamError → 422).

## Açık sorular
_(yok)_
