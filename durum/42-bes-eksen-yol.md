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
- **Açık nokta (test yazarının notu):** takım duvara doğru eğilirse eksen boyunca drop takımı duvarın
  üstüne ya da arkasına oturtabiliyor (eksen doğrusu duvarı deliyor); SPEC bunu çakmasız sayar, gövde
  denetimi yalnız sap / tutucu basamaklarına bakar. K5 testleri yüksek tek yüzlü duvarla bu durumu dışarıda
  bırakıyor. Ayrıca c'nin c₀'dan sapması (eksen doğrusu başka geometriye takıldığında) şu an hata değil.
  Çözüm önerisi (SPEC değişikliği, kullanıcı onayı gerekir): `|c − c₀| > tol` ise noktayı çarpışma sayıp
  kaçınmaya sokmak. SPEC metni şimdilik değişmedi.
