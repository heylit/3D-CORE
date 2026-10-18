# DURUM — SPEC 01 1D çubuk elemanı ve doğrusal statik çözücü

Dal: `claude/project-thread-gmmhu4` · Oturum: bulut thread "FEM çubuk (SPEC 01)"

## Sıradaki adım
PR incelemesi ve birleştirme. Sonra SPEC 02 (kafes) bu iskeleti kullanır.

## Test durumu
| Tarih | Geçen | Kalan | Not |
|---|---|---|---|
| 2026-10-18 | 117 | 0 | SPEC 01 uygulandı: tüm testler yeşil (bulut, .venv). |
| 2026-10-18 | 12 | 29 | Veri modeli testleri geçiyor, SPEC 01 testleri bilerek kırmızı (TDD). Yerelde Python 3.14.7 ile doğrulandı. |

## Son oturum
**2026-10-18 — SPEC 01 uygulandı**
- `bar1d` (length, ke, dofs, axial_force), `assemble_K` (COO -> CSR toplama), `assemble_F`, `solve`, `post` yazıldı.
- Mekanizma kontrolü: K_ff boyutu <= 2000 ise `cond > 1e12`, ayrıca `MatrixRankWarning`/`RuntimeError`/sonlu olmayan sonuç -> `ModelError`.
- Aynı DOF'a çelişen iki BC -> `ModelError`.
- Not: `core/model.py` `ruff format --check`'ten geçmiyor (önceden var, ortak dosya; ayrı PR).

**2026-10-18 — İskelet kurulumu**
- Proje yapısı, `core/model.py` veri modeli, SPEC 01 ve testleri (41 test) hazırlandı.
- Testler bağımsız bir örnek çözümle doğrulandı: 41/41 geçti; bilerek eklenen 3 hatayı yakaladı.
- Yerel CI kuruldu: pre-commit, pre-push hook'ları ve `ci.ps1`.

## Açık sorular
_(yok)_
