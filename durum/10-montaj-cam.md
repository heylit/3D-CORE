# DURUM — SPEC 10 Montaj-CAM bağlantısı ve bağlama (fikstür) kütüphanesi

Dal: `claude/spec-10-baglama-92agc0` · Oturum: bulut

## Sıradaki adım
SPEC metni kullanıcı onayı bekliyor; onaydan sonra `NotImplementedError` iskeleti (A0 `Fixture`, PR #60 `Frame`,
PR #53 `Part.moved` / `common` dallarının üstüne), ayrı test oturumu, sonra kod.

## Test durumu
| Tarih | Geçen | Kalan | Not |
|---|---|---|---|
| 2026-10-18 | — | — | Sadece SPEC taslağı; kod ve test yok. |

## Son oturum
**2026-10-18 — SPEC**
- `specs/10-montaj-cam.md` yazıldı: mengene / üç çeneli ayna / pabuç ilkel listeleri, sıkma denetimi, temkinli
  bağlama üst yüzey haritası, SPEC 05 sonucuna ek fikstür çarpışması, montaj ↔ CAM köprüsü.
- Eski yol haritası satırı (`docs/yol-haritasi.md`, Dalga 3 "10-montaj-cam → 05, 07") ile çakışma yok; ad korundu.

## Açık sorular
- A0 `Fixture`'a `params` alanı ve `name`'de `/` (montaj yolu) isteği "CAM model arayüzü" thread'ine iletilecek.
