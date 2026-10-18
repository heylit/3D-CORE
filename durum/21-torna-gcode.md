# DURUM — SPEC 21 torna-gcode

Dal: `claude/project-thread-6zs2nh` · Oturum: bulut

## Sıradaki adım
Testler ayrı oturumda yazılacak; test commit'i cherry-pick edilip kod ayrı commit'te yazılacak.

## Test durumu
| Tarih | Geçen | Kalan | Not |
|---|---|---|---|
| 2026-10-18 | — | — | Sadece SPEC taslağı; kod ve test yok. |

## Son oturum
**2026-10-18**
- `specs/21-torna-gcode.md` taslağı yazıldı: Fanuc torna sistem A, çap programlama, `G96`/`G97`/`G50`, `G32`,
  zorunlu takım değiştirme noktası ve iş mili yönü, okuyucu, gidiş-dönüş.
- `cam/model.py` değişikliği gerekmiyor.
- SPEC kullanıcı onayı: 2026-10-18 09:45 UTC, proje sohbetindeki kart ("Onayla"): X çap, açık hareketler + `G32`, M3/M4 zorunlu, takım değiştirme noktası zorunlu.
- `cam/gcode/lathe.py` iskeleti (`NotImplementedError`) push edildi.

## Açık sorular
_(yok)_
