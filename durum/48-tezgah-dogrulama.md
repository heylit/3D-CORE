# DURUM — SPEC 48 Gerçek tezgâh doğrulama programı

Dal: `claude/spec-06-cam-3d-09jwcj` · Oturum: bulut

## Sıradaki adım
Kod yazıldı; PR #114 GitHub CI'ı (pytest + kapi) yeşil olunca birleştirmek. Sonrası tezgâhta (kullanıcı):
S1 NLX 2500 `torna_2x`, S2 DMU 50 `freze_3x` / `freze_3arti2`.

## Test durumu
| Tarih | Geçen | Kalan | Not |
|---|---|---|---|
| 2026-10-18 | — | — | İskelet: tüm işlevler NotImplementedError |
| 2026-10-18 | 76 | 0 | Test commit'i 4bf7b63 (ayrı oturum) + kod; `tests/atolye/` 173 geçti |

## Son oturum
**2026-10-18**
- `specs/48-tezgah-dogrulama.md` onaylı taslaktan yazıldı (açık sorular → kararlar).
- `atolye/dogrulama.py` iskeleti; SPEC'in bıraktığı biçim ayrıntıları modül docstring'inde (profil özeti
  `verified` hariç, dosya adı ve hata mesajı, zincir kuralı, bağ denetimi girdileri, madde ayrıştırma).

- Kod: `atolye/dogrulama.py` (şema, sıra, ölçüm, bağ, hazırlık, HTML rapor); belgeye `## 7.` ve `## 8.` eklendi.
- Docstring dışı kararlar: `bos_kayit` ölçüm kalemlerini yalnız `olcum` basamağında doldurur; `job` verilip `gecti`
  ise föydeki her kalem ölçülmüş olmalı; `oku` dosya adındaki tarih / basamak / klasör adı kayıtla tutmazsa hata;
  `kaydet` var olan dosyanın üzerine yazmaz.

## Açık sorular
_(yok)_
