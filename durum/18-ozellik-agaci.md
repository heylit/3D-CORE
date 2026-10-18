# DURUM — SPEC 18 ozellik-agaci

Dal: `claude/spec-18-ozellik-agaci-ha61ak` · Oturum: bulut

## Sıradaki adım
İskelet push edildi; ayrı test oturumunun test commit'i cherry-pick edilecek, sonra kod ayrı commit'te. Adlar A2
(`geometry/part.py` `FaceRef`, `Part.names`, `Part.find`) ve S2 (`SegLine.src` / `SegArc.src`) arayüz PR'larını bekler.

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

- SPEC metni onaylandı (kullanıcı, 2026-10-18 11:13, yazılı toplu onay; S1–S5 önerilen seçenekler).
- `NotImplementedError` iskeleti: `geometry/agac.py`, `geometry/dondur.py`, `geometry/desen.py`. `FaceRef` A2 birleşene
  kadar yalnız `TYPE_CHECKING` altında import edilir.

## Açık sorular
_(yok)_
