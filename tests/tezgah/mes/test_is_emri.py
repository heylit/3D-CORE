"""SPEC 64 — iş emri uçları: K2 oluşturma ve eş-etkililik, K3 durum makinesi, K5 yoklama, K6 gönderimler,
K9 hata kuralı.

Durum geçişleri `baglandi` / `hazir` / `gonderildi` için REST ucu yoktur (Tezgah tarafının işi); testler
bunları `tezgah.mes.depo` fonksiyonlarıyla depo dosyasına yazar ve sonucu HTTP uçlarından okur (uçlar
dosyanın güncel hâlini görür). Bütün istemciler `raise_server_exceptions=True`: hiçbir senaryoda 500 yok (K9).
"""

from __future__ import annotations

import pytest

pytest.importorskip("pydantic")  # [web]: fastapi + pydantic

from tests.tezgah.mes.ortak import API, DEPO, IS_ADI, KAYIT, gonderim_satiri, govde, ornek_tanim, sha
from tezgah.mes import depo as mdepo


def _put(c, g: dict):
    return c.put(f"{API}/is-emirleri/{g['mes_id']}", json=g)


def _durum(c, mes_id: str) -> dict:
    r = c.get(f"{API}/is-emirleri/{mes_id}")
    assert r.status_code == 200, r.text
    return r.json()


def _bagla_hazirla(mes_id: str, hazirla: bool = True) -> None:
    d = mdepo.yukle(DEPO)
    mdepo.bagla(d, mes_id, IS_ADI)
    if hazirla:
        mdepo.hazirla(d, mes_id)


# ------------------------------------------------------------------ K2 oluşturma ve eş-etkililik


def test_put(istemci):
    g = govde()
    r1 = _put(istemci, g)
    assert r1.status_code == 200, r1.text
    J = r1.json()
    assert J["is_emri"] == g
    assert J["durum"] == "alindi"
    assert J["is_adi"] is None and J["ciktilar"] is None
    assert isinstance(J["degisiklik"], int) and J["degisiklik"] >= 1
    assert isinstance(J["uyarilar"], list)
    # aynı gövde ikinci kez: aynı yanıt, degisiklik artmıyor
    r2 = _put(istemci, g)
    assert r2.status_code == 200
    assert r2.json() == J
    assert _durum(istemci, g["mes_id"]) == J
    assert istemci.get(f"{API}/is-emirleri", params={"sonra": J["degisiklik"]}).json() == []
    # aynı revizyon, farklı gövde → 409; kayıt değişmez
    r3 = _put(istemci, govde(adet=26))
    assert r3.status_code == 409
    assert isinstance(r3.json()["detail"], str)
    assert _durum(istemci, g["mes_id"]) == J
    # yeni revizyon → yenisi alindi, eskisi iptal
    r4 = _put(istemci, govde(revizyon=2, adet=30))
    assert r4.status_code == 200, r4.text
    J4 = r4.json()
    assert J4["durum"] == "alindi"
    assert J4["is_emri"]["revizyon"] == 2 and J4["is_emri"]["adet"] == 30
    assert J4["degisiklik"] > J["degisiklik"]
    assert _durum(istemci, g["mes_id"]) == J4
    revler = mdepo.yukle(DEPO).kayitlar[g["mes_id"]]
    assert [k.is_emri.revizyon for k in revler] == [1, 2]
    assert [k.durum for k in revler] == ["iptal", "alindi"]


def test_put_dosyada_kalici(istemci):
    """Depo dosyası yazılıyor ve yeniden yükleme aynı kaydı veriyor."""
    J = _put(istemci, govde()).json()
    assert DEPO.is_file()
    d = mdepo.yukle(DEPO)
    assert mdepo.al(d, "IE-1001").model_dump(mode="json") == J


# ------------------------------------------------------------------ K3 durum makinesi


