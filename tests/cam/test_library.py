"""SPEC 14 — takım kütüphanesi dosyası ve işlemleri: K4, K5.

Testler sadece SPEC 14 metninden yazıldı; `cam/library.py` uygulama kodu okunmadı.

Dosya biçimi (SPEC 14 Arayüz `save_library`):
`json.dumps(lib.to_dict(), ensure_ascii=False, indent=2) + "\\n"`,
UTF-8, takımlar `id` sırasına dizilmiş.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from cam.gcode import DrillOp
from cam.library import check_tools, find_tools, load_library, materials, remove_tool, save_library
from cam.model import (
    CamError,
    CuttingData,
    LatheTool,
    LatheToolKind,
    Move,
    MoveType,
    Tool,
    ToolHolder,
    ToolKind,
    ToolLibrary,
    Toolpath,
)

ORNEK = Path(__file__).resolve().parents[2] / "examples" / "takim_kutuphanesi.json"


def tutucu() -> ToolHolder:
    return ToolHolder("BT30-ER", 60.0, ((0.0, 15.0), (40.0, 20.0)))


def kutuphane() -> ToolLibrary:
    """Freze + torna takımlı, id'leri karışık sırada eklenmiş uydurma kütüphane."""
    t5 = Tool(
        5,
        "şaft freze Ø10",  # Türkçe karakter: ensure_ascii=False
        ToolKind.FLAT,
        D=10.0,
        flute_length=25.0,
        flutes=3,
        stickout=40.0,
        holder=tutucu(),
        cutting={
            "celik": CuttingData(Vc=200.0, fz=0.05, ap=2.0, ae=5.0),
            "aluminyum": CuttingData(Vc=500.0, fz=0.08),
        },
    )
    t1 = Tool(
        1,
        "kuresel10",
        ToolKind.BALL,
        D=10.0,
        flute_length=20.0,
        flutes=2,
        cutting={"celik": CuttingData(Vc=180.0, fz=0.04)},
    )
    t3 = Tool(3, "matkap6", ToolKind.DRILL, D=6.0, flute_length=40.0, flutes=2, shank_d=6.0)
    t12 = LatheTool(
        12,
        "tornalama CNMG",
        LatheToolKind.TURN,
        nose_r=0.8,
        tip=3,
        kappa_r=95.0,
        eps_r=80.0,
        cutting={"celik": CuttingData(Vc=180.0, fn=0.2), "paslanmaz": CuttingData(Vc=120.0, fn=0.15)},
    )
    t7 = LatheTool(7, "kanal3", LatheToolKind.GROOVE, nose_r=0.2, tip=8, kappa_r=90.0, eps_r=90.0, width=3.0)
    return ToolLibrary([t5, t1, t12, t3, t7])


def beklenen_metin(lib: ToolLibrary) -> str:
    sirali = {"tools": [t.to_dict() for t in sorted(lib.tools, key=lambda t: t.id)]}
    return json.dumps(sirali, ensure_ascii=False, indent=2) + "\n"


# ---------------------------------------------------------------- K4 dosya


def test_save_load_birebir(tmp_path):
    lib = kutuphane()
    yol = tmp_path / "lib.json"
    save_library(lib, yol)
    geri = load_library(yol)
    assert [t.id for t in geri.tools] == [1, 3, 5, 7, 12]
    beklenen = {t.id: t.to_dict() for t in lib.tools}
    assert {t.id: t.to_dict() for t in geri.tools} == beklenen
    assert isinstance(geri.get(12), LatheTool)
    assert isinstance(geri.get(5), Tool)


def test_sirali_kutuphane_to_dict_aynen(tmp_path):
    lib = kutuphane()
    sirali = ToolLibrary(sorted(lib.tools, key=lambda t: t.id))
    yol = tmp_path / "lib.json"
    save_library(sirali, yol)
    assert load_library(yol).to_dict() == sirali.to_dict()


def test_dosya_metni_tanimli_bicimde(tmp_path):
    lib = kutuphane()
    yol = tmp_path / "lib.json"
    save_library(lib, yol)
    assert yol.read_bytes() == beklenen_metin(lib).encode("utf-8")
    assert "şaft freze Ø10" in yol.read_text(encoding="utf-8")


def test_iki_kayit_ayni_bayt(tmp_path):
    lib = kutuphane()
    a, b = tmp_path / "a.json", tmp_path / "b.json"
    save_library(lib, a)
    save_library(lib, b)
    assert a.read_bytes() == b.read_bytes()
    c = tmp_path / "c.json"
    save_library(load_library(a), c)
    assert c.read_bytes() == a.read_bytes()


def test_load_str_yol_kabul(tmp_path):
    lib = kutuphane()
    yol = tmp_path / "lib.json"
    save_library(lib, str(yol))
    assert len(load_library(str(yol)).tools) == 5


def test_save_yinelenen_id_hata(tmp_path):
    t = Tool(1, "a", ToolKind.FLAT, D=6.0, flute_length=10.0)
    u = Tool(1, "b", ToolKind.FLAT, D=8.0, flute_length=10.0)
    with pytest.raises(CamError):
        save_library(ToolLibrary([t, u]), tmp_path / "lib.json")


def test_ornek_kutuphane_okunuyor():
    lib = load_library(ORNEK)
    assert len(lib.tools) >= 1
    lib.validate()


def test_load_dosya_yok_hata_mesajda_yol(tmp_path):
    yol = tmp_path / "yok.json"
    with pytest.raises(CamError) as e:
        load_library(yol)
    assert str(yol) in str(e.value)


