# DURUM — SPEC 15 goruntuleyici

Dal: `claude/spec-15-goruntuleyici-d318ku` · Oturum: bulut (testler), kod ayrı oturumda

## Sıradaki adım
`yazici` oturumu `viz/scene.py`, `viz/plot.py`, `viz/__main__.py` gövdelerini yazar (testlere dokunmadan);
41 test yeşil olunca PR hazır duruma alınır.

## Test durumu
| Tarih | Geçen | Kalan | Not |
|---|---|---|---|
| 2026-10-18 | 0 | 41 uygulanmamış | Testler + arayüz taslakları (NotImplementedError) |

## Son oturum
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
