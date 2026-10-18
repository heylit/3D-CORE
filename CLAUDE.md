# 3D-CORE — Claude Code çalışma kuralları

> **Oturuma başlarken:** önce `BASLANGIC.md` (hedef ve çalışma şekli), sonra `DURUM.md`
> (aktif görev, son oturum, açık sorular) oku. Oturum sonunda `DURUM.md`'yi güncelle.

Sıfırdan yazılan bir FEM (sonlu elemanlar) çözücüsü ve ileride CAD katmanı.
Amaç hem öğrenmek hem de doğrulanmış, güvenilir bir çekirdek kurmak.

## Altın kurallar
1. **Testsiz kod yok.** Her değişiklikten sonra `pytest` çalıştır. Kırmızı test varken iş bitmiş sayılmaz.
2. **Testi değiştirerek testi geçirme.** `tests/benchmarks/` analitik çözümlerdir; bir benchmark tutmuyorsa hata koddadır. Bir testin yanlış olduğunu düşünüyorsan değiştirme, kullanıcıya gerekçesiyle sor.
3. **Bir seferde bir SPEC.** Sadece istenen `specs/NN-*.md` dosyasını uygula. Kapsam dışına taşma.
4. **Birim sistemi: N – mm – MPa.** Kodda birim dönüşümü yapma; girdiler zaten bu birimde.
5. **Sessiz hata yok.** Tekil matris, bilinmeyen düğüm, sıfır boy gibi durumlarda `core.model.ModelError` fırlat. Asla `nan` veya yanlış sayı döndürme.

## Mimari
```
core/           Saf hesap. numpy + scipy dışında bağımlılık YOK (matplotlib, pyvista yasak).
  model.py      Tek veri modeli. Tüm katmanlar sadece bunun üzerinden konuşur.
  elements/     Her eleman bir dosya: ke(), dofs(), axial_force(). Kayıt: elements/__init__.py
  assembly.py   Global K (scipy.sparse) ve F. Eleman tipinden bağımsız.
  solver.py     K u = F, sınır koşulları, tepkiler.
  post.py       Eleman kuvvet/gerilme, ileride von Mises.
geometry/       build123d sarmalayıcıları (Aşama 2)
mesh/           gmsh -> Model dönüşümü (Aşama 2-3)
fileio/         JSON / STEP / CalculiX .inp (adı bilerek 'io' değil: stdlib ile çakışır)
viz/            matplotlib / pyvista çizimleri. core/ buraya bağımlı olamaz, tersi serbest.
tests/unit/        Matris özellikleri (simetri, rijit cisim modu, özdeğerler)
tests/benchmarks/  Analitik çözümlerle karşılaştırma
tests/reference/   CalculiX çapraz kontrolü (ileride)
specs/          Her adımın tanımı ve kabul kriterleri
examples/       JSON örnek problemler
```

## Kod stili
- Python 3.11+, tip ipuçları, kısa fonksiyonlar.
- Docstring ve yorumlar Türkçe; değişken adları formüldeki sembollerle aynı (`E`, `A`, `L`, `ke`, `K`, `u`, `F`).
- Döngü yerine numpy vektör işlemleri tercih et, ama okunabilirlik önce gelir: bu bir öğrenme projesi.
- Yeni bağımlılık ekleme; gerekiyorsa sor.

## Komutlar
- Kurulum: `pip install -e ".[dev]"`
- Test: `pytest`  (tek dosya: `pytest tests/benchmarks/test_bar.py -v`)
- Lint: `ruff check .`  (otomatik düzelt: `ruff check . --fix`, biçim: `ruff format .`)
- Tam yerel CI (Windows): `.\ci.ps1`

## Git ve CI kuralları (GitHub Actions dakikası kısıtlı)
- CI yereldir: pre-commit (ruff + hızlı testler) ve pre-push (ruff + tüm testler) hook'ları kapıdır. `--no-verify` KULLANMA.
- Push'ları grupla: her küçük commit'te push etme. Bir SPEC bitince veya oturum sonunda bir kez push et.
- Bulut/uzak oturumlarda: `main` yerine `spec-NN-...` dalında çalış, iş bitince `main`'e tek PR aç. Actions sadece bu PR'da çalışır.
- 10 saniyeden uzun süren testleri `@pytest.mark.slow` ile işaretle.
- `.github/workflows/test.yml` dosyasında tetikleyici, Python sürümü sayısı veya işletim sistemi ekleme; dakika maliyetini artırır. Gerekirse kullanıcıya sor.

## Ajanlar
- `yazici` (.claude/agents/yazici.md): SPEC'i uygular, testlere dokunmaz.
- `dogrulayici` (.claude/agents/dogrulayici.md): Kodu görmeden SPEC'ten test yazar.
Akış: SPEC -> dogrulayici testleri yazar -> yazici kodu yazar -> pytest yeşil -> commit.

## Gizlilik
Gerçek şirket parçaları, çizimleri veya müşteri verisi repoya girmez. Bunlar sadece `yerel_parcalar/` (gitignore'da) altında durur. Testlerde uydurma geometri kullan.
