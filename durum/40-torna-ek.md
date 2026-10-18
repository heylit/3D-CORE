# DURUM — SPEC 40 torna-ek

Dal: `claude/spec-40-torna-ek-iemrjz` · Oturum: bulut

## Sıradaki adım
Kullanıcı onayı; sonra `cam/torna_ek.py` `NotImplementedError` iskeleti (bağımlılık dallarının üstüne).

## Test durumu
| Tarih | Geçen | Kalan | Not |
|---|---|---|---|
| 2026-10-18 | — | — | Sadece SPEC taslağı; kod ve test yok. |

## Son oturum
**2026-10-18**
- `specs/40-torna-ek.md` taslağı: eksenel delme / punta, ters bağlama, profilli kanal (`Recess`), torna tezgâh profili.
- Başka sahiplere ek listesi E1–E4 SPEC'te; koordinatöre gönderildi.

## Açık sorular
1. Tornada matkap: `cam.model.Tool` (`DRILL`/`CONE`) olarak mı (öneri; `cam/model.py` değişmez, 21 ve 22'ye küçük ek), yoksa yeni `LatheToolKind.DRILL` mı?
2. Torna tezgâh profili (D) bu SPEC'te mi kalsın (öneri; 30 sahibi uygular), yoksa ayrı "SPEC 30 Ek A" mı?
3. Profilli kanal incesi: tek yanal paso (öneri) mi, yoksa iki yarım paso (her yan kendi köşesiyle) mi?
4. Ters bağlamada `z_ref` varsayılanı: stok kendine (`zmin + zmax`, öneri) mi?
