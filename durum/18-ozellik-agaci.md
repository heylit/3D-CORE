# DURUM — SPEC 18 ozellik-agaci

Dal: `claude/spec-18-ozellik-agaci-ha61ak` · Oturum: bulut

## Sıradaki adım
Kod yazıldı; A2 (`geometry/part.py` `FaceRef`, `Part.names`, `Part.find`, `Part.face_refs`) birleşince `main` dala
alınıp push edilecek. S2 (`SegLine.src` / `SegArc.src`, PR #90) dala merge edildi.

## Test durumu
| Tarih | Geçen | Kalan | Not |
|---|---|---|---|
| 2026-10-18 | — | — | Yalnız SPEC metni; kod ve test yok |
| 2026-10-18 | 95 / 95 SPEC 18 | 0 | A2 yerel geçici kopyasıyla; tüm paket 3278 geçti |

## Son oturum
**2026-10-18**
- SPEC 18 taslağı yazıldı: kararlı yüz referansı (doğuşta ad + OCCT geçmişiyle taşıma), döndürme, pah / yuvarlatma,
  doğrusal / dairesel desen, özellik ve gövde aynası, hata yalıtımı, önbellek, JSON.
- Analitik değerler OCCT'de ön denendi (yuvarlatma, pah, döndürme 360° / 90°, delik ağzı yuvarlatma, eş düzlemli füzyon).
- `geometry/revolve.py` SPEC 28'in; döndürme `geometry/dondur.py`'de.

- SPEC metni onaylandı (kullanıcı, 2026-10-18 11:13, yazılı toplu onay; S1–S5 önerilen seçenekler).
- `NotImplementedError` iskeleti: `geometry/agac.py`, `geometry/dondur.py`, `geometry/desen.py`. `FaceRef` A2 birleşene
  kadar yalnız `TYPE_CHECKING` altında import edilir.

- Testler (ayrı oturum, 99d999f) cherry-pick edildi. Kod: `geometry/agac.py` (ağaç, ad taşıma: OCCT
  Modified / IsDeleted + UnifySameDomain History; pah / yuvarlatma Generated), `geometry/dondur.py` (döndürme;
  yan yüzler orta noktanın aci/2 döndürülmüş hali ile eşlenir, çünkü OCCT `Generated` eksene dik doğrularda boş),
  `geometry/desen.py`.
- Delik özelliği SPEC 02 / 23 fonksiyonlarını çağırır; ad taşıma için kaldırılan malzeme R = eski − yeni geçmiş
  izli kesimle yeniden uygulanır, R yüzleri delik kaydına göre adlanır.
- Yüze bağlı eskiz düzleminde origin = yüzün ağırlık merkezi, xdir = dünya X'in izdüşümü (testlerin varsayımı,
  koordinatör kabul etti; SPEC 26 `face_plane` kuralı).

## Açık sorular
_(yok)_
