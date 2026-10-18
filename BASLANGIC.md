# BAŞLANGIÇ — 3D-CORE projesine hoş geldin

> **Bu dosya, projede çalışan her ajanın ve oturumun ilk okuması gereken dosyadır.**
> Okuma sırası: `BASLANGIC.md` (bu dosya) → `CLAUDE.md` → `DURUM.md` → aktif SPEC (`DURUM.md` söyler).
> Bu dört dosyayı okumadan kod yazma.

---

## 1. Proje nedir?

**3D-CORE**, sıfırdan yazılan bir **3D tasarım, simülasyon ve analiz** sistemidir. Kalbinde
kendi yazdığımız ve adım adım **doğruladığımız** bir sonlu elemanlar (FEM) çözücüsü var.
Üzerine zamanla mesh, geometri (CAD) ve arayüz katmanları eklenecek.

İki amacı var, ikisi de eşit önemde:
1. **Öğrenmek.** FEM ve CAD'in içinde ne olduğunu gerçekten anlamak. Kod okunabilir,
   formüllerle birebir eşleşen, açıklamalı olmalı. "Çalışıyor ama neden bilmiyorum" kabul edilmez.
2. **Güvenilir bir çekirdek kurmak.** Mühendislik kararlarında kullanılabilecek kadar doğru.
   Her sonuç analitik çözüm veya bağımsız bir çözücüyle karşılaştırılarak doğrulanır.

**Nihai ürün hedefi (niş):** Sac metal parçalar için tasarım, büküm açılımı (K-faktörü / büküm payı)
ve basit dayanım kontrolü yapan bir araç. Genel amaçlı bir SolidWorks/ANSYS rakibi **değil**.

## 2. Hedefler

### Uzun vadeli (5–7 ay)
Kodla modellenen bir parçayı (ör. braket) tek komutla mesh'leyip, kendi çözücümüzle analiz edip,
gerilme haritasını gösteren; sonuçları CalculiX ile %1 içinde tutan uçtan uca bir zincir.

### Aşama hedefleri

| Aşama | Hedef | Ölçülebilir bitiş kriteri |
|---|---|---|
| **1. Analiz motoru** | 1D çubuk → 2D kafes → 2D üçgen eleman → von Mises | Delikli plakada gerilme yığılması Kt ≈ 3 (Kirsch), patch test geçiyor |
| **2. Geometri ve CAD** | Görüntüleyici, kodla parametrik parça, 2D kısıt çözücü | Ölçüsü değişen flanş STEP olarak çıkıyor; kısıtlı dikdörtgen doğru yeniden şekilleniyor |
| **3. Birleştirme** | 3D tetrahedron, uçtan uca zincir, CalculiX kontrolü, basit arayüz | Braket analizi CalculiX ile < %1 fark |
| **4. Ürün** | Sac metal nişi | Ayrıca planlanacak |

Ayrıntılı adım listesi: `docs/yol-haritasi.md`.

### Şu anki hedef
`DURUM.md` dosyasındaki **"Aktif görev"** satırı. Başka bir şey yapma.

## 3. Mimari (özet)

```
JSON model ─► core/model.py ─► core/elements/* (ke) ─► core/assembly.py (K, F)
                                                   ─► core/solver.py (K u = F)
                                                   ─► core/post.py (kuvvet, gerilme)
                                                   ─► viz/ (çizim, core'a bağımlı değil)
```

- **Tek veri modeli:** Her katman sadece `core/model.py` sınıflarıyla konuşur.
- **`core/` saftır:** numpy + scipy dışında bağımlılık yok.
- **Yeni eleman = yeni dosya:** `core/elements/` altına dosya + `ELEMENTS` sözlüğüne bir satır.
  `assembly.py` ve `solver.py` değişmez.
- **Birimler:** N – mm – MPa. Dönüşüm yok.

Tam kurallar: `CLAUDE.md`.

## 4. Nasıl çalışılır? (her SPEC için aynı döngü)

