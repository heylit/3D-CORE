# DURUM — projenin genel durumu

> Genel tablo. Her SPEC'in ayrıntılı durumu kendi dosyasında: `durum/NN-ad.md`.
> Bu dosya sadece bir PR `main`'e birleşirken ya da bir SPEC'e başlanırken, tek satır değiştirilerek güncellenir
> (kurallar: `BASLANGIC.md` bölüm 7). Sıra ve paralellik: `docs/yol-haritasi.md` → "Paralel çalışma: dalgalar".

## Açık dalga
**Dalga 1** — 01, 02, 04, 08 tamamlandı; 03-cam-2d sürüyor.

## SPEC tablosu
| SPEC | Dalga | Durum | Kimde (dal / oturum) | Ayrıntı |
|---|---|---|---|---|
| 00-arayuzler | 0 | tamamlandı (PR #1, `c633c87`) | — | `durum/00-arayuzler.md` |
| 01-bar | 1 | tamamlandı (PR #2, `a13574b`) | — | `durum/01-bar.md` |
| 02-parca | 1 | tamamlandı (PR #6, `a631d77`) | — | `durum/02-parca.md` |
| 03-cam-2d | 1 | SPEC yazılacak | — | — |
| 04-gcode | 1 | tamamlandı (PR #4, `32d2676`) | — | `durum/04-gcode.md` |
| 08-kisitlar | 1 | tamamlandı (PR #3, `46e7889`) | — | `durum/08-kisitlar.md` |
| 05-cam-sim, 06-cam-3d, 07-montaj-agaci, 11-tet4 | 2 | bekliyor | — | — |
| 09-girisim, 10-montaj-cam, 12-gmsh, 13-calculix | 3 | bekliyor | — | — |

## Tamamlananlar
| SPEC | Konu | Tarih | Test sayısı |
|---|---|---|---|
| — | İskelet + yerel CI | 2026-10-18 | 12 (model) |
| — | Hedef CAM + montaj olarak güncellendi, paralel çalışma düzeni | 2026-10-18 | — |
| 00-arayuzler | cam/assy/geometry arayüzleri, ortak kurulum | 2026-10-18 | — |
| 01-bar | 1D çubuk elemanı, doğrusal statik çözücü | 2026-10-18 | 117 |
| 08-kisitlar | Montaj kısıtları, konum çözücü | 2026-10-18 | 245 |
| 02-parca | Katı parça özellikleri, kütle özellikleri, STL | 2026-10-18 | 62 |
| 04-gcode | G-code yazıcı/okuyucu, G81/G83 | 2026-10-18 | 142 |

## Kurulum kontrol listesi (bir kez, kullanıcı)
- [x] `powershell -ExecutionPolicy Bypass -File _kurulum\yerlestir.ps1`
- [x] `.venv` oluşturuldu (uv, Python 3.14.7), `pip install -e ".[dev]"` yapıldı
- [x] `git init`, `core.hooksPath`, `--chmod=+x` (README "Git + GitHub")
- [x] GitHub private repo + ilk push (`c68fc5a`)
