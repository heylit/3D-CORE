# DURUM — SPEC 35 standart-parca

Dal: `claude/spec-35-standart-parca-xm561f` · Oturum: bulut

## Sıradaki adım
İskelet push edildi; ayrı test thread'inin test commit'i cherry-pick edilecek, sonra kod ayrı commit'te.

## Test durumu
| Tarih | Geçen | Kalan | Not |
|---|---|---|---|
| 2026-10-18 | — | — | Yalnız SPEC metni; kod ve test yok |

## Son oturum
**2026-10-18**
- SPEC 35 taslağı yazıldı: ISO 4762 / 4017 / 4032 / 7089 / 2338 / 15 parametrik parçalar (basit, el hesabıyla
  doğrulanan geometri), ISO 273 geçiş delikleri, SPEC 23 delik kayıtlarından eş eksen dizisi, vida boyu seçimi
  (dişliye imbus vida, boydan boyaya civata + 2 pul + somun), SPEC 08 eş eksen + düzlem kısıtlarıyla yerleşim.
- Arayüz (`*/model.py`, `geometry/part.py`) eki gerekmiyor.
- SPEC metni önerilen varsayılanlarla onaylandı (kullanıcı 11:14 kuralı: 2 dakika cevapsız → öneri kabul).
- `NotImplementedError` iskeleti: `geometry/standart/{__init__,tablo,parcalar}.py`, `assy/oneri.py`. Tablolar SPEC'teki
  değerlerle dolu; `tablo.P_KABA` = SPEC 23 kaba hatve tablosunun OCCT'siz kopyası (oneri.py 2P taşma için).

## Açık sorular
_(yok; 1–6 önerilen varsayılanlarla kabul edildi)_
