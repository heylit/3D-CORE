"""SPEC 64 K4 — hazır iş emrinin çıktıları: program, takım listesi, süre, maliyet, iş föyü.

Program (Karar 4, durum/64 varsayılanı 3): SPEC 31 `post` çıktısı + POST yorumunun hemen ardından tek satır
`MES <mes_id> REV <revizyon>` yorumu (kontrolörün yorum sözdizimiyle). O satır çıkarılınca `post` çıktısıyla
bayt bayt aynı (ISO ve Sinumerik); Heidenhain'de satır numaraları kaydığı için yalnız yorum satırı sınanır.
Föy: render_html(build_job_sheet(...)) kodlayıcıyla sabitlenen çağrıyla bayt bayt (ortak.beklenen_foy).
`X-Sha256` = programın UTF-8 sha256'sı = `ciktilar.program_ozeti`.
SPEC 58 (süre, maliyet) main'de değilken `sure` ve `maliyet` 503 (durum/64 varsayılanı 5).
"""

from __future__ import annotations

import importlib.util
import re

import pytest

pytest.importorskip("pydantic")  # [web]: fastapi + pydantic

from tests.tezgah.mes.ortak import (
    API,
    DEPO,
    HAAS_M,
    HEI_M,
    IS_ADI,
    SIN_M,
    beklenen_foy,
    beklenen_foy_html,
    beklenen_post,
    govde,
    mes_satiri,
    ornek_tanim,
    sha,
)
from tezgah.mes import depo as mdepo


def _hazir(c, mid: str, profil: str = HAAS_M, rev: int = 1) -> dict:
    r = c.put(f"{API}/is-emirleri/{mid}", json=govde(mes_id=mid, revizyon=rev, tezgah=profil))
    assert r.status_code == 200, r.text
    d = mdepo.yukle(DEPO)
    mdepo.bagla(d, mid, IS_ADI)
    mdepo.hazirla(d, mid)
    J = c.get(f"{API}/is-emirleri/{mid}").json()
    assert J["durum"] == "hazir"
    return J


@pytest.mark.parametrize("profil", [HAAS_M, SIN_M])
def test_program_bayt_bayt(istemci, profil):
    """MES satırı çıkarılınca post çıktısıyla bayt bayt aynı; X-Sha256 ve program_ozeti tutuyor."""
    mid = "IE-4001"
    J = _hazir(istemci, mid, profil)
    r = istemci.get(f"{API}/is-emirleri/{mid}/program")
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith("text/plain")
    metin = r.content.decode("utf-8")
    assert r.headers["x-sha256"] == sha(metin) == J["ciktilar"]["program_ozeti"]
    k, kalan = mes_satiri(metin, profil, mid, 1)
    beklenen = beklenen_post(ornek_tanim(), profil)
    assert "\n".join(kalan).encode("utf-8") == beklenen.encode("utf-8")
    satir = metin.split("\n")[k]
    if profil == HAAS_M:
        assert satir == f"(MES {mid} REV 1)"
    else:
        assert satir == f"; MES {mid} REV 1"
    assert satir.isascii()


def test_program_heidenhain(istemci):
    """Heidenhain: satır numaraları kaydığı için yalnız POST yorumunun ardındaki MES yorum satırı sınanır."""
    mid = "IE-4002"
    J = _hazir(istemci, mid, HEI_M)
    r = istemci.get(f"{API}/is-emirleri/{mid}/program")
    metin = r.content.decode("utf-8")
    k, _ = mes_satiri(metin, HEI_M, mid, 1)
    assert re.fullmatch(rf"\d+ ; MES {mid} REV 1", metin.split("\n")[k])
    assert r.headers["x-sha256"] == sha(metin) == J["ciktilar"]["program_ozeti"]


def test_hazirla_profil_yok(istemci):
    """tezgah null ya da bilinmeyen profil adı → hazirla hata (uçta 422'ye çevrilen çekirdek hatası)."""
    for mid, tz in (("IE-4011", None), ("IE-4012", "BOYLE-TEZGAH-YOK")):
        istemci.put(f"{API}/is-emirleri/{mid}", json=govde(mes_id=mid, tezgah=tz))
        d = mdepo.yukle(DEPO)
        mdepo.bagla(d, mid, IS_ADI)
        with pytest.raises((ValueError, KeyError)):
            mdepo.hazirla(d, mid)
        assert istemci.get(f"{API}/is-emirleri/{mid}").json()["durum"] == "baglandi"


def test_program_revizyon_satiri(istemci):
    """Yeni revizyon yeni program: yorum satırı ve özet değişir (iş emri başına ayrı program)."""
    mid = "IE-4003"
    J1 = _hazir(istemci, mid, HAAS_M, rev=1)
    J2 = _hazir(istemci, mid, HAAS_M, rev=2)
    p2 = istemci.get(f"{API}/is-emirleri/{mid}/program").text
    assert f"(MES {mid} REV 2)" in p2.split("\n")
    assert J1["ciktilar"]["program_ozeti"] != J2["ciktilar"]["program_ozeti"]


