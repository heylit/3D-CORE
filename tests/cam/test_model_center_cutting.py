"""Tool.center_cutting ("merkezden keser") alanı testleri.

Testler yalnızca onaylanan davranıştan (SPEC 03 Ek A, SPEC 04 Ek C) ve cam/model.py'deki
mevcut Tool arayüzünden yazıldı; alanın uygulama kodu okunmadı.

Davranış:
- center_cutting: bool, varsayılan True.
- bool olmayan değer (0 ve 1 dahil) → CamError.
- kind DRILL iken False → CamError (matkap ucu her zaman merkezden keser).
- to_dict "center_cutting" anahtarını yazar.
- from_dict'te anahtar isteğe bağlı; yoksa True (eski JSON dosyaları uyumlu kalır).
"""

from __future__ import annotations

import json

import pytest

from cam.model import CamError, Tool, ToolKind

# Konik takımda (SPEC 06b) tip_angle zorunlu; ToolKind.CONE yoksa bu ayar kullanılmaz.
TIP_ANGLE_CONE = 90.0


def kind_kw(kind: ToolKind) -> dict:
    """Takım tipinin zorunlu ek alanları (CONE: tip_angle)."""
    return {"tip_angle": TIP_ANGLE_CONE} if kind.name == "CONE" else {}


def make_tool(kind: ToolKind = ToolKind.FLAT, **kw) -> Tool:
    """Ø6 takım; kind ve ek alanlar parametre."""
    return Tool(id=1, name="t6", kind=kind, D=6.0, flute_length=20.0, **{**kind_kw(kind), **kw})


def old_dict(kind: ToolKind = ToolKind.FLAT) -> dict:
    """center_cutting alanı eklenmeden önceki to_dict biçimi (eski JSON dosyası)."""
    return {
        "id": 3,
        "name": "eski",
        "kind": kind.value,
        "D": 8.0,
        "flute_length": 25.0,
        "corner_r": 0.0 if kind is not ToolKind.BALL else 4.0,
        "flutes": 2,
        "shank_d": None,
        "stickout": None,
        "holder": None,
        "cutting": {},
        **kind_kw(kind),
    }


# ---------------------------------------------------------------- varsayılan


@pytest.mark.parametrize("kind", list(ToolKind))
def test_default_true(kind):
    t = make_tool(kind)
    assert t.center_cutting is True


@pytest.mark.parametrize("kind", [ToolKind.FLAT, ToolKind.BALL])
def test_explicit_values_accepted_for_mills(kind):
    assert make_tool(kind, center_cutting=True).center_cutting is True
    assert make_tool(kind, center_cutting=False).center_cutting is False


def test_drill_true_accepted():
    assert make_tool(ToolKind.DRILL, center_cutting=True).center_cutting is True


# ---------------------------------------------------------------- doğrulama


@pytest.mark.parametrize("deger", [0, 1, 0.0, 1.0, "True", "false", None, [True]])
def test_non_bool_rejected(deger):
    with pytest.raises(CamError):
        make_tool(center_cutting=deger)


def test_drill_false_rejected():
    with pytest.raises(CamError):
        make_tool(ToolKind.DRILL, center_cutting=False)


def test_drill_kind_as_string_false_rejected():
    # kind dize olarak verilse de ("matkap") kural geçerli
    with pytest.raises(CamError):
        Tool(id=1, name="m", kind="matkap", D=6.0, flute_length=20.0, center_cutting=False)


# ---------------------------------------------------------------- to_dict


@pytest.mark.parametrize("deger", [True, False])
def test_to_dict_writes_key(deger):
    d = make_tool(center_cutting=deger).to_dict()
    assert "center_cutting" in d
    assert d["center_cutting"] is deger


def test_to_dict_default_writes_true():
    assert make_tool().to_dict()["center_cutting"] is True


# ---------------------------------------------------------------- from_dict


@pytest.mark.parametrize("kind", list(ToolKind))
def test_from_dict_missing_key_is_true(kind):
    t = Tool.from_dict(old_dict(kind))
    assert t.center_cutting is True


@pytest.mark.parametrize("deger", [True, False])
def test_roundtrip(deger):
    t = make_tool(center_cutting=deger)
    t2 = Tool.from_dict(t.to_dict())
    assert t2.center_cutting is deger
    assert t2.to_dict() == t.to_dict()


@pytest.mark.parametrize("deger", [True, False])
def test_json_roundtrip(deger):
    t = make_tool(ToolKind.BALL, center_cutting=deger)
    t2 = Tool.from_dict(json.loads(json.dumps(t.to_dict())))
    assert t2.center_cutting is deger


def test_from_dict_old_json_text():
    # center_cutting anahtarı olmayan eski bir JSON metni yüklenir
    t = Tool.from_dict(json.loads(json.dumps(old_dict())))
    assert t.center_cutting is True
    assert t.to_dict()["center_cutting"] is True


@pytest.mark.parametrize("deger", [0, 1, "true", None])
def test_from_dict_non_bool_rejected(deger):
    d = old_dict()
    d["center_cutting"] = deger
    with pytest.raises(CamError):
        Tool.from_dict(d)


def test_from_dict_drill_false_rejected():
    d = old_dict(ToolKind.DRILL)
    d["center_cutting"] = False
    with pytest.raises(CamError):
        Tool.from_dict(d)
