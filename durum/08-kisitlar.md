# DURUM — SPEC 08 Montaj kısıtları ve konum çözücü

Dal: `claude/project-thread-fe0oon` · Oturum: bulut

## Sıradaki adım
SPEC taslağı kullanıcı onayında; onay gelince `tests/assy/test_mates.py` ve `tests/assy/test_solver.py`'yi yaz, sonra `assy/mates.py` ve `assy/solver.py`.

## Test durumu
| Tarih | Geçen | Kalan | Not |
|---|---|---|---|
| 2026-10-18 | — | — | Sadece SPEC taslağı, kod ve test yok |

## Son oturum
**2026-10-18**
- `specs/08-kisitlar.md` taslağı yazıldı (artık tablosu, Gauss–Newton en küçük normlu adım, rank ile DOF sayımı, 13 kabul kriteri).

## Açık sorular
- PLANE–PLANE çakışık/mesafe kısıtında normaller zıt mı (yüz yüze, varsayılan) yoksa her iki yön de mi kabul?
- AXIS yönü eş eksende serbest (varsayılan) mi?
