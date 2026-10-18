# DURUM — SPEC 68d Yüksek çevrimli yorulma (Marin, Basquin, Goodman)

Dal: `claude/project-thread-wmosjl` · Oturum: bulut thread "Çözücü düzeltmeleri" (kodlayıcı)

## Sıradaki adım
Test commit'i (ayrı `dogrulayici` thread'i) gelince alınacak, sonra K1–K6, K8 kodu. K7 67b'yi bekler.

## Test durumu
| Tarih | Geçen | Kalan | Not |
|---|---|---|---|
| 2026-10-18 | – | – | İskelet: `analiz/yorulma.py` arayüzü, gövdeler `NotImplementedError`. Testler henüz yok. |

## Son oturum
**2026-10-18 — İskelet**
- Onaylı metin `specs/68d-yorulma.md`'ye kondu (kullanıcı onayı 16:19).
- `analiz/yorulma.py`: `YUZEYLER`, `Marin`, `dayanim_siniri`, `goodman`, `omur`, `Yorulma`, `yorulma`,
  `parca_yorulmasi` imzaları SPEC'teki gibi; `analiz/__init__.py`'ye eklendi.
- Dal B2 iskeletinin (PR #121, 7ec8f7d) üstünde: `malzeme.model.Malzeme` oradan. B2 birleşince main alınacak.

## Açık sorular
- Hata sınıfı: SPEC "ModelError" diyor. `analiz/` `core.model.ModelError` kullanıyor; `malzeme.model` kendi
  `ModelError`'ını tanımlıyor (ikisi de `ValueError`). Kod `core.model.ModelError` fırlatacak.
- `analiz/dayanim.py` (67b) bu dalda yok; `parca_yorulmasi` ve K7 67b birleşince.
