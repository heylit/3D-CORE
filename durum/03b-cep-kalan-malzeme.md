# DURUM — SPEC 03b cep-kalan-malzeme

Dal: `claude/project-thread-aeemx5` · Oturum: bulut

## Sıradaki adım
SPEC metni kullanıcı onayı bekliyor. Onaydan sonra (ve PR #33 `main`'e birleşince) `NotImplementedError` iskeleti,
ardından ayrı test oturumu, sonra kod.

## Test durumu
| Tarih | Geçen | Kalan | Not |
|---|---|---|---|

## Son oturum
**2026-10-18**
- SPEC 03b taslağı yazıldı (`specs/03b-cep-kalan-malzeme.md`).
- Ön deneme (depoya girmedi, mevcut `offset` ile): kesin denetim 60×40 dikdörtgende eşiği tam
  `r(1 + sin 45°)` buldu; L cepte (D = 6) `s = 0,6D`, `0,7D`, `D` seviyelerini yakaladı. Denetimsiz ağaçta örnekleme
  ≈ 27 mm² (`0,6D`), ≈ 1,5 mm² (`0,7D`), dikdörtgende `s = D` ≈ 17 mm² kalan buldu; adım küçültmeyle dört şekilde
  (dikdörtgen, L, adalı, içbükey) `s ∈ {0,5 … 1,0}D` için 0,25 mm ızgarada kalan 0.

## Açık sorular
- Rampa / helis giriş SPEC 03'te "03b" diye anılıyordu; bu SPEC'ten ayrı, önerilen ad 03c.
