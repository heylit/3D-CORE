# DURUM — SPEC 40 torna-ek

Dal: `claude/spec-40-torna-ek-iemrjz` · Oturum: bulut

## Sıradaki adım
CI (pytest + kapı) yeşilse PR #75'i birleştirmek; sonra E3/E4 ve SPEC 22 birleşince atlanan K6, K9, K10'u çalıştırmak.

## Test durumu
| Tarih | Geçen | Kalan | Not |
|---|---|---|---|
| 2026-10-18 | — | — | Sadece SPEC taslağı; kod ve test yok. |
| 2026-10-18 | 160 (SPEC 40) | 0 | 12 atlanan: K6 (E3/E4 bekliyor), K9–K10 (SPEC 22 `RadialMap`/`simulate_lathe` henüz kodlanmadı). |

## Son oturum
**2026-10-18**
- `specs/40-torna-ek.md` taslağı: eksenel delme / punta, ters bağlama, profilli kanal (`Recess`), torna tezgâh profili.
- Başka sahiplere ek listesi E1–E4 SPEC'te; koordinatöre gönderildi.
- SPEC onayı: 2026-10-18 11:13 UTC, proje sohbetinde yazılı toplu onay (önerilerle).
- `cam/torna_ek.py` iskeleti (`NotImplementedError`) `main` üstüne; bağımlılıklar (SPEC 22 `RadialMap`, #60 `CONE`) yalnız tip ipucunda / gövdede.

- Testler ayrı oturumda (dal `claude/project-thread-mq266y`, commit `fa7a73b`) yazıldı, cherry-pick edildi (`448217d`); kod ayrı commit'te, testler ilk çalıştırmada yeşil.
- T4 notu: "`ccw` yay → `cw`" yalnız kapalı profilde geçerli (yeniden yönlendirilmez). Açık profil ters çevrilip ön→arka sıralanınca yansıma ve ters gezi birbirini götürür, yay yine `ccw`'dir; testler açık profilde yalnız noktaları ve geometriyi denetler.
- `flip_rmap` K9–K10'la henüz sınanmadı (SPEC 22 kodu yok); sütun eşlemesi `j = f − i`, `f = (z_ref − z0' − z0 − dz)/dz`.

## Açık sorular
Kararlar (önerilerle aynı; kullanıcı 11:13'te onayladı):
1. Tornada matkap `cam.model.Tool` (`DRILL`/`CONE`, `x = 0`).
2. Torna tezgâh profili (D) SPEC 40 metninde; kodu 30 sahibi yazar.
3. Profilli kanal incesi tek yanal paso.
4. Ters bağlamada `z_ref` varsayılanı stok kendine (`zmin + zmax`).
E1–E4 sahiplerine iletildi.
