# DURUM — SPEC 13 von Mises, düğüm gerilmesi ve CalculiX yazıcısı

Dal: `claude/project-thread-67phxl` · Oturum: bulut thread "SPEC 13 kodu"

## Sıradaki adım
PR birleştirme; K5–K6 (delikli plaka, L braket) SPEC 12 `mesh.tet_mesh` main'e girince koşar.

## Test durumu
| Tarih | Geçen | Kalan | Not |
|---|---|---|---|
| 2026-10-18 | 144 | 0 | SPEC 13 testleri (`--uygulanmamis-hata`) yeşil; gmsh gerektiren 6 test atlandı; ccx 2.21 ile T3D2 çapraz kontrolü geçti. |

## Son oturum
**2026-10-18 — kod**
- Testler ayrı oturumda yazıldı (dal `claude/project-thread-jt2kw0`, commit `87b1246`, bu dalda cherry-pick); kod ayrı commit'te.
- `core/post.py`: von_mises, principal_stresses (eigvalsh, azalan), nodal_stress_tensors (hacim ağırlıklı).
- `fileio/calculix.py`: to_inp / write_inp; T3D2 + C3D4, negatif hacimli tet'te 2. ve 3. düğüm yer değiştirir,
  sayılar `.12e`, aynı düğüm/DOF yükleri toplanır.

**2026-10-18 — iskelet**
- SPEC metni kullanıcı onaylı (2026-10-18 10:25 UTC, proje sohbetinde kart). `specs/13-calculix.md` eklendi.
- `core/post.py` (von_mises, principal_stresses, nodal_stress_tensors) ve `fileio/calculix.py` (to_inp, write_inp)
  `NotImplementedError` iskeletleri; `core/elements/__init__.py` sözleşmesine `volume` satırı.
- K5–K7 SPEC 12 (`mesh.tet_mesh`) birleşince yeşile döner.

## Açık sorular
_(yok)_
