# DURUM — SPEC 04b Punta, havşa ve kılavuz çevrimleri

Dal: `claude/spec-04b-cevrimler-9qxeq6` · Oturum: bulut

## Sıradaki adım
Kod yazıldı (K1–K7). A0 (`cam/model.py`) ve SPEC 30 `RigidTap`/`Dwell` blokları birleşince K8–K13 için yazıcı/okuyucu bağlantısı.

## Test durumu
| Tarih | Geçen | Kalan | Not |
|---|---|---|---|
| 2026-10-18 | — | — | Yalnız SPEC metni; kod ve test yok |
| 2026-10-18 | 33 | 140 uygulanmamış | Test commit db622a4 alındı; A0 yerelde taklit edilince K1–K7 123/123 yeşil |

## Son oturum
**2026-10-18**
- `specs/04b-cevrimler.md` taslağı yazıldı (K1–K14, Örnek A/B altın metinleri).
- Arayüz eki A0 isteği (ToolKind SPOT/CHAMFER/TAP; Tool.tip_d, pitch, lead) ve SPEC 30/31 blok ekleri listesi
  koordinatöre gönderildi.
- Onay işlendi; `cam/cevrimler.py` NotImplementedError iskeleti.
- Test commit'i (db622a4) cherry-pick edildi, `main` (SPEC 30 #50 dahil) dala birleştirildi, kod yazıldı.

## Açık sorular
_(yok; 11:13 onayı: Sinumerik/Heidenhain kılavuzu CamError, Fanuc'ta her G84'ten önce M29 S)_
