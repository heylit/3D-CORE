# DURUM — SPEC 08 Montaj kısıtları ve konum çözücü

Dal: `claude/project-thread-fe0oon` · PR #3 · Oturum: bulut

## Sıradaki adım
PR #3 incelemesi ve birleşmesi; birleşince `DURUM.md` SPEC tablosunda 08 satırı "tamamlandı" olur.

## Test durumu
| Tarih | Geçen | Kalan | Not |
|---|---|---|---|
| 2026-10-18 | 245 (SPEC 08) | 0 | `tests/assy/test_mates.py`, `test_solver.py`; main (SPEC 01) birleştirildikten sonra tüm depo 362 geçti, 0 uygulanmamış |

## Son oturum
**2026-10-18 — Ölçekli artıklar (inceleme O1)**
- Yön satırları (n_a + n_b, d_a × d_b, d_a·d_b − cos θ) karakteristik uzunluk L ile çarpılıyor
  (L = referans noktalarının başlangıç dünya çapı, en az 1 mm). Adım ve durma ölçütü artık mm cinsinden:
  önceden 1000 mm'lik parçada 1e-4 rad yön hatası tol = 1e-3 ile kabul ediliyordu (uçta 0,1 mm kayma).
- `assy.mates.angular_rows()`: satırın yön mü uzunluk mu olduğunu türevlerden çıkarır.
- `SolveResult.residual` artık ölçekli max|r| (mm).
- Yeni testler: `tests/assy/test_olcekli_artik.py`.
- Açık: tam yanlış dalda (n_a = n_b) başlangıç SPEC K10 gereği `AssyError`; bunu değiştirmek SPEC + test
  değişikliği ister, kullanıcı kararı bekleniyor.

**2026-10-18**
- SPEC kullanıcı tarafından onaylandı (düzlem çakışmasında normaller zıt, eş eksende eksen yönü serbest).
- `dogrulayici` kodu görmeden 245 test yazdı (K1–K13); kod yokken hepsinin "uygulanmamış" düştüğü ayrı kopyada doğrulandı.
- `yazici` `assy/mates.py` (artıklar, analitik Jacobian) ve `assy/solver.py` (Gauss–Newton, en küçük normlu adım, geri izleme, SVD ile rotasyon temizliği, rank ile DOF) yazdı.
- Blok üstüne blok 3 iterasyonda kapalı forma iniyor; zincir C konumu ~1e-11 mm.

## Açık sorular
- Yanlış dala yakın başlangıçta (ör. normaller zıt değil ~10° yakın aynı yönde) çözücü `AssyError` veriyor; SPEC'e uygun. Yön bayrağı (`flip`) ileride arayüz PR'ı ile eklenebilir.
- Çelişki mesajındaki "en büyük artıklı kısıt" çelişen kısıtlardan herhangi biri olabilir (belirsiz, testler sırayı kontrol etmiyor).
- `dof()` sabit bileşen istemiyor, `solve()` istiyor.