def test_program_dondurulmus(istemci):
    """Programı iki kez istemek aynı baytları verir; depo.program_metni ile aynı."""
    mid = "IE-4004"
    _hazir(istemci, mid)
    a = istemci.get(f"{API}/is-emirleri/{mid}/program").content
    b = istemci.get(f"{API}/is-emirleri/{mid}/program").content
    assert a == b
    assert mdepo.program_metni(mdepo.yukle(DEPO), mid).encode("utf-8") == a


@pytest.mark.parametrize("profil", [HAAS_M, SIN_M])
def test_takimlar(istemci, profil):
    """Takım listesi föyün ToolRow'larından, aynı sırada (T1 kontur, T2 delik)."""
    mid = "IE-4101"
    _hazir(istemci, mid, profil)
    r = istemci.get(f"{API}/is-emirleri/{mid}/takimlar")
    assert r.status_code == 200, r.text
    L = r.json()
    satirlar = beklenen_foy(ornek_tanim(), profil).setups[0].tools
    assert [t["t_no"] for t in L] == [s.T for s in satirlar] == [1, 2]
    for t, s in zip(L, satirlar, strict=True):
        assert t["ad"] == s.name
        assert t["tur"] == s.kind
        assert t["D"] == pytest.approx(s.D, abs=1e-12)
        assert t["boy"] == pytest.approx(s.stickout if s.stickout is not None else s.flute_length, abs=1e-12)
        assert t["tutucu"] == (s.holder or "")
        assert t["sure_s"] == pytest.approx(s.time, rel=1e-12)
    assert istemci.get(f"{API}/is-emirleri/IE-4102/takimlar").status_code == 404


def test_takimlar_alindi_409(istemci):
    istemci.put(f"{API}/is-emirleri/IE-4103", json=govde(mes_id="IE-4103"))
    assert istemci.get(f"{API}/is-emirleri/IE-4103/takimlar").status_code == 409


@pytest.mark.parametrize("profil", [HAAS_M, SIN_M])
def test_is_foyu(istemci, profil):
    """İş föyü SPEC 38 çıktısıyla bayt bayt aynı; sha256(gövde) = ciktilar.foy_ozeti; dondurulmuş."""
    mid = "IE-4201"
    J = _hazir(istemci, mid, profil)
    r = istemci.get(f"{API}/is-emirleri/{mid}/is-foyu.html")
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith("text/html")
    html = r.content.decode("utf-8")
    assert r.content == beklenen_foy_html(ornek_tanim(), profil).encode("utf-8")
    assert sha(html) == J["ciktilar"]["foy_ozeti"]
    assert istemci.get(f"{API}/is-emirleri/{mid}/is-foyu.html").content == r.content


def test_is_foyu_bayat_degil(istemci):
    """Bağlı iş değişince föy 409 (bayat çıktı verilmez); yeniden hazirla yeni işin föyünü verir."""
    from tezgah import depo

    mid = "IE-4202"
    _hazir(istemci, mid)
    yeni = ornek_tanim(F=350.0)
    depo.kaydet(IS_ADI, yeni)
    assert istemci.get(f"{API}/is-emirleri/{mid}/is-foyu.html").status_code == 409
    mdepo.hazirla(mdepo.yukle(DEPO), mid)
    r = istemci.get(f"{API}/is-emirleri/{mid}/is-foyu.html")
    assert r.content == beklenen_foy_html(yeni, HAAS_M).encode("utf-8")
    p = istemci.get(f"{API}/is-emirleri/{mid}/program").content.decode("utf-8")
    _, kalan = mes_satiri(p, HAAS_M, mid, 1)
    assert "\n".join(kalan) == beklenen_post(yeni, HAAS_M)


SPEC58 = (
    importlib.util.find_spec("atolye.maliyet") is not None
    or importlib.util.find_spec("cam.maliyet") is not None
)


@pytest.mark.parametrize("uc", ["sure", "maliyet"])
def test_sure_maliyet(istemci, uc):
    """SPEC 58 yokken 503 ve mesaj; varsa sure.t_parca_s sayısal ve > 0 (58'le eşitlik 58 gelince)."""
    mid = "IE-4301"
    _hazir(istemci, mid)
    r = istemci.get(f"{API}/is-emirleri/{mid}/{uc}")
    if not SPEC58:
        assert r.status_code == 503, r.text
        assert isinstance(r.json()["detail"], str) and r.json()["detail"]
        return
    assert r.status_code in (200, 422), r.text
    if uc == "sure" and r.status_code == 200:
        S = r.json()
        assert S["t_parca_s"] > 0
        assert set(S) >= {"t_isleme_s", "t_yukle_s", "t_hazirlik_s", "t_parca_s"}


def test_hazirla_post_hatasi_422(istemci):
    """Post edilemeyen iş (tutucusuz takımlı örnek iş) → hazirla CamError; durum değişmez."""
    from cam.model import CamError

    mid = "IE-4401"
    istemci.put(f"{API}/is-emirleri/{mid}", json=govde(mes_id=mid))
    d = mdepo.yukle(DEPO)
    mdepo.bagla(d, mid, "flans-plakasi")
    with pytest.raises(CamError):
        mdepo.hazirla(d, mid)
    J = istemci.get(f"{API}/is-emirleri/{mid}").json()
    assert J["durum"] == "baglandi" and J["ciktilar"] is None
