# DURUM — SPEC 62 tezgah-deneyim

Dal: `claude/spec-15-goruntuleyici-d318ku` (oturumun verdiği dal adı) · Oturum: bulut (kod), testler ayrı oturumda

## Aşamalar
- **Birinci aşama (bu PR):** komut paleti dilbilgisi (`tezgah/komut.py`), ISO 286 (`tezgah/tolerans.py`), sarma
  (`tezgah/sarma.py`), ekran uçları `POST /cozumle` ve `GET /sarma/{is}/{k}` (`tezgah/ekranlar/komut.py`),
  ön yüz `src/ekranlar/komut.ts` (Ctrl+K açılır katmanı, sekme değil) ve `src/sarma.ts`. Kriterler: K1–K4, K7, K8 (sarma kısmı),
  K9 (cozumle ve sıra atma kısmı).
- **İkinci aşama (ayrı PR):** canlı fark (`fark.py`, K5; 58 ve 72 bekliyor), artımlı hesap (`artimli.py`, K6, K8),
  `POST /uygula` ve `POST /surukle` (SPEC 37 geri al, #70 bekliyor), `surukle.ts`, uçtan uca K10.
- **Kabuk kancası:** `Ctrl+K` → `komut` ekranının açılır katmanı; A3 sahibi (Tezgah thread'i) ayrı küçük PR.

## Sıradaki adım
Birinci aşama kodu ve testleri dalda; CI yeşilse birleşir. Sonra ikinci aşama (#70, 58, 72 bekliyor) ve
Tezgah thread'inin Ctrl+K kanca PR'ı.

## Test durumu
| Tarih | Geçen | Kalan | Not |
|---|---|---|---|
| 2026-10-18 | — | — | İskelet: metin + arayüz (NotImplementedError) |
| 2026-10-18 | 104 py + 10 vitest | 0 | Birinci aşama kodu; testler 21a2461 (ayrı oturum, cherry-pick 41f2cb2) |

## Arayüz notları (iskeletin sabitledikleri, testler bunlara dayanır)
- `cozumle` yerleşimsiz adım verir (K1); yerleşim ayrı `yerlestir(adim, secim, model) -> list[dict]` ile
  (secim = {"duzlem": SPEC 26 Duzlem, "nokta": [u, v]}; secim None → "Önce bir yüz seçin", K3). Adım sözlüğünün
  anahtarları `tezgah/komut.py` açıklamasında (SPEC 26 adlarıyla: thread, csk_d, csk_angle, cbore_d, cbore_depth).
- `Sarici.durum(k)` (ny, nx) float64 dizi; başvuru `cam.sim.simulate(**girdi).zmap_at(k)`.
- `tests/tezgah/test_komut.py` SPEC 24'ün `tezgah` komut testidir; SPEC 62 palet testleri başka adla
  (ör. `test_komut_paleti.py`) yazılmalı.
- SPEC 26'da yalnız eskiz / ekstrüzyon / delik adımı var: cep, pah, fillet, kanal komutları çözülür (K1) ama
  modele uygulanamaz; ikinci aşamada SPEC 26 adımı gerekir.
- `GET /sarma/{is}/{k}` SPEC metnine göre SPEC 24 `sim_ikili` biçimindedir: k anındaki yüzey, başlangıç
  yüzeyinden (z_ust) farklı hücre başına tek olay, olay k'si = k. `kopru.sim_yuzey(veri, k)` = `zmap_at(k)` (float32).
  Bilinmeyen iş 404, k ∉ 0..n 422. Ön yüzde `sarmaCoz(veri, k)` (k parametresi iskelete eklendi) ve `SarmaOnbellek`.
- `POST /cozumle` hatası 422, gövde üst düzeyde `{detail, oneriler, okumalar}` (SPEC metni).
- Kabuk kancası imzası (Tezgah thread'i): `komut.ts` varsayılan dışa aktarım vermez; `paletAc(kabuk, komutlar)`,
  `paletKapat()`, `paletAcik()`. Saf: `yanitGecerliMi(yanitSira, sonGonderilen)`, `komutSuz(komutlar, metin)`.
  Sunucudaki `komut` ekranının uçları olduğu için `/api/ekranlar`'da görünür; ön yüz modülü olmadığından kapalı
  sekme olur. Kabuk bu ekranı sekmeden gizlemeli (kanca PR'ı).
- M8 kılavuz matkabı: K1 6.8 bekler (ISO 2306 tablosu, `KILAVUZ`); SPEC 23 geometrisi d_n − P = 6.75. Palet `d`
  alanına tablodan 6.8 yazar; ince hatvede d_n − P.
