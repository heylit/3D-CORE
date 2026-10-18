# DURUM — projenin genel durumu

> Genel tablo. Her SPEC'in ayrıntılı durumu kendi dosyasında: `durum/NN-ad.md`.
> Bu dosya sadece bir PR `main`'e birleşirken ya da bir SPEC'e başlanırken, tek satır değiştirilerek güncellenir
> (kurallar: `BASLANGIC.md` bölüm 7). Sıra ve paralellik: `docs/yol-haritasi.md` → "Paralel çalışma: dalgalar".

## Açık dalga
**Dalga 2 sürüyor.** Tamamlanan: 05, 06, 07, 11, 14, 15, 16, 20, 23. Diğerleri bulut thread'lerinde (aşağıdaki tablo). Dalga 1 tamamlandı (01, 02, 03, 04, 08).

## SPEC tablosu
| SPEC | Dalga | Durum | Kimde (dal / oturum) | Ayrıntı |
|---|---|---|---|---|
| 00-arayuzler | 0 | tamamlandı (PR #1, `c633c87`) | — | `durum/00-arayuzler.md` |
| 01-bar | 1 | tamamlandı (PR #2, `a13574b`) | — | `durum/01-bar.md` |
| 02-parca | 1 | tamamlandı (PR #6, `a631d77`) | — | `durum/02-parca.md` |
| 03-cam-2d | 1 | tamamlandı (PR #5, `b22c7ad`); testler "bağımsız değil" işaretli, sıradaki 03b | — | — |
| 04-gcode | 1 | tamamlandı (PR #4, `32d2676`) | — | `durum/04-gcode.md` |
| 08-kisitlar | 1 | tamamlandı (PR #3, `46e7889`); ölçekli artıklar birleşti (PR #15, `b30f5a4`); ters başlangıç kaçışı birleşti (PR #16, `26fced4`) | — | `durum/08-kisitlar.md` |
| 00-arayuzler ek 2 | 2 | tamamlandı: Dalga 2 CAM arayüzü (PR #24, `9027a42`); `Hole` + havşa alanları (PR #23, `1fcf021`); `Node` (PR #26, `cfde521`); değer eşitliği (PR #29, `d460645`) | — | `durum/00-arayuzler.md` |
| 11-tet4 | 2 | tamamlandı (PR #21, `98b6623`) | — | `durum/11-tet4.md` |
| 15-goruntuleyici | 2 | tamamlandı (SPEC + testler PR #18, `149d292`; kod PR #25, `1ce40fb`) | — | `durum/15-goruntuleyici.md` |
| 16-teknik-resim | 2 | tamamlandı (PR #22, `778d29b`) | — | `durum/16-teknik-resim.md` |
| 07-montaj-agaci | 2 | tamamlandı (PR #20, `9c60f14`) | — | `durum/07-montaj-agaci.md` |
| 14-cam-kurulum | 2 | tamamlandı (PR #27, `d647fd8`) | — | `durum/14-cam-kurulum.md` |
| 06-cam-3d | 2 | tamamlandı (PR #31, `b19271d`) | — | `durum/06-cam-3d.md` |
| 23-parca-ek | 2 | tamamlandı (PR #28, `0bf3649`) | — | `durum/23-parca-ek.md` |
| 20-torna-yol | 2 | tamamlandı (PR #34, `25548e0`) | — | `durum/20-torna-yol.md` |
| 05-cam-sim | 2 | tamamlandı (PR #54, `4084c2d`) | — | `durum/05-cam-sim.md` |
| 24-tezgah | 3 | SPEC onaylı (PR #19, `97935da`); K3/K5/K6 SPEC 05'ten sonra yeniden onaylanacak | — | — |
| 17-kroki | 3 | SPEC onaylı; `sketch/model.py` arayüzü birleşti (PR #55, `fb99eb6`) | — | — |
| 09-girisim, 12-gmsh, 13-calculix (von Mises + CalculiX) | 3 | SPEC onaylı (2026-10-18 10:38) | — | — |
| 21-torna-gcode | 3 | bekliyor | — | — |
| 10-montaj-cam | 3 → 5 | Dalga 5'e alındı | — | — |
| 22-torna-sim | 4 | SPEC onaylı (2026-10-18 10:38) | — | — |
| 18-ozellik-agaci, 19-adaptif-kaba | 4 → 5 | Dalga 5'e alındı | — | — |
| 03b-cep-kalan-malzeme, 06b-cam-3d-ek, 25-tezgah-torna-montaj, 26-tezgah-modelleme, 27-ozellik-tanima, 28-torna-profili, 30-tezgah-profili, 31-sinumerik-heidenhain, 41-kinematik-3arti2, 42-bes-eksen-yol, 43-tri-dexel, 44-tezgah-carpisma | — | SPEC onaylı (2026-10-18 10:38); dalgası henüz atanmadı. | — | — |
| 29-islem-plani | — | SPEC metni onaylı ve birleşti (PR #58, `94989a3`); kod bekliyor | — | `durum/29-islem-plani.md` |
| Dalga 5: 4 arayüz PR'ı + 03c, 04b, 10, 18, 19, 32, 33, 34, 35, 36, 37, 38, 39, 40, 45, 46, 47 | 5 | kapsam onaylı (2026-10-18 10:51); SPEC metinleri yazılıyor | — | — |

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
| — | CI: CalculiX çapraz kontrolü her PR'da (PR #17) | 2026-10-18 | — |
| — | CI + bulut: pyvista (viz ekstrası), OSMesa ekransız çizim (PR #18) | 2026-10-18 | — |
| 24-tezgah | Tezgah web arayüzü SPEC'i onaylandı (PR #19) | 2026-10-18 | — |
| 00-arayuzler | `Hole` kaydı, `Part.holes`, havşa alanları (PR #23) | 2026-10-18 | — |
| 00-arayuzler | Ek 2: Dalga 2 CAM arayüzü, G-code yazıcı koruması (PR #24) | 2026-10-18 | — |
| 00-arayuzler | `assy.model.Node` montaj ağacı düğümü, SPEC 07 için (PR #26, `cfde521`) | 2026-10-18 | — |
| 00-arayuzler | `Hole`, `Component`, `Node` için değer eşitliği (numpy alanları dataclass `==`'i bozuyordu) (PR #29, `d460645`) | 2026-10-18 | — |
| 11-tet4 | 3B tetrahedron eleman, gerilme tensörü (PR #21) | 2026-10-18 | 58 |
| 15-goruntuleyici | pyvista geliştirici görüntüleyici (PR #18, #25) | 2026-10-18 | 41 |
| 16-teknik-resim | Teknik resim, DXF R12 / SVG (PR #22) | 2026-10-18 | 129 |
| 23-parca-ek | Parça ekleri: delikler, havşa, eğik delik, pah/radyus (PR #28) | 2026-10-18 | 127 |
| 07-montaj-agaci | Montaj ağacı (PR #20) | 2026-10-18 | 88 |
| 06-cam-3d | 3B takım yolu (PR #31) | 2026-10-18 | 157 |
| — | CI: test bağımsızlığı kapısı (PR #30, `45a73dc`) | 2026-10-18 | — |
| 00-arayuzler | `Tool.center_cutting` alanı (PR #36, `4d52e80`) | 2026-10-18 | — |
| — | CI: kapı testi, hook içinde asıl reponun index'ini bozmuyor (PR #38, `75ba846`) | 2026-10-18 | — |
| — | CI: LinuxCNC rs274 çapraz kontrolü Debian kapsayıcısında çalışıyor, web ekstrası kuruluyor (PR #47, `5383d2d`) | 2026-10-18 | — |
| 00-arayuzler | `LatheHolder`, `LatheTool.edge_len` / `holder` (SPEC 22 arayüzü) (PR #52, `47082f6`) | 2026-10-18 | 64 |
| 03-cam-2d, 04-gcode | CAM güvenliği: SPEC 03 Ek A (cep yan paso sınırı, merkezden kesme), SPEC 04 Ek C (güvenli Z, `stock_top`) (PR #33, `6eb07ec`) | 2026-10-18 | — |
| 14-cam-kurulum | Takım kütüphanesi ve iş kurulumu (PR #27) | 2026-10-18 | 220 |
| 05-cam-sim | Talaş simülasyonu: z-map, dexel, süre, çarpışma, oyma (PR #54) | 2026-10-18 | 175 |
| 17-kroki | `sketch/model.py` eskiz veri modeli arayüzü (PR #55, `fb99eb6`) | 2026-10-18 | 138 |
| — | CI: gmsh (mesh ekstrası) ve sistem kütüphaneleri kuruluyor (PR #57, `49a739f`) | 2026-10-18 | — |
| 20-torna-yol | Torna takım yolları: alın, çap, kaba, finiş, kanal, diş, uç radyusu telafisi (PR #34) | 2026-10-18 | 220 |

## Kurulum kontrol listesi (bir kez, kullanıcı)
- [x] `powershell -ExecutionPolicy Bypass -File _kurulum\yerlestir.ps1`
- [x] `.venv` oluşturuldu (uv, Python 3.14.7), `pip install -e ".[dev]"` yapıldı
- [x] `git init`, `core.hooksPath`, `--chmod=+x` (README "Git + GitHub")
- [x] GitHub private repo + ilk push (`c68fc5a`)
