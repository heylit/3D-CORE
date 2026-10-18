# 3D-CORE — Claude Code çalışma kuralları

> **Oturuma başlarken:** önce `BASLANGIC.md` (hedef ve çalışma şekli), sonra `DURUM.md`
> (açık dalga, kim neyi yapıyor) ve SPEC'inin `durum/NN-*.md` dosyasını oku. Oturum sonunda `durum/NN-*.md`'yi güncelle.

3D CAM ve 3D montaj sistemi. Katı modelleme altyapısı hazır çekirdekle (OpenCascade, build123d üzerinden);
yanında kendi FEM çözücümüz analiz modülü olarak. Amaç hem öğrenmek hem de doğrulanmış, güvenilir bir çekirdek kurmak.
Birden fazla oturum (bulut + yerel) **aynı anda** çalışır: `BASLANGIC.md` bölüm 4.

## Altın kurallar
1. **Testsiz kod yok.** Her değişiklikten sonra `pytest` çalıştır. Kırmızı test varken iş bitmiş sayılmaz.
2. **Testi değiştirerek testi geçirme.** `tests/benchmarks/` analitik çözümlerdir; bir benchmark tutmuyorsa hata koddadır. Bir testin yanlış olduğunu düşünüyorsan değiştirme, kullanıcıya gerekçesiyle sor.
3. **Bir oturumda bir SPEC.** Sadece istenen `specs/NN-*.md` dosyasını uygula; sadece o SPEC'in paketine, test klasörüne ve `durum/NN-*.md` dosyasına yaz. Kapsam dışına taşma.
4. **Birim sistemi: N – mm – MPa.** Kodda birim dönüşümü yapma; girdiler zaten bu birimde.
5. **Sessiz hata yok.** Tekil matris, bilinmeyen düğüm, sıfır boy gibi durumlarda `core.model.ModelError` fırlat. Asla `nan` veya yanlış sayı döndürme.

## Mimari
```
geometry/       Katı altyapı: build123d / OCCT sarmalayıcıları. Arayüz: geometry/part.py (Part)
cam/            Takım yolu, G-code, talaş simülasyonu. Arayüz: cam/model.py (Tool, Stock, Move, Toolpath)
assy/           Montaj ağacı, kısıt çözücü, girişim. Arayüz: assy/model.py (Component, Assembly, Mate)
                (adı 'assy': FEM'deki core/assembly.py ile karışmasın)
core/           FEM. Saf hesap: numpy + scipy dışında bağımlılık YOK (OCCT, matplotlib, pyvista yasak).
  model.py      FEM'in tek veri modeli.
  elements/     Her eleman bir dosya: ke(), dofs(), axial_force(). Kayıt: elements/__init__.py
  assembly.py   Global K (scipy.sparse) ve F. Eleman tipinden bağımsız.
  solver.py     K u = F, sınır koşulları, tepkiler.
  post.py       Eleman kuvvet/gerilme, ileride von Mises.
mesh/           gmsh -> core.model.Model dönüşümü
fileio/         JSON / STEP / CalculiX .inp (adı bilerek 'io' değil: stdlib ile çakışır)
viz/            matplotlib / pyvista çizimleri. Hiçbir paket viz/'e bağımlı olamaz, tersi serbest.
tests/unit/, tests/benchmarks/   FEM (mevcut)
tests/geometry/, tests/cam/, tests/assy/   Paket başına testler
tests/reference/   CalculiX çapraz kontrolü (ileride)
specs/          Her adımın tanımı ve kabul kriterleri
durum/          SPEC başına canlı durum dosyası (paralel oturumlar çakışmasın diye)
examples/       JSON örnek problemler
```

### Paralel çalışma için bağımlılık kuralları
- Paketler birbirini **sadece `model.py` arayüzleri üzerinden** kullanır (ör. `cam` → `geometry.part.Part`),
  başka bir paketin iç dosyalarını import etmez.
- `cam/model.py` ve `assy/model.py` saf Python + numpy'dir; OCCT gerektirmez. Takım yolu, G-code ve
  kısıt çözücü OCCT olmadan geliştirilip test edilebilir.
