"""LatheTool.edge_len, LatheTool.holder ve LatheHolder arayüz eki testleri (SPEC 22 "Gerekli arayüz eki").

Testler yalnızca SPEC 22 taslağından ve koordinatörün aktardığı sözleşmeden yazıldı;
eklerin uygulama kodu (fonksiyon gövdeleri) okunmadı.

Davranış:
- LatheTool.edge_len: None (varsayılan) ya da sonlu ve > 0; 0, negatif, nan, inf → CamError.
- LatheHolder(name, polygon, half_width): polygon en az 3 sonlu (z, x) noktası, saat yönü tersi
  (alan > 0) ve dışbükey; içbükey köşe → CamError, doğrusal ardışık noktalar kabul.
  half_width sonlu ve > 0.
- LatheTool.holder: None (varsayılan) ya da LatheHolder; başka tip → CamError.
- to_dict / from_dict gidiş-dönüş; LatheTool.to_dict "edge_len" ve "holder" yazar;
  bu iki anahtar olmayan eski sözlükte ikisi None.
- LatheHolder.from_dict eksik ya da bilinmeyen alanda CamError.
"""

from __future__ import annotations

import json
import math

import pytest

from cam.model import CamError, LatheHolder, LatheTool, LatheToolKind

# Dikdörtgen tutucu: burun merkezine göre dış çerçevede (z, x), saat yönü tersi.
DIKDORTGEN = ((2.0, 3.0), (30.0, 3.0), (30.0, 23.0), (2.0, 23.0))


def alan(polygon) -> float:
    """Shoelace işaretli alanı (saat yönü tersi > 0)."""
    n = len(polygon)
    return 0.5 * sum(
        polygon[i][0] * polygon[(i + 1) % n][1] - polygon[(i + 1) % n][0] * polygon[i][1] for i in range(n)
    )


def make_holder(polygon=DIKDORTGEN, half_width: float = 6.0, name: str = "PCLNR") -> LatheHolder:
    return LatheHolder(name=name, polygon=polygon, half_width=half_width)


def make_tool(**kw) -> LatheTool:
    """Dış tornalama takımı (CNMG 0804, tip 3); ek alanlar parametre."""
    return LatheTool(
        id=1, name="T1", kind=LatheToolKind.TURN, nose_r=0.8, tip=3, kappa_r=95.0, eps_r=80.0, **kw
    )


def test_dikdortgen_yardimci_ccw():
    """Yardımcı veri kendi içinde tutarlı: dikdörtgen saat yönü tersi."""
    assert alan(DIKDORTGEN) == pytest.approx(28.0 * 20.0)


# ---------------------------------------------------------------- edge_len


def test_edge_len_varsayilan_none():
    assert make_tool().edge_len is None


@pytest.mark.parametrize("edge_len", [0.001, 4.0, 12.7, 1e4])
def test_edge_len_pozitif_sonlu_kabul(edge_len):
    assert make_tool(edge_len=edge_len).edge_len == pytest.approx(edge_len)


def test_edge_len_none_acik_kabul():
    assert make_tool(edge_len=None).edge_len is None


@pytest.mark.parametrize("edge_len", [0.0, -0.0, -1.0, -1e-9, math.nan, math.inf, -math.inf])
def test_edge_len_gecersiz(edge_len):
    with pytest.raises(CamError):
        make_tool(edge_len=edge_len)


# ---------------------------------------------------------------- LatheHolder: geçerli


def test_holder_alanlari():
    h = make_holder()
    assert h.name == "PCLNR"
    assert h.half_width == pytest.approx(6.0)
    assert len(h.polygon) == 4
    for (z, x), (z0, x0) in zip(h.polygon, DIKDORTGEN, strict=True):
        assert (z, x) == pytest.approx((z0, x0))


def test_holder_ucgen_kabul():
    h = make_holder(polygon=((0.0, 0.0), (10.0, 0.0), (0.0, 10.0)))
    assert len(h.polygon) == 3


