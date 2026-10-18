# DURUM — SPEC 52 diş ve helis simülasyonu

Dal: `claude/project-thread-012y8t` · Oturum: bulut (kod: session_01774ib8WCsNwcEC8uqzHvZh)

## Sıradaki adım
PR #119 CI (pytest + kapı) yeşilse birleştir.

## Test durumu
| Tarih | Geçen | Kalan | Not |
|---|---|---|---|
| 2026-10-18 | 53 | 0 | Testler `83fdb0f`, `654c480` (session_012CV12jWqYWKvYs5L85ZpEU, dal `claude/project-thread-py581v`). K6 (3 test) `slow`. |

## Son oturum
**2026-10-18**
- SPEC onayı: 14:53 UTC Dalga 6 onay sorusu, 2 dk itirazsız kabul kuralı (11:14 UTC); açık sorular önerilen cevaplarla.
- Ek 1 / Ek 2 (kullanıcı yazılı onayı 16:27 UTC): K8 tri-dexel yerine Pappus kapalı form hacmi; K6 `D = 10`, tolerans
  `0.03·P`.
- Kod: `cam/sim/polar.py` (`PolarMap`), `cam/sim/thread_sim.py` (torna diş pasoları kesici bandında kesin profil, kılavuz
  ISO iç profil + giriş pahı, diş frezesinde helis yaylarına helisel koordinat tablosu E(s) ve diğer hareketlere
  örnekleme), `cam/sim/thread_measure.py`, `cam/thread_mill.py`.
- Yön kuralı: sağ helis = z, θ ile artar; torna M3 ile −z'ye ilerleyen paso ve aşağı giden kılavuz sağ helis verir.
  `lead_err` SPEC formülüyle (sağ helis) hesaplanır; sol helis (ters yönlü paso) büyük `lead_err` gösterir.
- Diş frezesi takımı: `ThreadMillTool(Tool)` (FLAT türü, `form` alanı) `cam/thread_mill.py`'de; `ToolKind.THREAD_MILL`
  arayüz PR'ı gelene kadar (Karar 1) simülatör profili buradan okur.
- K6 zarf referansına uzaklık ≈ 3e-8 mm (sınır 1e-6); M16×1.5 iç diş `d₂` kayması +0.023·P (Ek 2).

## Açık sorular
_(yok)_
