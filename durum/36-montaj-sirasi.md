# DURUM — SPEC 36 Montaj sırası ve demontaj yolu

Dal: `claude/spec-36-montaj-sirasi-3h5rr8` · Oturum: bulut

## Sıradaki adım
PR #68: CI yeşilse birleştir.

## Test durumu
| Tarih | Geçen | Kalan | Not |
|---|---|---|---|
| 2026-10-18 | — | — | SPEC taslağı; test ve kod yok |
| 2026-10-18 | 119 (SPEC 36, K7 OCCT dahil) | 0 | kod commit'i sonrası |

## Son oturum
**2026-10-18 — kod**
- Testler ayrı oturumda yazıldı (`06107a6`, cherry-pick `b91d73d`); kod commit'i testlere dokunmadı.
- `assy/sira.py` uygulandı. Test yazarının yorumu (koordinatör kabul etti): `scope` verilince kapsam dışındaki parçalar engel sayılmaz.

**2026-10-18 — onay ve iskelet**
- SPEC metni önerilen varsayılanlarla onaylandı (kullanıcının proje sohbetindeki Dalga 5 toplu yazılı onayı, 11:13 UTC).
- `assy/sira.py` iskeleti (`NotImplementedError`) eklendi; SPEC 09 `main`'de.

**2026-10-18**
- `specs/36-montaj-sirasi.md` taslağı yazıldı (yol haritası Dalga 5, hat H11).
- Ek A sahnesinin beklenen sıraları, yönleri ve yol boyları depo dışı küçük bir prototiple (kutu kesişimi)
  doğrulandı.

## Açık sorular
_(yok; altı soru önerilen varsayılanlarla onaylandı)_
