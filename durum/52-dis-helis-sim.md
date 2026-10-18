# DURUM — SPEC 52 diş ve helis simülasyonu

Dal: `claude/project-thread-012y8t` · Oturum: bulut (kod: session_01774ib8WCsNwcEC8uqzHvZh)

## Sıradaki adım
İskelet gönderildi; testler ayrı oturumda yazılacak, sonra cherry-pick ve kod ayrı commit'te.

## Test durumu
| Tarih | Geçen | Kalan | Not |
|---|---|---|---|
| 2026-10-18 | — | — | Yalnız iskelet (`NotImplementedError`); test yok. |

## Son oturum
**2026-10-18**
- SPEC onayı: 14:53 UTC Dalga 6 onay sorusu, 2 dk itirazsız kabul kuralı (11:14 UTC); açık sorular önerilen cevaplarla.
- `specs/52-dis-helis-sim.md` taslaktan yazıldı; kararlar bölümü eklendi.
- İskelet: `cam/sim/polar.py` (`PolarMap`), `cam/sim/thread_sim.py` (`simulate_thread`), `cam/sim/thread_measure.py`
  (`ThreadMeasure`, `thread_measure`), `cam/thread_mill.py` (`ThreadMillForm`, `thread_mill`); `cam/sim/__init__.py` dışa açar.
- Bağımlılık notu: B0 (`PathMeta.strategy`) ve 04b (`G84` kılavuz op'u) henüz `main`'de değil; iskelet bunlara bağlı değil.

## Açık sorular
_(yok)_
- Ek 1 / Ek 2 (kullanıcı yazılı onayı 16:27 UTC): K8 tri-dexel yerine Pappus kapalı form hacmi; K6 `D = 10`, tolerans
  `0.03·P`. K5 testi `G84` yolunu elle kurar (04b'ye bağlı değil); `TapOp.to_toolpath` kullanan test 04b birleşene kadar
  "uygulanmamış" görünür.
