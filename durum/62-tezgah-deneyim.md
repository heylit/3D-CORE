# DURUM — SPEC 62 tezgah-deneyim

Dal: `claude/spec-15-goruntuleyici-d318ku` (oturumun verdiği dal adı) · Oturum: bulut (kod), testler ayrı oturumda

## Aşamalar
- **Birinci aşama (#134, birleşti e9e455c):** komut paleti dilbilgisi, ISO 286, sarma, `POST /cozumle`,
  `GET /sarma/{is}/{k}`, `komut.ts` (Ctrl+K katmanı), `sarma.ts`. K1–K4, K7, K8 (sarma), K9.
- **İkinci aşama a (bu PR):** `fark.py` (K5; süre 72 birleşene kadar SPEC 05 `move_time` ile, maliyet yok),
  `artimli.py` (K6, K8 artımlı kısmı), `POST /uygula`, `POST /surukle`, `surukle.ts`.
- **İkinci aşama b (sonra):** 72 süresi ve 58 maliyeti farka bağlanır; uçtan uca K10 (kanca PR'ı ve fark
  paneli gerekiyor).
- **Kabuk kancası:** `Ctrl+K` → palet; Tezgah thread'inin ayrı PR'ı.

## Sıradaki adım
İkinci aşama a iskeleti push edildi; testleri ayrı thread yazacak, sonra kod ayrı commit'te.

## İkinci aşama a arayüz notları
- Plan ekranda `examples/takim_kutuphanesi.json` + `AlMg3`, stok = parça kutusu + 1 mm (XY ve üst, alt 0).
  Not: SPEC 26 flanşında `plan_mill` stok payı 2 mm iken `CamError("Ofset halkası kapanmadı")` veriyor
  (cam/offset, açık bölge); 0 ve 1 mm'de çalışıyor. Testler 1 mm payla kurulmalı.
- `fark.plan_farki(eski, yeni, sure_eski, sure_yeni, maliyet=None)`: süreler `plan.ops` sırasıyla liste.
  Anahtar `feature|kind` (+ "#k"). `fark_json` JSON biçimi.
- `artimli.Onbellek(boyut=64)`: `insa`, `insa_ve_planla`, `istatistik()` = {adim_isabet, adim_kacirma,
  plan_isabet, plan_kacirma}, `temizle()`. `olcu_degistir(model, adim, olcu, deger)` saf yardımcı.
- `/surukle` önizlemedir; bırakınca ön yüz `/api/ekran/model/` PUT eder. `/uygula` modeli değiştirir, SPEC 37
  ara katmanı geri al kaydını tutar.
- `surukle.ts`: `geciktir(f, ms=150, zamanlayici)` → {cagir, hemen, iptal, bekliyor}; `SiraSayaci`.

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
