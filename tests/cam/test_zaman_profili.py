"""SPEC 72 — cam/sim/zaman_profili.py testleri: tezgâh zaman profili JSON okuma / yazma (K12, K13).

Testler yalnız specs/72-cevrim-suresi.md metninden ve iskeletin arayüzünden
(load_time_profile(path, machine=None), save_time_profile(p, path);
durum/72-cevrim-suresi.md) yazıldı; fonksiyon gövdeleri okunmadı.

Varsayımlar (koordinatöre bildirildi):
- JSON anahtarları dataclass alan adlarıyla aynı (TimeProfile: machine, dynamics, tool_change, ...; Dynamics:
  v_max, a_max, j_max, ...); bozma testleri anahtarı ağaçta adıyla arar, iç içe yapıyı varsaymaz.
- Gidiş-dönüş: save → load → save iki dosyanın baytları aynı ve yüklenen profil kaydedilenle eşit (==).
- Örnek profiller cam/post/profiles/zaman/*.json: hepsi yüklenir ve verified = False
  (Karar 2: uydurma, ölçülmedi).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from cam.model import CamError, MachineProfile
from cam.sim.cevrim import TimeProfile
from cam.sim.sure import Dynamics
from cam.sim.zaman_profili import load_time_profile, save_time_profile

ROOT = Path(__file__).resolve().parents[2]
EXAMPLES = ROOT / "cam" / "post" / "profiles" / "zaman"
NAME = "UYDURMA-DMU-50"


def prof(**kw) -> TimeProfile:
    """Uydurma (ölçülmemiş) değerli profil: döner eksen, sarsıntı ve tüm isteğe bağlı alanlar dolu."""
    d = Dynamics(
        v_max=(42000.0, 42000.0, 42000.0),
        a_max=(4000.0, 4000.0, 3500.0),
        j_max=(40000.0, 40000.0, 30000.0),
        rot_v=(9000.0,),
        rot_a=(1200.0,),
        tol=0.01,
        lookahead=200,
    )
    args = dict(
        machine=NAME,
        dynamics=d,
        tool_change=6.5,
        turret_index=0.0,
        spindle_accel=1500.0,
        pallet=0.0,
        program_fixed=12.0,
        k=1.08,
        verified=False,
        spindle_overlap="toplam",
    )
    args.update(kw)
    return TimeProfile(**args)


def machine(name: str = NAME) -> MachineProfile:
    return MachineProfile(name=name, controller="sinumerik", rpm_max=12000.0, feed_max=10000.0)


def edit_key(obj, key: str, fn) -> bool:
    """JSON ağacında adı key olan ilk anahtarı fn(eski) ile değiştirir (fn None dönerse siler)."""
    if isinstance(obj, dict):
        if key in obj:
            new = fn(obj[key])
            if new is None:
                del obj[key]
            else:
                obj[key] = new
            return True
        return any(edit_key(v, key, fn) for v in obj.values())
    if isinstance(obj, list):
        return any(edit_key(v, key, fn) for v in obj)
    return False


def saved(tmp_path: Path, p: TimeProfile | None = None) -> tuple[Path, dict]:
    path = tmp_path / "profil.json"
    save_time_profile(prof() if p is None else p, path)
    return path, json.loads(path.read_text(encoding="utf-8"))


# ================================================================ K12: gidiş-dönüş


@pytest.mark.parametrize(
    "p",
    [
        prof,
        lambda: prof(dynamics=Dynamics(v_max=(1.0, 2.0, 3.0), a_max=(4.0, 5.0, 6.0), j_max=None)),
        lambda: prof(spindle_accel=None),
    ],
    ids=["dolu", "sarsintisiz", "is_mili_anlik"],
)
def test_roundtrip_bytes_identical(tmp_path, p):
    """K12: save → load → save: baytlar aynı, yüklenen profil kaydedilenle eşit."""
    p = p()
    a, b = tmp_path / "a.json", tmp_path / "b.json"
    save_time_profile(p, a)
    q = load_time_profile(a)
    save_time_profile(q, b)
    assert a.read_bytes() == b.read_bytes()
    assert q == p
    assert isinstance(q.dynamics, Dynamics)
    assert q.dynamics.j_max == p.dynamics.j_max


def test_file_is_json(tmp_path):
    """K12: dosya geçerli JSON; makine adı içinde."""
    _, data = saved(tmp_path)
    assert NAME in json.dumps(data)


def test_machine_name_match(tmp_path):
    """K12: machine verilirse ad eşleşmesi: aynı ad kabul, farklı ad CamError (mesajda dosya yolu)."""
    path, _ = saved(tmp_path)
    assert load_time_profile(path, machine=machine()).machine == NAME
    with pytest.raises(CamError) as e:
        load_time_profile(path, machine=machine("BASKA-TEZGAH"))
    assert str(path) in str(e.value) or path.name in str(e.value)


# ================================================================ K12 / K13: bozuk dosyalar


def write_json(path: Path, data) -> None:
    path.write_text(json.dumps(data), encoding="utf-8")


def assert_load_error(path: Path) -> None:
    with pytest.raises(CamError) as e:
        load_time_profile(path)
    assert str(path) in str(e.value) or path.name in str(e.value), str(e.value)


def test_unknown_key_raises(tmp_path):
    """K12: bilinmeyen anahtar → CamError (mesajda dosya yolu)."""
    path, data = saved(tmp_path)
    data["bilinmeyen_alan"] = 1
    write_json(path, data)
    assert_load_error(path)


def test_unknown_nested_key_raises(tmp_path):
    """K12: dinamik bloğunda bilinmeyen anahtar da CamError."""
    path, data = saved(tmp_path)
    assert edit_key(data, "a_max", lambda v: v)  # öz denetim: alan adları dataclass adlarıyla aynı
    edit_key(data, "v_max", lambda v: v)

    def add(obj):
        if isinstance(obj, dict) and "a_max" in obj:
            obj["sarsinti_x"] = 5
            return True
        return isinstance(obj, dict) and any(add(v) for v in obj.values())

    assert add(data)
    write_json(path, data)
    assert_load_error(path)


@pytest.mark.parametrize(
    "key, fn",
    [
        ("a_max", lambda v: [-abs(v[0]), *v[1:]]),  # negatif ivme
        ("v_max", lambda v: [0.0, *v[1:]]),
        ("tool_change", lambda v: -1.0),
        ("k", lambda v: 0.0),
        ("tool_change", lambda v: None),  # eksik alan
        ("machine", lambda v: None),
        ("dynamics", lambda v: None),
    ],
    ids=["negatif_ivme", "sifir_hiz", "negatif_tc", "k_sifir", "eksik_tc", "eksik_ad", "eksik_dinamik"],
)
def test_bad_values_raise(tmp_path, key, fn):
    """K12 / K13: negatif ivme, pozitif olmayan değer, eksik alan → CamError (mesajda dosya yolu)."""
    path, data = saved(tmp_path)
    assert edit_key(data, key, fn)
    write_json(path, data)
    assert_load_error(path)


@pytest.mark.parametrize("text", ["{", "", "[1, 2]", '{"machine": '], ids=["yarim", "bos", "liste", "kesik"])
def test_broken_json_raises(tmp_path, text):
    """Arayüz: bozuk JSON → CamError (mesajda dosya yolu)."""
    path = tmp_path / "bozuk.json"
    path.write_text(text, encoding="utf-8")
    assert_load_error(path)


def test_missing_file_raises(tmp_path):
    """Arayüz: olmayan dosya → CamError (mesajda dosya yolu)."""
    assert_load_error(tmp_path / "yok.json")


# ================================================================ örnek profiller (Karar 2)


def test_example_profiles_load_and_unverified(tmp_path):
    """Dosyalar / Karar 2: cam/post/profiles/zaman/*.json örnekleri var, hepsi yüklenir, gidiş-dönüşü bayt
    olarak aynı ve verified = False (uydurma, ölçülmedi)."""
    save_time_profile(prof(), tmp_path / "x.json")  # yazıcı yokken "uygulanmamış" kalır
    files = sorted(EXAMPLES.glob("*.json"))
    assert files, f"{EXAMPLES} altında örnek profil yok"
    for f in files:
        p = load_time_profile(f)
        assert p.verified is False, f.name
        out = tmp_path / f.name
        save_time_profile(p, out)
        assert load_time_profile(out) == p
