# DURUM — SPEC 27 ozellik-tanima

Dal: `claude/project-thread-ysr96h` · Oturum: bulut

## Sıradaki adım
Kod yazıldı, 52/52 SPEC 27 testi yeşil; PR #46 birleşmeye hazır.

## Test durumu
| Tarih | Geçen | Kalan | Not |
|---|---|---|---|
| 2026-10-18 | 52 | 0 | test commit 0e1f4bd (ayrı oturum) cherry-pick; tüm paket 2047 geçti |

## Son oturum
**2026-10-18**
- SPEC 27 taslağı yazıldı (26 numarası eskiz thread'inde, 25 Tezgah torna/montaj ekranına ayrıldı).
- Yöntem OCCT'de ön denendi: dilim kesitleri, düz / silindir yüz sorguları, havşa koni alan dengesi (fark 111.5608 mm²
  formülle aynı), STEP'te Ø30 silindirin 270° + 90° iki yüze bölündüğü görüldü (silindir birleştirme kuralı eklendi).
- Arayüz değişikliği gerekmiyor: sadece `Part.bbox/area/holes/planar_faces/cylindrical_faces/section_z`.
- SPEC kullanıcı onayı: 2026-10-18 10:38 UTC, proje sohbetinde yazılı ("… 27 … metinlerini onaylıyorum").
- Torna girdisi atfı SPEC 28 `TurnProfile.outer` / `.inner` olarak güncellendi; `NotImplementedError` iskeletleri eklendi.
- Kod: `cam/features.py` (2.5D dilim kesitleri, yay geri kurma, delik tanıma), `cam/turn_features.py` (zarf, kanal).

## Açık sorular
_(yok)_ — torna girdisi SPEC 28 `TurnProfile` (SPEC 28 onaylı, kodu ayrı thread'de).
