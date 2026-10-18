# DURUM — SPEC 26 tezgah-modelleme

Dal: `claude/project-thread-uo3o39` · Oturum: bulut

## Sıradaki adım
Kod yazıldı (testler 53039a7 + 4dfe748 cherry-pick, kod ayrı commit). PR #92: pytest + kapi yeşil olunca birleşir.
Açık: K11 eskiz e2e testinin afterEach'i, testin kendisinin beklediği 422 çelişki yanıtında Chromium'un
yazdığı "Failed to load resource ... 422" konsol iletisini hata sayıyor; test thread'ine soruldu (test değiştirilmedi).

## Test durumu
| Tarih | Geçen | Kalan | Not |
|---|---|---|---|
| 2026-10-18 | pytest 4963 (36 atlandı), vitest 108, e2e 3/4 | e2e K11 eskiz: yalnız afterEach konsol kuralı | tam takım yerelde |

## Son oturum
**2026-10-18**
- SPEC yazıldı ve onaylandı (10:38). SPEC 17 (#39) ve 24 (#40) main'de.
- İskelet: `geometry/extrude.py`, `tezgah/ifade.py`, `tezgah/modelleme.py`, `tezgah/model_kopru.py`,
  `tezgah/arayuz/src/eskiz.ts`.
- Ek A (11:36): uçlar A3 ekran kaydında, `tezgah/ekranlar/model.py` + `src/ekranlar/model.ts`, `/api/ekran/model/`.
  Dal #86'nın (A3 iskeleti, ec8362f) üstünde; `sunucu.py` değişikliği geri alındı.

- Kod: `model_kopru` (çözüm/rapor JSON, yüz başına ağ ikilisi, Tezgah'a gönder: yüzey → cep → iç/dış kontur → delik),
  `ekranlar/model.py` (uçlar; PUT yanıtına `hacim`; eskiz çözümüne isteğe bağlı `olculer`/`parametreler` → "=genislik"
  sunucuda hesaplanır; gönderilen iş `model-<ad>` adıyla depoya eklenir), `src/ekranlar/model.ts` (3B sahnede eskiz,
  yakalama → kısıt, ölçü kutusu, çelişki kartı, sürükleme, parametre tablosu, geçmiş şeridi, Ctrl Z / Ctrl Shift Z).

## Açık sorular
- e2e K11 eskiz: beklenen 422'nin tarayıcı konsol iletisi (bkz. Sıradaki adım).
