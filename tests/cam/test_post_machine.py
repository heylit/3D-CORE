"""SPEC 30 — tezgâh profili dosyası (K3) ve profil doğrulama (K4).

Testler SPEC 30 metninden (Arayüz "Profil", K3, K4) ve `cam/model.py` arayüzünden yazıldı.
"""

from __future__ import annotations

import json
import math
from dataclasses import replace
from pathlib import Path

import pytest

import cam.post
from cam.model import CamError
from cam.post import AxisLimits, MachineProfile, builtin_machines, load_machine, save_machine

PROFIL_DIZINI = Path(cam.post.__file__).parent / "profiles"
ORNEKLER = {
    "ORNEK-GRBL-ROUTER": ("ornek-grbl-router.json", "grbl"),
    "ORNEK-FANUC-DIK": ("ornek-fanuc-dik.json", "fanuc"),
    "ORNEK-HAAS-DIK": ("ornek-haas-dik.json", "haas"),
}


def gecerli() -> MachineProfile:
    """Bütün alanları dolu, geçerli uydurma profil (K4'te tek tek bozulur)."""
    return MachineProfile(
        name="TEST DIK_1",
        controller="fanuc",
        kind="mill",
        x=AxisLimits(-300.0, 300.0),
        y=AxisLimits(-200.0, 200.0),
        z=AxisLimits(-400.0, 0.0),
        rpm_min=50.0,
        rpm_max=8000.0,
        feed_max=5000.0,
        rapid=(20_000.0, 20_000.0, 15_000.0),
        tool_slots=20,
        tool_change_z=0.0,
        program_no_range=(1, 7999),
        decimals=3,
        verified=False,
    )


# ---------------------------------------------------------------- K3: profil dosyası


def test_builtin_machines_are_the_three_examples():
    """K3: `builtin_machines()` örnek profilleri ada göre verir; hepsi doğrulanmamış (uydurma)."""
    ms = builtin_machines()
    assert set(ms) == set(ORNEKLER)
    for ad, (_, dil) in ORNEKLER.items():
        m = ms[ad]
        assert isinstance(m, MachineProfile)
        assert m.name == ad
        assert m.controller == dil
        assert m.kind == "mill"
        assert m.verified is False  # SPEC: uydurma kurs ve sınırlar, verified: false
        m.validate()


@pytest.mark.parametrize("ad", list(ORNEKLER))
def test_example_profile_files_load(ad):
    """K3: üç örnek dosya yükleniyor ve `builtin_machines()` ile aynı."""
    dosya, dil = ORNEKLER[ad]
    m = load_machine(PROFIL_DIZINI / dosya)
    assert m.name == ad and m.controller == dil
    assert m == builtin_machines()[ad]


@pytest.mark.parametrize("ad", list(ORNEKLER))
def test_save_load_roundtrip_and_bytes(ad, tmp_path):
    """K3: `load(save(m)) == m`; iki kayıt aynı bayt;
    biçim `json.dumps(to_dict, ensure_ascii=False, indent=2) + "\\n"`."""
    m = load_machine(PROFIL_DIZINI / ORNEKLER[ad][0])
    a, b = tmp_path / "a.json", tmp_path / "b.json"
    save_machine(m, a)
    save_machine(load_machine(a), b)
    assert load_machine(a) == m
    assert a.read_bytes() == b.read_bytes()
    beklenen = json.dumps(m.to_dict(), ensure_ascii=False, indent=2) + "\n"
    assert a.read_bytes() == beklenen.encode("utf-8")


def test_save_load_full_profile(tmp_path):
    """K3: bütün alanları dolu profil de gidiş-dönüşte aynı (str yol da kabul)."""
    m = gecerli()
    p = tmp_path / "tam.json"
    save_machine(m, str(p))
    assert load_machine(str(p)) == m


def test_missing_file(tmp_path):
    """K3: dosya yok → CamError, mesajda dosya yolu."""
    p = tmp_path / "yok.json"
    with pytest.raises(CamError) as e:
        load_machine(p)
    assert str(p) in str(e.value)


def test_broken_json(tmp_path):
    """K3: bozuk JSON → CamError (json.JSONDecodeError değil), mesajda dosya yolu."""
    p = tmp_path / "bozuk.json"
    p.write_text('{"name": "X", ', encoding="utf-8")
    with pytest.raises(CamError) as e:
        load_machine(p)
    assert str(p) in str(e.value)


def test_not_an_object(tmp_path):
    """Geçersiz değer: kök JSON nesne değilse (liste) CamError, mesajda yol."""
    p = tmp_path / "liste.json"
    p.write_text("[1, 2]\n", encoding="utf-8")
    with pytest.raises(CamError) as e:
        load_machine(p)
    assert str(p) in str(e.value)


