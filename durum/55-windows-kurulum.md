# DURUM — SPEC 55 Windows tek tık kurulum

Dal: `claude/project-thread-ayiorn` · Oturum: bulut

## Sıradaki adım
Kod yazıldı (testler 5453718, ayrı oturum). PR #124 yeşilse birleştirilir; sonra K12 elle kabul.

## Test durumu
| Tarih | Geçen | Kalan | Not |
|---|---|---|---|
| 2026-10-18 | — | — | İskelet: `kurulum/kontrol.py` (NotImplementedError); `.bat` dosyaları henüz yok. |
| 2026-10-18 | 52 | 0 | `tests/kurulum`: kontrol.py + 4 `.bat` (CRLF) + BENIOKU.md. |

## Son oturum
**2026-10-18**
- `specs/55-windows-kurulum.md` onaylı taslaktan yazıldı; açık sorular "Kararlar" bölümüne işlendi.
- Karar 3: `* text=auto` yüzünden CRLF ancak `.gitattributes`'a `*.bat text eol=crlf` ile korunur; satır bu PR'da.
- Kod: `kurulum/kontrol.py`, `kur.bat`, `baslat.bat`, `guncelle.bat`, `kaldir.bat`, `BENIOKU.md`; README ve BASLANGIC kurulum satırları.
- Karar 4: SPEC 24'te sağlık ucu yok; "port Tezgah'ta mı" `/api/openapi.json` `info.title == "Tezgah"` ile.

## Açık sorular
- K12 elle kabul (kullanıcının Windows makinesi) kod birleştikten sonra yapılacak.
