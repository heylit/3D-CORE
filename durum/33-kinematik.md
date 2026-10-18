# DURUM — SPEC 33 Montaj kinematiği

Dal: `claude/spec-33-kinematik-m2o4g7` · Oturum: bulut

## Sıradaki adım
PR #72: CI (pytest + kapı) yeşilse birleştir.

## Test durumu
| Tarih | Geçen | Kalan | Not |
|---|---|---|---|
| 2026-10-18 | 122 (SPEC 33) | 0 | Bağımsız testler 9db425e (cherry-pick); `tests/assy` 841 geçti |

## Son oturum
**2026-10-18 — Kod**
- `assy/kinematik.py`: eklem artıkları + analitik Jacobian (dünya türevlerinden zincir kuralı), sürme kilitleri,
  SPEC 08 tarzı Gauss–Newton (L sabit, geri izleme, durağan noktadan kaçış), Kutzbach + rank serbestlik,
  sıfır uzayında geri izlemeli sürükleme ve aktif küme sınırları, devamlı süpürme, SPEC 09 `check` ile
  hareket boyunca çarpışma ve ikiye bölmeli ilk temas.

**2026-10-18 — İskelet**
- Kullanıcı SPEC metnini önerilerle onayladı (11:13, toplu onay).
- `assy/kinematik.py` `NotImplementedError` iskeleti; A1 arayüz dalı (`claude/arayuz-dalga2-0mc0ys`, 80fc6e9,
  PR #85) dala merge edildi, `Joint` doğrudan içe aktarılıyor.

**2026-10-18**
- `specs/33-kinematik.md` taslağı yazıldı (K1–K16). Analitik değerler (Freudenstein, dönen kol `θ*`) sayısal
  olarak kontrol edildi.

## Açık sorular
_(yok — önerilen varsayılanlar onaylandı)_