def test_load_bozuk_json_hata_mesajda_yol(tmp_path):
    yol = tmp_path / "bozuk.json"
    yol.write_text('{"tools": [', encoding="utf-8")
    with pytest.raises(CamError) as e:
        load_library(yol)
    assert str(yol) in str(e.value)


def test_load_yinelenen_id_hata_mesajda_yol(tmp_path):
    t = Tool(1, "a", ToolKind.FLAT, D=6.0, flute_length=10.0).to_dict()
    u = Tool(1, "b", ToolKind.FLAT, D=8.0, flute_length=10.0).to_dict()
    yol = tmp_path / "cift.json"
    yol.write_text(json.dumps({"tools": [t, u]}), encoding="utf-8")
    with pytest.raises(CamError) as e:
        load_library(yol)
    assert str(yol) in str(e.value)


@pytest.mark.parametrize(
    "bozuk",
    [
        {"id": 1, "name": "x", "kind": "bilinmeyen", "D": 6.0, "flute_length": 10.0},  # tür yok
        {"id": 1, "name": "x", "kind": "duz", "D": -6.0, "flute_length": 10.0},  # D < 0
        {"id": 1, "name": "x", "kind": "duz", "D": 6.0},  # eksik alan
    ],
)
def test_load_gecersiz_takim_hata_mesajda_yol(tmp_path, bozuk):
    yol = tmp_path / "gecersiz.json"
    yol.write_text(json.dumps({"tools": [bozuk]}), encoding="utf-8")
    with pytest.raises(CamError) as e:
        load_library(yol)
    assert str(yol) in str(e.value)


# ---------------------------------------------------------------- K5 işlemler


def ids(tools) -> list[int]:
    return [t.id for t in tools]


def test_find_tools_filtresiz_id_sirasi():
    assert ids(find_tools(kutuphane())) == [1, 3, 5, 7, 12]


def test_find_tools_ture_gore():
    lib = kutuphane()
    assert ids(find_tools(lib, kind=ToolKind.FLAT)) == [5]
    assert ids(find_tools(lib, kind=ToolKind.BALL)) == [1]
    assert ids(find_tools(lib, kind=ToolKind.DRILL)) == [3]
    assert ids(find_tools(lib, kind=LatheToolKind.TURN)) == [12]
    assert ids(find_tools(lib, kind=LatheToolKind.GROOVE)) == [7]
    assert find_tools(lib, kind=LatheToolKind.THREAD) == []


def test_find_tools_capa_gore():
    lib = kutuphane()
    assert ids(find_tools(lib, D=10.0)) == [1, 5]
    assert ids(find_tools(lib, D=10.0 + 1e-10)) == [1, 5]  # |D − t.D| ≤ 1e-9
    assert find_tools(lib, D=10.001) == []
    assert ids(find_tools(lib, D=6.0)) == [3]


def test_find_tools_malzemeye_gore():
    lib = kutuphane()
    assert ids(find_tools(lib, material="celik")) == [1, 5, 12]
    assert ids(find_tools(lib, material="aluminyum")) == [5]
    assert ids(find_tools(lib, material="paslanmaz")) == [12]
    assert find_tools(lib, material="titanyum") == []


def test_find_tools_birlesik_filtre():
    lib = kutuphane()
    assert ids(find_tools(lib, kind=ToolKind.FLAT, D=10.0, material="celik")) == [5]
    assert find_tools(lib, kind=ToolKind.BALL, material="aluminyum") == []


def test_remove_tool():
    lib = kutuphane()
    remove_tool(lib, 5)
    assert ids(find_tools(lib)) == [1, 3, 7, 12]
    with pytest.raises(CamError):
        lib.get(5)


def test_remove_tool_yoksa_hata():
    lib = kutuphane()
    with pytest.raises(CamError):
        remove_tool(lib, 99)
    assert len(lib.tools) == 5


def test_materials_sirali():
    assert materials(kutuphane()) == ["aluminyum", "celik", "paslanmaz"]
    assert materials(ToolLibrary()) == []


def cep(tool: Tool) -> Toolpath:
    return Toolpath("cep", tool, (0.0, 0.0, 5.0), [Move(MoveType.LINEAR, (0.0, 0.0, -1.0), 100.0)], rpm=5000)


def delik(tool: Tool) -> DrillOp:
    return DrillOp(
        "delik", tool, rpm=2000, start=(0.0, 0.0, 5.0), holes=[(10.0, 10.0)], z=-5.0, r=2.0, feed=80.0
    )


def test_check_tools_dogru():
    lib = kutuphane()
    check_tools(lib, [cep(lib.get(5)), delik(lib.get(3))])
    # aynı tanımlı başka nesne de geçer (to_dict eşit)
    kopya = Tool.from_dict(lib.get(5).to_dict())
    check_tools(lib, [cep(kopya)])
    check_tools(lib, [])


def test_check_tools_eksik_takim():
    lib = kutuphane()
    yabanci = Tool(9, "freze8", ToolKind.FLAT, D=8.0, flute_length=20.0)
    with pytest.raises(CamError):
        check_tools(lib, [cep(lib.get(5)), cep(yabanci)])


def test_check_tools_ayni_id_farkli_tanim():
    """T5 numarası kütüphanedeki T5'ten farklı bir takımı çağırmasın."""
    lib = kutuphane()
    d = lib.get(5).to_dict()
    d["D"] = 12.0
    yanlis = Tool.from_dict(d)
    with pytest.raises(CamError):
        check_tools(lib, [cep(yanlis)])
    d = lib.get(3).to_dict()
    d["flute_length"] = 30.0
    with pytest.raises(CamError):
        check_tools(lib, [delik(Tool.from_dict(d))])
