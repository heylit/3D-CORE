# DURUM — SPEC 20 torna-yol

Dal: `claude/spec-20-torna-yol-sj8reg` · Oturum: bulut

## Sıradaki adım
PR'ın CI'ı yeşile dönünce kullanıcı birleştirme kararı (proje sohbeti).

## Test durumu
| Tarih | Geçen | Kalan | Not |
|---|---|---|---|
| 2026-10-18 | — | — | Sadece SPEC taslağı; kod ve test yok. |
| 2026-10-18 | 220 (SPEC 20) | 0 | `--uygulanmamis-hata` ile; testler kodu görmeden yazıldı ve ilk çalıştırmada yeşil. |

## Son oturum
**2026-10-18**
- `specs/20-torna-yol.md` taslağı yazıldı (alın, boy, kaba `G71` tip I, ince profil, kanal, diş `G76` derinlikleri, burun yarıçapı telafisi).
- SPEC kullanıcı onayı: 2026-10-18 08:56 UTC, proje sohbetindeki kart ("Onayla").
- `cam/lathe.py`, `cam/lathe_ops.py` iskeletleri (`NotImplementedError`) push edildi.
- Testler ayrı oturumda (dal `claude/project-thread-eqye5s`, commit `48aa5f1`) yazıldı, cherry-pick edildi; kod ayrı commit'te.
- `cam/model.py` değişikliği gerekmedi: Ek 2'deki `LatheTool`, `CylinderStock`, `Plane.ZX`, `FeedMode.PER_REV`, `css` yeterli.

## Açık sorular
_(yok)_
