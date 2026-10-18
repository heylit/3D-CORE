# DURUM — SPEC 67b Yüze yük ve mesnet, hacim kuvvetleri, ısıl yük, emniyet katsayısı

Dal: `claude/spec-06-cam-3d-09jwcj` (67a dalı `claude/spec-11-tet4-cvi89m` ucundan; 67a `main`'e girince `main`'e
taşınır) · Oturum: bulut · SPEC: `specs/67-fem-genisletme.md` (67b bölümü)

## Sıradaki adım
Ayrı test oturumunun test commit'ini cherry-pick edip `core/yukler.py`, `mesh/yuz_esleme.py`, `analiz/dayanim.py`
kodunu ayrı commit'te yazmak.

## Test durumu
| Tarih | Geçen | Kalan | Not |
|---|---|---|---|
| 2026-10-18 | — | — | İskelet: tüm işlevler NotImplementedError |

## Son oturum
**2026-10-18**
- İskelet: `core/yukler.py`, `mesh/yuz_esleme.py` (`mesh_part`, `PartMesh`), `analiz/dayanim.py` (`Dayanim`,
  `emniyet`, `parca_dayanimi`); `mesh/__init__.py`, `analiz/__init__.py` yeni adlar.
- SPEC'in bıraktığı biçim ayrıntıları her modülün docstring'inde (Load sırası, T / alpha biçimi, yüz üçgeni
  bölüntüsü, n eşitliği, gevrek grup, kuvvetin alanla dağıtımı, eksen biçimi).
- Bağımlılıklar `main`'de değil: B2 / 66 (`Malzeme`, #127) ve 56 (`ThermalResult`) ördek tipleme ile kullanılır,
  import edilmez.

## Açık sorular
_(yok)_