def test_holder_liste_girdisi_kabul():
    """Çokgen JSON'dan liste olarak gelebilir; liste girdisi de geçerli bir çokgendir."""
    h = make_holder(polygon=[[2.0, 3.0], [30.0, 3.0], [30.0, 23.0], [2.0, 23.0]])
    assert len(h.polygon) == 4


def test_holder_dogrusal_ardisik_noktalar_kabul():
    """Kenar ortasına konan doğrusal nokta (180° köşe) dışbükeyliği bozmaz."""
    poly = ((2.0, 3.0), (16.0, 3.0), (30.0, 3.0), (30.0, 23.0), (2.0, 23.0))
    assert alan(poly) > 0
    h = make_holder(polygon=poly)
    assert len(h.polygon) == 5


def test_holder_negatif_koordinat_kabul():
    """Çokgen burun merkezine göredir; negatif z / x geçerli."""
    poly = ((-5.0, -2.0), (5.0, -2.0), (5.0, 8.0), (-5.0, 8.0))
    h = make_holder(polygon=poly)
    assert len(h.polygon) == 4


def test_holder_besgen_disbukey_kabul():
    poly = tuple(
        (10.0 * math.cos(2 * math.pi * k / 5), 10.0 * math.sin(2 * math.pi * k / 5)) for k in range(5)
    )
    assert alan(poly) > 0
    make_holder(polygon=poly)


# ---------------------------------------------------------------- LatheHolder: hatalar


@pytest.mark.parametrize(
    "poly",
    [
        (),
        ((0.0, 0.0),),
        ((0.0, 0.0), (10.0, 0.0)),
    ],
)
def test_holder_ucten_az_nokta(poly):
    with pytest.raises(CamError):
        make_holder(polygon=poly)


@pytest.mark.parametrize("kotu", [math.nan, math.inf, -math.inf])
@pytest.mark.parametrize("i, j", [(0, 0), (1, 1), (3, 0)])
def test_holder_sonlu_olmayan_nokta(kotu, i, j):
    poly = [list(p) for p in DIKDORTGEN]
    poly[i][j] = kotu
    with pytest.raises(CamError):
        make_holder(polygon=tuple(tuple(p) for p in poly))


def test_holder_saat_yonu_cw():
    cw = tuple(reversed(DIKDORTGEN))
    assert alan(cw) < 0
    with pytest.raises(CamError):
        make_holder(polygon=cw)


@pytest.mark.parametrize(
    "poly",
    [
        ((0.0, 0.0), (10.0, 0.0), (20.0, 0.0)),  # hepsi doğrusal, alan 0
        ((1.0, 1.0), (1.0, 1.0), (1.0, 1.0)),  # tek nokta tekrar
    ],
)
def test_holder_sifir_alan(poly):
    assert alan(poly) == 0.0
    with pytest.raises(CamError):
        make_holder(polygon=poly)


def test_holder_icbukey_kose():
    """L şekli: saat yönü tersi, alan > 0, ama bir içbükey köşe var."""
    L = ((0.0, 0.0), (20.0, 0.0), (20.0, 5.0), (5.0, 5.0), (5.0, 20.0), (0.0, 20.0))
    assert alan(L) > 0
    with pytest.raises(CamError):
        make_holder(polygon=L)


def test_holder_icbukey_ok_ucu():
    """Ok ucu (dart): tek içbükey köşe, alan > 0."""
    dart = ((0.0, 0.0), (10.0, 5.0), (0.0, 10.0), (3.0, 5.0))
    assert alan(dart) > 0
    with pytest.raises(CamError):
        make_holder(polygon=dart)


@pytest.mark.parametrize("b", [0.0, -0.0, -3.0, math.nan, math.inf, -math.inf])
def test_holder_half_width_gecersiz(b):
    with pytest.raises(CamError):
        make_holder(half_width=b)


# ---------------------------------------------------------------- LatheTool.holder


def test_tool_holder_varsayilan_none():
    assert make_tool().holder is None


