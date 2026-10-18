# DURUM — SPEC 02 parca

Dal: `claude/project-thread-8dzgzc` · Oturum: bulut

## Sıradaki adım
PR'ın kullanıcı tarafından incelenip `main`'e birleştirilmesi; sonra DURUM.md'de 02-parca "tamamlandı" yapılır.

## Test durumu
| Tarih | Geçen | Kalan | Not |
|---|---|---|---|
| 2026-10-18 | 70 (tests/geometry) | 0 | 62 yeni SPEC 02 testi + 8 SPEC 00 testi; tüm depo 0 failed |

## Son oturum
**2026-10-18**
- SPEC kullanıcı tarafından onaylandı (proje sohbeti, 03:08 UTC).
- dogrulayici 62 test yazdı (K1–K9), yazici `geometry/features.py`, `props.py`, `mesh.py` dosyalarını uyguladı.
- `chamfer_top` üst yüzün (zmax, +Z normal) tüm kenarlarını pahlar: delik ve cep ağızları dahil.
- `tessellate` OCP `BRepMesh_IncrementalMesh(tol, açısal 0.5 rad)` kullanır; build123d'nin 0.1 rad varsayılanı tol'u etkisiz bırakıyordu.
- Köşe yarıçapı r = min(w, l)/2 olan cep kanal (SlotOverall) olarak kurulur.

## Açık sorular / notlar (sonraki SPEC'ler için)
- `hole` için depth = yükseklik boydan boya sayılır (SPEC sadece depth > yükseklik'i hata sayıyor).
- Eğri ya da çok parçalı üst yüz, çok gövdeli parçalar SPEC kapsamı dışında; `chamfer_top` tek katı ister.
- `read_stl` tutarsız yönlü (kapalı ama ters üçgenli) STL'yi onarmaz, hata verir.
