# DURUM — SPEC 68a Doğrusal burkulma (geometrik rijitlik + özdeğer)

Dal: `claude/project-thread-gmmhu4` · Oturum: bulut thread "FEM çubuk (SPEC 01)" (68a kodlayıcısı)

## Sıradaki adım
Aşama 1 (tet4: K1, K2, K3'ün tet4 maddesi, K5, K6, K9): test commit'i cherry-pick, sonra kod.
Aşama 2: 67a (#122, tet10) birleşince tet10 maddeleri + K7; 67b birleşince K8 (`analiz/burkulma.py`).

## Test durumu
| Tarih | Geçen | Kalan | Not |
|---|---|---|---|
| 2026-10-18 | — | — | İskelet; 68a testleri henüz yok. |

## Son oturum
**2026-10-18 — Onay ve iskelet**
- SPEC metni kullanıcı tarafından onaylandı (16:19 UTC, Dalga 7 toplu yazılı onayı, "önerileriyle").
- `NotImplementedError` iskeleti: `core/burkulma.py` (`BucklingResult` dataclass gerçek), `tet4.kg`, `assemble_Kg`;
  `core/elements/__init__.py` sözleşmesine `kg` satırı.
- `specs/68a-burkulma.md`'ye arayüz ayrıntısı eklendi: `sigma0` biçimi (eleman id → `(6,)` Voigt), `assemble_Kg` hataları.

## Açık sorular
_(yok)_
