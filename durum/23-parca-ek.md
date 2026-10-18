# DURUM — SPEC 23 parca-ek

Dal: `claude/spec-23-parca-ek-die5mp` · Oturum: bulut

## Sıradaki adım
Ayrı dogrulayici oturumu `tests/geometry/test_fillet.py` ve `tests/geometry/test_holes.py` dosyalarını yazar; arayüz PR #23 (`Hole`, `Part.holes`, lamba alanlarıyla) `main`'e girmeli.

## Test durumu
| Tarih | Geçen | Kalan | Not |
|---|---|---|---|
| 2026-10-18 | — | — | SPEC taslağı; test ve kod yok |

## Son oturum
**2026-10-18**
- SPEC 23 taslağı yazıldı. Tüm formüller OCCT ile ön denendi (build123d 0.13.0): fillet dikey / üst / tüm
  kenar, silindir ve delik ağzı Pappus, havşa, eğimli boydan boya ve kör delik; hepsi rel ≤ 2e-10.

- SPEC kullanıcı tarafından onaylandı (proje sohbeti kartı, 08:28 UTC, "Lamba da ekle"); `counterbore_hole`,
  ISO 4762 / DIN 974-1 lamba tablosu ve K5b eklendi. Lamba formülü OCCT ile ön denendi (rel ≤ 1.2e-14).
- Arayüz eki (`Hole`, `Part.holes`) "Dalga 2 arayüz ekleri" thread'inde PR #23 olarak açıldı; part.py sahibi o thread.

## Açık sorular
- PR #23'e `cbore_d`, `cbore_depth` alanları ve doğrulaması eklenmeli (arayüz thread'i).
- Lamba (counterbore) kullanıcı kararıyla eklendi (kart, 08:28 UTC: "Lamba da ekle"), SPEC bu ekle onaylı.
