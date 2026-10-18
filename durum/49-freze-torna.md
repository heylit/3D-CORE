# DURUM — SPEC 49 freze-torna

Dal: `claude/project-thread-k667wt` · Oturum: bulut

## Sıradaki adım
İskelet B0 (6077d13, PR #116) üstünde push edildi; ayrı oturum testleri yazacak. Sonra test commit'i cherry-pick,
kod ayrı commit'te.

## Test durumu
| Tarih | Geçen | Kalan | Not |
|---|---|---|---|
| 2026-10-18 | — | — | Yalnız SPEC metni; kod ve test yok |
| 2026-10-18 | — | — | İskelet (`NotImplementedError`); test yok |

## Son oturum
**2026-10-18**
- `specs/49-freze-torna.md` onaylı taslaktan yazıldı; açık sorular "Kararlar" bölümünde (MAPPS varsayımı, merkezden geçişte
  `CamError`, `G12.1`'de X çap).
- Bağımlılıklar: B0 (6077d13), SPEC 43 tri-dexel ve SPEC 31 kodu `main`'de olmalı (kod aşamasında denetlenecek).
- İskelet: `cam/millturn/` (`indeks`, `polar`, `ops`), `cam/sim/millturn.py`, `cam/post/millturn.py`; gövdeler
  `NotImplementedError`. B0 (6077d13) dala merge edildi.
- SPEC Arayüz'ünün yorumları (testler bunlara göre yazılsın):
  - Canlı takım işlemleri kesme verisini `LiveCut(feed, plunge_feed, rpm, clearance=1, safe=5)` ile alır; alın
    işlemleri SPEC 03'teki `Cut`'ı.
  - `face_contour` ikiye ayrıldı: `face_pocket(region, tool, cut)` ve `face_contour(profile, tool, cut, side)`;
    derinlik `cut`'tan, ayrı `z` yok.
  - Her işlem isteğe bağlı `station`, `machine` alır (machine verilirse canlılık, Y kursu, polar denetimi).
  - Yardımcılar: `indeks.c_for / shortest / index_angle`, `polar.to_polar / from_polar / from_cyl / polar_check /
    cyl_chords / to_cartesian`, `sim.millturn.rmap_to_tridexel / to_part_frame / simulate_mt`,
    `post.millturn.post_mt / read_mt`.
- G-code yazıcısı (`cam/gcode/writer.py`) polar / silindirik / `Move.c` için hâlâ `CamError` veriyor; SPEC 49 bunları
  `cam/post/millturn.py`'de yazar, ortak yazıcıya dokunmaz.

## Açık sorular
_(yok)_
