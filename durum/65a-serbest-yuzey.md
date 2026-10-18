# DURUM — SPEC 65a serbest-yuzey

Dal: `claude/project-thread-8dzgzc` · Oturum: bulut (kod)

## Sıradaki adım
Test thread'inin commit'ini cherry-pick et, sonra `geometry/serbest.py` ve `agac.py` gövdelerini yaz.

## Test durumu
| Tarih | Geçen | Kalan | Not |
|---|---|---|---|
| 2026-10-18 | — | — | İskelet: arayüz + NotImplementedError gövdeler; testler ayrı thread'de yazılıyor |

## Son oturum
**2026-10-18**
- Onaylı SPEC metni `specs/65a-serbest-yuzey.md`'ye kopyalandı (değiştirilmeden).
- İskelet: `geometry/serbest.py` (yol tipleri Cizgi / Yay / Spline / Yol; loft, sweep, B-spline OCCT
  çağrılarının imzaları), `geometry/agac.py`'ye Loft, Sweep, BSplineYuzey unsurları (doğrulama, bağımlılık,
  kurulum dağıtımı; gövdeler ve JSON NotImplementedError).
- Arayüz notları (docstring'de): hatalar `GeometryError` (ValueError; SPEC 18 ile aynı), `islem="cikar"`
  SPEC 18'deki "kes" anlamında; BSplineYuzey kalınlaştırma gövde yoksa yeni gövde, varsa ekle.

## Açık sorular
_(yok)_
