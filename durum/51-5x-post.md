# DURUM — SPEC 51 5x-post

Dal: `claude/project-thread-t2yott` · Oturum: bulut ("Postprosesörler ve tezgâh profilleri" thread'i)

## Sıradaki adım
İskelet push edildi (`cam/post/multiaxis.py`: `post5`, `swivel_angles`; `cam/post/read_multiaxis.py`:
`read_program5`; NotImplementedError). Testler ayrı test thread'inde (`tests/cam/test_post5_*.py`,
`tests/reference/test_post5_linuxcnc.py`); test commit'i cherry-pick edilince kod ayrı commit'te.

## Test durumu
| Tarih | Geçen | Kalan | Not |
|---|---|---|---|
| 2026-10-18 | 0 | K1–K9 | iskelet |

## Kararlar ve varsayımlar
- SPEC metni taslaktan alındı; açık sorular "Kararlar" bölümüne öneriyle işlendi (CYCLE800 güncel 840D sl,
  Heidenhain varsayılanı `FUNCTION TCPM`, LinuxCNC yalnız TCP kapalı, NTX / NLX MAPPS).
- Örnek 5 eksen profilleri (`ornek-sinumerik-5x.json`, `ornek-heidenhain-5x.json`, `ornek-fanuc-5x.json`) kod commit'iyle
  gelir: `builtin_machines()` listesine girdikleri için `test_post_machine.py` örnek listesi ve H15 filtresi (5 eksen
  profilleri 3 eksen uçtan uca testinde) test thread'inde güncellenmeli.

## Açık sorular
Yok.
