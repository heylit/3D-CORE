# 3D-CORE — Devam belgesi (durdurma: 2026-10-18 19:08, yedek: 2026-10-21)

Bu belge, sadece GitHub erişimi olan birinin (başka bilgisayar, yeni oturum) işi kaldığı yerden
sürdürebilmesi için yazıldı. Proje **duraklatılmış** durumda: kullanıcı "devam" diyene kadar yeni iş,
birleştirme veya röle yapılmaz.

Repo: https://github.com/heylit/3D-CORE · Sahibi: Mustafa (`heylit`) · Kullanıcıyla dil: **Türkçe**.
Bu klasör `main` a138b7c üstünden açılmış `claude/yedek-durdurma-tck6s4` dalındadır; **birleştirilmez**.

---

## 0. Önce bunu bil: GitHub Actions bozuk

- 2026-10-18 ~19:35'ten beri her kontrol (`testler`, `bagimsizlik`) 1–3 saniyede `failure` ile bitiyor,
  runner atanmıyor (runner_id 0), loglar 404. Son çalışma 2026-10-18 19:54 (#48). Bu, kod hatası değil.
- Etkilenen PR'lar: #120, #126, #141, #144, #147, #148, #157, #149, #48 (ve sonrasında açılan her şey, bu yedek PR dahil).
- **Devam ederken ilk adım:** tek bir PR'da CI'ı yeniden çalıştır (ör. #135). Hâlâ 1–2 sn'de düşüyorsa
  kullanıcıdan GitHub → Settings → Actions ve Billing/dakika kotasını kontrol etmesini iste.
- **Asla self-hosted runner kullanma.** Repo PUBLIC, GitHub bulut runner'ları kullanılır.

## 1. Bu klasörde ne var (hepsi `git apply --check` / `git bundle verify` ile 2026-10-21'de denetlendi)

`.py` dosyaları ruff/pytest bu klasörü taramasın diye **`.py.txt`** uzantısıyla kaydedildi;
kullanmadan önce `.txt`'yi at. Aynı nedenle (ruff format, içindeki Python kod bloklarını yeniden biçimlendirmek istiyor) 13 SPEC taslağı
`.md.txt` olarak duruyor; içerikleri proje klasöründekilerle bayt bayt aynı. Bütünlük için `SHA256SUMS` (orijinal adlarla değil, bu klasördeki adlarla).

| Dosya | Ait olduğu dal / uç | Denetim | Ne işe yarar |
|---|---|---|---|
| `bekleyen/spec-69/dal.bundle` | HEAD 4171a55 (= #140 ucu 6ee8a46 + `main` a138b7c birleştirmesi) | verify OK | 69 kodlayıcının push edilmemiş yerel dalı |
| `bekleyen/spec-69/yerel-degisiklikler.patch` | `claude/project-thread-fe0oon` 6ee8a46 ve bundle HEAD 4171a55 | apply OK (ikisinde de) | `assy/dinamik.py`, `durum/69`, `specs/08` errata (onay bekler, §4) |
| `bekleyen/spec-69/dinamik.py.txt`, `69-mekanizma-dinamigi.md` | — | — | aynı işin düz dosya kopyası ve durum notu |
| `bekleyen/spec-68c/68c-kod.patch` | #148 `claude/spec-45-modal-xigwto` a50eb80 | apply OK | `core/harmonik.py`, `fileio/calculix.py` (K5 = CalculiX yazıcı denetimi) |
| `taslak/spec47a-kod/47a-dal.bundle` | HEAD 7ad7a8f (= #87 ucu cf26455 + `main` birleştirmesi) | verify OK | 47a kodlayıcının push edilmemiş 7ad7a8f'si (GitHub'da YOK) |
| `taslak/spec47a-kod/47a-kod.patch` | #87 cf26455 ve 7ad7a8f | apply OK (ikisinde de) | 47a Plan ekranı kodu |
| `birlesme/47a-test-cozumu/` | cf26455 + `main` birleştirmesinin test çakışma çözümü | (tam dosya, patch değil) | `NOT.md` ne yapılacağını yazar |
| `spec-taslak/dalga-7/65a-kod.patch` | #144 `claude/project-thread-8dzgzc` 9ec24fc ve test dalı `qqxkwb` 6caace9 | apply OK (ikisinde de) | 65a serbest yüzey kodu |
| `tezgah-kanca/gonder-ucu-kodu.patch` | `claude/project-thread-c0lzh0` c4d516a | apply OK | Tezgah DNC gönder ucu |
| `tezgah-kanca/kanca-ve-gonder.bundle` | ref `kabuk-komut-kancasi` 1326921 | verify OK; zaten c0lzh0 içinde | sadece güvenlik kopyası |
| `spec-62-asama2-taslak/` | #157 f7b8e12 iskeletinin gövde taslakları | — | 62 aşama 2a gövdeleri |
| `arayuz/61-k11-kod-taslak.py.txt` | #155 c6a8dc6 | — | 61 K11 DFM ucu kod taslağı |
| `dnc-63/` | #130 sonrası K8 | — | Tezgah gönder ucu tasarımı + test taslağı |
| `spec-taslak/` | — | — | Dalga 6/7 SPEC taslakları, `takim-kutuphanesi.md` (§13 durdurma notu) |
| `yol-haritasi/` | — | — | yol haritası planları |
| `durdurma/2026-10-18.md` | — | — | durdurma defteri (bazı satırları bu belgeden eski; çelişirse bu belge geçerli) |

Bir bundle'ı kullanmak: `git fetch yedek/2026-10-18/bekleyen/spec-69/dal.bundle HEAD:refs/heads/yedek-69`.
Bir patch'i kullanmak: ilgili dalı checkout et, `git apply --check <patch>` sonra `git apply <patch>`.

**Kaydedilemeyen:** `2d64ca2` (SPEC 54 test thread'inin A0 #146 için hazırladığı durumlar 11/11b xfail kaldırma
commit'i) hiçbir yerde yok: ne GitHub'da ne proje klasöründe. Yeniden yazılması gerekir (§3, A0).

## 2. Çalışma kuralları (özet; tam metin `CLAUDE.md`, `BASLANGIC.md`)

- Testsiz kod yok; benchmark tutmuyorsa hata koddadır; testi değiştirerek geçirme. Birimler N–mm–MPa. Sessiz hata yok (`ModelError`).
- Bir SPEC = bir dal = bir PR. Paketler birbirini yalnız `*/model.py` üzerinden kullanır. Arayüz değişikliği = ayrı küçük PR + kullanıcı onayı.
- Ortak dosyalar (`*/model.py`, `pyproject.toml`, `.github/`, `CLAUDE.md`, `BASLANGIC.md`, `DURUM.md`) SPEC PR'ında değişmez; sahipleri:
  DURUM thread → DURUM.md/BASLANGIC.md/pyproject; CI thread → `.github/workflows`; A0 → `cam/model.py`; post thread → `cam/post/`;
  Tezgah thread → `tezgah/`; SPEC 54 thread → `docs/yol-haritasi.md`, SPEC 17/26; SPEC 55 → `.gitattributes`.
  68a/68b/68c ortak `core/elements/__init__.py` ve `analiz/__init__.py`'ye dokunur; sonra birleşen çakışmayı çözer.
- **Test bağımsızlığı:** testler ve kod ayrı oturumlarda, ayrı commit'lerde. Test commit'i cherry-pick edilir (squash yok, `Claude-Session:` izi korunur).
  Kodlayıcı test dosyasına dokunmaz (biçim dahil); test hatası test thread'ine geri gider. İstisna etiketi `bagimsizlik-istisnasi`'ni yalnız depo sahibi ekler.
- **Kırmızı test kilidi deseni:** test thread'i yeni testleri `xfail(strict=True)` işaretler → kodlayıcı kodu commit'ler →
  test thread'i kodlayıcının ucunda işaret kaldırma commit'i yazar → kodlayıcı cherry-pick eder. Hook kırmızıyken kod commit edilemiyorsa patch olarak saklanır.
- Hook'lar kapıdır (pre-commit: ruff + hızlı testler; pre-push: ruff + tüm testler, ~23–31 dk). **`--no-verify` asla.**
- PR açmadan önce `main` dala **merge** edilir (rebase/force-push yok). `main`'i alan dal I001 verirse bir kez `ruff check --fix`.
- Birleştirme koşulu: GitHub'da `pytest` + `kapi` yeşil. `pytest-windows` zorunlu değil (main'de SPEC 19 ada_45 yüzünden kırmızı).
- `.github/workflows/test.yml`'e tetikleyici/OS/Python sürümü eklenmez (dakika maliyeti).
- Gerçek şirket parçası/müşteri verisi repoya girmez (`yerel_parcalar/` gitignore'da).
- Her thread yalnız kendi dalına push eder; test dallarından otomatik açılan PR'lar kapatılır. Yer tutucu metin gönderilmez.
- Kullanıcı onayı: SPEC METNİ değişiklikleri ve `main`'i dala almak/PR birleştirmek için kullanıcının **kendi yazdığı cümle** gerekir;
  "2 dk içinde yanıt yoksa öneriyi kabul et" kuralından türetilen onay izin denetiminde reddediliyor. Hesap/fatura/GitHub ayarı engelleri bu kurala girmez.
- Kullanıcıya durum raporunda süre tahmini verme; neyi beklediğini yaz. Karar soruları proje sohbetinden sorulur.

## 3. Açık PR'lar (2026-10-21 itibarıyla uçlar)

| PR | SPEC | Dal | Uç | Ne bekliyor |
|---|---|---|---|---|
| #135 | 64 MES | `claude/project-thread-nkn98y` | da80d7a | **Hazırdı (yeşil)** → birleştir. Sonra 58 birleşince süre/maliyet uçları |
| #130 | 63 DNC | `claude/spec-38-is-foyu-y2a9bm` | c77be2c | **Hazırdı** → birleştir. Sonra Tezgah gönder ucu (§5 adım 6) |
| #150 | B1 / 37 | `claude/spec-37-proje-kabuk-trviuv` | af66da3 | **Hazırdı** → birleştir. Sonra küçük düzeltme: `_yukle` `Proje.goc/kaynak_yol` düşürüyor |
| #122 | 67a tet10 | `claude/spec-11-tet4-cvi89m` | 32e5d24 | **Hazırdı** → birleştir. 67b, 68a(aşama 2), 68b, 68c(K6), 68d(K7), 70 buna bağlı |
| #153 | numba | `claude/project-thread-22g6kz` | c1b5960 | **Hazırdı** → birleştir; merge hash'i 53 kodlayıcıya |
| #132 | 57 | `claude/project-thread-ysr96h` | ac193da | GitHub CI yeşil olunca birleştir |
| #129 | 50 | `claude/project-thread-w648u9` | cd1ae56 | CI yeşil olunca birleştir (pytest-windows kırmızısına bakılacak, zorunlu değil) |
| #119 | 52 | `claude/project-thread-012y8t` | 713ac2a | CI yeşil olunca birleştir |
| #118 | 56 | `claude/project-thread-67phxl` | 2cf72c8 | CI yeşil olunca birleştir |
| #143 | 72 çevrim süresi | `claude/project-thread-pzzbar` | 9e8f995 | CI yeşil olunca birleştir. 58 ve 62 (aşama 2b) bunu bekler |
| #126 | 49 freze-torna | `claude/project-thread-k667wt` | 7ce0422 | CI yeşil olunca birleştir. Sonra SPEC 48 kuru koşu (M13/M15, G12.1 X çap) |
| #156 | 54 test Windows düzeltmesi | `claude/project-thread-hvc38g` | 46e99cd | CI yeşil olunca birleştir |
| #120 | 53 performans | `claude/spec-05-cam-sim-ch33p2` | 002b31b | #153 birleşsin; 53 test thread'i B2 xfail'ini 002b31b üstünde kaldırır |
| #140 | 69 mekanizma dinamiği | `claude/project-thread-fe0oon` | 6ee8a46 | Kod push edilmedi → §1 bundle/patch. K7 testleri: `claude/project-thread-71up4b` fa936bc (+87a71b6) kodlayıcıya. `specs/08` errata kullanıcı onayı |
| #87 | 47a Plan ekranı | `claude/spec-47-tezgah-ekranlari-59jujx` | cf26455 | Kodlayıcı 7ad7a8f'i (bundle'da) push eder → test thread'i `birlesme/47a-test-cozumu/`'nü uygular. #48 de bekleniyor |
| #48 | 25 Tezgah torna/montaj | `claude/project-thread-udniip` | 97dad5c | Nerede kaldığı `durum/25` commit'inde (97dad5c). 47a buna bağlı |
| #146 | A0 (54 Karar 4) | `claude/cam-model-arayuz-dalga2-9lp9g2` | d9bdd63 | 54 test thread'i durumlar 11/11b xfail kaldırma commit'ini (eski 2d64ca2, **kayıp**) #146 ucunda yeniden yazıp push etmeli → A0 cherry-pick. Ayrıca `test_log_rotates_at_limit` CRLF (newline="\n"). Sonraki A0 işi: `ToolKind.THREAD_MILL` arayüz PR'ı |
| #155 | 61 K11 DFM ucu | `claude/project-thread-aeemx5` | c6a8dc6 (iskelet) | DFM testleri `claude/project-thread-caqs8f` 8dbf144 → kodlayıcı cherry-pick; kod taslağı §1 |
| #151 | 51 5X post | `claude/project-thread-t2yott` | 6a1b42c (iskelet) | Testler `claude/spec-51-5x-post-testler` ad0bd69 → post thread cherry-pick + kod + 3 örnek 5X profil |
| #147 | 67b | `claude/spec-06-cam-3d-09jwcj` | 57deac7 | Test dalı `claude/project-thread-gf85bj` 79b6b25 + e461361 cherry-pick; önce #122 |
| #139 | 58 süre/maliyet | `claude/spec-16-teknik-resim-u8ylv2` | 9eb53bc | Test dalı `claude/project-thread-e3jk0k` cfb4b12'ye fast-forward, `main` al; #143 sonrası tekrar |
| #148 | 68c harmonik | `claude/spec-45-modal-xigwto` | a50eb80 | SPEC düzeltmesi 6010608 dalda. Testler `claude/project-thread-p8ds2u` e9a8a7c + K5 onayı kodlayıcıya; kod `bekleyen/spec-68c/68c-kod.patch` |
| #144 | 65a serbest yüzey | `claude/project-thread-8dzgzc` | 9ec24fc | Testler `claude/project-thread-qqxkwb` 6caace9 (bbox düzeltmesi) → kodlayıcı; kod `spec-taslak/dalga-7/65a-kod.patch` |
| #145 | 65b PBR görünüm | `claude/project-thread-9npdya` | dbbd6c0 | `main` al, sonra a6f3565 (`claude/project-thread-z77l1v`) cherry-pick |
| #149 | 71 chatter lobu | `claude/spec-07-montaj-agaci-ejmdg5` | f6b8a6f (K7 arayüzü) | f6b8a6f'i 71 test thread'ine ilet; kodlayıcı testleri f8a2874 (`claude/project-thread-6bgsys`) cherry-pick eder |
| #157 | 62 aşama 2a | `claude/spec-15-goruntuleyici-d318ku` | f7b8e12 (iskelet) | f7b8e12'i 62 test thread'ine ilet; gövde taslakları `spec-62-asama2-taslak/` |
| #141 | 68a burkulma | `claude/project-thread-gmmhu4` | 95f7962 | #122/#147 sonrası aşama 2 |
| #136 | 68b geçici ısıl | `claude/project-thread-dt61rn` | 365cceb | #118, #122, #147 sonrası `main` al, ortak satırları çöz |
| #138 | 68d yorulma | `claude/project-thread-wmosjl` | 79bba55 | #147 sonrası K7 |
| #137 | 59 takım ömrü | `claude/spec-14-cam-kurulum-05r8z1` | 9595961 | B2 K9 ("cam malzeme'yi import etmez") çakışması kararı: `cam/omur.py` malzemeye duck typing, `ModelError` `core.model`'den; TAKIM_MALZEMELERI denetimi "tool_materials değeri `material.taylor` içinde" olur; K9 testi ve SPEC metni değişmez |

PR'sız dal: **Tezgah** `claude/project-thread-c0lzh0` c4d516a → #130 birleşince `main` al, `tezgah-kanca/gonder-ucu-kodu.patch`'i commit'le, PR aç.
Başlamamış: SPEC 70 (CalculiX köprüsü; 67a/67b sonrası).

## 4. Devam ederken sıra

1. **CI'ı tek PR'da yeniden çalıştır** (§0). Bozuksa dur, kullanıcıya Actions/dakika ayarını sor.
2. Yeşil olanları birleştir: #135, #130, #150, #122, #153.
3. CI yeşil olunca: #132, #129, #119, #118, #143, #126, #156.
4. Hazır hash'leri ilet (§3'teki "Ne bekliyor" sütunu): 69 (fa936bc+87a71b6), 51 (ad0bd69), 61 (8dbf144), 67b (79b6b25+e461361),
   58 (cfb4b12), 68c (e9a8a7c + K5 onayı + patch), 65a (6caace9 + patch), 71 (f6b8a6f → test thread; f8a2874), 62 (f7b8e12 → test thread), 53 (#153 merge hash).
5. Push edilmemiş işler: 69 bundle/patch, 47a 7ad7a8f bundle (sonra 47a test çözümü), A0 için kayıp commit'in yeniden yazımı, 65b `main` + a6f3565.
6. #130 sonrası Tezgah dalı (yukarıda). #122/#147 sonrası 68a/68b/68c(K6)/68d(K7)/70'e haber ver. 58 ve 62 aşama 2b #143'ü bekler; 64 uçları 58'i bekler.
7. B1 takip: `_yukle` `goc/kaynak_yol` düşürüyor (küçük SPEC 37 düzeltmesi).
8. 62 notu: `plan_mill` 2 mm stoklu flanşta "Ofset halkası kapanmadı" veriyor (cam/ofset hatası, 62 kapsamı dışı).

## 5. Kullanıcıyı bekleyenler

- **Gerçek takım kütüphanesi** (TK0 arayüz → TK1 envanter → TK4 tezgâh takım tablosu/post → TK3 kesme verisi → TK2 ISO 13399 içe aktarma):
  taslak `spec-taslak/takim-kutuphanesi.md`, durdurma notu §13. Onay bekliyor, kod yok.
- **Tezgâh doğrulaması (SPEC 48):** rehber ve betik kullanıcının yerel `yerel_parcalar/` klasöründe (NLX `O4801.NC`, DMU `DOGRULAMA_BLOK.MPF`, Z0 = stok altı).
  Kullanıcı önce profil varsayılanlarını tezgâh panelinden teyit eder, sonra kayıt JSON'ları + `rapor.html` gönderir ve `verified: true` yapar → SPEC 48 kapanır.
- **SPEC 69:** `specs/08-kisitlar.md`'deki "`|ω| < 1e-12` → birim" satırının güncellenmesi (rodrigues küçük açı kesmesi kaldırıldı) kullanıcı onayında.

## 6. Kararlar ve onaylar

**Kullanıcının yazılı onayları** (proje sohbeti): 16:06 Dalga 7; 16:19 65a, 65b, 68a–d, 69, 70, 71; 16:27 **kalıcı birleştirme onayı**
(thread'in izin denetimi `main` almayı/PR birleştirmeyi reddederse bu onay mesajı eklenir); 16:47 65a K5/K6; 17:57 50 ds_min, 08 ω=0, 53 numba;
19:08 68c K5 = CalculiX yazıcı denetimi, çözücü karşılaştırması tet10'a ertelendi; 19:08 "yarım kalmayacak şekilde işleri durdur".

**Genel kullanıcı kararları:** OpenCascade/build123d; FEM analiz modülü; CAM algoritmaları kendimiz; Python + numpy (numba izinli);
arayüz "Karma"; SPEC 05 z-map + dexel; `kapi` zorunlu; Dalga 6 "Tam"; Windows "Önce uv betiği"; DNC "Şimdilik dosya";
CalculiX gömülmez (GPL); chatter `cam/` içinde. Hedef: önce CAM (torna + freze) ve montaj, 3B katı tabanında (sac metal değil);
tasarımdan tezgâha tek yerel mühendislik uygulaması + analiz. Tezgah = FastAPI + tarayıcı.
Atölye: DMG MORI DMU 50/60/75/90, DMF 360, NTX 3000, NHC 5000, NLX 2500/700. Kontrol: önce Sinumerik 840D sl, sonra Heidenhain TNC 640;
NTX/NLX MAPPS varsayılır. MES yerel REST ile; Tezgah MES veritabanına yazmaz.

**SPEC kararları:** 56 K6 errata · 55 Karar 3/4 · B2: `ModelError(ValueError)` + salt okunur Mapping; K9: cam malzeme'yi import etmez (59 duck typing) ·
54 Karar 3/4/9 · 66: fiyat boş, 1.2312 Holdax, CW614N ν=0.31 · 67a D4: calculix eklemeli · 53 K7: d_H ≤ ρ − √(ρ² − c²/3) + δ + ε0 ·
52 K8 Pappus; 52 K6 D=10 tol 0.03·P · 47 K8: SPEC 44 kuralı + G93 yalnız kesme · SPEC 25 vs 24: önce freze ·
64: föy `build_job_sheet`/`render_html` ile · 61 K12 harfiyen; 61 DFM ucunu 61 kodlayıcı yazar · 65a K5 tol 5e-2, K6 60×60×40 ·
58 K1b: `maliyet(..., *, ops=None)` · 72 K3: tam çözüm yalnız eksene paralel doğru + yay; imza `toolpath_time(tp, dyn, *, q=None, tcp=False, inv_feed=None)` ·
65b: `GET /api/gorunum?montaj=…` · 68a K2: payda P·∫(w')² · 68d K3: sınırların hemen içi · 68b K2: ince Δt referansıyla · 67b: `kuvvet=` anahtar sözcüğü ·
47a bağımlılık testi katı kalır · 68c K5: CalculiX yazıcı denetimi · 50 ds_min 0,05; 08 kesme ω=0; 53 numba OK · 71 hataları `CamError` ·
B1 alan taşıma testini ayrı test thread'i yazar.

**Tezgah mimarisi:** uçlar yeni modül `tezgah/ekranlar/<x>.py` içinde `EKRAN = Ekran(...)`; `sunucu.py` `e.kur(app)` çağırır.

**Not:** #90 kırmızı CI ile birleştirildi (politika ihlali, kullanıcıya bildirildi). 2026-10-18 17:40 sonrası birleşenler:
#121 B2, #93 47b, #134 62 aşama 1, #152 SPEC 19 Windows, #112 SPEC 54, #127 66, #154 47c import düzeltmesi, #128 Tezgah hazır sinyali.

## 7. Başka bir yerden devam etmek

- GitHub'dan: bu dalı klonla (`git clone … && git checkout claude/yedek-durdurma-tck6s4`), `yedek/2026-10-18/` yeterli.
- Claude projesinden: aynı dosyalar proje klasöründe (`bekleyen/`, `taslak/`, `birlesme/`, `spec-taslak/`, …) ve bu belgenin kopyası `durdurma/DEVAM.md`.
- Yerelde: `pip install -e ".[dev,cad,viz]"`, `git config core.hooksPath .githooks`, `pytest`.
- Proje klasöründe olup buraya alınmayan eski malzeme (çoğu zaten birleşti): `inceleme/`, `arayuz/*.patch`, `testler/`, `spec22-yedek/`,
  `spec52-yedek/`, `yedek/47c/`, `tezgah/kod-taslak.patch`, `specs-taslak/`, `b1-iskelet/`, `atolye/`, `teknik-resim/`, `test-plani/`.
