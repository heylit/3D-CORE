# DURUM — SPEC 28 torna-profili

Dal: `claude/project-thread-hv45j3` · Oturum: bulut

## Sıradaki adım
SPEC metni kullanıcı onayında; onaydan sonra önce `geometry/part.py` arayüz PR'ı (`SectionEdge`, `SectionFace`,
`AxialSection`, `Part.axial_section`), sonra test thread'i, sonra kod.

## Test durumu
| Tarih | Geçen | Kalan | Not |
|---|---|---|---|
| 2026-10-18 | — | — | Sadece SPEC metni; kod ve test yok |

## Son oturum
**2026-10-18**
- SPEC 28 taslağı yazıldı: OCCT yarı düzlem kesiti (`BRepAlgoAPI_Common`), yüz sınıflamasıyla dönel simetri kontrolü,
  Pappus hacim + alan denetimi, serbest eğri için doğru + yay uydurma, kapalı kesitten SPEC 20 dış / iç profili.
- OCCT denemesi: basamaklı mil + küre uçta kesit kenarları tam `LINE` / `CIRCLE`; elipsin `revolve`'unda yüz
  `REVOLUTION`, kesit kenarı `ELLIPSE` (K9 testinin dayanağı).
- Tüketiciler: SPEC 22 (`profile_rmap` kapalı bölge alır → `TurnProfile.section`), SPEC 27 (`turn_features(profile)` →
  `outer` / `inner`).

## Açık sorular
- Dönel olmayan parça: hata (öneri) mi, dönel zarf mı? Koordinatöre karar sorusu olarak gönderildi.
- `geometry/part.py` arayüz eki: sahibi thread ve kullanıcı onayı bekleniyor.
