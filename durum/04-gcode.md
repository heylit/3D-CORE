# DURUM — SPEC 04 G-code çıkışı ve okuyucu

Dal: `claude/project-thread-5ai6c8` · Oturum: bulut

## Sıradaki adım
Kullanıcı `specs/04-gcode.md`'yi onaylayınca: `dogrulayici` ile `tests/cam/test_gcode_*.py`, sonra `yazici` ile `cam/gcode/`.

## Test durumu
| Tarih | Geçen | Kalan | Not |
|---|---|---|---|
| 2026-10-18 | — | — | Sadece SPEC taslağı; kod ve test yok. |

## Son oturum
**2026-10-18 — SPEC taslağı**
- `specs/04-gcode.md` yazıldı: GRBL + Fanuc son işlemci, okuyucu, G81/G83, ortak modal durum makinesi.
- Depo ile uyum: kod `cam/gcode/` altında (önerilen `post/` yerine); `cam/model.py`'de çevrim tipi olmadığı için `DrillOp` bu SPEC'in kendi sınıfı.
- "Birebir aynı" kriteri yazılan basamak sayısına bağlı toleransla tanımlandı (3 basamak → 5e-4 mm).

## Açık sorular
- SPEC metni onayı (BASLANGIC.md bölüm 8).
- Okuyucunun tolerans içindeki yayın merkezini orta dikmeye düzeltmesi uygun mu (varsayılan: evet)?
- GRBL'de takım değişimi `T<n>` + `M0` olarak yazılıyor (GRBL 1.1 M6 desteklemiyor varsayımı).
