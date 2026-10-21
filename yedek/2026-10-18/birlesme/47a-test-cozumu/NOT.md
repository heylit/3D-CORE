# 47a test çakışması çözümü (origin/main a138b7c ile)

Bu iki dosya `cf26455 + origin/main` birleştirmesinin çakışma çözümüdür. Main'in ekran başına bölüm yapısı korunmuş,
47a Plan kısmı ayrı bölüme taşınmıştır. Bu birleştirmede `tests/tezgah` koşusu 677 geçti, 91 uygulanmamış çıktı, hata yoktu.

Commit edilemedi: pre-commit ruff, kodlayıcının `tezgah/ekranlar/_plan_kopru.py:14` dosyasında I001 verdi. Bu kod dosyası
test oturumu tarafından değiştirilemez; büyük olasılıkla 7ad7a8f'de düzeltilmiştir.

Sırada: kodlayıcı 7ad7a8f'yi push eder → `git merge origin/main` → bu iki dosya buradan alınır → pytest → push.
