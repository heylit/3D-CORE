# DURUM — SPEC 03b cep-kalan-malzeme

Dal: `claude/project-thread-aeemx5` · Oturum: bulut

## Sıradaki adım
Kod yazıldı; PR #49 CI yeşil olunca birleşir. Sıradaki: SPEC 03c (rampa / helis giriş).

## Test durumu
| Tarih | Geçen | Kalan | Not |
|---|---|---|---|
| 2026-10-18 | tests/cam 1495 (slow dahil) | 0 | `--uygulanmamis-hata` ile |

## Son oturum
**2026-10-18**
- SPEC 03b taslağı yazıldı (`specs/03b-cep-kalan-malzeme.md`).
- Ön deneme (depoya girmedi, mevcut `offset` ile): kesin denetim 60×40 dikdörtgende eşiği tam
  `r(1 + sin 45°)` buldu; L cepte (D = 6) `s = 0,6D`, `0,7D`, `D` seviyelerini yakaladı. Denetimsiz ağaçta örnekleme
  ≈ 27 mm² (`0,6D`), ≈ 1,5 mm² (`0,7D`), dikdörtgende `s = D` ≈ 17 mm² kalan buldu; adım küçültmeyle dört şekilde
  (dikdörtgen, L, adalı, içbükey) `s ∈ {0,5 … 1,0}D` için 0,25 mm ızgarada kalan 0.

## Test bağımsızlığı
- Testler ayrı oturumda yazıldı (commit 75e2090, düzeltme c1492d9; burada cherry-pick e708838, 7682c2b). Kod commit'i test dosyalarına dokunmaz.

## Notlar
- `covered`: σ ≤ r'de doğrudan True (Önerme 1). σ ≈ r'de Y'nin dış ofsetinde sıfır yarıçaplı yaylar oluşup halka kapanmıyordu (halter, içbükey çokgenler).
- Yaprak ek halka kuralı (`MIN_EXTRA` dahil) `cam/ops2d.py`'den `cam/rest.py`'ye taşındı, davranış aynı.

## Açık sorular
_(yok)_ — rampa / helis giriş ayrı SPEC 03c (koordinatör kararı).
