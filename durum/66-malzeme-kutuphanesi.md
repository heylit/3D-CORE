# DURUM — SPEC 66 Malzeme kütüphanesi ve bağlantıları

Dal: `claude/spec-18-ozellik-agaci-ha61ak` (oturumun verdiği dal; SPEC 18 #73 birleşti, dal main'den yeniden başladı) ·
Oturum: bulut thread "Malzeme kütüphanesi (SPEC 66)"

## Sıradaki adım
B2 (#121) kodu main'e girince main'i al, tam takımı çalıştır, CI (pytest + kapı) yeşilse PR #127'yi birleştir.

## Test durumu
| Tarih | Geçen | Kalan | Not |
|---|---|---|---|
| 2026-10-18 | — | — | Yalnız SPEC metni; kod yok. |
| 2026-10-18 | — | — | İskelet (B2 7ec8f7d üstünde); SPEC 66 testleri henüz yok. |
| 2026-10-18 | 306 | 0 | Yerelde, B2 gövdeleri için commit'lenmeyen geçici uygulamayla. Gerçek B2 gelmeden CI'da `NotImplementedError`. |

## Son oturum
**2026-10-18 — Kod**
- Testler ayrı oturumda (session_017xRvetW16C52caDDUjesbT, dal `claude/project-thread-cw4rwc`, 7a871c6) yazıldı; cherry-pick 48668f8.
- `Kutuphane` (id sıralı, difflib yakın eşleşme), `yerlesik()` (`importlib.resources`, `lru_cache`), kullanıcı dosyası okuma/yazma.
- Köprüler: `bilesen_malzemeleri`, `yogunluk_haritasi` (parça başına tek malzeme), `kutle_tablosu` (`assy.bom.unit_masses`),
  `fem_malzemeleri`, `kesme_tablosu`, `malzeme_maliyeti_eur`.
- `yerlesik.json`: 14 kayıt, `fiyat` yok (D7). C45 `rho` = 7.85e-9 (EN 1991-1-1); DEW föyündeki 7.70 baskı hatası sayıldı.
- `malzeme/__init__.py` değişmedi: `baglanti` core/cam yükler, paket importunda yüklenirse B2 K9 bozulur.

**2026-10-18 — İskelet**
- B2 iskeleti (`claude/spec-34-tolerans-6t5zau`, 7ec8f7d, #121) dala merge edildi.
- `malzeme/kutuphane.py`, `malzeme/baglanti.py` `NotImplementedError` gövdeli; `malzeme/yerlesik.json` boş liste.
- Kaynaklı veri taslağı hazır (scratchpad), kod commit'inde girilecek.

**2026-10-18 — SPEC metni**
- Taslak `/mnt/project-files/spec-taslak/dalga-6/66-malzeme-kutuphanesi.md` onaylandı (14:52 UTC, otomatik kabul).
- `specs/66-malzeme-kutuphanesi.md` yazıldı; kararlar D1–D6 metnin sonunda.
- D7 (15:20, otomatik kabul): yerleşik kayıtlarda `fiyat` boş; K2 listesinden çıktı. D8: kaynak notları.
- Bağımlılık: B2 ("Malzeme arayüzü (B2)" thread'i) henüz yok.
