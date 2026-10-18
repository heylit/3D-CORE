# DURUM — SPEC 04b Punta, havşa ve kılavuz çevrimleri

Dal: `claude/spec-04b-cevrimler-9qxeq6` · Oturum: bulut

## Sıradaki adım
SPEC metni kullanıcı onayı bekliyor (açık sorular 1–2); onaydan sonra `NotImplementedError` iskeleti.

## Test durumu
| Tarih | Geçen | Kalan | Not |
|---|---|---|---|
| 2026-10-18 | — | — | Yalnız SPEC metni; kod ve test yok |

## Son oturum
**2026-10-18**
- `specs/04b-cevrimler.md` taslağı yazıldı (K1–K14, Örnek A/B altın metinleri).
- Arayüz eki A0 isteği (ToolKind SPOT/CHAMFER/TAP; Tool.tip_d, pitch, lead) ve SPEC 30/31 blok ekleri listesi
  koordinatöre gönderildi.

## Açık sorular
1. Sinumerik / Heidenhain'de kılavuz: `CamError` (öneri) mi, doğal `CYCLE84` / `CYCL DEF 207` mi?
2. Fanuc: her `G84`'ten önce `M29 S` (öneri) mi, parametreye mi bırakılsın?
