# DURUM — SPEC 55 Windows tek tık kurulum

Dal: `claude/project-thread-ayiorn` · Oturum: bulut

## Sıradaki adım
İskelet push edildi; ayrı test oturumu `tests/kurulum/` testlerini yazacak, sonra kod ayrı commit'te.

## Test durumu
| Tarih | Geçen | Kalan | Not |
|---|---|---|---|
| 2026-10-18 | — | — | İskelet: `kurulum/kontrol.py` (NotImplementedError); `.bat` dosyaları henüz yok. |

## Son oturum
**2026-10-18**
- `specs/55-windows-kurulum.md` onaylı taslaktan yazıldı; açık sorular "Kararlar" bölümüne işlendi.
- Karar 3: `* text=auto` yüzünden CRLF ancak `.gitattributes`'a `*.bat text eol=crlf` ile korunur; satır bu PR'da.
- Karar 4: SPEC 24'te sağlık ucu yok; "port Tezgah'ta mı" `/api/openapi.json` `info.title == "Tezgah"` ile.

## Açık sorular
- K12 elle kabul (kullanıcının Windows makinesi) kod birleştikten sonra yapılacak.
