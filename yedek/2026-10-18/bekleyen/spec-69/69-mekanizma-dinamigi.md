# DURUM — SPEC 69 Mekanizma dinamiği

Dal: `claude/project-thread-fe0oon` · PR #140 · Oturum: bulut (kod), testler ayrı thread (`claude/project-thread-71up4b`, 8ac24a9)

## Sıradaki adım
K7 (parça köprüsü, `kutleler_parcadan`) B2 + 66 main'e girince: `Component.material` → `rho`, `geometry.props.mass_props` → `Kutle`.

## Test durumu
| Tarih | Geçen | Kalan | Not |
|---|---|---|---|
| 2026-10-18 | 27 (test_dinamik.py) | K7 (1, B2/66 yokken atlanıyor) | Krank–biyel torku ~1e-9, sarkaç ~5e-9 göreli |

## Son oturum
**2026-10-18**
- `assy/dinamik.py`: konum SPEC 33 `drive`; hız `[Φ_q; sürücü satırı] ẋ = [0; q̇]`; ivme hız çözümünün beş noktalı
  merkezi farkı (h = 1e-4·T, T = t aralığı); Newton–Euler genelleştirilmiş kuvveti; `Aᵀλ = Q` en küçük kareler.
- `belirsiz` = SPEC 33 `mobility().redundant > 0` (düzlemsel mekanizmalar uzayda fazla kısıtlı sayılır; tork yine tek).
- Dış kuvvet: F kütle merkezine, M serbest moment, dünya çerçevesinde. Atalet J yarı pozitif tanımlı kabul edilir
  (noktasal kütle J = 0 olabilir), negatif özdeğer → ModelError.
- `assy/mates.py::rodrigues` küçük açı kesmesi kaldırıldı (L = 250 mm krank–biyelde drive son adımda takılıyordu).

## Açık sorular
- `specs/08-kisitlar.md`'deki "`|ω| < 1e-12` → birim" satırının güncellenmesi kullanıcı onayında.
