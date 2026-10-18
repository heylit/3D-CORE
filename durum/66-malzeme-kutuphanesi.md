# DURUM — SPEC 66 Malzeme kütüphanesi ve bağlantıları

Dal: `claude/spec-18-ozellik-agaci-ha61ak` (oturumun verdiği dal; SPEC 18 #73 birleşti, dal main'den yeniden başladı) ·
Oturum: bulut thread "Malzeme kütüphanesi (SPEC 66)"

## Sıradaki adım
Bağımsız test commit'ini cherry-pick et, sonra kodu (yerleşik veri + köprüler) ayrı commit'te yaz. B2 (#121) main'e girmeden birleştirme yok.

## Test durumu
| Tarih | Geçen | Kalan | Not |
|---|---|---|---|
| 2026-10-18 | — | — | Yalnız SPEC metni; kod yok. |
| 2026-10-18 | — | — | İskelet (B2 7ec8f7d üstünde); SPEC 66 testleri henüz yok. |

## Son oturum
**2026-10-18 — İskelet**
- B2 iskeleti (`claude/spec-34-tolerans-6t5zau`, 7ec8f7d, #121) dala merge edildi.
- `malzeme/kutuphane.py`, `malzeme/baglanti.py` `NotImplementedError` gövdeli; `malzeme/yerlesik.json` boş liste.
- Kaynaklı veri taslağı hazır (scratchpad), kod commit'inde girilecek.

**2026-10-18 — SPEC metni**
- Taslak `/mnt/project-files/spec-taslak/dalga-6/66-malzeme-kutuphanesi.md` onaylandı (14:52 UTC, otomatik kabul).
- `specs/66-malzeme-kutuphanesi.md` yazıldı; kararlar D1–D6 metnin sonunda.
- D7 (15:20, otomatik kabul): yerleşik kayıtlarda `fiyat` boş; K2 listesinden çıktı. D8: kaynak notları.
- Bağımlılık: B2 ("Malzeme arayüzü (B2)" thread'i) henüz yok.
