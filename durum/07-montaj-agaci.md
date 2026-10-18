# DURUM — SPEC 07 Montaj ağacı, BOM, montaj STEP'i

Dal: `claude/spec-07-montaj-agaci-ejmdg5` · Oturum: bulut

## Sıradaki adım
Testler "Montaj ağacı testleri (SPEC 07)" thread'inden, `Node` "Dalga 2 arayüz ekleri" thread'inin PR'ından gelecek; ikisi gelince kod ayrı commit'te.

## Test durumu
| Tarih | Geçen | Kalan | Not |
|---|---|---|---|
| 2026-10-18 | — | — | SPEC taslağı; test ve kod yok |

## Son oturum
**2026-10-18 — onay ve iskelet**
- SPEC metni kullanıcı tarafından onaylandı (proje sohbeti kartı, 08:29 UTC: Node arayüz PR'ı, ardından testler ve kod).
- `assy/tree.py`, `assy/bom.py`, `fileio/step_montaj.py` iskeletleri (`NotImplementedError`) eklendi.

**2026-10-18**
- `specs/07-montaj-agaci.md` taslağı yazıldı.
- Ön deneme (OCCT XCAF, `STEPCAFControl_Writer/Reader`): ürün adı = tanım, oluşum adı = düğüm adı ve
  paylaşımlı tanımlar (aynı parça tek `PRODUCT`) gidiş-dönüşte korunuyor; konum 13 anlamlı basamakla yazılıyor.
- build123d'nin `export_step` / `import_step` montajı yeterli değil: ürün adını etiketten alıyor, aynı
  şekli paylaşan ikinci oluşumun adını `=>[0:1:1:3]` yapıyor. Bu yüzden XCAF doğrudan kullanılacak.

## Açık sorular
_(yok; Node assy/model.py'de, STEP kodu fileio/step_montaj.py'de; kullanıcı onayı 08:29 UTC)_
