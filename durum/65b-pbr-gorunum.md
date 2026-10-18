# DURUM — SPEC 65b PBR görünüm

Dal: `claude/project-thread-9npdya` (oturumun verdiği dal; B2 iskeleti `7ec8f7d` üstünde, B2 birleşince main alınacak) · Oturum: bulut

## Sıradaki adım
SPEC 66 (`malzeme.kutuphane`) birleşince main'i al: kalan 5 K4 testi açılır. K7 testindeki ipucu zamanlaması test
thread'inde düzeltilecek (aşağıda). Sonra GitHub'da pytest + kapı yeşilse birleştir.

## Test durumu
| Tarih | Geçen | Kalan | Not |
|---|---|---|---|
| 2026-10-18 | 42 (pytest) | 5 uygulanmamış | K4'ün 5 testi SPEC 66 kütüphanesini bekliyor; sahte kütüphaneyle 7/7 geçti |
| 2026-10-18 | 4 (Playwright) | 1 | K7: kabuğun ipucu balonu 7 sn'de sönüyor, iki ekran görüntüsü arasında kayboluyor (test zamanlaması; `#ipucu` gizlenince geçer) |

## Son oturum
**2026-10-18**
- Metin onaylandı (16:19); `specs/65b-pbr-gorunum.md` olarak eklendi (Arayüz kod bloğu yalnız `ruff format` ile hizalandı, içerik aynı).
- İskelet: `tezgah/gorunum.py` (`NotImplementedError`; `montaj_gorunumu` API gövdesi için), `tezgah/arayuz/src/gorunum.ts`
  (`malzemeOlustur`, `ortamKur`, `gorunumModu`, test kancası `window.__tezgah.gorunum` arayüzü `GorunumKanca`).
- Hata sınıfı `core.model.ModelError` (`tezgah.gorunum.ModelError` olarak da erişilir).

## K9 performans (bilgi)
198 bin üçgen (4 küre × 49,5 bin), 1280×800, antialias, 60 kare ortalaması, bulut konteyneri **yazılım GPU'su**
(SwiftShader, readPixels ile eşzamanlı ölçüm): gerçekçi 399 ms, teknik 133 ms, analiz 117 ms/kare.
PBR (MeshPhysical + clearcoat/anisotropy + ortam) ≈ 3× teknik. Gerçek GPU'da yerelde yeniden ölçülmeli.
(Ölçüm RoomEnvironment ile yapıldı; stüdyo ortamı da tek PMREM dokusu, kare maliyeti aynı.)

## Kararlar
- K8: mevcut `index.html` Google Fonts yüklüyor; Tezgah thread'i ayrı PR'la kaldıracak (koordinatör 17:25).
  O PR'a kadar katı K8 testi xfail(strict); `index.html`'e bu SPEC dokunmaz.
- Montajı gösterecek ekran yoktu: yeni "Görünüm" sekmesi (A3 kaydı, `tezgah/ekranlar/gorunum.py` +
  `src/ekranlar/gorunum.ts`); `/api/gorunum` `Ekran.kur` ile bağlanır, `sunucu.py` değişmedi.

- Ortam haritası RoomEnvironment yerine kodla kurulan Z-yukarı stüdyo (koyu zemin geçişi, gök, ışık kutuları):
  RoomEnvironment Y-yukarı ve duvarları tekdüze, düz metal yüzler boz plastik gibi görünüyordu (K7). Dosya indirmez.
- Ekran açıkken sahne zemini düz opak renk (CSS gradyanı yerine); kapanınca önceki hâline döner.
- Varsayılan gri tablodan gelmez (`#a0a0a0`); tablo anahtarları yalnız `grup:` (GRUPLAR), `id:`, `bitim:`.
- Çelik ön ayarları gerçek metal F0'ına yakın açıldı (C45 `#b8bcc0`, pürüzlülük 0,25).
- Ön yüz görünümleri `GET /api/gorunum?montaj=ornek`'ten, geometri ekranın kendi ucundan alınır.

## Açık sorular
_(yok)_