def test_durum(istemci):
    from tezgah import depo

    mid = "IE-2001"
    assert _put(istemci, govde(mes_id=mid)).json()["durum"] == "alindi"
    # alindi: program yok
    assert istemci.get(f"{API}/is-emirleri/{mid}/program").status_code == 409
    assert istemci.get(f"{API}/is-emirleri/{mid}/is-foyu.html").status_code == 409
    # alindi → baglandi
    _bagla_hazirla(mid, hazirla=False)
    J = _durum(istemci, mid)
    assert J["durum"] == "baglandi" and J["is_adi"] == IS_ADI and J["ciktilar"] is None
    assert istemci.get(f"{API}/is-emirleri/{mid}/program").status_code == 409
    # baglandi → hazir: çıktılar donar
    d = mdepo.yukle(DEPO)
    H = mdepo.hazirla(d, mid)
    assert H.durum == "hazir" and H.ciktilar is not None
    J = _durum(istemci, mid)
    assert J["durum"] == "hazir"
    assert J["ciktilar"] == H.ciktilar.model_dump(mode="json")
    r = istemci.get(f"{API}/is-emirleri/{mid}/program")
    assert r.status_code == 200
    assert r.headers["x-sha256"] == sha(r.text) == J["ciktilar"]["program_ozeti"]
    # bağlı işin parametresi değişince hazir → baglandi (GET tazele'yi uygular, degisiklik artar), 409
    d_hazir = J["degisiklik"]
    depo.kaydet(IS_ADI, ornek_tanim(F=350.0))
    J = _durum(istemci, mid)
    assert J["durum"] == "baglandi"
    assert J["degisiklik"] > d_hazir
    assert mdepo.al(mdepo.yukle(DEPO), mid).durum == "baglandi"  # geçiş dosyaya yazıldı
    assert J["ciktilar"] is None
    assert istemci.get(f"{API}/is-emirleri/{mid}/program").status_code == 409
    # yeniden hazir → gonderildi (SPEC 63 kaydında program özeti eşleşir)
    H = mdepo.hazirla(mdepo.yukle(DEPO), mid)
    KAYIT.parent.mkdir(parents=True, exist_ok=True)
    KAYIT.write_text(gonderim_satiri(H.ciktilar.program_ozeti) + "\n", encoding="utf-8")
    mdepo.esitle(mdepo.yukle(DEPO), KAYIT)
    J = _durum(istemci, mid)
    assert J["durum"] == "gonderildi"
    assert istemci.get(f"{API}/is-emirleri/{mid}/program").status_code == 200
    # iptal gerekçesiz → 422
    for g in ({"gerekce": ""}, {}):
        assert istemci.post(f"{API}/is-emirleri/{mid}/iptal", json=g).status_code == 422
    assert _durum(istemci, mid)["durum"] == "gonderildi"
    # gonderildi'den iptal: kayıt silinmez
    r = istemci.post(f"{API}/is-emirleri/{mid}/iptal", json={"gerekce": "müşteri iptal etti"})
    assert r.status_code == 200, r.text
    assert r.json()["durum"] == "iptal"
    J = _durum(istemci, mid)
    assert J["durum"] == "iptal" and J["is_emri"]["mes_id"] == mid
    assert mid in [k["is_emri"]["mes_id"] for k in istemci.get(f"{API}/is-emirleri").json()]


def test_tazele(istemci):
    """depo.tazele: bağlı iş değişince hazir → baglandi; değişmemişse hazir kalır."""
    from tezgah import depo

    mid = "IE-2002"
    _put(istemci, govde(mes_id=mid))
    _bagla_hazirla(mid)
    d = mdepo.yukle(DEPO)
    assert mdepo.tazele(d, mid).durum == "hazir"
    depo.kaydet(IS_ADI, ornek_tanim(F=350.0))
    T = mdepo.tazele(mdepo.yukle(DEPO), mid)
    assert T.durum == "baglandi"
    assert T.ciktilar is None
    with pytest.raises(mdepo.MesCakisma):
        mdepo.program_metni(mdepo.yukle(DEPO), mid)


