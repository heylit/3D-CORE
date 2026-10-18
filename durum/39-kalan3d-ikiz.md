# DURUM — SPEC 39 3B kalan malzeme ve işlenmiş parça ikizi

Dal: `claude/spec-39-kalan3d-yrv7su` · Oturum: bulut

## Sıradaki adım
Ayrı test thread'inin test commit'ini cherry-pick etmek, sonra kodu ayrı commit'te yazmak.

## Test durumu
| Tarih | Geçen | Kalan | Not |
|---|---|---|---|
| 2026-10-18 | — | — | Sadece SPEC taslağı; kod ve test yok. |

## Son oturum
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
