# DURUM — SPEC 54 sağlamlık (hata mesajları, hatadan geri al, otomatik kayıt)

Dal: `claude/project-thread-uo3o39` (SPEC 37 dalı `claude/spec-37-proje-kabuk-trviuv` 4b31a59 üstünde) · Oturum: bulut

## Sıradaki adım
NotImplementedError iskeleti push edildi. Ayrı test oturumu `specs/54-saglamlik.md`'den testleri yazar; test
commit'i cherry-pick edilir, kod ayrı commit'te yazılır. Karar 9 (SPEC 37 K17 izin listesine `fileio.kurtarma` ve
`tezgah.hata` eklenmesi) kullanıcı onayı bekliyor; onaya kadar kabuk bu iki modülü import etmiyor.
Birleştirme: #70 (SPEC 37) birleştikten, `main` dala merge edildikten ve pytest + kapi yeşil olduktan sonra.

## Test durumu
| Tarih | Geçen | Kalan | Not |
|---|---|---|---|
| 2026-10-18 | — | K1–K12 | iskelet; testler henüz yok |

## Son oturum
**2026-10-18**
- SPEC metni taslaktan yazıldı (2 dakika kuralıyla onaylı); Kararlar 1–8 ve "Arayüz ayrıntıları" eklendi.
- İskelet: `fileio/kurtarma.py`, `fileio/parca_oku.py` (Karar 3), `tezgah/hata.py`; `Kabuk(…, kurtarma, klasor)`
  ve kurtarma yöntemleri; `GET/POST /api/proje/kurtarma`; `kabuk.ts` `hataKartiModeli`, `kurtarmaSecenekleri`.
- `*/model.py`, `geometry/part.py`, `pyproject.toml`, `DURUM.md` değişmedi. Karar 4: `model.py` mesajlarının K2'si
  ayrı arayüz PR'ı ister.
