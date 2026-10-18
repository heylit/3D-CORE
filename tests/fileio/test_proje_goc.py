"""B1 (SPEC 37 eki) — `.3dc` proje dosyası şema sürümü ve göç testleri (K1–K9).

Testler yalnız specs/37-ek-b1-proje-surumu.md ve fileio/proje.py arayüzünden (imzalar,
docstring'ler) yazıldı; göç gövdeleri okunmadı. Göç kayıtları testte kurulan sahte `GocKaydi()`
nesneleridir; gerçek ekran göçü yoktur.

Varsayımlar (metnin açık bıraktığı yerler):
- Hata mesajı biçimi `"<dosya adı>: <bolum|dosya>: <ne oldu> (sema <bulunan>, beklenen ≤ <güncel>)"`: sürüm
  reddinde testler dosya adını, bölüm adını (dosya düzeyinde "dosya"), `sema <bulunan>` parçasını ve güncel
  sürümü arar; adım çıktısı hatasında (atlayan, değiştiren, nan) yalnız dosya adı, bölüm adı ve k, k + 1.
- "Zincirde boşluk" `guncel` en büyük hedef olduğundan ancak arada eksik adımla oluşur: `1→2` ve
  `3→4` kayıtlı, `2→3` yok (metindeki "`1→2` var ama `2→3` yok" örneğinin anlamı).
- Göç uyarısının metni uyarı sözlüğünün herhangi bir alanında (metindeki `mesaj`) aranır.
- Yedek adı: `<ad>.sema<D>-<8 onaltılık>[-N].3dc.yedek`;
  testler `<ad>.sema1-` önekine ve `.3dc.yedek` sonekine bakar.
- "İkinci kayıt yeni yedek üretmez": kaydedilen dosya yeniden açılıp aynı yola
  kaydedilince yedek sayısı değişmez.
- Geçmişteki bir belgenin göç hatası, adımın kural dışı (`sema` atlayan) çıktısıyla üretilir (→ ProjeError).
"""

from __future__ import annotations

import copy
import json
import math
import os
import re
import zipfile
from pathlib import Path

import pytest

from fileio.proje import (
    SEMA,
    Goc,
    GocKaydi,
    Proje,
    ProjeError,
    ac,
    bos_proje,
    geri_al,
    incele,
    kanonik,
    kaydet,
    uygula,
)

GOC_KLASORU = Path(__file__).parent / "goc"
BOLUM = "parca"


# ---------------------------------------------------------------------------
# Yardımcılar
# ---------------------------------------------------------------------------


