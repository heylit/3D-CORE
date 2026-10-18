# BAŞLANGIÇ — 3D-CORE projesine hoş geldin

> **Bu dosya, projede çalışan her ajanın ve oturumun ilk okuması gereken dosyadır.**
> Okuma sırası: `BASLANGIC.md` (bu dosya) → `CLAUDE.md` → `DURUM.md` → üzerinde çalışacağın SPEC ve onun `durum/NN-*.md` dosyası.
> Bu dört dosyayı okumadan kod yazma.

---

## 1. Proje nedir?

**3D-CORE**, bir **3D CAM ve 3D montaj** sistemidir. Katı modelleme bunlara hizmet eden altyapıdır.
Yanında kendi yazdığımız ve adım adım **doğruladığımız** bir sonlu elemanlar (FEM) çözücüsü analiz
modülü olarak durur.

Katı modelleme çekirdeği **hazırdır: OpenCascade (OCCT), build123d üzerinden.** B-rep çekirdeğini
sıfırdan yazmıyoruz. Kendi yazdığımız ve doğruladığımız kısımlar: takım yolu ve G-code, talaş kaldırma
simülasyonu, montaj ağacı ve kısıt çözücü, girişim kontrolü, FEM.

İki amacı var, ikisi de eşit önemde:
1. **Öğrenmek.** CAM, montaj ve FEM'in içinde ne olduğunu gerçekten anlamak. Kod okunabilir,
   formüllerle birebir eşleşen, açıklamalı olmalı. "Çalışıyor ama neden bilmiyorum" kabul edilmez.
2. **Güvenilir bir çekirdek kurmak.** Tezgâhta ve mühendislik kararlarında kullanılabilecek kadar doğru.
   Her sonuç analitik çözüm veya bağımsız bir araçla karşılaştırılarak doğrulanır.

