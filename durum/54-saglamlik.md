# DURUM — SPEC 54 sağlamlık (hata mesajları, hatadan geri al, otomatik kayıt)

Dal: `claude/project-thread-uo3o39` (SPEC 37 dalı `claude/spec-37-proje-kabuk-trviuv` 4b31a59 üstünde) · Oturum: bulut

## Sıradaki adım
Kod tamam: testler d921a16, b227ebf, 116a4d4 ve işaret kaldırma 9aafa3b alındı; SPEC 37 a8e18b5 ve `main` dala
merge edildi, `sketch/solver.py` çelişki mesajı §1 biçiminde (durum 10). Kalan: #70 birleşince `main` yeniden
alınır, CI yeşilse PR birleşir. Durum 11 / 11b (`cam/model.py`) Karar 4 arayüz PR'ını bekler.

## Test durumu
| Tarih | Geçen | Kalan | Not |
|---|---|---|---|
| 2026-10-18 | — | K1–K12 | iskelet; testler henüz yok |
| 2026-10-18 | fileio 33, saglamlik 64, tezgah (A3'süz) | REST 33 uygulanmamış | REST, `main` + `app.state.ekranlar` geçici yamasıyla yerelde yeşil; durum 10 `main` gerektirir |

## Son oturum
**2026-10-18**
- SPEC metni taslaktan yazıldı (2 dakika kuralıyla onaylı); Kararlar 1–8 ve "Arayüz ayrıntıları" eklendi.
- İskelet: `fileio/kurtarma.py`, `fileio/parca_oku.py` (Karar 3), `tezgah/hata.py`; `Kabuk(…, kurtarma, klasor)`
  ve kurtarma yöntemleri; `GET/POST /api/proje/kurtarma`; `kabuk.ts` `hataKartiModeli`, `kurtarmaSecenekleri`.
- `*/model.py`, `geometry/part.py`, `pyproject.toml`, `DURUM.md` değişmedi. Karar 4: `model.py` mesajlarının K2'si
  ayrı arayüz PR'ı ister.
- Kod: `fileio/kurtarma.py`, `fileio/parca_oku.py`, `tezgah/hata.py`, kabuk otomatik kayıt / hata işleyicileri,
  `kabuk.ts` hata kartı ve kurtarma kutusu; §1 mesajları `assy/solver.py`, `core/solver.py`, `geometry/boolean.py`,
  `geometry/fillet.py` (öneride `max_fillet` sınırı), `fileio/step_montaj.py`, `fileio/proje.py` (`ac` dosya adı öneki).
| 2026-10-18 | tümü (main + SPEC 37 a8e18b5 ile) | 11 / 11b xfail (Karar 4) | durum 10 yeşil; K14 SPEC 25'e kadar atlanıyor |