def _kanon(x) -> bytes:
    return json.dumps(x, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()


class _Sayac:
    def __init__(self) -> None:
        self.n = 0


def _adim1(sayac: _Sayac):
    """1 → 2: `x`'in iki katı `x2` alanı eklenir."""

    def uygula_(b: dict) -> dict:
        sayac.n += 1
        return {**copy.deepcopy(b), "sema": 2, "x2": b["x"] * 2}

    return uygula_


def _adim2(sayac: _Sayac):
    """2 → 3: `x` alanı `y` olur."""

    def uygula_(b: dict) -> dict:
        sayac.n += 1
        yeni = {k: copy.deepcopy(v) for k, v in b.items() if k != "x"}
        yeni["y"] = b["x"]
        yeni["sema"] = 3
        return yeni

    return uygula_


def _beklenen(b1: dict) -> dict:
    """sema 1 belgenin iki adımdan sonraki hali (bağımsız hesap)."""
    sonuc = {k: v for k, v in b1.items() if k != "x"}
    sonuc.update({"sema": 3, "x2": b1["x"] * 2, "y": b1["x"]})
    return sonuc


def _kayit(sayac: _Sayac | None = None) -> GocKaydi:
    """`parca` için 1→2, 2→3 kayıtlı sahte göç kaydı."""
    s = sayac or _Sayac()
    k = GocKaydi()
    k.kaydet(Goc(BOLUM, 1, _adim1(s), "ilk adim"))
    k.kaydet(Goc(BOLUM, 2, _adim2(s), "ikinci adim"))
    return k


def _eski_proje(x: float = 7.0, ek: dict | None = None) -> Proje:
    bolumler = {"kabuk": {"sema": 1, "aktif_ekran": "freze"}, BOLUM: {"sema": 1, "x": x, "ad": "mil"}}
    bolumler.update(ek or {})
    return Proje(ad="eski proje", bolumler=bolumler)


def _yaz(p: Proje, yol: Path) -> Path:
    kaydet(p, yol)
    return yol


def _zip_oku(yol: Path) -> dict[str, bytes]:
    with zipfile.ZipFile(yol) as z:
        return {ad: z.read(ad) for ad in z.namelist()}


def _zip_yaz(yol: Path, girdiler: dict[str, bytes]) -> None:
    with zipfile.ZipFile(yol, "w", zipfile.ZIP_DEFLATED) as z:
        for ad, veri in girdiler.items():
            z.writestr(zipfile.ZipInfo(ad, date_time=(1980, 1, 1, 0, 0, 0)), veri, zipfile.ZIP_DEFLATED)


def _bolum(p: Proje, ad: str) -> dict:
    return dict(p.bolumler)[ad]


def _uyari_metinleri(p: Proje) -> list[str]:
    return [json.dumps(u, ensure_ascii=False) for u in p.uyarilar if u.get("durum") == "uyari"]


def _hata(yol: Path, kayit: GocKaydi) -> str:
    with pytest.raises(ProjeError) as e:
        ac(yol, kayit)
    return str(e.value)


def _mesaj_icerir(m: str, dosya: str, yer: str, bulunan: int, guncel: int) -> None:
    assert dosya in m, m
    assert yer in m, m
    assert f"sema {bulunan}" in m, m
    assert str(guncel) in m.split(f"sema {bulunan}", 1)[1], m


def _mesaj_iki_surum(m: str, dosya: str, yer: str, a: int, b: int) -> None:
    """Adım çıktısı hatası: dosya adı, bölüm adı ve iki sürüm numarası (k ve k + 1) mesajda."""
    assert dosya in m, m
    assert yer in m, m
    for n in (a, b):
        assert re.search(rf"(?<![\w.]){n}(?![\w.])", m), m


def _klasor(yol: Path) -> list[str]:
    return sorted(os.listdir(yol))


def _yedekler(klasor: Path) -> list[str]:
    return sorted(a for a in os.listdir(klasor) if a.endswith(".3dc.yedek"))


# ---------------------------------------------------------------------------
# GocKaydi
# ---------------------------------------------------------------------------


def test_registry_current_and_chain():
    k = _kayit()
    assert k.guncel(BOLUM) == 3
    assert k.guncel("baska_bolum") == 1
    assert k.guncel("") == SEMA
    assert [(g.bolum, g.kaynak) for g in k.zincir(BOLUM, 1)] == [(BOLUM, 1), (BOLUM, 2)]
    assert [g.kaynak for g in k.zincir(BOLUM, 2)] == [2]
    assert k.zincir(BOLUM, 3) == []
    with pytest.raises(ProjeError):
        k.zincir(BOLUM, 4)


def test_registry_order_independent():
    s = _Sayac()
    k = GocKaydi()
    k.kaydet(Goc(BOLUM, 2, _adim2(s), "ikinci adim"))
    k.kaydet(Goc(BOLUM, 1, _adim1(s), "ilk adim"))
    assert [g.kaynak for g in k.zincir(BOLUM, 1)] == [1, 2]


def test_registry_rejects_bad_steps():
    k = _kayit()
    with pytest.raises(ProjeError) as e:
        k.kaydet(Goc(BOLUM, 1, _adim1(_Sayac()), "yine ilk"))  # çift (bolum, kaynak)
    assert BOLUM in str(e.value) and "1" in str(e.value)
    with pytest.raises(ProjeError):
        k.kaydet(Goc(BOLUM, 0, _adim1(_Sayac()), "sıfırdan"))
    with pytest.raises(ProjeError):
        k.kaydet(Goc("diger", 1, _adim1(_Sayac()), ""))
    # reddedilen kayıtlar kaydı değiştirmez
    assert k.guncel(BOLUM) == 3 and k.guncel("diger") == 1


def test_registry_gap():
    s = _Sayac()
    k = GocKaydi()
    k.kaydet(Goc(BOLUM, 1, _adim1(s), "ilk adim"))
    k.kaydet(Goc(BOLUM, 3, lambda b: {**b, "sema": 4}, "dorduncu"))
    assert k.guncel(BOLUM) == 4
    with pytest.raises(ProjeError):
        k.zincir(BOLUM, 1)
    assert [g.kaynak for g in k.zincir(BOLUM, 3)] == [3]


# ---------------------------------------------------------------------------
# K1 Güncel dosya değişmez
# ---------------------------------------------------------------------------


def test_no_migration_no_change(tmp_path):
    k = _kayit()  # parca güncel: 3
    p = Proje(
        ad="guncel",
        bolumler={"kabuk": {"sema": 1, "aktif_ekran": "freze"}, BOLUM: {"sema": 3, "x2": 2.0, "y": 1.0}},
    )
    p = uygula(p, "y 2", "torna", {BOLUM: {"sema": 3, "x2": 4.0, "y": 2.0}})
    y1 = _yaz(p, tmp_path / "guncel.3dc")
    once = y1.read_bytes()

    q = ac(y1, k)
    assert dict(q.goc) == {}
    assert not any("sema" in m and "→" in m for m in _uyari_metinleri(q))
    kaydet(q, tmp_path / "kopya.3dc")
    assert (tmp_path / "kopya.3dc").read_bytes() == once
    kaydet(q, y1)  # aynı yola: yedek yok, bayt aynı
    assert y1.read_bytes() == once
    assert _yedekler(tmp_path) == []

    # boş kayıtla da aynı (varsayılan GOCLER yolu SPEC 37 ile aynı)
    assert dict(ac(y1, GocKaydi()).goc) == {}
    assert dict(ac(y1).goc) == {}


# ---------------------------------------------------------------------------
# K2 Zincir
# ---------------------------------------------------------------------------


def test_chain(tmp_path):
    s = _Sayac()
    k = _kayit(s)
    p = _eski_proje(x=7.0, ek={"diger": {"sema": 1, "v": [1, 2]}})
    yol = _yaz(p, tmp_path / "eski.3dc")
    once_bayt = yol.read_bytes()

    q = ac(yol, k)
    assert kanonik(_bolum(q, BOLUM)) == kanonik(_beklenen(_bolum(p, BOLUM)))
    assert _bolum(q, BOLUM)["sema"] == 3
    assert kanonik(_bolum(q, "diger")) == kanonik(_bolum(p, "diger"))  # sahipsiz, dokunulmaz
    assert kanonik(_bolum(q, "kabuk")) == kanonik(_bolum(p, "kabuk"))
    assert dict(q.goc) == {BOLUM: (1, 3)}
    assert s.n == 2
    assert any(f"{BOLUM}: sema 1 → 3 (ilk adim; ikinci adim)" in m for m in _uyari_metinleri(q)), q.uyarilar
    assert yol.read_bytes() == once_bayt  # açmak dosyayı değiştirmez
    assert q.kaynak_yol is not None and Path(q.kaynak_yol).resolve() == yol.resolve()


def test_chain_partial(tmp_path):
    """sema 2 belge yalnız 2→3 adımından geçer."""
    s = _Sayac()
    k = _kayit(s)
    p = Proje(ad="yarim", bolumler={BOLUM: {"sema": 2, "x": 5.0, "x2": 10.0}})
    q = ac(_yaz(p, tmp_path / "yarim.3dc"), k)
    assert kanonik(_bolum(q, BOLUM)) == kanonik({"sema": 3, "x2": 10.0, "y": 5.0})
    assert dict(q.goc) == {BOLUM: (2, 3)}
    assert s.n == 1
    assert any(f"{BOLUM}: sema 2 → 3 (ikinci adim)" in m for m in _uyari_metinleri(q))


def test_chain_input_object_untouched(tmp_path):
    """Göçten sonra kaydedilen dosya güncel sürümdedir; yeniden açmak göç yapmaz."""
    k = _kayit()
    q = ac(_yaz(_eski_proje(), tmp_path / "eski.3dc"), k)
    kaydet(q, tmp_path / "yeni.3dc")
    r = ac(tmp_path / "yeni.3dc", k)
    assert dict(r.goc) == {}
    assert kanonik(_bolum(r, BOLUM)) == kanonik(_bolum(q, BOLUM))


# ---------------------------------------------------------------------------
# K3 Reddedilenler
# ---------------------------------------------------------------------------


def test_rejects_newer_section(tmp_path):
    yol = _yaz(Proje(ad="yeni", bolumler={BOLUM: {"sema": 4, "z": 1}}), tmp_path / "gelecek_bolum.3dc")
    _mesaj_icerir(_hata(yol, _kayit()), "gelecek_bolum.3dc", BOLUM, 4, 3)


def test_rejects_newer_file(tmp_path):
    yol = _yaz(_eski_proje(), tmp_path / "gelecek_dosya.3dc")
    g = _zip_oku(yol)
    b = json.loads(g["proje.json"])
    b["sema"] = SEMA + 1
    g["proje.json"] = _kanon(b)
    _zip_yaz(yol, g)
    _mesaj_icerir(_hata(yol, _kayit()), "gelecek_dosya.3dc", "dosya", SEMA + 1, SEMA)


def test_rejects_gap(tmp_path):
    s = _Sayac()
    k = GocKaydi()
    k.kaydet(Goc(BOLUM, 1, _adim1(s), "ilk adim"))
    k.kaydet(Goc(BOLUM, 3, lambda b: {**b, "sema": 4}, "dorduncu"))
    yol = _yaz(_eski_proje(), tmp_path / "bosluk.3dc")
    _mesaj_icerir(_hata(yol, k), "bosluk.3dc", BOLUM, 1, 4)


def test_rejects_duplicate_registration():
    k = _kayit()
    with pytest.raises(ProjeError) as e:
        k.kaydet(Goc(BOLUM, 2, _adim2(_Sayac()), "baska ikinci"))
    assert BOLUM in str(e.value) and "2" in str(e.value)


def _tek_adim(uygula_) -> GocKaydi:
    k = GocKaydi()
    k.kaydet(Goc(BOLUM, 1, uygula_, "bozuk adim"))
    return k


def test_rejects_skipping_step(tmp_path):
    k = _tek_adim(lambda b: {**b, "sema": 3})  # 1 → 3 (tek adımda iki sürüm)
    yol = _yaz(_eski_proje(), tmp_path / "atlayan.3dc")
    _mesaj_iki_surum(_hata(yol, k), "atlayan.3dc", BOLUM, 1, 2)


def test_rejects_missing_sema_step(tmp_path):
    k = _tek_adim(lambda b: {kk: v for kk, v in b.items() if kk != "sema"})
    yol = _yaz(_eski_proje(), tmp_path / "semasiz.3dc")
    _mesaj_iki_surum(_hata(yol, k), "semasiz.3dc", BOLUM, 1, 2)


def test_rejects_mutating_step(tmp_path):
    def bozan(b: dict) -> dict:
        b["x"] = -1.0  # girdiyi değiştirir
        return {**copy.deepcopy(b), "sema": 2}

    yol = _yaz(_eski_proje(), tmp_path / "degistiren.3dc")
    _mesaj_iki_surum(_hata(yol, _tek_adim(bozan)), "degistiren.3dc", BOLUM, 1, 2)


def test_rejects_mutating_nested_step(tmp_path):
    def bozan(b: dict) -> dict:
        b["ic"]["liste"].append(9)
        return {**copy.deepcopy(b), "sema": 2}

    p = _eski_proje()
    bolumler = dict(p.bolumler)
    bolumler[BOLUM] = {"sema": 1, "x": 1.0, "ic": {"liste": [1, 2]}}
    yol = _yaz(Proje(ad="ic", bolumler=bolumler), tmp_path / "ic_degistiren.3dc")
    _mesaj_iki_surum(_hata(yol, _tek_adim(bozan)), "ic_degistiren.3dc", BOLUM, 1, 2)


@pytest.mark.parametrize("kotu", [math.nan, math.inf])
def test_rejects_nan_step(tmp_path, kotu):
    k = _tek_adim(lambda b: {**b, "sema": 2, "x": kotu})
    yol = _yaz(_eski_proje(), tmp_path / "nan_ureten.3dc")
    _mesaj_iki_surum(_hata(yol, k), "nan_ureten.3dc", BOLUM, 1, 2)


def test_rejects_leave_file_untouched(tmp_path):
    yol = _yaz(Proje(ad="yeni", bolumler={BOLUM: {"sema": 4}}), tmp_path / "dokunma.3dc")
    once = yol.read_bytes()
    _hata(yol, _kayit())
    assert yol.read_bytes() == once
    assert _klasor(tmp_path) == ["dokunma.3dc"]


# ---------------------------------------------------------------------------
# K4 Denetim önce
# ---------------------------------------------------------------------------


def test_checks_before_migration(tmp_path):
    s = _Sayac()
    k = _kayit(s)
    yol = _yaz(_eski_proje(), tmp_path / "bozuk_ozet.3dc")
    g = _zip_oku(yol)
    g[f"bolumler/{BOLUM}.json"] = _kanon({"sema": 1, "x": 99.0, "ad": "mil"})  # özet artık tutmuyor
    _zip_yaz(yol, g)
    with pytest.raises(ProjeError) as e:
        ac(yol, k)
    assert BOLUM in str(e.value)
    assert s.n == 0


def test_checks_before_migration_bad_json(tmp_path):
    s = _Sayac()
    k = _kayit(s)
    yol = _yaz(_eski_proje(), tmp_path / "bozuk_json.3dc")
    g = _zip_oku(yol)
    g["gecmis.json"] = b"{bozuk"
    _zip_yaz(yol, g)
    with pytest.raises(ProjeError):
        ac(yol, k)
    assert s.n == 0


# ---------------------------------------------------------------------------
# K5 Geçmiş göç eder
# ---------------------------------------------------------------------------


def _uc_kayitli(bolum_belgeleri: list[dict], ilk: dict) -> Proje:
    p = Proje(ad="gecmisli", bolumler={"kabuk": {"sema": 1, "aktif_ekran": "torna"}, BOLUM: ilk})
    for i, b in enumerate(bolum_belgeleri):
        p = uygula(p, f"adim {i}", "torna", {BOLUM: b})
    return p


def test_history_migrates(tmp_path):
    s = _Sayac()
    k = _kayit(s)
    eski_ilk = {"sema": 1, "x": 0.5, "ad": "mil"}
    eski = [{"sema": 1, "x": float(i), "ad": "mil"} for i in (1, 2, 3)]
    p1 = _uc_kayitli(eski, eski_ilk)
    assert len(p1.gecmis.kayitlar) == 3
    yol = _yaz(p1, tmp_path / "gecmisli.3dc")

    q = ac(yol, k)
    # aynı geçmiş baştan sema 3'te kurulmuş hali
    r = _uc_kayitli([_beklenen(b) for b in eski], _beklenen(eski_ilk))

    assert q.gecmis.konum == 3
    for kq, kr in zip(q.gecmis.kayitlar, r.gecmis.kayitlar, strict=True):
        assert kq["etiket"] == kr["etiket"] and kq["ekran"] == kr["ekran"]
        assert _kanon(kq["bolumler"]) == _kanon(kr["bolumler"])
        for once, sonra in kq["bolumler"].values():
            for belge in (once, sonra):
                assert belge is None or belge["sema"] == 3

    for _ in range(3):
        q, r = geri_al(q), geri_al(r)
        assert _bolum(q, BOLUM)["sema"] == 3
        assert kanonik(_bolum(q, BOLUM)) == kanonik(_bolum(r, BOLUM))
    assert kanonik(_bolum(q, BOLUM)) == kanonik(_beklenen(eski_ilk))


def test_history_with_created_section(tmp_path):
    """Geçmişte `once = null` olan (bölümü yaratan) kayıt: null göçe girmez."""
    k = _kayit()
    p = bos_proje("yaratan")
    p = uygula(p, "yarat", "torna", {BOLUM: {"sema": 1, "x": 1.0}})
    p = uygula(p, "x 2", "torna", {BOLUM: {"sema": 1, "x": 2.0}})
    q = ac(_yaz(p, tmp_path / "yaratan.3dc"), k)
    assert q.gecmis.kayitlar[0]["bolumler"][BOLUM][0] is None
    q = geri_al(geri_al(q))
    assert BOLUM not in q.bolumler


def test_history_migration_error_fails_open(tmp_path):
    def secici(b: dict) -> dict:
        # yalnız geçmişteki x == 2 belgesi için kural dışı çıktı
        return {**b, "sema": 3 if b["x"] == 2.0 else 2}

    k = GocKaydi()
    k.kaydet(Goc(BOLUM, 1, secici, "secici adim"))
    eski = [{"sema": 1, "x": float(i)} for i in (1, 2, 3)]
    yol = _yaz(_uc_kayitli(eski, {"sema": 1, "x": 0.0}), tmp_path / "gecmis_hatali.3dc")
    with pytest.raises(ProjeError) as e:
        ac(yol, k)
    assert "gecmis_hatali.3dc" in str(e.value) and BOLUM in str(e.value)


# ---------------------------------------------------------------------------
# K6 Tanınmayan bölüm
# ---------------------------------------------------------------------------


def test_unknown_section_untouched(tmp_path):
    s = _Sayac()
    k = _kayit(s)
    yabanci = {"sema": 1, "x": 3.0, "ağaç": [1, {"b": None}]}
    gelecek = {"sema": 9, "w": "ü"}
    p = _eski_proje(ek={"yabanci": yabanci, "gelecek": gelecek})
    y1 = _yaz(p, tmp_path / "yabanci.3dc")
    q = ac(y1, k)
    assert kanonik(_bolum(q, "yabanci")) == kanonik(yabanci)
    assert kanonik(_bolum(q, "gelecek")) == kanonik(gelecek)  # sahipsizde sürüm denetimi yok
    assert set(q.goc) == {BOLUM}
    assert s.n == 2  # yalnız parca göç etti
    kaydet(q, tmp_path / "yeniden.3dc")
    g1, g2 = _zip_oku(y1), _zip_oku(tmp_path / "yeniden.3dc")
    assert g2["bolumler/yabanci.json"] == g1["bolumler/yabanci.json"]
    assert g2["bolumler/gelecek.json"] == g1["bolumler/gelecek.json"]


# ---------------------------------------------------------------------------
# K7 Yedek
# ---------------------------------------------------------------------------


def test_backup_created(tmp_path):
    k = _kayit()
    yol = _yaz(_eski_proje(), tmp_path / "proje.3dc")
    ozgun = yol.read_bytes()
    q = ac(yol, k)
    kaydet(q, yol)

    yedekler = _yedekler(tmp_path)
    assert len(yedekler) == 1, _klasor(tmp_path)
    assert yedekler[0].startswith("proje.sema1-")
    assert re.fullmatch(r"proje\.sema1-[0-9a-f]{8}(-\d+)?\.3dc\.yedek", yedekler[0]), yedekler[0]
    assert (tmp_path / yedekler[0]).read_bytes() == ozgun
    assert yol.read_bytes() != ozgun
    assert _bolum(ac(yol, k), BOLUM)["sema"] == 3
    assert not [a for a in _klasor(tmp_path) if a.endswith(".tmp")]

    # ikinci kayıt (yeniden açılan, artık güncel proje) yedek üretmez
    r = ac(yol, k)
    assert dict(r.goc) == {}
    kaydet(r, yol)
    assert _yedekler(tmp_path) == yedekler


def test_backup_same_bytes_not_rewritten(tmp_path):
    k = _kayit()
    yol = _yaz(_eski_proje(), tmp_path / "proje.3dc")
    ozgun = yol.read_bytes()
    kaydet(ac(yol, k), yol)
    ilk = _yedekler(tmp_path)
    zaman = (tmp_path / ilk[0]).stat().st_mtime_ns

    yol.write_bytes(ozgun)  # aynı eski dosya yeniden
    kaydet(ac(yol, k), yol)
    assert _yedekler(tmp_path) == ilk
    assert (tmp_path / ilk[0]).stat().st_mtime_ns == zaman


def test_backup_different_bytes_get_new_name(tmp_path):
    k = _kayit()
    yol = tmp_path / "proje.3dc"
    _yaz(_eski_proje(x=1.0), yol)
    ozgun1 = yol.read_bytes()
    kaydet(ac(yol, k), yol)

    _yaz(_eski_proje(x=2.0), yol)  # aynı sürümler, farklı içerik
    ozgun2 = yol.read_bytes()
    kaydet(ac(yol, k), yol)

    yedekler = _yedekler(tmp_path)
    assert len(yedekler) == 2, yedekler
    assert sorted((tmp_path / a).read_bytes() for a in yedekler) == sorted([ozgun1, ozgun2])
    assert all(a.startswith("proje.sema1-") for a in yedekler)


def test_backup_failure_blocks_save(tmp_path, monkeypatch):
    k = _kayit()
    yol = _yaz(_eski_proje(), tmp_path / "proje.3dc")
    ozgun = yol.read_bytes()
    q = ac(yol, k)

    asil = os.replace

    def kesici(src, dst, *a, **kw):
        if str(dst).endswith(".yedek"):
            raise OSError("yedek yazılamadı (test)")
        return asil(src, dst, *a, **kw)

    with monkeypatch.context() as m:
        m.setattr(os, "replace", kesici)
        with pytest.raises(ProjeError):
            kaydet(q, yol)
    assert yol.read_bytes() == ozgun
    assert _klasor(tmp_path) == ["proje.3dc"]


def test_backup_other_path(tmp_path):
    k = _kayit()
    yol = _yaz(_eski_proje(), tmp_path / "proje.3dc")
    ozgun = yol.read_bytes()
    q = ac(yol, k)
    kaydet(q, tmp_path / "baska.3dc")
    assert _yedekler(tmp_path) == []
    assert yol.read_bytes() == ozgun
    assert _bolum(ac(tmp_path / "baska.3dc", k), BOLUM)["sema"] == 3


def test_backup_overwriting_other_file(tmp_path):
    """Göç edilmiş proje, kaynağı olmayan başka bir var olan dosyanın üstüne kaydedilirse yedek yok."""
    k = _kayit()
    yol = _yaz(_eski_proje(), tmp_path / "proje.3dc")
    baska = _yaz(_eski_proje(x=3.0), tmp_path / "baska.3dc")
    kaydet(ac(yol, k), baska)
    assert _yedekler(tmp_path) == []


# ---------------------------------------------------------------------------
# K8 Örnek dosyalar
# ---------------------------------------------------------------------------

_ORNEK_ADI = re.compile(r"(?P<bolum>[a-z0-9_]+)-sema(?P<k>\d+)\.3dc")


def _deneme_kaydi() -> GocKaydi:
    k = GocKaydi()
    k.kaydet(Goc("deneme", 1, lambda b: {**copy.deepcopy(b), "sema": 2, "goc": "1-2"}, "deneme 1 → 2"))
    return k


def test_sample_files(tmp_path):
    from fileio.proje import GOCLER

    ornekler = sorted(GOC_KLASORU.glob("*.3dc"))
    assert ornekler, f"{GOC_KLASORU} altında örnek yok"
    assert any(o.name == "deneme-sema1.3dc" for o in ornekler)
    for o in ornekler:
        m = _ORNEK_ADI.fullmatch(o.name)
        assert m, f"örnek adı <bolum>-sema<k>.3dc olmalı: {o.name}"
        bolum, k = m["bolum"], int(m["k"])
        kayit = _deneme_kaydi() if bolum == "deneme" else GOCLER
        hedef = kayit.guncel(bolum)
        once = o.read_bytes()
        p = ac(o, kayit)
        assert _bolum(p, bolum)["sema"] == hedef, o.name
        if k < hedef:
            assert dict(p.goc)[bolum] == (k, hedef), o.name
        assert o.read_bytes() == once  # örnek dosya değişmez
        # göç edilmiş proje kaydedilip yeniden açılınca göç yok
        kaydet(p, tmp_path / o.name)
        assert dict(ac(tmp_path / o.name, kayit).goc) == {}


def test_sample_deneme_content():
    p = ac(GOC_KLASORU / "deneme-sema1.3dc", _deneme_kaydi())
    b = _bolum(p, "deneme")
    assert b["sema"] == 2 and b["goc"] == "1-2"
    assert any("deneme: sema 1 → 2 (deneme 1 → 2)" in m for m in _uyari_metinleri(p))


# ---------------------------------------------------------------------------
# K9 İnceleme
# ---------------------------------------------------------------------------


def test_inspect(tmp_path):
    s = _Sayac()
    k = _kayit(s)

    # K2 dosyası: açılır
    eski = _yaz(_eski_proje(), tmp_path / "eski.3dc")
    once = eski.read_bytes()
    r = incele(eski, k)
    assert r["acilir"] is True and r["neden"] is None
    assert tuple(r["dosya"]) == (1, SEMA)
    assert tuple(r["bolumler"][BOLUM]) == (1, 3)
    assert eski.read_bytes() == once
    assert s.n == 0

    # K3: daha yeni bölüm
    yeni = _yaz(Proje(ad="yeni", bolumler={BOLUM: {"sema": 4}}), tmp_path / "gelecek_bolum.3dc")
    r = incele(yeni, k)
    assert r["acilir"] is False and BOLUM in r["neden"]
    assert tuple(r["bolumler"][BOLUM]) == (4, 3)

    # K3: daha yeni dosya şeması
    dosya = _yaz(_eski_proje(), tmp_path / "gelecek_dosya.3dc")
    g = _zip_oku(dosya)
    b = json.loads(g["proje.json"])
    b["sema"] = SEMA + 1
    g["proje.json"] = _kanon(b)
    _zip_yaz(dosya, g)
    once = dosya.read_bytes()
    r = incele(dosya, k)
    assert r["acilir"] is False and r["neden"]
    assert tuple(r["dosya"]) == (SEMA + 1, SEMA)
    assert dosya.read_bytes() == once

    # K3: zincirde boşluk
    kb = GocKaydi()
    kb.kaydet(Goc(BOLUM, 1, _adim1(s), "ilk adim"))
    kb.kaydet(Goc(BOLUM, 3, lambda b: {**b, "sema": 4}, "dorduncu"))
    r = incele(eski, kb)
    assert r["acilir"] is False and BOLUM in r["neden"]
    assert tuple(r["bolumler"][BOLUM]) == (1, 4)

    # güncel dosya
    guncel = _yaz(Proje(ad="g", bolumler={BOLUM: {"sema": 3}}), tmp_path / "guncel.3dc")
    r = incele(guncel, k)
    assert r["acilir"] is True and r["neden"] is None
    assert tuple(r["bolumler"][BOLUM]) == (3, 3)

    assert s.n == 0  # incele hiçbir göç fonksiyonunu çağırmaz
    assert _yedekler(tmp_path) == []
