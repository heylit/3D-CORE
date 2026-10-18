"""
SPEC 47a testlerinin ortak yardımcıları: planı köprüden bağımsız olarak doğrudan SPEC 29 ile kurmak.

Köprünün (`tezgah.ekranlar._plan_kopru`) çıktısı her zaman buradaki doğrudan çağrılarla karşılaştırılır:
`plan_mill` / `plan_mill_features` / `plan_turn` (SPEC 29), `turn_profile` (SPEC 28). Kütüphane süzgeci de
burada elle yazılır (köprünün `kutuphane_suz`'u kullanılmaz).

Bağımlılık yoksa (SPEC 29 kodu, SPEC 28, OCCT) test atlanır; SPEC 29 iskeleti varken NotImplementedError
"uygulanmamış" sayılır (conftest.py).
"""

from __future__ import annotations

import importlib
import json
import re

import pytest

from cam.model import ToolLibrary

PLAN = "/api/ekran/plan"

# SPEC 29 §1: gerekçe ve not kodları (sabit küme)
GEREKCE_KODLARI = (
    "kesme_verisi_yok",
    "takim_yok",
    "takim_sigmiyor",
    "kesici_boy_yetmez",
    "ustten_erisilemez",
    "havsa_takimi_yok",
    "kilavuz_cevrimi_yok",
    "baglama_carpismasi",
    "on_delik_yok",
    "genel_girinti",
)
NOT_KODLARI = ("kose_artigi", "yan_paso_kisildi", "delik_tasma_kisildi", "ikinci_baglama")

# Örnek adları, OCCT gerektirenler işaretli (SPEC 47 "Örnek işler")
FREZE = [pytest.param("plan_blogu", marks=pytest.mark.occt), "plan_engelli"]
HEPSI = [*FREZE, pytest.param("plan_mili", marks=pytest.mark.occt)]


def spec29():
    """SPEC 29 kodu yoksa testi atlar."""
    pytest.importorskip("cam.plan", reason="SPEC 29 (cam.plan) henüz yok")
    pytest.importorskip("cam.plan_verify", reason="SPEC 29 (cam.plan_verify) henüz yok")


def girdi(ad: str):
    """Örneğin girdisi (`_plan_ornekler.ornek`); torna örneği SPEC 29 torna ve SPEC 28 ister."""
    spec29()
    po = pytest.importorskip("tezgah.ekranlar._plan_ornekler", reason="47a iskeleti (_plan_ornekler) yok")
    g = po.ornek(ad)
    if g.tur == "torna":
        pytest.importorskip("cam.plan_turn", reason="SPEC 29 torna (cam.plan_turn) henüz yok")
        pytest.importorskip("cam.turn_profile", reason="SPEC 28 (cam.turn_profile) henüz yok")
    return g


def suz(lib: ToolLibrary, kapali) -> ToolLibrary:
    """`kapali` kimlikli takımları çıkarılmış yeni kütüphane (elle; sıra korunur)."""
    return ToolLibrary([t for t in lib.tools if t.id not in set(kapali)])


def planla(g, lib: ToolLibrary | None = None, secenekler: dict | None = None):
    """Girdinin planı, doğrudan SPEC 29 ile (köprüsüz)."""
    lib = g.lib if lib is None else lib
    s = {**g.secenekler, **(secenekler or {})}
    # importlib: modüller henüz olmayabilir; ruff sürümleri arası import sıralama farkına da takılmaz
    if g.tur == "torna":
        pt = importlib.import_module("cam.plan_turn")
        tp = importlib.import_module("cam.turn_profile").turn_profile(g.part)
        return pt.plan_turn(tp.outer, g.stok, lib, g.malzeme, pt.TurnOptions(**s), inner=tp.inner)
    pm = importlib.import_module("cam.plan")
    opt = pm.MillOptions(**s)
    if g.part is None:
        return pm.plan_mill_features(g.features, g.part_zmin, g.stok, lib, g.malzeme, options=opt)
    return pm.plan_mill(g.part, g.stok, lib, g.malzeme, options=opt)


def takim_degisimi(plan) -> int:
    """Freze: `tool_changes()`; torna: ilk takım + ardışık farklı takım geçişleri (SPEC 47 veri modeli)."""
    if hasattr(plan, "tool_changes"):
        return plan.tool_changes()
    ids = [r["tool_id"] for r in plan.summary()]
    return sum(1 for i, t in enumerate(ids) if i == 0 or t != ids[i - 1])


_GRUP = re.compile(r"^([a-z_]+)\[([0-9]+(?:,[0-9]+)*)\]$")


def ac(feature: str) -> list[str]:
    """İşlemin `feature` alanını tek adreslere açar (SPEC 29 §1): "holes[1,4]" → ["holes[1]", "holes[4]"]."""
    m = _GRUP.match(feature)
    if m is None:
        return [feature]
    return [f"{m.group(1)}[{i}]" for i in m.group(2).split(",")]


def ozellik_adresleri(plan) -> list[str]:
    """SPEC 27 sonucundaki adresler, SPEC 29 §1 sırasıyla (köprüden bağımsız)."""
    if hasattr(plan, "features"):
        f = plan.features
        return [
            *(f"faces[{i}]" for i in range(len(f.faces))),
            *(f"opens[{i}]" for i in range(len(f.opens))),
            *(f"pockets[{i}]" for i in range(len(f.pockets))),
            *(f"holes[{i}]" for i in range(len(f.holes))),
        ]
    tf = plan.outer
    out = ["alin"] if tf.z_face is not None else []
    out.append("dis")
    if plan.inner is not None:
        out.append("ic")
    out += [f"grooves[{i}]" for i in range(len(tf.grooves))]
    out += [f"recesses[{i}]" for i in range(len(tf.recesses))]
    return out


def tasiyanlar(plan) -> dict[str, set[str]]:
    """adres → o adresi (ya da onu içeren delik grubunu) taşıyan işlemlerin adları."""
    out: dict[str, set[str]] = {}
    for op in plan.ops:
        for a in ac(op.feature):
            out.setdefault(a, set()).add(op.name)
    return out


def jt(x):
    """JSON gidiş-dönüşü (nan/inf yasak): sözlükleri JSON türleriyle karşılaştırmak için."""
    return json.loads(json.dumps(x, allow_nan=False))


def ozet_satirlari(P: dict) -> list[dict]:
    """`Plan["islemler"]` satırlarından `sure` alanı çıkarılmış hali (= `summary()` satırı)."""
    return [{k: v for k, v in s.items() if k != "sure"} for s in P["islemler"]]


KONTROL_ALANLARI = {"kimlik", "baslik", "deger", "birim", "durum", "aciklama", "spec"}


def kontrol(kontroller: list[dict], kimlik: str) -> dict:
    """Listede tam bir kez bulunan kontrol (SPEC 24 `Kontrol` biçiminde)."""
    k = [x for x in kontroller if x["kimlik"] == kimlik]
    assert len(k) == 1, (kimlik, [x["kimlik"] for x in kontroller])
    assert set(k[0]) == KONTROL_ALANLARI, k[0]
    assert k[0]["durum"] in ("tamam", "uyari", "hata")
    return k[0]
