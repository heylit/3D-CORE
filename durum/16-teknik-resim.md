# DURUM — SPEC 16 teknik-resim

Dal: `claude/spec-16-teknik-resim-u8ylv2` · PR #22 · Oturum: bulut

## Sıradaki adım
CI yeşil olunca PR #22 hazır yapılır; birleştirme onayı proje sohbetinde.

## Test durumu
| Tarih | Geçen | Kalan | Not |
|---|---|---|---|
| 2026-10-18 | 129 (tests/geometry/drawing) | 0 | ek testler `be29183` dahil; `--uygulanmamis-hata` ile tüm depo 0 failed |

## Son oturum
**2026-10-18**
- SPEC kullanıcı tarafından onaylandı (proje sohbeti, 08:29 UTC).
- Testler ayrı oturumda yazıldı (`d17ae3a`, dal `claude/spec-16-teknik-resim-testler-ertqoo`), bu dala cherry-pick edildi.
- Kod `geometry/drawing/` altında testler görülmeden yazıldı; testler ilk çalıştırmada yeşil.
- HLR doğrudan OCP `HLRBRep_HLRToShape` ile: sadece `VCompound`/`OutLine*` (teğet kenarlar yok). build123d
  `project_to_viewport` teğet (Rg1) kenarları da verdiği için kullanılmadı.
- İzdüşen daireler dejenere B-spline gelir; `classify` PCA ile doğru, Kåsa en küçük kareler ile çember tanır.

## Yorum notları (koordinatör ve test oturumu, 2026-10-18)
1. Görünüşler arası boşluk kağıt üzerinde `g`'dir, ölçekten bağımsız (model biriminde `g/k`).
2. Ön görünüş A-A kesitiyle değişince temel ölçüler kesit görünüşüne yazılır.
3. DXF R12'de `Ø` → `%%c` (okurken geri çevrilir).

## Açık sorular / notlar
- DXF'te `Polyline2D` `LINE` dizisi olarak yazıldığı için geri okumada varlık sayısı artar (SPEC'e uygun).
- `ARC` açıları DXF'te [0, 360) aralığına indirgenir; geri okunan `a0` farklı temsil olabilir (aynı yay).
