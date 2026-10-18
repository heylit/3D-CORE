# DURUM — SPEC 31 sinumerik-heidenhain

Dal: `claude/project-thread-t2yott` · PR #102 · Oturum: bulut ("Postprosesörler ve tezgâh profilleri" thread'i)
Testler: ayrı oturum, commit b3e3b2d + aebefbc (cherry-pick c1672ff + f4afb19).

## Sıradaki adım
Kod yazıldı. Tüm testler yeşilse push; CI (pytest + kapı) yeşilse birleştir.

## Test durumu
| Tarih | Geçen | Kalan | Not |
|---|---|---|---|
| 2026-10-18 | SPEC 31: 82 / 82 | 0 | `test_post_sinumerik.py`, `test_post_heidenhain.py`, `test_post_machine.py` |

## Son oturum
**2026-10-18**
- `format_sinumerik`: ISO biçimleyicisinin alt sınıfı; noktasız sayı, `; yorum` (başlıktan önce), `T<n> M6` + `D1`.
- `format_heidenhain`: blok numaralı Klartext; `M3` ilk harekette, `M5` / `M30` son hareket bloğuna eklenir;
  aynı takımda devir değişimi `TOOL CALL Z S<n>`.
- Okuyucular: Sinumerik satırı beyaz listeden geçip ISO okuyucusunda (`G71` → `G21`) yürür; Heidenhain
  okuyucusu ISO okuyucusunun yol / yay kurallarını kullanır.
- Örnek profiller: `ornek-sinumerik-dik.json` (`tool_change_z: null`), `ornek-heidenhain-dik.json`
  (`tool_change_z: 0`, `presets {"G54": 1, "G55": 2}`); uydurma, `verified: false`.

## Kararlar ve varsayımlar
- **D numarası**: her takım değişiminden sonra `D1` (Siemens varsayılanı: D takımın kesici ağzıdır). "Flat D
  number" (MD18102) açık tezgâhlarda D = T gerekir; şimdilik desteklenmiyor (koordinatör kararı 13:47).
- **Sinumerik `tool_change_z`**: SPEC 31 makine koordinatı satırını (SUPA / G53) tanımlamıyor; verilirse CamError.
- **Heidenhain helisi** (`CP IPA IZ`): bitiş yazılmaz, tezgâhın gerçek başlangıcının CC çevresinde dönmesidir.
  - CC, başlangıç ile model bitişinin (`Arc.end`) orta dikmesine yuvarlanmış merkezin izdüşümüdür; 4 ondalıkla
    yazılır, ±2 ızgara noktasından okunan bitişi model bitişine en yakın yapan seçilir. 30 rastgele tohumda
    uç ≤ 0.49998·10⁻³, merkez ≤ 2.1·10⁻³ mm. TNC'nin 0.1 µm giriş çözünürlüğü doğrulanmalı.
  - CP'den sonra tezgâh konumu yazılan konumdan biraz farklıdır. Bu yüzden sonraki `L` üç ekseni de yazar,
    sonraki tam daire `CP IPA±360 IZ+0` olur (aynı noktalı `C`, küçük yay sanılabilir).
  - 3 ondalıklı CC ile eksene paralel kirişte sapma 10⁻³ mm'ye çıkıyordu (Ek B testindeki helis zinciri).
- `Arc.end` (yuvarlanmamış bitiş) SPEC 30 Ek B; onay 13:58 (2 dakika kuralı). Testleri 8ea8ec3 (cherry-pick fb4a17b).

## Açık sorular
Yok.
