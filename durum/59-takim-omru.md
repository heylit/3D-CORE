# DURUM — SPEC 59 Takım ömrü (Taylor, Miner, planlı takım değişimi)

Dal: `claude/spec-14-cam-kurulum-05r8z1` · Oturum: bulut

## Sıradaki adım
Testler (ayrı oturum `session_01Fzcm2HhgA3vqUEjgoF3vCm`, commit `c6fe777`, cherry-pick) ve kod dalda. B2 (#121) main'e
girince main alınacak; o zamana kadar 38 test "uygulanmamış" (B2'nin `Taylor` / `Malzeme` gövdeleri).

## Test durumu
| Tarih | Geçen | Kalan | Not |
|---|---|---|---|
| 2026-10-18 | — | — | Yalnız iskelet; test yok. |
| 2026-10-18 | 32 | 38 uygulanmamış | B2 iskeletiyle. B2 gövdeleri geçici olarak (commit'lenmeden) doldurulunca 70/70. |

## Son oturum
**2026-10-18 — kod**
- `cam/omur.py`: Taylor sarmalayıcısı, freze (adım başına sabit Vc, `effective_diameter`), torna (r = r* ve x = 0'da
  bölme, 8 noktalı Gauss–Legendre; tam sayı olmayan m'de ikiye bölme), öneri (kenar / kardeş / gerek_yok), JSON.
- Yaylar da (G18) aynı noktalarda bölünür; yoğun yamuk integraliyle 1e-12 göreli tutuyor (test dışı denetim).

**2026-10-18 — iskelet**
- `specs/59-takim-omru.md` (onaylı metin), `cam/omur.py` arayüzü (K10 için `from_dict` de var), bu dosya.

## Açık sorular
- Yok. `Tool.tool_material` arayüz PR'ı ayrı; bu SPEC `tool_materials` eşlemiyle çalışır.
