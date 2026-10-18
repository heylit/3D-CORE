"""
SPEC 24 — FastAPI sunucusu: REST uçları + derlenmiş ön yüzün (`arayuz/dist/`) statik servisi.

Uçlar:
    GET  /api/isler                 → {"sema": 1, "isler": [ad, ...]}
    GET  /api/is/{ad}               → Is JSON (kopru.is_json)
    GET  /api/is/{ad}/noktalar      → application/octet-stream (kopru.noktalar_ikili)
    GET  /api/is/{ad}/sim           → application/octet-stream (kopru.sim_ikili)
    POST /api/is/{ad}/parametre     gövde {"islem": int, "anahtar": str, "deger": float}
                                    → {"sema": 1, "is": Is, "sure_farki": yeni − eski toplam süre [s]}
Bilinmeyen iş → 404. Bilinmeyen işlem/anahtar → 422. Çekirdeğin `CamError` / `ModelError`'ı → 422,
gövde {"detail": hata metni}. Parametre değişikliği sunucu süreci boyunca o işte kalır.
Sunucu yalnızca 127.0.0.1'de dinler (`__main__`).
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI

DIST = Path(__file__).parent / "arayuz" / "dist"


def uygulama(dist: Path | None = DIST) -> FastAPI:
    """FastAPI uygulaması. `dist` varsa `/` altında statik servis edilir; None → yalnızca API."""
    raise NotImplementedError("SPEC 24: uygulanmadı")
