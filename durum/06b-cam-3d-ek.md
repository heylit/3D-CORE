# DURUM — SPEC 06b cam-3d-ek (torik / konik takım, waterline)

Dal: `claude/project-thread-cvoyhj` · Oturum: bulut

## Sıradaki adım
Testleri ayrı oturum yazar (iskelet push edildi); test commit'i cherry-pick edilince kod ayrı commit'te. Konik kısım `ToolKind.CONE` / `Tool.tip_angle` arayüz PR'ı birleşince.

## Test durumu
| Tarih | Geçen | Kalan | Not |
|---|---|---|---|

## Son oturum
**2026-10-18**
- SPEC 06b taslağı yazıldı (`specs/06b-cam-3d-ek.md`).
- SPEC konik takımla birlikte onaylandı (kart "Konikle onayla" 10:24 UTC; kullanıcının yazılı onayı proje sohbetinde 10:38 UTC).
- İskelet: `cam/cutter.py`, `cam/waterline.py`, `cam/scallop.py` ekleri (`NotImplementedError`).
- Konik takım için `cam/model.py` arayüz eki önerildi (`ToolKind.CONE`, `Tool.tip_angle`); sahibi "CAM model arayüzü" thread'i.

## Açık sorular
- Konik takım arayüz eki ayrı PR'da ("CAM model arayüzü" thread'i); bu dal `cam/model.py`'ye dokunmaz.
