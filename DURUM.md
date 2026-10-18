# DURUM — projenin genel durumu

> Genel tablo. Her SPEC'in ayrıntılı durumu kendi dosyasında: `durum/NN-ad.md`.
> Bu dosya sadece bir PR `main`'e birleşirken ya da bir SPEC'e başlanırken, tek satır değiştirilerek güncellenir
> (kurallar: `BASLANGIC.md` bölüm 7). Sıra ve paralellik: `docs/yol-haritasi.md` → "Paralel çalışma: dalgalar".

## Açık dalga
**Dalga 1 tamamlandı** (01, 02, 03, 04, 08). Sıradaki: **Dalga 2** (SPEC listesi PR #8 ile `docs/yol-haritasi.md`'de; başlatma kararı kullanıcıda).

## SPEC tablosu
| SPEC | Dalga | Durum | Kimde (dal / oturum) | Ayrıntı |
|---|---|---|---|---|
| 00-arayuzler | 0 | tamamlandı (PR #1, `c633c87`) | — | `durum/00-arayuzler.md` |
| 01-bar | 1 | tamamlandı (PR #2, `a13574b`) | — | `durum/01-bar.md` |
| 02-parca | 1 | tamamlandı (PR #6, `a631d77`) | — | `durum/02-parca.md` |
| 03-cam-2d | 1 | tamamlandı (PR #5, `b22c7ad`); testler "bağımsız değil" işaretli, sıradaki 03b | — | — |
| 04-gcode | 1 | tamamlandı (PR #4, `32d2676`) | — | `durum/04-gcode.md` |
| 08-kisitlar | 1 | tamamlandı (PR #3, `46e7889`); ölçekli artıklar birleşti (PR #15, `b30f5a4`); ters başlangıç kaçışı birleşti (PR #16, `26fced4`) | — | `durum/08-kisitlar.md` |
| 05-cam-sim, 06-cam-3d, 07-montaj-agaci, 11-tet4, 14-cam-kurulum, 15-goruntuleyici, 16-teknik-resim, 20-torna-yol, 23-parca-ek | 2 | bekliyor | — | — |
| 09-girisim, 10-montaj-cam, 12-gmsh, 13-calculix, 17-kroki, 21-torna-gcode | 3 | bekliyor | — | — |
| 18-ozellik-agaci, 19-adaptif-kaba, 22-torna-sim | 4 | bekliyor | — | — |

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
| 03-cam-2d | 2.5D takım yolu (PR #5) | 2026-10-18 | — |
| — | Test altyapısı ve `ruff format` zorunluluğu (PR #9, #14) | 2026-10-18 | — |
| 04-gcode | G-code tezgâh güvenliği, inceleme K1–K3 (PR #11) | 2026-10-18 | — |
| 00-arayuzler | Sonlu değer kontrolleri, `Mate.flip` (PR #12) | 2026-10-18 | — |
| — | Bağımsız çapraz kontrol, inceleme Y1 (PR #13) | 2026-10-18 | — |
| 08-kisitlar | Ölçekli artıklar (PR #15) | 2026-10-18 | — |
| 08-kisitlar | Ters başlangıç kaçışı (PR #16) | 2026-10-18 | — |

## Kurulum kontrol listesi (bir kez, kullanıcı)
- [x] `powershell -ExecutionPolicy Bypass -File _kurulum\yerlestir.ps1`
- [x] `.venv` oluşturuldu (uv, Python 3.14.7), `pip install -e ".[dev]"` yapıldı
- [x] `git init`, `core.hooksPath`, `--chmod=+x` (README "Git + GitHub")
- [x] GitHub private repo + ilk push (`c68fc5a`)
