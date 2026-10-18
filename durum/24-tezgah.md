# DURUM — SPEC 24 tezgah

Dal: `claude/project-thread-c0lzh0` · Oturum: bulut

## Sıradaki adım
SPEC 05 (PR #54) `main`'e girince `main`'i dala merge et; K3/K5/K6 gerçek simülasyonla yeşil olmalı.
CI'da `tests/tezgah/` için kurulum satırına `web` eklenmeli (PR #47 / `.github` sahibi).

## Test durumu
| Tarih | Geçen | Kalan | Not |
|---|---|---|---|
| 2026-10-18 | — | — | İskelet; test yok. |
| 2026-10-18 | pytest 2081 (tests/tezgah 86) · vitest 34 · Playwright 7 | 0 | SPEC 05 kodu yerelde çalışma ağacında (commit'lenmedi). Test commit'i 41e1ed4 (b760482'den cherry-pick, ayrı oturum). |

## Son oturum
**2026-10-18**
- Köprü (`tezgah/kopru.py`): hareket↔G-code satır eşlemesi (önek programlar; FANUC sabit çevrimleri delik başına),
  `cam.sim.simulate` (Machine(), cell=1.0, part_z=mesh_zmap) ile sim; noktalar/sim ikili biçimleri,
  kontroller (çakma, hızlı çarpma, sap, tutucu, G-code geri okuma).
- Örnek iş `flans-plakasi` (uydurma geometri): yüzey, dış kontur, dairesel cep, 4 delik G83, FANUC.
- Sunucu: FastAPI, `/api/isler`, `/api/is/{ad}`, `/noktalar`, `/sim`, `POST /parametre` (hata → 422, iş değişmez).
- Ön yüz: three.js sahne (z-map yüzeyi, yol katmanları, hayalet takım, eski yol izi), zaman şeridi,
  G-code paneli, müfettiş, komut çubuğu (Ctrl K), klavye kısayolları, 400–1440 px duyarlı.
- Playwright yerel çalıştırma: `TEZGAH_PYTHON` ve `TEZGAH_CHROMIUM` ortam değişkenleri.

## Açık sorular
- CI `.[dev,cad]` kuruyor; `tests/tezgah/` CI'da çalışsın diye kurulum satırına `web` eklenmeli
  (`.github` sahibi "Test bağımsızlığı CI kapısı" thread'i; koordinatöre bildirildi).
- SPEC 05 merge olana kadar sim'e bağlı Python testleri CI'da kırmızı.
