# DURUM — SPEC 18 ozellik-agaci

Dal: `claude/spec-18-ozellik-agaci-ha61ak` · Oturum: bulut

## Sıradaki adım
SPEC metni kullanıcı onayı bekliyor (açık sorular S1–S5). Onaydan sonra `NotImplementedError` iskeleti; adlar A2
(`geometry/part.py` `FaceRef`, `Part.names`, `Part.find`) arayüz PR'ını bekler.

## Test durumu
| Tarih | Geçen | Kalan | Not |
|---|---|---|---|
| 2026-10-18 | — | — | Yalnız SPEC metni; kod ve test yok |

## Son oturum
**2026-10-18**
- SPEC 18 taslağı yazıldı: kararlı yüz referansı (doğuşta ad + OCCT geçmişiyle taşıma), döndürme, pah / yuvarlatma,
  doğrusal / dairesel desen, özellik ve gövde aynası, hata yalıtımı, önbellek, JSON.
- Analitik değerler OCCT'de ön denendi (yuvarlatma, pah, döndürme 360° / 90°, delik ağzı yuvarlatma, eş düzlemli füzyon).
- `geometry/revolve.py` SPEC 28'in; döndürme `geometry/dondur.py`'de.

## Açık sorular
- S1–S5: `specs/18-ozellik-agaci.md` "Açık sorular" bölümü.
