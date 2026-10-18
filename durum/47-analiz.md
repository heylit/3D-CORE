# SPEC 47c — Tezgah Analiz ekranı: durum

- Dal: `claude/project-thread-3uq7jx`, PR #95. Test commit'i `66d277f` (ayrı oturum) cherry-pick edildi.
- Kod: `tezgah/ekranlar/analiz.py` (EKRAN, sekme `6`, uçlar `/api/ekran/analiz/...`), `_analiz_kopru.py`
  (saf köprü), `_analiz_ornekler.py` (`delikli_plaka` h = 5 + delik çevresinde Refine 1.25; `konsol_kiris` h = 5);
  ön yüz `src/ekranlar/analiz.ts`, `analiz_yardim.ts`. Yardımcı modüller `_` önekli (A3 keşfi atlar).
- Kararlar (kodu yazan oturum):
  - Delikli plakanın rijit cisim kilidi: ağda y = 50 çizgisinde düğüm garanti olmadığından y = 50 düzleminin
    toleransı h/2 (`tol_h`): x = 0 yüzünde y = 50'ye h/2'den yakın düğümler uy, bunların z = 0'dakileri uz.
  - Analitik satırlar: plaka Kt_g ↔ max σxx / 100 MPa (FEM ≈ 2.86, fark ≈ −%5.6); Kirsch kenar değeri 3σ yalnız
    bilgi; Kirsch eğrisi `egriler` alanında (sonda grafiğinde aynı doğru boyunca). Kiriş δ, δ_T ↔ u_max
    (tet4 eğilmede katı: fark ≈ −%16, `analitik_sapma` uyarısı beklenen davranış).
  - Delikli plakada σvM max ≈ 258 MPa > Re 235: `akma` kontrolü `hata` (örneğin gerçek sonucu).
  - Çözüm önbelleği: köprüde aynı (tanım, ağ) nesneleri için son 4 çözüm; ekranda tanım nesnesine bağlı.
    Ağ önbelleği (örnek, h, max_nodes) sıfırlamada da kalır (ağ girdinin saf fonksiyonu).
  - Kosul silme ve sonda (ikili POST) `EkranApi`'de olmadığından ön yüz bunları doğrudan `fetch` ile çağırır.
- Test düzeltmesi: testler `Part.bbox()` / `Part.volume()`'u yöntem gibi çağırıyordu (ikisi `@property`);
  test thread'inin `18cae6e` commit'i cherry-pick edildi.
- Doğrulama (yerel): `tests/tezgah/ekranlar` 62 geçti; vitest 100 geçti.
