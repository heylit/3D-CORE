# DURUM — SPEC 28 torna-profili

Dal: `claude/project-thread-hv45j3` · Oturum: bulut

## Sıradaki adım
Kod yazıldı; PR #56'da CI (pytest + kapi) yeşil olunca birleşir.

## Test durumu
| Tarih | Geçen | Kalan | Not |
|---|---|---|---|
| 2026-10-18 | — | — | Sadece SPEC metni; kod ve test yok |
| 2026-10-18 | 67 | 0 | Test commit'i `71d68f0` (ayrı oturum) cherry-pick edildi; kod `cam/turn_profile.py`, `geometry/revolve.py` |

## Son oturum
**2026-10-18**
- SPEC 28 taslağı yazıldı: OCCT yarı düzlem kesiti (`BRepAlgoAPI_Common`), yüz sınıflamasıyla dönel simetri kontrolü,
  Pappus hacim + alan denetimi, serbest eğri için doğru + yay uydurma, kapalı kesitten SPEC 20 dış / iç profili.
- OCCT denemesi: basamaklı mil + küre uçta kesit kenarları tam `LINE` / `CIRCLE`; elipsin `revolve`'unda yüz
  `REVOLUTION`, kesit kenarı `ELLIPSE` (K9 testinin dayanağı).
- Tüketiciler: SPEC 22 (`profile_rmap` kapalı bölge alır → `TurnProfile.section`), SPEC 27 (`turn_features(profile)` →
  `outer` / `inner`).

**2026-10-18 (kod)**
- `geometry/revolve.py`: yüz sınıflama (OCCT yüzey türü + eksen), otomatik eksen, yarı düzlem `BRepAlgoAPI_Common`
  kesiti, kenarlar `BRepTools_WireExplorer` sırasıyla; serbest eğri `tol/4` kiriş sapmasına kadar ikiye bölünerek örneklenir.
- `cam/turn_profile.py`: bağlama (ters kenar çevirme, ortak köşe, eksene çekme), açgözlü doğru + yay uydurma (ikili arama),
  birleştirme, yay içindeki uç noktalarda bölme, dış / iç profil, Gauss–Legendre Pappus denetimi.

## Açık sorular
_(yok)_ — Karar: dönel olmayan parça yüz numaralarıyla reddedilir; dönel zarf ileride ayrı SPEC.
Arayüz eki PR #53'te (`3fa6b5d`); bu dala merge edildi.
