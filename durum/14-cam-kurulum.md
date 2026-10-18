# DURUM — SPEC 14 CAM kurulumu (takım kütüphanesi, kesme verisi, WCS, takım boyu)

Dal: `claude/spec-14-cam-kurulum-05r8z1` · Oturum: bulut

## Sıradaki adım
SPEC onaylandı (kullanıcı, 2026-10-18: 08:54 kart, 09:27 yazılı; yazıcı eki dahil). Testler (ayrı oturum, `a8c1d81`) ve kod dalda; PR #27 CI ve birleşme onayı.

## Test durumu
| Tarih | Geçen | Kalan | Not |
|---|---|---|---|
| 2026-10-18 | — | — | Sadece SPEC taslağı; kod ve test yok. |
| 2026-10-18 | 1199 (`tests/cam`) | 0 | Bağımsız testler (K1–K13) cherry-pick edildi, kod yazıldı; 0 uygulanmamış. Tüm depo main ile birlikte yeşil. |

## Son oturum
**2026-10-18 — kod**
- `cam/cutting.py`, `cam/library.py`, `cam/setups.py`, `cam/tool_length.py`; `write(setup=, length_offsets=)`,
  okuyucuda `G43.1`, `G55`..`G59`. `examples/takim_kutuphanesi.json`, `docs/tezgah-dogrulama.md`.
- Testler `a8c1d81` (oturum `session_018RU4RqAEwZDcYp5xx9GxJC`), kod bu oturumda ayrı commit.

**2026-10-18 — SPEC**
- `specs/14-cam-kurulum.md` yazıldı. Ek A altın metinleri bugünkü yazıcıyla karşılaştırıldı: `setup`'sız
  çıktı, `G55` ve `G43.1` satırları dışında birebir aynı.

## Açık sorular
- Ayrı bir thread `writer.py`'de güvenli Z düzeltmesi yapıyor; main'e girince dala alınacak.
