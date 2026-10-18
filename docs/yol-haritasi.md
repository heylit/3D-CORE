# Yol haritası

Her adımın sonunda çalışan ve DOĞRULANMIŞ bir şey olur. Doğrulamadan sonraki adıma geçilmez.

## Aşama 1 — Analiz motoru
| # | SPEC | Konu | Bitti sayılır |
|---|------|------|---------------|
| 1 | 01-bar | 1D çubuk + çözücü iskeleti | δ = FL/EA ve tüm benchmark'lar yeşil |
| 2 | 02-truss2d | 2D kafes (koordinat dönüşümü) | Ders kitabı kafes örneği çubuk kuvvetleri tutuyor |
| 3 | 03-tri3 | Düzlem gerilme CST üçgen | Patch test + konsol kiriş yakınsaması |
| 4 | 04-gmsh | Gmsh ile mesh, delikli plaka | Delik kenarında Kt ≈ 3 (Kirsch) |
| 5 | 05-vonmises | Von Mises + renk haritası | Görsel sonuç + değer kontrolü |

## Aşama 2 — Geometri ve CAD
| 6 | 06-viewer | PyVista ile STL/STEP görüntüleme |
| 7 | 07-build123d | Kodla parametrik parça (flanş, braket) -> STEP |
| 8 | 08-sketch | 2D kısıt çözücü (Newton-Raphson) |

## Aşama 3 — Birleştirme
| 9  | 09-tet4 | 3D tetrahedron, uçtan uca braket analizi |
| 10 | 10-calculix | CalculiX çapraz kontrolü (fark < %1) |
| 11 | 11-ui | Basit arayüz (PySide veya FastAPI + HTML) |
| 12 | —  | Niş seçimi: sac metal tasarım + açılım + dayanım |
