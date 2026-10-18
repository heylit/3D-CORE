# DURUM — SPEC 37 proje-kabuk

Dal: `claude/spec-37-proje-kabuk-trviuv` · Oturum: bulut

## Sıradaki adım
Kod yazıldı. PR'ın CI'da yeşil olması A3'ün (#86) birleşmesini bekliyor: REST / K14 testleri A3'ün
`uygulama(ekranlar=...)` ve `ekranlar()` gövdelerine dayanıyor (şimdilik NotImplementedError). A3 birleşince
`main` dala merge edilir, testler yeniden çalıştırılır, yeşilse PR birleştirilir.

## Test durumu
| Tarih | Geçen | Kalan | Not |
|---|---|---|---|
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
