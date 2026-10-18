# DURUM — SPEC 71 Chatter kararlılık lobu

Dal: `claude/spec-07-montaj-agaci-ejmdg5` (bulut oturumunun verdiği dal adı; main'den yeniden başlatıldı) · Oturum: bulut

## Sıradaki adım
Testler ayrı thread'den gelecek; cherry-pick sonrası kod ayrı commit'te. K7 (Kienzle köprüsü) arayüzü hazır (`kesme_katsayisi`, `lob_freze(malzeme=, fz=)`); 66 main'e girdi (6c559bb), K7 testleri ayrı thread'den gelecek.

## Test durumu
| Tarih | Geçen | Kalan | Not |
|---|---|---|---|
| 2026-10-18 | — | — | iskelet (`NotImplementedError`) |

## Son oturum
**2026-10-18 — iskelet**
- SPEC metni onaylı taslaktan `specs/71-chatter-lobu.md`'ye kondu (kullanıcı onayı 16:19 UTC).
- `cam/frf.py` (FRF, frf_csv, frf_modal, TakimFRF) ve `cam/chatter.py` (Lob, yonsel_katsayilar, lob_freze, lob_torna, karar) iskeletleri.
- Hata sınıfı `cam.model.CamError` (ValueError alt sınıfı): SPEC "ModelError" diyor, ama K10 yalnız `cam.model` importuna izin veriyor; cam paketinin hatası budur.
- `yonsel_katsayilar` K5'i doğrudan test edilebilir kılmak için açık; `profil` (SPEC 30 MachineProfile, isteğe bağlı) hata listesindeki devir sınırı için.

**2026-10-18 — K7 arayüzü**
- main (SPEC 66, 6c559bb) dala merge edildi.
- `kesme_katsayisi(malzeme, fz, phi_st, phi_ex)` iskeleti: K_t = kc11·h_m^(−mc). `malzeme` ördek tiplemeli
  (`kc11`, `mc` öznitelikleri): `malzeme.model.Malzeme` ya da `cam.kuvvet.KienzleMaterial`; K10 gereği import edilmez.
- `lob_freze`: `K_t` verilmezse `malzeme` + `fz` ile `kesme_katsayisi`; `K_r` verilmezse 0.3 ve `varsayilan_Kr=True`.

## Açık sorular
_(yok)_