**Nihai ürün hedefi:** Katı parçaları (kodla oluşturulan veya STEP'ten okunan) montajda kısıtlarla
birleştiren ve CNC için doğrulanmış takım yolu ile G-code üreten bir araç; dayanım kontrolü kendi FEM
modülümüzle. Genel amaçlı bir SolidWorks/Fusion rakibi **değil**; önce dar ama doğru.

## 2. Hedefler

### Uzun vadeli
Bir montajı (ör. braket + mil + flanş) kurup kısıtlarını çözen, girişim kontrolü yapan, parçalardan biri
için G-code üreten ve simülasyonda CAD şekline tolerans içinde, çakmadan ulaştığını gösteren uçtan uca
zincir. Aynı parça FEM ile analiz edilip CalculiX ile %1 içinde tutulur.

### Aşama hedefleri

| Aşama | Hedef | Ölçülebilir bitiş kriteri |
|---|---|---|
| **0. FEM iskeleti** | SPEC 01: 1D çubuk + çözücü | 41 test yeşil |
| **1. Katı altyapı** | STEP/STL içe-dışa aktarma, kodla basit parça, kütle özellikleri | Hacim / alan / ağırlık merkezi analitik değerle tutuyor |
| **2. CAM** | 2.5D kontur / cep, G-code, talaş simülasyonu, 3D yüzey işleme | Simülasyondaki son parça CAD hacmiyle tolerans içinde; çakma yok |
| **3. Montaj** | Montaj ağacı, BOM, montaj kısıtları, girişim, montajdan CAM'e | Kısıtlı montajda konumlar kapalı form çözümle 1e-9 mm; girişim hacmi doğru |
| **4. Analiz** | tet4, gmsh, von Mises, CalculiX | Braket analizi CalculiX ile < %1 fark |

Ayrıntılı adım listesi: `docs/yol-haritasi.md`.

### Şu anki hedef
Sana verilen tek SPEC. Hangi SPEC'lerin açık olduğunu `DURUM.md` söyler. Başka bir şey yapma.

## 3. Mimari (özet)

```
geometry/ (build123d / OCCT katı parça) ─► assy/ (montaj, kısıtlar) ─► cam/ (takım yolu, G-code)
        │
        └─► mesh/ (gmsh) ─► core/model.py ─► core/elements/* ─► core/assembly.py (K, F)
                                                            ─► core/solver.py (K u = F)
                                                            ─► core/post.py (kuvvet, gerilme)
viz/ her katmanı çizebilir; hiçbir katman viz/'e bağımlı değildir.
```

- **FEM'in tek veri modeli:** FEM katmanları sadece `core/model.py` sınıflarıyla konuşur.
- **`core/` saftır:** numpy + scipy dışında bağımlılık yok. build123d / OCCT sadece `geometry/`,
  `assy/`, `cam/` ve `mesh/` içinde kullanılır.
- **İsimler:** montaj paketi `assy/` (FEM'deki `core/assembly.py` = global K birleştirme ile karışmasın).
- **Yeni eleman = yeni dosya:** `core/elements/` altına dosya + `ELEMENTS` sözlüğüne bir satır.
  `assembly.py` ve `solver.py` değişmez.
- **Birimler:** N – mm – MPa. Dönüşüm yok.

Tam kurallar: `CLAUDE.md`.

## 4. Nasıl çalışılır? (paralel, bulut + yerel)

Proje **aynı anda birden fazla oturumla** geliştirilir: GitHub üzerinden bulut thread'leri ve
bilgisayardaki yerel klasör. Mimari buna göre kuruldu:

- **Bir SPEC = bir dal = bir PR = bir oturum.** Aynı SPEC'te iki oturum aynı anda çalışmaz.
- **Her SPEC sadece kendi alanına yazar:** kendi paketi (`cam/`, `assy/`, `geometry/`, `core/`),
  kendi test klasörü (`tests/cam/` ...), kendi `specs/NN-*.md` ve `durum/NN-*.md` dosyası.
- **Ortak dosyalar** (`*/model.py` arayüzleri, `pyproject.toml`, `.github/`, `CLAUDE.md`, `BASLANGIC.md`,
  `DURUM.md`) bir SPEC PR'ında değişmez. Değişmesi gerekiyorsa ayrı, küçük bir "arayüz PR'ı" açılır,
  kullanıcı onaylar, önce o birleşir.
- **Sıra:** `docs/yol-haritasi.md` → "Paralel çalışma: dalgalar". Bir dalgadaki SPEC'ler aynı anda başlar.
- **Aynı kurulum her yerde:** `pip install -e ".[dev,cad,viz]"` ve `pytest`. OCCT gerektiren testler
  `@pytest.mark.occt` ile işaretlenir; build123d yoksa atlanır, böylece saf modüller her yerde hızlı test edilir.

### Her SPEC için döngü
```
1. DURUM.md'yi oku → hangi dalga açık, hangi SPEC boşta
2. Dal aç:            git switch -c spec-NN-kisa-ad   (bulutta oturumun verdiği dal adı da olur)
3. SPEC yoksa yaz:    specs/00-sablon.md'den kopyala → kullanıcı onayı al
4. Testler önce:      dogrulayici ajanı → tests/<paket>/ altına testler (KIRMIZI olmalı)
5. Kod:               yazici ajanı → <paket>/ altında uygula (YEŞİL olana kadar)
6. Yerel CI:          pytest  ve  ruff check .   (Windows'ta: .\ci.ps1)
7. durum/NN-*.md güncelle  (bkz. bölüm 7)
8. Commit             (pre-commit hook kontrol eder)
9. Push + PR          SPEC bitince tek push, main'e tek PR (pre-push hook kontrol eder)
10. Birleşmeden önce: main'i dala al (merge), testler yine yeşil
```

### Ajanlar
| Ajan | Görev | Dokunamaz |
|---|---|---|
| `dogrulayici` | SPEC'ten ve teoriden test yazar | Uygulama kodunun gövdesini okuyamaz |
| `yazici` | SPEC'i uygular | `tests/` klasörünü değiştiremez |

Testi yazan ile kodu yazan ayrı olmalı ki kod kendine not vermesin.

## 5. "Bitti" tanımı

Bir SPEC ancak şunların **hepsi** sağlandığında biter:
- [ ] SPEC'teki her kabul kriterinin en az bir testi var ve hepsi yeşil
- [ ] `pytest` → 0 failed ve bu SPEC'in testlerinde 0 "uygulanmamış", `ruff check .` → temiz
- [ ] Her beklenen değerin kaynağı (formül / kitap / el hesabı) test yorumunda yazılı
- [ ] Yeni fonksiyonların Türkçe docstring'i var, formüldeki sembollerle aynı adlar kullanılmış
- [ ] `durum/NN-*.md` güncellendi
- [ ] Ortak dosyalara (arayüzler, `pyproject.toml`, `.github/`) dokunulmadı
- [ ] Kapsam dışına çıkılmadı (SPEC'in "Kapsam dışı" bölümü)

## 6. Kurallar

### Her zaman
- Önce oku, sonra yaz. Mevcut arayüzü (`core/model.py`) koru.
- Küçük adımlarla ilerle; her adımdan sonra testleri çalıştır.
- Emin olmadığın bir mühendislik varsayımını (işaret kuralı, sınır koşulu, birim) **yaz ve sor**.
- Hata durumlarında `ModelError` fırlat; sessizce `nan` veya yanlış sayı döndürme.

### Asla
- Bir testi geçirmek için testi değiştirme. Test yanlış görünüyorsa gerekçesiyle kullanıcıya sor.
- `--no-verify` ile hook atlama.
- Her küçük commit'te push etme (GitHub Actions dakikası kısıtlı).
- `.github/workflows/` dosyasına tetikleyici, Python sürümü veya işletim sistemi ekleme.
- Yeni bağımlılık ekleme (sormadan).
- Gerçek şirket parçası, çizimi veya müşteri verisini repoya koyma. Bunlar sadece
  `yerel_parcalar/` altında durur (gitignore'da). Testlerde uydurma geometri kullan.
- Birden fazla SPEC'i aynı anda yapma.

### Ne zaman kendin karar ver, ne zaman sor
| Kendin karar ver | Kullanıcıya sor |
|---|---|
| Değişken adı, yardımcı fonksiyon, kod düzeni | Yeni bağımlılık |
| Test sayısını artırmak | Bir testin yanlış olduğu şüphesi |
| SPEC'te açıkça yazan her şey | SPEC'te belirsiz veya çelişkili nokta |
| Docstring ve yorum | Arayüz (`model.py`) değişikliği |
| | Kapsamı genişletmek |

## 7. Oturum sonu protokolü

Paralel oturumlar aynı dosyada çakışmasın diye her SPEC'in durumu **kendi dosyasında** tutulur:
`durum/NN-ad.md` (şablon: `durum/00-sablon.md`). Her oturumun sonunda, iş yarım kalsa bile:
1. **Son oturum:** tarih + 3–5 madde: ne yapıldı, test sayısı (geçen/kalan).
2. **Sıradaki adım:** bir sonraki oturumun ilk yapacağı şey, tek cümle.
3. **Açık sorular:** kullanıcıdan cevap bekleyen her şey.

`DURUM.md` genel tablodur (dalgalar, hangi SPEC kimde, tamamlananlar). Sadece bir PR `main`'e
birleşirken ya da yeni bir SPEC'e başlanırken, tek satır değiştirilerek güncellenir.

Sonraki oturum hiçbir şey hatırlamadan başlar; bilmesi gereken her şey bu dosyalarda olmalı.

## 8. SPEC yazma rehberi

Yeni bir SPEC (`specs/NN-ad.md`) yazarken:
- `specs/00-sablon.md` başlıklarını kullan.
- **Teori** bölümüne formülleri açıkça yaz; kaynak göster (kitap + bölüm).
- **Kabul kriterleri** ölçülebilir olsun: "δ = FL/EA, rel 1e-9" gibi. "Doğru çalışsın" yazma.
- Yaklaşık elemanlarda (üçgen, tetrahedron) **yakınsama testi** ve **patch test** zorunlu.
- **Kapsam dışı** bölümünü boş bırakma; neyin yapılmayacağını yaz.
- SPEC'i kod yazmadan önce kullanıcıya onaylat.

## 9. Görev kuyruğu

Sıra ve paralellik: `docs/yol-haritasi.md` → "Paralel çalışma: dalgalar". Kim neyi yapıyor: `DURUM.md`.

## 10. Hızlı komutlar

```powershell
pip install -e ".[dev,cad,viz]" # kurulum
pytest                          # tüm testler
pytest tests/benchmarks -v      # sadece analitik benchmark'lar
ruff check . --fix              # lint + otomatik düzeltme
.\ci.ps1                        # tam yerel CI + rapor (Windows)
.\ci.ps1 -Gecmis                # son CI çalıştırmaları
```

## 11. Kaynaklar
- build123d belgeleri (build123d.readthedocs.io) ve OpenCascade belgeleri — katı altyapı
- Held, *On the Computational Geometry of Pocket Machining* — cep / ofset takım yolları
- Smid, *CNC Programming Handbook* — G-code, çevrimler, post-işlemci
- Kramer, *Assembly constraint solving* çalışmaları ve Hartenberg–Denavit — montaj kısıtları, dönüşümler
- Logan, *A First Course in the Finite Element Method* — FEM'in ana kaynağı
- Cook vd., *Concepts and Applications of Finite Element Analysis* — patch test, yakınsama
- NAFEMS benchmark'ları — ileri doğrulama
