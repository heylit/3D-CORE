# DURUM — SPEC 38 is-foyu

Dal: `claude/spec-38-is-foyu-y2a9bm` · Oturum: bulut

## Sıradaki adım
Kod yazıldı; PR #69'da pytest + kapı yeşilse birleştir. SPEC 29 birleşince K10 (`test_plan.py`) atlanmadan çalışır.

## Test durumu
| Tarih | Geçen | Kalan | Not |
|---|---|---|---|
| 2026-10-18 | — | — | Yalnız SPEC metni ve `NotImplementedError` iskeleti; test yok |
| 2026-10-18 | 106 | 0 | `tests/atolye/` (test commit 84b2e94); K10 SPEC 29 bekliyor (1 atlandı) |

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
- Testler ayrı oturumda yazıldı (84b2e94, cherry-pick). Kod: `atolye/` (is_foyu, olcum, baglama, html, plan) ve
  `docs/tezgah-dogrulama.md` "## 6. İş föyü" bölümü.
- Not (SPEC metni ile K6 arasındaki çelişki): K6 metni "T2 `DrillOp` derinliği yok" der, ama Ek A'da T2 op'u bir
  `Toolpath`'tir; §6'ya göre Toolpath derinliği listeye girer. Kod §6'yı izler; K6 testi T2 deliğini `DrillOp` olarak
  kurar (koordinatör kararı, 2026-10-18 11:38).
- Örnek çıktı: `/mnt/project-files/atolye/is-foyu-ornek/` (Ek A + ikinci bağlama).

## Açık sorular
_(yok)_
