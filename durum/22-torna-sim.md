# DURUM — SPEC 22 torna-sim

Dal: `claude/project-thread-012y8t` · Oturum: bulut (kod: session_01774ib8WCsNwcEC8uqzHvZh)

## Sıradaki adım
PR #41 CI (pytest + kapı) yeşilse birleştir.

## Test durumu
| Tarih | Geçen | Kalan | Not |
|---|---|---|---|
| 2026-10-18 | 173 | 0 | Testler `9a2b157`, `97c7159`, `787c85e` (session_012CV12jWqYWKvYs5L85ZpEU, dal `claude/project-thread-py581v`). |

## Son oturum
**2026-10-18**
- SPEC onayı: 09:45 UTC kart, 10:38 UTC yazılı onay; E4 11:13 UTC; Ek 1 (denetim kesimden sonra) ve Ek 2 (gövde
  uzantısı eksende kırpılır) 11:24 UTC.
- Kod: `cam/sim/radial.py` (radyal dexel, `profile_rmap`, `mesh_rmap`, `part_rmap`), `lathe_shape.py` (kesici bölge,
  gövde, tutucu, matkap beşgeni, kesin süpürme aralığı), `lathe_time.py` (`G95`/`G96` kapalı form), `lathe.py`
  (sürücü, çarpışmalar, olay listesi).
- Ek 3 (11:42 UTC onaylı): taraf, yolun kuralı sağlayan ilk noktasından (initial ile stok içinde başlayan yol için).

## Açık sorular
_(yok)_ — K12, K16 test beklentileri test oturumunda düzeltildi; SPEC 20 kaba yol omuz çakması ayrı thread'de.
