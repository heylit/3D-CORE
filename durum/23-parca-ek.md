# DURUM — SPEC 23 parca-ek

Dal: `claude/spec-23-parca-ek-die5mp` · Oturum: bulut

## Sıradaki adım
SPEC metninin kullanıcı onayı (proje sohbeti); onaydan önce `geometry/part.py` arayüz PR'ı (`Hole`, `Part.holes`).

## Test durumu
| Tarih | Geçen | Kalan | Not |
|---|---|---|---|
| 2026-10-18 | — | — | SPEC taslağı; test ve kod yok |

## Son oturum
**2026-10-18**
- SPEC 23 taslağı yazıldı. Tüm formüller OCCT ile ön denendi (build123d 0.13.0): fillet dikey / üst / tüm
  kenar, silindir ve delik ağzı Pappus, havşa, eğimli boydan boya ve kör delik; hepsi rel ≤ 2e-10.

## Açık sorular
- Arayüz değişikliği: `geometry/part.py`'ye `Hole` ve `Part.holes` (ayrı PR, koordinatöre bildirildi).
- Düz havşa (counterbore) kapsama girsin mi? Taslakta kapsam dışı.