def _yaz(tmp_path, d: dict, ad: str = "p.json") -> Path:
    p = tmp_path / ad
    p.write_text(json.dumps(d, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return p


def test_unknown_key(tmp_path):
    """K3: bilinmeyen anahtar → CamError, mesajda yol ve alan adı."""
    d = gecerli().to_dict()
    d["devir_carpani"] = 2
    p = _yaz(tmp_path, d)
    with pytest.raises(CamError) as e:
        load_machine(p)
    assert str(p) in str(e.value)
    assert "devir_carpani" in str(e.value)


def test_missing_rpm_max(tmp_path):
    """K3: eksik `rpm_max` → CamError, mesajda yol ve alan adı."""
    d = gecerli().to_dict()
    del d["rpm_max"]
    p = _yaz(tmp_path, d)
    with pytest.raises(CamError) as e:
        load_machine(p)
    assert str(p) in str(e.value)
    assert "rpm_max" in str(e.value)


def test_invalid_value_in_file(tmp_path):
    """Arayüz: geçersiz değer (feed_max = 0) → CamError, mesajda yol ve alan."""
    d = gecerli().to_dict()
    d["feed_max"] = 0
    p = _yaz(tmp_path, d)
    with pytest.raises(CamError) as e:
        load_machine(p)
    assert str(p) in str(e.value)
    assert "feed_max" in str(e.value)


def test_utf8_file(tmp_path):
    """Dosya UTF-8 okunur: ASCII dışı karakterli (geçersiz) ad CamError verir, UnicodeDecodeError değil."""
    d = gecerli().to_dict()
    d["name"] = "ÖRNEK"
    p = _yaz(tmp_path, d)
    with pytest.raises(CamError):
        load_machine(p)


# ---------------------------------------------------------------- K4: validate() kuralları


def test_valid_profile_passes():
    gecerli().validate()
    replace(gecerli(), x=None, y=None, z=None, tool_change_z=None).validate()  # kurssuz profil geçerli


@pytest.mark.parametrize(
    "alan",
    [
        {"name": "örnek"},  # ASCII dışı
        {"name": "TEST-Ş"},
        {"name": "test"},  # küçük harf
        {"name": ""},  # 1–32 karakter
        {"name": "A" * 33},
        {"name": "TEST(1)"},  # izinli küme [A-Z0-9 _-] dışı
        {"controller": "mazak"},
        {"controller": "FANUC"},
        {"x": AxisLimits(100.0, 100.0)},  # min ≥ max
        {"y": AxisLimits(10.0, -10.0)},
        {"z": AxisLimits(0.0, -400.0), "tool_change_z": None},
        {"rpm_min": 8000.0},  # rpm_min ≥ rpm_max
        {"rpm_min": 9000.0},
        {"rpm_min": -1.0},  # 0 ≤ rpm_min
        {"feed_max": 0.0},
        {"feed_max": -100.0},
        {"rapid": (20_000.0, 0.0, 15_000.0)},
        {"rapid": (20_000.0, 20_000.0, -1.0)},
        {"tool_slots": 0},
        {"tool_change_z": 0.001},  # Z kursu [-400, 0] dışında
        {"tool_change_z": -400.001},
        {"z": None},  # tool_change_z var, Z kursu yok: konumu denetlenemeyen G53 yazılmaz
        {"program_no_range": (0, 7999)},
        {"program_no_range": (100, 99)},
        {"program_no_range": (1, 10_000)},  # Fanuc 4 hane
        {"controller": "haas", "program_no_range": (1, 100_000)},  # Haas 5 hane
        {"decimals": 2},
        {"decimals": 5},
        {"kind": "lathe"},  # SPEC 21'den sonra
        {"kind": "router"},
    ],
    ids=lambda d: ",".join(f"{k}={v!r}" for k, v in d.items()),
)
def test_validate_rule(alan):
    """K4: her kural ayrı ayrı CamError."""
    with pytest.raises(CamError):
        replace(gecerli(), **alan).validate()


@pytest.mark.parametrize(
    "alan",
    [
        {"rpm_max": math.nan},
        {"rpm_min": math.nan},
        {"feed_max": math.nan},
        {"feed_max": math.inf},
        {"x": AxisLimits(math.nan, 100.0)},
        {"z": AxisLimits(-400.0, math.inf), "tool_change_z": None},
        {"tool_change_z": math.nan},
        {"rapid": (math.nan, 1.0, 1.0)},
    ],
    ids=lambda d: ",".join(f"{k}={v!r}" for k, v in d.items()),
)
def test_validate_nan(alan):
    """K4: nan / inf → CamError (sessiz hata yok)."""
    with pytest.raises(CamError):
        replace(gecerli(), **alan).validate()


@pytest.mark.parametrize(
    "alan",
    [
        {"controller": "haas", "program_no_range": (1, 99_999)},
        {"program_no_range": (1, 9999)},
        {"program_no_range": (7, 7)},
        {"tool_change_z": -400.0},  # kurs sınırları dahil
        {"tool_slots": None},
        {"tool_slots": 1},
        {"rapid": None},
        {"decimals": 4},
        {"rpm_min": 0.0},
        {"controller": "grbl"},
        {"name": "A" * 32},
        {"name": "0 _-Z"},
    ],
    ids=lambda d: ",".join(f"{k}={v!r}" for k, v in d.items()),
)
def test_validate_accepts_boundaries(alan):
    """K4'ün sınır değerleri geçerlidir (kurallar fazla sıkı değil)."""
    replace(gecerli(), **alan).validate()


def test_load_runs_validate(tmp_path):
    """K3/K4: dosyadan yüklenen profil doğrulanır (decimals = 2 → CamError)."""
    d = gecerli().to_dict()
    d["decimals"] = 2
    with pytest.raises(CamError):
        load_machine(_yaz(tmp_path, d))
