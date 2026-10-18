# DURUM — SPEC 49 freze-torna

Dal: `claude/project-thread-k667wt` · Oturum: bulut

## Sıradaki adım
Kod yazıldı, 125 SPEC 49 testi yeşil. GitHub'da pytest + kapi yeşil olunca PR #126 birleşir. Sonra: tezgâhta kuru
çalıştırma (SPEC 48) ile Fanuc / MAPPS M kodları (M13 / M15) ve G12.1 X çap doğrulanır.

## Test durumu
| Tarih | Geçen | Kalan | Not |
|---|---|---|---|
| 2026-10-18 | — | — | Yalnız SPEC metni; kod ve test yok |
| 2026-10-18 | — | — | İskelet (`NotImplementedError`); test yok |
| 2026-10-18 | 125 | 0 | Testler 0d8aba2 (ayrı oturum), kod ayrı commit'te |

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

- Kod (test oturumundan sonra, testlere dokunulmadı):
  - `cam/millturn/istasyon.py` (yeni, paketin içinde): torna-freze profil, istasyon (var / canlı / yön), canlı devir,
    Y kursu, polar ve silindirik denetimi; simülasyon ve post ortak kullanır.
  - Alın cebinde `Cut.stepover` verilmezse takım çapının yarısı (SPEC 03 cebi stepover ister).
  - Kaçık delik girişi takım merkezindeki yüzeyden (x = √(R² − e²)), yaklaşma takım izdüşümündeki en yüksek yüzeyin
    üstünden.
  - Simülasyon: torna 22 ile, sonra `RadialMap` → `TriDexel`, freze 43 `simulate5` (`initial`); ayna halkası freze
    hareketlerinde takım silindiri örnekleriyle ayrıca denetlenir (`ayna_carpma`). Adım ve işlem numaraları programın
    tamamına göre.
  - Post: Fanuc'ta X her zaman çap, Sinumerik DIAMOF ile yarıçap; her yol `OP` yorumuyla takım / istasyon bilgisi
    taşır, okuyucu yolları bundan kurar. Canlı takım durdurma Fanuc `M15`, Sinumerik `M2=5` (taslak, Karar 1).
  - Yollar arası bağlantı hareketi üretilmez: `tool_change` (x, z) verilmezse güvenli nokta yazılmaz; çarpışma
    simülasyonda görünür (43 bağlantı adımı).

## Açık sorular
_(yok)_
