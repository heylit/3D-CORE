"""
SPEC 62 §3 — canlı fark: iki freze planı (SPEC 29 `MillPlan`) arasında işlem, süre ve maliyet farkı.

İşlemler **özellik adresi + işlem türü** ile eşleşir: `anahtar = f"{op.feature}|{op.kind}"`. Aynı anahtar bir
planda birden çok kez geçerse ikinci ve sonrakilere geçiş sırasıyla "#2", "#3" … eklenir.
    eklendi : yalnız yenide olan anahtar (dt = +t_yeni)
    kalkti  : yalnız eskide olan anahtar (dt = −t_eski)
    degisti : iki tarafta; takım (tool_id), devir (n), ilerleme (F), paso (a_p, stepover) ya da yol
              geometrisi (`yol_ozeti`) farklı (dt = t_yeni − t_eski)
    ayni    : geri kalanı (dt = t_yeni − t_eski)
Σ dt_i = Σ t_yeni − Σ t_eski = "dt". Sıra: önce yeni plandaki sırayla eklendi / degisti / ayni, sonra eski
plandaki sırayla kalkti.

Süreler işlem başına saniye, `plan.ops` ile aynı sırada; 72 birleşene kadar `islem_sureleri` (SPEC 05
`move_time` toplamı + takım değişimi). Maliyet (58) yoksa `dmaliyet` None. Süre listesinin uzunluğu
`len(plan.ops)` değilse ya da süre sonlu değilse → core.model.ModelError.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

from cam.plan import MillPlan, PlannedOp
from cam.sim import Machine

DURUMLAR = ("eklendi", "kalkti", "degisti", "ayni")
KARSILASTIRILAN = ("tool_id", "n", "F", "a_p", "stepover", "yol")  # ayrinti["alanlar"] bu adlardan


@dataclass(frozen=True)
class IslemFarki:
    """Bir işlemin farkı.

    anahtar : "feature|kind" (tekrarda "#k" ekli)
    durum   : DURUMLAR'dan biri
    dt      : süre farkı [s]
    ayrinti : {"ad_eski", "ad_yeni": str | None, "sira_eski", "sira_yeni": int | None (plan.ops indeksi),
               "alanlar": [değişen alan adları, KARSILASTIRILAN sırasıyla]}
    """

    anahtar: str
    durum: str
    dt: float
    ayrinti: dict = field(default_factory=dict)


def anahtarlar(plan: MillPlan) -> list[str]:
    """plan.ops sırasıyla işlem anahtarları (tekrarda "#2", "#3" …)."""
    raise NotImplementedError("SPEC 62: anahtarlar")


def yol_ozeti(op: PlannedOp) -> str:
    """İşlemin yol geometrisinin kanonik özeti (SHA-256, onaltılık): hareketler ya da delik noktaları ve
    çevrim parametreleri. Aynı yol → aynı özet."""
    raise NotImplementedError("SPEC 62: yol_ozeti")


def islem_sureleri(plan: MillPlan, machine: Machine | None = None) -> list[float]:
    """72 öncesi süre modeli: işlem başına SPEC 05 hareket süreleri + takım değişimi [s], plan.ops sırasıyla.
    machine None → cam.sim.Machine()."""
    raise NotImplementedError("SPEC 62: islem_sureleri")


def plan_farki(
    eski: MillPlan,
    yeni: MillPlan,
    sure_eski: Sequence[float],
    sure_yeni: Sequence[float],
    maliyet: tuple[float, float] | None = None,
) -> dict:
    """{"islemler": [IslemFarki], "dt": float, "dmaliyet": float | None,
    "planlanamayan": {"yeni": [Unplanned], "giden": [Unplanned]}, "sira_degisti": bool}

    maliyet = (eski, yeni) toplam; dmaliyet = yeni − eski. planlanamayan: (feature, code) anahtarıyla
    yalnız yenide / yalnız eskide olanlar. sira_degisti: iki planda da olan anahtarların göreli sırası farklı.
    """
    raise NotImplementedError("SPEC 62: plan_farki")


def fark_json(fark: dict) -> dict:
    """plan_farki sonucunun JSON biçimi: IslemFarki → {anahtar, durum, dt, ayrinti};
    Unplanned → {feature, code, detail}."""
    raise NotImplementedError("SPEC 62: fark_json")
