# DURUM — projenin genel durumu

> Genel tablo. Her SPEC'in ayrıntılı durumu kendi dosyasında: `durum/NN-ad.md`.
> Bu dosya sadece bir PR `main`'e birleşirken ya da bir SPEC'e başlanırken, tek satır değiştirilerek güncellenir
> (kurallar: `BASLANGIC.md` bölüm 7). Sıra ve paralellik: `docs/yol-haritasi.md` → "Paralel çalışma: dalgalar".

## Açık dalga
**Dalga 2 tamamlandı** (05, 06, 07, 11, 14, 15, 16, 20, 23). **Dalga 3 tamamlandı** (09, 12, 13, 17, 21, 24, 27); 03b, 22, 26, 28, 30, 31, 41, 42, 43, 44 ve Dalga 5'ten 18, 32, 33, 34, 35, 36, 38, 40, 45, 46 tamamlandı (46'nın altın zinciri H1–H15 tamam); Dalga 5 arayüzleri (A0, A1a, A1b, A2) tamam. Dalga 5'in SPEC metinleri onaylandı. Dalga 1 tamamlandı (01, 02, 03, 04, 08).

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
| 24-tezgah | 3 | tamamlandı (PR #40, `0c6ee2b`) | — | `durum/24-tezgah.md` |
| 17-kroki | 3 | tamamlandı (arayüz PR #55, kod PR #39, `0e82c65`) | — | `durum/17-kroki.md` |
| 13-calculix | 3 | tamamlandı (PR #62, `5ad8c41`); delikli plaka ve L braket testleri SPEC 12 ile çalışıyor | — | `durum/13-calculix.md` |
| 09-girisim | 3 | tamamlandı (PR #43, `af45f60`) | — | `durum/09-girisim.md` |
| 12-gmsh | 3 | tamamlandı (PR #61, `df5d352`) | — | `durum/12-gmsh.md` |
| 21-torna-gcode | 3 | tamamlandı (PR #42, `11c7414`) | — | `durum/21-torna-gcode.md` |
| 27-ozellik-tanima | 3 | tamamlandı (PR #46, `8918a0a`) | — | `durum/27-ozellik-tanima.md` |
| 10-montaj-cam | 3 → 5 | Dalga 5'e alındı | — | — |
| 22-torna-sim | 4 | tamamlandı (PR #41, `835845e`) | — | `durum/22-torna-sim.md` |
| 18-ozellik-agaci | 4 → 5 | tamamlandı (PR #73, `304d8cd`) | — | `durum/18-ozellik-agaci.md` |
| 19-adaptif-kaba | 4 → 5 | Dalga 5'e alındı | — | — |
| 03b-cep-kalan-malzeme | — | tamamlandı (PR #49, `4e59efe`) | — | `durum/03b-cep-kalan-malzeme.md` |
| 28-torna-profili | 4 | tamamlandı (PR #56, `fba8875`) | — | `durum/28-torna-profili.md` |
| 30-tezgah-profili | — | tamamlandı (PR #50, `8d64ac4`; Ek A = SPEC 40 E2 dahil) | — | `durum/30-tezgah-profili.md` |
| 41-kinematik-3arti2 | — | tamamlandı (PR #51, `53db99f`) | — | `durum/41-kinematik-3arti2.md` |
| 36-montaj-sirasi | 5 | tamamlandı (PR #68, `cd25d0e`) | — | `durum/36-montaj-sirasi.md` |
| 45-modal | 5 | tamamlandı (PR #78, `977d0bc`) | — | `durum/45-modal.md` |
| 35-standart-parca | 5 | tamamlandı (PR #82, `8fb636c`) | — | `durum/35-standart-parca.md` |
| 46-uctan-uca | 5 | tamamlandı: H1–H15 etkin ve yeşil, K18 karşılandı (PR #83, #104, #117 `cce9c56`); yalnız H5'in rs274 testi CI'da atlanıyor | — | `durum/46-uctan-uca.md` |
| 32-kuvvet | 5 | tamamlandı (PR #66, `40fc7c4`) | — | `durum/32-kuvvet.md` |
| 40-torna-ek | 5 | tamamlandı (PR #75, `eefa134`) | — | `durum/40-torna-ek.md` |
| 38-is-foyu | 5 | tamamlandı (PR #69, `4066ee9`); K10 (SPEC 29 uyarlayıcısı) `cam.plan` gelince çalışır | — | `durum/38-is-foyu.md` |
| 33-kinematik | 5 | tamamlandı (PR #72, `d2c581c`) | — | `durum/33-kinematik.md` |
| 34-tolerans | 5 | tamamlandı (PR #65, `6faa048`) | — | `durum/34-tolerans.md` |
| 06b-cam-3d-ek, 25-tezgah-torna-montaj | — | SPEC onaylı (2026-10-18 10:38); dalgası henüz atanmadı. | — | — |
| 26-tezgah-modelleme | — | tamamlandı (PR #92, `87d35b8`) | — | `durum/26-tezgah-modelleme.md` |
| 31-sinumerik-heidenhain | — | tamamlandı (PR #102, `35267e0`; SPEC 30 Ek B dahil) | — | `durum/31-sinumerik-heidenhain.md` |
| 42-bes-eksen-yol | — | tamamlandı (PR #97, `3c6b5c3`; Ek A dahil) | — | `durum/42-bes-eksen-yol.md` |
| 43-tri-dexel | — | tamamlandı (PR #96, `e0bf13f`) | — | `durum/43-tri-dexel.md` |
| 44-tezgah-carpisma | — | tamamlandı (PR #100, `695ea76`) | — | `durum/44-tezgah-carpisma.md` |
| 29-islem-plani | — | SPEC metni onaylı ve birleşti (PR #58, `94989a3`); kod bekliyor | — | `durum/29-islem-plani.md` |
| Dalga 5: 4 arayüz PR'ı + 03c, 04b, 10, 18, 19, 32, 33, 34, 35, 36, 37, 38, 39, 40, 45, 46, 47 | 5 | kapsam onaylı (2026-10-18 10:51); SPEC metinleri onaylı (35 ve 46 ~11:16, diğerleri 11:13) | — | — |

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
| 00-arayuzler | `Part.moved/common/cut/fuse/distance` (SPEC 09), `AxialSection` + `Part.axial_section` (SPEC 28) (PR #53, `7545395`) | 2026-10-18 | — |
| 24-tezgah | Tezgah web arayüzü: Python köprüsü, sunucu, three.js (PR #40) | 2026-10-18 | 87 (Python) + TypeScript |
| 13-calculix | von Mises, asal ve düğüm gerilmeleri, CalculiX .inp yazıcı (PR #62) | 2026-10-18 | 79 |
| 21-torna-gcode | Fanuc torna G-code yazıcı ve okuyucu (PR #42) | 2026-10-18 | 120 |
| 09-girisim | Boolean API, montaj girişim / temas / boşluk kontrolü (PR #43) | 2026-10-18 | 84 |
| 12-gmsh | `Part`'tan gmsh ile tet4 ağı, sınır seçimi, tutarlı yükler (PR #61) | 2026-10-18 | 87 |
| 27-ozellik-tanima | Özellik tanıma (PR #46) | 2026-10-18 | 52 |
| 17-kroki | Kısıt artıkları, Gauss-Newton çözücü, bölgeler (PR #39) | 2026-10-18 | 72 |
| 03b-cep-kalan-malzeme | Kalan malzeme kontrollü cep (PR #49) | 2026-10-18 | 123 |
| 00-arayuzler | Koni takım, tezgâh profili ve çok eksen arayüz ekleri (PR #60, `65381cf`) | 2026-10-18 | 272 |
| 47-tezgah-ekranlari | SPEC metni onaylandı (PR #74, `6b043ca`) | 2026-10-18 | — |
| 47-tezgah-ekranlari | K10 düzeltmesi (PR #106, `231faf3`) | 2026-10-18 | — |
| — | `pyproject.toml`: `atolye*` ve `analiz*` paketleri (PR #80, `b62c3a7`) | 2026-10-18 | — |
| 28-torna-profili | Katıdan torna profili (PR #56, `fba8875`) | 2026-10-18 | 67 |
| 30-tezgah-profili | Tezgâh profilleri, sınır denetimi, GRBL/Fanuc/Haas postprosesörleri (PR #50) | 2026-10-18 | 177 |
| 41-kinematik-3arti2 | Tezgâh kinematiği ve 3+2 indeksli işleme (PR #51) | 2026-10-18 | 42 |
| 36-montaj-sirasi | Montaj sırası ve demontaj yolu (PR #68) | 2026-10-18 | 119 |
| 00-arayuzler | Dalga 5 A1: tolerans ve eklem arayüzü, `assy/model.py` (PR #85, `2929f2a`) | 2026-10-18 | 134 |
| 45-modal | Modal analiz ve kesme kuvveti altında sehim, `core/modal.py` + `analiz/` (PR #78) | 2026-10-18 | 139 |
| 35-standart-parca | Standart parça kütüphanesi ve otomatik bağlantı önerisi (PR #82) | 2026-10-18 | 177 |
| 46-uctan-uca | Uçtan uca altın senaryo: flanş + mil (PR #83); H1–H9, H12, H13, H15 etkin | 2026-10-18 | 42 |
| 00-arayuzler | Dalga 5 A2: yüz referansı arayüzü (PR #99, `38bf070`); A1a, A1b, A2 tamam | 2026-10-18 | 43 |
| 04b (30 tarafı) | SPEC 04b için postprosesör blokları, `cam/post/` (PR #98, `01fe3ac`) | 2026-10-18 | — |
| 22-torna-sim | Torna talaş simülasyonu, K1–K19 (PR #41) | 2026-10-18 | 173 |
| 40-torna-ek | Torna ekleri: eksenel delme ve punta, ters bağlama, profilli kanal (PR #75) | 2026-10-18 | 172 |
| 38-is-foyu | İş föyü, `atolye/` (PR #69) | 2026-10-18 | 106 |
| 33-kinematik | Montaj kinematiği (PR #72) | 2026-10-18 | 122 |
| 00-arayuzler | Dalga 5 A0: CAM arayüzü Ek 3, `cam/model.py` (PR #107, `ea5a52d`) | 2026-10-18 | 299 |
| 31-sinumerik-heidenhain | Sinumerik ve Heidenhain diyalektleri, SPEC 30 Ek B (PR #102) | 2026-10-18 | 101 |
| 43-tri-dexel | Tri-dexel talaş simülasyonu (PR #96) | 2026-10-18 | 86 |
| 44-tezgah-carpisma | Tezgâh çarpışma denetimi (PR #100) | 2026-10-18 | 78 |
| 26-tezgah-modelleme | Tezgah modelleme ekranı (PR #92) | 2026-10-18 | 246 |
| 18-ozellik-agaci | Özellik ağacı (PR #73) | 2026-10-18 | 95 |
| 34-tolerans | Tolerans zinciri, `assy/tolerans.py` (PR #65) | 2026-10-18 | 73 |
| 46-uctan-uca | H10 halkası; zincir H1–H10, H12, H13, H15 (PR #104, `6507198`) | 2026-10-18 | 5 |
| 20-torna-yol | Uç kapağı düzeltmesi (PR #108, `318fd61`) | 2026-10-18 | — |
| — | CI: ubuntu-latest, belge PR'larında pytest yeşil raporu (PR #110, `7b80c58`) | 2026-10-18 | — |
| 00-arayuzler | `MachineProfile.to_dict` boş iş mili alanlarını yazmıyor; main yeniden yeşil (PR #113, `f1990eb`) | 2026-10-18 | — |
| — | CI: iş zaman aşımı 25 dakika (PR #115, `41dea4f`) | 2026-10-18 | — |
| 21-torna-gcode | E3 eki (SPEC 40) (PR #88, `36a779f`) | 2026-10-18 | 47 |
| 35-standart-parca | K12 düzeltmesi (PR #103, `23b6606`) | 2026-10-18 | — |
| 32-kuvvet | Kesme kuvveti (PR #66) | 2026-10-18 | 154 |
| 42-bes-eksen-yol | Beş eksen takım yolu, Ek A (PR #97) | 2026-10-18 | 60 |
| 46-uctan-uca | H11 + H14; altın zincir H1–H15 tamam (PR #117) | 2026-10-18 | 11 |
| — | `pyproject.toml`: `malzeme*`, `ruff==0.17.1`, ruff `known-first-party` (PR #123, `a4a4611`) | 2026-10-18 | — |
| 05-cam-sim | Talaş simülasyonu: z-map, dexel, süre, çarpışma, oyma (PR #54) | 2026-10-18 | 175 |
| 17-kroki | `sketch/model.py` eskiz veri modeli arayüzü (PR #55, `fb99eb6`) | 2026-10-18 | 138 |
| — | CI: gmsh (mesh ekstrası) ve sistem kütüphaneleri kuruluyor (PR #57, `49a739f`) | 2026-10-18 | — |
| 20-torna-yol | Torna takım yolları: alın, çap, kaba, finiş, kanal, diş, uç radyusu telafisi (PR #34) | 2026-10-18 | 220 |

## Kurulum kontrol listesi (bir kez, kullanıcı)
- [x] `powershell -ExecutionPolicy Bypass -File _kurulum\yerlestir.ps1`
- [x] `.venv` oluşturuldu (uv, Python 3.14.7), `pip install -e ".[dev]"` yapıldı
- [x] `git init`, `core.hooksPath`, `--chmod=+x` (README "Git + GitHub")
- [x] GitHub private repo + ilk push (`c68fc5a`)