def test_tool_holder_kabul():
    h = make_holder()
    t = make_tool(edge_len=12.0, holder=h)
    assert t.holder == h


@pytest.mark.parametrize(
    "kotu",
    [
        "PCLNR",
        {"name": "PCLNR", "polygon": [list(p) for p in DIKDORTGEN], "half_width": 6.0},
        DIKDORTGEN,
        6.0,
    ],
)
def test_tool_holder_yanlis_tip(kotu):
    with pytest.raises(CamError):
        make_tool(holder=kotu)


# ---------------------------------------------------------------- serileştirme


def test_holder_dict_gidis_donus():
    h = make_holder()
    assert LatheHolder.from_dict(h.to_dict()) == h


def test_holder_json_gidis_donus():
    h = make_holder()
    h2 = LatheHolder.from_dict(json.loads(json.dumps(h.to_dict())))
    assert h2.name == h.name
    assert h2.half_width == h.half_width
    assert [tuple(p) for p in h2.polygon] == [tuple(p) for p in h.polygon]


@pytest.mark.parametrize("eksik", ["name", "polygon", "half_width"])
def test_holder_from_dict_eksik_alan(eksik):
    d = make_holder().to_dict()
    del d[eksik]
    with pytest.raises(CamError):
        LatheHolder.from_dict(d)


def test_holder_from_dict_bilinmeyen_alan():
    d = make_holder().to_dict()
    d["kalinlik"] = 12.0
    with pytest.raises(CamError):
        LatheHolder.from_dict(d)


def test_holder_from_dict_dogrular():
    """from_dict yapıcıdaki denetimlerden geçer: CW çokgen reddedilir."""
    d = make_holder().to_dict()
    d["polygon"] = [list(p) for p in reversed(DIKDORTGEN)]
    with pytest.raises(CamError):
        LatheHolder.from_dict(d)


def test_tool_to_dict_anahtarlar_yazilir():
    d = make_tool().to_dict()
    assert "edge_len" in d and d["edge_len"] is None
    assert "holder" in d and d["holder"] is None


def test_tool_dict_gidis_donus_tutuculu():
    t = make_tool(edge_len=12.0, holder=make_holder())
    t2 = LatheTool.from_dict(t.to_dict())
    assert t2 == t
    assert isinstance(t2.holder, LatheHolder)
    assert t2.edge_len == pytest.approx(12.0)


def test_tool_json_gidis_donus_tutuculu():
    t = make_tool(edge_len=12.0, holder=make_holder())
    t2 = LatheTool.from_dict(json.loads(json.dumps(t.to_dict())))
    assert t2.edge_len == pytest.approx(12.0)
    assert isinstance(t2.holder, LatheHolder)
    assert t2.holder.name == "PCLNR"
    assert t2.holder.half_width == pytest.approx(6.0)
    assert [tuple(p) for p in t2.holder.polygon] == [tuple(p) for p in DIKDORTGEN]


def test_tool_dict_gidis_donus_tutucusuz():
    t = make_tool()
    assert LatheTool.from_dict(t.to_dict()) == t


def test_tool_eski_sozluk_okunur():
    """edge_len ve holder eklenmeden önceki to_dict biçimi: ikisi None."""
    d = make_tool(edge_len=12.0, holder=make_holder()).to_dict()
    del d["edge_len"]
    del d["holder"]
    t = LatheTool.from_dict(d)
    assert t.edge_len is None
    assert t.holder is None


@pytest.mark.parametrize("edge_len", [0.0, -2.0])
def test_tool_from_dict_edge_len_dogrular(edge_len):
    d = make_tool().to_dict()
    d["edge_len"] = edge_len
    with pytest.raises(CamError):
        LatheTool.from_dict(d)


def test_tool_from_dict_holder_dogrular():
    """İç içe tutucu sözlüğü de doğrulanır (bilinmeyen alan)."""
    d = make_tool(holder=make_holder()).to_dict()
    d["holder"]["kalinlik"] = 1.0
    with pytest.raises(CamError):
        LatheTool.from_dict(d)