```
1. DURUM.md'yi oku → aktif SPEC'i öğren
2. Dal aç:            git switch -c spec-NN-kisa-ad
3. SPEC yoksa yaz:    specs/00-sablon.md'den kopyala → kullanıcı onayı al
4. Testler önce:      dogrulayici ajanı → tests/ altına testler (KIRMIZI olmalı)
5. Kod:               yazici ajanı → core/ altında uygula (YEŞİL olana kadar)
6. Yerel CI:          pytest  ve  ruff check .   (Windows'ta: .\ci.ps1)
7. DURUM.md güncelle  (bkz. bölüm 7)
8. Commit             (pre-commit hook kontrol eder)
9. Push + PR          SPEC bitince tek push, main'e tek PR (pre-push hook kontrol eder)
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
- [ ] `pytest` → 0 failed, `ruff check .` → temiz
- [ ] Her beklenen değerin kaynağı (formül / kitap / el hesabı) test yorumunda yazılı
- [ ] Yeni fonksiyonların Türkçe docstring'i var, formüldeki sembollerle aynı adlar kullanılmış
- [ ] `DURUM.md` güncellendi
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

Her oturumun sonunda, iş yarım kalsa bile, `DURUM.md` dosyasını güncelle:
1. **Aktif görev** satırını güncel tut.
2. **Son oturum** bölümüne tarih + 3–5 maddelik özet yaz: ne yapıldı, test sayısı (geçen/kalan).
3. **Sıradaki adım:** bir sonraki oturumun ilk yapacağı şey, tek cümle.
4. **Açık sorular:** kullanıcıdan cevap bekleyen her şey.
5. Bir SPEC bittiyse **Tamamlananlar** tablosuna ekle ve kuyruktan bir sonrakini aktif yap.

Sonraki oturum hiçbir şey hatırlamadan başlar; bilmesi gereken her şey `DURUM.md`'de olmalı.

## 8. SPEC yazma rehberi

Yeni bir SPEC (`specs/NN-ad.md`) yazarken:
- `specs/00-sablon.md` başlıklarını kullan.
- **Teori** bölümüne formülleri açıkça yaz; kaynak göster (kitap + bölüm).
- **Kabul kriterleri** ölçülebilir olsun: "δ = FL/EA, rel 1e-9" gibi. "Doğru çalışsın" yazma.
- Yaklaşık elemanlarda (üçgen, tetrahedron) **yakınsama testi** ve **patch test** zorunlu.
- **Kapsam dışı** bölümünü boş bırakma; neyin yapılmayacağını yaz.
- SPEC'i kod yazmadan önce kullanıcıya onaylat.

## 9. Görev kuyruğu

| Sıra | SPEC | Konu | Not |
|---|---|---|---|
| 1 | `01-bar` | 1D çubuk + çözücü iskeleti | SPEC ve testler hazır, sadece kod yazılacak |
| 2 | `01b-viz-bar` | Çubuk sonucunu matplotlib ile çiz | Küçük; `viz/` altında, isteğe bağlı |
| 3 | `02-truss2d` | 2D kafes, koordinat dönüşümü (c = cosθ, s = sinθ) | Doğrulama: ders kitabı kafes örneği (Logan Bölüm 3) |
| 4 | `03-tri3` | Düzlem gerilme CST üçgen | Patch test + konsol kiriş yakınsaması |
| 5 | `04-gmsh` | Gmsh ile mesh, delikli plaka | Kirsch çözümü, Kt ≈ 3 |
| 6 | `05-vonmises` | Von Mises + renk haritası | |

Sonrası: `docs/yol-haritasi.md`.

## 10. Hızlı komutlar

```powershell
pip install -e ".[dev]"        # kurulum
pytest                          # tüm testler
pytest tests/benchmarks -v      # sadece analitik benchmark'lar
ruff check . --fix              # lint + otomatik düzeltme
.\ci.ps1                        # tam yerel CI + rapor (Windows)
.\ci.ps1 -Gecmis                # son CI çalıştırmaları
```

## 11. Kaynaklar
- Logan, *A First Course in the Finite Element Method* — Aşama 1'in ana kaynağı
- Cook vd., *Concepts and Applications of Finite Element Analysis* — patch test, yakınsama
- Piegl & Tiller, *The NURBS Book* — Aşama 2 (geometri)
- NAFEMS benchmark'ları — ileri doğrulama
