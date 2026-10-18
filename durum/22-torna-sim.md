# DURUM — SPEC 22 torna-sim

Dal: `claude/project-thread-012y8t` · Oturum: bulut

## Sıradaki adım
İskelet push edildi; testler ayrı oturumda yazılacak, sonra cherry-pick ve kod ayrı commit'te.

## Test durumu
| Tarih | Geçen | Kalan | Not |
|---|---|---|---|
| 2026-10-18 | — | — | Sadece SPEC taslağı; kod ve test yok. |

## Son oturum
**2026-10-18**
- `specs/22-torna-sim.md` taslağı: radyal dexel (z sütunu, r aralıkları), Pappus hacmi, `G95`/`G96` süre, kesici kenar boyu,
  tutucu, ayna (`Setup.fixtures`) çarpışması, çakma, SPEC 24 olay listesi.
- SPEC onayı: 2026-10-18 09:45 UTC kart, 10:38 UTC yazılı onay. Profil çıkarma ayrı SPEC ("Katı parçadan torna profili").
- Arayüz eki `LatheTool.edge_len`, `LatheHolder` PR #52 ile `main`'de (`47082f6`); SPEC 05 PR #54 ile `main`'de.
- `cam/sim/radial.py`, `lathe_shape.py`, `lathe_time.py`, `lathe.py` iskeletleri (`NotImplementedError`).

## Açık sorular
_(yok)_
