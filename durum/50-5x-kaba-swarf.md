# Durum — SPEC 50 5 eksen kaba, yanak, torik eğim, eksen düzgünleştirme

- SPEC: onaylandı (2026-10-18, 2 dakika kuralı). Açık sorular Kararlar bölümüne yazıldı; Ek A arayüz ayrıntıları.
- Dal: `claude/project-thread-w648u9` (PR #129). Taban: `main` (B0 #116 ve 06b #45 dahil).
- İskelet: 0966391 + 4d8ebe1 (Ek A). Testler: 564d53a (ayrı oturum, `claude/project-thread-e295er`), cherry-pick.
- Kod: `cam/multiaxis/swarf.py` (RuledSurface, swarf, swarf_error), `cam/multiaxis/smooth.py` (smooth_axes),
  `cam/multiaxis/rough5.py` (RoughCut, rough5), `cam/multiaxis/toolpath5.py` (finish5 torik dalı).
- Uygulama kararları (SPEC'in açık bıraktığı ayrıntılar):
  - swarf_error: aday yamalar, cetvel parçasının eksene dik uzaklığı − yama genişliği < R ile süzülür;
    kaba ızgara (n_check × n_check) sonra en büyük noktanın çevresinde 12 adım yerel daraltma.
  - swarf yalnız köşesiz düz uç kabul eder (torik köşe silindir değildir).
  - smooth_axes: kesme dizisi = ekseni dolu, aynı ilerlemeli ardışık G1'ler (dalma ayrı dizi).
    Torikte yeni eksen eski uçtan geçen doğruda 42 drop'uyla; kin verilirse ulaşılamayan eksen eski kalır.
  - finish5 torik: sürüş noktası düşey drop ucu + R·ẑ; Ek A |c − c₀| denetimi yalnız küresel uçta.
  - rough5: ds_min = 0.05 (DS_MIN; SPEC Ek A, kullanıcı onayıyla düzeltildi).
    Hava atlama: tek yolun 43 simülasyonunda v_min'den az kaldıran ardışık G1'ler z_safe'te G0 bağlantıya
    (yukarı, üstten, aşağı) çevrilir. Son stok yolların sırayla simülasyonu (yollar arası bağlantı yok).
