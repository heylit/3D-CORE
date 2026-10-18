# DURUM — SPEC B2 Malzeme veri modeli arayüzü

Dal: `claude/spec-34-tolerans-6t5zau` (oturumun verdiği dal, SPEC 34 birleştikten sonra main'den yeniden kuruldu) · Oturum: bulut

## Sıradaki adım
Bağımsız test thread'inin test commit'ini cherry-pick et, `malzeme/model.py` gövdelerini ayrı commit'te yaz.

## Test durumu
| Tarih | Geçen | Kalan | Not |
|---|---|---|---|

## Son oturum
**2026-10-18**
- Taslak onaylandı (14:52, 2 dakika kuralı); `specs/B2-malzeme-arayuz.md` olarak eklendi, "Kararlar" bölümüyle.
- İskelet: `malzeme/model.py` (`NotImplementedError`), `assy/model.py` `Component.material` (tam; eski testler değişmeden geçer).
- `pyproject.toml` `packages.find` listesine `malzeme*` eklenmesi ayrı küçük PR ("Durum tablosu ve kurulum belgeleri" sahibi).

## Açık sorular
_(yok)_
