# Durum — SPEC 42 Eş zamanlı 5 eksen takım yolu

- SPEC: onaylandı (2026-10-18 10:38 UTC). Dal: `claude/project-thread-w648u9` (PR #97).
- Bağımlılık: SPEC 41 main'de (#51), SPEC 06 drop-cutter, SPEC 05 `body_steps` main'de.
- İskelet: d838f1b. Testler: 00000ae (ayrı oturum, `claude/project-thread-dompr6`), 56 test, cherry-pick ile alındı.
- Kod: `cam/multiaxis/toolpath5.py` (drop_along, surface_normal, Orientation, Avoid, finish5),
  `cam/multiaxis/linearize.py` (joint_path, deviation, linearize, inverse_time). 56/56 yeşil.
- Uygulama kararları (SPEC'in açık bıraktığı ayrıntılar):
  - Sürüş noktaları 06 `_raster_cl` (aynı sıra / uyarlamalı Z kuralı); ilerleme yönü komşu merkezlerin
    merkezi farkı, araya eklenen noktada iki komşunun farkı.
  - Kaçınma `sabit` / `noktaya` / `noktadan`'da da stratejinin ekseni f etrafında döndürülerek uygulanır;
    `max_tilt`'i aşan aday atlanır.
  - Giriş / çıkış: eksen doğrusu üstünde z_safe'ten G0, clearance kadar yukarıdan G1 dalma, eksen boyunca G0 çıkış.
  - `linearize` eklem değerlerini çıkış yolunun sırasıyla hesaplar (joint_path(çıkış) ile aynı).
  - `inverse_time`: ilerlemesi olmayan (G0) uzunluklu hareket → CamError.
- Duvar eğimi açık noktası kapandı: SPEC Ek A (|c − c₀| > tol → çarpışma), 2 dakika kuralıyla onaylandı
  (2026-10-18 13:39 UTC). Regresyon testi ayrı oturumda yazılacak; kod ayrı commit'te.
