# DURUM — SPEC 04 G-code çıkışı ve okuyucu

Dal: `claude/project-thread-5ai6c8` · Oturum: bulut

## Sıradaki adım
Ek C (güvenli Z kesme seviyesinin üstünde, `stock_top`) onaylandı ve uygulandı: testler 95d273c (ayrı oturum), kod ayrı commit'te. · Dal: `claude/project-thread-ulgwqc`.

Ek B (tezgâh güvenliği) düzeltme PR'ının incelemesi ve birleşmesi. Sonra: bağımsız yorumlayıcıyla
çapraz kontrol (inceleme Y1), GRBL'de takım boyu.

## Test durumu
| Tarih | Geçen | Kalan | Not |
|---|---|---|---|
| 2026-10-18 | — | — | Sadece SPEC taslağı; kod ve test yok. |
| 2026-10-18 | 188 (tüm depo) | 0 failed | `cam/gcode/` yazıldı. 29 xfail SPEC 01'e ait. Testler paralel yazılırken çalıştırıldı (`test_gcode_cycles.py` henüz yoktu). |
| 2026-10-18 | 259 (tüm depo), 142 SPEC 04 | 0 | `dogrulayici` testleri (K1–K14) + `yazici` kodu birlikte yeşil; main (SPEC 01) dala alındı. `ruff check .` temiz. |

## Son oturum
**2026-10-18 — Ek B: G-code güvenlik düzeltmesi (inceleme K1, K2, K3)** · Dal: `claude/project-thread-6goesw`
- Önce düşen testler: `tests/cam/test_gcode_safety.py` (19 test; 14'ü düzeltmeden önce kırmızıydı).
- K1: yuvarlanınca tam daireye dönüşen kısa yay artık G1 (`writer.tiny_arc`).
- K2: `write(..., safe_z=None)`; op geçişi, devir/takım değişimi ve program sonunda güvenli Z'ye geri
  çekme; takım değişiminden önce M5; XY konumlama güvenli Z'de, iniş ayrı satırda.
- K3: Fanuc başında G54, takım değişiminden sonra `G0 G43 X Y Z H<n>`; okuyucu G43/H'yi denetliyor.
- Eski beklenen metinler Ek B'ye göre güncellendi (Fanuc altın, çok takımlı, devir değişimi, program
  sonu geri çekme, G99 okunuşu). `pytest` tüm depo yeşil, `ruff check .` temiz.

**Önceki oturum**
**2026-10-18 — `yazici`: `cam/gcode/` uygulandı**
- `modal.py` (`fmt`, `snap`, `ModalState`), `dialect.py` (`Dialect`, `GRBL`, `FANUC`), `cycles.py`
  (`DrillOp`, `hole_moves`, `peck_count`, `peck_depths`), `writer.py` (`write`), `reader.py` (`read`).
- Ek A altın metinleri (GRBL, Fanuc) birebir üretiliyor; altın yol okununca hareketler aynı.
- Rastgele 200 hareket (tohum 42) gidiş-dönüş: uç ≤ 4.99e-4 mm, F ≤ 0.05, merkez ≤ 9.2e-4 mm.
- G83 (r=2, z=−10, q=3, c=0.5): 4 G1, toplam G1 boyu 13.5; G81/G83 × G98/G99 Fanuc ve GRBL okunuşu `to_toolpath()` ile aynı.
- R biçimi çeyrek / 270° yaylarda merkez hatası ~2e-15 mm.

## Açık sorular
- GRBL'de takım boyu telafisi yok (G43.1 dinamik); `T2 M0` sonrası operatör Z'yi yeniden sıfırlamalı.
  Programa bir uyarı yorumu mu, G43.1 mi? (Ek B'de çözülmedi.)
- Varsayılan güvenli Z = op başlarının en yükseği. Ham malzeme üstü + pay gibi bir değer kurulum
  SPEC'inde (14) `cam/model.py`'ye taşınabilir.
- `Dialect.tool_change` alanının anlamı yazıcı tarafından belirlendi: `"M6"` her takım değişiminde yazılır,
  `"M0"` ilk takımda yazılmaz (GRBL). Uygun mu?
- GRBL 1.1'in `T` kelimesini kabul edip yok saydığı varsayımı gerçek kontrolörde doğrulanmadı.
- Okuyucu, ilk T/S'den önceki G0'ları konumlama olarak kabul ediyor (yola girmez); G1/G2/G3 ise `CamError`.