def test_gecersiz_gecisler(istemci):
    mid = "IE-2003"
    _put(istemci, govde(mes_id=mid))
    d = mdepo.yukle(DEPO)
    with pytest.raises(mdepo.MesCakisma):
        mdepo.hazirla(d, mid)  # alindi → hazir yok
    with pytest.raises(KeyError):
        mdepo.bagla(mdepo.yukle(DEPO), mid, "boyle-bir-is-yok")
    with pytest.raises(mdepo.MesYok):
        mdepo.bagla(mdepo.yukle(DEPO), "IE-YOK", IS_ADI)
    assert _durum(istemci, mid)["durum"] == "alindi"


def test_iptal_her_durumdan(istemci):
    """alindi ve hazir'dan iptal; iptal edilmiş iş emrinin programı 409."""
    for mid, hazir in (("IE-3001", False), ("IE-3002", True)):
        _put(istemci, govde(mes_id=mid))
        if hazir:
            _bagla_hazirla(mid)
        r = istemci.post(f"{API}/is-emirleri/{mid}/iptal", json={"gerekce": "plan değişti"})
        assert r.status_code == 200, r.text
        assert r.json()["durum"] == "iptal"
        assert istemci.get(f"{API}/is-emirleri/{mid}/program").status_code == 409


# ------------------------------------------------------------------ K5 yoklama


def test_yoklama(istemci):
    d1 = _put(istemci, govde(mes_id="IE-5001")).json()["degisiklik"]
    d2 = _put(istemci, govde(mes_id="IE-5002")).json()["degisiklik"]
    d3 = _put(istemci, govde(mes_id="IE-5003")).json()["degisiklik"]
    assert d1 < d2 < d3
    L = istemci.get(f"{API}/is-emirleri", params={"sonra": d1}).json()
    assert [k["is_emri"]["mes_id"] for k in L] == ["IE-5002", "IE-5003"]
    assert [k["degisiklik"] for k in L] == [d2, d3]
    hepsi = istemci.get(f"{API}/is-emirleri").json()
    assert [k["is_emri"]["mes_id"] for k in hepsi] == ["IE-5001", "IE-5002", "IE-5003"]
    # yeni değişiklik (iptal) listenin sonuna geçer
    istemci.post(f"{API}/is-emirleri/IE-5001/iptal", json={"gerekce": "test"})
    L = istemci.get(f"{API}/is-emirleri", params={"sonra": d3}).json()
    assert [(k["is_emri"]["mes_id"], k["durum"]) for k in L] == [("IE-5001", "iptal")]
    assert L[0]["degisiklik"] > d3


def test_yoklama_durum_suzgeci(istemci):
    _put(istemci, govde(mes_id="IE-5101"))
    _put(istemci, govde(mes_id="IE-5102"))
    istemci.post(f"{API}/is-emirleri/IE-5101/iptal", json={"gerekce": "test"})
    L = istemci.get(f"{API}/is-emirleri", params={"durum": "alindi"}).json()
    assert [k["is_emri"]["mes_id"] for k in L] == ["IE-5102"]
    L = istemci.get(f"{API}/is-emirleri", params={"durum": "iptal"}).json()
    assert [k["is_emri"]["mes_id"] for k in L] == ["IE-5101"]
    assert istemci.get(f"{API}/is-emirleri", params={"durum": "bilinmez"}).status_code == 422
    assert istemci.get(f"{API}/is-emirleri", params={"sonra": -1}).status_code == 422


def test_yoklama_degisenler_depo(istemci):
    """depo.degisenler: degisiklik > sonra, artan sırada."""
    for i in range(3):
        _put(istemci, govde(mes_id=f"IE-52{i}"))
    d = mdepo.yukle(DEPO)
    L = mdepo.degisenler(d, 0)
    assert [k.is_emri.mes_id for k in L] == ["IE-520", "IE-521", "IE-522"]
    assert mdepo.degisenler(d, L[0].degisiklik) == L[1:]


# ------------------------------------------------------------------ K6 gönderimler (SPEC 63 kaydı)


