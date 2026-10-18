# DURUM — projenin genel durumu

> Genel tablo. Her SPEC'in ayrıntılı durumu kendi dosyasında: `durum/NN-ad.md`.
> Bu dosya sadece bir PR `main`'e birleşirken ya da bir SPEC'e başlanırken, tek satır değiştirilerek güncellenir
> (kurallar: `BASLANGIC.md` bölüm 7). Sıra ve paralellik: `docs/yol-haritasi.md` → "Paralel çalışma: dalgalar".

## Açık dalga
**Dalga 0** — `00-arayuzler` (arayüzler + bulut/yerel ortak kurulum). Bitince Dalga 1'deki 5 SPEC aynı anda başlar.

## SPEC tablosu
| SPEC | Dalga | Durum | Kimde (dal / oturum) | Ayrıntı |
|---|---|---|---|---|
| 00-arayuzler | 0 | sırada | — | `durum/00-arayuzler.md` (açılınca) |
| 01-bar | 1 | SPEC + testler hazır, kod yok | — | `durum/01-bar.md` |
| 02-parca | 1 | SPEC yazılacak | — | — |
| 03-cam-2d | 1 | SPEC yazılacak | — | — |
| 04-gcode | 1 | SPEC yazılacak | — | — |
| 08-kisitlar | 1 | SPEC yazılacak | — | — |
| 05-cam-sim, 06-cam-3d, 07-montaj-agaci, 11-tet4 | 2 | bekliyor | — | — |
| 09-girisim, 10-montaj-cam, 12-gmsh, 13-calculix | 3 | bekliyor | — | — |

## Tamamlananlar
| SPEC | Konu | Tarih | Test sayısı |
|---|---|---|---|
| — | İskelet + yerel CI | 2026-10-18 | 12 (model) |
| — | Hedef CAM + montaj olarak güncellendi, paralel çalışma düzeni | 2026-10-18 | — |

## Kurulum kontrol listesi (bir kez, kullanıcı)
- [x] `powershell -ExecutionPolicy Bypass -File _kurulum\yerlestir.ps1`
- [x] `.venv` oluşturuldu (uv, Python 3.14.7), `pip install -e ".[dev]"` yapıldı
- [x] `git init`, `core.hooksPath`, `--chmod=+x` (README "Git + GitHub")
- [x] GitHub private repo + ilk push (`c68fc5a`)
