# DURUM — SPEC 28 torna-profili

Dal: `claude/project-thread-hv45j3` · Oturum: bulut

## Sıradaki adım
SPEC onaylandı (Mustafa, 2026-10-18 10:38, proje sohbeti; davranış kartta "Hata ver"). Sıradaki: `geometry/part.py` arayüz PR'ı (`SectionEdge`, `SectionFace`,
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
_(yok)_ — Karar: dönel olmayan parça yüz numaralarıyla reddedilir; dönel zarf ileride ayrı SPEC.
Arayüz eki PR #53'te (`3fa6b5d`); bu dala merge edildi.
