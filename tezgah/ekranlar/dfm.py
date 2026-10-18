"""
SPEC 61 K11 — DFM denetimi ucu: `GET /api/ekran/model/dfm`.

Sekme değil (uçsuz router, tuşsuz): uç `kur(app)` ile uygulamaya doğrudan bağlanır; model ekranının
dosyasına dokunmadan model bölümünü `paylasilan_bolum("model")` ile okur ve `tezgah.modelleme.insa` ile
katıyı kurar, `atolye.dfm.denetle` ile denetler.

Yanıt: {"bulgular": [Bulgu alanları], "tamam": bool, "sure_s": float, "uyarilar": [metin]}.
Her bulguda `yuzler` (Part yüz indisleri) var; model ekranı `GET /api/ekran/model/yuz/{index}` ile vurgular.
Takım kütüphanesi: Tezgah'ta seçili kütüphane yoksa repodaki örnek (`examples/takim_kutuphanesi.json`) ve
"örnek kütüphaneyle denetlendi" uyarısı (SPEC 61 Karar 2). Model kurulamazsa 422.
"""

from __future__ import annotations

from fastapi import FastAPI

from tezgah.ekranlar import Ekran

AD = "dfm"
YOL = "/api/ekran/model/dfm"


def model_dfm() -> dict:
    """Güncel modelin DFM raporu (SPEC 61 K11)."""
    raise NotImplementedError("SPEC 61 K11: model_dfm")


def kur(app: FastAPI) -> None:
    """`GET /api/ekran/model/dfm` ucunu uygulamaya bağlar."""
    app.add_api_route(YOL, model_dfm, methods=["GET"])


EKRAN = Ekran(ad=AD, baslik="DFM denetimi", sira=71, bagimli=("model",), kur=kur)
