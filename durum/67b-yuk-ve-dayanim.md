# DURUM — SPEC 67b Yüze yük ve mesnet, hacim kuvvetleri, ısıl yük, emniyet katsayısı

Dal: `claude/spec-06-cam-3d-09jwcj` (67a dalı `claude/spec-11-tet4-cvi89m` ucundan; 67a `main`'e girince `main`'e
taşınır) · Oturum: bulut · SPEC: `specs/67-fem-genisletme.md` (67b bölümü)

## Sıradaki adım
67a (#122) birleşince `main`'i dala almak; GitHub'da pytest + kapi yeşilse birleştirmek. K17 ve gerçek `ThermalResult` testi 66 / 56 `main`'e
girince açılır.

## Test durumu
| Tarih | Geçen | Kalan | Not |
|---|---|---|---|
| 2026-10-18 | — | — | İskelet: tüm işlevler NotImplementedError |
| 2026-10-18 | 87 | 2 | Kod + test düzeltmesi 79b6b25; 2 uygulanmamış (K17: 66 kütüphanesi, gerçek ThermalResult: 56) |

## Son oturum
**2026-10-18**
- İskelet: `core/yukler.py`, `mesh/yuz_esleme.py` (`mesh_part`, `PartMesh`), `analiz/dayanim.py` (`Dayanim`,
  `emniyet`, `parca_dayanimi`); `mesh/__init__.py`, `analiz/__init__.py` yeni adlar.
- SPEC'in bıraktığı biçim ayrıntıları her modülün docstring'inde (Load sırası, T / alpha biçimi, yüz üçgeni
  bölüntüsü, n eşitliği, gevrek grup, kuvvetin alanla dağıtımı, eksen biçimi).
- Bağımlılıklar `main`'de değil: B2 / 66 (`Malzeme`, #127) ve 56 (`ThermalResult`) ördek tipleme ile kullanılır,
  import edilmez.

**2026-10-18 (kod)**
- Test commit'leri 752ab6c ve 79b6b25 (`tet10_agi` sağ el düzeltmesi) cherry-pick edildi; 67a dalı (`b758e20` kod) birleştirildi.
- `core/yukler.py`: tet4 4 noktalı Gauss, tet10 15 noktalı Keast (eğri elemanda toplam tam); ısıl yük tet4'te
  ortalama T, tet10'da köşelerden doğrusal T ile 4 noktalı Gauss. `temperature_lookup`, `alpha_of`, `vector3`
  `analiz/dayanim.py` de kullandığı için açık ad.
- `mesh/yuz_esleme.py`: `tet_mesh` ağı + aynı seçeneklerle ayrı gmsh yüzey ağı; gmsh yüzeyi ↔ OCCT yüzü alan ve
  kütle merkeziyle (göreli 1e-6 / köşegen 1e-6), sınır üçgeni ↔ yüzey köşe koordinatlarıyla tam eşleşir
  (eşleşmeyen → ModelError). `mesh/gmsh_ag.py` değişmedi.
- `analiz/dayanim.py`: düğüm σ_vM `core.post.nodal_stress_tensors`; T varsa düğümde hacim ağırlıklı D α ΔT
  düşülür. `kuvvet` yüz alanı `add_traction`'ın kendi kuralıyla ölçülür (Σ = F tam, eğri tri6 dahil).
- K17 ön hesabı (D3, 66 dalının 1.0577 kaydıyla): n_min 6.011, hedef 5.854, oran 1.027 (%3 içinde); düğüm
  r = 5.000 delik kenarında; h = 2 tet10 ≈ 75 bin düğüm, ≈ 300 s (slow).

## Açık sorular
- `test_centrifugal_total_octant` yerelde ≈ 10.7 s (çoğu gmsh order=2 ağı); `slow` işareti test oturumunun kararı.
