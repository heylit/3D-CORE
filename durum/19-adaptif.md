# DURUM — SPEC 19 Adaptif ve trokoidal kaba

Dal: `claude/spec-19-adaptif-1kvh62` · Oturum: bulut

## Sıradaki adım
Kod yazıldı, SPEC 19 testleri yeşil. GitHub Actions çalıştırıcıları düzelince PR #76'yı (pytest + kapi yeşilse) birleştir.

## Test durumu
| Tarih | Geçen | Kalan | Not |
|---|---|---|---|
| 2026-10-18 | — | — | Yalnız SPEC metni, kod yok |
| 2026-10-18 | 258 | 0 | test_adaptive_grid + test_trochoid 199, test_adaptive_pocket 59 (yavaş, ~9,5 dk) |

## Son oturum
**2026-10-18**
- `specs/19-adaptif.md` taslağı yazıldı. Temas açısı formülleri (düz duvar, içbükey daire, trokoid ön noktası)
  ve ızgara hata sınırı `tol(φ)` sayısal olarak denetlendi.
- SPEC onaylandı (11:13); `cam/adaptive.py` NotImplementedError iskeleti.
- Ek A (trokoid döngüsü boyunca en büyük φ, p*) otomatik kabul kuralıyla onaylandı; tablo değerleri doğrulandı.
- Bağımsız testler (970a210, ayrı oturum) cherry-pick edildi; kod ayrı commit'te.
- Adaptif cep: ızgara üzerinde açgözlü yön seçimi, hava adımları, yeniden başlatma taraması, köşe ziyaretleri ve
  temizleme konturu. `trochoid_loop_pitch` ikiye bölmede yalnız φ_t'yi aşan α'ları tarar (φ(α) p'de artan).

## Açık sorular
_(yok)_ — 2026-10-18 11:13 kullanıcı metni önerilerle onayladı (dar bölge raporlanır, yerel helis, ızgara, trokoidal kanal dahil).
