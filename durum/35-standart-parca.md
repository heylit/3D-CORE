# DURUM — SPEC 35 standart-parca

Dal: `claude/spec-35-standart-parca-xm561f` · Oturum: bulut

## Sıradaki adım
Kod yazıldı, testler yeşil; PR #82 CI + kapı yeşilse birleştirilecek.

## Test durumu
| Tarih | Geçen | Kalan | Not |
|---|---|---|---|
| 2026-10-18 | — | — | Yalnız SPEC metni; kod ve test yok |
| 2026-10-18 | 177 | 0 | test_standart.py + test_oneri.py (K1–K13), bağımsız test commit'i 5aa8c24 |

## Son oturum
**2026-10-18**
- SPEC 35 taslağı yazıldı: ISO 4762 / 4017 / 4032 / 7089 / 2338 / 15 parametrik parçalar (basit, el hesabıyla
  doğrulanan geometri), ISO 273 geçiş delikleri, SPEC 23 delik kayıtlarından eş eksen dizisi, vida boyu seçimi
  (dişliye imbus vida, boydan boyaya civata + 2 pul + somun), SPEC 08 eş eksen + düzlem kısıtlarıyla yerleşim.
- Arayüz (`*/model.py`, `geometry/part.py`) eki gerekmiyor.
- SPEC metni önerilen varsayılanlarla onaylandı (kullanıcı 11:14 kuralı: 2 dakika cevapsız → öneri kabul).
- `NotImplementedError` iskeleti: `geometry/standart/{__init__,tablo,parcalar}.py`, `assy/oneri.py`. Tablolar SPEC'teki
  değerlerle dolu; `tablo.P_KABA` = SPEC 23 kaba hatve tablosunun OCCT'siz kopyası (oneri.py 2P taşma için).

- Testler ayrı oturumda yazıldı (`claude/project-thread-b5iore`, 5aa8c24), cherry-pick edildi; kod ayrı commit'te.
- Eşleşmeme kodlarının denetim sırası: ayni_bilesen, yon, ortada_dis, kor_ara, bosluk, havsa, ince_hatve,
  olcu_uyusmuyor, lamba_somun, bas_sigmiyor, uzunluk_yok, dis_yetersiz.

## Açık sorular
- K12 metni: "eklenen T'ler G·T" iddiası "en küçük dönme" kuralı yüzünden yalnız dizi eksenine dik
  eksenli G için tam doğru; keyfi G'de konum ve eksen yönü G ile taşınır (testler böyle denetliyor).
  SPEC metninin buna göre düzeltilmesi kullanıcı onayı bekliyor (kodu yazan oturum SPEC'i değiştirmez).
