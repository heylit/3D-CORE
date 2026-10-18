# DURUM — SPEC 08 Montaj kısıtları ve konum çözücü

Dal: `claude/project-thread-fe0oon` · PR #3 · Oturum: bulut

## Sıradaki adım
PR #3 incelemesi ve birleşmesi; birleşince `DURUM.md` SPEC tablosunda 08 satırı "tamamlandı" olur.

## Test durumu
| Tarih | Geçen | Kalan | Not |
|---|---|---|---|
| 2026-10-18 | 245 (SPEC 08) | 0 | `tests/assy/test_mates.py`, `test_solver.py`; tüm depo 333 geçti, 29 uygulanmamış (SPEC 01'e ait) |

## Son oturum
**2026-10-18**
- SPEC kullanıcı tarafından onaylandı (düzlem çakışmasında normaller zıt, eş eksende eksen yönü serbest).
- `dogrulayici` kodu görmeden 245 test yazdı (K1–K13); kod yokken hepsinin "uygulanmamış" düştüğü ayrı kopyada doğrulandı.
- `yazici` `assy/mates.py` (artıklar, analitik Jacobian) ve `assy/solver.py` (Gauss–Newton, en küçük normlu adım, geri izleme, SVD ile rotasyon temizliği, rank ile DOF) yazdı.
- Blok üstüne blok 3 iterasyonda kapalı forma iniyor; zincir C konumu ~1e-11 mm.

## Açık sorular
- Yanlış dala yakın başlangıçta (ör. normaller zıt değil ~10° yakın aynı yönde) çözücü `AssyError` veriyor; SPEC'e uygun. Yön bayrağı (`flip`) ileride arayüz PR'ı ile eklenebilir.
- Çelişki mesajındaki "en büyük artıklı kısıt" çelişen kısıtlardan herhangi biri olabilir (belirsiz, testler sırayı kontrol etmiyor).
- `dof()` sabit bileşen istemiyor, `solve()` istiyor.
