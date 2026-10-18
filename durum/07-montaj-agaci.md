# DURUM — SPEC 07 Montaj ağacı, BOM, montaj STEP'i

Dal: `claude/spec-07-montaj-agaci-ejmdg5` · Oturum: bulut

## Sıradaki adım
PR #20 CI yeşil olunca birleştirme onayı (proje sohbeti).

## Test durumu
| Tarih | Geçen | Kalan | Not |
|---|---|---|---|
| 2026-10-18 | — | — | SPEC taslağı; test ve kod yok |
| 2026-10-18 | 88 (SPEC 07: ağaç 45, BOM 30, STEP 13) | 0 | main (Node, PR #26) birleştirildikten sonra tüm depo 1448 geçti, 0 uygulanmamış |

## Son oturum
**2026-10-18 — kod**
- Testler ayrı oturumda yazıldı (`47284c9`, cherry-pick `d4a1361`); kod commit'i testlere dokunmadı.
- `assy/tree.py`, `assy/bom.py`, `fileio/step_montaj.py` uygulandı. STEP okumada aynı adlı iki farklı parça ürünü `AssyError` (aynı kimliğe sessizce iki şekil düşmesin).

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
