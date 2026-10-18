# DURUM — SPEC 38 is-foyu

Dal: `claude/spec-38-is-foyu-y2a9bm` · Oturum: bulut

## Sıradaki adım
İskelet push edildi; ayrı test thread'inin test commit'i cherry-pick edilecek, sonra kod ayrı commit'te.

## Test durumu
| Tarih | Geçen | Kalan | Not |
|---|---|---|---|
| 2026-10-18 | — | — | Yalnız SPEC metni ve `NotImplementedError` iskeleti; test yok |

## Son oturum
**2026-10-18**
- `specs/38-is-foyu.md` taslağı yazıldı: freze iş föyü (takım listesi ve boy ofsetleri, WCS tarifi, SPEC 05 süre
  modeli, SPEC 16 ile bağlama resmi, ISO 2768-1 ölçüm listesi, işe özel doğrulama maddeleri), HTML + SVG çıktı,
  SPEC 29 `MillPlan` uyarlayıcısı; `docs/tezgah-dogrulama.md`'ye "6. İş föyü" bölümü.
- Arayüz (`*/model.py`) değişikliği gerekmiyor. `pyproject.toml`'a `"atolye*"` include satırı ayrı PR'da (sahibi:
  "Durum tablosu ve kurulum belgeleri" thread'i).
- SPEC metni önerilerle onaylandı (kullanıcı, 2026-10-18 11:13, Dalga 5 toplu yazılı onay): torna föyü ayrı 38b,
  üst düzey `atolye/`, ISO 2768-1 `m` varsayılan, süre SPEC 05 modeliyle "tahmin" etiketli.
- `atolye/` iskeleti (veri tipleri tam, işlevler `NotImplementedError`) yazıldı.

## Açık sorular
_(yok)_
