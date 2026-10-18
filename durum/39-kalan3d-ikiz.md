# DURUM — SPEC 39 3B kalan malzeme ve işlenmiş parça ikizi

Dal: `claude/spec-39-kalan3d-yrv7su` · Oturum: bulut

## Sıradaki adım
06b `Cutter` kodu birleşince onu merge edip kalan 3 testi (torik ve konik) yeşile çekmek, sonra PR'ı birleştirmek.

## Test durumu
| Tarih | Geçen | Kalan | Not |
|---|---|---|---|
| 2026-10-18 | — | — | Sadece SPEC taslağı; kod ve test yok. |
| 2026-10-18 | 83 SPEC 39 (slow ve OCCT dahil) | 3 uygulanmamış | Kalan 3 test 06b `Cutter`'ı bekliyor (torik K8, konik K3 ve K8). |

## Son oturum
**2026-10-18 — kod**
- Bağımsız test commit'i a972402 cherry-pick edildi; test dosyalarına dokunulmadı. main merge edildi (CONE arayüzü).
- `cam/kalan3d.py`: kalınlık, 8 komşulu bölgeler (scipy.ndimage), girme derinliği ve süzgeç SPEC 05'in kiriş, alt adım ve
  zarf adımlarıyla (süzülmüş yolun simülasyonu süzgeç durumunu birebir verir); konik takımda 06b `Cutter` profiliyle altın oran zarfı.
- `cam/sim/ikiz.py`: kolon ağı (köşe doğrularında kırılma yükseklikleriyle bölünmüş duvarlar, fermuar üçgenleme), yüzey ağı,
  ikili STL, Ericson en yakın nokta ile vektörel nokta–ağ uzaklığı, sapma haritası.

**2026-10-18 — onay ve iskelet**
- SPEC onaylandı (11:13 UTC toplu yazılı onay, önerilerle). 06b iskelet dalı ve main merge edildi.
- `cam/kalan3d.py`, `cam/sim/ikiz.py` `NotImplementedError` iskeleti.

**2026-10-18 — SPEC**
- `specs/39-kalan3d-ikiz.md` taslağı: düşey kalan kalınlık ve 8 komşulu bölgeler; 05 zarfıyla (06b `Cutter`
  profiliyle genel) girme derinliği; sıralı kalan malzeme süzgeci (`0 ≤ z_süzülmüş − z_tam ≤ t_min` kanıtıyla);
  06 `finish` / `rough` üstüne `rest_finish` / `rest_rough`; kesin hacimli kolon ağı, görüntü için yüzey ağı,
  ikili STL; 3B nokta–ağ uzaklığıyla işaretli sapma haritası.
- `cam/model.py` eki gerekmiyor.

## Açık sorular
_(yok; öneriler onaylandı)_
