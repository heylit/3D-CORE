# CalculiX çapraz kontrolü (Adım 4'ten itibaren)

Analitik çözümü olmayan problemler için aynı JSON modelden CalculiX `.inp`
dosyası üretilip iki çözücünün sonucu karşılaştırılacak (fark < %1).

Şimdilik boş. CalculiX kurulu değilse bu klasördeki testler
`pytest.importorskip` / `shutil.which("ccx")` ile atlanmalı.
