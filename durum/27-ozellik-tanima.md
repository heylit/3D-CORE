# DURUM — SPEC 27 ozellik-tanima

Dal: `claude/project-thread-ysr96h` · Oturum: bulut

## Sıradaki adım
SPEC metni kullanıcı onayında; onaydan sonra `NotImplementedError` iskeleti, ardından ayrı oturumda testler.

## Test durumu
| Tarih | Geçen | Kalan | Not |
|---|---|---|---|

## Son oturum
**2026-10-18**
- SPEC 27 taslağı yazıldı (26 numarası eskiz thread'inde, 25 Tezgah torna/montaj ekranına ayrıldı).
- Yöntem OCCT'de ön denendi: dilim kesitleri, düz / silindir yüz sorguları, havşa koni alan dengesi (fark 111.5608 mm²
  formülle aynı), STEP'te Ø30 silindirin 270° + 90° iki yüze bölündüğü görüldü (silindir birleştirme kuralı eklendi).
- Arayüz değişikliği gerekmiyor: sadece `Part.bbox/area/holes/planar_faces/cylindrical_faces/section_z`.

## Açık sorular
- Katıdan dönel profil çıkarma SPEC 22'de (yol haritası); SPEC 27 torna tarafında profili girdi alır.
