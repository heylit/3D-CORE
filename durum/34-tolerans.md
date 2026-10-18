# DURUM — SPEC 34 Tolerans yığılımı

Dal: `claude/spec-34-tolerans-6t5zau` · Oturum: bulut

## Sıradaki adım
A1 (`Tolerance`, PR #85) kodu birleşince main'i al, pytest + kapı yeşilse PR #65'i birleştir.

## Test durumu
| Tarih | Geçen | Kalan | Not |
|---|---|---|---|
| 2026-10-18 | 12 (+61 A1 bekliyor) | 0 | `tests/assy/test_tolerans.py` (af5a7ab, bağımsız oturum); A1 gövdeleri geçici yamayla doldurulunca 73/73 geçti |

## Son oturum
**2026-10-18 — Kod**
- Test commit'i af5a7ab cherry-pick edildi; `assy/tolerans.py` ayrı commit'te yazıldı.
- 3B: `∂r/∂p` kısıt değeri değiştirilerek (mesafe ileri fark, kesin; açı merkezi fark) hesaplanıyor, böylece `flip` ve satır düzeni SPEC 08'deki gibi kalıyor.
- Ölçüyü etkilemeyen toleranslı kısıt (|a| ≤ 1e-12) `AssyError` (etkisiz halka kuralı, K1 ile tutarlı).

**2026-10-18 — Onay ve iskelet**
- SPEC 34 metni önerilerle onaylandı (kullanıcı, 11:13 toplu yazılı onay).
- `assy/tolerans.py` `NotImplementedError` iskeleti; `Tolerance` A1 gelene kadar yalnız tip ipucu olarak içe alınıyor.

**2026-10-18**
- SPEC 34 taslağı yazıldı (1B en kötü durum / RSS / Monte Carlo, 3B SPEC 08 Jacobian'ıyla doğrusal zincir).
- A1 için beklenen `Tolerance` arayüzü SPEC'te; koordinatöre iletildi.

## Açık sorular
_(yok; üç soru önerilen varsayılanlarla onaylandı)_
