# DURUM — SPEC 06b cam-3d-ek (torik / konik takım, waterline)

Dal: `claude/project-thread-cvoyhj` · Oturum: bulut

## Sıradaki adım
Kod yazıldı; PR #45'te CI (pytest + kapı) yeşilse birleştirilir.

## Test durumu
| Tarih | Geçen | Kalan | Not |
|---|---|---|---|
| 2026-10-18 | tüm CAM + referans testleri (yavaşlar dahil) | 0 | Testler ayrı oturumda: 025b896, 058f6fd, f23f1cf (konik) |

## Son oturum
**2026-10-18**
- SPEC 06b taslağı yazıldı (`specs/06b-cam-3d-ek.md`).
- SPEC konik takımla birlikte onaylandı (kart "Konikle onayla" 10:24 UTC; kullanıcının yazılı onayı proje sohbetinde 10:38 UTC).
- Ek 1 onaylandı (kullanıcı, 11:13 UTC): K16 eğimli duvara, SPEC 06 `test_k14_seviyeler_ve_cl[duz]` torik `_big()`, K1 dışbükeylik denetimi kapsam dışı.
- İskelet: `cam/cutter.py`, `cam/waterline.py`, `cam/scallop.py` ekleri (`NotImplementedError`).
- Konik takım için `cam/model.py` arayüz eki önerildi (`ToolKind.CONE`, `Tool.tip_angle`); sahibi "CAM model arayüzü" thread'i.
- Kod: `cam/cutter.py` (doğru + yay parçalı profil, Legendre desteği, kapalı form `f_ters`, Minkowski ofseti),
  `cam/dropcutter.py` genel profil testi (köşe / yüz kapalı form, kenar altın oran; koni kenarı kapalı form),
  `girisim()` (z eşiğiyle kenar araması ve üçgen üst sınırıyla budama), `cam/ops3d.py` kabada tam ofset,
  `cam/scallop.py` `scallop_torus` / `scallop_cone`, `cam/waterline.py` lifler + örgü + uyarlamalı bölme.
- Hız: yarıküre (16 bin üçgen) koni waterline 637 sn → ~25 sn/seviye; pahalı yüklemde çok parçalı bölme yerine
  1e-10'a ikiye bölme, köşe aralığı içinde kalan üçgen budaması.

## Açık sorular
- Konik takım arayüz eki ayrı PR'da ("CAM model arayüzü" thread'i); bu dal `cam/model.py`'ye dokunmaz.
