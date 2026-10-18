# DURUM — SPEC 38 is-foyu

Dal: `claude/spec-38-is-foyu-y2a9bm` · Oturum: bulut

## Sıradaki adım
SPEC metni kullanıcı onayını bekliyor; onaydan sonra `NotImplementedError` iskeleti, ayrı test thread'i, kod.

## Test durumu
| Tarih | Geçen | Kalan | Not |
|---|---|---|---|
| 2026-10-18 | — | — | Yalnız SPEC metni; kod ve test yok |

## Son oturum
**2026-10-18**
- `specs/38-is-foyu.md` taslağı yazıldı: freze iş föyü (takım listesi ve boy ofsetleri, WCS tarifi, SPEC 05 süre
  modeli, SPEC 16 ile bağlama resmi, ISO 2768-1 ölçüm listesi, işe özel doğrulama maddeleri), HTML + SVG çıktı,
  SPEC 29 `MillPlan` uyarlayıcısı; `docs/tezgah-dogrulama.md`'ye "6. İş föyü" bölümü.
- Arayüz (`*/model.py`) değişikliği gerekmiyor. `pyproject.toml`'a `"atolye*"` include satırı ayrı PR'da (sahibi:
  "Durum tablosu ve kurulum belgeleri" thread'i).

## Açık sorular
1. Torna iş föyü bu SPEC'te mi? Önerilen: hayır, ayrı ek 38b (SPEC 05 süre modeli yalnız G17).
2. Paket yeri: üst düzey `atolye/` (H15 satırı) mı, `pyproject` değişikliği gerektirmeyen `cam/atolye/` mı? Önerilen: `atolye/`.
3. Genel tolerans sınıfı varsayılanı ISO 2768-1 `m` mi? Önerilen: evet (parametreyle değişir).
4. Süre SPEC 05 modeliyle (güvenli Z geri çekmeleri hariç, "tahmin" etiketli) yeterli mi? Önerilen: evet.
