# DURUM — SPEC 21 torna-gcode

Dal: `claude/project-thread-6zs2nh` · Oturum: bulut

## Sıradaki adım
PR #42'nin CI'ı yeşile dönünce kullanıcının birleştirme kararı (proje sohbeti). #27 / #33 birleşirse `main` dala alınacak (`cam/gcode/writer.py`).

## Test durumu
| Tarih | Geçen | Kalan | Not |
|---|---|---|---|
| 2026-10-18 | — | — | Sadece SPEC taslağı; kod ve test yok. |
| 2026-10-18 | 120 (SPEC 21) | 0 | `--uygulanmamis-hata` ile; testler kodu görmeden yazıldı, ilk çalıştırmada yeşil. |

## Son oturum
**2026-10-18**
- `specs/21-torna-gcode.md` taslağı yazıldı: Fanuc torna sistem A, çap programlama, `G96`/`G97`/`G50`, `G32`,
  zorunlu takım değiştirme noktası ve iş mili yönü, okuyucu, gidiş-dönüş.
- `cam/model.py` değişikliği gerekmiyor.
- SPEC kullanıcı onayı: 2026-10-18 09:45 UTC, proje sohbetindeki kart ("Onayla"): X çap, açık hareketler + `G32`, M3/M4 zorunlu, takım değiştirme noktası zorunlu.
- `cam/gcode/lathe.py` iskeleti (`NotImplementedError`) push edildi (`7762b30`).
- Testler ayrı oturumda (dal `claude/project-thread-bb9p8s`, commit `7f6af1c`) yazıldı, cherry-pick edildi; kod ayrı commit'te.
- `cam/gcode/writer.py`: `_yazilabilir` koruması kalıcı, mesajı `write_lathe`'i gösteriyor (tek satır + docstring).

## Açık sorular
_(yok)_
