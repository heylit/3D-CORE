# SPEC 47c — Tezgah Analiz ekranı: durum

- Dal: `claude/project-thread-3uq7jx` (main + A3 iskeleti `ec8362f` birleştirildi).
- İskelet: `tezgah/ekranlar/analiz.py` (EKRAN + uçlar), `_analiz_kopru.py` (saf köprü), `_analiz_ornekler.py`
  (delikli_plaka, konsol_kiris); ön yüz `tezgah/arayuz/src/ekranlar/analiz.ts`, `analiz_yardim.ts`.
  Yardımcı modüller `_` önekli: A3 keşfi `_` ile başlayan modülü ekran olarak import etmez
  (SPEC metnindeki `analiz_kopru.py` / `analiz_ornekler.py` adlarının karşılığı).
- Sıradaki: bağımsız test commit'i (ayrı oturum), sonra kod.
