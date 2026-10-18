# DURUM — SPEC 03c rampa-helis

Dal: `claude/spec-03c-rampa-helis-uxonjr` · Oturum: bulut

## Sıradaki adım
SPEC metni kullanıcı onayı bekliyor; onaydan sonra A0 (`EntryMode`, `Tool.ramp_angle_max`) ve 03b dallarının üstüne `NotImplementedError` iskeleti.

## Test durumu
| Tarih | Geçen | Kalan | Not |
|---|---|---|---|

## Son oturum
**2026-10-18**
- `specs/03c-rampa-helis.md` taslağı yazıldı (helis, zigzag rampa, kontur boyunca rampa; kanıtlar ve kapalı form test değerleri).

## Açık sorular
- Cepte rampa biçimi: zigzag doğru (öneri) / ilk halka boyunca rampa.
- Giriş sığmazsa: `CamError` (öneri) / otomatik helis → rampa → dalma.
- Merkezden kesmeyen takım alt sınırları: `R_h ≥ r/2`, zigzag `2ℓ ≥ r`, kontur `P ≥ πr`; `ramp_angle_max` zorunlu (öneri).
- Varsayılanlar: `α = 2°`, `R_h = r/2`, `L = 2D`, `ramp_feed = feed` (öneri).
