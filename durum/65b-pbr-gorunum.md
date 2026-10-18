# DURUM — SPEC 65b PBR görünüm

Dal: `claude/project-thread-9npdya` (oturumun verdiği dal; B2 iskeleti `7ec8f7d` üstünde, B2 birleşince main alınacak) · Oturum: bulut

## Sıradaki adım
Bağımsız test thread'inin test commit'ini cherry-pick et, kodu ayrı commit'te yaz.

## Test durumu
| Tarih | Geçen | Kalan | Not |
|---|---|---|---|

## Son oturum
**2026-10-18**
- Metin onaylandı (16:19); `specs/65b-pbr-gorunum.md` olarak eklendi (Arayüz kod bloğu yalnız `ruff format` ile hizalandı, içerik aynı).
- İskelet: `tezgah/gorunum.py` (`NotImplementedError`; `montaj_gorunumu` API gövdesi için), `tezgah/arayuz/src/gorunum.ts`
  (`malzemeOlustur`, `ortamKur`, `gorunumModu`, test kancası `window.__tezgah.gorunum` arayüzü `GorunumKanca`).
- Hata sınıfı `core.model.ModelError` (`tezgah.gorunum.ModelError` olarak da erişilir).
- `/api/gorunum` uç noktası `tezgah/sunucu.py`'ye kod commit'inde eklenecek; sahibi Tezgah thread'i (koordinatör üzerinden).

## Açık sorular
_(yok)_
