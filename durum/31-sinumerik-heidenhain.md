# DURUM — SPEC 31 sinumerik-heidenhain

Dal: `claude/project-thread-t2yott` · Oturum: bulut ("Postprosesörler ve tezgâh profilleri" thread'i)

## Sıradaki adım
İskelet push edildi (NotImplementedError): `cam/post/format_sinumerik.py` (`SINUMERIK`, `format_sinumerik`),
`cam/post/format_heidenhain.py` (`HEIDENHAIN`, `format_heidenhain(blocks, presets, dialect, program_name)`),
`cam/post/read_sinumerik.py`, `cam/post/read_heidenhain.py`; `dialect_for`, `post`, `read_program` dile göre dağıtır.
Testler ayrı thread'de yazılacak, sonra kod.
Örnek profiller (`ornek-sinumerik-dik.json`, `ornek-heidenhain-dik.json`) kod commit'inde gelir: SPEC 30 testi
`builtin_machines()`'in tam üç profil vermesini istiyor; test thread'i o listeyi beşe çıkarır. Önerilen uydurma değerler:
X ±400, Y ±250, Z [−500, 0], rpm 50–12000, feed_max 10000, tool_slots 30, tool_change_z 0, program_no 1–9999,
decimals 3, verified false; Heidenhain'de ek olarak presets {"G54": 1, "G55": 2}.

## Test durumu
| Tarih | Geçen | Kalan | Not |
|---|---|---|---|

## Son oturum
**2026-10-18**
- SPEC taslağı yazıldı (`specs/31-sinumerik-heidenhain.md`).

## Açık sorular
SPEC dosyasının "Açık sorular" / "Varsayımlar" bölümüne bakınız.
