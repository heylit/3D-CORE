# DURUM — SPEC 21 torna-gcode

Dal: `claude/project-thread-6zs2nh` · Oturum: bulut

## Sıradaki adım
SPEC taslağı kullanıcı onayında (proje sohbeti). Onaydan sonra `cam/gcode/lathe.py` iskeleti (`NotImplementedError`).

## Test durumu
| Tarih | Geçen | Kalan | Not |
|---|---|---|---|
| 2026-10-18 | — | — | Sadece SPEC taslağı; kod ve test yok. |

## Son oturum
**2026-10-18**
- `specs/21-torna-gcode.md` taslağı yazıldı: Fanuc torna sistem A, çap programlama, `G96`/`G97`/`G50`, `G32`,
  zorunlu takım değiştirme noktası ve iş mili yönü, okuyucu, gidiş-dönüş.
- `cam/model.py` değişikliği gerekmiyor.

## Açık sorular
- Kullanıcı kararı bekleniyor: X çap mı, çevrimler, iş mili yönü, takım değiştirme noktası (SPEC "Teori").
