# DURUM — SPEC 17 kroki

Dal: `claude/project-thread-uo3o39` · PR #39 · Oturum: bulut

## Sıradaki adım
Kod tamam; PR #39'da pytest + kapi yeşil olunca birleştirilir. Sonra SPEC 26 (Tezgah modelleme, SPEC 24 main'de olunca).

## Test durumu
| Tarih | Geçen | Kalan | Not |
|---|---|---|---|
| 2026-10-18 | 210 (tests/sketch) | 0 | Tüm takım: 2777 geçti, 14 atlandı |

## Son oturum
**2026-10-18**
- SPEC taslağı yazıldı, onaylandı (10:38); Ek A (ortak uçta teğetlik, kullanıcı kararı 11:00).
- Bağımsız testler cherry-pick edildi (21744eb); kod ayrı commit'te: `sketch/constraints.py`, `solver.py`, `regions.py`.
- Yorum: `dof(sketch)` sayımı "çözülmüş konumda" yapar (SPEC "Serbestlik derecesi"); girdiyi değiştirmeden
  kopyayı çözer, çelişkide mevcut konumda sayar. Sağlanmamış dörtgende PARALLEL rank'ı yapay artırdığı için.

## Açık sorular
_(yok)_
