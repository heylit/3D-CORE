# DURUM — SPEC B2 Malzeme veri modeli arayüzü

Dal: `claude/spec-34-tolerans-6t5zau` (oturumun verdiği dal, SPEC 34 birleştikten sonra main'den yeniden kuruldu) · Oturum: bulut

## Sıradaki adım
CI yeşilse #121'i birleştir.

## Test durumu
| Tarih | Geçen | Kalan | Not |
|---|---|---|---|
| 2026-10-18 | 1072 (tests/malzeme + tests/assy) | 0 | test commit'i 5198454 (cherry-pick 11be1d8), `--uygulanmamis-hata` ile de yeşil |

## Son oturum
**2026-10-18**
- Taslak onaylandı (14:52, 2 dakika kuralı); `specs/B2-malzeme-arayuz.md` olarak eklendi, "Kararlar" bölümüyle.
- İskelet: `malzeme/model.py` (`NotImplementedError`), `assy/model.py` `Component.material` (tam; eski testler değişmeden geçer).
- Test commit'i (5198454, oturum session_01VBgPDCoxBjXeNHzZdeBcji) cherry-pick edildi; kod ayrı commit'te yazıldı, testlere dokunulmadı.
- `pyproject.toml` `packages.find` listesine `malzeme*` eklenmesi ayrı küçük PR ("Durum tablosu ve kurulum belgeleri" sahibi).

## Açık sorular
_(yok)_
