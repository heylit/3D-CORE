# DURUM — SPEC 04b Punta, havşa ve kılavuz çevrimleri

Dal: `claude/spec-04b-cevrimler-9qxeq6` · Oturum: bulut

## Sıradaki adım
Kod tamam; A0 (#107) ve SPEC 30 ekleri (#98) dalda. #107 main'e girip GitHub Actions düzelince main'i al, CI yeşilse PR #81'i birleştir.

## Test durumu
| Tarih | Geçen | Kalan | Not |
|---|---|---|---|
| 2026-10-18 | — | — | Yalnız SPEC metni; kod ve test yok |
| 2026-10-18 | 33 | 140 uygulanmamış | Test commit db622a4 alındı; A0 yerelde taklit edilince K1–K7 123/123 yeşil |
| 2026-10-18 | 173 (A0 WIP yamasıyla) | 0 | #98 birleştirildi; K1–K13 hepsi yeşil, A0 yaması `arayuz/a0-cam-ek3-wip.patch` ile scratch kopyada |
| 2026-10-18 | 5805 (tam paket, `--uygulanmamis-hata`) | 0 | A0 dalı #107 (5eb08c1) birleştirildi; bağımsızlık kapısı tamam |

## Son oturum
**2026-10-18**
- `specs/04b-cevrimler.md` taslağı yazıldı (K1–K14, Örnek A/B altın metinleri).
- Arayüz eki A0 isteği (ToolKind SPOT/CHAMFER/TAP; Tool.tip_d, pitch, lead) ve SPEC 30/31 blok ekleri listesi
  koordinatöre gönderildi.
- Onay işlendi; `cam/cevrimler.py` NotImplementedError iskeleti.
- Test commit'i (db622a4) cherry-pick edildi, `main` (SPEC 30 #50 dahil) dala birleştirildi, kod yazıldı.

## Açık sorular
_(yok; 11:13 onayı: Sinumerik/Heidenhain kılavuzu CamError, Fanuc'ta her G84'ten önce M29 S)_
