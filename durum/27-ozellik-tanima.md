# DURUM — SPEC 27 ozellik-tanima

Dal: `claude/project-thread-ysr96h` · Oturum: bulut

## Sıradaki adım
İskelet push edildi; testleri ayrı bir thread yazacak, kod ondan sonra ayrı commit'te.

## Test durumu
| Tarih | Geçen | Kalan | Not |
|---|---|---|---|

## Son oturum
**2026-10-18**
- SPEC 27 taslağı yazıldı (26 numarası eskiz thread'inde, 25 Tezgah torna/montaj ekranına ayrıldı).
- Yöntem OCCT'de ön denendi: dilim kesitleri, düz / silindir yüz sorguları, havşa koni alan dengesi (fark 111.5608 mm²
  formülle aynı), STEP'te Ø30 silindirin 270° + 90° iki yüze bölündüğü görüldü (silindir birleştirme kuralı eklendi).
- Arayüz değişikliği gerekmiyor: sadece `Part.bbox/area/holes/planar_faces/cylindrical_faces/section_z`.
- SPEC kullanıcı onayı: 2026-10-18 10:38 UTC, proje sohbetinde yazılı ("… 27 … metinlerini onaylıyorum").
- Torna girdisi atfı SPEC 28 `TurnProfile.outer` / `.inner` olarak güncellendi; `NotImplementedError` iskeletleri eklendi.

## Açık sorular
_(yok)_ — torna girdisi SPEC 28 `TurnProfile` (SPEC 28 onaylı, kodu ayrı thread'de).
