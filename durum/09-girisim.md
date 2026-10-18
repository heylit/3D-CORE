# DURUM — SPEC 09 Boolean API, montajda girişim ve boşluk kontrolü

Dal: `claude/project-thread-nkn98y` · Oturum: bulut

## Sıradaki adım
Testler ayrı oturumda yazılıyor; test commit'i cherry-pick edilince kod ayrı commit'te yazılacak.

## Test durumu
| Tarih | Geçen | Kalan | Not |
|---|---|---|---|
| 2026-10-18 | — | — | SPEC taslağı; test ve kod yok |

## Son oturum
**2026-10-18 — onay ve iskelet**
- SPEC metni ve `Part` arayüz eki kullanıcı tarafından onaylandı (proje sohbeti, 10:38 UTC, yazılı).
- `Part` arayüz eki (PR #53, `3fa6b5d`) dala merge edildi; `geometry/boolean.py` iskeleti oradan geldi.
- `assy/girisim.py` iskeleti (`NotImplementedError`) eklendi.

**2026-10-18**
- `specs/09-girisim.md` taslağı yazıldı (yol haritasındaki 09 satırı: boolean API + girişim + boşluk).
- Ön deneme (OCCT): yüz yüze bloklarda `V∩ = 0`, `d = 0` (temas girişimden ayrılıyor); içerdeki parçada
  `d` sınırlar arası (> 0), bu yüzden önce hacme bakılır; 45° küp sekizgeni rel 3e-16; pim–delik sıkı
  geçme rel 2e-15.
- build123d 0.13 `Sphere & Sphere` yanlış hacim veriyor (küçük kürenin tamamı); `BRepAlgoAPI_Common`
  doğrudan kullanılınca rel 2e-9. Boolean'lar doğrudan OCCT ile yazılacak.

## Açık sorular
_(yok)_
