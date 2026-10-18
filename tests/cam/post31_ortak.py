"""SPEC 31 testlerinin ortak yardımcıları: örnek profiller, kurulum, güvenlik durumları, okuma hataları.

Testler yalnız SPEC 31 metninden, SPEC 30 arayüzünden ve SPEC 04 altın yolundan yazıldı; `cam/post/`
uygulama kodu okunmadı (iskelet imzaları dışında).
"""

from __future__ import annotations

import re
from dataclasses import replace

import pytest

from cam.gcode import DrillOp
from cam.model import CamError, MachineProfile, Move, Toolpath
from cam.post import builtin_machines, post
from tests.cam.post_ortak import G0, G1, altin_yol, kurulum, takim

SIN_M = "ORNEK-SINUMERIK-DIK"
HEI_M = "ORNEK-HEIDENHAIN-DIK"
L = 100.0  # mm, takım ölçü boyu
RPM = 6000.0
TOL = 0.5e-3 + 1e-9  # uç toleransı (3 ondalık)

# İş sıfırı (makine koordinatı): Z kursu [−500, 0], L = 100 → z_ölçü = z − 100.
KURULUM = kurulum((0.0, 0.0, -200.0))


def ornek(ad: str) -> MachineProfile:
    """Örnek profil; SPEC 31 profilleri kod commit'inde gelir, o zamana dek test "uygulanmamış"."""
    ms = builtin_machines()
    if ad not in ms:
        raise NotImplementedError(f"SPEC 31: örnek profil {ad} henüz yok")
    return ms[ad]


def altin(ad: str) -> MachineProfile:
    """Altın metin profili: tool_change_z = None kopyası (SPEC 30 K12 gibi)."""
    return replace(ornek(ad), tool_change_z=None)


def iso_esi(m: MachineProfile) -> MachineProfile:
    """Aynı sınırlı Fanuc profili: güvenlik mesajlarını dilden bağımsız karşılaştırmak için."""
    return replace(m, controller="fanuc", presets=None)


def satirlar(text: str) -> list[str]:
    assert text.endswith("\n")
    return text[:-1].split("\n")


def drill(kind: str, retract: str) -> DrillOp:
    return DrillOp(
        "delik",
        takim(1, L=L),
        rpm=RPM,
        start=(10.0, 10.0, 5.0),
        holes=[(10.0, 10.0), (30.0, 10.0), (30.0, 25.0)],
        z=-12.0,
        r=1.0,
        feed=150.0,
        kind=kind,
        q=4.0 if kind == "G83" else None,
        retract=retract,
    )


DELIKLER = [("G81", "G98"), ("G81", "G99"), ("G83", "G98"), ("G83", "G99")]


def xy_hizli_alcakta() -> Toolpath:
    """Kesmeden sonra Z −1'de XY hızlı hareket (stock_top = 0 altında: SPEC 04 Ek C)."""
    return Toolpath(
        "alcak",
        takim(1, L=L),
        (0.0, 0.0, 5.0),
        rpm=RPM,
        moves=[
            Move(G1, (0.0, 0.0, -1.0), feed=100.0),
            Move(G0, (20.0, 0.0, -1.0)),
            Move(G0, (20.0, 0.0, 5.0)),
        ],
    )


def guvenlik_durumlari():
    """(ad, ops, kurulum, post kwargs): hepsi CamError olmalı (SPEC 04 Ek B/C, SPEC 30)."""
    yol = altin_yol(takim(1, L=L))
    return [
        ("alcak safe_z", [yol], KURULUM, dict(safe_z=-2.0)),
        ("stock_top altinda XY hizli", [xy_hizli_alcakta()], KURULUM, dict(safe_z=5.0, stock_top=0.0)),
        ("X kursu disi", [yol], kurulum((395.0, 0.0, -200.0)), dict(safe_z=5.0)),
        ("Z kursu disi", [yol], kurulum((0.0, 0.0, 0.0)), dict(safe_z=5.0)),
        ("devir siniri", [replace(yol, rpm=20000.0)], KURULUM, dict(safe_z=5.0)),
    ]


def ayni_mesaj(m: MachineProfile, ops, setup, kw) -> None:
    """Dilin çıktısı ISO eşiyle aynı CamError mesajıyla reddediliyor."""
    with pytest.raises(CamError) as iso:
        post(ops, iso_esi(m), setup, **kw)
    with pytest.raises(CamError, match=re.escape(str(iso.value))):
        post(ops, m, setup, **kw)


def satir_hatasi(fn, text: str) -> None:
    """Okuyucu CamError verir, mesajda 'satır <n>'."""
    with pytest.raises(CamError, match=r"satır \d+"):
        fn(text)
