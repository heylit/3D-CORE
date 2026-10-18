# DURUM — SPEC 68a Doğrusal burkulma (geometrik rijitlik + özdeğer)

Dal: `claude/project-thread-gmmhu4` · Oturum: bulut thread "FEM çubuk (SPEC 01)" (68a kodlayıcısı)

## Sıradaki adım
Aşama 1 (tet4) PR #141'de: GitHub'da pytest + kapı yeşilse birleştir.
Aşama 2: 67a (#122, tet10) birleşince tet10 maddeleri + K7; 67b birleşince K8 (`analiz/burkulma.py`).

## Test durumu
| Tarih | Geçen | Kalan | Not |
|---|---|---|---|
| 2026-10-18 | — | — | İskelet; 68a testleri henüz yok. |
| 2026-10-18 | 45 | 0 | tet4 aşaması; test commit `280b963` (ayrı oturum), kod ayrı commit. k=8 slow ~60 s. |

## Son oturum
**2026-10-18 — tet4 kodu**
- Testler ayrı oturumda yazıldı (dal `claude/project-thread-1kzji0`, commit `280b963`, iskeletin üstünde; ileri sarıldı, iz korundu).
- `tet4.kg`: `V · (GᵀSG) ⊗ I₃`. `assemble_Kg`: `assemble_M` deseni. `buckling`: `solve` ile u0, `(−Kg_ff) φ = ν K_ff φ`,
  n_f ≤ 300 yoğun `eigh`, aksi `eigsh(which="LM")`; `λ = 1/ν`, |ν| ≤ 1e-10·max|ν| → λ = ∞; max|ν| ≤ 1e-14 → `ModelError`.
- Konsol (tet4, λ1·P): k=1 39 142, k=2 18 157, k=4 12 703, k=8 11 286 > 10 794.88 (yukarıdan, azalan).
- Test yazarının varsayımları (SPEC metni değişmedi):
  1. K2 paydası `P·∫(w')² dz` (metindeki "P/L ∫" çubuk Kg'si ile boyutça tutarsız); çubuk z ekseninde 2×2×40,
     σzz = P/A doğrudan sigma0; w = sin(πz/L) ve (z/L)².
  2. K1 tam formül `Kg[3a+i, 3b+k] = δ_ik V ∇N_aᵀ S ∇N_b`; Voigt kayma bileşeni tensör bileşenidir.
  3. K5 tet4: çekmede bütün λ < 0 ve λ_çekme = −λ_basma (göreli 1e-6); "−10 794.88/P'ye %1" maddesi tet4
     kilitlenmesi yüzünden tet10 aşamasına kaldı.
  4. K3 tet4: her k'da λ1·P > P_cr, k = 2 → 4 → 8 azalır (k = 8 slow).
  5. K6'ya ek: serbest DOF yok, gerilmesiz model, n_modes = −1; assemble_Kg'de eksik sigma0 ve bar1d.
  6. K9: izinli import'lar numpy, scipy, core, __future__, dataclasses, typing, math, collections
     (bu yüzden `numbers` yerine `isinstance(n, (int, np.integer))`).

**2026-10-18 — Onay ve iskelet**
- SPEC metni kullanıcı tarafından onaylandı (16:19 UTC, Dalga 7 toplu yazılı onayı, "önerileriyle").
- `NotImplementedError` iskeleti: `core/burkulma.py` (`BucklingResult` dataclass gerçek), `tet4.kg`, `assemble_Kg`;
  `core/elements/__init__.py` sözleşmesine `kg` satırı.
- `specs/68a-burkulma.md`'ye arayüz ayrıntısı eklendi: `sigma0` biçimi (eleman id → `(6,)` Voigt), `assemble_Kg` hataları.

## Açık sorular
_(yok)_
