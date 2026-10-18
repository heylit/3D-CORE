# DURUM — SPEC 24 tezgah

Dal: `claude/project-thread-c0lzh0` · Oturum: bulut

## Sıradaki adım
Testleri ayrı oturum yazacak; test commit'i cherry-pick edilince kod ayrı commit'te yazılır.

## Test durumu
| Tarih | Geçen | Kalan | Not |
|---|---|---|---|
| 2026-10-18 | — | — | İskelet (`NotImplementedError` / `Error("SPEC 24: uygulanmadı")`); test yok. |

## Son oturum
**2026-10-18**
- `pyproject.toml`: `[web]` (fastapi, uvicorn), `[dev]`'e httpx, `tezgah` komutu, `tezgah*` paketi.
- Python iskeleti: `tezgah/kopru.py`, `isler.py`, `sunucu.py`, `__main__.py`.
- Ön yüz iskeleti: `tezgah/arayuz/` (Vite + TypeScript + three.js), saf fonksiyonlar `src/zaman.ts`, `src/gcode.ts`,
  test kancası `src/kanca.ts`.
- K3, K5, K6 (süre, kontroller, sim ikili dizisi) SPEC 05 `main`'e girince yeniden onaylanıp en son yazılır.

## Açık sorular
- CI `.[dev,cad]` kuruyor; `tests/tezgah/` CI'da çalışsın diye kurulum satırına `web` eklenmeli
  (`.github` sahibi "Test bağımsızlığı CI kapısı" thread'i; koordinatöre bildirildi).
