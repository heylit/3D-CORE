"""SPEC 64 K1 — şema anlık görüntüsü (`docs/mes-openapi-v1.json`) ve `/saglik`.

Alt şema: `/api/openapi.json`'daki `/api/mes/v1/` yolları + bunların (geçişli olarak) başvurduğu
`components/schemas` bileşenleri. Karşılaştırma kuralı (§1): anlık görüntüde olup çalışan şemada olmayan ya da
değeri değişen her şey KIRMIZI; yalnız eklenen (yeni yol, yeni bileşen, yeni isteğe bağlı alan) SARI: test
geçer, "anlık görüntüyü güncelle" uyarısı verir. Karşılaştırıcı bu dosyada, uygulamadan bağımsız yazıldı.
"""

from __future__ import annotations

import copy
import hashlib
import json
import warnings
from pathlib import Path

import pytest

pytest.importorskip("pydantic")  # [web]: fastapi + pydantic

from tests.tezgah.mes.ortak import API

ANLIK = Path(__file__).resolve().parents[3] / "docs" / "mes-openapi-v1.json"
REF = "#/components/schemas/"


def _anlik() -> dict:
    if not ANLIK.is_file():
        raise NotImplementedError("SPEC 64: docs/mes-openapi-v1.json henüz yok")
    return json.loads(ANLIK.read_text(encoding="utf-8"))


def _refler(x) -> set[str]:
    out: set[str] = set()
    if isinstance(x, dict):
        for k, v in x.items():
            if k == "$ref" and isinstance(v, str) and v.startswith(REF):
                out.add(v[len(REF) :])
            else:
                out |= _refler(v)
    elif isinstance(x, list):
        for v in x:
            out |= _refler(v)
    return out


def alt_sema(openapi: dict) -> dict:
    """MES yolları + geçişli bileşen şemaları: {"paths": {...}, "schemas": {...}}."""
    yollar = {p: v for p, v in openapi.get("paths", {}).items() if p.startswith(API + "/")}
    tum = openapi.get("components", {}).get("schemas", {})
    gerek, yigin = set(), list(_refler(yollar))
    while yigin:
        ad = yigin.pop()
        if ad in gerek or ad not in tum:
            continue
        gerek.add(ad)
        yigin += list(_refler(tum[ad]) - gerek)
    return {"paths": yollar, "schemas": {a: tum[a] for a in sorted(gerek)}}


def karsilastir(eski, yeni, yol: str = "") -> tuple[list[str], list[str]]:
    """(kırmızı: kaldırılan / değişen, sarı: eklenen) yol listeleri.

    Sözlükte yeni anahtar → eklenen; `required` listesine yeni ad → değişen (zorunlu alan eklemek kırıcıdır);
    diğer listeler ve yapraklar birebir.
    """
    kirmizi: list[str] = []
    sari: list[str] = []
    if isinstance(eski, dict) and isinstance(yeni, dict):
        for k in eski:
            if k not in yeni:
                kirmizi.append(f"{yol}/{k} kaldırıldı")
            else:
                r, s = karsilastir(eski[k], yeni[k], f"{yol}/{k}")
                kirmizi += r
                sari += s
        sari += [f"{yol}/{k} eklendi" for k in yeni if k not in eski]
    elif yol.endswith("/required") and isinstance(eski, list) and isinstance(yeni, list):
        if set(eski) != set(yeni):
            kirmizi.append(f"{yol} değişti: {eski} → {yeni}")
    elif eski != yeni:
        kirmizi.append(f"{yol} değişti: {eski!r} → {yeni!r}")
    return kirmizi, sari


def denetle(anlik: dict, canli: dict) -> None:
    """Kırmızıysa AssertionError; sarıysa UserWarning ile geçer."""
    kirmizi, sari = karsilastir(anlik, canli)
    assert not kirmizi, "MES v1 şeması kırıldı:\n" + "\n".join(kirmizi)
    if sari:
        warnings.warn(
            "MES v1 şemasına ekleme var, anlık görüntüyü güncelle:\n" + "\n".join(sari), stacklevel=2
        )


