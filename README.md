# 3D-CORE

Sıfırdan yazılan, adım adım doğrulanan bir FEM (sonlu elemanlar) çözücüsü. İleride CAD katmanı eklenecek.

- **Başlangıç (önce bunu oku):** [`BASLANGIC.md`](BASLANGIC.md)
- Canlı durum: [`DURUM.md`](DURUM.md)
- Kurallar ve mimari: [`CLAUDE.md`](CLAUDE.md)
- Yol haritası: [`docs/yol-haritasi.md`](docs/yol-haritasi.md)
- Şu anki adım: [`specs/01-bar.md`](specs/01-bar.md)

## Kurulum (Windows, bir kez)

PowerShell'de proje klasöründe:

```powershell
powershell -ExecutionPolicy Bypass -File _kurulum\yerlestir.ps1   # ajanları ve CI dosyasını yerine koyar
py -3.12 -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
pytest
```

> PowerShell "script çalıştırma kapalı" derse:
> `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`

İlk `pytest` çalıştırmasında **veri modeli testleri geçer, çubuk testleri kırmızı olur**.
Bu bilerek böyle: testler önce yazıldı (TDD), kod SPEC 01 ile yazılacak.

## Git + GitHub

```powershell
git init -b main
git config core.hooksPath .githooks                      # yerel CI kapıları
git add .
git update-index --chmod=+x .githooks/pre-commit .githooks/pre-push .githooks/_python.sh
git commit --no-verify -m "İskelet: veri modeli, SPEC 01, testler, yerel CI"
```
- `--chmod=+x`: hook'ların klonlanan her yerde (Claude bulut oturumları dahil) çalışması için. Atlanırsa Linux'ta git hook'ları sessizce yok sayar.
- İlk commit'te `--no-verify` var çünkü SPEC 01 henüz uygulanmadı. Sonrasında kullanma.

GitHub'da **private** bir repo aç (`3D-CORE`), sonra:

```powershell
git remote add origin https://github.com/<kullanici>/3D-CORE.git
git push -u origin main --no-verify      # sadece bu ilk push'ta
```

## CI: yerelde, ücretsiz

Kontrolün tamamı bilgisayarında yapılır. GitHub Actions sadece son kapıdır.

| Kapı | Ne zaman | Ne yapar |
|---|---|---|
| `.githooks/pre-commit` | her `git commit` | ruff + hızlı testler (`slow` işaretliler hariç) |
| `.githooks/pre-push` | her `git push` | ruff + **tüm** testler |
| `.\ci.ps1` | elle | ruff + tüm testler + HTML rapor + log |
| GitHub Actions | sadece `main`'e PR ve elle | aynı kontrol, bağımsız makinede |

```powershell
.\ci.ps1            # çalıştır
.\ci.ps1 -Ac        # çalıştır, raporu tarayıcıda aç
.\ci.ps1 -Gecmis    # son 15 çalıştırma: tarih, commit, geçti/kaldı, test sayısı
```
Çıktılar `reports\` altında (git'e girmez). Commit kodunun yanındaki `*`, commit edilmemiş değişiklik olduğunu gösterir.

**Actions dakikası nasıl az tutuluyor** (`.github/workflows/test.yml`):
- `main`'e doğrudan push CI tetiklemez; zaten pre-push'tan geçmiştir.
- Sadece belge (`*.md`, `docs/`, `specs/`) değişen PR'lar çalışmaz.
- Tek Python sürümü, sadece Ubuntu, pip önbelleği, 10 dk zaman aşımı.
- Aynı PR'a yeni push gelirse eski çalışma iptal edilir.

Uzun süren bir test yazarsan `@pytest.mark.slow` ile işaretle: commit'i yavaşlatmaz, push'ta yine çalışır.

## Claude Code ile çalışma döngüsü

Antigravity'de Claude Code'a:

```
yazici ajanıyla specs/01-bar.md'yi uygula. Testlere dokunma, pytest yeşil olana kadar devam et.
```

Sonraki her adım için:
1. `specs/00-sablon.md`'yi kopyalayıp `specs/02-truss2d.md` yaz (ya da Claude'a taslak yazdır, sen onayla).
2. `dogrulayici ajanıyla specs/02 için testleri yaz` — testler kırmızı olmalı.
3. `yazici ajanıyla specs/02'yi uygula` — testler yeşil olmalı.
4. Commit + push.

## Birimler
N – mm – MPa. Tüm girdi ve çıktılar bu sistemde.

## Gizlilik
Gerçek şirket parçaları `yerel_parcalar/` klasörüne konur; bu klasör `.gitignore`'da, repoya girmez.
