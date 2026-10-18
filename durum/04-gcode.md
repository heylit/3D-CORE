# DURUM — SPEC 04 G-code çıkışı ve okuyucu

Dal: `claude/project-thread-5ai6c8` · Oturum: bulut

## Sıradaki adım
PR #4 incelemesi ve birleşmesi; sonra DURUM.md'de 04-gcode satırı tamamlandı olarak işaretlenir.

## Test durumu
| Tarih | Geçen | Kalan | Not |
|---|---|---|---|
| 2026-10-18 | — | — | Sadece SPEC taslağı; kod ve test yok. |
| 2026-10-18 | 188 (tüm depo) | 0 failed | `cam/gcode/` yazıldı. 29 xfail SPEC 01'e ait. Testler paralel yazılırken çalıştırıldı (`test_gcode_cycles.py` henüz yoktu). |
| 2026-10-18 | 259 (tüm depo), 142 SPEC 04 | 0 | `dogrulayici` testleri (K1–K14) + `yazici` kodu birlikte yeşil; main (SPEC 01) dala alındı. `ruff check .` temiz. |

## Son oturum
**2026-10-18 — `yazici`: `cam/gcode/` uygulandı**
- `modal.py` (`fmt`, `snap`, `ModalState`), `dialect.py` (`Dialect`, `GRBL`, `FANUC`), `cycles.py`
  (`DrillOp`, `hole_moves`, `peck_count`, `peck_depths`), `writer.py` (`write`), `reader.py` (`read`).
- Ek A altın metinleri (GRBL, Fanuc) birebir üretiliyor; altın yol okununca hareketler aynı.
- Rastgele 200 hareket (tohum 42) gidiş-dönüş: uç ≤ 4.99e-4 mm, F ≤ 0.05, merkez ≤ 9.2e-4 mm.
- G83 (r=2, z=−10, q=3, c=0.5): 4 G1, toplam G1 boyu 13.5; G81/G83 × G98/G99 Fanuc ve GRBL okunuşu `to_toolpath()` ile aynı.
- R biçimi çeyrek / 270° yaylarda merkez hatası ~2e-15 mm.

## Açık sorular
- `Dialect.tool_change` alanının anlamı yazıcı tarafından belirlendi: `"M6"` her takım değişiminde yazılır,
  `"M0"` ilk takımda yazılmaz (GRBL). Uygun mu?
- GRBL 1.1'in `T` kelimesini kabul edip yok saydığı varsayımı gerçek kontrolörde doğrulanmadı.
- Okuyucu, ilk T/S'den önceki G0'ları konumlama olarak kabul ediyor (yola girmez); G1/G2/G3 ise `CamError`.
