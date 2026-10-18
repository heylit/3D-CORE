# DURUM — SPEC 53 performans (bloklu simülasyon, BVH, LOD)

Dal: `claude/spec-05-cam-sim-ch33p2` · Oturum: bulut

## Sıradaki adım
Bağımsız test commit'i cherry-pick edilecek; kod commit'i ve CI ölçümü. B2 < 10 s saf numpy ile tutmuyor:
CI ölçümünden sonra numba kararı kullanıcıya sorulacak (karar 2).

## Ölçümler (0.1 mm z-map, bulut oturumu; bu makinede bellek sayfa hataları pahalı, CI daha hızlı olmalı)
| Program | Yol | Süre | Not |
|---|---|---|---|
| B1 | eski (`block=None, merge=False`) | 32.2 s | 439 hareket; 13 s'si olay sıralaması (lexsort) |
| B1 | yeni | 9.6 s | z-map eski yolla bit düzeyinde aynı |
| B2 | eski | ölçülmedi | 0.5 mm'de bile 384 s (70 319 hareket, altın oran araması) |
| B2 | yeni | 103 s | fark ≤ 1.4e-14 mm; 39 s zarf, ~30 s olay kaydı/yerleştirme |
| CI (`ubuntu-latest`) | — | — | `test_perf_hiz.py` çıktısından yazılacak |

## Uygulama notları
- `merge=True`: hareketin alt adımları ve aynı doğrudaki ardışık G1'ler tek süpürme. Gövde denetimi hareket öncesi
  yüzeyle temiz çıkmıyorsa, `part_z` verilmişse veya hareket G0 ise SPEC 05 yolu (çarpışma kayıtları birebir).
- Küresel uç zarfı kapalı form (kapsül–ışın); iz sınırı halkasında (|d² − R²| ≤ 1e-9 R²) SPEC 05 zarfı, çünkü √ orada
  kötü koşullu (teğet hücrede iki yol farklı karar verebiliyordu: 0.2 mm ızgarada 4 mm fark görüldü, düzeltildi).
- Birleşmiş G1 grubunda adım hacmi "pencere farkı" ile paylaştırılır (SPEC); toplam ve z-map aynı.
- Olaylar hücre başına sayaçla doğrudan yerleştiriliyor (lexsort yerine, aynı sonuç).
- `block`: karo içinde hücre başına işlem → sonuç karo boyundan bağımsız (bit düzeyinde).
- BVH: 2000 halkalı mil senaryosunda sort and sweep 8.8 s, BVH 0.056 s (158×); aday listeleri aynı.
- LOD: 81 920 üçgenli kürede üç seviye 43 s; Hausdorff K7 sınırının ~1/3'ü; ağ kapalı. Hata tipi `VizError`.

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
