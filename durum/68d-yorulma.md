# DURUM — SPEC 68d Yüksek çevrimli yorulma (Marin, Basquin, Goodman)

Dal: `claude/project-thread-wmosjl` · Oturum: bulut thread "Çözücü düzeltmeleri" (kodlayıcı)

## Sıradaki adım
B2 (malzeme kodu) ve 67b main'e girince main'i al; K7 için `parca_yorulmasi`'nı 67b köprüsüyle yaz.

## Test durumu
| Tarih | Geçen | Kalan | Not |
|---|---|---|---|
| 2026-10-18 | 32 | 46 | Kod (K1–K6, K8, K9). 46 test B2 `Malzeme.__post_init__` henüz `NotImplementedError` olduğu için "uygulanmamış"; B2 doğrulaması yamalanınca 77/77 formül + FEM testi geçiyor. K7 (occt, slow) 67b'yi bekliyor. |
| 2026-10-18 | – | – | İskelet: `analiz/yorulma.py` arayüzü, gövdeler `NotImplementedError`. Testler henüz yok. |

## Son oturum
**2026-10-18 — Kod (K1–K6, K8, K9)**
- Testler ayrı oturumdan (commit 8f85adb, cherry-pick 13f97be) alındı; kod ayrı commit'te, test dosyalarına dokunulmadı.
- `Marin.katsayilar` (tablo 6-2, 6-5; kb aralığı 2.79–254 mm, nan dahil hata), `dayanim_siniri`, `goodman`,
  `omur`, `yorulma` (düğüm tensörleri SPEC 13 `nodal_stress_tensors`, işaretli von Mises iz işaretinden; iz = 0 → +).
- K3 yorumu (test oturumu, SPEC metni değişmedi): `σ_ar = Se` tam eşitlikte "σ_ar ≤ Se → inf" kuralı geçerli,
  `σ_ar = 0.9 Rm`'de düşük çevrim kuralı (N ≤ 1e3 kırpma); doğrunun uçları 1e6 / 1e3 sınırların hemen içinden sınanıyor.
- `σ_m ≥ Rm` (Goodman paydası ≤ 0): `σ_ar = inf`, düşük çevrim sayılır, N en küçük pozitif sayı (nan yok).
- `parca_yorulmasi` hâlâ `NotImplementedError` (67b).

**2026-10-18 — İskelet**
- Onaylı metin `specs/68d-yorulma.md`'ye kondu (kullanıcı onayı 16:19).
- `analiz/yorulma.py`: `YUZEYLER`, `Marin`, `dayanim_siniri`, `goodman`, `omur`, `Yorulma`, `yorulma`,
  `parca_yorulmasi` imzaları SPEC'teki gibi; `analiz/__init__.py`'ye eklendi.
- Dal B2 iskeletinin (PR #121, 7ec8f7d) üstünde: `malzeme.model.Malzeme` oradan. B2 birleşince main alınacak.

## Açık sorular
- Hata sınıfı: SPEC "ModelError" diyor. `analiz/` `core.model.ModelError` kullanıyor; `malzeme.model` kendi
  `ModelError`'ını tanımlıyor (ikisi de `ValueError`). Kod `core.model.ModelError` fırlatacak.
- `analiz/dayanim.py` (67b) bu dalda yok; `parca_yorulmasi` ve K7 67b birleşince.