def test_gonderim(istemci):
    """SPEC 63 §5 kaydındaki program özeti dondurulmuş programla eşleşince gonderildi ve mes_id'li kayıt."""
    mid = "IE-6001"
    _put(istemci, govde(mes_id=mid))
    _bagla_hazirla(mid)
    oz = _durum(istemci, mid)["ciktilar"]["program_ozeti"]
    KAYIT.parent.mkdir(parents=True, exist_ok=True)
    KAYIT.write_text(
        gonderim_satiri("f" * 64, program_ad="BASKA") + "\n" + gonderim_satiri(oz) + "\n", encoding="utf-8"
    )
    degisen = mdepo.esitle(mdepo.yukle(DEPO), KAYIT)
    assert [k.is_emri.mes_id for k in degisen] == [mid]
    assert degisen[0].durum == "gonderildi"
    assert _durum(istemci, mid)["durum"] == "gonderildi"
    L = istemci.get(f"{API}/gonderimler").json()
    assert [k["sira"] for k in L] == [1, 2]
    assert [k["mes_id"] for k in L] == [None, mid]
    assert L[1]["program"]["ozet"] == oz
    assert L[1]["sonuc"] == "yazildi"
    assert [k["sira"] for k in istemci.get(f"{API}/gonderimler", params={"sonra": 1}).json()] == [2]
    # ikinci eşitleme bir şey değiştirmez
    assert mdepo.esitle(mdepo.yukle(DEPO), KAYIT) == []


def test_gonderim_kaydi_yok(istemci):
    assert istemci.get(f"{API}/gonderimler").json() == []


# ------------------------------------------------------------------ K9 hata kuralı


def test_hatalar(istemci):
    g = govde(mes_id="IE-9001")
    for bozuk in (
        {**g, "bilinmeyen": 1},
        {**g, "adet": 0},
        {**g, "adet": -3},
        {**g, "revizyon": 0},
        {**g, "termin": "2026-13-01"},
        {**g, "termin": "2026-02-30"},
        {**g, "termin": "30.11.2026"},
        {k: v for k, v in g.items() if k != "parca_no"},
    ):
        r = istemci.put(f"{API}/is-emirleri/IE-9001", json=bozuk)
        assert r.status_code == 422, (bozuk, r.text)
    # yol ile gövde uyuşmazlığı, desen dışı mes_id
    assert istemci.put(f"{API}/is-emirleri/IE-9002", json=g).status_code == 422
    for kotu in ("a b", "x" * 41, "ş1"):
        assert istemci.put(f"{API}/is-emirleri/{kotu}", json={**g, "mes_id": kotu}).status_code == 422
    assert istemci.get(f"{API}/is-emirleri").json() == []
    # bilinmeyen mes_id → 404
    for yol in ("", "/program", "/takimlar", "/sure", "/maliyet", "/is-foyu.html"):
        r = istemci.get(f"{API}/is-emirleri/IE-YOK{yol}")
        assert r.status_code in ((404, 503) if yol in ("/sure", "/maliyet") else (404,)), (yol, r.status_code)
    assert istemci.get(f"{API}/is-emirleri/IE-YOK").status_code == 404
    assert istemci.post(f"{API}/is-emirleri/IE-YOK/iptal", json={"gerekce": "x"}).status_code == 404
    r = istemci.get(f"{API}/is-emirleri/IE-YOK")
    assert isinstance(r.json()["detail"], str)


def test_hata_govdesi_detail(istemci):
    """409 ve 404 yanıtlarında gövde {"detail": str}."""
    _put(istemci, govde(mes_id="IE-9101"))
    for r in (
        _put(istemci, govde(mes_id="IE-9101", adet=99)),
        istemci.get(f"{API}/is-emirleri/IE-9101/program"),
        istemci.get(f"{API}/is-emirleri/IE-9999"),
    ):
        assert r.status_code in (404, 409)
        assert isinstance(r.json()["detail"], str) and r.json()["detail"]
