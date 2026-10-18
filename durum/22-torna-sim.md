# DURUM — SPEC 22 torna-sim

Dal: `claude/project-thread-012y8t` · Oturum: bulut

## Sıradaki adım
Kullanıcı onayı (proje sohbeti, koordinatör üzerinden) ve `cam/model.py` arayüz eki (`LatheTool.edge_len`, `LatheHolder`).
SPEC 05 `main`'e girince `NotImplementedError` iskeleti; testler ayrı oturumda.

## Test durumu
| Tarih | Geçen | Kalan | Not |
|---|---|---|---|
| 2026-10-18 | — | — | Sadece SPEC taslağı; kod ve test yok. |

## Son oturum
**2026-10-18**
- `specs/22-torna-sim.md` taslağı: radyal dexel (z sütunu, r aralıkları), Pappus hacmi, `G95`/`G96` süre, kesici kenar boyu,
  tutucu, ayna (`Setup.fixtures`) çarpışması, çakma, SPEC 24 olay listesi.

## Açık sorular
- Arayüz eki: `LatheTool.edge_len`, `LatheTool.holder` (`LatheHolder`) — "CAM model arayüzü" thread'ine önerildi.
- Katı parçadan dönel profil çıkarma bu SPEC'te değil (ayrı SPEC önerisi); kullanıcı kararı bekliyor.
