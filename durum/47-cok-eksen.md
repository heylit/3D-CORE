# DURUM — SPEC 47b Tezgah çok eksen ekranı

Dal: `claude/project-thread-ol2w60` · Oturum: bulut · Metin: `specs/47-tezgah-ekranlari.md` (onay 2026-10-18 11:13)
Kapsam (SPEC 47 "Alt PR'lar"): K1 (çok eksen), K8–K13, K21, K22–K25 (çok eksen kısmı).
Taban: `main` + A3 iskeleti (`claude/project-thread-c0lzh0`, ec8362f, PR #86).

## Sıradaki adım
İskelet pushlandı. Ayrı test thread'i testleri yazar; test commit'i cherry-pick edilir, kod ayrı commit'te.
Kod SPEC 41 (PR #51), 42, 43, 44 ve A3 koduna bağlı; `main`'de olmayan modüller testlerde `importorskip`.

## Test durumu
| Tarih | Geçen | Kalan | Not |
|---|---|---|---|
| 2026-10-18 | — | — | İskelet (`NotImplementedError` / `Error("SPEC 47b: uygulanmadı")`); test yok. |

## Son oturum
**2026-10-18**
- Python: `tezgah/ekranlar/cok_eksen.py` (EKRAN: ad `cok_eksen`, tuş `5`, sıra 50; uçlar), `cok_eksen_kopru.py`
  (cok_json, kontroller, olaylar, sapma_ozeti, sim_ozeti, simule, parmak_izi, parametre_uygula, sure;
  noktalar/pozlar/sapma/dexel/govde `*_ikili` + `*_coz`), `cok_eksen_ornekler.py` (CokEksenIsi, ornek,
  tezgah_modeli, egik_yuz_3arti2, kubbe_5eksen, kubbe_carpisma).
- TS: `src/ekranlar/cok_eksen.ts` (EkranModulu), `src/ekranlar/cok_eksen_yardim.ts` (pozlarCoz, pozAl, dordey,
  dordeyMatris, slerp, pozAraDeger, zamandanIndeks, olayZamani, eklemSeridi).
- Küçük teknik seçimler (SPEC'in açık bıraktığı): `kubbe_5eksen` varsayılan profili `ac_besik_dar` (tarayıcıda
  `eksen_siniri` olayı görünsün; K10'un `ac_besik` hâli `ornek("kubbe_5eksen", profil="ac_besik")`);
  `dexel` ikilisinde görüntü başına ızgara başlığı; `/dexel` simülasyon yokken 409; durum dosyası alt PR'lar
  çakışmasın diye `durum/47-cok-eksen.md`.

## Açık sorular
- A3 `ekranlar()`, `EKRAN` vermeyen yardımcı modülleri (`cok_eksen_kopru`, `cok_eksen_ornekler`) atlamalı
  (SPEC 47 "Mimari ve dosyalar" bu dosyaları `tezgah/ekranlar/` altına koyuyor). Koordinatöre iletildi.
