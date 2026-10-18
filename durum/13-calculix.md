# DURUM — SPEC 13 von Mises, düğüm gerilmesi ve CalculiX yazıcısı

Dal: `claude/project-thread-67phxl` · Oturum: bulut thread "SPEC 13 kodu"

## Sıradaki adım
Test thread'inin commit'ini cherry-pick et, sonra kodu ayrı commit'te yaz.

## Test durumu
| Tarih | Geçen | Kalan | Not |
|---|---|---|---|

## Son oturum
**2026-10-18 — iskelet**
- SPEC metni kullanıcı onaylı (2026-10-18 10:25 UTC, proje sohbetinde kart). `specs/13-calculix.md` eklendi.
- `core/post.py` (von_mises, principal_stresses, nodal_stress_tensors) ve `fileio/calculix.py` (to_inp, write_inp)
  `NotImplementedError` iskeletleri; `core/elements/__init__.py` sözleşmesine `volume` satırı.
- K5–K7 SPEC 12 (`mesh.tet_mesh`) birleşince yeşile döner.

## Açık sorular
_(yok)_
