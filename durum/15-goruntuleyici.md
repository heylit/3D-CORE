# DURUM — SPEC 15 goruntuleyici

Dal: `claude/spec-15-goruntuleyici-d318ku` (SPEC + testler) · Kod: `claude/spec-15-goruntuleyici-kod-q8t5es` (ayrı bulut oturumu)

## Sıradaki adım
Kod commit'i PR #25 dalına alınır, `main` merge edilir, CI yeşil olunca PR hazır duruma alınır.

## Test durumu
| Tarih | Geçen | Kalan | Not |
|---|---|---|---|
| 2026-10-18 | 0 | 41 uygulanmamış | Testler + arayüz taslakları (NotImplementedError) |
| 2026-10-18 | 41 | 0 | Kod yazıldı (ayrı oturum); tüm paket 1000 geçti, 12 atlandı (ccx / rs274 yok) |

## Son oturum
**2026-10-18 (kod oturumu)**
- `viz/scene.py`: yay çokgeni SPEC formülüyle (`n = max(1, ⌈|Δθ| / min(φ_max, π/2)⌉)`), son nokta tam `end`;
  `split_rapid_feed` art arda aynı türü birleştirir; `assembly_meshes` aynı parçayı bir kez üçgenler;
  `stock_box` köşe indeksi `4·ix + 2·iy + iz`, kenarlar tek bitin değiştiği çiftler.
- `viz/plot.py`: yeni sahne beyaz arka planla kurulur; çizgiler `lighting=False` (renk saf görünür);
  `screenshot` görünümü ayarlar, paralel izdüşümü açar/kapatır, `reset_camera` ile sahneye oturtur.
- `viz/__main__.py`: argparse; okuma / model hataları (`OSError`, `ValueError` ve alt sınıfları) Türkçe
  iletiyle çıkış kodu 1. Uzantı ve dosya varlığı sahne kurulmadan kontrol edilir (PNG yazılmaz).
- Testlere ve SPEC metnine dokunulmadı.

**2026-10-18**
- PR #18 birleşti: CI ve bulut kurulumu `.[viz]` + `libosmesa6` kurar, VTK ekransız OSMesa ile çizer
  (`VTK_DEFAULT_OPENGL_WINDOW=vtkOSOpenGLRenderWindow`).
- SPEC metni kullanıcı tarafından onaylandı (proje sohbeti, 08:29 UTC). K3 düzeltmesi (tol 1e-4 → 1e-5,
  göreli boy hatası ≈ tol/(3r)) 08:40 UTC'de onaylandı.
- Testler SPEC'ten, kod yokken yazıldı: `tests/viz/test_scene.py` (K1–K9), `test_plot.py` (K10–K14),
  `test_cli.py` (K15). Arayüz taslakları `viz/*.py` içinde NotImplementedError fırlatır.

## Açık sorular / notlar
- Komut satırı testleri `viz.__main__.main(argv) -> int` fonksiyonunu süreç içinde çağırır
  (`python -m viz` → `sys.exit(main())`); bu imza testlerle sabitlendi.
- Aktör sınırları `plotter.actors[ad].GetBounds()` ile okunur; aktörler SPEC'teki adlarla eklenmeli.
- Piksel testleri arka planın beyaz olmasına ve G0 = saf kırmızı, G1 = saf mavi çizgilere dayanır
  (aydınlatma çizgi rengini koyulaştırmamalı).
- Yerelde: `pip install -e ".[dev,cad,viz]"`; Windows'ta ek ayar gerekmez.
