# Durum — SPEC 50 5 eksen kaba, yanak, torik eğim, eksen düzgünleştirme

- SPEC: onaylandı (2026-10-18, 2 dakika kuralı). Açık sorular Kararlar bölümüne yazıldı; Ek A arayüz ayrıntıları.
- Dal: `claude/project-thread-w648u9`. Taban: `main` (3c6b5c3) + B0 (#116, 6077d13) merge.
- İskelet: `cam/multiaxis/rough5.py` (RoughCut, rough5), `cam/multiaxis/swarf.py` (RuledSurface, swarf,
  swarf_error), `cam/multiaxis/smooth.py` (smooth_axes); hepsi NotImplementedError.
- `finish5` torik dalı kod aşamasında `toolpath5.py`'ye eklenecek (06b torik drop, #45 gerekli: K6–K7).
- Testler: ayrı oturum ("5 eksen kaba ve swarf (SPEC 50)" thread'i) yazacak; sonra cherry-pick, kod ayrı commit.
