# DURUM — projenin canlı durumu

> Her oturumun sonunda güncellenir (kurallar: `BASLANGIC.md` bölüm 7).
> Sonraki oturum hiçbir şey hatırlamaz; bilmesi gereken her şey burada olmalı.

## Aktif görev
**SPEC 01 — 1D çubuk elemanı ve doğrusal statik çözücü** → `specs/01-bar.md`
Dal: `spec-01-bar`

## Sıradaki adım
`yazici` ajanıyla `specs/01-bar.md`'yi uygula: `core/elements/bar1d.py`, `core/assembly.py`,
`core/solver.py`, `core/post.py` içindeki `NotImplementedError` fonksiyonları. Testlere dokunma.

## Test durumu
| Tarih | Geçen | Kalan | Not |
|---|---|---|---|
| 2026-10-18 | 12 | 29 | İskelet: veri modeli testleri geçiyor, SPEC 01 testleri bilerek kırmızı (TDD) |

## Son oturum
**2026-10-18 — İskelet kurulumu**
- Proje yapısı, `core/model.py` veri modeli, SPEC 01 ve testleri (41 test) hazırlandı.
- Testler bağımsız bir örnek çözümle doğrulandı: 41/41 geçti; bilerek eklenen 3 hatayı yakaladı.
- Yerel CI kuruldu: pre-commit, pre-push hook'ları ve `ci.ps1`. Actions sadece main'e PR'da çalışıyor.

## Açık sorular
_(yok)_

## Tamamlananlar
| SPEC | Konu | Tarih | Test sayısı |
|---|---|---|---|
| — | İskelet + yerel CI | 2026-10-18 | 12 (model) |

## Kurulum kontrol listesi (bir kez, kullanıcı)
- [ ] `powershell -ExecutionPolicy Bypass -File _kurulum\yerlestir.ps1`
- [ ] `.venv` oluşturuldu, `pip install -e ".[dev]"` yapıldı
- [ ] `git init`, `core.hooksPath`, `--chmod=+x` (README "Git + GitHub")
- [ ] GitHub private repo + ilk push
