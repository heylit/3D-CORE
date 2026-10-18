# DURUM — SPEC 34 Tolerans yığılımı

Dal: `claude/spec-34-tolerans-6t5zau` · Oturum: bulut

## Sıradaki adım
SPEC metni kullanıcı onayında; onaydan sonra `NotImplementedError` iskeleti (A1 `Tolerance` arayüzü dalının üstüne).

## Test durumu
| Tarih | Geçen | Kalan | Not |
|---|---|---|---|

## Son oturum
**2026-10-18**
- SPEC 34 taslağı yazıldı (1B en kötü durum / RSS / Monte Carlo, 3B SPEC 08 Jacobian'ıyla doğrusal zincir).
- A1 için beklenen `Tolerance` arayüzü SPEC'te; koordinatöre iletildi.

## Açık sorular
- Monte Carlo'da NORMAL örnekler kesilmesin mi? (öneri: kesilmez)
- 3B doğrusal olmayan Monte Carlo bu SPEC'te mi? (öneri: hayır, kapsam dışı)
- Parça içi ölçü toleransı (referans origin'ine tolerans) bu SPEC'te mi? (öneri: hayır; DISTANCE kısıtıyla modellenir)
