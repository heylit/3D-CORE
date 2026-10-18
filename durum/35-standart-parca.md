# DURUM — SPEC 35 standart-parca

Dal: `claude/spec-35-standart-parca-xm561f` · Oturum: bulut

## Sıradaki adım
SPEC metni kullanıcı onayında; onaydan sonra `NotImplementedError` iskeleti, ayrı test thread'inin testleri, sonra kod.

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

## Açık sorular
1. `assy/oneri.py`, OCCT'siz `geometry/standart/tablo.py`'yi import ediyor (önerilen: tablo geometry'nin ikinci
   OCCT'siz arayüz dosyası sayılır).
2. Basit geometri (diş, pah, köşe yuvarlatması yok; rulman dolu halka) kabul mü?
3. Boydan boya bağlantıda 2 pul (baş ve somun altı) + uçta 2 hatve taşma kuralı.
4. Diş kavrama katsayısı κ varsayılanı 1.0·d (çelik); alüminyum için kullanıcı 2.0 verir.
5. Otomatik öneri yalnız vida/civata; pim ve rulman yalnız kütüphane; havşa başlı vida yok.
