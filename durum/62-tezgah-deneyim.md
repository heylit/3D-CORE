# DURUM — SPEC 62 tezgah-deneyim

Dal: `claude/spec-15-goruntuleyici-d318ku` (oturumun verdiği dal adı) · Oturum: bulut (kod), testler ayrı oturumda

## Aşamalar
- **Birinci aşama (bu PR):** komut paleti dilbilgisi (`tezgah/komut.py`), ISO 286 (`tezgah/tolerans.py`), sarma
  (`tezgah/sarma.py`), ekran uçları `POST /cozumle` ve `GET /sarma/{is}/{k}` (`tezgah/ekranlar/komut.py`),
  ön yüz `src/ekranlar/komut.ts` (palet "Komut" sekmesinde) ve `src/sarma.ts`. Kriterler: K1–K4, K7, K8 (sarma kısmı),
  K9 (cozumle ve sıra atma kısmı).
- **İkinci aşama (ayrı PR):** canlı fark (`fark.py`, K5; 58 ve 72 bekliyor), artımlı hesap (`artimli.py`, K6, K8),
  `POST /uygula` ve `POST /surukle` (SPEC 37 geri al, #70 bekliyor), `surukle.ts`, uçtan uca K10.
- **Kabuk kancası:** `Ctrl+K` → `komut` ekranının açılır katmanı; A3 sahibi (Tezgah thread'i) ayrı küçük PR.

## Sıradaki adım
Test oturumu birinci aşama testlerini yazar; test commit'i bu dala alınır, sonra kod ayrı commit'te.

## Test durumu
| Tarih | Geçen | Kalan | Not |
|---|---|---|---|
| 2026-10-18 | — | — | İskelet: metin + arayüz (NotImplementedError) |

## Arayüz notları (iskeletin sabitledikleri, testler bunlara dayanır)
- `cozumle` yerleşimsiz adım verir (K1); yerleşim ayrı `yerlestir(adim, secim, model) -> list[dict]` ile
  (secim = {"duzlem": SPEC 26 Duzlem, "nokta": [u, v]}; secim None → "Önce bir yüz seçin", K3). Adım sözlüğünün
  anahtarları `tezgah/komut.py` açıklamasında (SPEC 26 adlarıyla: thread, csk_d, csk_angle, cbore_d, cbore_depth).
- `Sarici.durum(k)` (ny, nx) float64 dizi; başvuru `cam.sim.simulate(**girdi).zmap_at(k)`.
- `tests/tezgah/test_komut.py` SPEC 24'ün `tezgah` komut testidir; SPEC 62 palet testleri başka adla
  (ör. `test_komut_paleti.py`) yazılmalı.
- SPEC 26'da yalnız eskiz / ekstrüzyon / delik adımı var: cep, pah, fillet, kanal komutları çözülür (K1) ama
  modele uygulanamaz; ikinci aşamada SPEC 26 adımı gerekir.
