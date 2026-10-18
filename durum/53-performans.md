# DURUM — SPEC 53 performans (bloklu simülasyon, BVH, LOD)

Dal: `claude/spec-05-cam-sim-ch33p2` · Oturum: bulut

## Sıradaki adım
Bağımsız test thread'inin commit'i cherry-pick edilecek; başlangıç çizgisi (B1, B2 süreleri) ölçülecek; kod ayrı commit'te.

## Başlangıç çizgisi (mevcut sürüm, 0.1 mm z-map)
| Program | Makine | Süre | Not |
|---|---|---|---|
| B1 | — | — | ölçülecek |
| B2 | — | — | ölçülecek |

## Test durumu
| Tarih | Geçen | Kalan | Not |
|---|---|---|---|
| 2026-10-18 | — | — | `specs/53-performans.md` (onaylı taslaktan) + `NotImplementedError` iskeleti. |

## Son oturum
**2026-10-18 — SPEC ve iskelet**
- Taslak `specs/53-performans.md`'ye alındı; açık sorular önerilen cevaplarla karar olarak yazıldı.
- İskelet: `cam/sim/blok.py` (`merge_collinear`), `assy/bvh.py` (`Bvh`), `viz/lod.py` (`Level`, `simplify`,
  `hausdorff`, `levels`, `pick`); `simulate(block=256, merge=True)` ve `check(broadphase="bvh")` parametreleri
  doğrulanıyor, iskelette eski yol kullanılıyor (mevcut davranış bozulmaz).

## Açık sorular
- Yok.
