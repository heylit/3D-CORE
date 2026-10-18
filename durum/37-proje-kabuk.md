# DURUM — SPEC 37 proje-kabuk

Dal: `claude/spec-37-proje-kabuk-trviuv` · Oturum: bulut

## Sıradaki adım
Kod yazıldı; main ve A3 (#105) dalda. K14, SPEC 25 ekranları main'e girene kadar atlanıyor (test oturumunun
b4c672c düzeltmesi, SPEC 37'nin "A3, 24, 25 main'e girene kadar atlanır" kuralı). CI yeşilse PR birleştirilir.
B1 (proje dosyası sürümü) iskeleti ve testleri yerelde ayrı tutuluyor; #70 birleşince ayrı PR olur.

## Test durumu
| Tarih | Geçen | Kalan | Not |
|---|---|---|---|
| 2026-10-18 13:35 | fileio+tezgah 300, vitest 103 | K14 (SPEC 25 bekliyor) | A3 #105 birleştirildi, saplama yok |
| 2026-10-18 | fileio 63/63 (K1–K8) | — | |
| 2026-10-18 | kabuk 15 + 19 uygulanmamış | 19 | 19'u A3 NotImplementedError; geçici A3 taklidiyle 34/34 |
| 2026-10-18 | vitest 15/15 (K15) | K14, K16 | gerçek 24/25 ekranları ve A3 ön yüzü gerekli |

## Son oturum
**2026-10-18**
- SPEC 37 taslağı yazıldı: `.3dc` (belirlenimci, atomik, özetli zip), proje çapında geri al / yinele (bölüm
  anlık görüntüleri), kabuk yayılımı (bölüm bağımlılık grafiği, `Etki`, hata halinde bütün geri çevirme, önizleme),
  komut paleti eşleştirmesi (Türkçe katlama, parametreli komut), etki kartı ve sekme rozetleri.
- A3'ten beklenen kayıt arayüzü SPEC'in "A3'ten beklenen kayıt arayüzü" bölümünde; koordinatöre iletildi.
- `*/model.py` değişikliği gerekmiyor.

- SPEC metni önerilerle onaylandı (Dalga 5 toplu yazılı onay, 11:13); torna işleri ayrı `torna_isleri` bölümünde (A3 sürüm 2).
- `fileio/proje.py` NotImplementedError iskeleti.
- Bağımsız testler (fd3d1c5, 59c2fbd; test oturumu `claude/project-thread-hcoea0`) cherry-pick edildi; kod ayrı commit'te.
- A3'ten beklenen iki şey koordinatöre iletildi: `app.state.ekranlar` (kabuk ekran listesini buradan okur, yoksa
  `ekranlar()`), ön yüzde `baslat(kabuk, komutlar, tazele)` ve `ekranDegisti()` çağrıları, sekmelerde
  `data-testid="sekme"` / `data-ekran` ve rozette `data-testid="rozet"`.

## Açık sorular
_(yok)_

## B1 — proje dosyası sürümü ve göç (Dalga 6, SPEC 37 eki)
- Metin: `specs/37-ek-b1-proje-surumu.md` (onaylı, 2026-10-18 14:52). İskelet: `fileio/proje.py` içinde `Goc`,
  `GocKaydi` (gövdeler NotImplementedError), `GOCLER`, `Proje.goc`, `Proje.kaynak_yol`, `ac(yol, gocler)`, `incele`.
- Yorum (metindeki §3.3 + `guncel` "kayıt yoksa 1"): bir bölüm, `GocKaydi`'de en az bir adımı varsa sahiplenilmiş
  sayılır; adımı olmayan bölüm sahipsizdir ve SPEC 37 hoşgörüsüyle olduğu gibi korunur (K6).
- Sıradaki: ayrı test oturumunun testleri cherry-pick edilir, kod ayrı commit'te yazılır. PR #70 birleşince B1 ayrı PR.
