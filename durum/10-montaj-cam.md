# DURUM — SPEC 10 Montaj-CAM bağlantısı ve bağlama (fikstür) kütüphanesi

Dal: `claude/spec-10-baglama-92agc0` · Oturum: bulut

## Sıradaki adım
SPEC onaylandı (kullanıcı, 2026-10-18 11:13). İskelet dalda; ayrı test oturumu testleri yazacak, sonra kod.
İskelet `cam.model.Fixture` (A0) ve `Frame` (PR #60) ister; ikisi main'e girene dek `cam/baglama.py` import edilemez.

## Test durumu
| Tarih | Geçen | Kalan | Not |
|---|---|---|---|
| 2026-10-18 | — | — | Sadece SPEC taslağı; kod ve test yok. |

## Son oturum
**2026-10-18 — iskelet**
- `cam/baglama.py`, `geometry/baglama_parca.py`: Arayüz bölümündeki imzalar, gövdeler `NotImplementedError`.

**2026-10-18 — SPEC**
- `specs/10-montaj-cam.md` yazıldı: mengene / üç çeneli ayna / pabuç ilkel listeleri, sıkma denetimi, temkinli
  bağlama üst yüzey haritası, SPEC 05 sonucuna ek fikstür çarpışması, montaj ↔ CAM köprüsü.
- Eski yol haritası satırı (`docs/yol-haritasi.md`, Dalga 3 "10-montaj-cam → 05, 07") ile çakışma yok; ad korundu.

## Açık sorular
- A0 `Fixture`'a `params` alanı ve `name`'de `/` (montaj yolu) isteği koordinatöre iletildi; kullanıcı A0'ı onayladı.
