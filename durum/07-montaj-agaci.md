# DURUM — SPEC 07 Montaj ağacı, BOM, montaj STEP'i

Dal: `claude/spec-07-montaj-agaci-ejmdg5` · Oturum: bulut

## Sıradaki adım
SPEC metninin kullanıcı onayı; onaydan sonra `assy/model.py`'ye `Node` ekleyen ayrı arayüz PR'ı, sonra testler (ayrı oturum) ve kod.

## Test durumu
| Tarih | Geçen | Kalan | Not |
|---|---|---|---|
| 2026-10-18 | — | — | SPEC taslağı; test ve kod yok |

## Son oturum
**2026-10-18**
- `specs/07-montaj-agaci.md` taslağı yazıldı.
- Ön deneme (OCCT XCAF, `STEPCAFControl_Writer/Reader`): ürün adı = tanım, oluşum adı = düğüm adı ve
  paylaşımlı tanımlar (aynı parça tek `PRODUCT`) gidiş-dönüşte korunuyor; konum 13 anlamlı basamakla yazılıyor.
- build123d'nin `export_step` / `import_step` montajı yeterli değil: ürün adını etiketten alıyor, aynı
  şekli paylaşan ikinci oluşumun adını `=>[0:1:1:3]` yapıyor. Bu yüzden XCAF doğrudan kullanılacak.

## Açık sorular
- Ağaç düğümü (`Node`) `assy/model.py`'ye girmeli mi (önerilen, ayrı arayüz PR'ı), yoksa `assy/tree.py` içinde mi kalmalı?
- OCCT'li montaj STEP kodu `fileio/step_montaj.py`'de (önerilen) mi, `assy/` içinde mi?