- OCCT / build123d gerektiren testler `@pytest.mark.occt` ile işaretlenir (yoksa atlanır).
- Arayüz (`*/model.py`) değişikliği = ayrı küçük PR + kullanıcı onayı. SPEC PR'ı arayüzü değiştirmez.

## Kod stili
- Python 3.11+, tip ipuçları, kısa fonksiyonlar.
- Docstring ve yorumlar Türkçe; değişken adları formüldeki sembollerle aynı (`E`, `A`, `L`, `ke`, `K`, `u`, `F`).
- Döngü yerine numpy vektör işlemleri tercih et, ama okunabilirlik önce gelir: bu bir öğrenme projesi.
- Yeni bağımlılık ekleme; gerekiyorsa sor.

## Komutlar
- Kurulum (bulut ve yerel aynı): `pip install -e ".[dev,cad]"`  (sadece FEM için `.[dev]` yeter)
- Test: `pytest`  (tek dosya: `pytest tests/benchmarks/test_bar.py -v`)
- Lint: `ruff check .`  (otomatik düzelt: `ruff check . --fix`, biçim: `ruff format .`)
- Tam yerel CI (Windows): `.\ci.ps1`

## Git ve CI kuralları (GitHub Actions dakikası kısıtlı)
- CI yereldir: pre-commit (ruff + hızlı testler) ve pre-push (ruff + tüm testler) hook'ları kapıdır. `--no-verify` KULLANMA.
- Push'ları grupla: her küçük commit'te push etme. Bir SPEC bitince veya oturum sonunda bir kez push et.
- Bir SPEC = bir dal = bir PR. `main`'de doğrudan çalışma. Dal adı `spec-NN-...` (bulutta oturumun verdiği dal adı da olur). Actions sadece bu PR'da çalışır.
- Ortak dosyalar (`*/model.py`, `pyproject.toml`, `.github/`, `CLAUDE.md`, `BASLANGIC.md`, `DURUM.md`) SPEC PR'ında değişmez; gerekiyorsa ayrı PR.
- PR'ı açmadan önce `main`'i dala merge et ve testleri yeniden çalıştır (rebase / force-push yok).
- 10 saniyeden uzun süren testleri `@pytest.mark.slow` ile işaretle.
- `.github/workflows/test.yml` dosyasında tetikleyici, Python sürümü sayısı veya işletim sistemi ekleme; dakika maliyetini artırır. Gerekirse kullanıcıya sor.

## Ajanlar
- `yazici` (.claude/agents/yazici.md): SPEC'i uygular, testlere dokunmaz.
- `dogrulayici` (.claude/agents/dogrulayici.md): Kodu görmeden SPEC'ten test yazar.
Akış: SPEC -> dogrulayici testleri yazar -> yazici kodu yazar -> pytest yeşil -> commit.

### Test bağımsızlığı (zorunlu)
Aynı oturum hem testi hem kodu yazarsa testler koda göre ayarlanır; o yüzden:
- Testler ve kod **ayrı commit'lerde ve ayrı oturumlarda** yazılır: önce `dogrulayici` oturumu SPEC'in
  testlerini commit'ler (kod henüz yokken testler "uygulanmamış" görünür), sonra başka bir `yazici` oturumu kodu yazar.
- Kod commit'leri o SPEC'in test dosyalarını değiştirmez. Test yanlış görünüyorsa kullanıcıya sorulur (altın kural 2).
- PR açıklaması iki oturumun bağlantısını ve test commit'ini yazar; ikisi aynıysa PR "bağımsız değil" diye işaretlenir.
- Onaylanmış SPEC metni (kabul kriterleri, ekler) kullanıcı onayı olmadan değiştirilmez; kodu yazan oturum SPEC'i netleştirmez.
- PR'da (CI) `NotImplementedError` ile düşen test kırmızıdır (`pytest --uygulanmamis-hata`); yerelde TDD için "uygulanmamış" sayılır.

## Gizlilik
Gerçek şirket parçaları, çizimleri veya müşteri verisi repoya girmez. Bunlar sadece `yerel_parcalar/` (gitignore'da) altında durur. Testlerde uydurma geometri kullan.