@pytest.fixture
def canli(istemci) -> dict:
    r = istemci.get("/api/openapi.json")
    assert r.status_code == 200
    return r.json()


def test_info_title(canli):
    assert canli["info"]["title"] == "Tezgah"


def test_anlik_goruntu_ayni(canli):
    """Çalışan uygulamanın MES alt şeması anlık görüntüyle aynı (ekleme varsa sarı uyarıyla geçer)."""
    anlik = _anlik()
    A = alt_sema(anlik) if "paths" in anlik and "components" in anlik else anlik
    C = alt_sema(canli)
    assert C["paths"], "openapi.json'da /api/mes/v1/ yolu yok"
    denetle(A, C)


def test_beklenen_yollar(canli):
    """§3 uç tablosu şemada var."""
    yollar = alt_sema(canli)["paths"]
    beklenen = {
        f"{API}/saglik": {"get"},
        f"{API}/is-emirleri/{{mes_id}}": {"put", "get"},
        f"{API}/is-emirleri": {"get"},
        f"{API}/is-emirleri/{{mes_id}}/iptal": {"post"},
        f"{API}/is-emirleri/{{mes_id}}/program": {"get"},
        f"{API}/is-emirleri/{{mes_id}}/takimlar": {"get"},
        f"{API}/is-emirleri/{{mes_id}}/sure": {"get"},
        f"{API}/is-emirleri/{{mes_id}}/maliyet": {"get"},
        f"{API}/is-emirleri/{{mes_id}}/is-foyu.html": {"get"},
        f"{API}/gonderimler": {"get"},
    }
    for p, yontem in beklenen.items():
        assert p in yollar, p
        assert yontem <= set(yollar[p]), (p, set(yollar[p]))
    ad = set(alt_sema(canli)["schemas"])
    assert {"IsEmri", "IsEmriDurumu", "GonderimKaydi"} <= ad


def test_alan_silme_kirmizi(canli):
    """Test içi yama: IsEmri'den bir alan silmek ya da türünü değiştirmek karşılaştırmayı kırmızı yapar."""
    A = alt_sema(canli)
    sil = copy.deepcopy(A)
    del sil["schemas"]["IsEmri"]["properties"]["adet"]
    with pytest.raises(AssertionError, match="adet"):
        denetle(A, sil)
    tur = copy.deepcopy(A)
    tur["schemas"]["IsEmri"]["properties"]["parca_no"] = {"type": "integer", "title": "Parca No"}
    with pytest.raises(AssertionError, match="parca_no"):
        denetle(A, tur)
    yol = copy.deepcopy(A)
    del yol["paths"][f"{API}/gonderimler"]
    with pytest.raises(AssertionError, match="gonderimler"):
        denetle(A, yol)


def test_yeni_istege_bagli_alan_sari(canli):
    """Yeni isteğe bağlı alan (required'a girmeden) sarı: uyarıyla geçer."""
    A = alt_sema(canli)
    ek = copy.deepcopy(A)
    ek["schemas"]["IsEmri"]["properties"]["oncelik"] = {"type": "integer", "title": "Oncelik", "default": 0}
    with pytest.warns(UserWarning, match="oncelik"):
        denetle(A, ek)
    # aynı alan zorunlu yapılırsa kırmızı
    zor = copy.deepcopy(ek)
    zor["schemas"]["IsEmri"]["required"] = [*zor["schemas"]["IsEmri"].get("required", []), "oncelik"]
    with pytest.raises(AssertionError, match="required"):
        denetle(A, zor)


def test_saglik(istemci):
    r = istemci.get(f"{API}/saglik")
    assert r.status_code == 200, r.text
    J = r.json()
    assert J["api"] == "v1"
    assert isinstance(J["tezgah_surum"], str) and J["tezgah_surum"]
    _anlik()
    assert J["sema_ozeti"] == hashlib.sha256(ANLIK.read_bytes()).hexdigest()
