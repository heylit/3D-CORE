# DURUM — SPEC 40 torna-ek

Dal: `claude/spec-40-torna-ek-iemrjz` · Oturum: bulut

## Sıradaki adım
Ayrı test thread'inin test commit'ini cherry-pick etmek, sonra kodu ayrı commit'te yazmak.

## Test durumu
| Tarih | Geçen | Kalan | Not |
|---|---|---|---|
| 2026-10-18 | — | — | Sadece SPEC taslağı; kod ve test yok. |

## Son oturum
**2026-10-18**
- `specs/40-torna-ek.md` taslağı: eksenel delme / punta, ters bağlama, profilli kanal (`Recess`), torna tezgâh profili.
- Başka sahiplere ek listesi E1–E4 SPEC'te; koordinatöre gönderildi.
- SPEC onayı: 2026-10-18 11:13 UTC, proje sohbetinde yazılı toplu onay (önerilerle).
- `cam/torna_ek.py` iskeleti (`NotImplementedError`) `main` üstüne; bağımlılıklar (SPEC 22 `RadialMap`, #60 `CONE`) yalnız tip ipucunda / gövdede.

## Açık sorular
Kararlar (önerilerle aynı; kullanıcı 11:13'te onayladı):
1. Tornada matkap `cam.model.Tool` (`DRILL`/`CONE`, `x = 0`).
2. Torna tezgâh profili (D) SPEC 40 metninde; kodu 30 sahibi yazar.
3. Profilli kanal incesi tek yanal paso.
4. Ters bağlamada `z_ref` varsayılanı stok kendine (`zmin + zmax`).
E1–E4 sahiplerine iletildi.
