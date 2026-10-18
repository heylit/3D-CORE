# DURUM — SPEC 29 islem-plani

Dal: `claude/project-thread-k667wt` · Oturum: bulut

## Sıradaki adım
SPEC metni onaylandı (kullanıcı, 2026-10-18 10:46, "SPEC 29 onaylandı"); kod, bağımlılıklar (SPEC 27, 14, 05, 21, 22) `main`'e
birleşince yazılır (test bağımsızlığı akışıyla).

## Test durumu
| Tarih | Geçen | Kalan | Not |
|---|---|---|---|
| 2026-10-18 | — | — | Yalnız SPEC metni; kod ve test yok |

## Son oturum
**2026-10-18**
- SPEC 29 taslağı yazıldı: freze (yüz alma, açık bölge, cep + kalan malzeme, delik, lamba, alt yüz için ikinci
  bağlama) ve torna (alın, kaba, finiş, kanal, iç işlem) işlem planı; takım seçimi ve kesme verisi SPEC 14'ten;
  doğrulama SPEC 05 / 22; G-code SPEC 04 / 14 / 21.
- Arayüz (`*/model.py`, `geometry/part.py`) değişikliği gerekmiyor.
- SPEC metni onaylandı (2026-10-18 10:46). SPEC 05 `main`'de; kod 27, 14, 21, 22'yi bekliyor.

- İskelet: `cam/plan.py`, `cam/plan_turn.py`, `cam/plan_verify.py` (`NotImplementedError`); dal main + SPEC 27
  (`claude/project-thread-ysr96h`) + SPEC 22 iskeleti (`claude/project-thread-012y8t`) üstünde. Testler ayrı oturumda.

## Açık sorular
_(yok)_
