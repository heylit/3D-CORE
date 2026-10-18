# DURUM — SPEC 05 talaş simülasyonu, süre, çakma ve çarpışma

Dal: `claude/spec-05-cam-sim-ch33p2` · Oturum: bulut

## Sıradaki adım
Bağımsız test oturumunun test commit'ini cherry-pick ile al, kodu ayrı commit'te yaz, testleri yeşile çek.

## Test durumu
| Tarih | Geçen | Kalan | Not |
|---|---|---|---|
| 2026-10-18 | — | — | Sadece SPEC taslağı; kod ve test yok. |

## Son oturum
**2026-10-18**
- `specs/05-cam-sim.md` taslağı yazıldı: z-haritası, süpürme zarfı (düz kapalı form, küresel/köşe radyüslü
  dışbükey minimizasyon), gövde basamakları ile sap/tutucu çarpışması, hızlı çarpma, mesh'ten parça z-haritası
  ile çakma, trapez süre, SPEC 24 için olay listesi (CSR).
- Kararlar koordinatöre gönderildi (aşağıda).

- SPEC onaylandı (08:55 kapsam: tek yönlü dexel dahil, özellik okuma ayrı SPEC; 09:23 dexel eki).
- `NotImplementedError` gövdeli `cam/sim/` iskeleti push edildi.

## Açık sorular
- Matkap uç açısı modelde yok; matkap düz uçlu kabul edildi (ileride arayüz PR'ı).
