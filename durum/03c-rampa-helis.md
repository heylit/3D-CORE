# DURUM — SPEC 03c rampa-helis

Dal: `claude/spec-03c-rampa-helis-uxonjr` · Oturum: bulut

## Sıradaki adım
Kod tamam; A0 (PR #107) birleşip CI çalışınca PR #77 birleştirilir.

## Test durumu
| Tarih | Geçen | Kalan | Not |
|---|---|---|---|
| 2026-10-18 | 163 (SPEC 03c) | 0 | A0 ucu 5eb08c1 üstünde, `--uygulanmamis-hata` |

## Son oturum
**2026-10-18**
- `specs/03c-rampa-helis.md` taslağı yazıldı (helis, zigzag rampa, kontur boyunca rampa; kanıtlar ve kapalı form test değerleri).

- SPEC onaylandı (kullanıcı 11:13, önerilerle); `NotImplementedError` iskeleti: `cam/giris.py`, `Cut.entry`, `Cut.ramp_feed`.
- Testler ayrı oturumda (aadde68, cherry-pick); kod ayrı commit'te: `cam/giris.py`, `cam/ops2d.py` (`Cut.entry`/`ramp_feed`, pocket/contour girişi). İlk denemede 163/163.

## Açık sorular
_(yok; aşağıdakiler önerilerle onaylandı)_
- Cepte rampa biçimi: zigzag doğru (öneri) / ilk halka boyunca rampa.
- Giriş sığmazsa: `CamError` (öneri) / otomatik helis → rampa → dalma.
- Merkezden kesmeyen takım alt sınırları: `R_h ≥ r/2`, zigzag `2ℓ ≥ r`, kontur `P ≥ πr`; `ramp_angle_max` zorunlu (öneri).
- Varsayılanlar: `α = 2°`, `R_h = r/2`, `L = 2D`, `ramp_feed = feed` (öneri).
