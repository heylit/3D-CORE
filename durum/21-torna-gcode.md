# DURUM — SPEC 21 torna-gcode

Dal: `claude/project-thread-6zs2nh` · Oturum: bulut

## Sıradaki adım
PR #88 (Ek E3) CI'ı yeşile dönünce birleştirilecek.

## Test durumu
| Tarih | Geçen | Kalan | Not |
|---|---|---|---|
| 2026-10-18 | — | — | Sadece SPEC taslağı; kod ve test yok. |
| 2026-10-18 | 120 (SPEC 21) | 0 | `--uygulanmamis-hata` ile; testler kodu görmeden yazıldı, ilk çalıştırmada yeşil. |
| 2026-10-18 | 167 (SPEC 21 + Ek E3) | 0 | Ek E3: 47 test (`e01bbb2`, ayrı oturum); SPEC 40 K6 gidiş-dönüşü de yeşil. |

## Son oturum
**2026-10-18**
- `specs/21-torna-gcode.md` taslağı yazıldı: Fanuc torna sistem A, çap programlama, `G96`/`G97`/`G50`, `G32`,
  zorunlu takım değiştirme noktası ve iş mili yönü, okuyucu, gidiş-dönüş.
- `cam/model.py` değişikliği gerekmiyor.
- SPEC kullanıcı onayı: 2026-10-18 09:45 UTC, proje sohbetindeki kart ("Onayla"): X çap, açık hareketler + `G32`, M3/M4 zorunlu, takım değiştirme noktası zorunlu.
- `cam/gcode/lathe.py` iskeleti (`NotImplementedError`) push edildi (`7762b30`).
- Testler ayrı oturumda (dal `claude/project-thread-bb9p8s`, commit `7f6af1c`) yazıldı, cherry-pick edildi; kod ayrı commit'te.
- `cam/gcode/writer.py`: `_yazilabilir` koruması kalıcı, mesajı `write_lathe`'i gösteriyor (tek satır + docstring).

**2026-10-18 (Ek E3)**
- PR #42 birleşti (`11c7414`).
- SPEC 40'ın E3 eki SPEC 21 metnine "Ek E3" bölümü olarak işlendi (kullanıcı yazılı onayı 11:13 UTC); altın örnek K12,
  kabul kriterleri K12–K15.
- `cam/gcode/lathe.py` iskeleti: `DRILL`/`CONE` `Tool` yazıcıda ve okuyucuda `NotImplementedError`; `read_lathe`
  `tools` tipi `LatheTool | Tool`. K1–K11 değişmeden yeşil.
- Testler ayrı oturumda (`e01bbb2`) yazıldı, cherry-pick edildi; kod ayrı commit'te (`c36e2ac`).
- SPEC 40 K6 testinin z toleransı 0,25·10⁻³ idi; 3 ondalıklı Z ile tutmuyordu (uç −28,0043 → 0,3·10⁻³ hata).
  SPEC 40 sahibi SPEC 21 toleranslarına (x 0,25·10⁻³, z 0,5·10⁻³) çekti (`f3e9c02`), #88'e cherry-pick edildi.

## Açık sorular
_(yok)_
